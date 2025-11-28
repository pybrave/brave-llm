from elasticsearch import Elasticsearch
from langchain_openai import OpenAIEmbeddings

es = Elasticsearch("http://localhost:9200")
api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
base_url = "https://jeniya.cn/v1"
emb = OpenAIEmbeddings(
    base_url=base_url,
    api_key=api_key,
    model="text-embedding-3-large"
)


index_name = "microbiome-knowledge"
query = "How does gut microbiome influence metabolism?"
query_vector = emb.embed_query(query)

result = es.knn_search(
    index=index_name,
    knn={
        "field": "embedding",
        "query_vector": query_vector,
        "k": 3,
        "num_candidates": 10
    }
)

for hit in result["hits"]["hits"]:
    print(f"Score: {hit['_score']:.4f} - {hit['_source']['content']}")
