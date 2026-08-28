\set ON_ERROR_STOP on
-- Только величины (добор; алиасы сущности не трогаем). Доки: read_json; MERGE INTO.
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
