# mastodon_ingest_stream.py

import re
import time
import logging
from datetime import datetime, timezone

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
PAGE_SIZE  = 40
INDEX_NAME = "mastodon_election_raw"

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


def analyze_sentiment(text: str):
    vs = sentiment_analyzer.polarity_scores(text)
    s = vs["compound"]
    label = "positive" if s > 0 else "negative" if s < 0 else "neutral"
    return s, label


def main():
    logging.info("=== Incremental ingest start ===")
    es = Elasticsearch(
        [{"host":"elasticsearch-master.elastic.svc.cluster.local","port":9200,"scheme":"https"}],
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

    new_since_id = since_id or 0
    total_new = 0

    # get new timestamp    
    while True:
        statuses = masto.timeline_hashtag(
            HASHTAG,
            limit=PAGE_SIZE,
            since_id=since_id
        )
        if not statuses:
            logging.info("No more new statuses")
            break

        ops = []
        times = []
        for s in statuses:
            sid = int(s.id)
            dt  = s.created_at.astimezone(timezone.utc)
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
                "_id":     str(sid),
                "_source": {
                    "id":               str(sid),
                    "created_at":       dt.isoformat(),
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
            new_since_id = max(new_since_id, sid)

        if ops:
            first, last = min(times), max(times)
            logging.info(
                f"Indexing {len(ops)} new docs from {first.isoformat()} to {last.isoformat()}"
            )
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
        since_id = new_since_id

    logging.info(f"=== Incremental ingest complete, total new: {total_new}, new_since_id={new_since_id} ===")
    return {"indexed_count": total_new}

