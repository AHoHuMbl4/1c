#!/usr/bin/env bash
# Замер одной операции: wall time + peak RSS (kb) процессов песочницы.
# Usage: measure-cmd.sh <tag> <timeout_sec> <sql-or-command...>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TAG="${1:?tag}"; shift
TIMEOUT="${1:?timeout}"; shift

peak_rss_kb() {
  local best=0 p rss
  while read -r p; do
    [[ -z "$p" ]] && continue
    rss=$(awk '/VmRSS/{print $2; exit}' "/proc/$p/status" 2>/dev/null || echo 0)
    [[ "$rss" -gt "$best" ]] && best=$rss
  done < <(pgrep -f "flagfile=$ROOT/sandbox.conf" 2>/dev/null || true)
  echo "$best"
}

peak=0
t0=$(date +%s)
(
  if [[ $# -eq 1 && -f "$1" ]]; then
    psql "host=127.0.0.1 port=7895 user=postgres dbname=postgres" -v ON_ERROR_STOP=1 -f "$1"
  elif [[ $# -eq 1 ]]; then
    psql "host=127.0.0.1 port=7895 user=postgres dbname=postgres" -v ON_ERROR_STOP=1 -c "$1"
  else
    "$@"
  fi
) &
wpid=$!

while kill -0 "$wpid" 2>/dev/null; do
  r=$(peak_rss_kb)
  [[ "$r" -gt "$peak" ]] && peak=$r
  if [[ "$peak" -gt $((40 * 1024 * 1024)) ]]; then
    echo "${TAG}|CEILING_RSS_kb=${peak}|kill" >&2
    kill -9 "$wpid" 2>/dev/null || true
    pkill -9 -f "flagfile=$ROOT/sandbox.conf" 2>/dev/null || true
    echo "${TAG}|wall_sec=$(($(date +%s)-t0))|peak_rss_kb=${peak}|rc=CEILING"
    exit 3
  fi
  sleep 1
  if [[ $(($(date +%s)-t0)) -ge $TIMEOUT ]]; then
    kill -9 "$wpid" 2>/dev/null || true
    echo "${TAG}|TIMEOUT ${TIMEOUT}s peak_rss_kb=${peak}" >&2
    echo "${TAG}|wall_sec=${TIMEOUT}|peak_rss_kb=${peak}|rc=TIMEOUT"
    exit 124
  fi
done
wait "$wpid" 2>/dev/null; rc=$?
t1=$(date +%s)
r=$(peak_rss_kb); [[ "$r" -gt "$peak" ]] && peak=$r
echo "${TAG}|wall_sec=$((t1-t0))|peak_rss_kb=${peak}|rc=${rc}"
