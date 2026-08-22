#!/usr/bin/env bash
# Точный kNN vs IVF на f1_okna (1.23M). Тайминг — bash date +%s%3N (3 прогона, медиана).
set -euo pipefail
DSN="${1:?dsn}"
OUT="${2:?out}"
PSQL=(psql "$DSN" -v ON_ERROR_STOP=1)

QK=$("${PSQL[@]}" -At -c "
  SELECT src_table || '|' || row_key
  FROM search_corpus WHERE emb IS NOT NULL
  ORDER BY abs(sqrt(list_sum(list_transform(emb, x -> x*x))) - 1) LIMIT 1;")

"${PSQL[@]}" -q -c "DROP TABLE IF EXISTS f1_okna_q;"
if ! "${PSQL[@]}" -At -c "SELECT 1 FROM duckdb_tables() WHERE table_name='f1_okna' LIMIT 1;" | grep -q 1; then
  echo "okna-knn: recreating f1_okna (1.23M)…" >&2
  "${PSQL[@]}" -q -c "
    CREATE TABLE f1_okna AS SELECT i::VARCHAR AS k,
      list_transform(range(1024), x -> (random()::FLOAT * 2 - 1))::FLOAT[1024] AS emb
      FROM range(1230000) s(i);"
fi
"${PSQL[@]}" -q -c "
  CREATE TABLE f1_okna_q AS
  SELECT emb AS q FROM search_corpus
  WHERE src_table || '|' || row_key = '${QK}';"

time_median() {
  local mode="$1" nprobe="${2:-0}"
  local -a samples=()
  local i t0 t1
  for i in 1 2 3; do
    t0=$(date +%s%3N)
    if [[ "$mode" == "exact" ]]; then
      psql "$DSN" -q -v ON_ERROR_STOP=1 -c "
        SELECT count(*) FROM (
          SELECT k FROM f1_okna, f1_okna_q ORDER BY emb <#> f1_okna_q.q LIMIT 10
        ) x;" >/dev/null
    else
      psql "$DSN" -q -v ON_ERROR_STOP=1 -c "
        SET sdb_nprobe = ${nprobe};
        SELECT count(*) FROM (
          SELECT k FROM f1_okna_idx, f1_okna_q ORDER BY emb <#> f1_okna_q.q LIMIT 10
        ) x;" >/dev/null
    fi
    t1=$(date +%s%3N)
    samples+=($((t1 - t0)))
  done
  printf '%s\n' "${samples[@]}" | sort -n | awk 'NR==2 {print $1}'
}

"${PSQL[@]}" -q -c "DROP INDEX IF EXISTS f1_okna_idx;"
exact_med=$(time_median exact)
"${PSQL[@]}" -q -c "CREATE INDEX f1_okna_idx ON f1_okna USING inverted(k, emb ivf (metric = 'ip'));"

{
  echo "mode|nprobe|median_ms|runs|rows|query_key|note"
  echo "exact_none|0|${exact_med}|3|1230000|${QK}|DROP INDEX; brute ORDER BY <#> LIMIT 10"
  for nprobe in 4 16 32; do
    med=$(time_median ivf "$nprobe")
    echo "ivf_ip|${nprobe}|${med}|3|1230000|${QK}|f1_okna_idx sdb_nprobe=${nprobe}"
  done
} | tee "$OUT"
