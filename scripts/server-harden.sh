#!/bin/bash
# Усиление сервера: ufw, unattended-upgrades, swap, fail2ban, SSH limits
# Запуск: ssh deploy@<IP> 'bash -s' < scripts/server-harden.sh
# Или: scp scripts/server-harden.sh deploy@<IP>: && ssh deploy@<IP> 'sudo bash server-harden.sh'

set -e

echo "=== 1. UFW (firewall) ==="
apt-get update
apt-get install -y ufw
ufw --force reset 2>/dev/null || true
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 8000/tcp
ufw --force enable
ufw status

echo "=== 2. Unattended upgrades ==="
apt-get install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades <<< "true" 2>/dev/null || true

echo "=== 3. Swap 2GB ==="
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "Swap создан"
else
    echo "Swap уже есть"
fi

echo "=== 4. Fail2ban jail.local ==="
mkdir -p /etc/fail2ban
cat > /etc/fail2ban/jail.local << 'JAIL'
[sshd]
enabled = true
bantime = 1h
findtime = 10m
maxretry = 3
JAIL
systemctl restart fail2ban 2>/dev/null || true

echo "=== 5. SSH limits (sshd_config) ==="
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%s)
grep -q "^MaxAuthTries" /etc/ssh/sshd_config && \
    sed -i 's/^MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config || \
    echo "MaxAuthTries 3" >> /etc/ssh/sshd_config
grep -q "^ClientAliveInterval" /etc/ssh/sshd_config && \
    sed -i 's/^ClientAliveInterval.*/ClientAliveInterval 300/' /etc/ssh/sshd_config || \
    echo "ClientAliveInterval 300" >> /etc/ssh/sshd_config
grep -q "^ClientAliveCountMax" /etc/ssh/sshd_config && \
    sed -i 's/^ClientAliveCountMax.*/ClientAliveCountMax 2/' /etc/ssh/sshd_config || \
    echo "ClientAliveCountMax 2" >> /etc/ssh/sshd_config
systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || true

echo "=== 6. Утилиты (htop, iotop, ncdu) ==="
apt-get install -y htop iotop ncdu

echo "=== Готово ==="
echo "UFW: $(ufw status | head -1)"
echo "Swap: $(free -h | grep Swap)"
echo "Fail2ban: $(systemctl is-active fail2ban 2>/dev/null || echo 'не запущен')"
