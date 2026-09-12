\set ON_ERROR_STOP on
-- Дописать подтверждённые алиасы в основной словарь (не перезаписывает существующие).
-- Вход: rows_path — JSON {src_table, aliases} только для подтверждённых связей.
-- Доки: read_json; MERGE INTO.
MERGE INTO :alias_table t
USING (
  SELECT src_table, aliases
  FROM read_json(:'rows_path',
    columns := {src_table:'VARCHAR', aliases:'VARCHAR'})
  WHERE coalesce(aliases,'') <> ''
) n
ON (t.src_table = n.src_table)
WHEN MATCHED THEN
  UPDATE SET aliases = CASE
    WHEN position(lower(n.aliases) IN lower(coalesce(t.aliases,''))) > 0
      THEN t.aliases
    WHEN coalesce(t.aliases,'') = ''
      THEN n.aliases
    ELSE t.aliases || ' | ' || n.aliases
  END,
  seen_at = now()
WHEN NOT MATCHED THEN
  INSERT (src_table, aliases, seen_at)
  VALUES (n.src_table, n.aliases, now());
