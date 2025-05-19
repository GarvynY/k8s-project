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
