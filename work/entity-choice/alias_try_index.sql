-- Индекс и права для НОВОЙ редакции словаря синонимов, собранной в копию `alias_try`.
-- Зовётся ПОСЛЕ прогона генератора; боевой словарь и его индекс не трогаются.
--
-- Индекс строится ровно так же, как боевой `alias_idx` (`corpus_init.sql`): тот же словарь
-- разбора `search_dict`, тот же разделитель равенства `src_table` в INCLUDE. Иначе сравнение
-- двух редакций мерило бы разницу индексов, а не разницу словарей.
--
-- Права роли чтения обязательны: прибор `work/entity-choice/alias_rank_bench.py` ходит в базу
-- под `serene_ro`, как и сам сервис ответов. Без них проба молча покажет «эталон не найден
-- ни разу» — так и вышло при первом заходе 05.08.

DROP INDEX IF EXISTS alias_try_idx;
CREATE INDEX alias_try_idx ON alias_try
  USING inverted(aliases search_dict, src_table) INCLUDE (src_table);
GRANT SELECT ON alias_try TO serene_ro;
GRANT SELECT ON alias_try_idx TO serene_ro;

SELECT 'новая редакция словаря' AS шаг,
       count(*) AS сущностей,
       count(*) FILTER (aliases = '') AS пустых_модель_не_ответила,
       round(avg(len(str_split(aliases, ',')))) AS слов_на_сущность_в_среднем,
       (SELECT count(*) FROM search_entity_alias) AS в_боевом_словаре
  FROM alias_try;
