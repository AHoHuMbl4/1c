\set ON_ERROR_STOP on
-- Пачка day-basis: pay для модели + flat для отметки попытки. Доки: struct_pack; list.
WITH need AS (
  SELECT c.fork_key, c.src_set, c.measure_ctx
  FROM :fork_class_table c
  WHERE c.src_set <> ''
    AND NOT EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE trim(x.s, '{} ') NOT IN (:day_basis_ids))
    AND EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE trim(x.s, '{} ') IN (:day_basis_ids))
    AND EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE NOT EXISTS (
        SELECT 1 FROM :fork_label_table l
        WHERE l.fork_key = c.fork_key AND l.src = trim(x.s, '{} ')
          AND (coalesce(l.label, '') <> ''
               OR l.seen_at > now() - INTERVAL :fork_retry_h HOUR)))
  ORDER BY c.fork_key
  LIMIT :fork_batch),
raw_srcs AS (
  SELECT n.fork_key, n.measure_ctx, trim(x.s, '{} ') AS src
  FROM need n, unnest(str_split(n.src_set, ',')) AS x(s)
  WHERE NOT EXISTS (
    SELECT 1 FROM :fork_label_table l
    WHERE l.fork_key = n.fork_key AND l.src = trim(x.s, '{} ')
      AND (coalesce(l.label, '') <> ''
           OR l.seen_at > now() - INTERVAL :fork_retry_h HOUR))),
srcs AS (SELECT fork_key, measure_ctx, src FROM raw_srcs),
pay AS (
  SELECT to_json(list(struct_pack(fork_key := fork_key, measure := measure,
                                  sources := items))) AS j
  FROM (SELECT s.fork_key, max(s.measure_ctx) AS measure,
               list(struct_pack(src := s.src, title := s.src,
                                branchKind := 'day_basis_window',
                                scope := CASE s.src
                                  WHEN 'calendar_days' THEN 'all calendar dates in the period window'
                                  WHEN 'working_days' THEN 'only dates marked working in the calendar register'
                                  ELSE '' END)
                    ORDER BY s.src) AS items
        FROM srcs s
        GROUP BY s.fork_key
        ORDER BY s.fork_key) z),
flat AS (
  SELECT to_json(list(struct_pack(fork_key := fork_key, src := src))) AS j
  FROM srcs)
SELECT coalesce((SELECT j FROM pay), '[]') || chr(9) ||
       coalesce((SELECT j FROM flat), '[]');
