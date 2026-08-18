#!/usr/bin/env bash
# Собирает сквозной след по request-id из journald и gateway.log.
# Использование: bash work/acceptance/trace_rid.sh <rid> [since]
#   since — для journalctl (по умолчанию "10 min ago")
set -euo pipefail
RID="${1:?usage: trace_rid.sh <rid> [since]}"
SINCE="${2:-10 min ago}"

GATEWAY_LOG="${GATEWAY_LOG:-/home/undebot/.openclaw/logs/gateway.log}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

collect() {
  local src="$1" line
  while IFS= read -r line; do
    [[ "$line" == *"TRACE $RID"* ]] || continue
    printf '%s\t%s\n' "$src" "$line"
  done
}

{
  for u in $(systemctl list-units '1c-serene-ask@*' --no-legend 2>/dev/null | awk '{print $1}'); do
    journalctl -u "$u" --since "$SINCE" --no-pager -o cat 2>/dev/null | collect "$u" || true
  done
  for u in $(systemctl list-units '1c-mcp-ask@*' --no-legend 2>/dev/null | awk '{print $1}'); do
    journalctl -u "$u" --since "$SINCE" --no-pager -o cat 2>/dev/null | collect "$u" || true
  done
  journalctl -u '1c-mcp-ask.service' --since "$SINCE" --no-pager -o cat 2>/dev/null | collect '1c-mcp-ask' || true
  if [[ -r "$GATEWAY_LOG" ]]; then
    grep -F "TRACE $RID" "$GATEWAY_LOG" 2>/dev/null | collect "gateway.log" || true
  fi
} | sort -t$'\t' -k2 >"$TMP"

if [[ ! -s "$TMP" ]]; then
  echo "TRACE $RID: строк не найдено (since=$SINCE)"
  exit 1
fi

prev_ms=""
echo "=== TRACE $RID (since=$SINCE) ==="
while IFS=$'\t' read -r src line; do
  # TRACE <rid> <layer> <step> <ms> <status...>
  ms="$(echo "$line" | awk '{print $(NF-1)}')"
  status="$(echo "$line" | awk '{for(i=6;i<=NF-1;i++) printf "%s%s", $i, (i<NF-1?" ":"")}')"
  layer="$(echo "$line" | awk '{print $3}')"
  step="$(echo "$line" | awk '{print $4}')"
  delta=""
  if [[ -n "$prev_ms" && "$ms" =~ ^[0-9]+$ && "$prev_ms" =~ ^[0-9]+$ ]]; then
    d=$((ms - prev_ms))
    delta=" (+${d}ms)"
  fi
  prev_ms="$ms"
  printf '%8s%s  %-10s  %-16s  %s  [%s]\n' "${ms}ms" "$delta" "$layer" "$step" "$status" "$src"
done <"$TMP"

last_ms="$(tail -1 "$TMP" | awk '{print $(NF-1)}' | grep -oE '[0-9]+' | tail -1 || true)"
if [[ -n "$last_ms" ]]; then
  echo "--- итого от первого шага: ${last_ms}ms ---"
fi
