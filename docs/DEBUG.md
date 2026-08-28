# Отладка

## Цепочка обработки

```
Telegram → Poller (gateway) → Redis incoming → Worker → Redis outgoing → Sender → Telegram
```

## Быстрая диагностика

```bash
ssh deploy@<IP> "cd /opt/tg_mind_map && docker compose logs --tail=100 gateway worker sender"
```

### Что искать

| Компонент | Ожидается | Проблема |
|-----------|-----------|----------|
| **gateway** | `Poller: long polling started (webhook снят)` | Нет — BOT_TOKEN пустой или poller упал |
| **worker** | Без traceback | `vector type not found` → расширение pgvector не создано |
| **sender** | Без traceback | Ошибки API Telegram — проверь BOT_TOKEN |

## Частые ошибки

### 1. Worker: `vector type not found in the database`
Расширение pgvector не создано до первого `register_vector`. Исправлено: `get_conn()` теперь создаёт `CREATE EXTENSION IF NOT EXISTS vector` перед регистрацией.

### 2. Ответа нет
- **Worker падает** — смотри логи worker
- **Poller не получает** — проверь, что webhook снят: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`
- **Redis недоступен** — `docker compose ps`, все ли контейнеры Running

### 3. BOT_TOKEN
```bash
# На сервере: проверить, что .env содержит BOT_TOKEN
ssh deploy@<IP> "grep BOT_TOKEN /opt/tg_mind_map/.env | head -1"
```

## Ручная проверка очередей

```bash
# Redis CLI в контейнере
docker compose exec redis redis-cli
> LLEN mindmap:incoming
> LLEN mindmap:outgoing
> LRANGE mindmap:incoming 0 -1
```
