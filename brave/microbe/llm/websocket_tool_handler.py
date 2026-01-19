from fastapi import WebSocket
from typing import Dict
import asyncio
import uuid

# class WSConnection:
#     def __init__(self, ws: WebSocket, client_id: str):
#         self.ws = ws
#         self.client_id = client_id
#         self.queue = asyncio.Queue(maxsize=100)
#         self.alive = True

#     async def sender(self):
#         try:
#             while self.alive:
#                 msg = await self.queue.get()
#                 if msg is None:
#                     break
#                 await self.ws.send_json(msg)
#         except Exception:
#             self.alive = False

#     async def close(self):
#         self.alive = False
#         await self.queue.put(None)
#         await self.ws.close()

from fastapi import WebSocket
import asyncio

class WSConnection:
    def __init__(self, ws: WebSocket, client_id: str):
        self.ws = ws
        self.client_id = client_id
        self.queue = asyncio.Queue()
        self.alive = True
        self._sender_task: asyncio.Task | None = None

    def start(self):
        self._sender_task = asyncio.create_task(self.sender())

    async def sender(self):
        try:
            while True:
                msg = await self.queue.get()
                if msg is None:
                    break
                await self.ws.send_json(msg)
        except Exception as e:
            print(f"WebSocket sender error: {e}")
            self.alive = False
        finally:
            # sender 退出，确保 ws 关闭
            self.alive = False
            await self._safe_ws_close()

    async def send(self, msg: dict):
        if self.alive:
            await self.queue.put(msg)

    async def close(self):
        if not self.alive:
            return

        self.alive = False

        # 唤醒 sender
        await self.queue.put(None)

        # 等 sender 退出
        if self._sender_task:
            await self._sender_task

        await self.queue.join()

        await self._safe_ws_close()

    async def _safe_ws_close(self):
        try:
            await self.ws.close()
        except Exception as e:
            # print(f"Error closing WebSocket: {e}")
            pass

class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, WSConnection] = {}

    async def connect(self, ws: WebSocket) -> WSConnection:
        await ws.accept()
        client_id = str(uuid.uuid4())
        conn = WSConnection(ws, client_id)
        self.connections[client_id] = conn
        conn.start()
        return conn

    async def disconnect(self, client_id: str):
        conn = self.connections.pop(client_id, None)
        if conn:
            await conn.close()

# class ConnectionManager:
#     def __init__(self):
#         self.connections: Dict[str, WSConnection] = {}

#     async def connect(self, ws: WebSocket) -> WSConnection:
#         await ws.accept()
#         client_id = str(uuid.uuid4())
#         conn = WSConnection(ws, client_id)
#         self.connections[client_id] = conn
#         return conn

#     def disconnect(self, client_id: str):
#         conn = self.connections.pop(client_id, None)
#         if conn:
#             asyncio.create_task(conn.close())
