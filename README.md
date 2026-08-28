# Карта идей (Mind Map)

Система для накопления и структурирования мыслей, идей и обсуждений через Telegram: наговариваешь/пишешь боту → сервер кладёт в очередь → воркер обрабатывает ИИ (тема, RAG, ответ) → ответ возвращается в Telegram.

## Архитектура и проектирование

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — общая схема и компоненты.
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — граф мыслей и RAG.
- [docs/WORKER_PIPELINE.md](docs/WORKER_PIPELINE.md) — пайплайн воркера по шагам.
- [docs/AGENTS.md](docs/AGENTS.md) — контракт первого агента (универсальный помощник).

**Кратко:**
- **Telegram Bot** — приём голос/текст от пользователя.
- **Gateway** — приём с Telegram, валидация, постановка в очередь.
- **Очередь** — входящие сообщения и исходящие ответы.
- **Worker** — разбор очереди, ИИ (новая тема / продолжение), RAG, ответ через ИИ, в очередь ответов.
- **Sender** — отправка ответов в Telegram.
- **Агенты** — типы отвечающих; первый — универсальный помощник.

## Структура репозитория

```
tg_mind_map/
├── docs/          # Документация, архитектура
├── gateway/       # Webhook, постановка в очередь
├── worker/        # Обработка очереди, ИИ, RAG, граф
├── sender/        # Отправка ответов в Telegram
└── shared/        # Общие модели, клиенты очереди
```

## Запуск

### Локально (без Docker)
1. Redis и PostgreSQL: `docker compose up -d redis postgres`
2. `.env` с BOT_TOKEN, REDIS_URL, DATABASE_URL и ключом ИИ: `DASHSCOPE_API_KEY` (Qwen, по умолчанию) или `OPENAI_API_KEY`
3. `uvicorn gateway.main:app --port 8000`, `python -m worker.processor`, `python -m sender.run`

### Docker (полный стек)
```bash
cp .env.example .env   # заполни BOT_TOKEN, DASHSCOPE_API_KEY (Qwen) или OPENAI_API_KEY
docker compose up -d
```

### Деплой на сервер
```bash
# Один раз: bootstrap (rsync, Docker, права)
scp scripts/bootstrap.sh deploy@<IP>: && ssh deploy@<IP> "sudo bash bootstrap.sh"
# Затем: deploy
SERVER=deploy@<IP> ./deploy.sh
```
Подробнее: [docs/DEPLOY.md](docs/DEPLOY.md)

### Режим Gateway: poll или webhook

**По умолчанию — poll (long polling)**: не нужен HTTPS, webhook не настраивать. Бот сам опрашивает Telegram.

**Webhook** (для продакшена с доменом): укажи `GATEWAY_MODE=webhook` и установи webhook:
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<DOMAIN>/webhook"
```

## Статус

Реализовано: Gateway → Redis → Worker (граф PostgreSQL, RAG pgvector, ИИ OpenAI) → Sender. Первый агент — универсальный помощник. Дальше: классификация темы (ИИ), транскрипция голоса.
