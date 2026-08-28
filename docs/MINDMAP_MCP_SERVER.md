# Mindmap MCP Server — дерево тем и планировщик

## 1. Проблема текущей модели

Сейчас **каждый запрос** создаёт отдельный узел в графе. В результате:
- Много мелких узлов без иерархии
- Нет осмысленной структуры: «Заработка → Требования, Вижен, Архитектура»
- Планировщик не может прорабатывать темы по шагам и задавать уточняющие вопросы

## 2. Целевая модель: дерево тем

```
Заработка (корень)
├── Требования
├── Вижен
├── Архитектура
│   ├── API
│   └── База данных
└── MVP
```

- **Тема** — узел с названием и опциональным описанием
- **Подтемы** — дети по ребру (edge_type: sub_topic или continuation)
- **Активная тема** — контекст, с которым работает пользователь и планировщик
- **Заметки** — привязаны к теме, не создают новую подтему (или создают «заметку» как особый node_type)

Планировщик может:
- Создать тему «Заработка»
- Добавить подтемы: «Требования», «Вижен», «Архитектура»
- Выбрать активную тему и проработать её (найти инфо, задать вопросы пользователю)
- Перейти к следующей подтеме

## 3. MCP Server: список tools

Все tools принимают **user_id** (int) — владелец карты. Worker передаёт user_id в graph_context; planner должен подставлять его в аргументы.

| Tool | Описание | Аргументы |
|------|----------|-----------|
| `mindmap_get_tree` | Дерево тем пользователя (корни → дети) | `user_id` |
| `mindmap_get_active` | Активная тема | `user_id` |
| `mindmap_set_active` | Установить активную тему | `user_id`, `topic_id` |
| `mindmap_create_topic` | Создать тему (корневую или подтему) | `user_id`, `title`, `description`?, `parent_id`? |
| `mindmap_add_subtopic` | Добавить подтему к существующей | `user_id`, `parent_id`, `title`, `description`? |
| `mindmap_update_topic` | Обновить тему (title, description, status) | `user_id`, `topic_id`, `title`?, `description`?, `status`? |
| `mindmap_add_note` | Добавить заметку к теме (без создания новой темы) | `user_id`, `topic_id`, `content`, `source`? (user/ai) |
| `mindmap_search` | Поиск по темам и заметкам (RAG или текст) | `user_id`, `query`, `limit`? |
| `mindmap_get_context` | Контекст для планирования: активная тема + её дети + последние заметки | `user_id`, `topic_id`? |
| `mindmap_delete_topic` | Удалить тему и её подтемы | `user_id`, `topic_id` |

### JSON Schema для planner (inputSchema)

```json
{
  "mindmap_get_tree": {"user_id": {"type": "integer", "description": "Telegram user_id"}},
  "mindmap_get_active": {"user_id": {"type": "integer"}},
  "mindmap_set_active": {"user_id": {"type": "integer"}, "topic_id": {"type": "string"}},
  "mindmap_create_topic": {"user_id": {"type": "integer"}, "title": {"type": "string"}, "description": {"type": "string"}, "parent_id": {"type": "string"}},
  "mindmap_add_subtopic": {"user_id": {"type": "integer"}, "parent_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}},
  "mindmap_add_note": {"user_id": {"type": "integer"}, "topic_id": {"type": "string"}, "content": {"type": "string"}, "source": {"type": "string", "enum": ["user", "ai"]}},
  "mindmap_get_context": {"user_id": {"type": "integer"}, "topic_id": {"type": "string"}},
  "mindmap_search": {"user_id": {"type": "integer"}, "query": {"type": "string"}, "limit": {"type": "integer"}}
}
```

### Примеры сценариев

**Создание структуры:**
```
mindmap_create_topic(user_id, title="Заработка") → root_id
mindmap_add_subtopic(user_id, parent_id=root_id, title="Требования")
mindmap_add_subtopic(user_id, parent_id=root_id, title="Вижен")
mindmap_add_subtopic(user_id, parent_id=root_id, title="Архитектура")
```

**Проработка темы:**
```
mindmap_get_active(user_id) → текущая тема
mindmap_get_context(user_id, topic_id) → активная + дети + заметки
# Planner ищет инфо, задаёт вопрос пользователю
mindmap_add_note(user_id, topic_id, content="Пользователь ответил: ...", source="user")
```

---

## 4. Эскиз MCP-сервера (Python, stdio)

```
mcp_server_mindmap/
├── __init__.py
├── __main__.py      # python -m mcp_server_mindmap
└── server.py        # MCP tools → shared.graph / shared.rag
```

### config.yaml (mcp_hub)

```yaml
servers:
  mindmap:
    transport: stdio
    command: ["python", "-m", "mcp_server_mindmap"]
    env:
      DATABASE_URL: "${DATABASE_URL}"
    # user_id передаётся в каждом вызове как аргумент tool
```

### Передача user_id

Worker при вызове planner передаёт `user_id` в `graph_context` или в метаданных. Planner должен включать `user_id` в аргументы вызовов mindmap-инструментов. Варианты:
- **A.** Явный аргумент в каждом tool: `user_id` (обязательный)
- **B.** Через env при старте MCP-сервера — не подходит, т.к. один процесс на много пользователей

Используем **A**: `user_id` — обязательный аргумент всех mindmap tools.

**Изменение API planner:** добавить `user_id` в вызов:
```python
run_planner(query, rag_ctx, graph_ctx, user_id=user_id)
```
В промпте планирования указывать: «user_id текущего пользователя: {user_id}. Для всех mindmap_* tools передавай этот user_id в аргументах.»

---

## 5. Маппинг на текущий граф

Текущие таблицы `nodes` и `edges` можно использовать:
- `node_type`: `topic` (тема), `note` (заметка), `thought` (legacy)
- `summary` — краткое название темы, `content` — полное описание
- Ребро `from_node_id → to_node_id` с `edge_type = "sub_topic"` для иерархии

Миграция: добавить `edge_type = "sub_topic"` в EDGE_TYPES, новые темы создавать с `node_type = "topic"`.

---

## 6. Изменение пайплайна воркера

**Сейчас:** сообщение → extract_theme → create_node → RAG → ответ

**После:** сообщение → planner (в т.ч. mindmap tools) или fallback:

1. Planner видит `mindmap_*` tools и может:
   - Создать/дополнить тему
   - Получить контекст, задать вопрос
   - Добавить заметку как ответ пользователя
2. Если planner не вызвал mindmap и вернул None — текущий fallback (create_node и т.д.) можно оставить для обратной совместимости или упростить до «просто ответ без узла».

---

## 7. Пример server.py (скелет)

```python
"""MCP Server: Mindmap — дерево тем."""

import os
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("mindmap", dependencies=["shared"])

def _get_user_id(args: dict) -> int:
    uid = args.get("user_id")
    if uid is None:
        raise ValueError("user_id required")
    return int(uid)

@mcp.tool()
def mindmap_get_tree(user_id: int) -> str:
    """Дерево тем: корни и их дети."""
    from shared.graph import get_map
    nodes, edges = get_map(user_id, limit=100)
    # Построить дерево, отфильтровать node_type=topic
    ...

@mcp.tool()
def mindmap_create_topic(user_id: int, title: str, description: str = "", parent_id: str = "") -> str:
    """Создать тему (корневую или подтему)."""
    from shared.graph import create_node, create_edge, set_active_node
    summary = title[:200]
    content = description or title
    node_id = create_node(user_id, content=content, summary=summary, node_type="topic")
    if parent_id:
        create_edge(parent_id, node_id, edge_type="sub_topic")
    set_active_node(user_id, node_id)
    return json.dumps({"topic_id": node_id, "title": title})

# ... остальные tools
```

---

## 8. Планировщик и вопросы пользователю

Планировщик не может «задать вопрос» через MCP tool — ответ приходит отдельным сообщением. Варианты:

1. **Ответ с вопросом** — planner генерирует текст «Чтобы проработать "Требования", уточни: ...» и возвращает его пользователю. Пользователь пишет ответ → следующее сообщение. Planner может вызвать `mindmap_add_note` с этим ответом при следующем запросе.
2. **Состояние «ожидаю ответ»** — сохранять в user_state: «ожидаю ответ по topic_id X». При следующем сообщении planner сразу добавляет заметку и продолжает.
3. **Inline-уточнение** — в одном ответе: «Нашёл про X. Вот выжимка: ... Дальше могу разобрать "Вижен" — продолжить?» Пользователь: «да» → planner переключается на "Вижен".

Рекомендуется начать с **1**: простой цикл «вопрос в ответе → ответ пользователя → mindmap_add_note при следующем запросе».

---

## 9. Реализовано (Phase 6)

1. ✅ `sub_topic`, `note` в EDGE_TYPES; `topic`, `note` в NODE_TYPES
2. ✅ `mcp_server_mindmap` с 10 tools
3. ✅ mindmap в mcp_hub/config.yaml
4. ✅ planner получает `user_id`, инжектит в mindmap tools
5. Следующий шаг: постепенно менять пайплайн воркера — меньше авто create_node, больше через planner
