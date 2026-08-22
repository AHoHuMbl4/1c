#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$ROOT/sandbox.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "нет pidfile"
  exit 0
fi
pid=$(cat "$PIDFILE")
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
fi
rm -f "$PIDFILE"
echo "STOP pid=$pid"
