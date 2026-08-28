"""Клиент LLM-сервиса: отправка задач и ожидание результата."""

import time
from uuid import uuid4

from shared.models import LLMJob, LLMResult, LLMJobType
from shared.queues import push_llm_job, pop_llm_result, LLM_RESULTS_KEY


class LLMError(Exception):
    pass


def wait_for_llm_result(job_id: str, timeout_seconds: int = 120) -> LLMResult:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        raw = pop_llm_result(timeout_seconds=min(5, remaining))
        if raw and raw.job_id == job_id:
            return raw
        if raw and raw.job_id != job_id:
            push_llm_result(raw, queue=LLM_RESULTS_KEY)
    raise TimeoutError(f"LLM job {job_id} timed out")


def submit_chat(
    system: str,
    user: str,
    max_tokens: int = 1500,
    role_hint: str | None = None,
) -> str:
    job_id = uuid4().hex
    job = LLMJob(
        job_id=job_id,
        type=LLMJobType.CHAT,
        payload={
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "role_hint": role_hint or "universal",
        },
    )
    push_llm_job(job)
    result = wait_for_llm_result(job_id, timeout_seconds=120)
    if not result.success:
        raise LLMError(result.error)
    return result.result


def submit_embedding(text: str, dimensions: int | None = None) -> list[float]:
    job_id = uuid4().hex
    job = LLMJob(
        job_id=job_id,
        type=LLMJobType.EMBEDDING,
        payload={"text": text, "dimensions": dimensions},
    )
    push_llm_job(job)
    result = wait_for_llm_result(job_id, timeout_seconds=60)
    if not result.success:
        raise LLMError(result.error)
    return result.result


def submit_json_extract(
    prompt: str,
    schema_hint: str = "",
    max_tokens: int = 200,
) -> dict:
    job_id = uuid4().hex
    job = LLMJob(
        job_id=job_id,
        type=LLMJobType.JSON_EXTRACT,
        payload={"prompt": prompt, "schema_hint": schema_hint, "max_tokens": max_tokens},
    )
    push_llm_job(job)
    result = wait_for_llm_result(job_id, timeout_seconds=60)
    if not result.success:
        raise LLMError(result.error)
    return result.result
