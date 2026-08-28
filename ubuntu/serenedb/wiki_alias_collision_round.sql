\set ON_ERROR_STOP on
-- Один круг разведения: выбор слова, отметка probe, JSON пачки для модели.
-- Доки: Aggregate string_agg; Utility md5; struct_pack; read_json не нужен здесь.
WITH al AS (
  SELECT src_table, trim(lower(x.a)) AS alias
  FROM :alias_table, unnest(str_split(aliases, ',')) AS x(a)
  WHERE trim(x.a) <> ''),
dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
cand AS (
  SELECT a.alias,
         md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp,
         count(DISTINCT a.src_table) AS n
  FROM al a JOIN dup d ON d.alias = a.alias
  WHERE (:'target_word' = '' OR a.alias = lower(:'target_word'))
    AND NOT EXISTS (SELECT 1 FROM :alias_table s
                     WHERE s.src_table = a.src_table
                       AND s.not_enough_for ILIKE '%' || a.alias || '%')
  GROUP BY 1),
pick AS (
  SELECT c.alias, c.fp FROM cand c
  WHERE :'target_word' <> ''
     OR NOT EXISTS (SELECT 1 FROM search_alias_probe p
                     WHERE p.alias = c.alias AND p.entities_fp = c.fp)
  ORDER BY c.n DESC, c.alias LIMIT 1),
_mark AS (
  INSERT INTO search_alias_probe
  SELECT alias, fp, now() FROM pick RETURNING alias)
SELECT p.alias || chr(9) || p.fp || chr(9) || coalesce(
  (SELECT to_json(list(struct_pack(entity := f.src_table, title := f.label,
                                   quantities := coalesce(f.measures,''))))
   FROM (SELECT f.* FROM wiki_entity_facts f
          WHERE f.src_table IN (SELECT src_table FROM al WHERE alias = p.alias)
          ORDER BY f.src_table LIMIT :batch) f),
  '[]')
FROM pick p;
