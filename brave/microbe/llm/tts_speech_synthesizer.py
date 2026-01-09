import asyncio
import base64
import os
import threading
import time
import dashscope
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts_v2 import *
from requests_cache import datetime

# class AsyncQwenTtsCallback(QwenTtsRealtimeCallback):
#     """
#     将 QwenTtsRealtime 回调异步化，
#     audio delta 数据通过 asyncio.Queue 推送给事件循环。
#     """

#     def __init__(self, loop: asyncio.AbstractEventLoop, audio_queue: asyncio.Queue):
#         dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
#         self.loop = loop
#         self.audio_queue = audio_queue
#         self.done_event = threading.Event()  # 标记 session 完成

#     def on_open(self):
#         print("[TTS Callback] WSS opened")

#     def on_close(self, close_status_code, close_msg):
#         print(f"[TTS Callback] WSS closed: {close_status_code}, {close_msg}")
#         # 通知 asyncio 端队列结束
#         self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
#         self.done_event.set()

#     def on_event(self, response: dict):
#         # print(response)
#         """
#         response: dict, 可能包含：
#         - type: "session.created", "response.audio.delta", "response.done", "session.finished"
#         - delta: base64音频
#         """
#         try:
#             rtype = response.get("type")
#             if rtype == "response.audio.delta":
#                 audio_b64 = response.get("delta")
#                 print(f"[TTS Callback] Received audio delta, size: {len(audio_b64) if audio_b64 else 0}")
#                 if audio_b64:
#                     # 安全地推送给 asyncio 队列
#                     self.loop.call_soon_threadsafe(
#                         self.audio_queue.put_nowait,
#                         audio_b64
#                     )
#             elif rtype in ("response.done", "session.finished"):
#                 # 结束标记
#                 self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
#                 self.done_event.set()
#             elif rtype == "session.created":
#                 session_id = response.get("session", {}).get("id")
#                 print(f"[TTS Callback] Session created: {session_id}")

#         except Exception as e:
#             print(f"[TTS Callback Error] {e}")
#             self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
#             self.done_event.set()

#     def wait_for_finished(self, timeout: float = None):
#         """
#         阻塞等待 session 完成，用于线程结束同步。
#         """
#         self.done_event.wait(timeout=timeout)
def get_timestamp():
    now = datetime.now()
    formatted_timestamp = now.strftime("[%Y-%m-%d %H:%M:%S.%f]")
    return formatted_timestamp

class Callback(ResultCallback):
    # _player = None
    # _stream = None

    def __init__(self, loop: asyncio.AbstractEventLoop,emit: callable):
        dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
        self.loop = loop
        # self.audio_queue = audio_queue
        self.emit=emit

    def on_open(self):
        print("连接建立：" + get_timestamp())
        # self._player = pyaudio.PyAudio()
        # self._stream = self._player.open(
        #     format=pyaudio.paInt16, channels=1, rate=22050, output=True
        # )

    def on_complete(self):
        print("语音合成完成，所有合成结果已被接收：" + get_timestamp())

    def on_error(self, message: str):
        print(f"语音合成出现异常：{message}")

    def on_close(self):
        print("连接关闭：" + get_timestamp())
        # 停止播放器
        # self._stream.stop_stream()
        # self._stream.close()
        # self._player.terminate()

    def on_event(self, message):
        # print("收到事件消息：" + str(message))
        pass

    def on_data(self, data: bytes) -> None:
        print(get_timestamp() + " 二进制音频长度为：" + str(len(data)))
        # self._stream.write(data)
        audio_b64 = base64.b64encode(data).decode("utf-8")
        # self.loop.call_soon_threadsafe(
        #     self.audio_queue.put_nowait,
        #     audio_b64
        # )
        def schedule_emit(event, data):
            asyncio.create_task(self.emit(event, data))
        self.loop.call_soon_threadsafe(schedule_emit, "audio", {
                "content": audio_b64,
                "format": "pcm",
                "sample_rate": 24000,
            })

        # self.loop.call_soon_threadsafe(
        #     self.emit,
        #     "audio", {
        #         "content": audio_b64,
        #         "format": "pcm",
        #         "sample_rate": 24000,
        #     }
        # )



class QwenTtsWorker:
    def __init__(self, loop: asyncio.AbstractEventLoop, emit: callable):
        self.loop = loop
        self.text_queue = asyncio.Queue()
        # self.audio_queue = asyncio.Queue()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )
        self.emit = emit

    def start(self):
        self.thread.start()
    


    def _run(self):
        # time.sleep(15)  # 确保事件循环已启动
        # print("[TTS Worker] TTS worker thread ended sleep.")

        callback = Callback(self.loop,  self.emit)
        # 模型
        model = "cosyvoice-v3-flash"
        # 音色
        voice = "longanyang"
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,  
            callback=callback,
        )


        while True:
            text = asyncio.run_coroutine_threadsafe(
                self.text_queue.get(),
                self.loop
            ).result()

            if text is None:
                break
            print(f"[TTS Worker] TTS text: {text[:20]}")
            synthesizer.streaming_call(text)

        synthesizer.streaming_complete()


class TtsService:
    def __init__(self,emit):
        self.worker = None
        self.emit=emit  
        asyncio.create_task(self.start())

    async def start(self):
        loop = asyncio.get_running_loop()
        self.worker = QwenTtsWorker(loop,self.emit)
        self.worker.start()

    async def speak(self, text: str):
        if text != "":
            await self.worker.text_queue.put(text)

    # async def emit_audio(self,emit):
    #     while True:
    #         audio = await self.worker.audio_queue.get()
    #         if audio is None:
    #             break
    #         await emit("audio", {
    #             "content": audio,
    #             "format": "pcm",
    #             "sample_rate": 24000,
    #         })
    # async def terminate(self):
    #     await self.worker.text_queue.put(None)
    #     await asyncio.to_thread(self.worker.thread)
    def clear_queue_nowait(self):
        try:
            while True:
                self.worker.text_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    async def terminate(self):
        print("TtsService terminate called")
        self.clear_queue_nowait()
        await self.worker.text_queue.put(None)
        await asyncio.to_thread(self.worker.thread.join)
    async def stop(self):
        # if not self.worker:
        #     return

        # # 通知子线程退出
        # self.worker.stop()
        await self.speak(None)
        # 异步等待 join（不会阻塞 event loop）
        await asyncio.to_thread(self.worker.thread.join)