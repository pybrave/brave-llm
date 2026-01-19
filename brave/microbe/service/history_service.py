
from brave.microbe.schemas.chat_history import QueryChatHistory
from brave.microbe.models.core import t_chat_history
from sqlalchemy import select,func,and_

def page_chat_history(conn, query:QueryChatHistory):
    page_number = query.page_number
    page_size = query.page_size
    user_id = query.user_id
    session_id = query.session_id
    role = query.role


    stmt = select(
        t_chat_history
    )
    conditions = []
    if user_id:
        conditions.append(t_chat_history.c.user_id == user_id)
    if session_id:
        conditions.append(t_chat_history.c.session_id == session_id)
    if role:
        conditions.append(t_chat_history.c.role == role)


    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.offset((page_number - 1) * page_size).limit(page_size)
    stmt = stmt.order_by(t_chat_history.c.created_at.asc())

    result = conn.execute(stmt).mappings().all()

    count_stmt = select(func.count()).select_from(t_chat_history).where(and_(*conditions))
    total = conn.execute(count_stmt).scalar()
    result = {
        "items": result,
        "total": total,
        "page_number": page_number,
        "page_size": page_size
    }
    return {
        "data": result,
        "code": 200
    }