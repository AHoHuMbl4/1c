#!/usr/bin/env bash
# Монитор RSS процесса serened песочницы. Выход: peak_rss_kb duration_sec
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$ROOT/sandbox.pid"
DURATION="${1:-120}"
INTERVAL="${2:-1}"
CEILING_MB="${3:-40960}"  # 40 GiB потолок

if [[ ! -f "$PIDFILE" ]]; then
  echo "ERROR: нет pidfile" >&2
  exit 1
fi
spid=$(cat "$PIDFILE")
peak=0
elapsed=0
while [[ $elapsed -lt $DURATION ]]; do
  # pgrep возвращает несколько — берём наибольший RSS (PLAN_VECTOR_CHECKS §0).
  best=0
  bestpid=0
  while read -r p; do
    [[ -z "$p" ]] && continue
    rss=$(awk '/VmRSS/{print $2; exit}' "/proc/$p/status" 2>/dev/null || echo 0)
    if [[ "$rss" -gt "$best" ]]; then
      best=$rss
      bestpid=$p
    fi
  done < <(pgrep -f "flagfile=$ROOT/sandbox.conf" 2>/dev/null || true)
  if [[ "$best" -gt "$peak" ]]; then peak=$best; fi
  if [[ "$best" -gt $((CEILING_MB * 1024)) ]]; then
    echo "CEILING hit: rss_kb=$best pid=$bestpid — kill -9" >&2
    kill -9 "$bestpid" 2>/dev/null || true
    echo "$peak $elapsed CEILING"
    exit 3
  fi
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done
echo "$peak $elapsed OK"
