from elasticsearch import Elasticsearch
es = Elasticsearch("http://localhost:9200")


resp = es.search(
    index="microbiome-knowledge",
    query={"match": {"content": "益生菌"}},
    size=10
)
print("hits:", resp["hits"]["total"], "returned:", len(resp["hits"]["hits"]))
for hit in resp["hits"]["hits"]:
    print(hit["_id"], hit["_source"])