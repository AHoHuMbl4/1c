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
-- 🔴 Считаем только те строки, которым вектор ПОЛОЖЕН. Служебным он не считается по
-- решению владельца, и включать их сюда нельзя: их число не убывает никогда, и проверка
-- «за такт не убавилось ни одной» срабатывала бы ложно КАЖДЫЙ такт, как только
-- бизнес-строки досчитаны.
UNION ALL   SELECT now(), 'before_noemb', count(*) FILTER (WHERE emb IS NULL
              AND NOT EXISTS (SELECT 1 FROM search_entity_class e
                    WHERE e.src_table = search_corpus.src_table AND e.cls = 'service'))
            FROM search_corpus
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
-- Фильтр по базе: `duckdb_tables()` видит все присоединённые базы, и без него проверка
-- считала бы источник живым, потому что таблица с таким именем есть в ЧУЖОЙ базе.
WHERE NOT EXISTS (SELECT 1 FROM duckdb_tables() t WHERE t.table_name = s.src_table
                  AND t.database_name = current_database());

-- 4. Эмбеддер ЖИВ — проверяем ДО изменения корпуса. Секреты движка живут в памяти и
--    исчезают при рестарте; после этого `ai_embed` падает с ошибкой, а досчёт векторов
--    завершается «успешно», не посчитав ничего.
SELECT CASE WHEN coalesce(array_length(
                  ai_embed('проверка связи', :'embed_model', :'embed_secret')), 0) <> :embed_dim
       THEN error('эмбеддер не отвечает или отдал не ту размерность — такт остановлен до изменения корпуса') END;

-- 5. Размерность колонки совпадает с тем, подо что считает досчёт. Разойдётся — не
--    запишется ни одна строка, и скажет об этом только «предупреждение».
SELECT CASE WHEN data_type <> 'FLOAT[' || :embed_dim || ']'
       THEN error('search_corpus.emb = ' || data_type || ', а досчёт считает под ' || :embed_dim) END
FROM duckdb_columns() WHERE table_name = 'search_corpus' AND column_name = 'emb';

-- 6. 🔴 ПУЛ ИСПОЛНИТЕЛЕЙ ДВИЖКА. Проверка стоит здесь, а не в памяти установщика:
--    указание владельца 29.07 — «это точно нельзя пропустить, когда будем делать
--    установщик», и то же его правило, что и для имён, — делать невозможным, а не помнить.
--
--    [замер 29.07] `ai_embed` — сетевой вызов ВНУТРИ запроса, и запрос занимает
--    исполнителя на всё время ожидания ответа. При `--cpu_threads=0` пул равен числу
--    ядер: на шести ядрах наружу уходило РОВНО 5-6 запросов, сколько бы `psql`-потоков
--    ни запускали, и 12 против 64 давали одинаковые 9,2 строки/с. Первая векторизация
--    чужой базы растягивалась на 18 часов — молча, без единой ошибки.
--
--    Сравниваем НЕ с числом ядер (ограничение сетевое, а не счётное — в этом и ошибка
--    умолчания движка), а с НАШЕЙ же настройкой числа потоков плюс запас на обычные
--    запросы: при 64 потоках и пуле 6 движок переставал отвечать на посторонний SELECT.
--    Поэтому проверка универсальна: она не знает ни про эту машину, ни про эту базу.
SELECT CASE WHEN try_cast(current_setting('threads') AS BIGINT) IS NOT NULL
             AND try_cast(current_setting('threads') AS BIGINT) < :embed_workers + 8
       THEN error('пул исполнителей движка = ' || current_setting('threads')
                  || ', а досчёт просит ' || :embed_workers || ' потоков. Векторизация'
                  || ' упрётся в пул и пойдёт в разы медленнее, БЕЗ ошибок. Задайте в'
                  || ' /etc/serenedb/serened.conf: --cpu_threads=' || (:embed_workers + 32)
                  || ' и --io_threads=8, затем перезапустите движок') END;

SELECT 'проверки до такта пройдены' AS шаг,
       (SELECT v FROM build_state WHERE k = 'before_rows') AS строк_в_корпусе,
       (SELECT v FROM build_state WHERE k = 'before_res')  AS значений_резолвера;
