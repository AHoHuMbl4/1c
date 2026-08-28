\set ON_ERROR_STOP on
-- Пачка сущностей по векторной близости (первый проход). Доки: struct_pack; vector <=>; aggregate functions (string_agg).
WITH seed AS (
  SELECT f.src_table, t.emb FROM wiki_entity_facts f
  JOIN search_tables t ON t.src_table = f.src_table
  WHERE f.cls <> 'service'
    AND NOT EXISTS (SELECT 1 FROM :alias_table a WHERE a.src_table = f.src_table
                    AND (coalesce(a.aliases,'') <> ''
                         OR a.seen_at > now() - INTERVAL :retry_h HOUR))
  ORDER BY f.src_table LIMIT 1)
SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                quantities := coalesce(measures,''),
                                flows := flows)))
FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d,
             coalesce((SELECT string_agg(lbl, ', ') FROM (
                       SELECT DISTINCT t2.label AS lbl,
                              t2.src_table LIKE 'accumulationregister_%' AS is_reg
                       FROM search_refcols r
                       JOIN search_tables t2 ON t2.src_table = r.src_table
                       WHERE r.target_src = f.src_table
                       ORDER BY is_reg DESC, lbl LIMIT 12) x), '') AS flows
        FROM wiki_entity_facts f
        JOIN search_tables t ON t.src_table = f.src_table
       WHERE f.cls <> 'service'
         AND NOT EXISTS (SELECT 1 FROM :alias_table a WHERE a.src_table = f.src_table
                    AND (coalesce(a.aliases,'') <> ''
                         OR a.seen_at > now() - INTERVAL :retry_h HOUR))
       ORDER BY d, f.src_table LIMIT :batch);
