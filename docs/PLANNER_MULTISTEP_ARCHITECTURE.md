# Архитектура мультишагового планировщика

Многошаговый планировщик с цепочкой tools (output → input) и улучшением запросов LLM на каждом шаге.

---

## 1. Проблема

Текущий planner планирует все вызовы **до** выполнения. Результат шага N недоступен при планировании шага N+1. Поэтому нельзя сделать «найди про X и сохрани в файл» — для `write_file` нужен content из результата поиска.

---

## 2. Решение: итеративное планирование

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  MULTI-STEP PLANNER LOOP                                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Step 0: state = {original_query, results: [], remaining_goal: query}         │
│                                                                               │
│  loop (max_steps = 5):                                                        │
│    1. PLAN: LLM получает original_query + results + remaining_goal            │
│       → возвращает: next_call ИЛИ done                                        │
│    2. REFINE: LLM улучшает аргументы (профессиональный промпт, суть сохранена)│
│    3. EXECUTE: выполнить next_call                                            │
│    4. UPDATE: results.append(result), remaining_goal = refined                │
│    5. если done → SYNTHESIZE и выход                                          │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Компоненты

### 3.1 Состояние шага (StepState)

```python
@dataclass
class StepState:
    original_query: str          # Исходный запрос пользователя
    results: list[ToolResult]    # [{tool, args_used, refined_prompt, result}, ...]
    remaining_goal: str          # Что ещё нужно сделать (эволюционирует LLM)
    step_number: int
    max_steps: int = 5
```

### 3.2 ToolResult

```python
@dataclass
class ToolResult:
    server: str
    tool: str
    args_used: dict             # Фактические аргументы (включая refined)
    refined_prompt: str | None   # Улучшенный промпт для этого шага (для отладки)
    result: str                  # Ответ tool
```

### 3.3 Ответ LLM на шаге планирования

```json
{
  "action": "call" | "done",
  "reasoning": "Краткое обоснование шага",
  "remaining_goal": "Что осталось сделать после этого шага",
  "call": {
    "server": "brave_search",
    "tool": "brave_web_search",
    "arguments": {
      "query": "пептиды: свойства, применение, исследования 2024"
    },
    "refined_prompt": "Поиск актуальной информации о пептидах: определение, медицинское применение, последние исследования"
  }
}
```

При `action: "done"` поле `call` отсутствует.

---

## 4. Улучшение запросов (Query Refinement)

LLM на каждом шаге **преобразует** аргументы инструмента в профессиональный промпт, сохраняя суть.

### Правила refinement

| Исходный запрос пользователя | Refined для search | Refined для write_file (content) |
|-----------------------------|--------------------|----------------------------------|
| «найди про пептиды» | «пептиды: определение, свойства, применение в медицине, последние исследования» | — |
| «сохрани в файл» | — | Сжатая выжимка из results[0], структурированно |
| «что нового в Python 3.13» | «Python 3.13 release notes, new features, migration guide 2024» | — |

### Промпт для refinement

```
Для каждого вызова инструмента ты можешь улучшить аргументы:
- Сохрани суть и намерение пользователя
- Сделай запрос более точным, структурированным, профессиональным
- Для search: добавь релевантные ключевые слова, уточни временной диапазон
- Для write_file content: используй результаты предыдущих шагов, при необходимости сократи и структурируй
- Не выдумывай новую тему — только уточняй формулировку
```

---

## 5. Поток данных (пример)

**Запрос:** «Найди информацию про пептиды и сохрани в файл»

### Step 1

**Вход в LLM:**
```
original_query: «Найди информацию про пептиды и сохрани в файл»
results: []
remaining_goal: «Найди информацию про пептиды и сохрани в файл»
available_tools: [brave_web_search, ..., write_file, ...]
```

**Ответ LLM:**
```json
{
  "action": "call",
  "reasoning": "Сначала нужен поиск",
  "remaining_goal": "Сохранить найденную информацию в файл",
  "call": {
    "server": "brave_search",
    "tool": "brave_web_search",
    "arguments": {"query": "пептиды: определение, свойства, применение в медицине, исследования"},
    "refined_prompt": "Поиск структурированной информации о пептидах"
  }
}
```

**Выполнение:** brave_web_search → result_1 (3842 байт)

### Step 2

**Вход в LLM:**
```
original_query: «Найди информацию про пептиды и сохрани в файл»
results: [
  {tool: "brave_web_search", result: "<содержимое поиска ...>"}
]
remaining_goal: «Сохранить найденную информацию в файл»
```

**Ответ LLM:**
```json
{
  "action": "call",
  "reasoning": "Сохраняю выжимку в файл",
  "remaining_goal": "",
  "call": {
    "server": "filesystem",
    "tool": "write_file",
    "arguments": {
      "path": "/tmp/peptides_info.txt",
      "content": "<извлечённое и структурированное содержание из results[0]>"
    },
    "refined_prompt": "Сохранение структурированной выжимки о пептидах"
  }
}
```

**Выполнение:** write_file → result_2

### Step 3

**Вход в LLM:**
```
results: [result_1, result_2]
remaining_goal: ""
```

**Ответ LLM:**
```json
{"action": "done", "reasoning": "Оба шага выполнены"}
```

### Step 4: Synthesize

Финальный ответ пользователю на основе `original_query` + `results`.

---

## 6. Ограничения по объёму

- Результаты tools могут быть большими (10k+ символов). В промпт планирования передавать:
  - первые N символов (например 2000) для контекста;
  - или суммаризацию через отдельный LLM-вызов;
  - или ссылку `results[i]` с флагом «использовать при формировании content».
- Для `write_file` content ограничить (например 50k символов) или разрезать на чанки.

---

## 7. Структура кода (предложение)

```
planner/
├── run.py              # run_planner() — точка входа
├── run_multistep.py    # НОВЫЙ: _run_multistep_async()
├── prompts.py
│   ├── build_plan_prompt()           # текущий, одношаговый
│   ├── build_plan_step_prompt()      # НОВЫЙ: для одного шага
│   ├── build_refinement_instructions()
│   └── build_synthesize_*()
└── state.py            # НОВЫЙ: StepState, ToolResult
```

### Переключение режима

```python
USE_MULTISTEP_PLANNER = os.environ.get("USE_MULTISTEP_PLANNER", "false").lower() == "true"

if USE_MULTISTEP_PLANNER:
    reply = run_planner_multistep(query, rag_context, graph_context, role)
else:
    reply = run_planner(query, rag_context, graph_context, role)
```

---

## 8. Промпт для шага планирования (build_plan_step_prompt)

```
Ты планировщик задач. У пользователя запрос: «{original_query}»

Результаты предыдущих шагов:
{results_block}

Что осталось сделать: {remaining_goal}

Доступные инструменты:
{tools_desc}

Твоя задача:
1. Решить: нужен ли ещё один вызов инструмента? Если всё сделано — верни action: "done"
2. Если нужен вызов — выбери server, tool, arguments
3. УЛУЧШЬ аргументы: преврати их в профессиональный промпт, сохраняя суть. Например:
   - "найди про X" → query: "X: определение, применение, последние исследования"
   - content для write_file: используй результат предыдущего шага, структурируй и сократи при необходимости

Формат ответа (JSON):
{"action": "call"|"done", "reasoning": "...", "remaining_goal": "...",
 "call": {"server": "...", "tool": "...", "arguments": {...}, "refined_prompt": "..."}}

Ответ СТРОГО JSON.
```

---

## 9. Обработка ошибок

- Ошибка tool → добавляем в results `{result: "Ошибка: ..."}`, продолжаем цикл; LLM может повторить или выбрать другой инструмент
- LLM вернул невалидный JSON → retry 1 раз, иначе fallback на synthesize с тем что есть
- Превышен max_steps → принудительный синтез с накопленными results

---

## 10. Метрики и логирование

- Количество шагов
- Какие tools вызывались
- Refined prompts (для отладки)
- Время на шаг и суммарное
