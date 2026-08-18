#!/usr/bin/env bash
# Собирает сквозной след по request-id из journald и gateway.log.
# Использование: bash work/acceptance/trace_rid.sh <rid> [since]
#   since — для journalctl (по умолчанию "10 min ago")
# Формат строки: TRACE <rid> <слой> <шаг…> <мс> <статус…>
# <мс> — первое целое поле после слоя (не in=N, не строк=N).
set -euo pipefail

# Разбор одной строки TRACE: печатает ms<TAB>layer<TAB>step<TAB>status
# Время шага — только голое целое; токены/счётчики остаются именами в статусе.
parse_trace() {
  awk '
    {
      i = 1
      while (i <= NF && $i != "TRACE") i++
      if (i + 2 > NF) next
      layer = $(i + 2)
      start = i + 3
      msidx = 0
      for (j = start; j <= NF; j++) {
        if ($j ~ /^[0-9]+$/) { msidx = j; break }
      }
      if (!msidx) next
      step = ""
      for (j = start; j < msidx; j++)
        step = (step == "" ? $j : step " " $j)
      status = ""
      for (j = msidx + 1; j <= NF; j++)
        status = (status == "" ? $j : status " " $j)
      if (status == "") status = "ok"
      printf "%s\t%s\t%s\t%s\n", $msidx, layer, step, status
    }'
}

if [[ "${1:-}" == "--selftest" ]]; then
  RID="f9859de24c71bdd2"
  got="$(printf '%s\n' \
    "TRACE $RID model TOKENS 0 in=3446 out=12" \
    "TRACE $RID service посчитано базой 13412 сущность=контрагенты строк=1548892 со_значением=1548892" \
    "TRACE $RID gateway received 0 ok" \
    | parse_trace)"
  printf '%s\n' "$got"
  echo "$got" | grep -q $'0\tmodel\tTOKENS\tin=3446 out=12' || { echo "FAIL TOKENS"; exit 1; }
  echo "$got" | grep -q $'13412\tservice\tпосчитано базой\tсущность=контрагенты строк=1548892 со_значением=1548892' \
    || { echo "FAIL count"; exit 1; }
  echo "$got" | grep -Eq 'in=3446ms|строк=1548892ms' && { echo "FAIL glued ms"; exit 1; }
  echo "selftest ok"
  exit 0
fi

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
  parsed="$(printf '%s\n' "$line" | parse_trace)"
  [[ -n "$parsed" ]] || continue
  IFS=$'\t' read -r ms layer step status <<<"$parsed"
  delta=""
  if [[ -n "$prev_ms" && "$ms" =~ ^[0-9]+$ && "$prev_ms" =~ ^[0-9]+$ ]]; then
    d=$((ms - prev_ms))
    delta=" (+${d}ms)"
  fi
  prev_ms="$ms"
  printf '%8s%s  %-10s  %-16s  %s  [%s]\n' "${ms}ms" "$delta" "$layer" "$step" "$status" "$src"
done <"$TMP"

if [[ -n "$prev_ms" ]]; then
  echo "--- итого от первого шага: ${prev_ms}ms ---"
fi
