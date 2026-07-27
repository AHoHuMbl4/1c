# CHECK2_INCR_3 — штатные механизмы SereneDB против нашей пересборки корпуса

Сборка движка: **PostgreSQL 18.3 (SereneDB 26.07.3)**, `host=127.0.0.1 port=7890` на
192.168.56.42 (проверено: `SELECT version()` → `PostgreSQL 18.3 (SereneDB 26.07.3)`).
Репозиторий: `/srv/data/cursor/cursor/1/serenedb-src` (ветка main, новее нашей сборки).

Пометки: `[код]` — файл:строка в репозитории; `[вывод]` — вывод с живого движка;
`[замер]` — время, снятое на живом движке.

Все запросы к живому движку выполнялись через ssh (`psql` локально не установлен):
`ssh -i /home/ahohum/.ssh/id_ed25519_1c root@192.168.56.42 psql 'host=127.0.0.1 port=7890 user=postgres dbname=postgres'`.
Ничего кроме `SELECT` и каталожных функций не выполнялось; `CREATE/DROP/ALTER/INSERT/UPDATE/DELETE/VACUUM`
не запускались ни разу, `ivf` не трогался.

---

## Итог одной строкой

Вся фаза «прочитать базу — собрать `doc` — посчитать отпечаток — сравнить с корпусом»,
которая сегодня занимает **86 % пятиминутного такта и ~1 190 процессов `psql`**,
выражается **одним SQL-запросом в одном соединении** и выполняется на нашей базе за
**1,5–1,7 с** [замер]. Разрешение ссылок (главное требование правильности) при этом не
теряется, а становится **обычным JOIN**, то есть переименование в справочнике начинает
подхватываться автоматически, а не «если отпечаток изменился».

Индекс поверх VIEW в сборке есть, но он **статический** — на этом пути отдельная задача
про свежесть не решается (см. вопрос 1). Поэтому рекомендация: **оставить таблицу
корпуса + индекс на таблице**, но всю подготовку данных перенести в SQL.

---

## 1. Инвертированный индекс поверх VIEW

**Да, поддерживается.** И над внешними файлами, и над обычными таблицами движка, и над
`UNION ALL`-склейкой нескольких представлений.

Дословно, тест `tests/sqllogic/sdb/pg/index/inverted_index_view.test` [код]:

```sql
-- строки 30-36
CREATE VIEW pq_v AS SELECT * FROM read_parquet('${__TEST_DIR__}/view_idx.parquet');
CREATE INDEX pq_idx ON pq_v USING inverted(id, body view_idx_en);

-- строки 121-125: view над обычной rocksdb-таблицей движка
CREATE VIEW v_star AS SELECT * FROM base_t;
CREATE INDEX i_star ON v_star USING inverted(body view_idx_en);
```

Обращение — от имени индекса, как и у нас (`inverted_index_view.test:41`):
`SELECT count(*) FROM pq_idx WHERE body @@ ts_phrase('pudge');`

Наличие механизма в НАШЕЙ сборке подтверждено строкой из бинарника 26.07.3 [вывод]:

```
$ strings /opt/serenedb-dist/serenedb-26.07.3-linux-amd64/usr/bin/serened | grep -i 'view-backed'
materialising real columns from this view-backed inverted index is not yet supported --
view body must be a simple `SELECT * FROM <reader>(literal_args)` over a recognised
fast-path source (read_parquet/csv/json/...)
```

### Что происходит при изменении базовых таблиц — ГЛАВНОЕ

**Индекс поверх VIEW статический. Он не обновляется ни сам, ни по `VACUUM`.**
Это зафиксировано и в коде, и в тестах как намеренный контракт:

- `server/connector/duckdb_catalog.cpp:874` [код]:
  `// View-backed indexes are STATIC -- captured at CREATE INDEX, no DML refresh.`
- `tests/sqllogic/sdb/pg/index/inverted_index_view.test:110` [код]:
  `# View over a serenedb rocksdb table -- static, no DML refresh.`
- `tests/sqllogic/sdb/pg/index/inverted_index_view_include.test:189-204` [код] — тест
  специально «прибивает» это поведение, чтобы оно молча не поменялось:

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

- `tests/sqllogic/sdb/pg/index/inverted_index_view_duckdb.test:1-6` [код]: «Rows deleted
  in the source file after CREATE INDEX materialize as NULLs (same contract family as
  parquet/iceberg view indexes: **the index pins what it indexed**)».
- `tests/sqllogic/sdb/pg/index/inverted_index_partial.test:381` [код]: «Partial indexes on
  views are static (built once, no DML maintenance)».

`VACUUM (REFRESH_*)` тут не помогает: список глаголов — `refresh_/compact_/recompute_stats_`
для scope `database/schema/table/index/all` (`server/connector/duckdb_vacuum_function.cpp:56-83`
[код]). `Refresh` публикует **отложенные записи таблицы** в индекс
(`tests/sqllogic/recovery/vacuum_global.test:41`: «REFRESH_ALL publishes pending writes»),
а у view-индекса отложенных записей от DML базовой таблицы просто не возникает — он их
не отслеживает.

**Вывод по вопросу 1.** Путь «корпус = VIEW-джойн витрины, индекс на VIEW» даёт вечно
актуальное разрешение ссылок **только в момент CREATE INDEX**. Для свежести ≤ 20 минут
пришлось бы каждые 20 минут делать `DROP INDEX` + `CREATE INDEX` над всеми 98 тыс. строк —
это полная перестройка инвертированного индекса вместо инкремента, и на базе клиента
«в разы крупнее» это заведомо хуже, чем сейчас. **Не идти этим путём.**
Единственное, что из демки VIEW стоит взять — форму: `examples/demo6/bootstrap.sql`
показывает «вьюха на источник → UNION ALL мега-вьюха → один инвертированный индекс со
всеми колонками в `INCLUDE`» [код] — именно наша форма корпуса, но у них данные
неизменяемые (parquet на Hugging Face), поэтому статичность их не трогает.

Отдельно: у **generic**-вьюхи (UNION ALL, JOIN — всё, что не
`SELECT * FROM read_parquet/csv/json/duckdb(...)` и не простая таблица) читать реальные
колонки через индекс **нельзя** — ошибка из бинарника выше. demo6 обходит это тем, что
кладёт **все** колонки в `INCLUDE`, и индекс становится самодостаточным
(`examples/demo6/bootstrap.sql`, комментарий «after the build the index is self-sufficient:
queries never re-read the parquet») [код]. То есть индекс над JOIN-вьюхой корпуса
технически возможен, но только «всё в INCLUDE» — и всё равно статический.

---

## 2. Сборка строки `doc` в SQL

**Да, есть, и без списка колонок в клиенте.** Ключ — `to_json(<алиас таблицы>)`:
движок сам разворачивает строку в JSON с именами колонок, дальше `json_keys` +
`list_transform` + `list_aggregate('string_agg')` собирают «Колонка: значение | …».

Проверено на живом движке [вывод]:

```sql
SELECT list_aggregate(
         list_transform(json_keys(j),
           k -> k || ': ' || coalesce(json_extract_string(j, k), '')),
         'string_agg', ' | ') AS doc
FROM (SELECT to_json(t) AS j FROM (SELECT 1 a, 'x' b, NULL c, DATE '2020-01-01' d) t);
-- a: 1 | b: x | c:  | d: 2020-01-01
```

Замечание по синтаксису, важное для нас [вывод]: в этой сборке путь `$.a` в
`json_extract_string` **не работает** (возвращает NULL), рабочая форма — **голое имя
ключа**: `json_extract_string(j, 'a')`. Проверка:

```sql
SELECT json_extract_string('{"a":1,"b":"x"}'::json, '$.a') AS lit,   -- пусто
       json_extract_string('{"a":1,"b":"x"}'::json, '$.' || 'a') AS dyn, -- пусто
       json_extract_string('{"a":1,"b":"x"}'::json, 'a') AS bare;    -- 1
```

Что ещё доступно и проверено в сборке [вывод] (`duckdb_functions()`):
`to_json`, `row_to_json`, `json_object`, `struct_pack`, `list_transform`, `list_reduce`,
`list_aggregate`, `list_value`, `map_from_entries`, `string_agg`, `concat_ws`,
`array_to_string`, `union_value`.

`COLUMNS(*)` в этой сборке работает [вывод]:
`SELECT count(COLUMNS(*)) FROM (SELECT 1 a, 2 b)` → `1 | 1`;
`SELECT concat_ws(' | ', COLUMNS(*)) FROM (SELECT 1 a, 'x' b) t` → `1 | x`.
Но `COLUMNS(*)` **не даёт имён колонок внутри выражения** — годится для склейки значений,
не годится для «Колонка: значение». Для нашей задачи выигрывает `to_json`.

Есть также `query_table('<имя>')` — динамическое обращение к таблице по строке [вывод]:
`SELECT count(*) FROM query_table('search_corpus')` → `97965`. Имя всё равно должно быть
литералом в тексте запроса, поэтому от **генерации текста** запроса в Python уйти нельзя.

**Честный ответ: генерация SQL остаётся нужна** — но только генерация *имён таблиц*
(233 подзапроса `UNION ALL` в одном тексте), а **не** списка колонок и не значений.
Текст такого запроса на нашей базе — 76 КБ, строится одним `string_agg` из
`duckdb_tables()` [вывод], то есть его можно получить с самого же сервера:

```sql
SELECT string_agg(
  'SELECT ' || quote_literal(table_name) || ' AS src, md5(...) AS h FROM (SELECT to_json(t) AS j FROM '
  || quote_ident(table_name) || ' t)', ' UNION ALL ')
FROM duckdb_tables() WHERE schema_name='public';
```

---

## 3. Отпечаток в SQL

**Есть.** В сборке 26.07.3 присутствуют [вывод] (`duckdb_functions()`):
`md5`, `md5_number`, `md5_number_lower`, `md5_number_upper`, `sha1`, `sha256`, `hash`.
`xxhash`, `crc32`, `digest`, `farm_fingerprint` — **нет**.

Проверка работоспособности [вывод]:
```sql
SELECT md5('abc'), hash('abc'), sha256('abc');
-- 900150983cd24fb0d6963f7d28e17f72 | 1924864467101078684 |
-- ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
```

Наш текущий `hashlib.sha1(doc + "\x00" + refs)` (`ubuntu/serenedb/serene_search_build.py:809`)
заменяется на `sha1(doc || chr(0) || refs)` **без изменения значения отпечатка** — то есть
переход можно сделать без разовой полной перезаливки корпуса. (Совпадение байт-в-байт надо
подтвердить замером, см. последний раздел.)

**Отпечаток по собранной строке считается прямо в SQL — данные в Python не читаются вовсе.**
Замер на реальной таблице `catalog_поляформстатистики` (23 878 строк) [замер]:

```
SELECT count(DISTINCT h) FROM (SELECT md5(<сборка doc через to_json>) AS h FROM catalog_поляформстатистики t);
-- 23878, Time: 1199 ms
```

Замер по **всем 226 таблицам-источникам витрины** одним запросом [замер]:

```
-- 226 подзапросов UNION ALL, сгенерированы одним string_agg из duckdb_tables()
SELECT count(*), count(DISTINCT h) FROM ( ... );
-- 97965 | 97965      Time: 1643 ms
```

97 965 строк — ровно размер нашего корпуса, то есть покрытие полное.
**1,64 с в одном процессе против ~258 с и ~1 190 процессов сегодня — примерно в 150 раз.**

Полный «фингерпринт + сравнение с корпусом» одним запросом [замер]:

```
WITH fresh AS ( <226 UNION ALL с md5> )
SELECT count(*) FROM fresh f
LEFT JOIN search_corpus c ON c.src_table = f.src AND c.doc_hash = f.h
WHERE c.src_table IS NULL;
-- Time: 1497 ms
```

(Число «изменившихся» в этом замере равно 97 965, потому что формула `doc` в пробе
отличается от продовой — замерялась форма и скорость, не семантика.)

---

## 4. Обнаружение изменений штатно

- **CDC / журнал изменений / changefeed — НЕТ.** Единственные вхождения `cdc` в коде —
  это `duckdb::ColumnDataCollection` (`server/search/search_db_wal.cpp:503,737`) [код],
  к change-data-capture отношения не имеет. Грепа по `changefeed`, `change data capture`
  по всему репозиторию — пусто [код].
- **`xmin` / `ctid` / версии строк — НЕТ** [вывод]:
  `SELECT xmin, ctid FROM catalog_организации LIMIT 1;` →
  `ERROR: Referenced column "xmin" not found in FROM clause!`
- **`rowid` — ЕСТЬ и стабилен при in-place UPDATE** [вывод] (`SELECT rowid FROM catalog_организации` работает).
  Контракт зафиксирован тестом `tests/sqllogic/sdb/pg/dml/merge_returning_rowid.test:1-40` [код]:
  «MERGE … WHEN MATCHED THEN UPDATE … RETURNING must stay on the in-place update path and
  preserve rowid, exactly like a plain UPDATE … RETURNING». Но `rowid` — это позиция,
  а не «что изменилось»: узнать по нему, какие строки изменились с прошлого такта, нельзя.
- **`reltuples` в `pg_class` — есть, без сканирования** (см. вопрос 6). Это не «что
  изменилось», но даёт дешёвый сигнал «в таблице поменялось число строк».

### `MERGE ... RETURNING merge_action` — это и есть штатный ответ

Синтаксис (дословно, `tests/sqllogic/sdb/pg/site_docs/sql/statements/merge_into/index.test:104-125`) [код]:

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

Возвращается **текстовое действие** (`INSERT` / `UPDATE` / `DELETE`) плюс любые колонки
целевой и исходной таблицы. То есть **список затронутых ключей получается прямо из
`RETURNING`**: `RETURNING merge_action, t.src_table, t.row_key`.

Наличие в 26.07.3 [вывод]: `MERGE INTO` в бинарнике есть (строки
`MERGE INTO is not supported on tables with triggers`, `WHEN NOT MATCHED BY SOURCE`,
`Can only merge into base tables!`), и есть строка обработчика именно этого случая —
`Unsupported merge action for RETURNING`, а также `MergeActionType`,
`MergeActionCondition`. Плюс **мы уже используем `MERGE INTO` в проде**:
`ubuntu/serenedb/serene_search_build.py:729-737` [код].

Важно: `MERGE INTO (и INSERT ... ON CONFLICT) не поддержан на search-backed таблицах`
(строка из бинарника; тест `tests/sqllogic/sdb/pg/index/search_table_scan_10k.test:202`) —
но наш `search_corpus` это обычная таблица с инвертированным индексом, а не
`CREATE SEARCH TABLE`, поэтому ограничение нас не касается (и MERGE у нас уже работает).
Про взаимодействие MERGE с инвертированным индексом тест говорит прямо
(`tests/sqllogic/sdb/pg/dml/merge.test:2`): «the index forces the commit-time
append/delete path for every merge action» — движок сам приводит индекс в согласованное
состояние.

**Практический вывод:** staging-таблица отпечатков, `LEFT JOIN` по каждой таблице и
последующая догрузка не нужны. Один `MERGE INTO search_corpus USING (<тот самый
UNION ALL-запрос с doc/refs/hash>) ... WHEN MATCHED AND t.doc_hash <> s.h THEN UPDATE ...
WHEN NOT MATCHED THEN INSERT ... WHEN NOT MATCHED BY SOURCE THEN DELETE
RETURNING merge_action, t.src_table, t.row_key` — и на выходе ровно список ключей,
которым нужен эмбеддинг. Одна команда вместо ~490 + 233 + финальной gone-очистки.

---

## 5. Массовая вставка вместо 490 × `INSERT` по 200

Штатные варианты, доступные через обычное соединение по протоколу Postgres:

1. **`INSERT ... SELECT` / `MERGE ... USING (SELECT ...)` внутри базы** — лучший вариант:
   данные вообще не покидают движок. Именно это и предлагается в вопросе 4.
2. **`COPY ... FROM STDIN`** — поддержан по PG-протоколу, включая бинарный формат.
   Строки из бинарника 26.07.3 [вывод]: `unexpected EOF during COPY from stdin`,
   `COPY FROM STDIN: invalid PGCOPY signature`, `COPY FROM STDIN: received copy data after
   EOF marker`, `pg_binary_copy_from`, `COPY FROM requires a table name to be specified`.
3. **`read_csv` / `read_parquet` / `read_json` по пути на сервере** — проверено на живом
   движке [вывод]: файл `/tmp/agent_t.csv` (2 строки) прочитан
   `SELECT count(*), string_agg(v, ',') FROM read_csv('/tmp/agent_t.csv')` → `2 | aaa,bbb`.
   Годится, если файл кладётся на ту же машину (у нас движок и скрипт на одной машине —
   годится). Внимание: аргумент **обязан быть строковым литералом**, иначе
   `ERROR: Deprecated implicit conversion of unbound identifiers to strings in table
   function arguments detected` [вывод].
4. **Appender-API** — в бинарнике есть (`Unsupported statement type for appender: expected
   INSERT, DELETE, UPDATE or MERGE INTO`), но это C++/внутренний API, не по PG-протоколу.
   Для нас недоступен.

---

## 6. Каталог одним запросом вместо 233 + 233

**Колонки — да, одним запросом, без вариантов и без генерации** [вывод]:

```sql
SELECT count(*) FROM duckdb_columns();     -- 4002 (все колонки всех таблиц базы)
SELECT table_name, string_agg(column_name, ',' ORDER BY column_index)
FROM duckdb_columns() GROUP BY 1;
```

То есть цикл `serene_search_build.py:409` (`duckdb_columns()` по каждой таблице,
233 процесса `psql`) заменяется **одним** запросом целиком.

**Число строк — два варианта:**

- **Точное, одним запросом**: `UNION ALL` из `count(*)` по всем таблицам. Текст (40 КБ)
  строится одним `string_agg` из `duckdb_tables()`. Замер на живой базе: **305 таблиц,
  214 мс** [замер]. Это замена цикла `serene_search_build.py:405` (233 процесса `psql`).
- **Оценочное, вообще без сканирования**: `pg_class.reltuples` [вывод]:
  ```sql
  SELECT relname, reltuples FROM pg_class WHERE relkind='r' ORDER BY reltuples DESC;
  -- search_corpus 99009 | search_corpus_bak 97085 | resolver_index 60552 | ...
  ```
  Это **не точное** число: `search_corpus` показывает 99009 при фактических 97965
  (проверено `SELECT count(*)` [вывод]). Причина в коде: `server/pg/pg_catalog/pg_class.cpp:160-176`
  [код] — «reltuples is read from the store table's row-group metadata
  (DataTable::GetTotalRows), never a count(*) query: pg_catalog must not scan data».
  То есть считаются в том числе строки, вытесненные обновлениями/удалениями.
  **Как признак «в таблице что-то происходило» годится, как счётчик — нет.**

`duckdb_tables().estimated_size` в нашей базе пустой (NULL) [вывод] — использовать нельзя.
`SUMMARIZE` как функции в `duckdb_functions()` нет [вывод]; отдельно как оператор не
проверялся (см. «Что проверить замером»).

Отдельно — **`count(*)` сам по себе почти бесплатен**: `SELECT count(*) FROM
catalog_поляформстатистики` (23 878 строк) — **0,627 мс** [замер]. Все 305 таблиц —
214 мс. **86 % такта уходит не на счёт, а на запуск 233 процессов `psql`.**

---

## 7. Распространение переименования через SQL — и оно проверено

Требование: строка корпуса содержит **разрешённые** имена ссылок, и при переименовании
контрагента текст `doc`/`refs` обязан измениться. Сегодня это делается картой
`refmap: GUID -> имя` в Python (`serene_search_build.py:464-530`) и потому требует
вычитывания всей базы.

**В SQL это выражается как обычный JOIN, и — что важно — набор GUID-колонок определять
заранее не нужно.** GUID-колонки распознаются по форме значения прямо в SQL, через тот же
`to_json`. Проверено на живом движке, на реальном документе [вывод]:

```sql
WITH src AS (SELECT to_json(t) AS j FROM document_поступлениенарасчетныйсчет t),
kv AS (
  SELECT j,
         list_filter(json_keys(j),
           k -> regexp_matches(coalesce(json_extract_string(j,k),''),
                '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')) AS gkeys
  FROM src)
SELECT list_aggregate(list_transform(gkeys, k -> k || '=' || json_extract_string(j,k)),
                      'string_agg', ' | ') FROM kv LIMIT 3;
```
Результат (одна строка, сокращённо):
`Ref_Key=18c144c7-… | Организация_Key=fd3ff0c0-… | Контрагент=18c144c4-… |
ДоговорКонтрагента_Key=18c144c5-… | …` — **17 ссылочных колонок найдены сами, время 3,6 мс** [замер].

Полное разрешение имён одним запросом — проверено на живом движке [вывод]:

```sql
WITH refmap AS (
  SELECT "Ref_Key" AS g, "Description" AS nm FROM catalog_контрагенты
  UNION ALL SELECT "Ref_Key", "Description" FROM catalog_организации
  UNION ALL SELECT "Ref_Key", "Description" FROM catalog_договорыконтрагентов
),
src AS (SELECT to_json(t) AS j FROM document_поступлениенарасчетныйсчет t),
kv AS (
  SELECT j, json_extract_string(j,'Ref_Key') AS pk,
         list_filter(json_keys(j), k -> regexp_matches(coalesce(json_extract_string(j,k),''),
           '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
           AND json_extract_string(j,k) <> '00000000-0000-0000-0000-000000000000') AS gkeys
  FROM src),
ex AS (SELECT pk, unnest(gkeys) AS k, j FROM kv)
SELECT pk, string_agg(ex.k || ': ' || m.nm, ' | ') AS refs
FROM ex JOIN refmap m ON m.g = json_extract_string(ex.j, ex.k)
GROUP BY pk ORDER BY pk LIMIT 3;
```

Вывод [вывод]:
```
009451a6-8841-… | Организация_Key: Наша организация | Контрагент: ООО "Северный Ветер" | ДоговорКонтрагента_Key: Договор поставки № 4567/2025
009451a7-8841-… | Организация_Key: Наша организация | Контрагент: ООО "Сибирь Логистик" | ДоговорКонтрагента_Key: Договор поставки № 2630/2025
```
**Time: 62,9 мс** [замер].

Ключевые свойства этой формы:
- **один JOIN на таблицу**, а не по джойну на каждую из 17 ссылочных колонок —
  `unnest` разворачивает найденные GUID-колонки в строки, джойн один;
- **список ссылочных колонок нигде не задан** — ни в Python, ни в SQL;
- «Контрагент: ООО Ромашка» получается склейкой **имени колонки** и **разрешённого
  имени** — ровно наша семантика;
- при переименовании контрагента `refs` меняется **на следующем же такте**, потому что
  это результат джойна, а не сохранённая строка. Свойство, ради которого сделан
  отпечаток по `doc`+`refs`, **сохраняется и усиливается**.

**Динамического джойна «по метаданным» у движка нет** — джойн на `refmap` пишется руками,
но он один и одинаковый для всех 233 таблиц. Генерировать по метаданным придётся только
две вещи: (а) список таблиц для `UNION ALL`, (б) состав `refmap` — какие таблицы отдают
`Ref_Key -> Description` (у нас это уже вычислено логикой `own_key`/`name_cols`,
`serene_search_build.py:485-520`, и её можно материализовать в маленькую таблицу
`refmap` одним `INSERT ... SELECT`).

---

## Что переделать (первый проход)

| # | Что | Замена | Выигрыш |
|---|-----|--------|---------|
| 1 | `serene_search_build.py:405` — 233 × `psql` с `count(*)` | один `UNION ALL`-запрос | 233 процесса → 1, 214 мс [замер] |
| 2 | `serene_search_build.py:409` — 233 × `duckdb_columns()` | один `SELECT ... FROM duckdb_columns()` | 233 процесса → 1 |
| 3 | Вычитывание 97 965 строк в Python + сборка `doc` + SHA1 | `to_json` + `list_transform` + `md5/sha1` в SQL | ~258 с → 1,64 с [замер] |
| 4 | Staging-таблица + ~490 `INSERT` по 200 + 233 `LEFT JOIN` | один `MERGE INTO ... USING (<UNION ALL>) ... RETURNING merge_action, row_key` | ~723 процесса → 1 |
| 5 | `refmap` в Python | JOIN на таблицу `refmap` внутри того же запроса | 62,9 мс на документ-таблицу [замер]; переименования подхватываются всегда |
| 6 | (не делать) корпус как VIEW + индекс на VIEW | — | индекс статический, потребовалась бы полная перестройка каждые 20 мин |


---
---

# Второй проход: что нашлось дополнительно / что опровергнуто

Второй проход шёл по другим источникам: `tests/sqllogic/sdb/pg/site_docs/cookbook/`
(34 рецепта по поиску + `sql_features/`), `server/connector/view_fast_path.cpp`,
полный список табличных функций живого движка, и другие ключевые слова
(`UNPIVOT`, `COLUMNS`, `alias()`, `query()`, `MACRO`, `postgres_query`, `SUMMARIZE`,
`pragma_storage_info`). Первый проход не переписан.

## 2.1. Опровергнуто/уточнено из первого прохода

**(а) `to_json` — не лучший способ собрать `doc`. Есть штатный `UNPIVOT` + `COLUMNS(*)`.**

Кукбук движка `tests/sqllogic/sdb/pg/site_docs/cookbook/sql_features/query_and_query_table_functions.test:38-55`
[код] показывает штатный приём: `alias(COLUMNS(*))` даёт **имена** колонок, а
`UNPIVOT ... ON COLUMNS(* EXCLUDE (...)) INTO NAME ... VALUES ...` (там же, строки 65-73)
разворачивает строку в пары «колонка → значение» без всякого JSON.

Проверено на живом движке [вывод]:
```sql
SELECT any_value(alias(COLUMNS(*))) FROM (SELECT 1 AS foo, 'x' AS bar);
-- foo | bar
SELECT col, val FROM (SELECT COLUMNS(*)::VARCHAR FROM catalog_организации)
UNPIVOT (val FOR col IN (COLUMNS(*)));
-- Ref_Key | fd3ff0c0-...  / DataVersion | AAAABgAAAAA= / DeletionMark | false
-- Code | 00-000001 / Description | Наша организация      Time: 9 мс
```
Важная деталь: без явного каста `UNPIVOT` падает [вывод] —
`ERROR: Cannot unpivot columns of types VARCHAR and BOOLEAN - an explicit cast is required`.
Рабочая форма — `SELECT COLUMNS(*)::VARCHAR FROM t` во внутреннем подзапросе.

Поведение с NULL — ровно наша семантика «пустой реквизит в текст не идёт» [вывод]:
```sql
SELECT col, val FROM (SELECT 1 AS id, NULL::VARCHAR AS a, 'y' AS b) UNPIVOT (val FOR col IN (a, b));
-- b | y                      -- NULL отброшен
SELECT ... UNPIVOT INCLUDE NULLS (val FOR col IN (a, b));
-- a |  ; b | y               -- при желании можно и включить
```
`string_agg(..., ORDER BY ...)` работает [вывод]: `string_agg(x, ',' ORDER BY x DESC)` → `c,b,a`.

**Замеры (одна и та же задача — `doc` + md5 по всей таблице/базе):**

| Способ | `catalog_поляформстатистики` (23 878 строк) | все 226 таблиц (97 965 строк) |
|---|---|---|
| `to_json` + `json_keys` + `list_transform` | **1 199 мс** [замер] | **1 644 мс** [замер] |
| `UNPIVOT` + `COLUMNS(*)::VARCHAR`, без `ORDER BY` | **181 мс** [замер] | **1 139 мс** [замер] |
| `UNPIVOT`, группировка по `rowid`, с `ORDER BY col` | 401 мс [замер] | 5 593 мс [замер] |

То есть в первом проходе я выбрал `to_json`; **`UNPIVOT` быстрее (1,14 с против 1,64 с на
всей базе)**, но только если не добавлять `ORDER BY col` в `string_agg` — с сортировкой он
проигрывает в 3,4 раза (5,59 с). Порядок колонок в `UNPIVOT` задаётся списком `IN`, то есть
порядком объявления колонок в каталоге, и он стабилен между тактами, пока не менялась схема
таблицы; при изменении схемы отпечатки всё равно обязаны пересчитаться. **Рекомендация:
`UNPIVOT` без `ORDER BY`.** Оговорка: детерминированность порядка `UNPIVOT` я подтвердил
рассуждением и повторными прогонами, а не тестом движка — см. «Что проверить замером».

**(б) `sha1` в SQL совпадает с `hashlib.sha1` побайтно — переход без перезаливки корпуса.**
[вывод] + локально:
```
psql: SELECT sha1('Контрагент: ООО Ромашка') -> 54958b51121e123c13d899ef5b75eace06c829fa
py:   hashlib.sha1('Контрагент: ООО Ромашка'.encode()).hexdigest() -> 54958b51121e123c13d899ef5b75eace06c829fa
```
Значит перенос расчёта отпечатка в SQL не обесценивает 97 965 уже сохранённых `doc_hash`
и не вызывает повторного эмбеддинга всего корпуса — при условии, что формула склейки
`doc` воспроизведена ровно.

**(в) `pg_class.reltuples` — подтверждено, что это оценка, но добавилась причина.**
Первый проход это уже писал; во втором нашёлся ещё и практический ноль-результат:
`pragma_storage_info('catalog_организации')` и `pragma_metadata_info()` на нашей базе
возвращают **пусто** [вывод] — таблицы SereneDB лежат не в duckdb-storage, поэтому
дешёвого сигнала «в этой таблице что-то писали» через row-group-метаданные **нет**.
`duckdb_approx_database_count()` возвращает `1` (число баз) — к строкам отношения не имеет [вывод].

**(г) `SUMMARIZE` — есть, но не для нашей задачи.** [вывод]
`SUMMARIZE SELECT 1 AS a, 'x' AS b;` работает и отдаёт по колонке min/max/approx_unique/
null_percentage. Это профилирование колонок (могло бы заменить наш `profile_table`,
`serene_search_build.py:299`), но **не** даёт «число строк по всем таблицам».

**(д) MATERIALIZED VIEW — НЕТ.** Единственные вхождения в бинарнике 26.07.3 [вывод] —
`WHEN rel.relkind = 'm' THEN 'materialized view'::text` (просто расшифровка relkind в
`pg_catalog`) и `Cannot drop MATERIALIZED VIEW yet`. В репозитории тестов на
`CREATE MATERIALIZED VIEW` нет вовсе [код]. То есть «materialized view с REFRESH» как
штатный инкремент корпуса — **не существует**, и вывод первого прохода (оставить таблицу)
усиливается.

## 2.2. Что нашлось нового

**(е) Динамический SQL `query('<строка>')` — есть, но только из литералов.** [вывод]
```sql
SELECT * FROM query('SELECT ' || '1 AS a');   -- 1
SELECT * FROM query((SELECT 'SELECT 2 AS a'));
-- ERROR: Table function cannot contain subqueries
```
Штатный приём кукбука (`sql_features/query_and_query_table_functions.test:65-73`) —
собирать текст внутри `CREATE MACRO ... AS TABLE` из **параметров макроса**:
```sql
CREATE OR REPLACE MACRO stack(table_name, index, name, values) AS TABLE
FROM query('UNPIVOT ' || table_name || ' ON COLUMNS(* EXCLUDE (' ||
           array_to_string(index, ', ') || ')) INTO NAME ' || name || ' VALUES ' || values);
```
Практический вывод для нас: **список таблиц всё равно приходит из клиента**, но его можно
передать как параметр макроса, а не склеивать 76 КБ текста в Python. Проверить создание
макроса на живом инстансе я не мог (`CREATE MACRO` — DDL, под запретом), см. последний раздел.
`query_table('<имя>')` подтверждён рабочим [вывод] (`SELECT count(*) FROM query_table('search_corpus')` → 97965)
и штатно используется с `PREPARE ... $1` (`query_and_query_table_functions.test:12-17` [код]).

**(ж) Поиск можно JOIN-ить с обычными таблицами прямо в запросе — это меняет вопрос 7.**
Кукбук `tests/sqllogic/sdb/pg/site_docs/cookbook/search/search-with-joins.test:47-58` [код], дословно:
```sql
SELECT p.title, sum(o.amount) AS revenue, sum(o.qty) AS units
FROM products_idx p
JOIN orders o ON o.product_id = p.id
WHERE p.title @@ 'running'
GROUP BY p.title
ORDER BY revenue DESC, p.title;
```
То есть от имени индекса можно джойнить, группировать и агрегировать. Для нас это второй,
более дешёвый способ решать «переименование контрагента»: **разрешать ссылки не при сборке
корпуса, а в момент выдачи** — `FROM search_idx JOIN refmap ...`. Оговорка, которая делает
это дополнением, а не заменой: в `doc`/`refs` лежит текст, по которому строятся **термы
индекса и эмбеддинг**, поэтому старое имя всё равно останется в индексе до пересчёта строки.
Джойн на выдаче гарантирует только правильное **отображение**, а не находимость по новому имени.

**(з) `VACUUM (REFRESH_TABLE)` после записи — это не деталь, а часть штатного рецепта.**
**30 из 34** рецептов кукбука по поиску вызывают `VACUUM (REFRESH_TABLE) <t>;` сразу после
`INSERT` и до первого поискового запроса [код] (например
`cookbook/search/search-with-joins.test:31`, `one-search-box.test:39,75`,
`faceted-search.test:41`, `pagination.test:33`). У нас это уже делается — но точечно:
`ubuntu/serenedb/serene_search_build.py:915` — `VACUUM (REFRESH_INDEX) search_idx;`
с явным комментарием, почему `REFRESH_INDEX`, а не `REFRESH_TABLE`. Это **уже штатно**,
менять нечего; при переходе на один большой `MERGE` вызов надо сохранить.

**(и) Индекс поверх ATTACH-нутой базы: «видно сразу» относится к материализации, а не к новым строкам.**
`tests/sqllogic/sdb/pg/index/inverted_index_view_attached.test:1-7` [код]:
«materialization fetches rows from the live catalog entry through the caller's transaction,
so in-transaction changes to the source are visible immediately. Rows deleted in the source
after CREATE INDEX materialize as NULLs (**same contract family** … : the index pins what it
indexed)». То есть это НЕ инкрементальность: индекс по-прежнему помнит ровно тот набор
документов, который был на `CREATE INDEX`; «сразу видно» только изменение содержимого уже
проиндексированных строк при их вычитывании. Вывод первого прохода не меняется.

**(к) `postgres_scan` НЕ является fast-path источником для view-индекса.**
`server/connector/view_fast_path.cpp:140` [код]: `// TODO: read_avro, postgres_scan / postgres_query.`
Fast-path сегодня: parquet/csv/json/iceberg glob-ридеры, `read_duckdb` (ATTACH duckdb,
`view_fast_path.cpp:290-306`) и собственные таблицы SereneDB (`view_fast_path.cpp:309-320`).
Для целевой архитектуры «PG на Windows + attach» это значит: **индекс поверх вьюхи на
attach-нутую PG не сможет дочитывать не-INCLUDE колонки** — придётся класть всё в `INCLUDE`.

**(л) `postgres_query(dsn, sql)` в сборке есть** [вывод]
(`duckdb_functions()`: `postgres_query {col0, col1, params, use_transaction}`,
плюс `postgres_scan`, `postgres_scan_pushdown`, `postgres_attach`, `read_postgres_binary`).
Это даёт третий вариант для целевой архитектуры: отпечаток считается **на стороне
PostgreSQL на Windows** (`postgres_query(dsn, 'SELECT key, md5(...) FROM ...')`), и по сети
едут только пары (ключ, хеш), а не тексты. Не проверял на реальном соединении — у нас
сейчас витрина лежит в самом движке.

**(м) `json_each` / `json_tree` есть** [вывод] — альтернатива `json_keys`+`list_transform`
для разбора строки в пары. Скорость не мерил: `UNPIVOT` всё равно быстрее обоих JSON-путей.

**(н) `duckdb_indexes().sql` врёт про состав индекса.** [вывод]
```
SELECT index_name, table_name, sql FROM duckdb_indexes();
search_idx | search_corpus | CREATE INDEX search_idx ON public.search_corpus USING inverted ()
```
Скобки пустые. Настоящий DDL хранится у нас самих в `search_meta` [вывод]:
`CREATE INDEX search_idx ON search_corpus USING inverted(doc search_dict, refs search_dict, src_table) INCLUDE (src_table, row_key, amount, doc_date)`.
Вывод: **проверять «индекс тот, что нужен» по `duckdb_indexes().sql` нельзя** — наша
собственная таблица `search_meta` тут не самодеятельность, а обход дефекта интроспекции.

## 2.3. Полная сборка `refs` в SQL — замер на всей базе

Первый проход показал разрешение ссылок на одной таблице (62,9 мс). Второй проход прогнал
это по **всей базе**, generic-ом, одним запросом.

Карта `refmap` (все таблицы, у которых есть и `Ref_Key`, и `Description` — их 112 [вывод]),
собирается `UNION ALL` из `duckdb_columns()`:
```sql
SELECT count(*), count(DISTINCT nm) FROM (<112 × SELECT "Ref_Key" AS g, "Description" AS nm FROM t>);
-- 38515 | 14323        Time: 101,7 мс   [замер]
```

Разрешение ссылок по всем 226 таблицам-источникам (GUID-колонки определяются по форме
значения, список колонок нигде не задан):
```sql
WITH refmap AS (<...112 источников...>), ex AS (
  <226 × SELECT '<t>' AS src, rk, unnest(gkeys) AS col, j FROM (
     SELECT rk, j, list_filter(json_keys(j), k -> regexp_matches(coalesce(json_extract_string(j,k),''),
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        AND json_extract_string(j,k) <> '00000000-0000-0000-0000-000000000000') AS gkeys
     FROM (SELECT rowid AS rk, to_json(t) AS j FROM "<t>" t))>
)
SELECT count(*), count(DISTINCT src) FROM (
  SELECT src, rk, string_agg(ex.col || ': ' || m.nm, ' | ') AS refs
  FROM ex JOIN refmap m ON m.g = json_extract_string(ex.j, ex.col)
  GROUP BY src, rk);
-- 63524 строки с непустыми refs, 186 таблиц      Time: 2 927 мс   [замер]
```

**Итого весь «тяжёлый» такт целиком в SQL: `doc` + отпечаток 1,14 с + `refs` 2,93 с +
`refmap` 0,10 с ≈ 4,2 с, один процесс.** Сегодня та же работа — ~258 с и ~1 190 процессов
`psql`. **≈ в 60 раз по времени, в ~1 190 раз по числу процессов.** Всё измерено на нашей
живой базе 26.07.3, только `SELECT`.

## 2.4. Уточнённый список к переделке (с учётом второго прохода)

1. **`doc` собирать `UNPIVOT`-ом, а не `to_json`** (1,14 с против 1,64 с на всей базе; и то,
   и другое против ~258 с сейчас). `to_json` оставить только там, где нужен разбор значений
   по форме (детекция GUID-колонок) — там он удобнее.
2. **`refs` — JOIN на `refmap` внутри того же запроса** (2,93 с на всей базе), а не словарь
   в Python. Свойство «переименование меняет текст корпуса» сохраняется и перестаёт зависеть
   от того, попал ли справочник в такт.
3. **Отпечаток — `sha1()` в SQL**; побайтное совпадение с текущим `hashlib.sha1` проверено,
   значит миграция без перезаливки и без повторного эмбеддинга.
4. **Один `MERGE INTO ... USING (<этот запрос>) ... WHEN NOT MATCHED BY SOURCE THEN DELETE
   RETURNING merge_action, t.src_table, t.row_key`** вместо staging-таблицы, ~490 `INSERT`,
   233 `LEFT JOIN` и отдельной gone-очистки (`serene_search_build.py:853`).
   Список ключей на эмбеддинг приходит прямо из `RETURNING`.
5. **`VACUUM (REFRESH_INDEX) search_idx` сохранить** — это уже штатно и уже сделано
   (`serene_search_build.py:915`); при укрупнении транзакции его нельзя потерять.
6. **Каталог: один `duckdb_columns()` на всю базу** и один `UNION ALL` из `count(*)`
   (214 мс на 305 таблиц) вместо 466 процессов.
7. **Не идти в VIEW-корпус** — индекс над представлением статический (три независимых
   подтверждения: код, тест-«пин», строка в бинарнике 26.07.3).

## Что уже штатно и переделывать не надо

- `MERGE INTO` для записи корпуса (`serene_search_build.py:729`) — штатный механизм,
  выбран верно, и тест движка прямо оговаривает согласованность индекса при merge
  (`tests/sqllogic/sdb/pg/dml/merge.test:2`).
- `VACUUM (REFRESH_INDEX)` вместо `REFRESH_TABLE` (`serene_search_build.py:911-915`) —
  соответствует набору глаголов в `duckdb_vacuum_function.cpp:68-83`.
- Раздельные поля `doc` и `refs` в одном индексе — ровно форма demo6/кукбука
  (`examples/demo6/bootstrap.sql`, `cookbook/search/one-search-box.test`).
- Собственная таблица `search_meta` с текстом DDL индекса — вынужденно своё, потому что
  `duckdb_indexes().sql` состав индекса не отдаёт (см. п. «н»).

---

## Что я НЕ смог выяснить

1. **`RETURNING merge_action` на живом инстансе не выполнен.** Любая проверка — это DML.
   Косвенные доказательства: (а) тест `site_docs/sql/statements/merge_into/index.test:120,140`
   в репозитории; (б) строки в бинарнике 26.07.3: `Unsupported merge action for RETURNING`,
   `MergeActionType`, `MergeActionCondition`. Попытка выяснить парсером через несуществующую
   таблицу не сработала: движок сначала резолвит имя таблицы, и контрольный запрос с
   заведомо неверным `merge_actionZZZ` дал ту же ошибку `Table ... does not exist!` [вывод].
   Формат значения (строки `INSERT`/`UPDATE`/`DELETE`) взят из ожидаемого вывода теста.
2. **Сколько на самом деле стоит `CREATE INDEX` инвертированного индекса на 98 тыс. строк** —
   не измерено (создание индексов под запретом). Без этого числа нельзя точно оценить
   отвергнутый вариант «VIEW + пересоздание индекса каждые 20 минут», хотя качественно он
   проигрывает.
3. **Детерминированность порядка колонок в `UNPIVOT (... IN (COLUMNS(*)))`** — теста в
   репозитории, который бы это фиксировал, я не нашёл; вывод сделан из того, что список `IN`
   раскрывается из порядка колонок каталога, и из повторяемости результата между прогонами.
   Если порядок «поплывёт», поплывут все отпечатки разом (это заметно, но неприятно).
4. **Совпадёт ли отпечаток в SQL с текущим продовым `doc`** — нет, наверняка не совпадёт:
   продовый `doc` строится не из всех колонок, а из отфильтрованных по `$metadata`
   (`Edm.String`, исключения `STANDARD_SERVICE_PROPS`, `protocol_companion`,
   `serene_search_build.py:430-460`). Значит либо эту фильтрацию надо перенести в SQL
   (как список колонок в `EXCLUDE`, генерируемый из тех же метаданных), либо принять
   разовую полную перезаливку. Стоимость варианта не оценена.
5. **`CREATE MACRO ... AS TABLE` на живом инстансе не проверен** — это DDL.
6. **`postgres_query` на реальном соединении с PG на Windows не проверен** — функция в
   каталоге есть, но подключения не было.
7. **Не мерил параллельность**: все замеры — один клиент, база в прогретом состоянии.
   На холодном кеше цифры будут выше.

---

## Что проверить замером

Без `CREATE INDEX` (разрешено при обычном режиме работы, но всё это — запись, поэтому
делать на копии/в окне обслуживания):

```sql
-- 1. merge_action реально возвращается и содержит INSERT/UPDATE/DELETE
CREATE TABLE mtest(k TEXT PRIMARY KEY, h TEXT);
INSERT INTO mtest VALUES ('a','1'), ('b','2');
MERGE INTO mtest t USING (SELECT * FROM (VALUES ('a','1'),('c','3')) v(k,h)) s
  ON t.k = s.k
  WHEN MATCHED AND t.h <> s.h THEN UPDATE SET h = s.h
  WHEN NOT MATCHED THEN INSERT VALUES (s.k, s.h)
  WHEN NOT MATCHED BY SOURCE THEN DELETE
  RETURNING merge_action, t.k;
-- ожидание: INSERT c ; DELETE b ; строка 'a' не выдаётся (условие t.h <> s.h)

-- 2. MERGE принимает большой UNION ALL в USING (226 веток, 76 КБ текста)
--    и не деградирует на объёме — прогнать на копии корпуса.

-- 3. Детерминированность UNPIVOT: один и тот же отпечаток при 5 прогонах,
--    и после ALTER TABLE ... ADD COLUMN (ожидается изменение — это правильно).

-- 4. CREATE MACRO как способ убрать генерацию текста из Python:
CREATE OR REPLACE MACRO doc_of(table_name) AS TABLE
  FROM query('SELECT rowid AS rk, COLUMNS(*)::VARCHAR FROM ' || table_name);
SELECT * FROM doc_of('catalog_организации') LIMIT 1;

-- 5. Совпадение отпечатка с продовым: посчитать в SQL doc по тому же
--    списку колонок, что даёт split_cols(), и сверить sha1 с сохранённым
--    doc_hash по 1000 случайным строкам корпуса. Без 100% совпадения
--    переход означает полную переэмбеддировку.
```

Требует `CREATE INDEX` — **у нас под запретом, выполнять только по отдельному решению
владельца и не на рабочем инстансе**:

```sql
-- 6. Стоимость полной пересборки инвертированного индекса на 98 тыс. строк:
--    DROP INDEX search_idx; CREATE INDEX search_idx ON search_corpus
--      USING inverted(doc search_dict, refs search_dict, src_table)
--      INCLUDE (src_table, row_key, amount, doc_date);
--    Только это число закрывает вопрос «VIEW + пересоздание каждые 20 минут»
--    окончательно.

-- 7. Индекс поверх VIEW на наших данных (проверка, что generic-view с JOIN
--    вообще индексируется и что все нужные колонки достаются из INCLUDE):
--    CREATE VIEW corpus_v AS <UNION ALL + JOIN на refmap>;
--    CREATE INDEX corpus_v_idx ON corpus_v USING inverted(doc search_dict, refs search_dict)
--      INCLUDE (src_table, row_key, doc, refs, amount, doc_date);
--    ожидание по коду: сборка пройдёт, но индекс будет статическим.
```
