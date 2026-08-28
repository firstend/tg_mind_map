"""Реестр MCP-серверов: загрузка конфигурации из YAML."""

import logging
import os

logger = logging.getLogger("mcp_hub")
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MCPServerConfig:
    """Конфигурация одного MCP-сервера."""

    name: str
    transport: str  # "stdio" | "sse"
    command: str | None = None  # "npx" или "python"
    args: list[str] = field(default_factory=list)  # ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    url: str | None = None  # для sse
    env: dict[str, str] | None = None
    cwd: str | None = None


def _expand_env(val: str) -> str:
    """Подставляет переменные окружения: ${VAR:-default}."""
    if not isinstance(val, str):
        return val
    start = val.find("${")
    while start >= 0:
        end = val.find("}", start)
        if end < 0:
            break
        expr = val[start + 2 : end]
        if ":-" in expr:
            var, default = expr.split(":-", 1)
            var = var.strip()
            result = os.environ.get(var, default.strip())
        else:
            result = os.environ.get(expr.strip(), "")
        val = val[:start] + result + val[end + 1 :]
        start = val.find("${")
    return val


def load_config(path: str | None = None) -> list[MCPServerConfig]:
    """
    Загружает конфигурацию MCP-серверов из YAML.
    Путь: MCP_CONFIG_PATH или mcp_hub/config.yaml относительно корня проекта.
    """
    if path is None:
        path = os.environ.get("MCP_CONFIG_PATH")
    if path is None:
        base = Path(__file__).resolve().parent
        path = str(base / "config.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    servers = data.get("servers") or {}
    result: list[MCPServerConfig] = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        transport = (cfg.get("transport") or "stdio").lower()
        cmd = cfg.get("command")
        args_raw = cfg.get("args") or []
        # command может быть списком: ["npx", "-y", "package"] -> command="npx", args=["-y", "package"]
        if isinstance(cmd, list):
            cmd_list = [_expand_env(str(x)) for x in cmd]
            command = cmd_list[0] if cmd_list else "npx"
            args = cmd_list[1:] if len(cmd_list) > 1 else []
        else:
            command = _expand_env(str(cmd)) if cmd else "npx"
            args = [_expand_env(str(x)) for x in args_raw]
        url = cfg.get("url")
        if url:
            url = _expand_env(str(url))
        env_raw = cfg.get("env")
        env = {k: _expand_env(str(v)) for k, v in env_raw.items()} if env_raw else None
        cwd = cfg.get("cwd")
        if cwd:
            cwd = _expand_env(str(cwd))
        result.append(
            MCPServerConfig(
                name=name,
                transport=transport,
                command=command,
                args=args,
                url=url,
                env=env,
                cwd=cwd,
            )
        )
    logger.info("load_config: loaded %d servers from %s: %s", len(result), path, [c.name for c in result])
    return result
