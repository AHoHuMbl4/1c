# Аудит кода: где мы делаем СВОЁ вместо штатного механизма SereneDB

Дата: 2026-07-27. Сборка движка: **26.07.3** (`192.168.56.42:7890`, PostgreSQL 18.3 wire).
Репозиторий-первоисточник: `/srv/data/cursor/cursor/1/serenedb-src` (`main`).

Критерий засчёта (владелец): **обычный SQL, приёмы PostgreSQL и наш собственный код —
не считаются использованием SereneDB.** Засчитывается только механизм именно этого движка:
инвертированный индекс и его опции, словари `TEXT SEARCH DICTIONARY`, `ts_*`-функции,
скореры, словарь термов, `ivf`, `ai_embed`, `SUMMARIZE`, `MERGE`, `VACUUM (REFRESH_*)`,
`read_*`-ридеры, `sdb_*`-настройки.

Проверено на инстансе всё, что помечено «да». DDL не выполнялся (аудит read-only,
`ivf` не создавался).

---

## 1. БЛОКИРУЮЩИЕ

### 1.1 Резолвер терминов: ~2300 отдельных `psql` на каждый вопрос вместо одного запроса движка

```
МЕСТО: ubuntu/serenedb/serene_report.py:169-189 (dim_columns), :192-202 (_lexical_into)
```

**Сейчас.** `dim_columns()` берёт все VARCHAR-колонки витрины и на **каждую** запускает
отдельный процесс `psql` с `count(DISTINCT "col")`, затем ещё один — на образец значения.
Дальше `_lexical_into()` на каждую уцелевшую колонку делает ещё один `psql` c
`lower(col) LIKE '%слово%' OR jaro_winkler_similarity(...) > 0.9`.
`dim_columns()` не кэшируется и вызывается из `resolve_hints()` на **каждый** вопрос
(`run_report` → `resolve_hints` → `_lexical_into` → `dim_columns`).

Это ровно то, что владелец назвал самодеятельностью: `LIKE '%…%'` + строковая метрика
в скалярной функции, вместо словаря термов индекса.

**Замер на живой базе.** VARCHAR-колонок в `public` — **2297**, таблиц — 233.
20 последовательных `count(DISTINCT)` через `psql` = **732 мс** → на 2297 колонках
≈ **84 секунды** только на `dim_columns()`, и это до единого полезного действия.

**Штатно.** Механизм словаря термов инвертированного индекса — `ts_dict_agg` /
`ts_dict_score` / `ts_dict_count`, рецепт кукбука «исправление опечаток»
(`site_docs/cookbook/search/spell-correction.test:31-40`) и «автодополнение»
(`autocomplete.test:34-58`):

```sql
SELECT unnest(ts_dict_agg(v))  AS value,
       unnest(ts_dict_score(v)) AS sim
FROM   dim_idx
WHERE  v @@ ts_levenshtein('казань', 2)
ORDER  BY sim DESC LIMIT 5;
```

Один запрос вместо тысяч процессов; `ts_dict_score` возвращает уже нормированную
близость (`jaket`→`jacket` 0.8), то есть `jaro_winkler_similarity` не нужен вовсе.

**Важная оговорка (проверено запросом на инстансе):** `WHERE` в `ts_dict_*` фильтрует
**документы**, а не термы. На нашем многотокенном `search_idx.refs` запрос
`ts_dict_agg(refs) … WHERE refs @@ ts_levenshtein('казань',2)` вернул `04.09.2014`, `13`,
`2025` со `score=1` — мусор. Значит рецепт требует **однотокенной keyword-колонки**:
индекс над значениями измерений (`value` с `template='keyword'` или `text`), то есть
ровно тот объект, который у нас уже есть как `resolver_index`, только без индекса.

**Выигрыш.** Скорость: ~84 с → единицы миллисекунд на вопрос (порядок 4). Объём кода:
уходят `dim_columns`, `_lexical_into`, `jaro_winkler`-порог `min_sim` и подбор `0.9`.
Правильность: `ts_dict_score` — метрика движка, проверенная на их данных, а не наш порог.

**Проверено на инстансе:** да — время `psql`-цикла, `ts_dict_agg/score/count` работают,
поведение `WHERE` по документам проверено запросом.
**Важность: блокирует** (задержка ответа на отчёт измеряется минутами).

---

### 1.2 `get_schema()`: один `psql` на таблицу + один на текстовую колонку, каждый вопрос

```
МЕСТО: ubuntu/serenedb/serene_report.py:122-154, :114-119 (sample_values)
```

**Сейчас.** На каждый вопрос: 233 запуска `psql` для `count(*)` по таблице + до 2297
запусков `sample_values()` (`SELECT DISTINCT col … LIMIT 5`). При замеренных ~36 мс на
процесс это **~90 секунд** на построение промпта.

**Штатно.** `SUMMARIZE <table>` — команда движка (`index/inverted_index_summarize.test:34-40`),
отдаёт по каждой колонке `min, max, approx_unique, avg, std, q25/q50/q75, count,
null_percentage` **одним запросом на таблицу**. `min`/`max` заодно годятся как «примеры
значений» для промпта (проверено: на `search_corpus` они читаемые).

Замер на инстансе: `SUMMARIZE catalog_классификаторбанков` — **9.4 мс**.
233 таблицы × 9.4 мс ≈ **2.2 с** против ~90 с.

**Выигрыш.** Скорость ×40. Объём кода: `sample_values()` удаляется целиком.
**Проверено на инстансе:** да.
**Важность: блокирует.**

---

## 2. УХУДШАЕТ (штатное есть, мы не берём)

### 2.1 Индекс пересобирается с нуля каждый такт — вместо транзакционного сопровождения

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:865 (DROP INDEX) и :879-880 (CREATE INDEX)
```

**Сейчас.** Корпус обновляется инкрементально (`MERGE INTO`, :723 — это правильно), но
сразу после этого индекс **сносится и строится заново на всём корпусе**, каждый прогон.

**Штатно.** Инвертированный индекс SereneDB обновляется **транзакционно вместе с таблицей**
и переживает рестарт/WAL (`examples/demo2/README.md:8`; `index/inverted_index_isolation.test`).
Именно на это опирается наш же `MERGE`: тест движка отдельно оговаривает цель с
инвертированным индексом — «the index forces the commit-time append/delete path for every
merge action» (`tests/sqllogic/sdb/pg/dml/merge.test:2-3,46,57`).
Публикация свежих сегментов — штатной командой:

```sql
VACUUM (REFRESH_INDEX) search_idx;   -- или REFRESH_TABLE search_corpus
```
(`index/vacuum_options.test`; `refresh_interval=1000` мс стоит по умолчанию — проверено
в `reloptions` живого `search_idx`).

**Выигрыш.** Скорость такта: инкремент вместо полной пересборки (на 98 тыс. строк это
`index_sec` из отчёта сборки; на базе в 100 раз больше полная пересборка каждую ночь —
единственный элемент такта, растущий линейно с размером всей базы, а не с числом
изменений). Плюс исчезает окно, когда индекса нет, а сервис ответов уже работает.

**Оговорка:** `DROP/CREATE` оправдан только при **смене состава колонок или словаря**;
это уже отслеживается по `want != have_cols` (:754-760) — туда же и надо перенести.

**Проверено на инстансе:** частично (транзакционность и `VACUUM (REFRESH_*)` —
по тестам и справке движка; DDL не выполнялся по запрету).
**Важность: ухудшает.**

---

### 2.2 `optimize_top_k` не задан — WAND/Block-Max прунинг выключен на всех наших запросах

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:879-880 (CREATE INDEX без WITH)
       потребитель — ubuntu/serenedb/serene_ask.py:371 (ORDER BY bm25(...) DESC LIMIT)
```

**Сейчас.** `CREATE INDEX … USING inverted(doc, refs, src_table) INCLUDE (…)` — без
`WITH (…)`. Проверено на инстансе: `pg_class.reloptions` живого `search_idx` содержит
только умолчания, `optimize_top_k` отсутствует. `EXPLAIN` нашего запроса из `rows_of()`
показывает узел `TOP_N` **без** суффикса `, optimized`.

**Штатно.**
```sql
CREATE INDEX search_idx ON search_corpus USING inverted (...)
  WITH (optimize_top_k = 'bm25(1.2, 0.75)');
```
`site_docs/sql/indexes/inverted/ranking.test:32`, `index/inverted_index_optimize_top_k.test:1-20`,
`index/inverted_index_wand.test:1-17`. Писатель кладёт per-block max-impact, и
`ORDER BY bm25(idx.tableoid) DESC LIMIT k` исполняется с отсечением.

**Условие, которое надо выполнить у нас:** WAND срабатывает, только если скорер в
`ORDER BY` **совпадает** с записанным в индексе. У нас `ASK_SCORER` переключаемый
(`bm25` / `bm25_b0` / `tfidf`, serene_ask.py:74-79) — значит после A/B надо
зафиксировать победителя и записать именно его в `optimize_top_k`, иначе опция бесполезна.
Опция create-time-only (`ALTER INDEX` её отвергает).

**Выигрыш.** Скорость top-K. Сейчас на 98 тыс. документов запрос и так 5–6 мс, поэтому
измеримой выгоды **на нашем объёме нет** — выигрыш появляется на масштабе, где список
постингов длинный. Ставить вместе с 2.1 (всё равно пересоздаём индекс).
**Проверено на инстансе:** да (отсутствие опции и отсутствие `, optimized` в плане).
**Важность: ухудшает (на масштабе).**

---

### 2.3 Числовые/датовые условия не пушатся в постинги — они residual-фильтр

```
МЕСТО: ubuntu/serenedb/serene_ask.py:217-232 (_predicates), потребители :338, :357, :559
       причина — serene_search_build.py:879-880: amount/doc_date только в INCLUDE
```

**Сейчас.** `amount BETWEEN …`, `doc_date >= …` — обычные SQL-предикаты. Так как
`amount`/`doc_date` перечислены **только** в `INCLUDE`, движок применяет их как
`Column Filter` поверх скана.

Проверено `EXPLAIN` на инстансе: в `IRESEARCH_SCAN` секция `Index Filter:` содержит
только `Term` по `doc`, а `amount`/`doc_date` уходят в отдельную секцию `Column Filter:`.
Ровно то, что описано в `index/inverted_index_include_pushdown.test:1`.

**Штатно.** Колонка может быть **и ключом, и в `INCLUDE`** одновременно
(`index/inverted_index_indexed_vs_included.test:1-20`):
```sql
CREATE INDEX search_idx ON search_corpus
  USING inverted (doc search_dict, refs search_dict, src_table, amount, doc_date)
  INCLUDE (src_table, row_key, amount, doc_date);
```
после чего условие выражается запросом движка: `amount @@ ts_gt(500000)`,
`doc_date @@ ts_between(…, …, true, false)` — фильтр уходит в постинги и участвует в
пересечении вместе с текстовым термом.

**Выигрыш.** Масштаб: пересечение постингов вместо «найти всё по слову, потом отфильтровать».
На текущем объёме разницы нет (`count(*) … WHERE amount > 500000` — 0.88 мс по индексу).
**Проверено на инстансе:** да (план подтверждает разделение Index Filter / Column Filter).
**Важность: ухудшает (на масштабе).**

---

### 2.4 Эмбеддинги считаются питоновским пулом вместо `ai_embed()` в SQL

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:207-221 (embed), :23,:44-48,:780-834 (пул)
       ubuntu/serenedb/serene_ask.py:148-154 (embed_one), :548-549 (_vec)
       ubuntu/serenedb/serene_report.py:53-70 (embed, _vec_literal)
       ubuntu/serenedb/build_resolver_index.py:44-49
```

**Сейчас.** Четыре независимые реализации HTTP-похода в DashScope + собственный
`ThreadPoolExecutor(16)`, ручной батчинг по 10, ретраи, `inflight`-очередь,
сериализация вектора в SQL-литерал `'[…]'::FLOAT[1536]` — суммарно ~120 строк.

**Штатно.** `ai_embed(text, model, secret)` — функция движка, работает с любым
OpenAI-совместимым эндпоинтом (`demo5/bootstrap.sql:5-33`, `demo5/demo.sql:27-31`):

```sql
CREATE PERSISTENT SECRET dashscope (TYPE openai, api_key '…',
    base_url 'https://dashscope…', embeddings_path '/compatible-mode/v1/embeddings');

MERGE INTO search_corpus t USING (VALUES …) s (…)
  WHEN NOT MATCHED THEN INSERT VALUES (…, ai_embed(s.doc, 'text-embedding-v4', 'dashscope'));

SELECT … FROM search_tables ORDER BY emb <=> ai_embed('продажи','text-embedding-v4','dashscope');
```

Проверено на инстансе: `ai_embed(VARCHAR,VARCHAR,VARCHAR) -> FLOAT[]` есть в
`duckdb_functions()`; тип секрета `openai` есть в `duckdb_secret_types()`;
`duckdb_secrets()` пуст — секрет ещё не создан.

**Блокер, зафиксированный нами ранее и подтверждённый:** `docs/SERENEDB.md:116` —
у `ai_embed` **нет параметра `dimensions`**, DashScope отдал **1024**, а наш индекс и
`search_corpus.emb` объявлены `FLOAT[1536]`. Значит внедрение = смена `EMBED_DIM` на 1024
и пересборка корпуса, либо эндпоинт с нужной размерностью по умолчанию.

**Выигрыш.** Объём кода: минус ~120 строк и весь пул/ретраи/очередь. Правильность:
пропуски перестают быть «тихой пачкой» (`failed_batches`) — `ai_embed(NULL,…)` даёт NULL,
и недосчитанное видно как `count(*) FILTER (WHERE emb IS NULL)`
(`site_docs/sql/functions/ai_ollama.test_slow:41-76`). Скорость: не замерена, зависит от
параллелизма движка.

**Проверено на инстансе:** частично — функция и тип секрета есть; сквозной вызов не
делался (требует `CREATE SECRET`, то есть изменения на сервере).
**Важность: ухудшает.** Внедрять **только после A/B** (`ab_scorer.py`) на 1024 против 1536.

---

### 2.5 Векторный поиск — полный перебор косинуса, ANN-механизма нет ни в одном месте

```
МЕСТО: ubuntu/serenedb/serene_ask.py:920-922 (fallback по смыслу), :956-959, :969-973
       ubuntu/serenedb/serene_report.py:219-222 (_semantic_into)
       ubuntu/serenedb/build_resolver_index.py — таблица без индекса вовсе
```

**Сейчас.** Везде `array_cosine_similarity(emb, <литерал>)` + `ORDER BY … LIMIT` по
обычной таблице — это скалярная функция и полный скан, не механизм движка.
Замер на инстансе: перебор по `search_corpus` (97 965 × 1536) — **425 мс** на запрос.

**Штатно.** Опкласс `ivf` внутри инвертированного индекса + оператор дистанции
(`site_docs/sql/indexes/inverted/vector-search.test:9`), план `IRESEARCH_ANN_SCAN`:
```sql
CREATE INDEX … USING inverted (…, emb ivf (metric = 'cosine'));
SELECT src_table FROM idx ORDER BY emb <=> $1::FLOAT[1536] LIMIT 40;
```
Тюнинг — `sdb_nprobe` (8), `sdb_rerank_factor` (4) — обе настройки есть в сборке.

**Почему не внедряем прямо сейчас — и это надо сохранить в доках.** Сборка `ivf` на
96 931×1536 требовала >34 ГБ и убивалась OOM хоста (трижды, 2026-07-26;
`sdb_ivf_sample_factor` и `segment_memory_max` траекторию не меняли) —
`serene_search_build.py:866-871`, и запрет на создание `ivf` действует.

**Где `ivf` применим уже сегодня без риска:** `resolver_index` — **7 285 строк**
(проверено запросом), и `search_tables` — 232 строки. Это в 13 раз меньше объёма,
на котором сборка падала. Здесь `ivf` заменяет перебор в `_semantic_into`
(serene_report.py:219) штатным ANN.

**Отдельно: ложное утверждение в коде.** `build_resolver_index.py:10-12` пишет
«В SereneDB ЕСТЬ HNSW (проверено 2026-07-25)» и приводит DDL с `hnsw (m=32, ef_construction=64)`.
**В сборке 26.07.3 опкласса `hnsw` нет** — `pg_opclass` содержит только `ivf`, `included`
и по одному опклассу на словарь (проверено запросом; то же зафиксировано в
`docs/SERENEDB.md:161-163`). Этот комментарий обязан быть исправлен: он прямо
инструктирует будущего исполнителя выполнить DDL, который упадёт.

**Выигрыш.** Скорость: 425 мс → единицы мс на пути `serene_ask` fallback (после того как
объём позволит); на `resolver_index` — сразу. Правильность: убирается неверная инструкция в коде.
**Проверено на инстансе:** да (замер перебора, отсутствие `hnsw`, наличие `ivf`, размеры таблиц).
**Важность: ухудшает; строки 10-12 build_resolver_index.py — блокирует (ложная инструкция).**

---

### 2.6 Поле `refs` проиндексировано отдельно — и ни одним запросом не используется

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:879 (refs в ключах индекса)
       против ubuntu/serenedb/serene_ask.py:279, :318, :335 — всегда только `doc @@ …`
```

**Сейчас.** Сборка честно отделяет ссылки в `refs` и индексирует их своим словарём,
с обоснованием «спросить именно про контрагента и не получить склад, плюс можно поднять
вес поля». Но **ни один поисковый запрос `serene_ask` к `refs` не обращается** —
`probe()`, `match_expr()`, `rows_of()`, `tables_of()`, `aggregate()` используют только
`doc @@ …`. Единственный потребитель `refs` — `signal_terms()` (ts_dict_agg), то есть
подсказка модели, а не поиск.

**Штатно.** Два механизма, оба проверены на инстансе:
* пофилдовый запрос: `WHERE refs @@ ts_phrase('ромашка') OR doc @@ ts_phrase('ромашка')`
  — 8.6 мс, работает;
* буст поддерева: `doc @@ (ts_phrase('ромашка') ^ 3.0)` — работает
  (`cookbook/search/boosting.test:46`, `site_docs/.../full-text-search.test:206-210`).

То есть заявленная цель («поднять вес совпадения по ссылке») достижима штатно и
одной строкой, а сейчас не достигается вовсе: за `refs` мы платим местом в индексе и
временем сборки, не получая ранжирования.

**Выигрыш.** Правильность ранжирования (совпадение по имени контрагента должно весить
больше, чем случайное вхождение того же слова в текст) — размер эффекта **обязан
измеряться** `ab_scorer.py`, а не утверждаться.
**Проверено на инстансе:** да (оба синтаксиса выполнены).
**Важность: ухудшает.**

---

### 2.7 A/B гоняет 3 модели ранжирования из 7 и не проверяет ни бустов, ни RRF

```
МЕСТО: ubuntu/serenedb/ab_scorer.py:22 (SCORERS = ["bm25","bm25_b0","tfidf"])
       ubuntu/serenedb/serene_ask.py:74-78 (тот же список)
```

**Сейчас.** Три варианта. Проверено на нашем `search_idx` — работают **все семь** скореров:
```
bm25 5.925 | tfidf 6.305 | lm_jm 7.288 | lm_dirichlet 0.930
indri_dirichlet -6.032 | dfi 4.241 | raw_tf 3.000
```
**Штатно** (`site_docs/sql/functions/full_text_search.test:507-635`,
`server/catalog/scorer_options.cpp:55-198`): `lm_jm(oid, lambda)`,
`lm_dirichlet(oid, mu)`, `indri_dirichlet(oid, mu)`,
`dfi(oid, 'standardized'|'saturated'|'chi_squared')`, `bm25(oid, k1, b)`,
`tfidf(oid, with_norms)`. Плюс штатный обход ограничения «один скорер на запрос» —
RRF на `ROW_NUMBER()` + `SUM(1.0/(60+rank))` (`cookbook/search/reciprocal-rank-fusion.test:47-62`).

Правило владельца требует решать цифрами. Инструмент для этого уже написан —
надо лишь расширить список, это одна строка:
`SCORERS = ["bm25","bm25_b0","tfidf","lm_jm","lm_dirichlet","dfi"]` (+ соответствующие
записи в `serene_ask.SCORERS`).

**Выигрыш.** Правильность: решение о модели ранжирования принимается по 6-7 точкам, а не по 3.
**Проверено на инстансе:** да (все скореры выполнены на нашем индексе).
**Важность: ухудшает.**

---

### 2.8 CSV-сниффер типов вместо объявленных типов ридера

```
МЕСТО: ubuntu/serenedb/poc_load_entity.py:195-199 (read_csv без параметров)
```

**Сейчас.** `CREATE TABLE … AS SELECT * FROM read_csv('<путь>')` — тип каждой колонки
угадывает сниффер. Именно этот дефект описан в двух местах нашего же кода
(`serene_search_build.py:100-103, 547-551`): «сниффер типов превращает ИНН в число,
после чего "сумма документа" находится в паспортных данных контрагента», и лечится
это сейчас **вторым** источником правды — обращением к `$metadata` при сборке корпуса.

**Штатно.** У ридера есть параметры типов (`site_docs/cookbook/performance/file_formats.test:25`):
```sql
SELECT * FROM read_csv('<путь>', auto_detect=false, header=true,
                       columns={'ИНН':'VARCHAR','СуммаДокумента':'DOUBLE', …});
```
и `all_varchar=true` для «всё строкой» (проверено на инстансе: параметр `all_varchar`
принимается — ошибка приходит про файл, а не про параметр; неизвестный параметр движок
отвергает явно: `Invalid named parameter "zzz" for function read_csv`).

Объявленные типы у нас уже на руках: `declared_key()`/`$metadata` читается в том же файле
(:41-53) — карта `Edm.String → VARCHAR`, `Edm.Double → DOUBLE`, `Edm.DateTime → TIMESTAMP`.

**Выигрыш.** Правильность у источника: тип задаётся один раз при загрузке, а не
компенсируется вниз по конвейеру. Исчезает целый класс дефектов «витрина соврала про тип».
**Проверено на инстансе:** да (валидация параметров `read_csv`).
**Важность: ухудшает.**

---

## 3. КОСМЕТИКА

### 3.1 `doc` не в `INCLUDE` — проекция идёт lookup-ом в rocksdb

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:880 (INCLUDE без doc/refs)
       потребитель — serene_ask.py:369-376 (rows_of выбирает doc)
```
`EXPLAIN` на инстансе помечает источник колонок: `Projections: doc (l), src_table (i),
row_key (i), amount (i), doc_date (i)` — `(l)` = lookup в rocksdb, `(i)` = columnstore
(`index/inverted_index_explain_source.test:1-6`). Штатно — добавить `doc` в `INCLUDE`.
Замер: `SELECT row_key, doc … LIMIT 40` — 5.4-6.4 мс; без `doc` — 3.5-5.7 мс.
Разница ~2 мс на 40 строках, растёт с числом строк. **Важность: косметика.**

### 3.2 `stemming = false` в словаре — морфологию добираем `ts_levenshtein`

```
МЕСТО: ubuntu/serenedb/serene_search_build.py:858-860
       компенсация — serene_ask.py:275-276 (ts_levenshtein с расстоянием len//4)
```
Штатный механизм — `stemming = true` в `template='text'` (`inverted/text-analysis.test:64-67`),
или `template='pipeline'` со `stepN_template='stem'`. Сейчас словоформы ловятся
редакционным расстоянием, что и шире (ложные срабатывания), и дороже.
Менять **только через A/B**: стемминг режет точность на кодах и артикулах, а расстояние
`min(2, len//4)` уже подобрано замером. **Важность: косметика (кандидат на A/B).**

### 3.3 Неиспользуемые словари под подстроку и wildcard

`ts_like('%слово%')` (serene_ask.py:277) исполняется перебором термов. Штатно есть
`template='wildcard'` (ngramsize=3) — словарь, который ускоряет именно `ts_like`, и
`template='sparse_ngram'` (индексная + запросная сторона, `demo6/demo.sql:30-33`) —
подстрочный поиск конъюнкцией грамов с `LIKE`-постфильтром. Оба шаблона есть в бинарнике
26.07.3 (проверено `strings`). На нашем объёме `ts_like` по индексу — 6 мс, поэтому
выгоды сегодня нет; кандидат на масштаб. **Важность: косметика.**

### 3.4 Мёртвый код

`ubuntu/serenedb/serene_ask.py:235-241` — функция `_fetch()` определена и **ни разу не
вызывается** (её роль исполняет `rows_of()` начиная со строки 357). Проверено grep-ом.
**Важность: косметика.**

### 3.5 `profile_table()` — свои агрегаты вместо `SUMMARIZE`

`ubuntu/serenedb/serene_search_build.py:293-331` конструирует строку из
`count(DISTINCT …)` и `max(abs(TRY_CAST(…)))`. `SUMMARIZE "<t>"` даёт `approx_unique`,
`min`, `max`, `count` по всем колонкам одной командой и без TRY_CAST-обвязки
(проверено: 9.4 мс на таблице). Здесь это уже один запрос на таблицу, поэтому выигрыш
только в объёме кода. **Важность: косметика.**

---

## Где штатного НЕТ и своё оправдано

1. **Гейт чисел** — `serene_ask.py:662-896` (`_readings`, `_tokens`, `_dates`, `gate`,
   `check_claims`, `claims_in_text`). Разбор числовых токенов ответа модели по всем
   локальным записям разрядов и покомпонентная сверка дат — задача клиента, у движка
   такого механизма нет и быть не может. **Не переделывать.**
2. **Разбор намерения и выбор сущности моделью** — `serene_ask.py:161-213, 379-545`.
   Сопоставление слова человека с названием сущности — языковая задача; ближайший
   механизм движка (эмбеддинг названия) уже замерен и проигрывает (в комментарии на
   :461-464 приведены цифры). Свой код обоснован.
3. **Валидатор LLM-SQL** — `serene_report.py:377-458`. AST-allow-list поверх
   `json_serialize_sql` — единственный работающий энфорсмент: движковый
   `allowed_directories` под ro-ролью no-op, `enable_external_access` — глобальный
   one-way латч (наша проверка, :31-42; на инстансе `enable_external_access = on`,
   `allowed_directories = []`). RBAC движка PG-совместим и по критерию владельца
   отдельным механизмом SereneDB не считается. **Своё оправдано, помечено как своё.**
4. **Пагинация OData и сверка с `$count`** — `poc_load_entity.py:88-124`. Движок не
   умеет ходить в OData; `read_json_auto` по `http://` существует, но передать
   `Authorization: Bearer` через секрет нельзя — в бинарнике 26.07.3 нет
   `extra_http_headers` (проверено `strings`; есть только `bearer_token` для GCS).
5. **Перепись базы через `$metadata`/`$count`** — `odata_census.py` целиком. Источник
   истины о ключах и типах — 1С, а не движок.
6. **Отрисовка графика (matplotlib)** — `serene_report.py:501-532`. Механизма нет.
7. **`split_camel`, `safe_col`, `protocol_companion`, `machine_token`** — знание о
   контракте платформы 1С. К движку отношения не имеет.

---

## Что мы используем штатно и трогать не надо

| Место | Механизм движка |
|---|---|
| `serene_search_build.py:723-731` | `MERGE INTO … WHEN MATCHED/NOT MATCHED` — ровно тот путь, который тест движка оговаривает для цели с инвертированным индексом |
| `serene_search_build.py:858-860` | `CREATE TEXT SEARCH DICTIONARY (template='text', case='lower', frequency, position, norm)` — `position=true` **несущий**: без него не работают ни фразы со слопом, ни `ts_offsets`/`ts_highlight` (проверено: офсеты синтезируются из позиций, `index/ts_offsets_isolation.test:1-10` — отдельный `offset=true` не обязателен) |
| `serene_search_build.py:879-880` | пофилдовая индексация в **одном** индексе + `src_table` без словаря (keyword) + `INCLUDE` |
| `serene_ask.py:238, 349, 367` | обращение **от имени индекса** (`FROM search_idx`), а не от таблицы — везде корректно |
| `serene_ask.py:261-277` | `ts_phrase`, `ts_phrase(a, ARRAY[0,n], b)` со слопом, `ts_levenshtein`, `ts_like` — строители запросов движка |
| `serene_ask.py:322-335` | `ts_compound(NULL, NULL, [...], k)` — булев запрос движка с `min_should_match` (замер в комментарии: 6.9 мс против 42.5 мс у самодельного цикла) |
| `serene_ask.py:303` | `ts_any([...])` |
| `serene_ask.py:349` | `GROUP BY src_table` по keyword-колонке индекса — фасет из словаря термов (4.9 мс на 98 тыс.) |
| `serene_ask.py:369` | `ts_highlight(doc, 'MaxWords=…,MaxFragments=…,StartSel=…')` — подсветка движка |
| `serene_ask.py:371` | скореры `bm25`/`bm25(k1,b)`/`tfidf` через `<index>.tableoid` |
| `serene_ask.py:414-423` | `ts_dict_agg` + `ts_dict_count` — рецепт significant terms из кукбука движка |
| `serene_ask.py:559-578` | агрегаты **в базе по всему множеству**, без `LIMIT` — контракт соблюдён |
| `poc_load_entity.py:195-196` | `read_csv(...)` + `QUALIFY row_number() OVER (…)` — оба конструкции этого движка |
| `serene_report.py:400-436` | `json_serialize_sql()` — интроспекция AST средствами движка |
| `serene_report.py:126-128, 173-174, 395-396` | `duckdb_columns()` вместо `information_schema` (под ro-ролью последняя пуста) |

---

## Спорное

1. **`resolver_index` целиком.** Если внедрить 1.1 (`ts_dict_score` по индексу над
   значениями измерений), лексический и семантический слои резолвера решают одну и ту же
   задачу разными средствами. Чем закрыть «питер → Санкт-Петербург» — редакционным
   расстоянием по словарю термов или эмбеддингом — **не знаю без A/B**; замер
   `measure_resolver.py` мерил только эмбеддинг. Не хватает: прогона `ts_levenshtein` +
   `ts_ngram` на том же наборе токенов, что и в `measure_resolver.py`.
2. **`ivf` на `search_corpus`.** OOM зафиксирован трижды на 96 931×1536. Является ли это
   дефектом сборки, свойством `quant='none'` (по умолчанию векторы хранятся сырыми) или
   следствием `sdb_ivf_posting_size` — **не установлено**. Не хватает: прогона с
   `quant='sq8'`/`'pq'` (в 4-8 раз меньше памяти под векторы), но это DDL, запрещённый
   в этом аудите.
3. **Замена `search_corpus` на индекс поверх VIEW к витрине.** `docs/SERENEDB.md:186-209`
   уже описывает рабочий рецепт (`INCLUDE` + PG-view). Это убрало бы дублирование данных
   и всю сборку корпуса, но материализация «настоящих» колонок из view-backed индекса
   поддержана только для плоской проекции из одного `read_*` — наш корпус собирается из
   233 разнородных таблиц. Обход есть (всё нужное в `INCLUDE`, шаблон demo6), но цена
   пересборки и риск не оценены. Не хватает: пробного индекса над view (DDL).
4. **`storage = 'search'` для `search_corpus`** (`simple/search_table.test:1-70`) —
   таблица целиком в iresearch-columnstore, с проталкиванием фильтров внутрь кодека.
   Потенциально снимает и lookup из 3.1, и residual-фильтр из 2.3. В демках движка не
   используется, только в низкоуровневых тестах кодеков — **не берусь рекомендовать**
   без прогона.
5. **Батч-эмбеддинг в `ai_embed`.** Наш пул шлёт по 10 текстов в запрос (лимит DashScope).
   Как `ai_embed` группирует вызовы внутри вектора значений — из исходников не выяснил;
   при построчных запросах сборка корпуса может стать медленнее, а не быстрее.
   Не хватает: сквозного замера (требует `CREATE SECRET`).

---

## Итог: что действительно надо переделать, по порядку

1. `serene_report.py:169-202` — резолвер на `ts_dict_agg`/`ts_dict_score` вместо
   `LIKE` + `jaro_winkler` по 2297 колонкам (**~84 с → мс**).
2. `serene_report.py:122-154` — `SUMMARIZE` вместо ~2530 процессов `psql` (**~90 с → ~2 с**).
3. `build_resolver_index.py:10-12` — убрать ложное «в SereneDB есть HNSW»; в сборке
   26.07.3 только `ivf`.
4. `serene_search_build.py:865` — перестать сносить индекс каждый такт; `VACUUM (REFRESH_INDEX)`.
5. `serene_search_build.py:879-880` — `amount`/`doc_date` в ключи индекса (пушдаун),
   `doc` в `INCLUDE`, `WITH (optimize_top_k = '<скорер-победитель A/B>')`.
6. `serene_ask.py` — начать использовать проиндексированное поле `refs` (пофилдовый
   запрос + `^`-буст), результат подтвердить `ab_scorer.py`.
7. `ab_scorer.py:22` — расширить список до шести скореров.
8. `poc_load_entity.py:195` — `read_csv(..., auto_detect=false, columns={…})` по `$metadata`.
9. `serene_ask.py:235` — удалить мёртвую `_fetch()`.
10. `ai_embed()` — после A/B на размерности 1024 против нашей 1536.
