# Этап 2 миграции: MCP Hub

Интеграция Model Context Protocol (MCP) — подключаемые инструменты для расширения возможностей агента. Планировщик (planner) — этап 3.

---

## 1. Цель этапа 2

- Реализовать **mcp_hub**: реестр MCP-серверов, клиент для подключения и вызова tools.
- **Поведение бота не меняется** — mcp_hub пока не участвует в ответах.
- Этап 2 — инфраструктура; этап 3 — planner, использующий mcp_hub в агенте.

---

## 2. MCP: что это

Model Context Protocol — способ подключать внешние «инструменты» к LLM: файловая система, веб-поиск, базы данных и т.д. MCP-сервер предоставляет tools (read_file, write_file) и resources. Клиент (наш mcp_hub) подключается к серверу и вызывает tools по запросу.

**Транспорты:**
- **stdio** — сервер как дочерний процесс (npx, python -m)
- **sse** — HTTP Server-Sent Events (удалённый сервер)

---

## 3. Структура mcp_hub

```
mcp_hub/
├── __init__.py
├── config.yaml          # Конфигурация серверов (опционально: env путь)
├── registry.py          # MCPServerConfig, загрузка из YAML
├── client.py            # MCPHub: connect, list_tools, call_tool
├── catalog.py           # get_tools_catalog() — JSON для промпта planner
└── transports/          # (опционально) stdio, sse
    ├── __init__.py
    ├── stdio.py
    └── sse.py
```

---

## 4. API mcp_hub

### 4.1 Реестр (registry.py)

```python
@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio" | "sse"
    command: list[str] | None = None   # ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
    args: list[str] | None = None      # ["/path/to/allowed/dir"]
    url: str | None = None             # для sse
    env: dict[str, str] | None = None

def load_config(path: str = "mcp_hub/config.yaml") -> list[MCPServerConfig]: ...
```

### 4.2 Клиент (client.py)

```python
class MCPHub:
    def __init__(self, config_path: str | None = None): ...

    async def connect(self, server_name: str) -> None:
        """Подключиться к MCP-серверу. Вызывать до list_tools/call_tool."""

    async def list_tools(self, server_name: str) -> list[Tool]:
        """Список tools сервера. Tool: name, description, inputSchema."""

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Вызвать tool. Возвращает результат (str, list[dict] и т.д.)."""

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Прочитать resource (если сервер поддерживает)."""

    async def disconnect(self, server_name: str | None = None) -> None: ...
```

### 4.3 Каталог для planner (catalog.py)

```python
def get_tools_catalog(hub: MCPHub, server_names: list[str] | None = None) -> list[dict]:
    """
    Возвращает список tools для промпта планировщика.
    Формат: [
        {"server": "filesystem", "name": "read_file", "description": "...", "inputSchema": {...}},
        ...
    ]
    """
```

---

## 5. Конфигурация (config.yaml)

```yaml
servers:
  filesystem:
    transport: stdio
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
    args: ["/tmp"]  # или путь из env: ${MCP_FILESYSTEM_ROOT:-/tmp}

  # web (пример для этапа 3):
  #   transport: sse
  #   url: http://localhost:8080/sse
```

Путь к config: env `MCP_CONFIG_PATH` или `mcp_hub/config.yaml` относительно CWD.

---

## 6. Где запускать MCP

**Варианты:**

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| A. В worker | Близко к агенту | Worker уже нагружен; stdio = один MCP на процесс |
| B. В llm_service | Централизованный LLM-стек | llm_service синхронный; нужен async или отдельный поток |
| C. Отдельный mcp_service | Изоляция, масштабирование | Новый сервис, сетевые вызовы |

**Рекомендация для этапа 2:** не запускать MCP в prod-потоке. Сделать mcp_hub как библиотеку; в Phase 2 — только юнит-тесты и ручная проверка (скрипт `scripts/test_mcp.py`). Запуск в worker/llm_service — этап 3.

---

## 7. Зависимости

- **mcp** — официальный Python SDK: `pip install mcp`
- Или использовать низкоуровневый протокол через `json-rpc` + stdio/httpx

Проверить: `mcp` пакет поддерживает stdio/sse транспорты и упрощает подключение.

---

## 8. Пошаговый план этапа 2

### Шаг 2.1: Зависимости и структура

1. Добавить `mcp` в `requirements.txt` (или альтернативу).
2. Создать каталог `mcp_hub/` и пустые модули.

### Шаг 2.2: Реестр и конфиг

1. `mcp_hub/registry.py`: `MCPServerConfig`, `load_config()`.
2. `mcp_hub/config.yaml`: пример с filesystem.

### Шаг 2.3: Клиент MCP

1. `mcp_hub/client.py`: класс `MCPHub`.
2. Поддержка stdio (обязательно), sse (опционально).
3. Методы: `connect`, `list_tools`, `call_tool`, `disconnect`.

### Шаг 2.4: Каталог tools

1. `mcp_hub/catalog.py`: `get_tools_catalog(hub, server_names)`.
2. Формат вывода — список dict для промпта planner.

### Шаг 2.5: Тесты и скрипт

1. Тесты с моком MCP-сервера или пропуск при отсутствии `npx`.
2. `scripts/test_mcp.py`: подключение к filesystem, `list_tools`, `call_tool("read_file", {"path": "..."})`.

### Шаг 2.6: Документация

1. Обновить `ARCHITECTURE.md` — добавить mcp_hub в схему.
2. README в `mcp_hub/` с примерами использования.

---

## 9. Чеклист этапа 2

- [x] `mcp` в requirements.txt
- [x] `mcp_hub/registry.py`: MCPServerConfig, load_config
- [x] `mcp_hub/config.yaml`: filesystem
- [x] `mcp_hub/client.py`: MCPHub (connect, list_tools, call_tool)
- [x] `mcp_hub/catalog.py`: get_tools_catalog
- [x] `scripts/test_mcp.py`: ручная проверка
- [x] Тесты (tests/test_mcp_hub.py)
- [x] Документация

---

## 10. Связь с этапом 3 (Planner)

Этап 3 добавит:

- Новый тип LLM job: `PLAN_AND_EXECUTE` или отдельный pipeline.
- Planner: LLM получает `get_tools_catalog()`, решает, какие tools вызвать, возвращает план.
- Executor: вызовы `MCPHub.call_tool` по плану.
- Интеграция в `universal_assistant`: при определённых запросах — использовать planner + MCP вместо простого RAG/графа.

Этап 2 не меняет worker, llm_service, shared.llm — только добавляет mcp_hub.

---

## 11. Риски и упрощения

| Риск | Митигация |
|------|-----------|
| MCP SDK нестабилен / тяжёлый | Использовать минимальный HTTP/stdio + json-rpc вручную |
| npx недоступен в Docker | В docker добавить node или использовать Python MCP-сервер |
| Async в синхронном worker | В Phase 2 не интегрируем в worker; тесты — async скрипт |
