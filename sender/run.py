"""
Sender: забирает из очереди outgoing и отправляет в Telegram.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
import httpx

# корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import OutgoingMessage
from shared.queues import pop_outgoing

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_to_telegram(msg: OutgoingMessage) -> None:
    payload = {
        "chat_id": msg.chat_id,
        "text": msg.text,
    }
    if msg.reply_to_message_id is not None:
        payload["reply_to_message_id"] = msg.reply_to_message_id
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{BASE_URL}/sendMessage", json=payload)
        r.raise_for_status()


def run_sender() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Укажи BOT_TOKEN в окружении или .env")
    while True:
        msg = pop_outgoing(timeout_seconds=30)
        if msg is None:
            continue
        try:
            send_to_telegram(msg)
        except Exception as e:
            # TODO: логировать, повторные попытки
            print(f"Send failed: {e}", flush=True)


if __name__ == "__main__":
    run_sender()
