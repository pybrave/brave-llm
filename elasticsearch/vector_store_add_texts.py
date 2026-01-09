from langchain_openai import OpenAIEmbeddings
from langchain_elasticsearch import ElasticsearchStore
from langchain_community.embeddings import DashScopeEmbeddings

# api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
# base_url = "https://jeniya.cn/v1"
index_name = "microbiome-knowledge"

# # Embedding 模型
# embeddings = OpenAIEmbeddings(
#     base_url=base_url,
#     api_key=api_key,
#     model="text-embedding-3-large"
# )

api_key = "sk-5fc0520d085341d780bf6a9969f08661"
embeddings = DashScopeEmbeddings(
    model="text-embedding-v4",
    dashscope_api_key=api_key
)


# 向量存储
vector_store = ElasticsearchStore(
    index_name=index_name,
    embedding=embeddings,
    es_url="http://localhost:9200"
)

# 插入文档
docs = [
    # "乳酸杆菌能增强宿主免疫反应。",
    # "肠道菌群失衡可能引发炎症性肠病。",
    # "短链脂肪酸由某些厌氧菌产生，对代谢有益。"
]

from pdf import pdf_to_paragraphs

pdf_path = "paper1.pdf"
paragraphs = pdf_to_paragraphs(pdf_path)
for p in paragraphs:
    content = f"Page {p['page_num']}, Paragraph {p['paragraph_index']}:\n{p['content']}"
    docs.append(content)

vector_store.add_texts(docs)
print("Documents inserted.")
