import asyncio
import os
import threading
import dashscope
from dashscope.audio.qwen_tts_realtime import *


class AsyncQwenTtsCallback(QwenTtsRealtimeCallback):
    """
    将 QwenTtsRealtime 回调异步化，
    audio delta 数据通过 asyncio.Queue 推送给事件循环。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, audio_queue: asyncio.Queue):
        dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
        self.loop = loop
        self.audio_queue = audio_queue
        self.done_event = threading.Event()  # 标记 session 完成

    def on_open(self):
        print("[TTS Callback] WSS opened")

    def on_close(self, close_status_code, close_msg):
        print(f"[TTS Callback] WSS closed: {close_status_code}, {close_msg}")
        # 通知 asyncio 端队列结束
        self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
        self.done_event.set()

    def on_event(self, response: dict):
        # print(response)
        """
        response: dict, 可能包含：
        - type: "session.created", "response.audio.delta", "response.done", "session.finished"
        - delta: base64音频
        """
        try:
            rtype = response.get("type")
            if rtype == "response.audio.delta":
                audio_b64 = response.get("delta")
                print(f"[TTS Callback] Received audio delta, size: {len(audio_b64) if audio_b64 else 0}")
                if audio_b64:
                    # 安全地推送给 asyncio 队列
                    self.loop.call_soon_threadsafe(
                        self.audio_queue.put_nowait,
                        audio_b64
                    )
            elif rtype in ("response.done", "session.finished"):
                # 结束标记
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
                self.done_event.set()
            elif rtype == "session.created":
                session_id = response.get("session", {}).get("id")
                print(f"[TTS Callback] Session created: {session_id}")

        except Exception as e:
            print(f"[TTS Callback Error] {e}")
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)
            self.done_event.set()

    def wait_for_finished(self, timeout: float = None):
        """
        阻塞等待 session 完成，用于线程结束同步。
        """
        self.done_event.wait(timeout=timeout)


class QwenTtsWorker:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.text_queue = asyncio.Queue()
        self.audio_queue = asyncio.Queue()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )

    def start(self):
        self.thread.start()

    def _run(self):
        callback = AsyncQwenTtsCallback(self.loop, self.audio_queue)

        self.tts = QwenTtsRealtime(
            model="qwen3-tts-flash-realtime",
            callback=callback,
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        )

        self.tts.connect()
        self.tts.update_session(
            voice="Cherry",
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode="server_commit",
        )
        session_id = self.tts.get_session_id()
        response_id = self.tts.get_last_response_id()
        print(f"[TTS Worker] Session ID: {session_id}, Response ID: {response_id}")

        while True:
            text = asyncio.run_coroutine_threadsafe(
                self.text_queue.get(),
                self.loop
            ).result()

            if text is None:
                break
            print(f"[TTS Worker] TTS text: {text[:20]}")
            self.tts.append_text(text)

        # self.tts.finish()
        self.tts.finish()
        callback.wait_for_finished()
        self.tts.close()


class TtsService:
    def __init__(self):
        self.worker = None

    async def start(self):
        loop = asyncio.get_running_loop()
        self.worker = QwenTtsWorker(loop)
        self.worker.start()

    async def speak(self, text: str):
        if text != "":
            await self.worker.text_queue.put(text)

    async def emit_audio(self,emit):
        while True:
            audio = await self.worker.audio_queue.get()
            if audio is None:
                break
            await emit("audio", {
                "content": audio,
                "format": "pcm",
                "sample_rate": 24000,
            })
