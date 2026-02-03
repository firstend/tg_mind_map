"""Модели сообщений для очередей incoming/outgoing."""

from pydantic import BaseModel, Field
from typing import Optional


class IncomingMessage(BaseModel):
    """Запрос пользователя из Telegram → в очередь incoming."""

    chat_id: int
    user_id: int
    text: str = ""
    message_id: Optional[int] = None
    voice_file_id: Optional[str] = None  # для будущей транскрипции голоса


class OutgoingMessage(BaseModel):
    """Ответ пользователю → в очередь outgoing → Telegram."""

    chat_id: int
    text: str
    reply_to_message_id: Optional[int] = None
