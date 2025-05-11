#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, time
import requests
from datetime import datetime, timezone
from elasticsearch import Elasticsearch, helpers
from dotenv import load_dotenv

# —— 加载配置 —— #
load_dotenv()
SERVICE = os.getenv("https://bsky.social")       # e.g. https://bsky.social
HANDLE  = os.getenv("shangguanmuxian2b.bsky.social")        # 你的 bsky 账号
PASSWORD= os.getenv("vtgy-ybqk-kxcb-v6gt")

ES_HOST     = os.getenv("ES_HOST")           # e.g. http://localhost:9200
ES_INDEX    = os.getenv("ES_INDEX")          # aus_election_2025

KEYWORDS    = ["auspol","ausvotes","AustraliaElection"]
START_DATE  = datetime(2025,1,1,tzinfo=timezone.utc)
BATCH_SIZE  = 50
ES_BULK_SIZE= 500
DELAY       = 1.0

# —— 初始化 Elasticsearch —— #
es = Elasticsearch([ES_HOST])
if not es.indices.exists(index=ES_INDEX):
    es.indices.create(index=ES_INDEX, body={
      "mappings": {
        "properties": {
          "uri":         {"type":"keyword"},
          "createdAt":   {"type":"date"},
          "text":        {"type":"text"},
          "author":      {"properties":{"handle":{"type":"keyword"},"displayName":{"type":"text"}}},
          "keywords":    {"type":"keyword"}
        }
      }
    })

# —— 登录 BlueSky —— #
resp = requests.post(
    f"{SERVICE}/xrpc/com.atproto.server.createSession",
    json={"identifier": HANDLE, "password": PASSWORD}
)
resp.raise_for_status()
token = resp.json()["accessJwt"]
HEADERS = {"Authorization": f"Bearer {token}"}

def crawl_keyword(q):
    cursor = None
    while True:
        params = {"type":"posts","q":q,"limit":BATCH_SIZE}
        if cursor: params["cursor"] = cursor
        r = requests.get(
            f"{SERVICE}/xrpc/com.atproto.search.search",
            params=params, headers=HEADERS
        )
        r.raise_for_status()
        data = r.json()
        posts = data.get("posts",[])
        if not posts:
            break
        for p in posts:
            created = datetime.fromisoformat(p["indexedAt"].replace("Z","+00:00"))
            if created < START_DATE:
                return
            yield p
        cursor = data.get("cursor")
        time.sleep(DELAY)

def format_action(post, keyword):
    return {
      "_index": ES_INDEX,
      "_id":    post["uri"],
      "_source": {
        "uri":        post["uri"],
        "createdAt":  post["indexedAt"],
        "text":       post["record"]["text"],
        "author": {
          "handle":      post["author"]["handle"],
          "displayName": post["author"].get("displayName","")
        },
        "keywords":   [keyword]
      }
    }

def main():
    bulk = []
    for kw in KEYWORDS:
        print(f"爬取关键词 {kw}")
        for post in crawl_keyword(kw):
            bulk.append(format_action(post, kw))
            if len(bulk) >= ES_BULK_SIZE:
                helpers.bulk(es, bulk)
                print(f"  写入 {len(bulk)} 条")
                bulk.clear()
    if bulk:
        helpers.bulk(es, bulk)
        print(f"最后写入 {len(bulk)} 条")
    print("全部完成")

if __name__=="__main__":
    main()

