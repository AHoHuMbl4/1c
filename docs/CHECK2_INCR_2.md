# CHECK2_INCR_2 — штатные механизмы SereneDB под инкрементальную пересборку корпуса

Источники: клон `/srv/data/cursor/cursor/1/serenedb-src` (ветка main) и живой движок
**26.07.3** (`/opt/serenedb-dist/serenedb-26.07.3-linux-amd64/usr/bin/serened`,
DSN `host=127.0.0.1 port=7890 user=postgres dbname=postgres`, доступ по ssh на 192.168.56.42).
На живом движке выполнялись ТОЛЬКО `SELECT` / `SUMMARIZE` / `COPY … TO STDOUT` /
каталожные функции. Ни одной DDL/DML-команды, ни одного `CREATE INDEX`.

Пометки: **[код]** — файл:строка в репозитории, **[вывод]** — вывод команды с живого
движка, **[замер]** — время, снятое на живом движке.

---

## Первый проход

### 1. Инвертированный индекс поверх VIEW — есть, но он СТАТИЧЕСКИЙ

**Поддерживается — да, это штатный, документированный шаблон.**

[код] `examples/demo6/bootstrap.sql:71-116` — вся демка построена на индексах над
представлениями, включая `UNION ALL` двух источников:

```sql
CREATE VIEW tasks_cf_v AS SELECT id, title, ... FROM read_parquet('hf://…');
CREATE VIEW tasks_cc_v AS SELECT 'cc/' || row_number() OVER () AS id, ... FROM read_parquet('hf://…');
CREATE VIEW tasks_v AS SELECT * FROM tasks_cf_v UNION ALL SELECT * FROM tasks_cc_v;

CREATE INDEX tasks_idx ON tasks_v
USING inverted(id, rating, title cf_en, statement cf_en, editorial cf_en, tags cf_en)
INCLUDE (id, contest_name, rating, title, statement, editorial, tags);
```

[код] `tests/sqllogic/sdb/pg/site_docs/cookbook/search/indexing-views.test:18-31` — тот же
шаблон над **нативной таблицей**, это документированный рецепт (DOCS_TEST):

```sql
CREATE TABLE docs (id INTEGER PRIMARY KEY, body VARCHAR, category VARCHAR);
CREATE VIEW v_docs AS SELECT id, body, category FROM docs;
CREATE INDEX v_docs_idx ON v_docs USING inverted (id, body en, category);
```
и дальше запросы идут **от имени индекса**: `FROM v_docs_idx WHERE body @@ 'quick'`
(строки 37-41), `GROUP BY category` из индекса (строки 52-56), и даже вьюха поверх
индекса — `CREATE VIEW recent_hits AS SELECT … FROM v_docs_idx WHERE body @@ 'quick'`
(строка 67).

**Ограничение 1: только инвертированный.**
[код] `server/connector/duckdb_catalog.cpp:1065-1069`:
```
if (view_backed && create_index_info->index_type == "secondary") {
  THROW_SQL_ERROR(... "plain indexes on views are not supported; use an inverted index instead");
}
```
зафиксировано тестом `tests/sqllogic/sdb/pg/index/secondary_index_view.test:26`.

**Ограничение 2 (главное): индекс над вьюхой — СНИМОК на момент `CREATE INDEX`.
Изменения базовых таблиц в него НЕ попадают, ни сами, ни через `VACUUM`.**

[код] `server/connector/duckdb_catalog.cpp:874`:
```
// View-backed indexes are STATIC -- captured at CREATE INDEX, no DML refresh.
```
[код] `server/search/wal_recovery.cpp:112-119`:
```
// View-backed indexes are static -- the view body doesn't change at
// runtime, so the persisted index is already current.
```
[код] Это прямо закреплено тестом-«гвоздём»
`tests/sqllogic/sdb/pg/index/inverted_index_view_include.test:189-207`:
```
# 4. View-backed indexes are STATIC (captured at CREATE INDEX time, no DML
# refresh). New rows in the base table after CREATE INDEX are NOT visible
# through the view-backed index. This is the documented behaviour today;
# pinning it so it doesn't silently change.
statement ok
INSERT INTO inc_base VALUES (5, 'pudge surfaces fifth', MAP {'kills': 9}, 'e');
# After-insert read still returns only the rows captured at index creation.
query
SELECT pk, attrs FROM inc_base_idx WHERE body @@ ts_phrase('pudge') ORDER BY pk;
----
pk	attrs
1	{"(kills,7)","(deaths,2)"}
3	{"(kills,3)","(deaths,5)"}
```

**`VACUUM (REFRESH_*)` это не чинит.** Полный список глаголов —
[код] `server/connector/duckdb_vacuum_function.cpp:69-84`: `refresh_database`,
`refresh_schema`, `refresh_table`, `refresh_index`, `refresh_all`, `compact_*`,
`recompute_stats_*`. Что делает `Refresh` — [код] то же файл, `DispatchInverted`
(строки ~300-420) вызывает `inverted.Refresh()`, то есть **публикует уже записанные в
индекс изменения** (делает их видимыми читателям), а не перечитывает источник. Обход
целей идёт по `snapshot.GetTables(...)` → `CollectInvertedSteps(..., table, ...)`
([код] строки 264-290, 302-312) — то есть **по ТАБЛИЦАМ**; индекс над вьюхой в обход
`REFRESH_TABLE`/`REFRESH_SCHEMA`/`REFRESH_ALL` вообще не попадает, а `REFRESH_INDEX`
позовёт `Refresh()`, который источник не читает.

**Вывод по вопросу 1: путь «корпус = VIEW-джойн витрины, индекс над вьюхой» НЕ даёт
автоматической свежести.** Единственный способ подтянуть новые данные — `DROP INDEX` +
`CREATE INDEX`, то есть полная пересборка индекса каждый такт: ровно то, от чего мы
уходили (единственный элемент такта, растущий с размером всей базы, а не с числом
изменений). Плюс в этой схеме негде хранить эмбеддинг: он считается снаружи, а вьюха
его не породит (см. п. «ai_embed» ниже — функция есть, но это вызов в облако на каждую
строку при каждой пересборке индекса).

Что при этом ПОДТВЕРЖДЕНО как рабочее и годится нам иначе (см. второй проход и раздел
«Что переделать»): вьюха над **нативной** таблицей — законный источник (fast path),
[код] `server/connector/view_fast_path.cpp:308-330`, ветка `cat_type == "serenedb"`:
«The table's rows live in the hidden store table; views over it ride the same
rowid-keyed machinery as views over attached databases».

Важное ограничение fast-path: чтобы читать из индекса колонки, которые НЕ проиндексированы
и НЕ в `INCLUDE`, тело вьюхи должно быть простым `SELECT * FROM <reader>(literal_args)`;
иначе — ошибка [код] `tests/sqllogic/sdb/pg/index/inverted_index_store_pk.test:82`:
`materialising real columns from this view-backed inverted index is not yet supported --
view body must be a simple SELECT * FROM <reader>(literal_args) over a recognised
fast-path source (read_parquet/csv/json/...)`. Для вьюхи-джойна это значит: **все**
нужные колонки обязаны быть в `INCLUDE`.

### 2. Сборка строки «Колонка: значение | …» прямо в SQL — ДА, и без перечисления колонок

`concat_ws(' | ', COLUMNS(*))` **не подходит**: `COLUMNS(*)` размножает функцию по
колонкам, а не склеивает их.
[вывод] `SELECT concat_ws(' | ', COLUMNS(*)) FROM catalog_странымира LIMIT 1` вернул
14 отдельных колонок, а не одну строку.
[вывод] `SELECT concat_ws(' | ', *) …` → `ERROR: STAR expression is only allowed as the
root element of an expression. Use COLUMNS(*) instead.`

**Рабочий штатный приём — через JSON-представление строки. Список колонок берётся из
самих данных, в SQL не пишется ни одно имя:**

[вывод] выполнено на живом движке:
```sql
SELECT array_to_string(
         list_transform(json_keys(j), k -> k || ': ' || coalesce(json_extract_string(j, k), '')),
         ' | ')
FROM (SELECT to_json(t) AS j FROM catalog_странымира t LIMIT 1) s;
```
→
```
Ref_Key: d99f7eb1-7320-11ec-95fd-0242ac120003 | DataVersion: AAAAAQAAAAA= | DeletionMark: false | Code: 643 | Description: РОССИЯ | НаименованиеПолное: Российская Федерация | КодАльфа2: RU | КодАльфа3: RUS | УчастникЕАЭС: true | МеждународноеНаименование: The Russian Federation | ОтредактированныеПредопределенныеРеквизиты:  | ДополнительныеРеквизиты: [] | Predefined: true | PredefinedDataName: Россия
```
Это **дословно наш формат `doc`**. Отбор/исключение колонок делается `list_filter` по
именам ключей (`STANDARD_SERVICE_PROPS`, `*_Type`, `*_navigationLinkUrl`,
`*_Base64Data`) — тоже без перечисления колонок в SQL.

Вариант «строкой-парами» (нужен, когда надо ДЖОЙНИТЬ значения — резолвинг ссылок):
[вывод] `unnest(...) WITH ORDINALITY` работает:
```sql
WITH r AS (SELECT rowid AS rid, to_json(t) AS j FROM document_приходныйкассовыйордер t),
     kv AS (SELECT rid, u.k, u.i, json_extract_string(j, u.k) AS v
            FROM r, unnest(json_keys(j)) WITH ORDINALITY AS u(k, i))
SELECT rid, count(*) FROM kv GROUP BY rid;  ->  0|59  1|59  2|59
```

Также доступны: `to_json(t)`, `row_to_json`, `struct_keys(t)`, `struct_pack`,
`json_group_array`, `string_agg`/`group_concat`, `array_to_string`, `list_transform`,
`list_filter`, `COLUMNS('regex')` ([вывод] `SELECT COLUMNS('Наимен.*') FROM
catalog_странымира LIMIT 1` → 2 колонки).
Чего НЕТ: `struct_values(t)::VARCHAR[]` падает —
[вывод] `ERROR: Unimplemented type for cast (STRUCT(...) -> VARCHAR[])`.

**Один запрос на таблицу — да. Один запрос на ВСЮ базу — только с генерацией текста
UNION ALL**, потому что имя таблицы обязано быть литералом:
[вывод] `SELECT … FROM duckdb_tables() t, LATERAL query_table(t.table_name)` →
`ERROR: Table function "query_table" does not support lateral join column parameters …
The function only supports literals as parameters.`
Но **саму генерацию делает движок**, а не Python: `string_agg` по `duckdb_tables()`
собирает текст запроса (см. замер ниже). То есть Python остаётся «прокинуть строку»,
а не обходить таблицы.

### 3. Отпечаток в SQL — ДА, sha1 совпадает с нашим Python

[вывод] на живом движке:
```
SELECT sha1('abc'), md5('abc'), hash('abc'), sha256('abc');
a9993e364706816aba3e25717850c26c9cd0d89d|900150983cd24fb0d6963f7d28e17f72|1924864467101078684|ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```
`a9993e36…` — это ровно `hashlib.sha1(b"abc").hexdigest()`, то есть **переход на
SQL-отпечаток не инвалидирует уже сохранённые `doc_hash`**, если строка `doc` собирается
байт-в-байт так же.

Полный список хеш-функций сборки [вывод]:
`hash`, `md5`, `md5_number`, `md5_number_lower`, `md5_number_upper`, `sha1`, `sha256`.
(`xxhash`/`crc32`/`digest` — нет.)

[вывод] отпечаток по СОБРАННОЙ строке целиком в SQL, с резолвингом ссылок:
```sql
WITH r AS (SELECT rowid AS rid, to_json(t) AS j FROM document_приходныйкассовыйордер t),
     kv AS (SELECT rid, u.k, u.i, json_extract_string(j, u.k) AS v
            FROM r, unnest(json_keys(j)) WITH ORDINALITY AS u(k, i)),
     m AS (SELECT Ref_Key AS g, Description AS nm FROM catalog_контрагенты
           UNION ALL SELECT Ref_Key, Description FROM catalog_организации)
SELECT rid, sha1(string_agg(kv.k || ': ' || coalesce(m.nm, kv.v), ' | ' ORDER BY kv.i)) AS h
FROM kv LEFT JOIN m ON m.g = kv.v
WHERE kv.v IS NOT NULL AND kv.v <> '' GROUP BY rid ORDER BY rid LIMIT 3;
->
0|269ed5e98ab843b010ffc4168fafc7bdf2adac2b
1|8f02c443f393429d966c1181ce8ab60dfa9e7a6d
2|208eee886014dfc404742576c6af0549797fe379
```
**Свойство «отпечаток по разрешённым именам ссылок» сохранено**: имя контрагента
приходит из `LEFT JOIN` карты ссылок, поэтому переименование в справочнике меняет
отпечаток строки документа — ровно как в нынешнем Python-коде.

**[замер] то же самое по ВСЕЙ базе, одним запросом.** Сгенерировано движком
(`string_agg` по `duckdb_tables()` и по `duckdb_columns()`), 124 КБ текста, 233 ветки
UNION ALL, карта ссылок — UNION ALL всех таблиц, где есть и `Ref_Key`, и `Description`:

| что | время |
|---|---|
| выгрузить 97 965 отпечатков клиенту (`psql -tA -f fp.sql > файл`) | **20.4 с** |
| посчитать те же отпечатки, не отдавая наружу (`SELECT count(*), count(DISTINCT h) FROM (…)`) | **18.1 с**, результат `97965 \| 97651` |

Сейчас на эту работу (чтение всех строк в Python + сборка `doc` + SHA1 + вставка
отпечатков + LEFT JOIN) уходит **86 % пятиминутного такта ≈ 258 с**.
Замена: **18 с внутри базы**, ноль строк через Python. Это ~14×.

### 4. Обнаружение изменений — штатного CDC НЕТ, штатный `MERGE … RETURNING merge_action` ЕСТЬ

**Чего нет.** Ни журнала изменений, ни changefeed, ни системной колонки версии строки
(в тестах `xmin`/`xact` встречаются только как поля PG-совместимых системных вьюх —
`pg_stat_activity`, `pg_replication_slots`, `pg_index.indcheckxmin`,
[код] `tests/sqllogic/any/pg/system/check_columns.test:148,718`). Поиска по «cdc /
change data capture / changefeed / row version» в `tests/sqllogic` — ноль совпадений.

**Что есть.**

1. `rowid` — стабилен при in-place UPDATE.
   [код] `tests/sqllogic/sdb/pg/dml/merge_returning_rowid.test:1-34`: «the merge update
   … preserve rowid, exactly like a plain UPDATE … RETURNING», «Matched UPDATE of a
   non-PK column with RETURNING: in-place, rowid unchanged».
   Это значит: `rowid` **нельзя** использовать как детектор изменений (он не меняется),
   но **можно** как дешёвый стабильный ключ строки-источника.

2. `MERGE … RETURNING merge_action, *` — движок сам говорит, что он сделал с каждой
   строкой. [код] `tests/sqllogic/sdb/pg/site_docs/sql/statements/merge_into/index.test:108-145`:
   ```sql
   MERGE INTO people USING (…) AS upserts USING (id)
     WHEN MATCHED AND people.salary < 100_000.0 THEN UPDATE SET salary = upserts.salary
     WHEN MATCHED AND people.salary > 100_000.0 THEN DELETE
     WHEN NOT MATCHED THEN INSERT BY NAME
     RETURNING merge_action, *;
   ----
   merge_action	id	name	salary
   UPDATE	3	Sarah	89000
   DELETE	1	John	105000
   ```
   и `WHEN NOT MATCHED BY SOURCE THEN DELETE` с `RETURNING merge_action, *` (строки
   137-145) — это ровно наша «gone-очистка», встроенная в тот же оператор.
   [код] `tests/sqllogic/sdb/pg/site_docs/cookbook/sql_features/merge.test:55-78` — SCD2-рецепт
   с условием «поменялось» прямо в `WHEN MATCHED AND (target.x <> source.x OR …)`.

   **Ответ на «что именно возвращает `merge_action`»:** текстовый ярлык действия —
   `INSERT` / `UPDATE` / `DELETE` — и вместе с ним ЛЮБЫЕ колонки (`*`, `source.*`,
   `target.*`), то есть **список затронутых ключей получается прямо из оператора**,
   без второго запроса и без staging-таблицы.

   [вывод] В сборке 26.07.3 это есть: в бинарнике
   `/opt/serenedb-dist/serenedb-26.07.3-linux-amd64/usr/bin/serened` присутствуют строки
   `Unsupported merge action for RETURNING`, `MergeActionType`, `MergeActionCondition`,
   `WHEN NOT MATCHED BY SOURCE`, `Did you mean to use WHEN MATCHED or WHEN NOT MATCHED BY SOURCE?`.
   (Выполнить MERGE на живом движке я не мог — это запись.)

   Ограничение, которое надо знать: [вывод] в бинарнике есть
   `RETURNING is not implemented for Postgres yet` — то есть для ATTACH'нутых
   postgres-таблиц RETURNING не работает. Наш корпус нативный, нас это не касается.

### 5. Массовая вставка — 490 psql-INSERT не нужны вовсе

Штатные пути, доступные через обычное соединение по протоколу Postgres:

* **`CREATE TABLE … AS SELECT` / `INSERT … SELECT` целиком внутри базы** — для нашей
  задачи это ПОЛНАЯ замена: отпечатки считаются в базе (п. 3), значит их не надо ни
  выгружать, ни вставлять. 490 процессов → 0.
* **`MERGE INTO … USING (<подзапрос>)`** — источником MERGE может быть подзапрос
  ([код] `merge_into/index.test:109-114` — `USING (SELECT unnest([…]) …)`), то есть и
  сравнение, и вставка, и удаление делаются одной командой.
* **`COPY … FROM STDIN`** — есть в протоколе: [вывод] в бинарнике
  `unexpected EOF during COPY from stdin`, `COPY FROM STDIN: invalid PGCOPY signature`,
  `COPY FROM STDIN: invalid binary value in column`, `COPY FROM STDIN: received copy
  data after EOF marker`, `unexpected message during COPY from stdin` — поддержаны и
  текстовый, и бинарный (PGCOPY) форматы.
  Обратное направление проверено вживую: [вывод] `COPY (SELECT 1 AS a, 'x' AS b) TO
  STDOUT (FORMAT CSV, HEADER)` → `a,b` / `1,x`.
* **`read_csv` / `read_parquet` / `read_text`** — [вывод] есть в
  `duckdb_functions()`; годятся для загрузки из файла, подготовленного на стороне сервера.
* Тест `tests/sqllogic/sdb/pg/dml/copy_inverted_index.test` отдельно покрывает COPY в
  таблицу с инвертированным индексом.

Appender-API через PG-протокол недоступен (это C-API DuckDB), и он не нужен.

### 6. Каталог одним запросом — ДА, и счёт строк тоже

* **Состав колонок всех таблиц — один запрос.**
  [замер] `SELECT table_name, column_name, data_type FROM duckdb_columns()
  ORDER BY table_name, column_index` → 4002 строки, **0.041 с**.
  Сейчас: 233 отдельных вызова `duckdb_columns()` по одной таблице.
* **Число строк.** `duckdb_tables().estimated_size` **пустое** —
  [вывод] для `catalog_странымира` поле `estimated_size` пришло NULL. Зато полезен
  столбец `sql` — полный DDL с типами.
* **Точный счёт по всем таблицам одним сгенерированным запросом:**
  [замер] текст запроса собран самим движком
  (`SELECT string_agg('SELECT ''…'' AS t, count(*) AS n FROM "…"', E'\nUNION ALL\n')
  FROM duckdb_tables()`, 40 КБ), выполнение — **0.257 с** на 235 таблиц.
  Для сравнения [замер]: те же 235 `count(*)` отдельными процессами `psql` — **11.9 с**
  (≈50 мс на процесс). Выигрыш **46×**.
* **Оценка без сканирования — `pg_class.reltuples`, и на нашей витрине она ТОЧНАЯ.**
  [замер] `SELECT count(*) FROM pg_class …` — **0.089 с**.
  [вывод] сверка со всеми точными счётчиками: `всего=235, совпало=232, разошлось=3`.
  Разошлись ровно те, куда пишут: `search_meta` (1 против 2), `search_corpus`
  (97 965 против 99 009 — «мёртвые» строки после MERGE не вычтены) и `search_idx` (-1,
  это индекс). **Все 233 таблицы витрины (только чтение) сошлись точно.**
  Для задачи «пропустить пустые таблицы» этого достаточно, и это один запрос за 0.09 с.
* `SUMMARIZE SELECT * FROM <t>` работает [вывод], даёт count/min/max/approx_unique/
  null_percentage по каждой колонке, но это ОДИН оператор на таблицу и он сканирует —
  как замена 233 вызовам не годится, зато отлично заменяет наш `profile_table`
  (count DISTINCT + max(abs) + образцы) там, где он нужен.

### 7. Распространение переименования через VIEW — штатного динамического джойна нет

Ссылочная колонка → `Ref_Key` чужой таблицы, у каждой из 233 таблиц свой набор таких
колонок. Штатного средства «джойни по всем GUID-колонкам» в движке нет:

* имя таблицы и имя колонки в SQL — только литералы;
  [вывод] `query_table` с колонкой в LATERAL → `ERROR: Table function "query_table" does
  not support lateral join column parameters … The function only supports literals as
  parameters`;
* `query('…')` и `query_table('…')` [вывод] существуют и работают с константой
  (`SELECT * FROM query('SELECT 42 AS x')` → `42`), но
  [вывод] `SELECT * FROM query((SELECT '…'))` → `ERROR: Table function cannot contain
  subqueries`.

**Но динамический джойн и не нужен**, если резолвить не «колонка → таблица», а
«значение-GUID → карта имён», как это и сделано у нас в Python. В SQL это выражается
ОДНОЙ обобщённой формой, одинаковой для любой таблицы (проверено выше, п. 3):
развернуть строку в пары `(ключ, значение)` через `to_json` + `unnest(json_keys(…))
WITH ORDINALITY`, сделать `LEFT JOIN` с картой `(Ref_Key → Description)` **по значению**,
и склеить обратно `string_agg(… ORDER BY i)`. Тогда:

* переименование в справочнике меняет `doc` документа — свойство сохранено;
* никакого перечисления ссылочных колонок: GUID «сам себя находит» в карте;
* меняется только имя таблицы в шаблоне → генерация текста нужна, но её делает
  движок (`string_agg` по каталогу), а не Python.

Карта ссылок строится одним сгенерированным UNION ALL:
[вывод] запрос-генератор (выполнялся на живом движке, 12.9 КБ текста)
```sql
SELECT string_agg('SELECT "Ref_Key" AS g, "Description" AS nm FROM "'||table_name||'"',
                  E'\nUNION ALL\n')
FROM (SELECT table_name FROM duckdb_columns() WHERE database_name='postgres'
      GROUP BY table_name
      HAVING bool_or(column_name='Ref_Key') AND bool_or(column_name='Description')) s;
```
(в бою в `HAVING` надо добавить условие «объявленный ключ = ровно `Ref_Key`», иначе в
карту полезут табличные части — тот же дефект, что уже ловили в Python-коде.)

### Итог первого прохода: во что превращается такт

| фаза сейчас | процессов psql | штатная замена | замер |
|---|---|---|---|
| `count(*)` по 233 таблицам | 233 | `pg_class.reltuples` одним запросом | 11.9 с → **0.089 с** |
| `duckdb_columns()` по 233 таблицам | 233 | один `SELECT … FROM duckdb_columns()` | ≈12 с → **0.041 с** |
| чтение 97 965 строк в Python + сборка `doc`/`refs` + SHA1 | ~233 | один сгенерированный UNION ALL с `to_json`+`unnest`+`LEFT JOIN`+`sha1` | **18.1 с** внутри базы |
| вставка 97 965 отпечатков по 200 | ~490 | не нужна: `CREATE TABLE … AS SELECT` / прямой `MERGE … USING (<запрос>)` | **0** |
| `LEFT JOIN` staging↔корпус по таблицам | 233 | `MERGE … RETURNING merge_action, *` — список изменённых ключей отдаёт сам оператор | **0** доп. запросов |
| **итого** | **~1190** | | **≈2** |

Свойство «отпечаток по разрешённым именам ссылок» при этом сохраняется полностью:
резолвинг делается `LEFT JOIN`-ом внутри того же запроса, до `sha1`.

---

## Второй проход: что нашлось дополнительно / что опровергнуто

Второй заход шёл с другой стороны: не от демок, а от исходников (`server/connector/*`,
`server/catalog/*`) и от тех разделов тестов, которые в первом проходе не открывались
(`sdb/pg/simple/`, `sdb/pg/es/`, `sdb/pg/site_docs/cookbook/search/computed-values`,
`sdb/pg/index/inverted_index_expr*`), плюс проверка найденного через `strings` бинарника
26.07.3 и через системные вьюхи PG-совместимости.

### 2.1 Опровергнуто / уточнено из первого прохода

* **Ничего из первого прохода не отменено.** Статичность индекса над вьюхой
  подтвердилась третьим независимым свидетельством: обход целей `VACUUM` идёт по
  таблицам ([код] `server/connector/duckdb_vacuum_function.cpp:264-290`), а сам
  `Refresh()` источник не перечитывает.
* **Уточнение к «нет CDC».** `pg_stat_user_tables` в сборке ЕСТЬ, но это заглушка:
  [вывод] `SELECT relname,n_tup_ins,n_tup_upd,n_tup_del,n_live_tup FROM
  pg_stat_user_tables` даёт нули даже для `search_corpus`, куда пишет каждый такт
  (`search_corpus|0|0|0|0`). Использовать счётчики PG для «что изменилось» нельзя.
* **Уточнение к `pg_class.reltuples`.** Это не «оценка вообще»: на таблицах, в которые не
  писали, значение точное (232 из 235 сошлись), а расходится оно ровно там, где были
  удаления/обновления (`search_corpus` 99 009 против 97 965 — мёртвые строки ещё не
  вычтены). Для витрины (только чтение из ETL) — точное; для нашего корпуса — нет.
* **MATERIALIZED VIEW в движке нет.** [код] Поиск `MATERIALIZED VIEW` по всем 1653 тестам
  `tests/sqllogic` — ноль совпадений. То есть «материализованная вьюха с REFRESH» как
  обход статичности индекса над вьюхой недоступна.

### 2.2 Новое: генерируемые колонки (`GENERATED ALWAYS AS … STORED`)

Не было в первом проходе; это прямой ответ на «SHA1 в Python».

[код] `tests/sqllogic/sdb/pg/site_docs/cookbook/search/computed-values.test:6`:
```sql
CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR, price INTEGER,
                       price_with_tax INTEGER GENERATED ALWAYS AS (price * 110 / 100) STORED);
```
[код] `tests/sqllogic/sdb/pg/dml/merge.test:112` — генерируемая колонка работает и как
цель `MERGE`: `CREATE TABLE merge_gen(a INTEGER, b INTEGER DEFAULT 7,
g INTEGER GENERATED ALWAYS AS (a + b) STORED, c INTEGER)`.

[вывод] в бинарнике 26.07.3 есть все сообщения этого механизма:
`Cannot insert a non-DEFAULT value into generated column "%s"`,
`Column %s must have a type or be defined as a GENERATED column.`,
`cannot set a default on generated column`,
`Unsupported constraint for generated column!`,
`Lambda functions are currently not supported in generated columns.`

**Что это даёт нам:** колонку `doc_hash` в корпусе можно объявить
`GENERATED ALWAYS AS (sha1(doc || chr(0) || refs)) STORED` — движок будет пересчитывать
её сам при любом INSERT/UPDATE, и `hashlib` из Python исчезает вместе с риском
рассинхрона «hash не от того текста».
**Ограничение, важное для нас:** [вывод] `Lambda functions are currently not supported in
generated columns` — то есть сборку `doc` через `list_transform(json_keys(...), k -> ...)`
в генерируемую колонку положить НЕЛЬЗЯ; там останется только хеш от уже готовых `doc`/`refs`.

### 2.3 Новое: инвертированный индекс по ВЫРАЖЕНИЮ (и почему это не решает наш случай)

[код] `tests/sqllogic/sdb/pg/site_docs/cookbook/search/computed-values.test:9,65`:
```sql
CREATE INDEX products_idx ON products USING inverted (id, (lower(name)), price_with_tax);
CREATE INDEX people_idx   ON people   USING inverted (id, (first || ' ' || last));
```
и запрос идёт по тому же выражению: `WHERE (first || ' ' || last) @@ 'Jane Doe'`.
[код] `tests/sqllogic/sdb/pg/index/inverted_index_expr_backfill.test:78,131,155` —
выражение можно связать со словарём: `USING inverted(id, (a || '-' || b) verbatim_dict)`,
и индекс по выражению **достраивается (backfill) по уже существующим строкам**.

[вывод] в 26.07.3 механизм есть — в бинарнике присутствуют его же диагностики:
`window functions are not allowed in index expressions`,
`aggregate functions are not allowed in index expressions`,
`cannot use subquery in index expressions`,
`field_id collision in inverted index expression bridge`.

**Почему это НЕ заменяет корпус:** ровно из-за нашего требования про разрешённые имена
ссылок. Индексное выражение считается по колонкам ОДНОЙ строки одной таблицы; джойна в
нём быть не может — [вывод] `cannot use subquery in index expressions`. Значит
«Контрагент: ООО Ромашка» выражением не собрать, и таблица-корпус со своим `MERGE`
остаётся необходимой. Это как раз случай «штатного механизма нет ровно под нашу задачу».

Что при этом реально применимо: индекс по выражению снимает необходимость хранить
производные текстовые колонки в самом корпусе (например `lower(...)`, склейку `doc||refs`)
— их можно индексировать выражением, не занимая место и не пересчитывая в Python.

### 2.4 Новое: движок умеет посчитать «изменилось ли вообще» за 0.7 с по ВСЕЙ базе

Это самое ценное, что дал второй проход, и в первом его не было.

[вывод] агрегаты `bit_xor`, `bit_and`, `bit_or` в сборке есть.
[замер] один сгенерированный запрос (текст собран самим движком, 49 КБ, 226 веток):
```sql
SELECT '<таблица>' AS t, count(*) AS n,
       bit_xor(hash(to_json(x)::VARCHAR)) AS ck,
       sum(hash(to_json(x)::VARCHAR)::HUGEINT) AS s
FROM "<таблица>" x
UNION ALL …
```
| что | время |
|---|---|
| `count + bit_xor` по всем 226 таблицам витрины | **0.687 с** |
| `count + bit_xor + sum` (устойчивее к чётным дублям) | **0.711 с** |

Смысл: **контрольная сумма содержимого каждой таблицы витрины за 0.7 с.** Если для
таблицы `(n, ck, s)` совпали с прошлым тактом — её строки в корпусе трогать не нужно
вовсе. Если ни одна таблица-источник карты ссылок не менялась, то и переименований не
было, то есть весь остальной такт можно не делать.

Такт «ничего не изменилось» превращается в:
`pg_class.reltuples` 0.089 с + `duckdb_columns()` 0.041 с + контрольные суммы 0.711 с
≈ **0.85 с** вместо нынешних ~258 с. Это **~300×**, и оно не растёт с размером базы
линейно по числу процессов — растёт только по объёму данных, одним сканом.

Оговорка (наша, не движка): `bit_xor` по своей природе гасит пары одинаковых значений
(две полностью идентичные строки дают 0). Поэтому берём тройку `count + bit_xor + sum`,
а не только xor. Это наша конструкция поверх штатных агрегатов — штатной «контрольной
суммы таблицы» в движке нет.

Правило пересчёта, сохраняющее свойство про переименования:
1. посчитать `(n, ck, s)` по всем таблицам;
2. если изменилась хотя бы одна таблица, участвующая в КАРТЕ ССЫЛОК (та, у которой
   объявленный ключ — ровно `Ref_Key`) → пересчитывать отпечатки по всем таблицам
   (18 с, п. 3 первого прохода): переименование могло затронуть любой документ;
3. иначе пересчитывать отпечатки только по изменившимся таблицам.
   [замер] одна таблица на 11 688 строк — **0.381 с**.

### 2.5 Новое: `CREATE TABLE … WITH (storage = 'search')` — есть, но нам не подходит

[код] `server/connector/search_table_dispatch.cpp:80-103` — `WITH (storage =
'transactional' | 'search')`, плюс параметры `refresh_interval_ms`,
`compaction_interval_ms`, `cleanup_interval_step` ([код] там же, строки 133-140).
[код] `tests/sqllogic/sdb/pg/simple/search_table.test:12-200` — полный жизненный цикл:
INSERT/UPDATE/DELETE/TRUNCATE, `SELECT COUNT(*)` идёт по count-only пути без чтения колонок.
[вывод] в 26.07.3 механизм есть: строка `" must be 'transactional' or 'search', got "`.

**Почему не подходит корпусу.** Во-первых, видимость записей отложенная: почти после
каждой DML в тесте стоит `VACUUM (REFRESH_TABLE)`, без него данные не видны
([код] строки 66-72, 97-105, 122-130). Во-вторых, [код]
`server/connector/search_table_dispatch.cpp:104-113` `RejectIfSearchTable` →
`"<операция> on a search-backed table is not yet supported"`, и она вызывается из
`BindCreateIndex` ([код] `server/connector/duckdb_catalog.cpp:868-872`), то есть
**свой инвертированный индекс со словарями на такую таблицу не построить** — а нам
нужны именно наши словари, поля `doc`/`refs`/`src_table` и `INCLUDE`.

### 2.6 Новое: ES-совместимый путь записи (`es_bulk`) — есть, нам не подходит

[вывод] в сборке 26.07.3 зарегистрированы `es_create_index`, `es_drop_index`,
`es_mapping`, `es_cat_indices`, `es_doc(3)`, `es_bulk(2)`, `es_refresh(1)`.
[код] `tests/sqllogic/sdb/pg/es/write_path.test:1-20`:
```sql
CALL es_create_index('slt_es_w', '{"mappings":{"properties":{"title":{"type":"text"},…}}}');
INSERT INTO es.slt_es_w SELECT * FROM es_bulk('slt_es_w', '{"index":{"_id":"b"}}
{"title":"quick brown fox","n":8}
{"create":{}}
{"title":"lazy dog","ts":986121000000}
');
CALL es_refresh('slt_es_w');
```
Это отдельный мир: своя схема `es`, свой маппинг, свой `_source`, свои `$text`-таблицы и
обязательный `es_refresh`. Массовую загрузку он решает (`es_bulk` — табличная функция,
потребляемая через `INSERT … SELECT`), но ценой отказа от наших словарей, `INCLUDE` и
`MERGE`. Фиксирую как найденное и отклонённое.

### 2.7 Дополнительно к вопросу 2: подводные камни JSON-пути, проверенные вживую

* [вывод] Проблемных имён колонок в нашей витрине нет:
  `SELECT count(*) FROM duckdb_columns() WHERE column_name LIKE '%.%' OR … '%"%' OR … '% %'`
  → `0`. Значит `json_extract_string(j, k)` с «сырым» ключом безопасен (иначе понадобился
  бы экранированный путь `'$."'||k||'"'`, который, кстати,
  [вывод] на живом движке молча вернул ПУСТЫЕ значения — этот вариант использовать нельзя).
* [вывод] Полный набор типов витрины: `BIGINT, BOOLEAN, DOUBLE, HUGEINT, TIMESTAMP,
  VARCHAR` (плюс `FLOAT[1536]` только в корпусе/резолвере). Экзотики нет.
* [вывод] `TIMESTAMP` в `to_json` рендерится **так же**, как `::VARCHAR`:
  `2025-11-15 11:00:00` в обоих случаях.
* [вывод] **`BOOLEAN` рендерится по-разному:** `to_json` даёт `true`/`false`, а нынешний
  `psql --csv` — `t`/`f`. Это значит: при переходе на SQL-сборку `doc` тексты строк с
  логическими колонками ИЗМЕНЯТСЯ, отпечатки не совпадут и произойдёт **однократный полный
  пересчёт эмбеддингов**. Это не дефект перехода, но это надо запланировать (и, если
  нужно избежать, привести рендер к прежнему виду явным `CASE`).

### 2.8 Дополнительно к вопросу 1: индекс над вьюхой всё-таки нам полезен — но не для корпуса

Раз индекс над вьюхой статичен, есть ровно один сценарий, где он нам подходит: **данные,
которые не меняются между полными перезагрузками**. У нас такой сценарий — архитектура
«сырые данные в PG на Windows, Ubuntu только корпус+индекс»: вьюха над внешним источником
позволяет индексировать, вообще не копируя данные к себе.
[код] `tests/sqllogic/sdb/pg/duckdb_postgres/inverted_index_pgscan.test_slow:70` —
«count(*) over the view-backed index -- flows from iresearch, no source touch», но там же
строка 122 — попытка достать НЕиндексированную колонку даёт
`materialising real columns from this view-backed inverted index is not yet supported`.
Практический вывод: над внешним PG индекс над вьюхой работает, но **все нужные колонки
обязаны быть в `INCLUDE`**, иначе запрос упадёт. Это отдельная тема, не такт пересборки.

### 2.9 Дополнительно к вопросу 6: чего в каталоге НЕТ

* [вывод] `duckdb_tables().estimated_size` — NULL, счёта строк из каталога DuckDB нет.
* [вывод] `duckdb_indexes().sql` отдаёт `CREATE INDEX search_idx ON public.search_corpus
  USING inverted ();` — **пустые скобки**, состав индекса каталог не хранит
  (это уже зафиксировано в нашем коде, подтверждаю повторно).
* `SUMMARIZE` — есть и полезен как замена нашему `profile_table` (даёт
  count / approx_unique / null_percentage / min / max по всем колонкам одним оператором),
  но это оператор НА ТАБЛИЦУ и он сканирует; заменой 233 вызовам он не является.

---

## Что я НЕ смог выяснить

1. **Скорость `MERGE INTO search_corpus USING (<большой подзапрос>)` на живой базе.**
   MERGE — запись, а мне запрещены DML. Все выводы про MERGE опираются на тесты
   (`merge_into/index.test`, `cookbook/sql_features/merge.test`, `dml/merge.test`) и на
   строки бинарника. Сколько именно стоит MERGE 97 965 строк в таблицу с инвертированным
   индексом — не измерено.
2. **Возвращает ли `RETURNING merge_action` на НАШЕЙ сборке ровно значения
   `INSERT`/`UPDATE`/`DELETE`** — взято из docs-теста ветки main; в 26.07.3 подтверждено
   лишь косвенно (наличие `Unsupported merge action for RETURNING`, `MergeActionType`,
   `WHEN NOT MATCHED BY SOURCE` в бинарнике).
3. **Работает ли `CREATE TABLE … GENERATED ALWAYS AS … STORED` в 26.07.3 практически** —
   только по строкам бинарника и тестам main; DDL не выполнял.
4. **Стоимость `CREATE INDEX` над вьюхой на нашем объёме** — не измерял и не буду:
   `CREATE INDEX` под запретом. Поэтому вариант «вьюха + полная пересборка индекса каждый
   такт» количественно не оценён (качественно он проигрывает уже потому, что это полный
   пересчёт).
5. **Точное распределение 18.1 с** между `to_json`, `unnest`, `LEFT JOIN` с картой ссылок
   и `sha1` — не разбирал; `EXPLAIN ANALYZE` этого запроса не снимал.
6. **Поведение `json_extract_string` на значениях с управляющими символами** (перевод
   строки внутри «Комментария» — у нас это уже кусало в CSV-разборе). JSON такие значения
   экранирует корректно по формату, но побайтовое совпадение с нынешним `doc` я не сверял.
7. **Совместимость существующих `doc_hash`.** Проверено только, что `sha1()` движка
   совпадает с `hashlib.sha1` на `'abc'`. Совпадут ли ПОЛНЫЕ строки `doc` (порядок
   колонок, фильтры служебных колонок, обрезка `TEXT_CLIP`, формат чисел и дат) —
   не сверял построчно; по булевым точно НЕ совпадут (п. 2.7).
8. **Есть ли в движке ограничение на длину текста SQL-запроса** — 124 КБ прошли, но
   на базе клиента с тысячами таблиц текст будет в разы больше; предела не искал.

---

## Что проверить замером

Всё ниже — на копии/тестовой базе, не на боевом инстансе. Пометки: **[ЗАПРЕТ]** — требует
`CREATE INDEX`, у нас на это запрет; **[ЗАПИСЬ]** — DML/DDL, мне запрещено, вам можно.

1. **[ЗАПИСЬ] Отпечатки целиком в базе, без Python.** Сгенерировать текст движком и
   выполнить:
   ```sql
   -- шаг 1: движок собирает текст запроса
   SELECT string_agg('SELECT '''||table_name||''' AS src, rid,
      sha1(string_agg(k||'': ''||coalesce(nm,v), '' | '' ORDER BY i)) AS h FROM (
        SELECT r.rid, u.k, u.i, json_extract_string(r.j, u.k) AS v
        FROM (SELECT rowid AS rid, to_json(t) AS j FROM "'||table_name||'" t) r,
             unnest(json_keys(r.j)) WITH ORDINALITY AS u(k,i)) kv
      LEFT JOIN m ON m.g = kv.v
      WHERE kv.v IS NOT NULL AND kv.v <> '''' GROUP BY rid', E'\nUNION ALL\n')
   FROM duckdb_tables() WHERE database_name='postgres' AND table_name NOT LIKE 'search%';
   -- шаг 2: CREATE TABLE search_seen AS WITH m AS (<карта ссылок>) <текст из шага 1>;
   ```
   Ожидание по нашему замеру: ~18 с на 97 965 строк, ноль строк через Python.
   Замерить: время `CREATE TABLE … AS`, число строк, и **сверить `h` со значениями
   `search_corpus.doc_hash`** — сколько строк совпало (это и покажет цену однократного
   пересчёта эмбеддингов).

2. **[ЗАПИСЬ] MERGE как единственный механизм обнаружения изменений.** Заменить
   staging + `LEFT JOIN` + gone-очистку одним оператором и замерить:
   ```sql
   MERGE INTO search_corpus t
   USING (<запрос из п.1, отдающий src_table,row_key,doc,refs,doc_hash,amount,doc_date>) s
   ON t.src_table = s.src_table AND t.row_key = s.row_key
   WHEN MATCHED AND t.doc_hash <> s.doc_hash THEN UPDATE SET
        doc=s.doc, refs=s.refs, doc_hash=s.doc_hash,
        amount=s.amount, doc_date=s.doc_date, emb=NULL
   WHEN NOT MATCHED BY TARGET THEN INSERT (src_table,row_key,doc,refs,doc_hash,amount,doc_date,emb)
        VALUES (s.src_table,s.row_key,s.doc,s.refs,s.doc_hash,s.amount,s.doc_date,NULL)
   WHEN NOT MATCHED BY SOURCE THEN DELETE
   RETURNING merge_action, t.src_table, t.row_key;
   ```
   Проверить: (а) что `merge_action` реально приходит и содержит INSERT/UPDATE/DELETE;
   (б) время на 97 965 строк при нуле изменений и при 1 000 изменений;
   (в) что инвертированный индекс после этого согласован (запрос `FROM search_idx`
   находит новые строки без пересборки индекса).
   Затем эмбеддить строки `WHERE emb IS NULL` — список брать из `RETURNING`, а не из
   отдельного запроса.

3. **[ЗАПИСЬ] Контрольные суммы как «ранний выход» такта.** Завести
   `search_srcsum(src_table, n, ck, s)` и на каждом такте выполнять запрос из п. 2.4
   (замерено 0.711 с). Проверить сценарии: (а) ничего не менялось → такт < 1 с;
   (б) изменена одна строка в справочнике-источнике ссылок → пересчёт всей базы;
   (в) изменена одна строка в регистре, не участвующем в карте ссылок → пересчёт только
   этой таблицы (замерено 0.381 с на 11 688 строк).

4. **[ЗАПИСЬ] Генерируемая колонка вместо `hashlib`:**
   ```sql
   CREATE TABLE search_corpus_v2 (src_table TEXT, row_key TEXT, doc TEXT, refs TEXT,
     doc_hash TEXT GENERATED ALWAYS AS (sha1(doc || chr(0) || refs)) STORED,
     amount DOUBLE, doc_date TIMESTAMP, emb FLOAT[1536]);
   ```
   Проверить, что движок 26.07.3 это принимает и что `MERGE`/`INSERT` в такую таблицу не
   требует указывать `doc_hash` (ожидаемая ошибка при попытке указать —
   `Cannot insert a non-DEFAULT value into generated column`).

5. **[ЗАПИСЬ] Массовая загрузка через `COPY … FROM STDIN`** — если по какой-то причине
   часть данных всё-таки придётся отдавать из Python: замерить `COPY search_seen FROM
   STDIN (FORMAT CSV)` одним потоком против нынешних 490 `INSERT`. Ожидание: одна
   транзакция, один процесс.

6. **[ЗАПРЕТ] Индекс над вьюхой на нашем объёме.** Замерять время
   `CREATE INDEX … ON <view> USING inverted(...)` — нельзя. Если запрет когда-нибудь
   снимут, проверять надо ровно две вещи: (а) время полной пересборки на 97 965 строках;
   (б) что после `INSERT` в базовую таблицу индекс НЕ видит новую строку (ожидание —
   не видит, `inverted_index_view_include.test:189-207`).

7. **[ЗАПРЕТ] Индекс по выражению** `USING inverted(..., (doc || ' ' || refs) search_dict)`
   — снял бы необходимость хранить склейку, но требует `CREATE INDEX`.

8. **Точечно, без записи (можно делать хоть сейчас):**
   `EXPLAIN ANALYZE` запроса из п. 1 — разложить 18 с по операторам и понять, не
   упирается ли карта ссылок в hash join. Это чистый SELECT, запрета не нарушает.
