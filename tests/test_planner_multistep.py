"""Тесты мультишагового planner: state, prompts, run_planner_multistep."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.state import StepState, ToolResult
from planner.prompts import build_plan_step_prompt
from planner.run_multistep import run_planner_multistep


# --- State ---


def test_tool_result():
    r = ToolResult(
        server="brave_search",
        tool="brave_web_search",
        args_used={"query": "test"},
        refined_prompt="Улучшенный запрос",
        result="search result",
    )
    assert r.server == "brave_search"
    assert r.tool == "brave_web_search"
    assert r.result == "search result"


def test_step_state_empty():
    s = StepState(original_query="найди про X")
    assert s.original_query == "найди про X"
    assert s.results == []
    assert s.step_number == 0
    assert s.is_done is False


def test_step_state_is_done():
    s = StepState(original_query="x", step_number=5, max_steps=5)
    assert s.is_done is True
    s.step_number = 4
    assert s.is_done is False


# --- Prompts ---


def test_build_plan_step_prompt_empty_results():
    """Промпт для первого шага (нет результатов)."""
    state = StepState(original_query="найди про пептиды", remaining_goal="найди про пептиды")
    catalog = [
        {"server": "brave_search", "name": "brave_web_search", "description": "Web search"},
        {"server": "filesystem", "name": "write_file", "description": "Write file"},
    ]
    p = build_plan_step_prompt(state, catalog)
    assert "найди про пептиды" in p
    assert "brave_web_search" in p
    assert "write_file" in p
    assert "action" in p
    assert "refined" in p or "УЛУЧШЬ" in p
    assert "(пока нет)" in p


def test_build_plan_step_prompt_with_results():
    """Промпт со результатами предыдущего шага."""
    r1 = ToolResult(
        server="brave_search",
        tool="brave_web_search",
        args_used={"query": "пептиды"},
        refined_prompt="Поиск о пептидах",
        result="Пептиды — это короткие цепочки аминокислот...",
    )
    state = StepState(
        original_query="найди и сохрани в файл",
        results=[r1],
        remaining_goal="сохрани в файл",
        step_number=1,
    )
    catalog = [{"server": "filesystem", "name": "write_file", "description": "Write"}]
    p = build_plan_step_prompt(state, catalog)
    assert "Пептиды — это" in p
    assert "сохрани в файл" in p
    assert "write_file" in p


def test_build_plan_step_prompt_truncates_long_result():
    """Длинный результат обрезается."""
    long_result = "x" * 5000
    r = ToolResult("s", "t", {}, None, long_result)
    state = StepState(original_query="q", results=[r], step_number=1)
    catalog = [{"server": "s", "name": "t", "description": "d"}]
    p = build_plan_step_prompt(state, catalog, max_result_chars=100)
    assert "x" * 100 in p
    assert "[... обрезано ...]" in p


# --- run_planner_multistep ---


def test_run_planner_multistep_empty_catalog_returns_none():
    """При пустом каталоге возвращает None."""
    async def fake_catalog(*args, **kwargs):
        return []

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("mcp_hub.MCPHub") as mock_hub:
        mock_hub.return_value.server_names = ["fs"]
        result = run_planner_multistep("test", [], [])
    assert result is None


def test_run_planner_multistep_done_at_step1_returns_none():
    """LLM сразу вернул action=done — нет tool results → None."""
    catalog = [{"server": "fs", "name": "read_file", "description": "Read"}]

    async def fake_catalog(*args, **kwargs):
        return catalog

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run_multistep._call_llm_json", return_value={
             "action": "done",
             "reasoning": "не нужны tools",
             "remaining_goal": "",
         }), \
         patch("mcp_hub.MCPHub"):
        result = run_planner_multistep("привет", [], [])
    assert result is None


def test_run_planner_multistep_one_step_then_done():
    """Один вызов tool, затем done → synthesize."""
    catalog = [{"server": "fs", "name": "read_file", "description": "Read"}]

    async def fake_catalog(*args, **kwargs):
        return catalog

    mock_hub = MagicMock()
    mock_hub.server_names = ["fs"]
    mock_hub.connect = AsyncMock()
    mock_hub.call_tool = AsyncMock(return_value="file content")
    mock_hub.disconnect = AsyncMock()

    llm_responses = [
        {
            "action": "call",
            "reasoning": "читаю файл",
            "remaining_goal": "",
            "call": {
                "server": "fs",
                "tool": "read_file",
                "arguments": {"path": "/tmp/x"},
                "refined_prompt": "Чтение файла",
            },
        },
        {"action": "done", "reasoning": "готово", "remaining_goal": ""},
    ]

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run_multistep._call_llm_json", side_effect=llm_responses), \
         patch("planner.run_multistep._call_llm_chat", return_value="Вот содержимое."), \
         patch("mcp_hub.MCPHub", return_value=mock_hub):
        result = run_planner_multistep("прочитай /tmp/x", [], [])

    assert result == "Вот содержимое."
    mock_hub.call_tool.assert_called_once_with("fs", "read_file", {"path": "/tmp/x"})
    mock_hub.disconnect.assert_called()


def test_run_planner_multistep_two_steps_chain():
    """Два шага: search → write_file (цепочка)."""
    catalog = [
        {"server": "brave_search", "name": "brave_web_search", "description": "Search"},
        {"server": "filesystem", "name": "write_file", "description": "Write"},
    ]

    async def fake_catalog(*args, **kwargs):
        return catalog

    mock_hub = MagicMock()
    mock_hub.server_names = ["brave_search", "filesystem"]
    mock_hub.connect = AsyncMock()
    mock_hub.call_tool = AsyncMock(side_effect=["search result here", "ok"])
    mock_hub.disconnect = AsyncMock()

    llm_responses = [
        {
            "action": "call",
            "reasoning": "поиск",
            "remaining_goal": "сохрани в файл",
            "call": {
                "server": "brave_search",
                "tool": "brave_web_search",
                "arguments": {"query": "пептиды"},
                "refined_prompt": "Поиск о пептидах",
            },
        },
        {
            "action": "call",
            "reasoning": "сохранение",
            "remaining_goal": "",
            "call": {
                "server": "filesystem",
                "tool": "write_file",
                "arguments": {"path": "/tmp/p.txt", "content": "search result here"},
                "refined_prompt": "Сохранение в файл",
            },
        },
        {"action": "done", "reasoning": "готово", "remaining_goal": ""},
    ]

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run_multistep._call_llm_json", side_effect=llm_responses), \
         patch("planner.run_multistep._call_llm_chat", return_value="Нашёл и сохранил."), \
         patch("mcp_hub.MCPHub", return_value=mock_hub):
        result = run_planner_multistep("найди про пептиды и сохрани в файл", [], [])

    assert result == "Нашёл и сохранил."
    assert mock_hub.call_tool.call_count == 2


def test_run_planner_multistep_tool_error_continues():
    """Ошибка tool — результат сохраняется как "Ошибка: ...", цикл продолжается."""
    catalog = [{"server": "fs", "name": "read_file", "description": "Read"}]

    async def fake_catalog(*args, **kwargs):
        return catalog

    mock_hub = MagicMock()
    mock_hub.server_names = ["fs"]
    mock_hub.connect = AsyncMock()
    mock_hub.call_tool = AsyncMock(side_effect=RuntimeError("file not found"))
    mock_hub.disconnect = AsyncMock()

    llm_responses = [
        {
            "action": "call",
            "reasoning": "читаю",
            "remaining_goal": "",
            "call": {"server": "fs", "tool": "read_file", "arguments": {"path": "/bad"}, "refined_prompt": ""},
        },
        {"action": "done", "reasoning": "не получилось", "remaining_goal": ""},
    ]

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run_multistep._call_llm_json", side_effect=llm_responses), \
         patch("planner.run_multistep._call_llm_chat", return_value="Ошибка чтения."), \
         patch("mcp_hub.MCPHub", return_value=mock_hub):
        result = run_planner_multistep("прочитай /bad", [], [])

    assert result == "Ошибка чтения."
    mock_hub.call_tool.assert_called_once()
