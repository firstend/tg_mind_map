"""Тесты mcp_hub: registry, client (с моком), catalog."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_hub.registry import MCPServerConfig, load_config, _expand_env


def test_expand_env_simple():
    """Переменная ${VAR} подставляется."""
    import os
    os.environ["TEST_VAR"] = "hello"
    try:
        assert _expand_env("${TEST_VAR}") == "hello"
        assert _expand_env("a${TEST_VAR}b") == "ahellob"
    finally:
        os.environ.pop("TEST_VAR", None)


def test_expand_env_default():
    """${VAR:-default} — default при отсутствии VAR."""
    import os
    os.environ.pop("MISSING_VAR", None)
    assert _expand_env("${MISSING_VAR:-fallback}") == "fallback"
    os.environ["PRESENT_VAR"] = "value"
    try:
        assert _expand_env("${PRESENT_VAR:-other}") == "value"
    finally:
        os.environ.pop("PRESENT_VAR", None)


def test_load_config_internal():
    """load_config загружает config.yaml из mcp_hub."""
    configs = load_config()
    assert isinstance(configs, list)
    # config.yaml содержит filesystem и mindmap
    names = [c.name for c in configs]
    assert "filesystem" in names
    assert "mindmap" in names
    fs = next(c for c in configs if c.name == "filesystem")
    assert fs.transport == "stdio"
    assert fs.command == "npx"
    assert "@modelcontextprotocol/server-filesystem" in (fs.args or [])


def test_load_config_custom_path(tmp_path):
    """load_config с путём загружает указанный файл."""
    cfg_file = tmp_path / "mcp.yaml"
    cfg_file.write_text("""
servers:
  custom:
    transport: stdio
    command: ["python", "-m", "mymcp"]
    args: []
""")
    configs = load_config(str(cfg_file))
    assert len(configs) == 1
    assert configs[0].name == "custom"
    assert configs[0].command == "python"
    assert configs[0].args == ["-m", "mymcp"]


def test_mcp_hub_server_names():
    """MCPHub.server_names возвращает имена из конфига."""
    from mcp_hub.client import MCPHub

    with patch("mcp_hub.client.load_config") as mock_load:
        mock_load.return_value = [
            MCPServerConfig(name="fs", transport="stdio", command="npx", args=[]),
        ]
        hub = MCPHub()
        assert hub.server_names == ["fs"]


def test_get_tools_catalog_sync():
    """get_tools_catalog возвращает список dict с server, name, description."""
    import asyncio
    from mcp_hub.catalog import get_tools_catalog
    from mcp_hub.client import MCPHub

    hub = MagicMock(spec=MCPHub)
    hub.server_names = ["test"]
    hub.list_tools = AsyncMock(return_value=[
        {"name": "read_file", "description": "Read file", "inputSchema": {}},
    ])

    async def run():
        return await get_tools_catalog(hub, ["test"])

    catalog = asyncio.run(run())
    assert len(catalog) == 1
    assert catalog[0]["server"] == "test"
    assert catalog[0]["name"] == "read_file"
    assert catalog[0]["description"] == "Read file"


def test_mcp_hub_connect_unknown_server():
    """MCPHub.connect с неизвестным сервером — ValueError."""
    import asyncio
    from mcp_hub.client import MCPHub

    async def run():
        with patch("mcp_hub.client.load_config", return_value=[]):
            hub = MCPHub()
            with pytest.raises(ValueError, match="Unknown MCP server"):
                await hub.connect("nonexistent")

    asyncio.run(run())
