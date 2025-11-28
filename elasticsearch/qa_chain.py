# from langchain.chains import RetrievalQA
# from langchain.embeddings import OpenAIEmbeddings  # 需配置 OpenAI key
# from langchain.vectorstores import ElasticVectorSearch
# from langchain.llms import OpenAI

# es_url = "http://localhost:9200"
# index_name = "microbiome-knowledge"

# api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
# base_url = "https://jeniya.cn/v1"


# api_key = "sk-3c00405e530947c0b54a068886d308d4"
# base_url = "https://api.deepseek.com/v1"
# model = "deepseek-chat"
api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
model = "gpt-5"
base_url = "https://jeniya.cn/v1"

# 替换为自己模型或 API
# embedding = OpenAIEmbeddings(api_key=api_key, base_url=base_url)
# vectorstore = ElasticVectorSearch(
#     elasticsearch_url=es_url,
#     index_name=index_name,
#     embedding=embedding,
# )

# qa = RetrievalQA.from_chain_type(
#     llm=OpenAI(temperature=0, api_key=api_key, base_url=base_url),
#     chain_type="stuff",
#     retriever=vectorstore.as_retriever(),
# )

# question = "益生菌的主要健康作用有哪些？"
# answer = qa.run(question)
# print(answer)


from langchain_openai import OpenAIEmbeddings
from langchain_elasticsearch import ElasticsearchStore
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA

from langchain.callbacks.manager import CallbackManager
from langchain.callbacks import StdOutCallbackHandler
from langchain.prompts import PromptTemplate


handler = StdOutCallbackHandler()
manager = CallbackManager([handler])

embeddings = OpenAIEmbeddings(base_url=base_url,
                              api_key=api_key,
                              model="text-embedding-3-large")





# template = """
# Use the following context to answer the question.

# Context:
# {context}

# Question:
# {question}

# Answer:
# """

# prompt = PromptTemplate(
#     template=template,
#     input_variables=["context", "question"]
# )

template = """
You are an expert assistant. Use the context below to answer the question.

Each sentence in your answer **must include a source citation** corresponding to the document number, like [1], [2], etc.

Context:
{context}

Question:
{question}

Important rules:
- Only use information from context.
- For each sentence, cite at least one source document using [number].
- Do NOT make up citations.

Answer:
"""

prompt = PromptTemplate(
    template=template,
    input_variables=["context", "question"]
)


vector_store = ElasticsearchStore(
    "microbiome-knowledge", 
    embedding=embeddings, 
    es_url="http://localhost:9200"
)




# 获取 Retriever（用于检索相关文档）
retriever = vector_store.as_retriever(
    search_type="similarity",
    search_kwargs={"k": 3}
)
# retriever = vector_store.as_retriever(search_kwargs={"k": 3})  # 返回 top 3 文档

# ==============================
# 3️⃣ 初始化 LLM
# ==============================
llm = ChatOpenAI(
    api_key=api_key,
    base_url=base_url,
     callback_manager=manager,
    model_name="gpt-5-mini",   temperature=0)

# ==============================
# 4️⃣ 创建 RetrievalQA 链
# ==============================
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=retriever,
     verbose=True ,
     chain_type_kwargs={"prompt": prompt},
    return_source_documents=True  # 是否返回原始文档
)




# ==============================
# 5️⃣ 查询示例
# ==============================
query = "What gut microbes can influence?"
# query="乳酸杆菌能增强?"
result = qa_chain(query)

# 手动构造一次检索，打印 context
docs = retriever.get_relevant_documents(query)
context = "\n\n".join([d.page_content for d in docs])

print("\n==== 实际发给 LLM 的 Prompt ====\n")
print(prompt.format(context=context, question=query))


# 输出回答
print("LLM 回答：\n", result['result'])

# 输出源文档（可选）
print("\n源文档内容：")
for doc in result['source_documents']:
    print(doc.page_content)