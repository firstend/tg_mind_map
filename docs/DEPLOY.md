# Деплой

## Предварительные требования

- Сервер с Ubuntu 22.04 (или совместимый Linux)
- SSH-доступ по ключу (пользователь deploy с sudo)

## Первичная настройка (один раз)

1. **Bootstrap** — rsync, Docker, права:
   ```bash
   scp -i .ssh/tg_mind_map_ruvds scripts/bootstrap.sh deploy@<IP>:
   ssh -i .ssh/tg_mind_map_ruvds deploy@<IP> "sudo bash bootstrap.sh"
   # Выйди и войди снова (чтобы применилась группа docker)
   ```

2. **Создай `.env`** на сервере:
   ```bash
   scp -i .ssh/tg_mind_map_ruvds .env.example deploy@<IP>:/opt/tg_mind_map/.env
   ssh -i .ssh/tg_mind_map_ruvds deploy@<IP> "nano /opt/tg_mind_map/.env"
   ```
   Заполни: BOT_TOKEN, QWEN_API_KEY (или DASHSCOPE_API_KEY).

## Локальный деплой (deploy.sh)

```bash
SERVER=deploy@<IP> ./deploy.sh
```

Или с переменными:
```bash
SERVER=deploy@176.113.80.107 SSH_KEY=.ssh/tg_mind_map_ruvds ./deploy.sh
```

## GitHub Actions

### CI (lint, test)
Запускается автоматически при push в `main` и `develop`.

### Deploy
Запускается при push в `main` (и вручную через workflow_dispatch).

**Секреты репозитория** (Settings → Secrets and variables → Actions):
- `SSH_HOST` — IP сервера (например, `176.113.80.107`)
- `SSH_USER` — пользователь SSH (например, `deploy`)
- `SSH_PRIVATE_KEY` — содержимое приватного SSH-ключа (`.ssh/tg_mind_map_ruvds`)

## После деплоя

1. **Проверка здоровья Gateway** (Redis включён):
   ```bash
   curl http://<IP>:8000/health
   # {"status": "ok", "redis": "ok"}
   ```

2. **Мониторинг** (контейнеры + health + логи):
   ```bash
   ./scripts/monitor.sh deploy@<IP>
   ```

3. **Режим poll (по умолчанию)** — webhook не нужен, работает сразу.

   **Режим webhook** (если есть домен и HTTPS):
   ```bash
   # В .env: GATEWAY_MODE=webhook
   curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<DOMAIN>/webhook"
   ```

4. **Логи в реальном времени**:
   ```bash
   ssh deploy@<IP> "cd /opt/tg_mind_map && docker compose logs -f"
   ```
