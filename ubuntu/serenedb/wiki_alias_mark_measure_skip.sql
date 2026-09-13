\set ON_ERROR_STOP on
-- Пустышки величин после осечки (добор). Доки: read_json › Loading JSON;
-- MERGE INTO (Sql › Statements › MERGE INTO) — как mark_attempt в branch_alias.sh:
-- обновляет seen_at существующей пустышки, живую подпись не трогает.
MERGE INTO :measure_table t
USING (
  SELECT entity AS src_table, trim(q) AS measure, '' AS aliases, now() AS seen_at
  FROM read_json(:'pay_path',
    columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'}),
       unnest(str_split(quantities, ',')) AS x(q)
  WHERE trim(q) <> ''
) p
ON (t.src_table = p.src_table AND t.measure = p.measure)
WHEN MATCHED AND coalesce(t.aliases, '') = '' THEN UPDATE SET seen_at = p.seen_at
WHEN NOT MATCHED THEN INSERT;
