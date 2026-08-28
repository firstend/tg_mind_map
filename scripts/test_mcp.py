#!/usr/bin/env python3
"""Ручная проверка mcp_hub: подключение к filesystem, list_tools, call_tool read_file."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_hub import MCPHub, get_tools_catalog


async def main() -> None:
    hub = MCPHub()
    print("Servers in config:", hub.server_names)
    if "filesystem" not in hub.server_names:
        print("No 'filesystem' server. Add to mcp_hub/config.yaml")
        return
    try:
        tools = await hub.list_tools("filesystem")
        print(f"Tools: {[t['name'] for t in tools]}")
        catalog = await get_tools_catalog(hub)
        print(f"Catalog entries: {len(catalog)}")
        # Попробовать read_file если есть
        read_tool = next((t for t in tools if t["name"] == "read_file"), None)
        if read_tool:
            # Создать тестовый файл в /tmp
            test_path = "/tmp/mcp_test_hello.txt"
            with open(test_path, "w") as f:
                f.write("Hello from MCP test!")
            result = await hub.call_tool("filesystem", "read_file", {"path": test_path})
            print(f"read_file result: {result!r}")
            os.remove(test_path)
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        await hub.disconnect()
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
