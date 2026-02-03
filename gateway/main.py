"""
Gateway: приём webhook от Telegram, постановка в очередь incoming.
"""

import os

from dotenv import load_dotenv
load_dotenv()
from typing import Any, Optional

from fastapi import FastAPI, Request, Response

from shared.models import IncomingMessage
from shared.queues import push_incoming

app = FastAPI(title="Mind Map Gateway")


def extract_incoming(request_body: dict[str, Any]) -> Optional[IncomingMessage]:
    """Из Update Telegram извлекаем chat_id, user_id, text, message_id, voice."""
    msg = request_body.get("message") or request_body.get("edited_message")
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


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Принимаем Update от Telegram, кладём в очередь incoming."""
    body = await request.json()
    incoming = extract_incoming(body)
    if incoming is None:
        return Response(status_code=200)  # всё равно 200, чтобы Telegram не ретраил
    push_incoming(incoming)
    return Response(status_code=200)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
