#!/bin/bash
# Досчитать векторы тем строкам, у которых их нет — штатной функцией движка `ai_embed`.
#
# Э1б: обвязка (todo, transfer, drop, ai_embed, итоги) — один psql -f embed_missing.sql
# на раунд; tick-guard остаётся снаружи (оценка остатка до счёта).
# Пачечная схема ai_embed не меняется (предел 16–32 строк FLOAT[1024] на 26.07.3).
#
# Использование: embed_missing.sh <таблица> <выражение-источник> [игнор-воркеров] [ключ,через,запятую]
set -u
TBL="$1"; SRC="$2"; N="${3:-1}"; KEY="${4:-}"
ROWS_WHERE="${ROWS_WHERE:-}"
[ -n "$ROWS_WHERE" ] && ROWS_WHERE="AND ($ROWS_WHERE)"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
MODEL="${EMBED_MODEL:-text-embedding-v4}"
read -r -a SECRETS <<< "${EMBED_SECRETS:-${EMBED_SECRET:-qwen}}"
SEC0="${SECRETS[0]}"
DIM="${EMBED_DIM:-1024}"
if [ "${N:-1}" -gt 1 ] 2>/dev/null; then
  echo "embed_missing: внешние WORKERS=$N игнорируются (Э1: одна сессия psql; параллель = SET threads)" >&2
fi

DBNAME="${EMBED_DBNAME:-}"
if [ -z "$DBNAME" ]; then
  DBNAME=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
fi
[ -n "$DBNAME" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }
# EMBED_TAG: суффикс тега вместо «база_таблица». Второй параллельный досчёт
# (другой секрет → другой GPU-сервер) обязан иметь свой тег, чтобы todo/part
# -таблицы и уборка двух сеансов не пересекались.
TAG="emb_${EMBED_TAG:-${DBNAME}_${TBL}}"
TAG_OLD="emb_${TBL}"
TAG_TODO="${TAG}_todo"
TAG_PART0="${TAG}_part_0"

ROWS_PER_BATCH=${EMBED_BATCH_ROWS:-16}
BUDGET=${EMBED_BATCH_CHARS:-12000}
MAXLEN=${EMBED_MAXLEN:-20000}
# Массовый нативный раунд (26.08.1): один оператор ai_embed на :chunks_round
# чанков (строк/оператор = chunks_round × ROWS_PER_BATCH).
CHUNKS_ROUND=${EMBED_CHUNKS_PER_ROUND:-400}

if [ -n "$KEY" ]; then
  KCOLS="$KEY"
  ON=""
  for c in ${KEY//,/ }; do
    [ -n "$ON" ] && ON="$ON AND "
    ON="${ON}t.$c = p.$c"
  done
  ORD="$KEY"
else
  KCOLS="rowid AS rid"; ON="t.rowid = p.rid"; ORD="rid"
fi

USE_ROWS_FILTER=0
LIGHT_COLS=""
if [ -n "$ROWS_WHERE" ]; then
  USE_ROWS_FILTER=1
  LIGHT_COLS=$(printf '%s' "$ROWS_WHERE" \
    | grep -oE "${TBL}\\.[A-Za-z_][A-Za-z0-9_]*" \
    | sed "s/^${TBL}\\.//" \
    | sort -u \
    | paste -sd, -)
  [ -n "$LIGHT_COLS" ] || LIGHT_COLS="src_table"
fi

THR_SQL="--"
THR_OLD=""
restore_threads() {
  [ -n "$THR_OLD" ] && psql "$DSN" -q -c "SET threads = $THR_OLD" >/dev/null 2>&1
  THR_OLD=""
}
if [ -n "${EMBED_THREADS:-}" ]; then
  _thr_now=$(psql "$DSN" -tA -c "SHOW threads" 2>/dev/null | tr -cd '0-9')
  if [ -n "$_thr_now" ] && [ "$_thr_now" -lt "$EMBED_THREADS" ]; then
    THR_SQL="SET threads = $EMBED_THREADS;"
    THR_OLD="$_thr_now"
    echo "  потоки движка на время досчёта: $_thr_now -> $EMBED_THREADS" >&2
  fi
fi

run_sql_round() {
  local errf out rc n_err n_429 first_err
  errf=$(mktemp) || return 1
  out=$(psql "$DSN" -tA -v ON_ERROR_STOP=1 \
    -v "tbl=$TBL" \
    -v "src=$SRC" \
    -v "tag=$TAG" \
    -v "tag_old=$TAG_OLD" \
    -v "tag_todo=$TAG_TODO" \
    -v "tag_part0=$TAG_PART0" \
    -v "kcols=$KCOLS" \
    -v "on_clause=$ON" \
    -v "ord=$ORD" \
    -v "rows_per_batch=$ROWS_PER_BATCH" \
    -v "chunks_round=$CHUNKS_ROUND" \
    -v "budget=$BUDGET" \
    -v "maxlen=$MAXLEN" \
    -v "model=$MODEL" \
    -v "sec0=$SEC0" \
    -v "dim=$DIM" \
    -v "thr_sql=$THR_SQL" \
    -v "rows_where=$ROWS_WHERE" \
    -v "light_cols=$LIGHT_COLS" \
    -v "use_rows_filter=$USE_ROWS_FILTER" \
    -f "$(dirname "$0")/embed_missing.sql" 2>"$errf") || {
    echo "embed_missing.sql: $(tr '\n' ' ' <"$errf" | head -c 400)" >&2
    rm -f "$errf"
    restore_threads
    return 1
  }
  rc=$?
  restore_threads
  n_err=$(grep -cE '^(ERROR|FATAL|ОШИБКА)' "$errf" 2>/dev/null || true)
  n_429=$(grep -c 'HTTP 429' "$errf" 2>/dev/null || true)
  if [ "${n_err:-0}" -gt 0 ] || [ "$rc" -ne 0 ]; then
    first_err=$(grep -m1 -E '^(ERROR|FATAL|ОШИБКА)' "$errf" || true)
    echo "досчёт: отказов пачек $n_err (из них по перегрузке $n_429). Первая: ${first_err:0:160}" >&2
    bad=1
  fi
  rm -f "$errf"
  printf '%s\n' "$out" | tail -1
}

T0=$(date +%s)
# shellcheck disable=SC1091
. "$(dirname "$0")/embed_tick_guard.sh"
embed_tick_guard_check "$TBL" "$TAG"
_guard_rc=$?
if [ "$_guard_rc" -eq 2 ]; then
  exit 2
elif [ "$_guard_rc" -ne 0 ]; then
  exit "$_guard_rc"
fi

impossible=0; bad=0
ROUNDS=${EMBED_ROUNDS:-1}
PAUSE=${EMBED_RETRY_PAUSE:-0}
round=0
n=""
after=""

while : ; do
  round=$((round + 1))
  T0=$(date +%s)
  result=$(run_sql_round) || exit 1
  [ -n "$result" ] || { echo "не удалось прочитать итог по $TBL: пустой ответ" >&2; exit 1; }

  n=$(printf '%s' "$result" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('было_без_вектора',''))" 2>/dev/null)
  after=$(printf '%s' "$result" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('осталось',''))" 2>/dev/null)
  impossible=$(printf '%s' "$result" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('вектор_невозможен',0))" 2>/dev/null)
  tot=$(printf '%s' "$result" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('session_rows',0))" 2>/dev/null)

  secs=$(( $(date +%s) - T0 ))
  echo "  сессия: ${tot:-0} строк за ${secs}с (секрет $SEC0)" >&2

  [ -z "$n" ] && { echo "не удалось прочитать $TBL: пустой ответ" >&2; exit 1; }
  if [ "$n" = "0" ] && [ "${after:-0}" = "0" ]; then
    echo "$result"
    exit 0
  fi

  before_round="$n"
  if [ "${after:-0}" = "0" ]; then break; fi
  moved=$(( ${before_round:-0} - ${after:-0} ))
  if [ "$moved" -le 0 ]; then
    echo "  проход $round: не сдвинулось ни строки — повторять нечем" >&2; break
  fi
  if [ "$round" -ge "$ROUNDS" ]; then
    echo "  осталось $after — доберёт следующий такт (EMBED_ROUNDS=$ROUNDS)" >&2; break
  fi
  echo "  проход $round: посчитано $moved, осталось $after; пауза ${PAUSE}с" >&2
  sleep "$PAUSE"
done

echo "$result"

[ -z "$after" ] && { echo "не удалось прочитать итог по $TBL: пустой ответ" >&2; exit 1; }
[ "$after" -le "$impossible" ] && exit 0
[ "$after" -ge "$n" ] && { echo "досчёт не сдвинулся: было $n, осталось $after" >&2; exit 1; }
exit 0
