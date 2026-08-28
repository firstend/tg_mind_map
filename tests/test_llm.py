"""Тесты для shared.llm: extract_theme, infer_status."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.llm import extract_theme, infer_status


def test_extract_theme_empty_text():
    """Пустой текст → дефолт с suggested_role universal, context_type chitchat."""
    got = extract_theme("")
    assert got["theme"] == ""
    assert got["suggested_role"] == "universal"
    assert got["action_type"] == "new_thought"
    assert got["context_type"] == "chitchat"
    assert got["project_switch"] is False


def test_extract_theme_empty_whitespace():
    """Только пробелы → дефолт."""
    got = extract_theme("   \n  ")
    assert got["suggested_role"] == "universal"


@patch("shared.llm._client")
def test_extract_theme_parses_suggested_role(mock_client):
    """Мок LLM возвращает JSON → suggested_role, context_type, project_switch парсятся."""
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content='{"context_type": "project", "theme": "План тренировок", "key_parts": "", '
                '"action_type": "request", "is_continuation": false, "parent_hint": null, '
                '"project_switch": false, "suggested_role": "generator"}'
            )
        )
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_resp

    got = extract_theme("Предложи варианты плана тренировок")
    assert got["theme"] == "План тренировок"
    assert got["suggested_role"] == "generator"
    assert got["action_type"] == "request"
    assert got["context_type"] == "project"
    assert got["project_switch"] is False


@patch("shared.llm._client")
def test_extract_theme_parses_context_type_and_project_switch(mock_client):
    """context_type chitchat и project_switch true парсятся."""
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content='{"context_type": "chitchat", "theme": "привет", "key_parts": "", '
                '"action_type": "new_thought", "is_continuation": false, "parent_hint": null, '
                '"project_switch": true, "suggested_role": "universal"}'
            )
        )
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_resp
    got = extract_theme("Привет!")
    assert got["context_type"] == "chitchat"
    assert got["project_switch"] is True


@patch("shared.llm._client")
def test_extract_theme_invalid_suggested_role_falls_back_to_universal(mock_client):
    """Невалидный suggested_role → universal."""
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content='{"context_type": "project", "theme": "Тест", "key_parts": "", "action_type": "new_thought", '
                '"is_continuation": false, "parent_hint": null, "project_switch": false, "suggested_role": "hacker"}'
            )
        )
    ]
    mock_client.return_value.chat.completions.create.return_value = mock_resp

    got = extract_theme("Какая-то мысль")
    assert got["suggested_role"] == "universal"


@patch("shared.llm._client")
def test_extract_theme_exception_returns_fallback_with_universal(mock_client):
    """Исключение при вызове LLM → fallback с suggested_role universal."""
    mock_client.return_value.chat.completions.create.side_effect = RuntimeError("API error")

    got = extract_theme("Предложи идеи")
    assert got["theme"] == "Предложи идеи"[:80]
    assert got["suggested_role"] == "universal"
    assert got["action_type"] == "new_thought"
    assert got["context_type"] == "project"


# --- infer_status ---


@pytest.mark.parametrize(
    "text,action_type,expected",
    [
        ("Отложим проект", "new_thought", "deferred"),
        ("потом доделаем", "new_thought", "deferred"),
        ("любой текст", "defer", "deferred"),
        ("Принято решение", "new_thought", "accepted"),
        ("Сделаем так", "new_thought", "accepted"),
        ("да, так и будет", "new_thought", "accepted"),
        ("Отклоняем идею", "new_thought", "rejected"),
        ("не надо этого", "new_thought", "rejected"),
        ("В работе сейчас", "new_thought", "in_progress"),
        ("делаем апдейт", "new_thought", "in_progress"),
        ("Просто новая мысль", "new_thought", "idea"),
    ],
)
def test_infer_status(text, action_type, expected):
    assert infer_status(text, action_type) == expected
