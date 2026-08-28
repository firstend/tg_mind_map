"""Выполнение LLM-задач: chat, embedding, json_extract."""

import json
import re
import time
from typing import Any

from shared.llm import (
    _client,
    _chat_model,
    _embedding_model,
    LLM_PROVIDER,
    QWEN_EMBEDDING_DIM,
    MAX_REPLY_CHARS,
)
from shared.models import LLMJob, LLMResult, LLMJobType


def _do_chat(payload: dict) -> str:
    system = payload.get("system", "")
    user = payload.get("user", "")
    max_tokens = int(payload.get("max_tokens", 1500))
    c = _client()
    r = c.chat.completions.create(
        model=_chat_model(),
        messages=[
            {"role": "system", "content": system or "Ты помощник."},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    reply = (r.choices[0].message.content or "").strip()
    return reply[:MAX_REPLY_CHARS] if reply else "Мысль принята, контекст учтён."


def _do_embedding(payload: dict) -> list[float]:
    text = (payload.get("text") or "").strip() or "пусто"
    dimensions = payload.get("dimensions")
    c = _client()
    kwargs = {"input": [text], "model": _embedding_model()}
    if LLM_PROVIDER == "qwen":
        kwargs["dimensions"] = dimensions or QWEN_EMBEDDING_DIM
    r = c.embeddings.create(**kwargs)
    return r.data[0].embedding


def _do_json_extract(payload: dict) -> dict:
    prompt = payload.get("prompt", "")
    max_tokens = int(payload.get("max_tokens", 200))
    c = _client()
    r = c.chat.completions.create(
        model=_chat_model(),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    raw = (r.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def execute_job(job: LLMJob) -> LLMResult:
    start = time.monotonic()
    try:
        if job.type == LLMJobType.CHAT:
            out = _do_chat(job.payload)
        elif job.type == LLMJobType.EMBEDDING:
            out = _do_embedding(job.payload)
        elif job.type == LLMJobType.JSON_EXTRACT:
            out = _do_json_extract(job.payload)
        else:
            return LLMResult(job_id=job.job_id, success=False, error=f"Unknown type: {job.type}")
        duration_ms = int((time.monotonic() - start) * 1000)
        return LLMResult(job_id=job.job_id, success=True, result=out, duration_ms=duration_ms)
    except Exception as e:
        return LLMResult(job_id=job.job_id, success=False, error=str(e))
