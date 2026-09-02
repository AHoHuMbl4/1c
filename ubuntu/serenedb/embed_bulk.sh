#!/bin/bash
# Массовая векторизация корпуса: своя ATTACH-база на поток, длинный круг, перенос в конце.
#
# Тактовый embed_missing.sh пишет в одну базу — писатель один, сеть внутри оператора
# (docs/EMBED_BULK_HOWTO.md §3: 15,2 строк/с). Здесь каждому потоку — свой файл
# ATTACH ... (ROW_GROUP_SIZE ...): замер 240–354 строк/с, установившийся 168 строк/с.
#
# Доки:
#   sql/statements/attach/duckdb#options — ROW_GROUP_SIZE только при ATTACH
#   sql/statements/set#set-a-global-variable — SET GLOBAL threads / отдельно
#   sql/functions/ai#performance — каждый ai_embed = сетевой запрос
#   cookbook/performance/how_to_tune_workloads#querying-remote-files — 1 HTTP на thread
#
# Использование:
#   embed_bulk.sh <таблица> <выражение-источник> [ключ,через,запятую]
# Окружение (честные умолчания под ОДНУ карту, §4 HOWTO):
#   SERENEDB_DSN, EMBED_HOST, EMBED_PATH, EMBED_MODEL, EMBED_API_KEY(S)
#   EMBED_THREADS=3              # одновременных запросов = threads; карта насыщается на 3
#   EMBED_BATCH_ROWS=16          # предел движка FLOAT[1024]; выше — Vector::SetSize
#   EMBED_POOL_PER_STREAM=50000  # длинный круг на поток (§3.4)
#   EMBED_HTTP_TIMEOUT=600
#   EMBED_WORK_DIR               # каталог файлов wN.db (умолч. /var/lib/serenedb)
#   EMBED_ROW_GROUP_SIZE=122880
#   EMBED_ROUNDS=6 EMBED_RETRY_PAUSE=20 EMBED_CHUNK_RETRIES=8
#   ROWS_WHERE, EMBED_DIM, EMBED_MAXLEN, EMBED_BATCH_CHARS
#   EMBED_PROGRESS_SEC=300        # снимок прироста в рабочих базах (300–600 с)
set -u

TBL="${1:-}"; SRC="${2:-}"; KEY="${3:-}"
if [ -z "$TBL" ] || [ -z "$SRC" ]; then
  echo "использование: embed_bulk.sh <таблица> <выражение-источник> [ключ,через,запятую]" >&2
  exit 2
fi

DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
export SERENEDB_DSN="$DSN"
cd "$(dirname "$0")" || exit 1

N="${EMBED_THREADS:-3}"
ROWS_PER_BATCH="${EMBED_BATCH_ROWS:-16}"
# Жёсткий потолок движка 26.07.3 на FLOAT[1024] в одном операторе (§2 HOWTO).
if [ "$ROWS_PER_BATCH" -gt 16 ]; then
  echo "embed_bulk: EMBED_BATCH_ROWS=$ROWS_PER_BATCH > 16 — обрезаю до 16 (предел движка)" >&2
  ROWS_PER_BATCH=16
fi
POOL="${EMBED_POOL_PER_STREAM:-50000}"
HTTP_TO="${EMBED_HTTP_TIMEOUT:-600}"
WORK_DIR="${EMBED_WORK_DIR:-/var/lib/serenedb}"
RGS="${EMBED_ROW_GROUP_SIZE:-122880}"
ROUNDS="${EMBED_ROUNDS:-6}"
PAUSE="${EMBED_RETRY_PAUSE:-20}"
CHUNK_RETRIES="${EMBED_CHUNK_RETRIES:-8}"
# Интервал ticker прогресса: 300–600 с (v10); умолчание 300.
PROGRESS_SEC="${EMBED_PROGRESS_SEC:-300}"
case "$PROGRESS_SEC" in
  ''|*[!0-9]*) PROGRESS_SEC=300 ;;
esac
if [ "$PROGRESS_SEC" -lt 300 ]; then PROGRESS_SEC=300; fi
if [ "$PROGRESS_SEC" -gt 600 ]; then PROGRESS_SEC=600; fi
MODEL="${EMBED_MODEL:-}"
DIM="${EMBED_DIM:-1024}"
BUDGET="${EMBED_BATCH_CHARS:-12000}"
MAXLEN="${EMBED_MAXLEN:-20000}"
ROWS_WHERE="${ROWS_WHERE:-}"
[ -n "$ROWS_WHERE" ] && ROWS_WHERE="AND ($ROWS_WHERE)"

[ -n "${EMBED_HOST:-}" ] && [ -n "${EMBED_PATH:-}" ] \
  || { echo "не заданы EMBED_HOST/EMBED_PATH" >&2; exit 1; }
[ -n "$MODEL" ] || { echo "не задан EMBED_MODEL" >&2; exit 1; }

DBNAME=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DBNAME" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }
TAG="emb_${DBNAME}_${TBL}"
mkdir -p "$WORK_DIR" || { echo "нет каталога рабочих баз: $WORK_DIR" >&2; exit 1; }

# Ключ строки (как в embed_missing.sh).
if [ -n "$KEY" ]; then
  KCOLS="$KEY"
  ON=""
  ANTI=""
  for c in ${KEY//,/ }; do
    [ -n "$ON" ] && ON="$ON AND "
    ON="${ON}t.$c = p.$c"
    [ -n "$ANTI" ] && ANTI="$ANTI AND "
    ANTI="${ANTI}p.$c = s.$c"
  done
  ORD="$KEY"
else
  KCOLS="rowid AS rid"; ON="t.rowid = p.rid"; ANTI="p.rid = s.rid"; ORD="rid"
fi

# --- секреты (как embed_all: TEMPORARY, имя несёт базу) ---
IFS=',' read -r -a KEYS <<< "${EMBED_API_KEYS:-${EMBED_API_KEY:-${ALIBABA_API_KEYS:-${ALIBABA_API_KEY:-}}}}"
IFS=',' read -r -a HOSTS <<< "${EMBED_HOSTS:-${EMBED_HOST:-}}"
[ ${#HOSTS[@]} -gt 0 ] || HOSTS=("${EMBED_HOST:-}")
umask 077
SEC=$(mktemp); LIST=""
PAIRS=()
for h in "${HOSTS[@]}"; do
  h="$(printf '%s' "$h" | tr -d ' ')"
  [ -z "$h" ] && continue
  case "$h" in
    *"|"*) PAIRS+=("${h%%|*}|${h#*|}") ;;
    *)     for k0 in "${KEYS[@]}"; do PAIRS+=("$h|$(printf '%s' "$k0" | tr -d ' ')"); done ;;
  esac
done
for i in "${!PAIRS[@]}"; do
  h="${PAIRS[$i]%%|*}"; k="${PAIRS[$i]#*|}"
  [ -z "$k" ] || [ -z "$h" ] && continue
  printf "CREATE OR REPLACE TEMPORARY SECRET emb_%s_%s (TYPE openai, api_key '%s', base_url '%s', embeddings_path '%s');\n" \
    "$DBNAME" "$i" "$(printf '%s' "$k" | sed "s/'/''/g")" \
    "$h" "$EMBED_PATH" >> "$SEC"
  LIST="$LIST emb_${DBNAME}_${i}"
done
[ -n "$LIST" ] || { echo "не задан ни один ключ эмбеддера" >&2; rm -f "$SEC"; exit 1; }
psql "$DSN" -q -f "$SEC" >/dev/null 2>&1 || { echo "секреты не созданы" >&2; rm -f "$SEC"; exit 1; }
rm -f "$SEC"
if [ -f "$(dirname "$0")/box_tune.sh" ]; then
  # shellcheck disable=SC1091
  . "$(dirname "$0")/box_tune.sh"
  embed_secrets_base_url_check || { echo "base_url секретов openai не совпал с EMBED_HOST" >&2; exit 1; }
fi
read -r -a SECRETS <<< "${LIST# }"
NSEC=${#SECRETS[@]}
export EMBED_SECRETS="${LIST# }"

cleanup_secrets() {
  local d=""
  for s in $EMBED_SECRETS; do d="$d DROP SECRET IF EXISTS $s;"; done
  psql "$DSN" -q -c "$d" >/dev/null 2>&1
}

# SET GLOBAL — только отдельными операторами и на простое (§5 HOWTO).
# «parameter is global and cannot be set inside a transaction».
apply_globals() {
  psql "$DSN" -q -c "SET GLOBAL threads = $N" >/dev/null 2>&1 \
    || { echo "SET GLOBAL threads не применился (пул занят?)" >&2; return 1; }
  psql "$DSN" -q -c "SET GLOBAL http_timeout = $HTTP_TO" >/dev/null 2>&1 \
    || { echo "SET GLOBAL http_timeout не применился" >&2; return 1; }
  echo "embed_bulk: GLOBAL threads=$N http_timeout=$HTTP_TO" >&2
}

# Перенос из присоединённых рабочих таблиц в целевую — одним запросом на файл.
# Метка постоянная: прерванный прогон докатывается, а не считает заново.
# EMBED_TRANSFER_STRICT=1 — сбой переноса = exit 1 (такт, не «|| true»).
transfer_attached() {
  local w wdb alias _strict=0
  case "${EMBED_TRANSFER_STRICT:-0}" in
    1|true|TRUE|yes|YES) _strict=1 ;;
  esac
  for w in $(seq 0 $((N - 1))); do
    wdb="${WORK_DIR}/${TAG}_w${w}.db"
    [ -f "$wdb" ] || continue
    alias="bulk_w${w}"
    if [ "$_strict" -eq 1 ]; then
      psql "$DSN" -q -v ON_ERROR_STOP=1 <<SQL >/dev/null 2>&1 || return 1
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
UPDATE ${TBL} t SET emb = p.emb
  FROM ${alias}.${TAG}_part p
 WHERE ${ON} AND t.emb IS NULL AND p.emb IS NOT NULL;
DETACH ${alias};
SQL
    else
      psql "$DSN" -q -v ON_ERROR_STOP=1 <<SQL >/dev/null 2>&1 || true
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
UPDATE ${TBL} t SET emb = p.emb
  FROM ${alias}.${TAG}_part p
 WHERE ${ON} AND t.emb IS NULL AND p.emb IS NOT NULL;
DETACH ${alias};
SQL
    fi
  done
  return 0
}

# Сумма строк в рабочих part-таблицах присоединённых баз (живой прирост §8).
count_attached_parts() {
  local w wdb alias sum=0 n
  for w in $(seq 0 $((N - 1))); do
    wdb="${WORK_DIR}/${TAG}_w${w}.db"
    [ -f "$wdb" ] || continue
    alias="bulk_w${w}"
    n=$(psql "$DSN" -tAc "
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
SELECT count(*) FROM ${alias}.${TAG}_part;
DETACH ${alias};
" 2>/dev/null | tr -d '[:space:]')
    # [31.08] psql -tAc с ATTACH/DETACH в одном батче при сбое DETACH ("outstanding
    # work", замер: HOW_NOT_TO многооператорный -c) кладёт в n мусор вида «ATTACH1721»,
    # и set -u ронял ЗАПУСК bulk на арифметике. Счётчик — прибор: мусор игнорируем,
    # живой прирост остаётся у embed_progress.sh.
    case "$n" in ''|*[!0-9]*) ;; *) sum=$((sum + n)) ;; esac
  done
  printf '%s\n' "$sum"
}

# Лёгкий остаток без проекции emb (partial-reading).
left_count() {
  local errf out sql light
  errf=$(mktemp) || return 1
  if [ -z "${ROWS_WHERE}" ]; then
    sql="SELECT count(*) FROM $TBL WHERE emb IS NULL"
  else
    light=$(printf '%s' "$ROWS_WHERE" \
      | grep -oE "${TBL}\\.[A-Za-z_][A-Za-z0-9_]*" \
      | sed "s/^${TBL}\\.//" \
      | sort -u \
      | paste -sd, -)
    [ -n "$light" ] || light="src_table"
    sql="SELECT count(*) FROM (SELECT $light FROM $TBL WHERE emb IS NULL) $TBL WHERE true $ROWS_WHERE"
  fi
  out=$(psql "$DSN" -tA -v ON_ERROR_STOP=1 -c "$sql" 2>"$errf") || {
    echo "не удалось прочитать $TBL: $(tr '\n' ' ' <"$errf" | head -c 400)" >&2
    rm -f "$errf"
    return 1
  }
  rm -f "$errf"
  printf '%s\n' "$out"
}

# Воркер: своя база, пачки по ROWS_PER_BATCH, повтор при сетевом отказе.
run_worker() {
  local w="$1"
  local wdb="${WORK_DIR}/${TAG}_w${w}.db"
  local alias="bulk_w${w}"
  local secret="${SECRETS[$((w % NSEC))]}"
  local errf chunk_list c attempt rc
  errf=$(mktemp)

  # Схема part в присоединённой базе (постоянный файл — докатка).
  psql "$DSN" -q -v ON_ERROR_STOP=1 <<SQL 2>>"$errf" || { cat "$errf" >&2; rm -f "$errf"; return 1; }
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
CREATE TABLE IF NOT EXISTS ${alias}.${TAG}_part AS
  SELECT ${KCOLS}, CAST(NULL AS FLOAT[${DIM}]) AS emb FROM ${TAG}_todo WHERE false;
DETACH ${alias};
SQL

  # Список chunk этого потока из todo (один проход — список уже в основной базе).
  chunk_list=$(psql "$DSN" -tAc \
    "SELECT chunk FROM (SELECT DISTINCT chunk FROM ${TAG}_todo WHERE chunk % ${N} = ${w}) t ORDER BY 1" \
    2>>"$errf") || { cat "$errf" >&2; rm -f "$errf"; return 1; }

  for c in $chunk_list; do
    [ -n "$c" ] || continue
    attempt=0
    while : ; do
      attempt=$((attempt + 1))
      psql "$DSN" -q -v ON_ERROR_STOP=1 <<SQL >>"$errf" 2>&1
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
INSERT INTO ${alias}.${TAG}_part
SELECT * EXCLUDE (txt, chunk),
       ai_embed(txt, '${MODEL}', '${secret}')::FLOAT[${DIM}]
  FROM ${TAG}_todo s
 WHERE s.chunk = ${c}
   AND NOT EXISTS (
     SELECT 1 FROM ${alias}.${TAG}_part p WHERE ${ANTI}
   );
DETACH ${alias};
SQL
      rc=$?
      if [ "$rc" -eq 0 ]; then
        break
      fi
      # Сетевой отказ — «приходи позже»: повтор, не конец работы (§3.6).
      if [ "$attempt" -ge "$CHUNK_RETRIES" ]; then
        echo "worker $w: chunk $c исчерпал $CHUNK_RETRIES попыток" >&2
        break
      fi
      echo "worker $w: chunk $c отказ, пауза ${PAUSE}с (попытка $attempt/$CHUNK_RETRIES)" >&2
      sleep "$PAUSE"
    done
  done
  rm -f "$errf"
  return 0
}

# Монитор прогресса: число в рабочих базах по ходу (§8).
progress_loop() {
  local pids_file="$1"
  local prev=0 cur ts
  while : ; do
    sleep "$PROGRESS_SEC"
    # Все воркеры живы?
    if [ -f "$pids_file" ]; then
      local alive=0 p
      for p in $(cat "$pids_file"); do
        kill -0 "$p" 2>/dev/null && alive=1
      done
      [ "$alive" -eq 0 ] && break
    else
      break
    fi
    cur=$(count_attached_parts)
    ts=$(date -u +%H:%M:%S)
    if [ "$prev" -gt 0 ] && [ "$PROGRESS_SEC" -gt 0 ]; then
      echo "{\"bulk_progress\":\"$ts\",\"в_рабочих\":$cur,\"Δ\":$((cur - prev)),\"за_${PROGRESS_SEC}с\":true}" >&2
    else
      echo "{\"bulk_progress\":\"$ts\",\"в_рабочих\":$cur}" >&2
    fi
    prev=$cur
  done
}

echo "== embed_bulk  $(date -u +%H:%M:%S)  таблица=$TBL threads=$N batch=$ROWS_PER_BATCH pool/stream=$POOL" >&2

# Докатка прерванного: перенос уже посчитанного из рабочих файлов.
transfer_attached || {
  case "${EMBED_TRANSFER_STRICT:-0}" in 1|true|TRUE|yes|YES) exit 1 ;; esac
}

n0=$(left_count) || exit 1
if [ "${n0:-0}" = "0" ]; then
  echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":0,\"осталось\":0,\"режим\":\"bulk\"}"
  cleanup_secrets
  exit 0
fi

trap 'cleanup_secrets' EXIT INT TERM HUP

apply_globals || exit 1

round=0
after="$n0"
while : ; do
  round=$((round + 1))
  T0=$(date +%s)
  before_round=$(left_count) || exit 1
  [ "${before_round:-0}" = "0" ] && break

  # Список работы один раз на круг. Длина круга ≈ N × POOL (§3.3–3.4).
  # chunk режется по строкам И символам (как embed_missing).
  # ПОЛОСЫ ПО ДЛИНЕ (инструкция владельца 30.08, §4 HOWTO-замер): пачка считается
  # по самой длинной строке в ней (8 коротких = 0.72 с; 7 коротких + 1 длинная =
  # 17.6 с) — пул обязан группировать близкие длины, порядок ключей внутри полосы
  # только детерминирует перестановку.
  ROUND_CAP=$((N * POOL))
  psql "$DSN" -q -v ON_ERROR_STOP=1 -c "
CREATE OR REPLACE TABLE ${TAG}_todo AS
  WITH s AS (SELECT $KCOLS, $SRC AS txt FROM $TBL WHERE emb IS NULL $ROWS_WHERE),
       ok AS (SELECT * FROM s WHERE txt IS NOT NULL AND length(txt) BETWEEN 1 AND $MAXLEN),
       w AS (SELECT *, row_number() OVER (ORDER BY length(txt), $ORD) - 1 AS rn,
                    sum(length(txt)) OVER (ORDER BY length(txt), $ORD ROWS BETWEEN UNBOUNDED PRECEDING
                                                              AND 1 PRECEDING) AS cum
             FROM ok),
       capped AS (SELECT * FROM w WHERE rn < $ROUND_CAP)
  SELECT * EXCLUDE (rn, cum),
         (rn / $ROWS_PER_BATCH) + (coalesce(cum, 0) / $BUDGET) AS chunk
  FROM capped;
" || exit 1

  todo_n=$(psql "$DSN" -tAc "SELECT count(*) FROM ${TAG}_todo" | tr -d '[:space:]')
  echo "  круг $round: в todo $todo_n строк (cap $ROUND_CAP), потоков $N" >&2

  PIDS_FILE=$(mktemp)
  pids=()
  for w in $(seq 0 $((N - 1))); do
    run_worker "$w" &
    pids+=($!)
  done
  printf '%s\n' "${pids[@]}" > "$PIDS_FILE"

  progress_loop "$PIDS_FILE" &
  mon=$!

  bad=0
  for p in "${pids[@]}"; do wait "$p" || bad=$((bad + 1)); done
  rm -f "$PIDS_FILE"
  wait "$mon" 2>/dev/null || true

  parts_n=$(count_attached_parts)
  echo "  круг $round: в рабочих базах $parts_n; перенос в $TBL" >&2
  transfer_attached || {
    case "${EMBED_TRANSFER_STRICT:-0}" in 1|true|TRUE|yes|YES) exit 1 ;; esac
  }

  # После переноса рабочие part можно очистить (файлы баз остаются — схема IF NOT EXISTS).
  for w in $(seq 0 $((N - 1))); do
    wdb="${WORK_DIR}/${TAG}_w${w}.db"
    [ -f "$wdb" ] || continue
    alias="bulk_w${w}"
    psql "$DSN" -q <<SQL >/dev/null 2>&1 || true
ATTACH OR REPLACE '${wdb}' AS ${alias} (ROW_GROUP_SIZE ${RGS});
DELETE FROM ${alias}.${TAG}_part;
DETACH ${alias};
SQL
  done
  psql "$DSN" -q -c "DROP TABLE IF EXISTS ${TAG}_todo" >/dev/null 2>&1

  after=$(left_count) || exit 1
  moved=$(( ${before_round:-0} - ${after:-0} ))
  secs=$(( $(date +%s) - T0 ))
  echo "  круг $round: перенесено $moved за ${secs}с, осталось $after, воркеров_с_ошибкой=$bad" >&2

  if [ "${after:-0}" = "0" ]; then break; fi
  if [ "$moved" -le 0 ]; then
    echo "  круг $round: не сдвинулось — повтор бессмысленен" >&2
    break
  fi
  if [ "$round" -ge "$ROUNDS" ]; then
    echo "  предел кругов ($ROUNDS), осталось $after" >&2
    break
  fi
  sleep "$PAUSE"
done

echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":$n0,\"осталось\":${after:-?},\"потоков\":$N,\"режим\":\"bulk\",\"кругов\":$round}"
[ -z "$after" ] && exit 1
[ "$after" -eq 0 ] && exit 0
echo "bulk: осталось $after без вектора (было $n0)" >&2
exit 1
