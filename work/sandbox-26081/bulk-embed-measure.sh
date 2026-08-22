#!/usr/bin/env bash
# Замер массовой векторной записи на 26.08.1: CTAS с FLOAT[1024] и ai_embed батчами.
# Доки: sql/functions/ai#performance; секрет — TEMPORARY с уникальным именем (§3.93).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$ROOT/results/bulk-embed.tsv}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7895 user=postgres dbname=postgres}"
PSQL=(psql "$DSN" -v ON_ERROR_STOP=1)

# shellcheck disable=SC1091
source /etc/1c-embed.env 2>/dev/null || true
MODEL="${EMBED_MODEL:-Qwen3-Embedding-4B}"
DIM="${EMBED_DIM:-1024}"
PATH_EMB="${EMBED_PATH:-/v1/embeddings}"

# Первый хост|ключ из EMBED_HOSTS
raw="${EMBED_HOSTS:-${EMBED_HOST:-}}"
one=$(printf '%s' "$raw" | cut -d, -f1 | tr -d ' ')
HOST="${one%%|*}"
KEY="${one#*|}"
[[ "$KEY" == "$one" ]] && KEY="${EMBED_API_KEY:-}"
HOST="${HOST%/}"
SEC="f1_emb_$(date +%s)_$$"

mkdir -p "$(dirname "$OUT")"
{
  echo "test|rows|batch|result|wall_sec|rows_per_sec|note"

  for n in 64 10000 100000; do
    tag="ctas_gen_${n}"
    "${PSQL[@]}" -q -c "DROP TABLE IF EXISTS ${tag};" 2>/dev/null || true
    t0=$(date +%s.%N)
    if err=$("${PSQL[@]}" -At -c "
      CREATE TABLE ${tag} AS
      SELECT i::BIGINT AS id,
        list_transform(range(${DIM}), x -> (random()::FLOAT * 2 - 1))::FLOAT[${DIM}] AS emb
      FROM range(${n}) s(i);" 2>&1); then
      t1=$(date +%s.%N)
      wall=$(python3 -c "print(round(float('$t1')-float('$t0'), 3))")
      cnt=$("${PSQL[@]}" -At -c "SELECT count(*) FROM ${tag};")
      echo "ctas_float1024|${n}|-1|OK|${wall}|${cnt}|generated vectors dim=${DIM}"
    else
      t1=$(date +%s.%N)
      wall=$(python3 -c "print(round(float('$t1')-float('$t0'), 3))")
      short=$(printf '%s' "$err" | head -1 | tr '|' '/')
      echo "ctas_float1024|${n}|-1|FAIL|${wall}|0|${short}"
    fi
    "${PSQL[@]}" -q -c "DROP TABLE IF EXISTS ${tag};" 2>/dev/null || true
  done

  # ai_embed: таблица с текстом, батчи 64 и 256
  if [[ -z "$HOST" || -z "$KEY" ]]; then
    echo "ai_embed|0|0|SKIP|0|0|no EMBED_HOST/KEY in /etc/1c-embed.env"
  else
    "${PSQL[@]}" -q -c "CREATE OR REPLACE TEMPORARY SECRET ${SEC} (
      TYPE openai, api_key '${KEY}', base_url '${HOST}', embeddings_path '${PATH_EMB}');" >/dev/null

    for batch in 64 256; do
      tag="f1_embed_${batch}"
      "${PSQL[@]}" -q -c "DROP TABLE IF EXISTS ${tag};" 2>/dev/null || true
      need=$((batch * 2))
      "${PSQL[@]}" -q -c "
        CREATE TABLE ${tag} AS
        SELECT i::BIGINT AS id, 'probe text row ' || i::VARCHAR AS txt
        FROM range(${need}) s(i);"
      t0=$(date +%s.%N)
      if err=$("${PSQL[@]}" -At -c "
        CREATE TABLE ${tag}_out AS
        SELECT id, ai_embed(txt, '${MODEL}', '${SEC}')::FLOAT[${DIM}] AS emb
        FROM ${tag}
        LIMIT ${batch};" 2>&1); then
        t1=$(date +%s.%N)
        wall=$(python3 -c "print(round(float('$t1')-float('$t0'), 3))")
        rps=$(python3 -c "print(round(${batch}/max(float('$t1')-float('$t0'),0.001), 2))")
        echo "ai_embed|${batch}|${batch}|OK|${wall}|${rps}|secret=${SEC} model=${MODEL}"
      else
        t1=$(date +%s.%N)
        wall=$(python3 -c "print(round(float('$t1')-float('$t0'), 3))")
        short=$(printf '%s' "$err" | head -1 | tr '|' '/')
        echo "ai_embed|${batch}|${batch}|FAIL|${wall}|0|${short}"
      fi
      "${PSQL[@]}" -q -c "DROP TABLE IF EXISTS ${tag}; DROP TABLE IF EXISTS ${tag}_out;" 2>/dev/null || true
    done
  fi
} | tee "$OUT"
