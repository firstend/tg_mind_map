"""
Опрос Telegram (long polling) вместо webhook.
Не требует публичного HTTPS — удобно для локальной разработки и простого деплоя.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.updates import extract_incoming
from shared.queues import push_incoming

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_TIMEOUT = 25


def delete_webhook() -> None:
    """Снимаем webhook, иначе getUpdates ничего не вернёт."""
    with httpx.Client(timeout=10.0) as client:
        r = client.post(f"{BASE_URL}/deleteWebhook", json={"drop_pending_updates": False})
        r.raise_for_status()


def poll_updates(offset: int | None) -> list[dict]:
    """Long poll getUpdates. Возвращает список Update."""
    payload = {"offset": offset, "timeout": POLL_TIMEOUT}
    payload["allowed_updates"] = ["message", "edited_message", "callback_query"]
    with httpx.Client(timeout=POLL_TIMEOUT + 10) as client:
        r = client.post(f"{BASE_URL}/getUpdates", json=payload)
        r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data.get("result", [])


def run_poller() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Укажи BOT_TOKEN в окружении или .env")
    delete_webhook()
    print("Poller: long polling started (webhook снят)", flush=True)
    offset = None
    while True:
        try:
            updates = poll_updates(offset)
            for u in updates:
                offset = u["update_id"] + 1
                incoming = extract_incoming(u)
                if incoming is not None:
                    push_incoming(incoming)
        except Exception as e:
            print(f"Poller error: {e}", flush=True)
            # offset не меняем — повторно обработаем при reconnect


if __name__ == "__main__":
    run_poller()
