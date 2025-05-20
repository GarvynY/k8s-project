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
from elasticsearch import Elasticsearch, helpers

# ES config

ES_HOST  ="https://elasticsearch-master.elastic.svc.cluster.local:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
OLD_INDEX = "bluesky_zy"
NEW_INDEX = "election_v2"

def filter_doc(doc):
    # mapping
    keys = [
        "created_at",
        "sentiment_score",
        "emotion_label",
        "location",
        "geolocation",
        "content",
        "post_time_of_day"
    ]
    return {k: doc.get(k) for k in keys if k in doc}

def migrate_documents():
    es = Elasticsearch(
    [ES_HOST],
    http_auth=(ES_USER, ES_PASS),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False,
    )
    # scan all history data
    results = helpers.scan(
        es,
        index=OLD_INDEX,
        query={
            "_source": True
        }
    )

    actions = []
    for doc in results:
        new_doc = filter_doc(doc["_source"])
        # pass empty
        if not new_doc:
            continue
        actions.append({
            "_index": NEW_INDEX,
            "_source": new_doc
        })

        # commit every 1000 entries
        if len(actions) >= 1000:
            helpers.bulk(es, actions)
            actions = []

    # commit the rest
    if actions:
        helpers.bulk(es, actions)

def handler(context=None):
    migrate_documents()
    return {
        "status": "success",
        "message": "Documents migrated!"
    }
