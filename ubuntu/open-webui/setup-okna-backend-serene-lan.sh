#!/bin/bash
# Релей SereneDB на LAN для Grafana фронта okna (дашборды).
# Решение владельца 18.08: Grafana живёт на веб-сервере okna (10.3.0.2),
# а SereneDB слушает только 127.0.0.1:7890 — движок не перенастраиваем,
# ставим штатный systemd-socket-proxyd: LAN:7890 → 127.0.0.1:7890.
# Движок видит подключение как локальное — его auth не трогаем.
# ufw: только с фронта 10.3.0.2.
#
# Запуск (root на бэкенде): bash /opt/1c-open-webui/setup-okna-backend-serene-lan.sh

set -euo pipefail

LAN_IP="${LAN_IP:-10.3.0.4}"
FRONT_IP="${FRONT_IP:-10.3.0.2}"

[ "$(id -u)" = 0 ] || { echo "нужен root"; exit 1; }

cat > /etc/systemd/system/1c-serene-lan-relay.socket <<EOF
[Unit]
Description=SereneDB LAN relay socket (Grafana фронта okna)

[Socket]
ListenStream=$LAN_IP:7890
FreeBind=true

[Install]
WantedBy=sockets.target
EOF
cat > /etc/systemd/system/1c-serene-lan-relay.service <<EOF
[Unit]
Description=SereneDB LAN relay → 127.0.0.1:7890
Requires=1c-serene-lan-relay.socket
After=1c-serene-lan-relay.socket

[Service]
ExecStart=/lib/systemd/systemd-socket-proxyd 127.0.0.1:7890
EOF
systemctl daemon-reload
systemctl enable --now 1c-serene-lan-relay.socket >/dev/null
systemctl restart 1c-serene-lan-relay.socket

if command -v ufw >/dev/null 2>&1; then
    ufw allow from "$FRONT_IP" to any port 7890 proto tcp comment "grafana dashboards front" >/dev/null
fi

sleep 1
ss -tln | grep -q "$LAN_IP:7890" \
    && echo "✅ релей слушает $LAN_IP:7890 (только с $FRONT_IP по ufw)" \
    || { echo "релей не поднялся: journalctl -u 1c-serene-lan-relay* -n 30"; exit 1; }
