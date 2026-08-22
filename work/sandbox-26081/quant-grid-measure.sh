#!/usr/bin/env bash
# Сетка sdb_nprobe × sdb_rerank_factor на f1_corpus_sq8_idx (доки: maintenance#session-settings)
set -euo pipefail
DSN="${1:?dsn}"
OUT="${2:?out}"
QK=$(psql "$DSN" -At -c "SELECT k FROM f1_corpus_vec LIMIT 1;")
{
  echo "nprobe|rerank_factor|median_ms|runs"
  for nprobe in 4 8 16 32; do
    for rf in 1 4 8; do
      med=$(psql "$DSN" -v ON_ERROR_STOP=1 -At <<SQL 2>/dev/null || echo ERR
SET sdb_nprobe = ${nprobe};
SET sdb_rerank_factor = ${rf};
WITH runs AS (
  SELECT extract(milliseconds FROM (clock_timestamp() - t0)) AS ms
  FROM generate_series(1, 5) g,
  LATERAL (
    SELECT clock_timestamp() AS t0
  ) c,
  LATERAL (
    SELECT count(*) FROM (
      SELECT k FROM f1_corpus_sq8_idx
      ORDER BY emb <#> (SELECT emb FROM f1_corpus_vec WHERE k = '${QK}')
      LIMIT 10
    ) x
  ) q
)
SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY ms), 2) FROM runs;
SQL
)
      echo "${nprobe}|${rf}|${med}|5"
    done
  done
} | tee "$OUT"
