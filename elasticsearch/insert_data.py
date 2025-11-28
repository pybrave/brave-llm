from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")

doc = {
    "title": "益生菌功能",
    "content": "益生菌对于维持肠道菌群平衡、促进营养吸收有重要作用...",
    "tags": ["菌群", "益生菌", "健康"]
}

# 可根据实际需求批量插入文档
es.index(index="microbiome-knowledge", document=doc)