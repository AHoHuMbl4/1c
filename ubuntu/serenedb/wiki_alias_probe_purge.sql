\set ON_ERROR_STOP on
-- Самоочистка памяти разведения при смене версии генератора (Р5 → автомат).
-- Остаются: result='ok' любой версии; result='failed' текущей :gen_ver.
-- Уходят: failed чужой версии и ВСЕ пустые (result='' — kill/stall/легаси).
-- 🔴 Параллельный ручной прогон с той же probe может потерять in-flight
-- отметку — юниты oneshot; гонка документируется, не закрывается блокировкой.
-- Вывод: одна колонка deleted || chr(9) || failed_left (psql -tA; канон collision_round).
-- Доки: Sql › Statements › DELETE; CTE; Sql › Functions › String Functions.
WITH doomed AS (
  SELECT alias, entities_fp
  FROM :probe_table
  WHERE NOT (
    coalesce(result, '') = 'ok'
    OR (coalesce(result, '') = 'failed' AND coalesce(gen_ver, '') = :'gen_ver')
  )
),
del AS (
  DELETE FROM :probe_table p
  WHERE EXISTS (
    SELECT 1 FROM doomed d
    WHERE d.alias = p.alias AND d.entities_fp = p.entities_fp)
  RETURNING 1
)
SELECT (SELECT count(*) FROM del) || chr(9) ||
       (SELECT count(*) FROM :probe_table WHERE coalesce(result, '') = 'failed');
