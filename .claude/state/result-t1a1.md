# Аудит T1-A1: нативные средства SereneDB для быстрой сборки больших текстов + версии

**Дата:** 2026-09-02  
**Сборка проекта:** SereneDB **26.07.3**  
**Источники:** MCP `serenedb-docs` (индекс ~3343 разделов, hybrid), плюс read-only GitHub Releases / блог (там, где страница Releases в доках — «Loading GitHub releases…»).  
**Ограничения аудита:** код репо и серверы не трогались; живой `PRAGMA version` / замер на инстансе не выполнялись.  
**Важно:** официальные docs описывают *текущую* линейку движка. Пометка «уже в 26.07.3» ниже = «в доках нет версии-гейта + в changelog после `v26.07.3` фича не объявлена как новая». Это не замена пробы на живом 26.07.3.

Метки фактов:
- **подтверждено доками (линейка доков / вероятно 26.07.3)** — в docs есть явное описание; в post-26.07.3 release notes не фигурирует как новая.
- **есть только в версии X** — явно в release notes / State of Serene после 26.07.3.
- **в доках НЕ найдено — отрицательный вывод**
- **ГИПОТЕЗА** — вывод аудитора, не цитата docs.

---

## 1. Параллелизм и скорость тяжёлых запросов

### 1.1. Threads / GLOBAL threads

| Факт | Метка | Источник |
|---|---|---|
| `SET threads = 4;` — число потоков параллельного исполнения запроса | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/pragmas#threads |
| `SET GLOBAL threads = 4;` — GLOBAL переживает сессию; сброс `RESET GLOBAL threads` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/set#set-a-global-variable |
| `SET threads TO 1;` / `RESET threads;` / `current_setting('threads')` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/overview , https://docs.serenedb.com/sql/statements/set |
| «Too many threads» (напр. из‑за HyperThreading) может замедлять — тогда вручную `SET threads = X` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#the-effect-of-row-groups-on-parallelism |

### 1.2. Как устроен параллелизм (row groups)

Цитата (docs):

> SereneDB parallelizes the workload based on row groups… The default row group size … is **122,880** rows. Parallelism starts at the level of row groups, therefore, **for a query to run on k threads, it needs to scan at least k × 122,880 rows**.

| Факт | Метка | Источник |
|---|---|---|
| Параллелизм на уровне row group; порог ≈ 122 880 строк на поток | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#the-effect-of-row-groups-on-parallelism |
| `ATTACH … (ROW_GROUP_SIZE N)` задаёт размер row group для *нового* файла | подтверждено доками (вероятно 26.07.3) | там же; также https://docs.serenedb.com/sql/statements/attach/duckdb |
| Движок пытается параллелить **внутри одного** запроса; не всё параллелится | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#best-practices-for-using-connections |
| Несколько connections могут параллелить *разные* операции, полезно если bottleneck не CPU | подтверждено доками (вероятно 26.07.3) | там же |
| Движок «optimized for running **larger, less frequent** queries», не для массы мелких concurrent | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#prepared-statements |

**ГИПОТЕЗА (применительно к `p_doc` на ~75k строк):** 75 000 < 122 880 → **одна** row group на скане источника → штатный параллелизм скана **почти не включается**; картина «~1 ядро на 5 часов» согласуется с docs о пороге row groups. Чтобы получить k потоков на одном скане, нужно ≥ k×122 880 строк *или* меньший `ROW_GROUP_SIZE` при создании файла (для *нового* ATTACH).

### 1.3. JOIN: hash vs nested loop, хинты порядка

| Факт | Метка | Источник |
|---|---|---|
| Profiling: «**Avoid nested loop joins in favor of hash joins**» | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#profiling |
| Плохой join order с взрывом cardinality «should be avoided at all costs» | подтверждено доками (вероятно 26.07.3) | там же |
| Принуждение порядка JOIN: разбить на цепочку `CREATE OR REPLACE TEMPORARY TABLE … AS SELECT … JOIN …` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/join_operations#how-to-force-a-join-order |
| Или `SET disabled_optimizers = 'join_order,build_side_probe_side'` → left-deep по порядку JOIN; потом `SET disabled_optimizers = ''` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/join_operations#turn-off-the-join-order-optimizer |
| Синтаксис **ANTI JOIN** / **SEMI JOIN** есть (альтернатива `NOT EXISTS` на уровне SQL) | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/query_syntax/from_and_join#semi-and-anti-joins |
| В планах: probe = left, build = right у hash join | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/profiling#notation-in-query-plans |

**в доках НЕ найдено — отрицательный вывод:** именованных хинтов вида `/*+ HASH_JOIN */` / `FORCE NESTLOOP` — нет; управление — через rewrite / `disabled_optimizers` / temp tables / `EXPLAIN ANALYZE`.

**ГИПОТЕЗА:** тяжёлые `NOT EXISTS` на 1.66M×1.44M — кандидаты на hash anti-join; если план уходит в nested loop, пик памяти и время взрываются. Штатная диагностика: `EXPLAIN` / `EXPLAIN ANALYZE` (docs).

### 1.4. CTAS / INSERT SELECT / «streaming»

| Факт | Метка | Источник |
|---|---|---|
| `CREATE TABLE … AS SELECT` (CTAS) и `CREATE OR REPLACE TABLE … AS` поддерживаются | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/create_table#create-table--as-select-ctas |
| Temp tables: при заданном `temp_directory` spill при нехватке памяти | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/create_table#temporary-tables |

**в доках НЕ найдено — отрицательный вывод:** отдельной фичи «streaming CTAS», pipeline-CTAS или построчного flush при `CREATE TABLE AS` — нет (поиск по docs не дал раздела).

### 1.5. string_agg / list / regexp / list_contains

| Факт | Метка | Источник |
|---|---|---|
| `string_agg(arg)` / `string_agg(arg, sep)` — агрегаты; «affected by ordering» | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/functions/aggregates#string_aggarg |
| `list()` / `array_agg` — то же семейство | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/functions/aggregates#listarg |
| **Критично:** `list()` и `string_agg()` **do not support offloading to disk** | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#limitations |
| Holistic aggregates (со sorting) могут OOM на больших данных — «cannot yet offload some complex intermediate aggregate states» | подтверждено доками (вероятно 26.07.3) | там же |
| `string_agg` / `list` / `mode` / `quantile` / `approx*` используют память **вне** buffer manager → фактический RSS может превысить `memory_limit` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/pragmas#memory-limit |
| `list_contains` / `regexp_replace` / `list_string_agg` — обычные функции; **отдельных perf-советов «как ускорить сборку текста» в docs нет** | подтверждено доками (API есть) / отрицательный вывод по perf | https://docs.serenedb.com/sql/functions/list#list_containslist-element , https://docs.serenedb.com/sql/functions/regular_expressions#regexp_replacestring-pattern-replacement-options |

**ГИПОТЕЗА:** монолитный `p_doc` с `string_agg`/`list` на нечанкуемой сущности — ровно класс workload, который docs называют неспособным spill; многоядерность не спасает от удержания всего агрегатного состояния в RAM, а на малом числе row groups ещё и мало параллелизма.

### 1.6. Что ускоряет однотабличную сборку текстов (по docs)

Штатно из cookbook:

1. Достаточно строк / меньший row group → реальный multi-thread scan.  
2. `EXPLAIN ANALYZE` → hash join, не nested loop; фильтр pushdown.  
3. Избегать `string_agg`/`list` на огромных группах *или* дробить группы (чанки) так, чтобы state помещался и spill/threads имели смысл.  
4. Persistent + compression быстрее uncompressed in-memory (до ~8× на TPC-H Q1 SF30 в их замере).  
5. `SET preserve_insertion_order = false` — снизить память на крупных import/export без `ORDER BY`.  
6. Не вешать ART/PK до bulk load (индекс замедляет ingest).

Источники: https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads , https://docs.serenedb.com/cookbook/performance/indexing#indexes-and-opening-databases , https://docs.serenedb.com/cookbook/performance/environment

---

## 2. Управление памятью запроса / движка

### 2.1. Лимиты

| Параметр | Значение / смысл | Метка | Источник |
|---|---|---|---|
| `memory_limit` | по умолчанию **80% RAM**; только **buffer manager** | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/limits#limit-values , https://docs.serenedb.com/configuration/pragmas#memory-limit |
| `SET memory_limit = '10GB'` / `RESET memory_limit` | GLOBAL/SESSION через SET | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/overview |
| `max_temp_directory_size` | default **unlimited** | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/limits#limit-values |
| Memory allocation for a vector | лимит **128 GB** (hard table) | подтверждено доками (вероятно 26.07.3) | там же |
| Per-query / per-session soft cap отдельно от `memory_limit` | **в доках НЕ найдено — отрицательный вывод** | — | поиск `memory limit session query` не дал отдельного knob |

Цитата (Attention в pragmas):

> The specified memory limit is only applied to the buffer manager. … **aggregate functions with complex state (e.g., `list`, `mode`, `quantile`, `string_agg`, and `approx` functions) use memory outside of the buffer manager. Therefore, the actual memory consumption can be higher than the specified memory limit.**

**Вывод для OOM на anti-join / merge:** `SET memory_limit` **не гарантирует** защиту от kernel OOM, если доминируют join intermediates + `string_agg`/`list` вне buffer manager. Docs прямо предупреждают.

### 2.2. Spill-to-disk / temp

| Факт | Метка | Источник |
|---|---|---|
| Out-of-core для **GROUP BY, JOIN, ORDER BY, WINDOW** | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#blocking-operators |
| Default temp: `⟨database_file_name⟩.tmp` рядом с файлом БД; override `SET temp_directory = '…'` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/pragmas#temp-directory-for-spilling-data-to-disk |
| Несколько blocking operators в одном запросе → всё равно возможен OOM | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#limitations |
| Интроспекция spill: `duckdb_temporary_files()`; buffer manager: `duckdb_memory()` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/functions/duckdb_table_functions |

### 2.3. jemalloc / allocator

| Факт | Метка | Источник |
|---|---|---|
| На many-core + jemalloc: «consider enabling the allocator's background threads» | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/environment#memory-allocator |
| Опция `allocator_background_threads` BOOLEAN, **default false** | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/configuration/overview#global-configuration-options |
| Также: `allocator_flush_threshold` (default 128 MiB), `allocator_bulk_deallocation_flush_threshold` (512 MiB) | подтверждено доками (вероятно 26.07.3) | там же |

**в доках НЕ найдено — отрицательный вывод:** тюнинг jemalloc через env (`MALLOC_CONF` и т.п.) в официальных docs SereneDB не описан — только SQL-опции allocator_*.

### 2.4. Память на поток / hardware

| Факт | Метка | Источник |
|---|---|---|
| Цель: **1–4 GB RAM на thread**; aggregation-heavy 1–2, join-heavy 3–4 | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/environment#memory-for-ideal-performance |
| Минимум **125 MB / thread**; при нехватке — снизить `threads` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/environment#minimum-required-memory |
| Index buffers «not yet buffer-managed» — индексы могут удерживать память несмотря на eviction | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/indexing#indexes-and-memory |
| `vm.max_map_count` ≥ 262144; `RLIMIT_NOFILE` / LimitNOFILE=131072 для .deb | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/performance/environment#file-descriptors-and-memory-maps |

### 2.5. Чем штатно ограничить пик, чтобы не ловить kernel OOM

По docs (без своих скриптов поверх данных):

1. **`SET memory_limit = '…'`** ниже физической RAM с запасом — заставит buffer-managed операторы spill раньше; **но не покрывает `string_agg`/`list`**.  
2. **`SET threads = N`** вниз — меньше параллельных hash-build’ов → меньше пик (явная рекомендация при memory-constrained).  
3. **`SET temp_directory`** на быстрый локальный SSD/NVMe; при необходимости `max_temp_directory_size`.  
4. **Разнести blocking operators** по шагам (temp tables) — docs прямо: несколько blockers в одном query → OOM.  
5. **Переписать anti-join** (hash ANTI / ключи без взрыва) + `EXPLAIN ANALYZE`.  
6. **`preserve_insertion_order = false`**, где нет ORDER BY.  
7. **`allocator_background_threads = true`** на jemalloc many-core (возврат памяти ОС, не «лимит пика», но снижает RSS after peak).  
8. OS cgroup / systemd `MemoryMax=` — **в доках SereneDB НЕ найдено** как штатная процедура; это уже OS, не SQL.

**ГИПОТЕЗА:** для merge с NOT EXISTS на миллионах строк штатный путь «не умереть kernel OOM» = снизить threads + memory_limit + разбить запрос + убедиться что join hash+spill, а не держать два полных множества + string state вне BM.

---

## 3. Инкрементальность / материализация

### 3.1. Materialized views / scheduled refresh таблиц

| Факт | Метка | Источник |
|---|---|---|
| **«SereneDB has no MATERIALIZED VIEW»** (дословно) | подтверждено доками (текущие docs) | https://docs.serenedb.com/cookbook/search/indexing-views#no-materialized-views |
| Scheduled refresh / cron для **табличной** пересборки корпуса | **в доках НЕ найдено — отрицательный вывод** | поиск `scheduled refresh` → только inverted-index refresh |
| `refresh_interval` и `REFRESH_*` / `VACUUM` — про **inverted indexes**, не про CTAS корпуса | подтверждено доками | https://docs.serenedb.com/sql/indexes/inverted/maintenance#visibility-and-the-refresh-model , https://docs.serenedb.com/sql/statements/vacuum#refreshing--refresh_ |

### 3.2. MERGE / upsert (row-level дельта штатно)

| Факт | Метка | Источник |
|---|---|---|
| `MERGE INTO … USING … ON … WHEN MATCHED / WHEN NOT MATCHED [BY SOURCE\|BY TARGET]` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/merge_into |
| Cookbook SCD Type 2: upsert + soft-delete + history одним MERGE (+ follow-up INSERT) | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/cookbook/sql_features/merge |
| `INSERT … ON CONFLICT … DO UPDATE` / `INSERT OR REPLACE` | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/insert |
| CTAS `CREATE OR REPLACE TABLE … AS SELECT` — полная пересборка таблицы одним SQL | подтверждено доками (вероятно 26.07.3) | https://docs.serenedb.com/sql/statements/create_table |

**Штатный паттерн «только изменённое» без Python:**  
источник-дельта (таблица/запрос изменившихся ключей) → `MERGE INTO` целевого корпуса `ON (business_key)` → UPDATE текста/метаданных / INSERT новых / `WHEN NOT MATCHED BY SOURCE THEN DELETE` для исчезнувших. Это ровно то, что docs рекомендуют вместо «Python/Pandas logic».

**в доках НЕ найдено — отрицательный вывод:** автоматического change-data-capture / «incremental CTAS» / partition-swap materialization framework для пользовательских таблиц — нет. Дельта = ваш SQL + MERGE.

**ГИПОТЕЗА для такта:** «полная B (row-level дельта p_doc)» ложится на штатный `MERGE`, а не на отсутствующий MATERIALIZED VIEW.

### 3.3. CTAS по частям

Docs разрешают temp/CTAS цепочкой (join_operations). Партиционирование Hive/`COPY … PARTITION_BY` — про файловый lake, не про внутреннюю таблицу корпуса.

**в доках НЕ найдено — отрицательный вывод:** декларативного `CREATE TABLE … PARTITION BY` с incremental refresh внутри native format — как замены чанкованию приложения — нет.

---

## 4. Версии и обновление

### 4.1. Какая версия СЕЙЧАС последняя

| Утверждение | Метка | Источник |
|---|---|---|
| **v26.08.2** — latest stable на 2026-08-25 | подтверждено GitHub Release + блог | https://github.com/serenedb/serenedb/releases/tag/v26.08.2 ; https://blog.serenedb.com/state-of-serene-2026-08 («v26.08.2 is the latest release») |
| Страница docs `/releases` динамически грузит GitHub («Loading GitHub releases…») — в MCP-снимке списка версий нет | подтверждено доками (пустой список) | https://docs.serenedb.com/releases |
| Термины: Latest stable = newest non-prerelease GitHub release; release line = одинаковые x.y | подтверждено доками | https://docs.serenedb.com/releases/versioning |

Цепочка после **26.07.3** (по GitHub tags):

| Версия | Дата (GitHub) | Примечание |
|---|---|---|
| v26.07.4 | 2026-07-23 | patch той же линии |
| v26.07.5 | 2026-07-28 | «всё июльское» по State of Serene July |
| v26.08.1 | 2026-08-13 | первая 26.08 (тега v26.08.0 нет — 404) |
| **v26.08.2** | 2026-08-25 | current latest |

### 4.2. Changelog после 26.07.3 — релевантное производительности / памяти / параллелизму / строкам

#### v26.07.4 (compare base: v26.07.3…v26.07.4)
Источник: https://github.com/serenedb/serenedb/releases/tag/v26.07.4  

- `fix: Dedup agg better` (#953) — агрегаты.  
- `fix: INSERT ON CONFLICT may wrongly produce conflicts` (#957).  
- Index-scan / CTE / vector score-filter fixes (#965).  
- TsDict, UNION type, pg_depend — **не** про CTAS/`string_agg` корпуса.  

**есть только в версии ≥26.07.4** (перечисленное выше).

#### v26.07.5
Источник: https://github.com/serenedb/serenedb/releases/tag/v26.07.5 ; https://blog.serenedb.com/state-of-serene-2026-07  

- **`fix: … string column faster to compress and decompress … even smaller on 10-50%`** (#969) — прямо про скорость/размер **строковых колонок** (cold/hot reads).  
- Partial inverted indexes; foreign server; distinct aggregate tests; Zstd .col layout.  
- Блог July: IVF vector rebuild, non-blocking CREATE INDEX, FSST+ −23.8% URL on disk, WAL group commit, `sdb_progress`, RBAC — **пакет «All of it is in v26.07.5»**.  

**есть только в версии ≥26.07.5** (string compression #969 и июльский пакет блога).

#### v26.08.1 / v26.08.2
Источники: https://github.com/serenedb/serenedb/releases/tag/v26.08.1 , …/v26.08.2 ; https://blog.serenedb.com/state-of-serene-2026-08  

Релевантное скорости/нагрузке (в основном **search**, не analytical CTAS):

- `perf: Faster search` (#1027, #1028); postings path «up to **2.9×**»; BM25 «nearly halved».  
- Parallel **recovery** of inverted indexes; parallel **DML against inverted index**.  
- DDL transactional.  
- Sequences faster.  
- Azure storage, sloppy phrase, REINDEX remote, Lucene syntax, idf() — search/cloud.  
- Object-storage reads ~20% faster (блог).  

**есть только в версии ≥26.08.1 / 26.08.2.**

**в доках/changelog НЕ найдено — отрицательный вывод:** после 26.07.3 **нет** заявленного «string_agg теперь spill’ит на диск», «CTAS streaming», «memory_limit покрывает aggregate state», «автоматический row-level corpus refresh». То есть **апгрейд сам по себе не чинит класс бага OOM/`string_agg`**, описанный в текущих docs как limitation.

Ближайшее к «быстрее большие тексты» в патчах: **сжатие/разжатие string columns 10–50% (#969 → 26.07.5)** — косвенно ускоряет cold/hot read строковых колонок витрины/корпуса, не отменяет монолитный `string_agg`.

### 4.3. Процедура обновления / WAL / бэкап / откат

| Тема | Находка | Метка |
|---|---|---|
| Установка .deb | `sudo apt install ./serenedb_*.deb` затем `systemctl enable --now serenedb` | подтверждено доками: https://docs.serenedb.com/installation/debian |
| Отдельный раздел «Upgrade / migrate between versions» | **в доках НЕ найдено — отрицательный вывод** | search `upgrade migrate` |
| Совместимость WAL при смене бинарника | **в доках НЕ найдено явной процедуры «stop → replace binary → replay WAL»** | — |
| `STORAGE_VERSION` на ATTACH: min version, которая сможет читать файл; opt-in forwards-**incompatible** features; default `v1.0.0` | подтверждено доками: https://docs.serenedb.com/sql/statements/attach/duckdb#explicit-storage-versions | «When database files are written with this option, the resulting files **cannot be opened by older SereneDB versions**» |
| `CHECKPOINT` / `force_checkpoint` / checkpoint on shutdown (WAL → main file) | подтверждено доками | https://docs.serenedb.com/sql/functions/utility#checkpointdatabase ; pragmas checkpoint |
| Полный логический бэкап/restore | `EXPORT DATABASE 'dir'` / `IMPORT DATABASE 'dir'` (schema.sql + load.sql + CSV/Parquet) | подтверждено доками: https://docs.serenedb.com/sql/statements/export_and_import_database |
| Откат на старый бинарник | Docs: файл, записанный с более новым `STORAGE_VERSION`, **не** откроется старым движком. Без явного bump — **ГИПОТЕЗА**: patch внутри линии часто читает старые файлы (не доказано docs для 26.07→26.08) | ATTACH storage versions |

**Практическая «доказательная» схема апгрейда (сборка из docs + пробелы помечены):**

1. Остановить нагрузку записи; `CHECKPOINT` / `force_checkpoint()` — свернуть WAL.  
2. **Бэкап данных/векторов:** filesystem copy каталога data **после** checkpoint **и/или** `EXPORT DATABASE` (векторы/таблицы уедут как данные таблиц — проверить, что нужные relation’ы в export; **живая проверка на стенде обязательна — не делалась**).  
3. Поставить новый `.deb` (`apt install ./serenedb_26.08.2_….deb`) — docs.  
4. Старт сервиса; `PRAGMA version;` / smoke.  
5. Откат: вернуть старый `.deb` + восстановление из FS-копии / `IMPORT`, если новый бинарник успел переписать storage несовместимо.  

**ГИПОТЕЗА безопасности:** для сохранения векторов надёжнее **offline FS snapshot** каталога `/var/lib/serenedb` (после checkpoint), чем полагаться только на EXPORT без пробы. Docs не дают «vector-aware backup» checklist.

### 4.4. Матрица «уже в 26.07.3» vs «только в X»

| Средство | Версия |
|---|---|
| `SET threads` / `SET GLOBAL threads`, row-group parallelism, EXPLAIN ANALYZE | **вероятно уже в 26.07.3** (docs; не в post-changelog как new) |
| `memory_limit`, `temp_directory`, spill JOIN/GROUP/ORDER/WINDOW | **вероятно 26.07.3** |
| Ограничение: `string_agg`/`list` без disk offload; память вне BM | **вероятно 26.07.3** (и всё ещё в *текущих* docs → **не снято** апгрейдом) |
| MERGE INTO, INSERT ON CONFLICT, CTAS OR REPLACE | **вероятно 26.07.3** |
| Нет MATERIALIZED VIEW | **текущие docs** (и для 26.08) |
| String column compress/decompress +10–50% size (#969) | **только ≥26.07.5** |
| Июльский пакет (IVF rebuild, non-blocking CREATE INDEX, WAL group commit, …) | **только ≥26.07.5** (блог) |
| Faster search 2.9×, parallel index recovery/DML, Azure, Lucene, … | **только ≥26.08.1/26.08.2** |

---

## Топ-5 кандидатов «кратно быстрее» (по убыванию ожидаемого эффекта)

Оценка эффекта — из docs + соответствия симптомам (монолит `string_agg`/`list` на ~75k; merge anti-join 1.66M×1.44M → OOM 91 GB). Это **приоритет расследования/переписывания SQL**, не обещание коэффициента без замера.

### 1. Row-level дельта через штатный `MERGE` вместо полной пересборки `p_doc` / полного anti-join merge
**Почему кратно:** при малой доле изменившихся ключей работа O(Δ) вместо O(N) и O(N×M) anti-join. Docs позиционируют MERGE как «cleaner and faster than equivalent Python» и дают SCD/upsert паттерн.  
**Источник:** https://docs.serenedb.com/sql/statements/merge_into , https://docs.serenedb.com/cookbook/sql_features/merge  
**Версия:** вероятно уже 26.07.3.  
**Риск:** нужна корректная дельта-витрина ключей; иначе тихая порча корпуса.

### 2. Убрать / раздробить `string_agg`/`list` (чанки или иной native shape текста) — класс без spill
**Почему кратно:** docs прямо: эти агрегаты **не offload’ят на диск** и едят RAM вне `memory_limit`; на больших группах → CPU+RAM wall. Соседние чанкуемые сущности (~минуты) vs монолит (часы) согласуются с этим ограничением.  
**Источник:** https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#limitations , https://docs.serenedb.com/configuration/pragmas#memory-limit  
**Версия:** limitation актуален и в текущих docs (после 26.08).  
**Апгрейд не снимает.**

### 3. Переписать merge anti-join: hash ANTI / разнести blocking operators / форсировать join order; `EXPLAIN ANALYZE`
**Почему кратно на шаге слияния:** docs — избежать nested loop и cardinality explosion; несколько blockers в одном query → OOM; temp-table pipeline — штатный способ.  
**Источник:** https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#profiling , https://docs.serenedb.com/cookbook/performance/join_operations , https://docs.serenedb.com/sql/query_syntax/from_and_join#semi-and-anti-joins  
**Дополнительно:** `SET memory_limit` + ↓`threads` + `temp_directory` на SSD — чтобы spill сработал *до* kernel OOM (с оговоркой про память вне BM).

### 4. Включить реальный multi-core на больших сканах: `SET threads`, учесть порог row group 122 880; не раздувать threads на join-heavy без RAM
**Почему:** при достаточном числе row groups docs обещают параллельный scan; «1–4 GB/thread»; слишком много threads вредно. На 75k строк **ГИПОТЕЗА слабого эффекта** без чанкования/меньшего ROW_GROUP_SIZE. На merge 1.6M строк — threads могут помочь *если* план hash+parallel и хватает RAM.  
**Источник:** https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#the-effect-of-row-groups-on-parallelism , https://docs.serenedb.com/cookbook/performance/environment#memory-for-ideal-performance

### 5. Апгрейд 26.07.3 → **26.07.5** (минимум) / **26.08.2** (latest) — с FS-бэкапом векторов
**Почему не #1:** release notes **не** обещают spill для `string_agg` и не чинят analytical CTAS; выигрыш для корпуса скорее косвенный (**string compress #969**, storage fixes). Search perf 26.08 к такту сборки текстов почти не относится.  
**Зато:** патчи агрегатов/INSERT ON CONFLICT (26.07.4), string I/O (26.07.5), стабильность DDL/recovery (26.08).  
**Безопасность:** отдельной upgrade/WAL-compat процедуры в docs **нет** → checkpoint + offline copy data dir + `.deb` install; откат = старый пакет + копия. Не писать `STORAGE_VERSION` выше, чем готов откатывать.  
**Источники:** GitHub releases v26.07.4/5, v26.08.1/2; https://docs.serenedb.com/installation/debian ; https://docs.serenedb.com/sql/statements/attach/duckdb#explicit-storage-versions ; https://docs.serenedb.com/sql/statements/export_and_import_database

---

## Краткие ответы на вопросы владельца

| Вопрос | Ответ одной строкой |
|---|---|
| Как ускорить штатно? | Дельта-`MERGE`; не держать гигантский `string_agg`/`list` без чанков; hash anti-join + разбиение query; threads с учётом row groups; memory/temp тюнинг. |
| Чем ограничить пик? | `memory_limit` + ↓`threads` + spill temp — **частично**; `string_agg`/`list` лимит **не** ловит → нужен rewrite. |
| Инкремент штатно? | `MERGE` / upsert; **нет** MATERIALIZED VIEW и scheduled table refresh. |
| Обновлять движок? | Latest **26.08.2**; для строк полезен уже **26.07.5** (#969); limitation `string_agg` остаётся; апгрейд только с checkpoint+FS backup векторов. |

---

*Конец отчёта T1-A1. Только этот файл изменён аудитором.*
