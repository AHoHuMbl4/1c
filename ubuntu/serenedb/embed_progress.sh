#!/bin/bash
# Прогресс пересчёта эмбеддингов: посчитано / осталось / скорость / ETA.
#
# 🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ. Во время раунда embed_missing.sh пишет в корпус только
# в конце (transfer), а left()-count по всему search_corpus под нагрузкой не отвечает
# даже за сотни секунд ([замер 23.08 klient-1]). Живой прирост виден в рабочих таблицах
# emb_<база>_<таблица>_part_<N> — см. docs/EMBED_BULK_HOWTO.md §6.3 и §8.
#
# 🔴 ШТАТНОЕ СРЕДСТВО. Лёгкий count без проекции FLOAT[1024] — partial reading /
# projection pushdown (доки SereneDB: data_import_and_export/parquet/overview#partial-reading).
# Та же форма, что left() в embed_missing.sh; замок test_embed_left_count.py.
#
# Использование:
#   embed_progress.sh [таблица] [интервал_сек]
# Окружение:
#   SERENEDB_DSN          — подключение (dbname берётся у движка)
#   EMBED_SCOPE_TOTAL     — весь объём очереди (деловые строки без вектора), если полный
#                           count недоступен; после первого удавшегося left() запоминается
#   EMBED_COUNT_TIMEOUT   — секунд на запрос каталога или суммы part (умолч. 90)
#   EMBED_LEFT_TIMEOUT    — секунд на полный left()-count (умолч. 120)
#   EMBED_STATE_DIR       — каталог снимков для скорости (умолч. /tmp)
set -u

TBL="${1:-search_corpus}"
INTERVAL="${2:-0}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
COUNT_TO="${EMBED_COUNT_TIMEOUT:-90}"
LEFT_TO="${EMBED_LEFT_TIMEOUT:-120}"
STATE_DIR="${EMBED_STATE_DIR:-/tmp}"
PARTS_INCOMPLETE=false
PARTS_INCOMPLETE_REASON=""
PARTS_SUM=0

psql_q() { psql "$DSN" -q -v ON_ERROR_STOP=1 "$@"; }

DBNAME=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DBNAME" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }

TAG="emb_${DBNAME}_${TBL}"
STATE_FILE="${STATE_DIR}/embed_progress_${DBNAME}_${TBL}.json"
SERVICE_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e WHERE e.src_table = ${TBL}.src_table AND e.cls = 'service')"

# Та же лёгкая форма, что left() в embed_missing.sh (ROWS_WHERE с service-фильтром).
left_sql() {
  printf "SELECT count(*) FROM (SELECT src_table FROM %s WHERE emb IS NULL) %s WHERE true AND (%s)" \
    "$TBL" "$TBL" "$SERVICE_WHERE"
}

done_sql() {
  printf "SELECT count(*) FROM (SELECT src_table FROM %s WHERE emb IS NOT NULL) %s WHERE true AND (%s)" \
    "$TBL" "$TBL" "$SERVICE_WHERE"
}

# Запрос с потолком по wall-clock: SereneDB statement_timeout не действует
# ([зamер 23.08 klient-1]: «accepted for compatibility but is not enforced»).
psql_timeout() {
  local sec="$1"; shift
  local out errf
  errf=$(mktemp) || return 1
  out=$(timeout "$sec" psql "$DSN" -tA -v ON_ERROR_STOP=1 -c "$1" 2>"$errf") || {
    rm -f "$errf"
    return 1
  }
  rm -f "$errf"
  printf '%s\n' "$out"
}

load_state() {
  [ -f "$STATE_FILE" ] || return 1
  python3 - "$STATE_FILE" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    for k in ("ts", "parts", "corpus_done", "remaining", "scope_total"):
        print(f"{k}={d.get(k, '')}")
except Exception:
    sys.exit(1)
PY
}

save_state() {
  local ts="$1" parts="$2" corpus_done="$3" remaining="$4" scope="$5"
  python3 - "$STATE_FILE" "$ts" "$parts" "$corpus_done" "$remaining" "$scope" <<'PY'
import json, sys, os
path, ts, parts, corpus_done, remaining, scope = sys.argv[1:7]
d = {}
if os.path.isfile(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        d = {}
d.update({
    "ts": int(ts),
    "parts": int(parts),
    "corpus_done": int(corpus_done) if corpus_done != "" else d.get("corpus_done"),
    "remaining": int(remaining) if remaining != "" else d.get("remaining"),
    "scope_total": int(scope) if scope != "" else d.get("scope_total"),
})
with open(path, "w") as f:
    json.dump(d, f)
PY
}

# Сумма строк в emb_*_part_*: перечень — у каталога движка, сумма — одним запросом.
# Доки: sql/functions/duckdb_table_functions#duckdb_tables
#       sql/functions/utility#query_tabletbl_names-by_name
# Два вызова psql, без цикла по таблицам. Число воркеров подсчёт не ограничивает.
count_parts() {
  PARTS_INCOMPLETE=false
  PARTS_INCOMPLETE_REASON=""
  PARTS_SUM=0
  local like_pat lst n
  like_pat=$(printf '%s' "$TAG" | sed 's/[_%]/\\&/g')
  like_pat="${like_pat}\\_part\\_%"
  lst=$(psql_timeout "$COUNT_TO" \
    "SELECT coalesce('[' || string_agg(quote_literal(table_name), ', ' ORDER BY table_name) || ']', '') FROM duckdb_tables() WHERE table_name LIKE '${like_pat}' ESCAPE '\\' AND database_name = current_database()")
  if [ $? -ne 0 ]; then
    PARTS_INCOMPLETE=true
    PARTS_INCOMPLETE_REASON="каталог duckdb_tables недоступен"
    return 0
  fi
  lst=$(printf '%s' "$lst" | tr -d '\r')
  if [ -z "$lst" ]; then
    return 0
  fi
  n=$(psql_timeout "$COUNT_TO" "SELECT count(*) FROM query_table(${lst}, true)")
  if [ $? -ne 0 ]; then
    PARTS_INCOMPLETE=true
    PARTS_INCOMPLETE_REASON="сумма по part-таблицам недоступна"
    return 0
  fi
  PARTS_SUM="$n"
}

snapshot() {
  local ts parts corpus_done remaining scope scope_env left_ok done_ok
  ts=$(date +%s)
  count_parts
  parts="${PARTS_SUM:-0}"
  corpus_done=""
  remaining=""
  scope=""
  scope_env="${EMBED_SCOPE_TOTAL:-}"

  if done_ok=$(psql_timeout "$LEFT_TO" "$(done_sql)"); then
    corpus_done="$done_ok"
  fi
  if left_ok=$(psql_timeout "$LEFT_TO" "$(left_sql)"); then
    remaining="$left_ok"
    if [ -n "$corpus_done" ]; then
      scope=$((corpus_done + remaining))
    fi
  elif [ -n "$scope_env" ]; then
    scope="$scope_env"
    if [ -n "$corpus_done" ]; then
      remaining=$((scope - corpus_done - parts))
      [ "$remaining" -lt 0 ] && remaining=0
    else
      # Раунд: в корпус ещё не перенесли — очередь убывает только в part-таблицах.
      remaining=$((scope_env - parts))
      [ "$remaining" -lt 0 ] && remaining=0
    fi
  fi

  # Если полный count недоступен, но scope из прошлого снимка или env — оцениваем остаток.
  if [ -z "$remaining" ] && [ -n "$scope_env" ] && [ -n "$corpus_done" ]; then
    remaining=$((scope_env - corpus_done - parts))
    [ "$remaining" -lt 0 ] && remaining=0
    scope="$scope_env"
  fi
  if [ -z "$scope" ] && [ -n "$scope_env" ]; then
    scope="$scope_env"
  fi

  printf '%s|%s|%s|%s|%s|%s|%s\n' "$ts" "$parts" "${corpus_done:-}" "${remaining:-}" "${scope:-}" "${PARTS_INCOMPLETE}" "${PARTS_INCOMPLETE_REASON}"
}

fmt_eta() {
  local sec="$1"
  [ -z "$sec" ] || [ "$sec" -lt 0 ] 2>/dev/null && { echo "?"; return; }
  printf '%dh%02dm' $((sec / 3600)) $(((sec % 3600) / 60))
}

main() {
  local line ts parts corpus_done remaining scope
  local prev_ts prev_parts speed="" eta="" done_total=""
  local round_active=0

  eval "$(load_state 2>/dev/null | sed 's/^/prev_/')" || true

  line=$(snapshot)
  IFS='|' read -r ts parts corpus_done remaining scope PARTS_INCOMPLETE PARTS_INCOMPLETE_REASON <<< "$line"
  local snap1_ts="$ts" snap1_parts="$parts"

  [ "${parts:-0}" -gt 0 ] && round_active=1

  if [ "$INTERVAL" != "0" ] && [ "$INTERVAL" -gt 0 ] 2>/dev/null; then
    sleep "$INTERVAL"
    line=$(snapshot)
    IFS='|' read -r ts parts corpus_done remaining scope PARTS_INCOMPLETE PARTS_INCOMPLETE_REASON <<< "$line"
    dt=$INTERVAL
    speed=$(python3 - "$snap1_parts" "$parts" "$dt" <<'PY'
import sys
p0, p1, dt = (int(x) for x in sys.argv[1:])
print(f"{(p1 - p0) / dt:.2f}")
PY
)
  elif [ -n "${prev_ts:-}" ] && [ -n "${prev_parts:-}" ]; then
    dt=$((ts - prev_ts))
    [ "$dt" -gt 0 ] && speed=$(python3 - "$prev_parts" "$parts" "$dt" <<'PY'
import sys
p0, p1, dt = (int(x) for x in sys.argv[1:])
print(f"{(p1 - p0) / dt:.2f}")
PY
)
  fi

  # scope из state, если новый снимок его не дал
  if [ -z "$scope" ] && [ -n "${prev_scope_total:-}" ]; then
    scope="$prev_scope_total"
  fi
  if [ -z "$remaining" ] && [ -n "$scope" ] && [ -n "$corpus_done" ]; then
    remaining=$((scope - corpus_done - parts))
    [ "$remaining" -lt 0 ] && remaining=0
  elif [ -z "$remaining" ] && [ -n "$scope" ] && [ -n "${prev_corpus_done:-}" ]; then
    remaining=$((scope - prev_corpus_done - parts))
    [ "$remaining" -lt 0 ] && remaining=0
  fi

  done_total=""
  if [ -n "$corpus_done" ]; then
    done_total=$((corpus_done + parts))
  elif [ -n "$scope" ] && [ -n "$remaining" ]; then
    done_total=$((scope - remaining))
  fi

  if [ -n "$speed" ] && [ -n "$remaining" ] && python3 - "$speed" <<'PY' >/dev/null 2>&1
import sys
float(sys.argv[1])
PY
  then
    eta=$(python3 - "$remaining" "$speed" <<'PY'
import sys
rem, spd = float(sys.argv[1]), float(sys.argv[2])
print(int(rem / spd) if spd > 0 else -1)
PY
)
  fi

  save_state "$ts" "$parts" "${corpus_done:-}" "${remaining:-}" "${scope:-}"

  echo "{"
  echo "  \"база\": \"$DBNAME\","
  echo "  \"таблица\": \"$TBL\","
  echo "  \"раунд_активен\": $round_active,"
  echo "  \"в_рабочих_таблицах\": ${parts:-0},"
  if [ -n "$corpus_done" ]; then
    echo "  \"в_корпусе_с_вектором\": $corpus_done,"
  else
    echo "  \"в_корпусе_с_вектором\": null,"
  fi
  if [ -n "$done_total" ]; then
    echo "  \"посчитано_всего\": $done_total,"
  else
    echo "  \"посчитано_всего\": null,"
  fi
  if [ -n "$remaining" ]; then
    echo "  \"осталось\": $remaining,"
  else
    echo "  \"осталось\": null,"
  fi
  if [ -n "$scope" ]; then
    echo "  \"объём_очереди\": $scope,"
  else
    echo "  \"объём_очереди\": null,"
  fi
  if [ -n "$speed" ]; then
    echo "  \"скорость_стр_с\": $speed,"
    echo "  \"интервал_с\": ${INTERVAL:-0},"
    echo "  \"оценка_до_конца\": \"$(fmt_eta "${eta:-}")\","
  else
    echo "  \"скорость_стр_с\": null,"
    echo "  \"интервал_с\": ${INTERVAL:-0},"
    echo "  \"оценка_до_конца\": null,"
  fi
  if [ "$PARTS_INCOMPLETE" = true ]; then
    echo "  \"parts_incomplete\": true,"
    echo "  \"parts_incomplete_reason\": \"${PARTS_INCOMPLETE_REASON}\","
  else
    echo "  \"parts_incomplete\": false,"
    echo "  \"parts_incomplete_reason\": null,"
  fi
  echo "  \"снимок_utc\": \"$(date -u -d "@$ts" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -r "$ts" '+%Y-%m-%dT%H:%M:%SZ')\""
  echo "}"
}

main
