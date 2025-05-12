import os
import json
import requests
from elasticsearch import Elasticsearch, helpers

def main():
    # 1. Mastodon Token
    token = os.environ.get("ACCESS_TOKEN", "<你的 token>")
    masto_url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 拉数据
    resp = requests.get(masto_url, headers=headers, timeout=10)
    resp.raise_for_status()
    docs = resp.json()

    # 3. 从环境变量拿 ES 连接配置
    es_host   = os.environ["ES_HOST"]
    es_port   = int(os.environ["ES_PORT"])
    es_scheme = os.environ.get("ES_SCHEME", "http")
    es_user   = os.environ["ES_USERNAME"]
    es_pass   = os.environ["ES_PASSWORD"]

    # 4. 建立客户端
    es = Elasticsearch(
        [
            {
                "host":   es_host,
                "port":   es_port,
                "scheme": es_scheme
            }
        ],
        basic_auth=(es_user, es_pass),
        verify_certs=False
    )

    # 5. 索引名字
    index_name = "es_masto_test"

    # 6. 确保索引存在
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
                    "media_attachments": {"type": "nested"}
                }
            }
        }
        es.indices.create(index=index_name, body=mapping)

    # 7. 批量写入
    actions = [
        {"_index": index_name, "_id": doc["id"], "_source": doc}
        for doc in docs
    ]
    success, _ = helpers.bulk(es, actions, stats_only=True)

    # 8. 返回结果
    return json.dumps({
        "indexed_count": success,
        "index":         index_name
    })

