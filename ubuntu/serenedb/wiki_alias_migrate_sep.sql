\set ON_ERROR_STOP on
-- =============================================================================
-- Миграция разделителя словаря: ', ' → ' | ' (P4 §2.5).
--
-- 🔴 ЗАПУСКАТЬ ТОЛЬКО ПО СЛОВУ ВЛАДЕЛЬЦА. Этот файл — заготовка; сессия G2
--    его НЕ исполняет и к базе не подключается.
--
-- Перед запуском: снять snap (ниже CREATE TABLE … AS SELECT *), затем UPDATE.
-- После: wiki_pages (VIEW) пересоберётся на лету; при необходимости —
--    entity_card_build (aliases в card) и Solr-синонимы.
-- Неоднозначные строки (скобочные перечисления «(…,…») из B1) НЕ трогаем —
--    их перепишет force-перегенерация новыми промтами.
--
-- Пример вызова (после слова владельца):
--   psql "$DSN" \
--     -v alias_table=search_entity_alias \
--     -v measure_table=search_measure_alias \
--     -v alias_snap=search_entity_alias_pre_sep_snap \
--     -v measure_snap=search_measure_alias_pre_sep_snap \
--     -f wiki_alias_migrate_sep.sql
--
-- Доки: Text replace / position / regexp_matches; List len; Utility CREATE TABLE AS.
-- =============================================================================

-- 1) Snap перед миграцией (имена snap = <таблица>_pre_sep_snap через -v).
CREATE TABLE :alias_snap AS SELECT * FROM :alias_table;
CREATE TABLE :measure_snap AS SELECT * FROM :measure_table;

-- 2) Безопасный replace только без паттерна '(' … ',' … ')'.
-- Entity aliases
UPDATE :alias_table
SET aliases = replace(aliases, ', ', ' | ')
WHERE aliases IS NOT NULL
  AND position(', ' IN aliases) > 0
  AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)');

-- Entity best_used_for
UPDATE :alias_table
SET best_used_for = replace(best_used_for, ', ', ' | ')
WHERE best_used_for IS NOT NULL
  AND position(', ' IN best_used_for) > 0
  AND NOT regexp_matches(best_used_for, '\([^)]*,[^)]*\)');

-- Entity not_enough_for
UPDATE :alias_table
SET not_enough_for = replace(not_enough_for, ', ', ' | ')
WHERE not_enough_for IS NOT NULL
  AND position(', ' IN not_enough_for) > 0
  AND NOT regexp_matches(not_enough_for, '\([^)]*,[^)]*\)');

-- Measure aliases (обычно короткие слова без скобок)
UPDATE :measure_table
SET aliases = replace(aliases, ', ', ' | ')
WHERE aliases IS NOT NULL
  AND position(', ' IN aliases) > 0
  AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)');

-- 3) Контрольные SELECT: заменённые (vs snap) и не тронутые (ещё содержат ', ').
SELECT 'entity.aliases replaced' AS metric, count(*)::BIGINT AS n
  FROM :alias_table t
  JOIN :alias_snap s ON s.src_table = t.src_table
 WHERE coalesce(s.aliases, '') IS DISTINCT FROM coalesce(t.aliases, '')
UNION ALL
SELECT 'entity.aliases untouched (still has '', '')', count(*)::BIGINT
  FROM :alias_table
 WHERE position(', ' IN coalesce(aliases, '')) > 0
UNION ALL
SELECT 'entity.best_used_for replaced', count(*)::BIGINT
  FROM :alias_table t
  JOIN :alias_snap s ON s.src_table = t.src_table
 WHERE coalesce(s.best_used_for, '') IS DISTINCT FROM coalesce(t.best_used_for, '')
UNION ALL
SELECT 'entity.best_used_for untouched (still has '', '')', count(*)::BIGINT
  FROM :alias_table
 WHERE position(', ' IN coalesce(best_used_for, '')) > 0
UNION ALL
SELECT 'entity.not_enough_for replaced', count(*)::BIGINT
  FROM :alias_table t
  JOIN :alias_snap s ON s.src_table = t.src_table
 WHERE coalesce(s.not_enough_for, '') IS DISTINCT FROM coalesce(t.not_enough_for, '')
UNION ALL
SELECT 'entity.not_enough_for untouched (still has '', '')', count(*)::BIGINT
  FROM :alias_table
 WHERE position(', ' IN coalesce(not_enough_for, '')) > 0
UNION ALL
SELECT 'measure.aliases replaced', count(*)::BIGINT
  FROM :measure_table t
  JOIN :measure_snap s
    ON s.src_table = t.src_table AND s.measure = t.measure
 WHERE coalesce(s.aliases, '') IS DISTINCT FROM coalesce(t.aliases, '')
UNION ALL
SELECT 'measure.aliases untouched (still has '', '')', count(*)::BIGINT
  FROM :measure_table
 WHERE position(', ' IN coalesce(aliases, '')) > 0;
