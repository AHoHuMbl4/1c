#!/bin/sh
# Поднимает ТРЕТИЙ обратный туннель: EU-релей 2.28.54.129:6022 → Ubuntu:6090.
# Запускать ОТ ROOT на этом сервере (дев):
#   sudo sh ubuntu/wireguard/setup-ubuntu-tunnel-eu.sh
# Юниты RU-релея (1c-gate-tunnel-ubuntu.service) НЕ трогает: релеи живы
# параллельно, переключение трафика — DNS. Ключ тот же (ставится
# setup-ubuntu-tunnel.sh); публичная часть уже установлена на EU-релее
# (юзер gate-tunnel, restrict + permitlisten 127.0.0.1:6022).
set -eu

[ -f /etc/ssh/gate-tunnel.ed25519 ] || { echo "НЕТ /etc/ssh/gate-tunnel.ed25519 — сначала sudo sh ubuntu/wireguard/setup-ubuntu-tunnel.sh" >&2; exit 1; }

install -m 644 -o root -g root ubuntu/wireguard/1c-gate-tunnel-eu.service /etc/systemd/system/1c-gate-tunnel-eu.service

systemctl daemon-reload
systemctl enable --now 1c-gate-tunnel-eu.service
sleep 3
systemctl --no-pager --full status 1c-gate-tunnel-eu.service | head -8
echo "--- проверка слушателя: ssh -i ~/.ssh/id_ed25519_deploy root@2.28.54.129 'ss -tln | grep 6022'"
