-- Замер коллизий памяти выбора (PLAN_ANSWER_CONTRACT §8 шаг 6).
-- Коллизия: у одного class_key среди active AND NOT cancelled есть
-- ≥2 различных троек (chosen_src, chosen_measure, chosen_axis).
-- class_key в коде = sha256(readings|measure_ctx|window_fp); выбран src
-- в ключ не входит. Применение чужого выбора блокируется
-- (user_hash + class_key) и probe_memory_apply(reason=collision).
--
-- Доки: Sql › Query syntax › GROUP BY;
--       Sql › Functions › Aggregate Functions › DISTINCT;
--       Sql › Query syntax › WITH;
--       Sql › Query syntax › FROM / JOIN.
--
-- Запуск (только чтение): psql "$DSN" -f ask_choice_memory_collisions_measure.sql
-- Роль serene_ro: SELECT на ask_choice_memory; ask_journal — если GRANT есть.

-- A. Объём памяти
SELECT count(*) AS memory_total,
       count(*) FILTER (WHERE active AND NOT cancelled) AS memory_active,
       count(*) FILTER (WHERE cancelled OR NOT active) AS memory_inactive,
       count(DISTINCT class_key)
         FILTER (WHERE active AND NOT cancelled) AS active_classes,
       count(DISTINCT user_hash)
         FILTER (WHERE active AND NOT cancelled) AS active_users
FROM ask_choice_memory;

-- B. Сводка коллизий по class_key
WITH branches AS (
  SELECT class_key,
         chosen_src, chosen_measure, chosen_axis,
         count(DISTINCT user_hash) AS n_users,
         count(*) AS n_rows
  FROM ask_choice_memory
  WHERE active AND NOT cancelled
  GROUP BY 1, 2, 3, 4
),
per_class AS (
  SELECT class_key,
         count(*) AS n_branches,
         sum(n_users) AS n_users_total,
         sum(n_rows) AS n_rows_total
  FROM branches
  GROUP BY 1
)
SELECT
  (SELECT count(*) FROM ask_choice_memory
   WHERE active AND NOT cancelled) AS active_rows,
  (SELECT count(*) FROM per_class) AS classes,
  (SELECT count(*) FROM per_class WHERE n_branches >= 2)
    AS collision_classes,
  (SELECT coalesce(sum(n_rows_total), 0)
   FROM per_class WHERE n_branches >= 2) AS rows_in_collision_classes,
  (SELECT coalesce(sum(n_users_total), 0)
   FROM per_class WHERE n_branches >= 2) AS users_in_collision_classes;

-- C. Распределение классов по числу веток
WITH branches AS (
  SELECT class_key, chosen_src, chosen_measure, chosen_axis
  FROM ask_choice_memory
  WHERE active AND NOT cancelled
  GROUP BY 1, 2, 3, 4
),
per_class AS (
  SELECT class_key, count(*) AS n_branches
  FROM branches
  GROUP BY 1
)
SELECT n_branches, count(*) AS n_classes
FROM per_class
GROUP BY 1
ORDER BY 1;

-- D. Классы-коллизии (детально)
WITH branches AS (
  SELECT class_key,
         chosen_src, chosen_measure, chosen_axis,
         count(DISTINCT user_hash) AS n_users,
         count(*) AS n_rows
  FROM ask_choice_memory
  WHERE active AND NOT cancelled
  GROUP BY 1, 2, 3, 4
),
coll AS (
  SELECT class_key,
         count(*) AS n_branches,
         sum(n_users) AS n_users_total,
         sum(n_rows) AS n_rows_total
  FROM branches
  GROUP BY 1
  HAVING count(*) >= 2
)
SELECT c.class_key, c.n_branches, c.n_users_total, c.n_rows_total,
       b.chosen_src, b.chosen_measure, b.chosen_axis, b.n_users
FROM coll c
JOIN branches b ON b.class_key = c.class_key
ORDER BY c.n_branches DESC, c.class_key, b.n_users DESC;

-- E. Контекст журнала (не применение памяти: в ask_journal нет колонки
-- факта применения; ASK_MEMORY_APPLY по умолчанию выключен — «применялось»
-- и «разошлось бы с ответом» здесь не считаются).
SELECT count(*) AS journal_total,
       count(*) FILTER (WHERE fork_outcome IN ('B', 'C')) AS fork_bc,
       count(*) FILTER (WHERE ticket_used) AS ticket_used_n,
       count(DISTINCT user_hash) FILTER (WHERE user_hash <> '')
         AS users_with_hash,
       min(ts) AS oldest,
       max(ts) AS newest
FROM ask_journal;
