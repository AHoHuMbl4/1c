\set ON_ERROR_STOP on
-- =============================================================================
-- H4: лечение испорченных collision-строк из снапшота (план 13.09 вечер).
--
-- 🔴 ЗАПУСКАТЬ ТОЛЬКО ПО СЛОВУ ВЛАДЕЛЬЦА / ОРКЕСТРАТОРА.
--    Когда: после выката V2+G8b (мета-стоп в pick), ПЕРЕД повторным
--    collision-прогоном. Этот файл — заготовка; сессия G8c его НЕ исполняет
--    и к боевой базе не подключается.
--
-- Цель: в строках, где развод оставил обрубки aliases («номенклатуры | товара»,
--    «цен | и»), восстановить aliases / best_used_for / not_enough_for из
--    полного снапшота ДО. seen_at НЕ трогаем (остаётся свежим — init-цикл
--    не сочтёт строку нетронутой). Хорошие разведённые (≥3 полных слова)
--    не трогаем. Повторный запуск — 0 изменений (идемпотентность).
--
-- Таблицы — только через psql-переменные (п.0, без хардкода боевых имён):
--   :alias_table  — текущий словарь
--   :snap_table   — снапшот ДО (имя передаётся снаружи)
--   :since        — TIMESTAMP-отсечка: t.seen_at >= since (момент развода)
--
-- Пример (после слова владельца):
--   psql "$DSN" \
--     -v alias_table=alias_sandbox \
--     -v snap_table=alias_sandbox_pre_v2 \
--     -v since="'2026-09-13 00:00:00'" \
--     -f wiki_alias_recover_collision.sql
--
-- Доки: Text string_split / length; List len / list_filter / list_transform /
--       list_bool_and; UPDATE … FROM (Update Using Joins).
--
-- G8c2: счётчик элементов dual (position ' | ' → pipe, иначе ', ') —
--       потому что snap хранит СТАРЫЙ формат ', ' (до миграции).
-- =============================================================================

-- Критерий испорченности t (без snap):
--   stub(t) := n_elems(t) < 3
--           OR (aliases непусты и все элементы после trim имеют length < 4)
-- Критерий лечения (t JOIN s по src_table):
--   t.seen_at >= :since
--   AND stub(t)
--   AND ( n_elems(s) >= 3 OR n_elems(s) > n_elems(t) )
-- где n_elems(x) = len(CASE WHEN position(' | ' IN coalesce(x,'')) > 0
--                           THEN str_split(x, ' | ')
--                           ELSE str_split(x, ', ') END)
-- Ловит «номенклатуры | товара» (n=2) и «цен | и» (все короткие);
-- хорошие разводы с n≥3 и хотя бы одним словом ≥4 символов — вне критерия.
-- Короткость элементов у t — по ' | ' (текущий формат после V2); счётчик — dual.

-- 1) SELECT-отчёт: сколько подходит + первые 20 (src_table, текущее, из snap).
SELECT count(*)::BIGINT AS n_to_recover
  FROM :alias_table t
  JOIN :snap_table s ON s.src_table = t.src_table
 WHERE t.seen_at >= CAST(:'since' AS TIMESTAMP)
   AND (
         len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                  THEN str_split(coalesce(t.aliases, ''), ' | ')
                  ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3
      OR (
           coalesce(t.aliases, '') <> ''
           AND list_bool_and(
                 list_transform(
                   str_split(t.aliases, ' | '),
                   x -> length(trim(x)) < 4))
         )
       )
   AND (
         len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                  THEN str_split(coalesce(s.aliases, ''), ' | ')
                  ELSE str_split(coalesce(s.aliases, ''), ', ') END) >= 3
      OR len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                  THEN str_split(coalesce(s.aliases, ''), ' | ')
                  ELSE str_split(coalesce(s.aliases, ''), ', ') END)
           > len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                      THEN str_split(coalesce(t.aliases, ''), ' | ')
                      ELSE str_split(coalesce(t.aliases, ''), ', ') END)
       );

SELECT t.src_table,
       t.aliases AS cur_aliases,
       s.aliases AS snap_aliases,
       len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                THEN str_split(coalesce(t.aliases, ''), ' | ')
                ELSE str_split(coalesce(t.aliases, ''), ', ') END) AS cur_n,
       len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                THEN str_split(coalesce(s.aliases, ''), ' | ')
                ELSE str_split(coalesce(s.aliases, ''), ', ') END) AS snap_n
  FROM :alias_table t
  JOIN :snap_table s ON s.src_table = t.src_table
 WHERE t.seen_at >= CAST(:'since' AS TIMESTAMP)
   AND (
         len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                  THEN str_split(coalesce(t.aliases, ''), ' | ')
                  ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3
      OR (
           coalesce(t.aliases, '') <> ''
           AND list_bool_and(
                 list_transform(
                   str_split(t.aliases, ' | '),
                   x -> length(trim(x)) < 4))
         )
       )
   AND (
         len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                  THEN str_split(coalesce(s.aliases, ''), ' | ')
                  ELSE str_split(coalesce(s.aliases, ''), ', ') END) >= 3
      OR len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                  THEN str_split(coalesce(s.aliases, ''), ' | ')
                  ELSE str_split(coalesce(s.aliases, ''), ', ') END)
           > len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                      THEN str_split(coalesce(t.aliases, ''), ' | ')
                      ELSE str_split(coalesce(t.aliases, ''), ', ') END)
       )
 ORDER BY t.src_table
 LIMIT 20;

-- 2) Лечение: только aliases / best_used_for / not_enough_for; seen_at не трогаем.
UPDATE :alias_table t
SET aliases = s.aliases,
    best_used_for = s.best_used_for,
    not_enough_for = s.not_enough_for
FROM :snap_table s
WHERE t.src_table = s.src_table
  AND t.seen_at >= CAST(:'since' AS TIMESTAMP)
  AND (
        len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                 THEN str_split(coalesce(t.aliases, ''), ' | ')
                 ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3
     OR (
          coalesce(t.aliases, '') <> ''
          AND list_bool_and(
                list_transform(
                  str_split(t.aliases, ' | '),
                  x -> length(trim(x)) < 4))
        )
      )
  AND (
        len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                 THEN str_split(coalesce(s.aliases, ''), ' | ')
                 ELSE str_split(coalesce(s.aliases, ''), ', ') END) >= 3
     OR len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                 THEN str_split(coalesce(s.aliases, ''), ' | ')
                 ELSE str_split(coalesce(s.aliases, ''), ', ') END)
          > len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                     THEN str_split(coalesce(t.aliases, ''), ' | ')
                     ELSE str_split(coalesce(t.aliases, ''), ', ') END)
      );

-- 3) Контроль после: сколько ещё отличается от snap по трём полям среди
--    строк, попавших под критерий лечения ДО (после UPDATE критерий пуст —
--    считаем «исправленные» как совпавшие с snap при свежем seen_at и
--    бывшем stub-условии уже не применимо → отдельный счётчик stub-остатка).

-- Исправленные = join со snap, текст aliases совпал, seen_at всё ещё >= since,
-- и snap был качественным (≥3). Прокси приёмки после прогона.
SELECT 'recovered_now_match_snap' AS metric, count(*)::BIGINT AS n
  FROM :alias_table t
  JOIN :snap_table s ON s.src_table = t.src_table
 WHERE t.seen_at >= CAST(:'since' AS TIMESTAMP)
   AND coalesce(t.aliases, '') = coalesce(s.aliases, '')
   AND coalesce(t.best_used_for, '') = coalesce(s.best_used_for, '')
   AND coalesce(t.not_enough_for, '') = coalesce(s.not_enough_for, '')
   AND len(CASE WHEN position(' | ' IN coalesce(s.aliases, '')) > 0
                THEN str_split(coalesce(s.aliases, ''), ' | ')
                ELSE str_split(coalesce(s.aliases, ''), ', ') END) >= 3;

-- Оставшиеся испорченные (критерий stub БЕЗ snap-условия) — должно быть 0
-- либо явный список исключений.
SELECT 'remaining_stub' AS metric, count(*)::BIGINT AS n
  FROM :alias_table t
 WHERE t.seen_at >= CAST(:'since' AS TIMESTAMP)
   AND (
         len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                  THEN str_split(coalesce(t.aliases, ''), ' | ')
                  ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3
      OR (
           coalesce(t.aliases, '') <> ''
           AND list_bool_and(
                 list_transform(
                   str_split(t.aliases, ' | '),
                   x -> length(trim(x)) < 4))
         )
       );

SELECT t.src_table, t.aliases AS remaining_stub_aliases
  FROM :alias_table t
 WHERE t.seen_at >= CAST(:'since' AS TIMESTAMP)
   AND (
         len(CASE WHEN position(' | ' IN coalesce(t.aliases, '')) > 0
                  THEN str_split(coalesce(t.aliases, ''), ' | ')
                  ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3
      OR (
           coalesce(t.aliases, '') <> ''
           AND list_bool_and(
                 list_transform(
                   str_split(t.aliases, ' | '),
                   x -> length(trim(x)) < 4))
         )
       )
 ORDER BY t.src_table
 LIMIT 50;
