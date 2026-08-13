#!/bin/bash
set -euo pipefail
curl -sI -H 'Host: okna.timpul.pro' http://127.0.0.1/ | head -10
echo ===DNS===
getent hosts okna.timpul.pro || true
echo ===RELOAD_CADDY===
systemctl reload caddy || systemctl restart caddy
sleep 8
ss -tlnp | grep -E ':80|:443' || true
journalctl -u caddy -n 60 --no-pager | grep -iE 'certificate|acme|error|tls|okna|obtain' | tail -25 || true
TOK=$(grep OPENAI_API_KEY= /home/webui/.open-webui.env | cut -d= -f2-)
BASE=$(grep OPENAI_API_BASE_URL= /home/webui/.open-webui.env | cut -d= -f2-)
ADMIN_PASS=$(openssl rand -base64 18)
OWUI_URL=http://127.0.0.1:8080 ADMIN_EMAIL=admin@okna.local ADMIN_PASS="$ADMIN_PASS" \
  OPENAI_API_KEY="$TOK" OPENAI_API_BASE_URL="$BASE" \
  /home/webui/open-webui-venv/bin/python /opt/1c-open-webui/configure-branding.py
echo ADMIN_EMAIL=admin@okna.local
echo ADMIN_PASS=$ADMIN_PASS
curl -sI http://127.0.0.1:8080/ | head -3
