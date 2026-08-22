#!/usr/bin/env bash
# recall@10 vs точный перебор (row_number по всем парам q×corpus).
# Доки: vector-search; exact — таблица f1_corpus_exact без индекса (штатного force-exact нет).
set -euo pipefail
DSN="${1:?dsn}"
OUT="${2:?out}"
PSQL=(psql "$DSN" -v ON_ERROR_STOP=1)

"${PSQL[@]}" -q -c "DROP TABLE IF EXISTS f1_corpus_exact;"
"${PSQL[@]}" -q -c "CREATE TABLE f1_corpus_exact AS SELECT k, emb FROM f1_corpus_vec;"

"${PSQL[@]}" -At -f - >"$OUT.tmp" <<'SQL'
CREATE TEMP TABLE f1_queries AS
  SELECT row_number() OVER () AS qid, emb AS q
  FROM f1_corpus_exact ORDER BY random() LIMIT 50;

CREATE TEMP TABLE f1_exact10 AS
  SELECT qid, k FROM (
    SELECT q.qid, v2.k,
      row_number() OVER (PARTITION BY q.qid ORDER BY v2.emb <#> q.q) AS rn
    FROM f1_queries q
    CROSS JOIN f1_corpus_exact v2
  ) ranked
  WHERE rn <= 10;

WITH approx10 AS (
  SELECT q.qid, t.k FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_ip_idx t2 ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'ip_none|8|' || round(avg(recall_hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(DISTINCT a.k) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS recall_hit
  FROM approx10 a GROUP BY a.qid
) s;

WITH approx10 AS (
  SELECT q.qid, t.k FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_sq8_idx t2 ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'sq8|8|' || round(avg(recall_hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(DISTINCT a.k) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS recall_hit
  FROM approx10 a GROUP BY a.qid
) s;

WITH approx10 AS (
  SELECT q.qid, t.k FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_rabitq_idx t2 ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'rabitq|8|' || round(avg(recall_hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(DISTINCT a.k) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS recall_hit
  FROM approx10 a GROUP BY a.qid
) s;
SQL

{
  echo "metric|nprobe|recall@10_mean|queries|exact_source|approx_index"
  ip=$(grep '^ip_none|' "$OUT.tmp" | cut -d'|' -f3)
  sq=$(grep '^sq8|' "$OUT.tmp" | cut -d'|' -f3)
  rb=$(grep '^rabitq|' "$OUT.tmp" | cut -d'|' -f3)
  echo "ip_none|8|${ip}|50|f1_corpus_exact brute row_number|f1_corpus_ip_idx"
  echo "sq8|8|${sq}|50|f1_corpus_exact brute row_number|f1_corpus_sq8_idx"
  echo "rabitq|8|${rb}|50|f1_corpus_exact brute row_number|f1_corpus_rabitq_idx"
} | tee "$OUT"
rm -f "$OUT.tmp"
