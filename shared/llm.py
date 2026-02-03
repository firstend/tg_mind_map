"""ИИ: эмбеддинги и чат (OpenAI). Классификация темы и агент «универсальный помощник»."""

import os
from typing import Optional

from openai import OpenAI

client: Optional[OpenAI] = None

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
RAG_TOP_K = 5
MAX_REPLY_CHARS = 1000


def _get_client() -> OpenAI:
    global client
    if client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY не задан")
        client = OpenAI(api_key=api_key)
    return client


def get_embedding(text: str) -> list[float]:
    if not text.strip():
        # пустой текст — нулевой вектор не подходит; используем короткую заглушку
        text = "пусто"
    c = _get_client()
    r = c.embeddings.create(input=[text.strip()], model=EMBEDDING_MODEL)
    return r.data[0].embedding


def classify_topic(
    user_id: int,
    text: str,
    last_nodes: list,
) -> tuple[bool, Optional[str]]:
    """Новая тема или продолжение. Возвращает (is_new_topic, parent_node_id). Пока заглушка: всегда новая тема."""
    # TODO: вызов ИИ с last_nodes и text → is_new_topic, parent_node_id
    return True, None


def universal_assistant(
    query: str,
    user_id: int,
    rag_context: list[dict],
    graph_context: list[dict],
) -> str:
    """Агент «универсальный помощник»: ответ по запросу с учётом RAG и графа."""
    c = _get_client()
    rag_block = "\n".join(
        f"- {c.get('text', '').strip()}" for c in rag_context if c.get("text")
    ) or "(нет релевантных записей)"
    graph_block = "\n".join(
        f"- {n.get('content', '').strip()}" for n in graph_context
    ) or "(нет недавних тем)"
    system = (
        "Ты помощник по карте идей пользователя. Отвечай кратко и по делу, на русском. "
        f"Ограничь ответ {MAX_REPLY_CHARS} символами."
    )
    user_msg = (
        "Релевантные мысли пользователя из базы:\n"
        f"{rag_block}\n\n"
        "Недавние темы пользователя:\n"
        f"{graph_block}\n\n"
        f"Сообщение пользователя: {query}"
    )
    try:
        r = c.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=500,
        )
        reply = (r.choices[0].message.content or "").strip()
        return reply[:MAX_REPLY_CHARS] if reply else "Мысль принята, контекст учтён."
    except Exception as e:
        return f"Временная ошибка, попробуй позже. ({type(e).__name__})"
