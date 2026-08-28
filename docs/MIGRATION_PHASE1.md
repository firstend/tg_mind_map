# Контракты очередей, API llm_service и mcp_hub

## 1. Контракты очередей

### 1.1 Существующие (без изменений)

| Очередь    | Модель         | Описание                          |
|------------|----------------|-----------------------------------|
| `mindmap:incoming` | IncomingMessage | Запросы из Telegram               |
| `mindmap:outgoing` | OutgoingMessage | Ответы в Telegram                 |

### 1.2 Новые очереди

#### `mindmap:llm_jobs` — задачи для LLM-сервиса

```python
class LLMJobType(str, Enum):
    CHAT = "chat"           # Один раунд чата (system + user)
    EMBEDDING = "embedding" # Эмбеддинг текста
    JSON_EXTRACT = "json_extract"  # Структурированный вывод (extract_theme, classify_topic)

class LLMJob(BaseModel):
    job_id: str                    # UUID, для сопоставления с результатом
    type: LLMJobType
    payload: dict                  # Зависит от type, см. ниже
    reply_queue: str = "mindmap:llm_results"  # Куда положить результат
    priority: int = 0              # Выше = раньше (опционально)
    created_at: str = ""           # ISO timestamp (опционально)
```

**payload по типам:**

```python
# type=chat
{
    "system": str,           # Системный промпт
    "user": str,             # Сообщение пользователя
    "max_tokens": int = 1500,
    "role_hint": str | None  # universal, critic и т.д.
}

# type=embedding
{
    "text": str,
    "dimensions": int | None  # Для Qwen, иначе default
}

# type=json_extract
{
    "prompt": str,           # Полный промпт для LLM
    "schema_hint": str,      # Краткое описание ожидаемого JSON
    "max_tokens": int = 200
}
```

---

#### `mindmap:llm_results` — результаты LLM

```python
class LLMResult(BaseModel):
    job_id: str
    success: bool
    result: Any = None       # Для chat: str, для embedding: list[float], для json_extract: dict
    error: str | None = None # Сообщение об ошибке при success=False
    duration_ms: int = 0     # Опционально, для мониторинга
```

---

### 1.3 Сопоставление job ↔ result

- Воркер генерирует `job_id = uuid4().hex`, кладёт `LLMJob` в `llm_jobs`
- LLM-сервис забирает job, выполняет, кладёт `LLMResult` с тем же `job_id` в `reply_queue`
- Воркер может:
  - **Синхронно**: ждать результат по `job_id` (через отдельный Redis-ключ или подписчика)
  - **Асинхронно**: положить job и продолжить, результат обрабатывать отдельным consumer’ом

**Рекомендация для этапа 1:** синхронный режим — воркер ждёт результат в Redis-ключе `mindmap:llm:pending:{job_id}` с TTL (например 60 сек). LLM-сервис после выполнения пишет результат в этот ключ и делает `publish` в канал — воркер блокируется на `brpop`/`subscribe`.

Упрощённый вариант: отдельная очередь `mindmap:llm_results` с FIFO. Воркер после отправки job ждёт на `llm_results` с timeout; LLM-сервис кладёт результат. Проблема: при нескольких воркерах результат может прийти не тому. Решение: либо один воркер LLM, либо reply_queue = персональная очередь воркера `mindmap:llm:reply:{worker_id}`.

**Этап 1 (простой):** один экземпляр worker, один экземпляр llm_service. Worker кладёт job, блокируется на `llm_results` с timeout 120 сек. LLM-сервис кладёт результат в `llm_results`. Порядок сохраняется при одном consumer.

---

## 2. API llm_service

### 2.1 Входная точка (runner)

```python
# llm_service/runner.py

def run_llm_service():
    """Бесконечный цикл: pop llm_jobs → выполнить → push llm_results."""
    while True:
        job = pop_llm_job(timeout_seconds=30)
        if job is None:
            continue
        result = execute_job(job)
        push_llm_result(result, queue=job.reply_queue)
```

### 2.2 Исполнение job

```python
def execute_job(job: LLMJob) -> LLMResult:
    try:
        start = time.monotonic()
        if job.type == "chat":
            out = _do_chat(job.payload)
        elif job.type == "embedding":
            out = _do_embedding(job.payload)
        elif job.type == "json_extract":
            out = _do_json_extract(job.payload)
        else:
            return LLMResult(job_id=job.job_id, success=False, error=f"Unknown type: {job.type}")
        duration_ms = int((time.monotonic() - start) * 1000)
        return LLMResult(job_id=job.job_id, success=True, result=out, duration_ms=duration_ms)
    except Exception as e:
        return LLMResult(job_id=job.job_id, success=False, error=str(e))
```

### 2.3 Клиент для воркера (вызов через очередь)

```python
# llm_service/client.py

def submit_chat(system: str, user: str, max_tokens: int = 1500, role_hint: str | None = None) -> str:
    """Синхронно: отправить chat job, дождаться результата. Возвращает текст ответа."""
    job_id = uuid4().hex
    job = LLMJob(
        job_id=job_id,
        type="chat",
        payload={"system": system, "user": user, "max_tokens": max_tokens, "role_hint": role_hint},
    )
    push_llm_job(job)
    result = wait_for_llm_result(job_id, timeout_seconds=120)
    if not result.success:
        raise LLMError(result.error)
    return result.result

def submit_embedding(text: str, dimensions: int | None = None) -> list[float]:
    """Синхронно: embedding."""
    ...

def submit_json_extract(prompt: str, schema_hint: str, max_tokens: int = 200) -> dict:
    """Синхронно: извлечение JSON из ответа LLM."""
    ...
```

### 2.4 Ожидание результата (этап 1)

```python
def wait_for_llm_result(job_id: str, timeout_seconds: int = 120) -> LLMResult:
    """Потреблять из llm_results до получения result с нужным job_id или timeout."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        raw = pop_llm_result(timeout_seconds=min(5, int(deadline - time.monotonic())))
        if raw and raw.job_id == job_id:
            return raw
        if raw and raw.job_id != job_id:
            # Чужой результат — вернуть в очередь (LREM + RPUSH) или в отдельную буферную очередь
            push_llm_result(raw)  # Либо игнорировать при одном consumer
    raise TimeoutError(f"LLM job {job_id} timed out")
```

**Важно:** при одном worker и одном llm_service результаты приходят по порядку, можно не проверять `job_id`. При нескольких worker’ах нужны персональные reply-очереди.

---

## 3. API mcp_hub

### 3.1 Реестр MCP-серверов

```python
# mcp_hub/registry.py

@dataclass
class MCPServerConfig:
    name: str
    transport: str  # "stdio" | "sse"
    command: list[str] | None = None   # Для stdio: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path"]
    args: list[str] | None = None
    url: str | None = None             # Для SSE
    env: dict[str, str] | None = None
```

### 3.2 Клиент (подключение к серверу)

```python
# mcp_hub/client.py

class MCPHub:
    def __init__(self, config_path: str = "mcp_hub/config.yaml"):
        self.servers: dict[str, MCPClientSession] = {}
        self._load_config(config_path)

    async def connect(self, server_name: str) -> None:
        """Подключиться к MCP-серверу."""
        ...

    def list_tools(self, server_name: str) -> list[Tool]:
        """Список tools сервера."""
        ...

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Вызвать tool."""
        ...

    def read_resource(self, server_name: str, uri: str) -> str:
        """Прочитать resource."""
        ...
```

### 3.3 Каталог для планировщика

```python
# mcp_hub/catalog.py

def get_tools_catalog() -> list[dict]:
    """Возвращает список всех tools всех серверов для промпта планировщика.
    Формат: [{"server": "filesystem", "name": "read_file", "description": "...", "input_schema": {...}}, ...]
    """
```

### 3.4 Конфигурация (YAML)

```yaml
# mcp_hub/config.yaml

servers:
  filesystem:
    transport: stdio
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
    args: ["/tmp"]

  # web:
  #   transport: sse
  #   url: http://localhost:8080/sse
```

---

## 4. Этап 1 миграции — пошагово

### Цель этапа 1

Вынести вызовы LLM в отдельный сервис с очередью. Поведение системы не меняется.

---

### Шаг 1.1: Модели и очереди

**Файлы:** `shared/models.py`, `shared/queues.py`

1. Добавить `LLMJob`, `LLMResult`, `LLMJobType` в `models.py`
2. Добавить `LLM_JOBS_KEY`, `LLM_RESULTS_KEY`, `push_llm_job`, `pop_llm_job`, `push_llm_result`, `pop_llm_result` в `queues.py`

---

### Шаг 1.2: Структура llm_service

**Создать:**

```
llm_service/
├── __init__.py
├── runner.py    # Цикл pop → execute → push
├── executor.py  # execute_job(), _do_chat, _do_embedding, _do_json_extract
└── client.py    # submit_chat, submit_embedding, submit_json_extract (для воркера)
```

- `executor.py` — перенос логики из `shared/llm.py` (вызовы OpenAI/Qwen)
- `runner.py` — цикл обработки очереди
- `client.py` — обёртки, кладут job и ждут result

---

### Шаг 1.3: Интеграция shared.llm

**Файл:** `shared/llm.py` (без изменений в `worker/processor.py`)

1. Добавить флаг `USE_LLM_SERVICE` (env, по умолчанию `false`).
2. При `USE_LLM_SERVICE=true` делегировать вызовы в `llm_service.client`:
   - `get_embedding` → `submit_embedding`
   - `extract_theme` → `submit_json_extract` + парсинг
   - `classify_topic` → `submit_json_extract` + парсинг
   - `universal_assistant` → `submit_chat`
3. При `USE_LLM_SERVICE=false` — прямые вызовы LLM (совместимость, тесты).

---

### Шаг 1.4: Docker и запуск

1. Добавить сервис `llm_service` в `docker-compose.yml`
2. Команда: `python -m llm_service.runner`
3. Зависимости: Redis, переменные `QWEN_API_KEY` и т.д.
4. Worker зависит от Redis (очередь), явная зависимость от llm_service не нужна

---

### Шаг 1.5: Тесты

1. Юнит-тесты для `llm_service/executor.py` (с моком OpenAI)
2. Интеграционный тест: `push_llm_job` → `pop_llm_result` (при поднятом llm_service)
3. Проверить текущие тесты worker с моком `llm_service.client`

---

### Шаг 1.6: Обратная совместимость

- Переменная `USE_LLM_SERVICE=true|false` (по умолчанию `false`)
- При `false` shared.llm вызывает LLM напрямую (тесты, fallback)
- В docker-compose worker получает `USE_LLM_SERVICE=true`
- Позволяет откатываться без перезапуска llm_service

---

### Чеклист этапа 1

- [x] `shared/models.py`: LLMJob, LLMResult
- [x] `shared/queues.py`: llm_jobs, llm_results
- [x] `llm_service/executor.py`: _do_chat, _do_embedding, _do_json_extract
- [x] `llm_service/runner.py`: цикл
- [x] `llm_service/client.py`: submit_* + wait_for_llm_result
- [x] `shared/llm.py`: делегирование в llm_service по флагу
- [x] `docker-compose.yml`: сервис llm_service
- [x] Тесты (conftest, test_llm_service, test_llm, test_processor)
- [x] Документация

---

## 5. Зависимости этапа 1

Новые пакеты не требуются. Используются: `redis`, `pydantic`, `openai`.

MCP и planner — этапы 2 и 3.
