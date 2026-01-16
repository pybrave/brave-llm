# streaming_tool_handler.py
import asyncio
from dataclasses import dataclass
import json
import os
import re
import dashscope
from fastapi.responses import StreamingResponse
import openai
from typing import Callable, Optional

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
system_prompt2 = """

1.根据用户问题，生成用于知识库检索的中文与英文关键词, 关键词应尽量覆盖核心概念、人物、时间、技术名词
2.使用关键词调用 rag_tools 查询知识库, 不允许在未查询 RAG 的情况下直接作答, 回答必须以 rag_tools 返回的内容为主要依据,可在此基础上结合你的通用知识进行补充,禁止编造 RAG 中不存在的事实或引用

请每句话用一个 JSON 对象表示，字段包括 content 和 citation(当你引用或依赖块的特定部分时，请将其引用为 citation 字段)，格式如下:
{
    "content": "你最终回答的片段",
    "citation": [
        {
            "chunk_id": "N",
            "sentences": "X-Y"
        }
    ]   
}
N 是块 ID，X-Y 是引用的句子范围
例如:
{
    "content": "阿司匹林是一种常用的非甾体抗炎药，具有镇痛、解热和抗炎作用。它通过抑制环氧化酶（COX）酶的活性，减少前列腺素的合成，从而发挥其药理作用。",
    "citation": [
        {
            "chunk_id": "5",
            "sentences": "2-4"
        }
    ]   
}
"""
# <<chunk_id='N' sentences='X-Y'>><<chunk_id='N' sentences='X-Y'>>
# 当你引用或依赖句子的特定部分时，请在句子后面添加：
# @cite(N,N)
system_prompt ="""
你是一个健康的问答助手。
1.根据用户问题，生成用于知识库检索的中文与英文关键词, 关键词应尽量覆盖核心概念、人物、时间、技术名词
2.使用关键词调用 rag_tools 查询知识库, 不允许在未查询 RAG 的情况下直接作答, 回答必须以 rag_tools 返回的内容为主要依据,可在此基础上结合你的通用知识进行补充,禁止编造 RAG 中不存在的事实或引用

当你引用或依赖句子的特定部分时，请在句子后面添加：
@cite(N,N)
N 是块ID, 同一个句子多个引用用逗号分割直接跟在后面, 引用规则（必须严格遵守）。

例如:
阿司匹林是一种常用的非甾体抗炎药，具有镇痛、解热和抗炎作用。它通过抑制环氧化酶（COX）酶的活性，减少前列腺素的合成，从而发挥其药理作用。@cite(12345679,888888)

"""
system_prompt5 = """

你是一个健康的问答助手。
请将【每一句话】用<RESULT>开头，用</RESULT>结尾包裹起来，根据具体情况决定是否在这句话后面是否添加换行符，如果是一个段落不要在句子最后添加换行符。格式如下:
<RESULT>
    <CONTENT> 
        你最终回答的片段。
    </CONTENT>
</RESULT>
1.根据用户问题，生成用于知识库检索的中文与英文关键词, 关键词应尽量覆盖核心概念、人物、时间、技术名词
2.使用关键词调用 rag_tools 查询知识库, 不允许在未查询 RAG 的情况下直接作答, 回答必须以 rag_tools 返回的内容为主要依据,可在此基础上结合你的通用知识进行补充,禁止编造 RAG 中不存在的事实或引用

当你引用或依赖块的特定部分时，请将其引用为：
<RESULT>
    <CONTENT> 
        你最终回答的片段
    </CONTENT>
    <CITATION>
        <chunk_id='N' sentences='X-Y'/>
    </CITATION>
</RESULT>
N 是块 ID，X-Y 是引用的句子范围

例如:
<RESULT>
    <CONTENT>
        阿司匹林是一种常用的非甾体抗炎药，具有镇痛、解热和抗炎作用。它通过抑制环氧化酶（COX）酶的活性，减少前列腺素的合成，从而发挥其药理作用。
    </CONTENT>
    <CITATION>
        <chunk_id='5' sentences='2-4'/>
    </CITATION>
</RESULT>

注意: 如果用户的问题需要查询RAG, 请直接调用RAG不需输出自然语言
注意: 正式回答前, 不要输出根据RAG查询结果, 直接回答用户问题
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



class ResultCollector:
    def __init__(self, on_result: Optional[Callable[[str], None]] = None):
        self.buffer = ""
        self.on_result = on_result

    async def feed(self, chunk: str):
        self.buffer += chunk

        # 匹配完整的 RESULT
        while True:
            match = re.search(r"<RESULT>.*?</RESULT>", self.buffer, re.DOTALL)
            if not match:
                break  # 没有完整 RESULT，等待更多 chunk

            full_result = match.group()
            if self.on_result:
                await self.on_result(full_result)  # 交给单独函数解析

            # 切掉已经处理的部分
            self.buffer = self.buffer[match.end():]

class StreamingXMLParser:
    def __init__(
        self,
        on_content: Optional[Callable[[str], None]] = None,
        on_result: Optional[Callable[[dict], None]] = None,
    ):
        self.buffer = ""
        self.current_tag = None

        self.content_buffer = ""
        self.citation_buffer = ""

        self.on_content = on_content
        self.on_result = on_result

    async def feed(self, chunk: str):
        self.buffer += chunk

        while True:
            # 找下一个 tag
            match = re.search(r"</?\w+>", self.buffer)
            if not match:
                # 如果在 CONTENT 内，可以提前流式吐内容
                if self.current_tag == "CONTENT" and self.buffer:
                    self.content_buffer += self.buffer
                    if self.on_content:
                        await self.on_content(self.buffer)
                    self.buffer = ""
                return

            tag = match.group()
            tag_start, tag_end = match.span()

            # 处理 tag 前的内容
            text = self.buffer[:tag_start]
            if self.current_tag == "CONTENT" and text:
                self.content_buffer += text
                if self.on_content:
                    await self.on_content(text)
            elif self.current_tag == "CITATION":
                self.citation_buffer += text

            self.buffer = self.buffer[tag_end:]

            # 处理 tag 本身
            if tag.startswith("</"):
                closed = tag[2:-1]

                if closed == "CONTENT":
                    self.current_tag = None

                elif closed == "CITATION":
                    self.current_tag = None

                elif closed == "RESULT":
                    result = {
                        "content": self.content_buffer.strip(),
                        "citation": self.citation_buffer.strip(),
                    }
                    if self.on_result:
                        self.on_result(result)

                    # reset
                    self.content_buffer = ""
                    self.citation_buffer = ""
                    self.current_tag = None

            else:
                opened = tag[1:-1]
                self.current_tag = opened

def parse_result(result_str: str):
    content_match = re.search(r"<CONTENT>(.*?)</CONTENT>", result_str, re.DOTALL)
    citation_match = re.search(r"<CITATION>(.*?)</CITATION>", result_str, re.DOTALL)

    content = content_match.group(1) if content_match else ""
    citation = citation_match.group(1) if citation_match else ""

    return {
        "content": content,
        "citation": citation
    }



class CiteFSM2:
    def __init__(self, replace_fn=None):
        self.replace_fn = replace_fn or (lambda cite: "")
        self.results = []
        self.reset()

    def reset(self):
        self.state = "START"
        self.buf = ""          # cite 内容
        self.pending = ""      # 尚未确认的输出
        self.depth = 0

    def feed(self, ch: str) -> str:
        """
        返回：当前字符是否应该输出（"" 或 1+ 字符）
        """
        if self.state == "START":
            if ch == "@":
                self.pending = "@"
                self.state = "AT"
                return ""
            return ch

        elif self.state == "AT":
            if ch == "c":
                self.pending += ch
                self.state = "C"
                return ""
            else:
                out = self.pending + ch
                self.reset()
                return out

        elif self.state == "C":
            if ch == "i":
                self.pending += ch
                self.state = "I"
                return ""
            return self._fallback(ch)

        elif self.state == "I":
            if ch == "t":
                self.pending += ch
                self.state = "T"
                return ""
            return self._fallback(ch)

        elif self.state == "T":
            if ch == "e":
                self.pending += ch
                self.state = "E"
                return ""
            return self._fallback(ch)

        elif self.state == "E":
            if ch == "(":
                self.state = "IN"
                self.buf = ""
                self.depth = 0
                return ""   # 吞掉 "@cite("
            return self._fallback(ch)

        elif self.state == "IN":
            if ch == "(":
                self.depth += 1
                self.buf += ch
            elif ch == ")":
                if self.depth == 0:
                    return self._emit_and_replace()
                self.depth -= 1
                self.buf += ch
            else:
                self.buf += ch
            return ""

    def _fallback(self, ch):
        out = self.pending + ch
        self.reset()
        return out

    def _emit_and_replace(self):
        cite = self.buf
        self.results.append(cite)
        replacement = self.replace_fn(cite)
        self.reset()
        return replacement

    def flush(self):
        out = self.pending
        self.reset()
        return out

@dataclass
class CiteEvent:
    type: str                 # "TEXT" | "CITE"
    text: Optional[str] = None
    raw_cite: Optional[str] = None

class CiteFSM:
    def __init__(self):
        self.results = []
        self.reset()

    def reset(self):
        self.state = "START"
        self.buf = ""
        self.pending = ""
        self.depth = 0

    def feed(self, ch: str) -> list[CiteEvent]:
        events = []

        if self.state == "START":
            if ch == "@":
                self.pending = "@"
                self.state = "AT"
            else:
                events.append(CiteEvent("TEXT", text=ch))

        elif self.state == "AT":
            if ch == "c":
                self.pending += ch
                self.state = "C"
            else:
                events.append(CiteEvent("TEXT", text=self.pending + ch))
                self.reset()

        elif self.state == "C":
            if ch == "i":
                self.pending += ch
                self.state = "I"
            else:
                events.append(CiteEvent("TEXT", text=self.pending + ch))
                self.reset()

        elif self.state == "I":
            if ch == "t":
                self.pending += ch
                self.state = "T"
            else:
                events.append(CiteEvent("TEXT", text=self.pending + ch))
                self.reset()

        elif self.state == "T":
            if ch == "e":
                self.pending += ch
                self.state = "E"
            else:
                events.append(CiteEvent("TEXT", text=self.pending + ch))
                self.reset()

        elif self.state == "E":
            if ch == "(":
                self.state = "IN"
                self.buf = ""
                self.depth = 0
            else:
                events.append(CiteEvent("TEXT", text=self.pending + ch))
                self.reset()

        elif self.state == "IN":
            if ch == "(":
                self.depth += 1
                self.buf += ch
            elif ch == ")":
                if self.depth == 0:
                    events.append(CiteEvent("CITE", raw_cite=self.buf))
                    self.results.append(self.buf)
                    self.reset()
                else:
                    self.depth -= 1
                    self.buf += ch
            else:
                self.buf += ch

        return events

    def flush(self):
        events = []
        if self.pending:
            events.append(CiteEvent("TEXT", text=self.pending))
        self.reset()
        return events


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
        thinking_dict = {}
        async def emit_thinking(step,status, msg):
            if status!="done":
                thinking_dict[step] = msg
                # msg = {'key':'step1','title':'正在理解问题','content': 'LLM started'}
                thinking_list = [ item for item in thinking_dict.values()]
                await emit("thinking",{"status":status,"title":msg["title"],"content":thinking_list})
            else:
                thinking_list = [ item for item in thinking_dict.values()]
                await emit("thinking",{"status":status,"title":"思考完成","content":thinking_list})


        if is_tts:
            tts_service = TtsService(emit=emit)
    
        async def emit_data(data):
            print(data)
            content = data["content"]
            await emit("message",{'content': content})
            if is_tts:
                await tts_service.speak(content)
        
        fsm = CiteFSM()
        rag_citation_dict = {}
        currenct_citation_dict = {}
        # self.collector = ResultCollector(on_result=lambda r:emit_data(parse_result(r)))
        # self.collector = StreamingXMLParser(
        #     on_content=lambda text: emit("message", {"content": text}),
        #     on_result=lambda result: print(result)
        # )
            # asyncio.create_task(tts_service.emit_audio(emit))
        
        thought_chain_msg = []
        content = await llm_service.build_prompt(
                req,
                system_prompt,
                template,
                queue=queue,
            )
        
        # thought_chain_msg.append(content)
        # msg = {'key':'step1','title':'正在理解问题','content': 'LLM started'}
        await emit_thinking("step1","running",{'title':'正在理解问题','content': 'LLM started'})
        # thought_chain_msg.append(msg)
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
                #    response_format={"type": "json"},
                    # stream=True,
                    tools=tools,
                    # response_format={
                    #     'type': 'json_object'
                    # },
                    messages=current_messages,
                    # extra_body={
                    #     "enable_search": True,
                    #     "search_options": {"enable_search_extension": True},
                    #     "search_options": {
                    #         "enable_source": True,
                    #         "enable_citation": True,
                    #         "citation_format": "[ref_<number>]"
                    #     }
                    # }
                    # response_format={"type": "json_object"}

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
                            # await self.collector.feed(event.delta)
                            self.sentence_buffer += event.delta
                            # print("event.delta: "+event.delta)

                            out = []
                            tts_out = [] 
                            for ch in event.delta:
                                for ev in fsm.feed(ch):
                                    if ev.type == "TEXT":
                                        out.append(ev.text)
                                        tts_out.append(ev.text)
                                    elif ev.type == "CITE":
                                        # counter += 1  
                                        cite_nums = ev.raw_cite.split(",")
                                        for num in cite_nums:
                                            num = str(num.strip())
                                            if currenct_citation_dict.get(num) is None:
                                                citation = rag_citation_dict.get(num)
                                                if citation:
                                                    currenct_citation_dict[num] ={
                                                        "chunk_id": num,
                                                        "title": citation["title"],
                                                        "number":len(currenct_citation_dict)+1
                                                    }
                                        await emit("citation", {"content": currenct_citation_dict})


                                        def circled_number(n: int) -> str:
                                            """
                                            返回 Unicode 圆圈数字 1-20
                                            """
                                            if 1 <= n <= 20:
                                                return chr(0x2460 + n - 1)
                                            else:
                                                raise ValueError("只支持 1~20")
                                        display_num_list = []
                                        chunk_id_list = []
                                        for num in cite_nums:
                                            num = num.strip()
                                            if num in currenct_citation_dict:
                                                display_num = currenct_citation_dict[num]["number"]
                                                display_num_list.append(circled_number(display_num))
                                                chunk_id_list.append(num)


                                            
                                        if len(display_num_list)>0:
                                            display_num_str = ",".join(display_num_list)
                                            chunk_id_str = ",".join(chunk_id_list)
                                            out.append(f"[{display_num_str}](cite:{chunk_id_str})")



                                        # out.append(f"#ref{ev.raw_cite}")
                                        print(f"Citation found: {ev.raw_cite}")     

                            if out:
                                out_str = "".join(out)
                                # print("out_str: "+out_str)
                                await emit("message", {"content": out_str})
                            # await emit("message",{'content': event.delta})

                            if is_tts:
                                tts_out_str = "".join(tts_out)
                                await tts_service.speak(tts_out_str)


                            # print(f"Delta received: {event.delta} ")
                        elif event.type == "tool_calls.function.arguments.delta":
                            pass
                            # yield f"event: message\ndata: {json.dumps({'content': event.arguments_delta})}\n\n"
                        elif event.type == "tool_calls.function.arguments.done":
                            
                            # if idx in tool_calls:
                            #     # tool_calls[idx]["arguments"] = event.arguments
                            #     event.id = tool_calls[idx].id
                            # if event.name!="format_tools" :
                            pending_tool_calls.append(event)
                            # msg = f"Tool call {event.name} with arguments {event.arguments}."
                            # yield f"event: message\ndata: {json.dumps({'content': msg})}\n\n"
                            print(f"Tool call {event.name}: {event.arguments}.")
                            # msg = {'title':f"Tool Call: {event.name}",'content':f"Tool call {event.name} with arguments {event.arguments}."}
                            # # yield f"event:status\ndata:{json.dumps(msg)}\n\n"
                            # await emit("thinking",msg)
                            # thought_chain_msg.append(msg)
                        elif event.type == "error":
                            await emit("message",{'content': f"[Error] {event.error}"})
                        await asyncio.sleep(0)  # 让事件循环更流畅

            
                    
                    # ---------- ② 如果没有 tool call → 完成  ----------
                    if not pending_tool_calls:
                        break
                    else:
                        await emit_thinking("step1","running",{'title':'理解问题完成','content': 'LLM started'})

                    tool_results = []
                    if pending_tool_calls: 
                        for tc in pending_tool_calls:
                            idx = tc.index
                            if idx in  tool_calls:
                                args = json.loads(tc.arguments)
                                
                                result = await self.tool_manager.run(tc.name, emit_thinking,{**args})
                                if tc.name=="rag_tools":
                                    # 处理 RAG 工具的特殊输出格式
                                    #  {
                                    #     "data":[
                                    #         {
                                    #             "chunk_id": "12345679",
                                    #             "content": content1,
                                    #             "title": "低剂量阿司匹林对PI3K突变结直肠癌的影响研究综述"
                                    #         },{
                                    #             "chunk_id": "89454131",
                                    #             "content": contenet2,
                                    #             "title": "SAKK 41/13试验：辅助阿司匹林在PIK3CA突变结肠癌中的疗效分析"
                                    #         }
                                    #     ]
                                    # }

                                    data = result["data"]
                                    data_str = ""
                                    for item in data:
                                        chunk_id = item["chunk_id"]
                                        content = item["content"]
                                        if chunk_id not in rag_citation_dict:
                                            rag_citation_dict[chunk_id] = item

                                        # title = item.get("title","")
                                        data_str += f"chunk_id: {chunk_id}\n{content}\n\n"
                                    tool_results.append({
                                        "role": "tool",
                                        "name": tc.name,
                                        "tool_call_id":  tool_calls[idx]["id"],
                                        "content": data_str
                                    })
                                    print(f"RAG tool result: {data_str}")
                                else:
                                    tool_results.append({
                                        "role": "tool",
                                        "name": tc.name,
                                        "tool_call_id":  tool_calls[idx]["id"],
                                        "content": result
                                    })
                        
                        await emit_thinking("step2","done",{'title':"工具调用结束",'content': 'LLM started'})

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