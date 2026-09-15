\set ON_ERROR_STOP on
-- Один круг разведения: выбор слова, отметка probe, JSON пачки для модели.
-- Input: word раунда + текущие aliases/best/nef (промт v2; P2/P7).
-- Доки: Aggregate string_agg; Utility md5; struct_pack; read_json не нужен здесь.
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
         md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp,
         count(DISTINCT a.src_table) AS n
  FROM al a JOIN dup d ON d.alias = a.alias
  WHERE (:'target_word' = '' OR a.alias = lower(:'target_word'))
    AND a.alias NOT IN (SELECT word FROM meta_stop)
    AND NOT EXISTS (SELECT 1 FROM :alias_table s
                     WHERE s.src_table = a.src_table
                       AND s.not_enough_for ILIKE '%' || a.alias || '%')
  GROUP BY 1),
pick AS (
  SELECT c.alias, c.fp FROM cand c
  WHERE :'target_word' <> ''
     OR NOT EXISTS (SELECT 1 FROM :probe_table p
                     WHERE p.alias = c.alias AND p.entities_fp = c.fp)
  ORDER BY c.n DESC, c.alias LIMIT 1),
_mark AS (
  -- Явные колонки: probe += result/gen_ver (DEFAULT ''); позиционный INSERT
  -- из трёх значений на пятиколоночной таблице падает.
  INSERT INTO :probe_table (alias, entities_fp, asked_at)
  SELECT alias, fp, now() FROM pick RETURNING alias)
SELECT p.alias || chr(9) || p.fp || chr(9) || coalesce(
  (SELECT to_json(list(struct_pack(
      entity := f.src_table,
      title := f.label,
      quantities := coalesce(f.measures,''),
      flows := flows,
      word := p.alias,
      aliases := coalesce(a.aliases, ''),
      best_used_for := coalesce(a.best_used_for, ''),
      not_enough_for := coalesce(a.not_enough_for, ''))))
   FROM (SELECT f.*,
             coalesce((SELECT string_agg(lbl, ', ') FROM (
                       SELECT DISTINCT t2.label AS lbl,
                              t2.src_table LIKE 'accumulationregister_%' AS is_reg
                       FROM search_refcols r
                       JOIN search_tables t2 ON t2.src_table = r.src_table
                       WHERE r.target_src = f.src_table
                       ORDER BY is_reg DESC, lbl LIMIT 12) x), '') AS flows
           FROM wiki_entity_facts f
          WHERE f.src_table IN (SELECT src_table FROM al WHERE alias = p.alias)
          ORDER BY f.src_table LIMIT :batch) f
   LEFT JOIN :alias_table a ON a.src_table = f.src_table),
  '[]')
FROM pick p;
