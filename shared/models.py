"""Модели сообщений для очередей incoming/outgoing и llm."""

from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field


class LLMJobType(str, Enum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    JSON_EXTRACT = "json_extract"


class LLMJob(BaseModel):
    """Задача для LLM-сервиса."""

    job_id: str
    type: LLMJobType
    payload: dict
    reply_queue: str = "mindmap:llm_results"
    priority: int = 0


class LLMResult(BaseModel):
    """Результат выполнения LLM job."""

    job_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


class IncomingMessage(BaseModel):
    """Запрос пользователя из Telegram → в очередь incoming."""

    chat_id: int
    user_id: int
    text: str = ""
    message_id: Optional[int] = None
    voice_file_id: Optional[str] = None  # для будущей транскрипции голоса
    callback_query_id: Optional[str] = None  # если пришло из callback (кнопка)


class OutgoingMessage(BaseModel):
    """Ответ пользователю → в очередь outgoing → Telegram."""

    chat_id: int
    text: str
    reply_to_message_id: Optional[int] = None
    reply_markup: Optional[dict[str, Any]] = None  # InlineKeyboardMarkup и т.д.
    callback_query_id: Optional[str] = None  # если нужно ответить на callback (снять loading)
