\set ON_ERROR_STOP on
-- Пустышки после осечки модели (первый проход). Доки: read_json › Loading JSON.
INSERT INTO :alias_table
  SELECT entity, '', '', '', now()
  FROM read_json(:'pay_path',
    columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'})
  WHERE entity NOT IN (SELECT src_table FROM :alias_table);
INSERT INTO :measure_table
  SELECT entity, trim(q), '', now()
  FROM read_json(:'pay_path',
    columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'}),
       unnest(str_split(quantities, ',')) AS x(q)
  WHERE trim(q) <> ''
    AND NOT EXISTS (SELECT 1 FROM :measure_table a
                    WHERE a.src_table = entity AND a.measure = trim(q));
