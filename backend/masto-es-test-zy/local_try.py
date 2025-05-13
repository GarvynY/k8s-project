#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
from datetime import datetime, timezone
from mastodon import Mastodon

# —— 配置 —— #
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN", "OAe_XIfSurn6S8Cp5RjVlhacOmFLSqI1Pb6w6Zdaog0")
MASTODON_API_BASE_URL = os.getenv("MASTODON_API_BASE_URL", "https://mastodon.au")

OUTPUT_FILE = os.getenv("OUTPUT_FILE", "aus_election_2025.jsonl")

HASHTAGS = [
    "auspol",
    "ausvotes",
    "AustraliaElection",
    # 可加上 "澳大利亚大选"
]
START_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)
BATCH_SIZE = 40
REQUEST_DELAY = 1.0   # 秒

mastodon = Mastodon(
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=MASTODON_API_BASE_URL
)

def crawl_hashtag(tag):
    max_id = None
    while True:
        statuses = mastodon.timeline_hashtag(
            tag,
            limit=BATCH_SIZE,
            max_id=max_id
        )
        if not statuses:
            return
        for st in statuses:
            if st["created_at"] < START_DATE:
                return
            yield st

        # 强制把 id 转成 int，再减 1
        last_id = int(statuses[-1]["id"])
        max_id = last_id - 1
        time.sleep(REQUEST_DELAY)


def format_status(status):
    return {
        "id": status["id"],
        "created_at": status["created_at"].isoformat(),
        "content": status["content"],
        "account": {
            "id": status["account"]["id"],
            "acct": status["account"]["acct"],
            "display_name": status["account"]["display_name"]
        },
        "tags": [t["name"] for t in status["tags"]]
    }


def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout:
        total = 0
        for tag in HASHTAGS:
            print(f"开始爬取 #{tag} …")
            for status in crawl_hashtag(tag):
                fout.write(json.dumps(format_status(status), ensure_ascii=False) + "\n")
                total += 1
                if total % 100 == 0:
                    print(f"  已保存 {total} 条记录…")
        print(f"完成，共保存 {total} 条记录到 `{OUTPUT_FILE}`")


if __name__ == "__main__":
    main()