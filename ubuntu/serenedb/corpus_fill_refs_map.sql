\set ON_ERROR_STOP on
\timing on

-- Заполнение refs_map БЕЗ пересчёта вектора. Текст и doc_hash не трогаем.
-- Карта строится тем же SQL, что nums: map_from_entries + ORDER BY col.
-- Ref_Key табличной части в ось не входит. Цель оси — search_refmap.owner.
--
-- Нужны: search_refmap (есть), tmp3_cls и tmp3_key (последний такт). Нет — стоп,
-- не имитировать разбором текста refs.

SELECT CASE WHEN (SELECT count(*) FROM duckdb_tables()
                    WHERE table_name = 'tmp3_cls') = 0
              OR (SELECT count(*) FROM duckdb_tables()
                    WHERE table_name = 'tmp3_key') = 0
       THEN error('нет tmp3_cls/tmp3_key — карта ссылок без классификации колонок не собирается')
       END;

ALTER TABLE search_corpus ADD COLUMN IF NOT EXISTS refs_map MAP(VARCHAR, VARCHAR);

CREATE TABLE IF NOT EXISTS search_refcols (
  src_table VARCHAR, col VARCHAR, target_src VARCHAR);
GRANT SELECT ON search_refcols TO serene_ro;

-- Однозначная карта имён — та же, что в corpus_build.sql.
CREATE OR REPLACE TABLE tmp3_refmap AS
SELECT guid, name, owner FROM (
  SELECT guid, name, owner,
         count(*) OVER (PARTITION BY owner, guid) AS вхождений_у_владельца
  FROM search_refmap)
QUALIFY row_number() OVER (PARTITION BY guid
        ORDER BY вхождений_у_владельца, owner, name) = 1;

CREATE OR REPLACE TABLE tmp3_refs_fill (
  src_table VARCHAR, row_key VARCHAR,
  refs_map MAP(VARCHAR, VARCHAR), refs_own MAP(VARCHAR, VARCHAR));

PREPARE p_fill_refs AS
INSERT INTO tmp3_refs_fill
WITH kc AS (SELECT key_cols FROM tmp3_key WHERE entity = lower($1)),
 src AS (SELECT row_number() OVER () AS rid, COLUMNS(*)::VARCHAR FROM query_table($1)),
 cells AS (SELECT * FROM src UNPIVOT (val FOR col IN (COLUMNS(* EXCLUDE (rid))))),
 keyed AS (
   SELECT u.rid,
          string_agg(u.val, '|' ORDER BY list_position((SELECT key_cols FROM kc), u.col)) AS row_key
   FROM cells u
   WHERE list_position((SELECT key_cols FROM kc), u.col) IS NOT NULL
   GROUP BY u.rid),
 j AS (
   SELECT u.rid, u.col, u.val, r.name AS refname, r.owner AS refowner,
          regexp_full_match(u.val,
            '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}') AS is_guid
   FROM cells u
   JOIN tmp3_cls c ON c.tbl = $1 AND c.col = u.col
   LEFT JOIN tmp3_refmap r
          ON r.guid = CASE WHEN regexp_full_match(u.val,
               '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
             THEN u.val END
   WHERE u.val <> ''
     AND (c.kind = 'ref' OR regexp_full_match(u.val,
          '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'))
)
SELECT $1::VARCHAR,
       coalesce(any_value(k.row_key),
                max(j.val) FILTER (j.is_guid AND j.col = 'Ref_Key')) AS row_key,
       coalesce(map_from_entries(list({'key': replace(j.col,'_Key',''),
                                       'value': coalesce(j.refname, j.val)} ORDER BY j.col)
                        FILTER (j.is_guid AND j.col <> 'Ref_Key'
                                AND coalesce(j.val,'') <> ''
                                AND j.val <> '00000000-0000-0000-0000-000000000000')),
                MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_map,
       coalesce(map_from_entries(list({'key': replace(j.col,'_Key',''),
                                       'value': j.refowner} ORDER BY j.col)
                        FILTER (j.is_guid AND j.col <> 'Ref_Key'
                                AND j.refowner IS NOT NULL AND j.refowner <> '')),
                MAP{}::MAP(VARCHAR, VARCHAR)) AS refs_own
FROM j LEFT JOIN keyed k USING (rid)
GROUP BY rid;

-- Только сущности, у которых в корпусе есть строки и в классификации — ссылки.
SELECT 'EXECUTE p_fill_refs(' || quote_literal(s.src_table) || ');'
FROM (SELECT DISTINCT src_table FROM search_corpus) s
WHERE EXISTS (SELECT 1 FROM tmp3_cls c
              WHERE c.tbl = s.src_table AND c.kind = 'ref' AND c.col <> 'Ref_Key')
\gexec

-- Вектор не сбрасывается: колонка не входит в doc_hash.
UPDATE search_corpus c SET refs_map = t.refs_map
FROM tmp3_refs_fill t
WHERE t.src_table = c.src_table AND t.row_key = c.row_key
  AND c.refs_map IS DISTINCT FROM t.refs_map;

DELETE FROM search_refcols;
INSERT INTO search_refcols
SELECT src_table, col, min(target_src)
FROM (
  SELECT src_table, unnest(map_keys(refs_own)) AS col,
         unnest(map_values(refs_own)) AS target_src
  FROM tmp3_refs_fill
  WHERE refs_own IS NOT NULL AND len(map_keys(refs_own)) > 0
) h
WHERE target_src IS NOT NULL AND target_src <> ''
  AND EXISTS (SELECT 1 FROM search_tables s WHERE s.src_table = h.target_src)
GROUP BY src_table, col
HAVING count(DISTINCT target_src) = 1;

DELETE FROM search_quality WHERE k = 'refcols_empty_target';
INSERT INTO search_quality
SELECT 'refcols_empty_target', count(*),
       'осей ссылок без однозначной цели — в search_refcols не кладём'
FROM (
  SELECT DISTINCT src_table, unnest(map_keys(refs_map)) AS col
  FROM search_corpus
  WHERE refs_map IS NOT NULL AND len(map_keys(refs_map)) > 0
  EXCEPT
  SELECT src_table, col FROM search_refcols
) miss;

GRANT SELECT ON search_refcols TO serene_ro;

SELECT 'refs_map fill' AS шаг,
       (SELECT count(*) FROM search_corpus WHERE refs_map IS NOT NULL
          AND len(map_keys(refs_map)) > 0) AS с_картой,
       (SELECT count(*) FROM search_corpus WHERE emb IS NULL) AS без_вектора,
       (SELECT count(*) FROM search_refcols) AS осей,
       (SELECT v FROM search_quality WHERE k = 'refcols_empty_target') AS без_цели;
