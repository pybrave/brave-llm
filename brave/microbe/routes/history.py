from fastapi import APIRouter
from brave.microbe.schemas.chat_history import QueryChatHistory
from brave.microbe.service import history_service
from brave.api.config.db import get_engine

history_api = APIRouter(prefix="/history", tags=["history"])

@history_api.post("/page_chat_history")
async def page_chat_history(query:QueryChatHistory):
    with get_engine().begin() as conn:
        result = history_service.page_chat_history(conn, query)
    return result
