#!/usr/bin/env python3
"""Одноразовый патч corpus_build.sql: чанкованный p_doc. Идемпотентен."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "corpus_build.sql"


def patch(text: str) -> str:
    if "PREPARE p_doc_chunk AS" in text:
        return text

    section_5bis = '''
-- ============ 5-бис. ЧАНКОВАНИЕ p_doc (крупные сущности) ============
-- [замер K1-m 18.08, klient-1] `EXECUTE p_doc` на accumulationregister_себестоимостьтоваров
-- (638 330 строк, 100 колонок) — in-memory working set >9,7 GiB (unspillable); та же
-- логика порциями по 50 000 строк — 638 330/638 330, RSS ~2 GiB на порцию.
--
-- 🔴 ПОРОГ И РАЗМЕР ПОРЦИИ — ВЫВЕДЕНЫ, НЕ ПОДОБРАНЫ:
--   ws_bytes_per_row = 2 GiB / 50 000  (замер рабочего набора на строку этой формы);
--   chunk_budget     = memory_limit × 0,25  (50k строк ≈ 21 % лимита 9,7 GiB);
--   chunk_rows       = floor(chunk_budget / ws_bytes_per_row);
--   порог чанкования = chunk_rows: больше — порции, иначе — прежний `p_doc` целиком.
-- На другой коробке пересчитается от `SHOW memory_limit` (Configuration › Pragmas › Memory Limit).
CREATE OR REPLACE TABLE tmp3_pdoc_cfg AS
WITH ml AS (SELECT current_setting('memory_limit') AS s),
     mem AS (
       SELECT CASE WHEN s LIKE '%GiB' THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 3)
                   WHEN s LIKE '%GB'  THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1000::BIGINT, 3)
                   WHEN upper(s) LIKE '%MIB' OR upper(s) LIKE '%MB'
                        THEN try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) * power(1024::BIGINT, 2)
                   ELSE try_cast(regexp_extract(s, '^([0-9.]+)', 1) AS DOUBLE) END AS mem_bytes
       FROM ml)
SELECT 2147483648.0 / 50000.0 AS ws_bytes_per_row,
       0.25 AS mem_fraction,
       greatest(1000::BIGINT,
                floor((SELECT mem_bytes FROM mem) * 0.25
                      / (2147483648.0 / 50000.0))::BIGINT) AS chunk_rows
FROM mem;

CREATE TABLE IF NOT EXISTS tmp3_pdoc_progress (tbl VARCHAR PRIMARY KEY, rid_hi BIGINT, nrows BIGINT);
CREATE TABLE IF NOT EXISTS tmp3_pdoc_stage (
  src_table VARCHAR, rk VARCHAR, doc VARCHAR, refs VARCHAR,
  nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));

CREATE OR REPLACE TABLE tmp3_resume_pdoc AS
SELECT coalesce((SELECT max(ts) FROM tmp3_run), TIMESTAMP '1970-01-01') < now() - INTERVAL '6 hours'
       AND (SELECT count(*) FROM tmp3_pdoc_progress) > 0 AS on_;

CREATE OR REPLACE TABLE tmp3_entity_rows AS
SELECT b.tbl, (SELECT count(*)::BIGINT FROM query_table(b.tbl)) AS nrows
FROM tmp3_build b;

CREATE OR REPLACE TABLE tmp3_pdoc_chunks AS
SELECT e.tbl, gs AS lo, least(gs + cfg.chunk_rows - 1, e.nrows) AS hi, e.nrows
FROM tmp3_entity_rows e
CROSS JOIN tmp3_pdoc_cfg cfg
CROSS JOIN LATERAL (SELECT unnest(generate_series(1::BIGINT, e.nrows, cfg.chunk_rows)) AS gs) g
WHERE e.nrows > cfg.chunk_rows;

DELETE FROM search_quality WHERE k IN ('pdoc_chunk_rows', 'pdoc_chunk_entities', 'pdoc_resume');
INSERT INTO search_quality SELECT 'pdoc_chunk_rows', chunk_rows, current_setting('memory_limit')
FROM tmp3_pdoc_cfg;
INSERT INTO search_quality SELECT 'pdoc_chunk_entities', count(DISTINCT tbl), 'сущностей выше порога'
FROM tmp3_pdoc_chunks;
INSERT INTO search_quality SELECT 'pdoc_resume', (SELECT on_::INT FROM tmp3_resume_pdoc),
  CASE WHEN (SELECT on_ FROM tmp3_resume_pdoc) THEN 'докатка чанков' ELSE 'свежий такт' END;

CREATE TABLE IF NOT EXISTS tmp3_corpus
  (src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
   nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
   refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));
DELETE FROM tmp3_corpus WHERE NOT (SELECT on_ FROM tmp3_resume_pdoc);

DELETE FROM tmp3_pdoc_stage s
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = s.src_table)
  AND NOT (SELECT on_ FROM tmp3_resume_pdoc);
DELETE FROM tmp3_pdoc_progress p
WHERE EXISTS (SELECT 1 FROM tmp3_pdoc_chunks c WHERE c.tbl = p.tbl)
  AND (NOT (SELECT on_ FROM tmp3_resume_pdoc)
       OR EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = p.tbl));

SELECT 'pdoc лимиты' AS шаг,
       (SELECT ws_bytes_per_row FROM tmp3_pdoc_cfg)::BIGINT AS ws_байт_на_строку,
       (SELECT chunk_rows FROM tmp3_pdoc_cfg) AS порция_строк,
       (SELECT v FROM search_quality WHERE k = 'pdoc_chunk_entities') AS крупных,
       (SELECT note FROM search_quality WHERE k = 'pdoc_resume') AS режим;

'''

    old6 = '''-- ============ 6. СБОРКА ТЕКСТА ============
CREATE OR REPLACE TABLE tmp3_corpus
  (src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR, doc_hash VARCHAR,
   nums MAP(VARCHAR, DOUBLE), flags MAP(VARCHAR, BOOLEAN), doc_date TIMESTAMP,
   refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));

PREPARE p_doc AS'''
    new6 = f'-- ============ 6. СБОРКА ТЕКСТА ============\n{section_5bis}\nPREPARE p_doc AS'
    if old6 not in text:
        raise SystemExit("anchor old6 missing")
    text = text.replace(old6, new6, 1)

    pdoc_end = text.index('-- ============ 6-бис. УПРОЩЁННЫЙ')
    pdoc_start = text.index('PREPARE p_doc AS\n')
    pdoc_body = text[pdoc_start:pdoc_end]
    chunk = pdoc_body.replace(
        'PREPARE p_doc AS\nINSERT INTO tmp3_corpus\n',
        'PREPARE p_doc_chunk AS\nINSERT INTO tmp3_pdoc_stage\n',
    )
    chunk = chunk.replace(
        "src AS (SELECT row_number() OVER () AS rid, substr(coalesce(COLUMNS(*)::VARCHAR, ''), 1, 20000) FROM query_table($1)),\n cells AS (SELECT * FROM src UNPIVOT",
        "src AS (SELECT row_number() OVER () AS rid, substr(coalesce(COLUMNS(*)::VARCHAR, ''), 1, 20000) FROM query_table($1)),\n src_f AS (SELECT * FROM src WHERE rid BETWEEN $2::BIGINT AND $3::BIGINT),\n cells AS (SELECT * FROM src_f UNPIVOT",
    )
    marker = "SELECT src_table,\n       CASE WHEN count(*) OVER (PARTITION BY src_table, row_key) > 1"
    idx = chunk.index(marker)
    chunk = chunk[:idx] + (
        "SELECT src_table, rk, doc, refs, nums, flags, dt AS doc_date, refs_map, refs_own\n"
        "FROM (\n"
        "SELECT src_table, coalesce(row_key, sha1(doc)) AS rk, doc, refs, nums, flags, dt, refs_map, refs_own\n"
        "FROM (\n"
        "  SELECT $1::VARCHAR AS src_table,\n"
        "         coalesce(any_value(k.row_key),\n"
        "                  max(val) FILTER (is_guid AND col='Ref_Key' AND own_ref)) AS row_key,\n"
        "         regexp_replace($1,'^[^_]*_','') || coalesce(' | ' || string_agg(piece,' | ' ORDER BY prio, ord)\n"
        "                                                     FILTER (piece IS NOT NULL), '') AS doc,\n"
        "         coalesce(string_agg(piece,' | ' ORDER BY ord) FILTER (is_guid AND refname IS NOT NULL), '') AS refs,\n"
        "         map_from_entries(list({'key': col, 'value': try_cast(val AS DOUBLE)} ORDER BY col)\n"
        "                          FILTER (is_measure AND try_cast(val AS DOUBLE) IS NOT NULL)) AS nums,\n"
        "         coalesce(map_from_entries(list({'key': col, 'value': try_cast(val AS BOOLEAN)} ORDER BY col)\n"
        "                          FILTER (is_flag AND try_cast(val AS BOOLEAN) IS NOT NULL)),\n"
        "                  MAP{}::MAP(VARCHAR, BOOLEAN)) AS flags,\n"
        "         coalesce(map_from_entries(list({'key': replace(col,'_Key',''),\n"
        "                                         'value': coalesce(refname, val)} ORDER BY col)\n"
        "                          FILTER (is_guid AND col <> 'Ref_Key'\n"
        "                                  AND coalesce(val,'') <> ''\n"
        "                                  AND val <> '00000000-0000-0000-0000-000000000000')),\n"
        "                  MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_map,\n"
        "         coalesce(map_from_entries(list({'key': replace(col,'_Key',''),\n"
        "                                         'value': refowner} ORDER BY col)\n"
        "                          FILTER (is_guid AND col <> 'Ref_Key'\n"
        "                                  AND refowner IS NOT NULL AND refowner <> '')),\n"
        "                  MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_own,\n"
        "         max(nullif(try_cast(val AS TIMESTAMP), TIMESTAMP '0001-01-01 00:00:00'))\n"
        "             FILTER (is_dt IS NOT NULL) AS dt\n"
        "  FROM pieces LEFT JOIN keyed k USING (rid) GROUP BY rid) g) h;\n\n"
    )
    finalize = '''
PREPARE p_doc_finalize AS
INSERT INTO tmp3_corpus
WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower($1)),
fold AS (SELECT (SELECT key_cols FROM kc) = ['Ref_Key'] AS on_),
base AS (
  SELECT src_table, rk, doc, refs, nums, flags, doc_date AS dt, refs_map, refs_own
  FROM tmp3_pdoc_stage WHERE src_table = $1
),
dedup AS (
  SELECT DISTINCT src_table, rk, doc, refs, nums, flags, dt, refs_map, refs_own
  FROM base
),
mid AS (
  SELECT src_table,
         CASE WHEN NOT (SELECT on_ FROM fold)
               AND count(*) OVER (PARTITION BY src_table, rk) > 1
              THEN rk || '#' || sha1(doc) ELSE rk END AS row_key,
         doc, refs, sha1(doc || chr(0) || refs) AS doc_hash,
         nums, flags, dt, refs_map, refs_own
  FROM dedup
),
fin AS (
  SELECT src_table,
         CASE WHEN count(*) OVER (PARTITION BY src_table, row_key) > 1
              THEN row_key || '#' || row_number() OVER (PARTITION BY src_table, row_key
                                                        ORDER BY doc, refs, refs_map::VARCHAR,
                                                                 nums::VARCHAR, flags::VARCHAR, dt)
              ELSE row_key END AS row_key,
         doc, refs, doc_hash, nums, flags, dt, refs_map, refs_own
  FROM mid
)
SELECT src_table, row_key, doc, refs, doc_hash, nums, flags, dt, refs_map, refs_own
FROM fin
QUALIFY NOT (SELECT on_ FROM fold)
     OR row_number() OVER (PARTITION BY src_table, row_key ORDER BY doc, refs, doc_hash) = 1;

'''
    text = text[:pdoc_end] + '\n' + chunk + finalize + text[pdoc_end:]

    old_loop = """SELECT 'EXECUTE p_doc(' || quote_literal(tbl) || ');' FROM tmp3_build
\\gexec
\\set ON_ERROR_STOP on"""
    new_loop = """SELECT 'EXECUTE p_doc(' || quote_literal(b.tbl) || ');'
FROM tmp3_build b
JOIN tmp3_entity_rows e ON e.tbl = b.tbl
CROSS JOIN tmp3_pdoc_cfg cfg
WHERE e.nrows <= cfg.chunk_rows
  AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = b.tbl)
\\gexec

SELECT stmt FROM (
  SELECT c.tbl, c.lo, 1 AS ord,
         'EXECUTE p_doc_chunk(' || quote_literal(c.tbl) || ', ' || c.lo || ', ' || c.hi || ');' AS stmt
  FROM tmp3_pdoc_chunks c
  LEFT JOIN tmp3_pdoc_progress p ON p.tbl = c.tbl
  WHERE c.hi > coalesce(p.rid_hi, 0)
    AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = c.tbl)
  UNION ALL
  SELECT c.tbl, c.lo, 2,
         'INSERT INTO tmp3_pdoc_progress (tbl, rid_hi, nrows) SELECT '
           || quote_literal(c.tbl) || ', ' || c.hi || '::BIGINT, ' || c.nrows
           || '::BIGINT ON CONFLICT (tbl) DO UPDATE SET rid_hi = excluded.rid_hi, nrows = excluded.nrows;'
  FROM tmp3_pdoc_chunks c
  LEFT JOIN tmp3_pdoc_progress p ON p.tbl = c.tbl
  WHERE c.hi > coalesce(p.rid_hi, 0)
    AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = c.tbl)
) z ORDER BY tbl, lo, ord
\\gexec

SELECT 'EXECUTE p_doc_finalize(' || quote_literal(f.tbl) || ');'
FROM (
  SELECT c.tbl
  FROM tmp3_pdoc_chunks c
  JOIN tmp3_pdoc_progress p ON p.tbl = c.tbl
  GROUP BY c.tbl, p.nrows
  HAVING max(p.rid_hi) >= p.nrows
     AND NOT EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = c.tbl)
) f
\\gexec

DELETE FROM tmp3_pdoc_stage s
USING (SELECT DISTINCT tbl FROM tmp3_pdoc_chunks) c
WHERE s.src_table = c.tbl
  AND EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = c.tbl);
DELETE FROM tmp3_pdoc_progress p
WHERE EXISTS (SELECT 1 FROM tmp3_corpus t WHERE t.src_table = p.tbl);
\\set ON_ERROR_STOP on"""
    if old_loop not in text:
        raise SystemExit("anchor old_loop missing")
    return text.replace(old_loop, new_loop, 1)


def main():
    src = TARGET.read_text(encoding='utf-8')
    out = patch(src)
    tmp = TARGET.with_suffix('.sql.new')
    tmp.write_text(out, encoding='utf-8')
    tmp.replace(TARGET)
    print('patched', TARGET, 'lines', len(out.splitlines()))


if __name__ == '__main__':
    main()
