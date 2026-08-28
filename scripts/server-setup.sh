#!/bin/bash
# Запуск приложения (Docker). Вызывается из deploy.sh.
set -e

cd /opt/tg_mind_map

# Установка rsync (нужен для deploy.sh при первом запуске)
if ! command -v rsync &>/dev/null; then
    echo "Устанавливаю rsync..."
    sudo apt-get update && sudo apt-get install -y rsync
fi

# Установка Docker, если нет (только пакеты Ubuntu — без конфликта containerd)
if ! command -v docker &>/dev/null; then
    echo "Устанавливаю Docker (docker.io из Ubuntu)..."
    sudo rm -f /etc/apt/sources.list.d/docker*.list 2>/dev/null || true
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-plugin
    sudo usermod -aG docker "$(whoami)"
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "Docker установлен. Войди по SSH заново и перезапусти deploy."
    exit 0
fi

# docker-compose plugin
if ! docker compose version &>/dev/null; then
    echo "Устанавливаю Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin
fi

# Права на каталог (если был создан под root)
if [ ! -w . ]; then
    echo "Исправляю права на /opt/tg_mind_map..."
    sudo chown -R "$(whoami):$(whoami)" /opt/tg_mind_map
fi

# Проверка .env
if [ ! -f .env ]; then
    echo "ОШИБКА: .env не найден. Скопируй .env.example в .env и заполни BOT_TOKEN, QWEN_API_KEY."
    exit 1
fi

# Сборка и запуск
docker compose build --no-cache 2>/dev/null || docker compose build
docker compose up -d

echo "Готово. Gateway на порту 8000. Проверка: curl http://localhost:8000/health"
