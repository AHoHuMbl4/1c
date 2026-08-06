#!/bin/sh
# Поднимает постоянный обратный туннель FreeBSD:6022 → Ubuntu:6090 (приёмник пакетов).
# Запускать ОТ ROOT на этом сервере:
#   sudo sh ubuntu/wireguard/setup-ubuntu-tunnel.sh
# Ключ туннеля НЕ в git — читается из /home/claudedev/.ssh-bridge/gate-tunnel.ed25519
# (можно передать другой путь аргументом). Публичная часть уже установлена на FreeBSD
# (юзер gate-tunnel, restrict + permitlisten 127.0.0.1:6022).
set -eu

KEY_SRC="${1:-/home/claudedev/.ssh-bridge/gate-tunnel.ed25519}"
[ -f "$KEY_SRC" ] || { echo "НЕТ файла ключа: $KEY_SRC" >&2; exit 1; }

install -m 600 -o root -g root "$KEY_SRC" /etc/ssh/gate-tunnel.ed25519
install -m 644 -o root -g root ubuntu/wireguard/1c-gate-tunnel.service /etc/systemd/system/1c-gate-tunnel.service

# Ручной туннель из сессии (проба цепочки) держит 6022 — гасим, юнит поднимет свой
pkill -f "gate-tunnel@201.34.130.46" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now 1c-gate-tunnel.service
sleep 3
systemctl --no-pager --full status 1c-gate-tunnel.service | head -8
echo "--- слушатель на FreeBSD должен появиться: ssh root@201.34.130.46 'sockstat -4 -l | grep 6022'"
