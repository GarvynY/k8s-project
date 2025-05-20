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


# harvest_and_index_hardcoded.py

import json
import requests
from elasticsearch import Elasticsearch, helpers

def main():
    # 1. Mastodon Token（硬编码测试用）
    token = "cDWlSYHFFEPxIFpkrTf2ss5kAB7hOekUQ7DY3dglm4E"
    masto_url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 拉取数据
    resp = requests.get(masto_url, headers=headers, timeout=10)
    resp.raise_for_status()
    docs = resp.json()  # 列表，每项是一个 dict

    # 3. ES 客户端初始化（全部硬编码）
    es = Elasticsearch(
        [
            {
                "host": "elasticsearch-master.elastic.svc.cluster.local",
                "port": 9200,
                "scheme": "https",
            }
        ],
        basic_auth=("elastic", "elastic"),
        verify_certs=False,     # 跳过自签名证书校验
        ssl_show_warn=False,    # 不打印 InsecureRequest 警告
    )

    index_name = "observations"

    # 4. 确保索引存在
    if not es.indices.exists(index=index_name):
        mapping = {
            "mappings": {
                "properties": {
                    "id":                {"type": "keyword"},
                    "created_at":        {"type": "date"},
                    "visibility":        {"type": "keyword"},
                    "language":          {"type": "keyword"},
                    "content":           {"type": "text"},
                    "account":           {"type": "object"},
                    "media_attachments": {"type": "nested"},
                }
            }
        }
        es.indices.create(index=index_name, body=mapping)

    # 5. 批量写入
    actions = [
        {
            "_index": index_name,
            "_id":     doc["id"],
            "_source": doc
        }
        for doc in docs
    ]
    success_count, _ = helpers.bulk(es, actions, stats_only=True)

    # 6. 返回结果
    return json.dumps({
        "indexed_count": success_count,
        "index": index_name
    })

