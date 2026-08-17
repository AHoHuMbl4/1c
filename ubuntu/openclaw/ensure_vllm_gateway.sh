#!/bin/bash
# Подключить vLLM (Qwen3.8-27B) к шлюзу OpenClaw undebot — идемпотентно, с бэкапом.
#
# Зовётся из branch_alias.sh / wiki_alias.sh при ALIAS_ENSURE_VLLM=1 (умолчание).
# Должен выполняться от undebot (1c-branch-alias через runuser) или с правом писать
# ~/.openclaw/openclaw.json. Ключ и URL — из окружения (EnvironmentFile embed).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
BOTUSER="${OPENCLAW_USER:-undebot}"
HOME="${HOME:-/home/$BOTUSER}"
STATE="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
CFG="${OPENCLAW_CONFIG_PATH:-$STATE/openclaw.json}"
[ "${ALIAS_ENSURE_VLLM:-1}" = "0" ] && exit 0
[ "$(id -un)" != "${OPENCLAW_USER:-undebot}" ] && [ ! -w "$CFG" ] 2>/dev/null && exit 0

export VLLM_API_KEY="${VLLM_API_KEY:-${EMBED_API_KEY:-}}"
export VLLM_BASE_URL="${VLLM_BASE_URL:-}"
export VLLM_MODEL_ID="${VLLM_MODEL_ID:-Qwen3.8-27B}"
[ -z "$VLLM_API_KEY" ] || [ -z "$VLLM_BASE_URL" ] && {
  echo "ensure_vllm: нет VLLM_API_KEY=${VLLM_API_KEY:+set} VLLM_BASE_URL=${VLLM_BASE_URL:-unset} — пропуск" >&2
  exit 0
}

BAK=""
if [ -f "$CFG" ]; then
  BAK="$STATE/openclaw.json.bak-vllm-$(date +%Y%m%d-%H%M%S)"
  cp "$CFG" "$BAK"
  echo "ensure_vllm: бэкап $BAK"
fi

PATCH_OUT=$(python3 "$HERE/patch_vllm_provider.py" "$CFG" 2>&1) || exit 1
echo "$PATCH_OUT"
CONFIG_CHANGED=0
case "$PATCH_OUT" in *обновлён*) CONFIG_CHANGED=1;; esac

if command -v openclaw >/dev/null 2>&1; then
  printf '%s\n' "$VLLM_API_KEY" | openclaw models auth paste-api-key \
    --provider vllm --profile-id vllm:default 2>/dev/null || true
fi

GWENV="$STATE/gateway.systemd.env"
if [ -w "$GWENV" ] || { touch "$GWENV" 2>/dev/null && [ -w "$GWENV" ]; }; then
  grep -v '^VLLM_' "$GWENV" 2>/dev/null > "$GWENV.tmp" || : > "$GWENV.tmp"
  {
    cat "$GWENV.tmp"
    printf 'VLLM_API_KEY=%s\n' "$VLLM_API_KEY"
    printf 'VLLM_BASE_URL=%s\n' "$VLLM_BASE_URL"
  } > "$GWENV.new"
  mv "$GWENV.new" "$GWENV"
  chmod 600 "$GWENV" 2>/dev/null || true
  rm -f "$GWENV.tmp"
fi

if [ "$CONFIG_CHANGED" = 1 ] && [ "$(id -un)" = "${OPENCLAW_USER:-undebot}" ]; then
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export XDG_RUNTIME_DIR
  if systemctl --user is-active openclaw-gateway >/dev/null 2>&1; then
    systemctl --user restart openclaw-gateway && echo "ensure_vllm: шлюз перезапущен"
  fi
fi
