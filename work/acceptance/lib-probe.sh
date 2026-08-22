#!/usr/bin/env bash
# Общая обёртка протокола замера проб. source из приборов work/acceptance/*.sh
set -euo pipefail

PROBE_LIB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE_PY="$PROBE_LIB_ROOT/probe_protocol.py"

probe_rid() {
  echo "probe-$(date -u +%Y%m%dT%H%M%SZ)-$$"
}

probe_code_md5() {
  local f="${1:-/srv/1c/ubuntu/serenedb/serene_ask.py}"
  python3 -c 'import hashlib,sys; p=sys.argv[1]; print(hashlib.md5(open(p,"rb").read()).hexdigest()[:8])' "$f" 2>/dev/null \
    || md5sum "$f" 2>/dev/null | awk '{print substr($1,1,8)}' || echo "?"
}

# Печать + запись строки PROBE. Аргументы: rid port code_md5 outcome question [record_file]
probe_emit() {
  local rid="$1" port="$2" cmd5="$3" outcome="$4" question="$5" record="${6:-}"
  python3 "$PROBE_PY" format \
    --rid "$rid" --port "$port" --code-md5 "$cmd5" --outcome "$outcome" \
    ${record:+--record "$record"} \
    "$question" >&2
}

# Сверка ask_journal после /ask. DSN: PROBE_JOURNAL_DSN или postgres@7890.
probe_verify_journal() {
  local question="$1" rid="${2:-}" wait="${3:-1.5}"
  local args=(verify --wait "$wait")
  [[ -n "$rid" ]] && args+=(--rid "$rid")
  [[ -n "${PROBE_JOURNAL_DSN:-}" ]] && args+=(--dsn "$PROBE_JOURNAL_DSN")
  python3 "$PROBE_PY" "${args[@]}" "$question"
}

# Громкий провал самопроверки
probe_fail_journal() {
  echo "🔴 PROBE INVALID: $*" >&2
  exit 1
}
