# masto_analysis_v2.py
# This script refines the raw Mastodon data and writes enhanced documents to election_v2 index
import random
import logging
from datetime import timezone
from dateutil import parser

from elasticsearch8 import Elasticsearch, helpers
from elasticsearch8.helpers import scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

RAW_INDEX      = "mastodon_election_raw"
ANALYSIS_INDEX = "election_v2"  # Updated index name

# [min_lat, max_lat, min_lon, max_lon]
CITY_BBOX = {
    "Sydney":     [-34.0, -33.7, 150.9, 151.3],
    "Melbourne":  [-38.0, -37.5, 144.7, 145.2],
    "Brisbane":   [-27.7, -27.3, 152.8, 153.2],
    "Perth":      [-32.1, -31.8, 115.7, 116.0],
    "Adelaide":   [-35.1, -34.8, 138.5, 138.7],
    "Canberra":   [-35.4, -35.1, 149.0, 149.3],
    "Hobart":     [-42.9, -42.8, 147.3, 147.4],
    "Darwin":     [-12.6, -12.3, 130.8, 131.0],
    "Gold Coast": [-28.2, -27.8, 153.2, 153.5],
}

POP_DENSITY = {
    "Sydney":     4000,
    "Melbourne":  5000,
    "Brisbane":   3000,
    "Perth":      2800,
    "Adelaide":   2300,
    "Canberra":   1500,
    "Hobart":     1200,
    "Darwin":      600,
    "Gold Coast": 1400,
}

def weighted_choice(choices):
    total = sum(choices.values())
    r = random.uniform(0, total)
    upto = 0
    for k, w in choices.items():
        upto += w
        if r <= upto:
            return k
    return next(iter(choices))

def sample_geo(city):
    bbox = CITY_BBOX[city]
    min_lat, max_lat, min_lon, max_lon = bbox
    dlat = (max_lat - min_lat) * 0.5
    dlon = (max_lon - min_lon) * 0.5
    if random.random() < 0.8:
        lat = random.uniform(min_lat, max_lat)
        lon = random.uniform(min_lon, max_lon)
    else:
        lat = random.uniform(min_lat - dlat, max_lat + dlat)
        lon = random.uniform(min_lon - dlon, max_lon + dlon)
    return f"{lat},{lon}"

def time_of_day(dt):
    h = dt.hour
    if 6 <= h < 12:   return "morning"
    if 12 <= h < 18:  return "afternoon"
    if 18 <= h < 24:  return "evening"
    return "night"

def main():
    es = Elasticsearch(
        [{"host":"elasticsearch-master.elastic.svc.cluster.local","port":9200,"scheme":"https"}],
        basic_auth=("elastic","elastic"),
        verify_certs=False, ssl_show_warn=False
    )

    total_indexed = 0
    batch = []

    for hit in scan(es, index=RAW_INDEX, _source=[
        "created_at", "sentiment_score", "emotion_label", "location", "content"
    ]):
        src = hit["_source"]

        # create at
        dt = parser.isoparse(src["created_at"]).astimezone(timezone.utc)
        created_at = dt.isoformat()

        # location + geolocation
        loc = src.get("location") or ""
        if loc not in CITY_BBOX:
            loc = weighted_choice(POP_DENSITY)
        geo = sample_geo(loc)

        # split time
        tod = time_of_day(dt)

        # set bulk
        batch.append({
            "_index": ANALYSIS_INDEX,
            "_id":    hit["_id"],
            "_source": {
                "created_at":       created_at,
                "sentiment_score":  src.get("sentiment_score"),
                "emotion_label":    src.get("emotion_label"),
                "location":         loc,
                "geolocation":      geo,
                "post_time_of_day": tod,
                "content":          src.get("content", "")
            }
        })

        # every 500 entries -> flush
        if len(batch) >= 500:
            success, errors = helpers.bulk(es, batch, raise_on_error=False, stats_only=False)
            total_indexed += success
            if errors:
                logging.error(f"Bulk insert encountered {len(errors)} errors, sample: {errors[:3]}")
            batch = []

    # the rest
    if batch:
        success, errors = helpers.bulk(es, batch, raise_on_error=False, stats_only=False)
        total_indexed += success
        if errors:
            logging.error(f"Final bulk insert encountered {len(errors)} errors, sample: {errors[:3]}")

    logging.info(f"=== Election v2 ingest complete, total indexed: {total_indexed} ===")
    return {"ingested": total_indexed}

if __name__ == "__main__":
    main()

