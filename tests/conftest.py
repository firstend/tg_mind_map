"""Pytest fixtures. USE_LLM_SERVICE=false в тестах — мокируем shared.llm напрямую, без Redis."""

import pytest


@pytest.fixture(autouse=True)
def use_direct_llm(monkeypatch):
    """Отключаем llm_service в тестах: shared.llm вызывает LLM напрямую (мокается _client)."""
    import shared.llm as llm_mod
    monkeypatch.setattr(llm_mod, "USE_LLM_SERVICE", False)
