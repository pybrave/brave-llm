# streaming_tool_handler.py
import asyncio
import json
import os
import re
import dashscope
from fastapi.responses import StreamingResponse
import openai

from brave.microbe.llm import llm_service
from brave.microbe.llm.tool_manager import ToolManager
# from brave.microbe.llm.tss_worker import TtsService
from brave.microbe.llm.tts_speech_synthesizer import TtsService

from brave.microbe.llm.tts import tts_stream
from brave.microbe.schemas.chat_history import CreateChatHistory
from brave.microbe.service import chat_history_service
from brave.microbe.utils.lock_llm import BizProjectLock
from .schemas.llm import ChatRequest
from brave.api.config.db import get_engine

async def lock_wrapper(biz_id, project_id, gen):
    async with BizProjectLock(biz_id, project_id):
        async for item in gen:
            yield item

system_prompt = """

"""

template = """
{question}

"""

model_dict = {
    "qwen-plus":{
        "API_KEY_NAME":"DASHSCOPE_API_KEY",
        "model_name":"qwen-plus",
        "base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1"
    },"deepseek-chat":{
        "API_KEY_NAME":"DEEPSEEK_API_KEY",
        "model_name":"deepseek-chat",
        "base_url":"https://api.deepseek.com"
    }
}
SENTENCE_END_RE = re.compile(r"[。！？.!?\n]")

class StreamingToolHandler:

    def __init__(self, model_name:str,tool_manager: ToolManager):
        # self.client = client
   #     api_key=self.api_key,
        

        # client = openai.OpenAI(
        #         api_key=api_key,
        #         base_url="https://api.deepseek.com",
        #     )
        model_info = model_dict[model_name]
        self.model_name=model_info["model_name"]
        self.sentence_buffer = ""


        api_key = os.getenv(model_info["API_KEY_NAME"],"")
        self.client = openai.OpenAI(
                api_key=api_key,
                base_url=model_info["base_url"],
            )
        self.tool_manager = tool_manager
       
        # self.api_key = os.getenv("DEEPSEEK_API_KEY","")
        # self.client = openai.OpenAI(
          #     base_url="https://api.deepseek.com/v1",
        # )



    def should_tts(self,text: str) -> bool:
        if SENTENCE_END_RE.search(text):
            return True
        if len(text) > 40:
            return True
        return False
    
    def extract_sentence(self,text: str) -> str:
        match = SENTENCE_END_RE.search(text)
        if match:
            return text[: match.end()]
        return text
    
    async def tts(self,emit, text: str):
        """
        返回 base64 PCM / WAV
        """
        async for audio in tts_stream(text):
            await emit("audio",{'content':audio})
   
        # resp = await tts_client.synthesize(
        #     text=text,
        #     voice="zh-CN",
        #     format="pcm"  # or wav
        # )
        # response = dashscope.MultiModalConversation.call(
        #     model="qwen3-tts-flash",
        #     # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
        #     # 若没有配置环境变量，请用阿里云百炼API Key将下行替换为：api_key="sk-xxx"
        #     api_key=os.getenv("DASHSCOPE_API_KEY"),
        #     text=text,
        #     voice="Cherry",
        #     language_type="Chinese",
        #     stream=True
        # )
        # for chunk in response:
        #     audio = chunk["output"]["audio"]["data"]
        #     print(audio)
        #     # yield audio
        #     # yield self.sse("message",)
        #     # msg = {'title':'LLM started','content': 'LLM started'}
        #     await emit("audio",{'content':audio})
        # return resp.audio_base64
        
    async def run_(self, req, queue,conn,is_tts,format):
       
        async def emit(event,data):
             if queue:
                msg = format(event,data)
                await queue.put(msg)
        if is_tts:
            tts_service = TtsService(emit=emit)
            
            # asyncio.create_task(tts_service.emit_audio(emit))
        
        thought_chain_msg = []
        content = await llm_service.build_prompt(
                req,
                system_prompt,
                template,
                queue=queue,
            )
        
        thought_chain_msg.append(content)
        msg = {'title':'LLM started','content': 'LLM started'}
        await emit("status",msg)
        thought_chain_msg.append(msg)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        tools = self.tool_manager.get_schemas()
        assistant_message = ""  # 最终累积模型输出
        current_messages = list(messages)
        try:
            while True and conn.alive:
                pending_tool_calls = []
                round_text_buffer = ""   # 本轮累积文本
                with self.client.chat.completions.stream(
                    model=self.model_name,
                    # stream=True,
                    tools=tools,
                    # response_format={
                    #     'type': 'json_object'
                    # },
                    messages=current_messages,
                ) as completion:
                    
                    tool_calls = {}  # index -> {id, name, arguments}
                    # for completion in llm.stream_chat_completion(messages, tools):
                    for event  in completion:
                        if not  conn.alive:
                            await tts_service.terminate()
                            break
                        # print(event)
                        if event.type == "chunk":
                            snap = event.snapshot
                            if snap.choices:
                                msg = snap.choices[0].message
                                if msg and msg.tool_calls:
                                    for tc in msg.tool_calls:
                                        idx = tc.index
                                        tool_calls[idx] = {
                                            "id": tc.id,
                                            "name": tc.function.name,
                                            "arguments": ""   # 等待流式拼接
                                        }            
                        if event.type == "message":
                            assistant_message += event.message.content
                            round_text_buffer += event.message.content
                            # 完整消息一次性输出（可改为逐段输出）
                            # yield 
                            await emit("message",{'content': event.message.content})
                        elif event.type == "content.delta":
                            assistant_message += event.delta
                            round_text_buffer += event.delta
    
                            await emit("message",{'content': event.delta})
                            self.sentence_buffer += event.delta
                            if is_tts:
                                await tts_service.speak(event.delta)
                            # print(f"Delta received: {event.delta} ")
                        elif event.type == "tool_calls.function.arguments.delta":
                            pass
                            # yield f"event: message\ndata: {json.dumps({'content': event.arguments_delta})}\n\n"
                        elif event.type == "tool_calls.function.arguments.done":
                            
                            # if idx in tool_calls:
                            #     # tool_calls[idx]["arguments"] = event.arguments
                            #     event.id = tool_calls[idx].id
                            pending_tool_calls.append(event)
                            # msg = f"Tool call {event.name} with arguments {event.arguments}."
                            # yield f"event: message\ndata: {json.dumps({'content': msg})}\n\n"
                            print(f"Tool call {event.name}: {event.arguments}.")
                            msg = {'title':f"Tool Call: {event.name}",'content':f"Tool call {event.name} with arguments {event.arguments}."}
                            # yield f"event:status\ndata:{json.dumps(msg)}\n\n"
                            await emit("status",msg)
                            thought_chain_msg.append(msg)
                        elif event.type == "error":
                            await emit("message",{'content': f"[Error] {event.error}"})
                        await asyncio.sleep(0)  # 让事件循环更流畅

                    # ---------- ② 如果没有 tool call → 完成  ----------
                    if not pending_tool_calls:
                        break
                    tool_results = []
                    if pending_tool_calls: 
                        for tc in pending_tool_calls:
                            idx = tc.index
                            if idx in  tool_calls:
                                args = json.loads(tc.arguments)
                                
                                result = await self.tool_manager.run(tc.name, {"biz_id":biz_id,**args})
                                
                                tool_results.append({
                                    "role": "tool",
                                    "name": tc.name,
                                    "tool_call_id":  tool_calls[idx]["id"],
                                    "content": result
                                })

                    # 将 tool 结果加入消息，继续下一轮
                        # ---------- ④ 下一轮 messages ----------
    # 1. 构造 assistant 的工具调用消息（不能带 content 文本！）
                assistant_tool_call_msg = {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_calls[idx]["id"],
                            "type": "function",
                            "function": {
                                "name": tool_calls[idx]["name"],
                                "arguments": tc.arguments,
                            },
                        }
                        for tc in pending_tool_calls
                        for idx in [tc.index]
                    ]
                }

                # 2. 下一轮消息
                current_messages = (
                    current_messages
                    + [assistant_tool_call_msg]
                    + tool_results
                )
                # current_messages = (
                #     current_messages
                #     + [{"role": "assistant", "content": round_text_buffer}]
                #     + tool_results
                # )
            if is_tts:
                await tts_service.stop()  
            with get_engine().begin() as conn:
                
                create_chatHistory = CreateChatHistory(
                    user_id=None,
                    session_id=None,
                    biz_id=None,
                    biz_type=None,
                    role="assistant",
                    content=assistant_message,
                    project_id=None,
                    thought_chain=thought_chain_msg 
                )
                chat_history_service.insert_chat_history(conn, create_chatHistory)
            print(f"assistant_message: {assistant_message}")
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            # yield f"[Server Error] {str(e)}"
            await emit("status",{"error": str(e)})
        finally:
            print("StreamingToolHandler run_ finished.")
            # if is_tts:
            #     await tts_service.terminate()


    async def run(self, req,biz_id,biz_type, project_id,format):
        # biz_id = req.biz_id
        # biz_type= req.biz_type
        # project_id= req.project_id
        """
        流式返回 DeepSeek 响应
        """
        async def stream():
            queue = asyncio.Queue()
            llm_task = asyncio.create_task(
                self.run_(req, queue, True,format)
            )
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=0.05)
                    yield msg
                except asyncio.TimeoutError:
                    if llm_task.done():
                        break

        async with BizProjectLock(biz_id, project_id):
            return StreamingResponse(
                lock_wrapper(biz_id, project_id, stream()),
                media_type="text/event-stream"
            )