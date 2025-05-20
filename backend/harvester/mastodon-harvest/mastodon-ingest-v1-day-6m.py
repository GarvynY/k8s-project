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
from datetime import datetime, date, time as dtime, timezone, timedelta
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
API_BASE_URL           = "https://mastodon.social"

HASHTAG    = "ausvotes"
PAGE_SIZE  = 1000   # page 1000 
INDEX_NAME = "mastodon_election_test"

# initialize mastodon 
masto = Mastodon(
    client_id=MASTODON_CLIENT_ID,
    client_secret=MASTODON_CLIENT_SECRET,
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=API_BASE_URL
)
sentiment_analyzer = SentimentIntensityAnalyzer()


def clean_content(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html)).strip()


def contains_keyword(text: str) -> bool:
    kws = ["ausvotes", "election", "vote", "选举", "投票"]
    return any(kw in text.lower() for kw in kws)


def format_time_of_day(dt: datetime) -> str:
    h = dt.hour
    return "Night"     if h < 6 else \
           "Morning"   if h < 12 else \
           "Afternoon" if h < 18 else \
           "Evening"


def format_day_of_week(dt: datetime) -> str:
    return dt.strftime('%A')


def analyze_sentiment(text: str):
    vs = sentiment_analyzer.polarity_scores(text)
    s = vs["compound"]
    label = "positive" if s > 0 else "negative" if s < 0 else "neutral"
    return s, label


def main():
    logging.info("=== Historical ingest per-day start ===")
    today      = datetime.now(timezone.utc).date()
    six_months = today - relativedelta(months=6)
    es = Elasticsearch(
        [{"host":"elasticsearch-master.elastic.svc.cluster.local","port":9200,"scheme":"https"}],
        basic_auth=("elastic","elastic"),
        verify_certs=False, ssl_show_warn=False
    )

    grand_total = 0
    current     = today

    while current > six_months:
        day_start = datetime.combine(current - timedelta(days=1), dtime.min, tzinfo=timezone.utc)
        day_end   = datetime.combine(current,            dtime.min, tzinfo=timezone.utc)
        logging.info(f"--- Ingesting day: {day_start.date()} ---")

        day_total = 0
        max_id    = None
        round_num = 0

        while True:
            round_num += 1
            logging.info(f"Day {day_start.date()} Round {round_num}: fetching up to {PAGE_SIZE} posts (max_id={max_id})")
            try:
                statuses = masto.timeline_hashtag(HASHTAG, limit=PAGE_SIZE, max_id=max_id)
            except Exception as e:
                logging.error(f"Day {day_start.date()} Round {round_num}: fetch error: {e}")
                break
            if not statuses:
                logging.info(f"Day {day_start.date()} Round {round_num}: no more statuses, exiting")
                break

            ops, times = [], []
            for s in statuses:
                dt = s.created_at.astimezone(timezone.utc)
                if dt >= day_end:
                    continue
                if dt < day_start:
                    logging.info(f"Day {day_start.date()} Round {round_num}: reached before {day_start.date()}, stop paging")
                    statuses = []
                    break

                txt = clean_content(s.content)
                if not contains_keyword(txt):
                    continue

                score, label = analyze_sentiment(txt)
                acct_str     = getattr(s.account, "acct", "")
                reblogs      = getattr(s, "reblogs_count", 0)
                favs         = getattr(s, "favourites_count", 0)
                url          = getattr(s, "url", "")

                ops.append({
                    "_index": INDEX_NAME,
                    "_id":     str(s.id),
                    "_source": {
                        "id":               str(s.id),
                        "created_at":       dt.isoformat(),
                        "post_time_of_day": format_time_of_day(dt),
                        "post_day_of_week": format_day_of_week(dt),
                        "content":          txt,
                        "sentiment_score":  score,
                        "emotion_label":    label,
                        "account":          {"acct": acct_str},
                        "reblogs_count":    reblogs,
                        "favourites_count": favs,
                        "url":               url
                    }
                })
                times.append(dt)

            if ops:
                first, last = min(times), max(times)
                logging.info(f"Day {day_start.date()} Round {round_num}: indexing {len(ops)} docs from {first} to {last}")
                success, errors = helpers.bulk(es, ops, raise_on_error=False, stats_only=False)
                day_total   += success
                grand_total += success
                if errors:
                    logging.error(f"Day {day_start.date()} Round {round_num}: {len(errors)} errors (sample {errors[:3]})")
                else:
                    logging.info(f"Day {day_start.date()} Round {round_num}: successfully indexed {success} docs")
            else:
                logging.info(f"Day {day_start.date()} Round {round_num}: no valid docs, skip indexing")

            if not statuses:
                break

            max_id = int(statuses[-1].id) - 1
            time.sleep(1)

        logging.info(f"=== Day {day_start.date()} complete, day_total={day_total} ===")
        current -= timedelta(days=1)

    logging.info(f"=== All done, grand_total={grand_total} ===")
    return {"indexed_count": grand_total}

