# CHECK1_SCAN_2 — точный перебор по FLOAT[1536] в SereneDB 26.07.3: чем ускоряется штатно и где предел

Стенд: живой движок 127.0.0.1:7890 (`PostgreSQL 18.3 (SereneDB 26.07.3)`), сервер 192.168.56.42,
6 ядер (`nproc`=6), 62 ГБ ОЗУ, `threads=6`. Таблица `search_corpus` — 97 965 строк,
`emb FLOAT[1536]` заполнен у всех строк (`count(emb)=97965`). Индекс `search_idx` — `inverted`,
вектор в него НЕ входит (в плане `emb (l)` — доступ через row-store, а не через ANN-скан).
Ничего не создавалось и не менялось: только SELECT / EXPLAIN / EXPLAIN ANALYZE / справочные функции.

Все измерения — прогретые, wall-время клиента `psql \timing`, 5-9 повторов, приводится медиана.
Запрос-вектор — literal `FLOAT[1536]` (12,8 КБ текста SQL).

## Сводная таблица замеров [замер]

| # | форма запроса | строк под перебором | med, мс | min, мс |
|---|---|---|---|---|
| A | `FROM search_corpus ORDER BY emb <=> $q LIMIT 10` | 97 965 | **297.9** | 277.6 |
| B | `FROM search_corpus ORDER BY array_cosine_similarity(emb,$q) DESC LIMIT 10` | 97 965 | **440.6** | 410.4 |
| B2 | `FROM search_corpus ORDER BY cosine_similarity(emb,$q) DESC LIMIT 10` | 97 965 | **291.5** | 271.3 |
| F | `FROM search_corpus ORDER BY emb <#> $q LIMIT 10` | 97 965 | 293.8 | 281.2 |
| E | `FROM search_idx ORDER BY emb <=> $q LIMIT 10` (без фильтра) | 97 965 | **563.6** | 526.5 |
| C | `FROM search_idx WHERE doc @@ ts_phrase('банк') ORDER BY emb <=> $q LIMIT 10` | 1 433 | **35.1** | 28.4 |
| H | то же + `AND src_table LIKE 'catalog%'` | ~1 400 | 38.7 | 28.9 |
| G | `FROM search_corpus WHERE row_key IN (SELECT row_key FROM search_idx WHERE doc @@ …)` | 1 433 | 45.0 | 41.1 |
| D | `FROM search_corpus WHERE src_table='…' ORDER BY emb <=> $q LIMIT 10` | 2 779 | 35.7 | 30.2 |
| J | `FROM search_idx WHERE doc_date IS NOT NULL ORDER BY emb <=> $q` | 13 706 | 99.2 | 97.4 |
| I | `FROM search_corpus WHERE src_table LIKE 'catalog_%' ORDER BY emb <=> $q` | 40 846 | 141.4 | 134.4 |
| K | `SELECT sum(emb[1]) FROM search_corpus` — чистое чтение колонки | 97 965 | **223.4** | 197.2 |
| L | `SELECT count(*) FROM search_corpus` | — | 0.9 | 0.4 |

Главный вывод из K: **80 % времени полного перебора — это чтение колонки, а не арифметика.**
602 МБ (97 965 × 1536 × 4 Б) читаются за ~220 мс одним потоком (~2,7 ГБ/с); расчёт всех
98 тыс. расстояний добавляет 50-70 мс.

---

## 1. Форма запроса и план

### План одинаков для всех трёх форм [вывод EXPLAIN]

`EXPLAIN` на `ORDER BY emb <=> $q LIMIT 10`, `ORDER BY emb <#> $q LIMIT 10`,
`ORDER BY array_cosine_similarity(emb,$q) DESC LIMIT 10` даёт **побайтово одинаковую структуру**:

```
ORDER_BY (#1 ASC|DESC)
└── PROJECTION (row_key, <distance>)
    └── HASH_JOIN  Join Type: SEMI   Conditions: rowid = rowid
        ├── SEQ_SCAN  search_corpus  Projections: row_key, emb
        └── TOP_N  Top: 10, Order By: #0 ASC
            └── PROJECTION (<distance>)
                └── SEQ_SCAN  search_corpus  Projections: emb
```

Это штатная поздняя материализация DuckDB: правая ветка читает **только `emb`**, считает
расстояние, берёт top-10 rowid; левая ветка добирает остальные колонки по этим rowid.
`EXPLAIN ANALYZE` подтверждает, что второй скан не полный:

```
TABLE_SCAN search_corpus  Projections: row_key, emb
  optional: (rowid IN (111837, 114919, …, 125753)) AND optional: rowid IN PRF(rowid)
  10 rows
```

Итого: **один полный проход по колонке `emb`**, второй проход — точечная выборка 10 строк.
Расстояние считается один раз на строку, в `PROJECTION` над сканом.

### Тайминги по операторам [вывод EXPLAIN ANALYZE]

| ORDER BY | TABLE_SCAN(emb) | PROJECTION(расстояние) | Total |
|---|---|---|---|
| `emb <=> q` | 230 мс | 60 мс | 0.310 s |
| `emb <#> q` | 210 мс | 50 мс | 0.285 s |
| `emb <-> q` | 230 мс | 60 мс | 0.310 s |
| `cosine_distance(emb,q)` | 230 мс | 60 мс | 0.315 s |
| `cosine_similarity(emb,q) DESC` | 230 мс | 70 мс | 0.316 s |
| `inner_product(emb,q) DESC` | 220 мс | 60 мс | 0.297 s |
| `l2_distance` / `l2_sqr_distance` / `l1_distance` | 210-220 мс | 50 мс | 0.280-0.289 s |
| **`array_cosine_similarity(emb,q) DESC`** | 230 мс | **190 мс** | 0.436 s |
| **`array_cosine_distance(emb,q)`** | 220 мс | **190 мс** | 0.429 s |
| **`array_inner_product(emb,q) DESC`** | 220 мс | **170 мс** | 0.414 s |
| **`array_negative_inner_product`** | 220 мс | **180 мс** | 0.431 s |

### Почему `array_cosine_similarity` медленнее — точная причина [код]

Есть **два разных набора функций расстояния**, они не синонимы:

* **Свои, SereneDB** — `server/connector/functions/vector.cpp:447` `RegisterVectorFunctions`:
  `l1_distance`, `l2_distance`, `l2_sqr_distance`, `cosine_distance`, `cosine_similarity`,
  `inner_product`, `negative_inner_product`, `l1_norm`, `l2_norm`, `l1_normalize`, `l2_normalize`.
  Операторы — их же псевдонимы, зарегистрированы тем же `ScalarFunction`
  (`vector.cpp:436-441`, имена в `server/connector/functions/vector.h:57-71`):
  `<->` = `l2_distance`, `<+>` = `l1_distance`, `<=>` = `cosine_distance`,
  `<#>` = `negative_inner_product`. То есть **`emb <=> q` и `cosine_distance(emb,q)` — один и тот
  же код**, что и подтверждают замеры (297.9 vs 291.5 мс — в пределах шума).
  Ядро счёта — `libs/iresearch/include/iresearch/utils/vector.hpp:176` (`DotProductImpl`) и
  `:192` (`CosineDistanceImpl`), обе с `#pragma clang fp reassociate(on) contract(fast)` —
  цикл разрешено переассоциировать и векторизовать с FMA. Косинус считает `ll`, `lr`, `rr`
  за **один** проход по массиву (`vector.hpp:195-210`).
* **Чужие, из ядра DuckDB** — всё с префиксом `array_*` / `list_*`
  (`array_cosine_similarity`, `array_cosine_distance`, `array_distance`, `array_inner_product`,
  `array_negative_dot_product`, `list_cosine_distance`, …). В `serenedb-src/server/` их
  регистрации нет — это встроенные функции DuckDB, без `reassociate/contract` прагм.
  Отсюда 170-190 мс вместо 50-70 мс на тех же данных — **ровно 3x на шаге счёта**.

Проверено на инстансе: `duckdb_functions()` показывает обе группы;
`[1.0,2.0]::FLOAT[2] <=> [1.0,3.0]::FLOAT[2]` = 0.010050535, `<#>` = -7, `<->` = 1 — значения
совпадают с `cosine_distance` / `negative_inner_product` / `l2_distance`.

**Наш код использует медленную группу**: `ubuntu/serenedb/serene_ask.py:921,958,970`,
`ubuntu/serenedb/serene_report.py:220`, `ubuntu/serenedb/measure_resolver.py:11` — везде
`array_cosine_similarity`. Замер: 440.6 → 291.5 мс (**-34 % wall, -1.5x**) простой заменой
`array_cosine_similarity(emb, q) DESC` → `cosine_similarity(emb, q) DESC` или
`emb <=> q` (ASC). Замена побитово эквивалентна по порядку сортировки
(`cosine_distance = 1 - cosine_similarity`, `vector.cpp:119-121`).

### Прочие формы записи

* `l2_sqr_distance` (без `sqrt`) и `l1_distance` — самые быстрые (50 мс на счёт), но
  косинус на ненормированных данных они не заменяют.
* `l2_normalize(emb)` на приёме + `<#>` вместо `<=>`: экономия в пределах шума
  (293.8 vs 297.9 мс). Причина видна в коде: `CosineDistanceImpl` уже считает обе нормы
  в том же цикле, отдельного прохода за нормой нет.
* **Диапазонная форма `WHERE emb <=> q < 0.5` — медленнее, не использовать** [замер]:
  `SELECT count(*) … WHERE emb <=> q < 0.5` = 0.579 s, `… LIMIT 10` = 0.559 s против 0.31 s
  у `ORDER BY … LIMIT`. В плане это фильтр внутри `TABLE_SCAN` (570 мс в скане), поздней
  материализации нет. На таблице без ANN-индекса range-search штатного выигрыша не даёт.
  (В демке `examples/demo4/demo.sql:66` эта форма даёт `IRESEARCH_ANN_RANGE_SCAN`, но только
  при HNSW/IVF в индексе — у нас этого нет.)
* Bind-параметр вместо литерала (`PREPARE p AS … <=> $1::FLOAT[1536]` + `EXECUTE`) — 315 мс
  на запрос против 298 мс у литерала: **выигрыша нет**, разбор 12,8 КБ литерала не является
  узким местом. (В `examples/demo4/demo.sql:53` про `$1::FLOAT[1536]` сказано, что каст
  сворачивается на этапе плана — это про выбор ANN-скана, не про скорость разбора.)

---

## 2. Параллельность

**Полный скан по вектору идёт в ОДИН поток.** [замер]

Метод: снимаем `utime+stime` процесса `serened` (pid 688749) из `/proc/<pid>/stat` до и после
серии запросов, делим CPU на wall. Отношение ≈1 = один поток.

| нагрузка | wall | CPU | CPU/wall |
|---|---|---|---|
| 20× `search_corpus ORDER BY emb <=> q LIMIT 10` | 7 040 мс | 7 880 мс | **1.12** |
| 5× то же (контроль) | 1 491 мс | 1 340 мс | **0.89** |
| 10× `UNION ALL` двух РАЗНЫХ таблиц (`search_corpus` + `search_corpus_bak`) | 10 836 мс | 18 990 мс | **1.75** |
| 5× `UNION ALL` из 6 диапазонов `rowid` одной таблицы | 1 868 мс | 2 520 мс | 1.34 |

То есть планировщик потоков работает (два скана в `UNION ALL` реально идут параллельно,
1.75), но **скан одной таблицы на 98 тыс. строк параллелизма не получает**.

Ручное разбиение на 6 веток `WHERE rowid BETWEEN …` даёт CPU/wall 1.34, но **wall не
улучшает** (276-416 мс против 271-287 мс базовой формы) — упирается в пропускную способность
чтения колонки, а не в счёт. Штатного механизма нет — **и своего писать не стоит, замер
показал ноль**.

Настройки, которые это трогают [вывод `duckdb_settings()`]:

| настройка | значение | что делает |
|---|---|---|
| `threads` | 6 | общее число рабочих потоков |
| `worker_threads` | 6 | синоним |
| `external_threads` | 0 | принудительно 0, см. `server/query/server_engine.cpp:240-243` |
| `async_threads` | 12 | потоки под I/O-задачи |
| `pin_threads` | auto | пиннинг к ядрам, включается при >64 ядрах |

`threads` выставляется на старте из числа логических ядер с учётом cgroup
(`server/query/server_engine.cpp:230-237`), флаг `--cpu_threads`; `SET threads = N` на уровне
SQL перебивает (`server_engine.cpp:220`). **Настройки «параллелить скан маленькой таблицы» нет.**

Кода, отвечающего за параллельный скан ИМЕННО векторной колонки, в `server/` нет: скан обычной
таблицы — `SEQ_SCAN`/`TABLE_SCAN` из ядра DuckDB (строка `Sequential Scan` в `server/` не
встречается вообще). Параллельный top-k есть только у **индексного** скана:
`server/connector/duckdb_search_full_scan.hpp:67` («ORDER BY score LIMIT k: parallel top-k
collectors»), `duckdb_search_full_scan.cpp:1237` `state->collectors.resize(state->MaxThreads())`
— но это путь `text_scorer`/`vector_scorer`, а `vector_scorer` включается только когда колонка
проиндексирована ANN-опклассом (`duckdb_search_full_scan.cpp:1756-1762`, ветка
`col_id == catalog::Column::kInvertedIndexScoreId`). У нас `emb` — не индексная колонка,
поэтому эта ветка не работает.

Гипотеза «одна row-group = один morsel, поэтому один поток» правдоподобна (98 тыс. < 122 880),
но **не проверена**: `pragma_storage_info('search_corpus')` возвращает 0 строк, сабмодуль
`third_party/duckdb` в клоне не выкачан. Помечаю как невыясненное (см. последний раздел).

---

## 3. Префильтр — ДА, работает, и это главный рычаг

### 3.1 Скалярный / датовый префильтр по обычной колонке таблицы [вывод + замер]

`EXPLAIN ANALYZE SELECT row_key FROM search_corpus WHERE amount > 0 ORDER BY emb <=> $q LIMIT 10`:

```
TOP_N ← PROJECTION ← TABLE_SCAN search_corpus
   Filters: optional: (amount > 0)
   Projections: emb
```
`Total Time: 0.0343s`, `PROJECTION 0µs`, `TABLE_SCAN 10.0ms`.

**Множество сужается ДО вычисления расстояний**: фильтр вложен в сам скан, `emb` дочитывается
только для выживших строк. Подтверждено числами `rows` в плане и линейной зависимостью времени
от числа выживших строк:

| условие | выжило строк | med, мс | ускорение к 298 мс |
|---|---|---|---|
| `amount > 0` | 1 752 | 34 (Total Time) | 8.7x |
| `src_table = 'catalog_классификаторбанков'` | 2 779 | 35.7 | 8.3x |
| `doc_date IS NOT NULL` | 13 706 | 66 (Total Time) | 4.5x |
| `src_table LIKE 'catalog_%'` | 40 846 | 141.4 | 2.1x |
| без условия | 97 965 | 297.9 | 1.0x |

Регрессия по этим точкам: **≈20 мс постоянных + 2,7 мкс на строку**.

Исключение — `WHERE doc LIKE '%банк%'` (4 280 строк): 0.241 s. Экономия на `emb` есть, но
её съедает полный проход по строковой колонке `doc` (220 мс в скане). Подстрочный `LIKE`
как префильтр бесполезен — для этого есть индекс (ниже).

### 3.2 Текстовый префильтр через инвертированный индекс — 8.5x [вывод + замер]

**Это ответ на главный вопрос.** Форма — обращение **от имени индекса**:

```sql
SELECT row_key
FROM search_idx
WHERE doc @@ ts_phrase('банк')
ORDER BY emb <=> $q::FLOAT[1536]
LIMIT 10;
```

`EXPLAIN ANALYZE` целиком (сокращён только сам вектор):

```
Summary  Total Time: 0.0286s
TOP_N        Top: 10, Order By: #1 ASC, 10 rows
PROJECTION   row_key, emb <=> [...]      1,433 rows
TABLE_SCAN   Index: search_idx
             Lookup: table
             Index Filter:
               ╭─ Term ──────────────────────────────────╮
               │ Field: doc(string)                      │
               │ Value: \xd0\xb1\xd0\xb0\xd0\xbd\xd0\xba │
               ╰─────────────────────────────────────────╯
             Projections: row_key (i), emb (l)
             1,433 rows
```

Читается: iresearch-фильтр по посting-листу отдал **1 433 строки из 97 965**, и только для них
материализован `emb` (`(l)` = row-store lookup, `(i)` = типизированный columnstore —
расшифровка в `tests/sqllogic/sdb/pg/index/inverted_index_indexed_vs_included.test:1-18`).
`PROJECTION` считает 1 433 расстояния, `TOP_N` берёт 10. **28-35 мс против 298 мс — 8.5x.**

Другие проверенные комбинации на индексе:

| запрос | строк | med, мс |
|---|---|---|
| `WHERE src_table = '…'` (keyword-поле) | 2 779 | 44.8 (Total) |
| `WHERE doc @@ (ts_phrase('банк') \|\| ts_phrase('счёт'))` | 3 689 | 51.3 (Total) |
| `WHERE doc @@ ts_phrase('банк') AND amount > 0` | 0 | 22.7 (Total) |
| `WHERE doc @@ ts_phrase('банк') AND src_table LIKE 'catalog%'` | ~1 400 | 38.7 |

Скалярное условие видно в плане отдельной строкой `Filter: amount > 0` — оно тоже применяется
до расчёта расстояний.

### 3.3 Смешанная форма (если нужны колонки, которых нет в индексе)

```sql
SELECT row_key FROM search_corpus
WHERE row_key IN (SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('банк'))
ORDER BY emb <=> $q LIMIT 10;
```
45.0 мс. План: `TOP_N ← PROJECTION ← HASH_JOIN ← (TABLE_SCAN search_corpus + TABLE_SCAN search_idx)`,
с проталкиванием в скан таблицы `optional: row_key IN BF(#0)` (bloom-фильтр) и min/max по
`row_key`. То есть сужение тоже происходит до расчёта расстояний. Чуть медленнее прямой формы
из §3.2, но даёт доступ ко всем колонкам таблицы.

### 3.4 Обратное правило: БЕЗ фильтра ходить в индекс нельзя

`SELECT row_key FROM search_idx ORDER BY emb <=> $q LIMIT 10` = **563.6 мс**, вдвое хуже
таблицы (297.9 мс). Причина в плане: `TABLE_SCAN 500 мс`, `emb (l)` — все 97 965 векторов
достаются точечными lookup'ами из row-store вместо колоночного чтения.

**Правило, подтверждённое замером:**
есть текстовое/индексное условие → `FROM search_idx`;
есть только скалярное условие → `FROM search_corpus WHERE …`;
условий нет вовсе → `FROM search_corpus` (и только так).

### 3.5 Что по этому поводу есть в репозитории [код]

* `examples/demo4/demo.sql:71-80` — Q3 «Hybrid»: булев BM25-фильтр `&& || !!` в `WHERE`,
  `ORDER BY d.embedding <=> $1::FLOAT[1536] LIMIT 5`, всё от имени индекса `FROM dbpedia_idx d`.
  Ровно наша форма §3.2. Но там вектор ВНУТРИ индекса (`embedding hnsw(...)`,
  `examples/demo4/demo.sql:39-42`) — у нас HNSW в сборке нет, IVF заблокирован, поэтому
  у нас та же форма даёт честный перебор по отфильтрованному множеству, а не ANN.
* `examples/demo4/demo.sql:83-92` — Q4: proximity `##`, `ts_levenshtein`, `ts_regexp` в фильтре
  + `ORDER BY … <=>` — тот же шаблон.
* `tests/sqllogic/sdb/pg/index/vector_search.test_slow:35` — движок сам использует
  «фильтр + перебор по таблице» как ЭТАЛОН для проверки recall у ANN:
  `INSERT INTO correct_filtered SELECT id FROM vecs WHERE id > 25000 ORDER BY emb <-> [...] LIMIT 512;`
* `tests/sqllogic/sdb/pg/index/inverted_index_filter_pushdown.test`,
  `inverted_index_filter_topk_fallback.test`, `inverted_index_ivf_filter.test` — спецификация
  проталкивания фильтров в индексный скан.

---

## 4. Что ещё штатно ускоряет перебор

| механизм | что делает по коду | применимо к перебору БЕЗ ivf? |
|---|---|---|
| **своя группа функций расстояния** (`<=>`, `<#>`, `<->`, `cosine_distance`, …) вместо `array_*` | `vector.cpp:447`, ядро `vector.hpp:176,192` с `reassociate/contract` | **ДА, 1.5x**, замерено (440.6→291.5 мс) |
| **префильтр в индексе / в скане** | §3 | **ДА, до 8.5x**, замерено |
| **поздняя материализация top-k** | план: `TOP_N` по `emb` + semi-join по rowid, `rowid IN (…)` | **ДА, уже работает по умолчанию**, ничего включать не надо |
| `optimize_top_k` (опция индекса) | `server/catalog/scorer_options.cpp:203-262`: принимает ТОЛЬКО скорер-функцию (`bm25`, `tfidf`, `lm_jm`, `lm_dirichlet`, `indri_dirichlet`, `dfi`, `raw_boost`, `raw_tf`, `raw_dl`) — это WAND по текстовому ранжированию | **НЕТ**, вектора не касается |
| `sdb_disable_top_k_optimization` (=off) | `server/connector/duckdb_search_full_scan.cpp:1719-1722`, `1746-1762`: гейт для затягивания `ORDER BY <scorer> LIMIT k` внутрь индексного скана; ветка вектора требует `col_id == kInvertedIndexScoreId`, т.е. ANN-опкласса на колонке | **НЕТ** при нашем `emb` вне индекса. Трогать не нужно (default `off` = оптимизация включена) |
| `sdb_nprobe` (8), `sdb_rerank_factor` (4), `sdb_ivf_posting_size` (1024), `sdb_ivf_sample_factor` (0) | ручки IVF | **НЕТ**, IVF у нас заблокирован |
| `sdb_scored_terms_limit` (1024) | число термов для IDF-скоринга | **НЕТ**, текст |
| `row_group_size` / `norm_row_group_size` (122880) | по описанию в `duckdb_settings()` — только для INCLUDE-колонок и norm-колонок **создаваемых инвертированных индексов**; «Reads from existing indexes are unaffected» | **НЕТ** для скана таблицы |
| сжатие колонки | `… INCLUDE (col included (compression = 'zstd'\|'alp'\|'bitpacking'\|'rle'\|'uncompressed'\|'fsst'))` — `tests/sqllogic/sdb/pg/index/inverted_index_compression_option.test:35,68,98,125`; для IVF-колонок опции `compression`/`row_group_size` **сняты** (`там же:5,233-241`) | только для INCLUDE-колонок индекса; на таблице ручки нет |
| **FLOAT vs DOUBLE** | `vector.cpp:411-425`: обе перегрузки есть, `FLOAT[]`→FLOAT, `DOUBLE[]`→DOUBLE | **ДА, косвенно**: DOUBLE удвоит объём чтения (602 МБ → 1,2 ГБ), а чтение — 80 % времени. У нас уже `FLOAT[1536]` — правильно, менять нечего |
| предвычисленные нормы (`l2_normalize` при вставке + `<#>`) | `vector.cpp:145-156` (`l2_normalize`), косинус и так считает `ll,lr,rr` за один проход (`vector.hpp:195-210`) | **выигрыша нет**: 293.8 vs 297.9 мс |
| хранение вектора отдельной узкой таблицей | — | **бессмысленно**: скан уже проецирует только `emb` (`Projections: emb` в плане), лишних колонок не читается |
| `emb` в `INCLUDE` индекса | `(i)` = чтение из типизированного columnstore вместо `(l)` = row-store lookup — `inverted_index_indexed_vs_included.test:1-18`; массив в INCLUDE синтаксически допускается (`inverted_index_matrix_vector_ivf.test:12` `INCLUDE (emb)`, обработка `LogicalTypeId::ARRAY` в `server/catalog/index.cpp:182-187`) | **гипотеза, НЕ проверена** — потребовало бы `CREATE INDEX` (запрещено). Могло бы убрать разрыв 563.6 vs 297.9 мс на форме «FROM search_idx без фильтра» |
| ручное разбиение скана на N `UNION ALL` | своя конструкция, штатного механизма нет | **НЕТ выигрыша**, замерено (§2) |

Отдельно: **`SELECT count(*)` = 0.9 мс** — счёт строк идёт по метаданным, не сканом; любой
агрегат, не трогающий `emb`, стоит около нуля.

---

## 5. Замеры полного перебора в самом движке — практически НЕТ

Искал в `tests/sqllogic/` (19 наборов), `examples/demo0..demo6`, `scripts/perf/` (49 скриптов).

**Что нашёл — дословно:**

* `tests/sqllogic/sdb/pg/index/vector_search.test_slow` — **50 000 строк, размерность 8**.
  Перебор по таблице используется как ЭТАЛОН точности для ANN, времени не меряет:
  ```
  CREATE TABLE vecs (id INT, emb FLOAT[8]);
  INSERT INTO vecs SELECT s AS id, [ sin(s*0.001)::FLOAT, cos(s*0.001)::FLOAT, … ]::FLOAT[8]
    FROM generate_series(1, 50000) AS s;
  INSERT INTO correct SELECT id FROM vecs ORDER BY emb <-> [0.0,1.0,0.0,1.0,0.0,1.0,0.0,1.0]::FLOAT[8] LIMIT 512;
  INSERT INTO correct_filtered SELECT id FROM vecs WHERE id > 25000
    ORDER BY emb <-> [0.0,1.0,0.0,1.0,0.0,1.0,0.0,1.0]::FLOAT[8] LIMIT 512;
  INSERT INTO correct_cos2 SELECT id FROM vecs ORDER BY cosine_similarity(emb, [...]::FLOAT[8]) DESC LIMIT 512;
  ```
  Обратите внимание: в эталоне движка используется `cosine_similarity`, **не** `array_cosine_similarity`.
* `examples/demo4/README.md:1` — «Hybrid vector + full-text search over **100K DBpedia abstracts**»,
  датасет `Qdrant/dbpedia-entities-openai3-text-embedding-3-small-1536-100K`, **1536 измерений,
  100 тыс. строк** — ровно наш порядок. Но все четыре запроса демки идут через **HNSW**
  (`CREATE INDEX dbpedia_idx ON dbpedia USING inverted(text dbpedia_en, embedding hnsw (metric='cosine', m=32, ef_construction=64))`),
  цифр времени в README нет — только `\timing on` в скрипте.
* `examples/demo5` — **FLOAT[3072]** (`ai_embed(..., 'gemini')::FLOAT[3072]`), `ORDER BY … <=> ai_embed(...)`;
  объём не указан, замеров нет.
* `scripts/perf/sweep_hnsw.sh`, `sweep_hnsw_cross.sh`, `hnsw_index_size.sh` — свипы по
  тюнингу HNSW (`kChunkSizeFloats`, `kChunkCacheSlots`, `kRgCacheSlots`), гоняют
  `vector_search.test_slow` (50k × dim 8) и печатают «elapsed ms per config». Это замеры
  **ANN**, не перебора.
* `scripts/perf/gen_filtered_topk_report.sh` — единственный полноценный A/B в репозитории,
  но по **тексту**: `sdb_disable_top_k_optimization=false` (WAND+фильтр) против `true`
  (streaming+TopN), `ORDER BY BM25(dt.tableoid) DESC LIMIT k`, 9 прогретых прогонов,
  min/median. К вектору не относится. Методику стоит скопировать.
* Прочие `scripts/perf/*` (`run_hits_perf.sh`, `bench_pk_lookup.sh`, `profile_query.sh`,
  `cs_perf.sh`, …) — про хранилище, wire-протокол, PK-lookup, ClickBench-hits. Вектора нет.

**Замеров полного перебора по векторам большой размерности на больших объёмах в репозитории
нет.** Наши цифры выше — первые известные для этой сборки.

---

## Что проверить замером (без создания индексов)

Всё ниже — только SELECT/EXPLAIN. `$q` — литерал `[…]::FLOAT[1536]` или bind-параметр.

```sql
-- 1. Подтвердить выигрыш от смены группы функций (ожидание: ~440 → ~292 мс).
\timing on
SELECT row_key FROM search_corpus ORDER BY array_cosine_similarity(emb, $q) DESC LIMIT 10;
SELECT row_key FROM search_corpus ORDER BY cosine_similarity(emb, $q) DESC LIMIT 10;
SELECT row_key FROM search_corpus ORDER BY emb <=> $q LIMIT 10;

-- 2. Убедиться, что порядок top-10 у трёх форм идентичен (правильность замены).
WITH a AS (SELECT row_key, row_number() OVER () i FROM
             (SELECT row_key FROM search_corpus ORDER BY array_cosine_similarity(emb,$q) DESC LIMIT 50)),
     b AS (SELECT row_key, row_number() OVER () i FROM
             (SELECT row_key FROM search_corpus ORDER BY emb <=> $q LIMIT 50))
SELECT count(*) FILTER (WHERE a.i IS DISTINCT FROM b.i) AS расхождений
FROM a FULL JOIN b USING (row_key);

-- 3. Текстовый префильтр от имени индекса (ожидание: ~30-40 мс, 1433 строки в плане).
EXPLAIN ANALYZE SELECT row_key FROM search_idx
  WHERE doc @@ ts_phrase('банк') ORDER BY emb <=> $q LIMIT 10;

-- 4. Проверить, что тот же ответ приходит и полным перебором (эталон по recall).
WITH exact AS (SELECT row_key FROM search_corpus
                 WHERE row_key IN (SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('банк'))
                 ORDER BY emb <=> $q LIMIT 10),
     idx   AS (SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('банк')
                 ORDER BY emb <=> $q LIMIT 10)
SELECT count(*) AS совпало FROM exact JOIN idx USING (row_key);

-- 5. Пол производительности: сколько стоит просто прочитать колонку (ожидание ~220 мс).
SELECT sum(emb[1]) FROM search_corpus;

-- 6. Однопоточность: до и после серии запросов снять
--    awk '{print $14+$15}' /proc/$(pgrep -x serened)/stat  (тики по 10 мс),
--    поделить CPU на wall. Ожидание ~1.0.

-- 7. Зависимость от числа выживших строк — построить свою кривую на своих фильтрах:
EXPLAIN ANALYZE SELECT row_key FROM search_corpus WHERE <условие> ORDER BY emb <=> $q LIMIT 10;
--    в плане смотреть строку "N rows" у PROJECTION — это и есть сколько строк реально перебрано.
```

---

## Чего я не смог выяснить

1. **Почему именно скан одной таблицы однопоточный.** Факт измерен (CPU/wall = 0.89-1.12),
   но причина не доказана. Гипотеза «97 965 < `row_group_size` 122 880 → одна row-group →
   один morsel» проверить не удалось: `pragma_storage_info('search_corpus')` возвращает 0 строк
   (SereneDB-каталог не отдаёт storage-info), сабмодуль `third_party/duckdb` в клоне не выкачан,
   в `server/` кода скана обычной таблицы нет. Проверяется таблицей на >122 880 строк — а это
   запись, которая мне запрещена.
2. **Даст ли `emb` в `INCLUDE` индекса колоночное чтение `(i)` вместо lookup `(l)`** и снимет
   ли это разрыв 563.6 vs 297.9 мс. Синтаксис допускает (`INCLUDE (emb)` встречается в
   `inverted_index_matrix_vector_ivf.test:12`, но там рядом стоит `emb ivf (...)`), обработка
   `ARRAY` в `catalog/index.cpp:182-187` есть. Отдельного теста «FLOAT[N] в INCLUDE БЕЗ
   ivf-опкласса» в `tests/sqllogic/` я не нашёл. Требует `CREATE INDEX` — не проверял.
3. **Есть ли способ ускорить чтение колонки `emb` (220 мс = 80 % времени)** штатно, без
   пересоздания хранилища: ручек сжатия/row-group для колонок обычной таблицы в
   `duckdb_settings()` не видно, `pragma_storage_info` недоступен, какой кодек применён к
   `FLOAT[1536]` — узнать не смог.
4. **Влияние `SET threads = N` на эту конкретную форму** — не мерил сознательно:
   в DuckDB `threads` глобальная, а инстанс общий; менять его на живом сервере не стал.
5. **Квантование вне ANN-индекса** (int8/binary для ускорения перебора): функций
   `*quantize*` в `duckdb_functions()` нет (есть только статистические `quantile*` и
   `*normalize*`), в `vector.cpp` тоже нет. Похоже, квантование живёт исключительно внутри
   IVF (`sdb_ivf_*`, `quant='none'|'sq8'|'sq4'|'pq'|'rabitq'` по именам тестов). Своими силами
   это делать — своя конструкция, штатного механизма нет.
