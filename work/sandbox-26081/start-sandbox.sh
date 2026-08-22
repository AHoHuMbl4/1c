#!/usr/bin/env bash
# Запуск песочницы 26.08.1. Флаг --keep-wal: не переименовывать store.db.wal
# (нужно для WAL-гейта после прерванной сборки IVF).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN="$ROOT/serened"
CONF="$ROOT/sandbox.conf"
PIDFILE="$ROOT/sandbox.pid"
LOG="$ROOT/logs/serened.log"
KEEP_WAL=0
for arg in "$@"; do
  [[ "$arg" == "--keep-wal" ]] && KEEP_WAL=1
done

"$ROOT/extract.sh"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "OK: песочница уже запущена pid=$(cat "$PIDFILE")"
  exit 0
fi

mkdir -p "$ROOT/logs" "$ROOT/data/engine_duckdb" "$ROOT/results"

if [[ "$KEEP_WAL" -eq 0 ]]; then
  if [[ -f "$ROOT/data/engine_duckdb/store.db.wal" ]]; then
    mv "$ROOT/data/engine_duckdb/store.db.wal" \
      "$ROOT/data/engine_duckdb/store.db.wal.bak-$(date +%Y%m%d-%H%M%S)"
  fi
else
  echo "KEEP_WAL: store.db.wal не трогаем ($(stat -c%s "$ROOT/data/engine_duckdb/store.db.wal" 2>/dev/null || echo 0) bytes)"
fi

nohup "$BIN" --flagfile="$CONF" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "START pid=$(cat "$PIDFILE") port=7895 keep_wal=${KEEP_WAL} log=$LOG"

for i in $(seq 1 120); do
  if psql "host=127.0.0.1 port=7895 user=postgres dbname=postgres" -At -c "SELECT 1" &>/dev/null; then
    echo "READY after ${i}s"
    psql "host=127.0.0.1 port=7895 user=postgres dbname=postgres" -At -c "SELECT version();"
    exit 0
  fi
  sleep 1
done
echo "TIMEOUT: песочница не ответила за 120 с — см. $LOG" >&2
exit 1
