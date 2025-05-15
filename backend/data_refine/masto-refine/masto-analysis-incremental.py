# election_analysis_incremental.py
# This script is used to update the latest raw data in the mastodon table
# masto-analysis-incremental.py

import random
import logging
from datetime import timezone
from dateutil import parser

from elasticsearch8 import Elasticsearch, helpers

# —— 日志配置 ——
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

RAW_INDEX      = "mastodon_election_raw"
ANALYSIS_INDEX = "election_analysis"

# 城市边界框 [min_lat, max_lat, min_lon, max_lon]
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

# 人口密度，用于加权抽样
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
    min_lat, max_lat, min_lon, max_lon = CITY_BBOX[city]
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
    logging.info("=== Incremental analysis update start ===")
    es = Elasticsearch(
        [{"host":"elasticsearch-master.elastic.svc.cluster.local","port":9200,"scheme":"https"}],
        basic_auth=("elastic","elastic"),
        verify_certs=False, ssl_show_warn=False
    )

    # 1) 查最新分析索引时间
    resp = es.search(
        index=ANALYSIS_INDEX,
        size=1,
        sort=[{"created_at": {"order": "desc"}}],
        _source=["created_at"]
    )
    hits = resp["hits"]["hits"]
    since_ts = None
    if hits:
        since_ts = parser.isoparse(hits[0]["_source"]["created_at"]).astimezone(timezone.utc)
    logging.info(f"Starting update from {since_ts}")

    # 2) 构造查询 new raw 文档
    query = {"query": {"range": {"created_at": {"gt": since_ts.isoformat()}}}} if since_ts else None

    batch = []
    total = 0

    # 3) 一定要调用 helpers.scan 并传 client=es
    scan_kwargs = dict(
        index=RAW_INDEX,
        _source=["created_at","sentiment_score","emotion_label","location"]
    )
    if query:
        scan_kwargs["query"] = query

    # 这里改成 helpers.scan(client=es, ...)
    for hit in helpers.scan(client=es, **scan_kwargs):
        src = hit["_source"]
        dt = parser.isoparse(src["created_at"]).astimezone(timezone.utc)
        created_at = dt.isoformat()

        loc = src.get("location") or ""
        if loc not in CITY_BBOX:
            loc = weighted_choice(POP_DENSITY)
        geo = sample_geo(loc)
        tod = time_of_day(dt)

        batch.append({
            "_index": ANALYSIS_INDEX,
            "_id":    hit["_id"],
            "_source": {
                "created_at":       created_at,
                "sentiment_score":  src["sentiment_score"],
                "emotion_label":    src["emotion_label"],
                "location":         loc,
                "geolocation":      geo,
                "post_time_of_day": tod
            }
        })

        if len(batch) >= 500:
            success, errors = helpers.bulk(es, batch, raise_on_error=False, stats_only=False)
            total += success
            if errors:
                logging.error(f"Bulk insert errors: {len(errors)}; sample: {errors[:3]}")
            batch.clear()

    # 写入剩下的
    if batch:
        success, errors = helpers.bulk(es, batch, raise_on_error=False, stats_only=False)
        total += success
        if errors:
            logging.error(f"Final bulk insert errors: {len(errors)}; sample: {errors[:3]}")

    logging.info(f"=== Incremental update complete, total new indexed: {total} ===")
    return {"indexed_count": total}

