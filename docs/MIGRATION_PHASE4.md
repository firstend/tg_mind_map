# Этап 4 миграции: Автоматический Planner (USE_PLANNER_AUTO)

Интеграция planner в основной поток: при запросе без явного `/tools` — автоматически определять, нужен ли planner (MCP tools), и вызывать его при необходимости.

---

## 1. Цель этапа 4

- **USE_PLANNER_AUTO**: при обычном сообщении (не команда) — роутинг: tools_request → planner, иначе → пайплайн (граф → RAG → universal_assistant).
- **Роутер**: классификация запроса (chitchat / new_thought / tools_request) перед основным пайплайном.
- Поведение `/tools` не меняется — явный вызов planner остаётся.

---

## 2. Архитектура

```
User: прочитай /tmp/readme.txt
         │
         ▼
Worker: process_message
         │
         ├─► USE_PLANNER_AUTO=true?
         │        │
         │        ├─► route_request(text) → "tools_request" | "new_thought" | "chitchat"
         │        │
         │        ├─► tools_request → run_planner(query, rag, graph)
         │        │        │
         │        │        └─► reply или None → fallback universal_assistant
         │        │
         │        └─► new_thought/chitchat → обычный пайплайн (граф → RAG → universal_assistant)
         │
         └─► push_outgoing(reply)
```

---

## 3. Роутер

### 3.1 Вариант A: Ключевые слова (простой)

```python
# shared/router.py или worker/router.py

PLANNER_KEYWORDS = [
    "прочитай", "прочти", "открой файл", "посмотри файл", "покажи файл",
    "read file", "list dir", "посмотри папку", "содержимое папки",
    "создай файл", "запиши в файл", "write file",
]

def route_request(text: str) -> str:
    """Возвращает: 'tools_request' | 'new_thought' | 'chitchat'."""
    t = text.strip().lower()
    if not t:
        return "chitchat"
    for kw in PLANNER_KEYWORDS:
        if kw in t:
            return "tools_request"
    return "new_thought"
```

- Плюсы: быстрый, без LLM, дешёвый.
- Минусы: ложные срабатывания («прочитай эту мысль» → tools_request).

### 3.2 Вариант B: LLM-классификация (точнее)

```python
def route_request(text: str) -> str:
    """LLM: tools_request | new_thought | chitchat."""
    prompt = f"""Классифицируй запрос пользователя в один из типов:
- tools_request: пользователь просит прочитать/записать файл, посмотреть папку, выполнить действие с файловой системой
- chitchat: приветствие, благодарность, общий вопрос не про файлы
- new_thought: идея, мысль, вопрос по карте идей (не про файлы)

Запрос: {text}

Ответь одним словом: tools_request, chitchat или new_thought"""
    result = submit_json_extract(prompt, schema_hint='{"type": "tools_request|chitchat|new_thought"}')
    return result.get("type", "new_thought")
```

- Плюсы: точнее.
- Минусы: дополнительный вызов LLM, задержка.

### 3.3 Рекомендация

- **Этап 4**: вариант A (ключевые слова) + env `USE_PLANNER_AUTO_ROUTER=keywords|llm`.
- По умолчанию `keywords` — без лишних вызовов LLM.

---

## 4. Интеграция в process_message

### 4.1 Порядок проверок

1. Команды: `/map`, `/topic`, `/help`, `/tools`, `/del` — без изменений.
2. Пустой текст / голос — без изменений.
3. **Новый шаг**: если `USE_PLANNER_AUTO=true`:
   - `route = route_request(text)`
   - если `route == "tools_request"`:
     - `reply = run_planner(text, rag_context=[], graph_context=...)`
     - при `reply` — вернуть OutgoingMessage
     - при `None` — fallback: `universal_assistant` (как в /tools)
4. Далее — обычный пайплайн (extract_theme → classify_topic → граф → RAG → universal_assistant).

### 4.2 RAG при tools_request

При авто-planner RAG можно не вызывать (контекст из графа достаточен). Или вызвать `rag_search` для обогащения — по желанию. Минимум: `graph_context = get_last_nodes`.

---

## 5. Конфигурация

| Переменная | Значение | Описание |
|------------|----------|----------|
| `USE_PLANNER_AUTO` | `true` \| `false` | Включить авто-planner для обычных сообщений |
| `USE_PLANNER_AUTO_ROUTER` | `keywords` \| `llm` | Способ роутинга (по умолчанию `keywords`) |

---

## 6. Риски и ограничения

| Риск | Митигация |
|------|-----------|
| Ложный tools_request («прочитай мою мысль») | Уточнить ключевые слова; при llm-роутере — точнее |
| MCP недоступен (нет npx) | planner вернёт None → fallback universal_assistant |
| Доп. задержка при llm-роутере | Использовать keywords по умолчанию |

---

## 7. Чеклист этапа 4

- [x] `shared/router.py`: `route_request(text)` (keywords + llm)
- [x] `worker/processor.py`: интеграция USE_PLANNER_AUTO в process_message
- [x] Тесты: test_router, test_processor (planner_auto)
- [x] /help: подсказка про авто-planner при USE_PLANNER_AUTO=true

---

## 8. Связь с этапом 3

- Этап 3: только `/tools` — явный вызов planner.
- Этап 4: обычное сообщение «прочитай файл X» → автоматически planner (если USE_PLANNER_AUTO=true).
