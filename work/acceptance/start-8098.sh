#!/bin/bash
# Временный инстанс :8098 — ut_test, модель ответов vLLM/Qwen (не трогает :8099).
set -euo pipefail

load_env() {
  local p line key val
  for p in "$@"; do
    [ -r "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"
      line="${line#"${line%%[![:space:]]*}"}"
      [ -z "$line" ] && continue
      [[ "$line" != *=* ]] && continue
      key="${line%%=*}"
      val="${line#*=}"
      val="${val#"${val%%[![:space:]]*}"}"
      val="${val%"${val##*[![:space:]]}"}"
      if [ "${#val}" -ge 2 ] && [ "${val:0:1}" = "${val: -1}" ]; then
        case "${val:0:1}" in \"|\') val="${val:1:-1}";; esac
      fi
      export "$key=$val"
    done < "$p"
  done
}

load_env /etc/1c-mcp-reports.env /etc/1c-embed.env /etc/1c-serene-ask.env \
         /etc/1c-serene-ask-ut_test.env

export ASK_LISTEN_PORT=8098
export DEEPSEEK_BASE=https://a1f19thc-8000.thundercompute.net
export DEEPSEEK_API_KEY="$EMBED_API_KEY"
export DEEPSEEK_MODEL=Qwen3.8-27B
export DEEPSEEK_THINKING=disabled
export ASK_THINKING_OFF_BODY=1
export ASK_INTENT_MAX_TOKENS=900
export PYTHONPATH=/srv/1c/ubuntu/serenedb:/opt/1c-mcp-reports
exec /opt/openclaw-mcp/venv/bin/python /srv/1c/ubuntu/serenedb/serene_ask.py
