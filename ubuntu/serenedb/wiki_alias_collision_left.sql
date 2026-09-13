\set ON_ERROR_STOP on
-- Сколько столкновений ещё не спрашивали. Доки: Aggregate string_agg; Utility md5.
-- Токены aliases: ' | ' с фолбэком ', '. Доки: Text string_split / len(list) / position.
-- meta_stop: источник wiki_alias_parse.py:_PLATFORM_META_STOP (P3); рассинхрон ловит замок.
WITH meta_stop(word) AS (VALUES
  ('список'),('списки'),
  ('справочник'),('справочники'),
  ('каталог'),('каталоги'),
  ('реестр'),('реестры'),
  ('тип'),('типы'),
  ('вид'),('виды'),
  ('группа'),('группы'),
  ('документ'),('документы'),
  ('журнал'),('журналы'),
  ('регистр'),('регистры'),
  ('отчет'),('отчеты'),
  ('запись'),('записи'),
  ('карточка'),('карточки'),
  ('перечень'),('перечни'),
  ('перечисление'),('перечисления'),
  ('константа'),('константы'),
  ('движение'),('движения'),
  ('list'),('lists'),
  ('catalog'),('catalogues'),('catalogs'),
  ('directory'),('directories'),
  ('journal'),('journals'),
  ('register'),('registers'),
  ('document'),('documents'),
  ('report'),('reports'),
  ('enum'),('enumeration')
),
al AS (
  SELECT src_table, trim(lower(x.a)) AS alias
  FROM :alias_table, unnest(
    CASE
      WHEN len(str_split(coalesce(aliases, ''), ' | ')) = 1
           AND position(', ' IN coalesce(aliases, '')) > 0
        THEN str_split(aliases, ', ')
      ELSE str_split(coalesce(aliases, ''), ' | ')
    END) AS x(a)
  WHERE trim(x.a) <> ''),
dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
cand AS (
  SELECT a.alias,
         md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp
  FROM al a JOIN dup d ON d.alias = a.alias
  WHERE a.alias NOT IN (SELECT word FROM meta_stop)
    AND NOT EXISTS (SELECT 1 FROM :alias_table s
                     WHERE s.src_table = a.src_table
                       AND s.not_enough_for ILIKE '%' || a.alias || '%')
  GROUP BY 1)
SELECT count(*) FROM cand c
WHERE NOT EXISTS (SELECT 1 FROM :probe_table p
                   WHERE p.alias = c.alias AND p.entities_fp = c.fp);
