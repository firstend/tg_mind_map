"""Каталог tools для планировщика: список tools всех серверов в формате для промпта."""

import logging
from typing import Any

from mcp_hub.client import MCPHub, Tool

logger = logging.getLogger("mcp_hub")


async def get_tools_catalog(
    hub: MCPHub,
    server_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Возвращает список tools для промпта планировщика.
    Формат: [
        {"server": "filesystem", "name": "read_file", "description": "...", "inputSchema": {...}},
        ...
    ]
    """
    if server_names is None:
        server_names = hub.server_names
    result: list[dict[str, Any]] = []
    logger.info("get_tools_catalog: servers=%s", server_names)
    for name in server_names:
        try:
            tools = await hub.list_tools(name)
        except Exception as e:
            logger.warning("get_tools_catalog: server %s failed: %s", name, e, exc_info=True)
            continue
        for t in tools:
            result.append({
                "server": name,
                "name": t["name"],
                "description": t.get("description") or "",
                "inputSchema": t.get("inputSchema") or {},
            })
    logger.info("get_tools_catalog: total %d tools", len(result))
    return result
