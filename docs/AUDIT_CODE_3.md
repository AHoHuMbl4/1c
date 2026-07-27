# Аудит кода №3: где мы делаем СВОЁ вместо штатного механизма SereneDB

Дата: 2026-07-27. Аудитор работал независимо; чужие файлы аудита не читались.
Сборка движка: **26.07.3** (`192.168.56.42:7890`), корпус `search_corpus` = 97 965 строк,
индекс `search_idx`, витрина = 233 таблицы / 2297 VARCHAR-колонок.

**Критерий владельца (жёсткий):** обычный SQL, приёмы PostgreSQL и наш собственный код —
НЕ считаются использованием SereneDB. Засчитывается только механизм ИМЕННО этого движка:
`USING inverted` / `USING secondary`, `@@` + `ts_*`, скореры, `ts_dict_*`, `ts_highlight`,
`ai_embed`, `MERGE INTO`, `SUMMARIZE`, `ivf`, словари `CREATE TEXT SEARCH DICTIONARY`,
`VACUUM (REFRESH_*/COMPACT_*)`, `sdb_*`-настройки, `sdb_metrics`, `es_*`.
По этому критерию `jaro_winkler_similarity`, `array_cosine_similarity`, `LIKE`, `QUALIFY`,
`json_serialize_sql` — **НЕ** засчитываются как использование SereneDB (это DuckDB-слой).

Все замеры ниже сделаны на инстансе через `psql ... \timing on`; сервер не менялся
(только SELECT/EXPLAIN/SHOW/SUMMARIZE), индексы не создавались.

---

## Находки

### 1. Точечный доступ к корпусу идёт SEQ_SCAN — нет индекса `USING secondary`

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:723-731 (_flush), :812-816 (детектор изменений),
       :847-853 (gone-очистка)
Сейчас: `MERGE INTO search_corpus t USING (VALUES ...) ON t.src_table=s.src_table
        AND t.row_key=s.row_key` — MERGE штатный, НО таблица-цель не имеет ни одного
        индекса по (src_table,row_key). Проверено: duckdb_indexes() отдаёт только
        `search_idx` (inverted). EXPLAIN точечного поиска по этой паре:
            ╭─ SEQ_SCAN ─╮ Table: search_corpus │ Type: Sequential Scan
        То есть каждый MERGE пачки из 200 строк и каждый LEFT JOIN-детектор изменений
        сканируют все 97 965 строк.
Штатно: `USING secondary` — отдельный access-method SereneDB (ART-индекс), а не «обычный
        индекс PostgreSQL». Проверено на инстансе:
            SELECT amname, amtype FROM pg_am;  -->  inverted|i, iresearch|t, secondary|i
        Синтаксис (tests/sqllogic/sdb/pg/index/secondary_index_point_lookup.test:19):
            CREATE INDEX search_corpus_pk ON search_corpus USING secondary (src_table, row_key);
Выигрыш: масштаб. Сейчас полная пересборка = ceil(97965/200)=490 MERGE × 97 965 строк
        ≈ 4.8×10^7 сравнений + 233 LEFT JOIN-прохода по всему корпусу. Рост квадратичный:
        на базе ×100 это 4.8×10^11. Точечный lookup по ART — O(log n).
Проверено на инстансе: да (pg_am + EXPLAIN SEQ_SCAN; сам индекс не создавал — запрет на DDL).
Важность: ухудшает (на нашем объёме терпимо, на клиентской базе — блокирует).
```

### 2. Индекс полностью пересоздаётся каждый прогон, хотя движок ведёт его транзакционно

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:865-880
Сейчас: `DROP INDEX IF EXISTS search_idx;` затем `CREATE INDEX ... USING inverted(...)`
        — безусловно, на каждом такте, ПОСЛЕ того как MERGE уже обновил строки.
        То есть индекс сначала платит цену за все MERGE (он существует во время них),
        а потом выбрасывается и строится с нуля.
Штатно: инвертированный индекс SereneDB обновляется транзакционно вместе с таблицей и
        переживает рестарт (examples/demo2/README.md:8; index/inverted_index_isolation.test).
        Собственный комментарий в _flush (:712-718) это и цитирует: «the index forces the
        commit-time append/delete path for every merge action». Публикация сегментов —
        `refresh_interval` или явно:
            VACUUM (REFRESH_INDEX) search_idx;
            VACUUM (COMPACT_INDEX)  search_idx;
        (index/vacuum_options.test; грамматика подтверждена текстами ошибок движка).
        Пересборка нужна ТОЛЬКО когда меняется DDL индекса (состав колонок/словарь) —
        ровно та же логика, что уже реализована для схемы корпуса на :754-760.
Выигрыш: скорость такта. Индекс на 97 965 док. = 13 МБ / 1 сегмент (sdb_metrics);
        инкрементальный такт после этого — только REFRESH+COMPACT вместо полной
        переиндексации всего корпуса. Заявленная цель модуля («такт минутами, а не
        8 минутами») сейчас сводится на нет этой строкой.
Проверено на инстансе: частично (грамматика VACUUM (REFRESH_INDEX) и транзакционность —
        да; замер «инкремент vs пересборка» требует DDL, запрещён).
Важность: ухудшает.
```

### 3. `amount` и `doc_date` — только в `INCLUDE`, поэтому условия по числу и дате не уходят в постинги

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:879-880 (DDL индекса)
       ubuntu/serenedb/serene_ask.py:217-232 (_predicates)
Сейчас: CREATE INDEX search_idx ON search_corpus USING inverted(doc, refs, src_table)
        INCLUDE (src_table, row_key, amount, doc_date);
        _predicates() строит обычные SQL-предикаты: `amount > 500000`,
        `doc_date >= '...'`, `doc_date < ('...'::date + INTERVAL 1 day)`.
        EXPLAIN подтверждает, что это residual-фильтр, а не индексный:
            IRESEARCH_SCAN │ Index Filter: Term(doc)  │ Column Filter: amount > 500000
Штатно: колонка, попавшая в СПИСОК КЛЮЧЕЙ `inverted(...)`, фильтруется постингами; колонка
        только в INCLUDE — residual FILTER над сканом
        (index/inverted_index_include_pushdown.test:1). Колонка может быть И ключом,
        И в INCLUDE одновременно (index/inverted_index_indexed_vs_included.test:1-20).
            CREATE INDEX search_idx ON search_corpus
              USING inverted (doc search_dict, refs search_dict, src_table, amount, doc_date)
              INCLUDE (src_table, row_key, amount, doc_date);
        Тогда предикаты пишутся штатными range-строителями:
            WHERE amount   @@ ts_gt(500000)
            WHERE amount   @@ ts_between(100, 500, true, true)
            WHERE doc_date @@ ts_between(TIMESTAMP '2025-12-01', TIMESTAMP '2026-01-01', true, false)
        Проверено, что сейчас так НЕЛЬЗЯ (и почему это находка):
            SELECT count(*) FROM search_idx WHERE amount @@ ts_ge(500000);
            ERROR: @@ requires an inverted-indexed column on one side
            HINT: ... CREATE INDEX ... USING inverted(<col>) if missing.
Выигрыш: правильность + масштаб. На 98 тыс. строк разницы нет (замер: `doc_date >= ...`
        по индексу 1.32 мс, по таблице 1.07 мс — обе формы читают всё). Значение в том,
        что при росте корпуса residual-фильтр остаётся линейным по числу совпадений
        текста, а постинги — нет. Плюс это снимает главный архитектурный перекос:
        сейчас при вопросе БЕЗ слов (только период/порог) код уходит `FROM search_corpus`
        (serene_ask.py:238, 349, 372) — то есть мимо индекса вообще.
Проверено на инстансе: да (EXPLAIN + текст ошибки ts_ge + оба замера).
Важность: ухудшает.
```

### 4. `optimize_top_k` не задан, хотя запрос имеет ровно форму, под которую сделан WAND

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:879 (нет WITH (...))
       ubuntu/serenedb/serene_ask.py:369-376 (rows_of: ORDER BY <скорер> DESC LIMIT 40)
Сейчас: reloptions живого search_idx (проверено запросом) содержат только умолчания:
        row_group_size, norm_row_group_size, refresh_interval, compaction_interval,
        cleanup_interval_step, segment_memory_max, segment_docs_max,
        compaction_max_segments*, compaction_floor_segment_bytes.
        `optimize_top_k` отсутствует → per-block max-impact не пишется → отсечения нет.
Штатно: CREATE INDEX ... WITH (optimize_top_k = 'bm25(1.2, 0.75)');
        (site_docs/sql/indexes/inverted/ranking.test:32, index/inverted_index_wand.test:1-17;
        глобальный выключатель `sdb_disable_top_k_optimization` есть в duckdb_settings()
        нашей сборки). Условие срабатывания: скорер в ORDER BY совпадает с записанным.
        Наш rows_of() ровно такой: WHERE <фильтр> ORDER BY bm25(idx.tableoid) DESC LIMIT 40.
        Важно: значение обязано совпадать с ASK_SCORER — сейчас скорер выбирается
        переменной окружения (serene_ask.py:74-79), а индекс о ней не знает.
Выигрыш: скорость top-K. Замер сейчас: `ORDER BY bm25 DESC LIMIT 40` по 2 639 совпадениям
        — 4.10 мс; без ORDER BY тот же фильтр — 2.64 мс, т.е. ~35% времени запроса уходит
        на скоринг всех совпадений. С WAND скорится только пул кандидатов.
        EXPLAIN должен пометить строку TopK суффиксом «, optimized».
Проверено на инстансе: частично (отсутствие опции и замеры — да; включение требует DDL).
Важность: косметика на 98 тыс., ухудшает на масштабе.
```

### 5. Резолвер значений: подстрока + jaro_winkler по каждой колонке вместо инвертированного индекса

```
МЕСТО: ubuntu/serenedb/serene_report.py:192-203 (_lexical_into), :169-189 (dim_columns)
Сейчас: на КАЖДЫЙ вопрос обходятся все текстовые колонки витрины и на каждую строится
            SELECT DISTINCT "c" FROM "t"
             WHERE lower("c") LIKE '%слово%'
                OR jaro_winkler_similarity(lower("c"), 'слово') > 0.9
        `LIKE '%...%'` и `jaro_winkler_similarity` — функции DuckDB-слоя, НЕ механизм
        SereneDB. Плюс это ровно тот признак самодеятельности, который назван в брифе.
        Отбор колонок (dim_columns) делает по одному `count(DISTINCT)` и по одному
        `SELECT ... LIMIT 1` на колонку: 2297 VARCHAR-колонок × 2 запуска psql.
        Замер стоимости запуска psql на этом сервере: 39 мс → ≈179 с на один вызов
        dim_columns(), и он вызывается внутри _lexical_into на каждый вопрос.
Штатно: инвертированный индекс над значениями измерений + термовые функции движка.
        Отдельная таблица уже есть (`resolver_index`, 8 200 значений) — над ней:
            CREATE TEXT SEARCH DICTIONARY dim_kw (template='keyword');
            CREATE TEXT SEARCH DICTIONARY dim_tx (template='text', locale='ru_RU.UTF-8',
                   case='lower', accent=false, frequency=true, position=true, norm=true);
            CREATE INDEX resolver_idx ON resolver_index
              USING inverted (value dim_tx, table_name, column_name) INCLUDE (value);
        Запрос вместо LIKE+jaro (все функции проверены на нашем инстансе):
            SELECT table_name, column_name, value FROM resolver_idx
             WHERE value @@ ts_any([ ts_phrase('казань'),
                                     ts_levenshtein('казань', 1),
                                     ts_starts_with('казан') ]::tsquery[])
             ORDER BY bm25(resolver_idx.tableoid) DESC LIMIT 5;
        Для подстроки — штатная схема GitHub code search (demo6/demo.sql:30-33):
            CREATE TEXT SEARCH DICTIONARY grams   (template='sparse_ngram', frequency=true, norm=true);
            CREATE TEXT SEARCH DICTIONARY grams_q (template='copy_from', from='grams', covering=true);
            ... WHERE value @@ ts_all(ts_tokenize(ARRAY['казан'],'grams_q'))
                  AND value LIKE '%казан%';
        Шаблоны `sparse_ngram`, `ngram`, `stem`, `wildcard`, `pipeline`, `copy_from`,
        `solr_synonyms` — проверены `strings` в бинарнике 26.07.3, присутствуют.
        Для «похожести с порогом» вместо jaro есть `ts_ngram(t, threshold)` (Jaccard) и
        `ts_dict_score(col)` (проверено запросом: вернул выровненный FLOAT[] по термам).
Выигрыш: скорость на порядки (2297 отдельных psql-запросов → 1 запрос по индексу,
        1-5 мс: замер аналогичных форм на search_idx — ts_levenshtein 3.6 мс,
        ts_starts_with/ts_phrase 2.6 мс, ts_like 5.1 мс) + правильность (jaro по
        символам путает города, что уже задокументировано в комментарии :207-211;
        ts_levenshtein с обязательным префиксом `ts_levenshtein('азань',1,true,'к')`
        снимает именно этот класс ошибок) + меньше кода (dim_columns/_lexical_into
        исчезают целиком).
Проверено на инстансе: да (все ts_*-функции и bm25 — запросом; sparse_ngram — по бинарнику;
        стоимость 39 мс/psql и 2297 колонок — замерены).
Важность: блокирует (это главный «своими руками» участок).
```

### 6. Интроспекция схемы для LLM: N+1 запросов вместо `SUMMARIZE`

```
МЕСТО: ubuntu/serenedb/serene_report.py:114-154 (sample_values, get_schema),
       :169-189 (dim_columns), ubuntu/serenedb/serene_search_build.py:293-331 (profile_table)
Сейчас: get_schema() делает один psql на count(*) КАЖДОЙ таблицы (233 шт.) и один psql
        на примеры значений КАЖДОЙ текстовой колонки (2297 шт.) ≈ 2530 запусков процесса
        × 39 мс ≈ 99 секунд на один вопрос-отчёт.
        profile_table() в сборщике собирает `count(DISTINCT ...)` и `max(abs(...))`
        руками в один SELECT — уже лучше, но всё равно своя конструкция.
Штатно: `SUMMARIZE` — механизм движка, отдельно оговорённый и для индекса
        (index/inverted_index_summarize.test:34-40). Отдаёт по каждой колонке
        column_name, column_type, min, max, approx_unique, avg, std, q25/q50/q75,
        count, null_percentage — одним запросом на таблицу.
            SUMMARIZE "catalog_классификаторбанков";
            SUMMARIZE search_idx;      -- работает и по индексу
        Плюс `approx_count_distinct(col)` и `stats(col)`; для NDV прямо из индекса —
        опкласс `included (hyperloglog = true)` на INCLUDE-колонке
        (index/inverted_index_hyperloglog_option.test:24-28; опкласс `included` есть
        в pg_opclass нашей сборки).
Выигрыш: скорость. Замерено на инстансе: SUMMARIZE одной таблицы витрины (все колонки,
        2779 строк) = 14.7 мс. Ручной путь по той же таблице ≈ 20 колонок × (39 мс запуск
        + 1.3 мс запрос) ≈ 800 мс. То есть 54× на таблицу; по всей витрине
        ≈ 3.4 с вместо ≈ 186 с.
        Дополнительно: min/max из SUMMARIZE закрывают и «примеры значений» для промпта,
        и `count(DISTINCT)` (через approx_unique) в dim_columns.
Проверено на инстансе: да (SUMMARIZE выполнен на search_corpus и на таблице витрины,
        время снято; 39 мс/psql замерены).
Важность: ухудшает (на клиентской витрине из тысяч таблиц — блокирует).
```

### 7. Эмбеддинги считаются из Python, хотя в сборке есть `ai_embed()`

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:207-221 (embed) + :776-834 (пул на 16
       потоков, батчи по 10, ретраи, harvest, inflight-очередь)
       ubuntu/serenedb/serene_ask.py:148-154 (embed_one), :548-549 (_vec)
       ubuntu/serenedb/serene_report.py:53-66 (embed)
       ubuntu/serenedb/build_resolver_index.py:41-52
Сейчас: три независимые реализации HTTP-клиента к DashScope + собственный пул
        параллельности + собственные ретраи + собственная сериализация вектора в литерал.
Штатно: ai_embed(text, model, secret) -> FLOAT[] — есть в 26.07.3, проверено:
            SELECT function_name, parameter_types, return_type FROM duckdb_functions()
             WHERE function_name LIKE 'ai%';
            ai_embed | {VARCHAR,VARCHAR,VARCHAR} | FLOAT[]
        Секреты (duckdb_secrets, which_secret — тоже есть в сборке, проверено):
            CREATE SECRET qwen (TYPE openai, api_key '...',
                base_url 'https://dashscope...', embeddings_path '/v1/embeddings');
            INSERT INTO t SELECT ..., ai_embed(doc,'text-embedding-v4','qwen')::FLOAT[N] ...
            ... ORDER BY emb <=> ai_embed('вопрос','text-embedding-v4','qwen')::FLOAT[N]
        (demo5/bootstrap.sql:5-33, demo5/demo.sql:27-31.)
БЛОКЕР, зафиксированный нашим же замером: docs/SERENEDB.md:116 — «⚠ размерность 1024,
        а у нас индекс на 1536: у функции НЕТ параметра dimensions». Подтверждаю по
        каталогу: сигнатура ровно три VARCHAR, четвёртого параметра нет.
Выигрыш: минус ~120 строк кода (пул/батчи/ретраи/литералы в трёх файлах), минус один
        сетевой хоп на вопрос (сейчас Python→облако→Python→psql→движок).
Проверено на инстансе: да (функция есть), но применимость — НЕТ (1024 ≠ 1536).
Важность: не внедрять как есть. Внедряемо только вместе с решением про размерность:
        либо перевести весь корпус и resolver_index на 1024 и замерить A/B качества,
        либо дождаться параметра dimensions. Пока — оставить своё, но пометить.
```

### 8. Полная перезагрузка таблицы витрины `DROP TABLE + CREATE TABLE AS` вместо `MERGE INTO`

```
МЕСТО: ubuntu/serenedb/poc_load_entity.py:192-206
Сейчас: DROP TABLE IF EXISTS "t"; CREATE TABLE "t" AS SELECT * FROM read_csv(...)
        QUALIFY row_number() OVER (PARTITION BY key) = 1;
        `read_csv` — штатный ридер движка (это плюс), но `QUALIFY`/`DISTINCT` — DuckDB-слой,
        а DROP+CTAS уничтожает всё, что на таблице построено, и на время такта таблица
        не существует.
Штатно: MERGE INTO — механизм SereneDB, и в его тестах отдельно оговорено поведение цели
        с инвертированным индексом (site_docs/sql/statements/merge_into/index.test:16-140;
        cookbook/sql_features/merge.test:56-77). Ветка `WHEN NOT MATCHED BY SOURCE THEN
        DELETE` закрывает и удаление исчезнувших строк, `USING (ключ)` — краткая форма
        равенства по одноимённым колонкам, `RETURNING merge_action, *` даёт готовую
        статистику вместо нашей сверки len(rows) != n на :214.
            MERGE INTO "t" USING (SELECT * FROM read_csv('...')) s USING ("Ref_Key","LineNumber")
            WHEN MATCHED THEN UPDATE
            WHEN NOT MATCHED BY TARGET THEN INSERT BY NAME
            WHEN NOT MATCHED BY SOURCE THEN DELETE
            RETURNING merge_action;
Выигрыш: правильность (таблица не исчезает под читателем, GRANT не теряется —
        сейчас его приходится переиздавать строкой :174) + масштаб (перезаливаются
        только изменившиеся строки) + меньше кода (уходит ручной QUALIFY-дедуп
        и ручной подсчёт dropped).
Проверено на инстансе: нет (MERGE — DDL/DML, запрещён; синтаксис — из тестов движка).
        Косвенно: MERGE INTO уже работает у нас в serene_search_build.py:723, форма та же.
Важность: ухудшает.
```

### 9. Тип-сниффер CSV ломает коды (ИНН/КПП/счёт) — есть штатный параметр ридера

```
МЕСТО: ubuntu/serenedb/poc_load_entity.py:195-199 (read_csv без опций)
       следствие описано в ubuntu/serenedb/serene_search_build.py:96-103, :548-551
Сейчас: read_csv() вызывается без параметров, сниффер превращает ИНН в BIGINT.
        Компенсация построена НАД дефектом: сборщик тянет 15 МБ $metadata (16 с) и
        восстанавливает объявленные типы (odata_types), плюс всюду TRY_CAST.
Штатно: `read_csv` в 26.07.3 принимает (проверено списком параметров из duckdb_functions()):
        all_varchar, columns, column_types, types, dtypes, names, column_names,
        auto_detect, sample_size, ignore_errors, store_rejects, rejects_table, strict_mode.
        То есть тип задаётся ридеру явно, а не чинится потом:
            SELECT * FROM read_csv('/var/lib/serenedb/t.csv', all_varchar = true);
            SELECT * FROM read_csv('...', column_types = {'ИНН':'VARCHAR','СуммаДокумента':'DOUBLE'});
        Карта типов у нас уже есть — это ровно `$metadata`, который уже парсится.
Выигрыш: правильность в источнике вместо компенсации в трёх местах; плюс `store_rejects`/
        `rejects_table` дают штатный журнал непрочитанных строк вместо тишины.
Проверено на инстансе: да (полный список именованных параметров read_csv снят из
        duckdb_functions()).
Важность: ухудшает.
```

### 10. Векторный поиск идёт полным сканом (правомерно), но написан не операторной формой

```
МЕСТО: ubuntu/serenedb/serene_ask.py:920-922, :956-959, :969-973
       ubuntu/serenedb/serene_report.py:219-222
       ubuntu/serenedb/measure_resolver.py:11
Сейчас: ORDER BY array_cosine_similarity(emb, '[...]'::FLOAT[1536]) DESC LIMIT k.
        `array_cosine_similarity` — скалярная функция DuckDB-слоя. Планировщик под неё
        ANN-скан не выбирает даже при наличии ivf-индекса.
Штатно: операторы дистанции движка: `<=>` (cosine), `<->` (L2), `<#>` (ip), `<+>` (L1).
        Форма `ORDER BY emb <=> $1::FLOAT[N] LIMIT k` — та, что даёт план
        IRESEARCH_ANN_SCAN, а `WHERE emb <=> $1 < 0.3` — IRESEARCH_ANN_RANGE_SCAN
        (site_docs/sql/indexes/inverted/vector-search.test, demo4/demo.sql:56-94).
        Проверено на нашем инстансе, что `<=>` работает и БЕЗ индекса (полный скан):
            SELECT src_table FROM search_corpus ORDER BY emb <=> (...) LIMIT 5;  -- 352.7 мс
        против array_cosine_similarity — 394.9 мс. Разница в пределах шума, но форма
        `<=>` — единственная, которую движок сможет превратить в ANN, когда ivf появится.
Выигрыш: правильность формы (нулевая цена сейчас, автоматическое ускорение потом) +
        снимается риск «построили ivf, а он не используется, потому что в ORDER BY функция».
Проверено на инстансе: да (обе формы выполнены, время снято).
Важность: косметика (но дёшево и снимает будущую ловушку).
```

### 11. Комментарий в коде утверждает наличие `hnsw` — в нашей сборке его нет

```
МЕСТО: ubuntu/serenedb/build_resolver_index.py:9-12
Сейчас: docstring: «В SereneDB ЕСТЬ HNSW (проверено 2026-07-25), синтаксис — колонка внутри
        инвертированного индекса: CREATE INDEX i ON resolver_index USING inverted(emb hnsw
        (metric='cosine', m=32, ef_construction=64)); ... Включать после замера».
        Это инструкция к действию, которая на сборке 26.07.3 упадёт.
Штатно: доступен только `ivf`:
            CREATE INDEX i ON t USING inverted (id, emb ivf (metric='cosine', quant='sq8'));
        Опровержение уже записано в docs/SERENEDB.md:161-163 («Unknown built-in opclass
        'hnsw' on 'emb' (known: included, ivf)»), но в код не доехало.
Выигрыш: правильность (не даём следующему исполнителю ложную инструкцию).
Проверено на инстансе: да, косвенно — pg_opclass содержит только ivf/included/словари
        (зафиксировано во всех трёх каталогах возможностей и в SERENEDB.md).
Важность: ухудшает (документационный дефект в исполняемом файле).
ВНИМАНИЕ: сам ivf на resolver_index (8 200 значений) сейчас не нужен — перебор 8 200
        строк мгновенный; и ivf на корпусе строить НЕЛЬЗЯ (OOM, 30+ ГБ — см. ниже).
```

### 12. Ранжирование A/B ограничено тремя моделями из семи

```
МЕСТО: ubuntu/serenedb/serene_ask.py:74-79 (SCORERS), ubuntu/serenedb/ab_scorer.py:22
Сейчас: SCORERS = {bm25, bm25_b0, tfidf}.
Штатно: в 26.07.3 семь скореров, все проверены запросом на нашем search_idx (см. каталоги):
        bm25(oid[,k1,b]), tfidf(oid[,with_norms]), lm_jm(oid[,lambda]),
        lm_dirichlet(oid[,mu]), indri_dirichlet(oid[,mu]), dfi(oid[,'standardized'|
        'saturated'|'chi_squared']), raw_tf/raw_dl/raw_boost.
        Наш корпус — короткие «мешки реквизитов» очень разной длины; ровно тот случай,
        где lm_dirichlet/dfi ведут себя иначе, чем BM25. Инструмент для решения уже есть:
        ab_scorer.py прогоняет золотой набор на каждом варианте.
        Ограничение движка (проверено): один скорер на запрос к одному индексу,
        «Only one scorer function is allowed per inverted index / HINT: Use UNION».
        Поэтому сравнение — только последовательными прогонами, как сейчас в ab_scorer.
Выигрыш: правильность, но цифра неизвестна до прогона — это и есть аргумент по п.2
        правила владельца.
Проверено на инстансе: да (все скореры вызываются на search_idx).
Важность: косметика (расширение существующего A/B, не переделка).
```

### 13. Мёртвый код: `_fetch`

```
МЕСТО: ubuntu/serenedb/serene_ask.py:235-241
Сейчас: функция _fetch определена, но не вызывается ниоткуда (grep по всему каталогу).
        Её заменил rows_of (:357). В ней зашита старая форма `%s AS s ... ORDER BY s DESC`.
Штатно: —
Выигрыш: меньше кода; убирает вторую, расходящуюся формулировку поискового запроса.
Проверено на инстансе: неприменимо.
Важность: косметика.
```

---

## Где штатного НЕТ и своё оправдано

1. **Векторный индекс над корпусом (`ivf`) не строится — serene_search_build.py:865-871.**
   Обоснование в коде подтверждается: сборка ivf на 96 931 × 1536 требует >34 ГБ и убивается
   OOM (замерено трижды 2026-07-26; `sdb_ivf_sample_factor` и `segment_memory_max` траекторию
   не меняют). `hnsw` в 26.07.3 отсутствует. Полный скан по 97 965 векторам — 352 мс
   (замерено), для запасного пути это приемлемо. **Не переделывать, пока не решён вопрос с
   памятью ivf.** Запрет владельца на создание ivf-индекса действует.

2. **Гейт ответа модели (serene_ask.py:662-896).** Разбор числовых токенов во все прочтения
   локали, покомпонентная сверка дат, роли claims — у движка такого механизма нет и быть не
   может. Своё, оправдано, помечено как своё.

3. **Разбор `$metadata` OData и перепись базы (odata_census.py, serene_search_build.py:94-134,
   poc_load_entity.py:41-53).** Это протокол 1С, не движок. `CREATE PUBLICATION/SUBSCRIPTION`
   в SereneDB парсятся, но не реализованы (`ddl/create_publication.test:1-6`), `ATTACH ... TYPE
   postgres` к 1С неприменим. Своё оправдано.

4. **Валидатор LLM-SQL (serene_report.py:400-458).** Использует `json_serialize_sql` — это
   DuckDB-слой, но иного AST-механизма движок не даёт, а allow-list по BASE_TABLE — наша
   логика. Своё оправдано; денайлисты честно помечены как fallback.

5. **Выбор денежной колонки и сущности через LLM (serene_search_build.py:224-282,
   serene_ask.py:379-545).** Языковая задача, у движка механизма нет. Оправдано; и уже
   подпёрто штатными данными — `ts_dict_agg`/`ts_dict_count` (см. ниже).

6. **Bearer-авторизация сервисов (serene_ask.py:1088, mcp_reports.py:43-66).** У движка есть
   `auth_api_key`/`auth_bearer_token` в `sdb_settings`, но они защищают порт движка, а не наши
   HTTP-сервисы. Своё оправдано.

---

## Что мы используем штатно и трогать не надо

| Место | Механизм SereneDB | Подтверждение |
|---|---|---|
| serene_search_build.py:723-731 | `MERGE INTO ... WHEN MATCHED/NOT MATCHED` в цель с инвертированным индексом | штатный DML движка; заменил связку DELETE+INSERT |
| serene_search_build.py:858-860 | `CREATE TEXT SEARCH DICTIONARY (template='text', locale, case='lower', accent=false, frequency, position, norm)` | словарь движка; `frequency`+`norm` дают рабочий BM25 |
| serene_search_build.py:879-880 | `CREATE INDEX ... USING inverted(doc, refs, src_table)` — раздельные поля в ОДНОМ индексе, шаблон demo6/one-search-box | подтверждено запросами по `refs` и `src_table` |
| serene_ask.py:279, 318, 335 | `@@` от имени ИНДЕКСА (`FROM search_idx`), не от таблицы | проверено: все запросы к search_idx идут `FROM search_idx` |
| serene_ask.py:261-277 | `ts_phrase`, `ts_phrase(a, ARRAY[0,n], b)` со слопом, `ts_levenshtein`, `ts_like` | все выполнены на инстансе |
| serene_ask.py:322-335 | `ts_compound(NULL, NULL, [...], k)` — булев запрос движка | проверено: `ts_compound(...,2)` = 103, совпало с `ts_any([...],2)` = 103 |
| serene_ask.py:303 | `ts_any([...])` | проверено |
| serene_ask.py:349 | `SELECT src_table, count(*) FROM search_idx GROUP BY 1` — фасет из словаря термов по keyword-колонке | `index/ts_dict_facets.test`; EXPLAIN подтверждает Index Filter на src_table |
| serene_ask.py:369-370 | `ts_highlight(doc, 'MaxWords=..,MaxFragments=..,StartSel=..,StopSel=..')` | проверено на инстансе; работает, несмотря на то что словарь создан без `offset=true` — `ts_offsets(doc)` тоже отдаёт `{109,117}`. **Не «чинить» словарь ради offset: и так работает.** |
| serene_ask.py:371 | скорер `bm25(search_idx.tableoid)` / `bm25(oid,1.2,0.0)` / `tfidf(oid)` в ORDER BY | проверено |
| serene_ask.py:412-423 | significant terms из `ts_dict_agg(refs)` + `ts_dict_count(refs)` — штатный рецепт кукбука | проверено: `ts_dict_agg`/`ts_dict_count`/`ts_dict_score` работают |
| serene_ask.py:367, 568 | `src_table = '...'` по индексированной keyword-колонке | EXPLAIN: уходит в **Index Filter → Term(src_table)**, не в Column Filter. Это уже пушдаун, переписывать на `@@` не нужно |
| serene_ask.py:559-587 | count/sum/min/max/avg/count(amount) считаются в базе по всему множеству, без LIMIT | соответствует требованию «агрегация в базе» |
| poc_load_entity.py:195-199 | `read_csv('...')` как источник CTAS | штатный ридер движка |
| serene_report.py:123-129, :174 | `duckdb_columns()` вместо information_schema | верно для read-only роли |

---

## Спорное

1. **Отказ от таблицы `search_corpus` в пользу индекса над VIEW (zero-ETL, шаблон demo6).**
   Каталоги описывают: индекс можно строить над вьюхой, в том числе `UNION ALL` из разнородных
   источников с `CASE`/`concat_ws`, если все нужные колонки положить в `INCLUDE`
   (`demo6/bootstrap.sql:100-131`, caps1 §11.1). Это убрало бы весь Python-конвейер сборки
   `doc` (serene_search_build.py:534-706), хеши, STAGE-таблицу и MERGE.
   **Чего не хватило для вывода:** (а) вьюха должна собираться из 233 таблиц с разным составом
   колонок и с резолвом GUID→наименование (это JOIN), а fast-path материализации требует
   плоской проекции — обход через `INCLUDE` заявлен, но у нас не проверен; (б) при 233
   источниках `UNION ALL` придётся генерировать динамически, то есть DDL всё равно строится
   кодом; (в) проверка требует DDL, запрещённого в этом аудите. Оцениваю как перспективное,
   но не как готовое предписание.

2. **`GENERATED ALWAYS AS (concat_ws(...)) STORED` / индекс по выражению вместо сборки `doc`
   в Python.** Механизм есть (`cookbook/search/one-search-box.test:23-25`,
   `cookbook/search/computed-values.test`). Но резолв ссылок (GUID → наименование владельца)
   — межтабличный, в выражение индекса не помещается, а агрегаты в выражениях запрещены.
   Применимо только к части `doc`, выигрыш неочевиден. Не хватило: замера, какая доля `doc`
   строится без обращения к refmap.

3. **`refs` с бустом `^`.** Комментарий serene_search_build.py:876 обещает «можно поднять вес
   поля (^)», но ни один запрос в serene_ask.py буст не использует. Оператор проверен на
   инстансе (`refs @@ ('ромашка'::tsquery ^ 3.0)` → 29). Стоит ли — вопрос качества, ответ
   даёт только A/B на золотом наборе. Не хватило: прогона ab_scorer с вариантом
   «doc-запрос OR (refs-запрос ^ N)».

4. **`stemming=false` в словаре (serene_search_build.py:859).** Штатная альтернатива —
   `stemming=true` или шаг `stem` в `pipeline`; это сняло бы часть нагрузки с
   `ts_levenshtein`-компенсации в probe(). Но: стемминг привязывает словарь к языку
   конфигурации, а продукт коробочный; и `locale` у нас уже вынесен в env с пометкой
   «на результат не влияет». Не хватило: A/B «stemming on/off» на золотом наборе —
   а он требует пересборки индекса (DDL).

5. **ES-совместимый слой (`es_create_index`/`es_bulk`/`es."idx$text"`).** Все семь функций есть
   в 26.07.3. Теоретически он мог бы заменить нашу пару «корпус + индекс» на готовую схему
   с `_source`. Но анализатор там фиксирован (`es."standard"`, lowercase без стемминга),
   INCLUDE-колонок и скореров кроме BM25 в этом контракте нет, а наш `refs`/`src_table`
   в модель ES-mapping ложатся плохо. Скорее нет, чем да; не хватило эксперимента.

6. **`serene_report.py:265` — комментарий «DuckDB lower() НЕ лоуэркейсит кириллицу
   (ASCII-only)».** Проверено на 26.07.3: `SELECT lower('АБВГ')` → `абвг`. Комментарий
   неверен для нашей сборки (собран ICU). Приведение регистра в Python из-за этого — лишнее,
   но и безвредное. Штатным механизмом приведения регистра является словарь
   (`case='lower'` + `locale`) / `ts_lexize`. Не хватило: понимания, не сломает ли снятие
   Python-lower() сравнение имён колонок в measure_caveat/_schema_tables.

---

## Итог: что действительно надо переделать

**По убыванию важности.**

1. `USING secondary (src_table, row_key)` на `search_corpus` — снимает SEQ_SCAN во всех MERGE
   и в детекторе изменений (находка 1).
2. Заменить `LIKE '%..%' + jaro_winkler` резолвера на инвертированный индекс над
   `resolver_index` с `ts_levenshtein` / `ts_starts_with` / `ts_any` / `sparse_ngram`
   (находка 5) — самый крупный «своими руками» участок.
3. `SUMMARIZE` вместо N+1 интроспекции в `get_schema`/`dim_columns`/`profile_table`
   (находка 6): 14.7 мс против ~800 мс на таблицу, замерено.
4. Перестать пересоздавать `search_idx` каждый прогон; публиковать через
   `VACUUM (REFRESH_INDEX)` / `VACUUM (COMPACT_INDEX)` (находка 2).
5. Внести `amount` и `doc_date` в список ключей `inverted(...)` и перевести `_predicates`
   на `ts_between` / `ts_gt` / `ts_lt` (находка 3).
6. `MERGE INTO` вместо `DROP TABLE + CTAS` в загрузчике витрины (находка 8) и явные
   `column_types`/`all_varchar` у `read_csv` (находка 9).
7. `WITH (optimize_top_k = '<тот же скорер, что в ASK_SCORER>')` (находка 4).
8. Исправить docstring `build_resolver_index.py` про HNSW (находка 11);
   перевести векторные запросы на оператор `<=>` (находка 10); удалить `_fetch` (находка 13);
   расширить `SCORERS`/`ab_scorer` до всех семи моделей (находка 12).

**Не внедрять:** `ai_embed()` в текущем виде (1024 ≠ 1536, находка 7); любой `ivf` на корпусе
(OOM); любой `hnsw` (в сборке отсутствует).
