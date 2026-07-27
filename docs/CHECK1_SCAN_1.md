# CHECK1_SCAN_1 — точный перебор по FLOAT[1536] в SereneDB 26.07.3: план, параллельность, префильтр, предел

Дата: 2026-07-27. Инстанс: `host=127.0.0.1 port=7890 user=postgres dbname=postgres`
(через `ssh root@192.168.56.42`, psql на самом сервере). Репозиторий: `/srv/data/cursor/cursor/1/serenedb-src`.

Никаких CREATE/DROP/ALTER/INSERT/UPDATE/DELETE/VACUUM не выполнялось. Только SELECT / EXPLAIN /
справочные функции + сессионные `SET` (`late_materialization_max_rows`, `sdb_disable_top_k_optimization`).

Объект: `public.search_corpus(src_table VARCHAR, row_key VARCHAR, doc VARCHAR, refs VARCHAR,
doc_hash VARCHAR, amount DOUBLE, doc_date TIMESTAMP, emb FLOAT[1536])`, 97 965 строк [вывод: `duckdb_tables()`].
Индекс: `CREATE INDEX search_idx ON public.search_corpus USING inverted(doc <dict>, refs <dict>, src_table)
INCLUDE (src_table, row_key, amount, doc_date)` — **`emb` в индекс НЕ входит**
[код: `/srv/data/cursor/cursor/1/1c/ubuntu/serenedb/serene_search_build.py:879`].

Оговорка к цифрам: сервер 6 ядер, во время замеров load average ~11-13 (машина не изолирована).
Абсолютные значения шумят ±10 %, но все сравнения делались чередованием форм в одной сессии.

---

## 1. Форма запроса и план

### 1.1 Планы трёх форм — одинаковые по структуре

[вывод] `EXPLAIN (FORMAT json) SELECT row_key FROM search_corpus ORDER BY <форма> LIMIT 10`
даёт для **всех трёх** форм (`<=>`, `<#>`, `array_cosine_similarity(...) DESC`) идентичное дерево:

```
ORDER_BY  (#1 ASC/DESC, ~98508 rows)
└─ PROJECTION [row_key, <выражение расстояния>]
   └─ HASH_JOIN  Join Type: SEMI, Conditions: rowid = rowid
      ├─ SEQ_SCAN search_corpus  Projections: [row_key, emb]
      └─ TOP_N  Top: 10, Order By: #0
         └─ PROJECTION [<выражение расстояния>]
            └─ SEQ_SCAN search_corpus  Projections: emb
```

Что делает движок: один последовательный проход по колонке `emb`, расстояние считается **в PROJECTION
под TOP_N** (по всем 97 965 строкам), TOP_N держит кучу на 10 элементов; затем semi-join по `rowid`
обратно к таблице, чтобы дотащить `row_key`, и пересчёт выражения для выживших 10 строк.

Это штатная оптимизация DuckDB **late materialization**, включается когда `LIMIT <= late_materialization_max_rows`
[вывод: `duckdb_settings()` → `late_materialization_max_rows = 50`, «The maximum amount of rows in the
LIMIT/SAMPLE for which we trigger late materialization»].

[замер] Она нам **ничего не портит и ничего не даёт**: `SET late_materialization_max_rows=0` убирает
semi-join (план становится `TOP_N ← PROJECTION ← SEQ_SCAN`), а время не меняется:
- с late-mat: 311 / 345 / 300 мс
- без late-mat: 316 / 306 / 300 мс

Вывод: **трогать эту настройку смысла нет**.

### 1.2 Все формы записи, доступные в нашей сборке

[вывод] `duckdb_functions()`: `array_cosine_distance`, `array_cosine_similarity`, `array_distance`,
`array_inner_product`, `array_dot_product`, `array_negative_inner_product`, `array_negative_dot_product`
— каждая в двух перегрузках `FLOAT[ANY]` и `DOUBLE[ANY]`. Операторы: `<=>`, `<->`, `<#>`.
Функций `cosine_distance` / `l2_distance` (имена pgvector) **нет**.

[замер] Одна сессия, `LIMIT 10 OFFSET 9`, по 1-2 прогона на форму:

| форма | время |
|---|---|
| `emb <=> q` | 308, 321 мс |
| `emb <#> q` | 360, 309 мс |
| `emb <-> q` | 322 мс |
| `array_cosine_distance(emb, q)` | 440, 410 мс |
| `array_cosine_similarity(emb, q) DESC` | 433, 422 мс |
| `array_distance(emb, q)` | 449 мс |
| `array_inner_product(emb, q) DESC` | 432 мс |
| `array_negative_inner_product(emb, q)` | 450 мс |

Чередованный контрольный прогон (`<=>` / `array_cosine_distance` подряд, 3 пары):
355/435, 299/448, 314/424 мс. Разрыв устойчивый: **операторы быстрее именованных функций на ~25-30 %**.

### 1.3 Почему `array_cosine_similarity` медленнее оператора

Не из-за плана — планы совпадают. Оператор **не является алиасом функции**, это другая реализация:

[замер] `SELECT count(*) FROM search_corpus WHERE (emb <=> q) IS DISTINCT FROM array_cosine_distance(emb, q)`
→ **20 382** строки из 97 965 дают разные значения.
`SELECT max(abs((emb <=> q) - array_cosine_distance(emb, q)))` → **2.38e-07**;
для `<#>` vs `array_negative_inner_product` → **1.71e-07**. `typeof` у обоих `FLOAT`.

Т.е. математика та же, разный порядок накопления → разный (векторизованный) кернел. Расхождение на уровне
FLOAT-эпсилон, на ранжирование не влияет; экономия 25-30 % — влияет.

**Практический вывод: везде использовать операторы `<=>` / `<#>` / `<->`, никогда — `array_*`.**

### 1.4 Побочная находка: стоимость литерала в тексте запроса

[замер] Разбор одного 11 335-байтового литерала `CAST([...1536 чисел...] AS FLOAT[1536])` стоит
**25 мс**: `SELECT (<литерал>)[1];` → 25.4 / 25.4 мс.
Тот же запрос через bind-параметр расширенного протокола (`$1::FLOAT[1536]`, как в
`examples/demo4/demo.sql:58`) — 266 / 287 мс против 293 мс с инлайн-литералом.
Экономия ~20-25 мс (7-8 %) «бесплатно», если клиент передаёт вектор параметром, а не подставляет в текст.

---

## 2. Параллельность

### 2.1 Факт: перебор идёт в ОДИН поток

[вывод] `duckdb_settings()`: `threads = 6`, `worker_threads = 6`, `external_threads = 0`,
`parallelize_sequential_sources = on`, `standard_vector_size = 2048`. `nproc` = 6.

[замер] Дельта `utime+stime` процесса `serened` (поля 14+15 `/proc/PID/stat`) вокруг запроса:

| запрос | wall | cpu |
|---|---|---|
| `ORDER BY emb <=> q LIMIT 10` | 341 / 342 / 437 мс | 280 / 260 / 270 мс |
| `SELECT count(*) ... regexp_matches(doc, ...)` | 160 мс | 100 мс |

cpu/wall ≈ 0.8 (в wall входит ~40-50 мс на запуск psql и разбор литерала). Если бы работали 6 потоков,
cpu был бы ~1.6-2 с. **Работает один поток.**

[замер] Прямой счёт занятых потоков во время длинного запроса (`ps -L`, дельта cpu за 3 с):
`cpu_ticks_in_3s=290 → threads_busy=0.96`, `running_threads=1`.

### 2.2 Что за это отвечает в коде

- Скан **таблицы** — это DuckDB `SEQ_SCAN`; он распараллеливается по row-group'ам. 97 965 строк меньше
  одной row-group (122 880) → одна единица работы → один поток. [вывод; прямого подтверждения из
  `pragma_storage_info` получить не удалось — она возвращает 0 строк для таблиц SereneDB, см. раздел
  «Чего я не смог выяснить»]
- Скан **индекса** (`IRESEARCH_SCAN`) параллелится штатно и явно:
  [код] `server/connector/duckdb_search_full_scan.hpp:242-254` —
  ```
  duckdb::idx_t MaxThreads() const final {
    switch (mode) {
      case ScanMode::CountFast: return 1;
      case ScanMode::ColScan:   return max(1, col_scan.units.size());
      default:                  return max(1, scorer_obj ? total_segments : claimable_segments);
    }
  }
  ```
  [код] `server/connector/duckdb_search_full_scan.cpp:1291-1302` — размер «unit» в режиме `ColScan`
  берётся из `inverted_index->GetOptions().row_group_size` (умолчание `DEFAULT_ROW_GROUP_SIZE`,
  оно же `row_group_size = 122880` в `duckdb_settings()`):
  ```
  uint64_t rg_rows = bind_data.inverted_index ? ...->GetOptions().row_group_size : 0;
  if (rg_rows == 0) rg_rows = DEFAULT_ROW_GROUP_SIZE;
  const uint64_t unit_rows = rg_rows >= DEFAULT_ROW_GROUP_SIZE ? rg_rows
                                                               : DEFAULT_ROW_GROUP_SIZE / rg_rows * rg_rows;
  ```
  [код] `server/connector/duckdb_search_full_scan.cpp:969-996` `DecideScanMode` — `ColScan` выбирается
  только когда запрос `IsMatchAll()` (нет фильтра по индексу), нет `needs_lookup` (все выводимые колонки
  лежат В индексе) и есть хотя бы одна реальная колонка. Иначе `Stream`, и там параллельность = число
  сегментов индекса.

**Ключ:** чтобы `ColScan` вообще применился к `emb`, `emb` должен быть колонкой индекса (`INCLUDE`),
а не подтягиваться lookup'ом из таблицы. У нас он lookup — см. раздел 3.

### 2.3 Ручное распараллеливание (UNION ALL по диапазонам rowid) — НЕ работает

[замер] `min(rowid)=97974, max(rowid)=195938, count=97965` (rowid плотный, но со смещением).

Форма из demo-подобной практики «разрезать на N веток, в каждой свой TOP-K, потом слить»:
```sql
SELECT ... FROM (
  (SELECT row_key, emb <=> q AS d FROM search_corpus WHERE rowid >= a AND rowid < b ORDER BY d LIMIT 10)
  UNION ALL
  (SELECT ... )
) ORDER BY d LIMIT 10;
```
даёт **ошибку движка**:
```
ERROR:  Attempted to access index -1 within vector of size 8
```
Воспроизводится на 2, 4, 6, 12 ветках. Изолировано: одна ветка (`WHERE rowid ... ORDER BY d LIMIT 10`)
работает (176 мс на 52 026 строк); `UNION ALL` без внутреннего `ORDER BY ... LIMIT` работает (8 мс);
падает именно комбинация «UNION ALL + внутренний ORDER BY по расстоянию + LIMIT». Это баг 26.07.3.

Вариант без внутреннего `ORDER BY` (сортировка снаружи) отрабатывает, но **медленнее** базовой формы:
2 ветки — 421 мс, 6 веток — 362 мс против 336 мс у обычного `ORDER BY emb <=> q LIMIT 10`.

[замер] `UNION ALL` из 4 одинаковых полных сканов: wall 888 мс, cpu 1360 мс → занято ~1.6 потока,
т.е. даже когда ветки идут параллельно, ускорения нет — упирается не в CPU (см. раздел 4.1).

**Итог по параллельности: штатного способа распараллелить перебор по `emb` на нашей конфигурации нет.
Единственный штатный рычаг — положить `emb` в `INCLUDE` индекса с уменьшенным `row_group_size`
(раздел 4.2); проверить это замером мы не могли (нужен CREATE INDEX).**

---

## 3. Префильтр — ГЛАВНОЕ. Да, работает, и очень хорошо

### 3.1 Форма есть в демках и в тестах

[код] `examples/demo4/demo.sql:75-82` — Q3, ровно наш случай (фильтр текстом, порядок вектором):
```sql
SELECT title, left(text, 80) AS snippet
FROM dbpedia_idx d
WHERE text @@ (ts_phrase('physicist')
               && !!ts_phrase('philosophy')
               && (ts_phrase('quantum mechanics') || ts_phrase('general relativity')))
ORDER BY d.embedding <=> $1::FLOAT[1536]
LIMIT 5
```
[код] `tests/sqllogic/sdb/pg/index/inverted_index_filter_pushdown.test:220,228`:
`SELECT id FROM fpvecs_idx WHERE val >= 30 ORDER BY emb <-> [0,0,0]::FLOAT[3] LIMIT 2;`
[код] `tests/sqllogic/sdb/pg/index/vector_search.test_slow:255-287` — эталонные (brute-force) ответы для
комбинаций «текстовый предикат + ORDER BY вектор», в т.ч. `WHERE body IN (...) AND id > 10000`.

### 3.2 План на нашем инстансе: множество сужается ДО вычисления расстояний

[вывод] `EXPLAIN SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('реализация') ORDER BY emb <=> q LIMIT 10;`
```
TOP_N  Top: 10, Order By: #1 ASC
└─ PROJECTION [row_key, (emb <=> [...])]
   └─ IRESEARCH_SCAN
      Index: search_idx
      Lookup: table
      Index Filter: Term { Field: doc(string), Value: "реализация" }
      Projections: row_key (i), emb (l)
```
Никакого `SEQ_SCAN` по таблице. `Index Filter` применяется внутри скана индекса; `PROJECTION`
(где и считается `<=>`) стоит НАД сканом, то есть расстояние считается только для выживших строк.

[код] расшифровка `(i)`/`(l)`: `server/connector/duckdb_table_function.cpp:757-762` —
`e.from_index ? "i" : "l"` («i» = колонка отдана колоночным хранилищем индекса, «l» = lookup в базовое
отношение). У нас `row_key (i)`, `emb (l)` — `emb` дотягивается из таблицы построчно, потому что его нет
в `INCLUDE`.

Скалярный предикат по `INCLUDE`-колонке тоже уезжает внутрь скана:
[вывод] `EXPLAIN ... FROM search_idx WHERE amount > 100000 ORDER BY emb <=> q LIMIT 10` →
`IRESEARCH_SCAN ... Column Filter: amount > 100000`.
Комбинация «текст И скаляр» — оба фильтра внутри одного скана:
[вывод] `WHERE doc @@ ts_phrase('организация') AND amount > 0` →
`Index Filter: Term{doc="организация"}` + `Column Filter: amount > 0`, оценка `~3 918 rows`.

### 3.3 Замеры: время линейно по числу отобранных строк

[замер] `SELECT md5(string_agg(row_key,'|')) FROM (SELECT row_key FROM search_idx WHERE doc @@ ts_phrase(T)
ORDER BY emb <=> q LIMIT 10);` одна сессия, один вектор:

| термин | строк по фильтру | время |
|---|---|---|
| `справочник` | 57 | 31 мс |
| `документ` | 538 | 40 мс |
| `2023` | 872 | 36 мс |
| `организация` | 1 213 | 47 мс |
| `реализация` | 392 | 45 / 40 мс |
| `true` | 36 121 | 205 мс |
| `false` | 45 936 | 284 мс |
| — (полный перебор по таблице) | 97 965 | 313 мс |

Дополнительно, предикат по обычной колонке **самой таблицы** тоже сужает до вычисления расстояний:
[вывод] `EXPLAIN ... FROM search_corpus WHERE src_table = 'catalog_пользователи' ORDER BY emb <=> q LIMIT 10`
→ `SEQ_SCAN ... Column Filter: optional: (src_table = 'catalog_пользователи')`, и
[замер] время **29.6 мс** при 5 подходящих строках (против 313 мс без фильтра).

### 3.4 Как это читать

- Фиксированная плата за путь через индекс ≈ **28-30 мс** (даже при 5-57 строках). Дальше ~5.7 мкс на строку
  (lookup `emb` из таблицы построчно).
- Прямой скан таблицы: ~3.2 мкс на строку, старт почти бесплатный.
- **Точка безубыточности ≈ 55-60 тыс. строк.** Если фильтр оставляет меньше — идти через `search_idx`
  (при 1 тыс. строк выигрыш 313→47 мс, ~6.7x; при 400 строках 313→40 мс, ~8x). Если фильтр почти ничего
  не отсекает (>60 тыс.) — дешевле обычный `FROM search_corpus`.
- **Полный скан ЧЕРЕЗ индекс без WHERE — худший вариант:** [замер] `SELECT row_key FROM search_idx
  ORDER BY emb <=> q LIMIT 10` = **541 / 549 мс** против 313 мс от таблицы. Причина — `emb (l)`,
  построчный lookup 97 965 раз. Без фильтра к индексу обращаться нельзя.

---

## 4. Что ещё штатно ускоряет перебор

### 4.1 Где на самом деле уходит время (это определяет, что вообще может помочь)

[замер] в одной сессии:
- `SELECT sum(emb[1]) FROM search_corpus;` → **250 / 241 мс**
- `SELECT sum(emb[1]+emb[1536]) FROM search_corpus;` → **225 мс**
- `SELECT min(emb <=> q) FROM search_corpus;` → **322 / 322 мс**
- `SELECT sum(length(doc)) FROM search_corpus;` → 16 мс (для масштаба)

Т.е. из ~320 мс **~245 мс — это чтение колонки** (97 965 × 1536 × 4 Б = 602 МБ, ≈2.5 ГБ/с) и только
~77 мс — сама арифметика. **Перебор упирается в пропускную способность чтения, не в CPU.**
Отсюда: ускорить можно только «читать меньше байт» или «читать в несколько потоков».

### 4.2 Разбор кандидатов

| механизм | что делает по коду | применимо к перебору БЕЗ ivf |
|---|---|---|
| `optimize_top_k` (опция `WITH` у индекса) | принимает **выражение скорера** (BM25/TFIDF); `server/catalog/scorer_options.cpp:210-259`: «'optimize_top_k' expects a scorer function call» | **нет** — только текстовые скореры |
| `sdb_disable_top_k_optimization` | описание в `duckdb_settings()`: отключает затягивание `ORDER BY <scorer>(...) DESC LIMIT k` в скан индекса и WAND-отсечение | **нет**. [замер] `SET ...=true` → 298 мс, без изменений |
| `late_materialization_max_rows` (50) | порог LIMIT для late materialization (раздел 1.1) | есть, но [замер] эффекта 0 |
| **`INCLUDE (emb)` в инвертированном индексе** | [код] `tests/sqllogic/sdb/pg/index/inverted_index_array_include.test:28-30`: `CREATE INDEX arr_t_idx ON arr_t USING inverted(pk, text_for_search en) INCLUDE (vec)` при `vec FLOAT[3]` — **вектор можно класть в INCLUDE без всякого векторного опкласса**. Тогда `emb` станет `(i)` вместо `(l)`, а `DecideScanMode` сможет выбрать `ColScan` | **да, главный нереализованный кандидат** (см. ниже) |
| `row_group_size` на `INCLUDE`-колонке | [код] `duckdb_search_full_scan.cpp:1291-1302` — определяет `unit_rows`, а `MaxThreads() = col_scan.units.size()`. [код] `inverted_index_compression_option.test:230-236`: «`row_group_size` was dropped from the IVF opclass; it stays valid on the `included` opclass» — синтаксис `INCLUDE (emb included (row_group_size = N))` | **да**, но только вместе с `INCLUDE (emb)`; при 97 965 строках и `row_group_size=16384` получится 6 units → до 6 потоков |
| сжатие колонки | [код] `inverted_index_compression_option.test:1-5`: `compression` пинит кодек на `INCLUDE`-колонке; **«vectors always use the auto codec»** | частично: для `FLOAT[]` кодек выбирается автоматически (ALP/ALPRD), пользовательская опция игнорируется |
| FLOAT vs DOUBLE | обе перегрузки есть; у нас уже `FLOAT` = 4 Б/элемент | уже оптимально, DOUBLE удвоил бы чтение |
| предвычисленные нормы + `<#>` | [вывод] в сборке есть `l2_norm`, `l2_normalize`, `l1_norm`, `l1_normalize`, `normalize` | **выигрыша нет**: [замер] `<#>` 360/309 мс против `<=>` 308/321 мс — считать норму дёшево, узкое место — чтение |
| квантование (SQ8 / PQ / RaBitQ) | [код] `server/catalog/index.cpp:302-396` — `quant` это опция **опкласса ivf** (`ivf (metric=..., quant='sq8'|'pq'|'rabitq')`); отдельных SQL-функций квантования нет [вывод: в `duckdb_functions()` ничего по `quant`/`rabit`/`sq8`] | **нет** — единственный способ читать в 4 раза меньше байт заперт внутри ivf, который у нас запрещён |
| `hnsw` | [вывод] `strings /usr/local/bin/serened \| grep -ciw hnsw` → **0**. Полностью отсутствует в 26.07.3 | нет |
| bind-параметр вместо литерала | `examples/demo4/demo.sql:52-60`: «the cast `$1::FLOAT[1536]` folds at plan time» | **да**, −25 мс (раздел 1.4) |
| `sdb_nprobe`, `sdb_rerank_factor`, `sdb_ivf_posting_size`, `sdb_ivf_sample_factor` | [вывод] есть в `duckdb_settings()` | ivf-only, к перебору неприменимы |

**Единственный неиспробованный штатный рычаг с реальным потенциалом:**
```sql
CREATE INDEX ... USING inverted(doc <dict>, refs <dict>, src_table)
  INCLUDE (src_table, row_key, amount, doc_date, emb included (row_group_size = 16384));
```
Ожидание по коду: (а) для запросов с фильтром исчезает построчный lookup `emb (l)` → снимается плата
~5.7 мкс/строку, кривая из 3.3 должна лечь на ~3 мкс/строку; (б) для запроса без фильтра включается
`ColScan` с 6 units → до 6 потоков (`MaxThreads() = col_scan.units.size()`).
Цена: +602 МБ на диске (копия векторов) и время пересборки индекса.
**Не проверено замером** — требует CREATE INDEX, что в этой задаче запрещено. Риск ivf-подвисания
здесь не возникает: `included` — не векторный опкласс.

---

## 5. Замеры перебора в самом движке

**Полноценных бенчмарков brute-force по векторам большой размерности в репозитории нет.** Что есть:

- [код] `tests/sqllogic/sdb/pg/index/vector_search.test_slow:1-35` — перебор используется как **эталон
  правильности** для ivf, а не как рабочий путь. 50 000 строк, **8 измерений**:
  ```
  CREATE TABLE vecs (id INT, emb FLOAT[8]);
  INSERT INTO vecs SELECT s, [sin(s*0.001)::FLOAT, cos(s*0.001)::FLOAT, ...]::FLOAT[8]
    FROM generate_series(1, 50000) AS s;
  INSERT INTO correct SELECT id FROM vecs
    ORDER BY emb <-> [0.0,1.0,0.0,1.0,0.0,1.0,0.0,1.0]::FLOAT[8] LIMIT 512;
  INSERT INTO correct_filtered SELECT id FROM vecs WHERE id > 25000
    ORDER BY emb <-> [...]::FLOAT[8] LIMIT 512;
  ```
  Дальше recall ivf сверяется с `correct` / `correct_filtered`. Тайминги не собираются.
- [код] `scripts/perf/iresearch_sweep/cases.manifest:20` — единственный векторный perf-кейс, и он про hnsw:
  ```
  hnsw	pk, body hnsw (metric = 'l2', m = 16)	SELECT pk FROM sweep_t ORDER BY body <-> list_transform(range(128), x -> 0.5::FLOAT)::FLOAT[128] LIMIT 10	...	200000	1000000
  ```
  128 измерений, 200 000 и 1 000 000 строк. **Опкласса hnsw в нашей сборке нет**, кейс неповторим.
- [код] `scripts/perf/hnsw_index_size.sh:81,94` — `CREATE TABLE bench (id BIGINT PRIMARY KEY, vec FLOAT[${DIM}])`,
  измеряется размер индекса, не скорость перебора; hnsw.
- [код] `scripts/perf/gen_filtered_topk_report.sh` — «filtered-top-k A-vs-B», но A/B там про
  `sdb_disable_top_k_optimization` и `ORDER BY BM25(...)`, **текст, не вектор**.
- [код] `examples/demo4/demo.sql` — 100 тыс. abstracts × 1536, но все три векторных запроса рассчитаны
  на HNSW-граф (`IRESEARCH_ANN_SCAN` / `IRESEARCH_ANN_RANGE_SCAN`), не на перебор.
- [код] `scripts/perf/run_nested_perf.sh:120`, `full_matrix.sh:245` — `FLOAT[3]`, векторы там просто как тип данных.

Максимальная размерность, встречающаяся в тестах перебора: **8**. Максимальная в perf-скриптах: **128** (и то ANN).
**Перебор по 1536 измерениям на ~100 тыс. строк в движке не бенчмаркался ни разу.**

---

## Что проверить замером

Все команды read-only. `q` = вектор запроса; передавать **bind-параметром** `$1::FLOAT[1536]`.

```sql
-- 0. Разогрев/базовая точка (повторить 3 раза, брать медиану)
\timing on
SELECT count(*) FROM (SELECT row_key FROM search_corpus ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10);

-- 1. Оператор против функции — подтвердить 25-30 % на нашем железе
SELECT count(*) FROM (SELECT row_key FROM search_corpus ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10);
SELECT count(*) FROM (SELECT row_key FROM search_corpus ORDER BY array_cosine_distance(emb, $1::FLOAT[1536]) LIMIT 10);

-- 2. Литерал против bind-параметра (второй прогнать через extended protocol)
SELECT ($1::FLOAT[1536])[1];   -- чистая стоимость передачи вектора

-- 3. Разделение «чтение / арифметика» — сколько вообще можно выиграть
SELECT sum(emb[1]) FROM search_corpus;                 -- только чтение колонки
SELECT min(emb <=> $1::FLOAT[1536]) FROM search_corpus; -- чтение + расстояние

-- 4. Кривая префильтра: время от числа отобранных строк.
--    Подставить термины с df 50 / 500 / 5 000 / 30 000.
EXPLAIN SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('<термин>')
        ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10;
SELECT count(*) FROM search_idx WHERE doc @@ ts_phrase('<термин>');
SELECT count(*) FROM (SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('<термин>')
                      ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10);

-- 5. Точка безубыточности «индекс vs таблица» — где кривая из п.4 пересекает 313 мс.
--    Проверить, что для широких фильтров дешевле таблица:
SELECT count(*) FROM (SELECT row_key FROM search_corpus WHERE src_table = '<таблица>'
                      ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10);

-- 6. Скаляр/дата предикатом по INCLUDE-колонке (должен уйти в Column Filter внутри IRESEARCH_SCAN)
EXPLAIN SELECT row_key FROM search_idx
        WHERE doc @@ ts_phrase('<термин>') AND doc_date >= TIMESTAMP '2024-01-01' AND amount > 0
        ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10;

-- 7. Контроль: путь через индекс БЕЗ WHERE — убедиться, что он медленнее таблицы (у нас 541 vs 313 мс),
--    и никогда так не делать в коде.
SELECT count(*) FROM (SELECT row_key FROM search_idx ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10);
```

Отдельно, **на копии/тестовом инстансе, не на боевом** (требует CREATE INDEX, поэтому здесь не делалось):
```sql
CREATE INDEX search_idx2 ON search_corpus USING inverted(doc <dict>, refs <dict>, src_table)
  INCLUDE (src_table, row_key, amount, doc_date, emb included (row_group_size = 16384));
-- проверить в EXPLAIN, что стало «emb (i)» вместо «emb (l)», и замерить п.4 и п.7 заново.
```
Опкласса `ivf` в этом DDL нет — известного подвисания сборки ivf он не воспроизводит.

---

## Чего я не смог выяснить

1. **Почему `SEQ_SCAN` по таблице однопоточный — прямого подтверждения нет.** `pragma_storage_info('search_corpus')`
   возвращает 0 строк (SereneDB держит таблицы в своём columnstore, не в блоках DuckDB), число row-group
   посмотреть нечем. Гипотеза «97 965 < 122 880 → одна row-group → один поток» согласуется со всеми замерами,
   но это [вывод], а не факт. Подкода DuckDB в клоне нет: `third_party/duckdb` — пустая директория (submodule
   не выкачан), поэтому реализацию `SEQ_SCAN`, `<=>` и `array_cosine_*` процитировать нельзя.
2. **Сколько сегментов у `search_idx`** — от этого зависит параллельность режима `Stream`
   (`MaxThreads() = claimable_segments`). Способа увидеть число сегментов из SQL не нашёл.
3. **Что даст `INCLUDE (emb)`** — только рассуждение по коду (`DecideScanMode`, `MaxThreads`, `unit_rows`).
   Ни замера, ни теста в репозитории с вектором в `INCLUDE` **и** проверкой скорости нет; тест
   `inverted_index_array_include.test` проверяет только корректность round-trip на `FLOAT[3]`.
4. **Сжат ли `emb` на диске и каким кодеком** — `pragma_storage_info` пуст, а `duckdb_logs()` при
   `log_storage=stdout` недоступен. Косвенно: 2.5 ГБ/с на чтение 602 МБ.
5. **Ошибка `Attempted to access index -1 within vector of size 8`** воспроизводится устойчиво на
   `UNION ALL` c внутренним `ORDER BY <расстояние> LIMIT`, но до минимального репро (какой именно узел
   ломается, зависит ли от числа веток/типа выражения) я не доводил — это выходило за рамки задачи.
6. **Разброс замеров.** Машина всё время была под сторонней нагрузкой (load 11-13 при 6 ядрах).
   Соотношения между формами воспроизводились устойчиво, абсолютные числа — нет; перед тем как класть
   их в `docs/SERENEDB.md`, стоит перемерить на простаивающем сервере.
