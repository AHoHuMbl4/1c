-- Метрика коллизий памяти выбора (план §8 шаг 6, аудит §13).
-- Класс = class_key (набор прочтений + величина + окно). Коллизия: у одного
-- class_key активные записи с разными ветками (chosen_src/measure/axis) у
-- разных user_hash. Такой класс не применяется (shadow/clarify).
--
-- Запуск (postgres, rw): psql "$DSN" -f ask_choice_memory_collisions.sql
-- Живые данные накапливаются сами; синтетика — test_ask_choice_memory.py.

-- Сводка по базе
SELECT current_database() AS db_name,
       count(*) AS active_rows,
       count(DISTINCT class_key) AS classes,
       count(DISTINCT user_hash) AS users
FROM ask_choice_memory
WHERE active AND NOT cancelled;

-- Классы с коллизией (≥2 различных веток среди активных записей)
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

-- Связь с журналом: последние исходы B/C по классу (fork_keys как прокси)
SELECT j.class_key, j.outcome, j.fork_outcome, count(*) AS n
FROM (
  SELECT user_hash,
         fork_keys AS class_key,
         outcome, fork_outcome
  FROM ask_journal
  WHERE fork_outcome IN ('B', 'C')
) j
WHERE j.class_key IN (
  SELECT class_key FROM ask_choice_memory WHERE active AND NOT cancelled
)
GROUP BY 1, 2, 3
ORDER BY 1, 4 DESC;
