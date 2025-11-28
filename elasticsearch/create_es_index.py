from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

index_name = "microbiome-knowledge"

index_body = {
    "mappings": {
        "properties": {
            "content": {"type": "text"},
            "embedding": {
                "type": "dense_vector",
                "dims": 3072  # text-embedding-3-large 维度
            }
        }
    }
}

if not es.indices.exists(index=index_name):
    es.indices.create(index=index_name, body=index_body)
    print("Index created!")
else:
    print("Index already exists")
