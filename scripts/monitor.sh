#!/bin/bash
# Мониторинг: health, статус контейнеров, логи.
# Использование: ./scripts/monitor.sh [user@host]
# Без аргументов — локальная проверка (если gateway на localhost:8000).

set -e

SERVER="${1:-}"
SSH_KEY="${SSH_KEY:-.ssh/tg_mind_map_ruvds}"
REMOTE_DIR="/opt/tg_mind_map"

run_remote() {
    SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=5)
    [ -f "$SSH_KEY" ] && SSH_OPTS+=(-i "$SSH_KEY")
    ssh "${SSH_OPTS[@]}" "$SERVER" "$@"
}

if [ -n "$SERVER" ]; then
    echo "=== Мониторинг $SERVER ==="
    echo ""
    echo "--- Docker контейнеры ---"
    run_remote "cd $REMOTE_DIR && docker compose ps"
    echo ""
    echo "--- Health (Gateway) ---"
    IP=$(echo "$SERVER" | cut -d@ -f2)
    if curl -sf "http://${IP}:8000/health" 2>/dev/null; then
        echo ""
    else
        echo "Health check failed"
    fi
    echo ""
    echo "--- Последние логи (gateway worker sender) ---"
    run_remote "cd $REMOTE_DIR && docker compose logs --tail=20 gateway worker sender"
else
    echo "=== Локальный мониторинг ==="
    echo ""
    echo "--- Health ---"
    curl -sf http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "Gateway не отвечает на localhost:8000"
fi
