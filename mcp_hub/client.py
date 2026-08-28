"""MCP Hub: клиент для подключения к MCP-серверам и вызова tools."""

import logging
from contextlib import AsyncExitStack

logger = logging.getLogger("mcp_hub")
from typing import Any, TypedDict

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp_hub.registry import MCPServerConfig, load_config


class Tool(TypedDict):
    """Tool из MCP: name, description, inputSchema."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPHub:
    """
    Клиент MCP: подключение к серверам, list_tools, call_tool.
    Использует async API — для sync-обёртки см. run_sync().
    """

    def __init__(self, config_path: str | None = None):
        self._configs = {c.name: c for c in load_config(config_path)}
        self._sessions: dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()

    @property
    def server_names(self) -> list[str]:
        return list(self._configs.keys())

    def _get_config(self, server_name: str) -> MCPServerConfig:
        if server_name not in self._configs:
            raise ValueError(f"Unknown MCP server: {server_name}")
        return self._configs[server_name]

    async def connect(self, server_name: str) -> None:
        """Подключиться к MCP-серверу. Вызывать до list_tools/call_tool."""
        if server_name in self._sessions:
            logger.debug("connect %s: already connected", server_name)
            return
        cfg = self._get_config(server_name)
        logger.info("connect %s: transport=%s command=%s args=%s", server_name, cfg.transport, cfg.command, cfg.args)
        if cfg.transport != "stdio":
            raise NotImplementedError(f"Transport {cfg.transport} not implemented yet")
        if not cfg.command:
            raise ValueError(f"Server {server_name}: command required for stdio")
        params = StdioServerParameters(
            command=cfg.command,
            args=cfg.args or [],
            env=cfg.env,
            cwd=cfg.cwd,
        )
        try:
            stdio_transport = await self._exit_stack.enter_async_context(stdio_client(params))
            read_stream, write_stream = stdio_transport
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            self._sessions[server_name] = session
            logger.info("connect %s: ok", server_name)
        except Exception as e:
            logger.exception("connect %s failed: %s", server_name, e)
            raise

    async def list_tools(self, server_name: str) -> list[Tool]:
        """Список tools сервера."""
        await self.connect(server_name)
        session = self._sessions[server_name]
        result = await session.list_tools()
        tools = [
            Tool(
                name=t.name,
                description=t.description or "",
                inputSchema=t.inputSchema if hasattr(t, "inputSchema") else {},
            )
            for t in result.tools
        ]
        logger.info("list_tools %s: %d tools %s", server_name, len(tools), [t["name"] for t in tools])
        return tools

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        Вызвать tool. Возвращает результат.
        Для text-результатов — строка; для content — список dict с type/text.
        """
        await self.connect(server_name)
        session = self._sessions[server_name]
        logger.info("call_tool %s.%s args=%s", server_name, tool_name, arguments or {})
        result = await session.call_tool(tool_name, arguments or {})
        # CallToolResult.content: list[TextContent | ImageContent | ...]
        if not result.content:
            return ""
        parts = []
        for item in result.content:
            text = getattr(item, "text", None) if not isinstance(item, dict) else item.get("text")
            if text:
                parts.append(text)
        out = "\n".join(parts) if parts else ""
        logger.info("call_tool %s.%s: result_len=%d", server_name, tool_name, len(out))
        return out

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Прочитать resource (если сервер поддерживает)."""
        await self.connect(server_name)
        session = self._sessions[server_name]
        result = await session.read_resource(uri)
        if not result.contents:
            return ""
        parts = []
        for c in result.contents:
            if hasattr(c, "text"):
                parts.append(c.text)
            elif isinstance(c, dict) and "text" in c:
                parts.append(c["text"])
        return "\n".join(parts) if parts else ""

    async def disconnect(self, server_name: str | None = None) -> None:
        """Отключиться от сервера(ов) и освободить ресурсы."""
        await self._exit_stack.aclose()
        if server_name:
            self._sessions.pop(server_name, None)
        else:
            self._sessions.clear()
        # exit_stack уже закрыт; при следующем connect нужен новый
        self._exit_stack = AsyncExitStack()
