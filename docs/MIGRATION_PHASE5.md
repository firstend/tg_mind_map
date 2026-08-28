# Этап 5 миграции: Расширение MCP серверов

Добавление дополнительных MCP серверов: веб-поиск (Brave), загрузка URL (Fetch), работа со временем (Time).

---

## 1. Цель этапа 5

- **Brave Search**: поиск информации в интернете по запросу пользователя
- **Fetch**: загрузка и извлечение контента с URL
- **Time**: работа с датой/временем, конвертация таймзон

---

## 2. Новые MCP серверы

| Сервер | Пакет | Описание |
|--------|-------|----------|
| `brave_search` | `@brave/brave-search-mcp-server` | Веб-поиск через Brave Search API |
| `fetch` | `mcp-server-fetch` (pip) | Загрузка контента с URL |
| `time` | `mcp-server-time` (pip) | Текущее время, конвертация таймзон |

---

## 3. Инструменты (Tools)

### 3.1 Brave Search

- `brave_web_search` — общий веб-поиск
- `brave_local_search` — поиск локальных бизнесов
- `brave_news_search` — поиск новостей
- `brave_image_search` — поиск изображений
- `brave_video_search` — поиск видео

### 3.2 Fetch

- `fetch` — загрузить контент с URL (HTML → Markdown)

### 3.3 Time

- `get_current_time` — текущее время в указанной таймзоне
- `convert_time` — конвертация времени между таймзонами

---

## 4. Конфигурация

### 4.1 config.yaml

```yaml
servers:
  filesystem:
    transport: stdio
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

  brave_search:
    transport: stdio
    command: ["npx", "-y", "@brave/brave-search-mcp-server"]
    env:
      BRAVE_API_KEY: "${BRAVE_API_KEY}"

  fetch:
    transport: stdio
    command: ["python", "-m", "mcp_server_fetch"]

  time:
    transport: stdio
    command: ["python", "-m", "mcp_server_time"]
```

### 4.2 Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BRAVE_API_KEY` | API ключ Brave Search (https://brave.com/search/api/) |

---

## 5. Обновление router.py

Добавлены ключевые слова для новых инструментов:

```python
PLANNER_KEYWORDS = [
    # Filesystem
    "прочитай", "прочти", "открой файл", ...
    # Web search
    "найди в интернете", "поищи в интернете", "загугли", ...
    # Fetch URL
    "открой ссылку", "загрузи страницу", "fetch url", ...
    # Time
    "который час", "сколько времени", "текущее время", ...
]
```

---

## 6. Примеры запросов

| Запрос | Сервер | Tool |
|--------|--------|------|
| "Найди в интернете информацию про Python 3.13" | brave_search | brave_web_search |
| "Что на сайте https://example.com?" | fetch | fetch |
| "Который сейчас час в Токио?" | time | get_current_time |
| "Прочитай /tmp/data.txt" | filesystem | read_text_file |

---

## 7. Получение Brave API Key

1. Зарегистрируйся на https://brave.com/search/api/
2. Бесплатный план: 2000 запросов/месяц
3. Получи ключ в https://api-dashboard.search.brave.com/app/keys
4. Добавь в `.env`: `BRAVE_API_KEY=your_key_here`

---

## 8. Чеклист этапа 5

- [x] Dockerfile: установка `mcp-server-fetch`, `mcp-server-time`
- [x] config.yaml: добавлены brave_search, fetch, time
- [x] registry.py: поддержка env с ${VAR} синтаксисом
- [x] router.py: keywords для поиска, URL, времени
- [x] .env.example: документация BRAVE_API_KEY
- [ ] Деплой и тестирование
- [ ] Тесты для новых серверов

---

## 9. Риски и ограничения

| Риск | Митигация |
|------|-----------|
| BRAVE_API_KEY не задан | brave_search не загрузится, остальные работают |
| Лимит Brave (2000/мес) | Мониторить использование, при необходимости платный план |
| Fetch блокируется сайтами | Некоторые сайты блокируют автоматические запросы |
