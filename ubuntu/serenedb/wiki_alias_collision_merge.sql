\set ON_ERROR_STOP on
-- Обновление алиасов после разведения столкновений. Доки: read_json; MERGE INTO
-- (RETURNING — число затронутых строк для probe ok/failed).
MERGE INTO :alias_table t
USING (
  SELECT src_table, aliases, best_used_for, not_enough_for
  FROM read_json(:'rows_path',
    columns := {src_table:'VARCHAR', aliases:'VARCHAR',
                best_used_for:'VARCHAR', not_enough_for:'VARCHAR'})
) n
ON (t.src_table = n.src_table)
WHEN MATCHED THEN
  UPDATE SET aliases = n.aliases, best_used_for = n.best_used_for,
             not_enough_for = n.not_enough_for, seen_at = now()
RETURNING t.src_table;
