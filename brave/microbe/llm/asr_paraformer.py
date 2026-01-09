import asyncio
import base64
import os
import threading
import time
import dashscope
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts_v2 import *
from requests_cache import datetime
from dashscope.audio.asr import (Recognition, RecognitionCallback,
                                 RecognitionResult)


def get_timestamp():
    now = datetime.now()
    formatted_timestamp = now.strftime("[%Y-%m-%d %H:%M:%S.%f]")
    return formatted_timestamp



class Callback(RecognitionCallback):
    def __init__(self, loop: asyncio.AbstractEventLoop, emit: callable):
        dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
        self.loop = loop
        self.emit = emit
        self.asr_result = ""


    def on_open(self) -> None:
        # global mic
        # global stream
        # print('RecognitionCallback open.')
        pass
        # mic = pyaudio.PyAudio()
        # stream = mic.open(format=pyaudio.paInt16,
        #                   channels=1,
        #                   rate=16000,
        #                   input=True)

    def on_close(self) -> None:
        # global mic
        # global stream
        print('RecognitionCallback close.')
        # stream.stop_stream()
        # stream.close()
        # mic.terminate()
        # stream = None
        # mic = None

    def on_event(self, result: RecognitionResult) -> None:
        sentence =  result.get_sentence()
        print('RecognitionCallback sentence: ',sentence["text"])

        # def schedule_emit(event, data):
        #     asyncio.create_task(self.emit(event, data))
        text = sentence["text"]
        if text != "":
            # self.loop.call_soon_threadsafe(self.queue.put_nowait, {
            #     "event": "asr",
            #     "data": {
            #         "content": text,
            #     }
            # })
            asyncio.run_coroutine_threadsafe(
                self.emit("asr", {
                    "content": text
                }),
                self.loop
            )
            self.asr_result = text

            # self.asr_result = text
            # def schedule_emit(event, data):
            #     asyncio.create_task(self.emit(event, data))
            # self.loop.call_soon_threadsafe(schedule_emit, "asr", {
            #         "content": text
            #     })


class QwenASRWorker:
    def __init__(self, loop: asyncio.AbstractEventLoop, emit:Callback):
        self.loop = loop
        self.audio_queue = asyncio.Queue()
        # self.audio_queue = asyncio.Queue()
        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )
        self.emit = emit
        self.asr_reslut = loop.create_future()

    def start(self):
        self.thread.start()

    def _run(self):
        # time.sleep(15)  # 确保事件循环已启动
        # print("[TTS Worker] TTS worker thread ended sleep.")

        callback = Callback(self.loop,  self.emit)

        recognition = Recognition(model='paraformer-realtime-v2',
                            format='pcm',
                            sample_rate=16000,
                            callback=callback)

        recognition.start()
        while True:
            data = asyncio.run_coroutine_threadsafe(
                self.audio_queue.get(),
                self.loop
            ).result()

            if data is None:
                break
            # print(f"[ASR Worker] ASR audio frame: {len(data)} bytes")
            recognition.send_audio_frame(data)

        recognition.stop()
        asr_result = callback.asr_result
        self.loop.call_soon_threadsafe(
            self.asr_reslut.set_result,
            asr_result
        )
        # if asr_result!="":
        #     asyncio.run_coroutine_threadsafe(
        #         self.emit("event", {
        #             "content": "asr_done"
        #         }),
        #         self.loop
        #     )
        # return asr_result
        # print(f"[ASR Worker] ASR worker thread ended. Final result: {asr_result}")
        


class ASRService:
    def __init__(self,emit):
        self.emit=emit  
        loop = asyncio.get_running_loop()
        self.worker = QwenASRWorker(loop,self.emit)
        # self.final_result = loop.create_future()

        asyncio.create_task(self.start())
    # async def emit_(self, event: str, data: dict):
    #     await self.emit(event, data)
    #     self.final_result.set_result(data["content"])
    async def start(self):
      
        self.worker.start()

    async def recognition(self, text: str):
        if text != "":
            await self.worker.audio_queue.put(text)
    async def stop(self):
        await self.worker.audio_queue.put(None)
        # if self.worker.thread.is_alive():
        await asyncio.to_thread(self.worker.thread.join)
        print("[ASR Service] ASR service stopped.")
        result = await self.worker.asr_reslut
        return result
