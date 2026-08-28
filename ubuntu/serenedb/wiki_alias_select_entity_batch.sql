\set ON_ERROR_STOP on
-- Пачка сущностей по векторной близости (первый проход). Доки: struct_pack; vector <=>.
WITH seed AS (
  SELECT f.src_table, t.emb FROM wiki_entity_facts f
  JOIN search_tables t ON t.src_table = f.src_table
  WHERE f.cls <> 'service'
    AND NOT EXISTS (SELECT 1 FROM :alias_table a WHERE a.src_table = f.src_table
                    AND (coalesce(a.aliases,'') <> ''
                         OR a.seen_at > now() - INTERVAL :retry_h HOUR))
  ORDER BY f.src_table LIMIT 1)
SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                quantities := coalesce(measures,''))))
FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
        FROM wiki_entity_facts f
        JOIN search_tables t ON t.src_table = f.src_table
       WHERE f.cls <> 'service'
         AND NOT EXISTS (SELECT 1 FROM :alias_table a WHERE a.src_table = f.src_table
                    AND (coalesce(a.aliases,'') <> ''
                         OR a.seen_at > now() - INTERVAL :retry_h HOUR))
       ORDER BY d, f.src_table LIMIT :batch);
