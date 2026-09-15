\set ON_ERROR_STOP on
-- =============================================================================
-- Перенос словаря черновик → бой: union-MERGE ТОКЕНОВ (HOW_NOT_TO §3.99).
--
-- 🔴 ЗАПУСКАТЬ ТОЛЬКО ПО СЛОВУ ВЛАДЕЛЬЦА / ОРКЕСТРАТОРА.
--    Не replace строки целиком: живые токены боя не терять никогда.
--    Solr после переноса — только из боя (хвост wiki_alias.sh), не из черновика.
--
-- Параметры psql (-v):
--   draft_table     — черновик сущностей (ОБЯЗАТЕЛЕН; умолчание убрано по п.0)
--   battle_table    — бой сущностей (умолч. search_entity_alias)
--   draft_measure   — черновик мер (ОБЯЗАТЕЛЕН; умолчание убрано по п.0)
--   battle_measure  — бой мер (умолч. search_measure_alias)
--   snap_suffix     — дата/метка снапшота (ОБЯЗАТЕЛЕН), напр. 20260913
--
-- Снапшот боя: <battle>_pre_promote_<snap_suffix> (+ measure).
-- Повтор с тем же suffix → CREATE TABLE падает (не молчаливый overwrite).
--
-- best_used_for / not_enough_for — матрица заморозки (г) / dictfix-plan §4 шаг 3:
--   бой заморожен (паттерн '\([^)]*,[^)]*\)') + draft чист и непуст → поле := draft
--     ЦЕЛИКОМ (replace, не union — атомы битой строки резать нельзя);
--   бой заморожен + (draft с паттерном ИЛИ trim(draft)='') → боевое;
--   бой чист + draft с паттерном → боевое (не union — защита от грязного черновика);
--   оба чисты → _alias_union_tokens (как aliases / §3.99);
--   aliases — по-прежнему только union токенов (§3.99);
--   NOT MATCHED INSERT — draft сырьём; паттерн в новых строках — счётчиком отчёта.
--
-- Пример:
--   psql "$DSN" \
--     -v draft_table=<имя-черновика-сущностей> \
--     -v battle_table=search_entity_alias \
--     -v draft_measure=<имя-черновика-мер> \
--     -v battle_measure=search_measure_alias \
--     -v snap_suffix=20260913 \
--     -f wiki_alias_promote.sql
--
-- Доки: MERGE INTO; CREATE TABLE AS SELECT; list_concat / list_distinct /
--       list_filter / list_transform / list_sort / array_to_string;
--       regexp_split_to_array (паттерн ',| [|] ' — класс [|], без backslash, scs §3.119);
--       error(); Utility CREATE MACRO.
-- =============================================================================

-- 🔴 [п.0] Имя черновика — ОБЯЗАТЕЛЬНЫЙ параметр: умолчание с именем таблицы
-- конкретной базы было привязкой (замер п.0-пробы 15.09). Боевые имена — контур
-- продукта, одинаковы на любой базе, остаются умолчаниями.
\if :{?draft_table}
\else
SELECT error(
  'wiki_alias_promote: нужен -v draft_table=<черновик сущностей> (умолчание убрано по п.0 TARGET)'
);
\endif
\if :{?battle_table}
\else
\set battle_table search_entity_alias
\endif
\if :{?draft_measure}
\else
SELECT error(
  'wiki_alias_promote: нужен -v draft_measure=<черновик мер> (умолчание убрано по п.0 TARGET)'
);
\endif
\if :{?battle_measure}
\else
\set battle_measure search_measure_alias
\endif
\if :{?snap_suffix}
\else
SELECT error(
  'wiki_alias_promote: нужен -v snap_suffix=YYYYMMDD (без suffix снапшот не датирован)'
);
\endif

-- Имена снапшотов: <battle>_pre_promote_<suffix>
\set entity_snap :battle_table'_pre_promote_':snap_suffix
\set measure_snap :battle_measure'_pre_promote_':snap_suffix

-- ── Макрос: union токенов dual-сплитом ', ' / ' | ' → канон ' | ' ─────────────
-- 🔴 Паттерн БЕЗ backslash: ',| [|] ' (как solr_synonyms_compile.sql, §3.119).
CREATE OR REPLACE MACRO _alias_union_tokens(a, b) AS (
  coalesce(
    array_to_string(
      list_sort(
        list_distinct(
          list_filter(
            list_transform(
              list_concat(
                coalesce(regexp_split_to_array(coalesce(a, ''), ',| [|] '),
                         []::VARCHAR[]),
                coalesce(regexp_split_to_array(coalesce(b, ''), ',| [|] '),
                         []::VARCHAR[])
              ),
              x -> trim(x)
            ),
            x -> x <> ''
          )
        )
      ),
      ' | '
    ),
    ''
  )
);

-- ── 0) Счётчики ДО ───────────────────────────────────────────────────────────
SELECT 'before' AS phase,
       (SELECT count(*) FROM :"battle_table") AS battle_entity_rows,
       (SELECT count(*) FROM :"draft_table") AS draft_entity_rows,
       (SELECT count(*) FROM :"battle_measure") AS battle_measure_rows,
       (SELECT count(*) FROM :"draft_measure") AS draft_measure_rows,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(' | ' IN coalesce(aliases, '')) > 0) AS battle_aliases_pipe,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(', ' IN coalesce(aliases, '')) > 0
           AND position(' | ' IN coalesce(aliases, '')) = 0) AS battle_aliases_comma_only,
       (SELECT count(DISTINCT trim(tok))
          FROM :"battle_table" b,
               unnest(regexp_split_to_array(coalesce(b.aliases, ''), ',| [|] ')) u(tok)
         WHERE trim(tok) <> '') AS battle_alias_tokens_distinct;

-- ── 1) Снапшот боя (честная ошибка при повторном том же suffix) ──────────────
CREATE TABLE :"entity_snap" AS SELECT * FROM :"battle_table";
CREATE TABLE :"measure_snap" AS SELECT * FROM :"battle_measure";

\echo promote: snap → :entity_snap / :measure_snap

-- ── 2) Источник MERGE: только строки черновика (бой-only не попадают → не трогаем)
-- Поля draft_* — сырой черновик. aliases — только union (§3.99); best/nef — CASE (г):
--   heal = подмена поля чистым непустым draft, keep при битом/пустом draft,
--   union при обоих чистых (см. UPDATE SET ниже).
-- 🔴 СИРОТЫ ЧЕРНОВИКА НЕ УХОДЯТ В БОЙ [замер 14.09]: строка, которой нет в
-- wiki_entity_facts (движок — источник истины), иначе INSERT-ветка MERGE внесла
-- бы её в бой навсегда (unmatched-by-source не удаляются). Живой пример:
-- фантом-опечатка от 28.08. Пропущенные сироты видны счётчиком orphan_skipped
-- в фазе after — молчаливой потери нет (п. 13).
CREATE OR REPLACE TEMP TABLE _promote_entity_src AS
SELECT
  d.src_table,
  coalesce(d.aliases, '') AS draft_aliases,
  coalesce(d.best_used_for, '') AS draft_best,
  coalesce(d.not_enough_for, '') AS draft_nef,
  coalesce(d.seen_at, now()) AS draft_seen_at
FROM :"draft_table" d
WHERE EXISTS (SELECT 1 FROM wiki_entity_facts f WHERE f.src_table = d.src_table);

CREATE OR REPLACE TEMP TABLE _promote_measure_src AS
SELECT
  d.src_table,
  d.measure,
  coalesce(d.aliases, '') AS draft_aliases,
  coalesce(d.seen_at, now()) AS draft_seen_at
FROM :"draft_measure" d;

-- ── 3) MERGE: aliases = union (§3.99); best/nef = CASE матрицы (г) ────────────
--   heal → подмена поля чистым непустым draft; keep → бой при битом/пустом draft
--   (и при dirty draft на чистом бое); union → оба чисты (_alias_union_tokens).
BEGIN;

MERGE INTO :"battle_table" t
USING _promote_entity_src s
ON (t.src_table = s.src_table)
WHEN MATCHED THEN UPDATE SET
  aliases = _alias_union_tokens(t.aliases, s.draft_aliases),
  -- матрица (г): порядок веток важен — heal раньше keep-frozen
  best_used_for = CASE
    WHEN regexp_matches(coalesce(t.best_used_for, ''), '\([^)]*,[^)]*\)')
     AND NOT regexp_matches(coalesce(s.draft_best, ''), '\([^)]*,[^)]*\)')
     AND trim(s.draft_best) <> ''
      THEN s.draft_best
    WHEN regexp_matches(coalesce(t.best_used_for, ''), '\([^)]*,[^)]*\)')
      THEN t.best_used_for
    WHEN regexp_matches(coalesce(s.draft_best, ''), '\([^)]*,[^)]*\)')
      THEN t.best_used_for
    ELSE _alias_union_tokens(t.best_used_for, s.draft_best)
  END,
  not_enough_for = CASE
    WHEN regexp_matches(coalesce(t.not_enough_for, ''), '\([^)]*,[^)]*\)')
     AND NOT regexp_matches(coalesce(s.draft_nef, ''), '\([^)]*,[^)]*\)')
     AND trim(s.draft_nef) <> ''
      THEN s.draft_nef
    WHEN regexp_matches(coalesce(t.not_enough_for, ''), '\([^)]*,[^)]*\)')
      THEN t.not_enough_for
    WHEN regexp_matches(coalesce(s.draft_nef, ''), '\([^)]*,[^)]*\)')
      THEN t.not_enough_for
    ELSE _alias_union_tokens(t.not_enough_for, s.draft_nef)
  END,
  seen_at = greatest(t.seen_at, s.draft_seen_at)
WHEN NOT MATCHED THEN
  INSERT (src_table, aliases, best_used_for, not_enough_for, seen_at)
  VALUES (
    s.src_table,
    _alias_union_tokens('', s.draft_aliases),
    s.draft_best,
    s.draft_nef,
    s.draft_seen_at
  );
-- Orphan-только-в-бою не удаляем (C2/§3.99: unmatched-by-source DELETE запрещён).

MERGE INTO :"battle_measure" t
USING _promote_measure_src s
ON (t.src_table = s.src_table AND t.measure = s.measure)
WHEN MATCHED THEN UPDATE SET
  aliases = _alias_union_tokens(t.aliases, s.draft_aliases),
  seen_at = greatest(t.seen_at, s.draft_seen_at)
WHEN NOT MATCHED THEN
  INSERT (src_table, measure, aliases, seen_at)
  VALUES (
    s.src_table,
    s.measure,
    _alias_union_tokens('', s.draft_aliases),
    s.draft_seen_at
  );

-- ── 4) Гейты fail-closed (до COMMIT) ─────────────────────────────────────────
-- (a) число строк боя не уменьшилось
SELECT count(*)::BIGINT AS n FROM :"battle_table";
\gset after_ent_rows_
SELECT count(*)::BIGINT AS n FROM :"entity_snap";
\gset snap_ent_rows_
SELECT count(*)::BIGINT AS n FROM :"battle_measure";
\gset after_meas_rows_
SELECT count(*)::BIGINT AS n FROM :"measure_snap";
\gset snap_meas_rows_

SELECT (:after_ent_rows_n >= :snap_ent_rows_n
    AND :after_meas_rows_n >= :snap_meas_rows_n) AS ok;
\gset gate_a_

\if :gate_a_ok
\else
SELECT error(
  'wiki_alias_promote GATE (a): строк боя уменьшилось '
  || '(entity ' || :snap_ent_rows_n || '→' || :after_ent_rows_n
  || ', measure ' || :snap_meas_rows_n || '→' || :after_meas_rows_n
  || '). Транзакция не фиксируется; откат из снапшота — блок внизу файла.'
);
\endif

-- (b) DISTINCT токены aliases боя не сжались относительно снапшота
SELECT count(DISTINCT trim(tok))::BIGINT AS n
  FROM :"battle_table" b,
       unnest(regexp_split_to_array(coalesce(b.aliases, ''), ',| [|] ')) u(tok)
 WHERE trim(tok) <> '';
\gset after_tok_
SELECT count(DISTINCT trim(tok))::BIGINT AS n
  FROM :"entity_snap" s,
       unnest(regexp_split_to_array(coalesce(s.aliases, ''), ',| [|] ')) u(tok)
 WHERE trim(tok) <> '';
\gset snap_tok_
SELECT count(DISTINCT trim(tok))::BIGINT AS n
  FROM :"battle_measure" b,
       unnest(regexp_split_to_array(coalesce(b.aliases, ''), ',| [|] ')) u(tok)
 WHERE trim(tok) <> '';
\gset after_mtok_
SELECT count(DISTINCT trim(tok))::BIGINT AS n
  FROM :"measure_snap" s,
       unnest(regexp_split_to_array(coalesce(s.aliases, ''), ',| [|] ')) u(tok)
 WHERE trim(tok) <> '';
\gset snap_mtok_

SELECT (:after_tok_n >= :snap_tok_n
    AND :after_mtok_n >= :snap_mtok_n) AS ok;
\gset gate_b_

\if :gate_b_ok
\else
SELECT error(
  'wiki_alias_promote GATE (b): DISTINCT токены aliases сжались '
  || '(entity ' || :snap_tok_n || '→' || :after_tok_n
  || ', measure ' || :snap_mtok_n || '→' || :after_mtok_n
  || '). Транзакция не фиксируется; откат из снапшота — блок внизу файла. HOW_NOT_TO §3.99.'
);
\endif

-- (c) aliases не стал пустым из непустого
SELECT count(*)::BIGINT AS n
  FROM :"battle_table" t
  JOIN :"entity_snap" s ON s.src_table = t.src_table
 WHERE coalesce(s.aliases, '') <> ''
   AND coalesce(t.aliases, '') = '';
\gset empty_ent_
SELECT count(*)::BIGINT AS n
  FROM :"battle_measure" t
  JOIN :"measure_snap" s
    ON s.src_table = t.src_table AND s.measure = t.measure
 WHERE coalesce(s.aliases, '') <> ''
   AND coalesce(t.aliases, '') = '';
\gset empty_meas_

SELECT (:empty_ent_n = 0 AND :empty_meas_n = 0) AS ok;
\gset gate_c_

\if :gate_c_ok
\else
SELECT error(
  'wiki_alias_promote GATE (c): aliases стал пустым из непустого '
  || '(entity ' || :empty_ent_n || ', measure ' || :empty_meas_n
  || '). Транзакция не фиксируется; откат из снапшота — блок внизу файла.'
);
\endif

-- (d) ПОСТРОЧНО: токены снапшота ⊆ токенов боя по каждому ключу (красная pm3:
-- глобальный DISTINCT из (b) компенсируется чужими строками, полстроки потерять можно)
SELECT count(*)::BIGINT AS n
  FROM :"entity_snap" s
  JOIN :"battle_table" t ON t.src_table = s.src_table
 WHERE NOT list_has_all(
     list_transform(coalesce(regexp_split_to_array(coalesce(t.aliases, ''), ',| [|] '), []::VARCHAR[]), x -> trim(x)),
     list_filter(list_transform(coalesce(regexp_split_to_array(coalesce(s.aliases, ''), ',| [|] '), []::VARCHAR[]), x -> trim(x)), x -> x <> ''));
\gset sub_ent_
SELECT count(*)::BIGINT AS n
  FROM :"measure_snap" s
  JOIN :"battle_measure" t ON t.src_table = s.src_table AND t.measure = s.measure
 WHERE NOT list_has_all(
     list_transform(coalesce(regexp_split_to_array(coalesce(t.aliases, ''), ',| [|] '), []::VARCHAR[]), x -> trim(x)),
     list_filter(list_transform(coalesce(regexp_split_to_array(coalesce(s.aliases, ''), ',| [|] '), []::VARCHAR[]), x -> trim(x)), x -> x <> ''));
\gset sub_meas_

SELECT (:sub_ent_n = 0 AND :sub_meas_n = 0) AS ok;
\gset gate_d_

\if :gate_d_ok
\else
SELECT error(
  'wiki_alias_promote GATE (d): построчная потеря токенов '
  || '(entity ' || :sub_ent_n || ', measure ' || :sub_meas_n
  || ' строк с неполным подмножеством). Транзакция не фиксируется; '
  || 'откат из снапшота — блок внизу файла. HOW_NOT_TO §3.99.'
);
\endif

COMMIT;

-- ── 5) Счётчики ПОСЛЕ (+ матрица (г): frozen heal/dirty/empty, insert-pattern) ─
-- healed/dirty/empty — eligibility по snap×draft (не сверка поля боя после MERGE);
-- after-бой участвует только в insert_with_pattern (бой ∉ snap ∧ паттерн).
SELECT 'after' AS phase,
       (SELECT count(*) FROM :"battle_table") AS battle_entity_rows,
       (SELECT count(*) FROM :"battle_measure") AS battle_measure_rows,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(' | ' IN coalesce(aliases, '')) > 0) AS battle_aliases_pipe,
       (SELECT count(*) FROM :"battle_table"
         WHERE position(', ' IN coalesce(aliases, '')) > 0
           AND position(' | ' IN coalesce(aliases, '')) = 0) AS battle_aliases_comma_only,
       (SELECT count(DISTINCT trim(tok))
          FROM :"battle_table" b,
               unnest(regexp_split_to_array(coalesce(b.aliases, ''), ',| [|] ')) u(tok)
         WHERE trim(tok) <> '') AS battle_alias_tokens_distinct,
       (SELECT count(DISTINCT trim(tok))
          FROM :"battle_measure" b,
               unnest(regexp_split_to_array(coalesce(b.aliases, ''), ',| [|] ')) u(tok)
         WHERE trim(tok) <> '') AS battle_measure_tokens_distinct,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.best_used_for, ''), '\([^)]*,[^)]*\)')
           AND NOT regexp_matches(coalesce(d.best_used_for, ''), '\([^)]*,[^)]*\)')
           AND trim(coalesce(d.best_used_for, '')) <> '') AS best_frozen_healed,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.best_used_for, ''), '\([^)]*,[^)]*\)')
           AND regexp_matches(coalesce(d.best_used_for, ''), '\([^)]*,[^)]*\)')) AS best_frozen_dirty_draft,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.best_used_for, ''), '\([^)]*,[^)]*\)')
           AND trim(coalesce(d.best_used_for, '')) = '') AS best_frozen_empty_draft,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.not_enough_for, ''), '\([^)]*,[^)]*\)')
           AND NOT regexp_matches(coalesce(d.not_enough_for, ''), '\([^)]*,[^)]*\)')
           AND trim(coalesce(d.not_enough_for, '')) <> '') AS nef_frozen_healed,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.not_enough_for, ''), '\([^)]*,[^)]*\)')
           AND regexp_matches(coalesce(d.not_enough_for, ''), '\([^)]*,[^)]*\)')) AS nef_frozen_dirty_draft,
       (SELECT count(*)
          FROM :"entity_snap" s
          JOIN :"draft_table" d ON d.src_table = s.src_table
         WHERE regexp_matches(coalesce(s.not_enough_for, ''), '\([^)]*,[^)]*\)')
           AND trim(coalesce(d.not_enough_for, '')) = '') AS nef_frozen_empty_draft,
       (SELECT count(*)
          FROM :"battle_table" t
          LEFT JOIN :"entity_snap" s ON s.src_table = t.src_table
         WHERE s.src_table IS NULL
           AND (regexp_matches(coalesce(t.best_used_for, ''), '\([^)]*,[^)]*\)')
                OR regexp_matches(coalesce(t.not_enough_for, ''), '\([^)]*,[^)]*\)'))) AS insert_with_pattern,
       (SELECT count(*)
          FROM :"draft_table" d
         WHERE NOT EXISTS (SELECT 1 FROM wiki_entity_facts f
                            WHERE f.src_table = d.src_table)) AS orphan_skipped;

\echo promote: OK. Дальше — wiki_alias_migrate_sep.sql (residual ', '→' | '), затем Solr из боя.

-- =============================================================================
-- ОТКАТ (раскомментировать и выполнить вручную при красном гейте / после COMMIT):
--
-- BEGIN;
-- DELETE FROM search_entity_alias;
-- INSERT INTO search_entity_alias SELECT * FROM search_entity_alias_pre_promote_YYYYMMDD;
-- DELETE FROM search_measure_alias;
-- INSERT INTO search_measure_alias SELECT * FROM search_measure_alias_pre_promote_YYYYMMDD;
-- COMMIT;
-- VACUUM (REFRESH_TABLE) search_entity_alias;
-- -- затем пересобрать Solr из боя.
--
-- Имена таблиц подставить из фактических -v battle_table / battle_measure / snap_suffix.
-- =============================================================================
