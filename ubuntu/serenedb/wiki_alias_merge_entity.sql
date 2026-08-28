\set ON_ERROR_STOP on
-- Запись сущностей и величин после разбора ответа модели. Доки: read_json; MERGE INTO.
MERGE INTO :alias_table t
USING (
  SELECT src_table, aliases, best_used_for, not_enough_for
  FROM read_json(:'rows_path',
    columns := {src_table:'VARCHAR', aliases:'VARCHAR',
                best_used_for:'VARCHAR', not_enough_for:'VARCHAR'})
  WHERE coalesce(aliases,'') <> ''
) n
ON (t.src_table = n.src_table)
WHEN MATCHED AND coalesce(t.aliases,'') = '' THEN
  UPDATE SET aliases = n.aliases, best_used_for = n.best_used_for,
             not_enough_for = n.not_enough_for, seen_at = now()
WHEN NOT MATCHED THEN
  INSERT (src_table, aliases, best_used_for, not_enough_for, seen_at)
  VALUES (n.src_table, n.aliases, n.best_used_for, n.not_enough_for, now());
MERGE INTO :measure_table t
USING (
  SELECT src_table, measure, aliases
  FROM read_json(:'measures_path',
    columns := {src_table:'VARCHAR', measure:'VARCHAR', aliases:'VARCHAR'})
  WHERE coalesce(aliases,'') <> ''
) n
ON (t.src_table = n.src_table AND t.measure = n.measure)
WHEN MATCHED AND coalesce(t.aliases,'') = '' THEN
  UPDATE SET aliases = n.aliases, seen_at = now()
WHEN NOT MATCHED THEN
  INSERT (src_table, measure, aliases, seen_at)
  VALUES (n.src_table, n.measure, n.aliases, now());
