#!/bin/bash
# Деплой на сервер: rsync + запуск server-setup.sh
# Использование: ./deploy.sh [user@host]
# Или: SERVER=root@176.113.80.107 ./deploy.sh

set -e

SERVER="${SERVER:-$1}"
SSH_KEY="${SSH_KEY:-.ssh/tg_mind_map_ruvds}"
REMOTE_DIR="${REMOTE_DIR:-/opt/tg_mind_map}"

if [ -z "$SERVER" ]; then
    echo "Укажи сервер: ./deploy.sh root@176.113.80.107"
    echo "Или: SERVER=root@176.113.80.107 ./deploy.sh"
    exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
[ -f "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")

echo "Синхронизация на $SERVER:$REMOTE_DIR ..."
rsync -avz --delete \
    -e "ssh ${SSH_OPTS[*]}" \
    --exclude '.git' \
    --exclude '.env' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.ssh' \
    ./ "$SERVER:$REMOTE_DIR/"

echo "Запуск server-setup на сервере..."
ssh "${SSH_OPTS[@]}" "$SERVER" "cd $REMOTE_DIR && chmod +x scripts/server-setup.sh && ./scripts/server-setup.sh"

echo "Деплой завершён."
