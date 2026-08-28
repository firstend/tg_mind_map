"""Разбор Telegram Update в IncomingMessage."""

from typing import Any, Optional

from shared.models import IncomingMessage


def extract_incoming(update: dict[str, Any]) -> Optional[IncomingMessage]:
    """Из Update Telegram извлекаем chat_id, user_id, text. Поддержка message и callback_query."""
    # callback_query — нажатие кнопки (например удаление)
    cb = update.get("callback_query")
    if cb:
        data = (cb.get("data") or "").strip()
        if data.startswith("del:"):
            node_id = data[4:].strip()
            if node_id:
                msg = cb.get("message") or {}
                chat = msg.get("chat", {})
                from_user = cb.get("from") or {}
                return IncomingMessage(
                    chat_id=chat.get("id", 0),
                    user_id=from_user.get("id", 0),
                    text=f"/del {node_id}",
                    message_id=msg.get("message_id"),
                    callback_query_id=cb.get("id"),
                )
        return None

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    chat = msg.get("chat")
    from_user = msg.get("from")
    if not chat or not from_user:
        return None
    text = (msg.get("text") or "").strip()
    voice = msg.get("voice")
    voice_file_id = voice.get("file_id") if voice else None
    return IncomingMessage(
        chat_id=chat["id"],
        user_id=from_user["id"],
        text=text,
        message_id=msg.get("message_id"),
        voice_file_id=voice_file_id,
    )
