\set ON_ERROR_STOP on
-- Отчёт качества init-фазы: одна строка key=value в journal (plan-quality-report v2).
-- Доки: Regular Expressions › regexp_split_to_array; Expressions › Subqueries
--       › EXISTS; Aggregate Functions (FILTER). Вывод — конкатенация || с
--       ::VARCHAR: printf с BIGINT в SereneDB даёт «invalid format
--       specifier» (живая проба 15.09).
-- Канон токенов aliases: regexp_split_to_array ',| [|] ' (wiki_alias_promote).
-- Потоки (need_event): EXISTS search_refcols.target_src — как
-- wiki_alias_select_entity_batch (не колонка facts, не имена мер).
-- эвристика event-аффиксов (только окончания языка, не слова базы): -али -или -айся -айте -уйте -ируй
-- (gap оптимистичен к ложным «глаголам» — сигнал копать, не вердикт).
WITH ent AS (
  SELECT a.src_table,
         coalesce(a.aliases, '') AS aliases,
         coalesce(a.best_used_for, '') AS best_used_for,
         coalesce(a.not_enough_for, '') AS not_enough_for,
         EXISTS (
           SELECT 1 FROM search_refcols r WHERE r.target_src = a.src_table
         ) AS has_flows
    FROM :alias_table a
),
base AS (
  SELECT count(*)::BIGINT AS entities,
         count(*) FILTER (WHERE aliases = '')::BIGINT AS empty_aliases,
         count(*) FILTER (WHERE best_used_for = '')::BIGINT AS empty_best,
         count(*) FILTER (WHERE not_enough_for = '')::BIGINT AS empty_nef,
         count(*) FILTER (WHERE has_flows)::BIGINT AS need_event,
         count(*) FILTER (
           WHERE has_flows
             AND EXISTS (
               SELECT 1
                 FROM unnest(regexp_split_to_array(aliases, ',| [|] ')) u(tok)
                WHERE trim(tok) <> ''
                  -- токен длины суффикса — сам суффикс/союз, не форма
                  AND length(trim(tok)) > 3
                  AND lower(trim(tok)) ~ '(али|или|айся|айте|уйте|ируй)$'
             )
         )::BIGINT AS has_event
    FROM ent
),
meas AS (
  SELECT count(*)::BIGINT AS measures,
         count(*) FILTER (WHERE coalesce(aliases, '') <> '')::BIGINT
           AS measures_nonempty,
         (SELECT count(*)::BIGINT
            FROM :measure_table m,
                 unnest(regexp_split_to_array(coalesce(m.aliases, ''),
                                              ',| [|] ')) u(tok)
           WHERE trim(tok) <> '') AS measure_tokens
    FROM :measure_table
)
-- Конкатенация || с кастами — канон репо (collision_round); printf с BIGINT
-- в SereneDB даёт «invalid format specifier» (живая проба 15.09, ABORT-ветка).
SELECT 'entities=' || b.entities::VARCHAR
    || ' empty_aliases=' || b.empty_aliases::VARCHAR
    || ' empty_best=' || b.empty_best::VARCHAR
    || ' empty_nef=' || b.empty_nef::VARCHAR
    || ' measures=' || m.measures::VARCHAR
    || ' measures_nonempty=' || m.measures_nonempty::VARCHAR
    || ' measure_tokens=' || m.measure_tokens::VARCHAR
    || ' need_event=' || b.need_event::VARCHAR
    || ' has_event=' || b.has_event::VARCHAR
    || ' event_gap=' || (b.need_event - b.has_event)::VARCHAR
FROM base b, meas m;
