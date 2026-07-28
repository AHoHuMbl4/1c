\set ON_ERROR_STOP on

-- ПРОВЕРКИ ДО ТАКТА. Каждая — через штатную `error()`: она даёт настоящую ошибку и
-- ненулевой код возврата, который видит вызывающий. Печатать предупреждение и идти
-- дальше нельзя — именно так данные терялись молча (`HOW_NOT_TO §2.10`).
--
-- Порядок проверок не случаен: всё, что может остановить такт, обязано сработать ДО
-- того, как `MERGE` обнулит вектор у изменившихся строк.

-- Состояние ДО живёт в базе, а не в переменной оболочки: сравнивать будет тот же движок,
-- и отпечаток переживёт рестарт движка посреди прогона.
DELETE FROM build_state WHERE k LIKE 'before_%';
INSERT INTO build_state
            SELECT now(), 'before_rows',  count(*)                            FROM search_corpus
UNION ALL   SELECT now(), 'before_src',   count(DISTINCT src_table)           FROM search_corpus
UNION ALL   SELECT now(), 'before_noemb', count(*) FILTER (WHERE emb IS NULL) FROM search_corpus
UNION ALL   SELECT now(), 'before_res',   count(*)                            FROM resolver_index;

-- 1. Индекс на месте. Без него `VACUUM (REFRESH_INDEX)` упадёт УЖЕ ПОСЛЕ `MERGE`:
--    строки окажутся в таблице и не окажутся в поиске.
SELECT CASE WHEN count(*) = 0
       THEN error('нет индекса search_idx — сначала corpus_init.sql, потом сборка') END
FROM duckdb_indexes() WHERE index_name = 'search_idx';

-- 2. Права читающих ролей. Пересозданная таблица теряет `GRANT`, и сервис молча отдаёт
--    пустоту вместо ошибки — по журналу это неотличимо от «данных нет».
SELECT CASE
  WHEN count(*) FILTER (WHERE grantee = 'serene_ro' AND table_name = 'search_corpus') = 0
       THEN error('serene_ro потерял SELECT на search_corpus — бот будет молча отвечать «ничего не нашёл»')
  WHEN count(*) FILTER (WHERE grantee = 'serene_resolver' AND table_name = 'resolver_index') = 0
       THEN error('serene_resolver потерял SELECT на resolver_index — резолвер молча перестанет разрешать слова')
  END
FROM information_schema.role_table_grants
WHERE privilege_type = 'SELECT' AND table_name IN ('search_corpus', 'resolver_index');

-- 3. Таблицы-источники существуют. Синк пересоздаёт их через `DROP`+`CREATE`, и в это
--    окно `query_table()` падает — сборка соберёт НЕПОЛНЫЙ набор, а слияние такого
--    набора вычистит живые сущности. [замер 28.07] такое наложение уже случилось.
SELECT CASE WHEN count(*) > 0
       THEN error('нет таблиц-источников (идёт синк витрины?): ' || string_agg(src_table, ', ')) END
FROM (SELECT DISTINCT src_table FROM search_sources) s
WHERE NOT EXISTS (SELECT 1 FROM duckdb_tables() t WHERE t.table_name = s.src_table);

-- 4. Эмбеддер ЖИВ — проверяем ДО изменения корпуса. Секреты движка живут в памяти и
--    исчезают при рестарте; после этого `ai_embed` падает с ошибкой, а досчёт векторов
--    завершается «успешно», не посчитав ничего.
SELECT CASE WHEN coalesce(array_length(
                  ai_embed('проверка связи', :'embed_model', 'qwen')), 0) <> :embed_dim
       THEN error('эмбеддер не отвечает или отдал не ту размерность — такт остановлен до изменения корпуса') END;

-- 5. Размерность колонки совпадает с тем, подо что считает досчёт. Разойдётся — не
--    запишется ни одна строка, и скажет об этом только «предупреждение».
SELECT CASE WHEN data_type <> 'FLOAT[' || :embed_dim || ']'
       THEN error('search_corpus.emb = ' || data_type || ', а досчёт считает под ' || :embed_dim) END
FROM duckdb_columns() WHERE table_name = 'search_corpus' AND column_name = 'emb';

SELECT 'проверки до такта пройдены' AS шаг,
       (SELECT v FROM build_state WHERE k = 'before_rows') AS строк_в_корпусе,
       (SELECT v FROM build_state WHERE k = 'before_res')  AS значений_резолвера;
