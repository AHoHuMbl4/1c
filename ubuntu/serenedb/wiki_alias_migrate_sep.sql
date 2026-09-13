\set ON_ERROR_STOP on
-- =============================================================================
-- Остаточная миграция разделителя ПОСЛЕ promote: ', ' → ' | ' (P4 §2.5 / SEP).
--
-- 🔴 ЗАПУСКАТЬ ТОЛЬКО ПО СЛОВУ ВЛАДЕЛЬЦА / ОРКЕСТРАТОРА.
--    Порядок: dual-Solr → wiki_alias_promote.sql → ЭТОТ файл → Solr из боя.
--    Собственного снапшота НЕТ: откат — из снапшота promote
--    (<battle>_pre_promote_<snap_suffix>).
--
-- Что делает: replace ', ' → ' | ' в aliases / best_used_for / not_enough_for
-- боя и в aliases мер, ТОЛЬКО если:
--   • есть ', ';
--   • ещё нет ' | ' (guard — повтор безопасен);
--   • нет скобочного паттерна «(…,…») — скобочные 13/27 НЕ трогаем
--     (force-regen отдельным эпизодом; только комментарий, не UPDATE).
--
-- Параметры psql (-v):
--   battle_table    — бой сущностей (умолч. search_entity_alias)
--   battle_measure  — бой мер (умолч. search_measure_alias)
--   snap_suffix     — тот же suffix, что у promote (для имён отката)
--   dry_run         — 1 = только SELECT-счётчики, без UPDATE (умолч. 0)
--
-- Пример (после promote с тем же snap_suffix):
--   psql "$DSN" \
--     -v battle_table=search_entity_alias \
--     -v battle_measure=search_measure_alias \
--     -v snap_suffix=20260913 \
--     -f wiki_alias_migrate_sep.sql
--
-- Доки: Text replace / position / regexp_matches; Statements BEGIN/COMMIT;
--       UPDATE.
-- =============================================================================

\if :{?battle_table}
\else
\set battle_table search_entity_alias
\endif
\if :{?battle_measure}
\else
\set battle_measure search_measure_alias
\endif
\if :{?dry_run}
\else
\set dry_run 0
\endif
\if :{?snap_suffix}
\else
SELECT error(
  'wiki_alias_migrate_sep: нужен -v snap_suffix=… (тот же, что у promote — откат из его снапшота)'
);
\endif

\set entity_snap :battle_table'_pre_promote_':snap_suffix
\set measure_snap :battle_measure'_pre_promote_':snap_suffix

-- Скобочный паттерн (как в прежней заготовке / check-sepw4): запятая внутри (…).
-- Скобочные best/nef (живые 13/27 на OKNA) — НЕ replace; force-regen отдельно.

-- ── Dry-run счётчики (eligible / skip) ───────────────────────────────────────
SELECT 'dry_run' AS phase,
       (SELECT count(*) FROM :"battle_table"
         WHERE aliases IS NOT NULL
           AND position(', ' IN aliases) > 0
           AND position(' | ' IN aliases) = 0
           AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)')) AS aliases_elig,
       (SELECT count(*) FROM :"battle_table"
         WHERE aliases IS NOT NULL
           AND position(', ' IN aliases) > 0
           AND (position(' | ' IN aliases) > 0
                OR regexp_matches(aliases, '\([^)]*,[^)]*\)'))) AS aliases_skip,
       (SELECT count(*) FROM :"battle_table"
         WHERE best_used_for IS NOT NULL
           AND position(', ' IN best_used_for) > 0
           AND position(' | ' IN best_used_for) = 0
           AND NOT regexp_matches(best_used_for, '\([^)]*,[^)]*\)')) AS best_elig,
       (SELECT count(*) FROM :"battle_table"
         WHERE best_used_for IS NOT NULL
           AND position(', ' IN best_used_for) > 0
           AND regexp_matches(best_used_for, '\([^)]*,[^)]*\)')) AS best_paren_skip,
       (SELECT count(*) FROM :"battle_table"
         WHERE not_enough_for IS NOT NULL
           AND position(', ' IN not_enough_for) > 0
           AND position(' | ' IN not_enough_for) = 0
           AND NOT regexp_matches(not_enough_for, '\([^)]*,[^)]*\)')) AS nef_elig,
       (SELECT count(*) FROM :"battle_table"
         WHERE not_enough_for IS NOT NULL
           AND position(', ' IN not_enough_for) > 0
           AND regexp_matches(not_enough_for, '\([^)]*,[^)]*\)')) AS nef_paren_skip,
       (SELECT count(*) FROM :"battle_measure"
         WHERE aliases IS NOT NULL
           AND position(', ' IN aliases) > 0
           AND position(' | ' IN aliases) = 0
           AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)')) AS measure_elig;

SELECT (:dry_run = 0) AS do_update;
\gset sep_

\if :sep_do_update

BEGIN;

-- Entity aliases
UPDATE :"battle_table"
SET aliases = replace(aliases, ', ', ' | ')
WHERE aliases IS NOT NULL
  AND position(', ' IN aliases) > 0
  AND position(' | ' IN aliases) = 0
  AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)');

-- Entity best_used_for
UPDATE :"battle_table"
SET best_used_for = replace(best_used_for, ', ', ' | ')
WHERE best_used_for IS NOT NULL
  AND position(', ' IN best_used_for) > 0
  AND position(' | ' IN best_used_for) = 0
  AND NOT regexp_matches(best_used_for, '\([^)]*,[^)]*\)');

-- Entity not_enough_for
UPDATE :"battle_table"
SET not_enough_for = replace(not_enough_for, ', ', ' | ')
WHERE not_enough_for IS NOT NULL
  AND position(', ' IN not_enough_for) > 0
  AND position(' | ' IN not_enough_for) = 0
  AND NOT regexp_matches(not_enough_for, '\([^)]*,[^)]*\)');

-- Measure aliases
UPDATE :"battle_measure"
SET aliases = replace(aliases, ', ', ' | ')
WHERE aliases IS NOT NULL
  AND position(', ' IN aliases) > 0
  AND position(' | ' IN aliases) = 0
  AND NOT regexp_matches(aliases, '\([^)]*,[^)]*\)');

COMMIT;

\echo migrate_sep: UPDATE committed. Снапшот отката = :entity_snap / :measure_snap

\else
\echo migrate_sep: dry_run=1 — UPDATE пропущен
\endif

-- ── Контрольные SELECT после (или после dry-run: текущее состояние) ──────────
SELECT 'after' AS phase,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(' | ' IN coalesce(aliases, '')) > 0) AS aliases_pipe,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(', ' IN coalesce(aliases, '')) > 0
           AND position(' | ' IN coalesce(aliases, '')) = 0) AS aliases_comma_only,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(', ' IN coalesce(best_used_for, '')) > 0
           AND regexp_matches(coalesce(best_used_for, ''), '\([^)]*,[^)]*\)'))
         AS best_paren_residual,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(', ' IN coalesce(not_enough_for, '')) > 0
           AND regexp_matches(coalesce(not_enough_for, ''), '\([^)]*,[^)]*\)'))
         AS nef_paren_residual,
       (SELECT count(*) FROM :"battle_measure"
         WHERE position(', ' IN coalesce(aliases, '')) > 0
           AND position(' | ' IN coalesce(aliases, '')) = 0) AS measure_comma_only;

-- =============================================================================
-- ОТКАТ из снапшота promote (НЕ свой snap):
--
-- BEGIN;
-- DELETE FROM search_entity_alias;
-- INSERT INTO search_entity_alias SELECT * FROM search_entity_alias_pre_promote_YYYYMMDD;
-- DELETE FROM search_measure_alias;
-- INSERT INTO search_measure_alias SELECT * FROM search_measure_alias_pre_promote_YYYYMMDD;
-- COMMIT;
--
-- Имена = :battle_table / :battle_measure + _pre_promote_ + :snap_suffix
-- (те же, что wiki_alias_promote.sql создал до MERGE).
-- =============================================================================
