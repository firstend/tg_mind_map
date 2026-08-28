#!/bin/bash
# Первичная настройка сервера (один раз). Запускать по SSH: bash -s < scripts/bootstrap.sh
# Или: scp scripts/bootstrap.sh deploy@<IP>: && ssh deploy@<IP> 'sudo bash bootstrap.sh'

set -e

echo "=== 1. Установка rsync ==="
apt-get update
apt-get install -y rsync

echo "=== 2. Права на /opt/tg_mind_map ==="
mkdir -p /opt/tg_mind_map
# Владелец — пользователь, от которого запущен скрипт (обычно deploy)
CURRENT_USER="${SUDO_USER:-$USER}"
if [ -n "$CURRENT_USER" ] && [ "$CURRENT_USER" != "root" ]; then
    chown -R "$CURRENT_USER:$CURRENT_USER" /opt/tg_mind_map
fi

echo "=== 3. Docker (Ubuntu packages, без конфликта containerd) ==="
# Удалить репозиторий Docker, если есть — он конфликтует с Ubuntu
rm -f /etc/apt/sources.list.d/docker*.list 2>/dev/null || true
apt-get update

# Установить из Ubuntu (docker.io использует системный containerd)
apt-get install -y docker.io docker-compose-plugin

# Пользователь в группу docker
if [ -n "$CURRENT_USER" ] && [ "$CURRENT_USER" != "root" ]; then
    usermod -aG docker "$CURRENT_USER"
    echo "Пользователь $CURRENT_USER добавлен в группу docker. Войди заново для применения."
fi

systemctl enable docker
systemctl start docker

echo "=== Готово. Дальше: скопируй .env, затем ./deploy.sh ==="
