#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from mastodon import Mastodon
from elasticsearch import Elasticsearch, helpers
from datetime import datetime, timezone
import time
import os

# —— 配置 —— #
# Mastodon API 配置
MASTODON_ACCESS_TOKEN = "OAe_XIfSurn6S8Cp5RjVlhacOmFLSqI1Pb6w6Zdaog0"
MASTODON_API_BASE_URL = "https://mastodon.au"

# Elasticsearch 配置
ES_HOST = "http://172.29.158.30:9300 "
ES_INDEX = "aus_election_2025"

# 爬取设置
HASHTAGS = [
    "auspol",
    "ausvotes",
    "AustraliaElection",
]
START_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)
BATCH_SIZE = 40       # Mastodon 单次返回上限通常是 40
ES_BULK_SIZE = 500    # 每次 bulk 写入 ES 的数量
REQUEST_DELAY = 1.0   # ms，防止被限流

# —— 初始化客户端 —— #
mastodon = Mastodon(
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=MASTODON_API_BASE_URL
)

es = Elasticsearch([ES_HOST])

# 如果索引不存在，先建立一个简单 mapping
if not es.indices.exists(index=ES_INDEX):
    es.indices.create(index=ES_INDEX, body={
        "mappings": {
            "properties": {
                "id":          {"type": "keyword"},
                "created_at":  {"type": "date"},
                "content":     {"type": "text"},
                "account": {
                    "properties": {
                        "id":           {"type": "keyword"},
                        "acct":         {"type": "keyword"},
                        "display_name": {"type": "text"}
                    }
                },
                "tags": {"type": "keyword"}
            }
        }
    })


def crawl_hashtag(tag):
    """
    通过 /api/v1/timelines/tag/{tag} 向后翻页地拉取贴文，
    直到遇到比 START_DATE 更早的贴文为止。
    """
    max_id = None
    while True:
        statuses = mastodon.timeline_hashtag(
            tag,
            limit=BATCH_SIZE,
            max_id=max_id,
            only_local=False
        )
        if not statuses:
            break

        for st in statuses:
            if st["created_at"] < START_DATE:
                return
            yield st

        # 翻页：取最后一条的 id 减 1
        max_id = statuses[-1]["id"] - 1
        time.sleep(REQUEST_DELAY)


def format_action(status):
    """
    把 Mastodon status 转成 ES bulk API 的单条 action
    """
    return {
        "_index": ES_INDEX,
        "_id": str(status["id"]),   # 用 Mastodon 的 id 作为 ES _id
        "_source": {
            "id":          status["id"],
            "created_at":  status["created_at"],
            "content":     status["content"],
            "account": {
                "id":           status["account"]["id"],
                "acct":         status["account"]["acct"],
                "display_name": status["account"]["display_name"]
            },
            "tags": [t["name"] for t in status["tags"]]
        }
    }


def main():
    bulk_actions = []

    for tag in HASHTAGS:
        print(f"开始爬取 #{tag} …")
        for status in crawl_hashtag(tag):
            bulk_actions.append(format_action(status))
            # 达到批量大小就提交一次
            if len(bulk_actions) >= ES_BULK_SIZE:
                helpers.bulk(es, bulk_actions)
                print(f"  已写入 {len(bulk_actions)} 条数据到 ES")
                bulk_actions.clear()

    # 写入剩余
    if bulk_actions:
        helpers.bulk(es, bulk_actions)
        print(f"结束，共写入 {len(bulk_actions)} 条剩余数据到 ES")

    print("全部爬取完成。")


if __name__ == "__main__":
    main()