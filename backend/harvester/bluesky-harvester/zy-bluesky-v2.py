import os
import re
import time
import random
import logging
from datetime import datetime, timezone

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from geopy.geocoders import Nominatim
from elasticsearch import Elasticsearch, helpers

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ─── BlueSky 配置 ───
BLUESKY_HANDLE       = "shangguanmuxian2b.bsky.social"
BLUESKY_APP_PASSWORD = "vtgy-ybqk-kxcb-v6gt"
SESSION_URL  = "https://bsky.social/xrpc/com.atproto.server.createSession"
SEARCH_URL   = "https://api.bsky.social/xrpc/app.bsky.feed.searchPosts"

# ─── 分页与批处理配置 ───
PAGE_SIZE    = 25     # 每页API请求获取的数据量
BATCH_SIZE   = 50     # 每批次处理的数量
MAX_RETRIES  = 3      # 最大重试次数
RETRY_DELAY  = 3      # 重试延迟(秒)

SEARCH_QUERY = "ausvotes"

KEYWORDS = [
    "ausvotes", "australia election", "australian election",
    "election", "vote"
]

CITY_COORDS = {
    "Sydney":      "-33.868820,151.209296",
    "Melbourne":   "-37.813629,144.963058",
    "Brisbane":    "-27.469770,153.025131",
    "Perth":       "-31.950527,115.860458",
    "Adelaide":    "-34.928497,138.600739",
    "Canberra":    "-35.280937,149.130009",
    "Hobart":      "-42.882137,147.327195",
    "Darwin":      "-12.463440,130.845642",
    "Gold Coast":  "-28.016667,153.400000"
}
CITY_CHOICES = list(CITY_COORDS.keys())

sentiment_analyzer = SentimentIntensityAnalyzer()
geolocator = Nominatim(user_agent="bsky_city_extractor")

# ─── Elasticsearch 配置 ───
ES_HOST  = "https://elasticsearch-master.elastic.svc.cluster.local:9200"
ES_USER  = "elastic"
ES_PASS  = "elastic"
ES_INDEX = "bluesky-v2"

es = Elasticsearch(
    [ES_HOST],
    http_auth=(ES_USER, ES_PASS),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
)

# ─── 简化的状态管理 ───
STATE_DOC_ID = "bluesky_cursor_state"

def load_state():
    """读取处理状态，仅包含分页游标和统计数据"""
    try:
        doc = es.get(index=ES_INDEX, id=STATE_DOC_ID)["_source"]
        return {
            "cursor": doc.get("cursor"),
            "batch_num": doc.get("batch_num", 0),
            "processed_count": doc.get("processed_count", 0),
            "last_run": doc.get("last_run")
        }
    except:
        return {
            "cursor": None,
            "batch_num": 0,
            "processed_count": 0,
            "last_run": None
        }

def save_state(state):
    """保存处理状态"""
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    es.index(
        index=ES_INDEX,
        id=STATE_DOC_ID,
        body=state
    )
    logging.info(f"状态已保存：批次 {state['batch_num']}, 总处理 {state['processed_count']} 条, cursor={state['cursor'][:20]}...")

def get_jwt():
    """获取JWT令牌，添加重试逻辑"""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                SESSION_URL,
                json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json().get("data", resp.json())
            for key in ("accessJwt","access_jwt","jwt","encodedJwt"):
                if key in data:
                    return data[key]
            raise RuntimeError(f"无法获取JWT：{resp.text}")
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logging.warning(f"JWT获取失败，重试 ({attempt+1}/{MAX_RETRIES}): {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise

def clean_content(html: str) -> str:
    text = re.sub(r'<[^>]+>', '', html or "")
    return re.sub(r'\s+', ' ', text).strip()

def contains_keyword(text: str) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in KEYWORDS)

def get_time_of_day(ts_iso: str) -> str:
    h = datetime.fromisoformat(ts_iso).hour
    if h < 6:   return "early morning"
    if h < 12:  return "morning"
    if h < 18:  return "afternoon"
    return "evening"

def get_day_of_week(ts_iso: str) -> str:
    return ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][
        datetime.fromisoformat(ts_iso).weekday()
    ]

def analyze_sentiment(txt: str):
    vs = sentiment_analyzer.polarity_scores(txt)
    s = vs["compound"]
    if s >= 0.05:    return s, "positive"
    if s <= -0.05:   return s, "negative"
    return s, "medium"

def parse_iso_z(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)

def infer_location(account) -> str:
    for f in getattr(account, "fields", []):
        if "location" in f.get("name","").lower():
            val = f.get("value","") or ""
            val = re.sub(r'\s*,?\s*Australia$', '', val, flags=re.IGNORECASE).strip()
            spans = re.findall(r'<span>([^<]+)</span>', val)
            for city in spans:
                if city.strip().lower() in [c.lower() for c in CITY_CHOICES]:
                    return city.strip()
            text = re.sub(r'<[^>]+>', '', val)
            for c in CITY_CHOICES:
                if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE):
                    return c
    return ""

def geocode_location(loc: str):
    coord = CITY_COORDS.get(loc)
    if not coord:
        return None
    lat_str, lon_str = coord.split(",")
    lat, lon = float(lat_str), float(lon_str)
    # GeoJSON order: [lon, lat]
    return {"type": "Point", "coordinates": [lon, lat]}

def fetch_batch(state):
    """使用cursor获取一批数据，返回获取的数据和更新的状态"""
    jwt = get_jwt()
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Origin":        "https://bsky.app",
        "User-Agent":    "python-requests"
    }

    # 从状态中获取分页参数
    cursor = state.get("cursor")
    
    batch_posts = []
    page_count = 0
    final_cursor = cursor  # 记录最后一次使用的cursor
    
    # 循环获取页面直到达到批次大小
    while len(batch_posts) < BATCH_SIZE:
        page_count += 1
        cursor_display = f"{cursor[:15]}..." if cursor else "None"
        logging.info(f"获取第 {page_count} 页数据 (cursor={cursor_display})")
        
        # 准备请求参数
        params = {"q": SEARCH_QUERY, "limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        
        try:
            r = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            posts = data.get("posts", [])
            
            if not posts:
                logging.info("没有更多数据")
                break
                
            logging.info(f"获取到 {len(posts)} 条原始数据")
            
            # 处理本页数据
            for item in posts:
                view = item.get("post", item)
                rec = view.get("record", {})
                raw_ts = rec.get("createdAt")
                if not raw_ts:
                    continue

                ts_iso = parse_iso_z(raw_ts).astimezone(timezone.utc).isoformat()
                content = clean_content(rec.get("text",""))
                
                if not contains_keyword(content):
                    continue

                score, label = analyze_sentiment(content)
                author = view.get("author",{}).get("handle","")
                loc = infer_location(view.get("author",{})) or random.choice(CITY_CHOICES)
                geo = geocode_location(loc)

                batch_posts.append({
                    "uri":              view.get("uri",""),
                    "created_at":       ts_iso,
                    "post_time_of_day": get_time_of_day(ts_iso),
                    "post_day_of_week": get_day_of_week(ts_iso),
                    "content":          content,
                    "sentiment_score":  score,
                    "emotion_label":    label,
                    "author":           author,
                    "location":         loc,
                    "geolocation":      geo,
                })
                
                if len(batch_posts) >= BATCH_SIZE:
                    logging.info(f"已达到批次大小 ({BATCH_SIZE})")
                    break
            
            # 获取下一页的游标
            new_cursor = data.get("cursor")
            if not new_cursor:
                logging.info("无下一页游标，已到达数据末尾")
                break
                
            final_cursor = cursor = new_cursor
            time.sleep(1)  # 请求间隔
            
        except Exception as e:
            logging.error(f"获取数据失败: {e}")
            break
    
    logging.info(f"批次完成，获取到 {len(batch_posts)} 条符合条件的数据")
    
    # 返回数据和更新的状态 - 只需要保存最后使用的cursor
    return batch_posts, {
        "cursor": final_cursor
    }

def save_to_es(rows):
    """保存数据到ES"""
    if not rows:
        return 0
    
    actions = [
        {"_index": ES_INDEX, "_id": row["uri"], "_source": row}
        for row in rows
    ]
    
    success, errors = helpers.bulk(es, actions, stats_only=True)
    if errors:
        logging.warning(f"保存时出现 {errors} 个错误")
    
    return success

def process_batches(batch_count=1):
    """处理指定数量的批次"""
    # 加载状态
    state = load_state()
    batch_num = state.get("batch_num", 0)
    processed_count = state.get("processed_count", 0)
    
    logging.info(f"开始处理，当前批次：{batch_num}，已处理：{processed_count}")
    
    total_processed = 0
    
    # 处理指定数量的批次
    for i in range(batch_count):
        current_batch = batch_num + 1
        logging.info(f"===== 处理批次 #{current_batch} =====")
        
        # 获取一批数据
        batch_data, batch_state = fetch_batch(state)
        
        if not batch_data:
            logging.info(f"批次 #{current_batch} 没有数据，停止处理")
            break
        
        # 保存数据
        saved_count = save_to_es(batch_data)
        logging.info(f"批次 #{current_batch} 保存了 {saved_count} 条数据")
        
        # 更新状态
        total_processed += saved_count
        state.update(batch_state)
        state["batch_num"] = current_batch
        state["processed_count"] = processed_count + total_processed
        
        # 保存状态
        save_state(state)
        
        # 批次间隔
        if i < batch_count - 1:
            time.sleep(2)
    
    return {
        "batches_processed": min(batch_count, current_batch - batch_num + 1),
        "records_processed": total_processed,
        "total_processed": state["processed_count"]
    }

def main(context=None, data=None):
    try:
        # 从输入参数中获取批次数量
        batch_count = 1
        if isinstance(data, dict) and "batch_count" in data:
            try:
                batch_count = max(1, int(data["batch_count"]))
            except:
                pass
                
        result = process_batches(batch_count)
        
        return f"完成：处理了 {result['batches_processed']} 个批次，本次索引 {result['records_processed']} 条帖子，总计已处理 {result['total_processed']} 条"
    except Exception as e:
        logging.exception("处理失败")
        return f"错误：{e}"
