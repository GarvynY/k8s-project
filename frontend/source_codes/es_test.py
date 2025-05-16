from elasticsearch8 import Elasticsearch

es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)

# 集群健康检查
health = es.cluster.health()
print("Cluster health:", health["status"])

# 列出所有索引（用关键字参数）
alias_map = es.indices.get_alias(index="*")
indices = list(alias_map.keys())
print("Indices:", indices)
