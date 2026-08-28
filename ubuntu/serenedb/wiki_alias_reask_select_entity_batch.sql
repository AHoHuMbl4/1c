\set ON_ERROR_STOP on
-- Пачка reask: журнальные кандидаты (файл) + устаревшие записи основного словаря.
-- Порядок: сначала из pool-файла (прибор ask_journal), затем stale по seen_at.
-- Доки: read_json; struct_pack; vector <=>.
WITH pool AS (
  SELECT trim(x.t) AS src_table
  FROM read_json(:'pool_path',
    columns := {t:'VARCHAR'}) x
  WHERE trim(coalesce(x.t,'')) <> ''),
stale AS (
  SELECT f.src_table
  FROM wiki_entity_facts f
  JOIN :alias_table a ON a.src_table = f.src_table
  WHERE f.cls <> 'service'
    AND coalesce(a.aliases,'') <> ''
    AND a.seen_at < now() - INTERVAL :reask_stale_days DAY
    AND f.src_table NOT IN (SELECT src_table FROM pool)),
pick AS (
  SELECT src_table, 0 AS pri FROM pool
  UNION ALL
  SELECT src_table, 1 AS pri FROM stale
  ORDER BY pri, src_table
  LIMIT :batch),
seed AS (
  SELECT f.src_table, t.emb FROM wiki_entity_facts f
  JOIN search_tables t ON t.src_table = f.src_table
  WHERE f.src_table IN (SELECT src_table FROM pick)
  ORDER BY f.src_table LIMIT 1)
SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                quantities := coalesce(measures,''),
                                flows := flows)))
FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d,
             coalesce((SELECT string_agg(lbl, ', ') FROM (
                       SELECT DISTINCT t2.label AS lbl,
                              t2.src_table LIKE 'accumulationregister_%%' AS is_reg
                       FROM search_refcols r
                       JOIN search_tables t2 ON t2.src_table = r.src_table
                       WHERE r.target_src = f.src_table
                       ORDER BY is_reg DESC, lbl LIMIT 12) x), '') AS flows
        FROM wiki_entity_facts f
        JOIN search_tables t ON t.src_table = f.src_table
       WHERE f.src_table IN (SELECT src_table FROM pick)
       ORDER BY d, f.src_table LIMIT :batch);
