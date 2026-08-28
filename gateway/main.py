"""
Gateway: приём webhook или long polling от Telegram, постановка в очередь incoming.
"""

import os
import threading

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response

from gateway.updates import extract_incoming
from shared.queues import push_incoming

GATEWAY_MODE = os.environ.get("GATEWAY_MODE", "poll").lower()


def _run_poller() -> None:
    from gateway.poller import run_poller
    run_poller()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if GATEWAY_MODE == "poll":
        t = threading.Thread(target=_run_poller, daemon=True)
        t.start()
    yield


app = FastAPI(title="Mind Map Gateway", lifespan=lifespan)


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
    """Проверка: процесс жив, Redis доступен."""
    from shared.queues import get_redis

    redis_ok = False
    try:
        r = get_redis()
        r.ping()
        redis_ok = True
    except Exception:
        pass
    status = "ok" if redis_ok else "degraded"
    return {"status": status, "redis": "ok" if redis_ok else "unavailable"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
