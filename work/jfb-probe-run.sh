#!/bin/bash
# Загрузка env полигона :8092 и запуск jfb-probe.py на OKNA.
# Не source целиком: DSN с пробелами. Строки KEY=VALUE → export.
set -euo pipefail

PROBE_ROOT="${PROBE_ROOT:-/tmp/probe_root}"
PROBE_PY="${PROBE_PY:-/tmp/jfb-probe.py}"
PY="${PY:-/opt/openclaw-mcp/venv/bin/python}"

load_env_file() {
  local f="$1" line key val
  [ -f "$f" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    val="${line#*=}"
    # только имена переменных окружения
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # снять одну пару кавычек, если обёрнуто
    if [[ "$val" == \"*\" && "$val" == *\" ]]; then
      val="${val:1:${#val}-2}"
    elif [[ "$val" == \'*\' && "$val" == *\' ]]; then
      val="${val:1:${#val}-2}"
    fi
    export "$key=$val"
  done < "$f"
}

# Порядок как у transient probe8092.service
load_env_file /etc/1c-mcp-reports.env
load_env_file /etc/1c-embed.env
load_env_file /etc/1c-serene-ask.env
load_env_file /etc/1c-serene-ask-postgres.env
load_env_file "$PROBE_ROOT/port.env"

# LLM/агент: песочница, если юнит не задал
export OPENCLAW_HOME="${OPENCLAW_HOME:-/home/undebot/.openclaw-sandbox}"
# независимые разборы двух формулировок
export ASK_INTENT_MEMO="${ASK_INTENT_MEMO:-0}"
export PROBE_ROOT

echo "jfb-probe-run: PROBE_ROOT=$PROBE_ROOT OPENCLAW_HOME=$OPENCLAW_HOME" >&2
echo "jfb-probe-run: DSN_RO_set=$([[ -n ${SERENEDB_DSN_RO:-} ]] && echo yes || echo no) DS_KEY_set=$([[ -n ${DEEPSEEK_API_KEY:-} ]] && echo yes || echo no) MODEL=${DEEPSEEK_MODEL:-}" >&2

cd "$PROBE_ROOT"
exec "$PY" "$PROBE_PY"
