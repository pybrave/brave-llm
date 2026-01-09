import os
import aiohttp
import json
import asyncio

DASHSCOPE_TTS_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/"
    "aigc/multimodal-generation/generation"
)

async def tts_stream(text: str):
    api_key = os.getenv('DASHSCOPE_API_KEY')
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable",
    }

    payload = {
        "model": "qwen3-tts-flash",
        "input": {
            "text": text,
            "voice": "Cherry",
            "language_type": "Chinese",
        },
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            DASHSCOPE_TTS_URL,
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()

            async for raw in resp.content:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue

                # SSE: data: {...}
                if not line.startswith("data:"):
                    continue

                data = json.loads(line[5:].strip())

                # 结束信号
                if data.get("event") == "end":
                    break

                audio = (
                    data.get("output", {})
                        .get("audio", {})
                        .get("data")
                )

                if audio:
                    yield audio
