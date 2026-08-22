#!/usr/bin/env bash
# Сетка sdb_nprobe × латентность + recall@10 (1 запрос).
# Доки: maintenance#session-settings
set -euo pipefail
DSN="${1:?dsn}"
OUT="${2:?out}"
QK=$(psql "$DSN" -At -c "SELECT k FROM f1_corpus_vec LIMIT 1;")

time_median_ms() {
  local idx="$1" nprobe="$2" rf="$3"
  local -a samples=()
  local i t0 t1 ms
  for i in 1 2 3 4 5; do
    t0=$(date +%s%3N)
    psql "$DSN" -q -v ON_ERROR_STOP=1 -c "
      SET sdb_nprobe = ${nprobe};
      SET sdb_rerank_factor = ${rf};
      SELECT count(*) FROM (
        SELECT t.k FROM f1_corpus_vec v, ${idx} t
        WHERE v.k = '${QK}'
        ORDER BY t.emb <#> v.emb
        LIMIT 10
      ) x;" >/dev/null
    t1=$(date +%s%3N)
    ms=$((t1 - t0))
    samples+=("$ms")
  done
  printf '%s\n' "${samples[@]}" | sort -n | awk 'NR==3 {print $1}'
}

recall_one() {
  local idx="$1" nprobe="$2" rf="$3"
  psql "$DSN" -q -v ON_ERROR_STOP=1 -At <<SQL
SET sdb_nprobe = ${nprobe};
SET sdb_rerank_factor = ${rf};
WITH q AS (SELECT emb FROM f1_corpus_vec WHERE k = '${QK}'),
exact10 AS (
  SELECT k FROM (
    SELECT v2.k, row_number() OVER (ORDER BY v2.emb <#> q.emb) rn
    FROM f1_corpus_exact v2, q
  ) s WHERE rn <= 10
),
approx10 AS (SELECT k FROM ${idx} t, q ORDER BY t.emb <#> q.emb LIMIT 10)
SELECT round(count(DISTINCT a.k) FILTER (WHERE a.k IN (SELECT k FROM exact10))::FLOAT / 10, 4)
FROM approx10 a;
SQL
}

{
  echo "index|nprobe|rerank_factor|recall@10|median_ms|runs|query_k"
  for idx in f1_corpus_ip_idx f1_corpus_sq8_idx f1_corpus_rabitq_idx; do
    base="${idx#f1_corpus_}"
    base="${base%_idx}"
    rf=4
    [[ "$base" == "ip" ]] && rf=1
    for nprobe in 4 16 32; do
      med=$(time_median_ms "$idx" "$nprobe" "$rf")
      rc=$(recall_one "$idx" "$nprobe" "$rf")
      echo "${base}|${nprobe}|${rf}|${rc}|${med}|5|${QK}"
    done
  done
} | tee "$OUT"
