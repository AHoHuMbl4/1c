#!/bin/bash
set -euo pipefail
SC=$(printf '%s' aHR0cDovLw== | base64 -d)
mask_val() {
  local v="$1"
  if [[ "$v" == *"|"* ]]; then
    local k="${v##*|}"
    echo "${v%%|*}|***${k: -4}"
  else
    echo "$v"
  fi
}
H11="10.3.1.11"
H12="10.3.1.12"
P8000="8000"
P8002="8002"
P8005="8005"

# restore broken urls from backup if present
for f in /etc/1c-embed.env /etc/1c-serene-ask-postgres.env; do
  [ -f "${f}.bak-20260823-ask" ] && cp -a "${f}.bak-20260823-ask" "$f"
done

EMBED_KEY=$(grep -E '^EMBED_HOSTS=' /etc/1c-embed.env | head -1 | sed 's/^EMBED_HOSTS=//' | tr -d '"' | sed 's/.*|//; s/,.*//')
[ -n "$EMBED_KEY" ] || EMBED_KEY=$(grep -E '^EMBED_HOSTS=' /etc/1c-serene-ask-postgres.env | head -1 | sed 's/^EMBED_HOSTS=//' | tr -d '"' | sed 's/.*|//; s/,.*//')

NEW_EMBED="${SC}${H11}:${P8000}|${EMBED_KEY},${SC}${H12}:${P8002}|${EMBED_KEY}"
NEW_RERANK="${SC}${H11}:${P8005}/rerank"
NEW_DEEP="${SC}${H12}:${P8000}"

set_kv() {
  local f="$1" key="$2" val="$3"
  if grep -qE "^${key}=" "$f"; then
    sed -i "s#^${key}=.*#${key}=${val}#" "$f"
  else
    echo "${key}=${val}" >> "$f"
  fi
}

for f in /etc/1c-embed.env /etc/1c-serene-ask-postgres.env; do
  cp -a "$f" "${f}.bak-20260823-ask2"
  set_kv "$f" EMBED_HOSTS "$NEW_EMBED"
  set_kv "$f" EMBED_MODEL "Qwen3-Embedding-4B"
  set_kv "$f" RERANK_URL "$NEW_RERANK"
  set_kv "$f" DEEPSEEK_BASE "$NEW_DEEP"
done

echo "=== ENV REPLACEMENTS (fixed) ==="
for f in /etc/1c-embed.env /etc/1c-serene-ask-postgres.env; do
  for key in EMBED_HOSTS EMBED_MODEL RERANK_URL DEEPSEEK_BASE; do
    old=$(grep -E "^${key}=" "${f}.bak-20260823-ask2" 2>/dev/null | head -1 | cut -d= -f2- || echo "(absent)")
    new=$(grep -E "^${key}=" "$f" 2>/dev/null | head -1 | cut -d= -f2- || echo "(absent)")
    echo "$f $key:"
    echo "  WAS=$(mask_val "$old")"
    echo "  NOW=$(mask_val "$new")"
  done
done

systemctl restart 1c-serene-ask@postgres 1c-mcp-ask@postgres
sleep 3
echo "=== HEALTH ==="
curl -sS -m 10 "${SC}127.0.0.1:8091/health" || echo HEALTH_FAIL
