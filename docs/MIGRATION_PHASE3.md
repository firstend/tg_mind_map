# Этап 3 миграции: Planner (MCP + LLM)

Интеграция планировщика: LLM выбирает MCP tools по запросу пользователя, выполняет их и формирует ответ.

---

## 1. Цель этапа 3

- **Planner**: LLM получает каталог tools из mcp_hub, решает, какие вызвать, возвращает план.
- **Executor**: выполнение плана через MCPHub.call_tool.
- **Интеграция**: команда `/tools <запрос>` — явный вызов planner; при ошибке MCP — fallback на universal_assistant.

---

## 2. Архитектура

```
User: /tools прочитай /tmp/readme.txt
         │
         ▼
Worker: process_message
         │
         ├─► /tools detected → run_planner(query)
         │        │
         │        ├─► MCPHub.connect("filesystem")
         │        ├─► get_tools_catalog(hub)
         │        ├─► LLM: plan = "call read_file path=/tmp/readme.txt"
         │        ├─► hub.call_tool("filesystem", "read_file", {path: "..."})
         │        ├─► LLM: synthesize(query, tool_result) → reply
         │        └─► return reply
         │
         └─► push_outgoing(reply)
```

---

## 3. Структура planner

```
planner/
├── __init__.py
├── run.py          # run_planner(query, rag_context, graph_context) -> str
└── prompts.py      # Промпты для plan и synthesize
```

---

## 4. API

### run_planner(query, rag_context, graph_context, role) -> str | None

- Подключается к MCP (async через asyncio.run).
- Получает get_tools_catalog.
- LLM (json_extract): план вида `[{"server": "filesystem", "tool": "read_file", "arguments": {"path": "..."}}]`.
- Выполняет каждый вызов tool.
- LLM (chat): синтезирует ответ из query + результатов tools + rag/graph.
- Возвращает reply_text или None при ошибке (fallback на universal_assistant).

---

## 5. Триггеры

- **/tools \<запрос\>** — явный вызов planner.
- Опционально: USE_PLANNER_AUTO=true + ключевые слова ("прочитай файл", "посмотри папку") — автоматический planner.

Этап 3: только `/tools` для простоты.

---

## 6. Fallback

- MCP connect fail (нет npx) → return None → universal_assistant.
- LLM plan = [] (tools не нужны) → можно сразу universal_assistant.
- call_tool error → включить ошибку в контекст synthesize.

---

## 7. Docker

MCP filesystem требует npx. Варианты:
- Добавить Node.js в Dockerfile worker (для /tools).
- Или: при отсутствии npx planner возвращает "MCP недоступен, используй обычный режим."

---

## 8. Чеклист

- [x] planner/run.py: run_planner()
- [x] planner/prompts.py: plan + synthesize промпты
- [x] worker: /tools → run_planner, fallback universal_assistant
- [x] Тесты planner (мок MCP)
- [ ] Docker: Node.js в worker (опционально, для MCP filesystem)
- [x] /help: добавить /tools
