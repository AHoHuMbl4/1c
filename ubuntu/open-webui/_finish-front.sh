#!/bin/bash
# Завершение установки фронта okna (после uv/open-webui).
set -euo pipefail
TOK="${GATEWAY_TOKEN:?нужен GATEWAY_TOKEN}"
BACKEND="${BACKEND_IP:-10.3.0.4}"
GPORT="${GATEWAY_PORT:-18801}"

cat > /home/webui/.open-webui.env <<EENV
OPENAI_API_KEY=${TOK}
OPENAI_API_BASE_URL=http://${BACKEND}:${GPORT}/v1
ENABLE_OLLAMA_API=false
DATA_DIR=/home/webui/open-webui-data
WEBUI_NAME="Ассистент 1С"
ENABLE_VERSION_UPDATE_CHECK=false
EENV
chown webui:webui /home/webui/.open-webui.env
chmod 600 /home/webui/.open-webui.env
install -d -m 700 -o webui -g webui /home/webui/open-webui-data
install -d -m 755 -o webui -g webui /home/webui/.config/systemd/user
install -m 644 -o webui -g webui /opt/1c-open-webui/systemd/open-webui.service \
  /home/webui/.config/systemd/user/open-webui.service
install -m 644 /opt/1c-open-webui/Caddyfile.okna /etc/caddy/Caddyfile
sed -i "s|__DOMAIN__|okna.timpul.pro|g" /etc/caddy/Caddyfile

UID_WEB=$(id -u webui)
systemctl start "user@${UID_WEB}.service" || true
sleep 2
runuser -u webui -- env XDG_RUNTIME_DIR=/run/user/"$UID_WEB" systemctl --user daemon-reload
runuser -u webui -- env XDG_RUNTIME_DIR=/run/user/"$UID_WEB" systemctl --user enable --now open-webui.service
systemctl enable --now caddy
# 🔴 СНАЧАЛА 22 — иначе enable отрежет SSH (живой случай 13.08)
ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
sleep 15

echo ===STATUS===
runuser -u webui -- env XDG_RUNTIME_DIR=/run/user/"$UID_WEB" systemctl --user is-active open-webui || true
systemctl is-active caddy || true
ss -tlnp | grep -E ':8080|:80 |:443' || true
curl -sI http://127.0.0.1:8080/ | head -5 || true

ADMIN_PASS=$(openssl rand -base64 18)
OWUI_URL=http://127.0.0.1:8080 ADMIN_EMAIL=admin@okna.local ADMIN_PASS="$ADMIN_PASS" \
  OPENAI_API_KEY="$TOK" OPENAI_API_BASE_URL="http://${BACKEND}:${GPORT}/v1" \
  /home/webui/open-webui-venv/bin/python /opt/1c-open-webui/configure-branding.py \
  || echo BRANDING_FAIL
echo "ADMIN_EMAIL=admin@okna.local"
echo "ADMIN_PASS=$ADMIN_PASS"

curl -sI "https://okna.timpul.pro/" | head -8 || true
