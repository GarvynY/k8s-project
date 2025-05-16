import os
import re
import time
import random
from datetime import datetime, timezone

import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from geopy.geocoders import Nominatim
from elasticsearch import Elasticsearch, helpers

# ─── BlueSky 配置 ───
BLUESKY_HANDLE       = "shangguanmuxian2b.bsky.social"
BLUESKY_APP_PASSWORD = "vtgy-ybqk-kxcb-v6gt"
SESSION_URL  = "https://bsky.social/xrpc/com.atproto.server.createSession"
SEARCH_URL   = "https://api.bsky.social/xrpc/app.bsky.feed.searchPosts"

PAGE_SIZE    = 100   # 每页最多拉取 100 条
TARGET_COUNT = 100   # 每次运行总共拉取 100 条

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
ES_INDEX = "bluesky_zy"

es = Elasticsearch(
    [ES_HOST],
    http_auth=(ES_USER, ES_PASS),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
)

# ─── 状态持久化（方案 2：按历史翻页） ───
STATE_DOC_ID = "ausvotes_state"

def load_state():
    """更改：读取上次运行存的最早时间戳 min_ts"""
    try:
        doc = es.get(index=ES_INDEX, id=STATE_DOC_ID)["_source"]
        return doc.get("min_ts")
    except:
        return None

def save_state(min_ts):
    """更改：保存本次运行抓到的最早时间戳"""
    es.index(
        index=ES_INDEX,
        id=STATE_DOC_ID,
        body={"min_ts": min_ts},
    )

def get_jwt():
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
    raise RuntimeError(f"can not get JWT：{resp.text}")

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

def fetch_posts():
    jwt = get_jwt()
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Origin":        "https://bsky.app",
        "User-Agent":    "python-requests"
    }

    # 更改：读取并初始化“历史翻页”的阈值时间
    last_min_ts = load_state() or "9999-12-31T23:59:59.999Z"
    min_ts_this_run = last_min_ts

    rows = []
    cursor = None

    while len(rows) < TARGET_COUNT:
        params = {"q": SEARCH_QUERY, "limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor

        r = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            break
        data = r.json()
        posts = data.get("posts", [])
        if not posts:
            break

        for item in posts:
            view = item.get("post", item)
            rec = view.get("record", {})
            raw_ts = rec.get("createdAt")
            if not raw_ts:
                continue

            ts_iso = parse_iso_z(raw_ts).astimezone(timezone.utc).isoformat()

            # 更改：只处理更早于上次 min_ts 的记录
            if ts_iso >= last_min_ts:
                continue

            # 更新本次运行的最早时间戳
            if ts_iso < min_ts_this_run:
                min_ts_this_run = ts_iso

            content = clean_content(rec.get("text",""))
            if not contains_keyword(content):
                continue

            score, label = analyze_sentiment(content)
            author = view.get("author",{}).get("handle","")
            loc = infer_location(view.get("author",{})) or random.choice(CITY_CHOICES)
            geo = geocode_location(loc)

            rows.append({
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
            if len(rows) >= TARGET_COUNT:
                break

        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(1)

    # 更改：存回本次运行抓到的最早时间戳
    save_state(min_ts_this_run)
    return rows

def save_to_es(rows):
    if not rows:
        return 0
    actions = [
        {"_index": ES_INDEX, "_id": row["uri"], "_source": row}
        for row in rows
    ]
    helpers.bulk(es, actions)
    return len(rows)

def main(context=None, data=None):
    try:
        posts = fetch_posts()
        count = save_to_es(posts)
        return f"完成：抓取并索引 {count} 条帖子到 ES 索引 '{ES_INDEX}'"
    except Exception as e:
        return f"错误：{e}"