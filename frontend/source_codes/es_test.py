from elasticsearch8 import Elasticsearch

es = Elasticsearch(
    ["https://elasticsearch-master.elastic.svc.cluster.local:9200"],
    basic_auth=("elastic", "elastic"),
    verify_certs=False
)

# check health
health = es.cluster.health()
print("Cluster health:", health["status"])

# indexes
alias_map = es.indices.get_alias(index="*")
indices = list(alias_map.keys())
print("Indices:", indices)
