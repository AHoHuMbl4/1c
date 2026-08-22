#!/usr/bin/env bash
# recall@10: exact = f1_corpus_vec (нет inverted-индекса на exact-пути),
# approx = f1_corpus_*_idx. Доки: maintenance#session-settings (sdb_nprobe/sdb_rerank_factor).
set -euo pipefail
DSN="${1:?dsn}"
OUT="${2:?out}"
psql "$DSN" -v ON_ERROR_STOP=1 -At -f - <<'SQL' >"$OUT.tmp"
DROP TABLE IF EXISTS f1_queries, f1_exact10;
CREATE TEMP TABLE f1_queries AS
  SELECT row_number() OVER () AS qid, emb AS q
  FROM f1_corpus_vec
  ORDER BY random()
  LIMIT 50;

CREATE TEMP TABLE f1_exact10 AS
  SELECT q.qid, v.k
  FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_vec v2
    ORDER BY v2.emb <#> q.q
    LIMIT 10
  ) v;

-- ip none
WITH approx10 AS (
  SELECT q.qid, t.k
  FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_ip_idx t2
    ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'ip_none|' || round(avg(hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(*) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS hit
  FROM approx10 a GROUP BY a.qid
) s;

-- sq8
WITH approx10 AS (
  SELECT q.qid, t.k
  FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_sq8_idx t2
    ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'sq8|' || round(avg(hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(*) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS hit
  FROM approx10 a GROUP BY a.qid
) s;

-- rabitq
WITH approx10 AS (
  SELECT q.qid, t.k
  FROM f1_queries q
  CROSS JOIN LATERAL (
    SELECT k FROM f1_corpus_rabitq_idx t2
    ORDER BY t2.emb <#> q.q LIMIT 10
  ) t
)
SELECT 'rabitq|' || round(avg(hit)::DOUBLE, 4)
FROM (
  SELECT a.qid,
    count(*) FILTER (
      WHERE a.k IN (SELECT e.k FROM f1_exact10 e WHERE e.qid = a.qid)
    )::FLOAT / 10 AS hit
  FROM approx10 a GROUP BY a.qid
) s;
SQL

{
  echo "metric|recall@10_mean|queries|exact_source|approx_index"
  echo "ip_none|$(grep '^ip_none|' "$OUT.tmp" | cut -d'|' -f2)|50|f1_corpus_vec ORDER BY <#>|f1_corpus_ip_idx"
  echo "sq8|$(grep '^sq8|' "$OUT.tmp" | cut -d'|' -f2)|50|f1_corpus_vec ORDER BY <#>|f1_corpus_sq8_idx"
  echo "rabitq|$(grep '^rabitq|' "$OUT.tmp" | cut -d'|' -f2)|50|f1_corpus_vec ORDER BY <#>|f1_corpus_rabitq_idx"
} | tee "$OUT"
rm -f "$OUT.tmp"
