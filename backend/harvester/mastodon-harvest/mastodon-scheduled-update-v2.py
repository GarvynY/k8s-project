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
import re
import time
import logging
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

from mastodon import Mastodon
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from elasticsearch8 import Elasticsearch, helpers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

MASTODON_CLIENT_ID     = "2BFvlyAmZRT3id9ZKNJJbXD6-nPPh8jo2WJaHTmQ1bA"
MASTODON_CLIENT_SECRET = "FQpO_BwYURSno8vbkVkk5USCZPA9SAzI_G9FUMts4bo"
MASTODON_ACCESS_TOKEN  = "Tvx3jwk5Ilz4ixUzG_DTrNny98G4RYfQym8sVDez9F8"
API_BASE_URL           = "https://mastodon.au"

KEYWORDS   = [
    'Australia Election', 'AusPol', 'AUSElection',
    'ausvotes2025', '#ausvotes2025', 'auspol2025', '#auspol2025', 'ausvotes',
    'Albanese', 'Dutton', 'Bandt',
    'Labor', 'Liberal', 'Greens'
]
PAGE_SIZE  = 100
INDEX_NAME = "mastodon_election_raw"

CITY_COORDS = {
    "Sydney":    "-33.868820,151.209296",
    "Melbourne": "-37.813629,144.963058",
    "Brisbane":  "-27.469770,153.025131",
    "Perth":      "-31.950527,115.860458",
    "Adelaide":  "-34.928497,138.600739",
    "Canberra":  "-35.280937,149.130009",
    "Hobart":    "-42.882137,147.327195",
    "Darwin":     "-12.463440,130.845642",
    "Gold Coast":"-28.016667,153.400000"
}

masto = Mastodon(
    client_id=MASTODON_CLIENT_ID,
    client_secret=MASTODON_CLIENT_SECRET,
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=API_BASE_URL
)
sentiment_analyzer = SentimentIntensityAnalyzer()


def clean_content(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()


def infer_location(account) -> str:
    for f in getattr(account, "fields", []):
        if "location" in f.get("name", "").lower():
            val = f.get("value", "").split(",")[0].strip()
            if val in CITY_COORDS:
                return val
    return ""


def main():
    logging.info("=== Incremental multi-keyword ingest start ===")

    # get latest es record
    es = Elasticsearch(
        [{"host":"elasticsearch-master.elastic.svc.cluster.local",
          "port":9200, "scheme":"https"}],
        basic_auth=("elastic","elastic"),
        verify_certs=False, ssl_show_warn=False
    )
    res = es.search(
        index=INDEX_NAME,
        size=1,
        sort=[{"created_at": {"order": "desc"}}],
        _source=["id"]
    )
    hits = res["hits"]["hits"]
    since_id = int(hits[0]["_source"]["id"]) if hits else None
    logging.info(f"Starting since_id={since_id}")

    total_new = 0
    new_since_id = since_id or 0
    seen_ids = set()

    # fetch by pages
    for kw in KEYWORDS:
        tag = kw.lstrip("#")
        logging.info(f">>> Keyword: {kw}")
        max_id = None
        round_num = 0

        while True:
            round_num += 1
            logging.info(f"Keyword {kw} Round {round_num}: fetching up to {PAGE_SIZE} posts "
                         f"(since_id={since_id}, max_id={max_id})")
            try:
                statuses = masto.timeline_hashtag(
                    hashtag=tag,
                    limit=PAGE_SIZE,
                    since_id=since_id,
                    max_id=max_id
                )
            except Exception as e:
                logging.error(f"Keyword {kw} Round {round_num}: fetch error: {e}")
                break

            if not statuses:
                logging.info(f"Keyword {kw} Round {round_num}: no more statuses")
                break

            ops, times = [], []
            for s in statuses:
                sid = int(s.id)
                if sid <= (since_id or 0) or sid in seen_ids:
                    continue

                dt = s.created_at.astimezone(timezone.utc)
                txt = clean_content(s.content)
                # check keyword
                if tag.lower() not in txt.lower():
                    continue

                vs = sentiment_analyzer.polarity_scores(txt)
                score = vs["compound"]
                label = "positive" if score > 0 else "negative" if score < 0 else "neutral"

                acct_str = getattr(s.account, "acct", "")
                reblogs  = getattr(s, "reblogs_count", 0)
                favs     = getattr(s, "favourites_count", 0)
                url      = getattr(s, "url", "")

                loc = infer_location(s.account)
                geo = CITY_COORDS.get(loc)

                # construct doc
                doc = {
                    "id":               str(sid),
                    "created_at":       dt.isoformat(),
                    "post_time_of_day": dt.strftime("%p"),
                    "post_day_of_week": dt.strftime("%A"),
                    "content":          txt,
                    "sentiment_score":  score,
                    "emotion_label":    label,
                    "location":         loc,
                    "account":          acct_str,
                    "reblogs_count":    reblogs,
                    "favourites_count": favs,
                    "url":               url
                }
                if geo:
                    doc["geolocation"] = geo

                ops.append({"_index": INDEX_NAME, "_id": str(sid), "_source": doc})
                times.append(dt)
                seen_ids.add(sid)
                new_since_id = max(new_since_id, sid)

            if ops:
                first, last = min(times), max(times)
                logging.info(f"Keyword {kw} Round {round_num}: indexing {len(ops)} docs "
                             f"from {first} to {last}")
                success, errors = helpers.bulk(
                    es, ops,
                    raise_on_error=False,
                    stats_only=False
                )
                total_new += success
                if errors:
                    logging.error(f"Encountered {len(errors)} errors, sample: {errors[:3]}")
                else:
                    logging.info(f"Successfully indexed {success} new docs")

            if len(statuses) < PAGE_SIZE:
                break

            max_id = int(statuses[-1].id) - 1
            time.sleep(1)

    logging.info(
        f"=== Incremental ingest complete: total new={total_new}, "
        f"new_since_id={new_since_id} ==="
    )
    return {"indexed_count": total_new}

