from elasticsearch import Elasticsearch, helpers

# 你的ES配置

ES_HOST  ="https://elasticsearch-master.elastic.svc.cluster.local:9200"
ES_USER = "elastic"
ES_PASS = "elastic"
OLD_INDEX = "bluesky_zy"
NEW_INDEX = "election_v2"

def filter_doc(doc):
    # 只保留新mapping定义的字段
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
    # 使用 scan 高效遍历所有旧数据
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
        # 若没有内容则跳过
        if not new_doc:
            continue
        actions.append({
            "_index": NEW_INDEX,
            "_source": new_doc
        })

        # 每1k条bulk提交一次，节省内存
        if len(actions) >= 1000:
            helpers.bulk(es, actions)
            actions = []

    # 提交剩余数据
    if actions:
        helpers.bulk(es, actions)

def handler(context=None):
    migrate_documents()
    return {
        "status": "success",
        "message": "Documents migrated!"
    }