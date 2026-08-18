#!/bin/bash
# okna backend: memory-core → наш эмбеддер (web-профиль OpenClaw)
set -euo pipefail
STATE=/home/undebot/.openclaw-web
MAIN_ENV=/home/undebot/.openclaw/gateway.systemd.env
WEB_ENV=$STATE/gateway.systemd.env
BOT=undebot
UID_BOT=$(id -u "$BOT")
XDG="/run/user/$UID_BOT"

# baseUrl из /etc/1c-embed.env — один источник правды на юните
# shellcheck disable=SC1091
source /etc/1c-embed.env
BASE_URL="${EMBED_BASE_URL:-${EMBED_HOST%/}/v1}"
BASE_URL="${BASE_URL%/}/v1"
BASE_URL="${BASE_URL//\/v1\/v1/\/v1}"

if grep -q '^EMBED_API_KEY=' "$MAIN_ENV" 2>/dev/null; then
  grep '^EMBED_API_KEY=' "$MAIN_ENV" >"$WEB_ENV.embed.tmp"
  grep -v '^EMBED_API_KEY=' "$WEB_ENV" 2>/dev/null >>"$WEB_ENV.embed.tmp" || true
  mv "$WEB_ENV.embed.tmp" "$WEB_ENV"
  chown "$BOT:$BOT" "$WEB_ENV"
  chmod 600 "$WEB_ENV"
  echo "EMBED_API_KEY: synced to web env"
fi

oc() {
  runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" openclaw --profile web "$@"
}

oc config set agents.defaults.memorySearch.enabled true
oc config set agents.defaults.memorySearch.provider openai-compatible
oc config set agents.defaults.memorySearch.model "${EMBED_MODEL:-Qwen3-Embedding-8B}"
oc config set agents.defaults.memorySearch.remote.baseUrl "$BASE_URL"
oc config set agents.defaults.memorySearch.remote.apiKey '${EMBED_API_KEY}'
oc config set agents.defaults.memorySearch.remote.nonBatchConcurrency 2
oc config set agents.defaults.memorySearch.fallback none
oc config set "agents.defaults.memorySearch.extraPaths" "[\"${STATE}/wiki/main/entities\"]" --strict-json
oc config validate

runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" \
  systemctl --user restart openclaw-gateway-web
sleep 4
curl -sf "http://127.0.0.1:18801/health" >/dev/null && echo "health OK"

EMBED_API_KEY="$(grep '^EMBED_API_KEY=' "$WEB_ENV" | cut -d= -f2-)"
runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" EMBED_API_KEY="$EMBED_API_KEY" \
  openclaw --profile web memory index --force --agent main

runuser -u "$BOT" -- env HOME="/home/$BOT" XDG_RUNTIME_DIR="$XDG" \
  openclaw --profile web memory status --deep --agent main

echo "=== memory errors last 3 min ==="
journalctl _SYSTEMD_USER_UNIT=openclaw-gateway-web -M "${BOT}@" --since "3 min ago" --no-pager \
  | grep -iE 'Memory index failed|memory embeddings|No API key|openai-compatible embeddings failed' \
  || echo "(none)"
