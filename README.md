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

## Запуск прототипа

1. **Окружение**
   - Python 3.11+
   - Redis и PostgreSQL с pgvector: `docker compose up -d`
   - Создай бота через [@BotFather](https://t.me/BotFather), возьми токен.

2. **Конфиг**
   - Скопируй `.env.example` в `.env`.
   - Заполни `BOT_TOKEN`, `OPENAI_API_KEY`. `REDIS_URL` и `DATABASE_URL` — по умолчанию для docker-compose (Redis, PostgreSQL с pgvector).

3. **Установка**
   ```bash
   pip install -r requirements.txt
   ```

4. **Запуск (из корня репозитория)**
   - Gateway (webhook): `uvicorn gateway.main:app --host 0.0.0.0 --port 8000`
   - Worker: `python -m worker.processor`
   - Sender: `python -m sender.run`

5. **Webhook**
   - Gateway должен быть доступен по HTTPS (для продакшена или ngrok для теста).
   - Установи webhook: `curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<BASE_URL>/webhook"`

После этого сообщения боту попадают в очередь, воркер обрабатывает пайплайн (граф + RAG + агент «универсальный помощник»), Sender шлёт ответ в Telegram.

## Статус

Реализовано: Gateway → Redis → Worker (граф PostgreSQL, RAG pgvector, ИИ OpenAI) → Sender. Первый агент — универсальный помощник. Дальше: классификация темы (ИИ), транскрипция голоса.
