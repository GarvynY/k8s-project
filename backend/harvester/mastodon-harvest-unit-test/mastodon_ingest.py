import re
import time
import random
import logging
from datetime import datetime, timezone

from mastodon import Mastodon
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from geopy.geocoders import Nominatim
from elasticsearch8 import Elasticsearch, helpers

# —— 日志配置 —— 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# —— Mastodon 凭据 —— （请替换为你的真实值）
MASTODON_CLIENT_ID     = "2BFvlyAmZRT3id9ZKNJJbXD6-nPPh8jo2WJaHTmQ1bA"
MASTODON_CLIENT_SECRET = "FQpO_BwYURSno8vbkVkk5USCZPA9SAzI_G9FUMts4bo"
MASTODON_ACCESS_TOKEN  = "Tvx3jwk5Ilz4ixUzG_DTrNny98G4RYfQym8sVDez9F8"
API_BASE_URL           = "https://mastodon.social"

# —— 配置 —— 
HASHTAG      = "ausvotes"
PAGE_SIZE    = 40
TARGET_COUNT = 300
INDEX_NAME   = "mastodon_election_test"

CITY_COORDS = {
    "Sydney":    "-33.868820,151.209296", "Melbourne": "-37.813629,144.963058",
    "Brisbane":  "-27.469770,153.025131", "Perth":      "-31.950527,115.860458",
    "Adelaide":  "-34.928497,138.600739", "Canberra":  "-35.280937,149.130009",
    "Hobart":    "-42.882137,147.327195", "Darwin":     "-12.463440,130.845642",
    "Gold Coast":"-28.016667,153.400000"
}
CITY_CHOICES = list(CITY_COORDS.keys())

logging.info("Initializing Mastodon client and tools")
masto = Mastodon(
    client_id=MASTODON_CLIENT_ID,
    client_secret=MASTODON_CLIENT_SECRET,
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=API_BASE_URL
)
sentiment_analyzer = SentimentIntensityAnalyzer()
geolocator = Nominatim(user_agent="fission_mastodon_ingest")


def clean_content(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()

def contains_keyword(text: str) -> bool:
    kws = ["ausvotes", "election", "vote", "选举", "投票"]
    return any(kw in text.lower() for kw in kws)

def get_time_of_day(ts_iso: str) -> str:
    h = datetime.fromisoformat(ts_iso).hour
    return "凌晨" if h < 6 else "上午" if h < 12 else "下午" if h < 18 else "晚上"

def get_day_of_week(ts_iso: str) -> str:
    return ["周一","周二","周三","周四","周五","周六","周日"][datetime.fromisoformat(ts_iso).weekday()]

def analyze_sentiment(text: str):
    vs = sentiment_analyzer.polarity_scores(text)
    s = vs["compound"]
    return s, ("积极" if s >= 0.05 else "消极" if s <= -0.05 else "中性")

def infer_location(account) -> str:
    for f in getattr(account, "fields", []):
        if "location" in f.get("name", "").lower():
            val = re.sub(r',?\s*Australia$', '', f.get("value", ""))
            for c in CITY_CHOICES:
                if re.search(rf"\b{re.escape(c)}\b", val, re.IGNORECASE):
                    return c
    return random.choice(CITY_CHOICES)

def geocode_location(loc: str) -> str:
    return CITY_COORDS.get(loc, "")

def main():
    logging.info("Function start")
    rows = []
    max_id = None

    # 抓取
    fetch_start = time.time()
    logging.info("Begin fetching posts")
    while len(rows) < TARGET_COUNT:
        to_fetch = min(PAGE_SIZE, TARGET_COUNT - len(rows))
        try:
            statuses = masto.timeline_hashtag(HASHTAG, limit=to_fetch, max_id=max_id)
        except Exception as e:
            logging.error(f"Fetch error: {e}")
            break
        if not statuses:
            logging.info("No more statuses, exit fetch loop")
            break

        for s in statuses:
            ts  = s.created_at.astimezone(timezone.utc).isoformat()
            txt = clean_content(s.content)
            if not contains_keyword(txt): continue
            score, label = analyze_sentiment(txt)
            loc  = infer_location(s.account)
            geo  = geocode_location(loc)
            rows.append({
                "id":               str(s.id),
                "created_at":       ts,
                "post_time_of_day": get_time_of_day(ts),
                "post_day_of_week": get_day_of_week(ts),
                "content":          txt,
                "sentiment_score":  score,
                "emotion_label":    label,
                "location":         loc,
                "geolocation":      geo,
            })
            if len(rows) >= TARGET_COUNT:
                break

        max_id = int(statuses[-1].id) - 1
        logging.info(f"Fetched {len(rows)}/{TARGET_COUNT}")
        time.sleep(1)

    logging.info(f"Fetch complete in {time.time()-fetch_start:.1f}s")

    # 写入 ES
    logging.info("Connecting to Elasticsearch")
    es = Elasticsearch(
        [{"host": "elasticsearch-master.elastic.svc.cluster.local",
          "port": 9200, "scheme": "https"}],
        basic_auth=("elastic", "elastic"),
        verify_certs=False,
        ssl_show_warn=False
    )

    logging.info("Begin bulk insert")
    bulk_start = time.time()
    try:
        success, _ = helpers.bulk(es, [
            {"_index": INDEX_NAME, "_id": r["id"], "_source": r}
            for r in rows
        ], stats_only=True)
        logging.info(f"Bulk indexed {success} docs")
    except Exception as e:
        logging.error(f"Bulk error: {e}")
        success = 0

    logging.info(f"Bulk complete in {time.time()-bulk_start:.1f}s")
    return {"indexed_count": success}

