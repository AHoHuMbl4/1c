# CHECK2_INCR_1 — штатные механизмы SereneDB против нашей 5-минутной пересборки корпуса

Сборка на инстансе: **PostgreSQL 18.3 (SereneDB 26.07.3)**, `host=127.0.0.1 port=7890`.
Репозиторий: `/srv/data/cursor/cursor/1/serenedb-src` (ветка `main`, расхождения со сборкой отмечены).
Проверяемый код: `/srv/data/cursor/cursor/1/1c/ubuntu/serenedb/serene_search_build.py` (990 строк).

Пометки: **[код]** — ссылка на файл:строку в исходниках/тестах/демках, **[замер]** — время, снятое на живом
инстансе, **[вывод]** — дословный вывод команды с живого инстанса.

---

## Краткий итог первого прохода

Фаза, которая сейчас занимает 86 % пятиминутного такта (233 `count(*)` + 233 `duckdb_columns()` +
вычитывание 97 965 строк в Python + сборка `doc`/`refs` + SHA1 в Python + 490 `INSERT` в staging +
233 `LEFT JOIN`), **целиком выражается штатными средствами движка одним запросом**.

**Замерено на нашей базе [замер]:** один запрос строит `doc` с РАЗРЕШЁННЫМИ именами ссылок по всем
233 таблицам (96 931 строка, 47 302 850 байт текста), считает `sha1` и делает анти-джойн с
`search_corpus` — **4.4 с**, один процесс `psql`, ноль строк в Python.

Против ~258 с и ~1 190 процессов `psql` сейчас. Это **×58** по времени фазы и −1 189 процессов.

Свойство «ссылки разрешаются в имена» при этом НЕ теряется, а усиливается: разрешение делается
`LEFT JOIN` на карту `Ref_Key → Description`, собранную из базы в тот же момент, поэтому переименование
контрагента меняет `doc` того же такта (сейчас — тоже, но ценой перекачки всей базы).

---

## 1. Индекс поверх VIEW

### 1.1. Поддерживается — да, штатно и широко

**[код]** `examples/demo6/bootstrap.sql` — целая демка построена на «нет таблиц вообще, только VIEW»:

```
-- The pattern this demo showcases (no COPY, no native tables):
--   1. one view per source, each reshaping its own parquet schema in SQL
--      (renames, casts, CASE mappings, computed columns, generated ids);
--   2. one UNION ALL mega view gluing the per-source views together;
--   3. one inverted index over the mega view where every retrieved column is
--      also INCLUDEd -- after the build the index is self-sufficient: queries
--      never re-read the parquet, even across restarts.
```

и там же:

```sql
CREATE VIEW tasks_v AS
SELECT * FROM tasks_cf_v
UNION ALL
SELECT * FROM tasks_cc_v;

CREATE INDEX tasks_idx ON tasks_v
USING inverted(id, rating, title cf_en, statement cf_en, editorial cf_en, tags cf_en)
INCLUDE (id, contest_name, rating, title, statement, editorial, tags);
```

**[код]** `tests/sqllogic/sdb/pg/site_docs/cookbook/search/indexing-views.test` — индекс над VIEW поверх
ОБЫЧНОЙ таблицы `docs`, с BM25, `GROUP BY` по `category` и VIEW поверх самого индекса:

```sql
CREATE VIEW v_docs AS SELECT id, body, category FROM docs;
CREATE INDEX v_docs_idx ON v_docs USING inverted (id, body en, category);
SELECT category, count(*) AS n FROM v_docs_idx WHERE body @@ 'quick' GROUP BY category;
```

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view.test`, `inverted_index_view_variants.test`,
`inverted_index_view_include.test`, `inverted_index_view_attached.test`, `inverted_index_view_glob.test`,
`inverted_index_view_pruning.test`, `inverted_index_view_params.test`, `inverted_index_view_duckdb.test`,
`recovery/catalog_view_inverted_index.test` — индекс над VIEW переживает рестарт, покрыт проекциями,
кастами, переименованиями, `WHERE/ORDER BY/LIMIT` в теле VIEW.

### 1.2. Что происходит при изменении базовых данных — индекс ЗАМОРОЖЕН

Это ответ «нет» на главный вопрос, и он жёсткий.

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view_attached.test:137-152` — дословно:

```
# The index is frozen at CREATE INDEX time: rows inserted into the source
# afterwards exist in the view but produce no postings.
statement ok
INSERT INTO db172.main.docs VALUES (5, 'eta cat hides', 50);

query
SELECT count(*) FROM v_att;
----
count
5

query
SELECT id FROM v_att_idx WHERE body @@ ts_phrase('cat') ORDER BY id;
----
id
1
3
```

То есть источник видит 5 строк, индекс — по-прежнему 2 постинга.

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view.test:103` — комментарий в самом тесте:
`# View over a serenedb rocksdb table -- static, no DML refresh.`

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view_attached.test:158-160` — удалённая в источнике
строка не исчезает из индекса, а материализуется как NULL:
`# Committed source deletion after CREATE INDEX: the stale posting materializes as NULLs instead of garbage.`

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view_attached.test:1-7` — формулировка контракта:
`the index pins what it indexed`.

### 1.3. `VACUUM (REFRESH_*)` не помогает — это НЕ перечитывание источника

**[код]** `server/connector/duckdb_vacuum_function.cpp:68-77` — полный список глаголов:
`refresh_database`, `refresh_schema`, `refresh_table`, `refresh_index`, `refresh_all`,
`compact_table` (+ `compact_*`).

**[код]** `server/connector/duckdb_vacuum_function.cpp:431` — что именно делает Refresh:
`search->VacuumRefresh();  // commit pending inserts + reclaim files`.

То есть REFRESH коммитит уже принятые движком вставки и подчищает файлы. Он не идёт в источник VIEW.

### 1.4. Штатный способ обновить индекс над VIEW — `DROP INDEX` + `CREATE INDEX`

**[код]** `tests/sqllogic/sdb/pg/site_docs/cookbook/search/indexing-external-data.test`, example_006 —
в официальном кукбуке ровно это:

```sql
DROP INDEX logs_idx;
CREATE INDEX logs_idx ON logs USING inverted (id, level, service, message english_dict);
```

**[замер, наш, уже зафиксирован]** `docs/SERENEDB.md:244-260`: «Индекс — это СНИМОК»; построение индекса
над PG-VIEW на 50 000 строк — **423 мс**, пересборка **0.4–0.5 с на 50 тыс. строк**;
`DROP INDEX` + `CREATE INDEX` — единственное, что подхватывает изменения источника.

**[код]** пересборка при этом онлайновая и безопасна относительно параллельного DML:
`tests/sqllogic/recovery/online_create_index_concurrent_dml.test:1-6` —
`the build runs async while real DML executes against the same table; the published index must exactly
match the table`.

### 1.5. Вывод по вопросу 1

Корпус **можно** выразить как VIEW-джойн витрины, и тогда:
- разрешение ссылок становится обычным JOIN и всегда актуально (требование правильности выполняется
  по построению, а не отпечатком);
- отдельной таблицы корпуса и её построчной пересборки не нужно;
- НО индекс придётся **пересоздавать каждый такт** (`DROP`+`CREATE`), потому что он снимок.
  При 98 тыс. строк это по нашему же замеру порядка **1 с** — в бюджет 20 минут укладывается с запасом.

Ограничения, которые это накладывает и которые надо решить до внедрения:
- **Материализация колонок.** Для VIEW, тело которого не `SELECT * FROM read_parquet/csv/json(...)`,
  вернуть колонку, которой нет ни в ключах, ни в `INCLUDE`, нельзя:
  **[код]** `tests/sqllogic/sdb/pg/site_docs/sql/indexes/inverted/views.test`, блок `generic_error`:
  `db error: ERROR: materialising real columns from this view-backed inverted index is not yet supported --
  view body must be a simple SELECT * FROM <reader>(literal_args) over a recognised fast-path source
  (read_parquet/csv/json/...)`.
  Для VIEW над обычной таблицей движка материализация работает
  (**[код]** `inverted_index_view.test:120-135`, `SELECT id, body, extra FROM i_star` возвращает строки),
  но наш корпус — это UNION ALL из 233 источников, то есть generic-случай ⇒ **всё, что нужно вернуть,
  обязано быть в `INCLUDE`**.
- **Вектор `emb FLOAT[1536]`** во VIEW взять неоткуда, кроме как `LEFT JOIN` на таблицу-кэш эмбеддингов
  по `doc_hash`. Работоспособность `FLOAT[1536]` как `INCLUDE`-колонки индекса над VIEW **не проверена**
  (см. «Что проверить замером»); опклассом `ivf` его индексировать нельзя — запрет владельца
  (`memory: project-serenedb-ivf-blocked`).

---

## 2. Сборка строки `doc` в SQL

### 2.1. Да, и БЕЗ генерации списка колонок

Проверено на живом движке. Ключ — `to_json(t)` по всей строке + `json_each` в `LATERAL` + `string_agg`.

**[вывод]** `to_json(t)` по всей строке:
```
$ psql "$D" -tAc "SELECT to_json(t) FROM catalog_странымира t LIMIT 1"
{"Ref_Key":"d99f7eb1-7320-11ec-95fd-0242ac120003","DataVersion":"AAAAAQAAAAA=","DeletionMark":false,
 "Code":643,"Description":"РОССИЯ","НаименованиеПолное":"Российская Федерация","КодАльфа2":"RU", ...}
```

**[вывод]** «Колонка: значение | Колонка: значение» одним выражением, имена колонок нигде не перечислены:
```sql
SELECT j.Ref_Key, s.doc
FROM (SELECT Ref_Key, to_json(t) AS jj FROM catalog_странымира t) j,
LATERAL (SELECT string_agg(je.key || ': ' || je.value, ' | ') AS doc FROM json_each(j.jj) je) s;
```
```
d99f7eb1-7320-11ec-95fd-0242ac120003|Ref_Key: "d99f7eb1-..." | DataVersion: "AAAAAQAAAAA=" |
DeletionMark: false | Code: 643 | Description: "РОССИЯ" | НаименованиеПолное: "Российская Федерация" | ...
```

### 2.2. Что ещё есть в сборке (проверено `duckdb_functions()`)

**[вывод]** есть: `string_agg`, `concat_ws`, `array_to_string`, `list_transform`, `list_aggregate`,
`struct_pack`, `struct_extract`, `to_json`, `row_to_json`, `json_each`, `json_keys`, `json_extract_string`,
`json_group_array`, `json_group_object`, `json_serialize_sql`, `json_deserialize_sql`.

**[вывод]** `COLUMNS(*)` поддерживается, но она **размножает выражение по колонкам**, а не склеивает:
```
$ SELECT concat_ws(' | ', COLUMNS(*)) FROM catalog_странымира LIMIT 1;
d99f7eb1-...|AAAAAQAAAAA=|false|643|РОССИЯ|Российская Федерация|RU|RUS|true|...   <- 14 отдельных колонок
```
**[вывод]** голая звезда внутри функции запрещена:
```
$ SELECT concat_ws(' | ', *) FROM catalog_странымира LIMIT 1;
ERROR:  STAR expression is only allowed as the root element of an expression. Use COLUMNS(*) instead.
```
То есть путь через `COLUMNS(*)` для склейки в ОДНУ строку не годится; годится путь через `to_json`.

### 2.3. Нужна ли генерация SQL

Для **одной таблицы** — нет: запрос из 2.1 универсален, в нём меняется только имя таблицы.
Для **всех таблиц сразу** — нужна ровно одна генерация: `UNION ALL` из 233 веток. Она делается
**внутри движка** одним `string_agg` по каталогу, Python в ней не участвует:

**[вывод]**
```sql
SELECT string_agg(
  'SELECT ' || quote_literal(table_name) || ' AS src_table, t."Ref_Key"::VARCHAR AS row_key,
   to_json(t) AS jj FROM ' || quote_ident(table_name) || ' t', E'\nUNION ALL ')
FROM (SELECT table_name, bool_or(column_name='Ref_Key') AS has_ref,
             bool_or(data_type LIKE '%[]') AS has_vec
      FROM duckdb_columns() WHERE schema_name='public' GROUP BY table_name)
WHERE NOT has_vec AND table_name NOT LIKE 'search%';
```
Отдаёт готовый текст 50 540 байт [замер: 0.27 с]. Дальше его можно скормить обратно одним `psql -f`.
Динамического SQL (`EXECUTE`) в движке нет — текст надо прогнать вторым вызовом, но это **два процесса
`psql` на весь такт**, а не 1 190.

---

## 3. Отпечаток в SQL

**[вывод]** в сборке 26.07.3 есть:
```
$ SELECT DISTINCT function_name FROM duckdb_functions() WHERE function_name ~ 'md5|sha|hash|crc|digest';
hash
md5
md5_number
md5_number_lower
md5_number_upper
sha1
sha256
```
`xxhash` — **нет**. `digest`/`crc32` — **нет**.

**[вывод]** все работают:
```
$ SELECT sha1('1'), sha256('1'), md5('1'), hash('1'), md5_number('1');
356a192b7913b04c54574d18c28d46e6395428ab|6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b|
c4ca4238a0b923820dcc509a6f75849b|15512189757048957329|206718104415996593065841226801035266756
```
`sha1` даёт тот же алгоритм, что `hashlib.sha1` в `serene_search_build.py:809` — то есть отпечатки
совместимы и переход не требует разовой полной переиндексации (при условии побайтово того же `doc`).

**[замер]** отпечаток по СОБРАННОЙ строке считается прямо в SQL, данные наружу не идут.
Таблица `catalog_поляформстатистики`, 23 878 строк:

| что | время |
|---|---|
| собрать `doc` (`to_json`+`json_each`+`string_agg`), 21.9 МБ текста | 900 мс |
| собрать `doc` + `sha1(doc)`, `count(DISTINCT)` = 23 878 (коллизий 0) | **815 мс** |
| `sha1(to_json(t)::VARCHAR)` напрямую, без сборки строки | 376 мс |

---

## 4. Обнаружение изменений штатно

### 4.1. Журнала изменений / CDC / версий строк — НЕТ

Просмотрено: `duckdb_*` табличные функции сборки (**[вывод]** полный список:
`duckdb_approx_database_count, duckdb_available_metrics, duckdb_columns, duckdb_connection_count,
duckdb_constraints, duckdb_coordinate_systems, duckdb_databases, duckdb_dependencies,
duckdb_eviction_queues, duckdb_extensions, duckdb_external_file_cache, duckdb_format_sql,
duckdb_functions, duckdb_indexes, duckdb_keywords, duckdb_log_contexts, duckdb_logs,
duckdb_logs_parsed, duckdb_memory, duckdb_optimizers, duckdb_prepared_statements,
duckdb_profiling_settings, duckdb_schemas, duckdb_secret_types, duckdb_secrets, duckdb_sequences,
duckdb_settings, duckdb_table_sample, duckdb_tables, duckdb_temporary_files, duckdb_triggers,
duckdb_types, duckdb_variables, duckdb_views`) — **ни одной с журналом изменений или счётчиком версий
таблицы**. `duckdb_tables()` не отдаёт даже времени последней модификации.

`xmin`/`xid` в pg-совместимом слое есть только как функции над снапшотами
(**[код]** `tests/sqllogic/any/pg/system/functions-info.test:1121,1193`), к строкам они не привязаны.

### 4.2. `rowid` — есть и стабилен при in-place UPDATE

**[код]** `tests/sqllogic/sdb/pg/dml/merge_returning_rowid.test:2-5,21` —
`Matched UPDATE of a non-PK column with RETURNING: in-place, rowid unchanged`;
**[код]** `tests/sqllogic/sdb/pg/dml/upsert_returning_rowid.test:4-5` — обновление индексированной или
LIST-колонки идёт через delete+insert и **rowid двигается**. То есть `rowid` не годится как «версия
строки» для обнаружения изменений в источнике.

### 4.3. `MERGE ... RETURNING merge_action` — ЕСТЬ и это лучший штатный инструмент

**[код]** `tests/sqllogic/sdb/pg/site_docs/sql/statements/merge_into/index.test:110-145` — дословный
контракт возвращаемого значения:

```sql
MERGE INTO people
    USING (SELECT unnest([3, 1]) AS id, unnest([89_000.0, 70_000.0]) AS salary) AS upserts
    USING (id)
    WHEN MATCHED AND people.salary < 100_000.0 THEN UPDATE SET salary = upserts.salary
    WHEN MATCHED AND people.salary > 100_000.0 THEN DELETE
    WHEN NOT MATCHED THEN INSERT BY NAME
    RETURNING merge_action, *;
----
merge_action	id	name	salary
UPDATE	3	Sarah	89000
DELETE	1	John	105000
```

и с `NOT MATCHED BY SOURCE` (то есть удаление исчезнувших из источника — наша «gone-очистка»):

```sql
MERGE INTO target USING (SELECT 1 AS id) source USING (id)
    WHEN MATCHED THEN UPDATE
    WHEN NOT MATCHED BY SOURCE THEN DELETE
    RETURNING merge_action, *;
----
merge_action	id
UPDATE	1
DELETE	2
```

**`merge_action`** — это `VARCHAR` со значениями `INSERT` / `UPDATE` / `DELETE`, и рядом с ним можно
вернуть `*` (или любые колонки цели), то есть **да, список затронутых ключей получается напрямую**.

**[вывод]** проверено на НАШЕЙ сборке — план строится, колонка `merge_action` признаётся:
```
$ EXPLAIN MERGE INTO search_corpus t
    USING (SELECT 'zzz'::VARCHAR AS src_table, 'zzz'::VARCHAR AS row_key) s
    ON t.src_table = s.src_table AND t.row_key = s.row_key
    WHEN MATCHED THEN DELETE
    RETURNING merge_action, t.row_key;
╭─ PROJECTION ───────────────────────╮
│ Projections: merge_action, row_key │
╰──────────────────┬─────────────────╯
╭─ MERGE_INTO ─────┴─────────────────╮
...
╭─ SEQ_SCAN ───────┴─────────────────╮
│ Table: search_corpus               │
```
(EXPLAIN, не исполнение — запрет на DML соблюдён.)

### 4.4. Ограничение MERGE, которое надо знать

**[код]** `server/connector/duckdb_catalog.cpp:824-838`:
```cpp
if (table_entry.GetSereneDBTable()->GetEngine() == catalog::TableEngine::Search) {
  // MERGE INTO (and INSERT ... ON CONFLICT, which duckdb also lowers to
  // MergeInto) delegates each action to the store mirror, which bypasses the
  // iresearch index -- it silently corrupts the search index. Reject it with
  // a clear error until search-backed MERGE is implemented.
  THROW_SQL_ERROR(... "MERGE INTO (and INSERT ... ON CONFLICT) is not yet supported on "
                      "search-backed tables");
}
```
Запрет распространяется **только на таблицы движка `TableEngine::Search`** (search-таблицы), а не на
обычную таблицу с инвертированным индексом. Наш `search_corpus` — обычная таблица
(**[вывод]** `duckdb_tables()` отдаёт для неё `CREATE TABLE public.search_corpus(src_table VARCHAR, ...)`),
поэтому MERGE по ней разрешён — что и подтверждает EXPLAIN выше и текущая работа
`serene_search_build.py:729`.

**[код]** MERGE в цель с инвертированным индексом отдельно покрыт тестом:
`tests/sqllogic/sdb/pg/dml/merge.test:2,46,57` — `Same merge actions against a table with an inverted
index` … `the index forces the commit-time append/delete path`.

---

## 5. Массовая вставка вместо 490 `INSERT` по 200 строк

| механизм | доступен по pg-протоколу | доказательство |
|---|---|---|
| `COPY ... FROM STDIN` | **да**, и есть регресс-тест именно на wire-протокол | **[код]** `tests/drivers/psql/tests.test:969-972`: `# COPY FROM STDIN over the wire: every CopyData row must land exactly once` … `\copy {schema}.copyin_t from stdin<NL>1<NL>2<NL>3<NL>\.` |
| `COPY ... FROM STDIN (FORMAT BINARY)` | да | **[вывод]** строки бинарника: `COPY FROM STDIN: invalid PGCOPY signature`, `COPY FROM STDIN: invalid binary value in column ` |
| `read_csv` / `read_parquet` / `read_json` из файла на сервере | да, штатный путь всех демок | **[код]** `examples/demo6/bootstrap.sql`, `tests/.../indexing-external-data.test` |
| `INSERT ... SELECT` внутри базы | да | **[код]** `tests/.../cookbook/sql_features/merge.test`, example_004 |
| `MERGE INTO ... USING (SELECT ...)` внутри базы | да | см. п. 4 |
| appender-API | **нет** по pg-протоколу (это C++/внутренний API) | — |

**Практический вывод:** ни `COPY`, ни appender нам не нужны — при подходе из п. 2/3 строки вообще не
покидают движок, staging-таблица не заполняется извне, а строится как CTE. `COPY FROM STDIN` остаётся
запасным вариантом для случая «эмбеддинги пришли из Python и их надо влить пачкой».

---

## 6. Каталог одним запросом

### 6.1. Состав колонок — да, ОДНИМ вызовом

**[вывод]** `SELECT count(*) FROM duckdb_columns()` → `4002`. Функция уже отдаёт колонки **всех** таблиц
базы; фильтр по `table_name` в нашем коде (`serene_search_build.py:409`) и заставляет вызывать её 233 раза.
Замена: один вызов + группировка в Python (или сразу агрегат в SQL).

### 6.2. Число строк — да, и двумя способами

**(а) Точно, одним запросом [замер] — 0.27 с на все 235 таблиц.**
Генерируем текст запроса в самом движке:
```sql
SELECT string_agg('SELECT ' || quote_literal(table_name) || ' AS t, count(*) AS c FROM '
                  || quote_ident(table_name), ' UNION ALL ')
FROM duckdb_tables() WHERE schema_name='public';
```
**[вывод]** результат — 40 388 байт SQL; его прогон:
```
real    0m0.266s
235 строк, напр.:  catalog_странымира|1
                   catalog_способыотражениязарплатывбухучете|3
```
Против 233 отдельных процессов `psql` сейчас (`serene_search_build.py:405`).

**(б) Приблизительно, мгновенно — `pg_class.reltuples`.**
**[замер]** `SELECT sum(reltuples) FROM pg_class WHERE relkind='r'` → `359806` за **0.069 с**.
**[вывод]** ВАЖНО, оценка неточная: `search_corpus` — `reltuples = 99009`, реальный `count(*) = 97965`.
Для малых справочников совпадает точно (`catalog_видыдоходовндфл` = 120 = 120).
Годится как дешёвый предфильтр «таблица пустая / непустая», НЕ годится как источник истины.

### 6.3. Чего НЕТ

**[вывод]** `duckdb_tables().estimated_size` у нас **пустой (NULL)** по всем таблицам —
счётчика строк оттуда не будет. `index_count` для `search_corpus` = 0, хотя инвертированный индекс есть,
то есть инвертированные индексы в этой колонке не учитываются (искать их надо в `duckdb_indexes()`).
`SUMMARIZE` работает, но это полный проход с профилированием — для «сколько строк» дороже, чем `count(*)`.

---

## 7. Распространение переименования: как выразить «строка + разрешённые имена ссылок»

### 7.1. Динамического джойна по метаданным в движке нет

Ни `EXECUTE`, ни динамического `USING`, ни «джойна по всем таблицам, у которых есть колонка X» в SQL
движка нет. Но он и **не нужен**: 233 разных набора ссылочных колонок сводятся к ОДНОЙ карте имён.

### 7.2. Одна карта `Ref_Key → Description` на всю базу — 141 мс

**[вывод]** генерация текста (в движке, по каталогу):
```sql
SELECT string_agg('SELECT "Ref_Key"::VARCHAR AS k, "Description"::VARCHAR AS nm FROM '
                  || quote_ident(table_name), ' UNION ALL ')
FROM (SELECT table_name FROM duckdb_columns() WHERE schema_name='public' AND column_name='Ref_Key'
      INTERSECT
      SELECT table_name FROM duckdb_columns() WHERE schema_name='public' AND column_name='Description');
```
**[замер]** прогон получившегося (14 903 байта):
```
38515|38515        -- 38 515 пар, все ключи уникальны
Time: 141.436 ms
```

### 7.3. Разрешение ссылок БЕЗ знания, какие колонки ссылочные

Ключевой трюк: `to_json(t)` разворачивается в пары (колонка, значение), и **значение** джойнится с картой
имён. Никакого перечисления колонок, ни на одной из 233 таблиц.

**[вывод]** работает, проверено на `document_реализациятоваровуслуг` (35 ссылочных колонок):
```sql
WITH refmap AS (<запрос из 7.2>),
rows_j AS (SELECT "Ref_Key"::VARCHAR AS row_key, to_json(t) AS jj
           FROM document_реализациятоваровуслуг t),
kv AS (SELECT r.row_key, x.key AS k, trim(x.value::VARCHAR,'"') AS v
       FROM rows_j r, LATERAL (SELECT key, value FROM json_each(r.jj)) x
       WHERE x.key NOT LIKE '%navigationLinkUrl'),
res AS (SELECT kv.row_key, kv.k, COALESCE(m.nm, kv.v) AS val
        FROM kv LEFT JOIN refmap m ON m.k = kv.v AND kv.k LIKE '%\_Key' ESCAPE '\')
SELECT row_key, sha1(string_agg(k || ': ' || val, ' | ' ORDER BY k)) AS doc_hash
FROM res GROUP BY row_key;
```
**[замер]** 790 мс на всю таблицу; диагностика по 50 строкам: `pairs=3564, key_cols=1260, resolved=318` —
то есть 318 из 1260 ссылочных ячеек разрешились в человекочитаемые имена (остальные — нулевые GUID
`00000000-...` и ссылки на таблицы без колонки `Description`).

**Правильность по требованию задачи сохраняется и усиливается:** имя контрагента подставляется джойном
на текущее содержимое справочника, поэтому переименование меняет `doc` в тот же такт — без всякого
отпечатка по «итоговой строке». Отпечаток при этом всё равно считается по итоговому `doc`
(`sha1(string_agg(...))`), то есть контракт «отпечаток по разрешённому тексту» не нарушен.

Синтаксические грабли, на которые я наступил (фиксирую, чтобы не повторяли):
- **[вывод]** `json_each(r.jj)` нельзя писать в `FROM` рядом с `rows_j` — `ERROR: Failed to bind column
  reference "jj"`. Нужен явный `LATERAL (SELECT key, value FROM json_each(r.jj))`.
- **[вывод]** `json_extract_string(v, '$')` на скалярном JSON возвращает **пусто**; снимать кавычки надо
  через `trim(v::VARCHAR, '"')`.
- **[вывод]** `btrim` в сборке **нет**: `ERROR: Scalar Function with name btrim does not exist! Did you
  mean "trim"?`

### 7.4. Весь корпус одним запросом — измерено

Генерация `UNION ALL` по всем таблицам (см. 2.3) даёт 50 540 байт SQL, 233 ветки.

**[замер]** сборка `doc` с разрешёнными ссылками по ВСЕЙ базе:
```
SELECT count(*) AS total, sum(length(doc)) AS bytes FROM fresh;
96931|47302850
Time: 4418.940 ms (00:04.419)
```
**[замер]** то же + `sha1` + анти-джойн с `search_corpus` (== ответ «что пересчитывать»):
```
SELECT count(*) AS changed FROM (SELECT src_table,row_key,sha1(doc) AS h FROM fresh) f
LEFT JOIN search_corpus c ON c.src_table=f.src_table AND c.row_key=f.row_key
WHERE c.doc_hash IS NULL OR c.doc_hash <> f.h;
96931
Time: 4388.003 ms (00:04.388)
```
(`changed = 96931` — потому что формат `doc` в этом эксперименте отличается от нашего продового, значит
отличаются все отпечатки. Замер доказывает пропускную способность конвейера, а не число реальных
изменений. На совпадающем формате `changed` будет реальным.)

Только 141 таблица имеет `Ref_Key`; для остальных (табличные части, регистры) взят
`row_key = sha1(to_json(t)::VARCHAR)` — та же логика, что и в нашем коде
(`serene_search_build.py:710`: `row_id = declared_key or key or hashlib.sha1(doc...)`).

---

## Что надо переделать (по формату «место — сейчас — штатно — выигрыш»)

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:405`
**Сейчас:** `for t in tables: n = int(q('SELECT count(*) FROM "%s"' % t)[0][0])` — 233 процесса `psql`.
**Штатно:** один сгенерированный движком `UNION ALL` (п. 6.2а) либо `pg_class.reltuples` как предфильтр.
**Выигрыш:** 233 процесса → 2; **[замер]** 0.27 с на все 235 таблиц.
**Проверено на инстансе:** да.

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:409`
**Сейчас:** `cols = {t: q("SELECT column_name, data_type FROM duckdb_columns() WHERE table_name=%s ...")}`
— 233 процесса `psql`.
**Штатно:** один вызов `duckdb_columns()` без фильтра по таблице (**[вывод]** 4002 строки на всю базу).
**Выигрыш:** 233 процесса → 1.
**Проверено на инстансе:** да.

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:387-712` (`iter_corpus`, сборка `doc`/`refs` в Python)
**Сейчас:** все 97 965 строк вычитываются в Python через CSV, `doc` и `refs` склеиваются в Python.
**Штатно:** `to_json(t)` + `LATERAL json_each` + `string_agg` + `LEFT JOIN` на карту имён (п. 7.3),
одним запросом на всю базу.
**Выигрыш:** 47 МБ текста не покидают движок; **[замер]** 4.4 с против ~258 с фазы.
**Проверено на инстансе:** да (формат `doc` в замере упрощённый — см. «Что проверить замером»).

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:809`
**Сейчас:** `hashlib.sha1(("%s\x00%s" % (doc, refs)).encode("utf-8")).hexdigest()` в Python.
**Штатно:** `sha1(...)` в SQL — тот же алгоритм, отпечатки совместимы (п. 3).
**Выигрыш:** −1 полный проход по корпусу в Python; **[замер]** 815 мс на 24 тыс. строк вместе со сборкой строки.
**Проверено на инстансе:** да.

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:812-817`
**Сейчас:** `for i in range(0, len(fresh), INS): ddl("INSERT INTO %s VALUES %s;")` — ~490 процессов `psql`.
**Штатно:** staging вообще не нужен — «свежие» отпечатки живут как CTE внутри того же запроса (п. 7.4).
Если staging всё же нужен: `INSERT ... SELECT` внутри базы либо `COPY FROM STDIN` (п. 5).
**Выигрыш:** ~490 процессов → 0.
**Проверено на инстансе:** да (CTE-вариант отработал за 4.4 с).

### МЕСТО: `ubuntu/serenedb/serene_search_build.py:819-822`
**Сейчас:** `LEFT JOIN` staging с корпусом по каждой таблице — 233 процесса `psql`.
**Штатно:** один анти-джойн на всю базу (п. 7.4), либо сразу
`MERGE INTO search_corpus ... RETURNING merge_action, src_table, row_key` (п. 4.3) — тогда и список
изменившихся ключей, и применение изменения делаются одной командой.
**Выигрыш:** 233 процесса → 1; `NOT MATCHED BY SOURCE THEN DELETE` заодно закрывает gone-очистку
(`serene_search_build.py:853`) без отдельного `count(*)`.
**Проверено на инстансе:** да для анти-джойна [замер 4.4 с]; для MERGE — план построен через EXPLAIN,
исполнение не проверялось (запрет на DML).

### Итоговая арифметика такта
| фаза | сейчас | штатно |
|---|---|---|
| счёт строк по таблицам | 233 `psql` | 2 `psql`, 0.27 с |
| состав колонок | 233 `psql` | 1 `psql` |
| чтение + сборка `doc`/`refs` + SHA1 | 97 965 строк в Python, ~258 с | 0 строк в Python, 4.4 с |
| staging | ~490 `psql` | 0 |
| поиск изменившихся | 233 `psql` | 1 `psql` (в том же запросе) |
| **итого** | **~1 190 процессов, ~258 с** | **~4 процесса, ~5 с** |

---

## Что уже штатное и трогать не надо

- `MERGE INTO` для записи корпуса (`serene_search_build.py:729`) — штатный механизм, к цели с
  инвертированным индексом применим (**[код]** `tests/sqllogic/sdb/pg/dml/merge.test:46-57`), и наша
  таблица не `TableEngine::Search`, так что запрет из `duckdb_catalog.cpp:829` нас не касается.
- Инвертированный индекс над **обычной таблицей** (`search_idx ON public.search_corpus`) обновляется
  движком при DML — в отличие от индекса над VIEW. Менять на VIEW ради «свежести» не нужно и вредно.
- Отпечаток по итоговому `doc`+`refs`, а не по сырым колонкам — правильное решение, и в SQL-варианте
  оно сохраняется дословно.

---
---

# Второй проход: что нашлось дополнительно / что опровергнуто

Первый проход шёл от демок (`examples/demo6`) и тестов индекса над VIEW. Второй прошёл с другой стороны:
`examples/demo0..demo5`, тесты DDL/DML/системного каталога вместо индексных, строки бинарника,
`duckdb_keywords()`/`duckdb_settings()` вместо `duckdb_functions()`, и отдельно — вопрос «а можно ли
вообще НЕ читать таблицу, если она не менялась».

## Д1. Главная находка второго прохода: подигест таблицы — 0.9 с на всю базу

Первый проход дал «пересобрать все `doc` и сравнить отпечатки» = 4.4 с. Но при нуле изменений даже это
лишнее: можно спросить у движка **один агрегат на таблицу** и сравнить с сохранённым.

**[вывод]** `bit_and`, `bit_or`, `bit_xor`, `sum` — есть; `checksum` — нет.

**[замер]** посчитать `(count(*), sum(hash(to_json(x)::VARCHAR)::HUGEINT))` по ВСЕМ 233 таблицам
одним запросом (сгенерированным в самом движке по `duckdb_columns()`, 50 798 байт SQL):
```
catalog_кодыдокументовкадровыхмероприятий|136|1123421135981984640831
catalog_рабочиеместа_macадреса|4|47235955433040260566
catalog_операции0|65|585672552324576867753
Time: 917.500 ms
```

Схема такта получается трёхуровневой:

| ситуация | что делаем | цена |
|---|---|---|
| ничего не изменилось | только дайджесты, сравнили, вышли | **0.92 с** |
| изменились N таблиц, ни одна не «именующая» | дайджесты + сборка `doc` только по этим N | 0.92 с + доля от 4.4 с |
| изменилась таблица с колонкой `Description` (переименование!) | дайджесты + полная пересборка `doc` (ссылки могли протухнуть везде) | 0.92 + 4.4 ≈ **5.3 с** |

Третья строка — прямое следствие требования задачи («переименовали контрагента → `doc` документа обязан
измениться»). Дайджест самого документа при переименовании НЕ меняется, поэтому по нему одному решать
нельзя; но «изменилась хоть одна таблица-справочник ⇒ пересобрать `doc` целиком» это закрывает, и стоит
5.3 с вместо 300.

Оговорка про `sum(hash(...))`: агрегат аддитивный и коммутативный, теоретически возможна компенсация
(две строки изменились так, что сумма совпала). Для «свежесть не позднее 20 минут» риск приемлем,
но это **наша** конструкция, а не штатный механизм — помечаю явно (правило 3 владельца).
`bit_xor` для этой роли ХУЖЕ: он обнуляет пары одинаковых значений.

## Д2. `\gexec` — генерация и исполнение в ОДНОМ процессе psql

В первом проходе я написал «два процесса `psql`: сгенерировать текст и прогнать». Это **опровергнуто**:
psql умеет `\gexec`, и сгенерированный SQL исполняется в той же сессии.

**[вывод]**
```
$ cat n1.sql
SELECT 'SELECT count(*) AS n FROM ' || quote_ident(table_name) AS q
FROM duckdb_tables() WHERE schema_name='public' LIMIT 3
\gexec
$ psql "$D" -tAf n1.sql
1
Time: 0.691 ms
3
Time: 0.439 ms
1
Time: 0.480 ms
Time: 6.160 ms
```
Итого весь такт — **один процесс `psql`**, а не два и не 1 190.
(`\gexec` — механизм psql, не движка; но psql у нас и так единственный транспорт.)

## Д3. Триггеры: в бинарнике есть, для НАШИХ таблиц — НЕТ

Это самая заманчивая версия «штатного CDC», и её надо закрыть явно.

**[вывод]** строки бинарника 26.07.3 содержат полноценный триггерный аппарат:
```
CREATE TRIGGER requires a base table
CREATE TRIGGER is only supported for storage versions v2.0.0 and higher.
CREATE TRIGGER requires a base table, not a view or subquery
Triggers are not supported for this table type
FOR EACH ROW trigger "%s" on table "%s" writes to the trigger table (self-referential triggers are not supported)
```
**[вывод]** `SELECT count(*) FROM duckdb_triggers()` → `0` (функция каталога существует).

**[код]** НО в pg-слое SereneDB это зафиксировано как НЕподдерживаемое:
`tests/sqllogic/sdb/pg/site_docs/compatibility/core_sql_claims.test:243-244`
```
# ddl_misc: Triggers
statement error
CREATE TRIGGER ddl_misc_t1 BEFORE INSERT ON ddl_misc_trg FOR EACH ROW EXECUTE FUNCTION ddl_misc_fn();
```
Строка `Triggers are not supported for this table type` — ровно про таблицы движка SereneDB
(триггерный аппарат достался от встроенного DuckDB и работает только в его собственных каталогах
`memory`/`temp`, где наших данных нет: **[вывод]** `duckdb_databases()` → `memory|duckdb`,
`postgres|serenedb`, `system|duckdb`, `temp|duckdb`).

**Вывод: штатного CDC через триггеры у нас нет.** Проверять исполнением не стал — это DDL.

Побочный факт из того же места: **[вывод]** `MERGE INTO is not supported on tables with triggers` —
то есть даже если бы триггеры завелись, они бы отключили MERGE на той же таблице.

## Д4. Материализованных представлений НЕТ — опровергает соблазнительный обходной путь

**[вывод]** `duckdb_keywords()` отдаёт `materialized|unreserved` — но это только про CTE.
**[вывод]** в бинарнике `MATERIALIZED` встречается лишь как `materialized_cte`,
`Referenced materialized CTE does not exist.`, `AS NOT MATERIALIZED (`, и как отображение
`WHEN rel.relkind = 'm' THEN 'materialized view'` в pg-совместимом вью каталога.
**[код]** `grep -rn "CREATE MATERIALIZED" server/ tests/` → **пусто**.

То есть «сделать MATERIALIZED VIEW и REFRESH его» — не вариант, такого механизма нет.
Наша таблица `search_corpus` + `MERGE INTO` и есть ручной эквивалент матвью, и это правильно.

## Д5. `REINDEX` / `ALTER INDEX` не перечитывают источник — подтверждение п.1.3 с другой стороны

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_options.test:48-100` — `ALTER INDEX SET/RESET`
меняет только эксплуатационные опции; **[вывод]** реальный набор из `pg_class.reloptions`:
```
{row_group_size=122880,norm_row_group_size=122880,refresh_interval=1000,compaction_interval=1000,
 cleanup_interval_step=1,segment_memory_max=268435456,segment_docs_max=0,compaction_max_segments=10,
 compaction_max_segments_bytes=5368709120,compaction_floor_segment_bytes=2097152}
```
Здесь есть `refresh_interval=1000` — **и это НЕ перечитывание источника**:
**[код]** `server/catalog/persistence/index.h:48` → `uint32_t refresh_interval_ms = 1000;` →
`server/search/search_table.cpp:115` → `_maint_settings.refresh_interval_msec` — это интервал
видимости уже закоммиченных сегментов iresearch. Название обманчиво, легко принять за то, чего нет.

**[вывод]** `REINDEX` в бинарнике упоминается только в аварийном контексте:
`is out of sync with its store table; refusing to checkpoint (WAL retained for replay; REINDEX to clear)`,
и `unsupported ALTER INDEX action`. Штатного «перестроить индекс над VIEW по источнику» нет —
остаётся `DROP INDEX` + `CREATE INDEX` (п. 1.4).

## Д6. Индекс над VIEW: уточнение области «быстрого пути» (важно для нашей архитектуры)

**[код]** `server/connector/view_fast_path.cpp:82-150` — зарегистрированные источники быстрого пути:
`read_parquet` (+`parquet_scan`), `read_csv` (+`read_csv_auto`), `read_json` (+`read_json_auto`),
`read_json_objects`, `iceberg_scan`; строка 140: `// TODO: read_avro, postgres_scan / postgres_query.`

**[код]** `tests/sqllogic/sdb/pg/index/inverted_index_view_include.test:5-11` — дословно:
```
# Today the fast-path source set is parquet / csv / json / iceberg / rocksdb
# tables (see server/connector/view_fast_path.cpp). Once postgres_scan joins
# that set, this same shape of test should pin the behaviour for a view over
# an ATTACH'd postgres table -- the only thing that changes is the source.
```
Практический смысл для нас (архитектура «PG на Windows + attach»): **VIEW над ATTACH-нутым Postgres
в быстрый путь НЕ входит**, значит всё, что нужно вернуть или агрегировать, обязано быть в `INCLUDE`.
Это ровно то, что уже записано в `docs/SERENEDB.md:209-217` — второй проход это подтверждает по коду,
а не по замеру.

**[код]** `FLOAT[N]` как `INCLUDE`-колонка — поддерживается:
`tests/sqllogic/sdb/pg/index/inverted_index_merge_include.test:26-30`
(`CREATE TABLE arr_c (pk INTEGER PRIMARY KEY, body VARCHAR, vec FLOAT[3])` +
`CREATE INDEX arr_c_idx ON arr_c USING inverted(pk, body en) INCLUDE (vec)`),
`inverted_index_array_nulls.test:32-33`. На **таблице** — да; на VIEW с `FLOAT[1536]` — не проверено.

## Д7. `ai_embed` прямо в `INSERT ... SELECT` — механизм есть, но наша размерность его блокирует

**[код]** `examples/demo5/bootstrap.sql:5-37` — полный штатный путь:
```sql
CREATE SECRET gemini (TYPE openai, api_key 'API_KEY',
   base_url 'https://generativelanguage.googleapis.com',
   embeddings_path '/v1beta/openai/embeddings');
INSERT INTO arxiv
SELECT id, title, abstract, authors, published_date,
       ai_embed(abstract, 'gemini-embedding-001', 'gemini')::FLOAT[3072] AS embedding
FROM ( ... read_parquet(...) ... ) src;
```
**[вывод]** в нашей сборке функция есть: `ai_embed|{col0,col1,col2}|{VARCHAR,VARCHAR,VARCHAR}` —
ровно три VARCHAR-аргумента, параметра `dimensions` НЕТ.
Это подтверждает уже записанное в `docs/SERENEDB.md:117,180`: наш провайдер отдаёт 1024, индекс на 1536,
и без `dimensions` подменить нечем. **Для текущего такта `ai_embed` не годится**; менять размерность —
отдельное решение под новый индекс, не в рамках этой задачи.

Что при этом всё равно верно: если бы эмбеддинг считался в SQL, весь такт стал бы одним запросом
без единого выхода в Python. Это стоит держать как цель на смену размерности.

## Д8. `demo2` подтверждает: корпус-как-ТАБЛИЦА — правильная форма, не менять

**[код]** `examples/demo2/README.md`:
```
- **Production storage.** Durable across restarts, supports `INSERT` / `UPDATE` / `DELETE`
  (the index updates transactionally with the table), recoverable via WAL -- the inverted index
  is just another secondary index.
```
Это прямое противопоставление индексу над VIEW из demo0/demo1 (там VIEW над parquet — снимок).
Наш `search_idx ON public.search_corpus` = форма demo2, и она единственная даёт «индекс сам догоняет
изменения». Соблазн «переписать корпус на VIEW и не пересобирать» **опровергнут**: пересобирать всё
равно пришлось бы, только уже сам индекс, каждый такт.

## Д9. `sha1` в SQL побайтово совпадает с `hashlib.sha1` на кириллице — переход без переиндексации

Первый проход это предположил; второй — проверил.

**[вывод]**
```
$ psql "$D" -tAc "SELECT sha1('Контрагент: ООО Ромашка | Сумма: 100')"
21a373c088fa55aff8c340c389c72a76014fb7aa
$ python3 -c "import hashlib;print(hashlib.sha1('Контрагент: ООО Ромашка | Сумма: 100'.encode()).hexdigest())"
21a373c088fa55aff8c340c389c72a76014fb7aa
```
Значит перенос вычисления `doc_hash` из Python в SQL **не требует разового пересчёта всего корпуса** —
при условии, что строка `doc` собирается побайтово так же (см. риск в «Что проверить замером»).

## Д10. Что во втором проходе НЕ подтвердилось / уточнено против первого

1. **«Нужно два процесса psql (генерация + прогон)»** — неверно, `\gexec` делает это одним (Д2).
2. **«`estimated_size` в `duckdb_tables()` даст размер»** — подтверждено, что NULL, но во втором проходе
   нашёлся лучший заменитель для «менялось ли»: не число строк, а дайджест (Д1). Число строк вообще
   плохой детектор — правка поля не меняет `count(*)`.
3. **«`reltuples` можно использовать как счётчик»** — усиливаю предупреждение: `search_corpus`
   `reltuples=99009` при реальных `97965`, расхождение 1 %. Только как предфильтр «пусто/непусто».
4. **Триггеры** — в первом проходе я их не проверял вовсе; во втором проверил и закрыл: нет (Д3).
5. **Матвью** — не проверял в первом проходе; во втором закрыл: нет (Д4).
6. **`refresh_interval`** — опасная ложная зацепка, которая при беглом чтении `reloptions` выглядит как
   «индекс сам обновляется раз в секунду». Это не так (Д5).

---

# Что я НЕ смог выяснить

1. **Реальное число изменившихся строк за такт.** Все мои замеры дали `changed = 96931`, потому что
   формат `doc` в эксперименте (`ключ: значение` по всем полям JSON, сортировка по имени колонки)
   отличается от продового (`serene_search_build.py:640-712`: отбрасывание машинных токенов,
   `TEXT_CLIP`, отдельные `amount`/`doc_date`, порядок колонок из каталога). Пока формат не воспроизведён
   побайтово, число «сколько на самом деле меняется за 20 минут» я не измерил.
2. **Исполнение `MERGE ... RETURNING merge_action` на нашей базе.** План строится (EXPLAIN приведён),
   но сам MERGE — DML, запрещён в этой сессии. Не проверено: сколько строк реально вернёт `RETURNING`
   при большой USING-выборке и не окажется ли это узким местом.
3. **`FLOAT[1536]` как `INCLUDE`-колонка индекса над VIEW.** На таблице `FLOAT[3]` покрыт тестами;
   на VIEW и на 1536 измерениях — нет ни теста, ни замера. Требует `CREATE INDEX` — запрещено.
4. **Стоимость `DROP INDEX`+`CREATE INDEX` на НАШИХ 98 тыс. строк.** Есть наш прошлый замер
   0.4–0.5 с на 50 тыс. (`docs/SERENEDB.md:256`), но он на другом наборе колонок и без вектора.
   Требует DDL — запрещено.
5. **Поведение при параллельном чтении во время пересборки.** `online_create_index_concurrent_dml.test`
   говорит, что билд асинхронный и согласованный, но что видит `SELECT ... FROM search_idx` в момент
   между `DROP` и завершением `CREATE` — из тестов не следует, а проверить нельзя (DDL).
6. **Верхняя граница длины SQL-текста.** 50 798 байт и 233 ветки `UNION ALL` прошли; где предел
   (и есть ли деградация планировщика на 1000+ ветках на базе клиента «в разы крупнее») — не выяснял.
7. **Стабильность `sum(hash(...))` как дайджеста** — теоретически компенсируемый агрегат; частота
   ложных «не изменилось» не оценивалась.
8. **Полнота карты имён.** `refmap` покрывает 141 таблицу с парой `Ref_Key`+`Description`
   (38 515 значений). Сколько ссылок в наших документах указывает на таблицы БЕЗ `Description`
   (и как их именует текущий питоновский код) — не сверял; в замере разрешилось 318 из 1260
   ссылочных ячеек, остальное — нулевые GUID и такие таблицы.

---

# Что проверить замером

Без `CREATE INDEX` (можно делать сейчас):

1. **Воспроизвести продовый формат `doc` в SQL и сверить отпечатки построчно.** Это главный
   блокирующий замер: пока он не сойдётся, переход требует разовой полной переиндексации.
   ```sql
   -- сравнить SQL-сборку с тем, что уже лежит в корпусе
   WITH refmap AS (<7.2>), rows_j AS (<2.3>),
   kv AS (SELECT r.src_table, r.row_key, x.key AS k, trim(x.value::VARCHAR,'"') AS v
          FROM rows_j r, LATERAL (SELECT key, value FROM json_each(r.jj)) x),
   res AS (SELECT kv.*, COALESCE(m.nm, kv.v) AS val
           FROM kv LEFT JOIN refmap m ON m.k = kv.v AND kv.k LIKE '%\_Key' ESCAPE '\'),
   fresh AS (SELECT src_table, row_key, string_agg(k||': '||val,' | ' ORDER BY k) AS doc
             FROM res GROUP BY src_table, row_key)
   SELECT count(*) FILTER (WHERE c.doc = f.doc) AS same,
          count(*) FILTER (WHERE c.doc <> f.doc) AS diff
   FROM fresh f JOIN search_corpus c USING (src_table, row_key);
   ```
2. **Реальное число изменений за 20 минут.** Снять дайджесты (Д1), подождать такт, снять снова,
   сравнить: сколько таблиц и сколько строк реально двигается. Это цифра, от которой зависит,
   нужен ли вообще уровень «дайджест» или хватает 4.4 с.
3. **Покрытие карты имён.** Сколько ссылочных колонок указывает на таблицы без `Description`:
   ```sql
   SELECT count(*) AS unresolved FROM (<kv из п.1>) kv
   LEFT JOIN (<refmap>) m ON m.k = kv.v
   WHERE kv.k LIKE '%\_Key' ESCAPE '\' AND m.nm IS NULL
     AND kv.v <> '00000000-0000-0000-0000-000000000000';
   ```
4. **Стоимость дайджеста при росте базы.** Тот же запрос Д1 на копии витрины кратного размера —
   линеен ли он.
5. **EXPLAIN ANALYZE большого запроса** (это чтение, DML нет) — где реально уходит время:
   `json_each` или `LEFT JOIN refmap`. Если в `json_each`, имеет смысл строить `doc` только по
   изменившимся таблицам (Д1), а не по всей базе.

Требует `CREATE INDEX` / DDL — **у нас запрещено**, выносить отдельным согласованным окном:

6. `DROP INDEX search_idx; CREATE INDEX search_idx ON search_corpus USING inverted(...)` — замерить
   время на 98 тыс. строк с нашим набором колонок (закрывает пункт 4 «не выяснил»).
7. `CREATE INDEX ... ON <view> USING inverted(...) INCLUDE (emb)` с `FLOAT[1536]` — проверить,
   принимается ли вообще (пункт 3 «не выяснил»). **Опклассы `ivf`/`hnsw` не трогать** — `ivf` роняет
   инстанс (`memory: project-serenedb-ivf-blocked`), `hnsw` в сборке 26.07.3 отсутствует.
8. `MERGE INTO search_corpus ... WHEN NOT MATCHED BY SOURCE THEN DELETE RETURNING merge_action,
   src_table, row_key` — исполнить на копии корпуса и убедиться, что gone-очистка
   (`serene_search_build.py:853`) закрывается той же командой.
9. `CREATE TRIGGER` на таблице витрины — формально закрыть Д3 исполнением (ожидаемый результат:
   ошибка, как в `core_sql_claims.test:243`).
