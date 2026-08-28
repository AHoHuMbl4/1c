\set ON_ERROR_STOP on
-- Подписи day-basis после модели. Доки: read_json; MERGE INTO.
MERGE INTO :fork_label_table t
USING (
  SELECT fork_key, src, label, now() AS seen_at
  FROM read_json(:'rows_path',
    columns := {fork_key:'VARCHAR', src:'VARCHAR', label:'VARCHAR'})
) n
ON (t.fork_key = n.fork_key AND t.src = n.src)
WHEN MATCHED THEN UPDATE SET label = n.label, seen_at = n.seen_at
WHEN NOT MATCHED THEN INSERT;
