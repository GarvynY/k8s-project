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


# harvest_and_index.py

import os
import json
import requests
from elasticsearch import Elasticsearch, helpers

def main():
    # 1. Mastodon Token（也可以从环境变量读）
    token = os.environ.get("ACCESS_TOKEN", "cDWlSYHFFEPxIFpkrTf2ss5kAB7hOekUQ7DY3dglm4E")
    masto_url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 拉数据
    resp = requests.get(masto_url, headers=headers, timeout=10)
    resp.raise_for_status()
    docs = resp.json()  # 列表，每项是一个 dict

    # 3. ES 连接配置（假设已通过 ConfigMap or Secret 注入环境变量）
    es_host = os.environ.get("ES_HOST", "127.0.0.1")
    es_port = int(os.environ.get("ES_PORT", 9200))
    es_user = os.environ.get("ES_USERNAME", "elastic")
    es_pass = os.environ.get("ES_PASSWORD", "elastic")

    es = Elasticsearch(
        [{"host": es_host, "port": es_port}],
        http_auth=(es_user, es_pass),
        verify_certs=False,  # 如果是自签证书，需要跳过验证
        timeout=30
    )

    index_name = "es_masto_test"

    # 4. 确保索引存在（如果不存在就创建，mapping 已用 curl 设置过，这里略过）
    if not es.indices.exists(index=index_name):
        # 如果你想在代码里也创建，可以复制上面 curl 的 mapping
        mapping = {
          "mappings": {
            "properties": {
              "id":               {"type": "keyword"},
              "created_at":       {"type": "date"},
              "visibility":       {"type": "keyword"},
              "language":         {"type": "keyword"},
              "content":          {"type": "text"},
              "account":          {"type": "object"},
              "media_attachments": {"type": "nested"}
            }
          }
        }
        es.indices.create(index=index_name, body=mapping)

    # 5. 批量写入
    actions = []
    for doc in docs:
        actions.append({
            "_index": index_name,
            "_id":     doc["id"],
            "_source": doc
        })
    success, _ = helpers.bulk(es, actions, stats_only=True)

    # 6. 返回执行结果
    return json.dumps({
        "indexed_count": success,
        "index": index_name
    })
