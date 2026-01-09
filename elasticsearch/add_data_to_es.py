from langchain_openai import OpenAIEmbeddings
import uuid
from elasticsearch import Elasticsearch
from langchain_community.embeddings import DashScopeEmbeddings

es = Elasticsearch("http://localhost:9200")
index_name = "microbiome-knowledge"
# api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
# base_url = "https://jeniya.cn/v1"
# emb = OpenAIEmbeddings(
#     base_url=base_url,
#     api_key=api_key,
#     model="text-embedding-3-large"
# )
api_key = "sk-5fc0520d085341d780bf6a9969f08661"
emb = DashScopeEmbeddings(
    model="text-embedding-v4",
    dashscope_api_key=api_key
)




# docs = [
#     "Gut microbiome affects metabolism.",
#     "Probiotics improve digestive health.",
#     "Antibiotics reduce microbial diversity."
# ]
docs = [
    "乳酸杆菌能增强宿主免疫反应。",
    "肠道菌群失衡可能引发炎症性肠病。",
    "短链脂肪酸由某些厌氧菌产生，对代谢有益。"
]
for text in docs:
    vec = emb.embed_query(text)  # -> list of floats (长度 3072)

    doc_id = str(uuid.uuid4())
    es.index(
        index=index_name,
        id=doc_id,
        document={
            "content": text,
            "embedding": vec
        }
    )

print("Inserted documents.")
