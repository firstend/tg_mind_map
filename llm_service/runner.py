"""Цикл обработки LLM-задач из очереди."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.queues import pop_llm_job, push_llm_result
from shared.models import LLMJob
from llm_service.executor import execute_job


def run_llm_service() -> None:
    while True:
        job = pop_llm_job(timeout_seconds=30)
        if job is None:
            continue
        result = execute_job(job)
        push_llm_result(result, queue=job.reply_queue)


if __name__ == "__main__":
    run_llm_service()
