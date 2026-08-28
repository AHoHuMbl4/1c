\set ON_ERROR_STOP on
-- Отметка попытки day-basis. Доки: read_json; MERGE INTO.
MERGE INTO :fork_label_table t
USING (
  SELECT fork_key, src, '' AS label, now() AS seen_at
  FROM read_json(:'flat_path', columns := {fork_key:'VARCHAR', src:'VARCHAR'})
) p
ON (t.fork_key = p.fork_key AND t.src = p.src)
WHEN MATCHED AND coalesce(t.label, '') = '' THEN UPDATE SET seen_at = p.seen_at
WHEN NOT MATCHED THEN INSERT;
