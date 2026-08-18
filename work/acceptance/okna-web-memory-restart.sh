#!/bin/bash
# Добавить EMBED_API_KEY в managed env web-гейтвея + пересборка индекса
set -euo pipefail
UNIT=/home/undebot/.config/systemd/user/openclaw-gateway-web.service
BOT=undebot
UID_BOT=$(id -u "$BOT")
XDG="/run/user/$UID_BOT"

python3 - "$UNIT" <<'PY'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
text = p.read_text()
if "EMBED_API_KEY" not in text:
    text = text.replace(
        "Environment=OPENCLAW_SERVICE_MANAGED_ENV_KEYS=DEEPSEEK_API_KEY",
        "Environment=OPENCLAW_SERVICE_MANAGED_ENV_KEYS=DEEPSEEK_API_KEY,EMBED_API_KEY",
    )
    p.write_text(text)
    print("unit: added EMBED_API_KEY to managed env keys")
else:
    print("unit: EMBED_API_KEY already in unit")
PY

runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" \
  systemctl --user daemon-reload
runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" \
  systemctl --user restart openclaw-gateway-web
sleep 5
curl -sf "http://127.0.0.1:18801/health" >/dev/null && echo "health OK"

WEB_ENV=/home/undebot/.openclaw-web/gateway.systemd.env
# shellcheck disable=SC1091
source /etc/1c-embed.env
grep -v '^EMBED_API_KEY=' "$WEB_ENV" 2>/dev/null >"$WEB_ENV.tmp" || true
printf 'EMBED_API_KEY=%s\n' "$EMBED_API_KEY" >>"$WEB_ENV.tmp"
mv "$WEB_ENV.tmp" "$WEB_ENV"
chown undebot:undebot "$WEB_ENV"
chmod 600 "$WEB_ENV"
export EMBED_API_KEY
runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" EMBED_API_KEY="$EMBED_API_KEY" \
  openclaw --profile web memory index --force --agent main 2>&1 | tail -8

runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" \
  openclaw --profile web memory status --deep --agent main 2>&1 | tail -12

echo "=== memory errors last 5 min ==="
journalctl _SYSTEMD_USER_UNIT=openclaw-gateway-web -M "${BOT}@" --since "5 min ago" --no-pager \
  | grep -iE 'Memory index failed|memory embeddings|No API key|openai-compatible embeddings failed|401' \
  || echo "(none)"
