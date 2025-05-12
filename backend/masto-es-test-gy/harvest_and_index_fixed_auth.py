# harvest_and_index_auth.py

import os
import json
import requests
from requests.auth import AuthBase
from elasticsearch import Elasticsearch, helpers

class BearerAuth(AuthBase):
    """Attaches HTTP Bearer Authentication to the given Request object."""
    def __init__(self, token: str):
        # strip to remove any accidental whitespace or newlines
        self.token = token.strip()

    def __call__(self, r):
        r.headers["Authorization"] = f"Bearer {self.token}"
        return r

def main():
    # 1. Mastodon Token (from env or fallback)
    token = os.environ.get("ACCESS_TOKEN", "cDWlSYHFFEPxIFpkrTf2ss5kAB7hOekUQ7DY3dglm4E")
    masto_url = "https://mastodon.social/api/v1/timelines/public?limit=5"
    auth = BearerAuth(token)

    # 2. Fetch data
    resp = requests.get(masto_url, auth=auth, timeout=10)
    resp.raise_for_status()
    docs = resp.json()  # list of status dicts

    # 3. Elasticsearch connection settings
    es_host   = os.environ.get("ES_HOST", "127.0.0.1")
    es_port   = int(os.environ.get("ES_PORT", 9200))
    es_user   = os.environ.get("ES_USERNAME", "elastic")
    es_pass   = os.environ.get("ES_PASSWORD", "elastic")
    es_scheme = os.environ.get("ES_SCHEME", "https")  # or "http" in-cluster

    es = Elasticsearch(
        [
            {
                "host":   es_host,
                "port":   es_port,
                "scheme": es_scheme,
            }
        ],
        basic_auth=(es_user, es_pass),
        verify_certs=False,
    )

    index_name = "es_masto_test"

    # 4. Ensure index exists
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

    # 5. Bulk index
    actions = [
        {
            "_index": index_name,
            "_id":    doc["id"],
            "_source": doc
        }
        for doc in docs
    ]
    success, _ = helpers.bulk(es, actions, stats_only=True)

    # 6. Return result
    return json.dumps({
        "indexed_count": success,
        "index":         index_name
    })

