"""Клиент очередей на Redis (incoming / outgoing)."""

import os
from typing import Optional

import redis

from .models import IncomingMessage, OutgoingMessage

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
INCOMING_KEY = "mindmap:incoming"
OUTGOING_KEY = "mindmap:outgoing"


def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def push_incoming(msg: IncomingMessage) -> None:
    r = get_redis()
    r.lpush(INCOMING_KEY, msg.model_dump_json())


def pop_incoming(timeout_seconds: int = 30) -> Optional[IncomingMessage]:
    r = get_redis()
    raw = r.brpop(INCOMING_KEY, timeout=timeout_seconds)
    if raw is None:
        return None
    _, payload = raw
    return IncomingMessage.model_validate_json(payload)


def push_outgoing(msg: OutgoingMessage) -> None:
    r = get_redis()
    r.lpush(OUTGOING_KEY, msg.model_dump_json())


def pop_outgoing(timeout_seconds: int = 30) -> Optional[OutgoingMessage]:
    r = get_redis()
    raw = r.brpop(OUTGOING_KEY, timeout=timeout_seconds)
    if raw is None:
        return None
    _, payload = raw
    return OutgoingMessage.model_validate_json(payload)
