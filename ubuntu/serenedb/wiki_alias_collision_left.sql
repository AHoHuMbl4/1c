\set ON_ERROR_STOP on
-- Сколько столкновений ещё не спрашивали. Доки: Aggregate string_agg; Utility md5.
WITH al AS (
  SELECT src_table, trim(lower(x.a)) AS alias
  FROM :alias_table, unnest(str_split(aliases, ',')) AS x(a)
  WHERE trim(x.a) <> ''),
dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
cand AS (
  SELECT a.alias,
         md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp
  FROM al a JOIN dup d ON d.alias = a.alias
  WHERE NOT EXISTS (SELECT 1 FROM :alias_table s
                     WHERE s.src_table = a.src_table
                       AND s.not_enough_for ILIKE '%' || a.alias || '%')
  GROUP BY 1)
SELECT count(*) FROM cand c
WHERE NOT EXISTS (SELECT 1 FROM search_alias_probe p
                   WHERE p.alias = c.alias AND p.entities_fp = c.fp);
