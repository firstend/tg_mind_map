"""Проверка, что модули импортируются без ошибок."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_shared_imports():
    from shared.models import IncomingMessage, OutgoingMessage
    from shared.router import route_request
    assert IncomingMessage
    assert OutgoingMessage
    assert route_request


def test_gateway_app():
    from gateway.main import app
    assert app.title == "Mind Map Gateway"


def test_mcp_hub_imports():
    from mcp_hub import MCPHub, load_config, get_tools_catalog
    assert MCPHub
    assert load_config
    assert get_tools_catalog


def test_planner_imports():
    from planner import run_planner
    assert run_planner


def test_mindmap_mcp_imports():
    from mcp_server_mindmap.server import mcp
    tools = list(mcp._tool_manager._tools.values())
    assert len(tools) >= 10
    names = [t.name for t in tools]
    assert "mindmap_get_tree" in names
    assert "mindmap_create_topic" in names
