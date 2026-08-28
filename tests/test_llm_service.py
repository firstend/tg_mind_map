"""Тесты llm_service: executor с моком LLM."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_service.executor import execute_job
from shared.models import LLMJob, LLMJobType, LLMResult


@patch("llm_service.executor._client")
def test_execute_job_chat(mock_client):
    """CHAT job → вызывает chat.completions.create, возвращает reply."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="  Вот ответ  "))]
    mock_client.return_value.chat.completions.create.return_value = mock_resp

    job = LLMJob(
        job_id="x",
        type=LLMJobType.CHAT,
        payload={"system": "Ты помощник.", "user": "Привет", "max_tokens": 100},
    )
    result = execute_job(job)

    assert isinstance(result, LLMResult)
    assert result.job_id == "x"
    assert result.success is True
    assert result.result == "Вот ответ"
    assert result.duration_ms >= 0


@patch("llm_service.executor._client")
def test_execute_job_embedding(mock_client):
    """EMBEDDING job → вызывает embeddings.create, возвращает вектор."""
    vec = [0.1] * 1536
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(embedding=vec)]
    mock_client.return_value.embeddings.create.return_value = mock_resp

    job = LLMJob(
        job_id="y",
        type=LLMJobType.EMBEDDING,
        payload={"text": "тест", "dimensions": 1536},
    )
    result = execute_job(job)

    assert result.success is True
    assert result.result == vec


@patch("llm_service.executor._client")
def test_execute_job_json_extract(mock_client):
    """JSON_EXTRACT job → парсит JSON из ответа."""
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(content='{"parent_id": "a1", "edge_type": "continuation"}')
        )
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_resp

    job = LLMJob(
        job_id="z",
        type=LLMJobType.JSON_EXTRACT,
        payload={"prompt": "Classify...", "max_tokens": 100},
    )
    result = execute_job(job)

    assert result.success is True
    assert result.result == {"parent_id": "a1", "edge_type": "continuation"}


