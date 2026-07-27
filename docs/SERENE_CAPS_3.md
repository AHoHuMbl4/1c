# Каталог возможностей SereneDB

Источники: полный клон `/srv/data/cursor/cursor/1/serenedb-src` (ветка `main`) +
живой инстанс **26.07.3** (`192.168.56.42:7890`, `PostgreSQL 18.3 (SereneDB 26.07.3)`).

Формат записи: **что делает** → **точный синтаксис** → **файл-доказательство** →
**есть ли в нашей сборке 26.07.3** (`проверено на инстансе` / `нет` / `не проверялось`).

Проверка на инстансе выполнялась только чтением (`SELECT`/`EXPLAIN`/`duckdb_*()`/
`CREATE ... (help)`-пробы, которые падают с ошибкой и ничего не создают) поверх уже
существующего индекса `search_idx` на таблице `search_corpus` (97 965 строк).

---

# 1. Общая архитектура и объекты

| Объект | Назначение |
|---|---|
| `CREATE TEXT SEARCH DICTIONARY` | токенизатор/анализатор (шаблон + опции + index-features) |
| `CREATE INDEX ... USING inverted (...)` | инвертированный индекс iresearch: текст, числа, даты, векторы, гео |
| `CREATE INDEX ... USING inverted (...) INCLUDE (...)` | колоночное хранилище внутри индекса (self-sufficient index) |
| `CREATE INDEX ... (...)` без USING / `USING btree`/`art` | вторичный ART-индекс (`secondary`) |
| индекс как таблица | `FROM <index_name>` — запрос идёт **от имени индекса**, не от таблицы |
| `es.<index>` / `es."<index>$text"` | таблицы, создаваемые ES-совместимым слоем |

**Ключевое правило формы запроса.** Оператор `@@` работает только когда слева стоит
проиндексированная колонка сканируемого индекса:
```
ERROR: @@ requires an inverted-indexed column on one side
HINT:  Use: <indexed_col> @@ <tsquery_expr>. CREATE INDEX ... USING inverted(<col>) if missing.
```
(проверено на инстансе; текст ошибки получен запросом `WHERE doc_date @@ ts_between(...)`
по колонке, которая в индексе только как INCLUDE).

---

# 2. Словари (CREATE TEXT SEARCH DICTIONARY)

## 2.1 Синтаксис и справка

```sql
CREATE TEXT SEARCH DICTIONARY <name> (
    template = '<tokenizer>',
    <опции шаблона...>,
    -- index features (общие для всех шаблонов):
    norm = <bool>, frequency = <bool>, position = <bool>, offset = <bool>,
    norm_row_group_size = <int>
);
```

**Встроенная справка**: `CREATE TEXT SEARCH DICTIONARY x (help);` — выбрасывает ошибку,
печатая полный список шаблонов и их опций.
Доказательство: `server/pg/tokenizer_options.h:419-433` (`kTokenizerSubgroups`),
`server/pg/commands/create_tsdictionary.cpp`.
**Проверено на инстансе: да** (вывод содержит все 25 шаблонов).

## 2.2 Полный список шаблонов (все присутствуют в 26.07.3)

Проверка: `strings /opt/serenedb-dist/serenedb-26.07.3-linux-amd64/usr/bin/serened` +
вывод `(help)` на инстансе.

| template | Что делает | Опции |
|---|---|---|
| `text` | ICU-токенизатор: locale, регистр, диакритика, стемминг, стоп-слова, edge-ngram | `locale`, `accent`, `stemming`, `stopwords`, `stopwordspath`, `case` (`none`/`lower`/`upper`), подгруппа edgengram: `mingram`, `maxgram`, `preserveoriginal` |
| `keyword` | значение целиком как один терм | — |
| `ngram` | скользящие n-граммы | `mingram`(2), `maxgram`(3), `preserveoriginal`(false), `inputtype` (`utf8`/`binary`), `startmarker`, `endmarker` |
| `sparse_ngram` | GitHub-code-search схема разрежённых n-грамм | `maxngramlength`(16, мин 3), `covering`(false) |
| `stem` | только стемминг | `locale` |
| `stopwords` | только фильтр стоп-слов | `stopwords`, `hex`(false) |
| `norm` | нормализация без разбиения | `locale`, `case`, `accent` |
| `collation` | бинарный ключ сортировки локали | `locale` |
| `segmentation` | сегментация по UAX#29 | `case`, `break` (`all`/`graphic`/`alpha`) |
| `delimiter` | сплит по одной строке-разделителю | `delimiter` (**required**) |
| `multi_delimiter` | сплит по списку разделителей | `delimiters` (**required**), формат `'":", ";", " "'` |
| `pattern` | RE2: сплит или извлечение | `pattern` (**required**), `group` (`-1`=split, `0`=весь матч, `N`=группа) |
| `path_hierarchy` | иерархия путей/доменов | `delimiter`('/'), `replacement`, `reverse`(false), `skip`(0), `buffersize`(1024) |
| `pipeline` | цепочка токенизаторов | `stepN_template`, `stepN_<опция>`; вложенность `step2_step1_template` |
| `union` | объединение выходов нескольких токенизаторов | `tokenizerN_template`, `tokenizerN_<опция>` |
| `copy_from` | наследование чужого словаря с переопределением опций | `from` (**required**) + любые переопределяемые опции |
| `solr_synonyms` | Solr-синонимы (двусторонние `a, b, c` и односторонние `a => b`) | `synonyms` (**required**, инлайн-текст) |
| `wordnet_synonyms` | WordNet Prolog-синсеты | `synonyms` (**required**, `s(synset,w_num,'word',ss_type,sense,tag).`) |
| `minhash` | MinHash-сигнатуры поверх вложенного токенизатора | `numhashes`(1), `tokenizer_<опция>` |
| `wildcard` | n-граммный индекс для быстрых `ts_like` | `ngramsize`(3, мин 2), `tokenizer_<опция>` |
| `classification` | fastText-классификатор → метки как термы | `modellocation`, `topk`(1), `threshold`(0.0) |
| `nearest_neighbors` | fastText kNN по словам | `modellocation`, `topk`(1) |
| `geopoint` | S2-ячейки из JSON `{lat,lng}` или `[lat,lng]` | `latitude`, `longitude`, `maxcells`(20), `minlevel`(4), `maxlevel`(23), `levelmod`(1), `optimizeforspace` |
| `geojson` | S2-ячейки из GeoJSON/GEOMETRY | `type` (`shape`/`centroid`/`point`), `coding` (`source`/`s2point`/`s2latlngf64`/`s2latlngu32`) + те же S2-опции |

Доказательство опций: `server/pg/tokenizer_options.h:63-292` (описания), `:243-291`
(наборы опций на шаблон), `server/pg/geo_tokenizer_options.h`.
Примеры на каждый шаблон:
`tests/sqllogic/sdb/pg/site_docs/sql/statements/create_text_search_dictionary/*.test`.

**Проверено на инстансе: да** — все 25 шаблонов перечислены в выводе `(help)`.

## 2.3 Index features (влияют на то, что вообще можно спросить)

| Опция | Что включает | Без неё не работает |
|---|---|---|
| `frequency = true` | частоты термов | BM25/TFIDF/LM/DFI, `ts_dict_freq` |
| `position = true` | позиции | `ts_phrase` из >1 слова, `##`, слоп, `phraseto_tsquery` |
| `norm = true` | длина документа | нормализация длины в BM25, `raw_dl` |
| `offset = true` | байтовые смещения | `ts_offsets`, `ts_highlight` по колонке индекса |

Доказательство: `server/pg/tokenizer_options.h:63-76`; `examples/demo0/demo.sql:26-37`;
`examples/demo3/demo.sql:27-37` (`offset = true` для подсветки).
**Проверено на инстансе: да** — `ts_offsets(doc)` и `ts_highlight(doc)` работают на
`search_idx` (значит `search_dict` создан с `offset = true`).

## 2.4 Примеры точного синтаксиса (все из тестов)

```sql
-- pipeline: сплит по запятой → lower → стемминг
CREATE TEXT SEARCH DICTIONARY pipe_delim_stem (
    template = 'pipeline',
    STEP1_TEMPLATE = 'delimiter', STEP1_DELIMITER = ',',
    STEP2_TEMPLATE = 'text', STEP2_LOCALE = 'en_US.UTF-8',
    STEP2_CASE = 'lower', STEP2_STEMMING = true);
-- ts_lexize('pipe_delim_stem','Cats,RUNNING') -> {cat,run}

-- union: verbatim + 2-граммы одновременно
CREATE TEXT SEARCH DICTIONARY union_dict (
    template = 'union',
    TOKENIZER1_TEMPLATE = 'keyword',
    TOKENIZER2_TEMPLATE = 'ngram', TOKENIZER2_MINGRAM = 2, TOKENIZER2_MAXGRAM = 2);
-- ts_lexize('union_dict','abcd') -> {abcd,ab,bc,cd}

-- copy_from: тот же словарь, но без стемминга
CREATE TEXT SEARCH DICTIONARY english_no_stem (
    template = 'copy_from', from = 'english_dict', stemming = false);

-- синонимы (Solr)
CREATE TEXT SEARCH DICTIONARY syn (
    template = 'pipeline',
    step1_template = 'text', step1_locale = 'en_US.UTF-8', step1_case = 'lower',
    step1_stemming = false,
    step2_template = 'solr_synonyms',
    step2_synonyms = 'tv, television, telly
laptop => notebook',
    frequency = true, position = true);
```
Доказательства: `.../create_text_search_dictionary/pipeline/index.test:76-100`,
`.../union.test:1-20`, `.../copy-from.test:20-35`,
`.../cookbook/search/synonyms.test:5-20`.

## 2.5 `ts_lexize` — посмотреть, что реально попадёт в индекс

```sql
SELECT ts_lexize('<dict>', '<text>');            -- -> VARCHAR[]
SELECT ts_lexize('<dict>', ARRAY['a','b']);      -- вторая перегрузка
```
Доказательство: `tests/.../site_docs/sql/indexes/inverted/text-analysis.test`.
**Проверено на инстансе: да** —
`ts_lexize('search_dict','Проверка Регистра Тест') -> {проверка,регистра,тест}`,
`ts_lexize('bench_dict', ...) -> {Проверка,Регистра,Тест}` (регистр сохранён).

---

# 3. CREATE INDEX ... USING inverted

## 3.1 Грамматика

```
CREATE INDEX <name> ON <table|view>
  USING inverted ( <элемент> [, ...] )
  [ INCLUDE ( <колонка> [ included ( <опции> ) ] [, ...] ) ]
  [ WITH ( <опция> = <литерал> [, ...] ) ]
  [ WHERE <предикат> ]                        -- частичный индекс

<элемент> := <колонка> | (<выражение>)  [ <opclass> [ ( <опции> ) ] ]
```
Из бинарника (`strings ... | grep opclass`):
```
IndexElement    <- Expression IndexOpclass? DescOrAsc? NullsFirstOrLast?
IncludedColumn  <- ColId IndexOpclass?
IndexOpclass    <- Identifier ('.' Identifier)? IndexOpclassOptions?
IndexOpclassOptions <- Parens(List(IndexOpclassOption)?)
```

## 3.2 Опклассы

| Опкласс | Назначение | В 26.07.3 |
|---|---|---|
| `<имя словаря>` | текстовый анализатор для колонки | да |
| `ivf` | векторный ANN (IVF + квантизация) | **да** |
| `hnsw` | графовый ANN | **НЕТ** (см. §14) |
| `included` | параметры хранения INCLUDE-колонки | да |

Доказательство: `server/catalog/index.h:40-41` (`kIncludedKind="included"`,
`kIVFKind="ivf"`), `server/catalog/index.cpp:110-113` (`kKnownOpclassTypes`).

### `ivf (...)`
```sql
CREATE INDEX i ON t USING inverted (id, emb ivf (metric = 'l2'));
CREATE INDEX i ON t USING inverted (emb ivf (metric='cosine', quant='sq4'));
```
| Опция | Значения | Дефолт |
|---|---|---|
| `metric` **(обязательна)** | `l2`, `l1`, `cosine`, `ip` | — |
| `quant` | `sq8`, `sq4`, `pq`, `rabitq`, `none` | `sq8` для `l2`/`ip`/`cosine`, `none` для `l1` |
| `pq_m` | int ≥ 1, делит размерность; только `quant='pq'` | авто ≈ d/2 |
| `rabitq_bits` | только `quant='rabitq'` (не сочетается с `cosine`) | минимум |
| `compression` | bool; `false` — вектора без сжатия (быстрее, больше диска) | true |

Доказательство: `server/catalog/index.cpp:55-68` (литералы), `:240-260`
(`DescribeIVFOptions`), `:305-400` (валидация).
Тип колонки обязан быть `ARRAY(FLOAT, N)` (`FLOAT[1536]`), иначе:
`'...' must be ARRAY(FLOAT, N) to use the 'ivf' opclass, not ...` (строка в бинарнике).
**Проверено на инстансе: строки ошибок ivf присутствуют в бинарнике; индекс не создавался
(запрещено заданием).**

### `included (...)` на INCLUDE-колонках
```sql
CREATE INDEX i ON t USING inverted (body en)
INCLUDE (v included (hyperloglog = true),
         big_int included (compression = 'uncompressed'),
         plain);
```
| Опция | Значения | Дефолт |
|---|---|---|
| `compression` | `auto`, `uncompressed`, `rle`, `bitpacking`, `zstd`, `alp`, `alprd`, `roaring`, `dict_fsst` | `auto` |
| `hyperloglog` | bool — считать NDV в HLL, отдаётся оптимизатору как `approx_unique` | false |

Доказательство: `server/catalog/index.cpp:138-178` (`ParseCompressionName`),
`:520-545` (`ApplyIncludedOpclass`);
тесты `tests/.../index/inverted_index_hyperloglog_option.test:20-45`,
`inverted_index_compression_option.test:20-45`.
**Не проверялось на инстансе** (нужен CREATE INDEX).

## 3.3 `WITH (...)` — опции индекса

Полный список из `server/connector/inverted_index_options_util.h:42-76`:

| Опция | Тип | Дефолт | ALTER INDEX SET |
|---|---|---|---|
| `row_group_size` | uint32 | 122880 | нет (create-only) |
| `norm_row_group_size` | uint32 | 122880 | нет |
| `refresh_interval` | uint32 мс | 1000 (0 = выкл) | **да** |
| `compaction_interval` | uint32 мс | 1000 (0 = выкл) | **да** |
| `cleanup_interval_step` | uint32 тиков | 1 (0 = выкл) | **да** |
| `segment_memory_max` | uint64 байт | 268435456 | **да** |
| `segment_docs_max` | uint32 | 0 = ∞ | **да** |
| `compaction_max_segments` | uint32 | 10 | **да** |
| `compaction_max_segments_bytes` | uint64 | 5368709120 | **да** |
| `compaction_floor_segment_bytes` | uint64 | 2097152 | **да** |
| `optimize_top_k` | строка-скорер, напр. `'bm25(1.2, 0.75)'`, `'tfidf()'`, `'raw_tf()'` | выкл | нет |
| `store_pk` | `'none'`/`'auto'`/`'i64'`/`'i64i64'` (или `true`≡auto / `false`≡none) | auto | нет |

Явный `0` отвергается для всех числовых опций, кроме `segment_docs_max`,
`refresh_interval`, `compaction_interval`, `cleanup_interval_step`
(`inverted_index_options_util.h:92-100`).

```sql
CREATE INDEX i ON t USING inverted(label)
  WITH (segment_memory_max = 67108864, segment_docs_max = 5000,
        compaction_max_segments = 4);
ALTER INDEX i SET (refresh_interval = 250, compaction_interval = 500);
ALTER INDEX i RESET (segment_memory_max);
```
Опции видны как `pg_class.reloptions`, метод — через `relam -> pg_am.amname`.
Доказательство: `tests/.../index/inverted_index_options.test:24-120`.
**Проверено на инстансе: да** — `search_idx` имеет `amname = inverted` и полный
`reloptions` со всеми 10 числовыми опциями (значения дефолтные).

`store_pk = 'none'` — индекс не хранит PK строк; тогда:
* `DELETE`/`UPDATE` по таблице невозможны («drop the index first»),
* из индекса можно выбирать только INCLUDE-колонки, счётчики и скоры.
Доказательство: строки бинарника + `tests/.../index/inverted_index_store_pk.test:40-60`.

## 3.4 Частичный индекс

```sql
CREATE INDEX pt_live ON t USING inverted(label) WHERE live;
```
Только для inverted (`partial indexes are only supported for inverted indexes`,
`server/connector/duckdb_catalog.cpp:1056-1062`). NULL-предикат = false.
Доказательство: `tests/.../index/inverted_index_partial.test:1-45`.

## 3.5 Индексируемые выражения

```sql
CREATE INDEX i ON t USING inverted (id, (lower(name)), (first || ' ' || last),
                                    (CASE WHEN amount >= 100 THEN 'big' ELSE 'small' END));
-- запрос повторяет выражение дословно:
SELECT id FROM i WHERE lower(name) @@ 'widget';
```
Запрещены: агрегаты (`aggregate functions are not allowed in index expressions`) и
side-effect-выражения (`Index keys cannot contain expressions with side effects.`).
Доказательство: `tests/.../site_docs/sql/indexes/inverted/modeling.test:1-40, 70-95`;
`tests/.../cookbook/search/computed-values.test`.

## 3.6 Типы колонок

**Индексируемые ключи:** VARCHAR, BLOB, LIST/ARRAY of VARCHAR|BLOB (с токенизатором);
TINYINT/SMALLINT/INTEGER/BIGINT, UTINYINT/USMALLINT/UINTEGER, FLOAT/DOUBLE,
BOOLEAN, DATE/TIME/TIMESTAMP/TIMESTAMPTZ, INET, JSON/VARIANT-выражения,
GEOMETRY/JSON (только с гео-анализатором).
**Отвергаются как ключи:** HUGEINT, UHUGEINT, UBIGINT, DECIMAL(p,s), UUID, INTERVAL, BIT
(`Column 'x' has unsupported type ... and can not be indexed`).
**INCLUDE-колонки принимают всё**, включая перечисленные выше отвергаемые типы
и вложенные STRUCT/LIST/MAP/UNION/VARIANT.

Доказательство: `tests/.../index/inverted_index_unsupported_numeric.test:1-40`,
`inverted_index_include_types.test:1-45`, `inverted_index_matrix_*.test` (21 файл матрицы),
`inverted_index_matrix_validator.test:15-60`.

## 3.7 Индекс поверх VIEW (Zero-ETL)

```sql
CREATE VIEW v AS SELECT * FROM read_parquet('hf://datasets/.../*.parquet');
CREATE INDEX v_idx ON v USING inverted (text en, label);
```
* PK автоматически выводится как `(file_index, file_row_number)`.
* `count(*)`, скоры, ANN-дистанции — чистое чтение индекса, к источнику не ходим.
* Материализация «настоящих» колонок работает только для fast-path источников
  (`read_parquet/read_csv/read_json/read_text/...` с одним строковым литералом);
  иначе: `materialising real columns from this view-backed inverted index is not yet
  supported — view body must be a simple SELECT * FROM <reader>(literal_args) ...`.
* `INCLUDE (все нужные колонки)` делает индекс самодостаточным — после сборки источник
  не нужен вовсе (паттерн demo6).
* Plain (`secondary`) индексы на view запрещены.

Доказательство: `examples/demo0/demo.sql:41-57`, `examples/demo6/bootstrap.sql:70-131`,
`examples/demo4/bootstrap_view.sql:12-24`,
`tests/.../site_docs/sql/indexes/inverted/views.test`,
`server/connector/duckdb_catalog.cpp:1064-1070`.

Совет из demo6: **не использовать `row_number() OVER ()`** для генерации id — глобальное
оконное выражение сериализует весь конвейер в один поток; натуральный ключ даёт
параллельную сборку (17× на 11.5 млн строк). `examples/demo6/README.md:356-363`.

## 3.8 Онлайн-сборка, обслуживание

* Индекс строится онлайн, конкурентный DML допускается
  (`tests/sqllogic/recovery/online_create_index_concurrent_dml.test`).
* `EXPLAIN CREATE INDEX ...` показывает план бэкфилла.
* Фоновые задачи: refresh (видимость), compaction (слияние сегментов), cleanup.

---

# 4. Полнотекстовый поиск

## 4.1 Оператор и базовые формы

```sql
SELECT ... FROM <index> WHERE <indexed_col> @@ <tsquery>;
SELECT ... FROM <index> WHERE <indexed_col> @@ 'слово';   -- неявный каст в tsquery
```

## 4.2 Все конструкторы `tsquery` (проверены на инстансе)

| Функция | Сигнатура | Что делает |
|---|---|---|
| `ts_phrase(t)` | VARCHAR\|BLOB → TSQUERY | фраза (несколько слов = точная последовательность) |
| `ts_starts_with(p)` | VARCHAR\|BLOB | префикс |
| `ts_like(p)` | VARCHAR\|BLOB | wildcard `%`/`_`, экранирование `\_` |
| `ts_regexp(re)` / `ts_regexp(re, flags)` | | RE2 по термам |
| `ts_levenshtein(t)` / `(t,d)` / `(t,d,transpositions)` / `(t,d,transp,prefix)` | | фаззи; `transpositions=false` выключает перестановки; 4-й аргумент — обязательный точный префикс |
| `ts_ngram(t)` / `ts_ngram(t, threshold)` | | Jaccard по n-граммам (нужен `ngram`-словарь) |
| `ts_tokenize(t[, dict])`, `ts_tokenize(ARRAY[...][, dict])` | → TSQUERY / TSQUERY[] | токенизировать строку(и) указанным словарём |
| `ts_any(arr)` / `ts_any(arr, k)` | TSQUERY[] | «хотя бы k из» (terms-set) |
| `ts_all(arr)` | TSQUERY[] | конъюнкция |
| `ts_compound(must, must_not, should[, min_should])` | TSQUERY\|TSQUERY[] ×3 (+INTEGER) | ES-подобный bool: must / must_not / should |
| `ts_between(lo, hi, incl_lo, incl_hi)` | ANY,ANY,BOOL,BOOL | диапазон по индексированной колонке |
| `ts_lt/ts_le/ts_gt/ts_ge(v)` | ANY | односторонние диапазоны (числа, даты, строки) |
| `tsquery_phrase(a, b[, slop])` | TSQUERY,TSQUERY[,INT] | фраза из двух подзапросов со слопом |

**Проверено на инстансе: да** — все перечисленные имена и сигнатуры присутствуют в
`duckdb_functions()`; `ts_phrase/ts_starts_with/ts_like/ts_levenshtein/ts_any/ts_all/
ts_compound/tsquery_phrase` выполнены на `search_idx` и вернули результаты.
`ts_regexp('дог.вор')` вернул 0 — регулярка применяется к **термам** словаря, не к тексту.

## 4.3 Операторы tsquery

| Оператор | Смысл | Пример |
|---|---|---|
| `&&` | AND | `text @@ (ts_phrase('a') && ts_phrase('b'))` |
| `\|\|` | OR | `text @@ ('a'::tsquery \|\| 'b'::tsquery)` |
| `!!` | NOT (унарный) | `text @@ (ts_phrase('a') && !!ts_phrase('b'))` |
| `^ N` | буст скора | `text @@ (('a'::tsquery ^ 5.0) \|\| 'b'::tsquery)` |
| `##` | фраза-цепочка из разнородных частей | см. ниже |

```sql
-- ## со слопом: целое = ровно N токенов между, ARRAY[min,max] = окно
WHERE text @@ ('quick' ## 'brown')                 -- смежные
WHERE text @@ ('quick' ## 1 ## 'fox')              -- ровно 1 токен между
WHERE text @@ ('quick' ## [0, 2] ## 'fox')         -- 0..2 токена
-- допустимые части ##: 'слово', ts_starts_with, ts_like, ts_levenshtein,
--                      ts_phrase, ts_any, ts_between
WHERE text @@ ( ts_levenshtein('tarintino', 2)
                ## ARRAY[1,5] ## ts_starts_with('direct')
                ## ARRAY[0,8] ## 'film' )
```
Доказательство: `examples/demo3/demo.sql:177-203`,
`tests/.../site_docs/sql/indexes/inverted/full-text-search.test:160-200`.
**Проверено на инстансе: да** (`('договор' ## [0,3] ## 'поставки')` → 157 строк).

Буст масштабирует BM25-вклад всех форм: фразы, булевых групп, автоматных
(fuzzy/wildcard/regexp). Доказательство: `tests/.../index/boost_score.test:1-60`.

## 4.4 Фраза со слопом через `ts_phrase`

```sql
WHERE text @@ ts_phrase('plot', ARRAY[0,3], 'twist')
```
Доказательство: `examples/demo3/demo.sql:66-69`.
**Проверено на инстансе: да** — `doc @@ ts_phrase('договор', ARRAY[0,3], 'поставки')`
вернул 157 строк, ровно столько же, сколько `doc @@ ('договор' ## [0,3] ## 'поставки')`.
Обратите внимание: в `duckdb_functions()` видна только одноаргументная перегрузка
`ts_phrase(VARCHAR)` — вариадическую форму разбирает биндер, её отсутствие в каталоге
функций ни о чём не говорит.

## 4.5 Парсеры пользовательских строк

| Функция | Синтаксис входа | Проверено на инстансе |
|---|---|---|
| `plainto_tsquery(s)` | все слова через AND | **да** (157) |
| `phraseto_tsquery(s)` | все слова как фраза | **да** (157) |
| `websearch_to_tsquery(s)` | Google-стиль: `"фраза"`, `OR`, `-минус` | **да** (`'"договор поставки" -счет'` → 67) |
| `to_tsquery(s)` | **Lucene**: `AND/OR/NOT`, `+/-`, `field:term`, `prefix*`, `~N` fuzzy, `^N` boost, `[a TO b]` | **да** |

Точный текст подсказки движка:
```
HINT: Example: to_tsquery('field:foo AND bar*').
      Lucene syntax: AND/OR/NOT, +/-, prefix/wildcard/regex, ranges, ^N, ~N.
```
**Важная особенность (проверено на инстансе):** `to_tsquery` — Lucene-парсер, и
нецитированные кириллические термы он не принимает (`syntax error`). Работает
`to_tsquery('"договор" AND "поставки"')` → 157. Также при указании поля вне текущей
колонки: `field-prefix in strict-field mode must match the default field`.
`websearch_to_tsquery` и `plainto_tsquery` кириллицу принимают без кавычек.

Доказательство синтаксиса: `examples/demo3/demo.sql:83-86`,
`tests/.../site_docs/sql/functions/full_text_search.test` (`to_tsquery_lucene`:
`to_tsquery('+fox -red')`).

## 4.6 Булевы функции-предикаты (без `@@`)

| Функция | Сигнатура |
|---|---|
| `phrase_matches(col, 'a b')` | ANY,VARCHAR → BOOLEAN |
| `ngram_matches(col, 't'[, threshold])` | ANY,VARCHAR[,DOUBLE] |
| `levenshtein_matches(col, 't', d[, transp[, prefix]])` | ANY,VARCHAR,INT[,BOOL[,VARCHAR]] |
| `has_all_tokens(col, ARRAY[...])` | ANY,VARCHAR[] |
| `has_any_tokens(col, ARRAY[...][, k])` | ANY,VARCHAR[]\|VARCHAR[,INT] |

**Проверено на инстансе: да** (все есть; `phrase_matches(doc,'договор поставки')` → 157,
`has_any_tokens(doc, ARRAY['договор','счет'], 2)` → 103,
`levenshtein_matches(doc,'договор',1)` → 2055).

## 4.7 Прямые предикаты по индексу

Работают и обычные SQL-сравнения на индексированных и INCLUDE-колонках:
```sql
SELECT count(*) FROM search_idx WHERE amount > 1000;             -- 941
SELECT count(*) FROM search_idx WHERE doc_date >= TIMESTAMP '2024-01-01';  -- 2929
SELECT id FROM idx WHERE dual IS NULL;                            -- null-marker term
SELECT id FROM idx WHERE NOT (genre @@ 'sci-fi');                 -- корректная 3VL
```
Три-значная логика реализована аккуратно (guard-конъюнкты IS NOT NULL при отрицании).
Доказательство: `tests/.../index/null_semantics.test:1-50`.
**Проверено на инстансе: да** (числовой и датный предикаты по INCLUDE-колонкам).

---

# 5. Ранжирование

## 5.1 Все скореры

| Функция | Аргументы | Смысл |
|---|---|---|
| `bm25(idx.tableoid)` / `bm25(t, k1, b)` | DOUBLE,DOUBLE | BM25; `b=0` → BM15 (без нормализации длины) |
| `tfidf(idx.tableoid)` / `tfidf(t, with_norms)` | BOOLEAN | классический TF-IDF |
| `lm_jm(t[, lambda])` | DOUBLE | языковая модель Jelinek–Mercer |
| `lm_dirichlet(t[, mu])` | DOUBLE | языковая модель Dirichlet |
| `indri_dirichlet(t[, mu])` | DOUBLE | Indri-вариант Dirichlet (лог-скор) |
| `dfi(t)` / `dfi(t, measure)` | VARCHAR | Divergence From Independence; measure ∈ `standardized`, `saturated`, `chi_squared` |
| `raw_tf(t)` | — | сырая частота терма |
| `raw_boost(t)` | — | накопленный буст |
| `raw_dl(t)` | — | длина документа |

**Проверено на инстансе: да** — все 9 присутствуют в `duckdb_functions()`; на `search_idx`
выполнены `bm25`, `bm25(t,1.2,0.0)`, `tfidf`, `lm_jm`, `lm_dirichlet`, `indri_dirichlet`,
`dfi`, `raw_dl`.
Список measure для `dfi` получен из ошибки движка:
`Unknown dfi measure 'chisquared'  HINT: Expected one of: standardized, saturated, chi_squared`.

Доказательство: `tests/.../site_docs/sql/functions/full_text_search.test`
(секции `bm25`…`raw_dl`), `examples/demo3/demo.sql:125-143`.

## 5.2 Жёсткое ограничение: один скорер на индекс на запрос

```
ERROR: Only one scorer function is allowed per inverted index
HINT:  Use UNION to combine different score functions for the same inverted index
```
**Проверено на инстансе: да.** Нельзя в одном SELECT посчитать и BM25, и TFIDF по
одному индексу — только через `UNION`/подзапросы.

## 5.3 Форма вызова

Аргумент скорера — `<alias>.tableoid` того самого индекса:
```sql
SELECT id, BM25(movies_idx.tableoid) AS relevance
FROM movies_idx WHERE description @@ ts_phrase('alien')
ORDER BY relevance DESC;
-- с алиасом:
FROM dbpedia_idx d ... ORDER BY BM25(d.tableoid) DESC
```
Вне контекста индекса: `Inverted index function called outside inverted index context.`

## 5.4 Комбинирование скора с колонками (recency / popularity / pinning)

```sql
ORDER BY BM25(idx.tableoid) * popularity DESC              -- популярность
ORDER BY BM25(idx.tableoid) * (1.0/(1+age_days)) DESC      -- свежесть
ORDER BY BM25(idx.tableoid) * (pop/(pop+10)) DESC          -- насыщение
ORDER BY CASE WHEN id IN (2,5) THEN 0 ELSE 1 END,          -- закреплённые
         BM25(idx.tableoid) DESC, id
ORDER BY array_position(ARRAY[5,2,7], id) NULLS LAST,      -- явный порядок пинов
         BM25(idx.tableoid) DESC
```
Доказательство: `tests/.../cookbook/search/recency-and-decay.test`,
`boosting.test:80-110`, `pinned-results.test:40-97`.

## 5.5 Reciprocal Rank Fusion (RRF) — гибрид лексики и вектора

```sql
WITH fused AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY s DESC) AS rank FROM (
      SELECT id, BM25(idx.tableoid) AS s FROM idx WHERE name @@ 'running'
      ORDER BY s DESC LIMIT 100) lex
  UNION ALL
  SELECT id, ROW_NUMBER() OVER (ORDER BY dist) AS rank FROM (
      SELECT id, emb <-> [1.0,0.0,0.0]::FLOAT[3] AS dist FROM idx
      ORDER BY dist LIMIT 100) vec
)
SELECT id FROM fused GROUP BY id
ORDER BY SUM(1.0 / (60 + rank)) DESC, id LIMIT 4;
```
Доказательство: `tests/.../cookbook/search/hybrid-search.test:60-105`,
`reciprocal-rank-fusion.test`.

## 5.6 WAND / Block-Max top-K

`WITH (optimize_top_k = '<scorer-expr>')` включает запись per-block max-impact.
Срабатывает, если:
* запрос вида `WHERE <filter> ORDER BY <scorer>(idx.tableoid) DESC LIMIT k`,
* скорер запроса **совпадает** со скорером в `optimize_top_k`,
* фильтр компилируется в итератор с max-impact: одиночный Term или ByTerms
  (`ts_any([...])`).

`EXPLAIN` печатает `Top: k, optimized`. Выключатель — `SET sdb_disable_top_k_optimization = true`.
Доказательство: `tests/.../index/inverted_index_wand.test:1-20`,
`inverted_index_optimize_top_k.test:1-20`, `server/catalog/scorer_options.cpp:200-260`.
**В сборке: да** (`sdb_disable_top_k_optimization` есть в `duckdb_settings()`);
`optimize_top_k` на нашем индексе не задан.

---

# 6. Подсветка и смещения

| Функция | Сигнатура | Смысл |
|---|---|---|
| `ts_offsets(col)` | ANY → INTEGER[] | байтовые пары [start,end] всех совпадений |
| `ts_offsets(col, n)` | ANY,INT | ограничить n |
| `ts_offsets(dict, text, tsquery[, n])` | VARCHAR,VARCHAR,TSQUERY[,INT] | автономно, без индекса |
| `ts_highlight(col)` | ANY → VARCHAR | сниппет с `<b>…</b>` |
| `ts_highlight(col, opts)` | ANY,VARCHAR | опции |
| `ts_highlight(text, offsets[, opts])` | VARCHAR,INTEGER[][,VARCHAR] | чистая функция по готовым смещениям |
| `ts_highlight(dict, text, tsquery[, opts])` | | автономно |

Опции (строка вида `'Key=Value, Key=Value'`):
`StartSel=`, `StopSel=`, `MaxWords=`, `MaxFragments=`, `HighlightAll=true`.

```sql
SELECT id, ts_highlight(body) FROM articles_idx WHERE body @@ 'search';
SELECT id, ts_highlight(body, 'StartSel=<mark>, StopSel=</mark>') FROM ...;
SELECT ts_highlight(body, 'MaxWords=9') FROM ...;
SELECT ts_highlight('A quick fox runs. Slow turtle naps. Another quick fox.',
                    ARRAY[2,7,8,11,44,49,50,53], 'MaxFragments=2');
-- -> 'A <b>quick fox</b> runs ... Another <b>quick fox</b>'
SELECT id, ts_highlight(body, ts_offsets(body)) FROM passages_idx WHERE ...;
```
Требуется `offset = true` в словаре.
Доказательство: `tests/.../cookbook/search/highlighting.test:1-124`,
`tests/.../index/headline.test:1-60`,
`tests/.../site_docs/sql/functions/full_text_search.test` (секции `ts_highlight_*`).
**Проверено на инстансе: да** — `ts_highlight(doc)` на `search_idx` вернул
`... Трудовой <b>договор</b> с работником ...`; `ts_offsets(doc)` → `{188,202}`;
опции `StartSel/StopSel` и `MaxFragments=2` работают;
`ts_offsets('search_dict','the quick brown fox','quick'::TSQUERY)` → `{4,9}`.

---

# 7. Словарь термов (term dictionary) — фасеты, автодополнение, статистика

## 7.1 Явные агрегаты

| Функция | Возврат | Смысл |
|---|---|---|
| `ts_dict_agg(col)` | VARCHAR[] | все живые термы поля |
| `ts_dict_raw_agg(col)` | BLOB[] | те же термы в сырых байтах |
| `ts_dict_count(col)` | INTEGER[] | число документов на терм (позиционно выровнено) |
| `ts_dict_freq(col)` | BIGINT[] | суммарная частота терма |
| `ts_dict_score(col)` | FLOAT[] | скор терма (например similarity при `ts_levenshtein`) |
| `ts_dict_min(col)` / `ts_dict_max(col)` | VARCHAR | лексикографический min/max терма |

```sql
-- фасет по колонке
SELECT unnest(ts_dict_agg(category)) AS category,
       unnest(ts_dict_count(category)) AS n
FROM products_idx WHERE title @@ 'running' ORDER BY n DESC;

-- tag cloud по частотам
SELECT unnest(ts_dict_agg(body)) AS term, unnest(ts_dict_freq(body)) AS mentions
FROM posts_idx ORDER BY mentions DESC;

-- автодополнение (keyword-словарь + LIKE по термам)
SELECT unnest(ts_dict_agg(query)) AS suggestion,
       unnest(ts_dict_count(query)) AS searches
FROM searches_idx WHERE query LIKE 'run%' ORDER BY searches DESC LIMIT 10;

-- исправление опечаток: similarity из ts_dict_score
SELECT unnest(ts_dict_agg(term))   AS suggestion,
       unnest(ts_dict_score(term)) AS similarity,
       unnest(ts_dict_count(term)) AS searches
FROM query_log_idx WHERE term @@ ts_levenshtein('jaket', 2)
ORDER BY similarity DESC, searches DESC;

-- significant terms (lift к фону) — два term-скана + JOIN
```
Доказательство: `tests/.../index/ts_dict.test:38-100`,
`cookbook/search/faceted-search.test:58-110`, `tag-cloud.test`, `autocomplete.test`,
`spell-correction.test`, `significant-terms.test:41-118`, `saved-searches.test`.
**Проверено на инстансе: да** —
`SELECT unnest(ts_dict_agg(doc)), unnest(ts_dict_count(doc)) FROM search_idx ...` работает,
`ts_dict_min/ts_dict_max` работают, `ts_dict_score` при `ts_levenshtein` работает.

## 7.2 Неявные перезаписи (движок сам берёт из словаря термов)

Следующие запросы к индексу планируются как **term scan** (`EXPLAIN` показывает
`TsDict: <col>` внутри `IRESEARCH_SCAN`), а не как скан документов:

| SQL | Условие срабатывания |
|---|---|
| `SELECT col, count(*) FROM idx GROUP BY col` | col — keyword-колонка/выражение |
| `count(DISTINCT col)`, `min(col)`, `max(col)`, `array_agg(DISTINCT col)` | VARCHAR-колонка |
| `GROUP BY GROUPING SETS ((a),(b),(c))` | одиночные keyword-ключи, максимум один nullable |
| фильтр `WHERE ... @@ ...` / `WHERE col LIKE 'p%'` | конъюнкты, которые движок умеет заявить |

NULL-группа синтезируется из null-marker поля. Удаления учитываются точно.
Доказательство: `tests/.../index/ts_dict_facets.test:8-30` (спецификация в комментарии),
`ts_dict_minmax_count.test`, `ts_dict_cartesian.test`.
**Проверено на инстансе: да** —
`EXPLAIN SELECT src_table, count(*) FROM search_idx GROUP BY src_table`
даёт `IRESEARCH_SCAN … TsDict: src_table`, а не скан документов.

## 7.3 Композиция условий над словарём

Один предикат на поле; булеву композицию делает пользователь через `UNION`/`INTERSECT`/
`EXCEPT` над `unnest(ts_dict_agg(...))`.
Доказательство: `tests/.../index/ts_dict_compose.test:1-60`.

---

# 8. Агрегация и статистика из индекса

* Любые SQL-агрегаты поверх `FROM <index>`: `count`, `sum`, `avg`, `min`, `max`,
  `approx_quantile`, `approx_count_distinct`, `count(DISTINCT ...)`, `GROUP BY`, `HAVING`,
  оконные функции, `QUALIFY`, `JOIN` между индексами.
* `SUMMARIZE <index>` и `SUMMARIZE SELECT ... FROM <index>` — min/max/approx_unique/avg/
  std/q25/q50/q75/count/null_percentage по всем колонкам.
* `stats(col)` — структура статистик колонки (`(stats(v)).approx_unique`, `.min`, `.max`),
  `approx_unique` появляется только при `included (hyperloglog = true)`.
* Статистики min/max с INCLUDE-колонок доходят до оптимизатора (например, `sum` →
  `sum_no_overflow`, если границы доказывают отсутствие переполнения).

```sql
SELECT lang, count(*), min(time_ms),
       round(approx_quantile(time_ms, 0.5)) AS p50, min(code_len)
FROM solutions_idx WHERE task_id = '4/A' GROUP BY lang ORDER BY 2 DESC;

SELECT s.task_id, t.title, count(*) AS n,
       round(approx_quantile(s.time_ms, 0.5)) AS p50_ms, max(s.time_ms)
FROM solutions_idx s JOIN tasks_idx t ON t.id = s.task_id
GROUP BY s.task_id, t.title HAVING count(*) >= 10 ORDER BY p50_ms DESC LIMIT 10;
```
Доказательство: `examples/demo6/demo.sql:62-96`,
`tests/.../index/inverted_index_summarize.test:1-60`,
`inverted_index_statistics.test:1-60`, `cookbook/search/result-cardinality.test`.
**Проверено на инстансе: да** — `SUMMARIZE SELECT amount FROM search_idx` вернул полный
профиль по 97 965 строкам; `approx_quantile(amount, 0.5)` = 809.07;
`approx_count_distinct(src_table)` = 232; `(stats(amount)).min` = 0.0.

---

# 9. Векторный поиск

## 9.1 Операторы дистанции

| Оператор | Метрика | Функция-эквивалент |
|---|---|---|
| `<->` | L2 | `l2_distance` |
| `<+>` | L1 | `l1_distance` |
| `<=>` | cosine | `cosine_distance` |
| `<#>` | negative inner product | `negative_inner_product` |

Скалярные функции (все проверены на инстансе):
`l2_distance`, `l2_sqr_distance`, `l1_distance`, `cosine_distance`, `cosine_similarity`,
`inner_product`, `negative_inner_product`, `l2_norm`, `l1_norm`, `l2_normalize`,
`l1_normalize` — перегрузки для `FLOAT[ANY]` и `DOUBLE[ANY]`.

## 9.2 Формы запросов

```sql
-- top-K ANN
SELECT id FROM idx ORDER BY emb <-> [0,0,0]::FLOAT[3] LIMIT 5;
-- range search
SELECT id FROM idx WHERE emb <-> [0,0,0]::FLOAT[3] < 100;
-- гибрид: текстовый фильтр + векторный порядок (один скан индекса)
SELECT title FROM idx WHERE text @@ (ts_phrase('physicist') && !!ts_phrase('philosophy'))
ORDER BY emb <=> $1::FLOAT[1536] LIMIT 5;
-- «похожие документы»
SELECT id FROM idx WHERE id <> 1
ORDER BY emb <-> (SELECT emb FROM articles WHERE id = 1) LIMIT 3;
```
Вектор можно передать bind-параметром расширенного протокола: `$1::FLOAT[1536]`
складывается на этапе плана, и оптимизатор выбирает ANN-скан
(`examples/demo4/demo.sql:51-60`, `\bind :qvec \g` в psql).

## 9.3 Настройки поиска (сессионные)

| Настройка | Дефолт | Смысл |
|---|---|---|
| `sdb_nprobe` | 8 | сколько кластеров IVF просматривать |
| `sdb_rerank_factor` | 4 | пул для точного пересчёта = factor × k; 0 — без реранка |
| `sdb_ivf_posting_size` | 1024 | целевой размер листового постинга (фиксируется при CREATE INDEX) |
| `sdb_ivf_sample_factor` | 0 (адаптивно) | доля строк для обучения дерева центроидов |

**Проверено на инстансе: да** — все четыре есть в `duckdb_settings()` с описаниями.

Доказательство: `tests/.../site_docs/sql/indexes/inverted/vector-search.test`,
`hybrid-search.test`, `cookbook/search/similar-documents.test`,
`tests/.../index/inverted_index_ivf_*.test` (pq, rabitq, sq4, sq8, levels, filter, nulls,
exact_distance, multi_vector).

---

# 10. Геопоиск

Словари `geojson` / `geopoint` → S2-ячейки. Поисковые предикаты:
```sql
WHERE ST_Intersects(geo, 'POINT(37.6 55.7)'::GEOMETRY('OGC:CRS84'))
WHERE ST_Intersects(shape, '{"type":"Polygon","coordinates":[...]}')
WHERE ST_Contains(geo, <shape>)
WHERE ST_Distance_Between(geo, <point>, 0, 5000)      -- кольцо, метры
WHERE ST_Distance_Centroid(geo, <point>) < 1000       -- радиус, метры
WHERE (geo <-> <point>) < 5000                        -- то же оператором
```
Тип колонки: `JSON` (GeoJSON), `GEOMETRY('OGC:CRS84')` (WKB) или VARCHAR с GeoJSON.
`GEOMETRY` допустим только со скалярным гео-анализатором.

Доказательство: `tests/.../index/geo_search.test:1-40`,
`cookbook/search/geospatial-search.test`,
`site_docs/sql/indexes/inverted/geospatial-search.test`.

**Состояние в 26.07.3:**
* тип `GEOMETRY('OGC:CRS84')` — **есть** (проверено: литерал приводится);
* шаблоны `geojson`/`geopoint` — **есть** (в `(help)`);
* `ST_*` — **есть, но только как inverted-index-предикаты**: вне контекста индекса
  запрос падает с `Inverted index function called outside inverted index context.`;
  в `duckdb_functions()` их нет, DuckDB-расширение `spatial` — `installed=false`.
  То есть `ST_AsText`, `ST_X` и прочая обычная геометрия недоступны;
  доступны только 5 поисковых предикатов выше.

---

# 11. DML, транзакции, обслуживание

## 11.1 MERGE INTO

```sql
MERGE INTO people
USING (SELECT unnest([3,1]) AS id, unnest([95000.0,105000.0]) AS salary) AS upserts
  ON (upserts.id = people.id)
WHEN MATCHED THEN UPDATE
WHEN NOT MATCHED THEN INSERT;

-- короткая форма ключа
MERGE INTO people USING (SELECT 1 AS id, 98000.0 AS salary) AS s
USING (id)
WHEN MATCHED THEN UPDATE SET salary = s.salary;

-- несколько условий, RETURNING merge_action
MERGE INTO people USING (...) AS u USING (id)
WHEN MATCHED AND people.salary < 100000 THEN UPDATE SET salary = u.salary
WHEN MATCHED AND people.salary > 100000 THEN DELETE
WHEN NOT MATCHED THEN INSERT BY NAME
RETURNING merge_action, *;
```
Доказательство: `tests/.../site_docs/sql/statements/merge_into/index.test:1-120`,
`tests/.../dml/merge.test:1-60` (в т.ч. поверх таблицы с inverted-индексом).

## 11.2 UPSERT

```sql
INSERT INTO t VALUES (...) ON CONFLICT DO NOTHING;
INSERT INTO t VALUES (...) ON CONFLICT (id) DO UPDATE SET v = excluded.v;
INSERT INTO t BY NAME SELECT ...;
INSERT OR REPLACE INTO t VALUES (...);
INSERT INTO t ... RETURNING rowid, *;
```
Доказательство: `tests/.../site_docs/sql/statements/insert/*.test` (16 файлов),
`tests/.../dml/upsert_returning_rowid.test`, `merge_returning_rowid.test`.

## 11.3 VACUUM — полный список форм

```sql
VACUUM;  VACUUM ANALYZE;  VACUUM my_table(col);  VACUUM ANALYZE my_table(col);
VACUUM (REFRESH_INDEX)   <index>;      -- опубликовать записи для читателей
VACUUM (REFRESH_TABLE)   <table>;
VACUUM (REFRESH_SCHEMA)  <schema>;
VACUUM (REFRESH_DATABASE) <db>;
VACUUM (REFRESH_ALL);
VACUUM (COMPACT_INDEX|COMPACT_TABLE|COMPACT_SCHEMA|COMPACT_DATABASE|COMPACT_ALL) ...;
VACUUM (RECOMPUTE_STATS_COLUMN|_TABLE|_SCHEMA|_DATABASE|_ALL) ...;
VACUUM (COMPACT_SCHEMA, REFRESH_ALL);  -- сочетаются между собой
```
`VACUUM FULL` → `ERROR: FULL is not yet implemented`.
SereneDB-опции нельзя смешивать со стандартными:
`VACUUM (REFRESH_TABLE, ANALYZE) t` → `ERROR: VACUUM SereneDB option 'refresh_table'
cannot be combined with standard VACUUM options`.
Доказательство: `tests/.../index/vacuum_options.test`,
`tests/.../site_docs/sql/statements/vacuum/index.test:35-120`.

## 11.4 DDL и транзакции

DDL **не транзакционен**: коммитится сразу, `ROLLBACK` его не отменяет.
На инстансе это подтверждено предупреждением:
`WARNING: DDL is not transactional: the statement commits immediately and is not undone by ROLLBACK`.
`SET sdb_strict_ddl = true` заставляет DDL внутри транзакционного блока падать с ошибкой
вместо тихого коммита. **Проверено на инстансе: да** (настройка есть, значение `off`).

## 11.5 ALTER TABLE при наличии inverted-индекса

* `RENAME` колонки/таблицы/индекса — индекс следует (ключи по id колонки).
* `ADD COLUMN` — нейтрально, DEFAULT бэкфиллится.
* `DROP COLUMN`, покрытой индексом → каскадный DROP индекса.
* `ALTER COLUMN TYPE` — можно для неиндексированной, запрещено для индексированной.

Доказательство: `tests/.../ddl/alter_table_inverted_index.test:1-45`.

## 11.6 COPY в таблицу с индексом

`COPY t FROM 'file.parquet' (FORMAT PARQUET)` идёт по bulk-пути, но кормит
inverted-sink; после `VACUUM (REFRESH_TABLE)` строки ищутся, INCLUDE round-trip.
Доказательство: `tests/.../dml/copy_inverted_index.test:1-50`.

## 11.7 Транзакции, изоляция, восстановление

* `default_transaction_isolation = repeatable read` (проверено на инстансе).
* WAL: `wal_autocheckpoint = 16 MiB`, `wal_autocheckpoint_entries`,
  `auto_checkpoint_skip_wal_threshold = 100000`, `CHECKPOINT`.
* `ATTACH ... (RECOVERY_MODE no_wal_writes)`.
* Отдельный набор recovery-тестов (~70 файлов) для каталога, индексов, backfill,
  крэшей при создании/вставке, WAND-компакции, изоляции сбоев:
  `tests/sqllogic/recovery/*.test` (в т.ч. `inverted_index_create_crash.test`,
  `inverted_index_insert_crash_registry.test`, `index_backfill_segments.test`,
  `wal_*`, `faults.test`).

---

# 12. Внешние источники и Zero-ETL

## 12.1 Табличные функции (все проверены на инстансе)

`read_parquet`, `read_csv`, `read_json_auto`, `read_text`, `read_blob`, `read_avro`,
`iceberg_scan`, `postgres_scan`, `postgres_query`, `query`, `query_table`,
`duckdb_secrets`, `which_secret`, `duckdb_logs`.

Схемы URL: локальный путь, glob (`/tmp/imdb_*.parquet`), `https://`, `s3://`, `gs://`,
`r2://`, `hf://datasets/<ds>@~parquet/<config>/**/*.parquet`.

```sql
CREATE VIEW imdb_v AS
  SELECT * FROM read_parquet('hf://datasets/stanfordnlp/imdb@~parquet/plain_text/**/*.parquet');
CREATE INDEX imdb_idx ON imdb_v USING inverted(text imdb_en, label);
COPY (SELECT * FROM read_parquet('hf://...')) TO '/tmp/x.parquet' (FORMAT PARQUET);
SET http_retries = 10; SET http_retry_wait_ms = 3000;   -- против 429 у HF
```
Доказательство: `examples/demo0/demo.sql:41-57`, `examples/demo1/bootstrap.sql:11-18`,
`examples/demo6/bootstrap.sql:28-29`, `cookbook/network_cloud_storage/*.test`.

## 12.2 ATTACH

```sql
ATTACH 'file.db';                     ATTACH 'file.db' AS db;
ATTACH 'file.db' (READ_ONLY);         ATTACH IF NOT EXISTS 'file.db' AS db;
ATTACH 'file.db' (BLOCK_SIZE 16_384);
ATTACH 'file.db' (ROW_GROUP_SIZE 2048);
ATTACH 'file.db' (RECOVERY_MODE no_wal_writes);
ATTACH 'host=... port=... dbname=... user=...' AS pg (TYPE postgres);
DETACH [IF EXISTS] db;
```
Доказательство: `tests/.../site_docs/sql/statements/attach/index.test:60-120`,
`tests/.../duckdb_postgres/attach_pgscan.test_slow:1-40`.

**Postgres-scanner в сборке есть** (`duckdb_extensions(): postgres_scanner installed=true,
loaded=true`; функции `postgres_scan`/`postgres_query` присутствуют).
Настройки пула: `pg_connection_limit`, `pg_pool_max_connections`, `pg_pool_idle_timeout_millis`,
`pg_use_binary_copy`, `pg_experimental_filter_pushdown`, `pg_order_pushdown`, `pg_use_ctid_scan`.

**Inverted-индекс поверх ATTACH'нутой Postgres-таблицы:** CREATE INDEX работает,
`count(*)` и BM25 работают, а **материализация исходных колонок пока падает** —
`postgres_scan` ещё не в fast-path-реестре.
Доказательство: `tests/.../duckdb_postgres/inverted_index_pgscan.test_slow:1-25`.

## 12.3 Чего нет как коннекторов

`mysql_scanner`, `sqlite_scanner`, `delta`, `ducklake`, `azure`, `aws`, `excel`,
`spatial`, `vss`, `lance`, `motherduck`, `unity_catalog`, `vortex`, `odbc_scanner`,
`encodings`, `fts`, `ui`, `quack` — `installed=false`.
Расширения **нельзя загрузить в рантайме**:
`LOAD is not supported by SereneDB: extensions are compiled into the server binary`.
**Проверено на инстансе: да** (`duckdb_extensions()`).

## 12.4 Логическая репликация (Zero-ETL «в другую сторону»)

`CREATE PUBLICATION` / `CREATE SUBSCRIPTION` **разбираются грамматикой, но не реализованы**:
`ERROR: Pragma Function with name create_publication does not exist!`
Доказательство: `tests/.../ddl/create_publication.test:1-30`,
`create_subscription.test:1-35` (в самих тестах написано «catalog handler is not yet
implemented»).

---

# 13. ES-совместимый слой

## 13.1 SQL-функции

| Функция | Тип | Что делает |
|---|---|---|
| `es_create_index(name, mapping_json)` | table (CALL) | создаёт таблицу `es.<name>` + inverted-индекс `es."<name>$text"` |
| `es_drop_index(name)` | table | удаляет |
| `es_mapping(name)` | table | нормализованный mapping |
| `es_cat_indices()` | table | список индексов |
| `es_refresh(name)` | table | публикует шарды (делает записи видимыми) |
| `es_doc(index, id, json)` | table | одна строка в форме целевой таблицы |
| `es_bulk(index, ndjson)` | table | набор строк из bulk-тела |

```sql
CALL es_create_index('books',
  '{"mappings":{"properties":{"title":{"type":"text"},"author":{"type":"keyword"},
    "year":{"type":"integer"}}}}');
INSERT INTO es.books SELECT * FROM es_bulk('books', '{"index":{"_id":"1"}}
{"title":"The Quick Brown Fox","author":"aesop","year":1900}
');
CALL es_refresh('books');
SELECT "_id" FROM es."books$text" WHERE "title" @@ ts_tokenize('QUICK dog') ORDER BY "_id";
SELECT "_id" FROM es."books$text" WHERE "title" @@ plainto_tsquery('quick fox');  -- operator=and
SELECT "_id" FROM es."books$text" AS t WHERE "title" @@ ts_tokenize('quick')
ORDER BY BM25(t.tableoid) DESC;
CALL es_drop_index('books');
```
Соответствие ES: `match` (operator=or) → `ts_tokenize`; `match` (operator=and) →
`plainto_tsquery`; `term`/`range` → обычные предикаты; `bool` → `AND`/`NOT`.
Типы mapping: `text` (инвертированный VARCHAR), `keyword`, `integer`, `long`, `double`,
`date`, `boolean`. Служебные колонки: `_id` (PK), `_source`.

Доказательство: `tests/.../es/index_functions.test:1-60`, `es/search.test:1-70`,
`es/write_path.test:1-50`.
**Проверено на инстансе: да** — все 7 функций есть в `duckdb_functions()` (table).
Схемы `es` ещё нет (ни одного ES-индекса не создано).

## 13.2 HTTP REST API

Отдельный listener: `listen = http://host:port?api=es`.
Маршруты (`server/network/http/es/handlers.cpp`):
```
GET  /                        GET/PUT/DELETE /:index
POST /_bulk                   POST /:index/_bulk
GET  /_cat/indices            GET /_cat/count
GET  /_cluster/health[/:index]  GET /_cluster/settings
POST /_forcemerge             POST /:index/_forcemerge
POST /:index/_count           POST/PUT /:index/_doc[/:id]
GET  /:index/_mapping         POST /:index/_mget
POST /:index/_refresh   POST /_refresh
POST /:index/_search    POST /_search/scroll
GET  /:index/_source/:id
GET  /:index/_stats[/:metric]  GET /_stats
GET  /_nodes/stats[/:metric]
```
Поддерживаемый DSL (`server/network/http/es/dsl.cpp`):
`query`, `bool` (`must`/`must_not`/`should`/`filter`/`minimum_should_match`),
`match` (`operator`: and/or), `match_phrase`, `match_all`, `term`, `terms`, `range`
(`gt/gte/lt/lte`), `sort` (`asc`/`desc`, `_score`, `_doc`), `from`, `size`,
`track_total_hits`, `_source`,
агрегации: `aggs`/`aggregations` — `terms`, `date_histogram` (`calendar_interval`:
`minute/hour/day/week/month/quarter/year`), `min`, `max`, `avg`, `sum`, `cardinality`,
`value_count`.
Аутентификация HTTP: `auth_api_key` (`id:key`), `auth_bearer_token`, `http_cors_origins`.

**В нашей сборке слой скомпилирован, но HTTP-listener не поднят**: на инстансе
`sdb_settings.listen = postgres://127.0.0.1:7890` — только pg-wire.

---

# 14. ai_embed и секреты

```sql
CREATE SECRET gemini (
    TYPE openai,
    api_key 'API_KEY',
    base_url 'https://generativelanguage.googleapis.com',
    embeddings_path '/v1beta/openai/embeddings');

-- на приёме
INSERT INTO arxiv
SELECT id, title, abstract, authors, published_date,
       ai_embed(abstract, 'gemini-embedding-001', 'gemini')::FLOAT[3072]
FROM (...) src;

-- в запросе
SELECT title FROM arxiv_idx a
ORDER BY a.embedding <=> ai_embed('Compaction in LLM','gemini-embedding-001','gemini')::FLOAT[3072]
LIMIT 5;
```
Сигнатура: `ai_embed(VARCHAR text, VARCHAR model, VARCHAR secret_name) -> FLOAT[]`.
Работает с любым OpenAI-совместимым endpoint — меняются только `base_url` и
`embeddings_path`.

Секреты вообще:
```sql
CREATE SECRET s (TYPE s3, KEY_ID '...', SECRET '...', REGION '...', SCOPE 's3://bucket');
CREATE PERSISTENT SECRET s (...);       DROP [PERSISTENT] SECRET s;
SET secret_directory = '/path';         FROM duckdb_secrets();
FROM which_secret('s3://bucket/f.parquet', 's3');
```
Доказательство: `examples/demo5/bootstrap.sql:3-33`, `examples/demo5/demo.sql:21-46`,
`tests/.../site_docs/configuration/secrets_manager.test`,
`tests/.../site_docs/sql/functions/ai_ollama.test_slow` (Ollama как провайдер).

**Проверено на инстансе: да** — `ai_embed(VARCHAR,VARCHAR,VARCHAR) -> FLOAT[]` есть,
`duckdb_secrets()` и `which_secret()` есть, `secret_directory =
/home/serenedb/.duckdb/stored_secrets`, `allow_persistent_secrets = on`.
Секретов сейчас **не создано ни одного** (`duckdb_secrets()` пуст) — то есть
`ai_embed()` в SQL сегодня не сконфигурирован, хотя механизм доступен.

---

# 15. Протокол, драйверы, безопасность

* Протокол: PostgreSQL wire, `server_version = 18.3`; simple и extended (bind-параметры,
  `PREPARE`/`EXECUTE`). `pg_max_message_bytes = 64 MiB` (объём — через `COPY`).
* TLS: `tls_cert`, `tls_key`, `tls_ca`, `tls_min_version` (1.2/1.3), `tls_ciphers`,
  `tls_groups`; `sslmode=prefer/require/verify-ca/verify-full`.
* Listener-строка: `postgres://host:port[?sslmode=...]`, `http(s)://host:port?api=es`,
  `postgres:///path/to.sock` (unix), несколько через запятую.
* Аутентификация: `pg_hba.conf` (`hba_config`), SCRAM (`scram_iterations = 4096`),
  предхэшированные пароли, `VALID UNTIL`, HTTP ApiKey/Bearer.
* RBAC: `CREATE ROLE`, `GRANT`/`REVOKE` (в т.ч. на колонки), `SET ROLE`, членство,
  `has_table_privilege`/`has_column_privilege`/`has_schema_privilege`/`has_role` и др.
  Тесты: `tests/sqllogic/sdb/pg/rbac/*.test` (15 файлов),
  `site_docs/security/*.test`.
* Драйверы, покрытые тестами: C (libpq), C#, Go (pgx + libpq), Java (JDBC), JS, PHP,
  Python, R, Ruby, Rust, psql — `tests/drivers/`.
* Таймауты: `auth_timeout`, `idle_session_timeout`, `http_body_timeout`,
  `statement_timeout`, `max_execution_time`, `max_connections`.
* Логи: `logging_storage = 'stdout'|'memory'|'file'`, `SELECT * FROM duckdb_logs()`,
  `logging_level`, `enabled_log_types`/`disabled_log_types`.

**Проверено на инстансе: да** — все перечисленные `sdb_settings` присутствуют
(контекст `postmaster`), `duckdb_logs()` вызывается.

---

# 16. Общий SQL-слой (DuckDB-диалект + PG-совместимость)

Не полнотекстовое, но доступно и часто заменяет ручной код:

* `MERGE INTO`, `ASOF JOIN`, `QUALIFY`, `PIVOT`/`UNPIVOT`, `GROUPING SETS`/`ROLLUP`/`CUBE`,
  `SAMPLE`, `LATERAL`, `UNNEST`, `WITH RECURSIVE`, оконные функции, `SUMMARIZE`,
  `DESCRIBE`, `EXPLAIN [ANALYZE]`, `COLUMNS(*)`/`COLUMNS('regex')`, `*EXCLUDE/REPLACE`.
* `CREATE MACRO` (скалярный и `AS TABLE`), `query_table($1)`, `query($1)`.
* Типы: `LIST`, `ARRAY(T,N)`, `STRUCT`, `MAP`, `UNION`, `VARIANT`, `JSON`, `ENUM`, `BIT`,
  `INET`, `GEOMETRY`, `UUID`, `HUGEINT`, `TIMESTAMPTZ` (нс), `INTERVAL`, `TSQUERY`.
* `VARIANT`: `'{"a":1}'::JSON::VARIANT`, доступ `doc['k']['k2']::TYPE`;
  такие выражения индексируются напрямую.
* Файлы: `COPY ... TO/FROM` с `FORMAT CSV|PARQUET|JSON|BINARY`, hive-партиционирование,
  partitioned writes, Parquet-метаданные и шифрование, Iceberg-каталог.
* Последовательности, `GENERATED ALWAYS AS (...) STORED`, `CHECK`, `FOREIGN KEY`,
  `PRIMARY KEY`, `CREATE OR REPLACE`, `EXPORT/IMPORT DATABASE`, `COMMENT ON`, `USE`,
  `SET VARIABLE`, `CHECKPOINT`, `CALL`, `TRUNCATE`.
* Системные представления: `pg_class`, `pg_index`, `pg_am`, `pg_attribute`, `pg_indexes`,
  `pg_ts_dict`, `pg_roles`, `pg_policies`, `information_schema.*`, `sdb_settings`,
  `duckdb_settings()`, `duckdb_functions()`, `duckdb_indexes()`, `duckdb_tables()`,
  `duckdb_databases()`, `duckdb_extensions()`, `duckdb_secrets()`, `duckdb_logs()`.

Доказательства: `tests/sqllogic/sdb/pg/site_docs/sql/**` (≈300 файлов),
`tests/.../cookbook/sql_features/*.test`, `tests/.../simple/*.test`.
**Проверено на инстансе выборочно: да** (`QUALIFY`, `query_table`, `SUMMARIZE`,
`approx_quantile`, `GROUPING SETS`, все системные вьюхи выше).

---

# 17. Чего в сборке 26.07.3 НЕТ

| Возможность | Где встречается | Статус в 26.07.3 |
|---|---|---|
| **Опкласс `hnsw`** | `examples/demo4/demo.sql:39-42`, `examples/demo5/demo.sql:16-19` (`embedding hnsw (metric='cosine', m=32, ef_construction=64)`) | **НЕТ.** `server/catalog/index.cpp:110-113` знает только `included` и `ivf`; в бинарнике нет ни `ef_construction`, ни опкласса `hnsw` (найденные `hnsw_*` строки — внутренности неподключённого DuckDB-расширения `vss`). Замена — `ivf (metric='cosine')`. **Индекс не создавался (запрет задания), вывод — по бинарнику и исходникам.** |
| **Расширение `spatial`** и обычные `ST_*` функции | `cookbook/search/geospatial-search.test` (`ST_AsText`) | **НЕТ.** `duckdb_extensions(): spatial installed=false`. Доступны только 5 поисковых предикатов `ST_Intersects/ST_Contains/ST_Distance_Between/ST_Distance_Centroid/<->`, и то лишь внутри `WHERE` по гео-индексу. |
| **Расширение `vss`** | — | НЕТ (`installed=false`). |
| `mysql_scanner`, `sqlite_scanner` | `cookbook/database_integration/mysql.test`, `sqlite.test` | **НЕТ** — и в самих тестах это зафиксировано как ожидаемая ошибка. Расширения нельзя догрузить: `LOAD is not supported by SereneDB`. |
| `delta`, `ducklake`, `azure`, `aws`, `excel`, `lance`, `motherduck`, `odbc_scanner`, `unity_catalog`, `vortex`, `encodings`, `fts`, `ui`, `quack` | — | НЕТ (`installed=false`). |
| **`CREATE PUBLICATION` / `CREATE SUBSCRIPTION`** | `ddl/create_publication.test`, `create_subscription.test` | Парсятся, но **не реализованы** (`Pragma Function ... does not exist`) — и в `main` тоже. |
| **`VACUUM FULL`** | `site_docs/sql/statements/vacuum/index.test` | `FULL is not yet implemented`. |
| **Несколько скореров в одном запросе** | — | Запрещено: `Only one scorer function is allowed per inverted index`. Обход — `UNION`. |
| **Материализация колонок из view поверх `postgres_scan`** | `duckdb_postgres/inverted_index_pgscan.test_slow` | Не поддержано (fast-path реестр не включает `postgres_scan`). `count(*)`/BM25 работают. |
| **Материализация колонок из «generic» view** (UNION ALL из VALUES и т.п. без fast-path reader) | `site_docs/sql/indexes/inverted/views.test` (`generic_error`) | Не поддержано. Обход — `INCLUDE (...)` всех нужных колонок (паттерн demo6). |
| **HTTP/ES listener** | `server/network/http/es/*` | Код есть, но у нас **не сконфигурирован**: `listen = postgres://127.0.0.1:7890`. |
| **`to_tsquery` с некавыченной кириллицей** | — | Синтаксическая ошибка Lucene-парсера; нужны кавычки. |
| **Индексирование HUGEINT/UHUGEINT/UBIGINT/DECIMAL/UUID/INTERVAL/BIT** как ключей | `inverted_index_unsupported_numeric.test` | Не поддержано (INCLUDE — можно). |

---

# 18. Что показалось неочевидным

1. **`CREATE TEXT SEARCH DICTIONARY x (help)`** — движок сам печатает полный справочник
   всех шаблонов и опций с дефолтами. Самый быстрый способ узнать, что доступно
   в конкретной сборке. Для индекса аналога нет: `WITH (HELP)` → `unrecognized parameter "help"`.

2. **Один скорер на индекс на запрос.** Нельзя сравнить BM25 и TFIDF в одном SELECT;
   A/B по моделям ранжирования делается через `UNION` или два прогона.

3. **`to_tsquery` — это Lucene, а не PostgreSQL.** `field:term`, `term*`, `term~2`,
   `term^3`, `[a TO b]`, `+/-`. И нецитированная кириллица его ломает. Настоящий
   PG-подобный ввод — `plainto_tsquery`/`phraseto_tsquery`/`websearch_to_tsquery`.

4. **`ts_regexp` и `ts_like` идут по термам словаря, а не по тексту.** Поэтому
   `ts_regexp('дог.вор')` даёт 0 на индексе, где `договор` — отдельный терм: точка не
   попадает ни в один терм. `ts_like('%овор%')` при этом работает (подстрока терма).

5. **`ts_dict_*` — не только фасеты.** Это готовые автодополнение (`ts_dict_agg` + `LIKE`),
   исправление опечаток (`ts_dict_score` при `ts_levenshtein` даёт similarity),
   tag cloud (`ts_dict_freq`), significant terms (`lift` = fg − bg·fg_total/bg_total),
   и «сохранённые поиски» (JOIN списка алертов к `unnest(ts_dict_agg(body))`).

6. **Неявная перезапись в term-scan.** `SELECT col, count(*) FROM idx GROUP BY col`,
   `count(DISTINCT col)`, `min/max(col)`, `array_agg(DISTINCT col)` и `GROUPING SETS`
   планируются как перечисление словаря термов (`EXPLAIN` показывает `TsDict:`), без
   чтения документов. Проверено на нашем индексе.

7. **`sparse_ngram` — не «ещё один ngram».** Две роли одного алгоритма: индексная
   (`covering = false`, ≤ 2n−2 грамм) и запросная (`covering = true`, ≤ n−2 грамм).
   Подстрочный поиск = конъюнкция covering-грамм + `LIKE` для точности:
   `WHERE code @@ ts_all(ts_tokenize(ARRAY['sys.setrecursionlimit('], 'code_grams_q'))
    AND code LIKE '%sys.setrecursionlimit(%'`.
   Замена `ts_all` на `ts_any(..., k)` превращает это в фаззи-поиск «по форме».
   Запросный словарь **не привязывается к индексу** — он существует только чтобы быть
   названным в `ts_tokenize`.

8. **`ts_highlight` — чистая функция.** Перегрузка `(text, INTEGER[] offsets[, opts])`
   работает вообще без индекса, поэтому подсветку можно применять к любой строке,
   если смещения уже есть. Есть и полностью автономная
   `ts_offsets(dict, text, tsquery)` / `ts_highlight(dict, text, tsquery, opts)`.
   Опции `MaxWords`, `MaxFragments`, `HighlightAll`, `StartSel`, `StopSel`.

9. **`INCLUDE` делает индекс самодостаточным.** demo6 строит два индекса над `UNION ALL`
   view поверх Hugging Face parquet и после сборки **ни разу не ходит в сеть**: все
   выдаваемые колонки лежат в columnstore индекса. Это же решает проблему
   «generic view нельзя материализовать».

10. **`included (hyperloglog = true)`** — единственный способ получить `approx_unique`
    в статистике колонки, которую оптимизатор использует для порядка соединений.
    `included (compression = '...')` пинит кодек (`zstd`, `dict_fsst`, `roaring`, `alp`, …).

11. **`store_pk = 'none'`** — индекс без PK: меньше места, но нельзя ни `DELETE`/`UPDATE`
    по таблице, ни выбирать не-INCLUDE колонки. Полезно для чисто аналитических/счётных
    индексов над неизменяемыми view.

12. **`WITH (storage = 'search')` на `CREATE TABLE`** — таблица с iresearch-шардом вместо
    транзакционного хранилища (`simple/search_table.test:1-40`). Редкий, но существующий режим.

13. **Частичный индекс `CREATE INDEX ... WHERE <pred>`** доступен только для inverted, и
    строки мигрируют в/из индекса при UPDATE, пересекающем границу предиката.

14. **`ALTER INDEX ... SET/RESET`** меняет только «эксплуатационные» опции (интервалы,
    размеры сегментов, параметры компакции). Структурные (`row_group_size`, `store_pk`,
    `optimize_top_k`) — только при создании.

15. **DDL не транзакционен** и на каждом DDL выдаётся WARNING. `sdb_strict_ddl = true`
    превращает DDL-в-транзакции в ошибку — стоит включать в скриптах миграций.

16. **`ts_any(arr, k)` = terms-set query** («хотя бы k из списка»), а `ts_compound(must,
    must_not, should[, min_should])` — прямой аналог ES `bool`. У нас в коде на такое
    обычно пишут «И»/«ИЛИ» вручную.

17. **`ts_levenshtein(term, d, transpositions, prefix)`** — 4-й аргумент задаёт
    обязательный точный префикс, что резко сужает автомат и ускоряет фаззи-поиск
    (`ts_levenshtein('t', 1, true, 'ca')` → cat/car/cats).

18. **`ts_between`/`ts_lt/le/gt/ge` работают и по строкам** (лексикографически), а не только
    по числам: `genre @@ ts_ge('comedy') AND genre @@ ts_le('fantasy')`.

19. **Bind-параметры протокола прямо в векторном ORDER BY**: `ORDER BY emb <=> $1::FLOAT[1536]`
    — каст сворачивается на этапе плана и включается ANN-скан. В psql это `\bind :qvec \g`.

20. **`sdb_nprobe` / `sdb_rerank_factor`** — рычаги recall/latency для IVF на уровне сессии,
    без пересоздания индекса. `sdb_scored_terms_limit` (1024) ограничивает число термов,
    учитываемых при скоринге многотермовых фильтров — влияет на качество IDF при
    wildcard/fuzzy/prefix-запросах с большим раскрытием.

21. **`ts_tokenize(ARRAY[...], 'dict')` возвращает `TSQUERY[]`**, который подаётся прямо в
    `ts_all`/`ts_any` — это единственный способ «прогнать пользовательскую строку через
    произвольный словарь и превратить в булев запрос».

22. **`VACUUM (REFRESH_*)` — не уборка мусора, а публикация записей.** Без него свежие
    строки не видны в индексе (при `refresh_interval = 0` или сразу после массовой
    загрузки). Три семейства: `REFRESH_*` (видимость), `COMPACT_*` (слияние),
    `RECOMPUTE_STATS_*` (статистики), каждое в 4–5 областях видимости.

---

## Второй проход

Дополнения, найденные при повторном, целенаправленном просмотре материала.

### П2.1 Скореры, пропущенные в первом проходе

`lm_jm`, `indri_dirichlet`, `raw_tf`, `raw_boost`, `raw_dl` не упоминаются ни в одной
демке (там показаны только четыре: BM25/TFIDF/LM-Dirichlet/DFI). Найдены в
`tests/.../site_docs/sql/functions/full_text_search.test` (секции `lm_jm`,
`indri_dirichlet`, `raw_tf`, `raw_boost`, `raw_dl`). **Все есть в 26.07.3, проверено.**
`raw_tf`/`raw_dl` полезны как отладочные: показывают, сколько раз терм встретился и
какова длина документа — можно строить свои формулы прямо в SQL.

`dfi` имеет второй аргумент — меру расхождения: `standardized` (дефолт), `saturated`,
`chi_squared`. Ни в одной демке этого нет; список получен из ошибки движка на инстансе.

### П2.2 `ts_compound` требует явных кастов

`ts_compound('a','b',['c'])` не биндится:
```
Could not choose a best candidate function for the function call
"ts_compound(STRING_LITERAL, STRING_LITERAL, VARCHAR[])"
```
Рабочая форма (проверено): `ts_compound('a'::tsquery, 'b'::tsquery, ARRAY['c'::tsquery])`,
либо через `ts_phrase(...)`, как в документации.
Четвёртый аргумент — `minimum_should_match` (INTEGER).

### П2.3 `included()` без опций — это тоже опкласс

`CREATE INDEX i ON v USING inverted(body dict, id included())` — `included()` можно
поставить и в **списке ключей** (не только в `INCLUDE (...)`), чтобы колонка попала в
columnstore, но не в термы. Используется вместе с `store_pk = false`.
Доказательство: `tests/.../index/inverted_index_store_pk.test:45-60`.
Сообщение движка (из бинарника) прямо на это указывает:
`'...' is listed more than once with a tokenizer opclass; ... Stack \`included(...)\` on the
same column instead`.

### П2.4 Per-column `row_group_size`

Из описаний настроек: *«Per-column `(row_group_size = ...)` and per-index
`WITH (row_group_size = ...)` override»* — то есть размер row-group задаётся и на уровне
отдельной INCLUDE-колонки, в скобках опкласса. В `ApplyIncludedOpclass`
(`server/catalog/index.cpp:520-545`) принимаются только `compression` и `hyperloglog`,
поэтому per-column форма, судя по всему, идёт через отдельный путь; на инстансе
не проверялось.

### П2.5 `sdb_scored_terms_limit`

Не встречается ни в демках, ни в cookbook. Описание из `duckdb_settings()`:
«максимум термов, учитываемых при скоринге многотермовых фильтров; больше — точнее
IDF-скоринг ценой памяти и работы на запрос; 0 полностью отключает сбор скоринговых
термов». Дефолт 1024. Это прямой рычаг качества ранжирования для
prefix/wildcard/fuzzy-запросов, которые раскрываются в тысячи термов.
**Есть в 26.07.3, проверено.**

### П2.6 Гео-предикаты существуют вне `duckdb_functions()`

`ST_Intersects` и др. не видны в `duckdb_functions()`, но вызов даёт
`Inverted index function called outside inverted index context` — значит функция
зарегистрирована особым образом и работает **только** как предикат по гео-индексу.
Это важно: отсутствие имени в `duckdb_functions()` не означает отсутствие функции.

### П2.7 `WITH (storage = 'search')` — таблица-поисковый-шард

```sql
CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT) WITH (storage = 'search');
```
Допустимые значения: `'transactional'` (дефолт) и `'search'` (регистронезависимо).
`tests/.../simple/search_table.test:1-45`. В демках и cookbook не встречается.

### П2.8 `ts_split_by_non_alpha`

`ts_split_by_non_alpha(VARCHAR[, BOOLEAN]) -> VARCHAR[]` — служебная нарезка строки по
не-буквенным символам, доступна как обычная скалярная функция (без словаря).
`tests/.../simple/ts_split_by_non_alpha.test`. **Есть в 26.07.3.**

### П2.9 `ts_dict_raw_agg`

Возвращает термы как `BLOB[]` — нужно, когда термы не являются валидным UTF-8
(например, `collation`-словарь, `geojson` S2-ячейки, бинарные n-граммы).
`tests/.../index/ts_dict.test:55-65`.

### П2.10 Опции `ngram`: маркеры границ и binary-режим

`startmarker`/`endmarker` добавляют маркеры на границах значения — так n-граммный
индекс отличает «начало слова» от середины:
`ts_lexize('tok_ngram_mark','cat')` → `{^ca,^cat,cat$,at$}`.
`inputtype = 'binary'` переключает нарезку с UTF-8-символов на байты.
`tests/.../create_text_search_dictionary/ngram.test:60-80`.

### П2.11 `text` со встроенным edge-ngram

У шаблона `text` есть **подгруппа** `edgengram`: указав `mingram`/`maxgram`/
`preserveoriginal` прямо в `text`-словаре, получаем префиксные n-граммы уже после
стемминга и стоп-слов:
```sql
CREATE TEXT SEARCH DICTIONARY tok_text_edge (
  template='text', locale='en_US.UTF-8', case='lower',
  mingram=2, maxgram=4, preserveoriginal=true);
-- ts_lexize(...,'Search') -> {se,sea,sear,search}
```
Это готовый автокомплит без отдельного индекса.
`tests/.../create_text_search_dictionary/text.test:60-90`,
`server/pg/tokenizer_options.h:295-302`.

### П2.12 `wildcard`-словарь ускоряет `ts_like`

Шаблон `wildcard` (`ngramsize = 3` + вложенный `tokenizer_*`) строит n-граммный
вспомогательный индекс, по которому `ts_like('%ear%')` и `ts_like('sea%')` идут без
полного обхода словаря термов.
`tests/.../create_text_search_dictionary/wildcard.test:1-40`. **Шаблон есть в 26.07.3.**

### П2.13 `minhash`-словарь

`template='minhash'` c `numhashes` и вложенным `tokenizer_*` даёт LSH-сигнатуры —
основа дешёвой дедупликации/«похожести» документов без векторов.
`.../create_text_search_dictionary/minhash/index.test`. **Есть в сборке.**

### П2.14 `classification` / `nearest_neighbors`

fastText-модели прямо в словаре: `classification` кладёт в индекс предсказанные метки
(`topk`, `threshold`), `nearest_neighbors` — ближайшие по эмбеддингу слова.
Требуют файла модели на сервере (`modellocation`).
`.../classification.test_slow`, `.../nearest-neighbors.test_slow`. **Шаблоны в сборке есть.**

### П2.15 `pipeline` вкладывается сам в себя

`STEP2_TEMPLATE = 'pipeline'` + `STEP2_STEP1_TEMPLATE = ...` — вложенные конвейеры
произвольной глубины. `.../pipeline/index.test:45-70`.

### П2.16 `copy_from` умеет **расширять** конвейер

`template='copy_from', from='pipe_dict', STEP3_TEMPLATE='stopwords', STEP3_STOPWORDS='...'`
— наследуемый словарь получает дополнительный шаг, которого не было в оригинале.
`.../copy-from.test:80-95`.

### П2.17 Отладочные / служебные детали `EXPLAIN`

Внутри `IRESEARCH_SCAN` печатаются строки: `Index:`, `Index Filter:` (с деревом
`Term/Range/Boolean` и полями `Field:`/`Value:`), `Lookup: table`, `Score:` (с
параметрами скорера: `bm25(k1=1.2, b=0.75)`), `Top: k[, optimized]`, `Min Score:`,
`Offsets:`, `TsDict: <col>`, `Projections:`.
**Проверено на инстансе** — все, кроме `optimized`/`Min Score` (у нас нет `optimize_top_k`).

### П2.18 `stats(col)` — скалярная функция

`SELECT (stats(v)).approx_unique, (stats(v)).min, (stats(v)).max FROM idx LIMIT 1;`
Даёт доступ к тем же статистикам, что видит оптимизатор.
`tests/.../index/inverted_index_hyperloglog_option.test:30-50`.
**Проверено на инстансе: да** (`(stats(amount)).min` = 0.0).

### П2.19 Индексирование `VARIANT`/JSON-путей

```sql
CREATE INDEX products_idx ON products USING inverted (
  id,
  (doc['name']::VARCHAR) jtext,
  (doc['attrs']['brand']::VARCHAR),
  (doc['tags']::VARCHAR[]),
  (doc['price']::INTEGER));
SELECT id FROM products_idx WHERE (doc['tags']::VARCHAR[]) @@ ts_all(['sale','new']);
```
Массив JSON индексируется как мульти-значное поле (каждый элемент — терм).
`tests/.../cookbook/search/json-search.test`, `site_docs/sql/indexes/inverted/json.test`.

### П2.20 «Одно поисковое поле» через GENERATED-колонку

```sql
all_text VARCHAR GENERATED ALWAYS AS (concat_ws(' ', name, brand, owner, notes)) STORED
CREATE INDEX machines_idx ON machines USING inverted (id, name osb_en, all_text osb_en);
SELECT ... WHERE name @@ ('vario'::tsquery ^ 2.0) OR all_text @@ 'vario'
ORDER BY BM25(machines_idx.tableoid) DESC;
```
Одно поле для «одной строки поиска» + буст на точное поле.
`tests/.../cookbook/search/one-search-box.test:1-83`.

### П2.21 Дедупликация/группировка результатов

Top-1 в группе — оконная функция поверх скана индекса:
```sql
SELECT * FROM (
  SELECT id, category, title,
         ROW_NUMBER() OVER (PARTITION BY category
                            ORDER BY BM25(products_idx.tableoid) DESC, id) rn
  FROM products_idx WHERE title @@ 'running') s
WHERE rn = 1;
```
`tests/.../cookbook/search/grouping-results.test`.

### П2.22 Индекс над индексом (VIEW поверх индекса)

```sql
CREATE VIEW recent_hits AS SELECT id, body, category FROM v_docs_idx WHERE body @@ 'quick';
SELECT * FROM recent_hits WHERE category = 'animal';
```
`tests/.../cookbook/search/indexing-views.test:60-78`.

### П2.23 Prepared statements с `@@`

`PREPARE p AS SELECT a FROM idx WHERE b @@ $1;` — при `EXECUTE` параметр
подставляется как константа и фильтр компилируется полностью. `NULL` матчит ноль строк
(Empty-семантика). Работает и `$1::tsquery`, и параметры внутри `ts_phrase($1)`,
и скоринг через параметризованный фильтр.
`tests/.../index/tsquery_params.test:1-100`.

### П2.24 `has_any_tokens` со строкой вместо массива

Есть перегрузки `has_any_tokens(ANY, VARCHAR)` и `has_any_tokens(ANY, VARCHAR, INTEGER)` —
токены передаются одной строкой, а не массивом. В документации это не показано.
**Проверено в `duckdb_functions()` на инстансе.**

### П2.25 Настройки, влияющие на индекс, но задаваемые сессией

`SET refresh_interval = 0; SET compaction_interval = 0;` — сессионные значения
становятся дефолтом для **вновь создаваемых** индексов (и используются в тестах, чтобы
сделать поведение детерминированным). На уже созданные индексы не влияют — там нужен
`ALTER INDEX`. Доказательство: `tests/.../index/ts_dict.test:4-8`, описания настроек
в `duckdb_settings()`.

### П2.26 `SET http_retries` / `http_retry_wait_ms`

Прямо в demo6 как средство пережить 429 от Hugging Face:
`SET http_retries = 10; SET http_retry_wait_ms = 3000;` (`examples/demo6/bootstrap.sql:28-29`).
Полезно для любого чтения по HTTP. **Есть в сборке** (дефолты 3 и 100).

### П2.27 Точный список кодеков сжатия INCLUDE-колонок и что исключено

Разрешены: `auto`, `uncompressed`, `rle`, `bitpacking`, `zstd`, `alp`, `alprd`,
`roaring`, `dict_fsst`.
Намеренно исключены (с объяснением в комментарии кода
`server/catalog/index.cpp:138-160`): `dictionary`, `fsst` (заменены на `dict_fsst`),
`chimp`, `patas` (deprecated в DuckDB), `constant` (внутренний).

### П2.28 Матрица «тип колонки × токенизатор» проверяется на CREATE INDEX

21 файл `inverted_index_matrix_*.test` фиксирует валидатор. Ключевые правила:
* текстовый токенизатор — только VARCHAR/BLOB/LIST|ARRAY этих типов;
* гео-токенизатор — только JSON / VARCHAR(GeoJSON) / GEOMETRY(WKB), скаляр;
* GEOMETRY вообще нельзя без гео-токенизатора;
* JSON внутри LIST/ARRAY отвергается для любого токенизатора;
* одна колонка не может быть указана дважды с токенизатором — вторую роль оформляют
  через `included(...)`.
`tests/.../index/inverted_index_matrix_validator.test:15-60`.

### П2.29 `es_bulk`/`es_doc` — это **табличные** функции, а не команды

Они возвращают строки в форме целевой таблицы, поэтому пишутся через
`INSERT INTO es.<index> SELECT * FROM es_bulk(...)`. Это позволяет вставить bulk-тело
куда угодно, в том числе в обычную (не-ES) таблицу.
`tests/.../es/write_path.test:9-20`.

### П2.30 Что ещё есть в `sdb_settings` (уровень процесса)

`listen` (мультилистенеры, unix-сокеты, `?api=es`), `hba_config`, `auth_api_key`,
`auth_bearer_token`, `auth_timeout`, `idle_session_timeout`, `http_body_timeout`,
`http_cors_origins`, `max_connections`, `pg_max_message_bytes`, `cpu_threads`,
`io_threads`, `background_threads`, `log_level`/`log_storage`/`log_path`,
`server_directory`, `tls_*`, плюс большой блок настроек S2 (гео).
Все с контекстом `postmaster` — меняются только рестартом.
**Проверено на инстансе: да.**
