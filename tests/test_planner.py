"""Тесты planner: run_planner с моками MCP и LLM."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner import run_planner
from planner.prompts import build_plan_prompt, build_synthesize_user


def test_build_plan_prompt():
    """Промпт содержит tools и query."""
    catalog = [
        {"server": "fs", "name": "read_file", "description": "Read file"},
    ]
    p = build_plan_prompt("прочитай /tmp/x", catalog)
    assert "read_file" in p
    assert "прочитай /tmp/x" in p
    assert "calls" in p


def test_build_synthesize_user():
    """user message содержит query, results, rag, graph."""
    results = [{"tool": "read_file", "result": "hello"}]
    msg = build_synthesize_user("query", results, "rag", "graph")
    assert "query" in msg
    assert "read_file" in msg
    assert "hello" in msg


def test_run_planner_empty_catalog_returns_none():
    """При пустом каталоге planner возвращает None."""
    with patch("mcp_hub.get_tools_catalog", new_callable=AsyncMock) as mock_cat, \
         patch("mcp_hub.MCPHub") as mock_hub:
        mock_cat.return_value = []
        mock_hub.return_value.server_names = ["fs"]
        result = run_planner("test", [], [])
    assert result is None


def test_run_planner_no_calls_returns_none():
    """LLM вернул calls=[] — planner возвращает None."""
    async def fake_catalog(*args, **kwargs):
        return [{"server": "fs", "name": "read_file", "description": "x"}]

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run._call_llm_json", return_value={"calls": []}), \
         patch("mcp_hub.MCPHub"):
        result = run_planner("test", [], [])
    assert result is None


def test_run_planner_success():
    """Planner с моками: plan → execute → synthesize → reply."""
    catalog = [{"server": "fs", "name": "read_file", "description": "Read"}]

    async def fake_catalog(*args, **kwargs):
        return catalog

    mock_hub = MagicMock()
    mock_hub.server_names = ["fs"]
    mock_hub.connect = AsyncMock()
    mock_hub.call_tool = AsyncMock(return_value="file content here")
    mock_hub.disconnect = AsyncMock()

    with patch("mcp_hub.get_tools_catalog", side_effect=fake_catalog), \
         patch("planner.run._call_llm_json", return_value={
             "calls": [{"server": "fs", "tool": "read_file", "arguments": {"path": "/tmp/x"}}]
         }), \
         patch("planner.run._call_llm_chat", return_value="Вот содержимое файла."), \
         patch("mcp_hub.MCPHub", return_value=mock_hub):
        result = run_planner("прочитай /tmp/x", [], [])

    assert result == "Вот содержимое файла."
    mock_hub.call_tool.assert_called_once()
    mock_hub.disconnect.assert_called_once()


def test_run_planner_mcp_error_returns_none():
    """При ошибке MCP (get_tools_catalog) — None."""
    with patch("mcp_hub.get_tools_catalog", new_callable=AsyncMock, side_effect=RuntimeError("no npx")):
        result = run_planner("test", [], [])
    assert result is None
