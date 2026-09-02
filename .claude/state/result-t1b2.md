# T1-B2: аудит аудита A1 (доки SereneDB)

**Дата:** 2026-09-02  
**Проверяемый отчёт:** `/srv/1c/.claude/state/result-t1a1.md`  
**Метод:** независимый повторный поход MCP `serenedb-docs` (`search_docs` → `read_section`) + read-only WebFetch (docs / GitHub Releases / блог).  
**Ограничения:** серверы не трогались; код репо не правился; живой `PRAGMA version` не снимался.

Метки вердикта: **ПОДТВЕРЖДЕНО** / **ОПРОВЕРГНУТО** / **НЕПРОВЕРЯЕМО**.

---

## Таблица: утверждение → вердикт → мой источник

| # | Утверждение A1 | Вердикт | Мой источник (url / цитата) |
|---|---|---|---|
| 1a | Параллелизм по row groups; default **122 880**; для k потоков нужно ≥ **k×122 880** строк | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#the-effect-of-row-groups-on-parallelism — «The default row group size … is 122,880 rows. … for a query to run on k threads, it needs to scan at least k * 122,880 rows.» |
| 1b | `ATTACH … (ROW_GROUP_SIZE N)` только для **нового** файла | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/statements/attach/duckdb — Options: `ROW_GROUP_SIZE · The row group size of a **new** database file · … · 122880`. (Аналог `BLOCK_SIZE`: «Cannot be set for existing files».) |
| 1c | Это объясняет «75k строк ≈ 1 поток» | **ПОДТВЕРЖДЕНО** (как следствие docs; живой замер — вне scope) | Из 1a: 75 000 < 122 880 ⇒ при default size ≤1 row group на скане ⇒ штатный multi-thread scan не включается. Согласуется с гипотезой A1. |
| 2a | `list()` / `string_agg()` **не** support offloading to disk | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#limitations — «Some aggregate functions, such as list() and string_agg(), do not support offloading to disk.» |
| 2b | Память `string_agg`/`list`/… **вне** buffer manager; `memory_limit` её не ловит | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/configuration/pragmas#memory-limit — Attention: «… aggregate functions with complex state (e.g., list, mode, quantile, string_agg, and approx functions) use memory outside of the buffer manager. Therefore, the actual memory consumption can be higher than the specified memory limit.» |
| 2c | Несколько blocking operators в одном запросе → возможен OOM | **ПОДТВЕРЖДЕНО** | Там же Limitations: «If multiple blocking operators appear in the same query, SereneDB may still throw an out-of-memory exception…» |
| 3a | `memory_limit` default **80% RAM**, только buffer manager | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/configuration/limits#limit-values — «Memory use · 80% of RAM · memory_limit · Note: This limit only applies to the buffer manager.»; также OOM cookbook. |
| 3b | Per-query memory cap отсутствует | **ПОДТВЕРЖДЕНО** (отриц. вывод) | Поиск `per-query` / session memory: отдельного knob нет; в Limits только глобальный `memory_limit`. Конфиг overview / OOM: советуют ↓`threads` + ↓`memory_limit`, не per-query. |
| 4a | Синтаксис ANTI JOIN / SEMI JOIN есть | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/query_syntax/from_and_join#semi-and-anti-joins (+ anti-join example на той же странице). |
| 4b | Рекомендация «hash join вместо nested loop» | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads#profiling — «Avoid nested loop joins in favor of hash joins.» |
| 4c | Форсировать порядок JOIN: temp-таблицы или `disabled_optimizers` | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/join_operations#how-to-force-a-join-order ; `#turn-off-the-join-order-optimizer` — `SET disabled_optimizers = 'join_order,build_side_probe_side'`. |
| 5a | MERGE INTO: `WHEN MATCHED` / `NOT MATCHED [BY SOURCE\|BY TARGET]` (+ THEN DELETE) | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/statements/merge_into — примеры `WHEN MATCHED THEN DELETE`, `WHEN NOT MATCHED BY SOURCE THEN DELETE`, `WHEN NOT MATCHED BY TARGET`. |
| 5b | Cookbook SCD-паттерн | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/sql_features/merge — SCD Type 2 + таблица паттернов upsert/delete. |
| 6a | MATERIALIZED VIEW нет | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/search/indexing-views#no-materialized-views — «SereneDB has no MATERIALIZED VIEW.»; CREATE VIEW: «The view is not physically materialized.» |
| 6b | Scheduled refresh **пользовательских таблиц** нет | **ПОДТВЕРЖДЕНО** (отриц. вывод) | Поиск `scheduled refresh` → только inverted-index `refresh_interval` / `VACUUM REFRESH_*` (https://docs.serenedb.com/sql/indexes/inverted/maintenance#visibility-and-the-refresh-model). Отдельного cron/refresh для CTAS-таблиц корпуса нет. |
| 7a | Цепочка версий после 26.07.3: 26.07.4 (2026-07-23), 26.07.5 (2026-07-28), 26.08.1 (2026-08-13), 26.08.2 (2026-08-25, latest) | **ПОДТВЕРЖДЕНО** | GitHub Releases tags (WebFetch): даты совпали. Блог: https://blog.serenedb.com/state-of-serene-2026-08 — «v26.08.2 is the latest release.» |
| 7b | В этих релизах **нет** string_agg spill / CTAS streaming / per-query memory / параллелизма аналитических агрегатов | **ПОДТВЕРЖДЕНО** (отриц. вывод) | Прочитаны notes v26.07.4, v26.07.5, v26.08.1, v26.08.2: нет пунктов про spill `string_agg`/`list`, streaming CTAS, per-query memory. 26.08 — в основном **search** (faster search, Lucene, parallel **index recovery/DML** в блоге). Текущие docs Limitations всё ещё говорят «do not support offloading». |
| 8 | #969 в 26.07.5: string column faster compress/decompress, 10–50% smaller | **ПОДТВЕРЖДЕНО** | https://github.com/serenedb/serenedb/releases/tag/v26.07.5 — PR #969: «string column faster to compress and decompress … even smaller on 10-50%». |
| 9a | Отдельной процедуры upgrade/migrate в доках нет | **ПОДТВЕРЖДЕНО** (отриц. вывод) | `search_docs` `upgrade migrate` → Releases/Versioning/утилиты, не runbook апгрейда. Установка — https://docs.serenedb.com/installation/debian. |
| 9b | `STORAGE_VERSION` на ATTACH: файлы с более новой версией не открываются старым движком | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/statements/attach/duckdb#explicit-storage-versions — «… cannot be opened by older SereneDB versions than the specified version.» |
| 9c | `EXPORT`/`IMPORT DATABASE`; `CHECKPOINT`/`force_checkpoint` | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/statements/export_and_import_database ; https://docs.serenedb.com/sql/functions/utility#checkpointdatabase / `#force_checkpointdatabase`. |
| 10a | `duckdb_memory()` / `duckdb_temporary_files()` | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/sql/functions/duckdb_table_functions — «duckdb_memory() · Buffer manager memory usage»; «duckdb_temporary_files() · Temporary files written to disk». |
| 10b | `preserve_insertion_order=false` | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/cookbook/performance/how_to_tune_workloads (раздел preserve_insertion_order); OOM cookbook. |
| 10c | `allocator_background_threads` default **false**; `allocator_flush_threshold` **128 MiB** | **ПОДТВЕРЖДЕНО** | https://docs.serenedb.com/configuration/overview#global-configuration-options — `allocator_background_threads · … · BOOLEAN · false`; `allocator_flush_threshold · … · 128.0 MiB`. |

---

## Доп. проверки (то, что A1 мог не найти)

| Вопрос | Вердикт | Источник / вывод |
|---|---|---|
| (а) Задать `ROW_GROUP_SIZE` для **существующей** БД/таблицы без пересоздания? | **НЕ найдено** (отриц.) | ATTACH: опция только для **new** database file. ALTER TABLE (compat) не упоминает row group size. Путь «новый ATTACH + COPY» = пересоздание файла, не in-place. |
| (б) Perf-советы по UNPIVOT / `COLUMNS(*)`? | **НЕ найдено** (синтаксис есть, perf — нет) | https://docs.serenedb.com/sql/statements/unpivot — API + `COLUMNS(* EXCLUDE …)`; https://docs.serenedb.com/sql/expressions/star#columns-expression. Отдельных cookbook/perf-разделов по скорости UNPIVOT/`COLUMNS(*)` поиск не дал. PIVOT в Limitations привязан к `list()` (OOM), не к UNPIVOT. |

---

## Опровержения

**Существенных опровержений ключевых утверждений A1 нет.**

Уточнения (не опровержения):

1. **«75k = 1 поток»** — следствие порога row groups из docs + гипотеза A1; живой CPU-профиль в B2 не снимался → формулировка «объясняет» логически верна по docs, но не заменена замером.
2. **Параллелизм в 26.08** (блог: parallel recovery / DML **inverted indexes**) — есть, но это **search/index**, не снятие limitation `string_agg`/`list`. A1 это и так отделяет; не меняет вывод про апгрейд и spill.
3. **#969** — про сжатие **string columns** на storage I/O, не про aggregate spill; A1 корректно называет косвенным.

---

## Вывод A1 «апгрейд до 26.08.2 не снимает ограничение string_agg/память»

**Подтверждаю.**  
В release notes 26.07.4…26.08.2 и в State of Serene August **нет** объявления spill для `string_agg`/`list`, покрытия aggregate state через `memory_limit`, streaming CTAS или per-query memory. Актуальные docs Limitations и Attention у `memory_limit` по-прежнему описывают то же ограничение. Апгрейд сам по себе **не** меняет план относительно класса OOM/`string_agg`.

---

## Вывод: отчёт A1 пригоден как основа плана — **да**

Все 10 обязательных блоков сверены независимым походом; опровержений нет; отрицательные выводы A1 (нет MV/table schedule, нет upgrade runbook, нет spill в changelog) воспроизведены. Доп. находки (а)/(б) план не ломают: in-place `ROW_GROUP_SIZE` нет; UNPIVOT/`COLUMNS(*)` без perf-guidance в docs.
