"""
COMP90024 Cluster and Cloud Computing - Assignment 2
Big Data Analytics on the Cloud

Team Information:
Team Name: COMP90024_team_43
Team Members:
- Linyao ZHOU     (Student ID: 1619649)
- Yihao SANG      (Student ID: 1562582)
- Xiwen CHEN      (Student ID: 1542252)
- Yuan GAO        (Student ID: 1602894)
- Yao ZHAO        (Student ID: 1695969)

This file is part of the team's solution for Assignment 2,
demonstrating the use of cloud technologies (Kubernetes, Fission,
ElasticSearch) for social media data analytics related to Australia.
"""
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

BLUESKY_HANDLE       = "shangguanmuxian2b.bsky.social"
BLUESKY_APP_PASSWORD = "vtgy-ybqk-kxcb-v6gt"
SESSION_URL  = "https://bsky.social/xrpc/com.atproto.server.createSession"
SEARCH_URL   = "https://api.bsky.social/xrpc/app.bsky.feed.searchPosts"

PAGE_SIZE    = 25     # each page
BATCH_SIZE   = 50     # batch size
MAX_RETRIES  = 3      # retry
RETRY_DELAY  = 3      # retry sec

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

STATE_DOC_ID = "bluesky_cursor_state"

def load_state():
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
    """save state"""
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    es.index(
        index=ES_INDEX,
        id=STATE_DOC_ID,
        body=state
    )
    logging.info(f"state saved：count: {state['batch_num']}, total count: {state['processed_count']} , cursor={state['cursor'][:20]}...")

def get_jwt():
    """JWT token + retry"""
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
            raise RuntimeError(f"error JWT：{resp.text}")
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logging.warning(f"JWT failed，retry ({attempt+1}/{MAX_RETRIES}): {e}")
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
    jwt = get_jwt()
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Origin":        "https://bsky.app",
        "User-Agent":    "python-requests"
    }

    # page set
    cursor = state.get("cursor")
    
    batch_posts = []
    page_count = 0
    final_cursor = cursor  # record cursor pos
    
    # loop page
    while len(batch_posts) < BATCH_SIZE:
        page_count += 1
        cursor_display = f"{cursor[:15]}..." if cursor else "None"
        logging.info(f"count : {page_count} page data (cursor={cursor_display})")
        
        # params
        params = {"q": SEARCH_QUERY, "limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        
        try:
            r = requests.get(SEARCH_URL, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            posts = data.get("posts", [])
            
            if not posts:
                logging.info("no more data")
                break
                
            logging.info(f" {len(posts)} entries")
            
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
                    logging.info(f"reach batch size ({BATCH_SIZE})")
                    break
            
            # next page cursor
            new_cursor = data.get("cursor")
            if not new_cursor:
                logging.info("no more data")
                break
                
            final_cursor = cursor = new_cursor
            time.sleep(1)
            
        except Exception as e:
            logging.error(f"failed: {e}")
            break
    
    logging.info(f"completed: count {len(batch_posts)}")
    
    return batch_posts, {
        "cursor": final_cursor
    }

def save_to_es(rows):
    """ES"""
    if not rows:
        return 0
    
    actions = [
        {"_index": ES_INDEX, "_id": row["uri"], "_source": row}
        for row in rows
    ]
    
    success, errors = helpers.bulk(es, actions, stats_only=True)
    if errors:
        logging.warning(f" {errors} errors")
    
    return success

def process_batches(batch_count=1):
    state = load_state()
    batch_num = state.get("batch_num", 0)
    processed_count = state.get("processed_count", 0)
    
    logging.info(f"current batch {batch_num}，completed：{processed_count}")
    
    total_processed = 0
    
    for i in range(batch_count):
        current_batch = batch_num + 1
        logging.info(f"===== batch #{current_batch} =====")
        
        batch_data, batch_state = fetch_batch(state)
        
        if not batch_data:
            logging.info(f"batch #{current_batch} no more data")
            break
        
        saved_count = save_to_es(batch_data)
        logging.info(f"batch #{current_batch}saved {saved_count} ")
        
        total_processed += saved_count
        state.update(batch_state)
        state["batch_num"] = current_batch
        state["processed_count"] = processed_count + total_processed
        
        save_state(state)
        
        if i < batch_count - 1:
            time.sleep(2)
    
    return {
        "batches_processed": min(batch_count, current_batch - batch_num + 1),
        "records_processed": total_processed,
        "total_processed": state["processed_count"]
    }

def main(context=None, data=None):
    try:
        batch_count = 1
        if isinstance(data, dict) and "batch_count" in data:
            try:
                batch_count = max(1, int(data["batch_count"]))
            except:
                pass
                
        result = process_batches(batch_count)
        
        return f"completed： {result['batches_processed']} ，{result['records_processed']} ，{result['total_processed']} 条"
    except Exception as e:
        logging.exception("error")
        return f"error：{e}"
