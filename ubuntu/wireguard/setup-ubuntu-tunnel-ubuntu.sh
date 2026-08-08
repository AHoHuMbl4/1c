#!/bin/sh
# Поднимает ВТОРОЙ обратный туннель: Ubuntu-релей 89.23.101.22:6022 → Ubuntu:6090.
# Запускать ОТ ROOT на этом сервере:
#   sudo sh ubuntu/wireguard/setup-ubuntu-tunnel-ubuntu.sh
# Первый юнит (1c-gate-tunnel.service, FreeBSD) НЕ трогает: оба релея живы
# параллельно, переключение трафика — DNS. Ключ тот же (ставится
# setup-ubuntu-tunnel.sh); публичная часть уже установлена на новом релее
# (юзер gate-tunnel, restrict + permitlisten 127.0.0.1:6022).
set -eu

[ -f /etc/ssh/gate-tunnel.ed25519 ] || { echo "НЕТ /etc/ssh/gate-tunnel.ed25519 — сначала sudo sh ubuntu/wireguard/setup-ubuntu-tunnel.sh" >&2; exit 1; }

install -m 644 -o root -g root ubuntu/wireguard/1c-gate-tunnel-ubuntu.service /etc/systemd/system/1c-gate-tunnel-ubuntu.service

# Ручной туннель из сессии (проба цепочки) держит 6022 на новом релее — гасим,
# юнит поднимет свой
pkill -f "gate-tunnel@89.23.101.22" 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now 1c-gate-tunnel-ubuntu.service
sleep 3
systemctl --no-pager --full status 1c-gate-tunnel-ubuntu.service | head -8
echo "--- проверка слушателя: ssh root@89.23.101.22 'ss -tln | grep 6022'"
