\set ON_ERROR_STOP on

-- Словарь относительных окон (form_id → фразы) → search_meta.
-- Источник — JSON-файл такта (язык/фразы = данные, не код ask).
-- Движок читает файл сам (read_text); путь обязан быть виден процессу serened
-- (обычно копия в CSV_DIR — тот же приём, что wiki_alias / poc_load).
-- Доки: cookbook/file_formats/read_file#read_text;
--       data_import_and_export/json/json_functions (json_valid, json_type, json_keys, json).

DELETE FROM search_meta WHERE k = 'period_relative_forms';

INSERT INTO search_meta
SELECT 'period_relative_forms', json(content)::VARCHAR
FROM read_text(:'period_forms_path')
WHERE json_valid(content)
  AND json_type(content) = 'OBJECT'
  AND len(json_keys(content::JSON)) > 0;

SELECT CASE
  WHEN (SELECT count(*) FROM search_meta WHERE k = 'period_relative_forms') <> 1
  THEN error('period_relative_forms: файл не прочитан или словарь пуст/не OBJECT')
END;

SELECT 'period_relative_forms' AS step,
       (SELECT len(json_keys(v::JSON))
          FROM search_meta WHERE k = 'period_relative_forms') AS forms;
