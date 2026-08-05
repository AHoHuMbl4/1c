-- ОПЫТ НА КОПИИ: что даёт чистка словаря синонимов. Боевой словарь НЕ трогается.
--
-- Проверяемая мысль (замер 05.08): словарь портят не слова, а ФРАЗЫ. Задание генератора
-- просит «естественный способ спросить про величину», и модель кладёт в словарь вопросы
-- целиком — «сколько тары у нас». Поиск считает совпадение по всем словам вопроса, включая
-- «сколько», «у», «нас», и регистр тары становится лидером ЛЮБОГО вопроса «сколько у нас …».
--
-- Отсечка по числу слов — признак СТРУКТУРНЫЙ, а не языковой: списка стоп-слов здесь нет и
-- быть не может (он был бы привязкой к языку, п. 9). Штатный список стоп-слов у движка тоже
-- задаётся руками (доки: Sql › Statements › Create text search dictionary › stopwords), то
-- есть тот же хардкод, только в другом месте.
--
-- Три копии сравниваются одним прибором `alias_rank_bench.py`:
--   alias_w2 — оставлены записи в 1-2 слова;
--   alias_w3 — 1-3 слова;
--   alias_w3l — 1-3 слова ПЛЮС собственное название сущности (его в словаре может не быть).
-- Индекс у каждой свой, словарь разбора тот же (`search_dict`), чтобы сравнение было честным.

DROP TABLE IF EXISTS alias_w2;
DROP TABLE IF EXISTS alias_w3;
DROP TABLE IF EXISTS alias_w3l;

CREATE TABLE alias_w2 AS
WITH w AS (SELECT src_table, trim(u.w) AS t
             FROM search_entity_alias, unnest(str_split(aliases, ',')) AS u(w))
SELECT src_table, string_agg(DISTINCT t, ', ') AS aliases
  FROM w WHERE t <> '' AND len(str_split(t, ' ')) <= 2
 GROUP BY src_table;

CREATE TABLE alias_w3 AS
WITH w AS (SELECT src_table, trim(u.w) AS t
             FROM search_entity_alias, unnest(str_split(aliases, ',')) AS u(w))
SELECT src_table, string_agg(DISTINCT t, ', ') AS aliases
  FROM w WHERE t <> '' AND len(str_split(t, ' ')) <= 3
 GROUP BY src_table;

CREATE TABLE alias_w3l AS
WITH w AS (SELECT a.src_table, trim(u.w) AS t
             FROM search_entity_alias a, unnest(str_split(a.aliases, ',')) AS u(w)
            WHERE trim(u.w) <> '' AND len(str_split(trim(u.w), ' ')) <= 3
           UNION ALL
           SELECT t.src_table, t.label FROM search_tables t
            WHERE t.label IS NOT NULL AND t.label <> ''
              AND EXISTS (SELECT 1 FROM search_entity_alias a WHERE a.src_table = t.src_table))
SELECT src_table, string_agg(DISTINCT t, ', ') AS aliases
  FROM w GROUP BY src_table;

CREATE INDEX alias_w2_idx  ON alias_w2  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
CREATE INDEX alias_w3_idx  ON alias_w3  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
CREATE INDEX alias_w3l_idx ON alias_w3l USING inverted(aliases search_dict, src_table) INCLUDE (src_table);

SELECT 'копии словаря собраны' AS шаг,
       (SELECT count(*) FROM alias_w2)  AS в_1_2_слова,
       (SELECT count(*) FROM alias_w3)  AS в_1_3_слова,
       (SELECT count(*) FROM alias_w3l) AS с_названием,
       (SELECT count(*) FROM search_entity_alias) AS исходно;
