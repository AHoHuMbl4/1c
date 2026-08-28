\set ON_ERROR_STOP on
-- Итог словаря + публикация inverted. Доки: VACUUM › REFRESH_*; inverted lifecycle.
\pset fieldsep ' | '
\pset tuples_only on
SELECT 'алиасов в базе', count(*) FROM :alias_table
UNION ALL SELECT 'из них ПУСТЫХ (модель не ответила)', count(*) FROM :alias_table
  WHERE coalesce(aliases,'') = ''
UNION ALL SELECT 'величин в словаре', count(*) FROM :measure_table
  WHERE coalesce(aliases,'') <> ''
UNION ALL SELECT 'пустышек величин (модель не ответила)', count(*) FROM :measure_table
  WHERE coalesce(aliases,'') = '';
VACUUM (REFRESH_TABLE) :alias_table;
