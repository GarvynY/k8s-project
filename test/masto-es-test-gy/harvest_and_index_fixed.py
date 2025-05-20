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


import os
import json
import requests
from elasticsearch import Elasticsearch, helpers

def main():
    # 1. Mastodon Token（从环境变量读取，或使用默认）
    token = os.environ.get("ACCESS_TOKEN", "cDWlSYHFFEPxIFpkrTf2ss5kAB7hOekUQ7DY3dglm4E")
    masto_url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 拉取数据
    resp = requests.get(masto_url, headers=headers, timeout=10)
    resp.raise_for_status()
    docs = resp.json()

    # 3. ES 连接配置
    es_host = os.environ.get("ES_HOST", "127.0.0.1")
    es_port = int(os.environ.get("ES_PORT", 9200))
    es_user = os.environ.get("ES_USERNAME", "elastic")
    es_pass = os.environ.get("ES_PASSWORD", "elastic")
    es_scheme = os.environ.get("ES_SCHEME", "https")  # 集群内可改为 "http"

    es = Elasticsearch(
        [
            {
                "host": es_host,
                "port": es_port,
                "scheme": es_scheme,
            }
        ],
        basic_auth=(es_user, es_pass),
        verify_certs=False,
    )

    index_name = "es_masto_test"

    # 4. 确保索引存在（如果不存在则创建）
    if not es.indices.exists(index=index_name):
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "visibility": {"type": "keyword"},
                    "language": {"type": "keyword"},
                    "content": {"type": "text"},
                    "account": {"type": "object"},
                    "media_attachments": {"type": "nested"},
                }
            }
        }
        es.indices.create(index=index_name, body=mapping)

    # 5. 批量写入
    actions = [
        {
            "_index": index_name,
            "_id": doc.get("id"),
            "_source": doc,
        }
        for doc in docs
    ]
    success, _ = helpers.bulk(es, actions, stats_only=True)

    # 6. 返回执行结果
    return json.dumps({
        "indexed_count": success,
        "index": index_name,
    })

