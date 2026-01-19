import asyncio
import uuid
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.params import Depends
from pydantic import BaseModel
import openai
import os
from fastapi.responses import StreamingResponse
import json
from dependency_injector.wiring import Provide
from dependency_injector.wiring import inject
from brave.microbe.llm import llm_service
from brave.app_container import AppContainer
from brave.microbe.llm.asr_paraformer import ASRService
from brave.microbe.llm.schemas.llm import ChatRequest
from brave.microbe.llm.tool_manager import ToolManager
from brave.microbe.llm.streaming_tool_handler import StreamingToolHandler
from brave.microbe.llm.websocket_tool_handler import ConnectionManager


# DeepSeek 官方兼容 OpenAI SDK
# openai.api_base = "https://api.deepseek.com/v1"
# openai.api_key =  "sk-" #os.getenv("DEEPSEEK_API_KEY")
api_key = os.getenv("DEEPSEEK_API_KEY","")
llm_api = APIRouter(prefix="/llm", tags=["llm"])
client = openai.OpenAI(
            api_key=api_key,
        base_url="https://api.deepseek.com/v1",
    )
# class ChatRequest(BaseModel):
#     message: str

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather of a location, the user should supply a location first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    }
                },
                "required": ["location"]
            },
        }
    },
]

system_prompt = """
The user will provide some exam text. Please parse the "question" and "answer" and output them in JSON format. 

EXAMPLE INPUT: 
Which is the highest mountain in the world? Mount Everest.

EXAMPLE JSON OUTPUT:
{
    "question": "Which is the highest mountain in the world?",
    "answer": "Mount Everest"
}
"""

@llm_api.post("/chat22")
async def chat(req: ChatRequest):
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            tools=tools,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": req.message},
            ]
        )
        reply = response.choices[0].message.content
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# curl -X POST "https://localhost:5005/brave-api/llm/chat" \
#   -H "Content-Type: application/json" \
#   -d '{"message": "你好，介绍一下DeepSeek"}'


@llm_api.post("/chat/stream22")
async def chat_stream(req: ChatRequest):
    """
    流式返回 DeepSeek 响应
    """
    async def stream():
        try:
            # 使用新版 SDK 的 stream=True
            with client.chat.completions.stream(
                model="deepseek-chat",
                tools=tools,
                # response_format={
                #     'type': 'json_object'
                # },
                messages=[
                    # {"role": "system", "content":system_prompt},
                    {"role": "user", "content": req.message},
                ],
            ) as completion:
                for event in completion:
                    if event.type == "message":
                        # 完整消息一次性输出（可改为逐段输出）
                        yield event.message.content
                    elif event.type == "content.delta":
                        # 模型输出的每一小段（类似 ChatGPT 打字机效果）
                        yield event.delta
                    elif event.type == "error":
                        yield f"[Error] {event.error}"
                    await asyncio.sleep(0)  # 让事件循环更流畅

        except Exception as e:
            yield f"[Server Error] {str(e)}"

    return StreamingResponse(stream(), media_type="text/event-stream")

# curl -N -k -X POST "https://localhost:5005/brave-api/llm/chat/stream" \
#   -H "Content-Type: application/json" \
#   -d '{"message": "你好，介绍一下精准医学"}'


# @llm_api.post("/chat/stream")
# async def chat_stream(req: ChatRequest):
#     async def stream():
#         completion = await openai.ChatCompletion.acreate(
#             model="deepseek-chat",
#             messages=[{"role": "user", "content": req.message}],
#             stream=True,
#         )
#         async for chunk in completion:
#             if chunk.choices and chunk.choices[0].delta.get("content"):
#                 yield chunk.choices[0].delta.content
#     return StreamingResponse(stream(), media_type="text/event-stream")





from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langchain_openai import OpenAIEmbeddings
from langchain_elasticsearch import ElasticsearchStore
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.base import BaseCallbackHandler
import asyncio
from langchain_community.embeddings import DashScopeEmbeddings


# ==============================
# 1️⃣ LLM 回调处理器，用于流式输出
# ==============================
class StreamHandler(BaseCallbackHandler):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def on_llm_new_token(self, token: str, **kwargs):
        # 每个 token 放入队列
            #         asyncio.create_task(self.queue.put(json.dumps({
            #     "type": "answer",
            #     "content": token
            # })))
        # self.queue.put_nowait(token)
        self.queue.put_nowait(json.dumps({
                "type": "answer",
                "content": token
            }))

# ==============================
# 2️⃣ 初始化向量存储和 LLM
# ==============================
# api_key = "sk-kS6vHrWPHrysTVEvm3yPwvuHdZNy3CIIoJlGTXNGOgKusvk0"
# base_url = "https://jeniya.cn/v1"

api_key = "sk-5fc0520d085341d780bf6a9969f08661"
model = "qwen-plus"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
embeddings_model="text-embedding-v4"

index_name = "microbiome-knowledge"

embeddings = DashScopeEmbeddings(
    model="text-embedding-v4",
    dashscope_api_key=api_key
)
# embeddings = OpenAIEmbeddings(base_url=base_url, api_key=api_key, model="text-embedding-3-large")
vector_store = ElasticsearchStore(index_name, embedding=embeddings, es_url="http://localhost:9200")
retriever = vector_store.as_retriever(search_type="similarity",
                                       search_kwargs={"k": 3, "score_threshold": 0.75 })

template = """
You are an expert assistant. Use the context below to answer the question.

Each sentence in your answer must include a source citation like [1], [2], etc.

Context:
{context}

Question:
{question}

Answer:
"""

prompt = PromptTemplate(template=template, input_variables=["context", "question"])

# ==============================
# 3️⃣ FastAPI SSE endpoint
# ==============================
@llm_api.post("/rag-stream2")
async def rag_stream(req: ChatRequest):
    query = req.message
    queue = asyncio.Queue()
    handler = StreamHandler(queue)
    manager = CallbackManager([handler])

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model_name=model,
        temperature=0.2,
        streaming=True,
        callback_manager=manager
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    # ==============================
    # 4️⃣ SSE generator
    # ==============================
    async def event_generator():
        # 异步调用 LLM
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, qa_chain, query)

        while True:
            try:
                token = await asyncio.wait_for(queue.get(), timeout=0.1)
                # yield f"data: {token}\n\n"
                yield token
            except asyncio.TimeoutError:
                if task.done():
                    break

    return StreamingResponse(event_generator(), media_type="text/event-stream")





@llm_api.post("/rag-stream")
async def rag_stream(req: ChatRequest):
    query = req.message
    queue = asyncio.Queue()

    # 1️⃣ 先检索 Top K 文档
    docs = retriever.get_relevant_documents(query)
    for d in docs:
        # 先把文档信息放入队列，类型标记为 doc
        await queue.put(json.dumps({
            "type": "doc",
            "id": d.metadata.get("source", ""),
            "content": d.page_content[:200]  # 可截取摘要
        }))

    # 2️⃣ 设置流式 LLM
    # class StreamHandler:
    #     def __init__(self, queue):
    #         self.queue = queue

    #     def on_llm_new_token(self, token: str, **kwargs):
            # asyncio.create_task(self.queue.put(json.dumps({
            #     "type": "answer",
            #     "content": token
            # })))
    # class StreamHandler(BaseCallbackHandler):
    #     def __init__(self, queue: asyncio.Queue):
    #         super().__init__()
    #         self.queue = queue
    #         self.raise_error = False  # 避免 AttributeError

    #     def on_llm_new_token(self, token: str, **kwargs):
    #         asyncio.create_task(self.queue.put(json.dumps({
    #             "type": "answer",
    #             "content": token
    #         })))

    #     def on_llm_end(self, response, **kwargs):
    #         # 可选：在 LLM 完成时发送结束标记
    #         asyncio.create_task(self.queue.put(json.dumps({
    #             "type": "end"
    #         })))

    handler = StreamHandler(queue)
    manager = CallbackManager([handler])

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model_name=model,
        temperature=0.2,
        streaming=True,
        callback_manager=manager
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    # 3️⃣ SSE generator
    async def event_generator():
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, qa_chain, query)

        while True:
            try:
                token = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield f"data: {token}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    break

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@llm_api.post("/chat/stream")
@inject
async def chat_stream(req: ChatRequest,
                      tool_manager: ToolManager= Depends(Provide[AppContainer.tool_manager])):
    
    biz_id = req.biz_id
    project_id = req.project_id
    biz_type = req.biz_type
    model_name = req.model_name
    def format(event: str, data: dict):
        return (
            f"event:{event}\ndata:{json.dumps(data)}\n\n"
        )

    # def format(event: str, data: dict):
    #         return ({
    #             "event": event,
    #             "data": data
    #         })
    handler:StreamingToolHandler = StreamingToolHandler( model_name,tool_manager)

    return await handler.run(
        req=req,
        biz_id=biz_id,
        biz_type=biz_type,
        project_id=project_id,
        format=format
    )




manager = ConnectionManager()

@llm_api.websocket("/ws/stream")
@inject
async def websocket_endpoint(
    ws: WebSocket,
    tool_manager: ToolManager= Depends(Provide[AppContainer.tool_manager])
):
    query_params = ws.query_params

    conn = await manager.connect(ws)
    handler:StreamingToolHandler = StreamingToolHandler( "qwen-plus",tool_manager)
    # queue = asyncio.Queue()
    # async def audio_emit(data):
    #     if queue:
    #         # msg = format(event,data)
    #         await queue.put(data)
    # sender_task = asyncio.create_task(conn.sender())
    def format(event: str, data: dict):
        return ({
            "event": event,
            "data": data
        })
            # return (
        #     f"event:{event}\ndata:{json.dumps(data)}\n\n"
        # )
    async def emit(event: str, data: dict):
        await conn.queue.put({
            "event": event,
            "data": data
        })


    
    token = query_params.get("token")
    user_id = token
    session_id = query_params.get("conversation_id","")
    if session_id=="":
        session_id = str(uuid.uuid4())
    asr_service = None
    is_tts = False
    if query_params.get("is_tts") is not None:
        is_tts = query_params.get("is_tts") == "true"
    try:
        while True:
            message = await ws.receive()
            
            # 1️⃣ 文本消息
            if message.get("text") is not None:
                data = message["text"]
                req = ChatRequest(message=data,user_id=user_id, session_id=session_id)
                await handler.run_(req, conn.queue,conn,is_tts,format)
                break

            # 2️⃣ 二进制消息
            elif message.get("bytes") is not None:
                message = message["bytes"]
                msg_type = message[0]
           
                if msg_type == 0x01:
                    print("START")
                    asr_service = ASRService(emit=emit)
                elif msg_type == 0x02:
                    data = message[1:]
                    # print("DATA", data)
                    await asr_service.recognition(data)
                elif msg_type == 0x03:
                    print("STOP")
                    data = await asr_service.stop()
                    print(f"ASR stopped {data}")
                    if data!="":
                        conn.queue.put_nowait({
                            "event": "asr_result",
                            "data": {"content": data}
                        })
                        req = ChatRequest(message=data, user_id=user_id, session_id=session_id)
                        await handler.run_(req, conn.queue,conn,is_tts,format)
                      
                    else:
                        conn.queue.put_nowait({
                            "event": "event",
                            "data": {"content": "no_asr_result"}
                        })
                    break
                elif msg_type == 0x04:
                    print("cancel")
                    break
                # elif msg_type == 0x05:
                #     is_tts = True
                #     print("TTS enabled")
                # await handle_binary_message(data)
                # print("Received data:", data)
           
            # await conn.queue.put({"type": "pong"})
            # try:
            #     data = json.loads(data)
            # except Exception as e:
            #     print("Invalid message format :", e)
            #     continue
            # if "type" not in data:
            #     continue

            # # 控制消息
            # if data["type"] == "ping":
            #     await conn.queue.put({"type": "pong"})
            # elif data["type"] == "msg":
               
                # asyncio.create_task(run_llm_task(biz_id, conn))
            # elif data["type"] == "stop":
            #     break

    except WebSocketDisconnect as e:
        print(f"WebSocket disconnected: {e}")
        pass
    finally:
        await manager.disconnect(conn.client_id)
        # sender_task.cancel()
        print("WebSocket disconnected")

# async def handle_binary_message(message: bytes):
