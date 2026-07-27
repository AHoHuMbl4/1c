# Каталог возможностей SereneDB

Источники: репозиторий `/srv/data/cursor/cursor/1/serenedb-src` (ветка `main`)
и живой инстанс `192.168.56.42:7890` — **PostgreSQL 18.3 (SereneDB 26.07.3)**.

Обозначения в графе «в сборке 26.07.3»:
* **да (запрос)** — проверено выполнением на инстансе;
* **да (каталог)** — функция/опкласс/настройка найдены в `duckdb_functions()` / `pg_opclass` / `duckdb_settings()`;
* **да (бинарник)** — строка найдена в `/opt/serenedb-dist/serenedb-*/usr/bin/serened` (DDL не выполнялся: аудит read-only);
* **нет** — отсутствует, проверено.

Все пути `file:line` — относительно `/srv/data/cursor/cursor/1/serenedb-src`.

---

## 1. Модель: индекс — это отношение

Ключевой принцип всего движка. `CREATE INDEX ... USING inverted(...)` создаёт объект,
из которого **читают как из таблицы**: `FROM <имя_индекса>`. Обращение к базовой
таблице индекс не задействует и падает на `@@`.

```sql
CREATE INDEX movies_idx ON movies USING inverted (id, title basic_dict, description basic_dict, genre);
SELECT id, title FROM movies_idx WHERE description @@ ts_phrase('alien');
```
Доказательство: `tests/sqllogic/sdb/pg/site_docs/sql/indexes/inverted/index.test:30-41`.
В сборке: **да (запрос)** — `SELECT count(*) FROM search_idx WHERE doc @@ ts_phrase('договор')` → 565.

Скоринг адресуется через `<index>.tableoid`: `BM25(movies_idx.tableoid)`.

Индекс можно строить над:
* таблицей (`demo2/demo.sql:35`);
* **вьюхой над внешними файлами** — `read_parquet`/`read_csv`/`read_json` (`demo0/demo.sql:39-43`);
* вьюхой-UNION ALL из нескольких разнородных источников (`demo6/bootstrap.sql:100-110`).

---

## 2. CREATE INDEX: полный синтаксис

```sql
CREATE INDEX <name> ON <table|view>
USING inverted ( <col> [<dict>|<opclass> (<opts>)] , ... )
[ INCLUDE ( <col> [included (<opts>)] , ... ) ]
[ WHERE <predicate> ]                  -- частичный индекс
[ WITH ( <option> = <value>, ... ) ];
```

### 2.1 Виды ключей

| Вид ключа | Синтаксис | Доказательство |
|---|---|---|
| Текст с токенизатором | `title basic_dict` | `site_docs/sql/indexes/inverted/index.test:31` |
| Keyword/числовой/дата без словаря | `genre`, `price`, `id` | `.../index.test:92`, `:134` |
| Массив | `tags` (TEXT[]) | `.../inverted/modeling.test:66` |
| Выражение | `(lower(s))`, `(first \|\| ' ' \|\| last)`, `(CASE WHEN ... END)` | `.../inverted/modeling.test:16`, `cookbook/search/computed-values.test:9,65,87` |
| JSON-путь | `(doc['name']::VARCHAR) jtext`, `(content->>'host') verbatim_dict` | `cookbook/search/json-search.test:24`, `index/inverted_index_json.test:14` |
| Вектор | `emb ivf (metric = 'l2')` | `site_docs/sql/indexes/inverted/vector-search.test:9` |
| Гео | `geo geo_s2` (словарь `geojson`/`geopoint`) | `cookbook/search/geospatial-search.test:12` |

Запрещено: агрегаты в выражении (`ERROR: aggregate functions are not allowed in index expressions`,
`inverted/modeling.test:85`) и выражения с побочными эффектами (`n + random()`, `:95`).

### 2.2 `INCLUDE` — колонки-«пассажиры»

Колонки, которые не индексируются термами, но **хранятся в columnstore индекса**.
После этого запросы (проекция, предикаты, агрегаты) не читают исходную таблицу/parquet.

```sql
CREATE INDEX pages_idx ON pages USING inverted (id, body english_dict) INCLUDE (url);
```
`site_docs/sql/indexes/inverted/index.test:60-62`.

Опции на конкретной INCLUDE-колонке через опкласс `included`:
```sql
INCLUDE (pk, big_int included (compression = 'uncompressed'))
INCLUDE (v included (hyperloglog = true), s included (hyperloglog = true), plain)
```
`index/inverted_index_compression_option.test:38`, `index/inverted_index_hyperloglog_option.test:25-28`.
`hyperloglog = true` даёт оптимизатору `approx_unique` (NDV) по колонке.
Опкласс `included` в сборке: **да (каталог)** — `pg_opclass` содержит `included`.

Разрешённые типы INCLUDE — практически все, включая STRUCT/MAP/LIST/VARIANT/UNION/GEOMETRY:
`server/catalog/inverted_index.cpp:262-306`.

### 2.3 Частичный индекс

```sql
CREATE INDEX pt_live ON subscribers USING inverted(label) WHERE live;
```
Индексируются только строки, удовлетворяющие предикату; при UPDATE строки
мигрируют в индекс и из него. NULL-предикат = false (семантика PG).
`index/inverted_index_partial.test:1-5, 51`.

### 2.4 `WITH (...)` — опции индекса

Полный список опций (значения по умолчанию — из `pg_class.reloptions`,
`index/inverted_index_options.test:36`):

| Опция | Умолчание | ALTER INDEX | Смысл |
|---|---|---|---|
| `row_group_size` | 122880 | нет | размер row-group columnstore |
| `norm_row_group_size` | 122880 | нет | то же для norm-колонок |
| `refresh_interval` | 1000 | да | мс между авто-refresh (0 = выключить фон) |
| `compaction_interval` | 1000 | да | мс между авто-compaction (0 = выключить) |
| `cleanup_interval_step` | 1 | да | шаг фоновой уборки |
| `segment_memory_max` | 268435456 | да | байт памяти на сегмент |
| `segment_docs_max` | 0 (=безлимит) | да | документов на сегмент |
| `compaction_max_segments` | 10 | да | сколько сегментов сливать |
| `compaction_max_segments_bytes` | 5368709120 | да | верхняя граница слияния |
| `compaction_floor_segment_bytes` | 2097152 | да | нижняя граница слияния |
| `store_pk` | — | нет | `'none'`/`'i64'`/`'i64i64'`/`'i256'`/`false` |
| `optimize_top_k` | — | нет | скорер для WAND-прунинга |
| `compression` | — | нет | только внутри `included (...)` |

`ALTER INDEX <name> SET (opt = v)` / `RESET (opt)` — `index/inverted_index_options.test:50,63,75`.
Неизвестная опция отвергается (`unrecognized parameter`), 0 запрещён везде кроме
`segment_docs_max`/`refresh_interval`/`compaction_interval` (`:112-153`).
В сборке: **да (запрос)** — reloptions живого `search_idx` содержит ровно этот набор.

Все они же — **сессионные настройки** с теми же именами (`SET row_group_size = ...`).
Проверено: `duckdb_settings()` возвращает `row_group_size=122880`, `refresh_interval=1000`,
`compaction_interval=1000`, `cleanup_interval_step=1`, `segment_memory_max=268435456`,
`segment_docs_max=0`, `compaction_max_segments=10`, `compaction_max_segments_bytes=5368709120`,
`compaction_floor_segment_bytes=2097152`, `norm_row_group_size=122880`.

### 2.5 `optimize_top_k` — WAND / Block-Max прунинг

```sql
CREATE INDEX movies_idx ON movies USING inverted (...) WITH (optimize_top_k = 'bm25(1.2, 0.75)');
```
Писатель кладёт per-block max-impact, и `ORDER BY BM25(...) DESC LIMIT k`
исполняется с отсечением. WAND срабатывает **только если скорер в ORDER BY
совпадает с записанным в индексе**. Значения: `'bm25'`, `'bm25(1.2, 0.75)'`,
`'tfidf()'`, `'lm_jm(2.0)'`, `'raw_tf()'`, либо `true`.
`site_docs/sql/indexes/inverted/ranking.test:32`, `index/inverted_index_optimize_top_k.test:1-20`.
EXPLAIN помечает строку `TopK` суффиксом `, optimized`.
Отключить глобально: `SET sdb_disable_top_k_optimization = true`.
В сборке: **да (бинарник + настройка `sdb_disable_top_k_optimization`)**.

---

## 3. Словари (токенизаторы): `CREATE TEXT SEARCH DICTIONARY`

```sql
CREATE TEXT SEARCH DICTIONARY <name> ( template = '<tpl>', <опции...> );
DROP TEXT SEARCH DICTIONARY [IF EXISTS] <name>;
```
Словари живут в схеме и резолвятся из схемы **целевой таблицы**
(`index/vacuum_options.test:19-36`). Проверка словаря без индекса:
`SELECT ts_lexize('<dict>', '<текст>')`.

Все 23 шаблона найдены в бинарнике 26.07.3 (**да (бинарник)**):
`classification, collation, copy_from, delimiter, geojson, geopoint, keyword,
minhash, multi_delimiter, nearest_neighbors, ngram, norm, path_hierarchy,
pipeline, segmentation, solr_synonyms, sparse_ngram, stem, stopwords, text,
union, wildcard, wordnet_synonyms`.

### 3.1 `text` — основной анализатор

```sql
CREATE TEXT SEARCH DICTIONARY english_dict (
    template   = 'text',
    locale     = 'en_US.UTF-8',
    case       = 'lower' | 'upper' | 'none',
    stemming   = true|false,
    accent     = true|false,       -- true = СОХРАНИТЬ диакритику
    stopwords  = '"the","a","an"',
    frequency  = true,             -- частоты термов -> нужны для BM25
    position   = true,             -- позиции -> нужны для фраз/слопа
    norm       = true,             -- длина документа -> нужна для BM25 b>0
    offset     = true,             -- байтовые смещения -> ts_offsets/ts_highlight
    mingram = 2, maxgram = 5, preserveoriginal = true   -- edge-ngram внутри text
);
```
`site_docs/sql/statements/create_text_search_dictionary/text.test:5-14, 36-43, 120-133`.

Смысл флагов (проверено выводом `ts_lexize`):
* `case='none'` + `accent=true` → термы как есть: `{The,Runners,Café}` (`text.test:91-94`);
* `case='lower'` + `accent=false` → `{cafe,resume}` (`cookbook/search/case-sensitivity-and-diacritics.test:62-65`);
* `case='upper'` → `{CAFE,RESUME}` (`:210-213`);
* `stemming=true` → `{run,runner,ran}` (`inverted/text-analysis.test:64-67`);
* `stopwords` → `{speed,light}` из `the speed of light` (`text-analysis.test:84-87`);
* `mingram/maxgram/preserveoriginal` внутри `text` → edge-ngram: `Search` → `{se,sea,sear,search}` (`text.test:129-133`).

**Без `frequency` нет BM25; без `position` нет фраз и слопа; без `norm`
нормализация длины (`b`) не работает; без `offset` не работают `ts_offsets`/`ts_highlight`.**

### 3.2 `ngram` — символьные n-граммы

```sql
CREATE TEXT SEARCH DICTIONARY ngram_dict (
    template = 'ngram', mingram = 2, maxgram = 3,
    preserveoriginal = true, startmarker = '^', endmarker = '$',
    frequency = true, position = true
);
```
`search` → `{se,sea,ea,ear,ar,arc,rc,rch,ch}`; с маркерами `cat` → `{^ca,^cat,cat$,at$}`.
`create_text_search_dictionary/ngram.test:5-10, 34-38, 62-75`.

### 3.3 `sparse_ngram` — подстрочный/«грепоподобный» поиск (схема GitHub code search)

```sql
-- индексная сторона: все грамы, покрывают любую подстроку (<= 2n-2 грам)
CREATE TEXT SEARCH DICTIONARY code_grams   (template='sparse_ngram', frequency=true, norm=true);
-- запросная сторона: минимальная покрывающая цепочка (<= n-2 грам)
CREATE TEXT SEARCH DICTIONARY code_grams_q (template='sparse_ngram', covering=true);
-- ограничение длины грама
CREATE TEXT SEARCH DICTIONARY code_grams_short (template='sparse_ngram', maxngramlength=4);
```
`create_text_search_dictionary/sparse-ngram.test:5-32, 110-120`; `demo6/bootstrap.sql:56-68`.

Приём поиска подстроки — **конъюнкция грамов + `LIKE` как точный постфильтр**:
```sql
SELECT count(*) FROM solutions_idx
WHERE code @@ ts_all(ts_tokenize(ARRAY['sys.setrecursionlimit('], 'code_grams_q'))
  AND code LIKE '%sys.setrecursionlimit(%';
```
`demo6/demo.sql:30-33`. Нечёткий вариант — `ts_any(..., k)` (k из n грамов): `demo6/demo.sql:58`.
Словарь `code_grams_q` **никогда не привязан к индексу**, он используется только
по имени в `ts_tokenize`/`ts_lexize`.

### 3.4 Остальные шаблоны

| Шаблон | Синтаксис | Результат `ts_lexize` | Файл |
|---|---|---|---|
| `keyword` | `(template='keyword')` | `'Hello World'` → `{"Hello World"}` | `keyword.test:5-18` |
| `delimiter` | `(template='delimiter', delimiter=',')` | `red,green,blue` → `{red,green,blue}` | `delimiter.test:26-35` |
| `multi_delimiter` | `(template='multi_delimiter', delimiters='":", ";", " "')` | `key:value; key2:value2` → `{key,value,key2,value2}` | `multi-delimiter.test:16-25` |
| `norm` | `(template='norm', locale, case, accent)` | `CAFÉ` → `{cafe}` | `norm.test:5-17` |
| `stem` | `(template='stem', locale='en')` | `running` → `{run}` | `stem.test:5-15` |
| `stopwords` | `(template='stopwords', stopwords='"the"', HEX=true)` | `the` → `{}` | `stopwords.test:5-15, 41-51` |
| `segmentation` | `(template='segmentation', case, BREAK='alpha'\|'graphic'\|'all')` | `The Quick fox-trot.` → `{the,quick,fox,trot}` | `segmentation.test:5-49` |
| `pattern` | `(template='pattern', pattern='\s+', group=-1)` | `group=-1` = сплит по совпадению, `group=N` = захват группы | `pattern.test:5-67` |
| `path_hierarchy` | `(template='path_hierarchy', delimiter='/', reverse=true, skip=1)` | `/usr/local/bin` → `{/usr,/usr/local,/usr/local/bin}` | `path-hierarchy.test:5-49` |
| `wildcard` | `(template='wildcard', ngramsize=3, tokenizer_template='delimiter', tokenizer_delimiter=' ')` | ускоряет `ts_like('%ear%')` | `wildcard.test:4-34` |
| `collation` | `(template='collation', locale='en_US.UTF-8')` | бинарный ключ сортировки локали | `collation.test:5-19` |
| `geojson` | `(template='geojson' [, coding='s2point'])` | GeoJSON → S2-ячейки | `geojson.test:5-31` |
| `geopoint` | `(template='geopoint', latitude='lat', longitude='lng')` | `{"lat":..,"lng":..}` → S2-ячейки | `geopoint.test:5-23` |
| `solr_synonyms` | `(template='solr_synonyms', synonyms='car, automobile\nlaptop => notebook')` | `car`→`{auto,automobile,car}`, `laptop`→`{notebook}` | `solr-synonyms.test:5-51` |
| `wordnet_synonyms` | `(template='wordnet_synonyms', synonyms='s(100000001,1,''fast'',v,1,0).')` | синонимы → id синсета | `wordnet-synonyms.test:5-44` |
| `union` | `(template='union', TOKENIZER1_TEMPLATE='keyword', TOKENIZER2_TEMPLATE='ngram', TOKENIZER2_MINGRAM=2, ...)` | объединение выходов | `union.test:5-38` |
| `minhash` | `(template='minhash', tokenizer_template='text', tokenizer_locale=..., numhashes=6)` | LSH-подписи | `minhash/index.test:5-25` |
| `classification` | `(template='classification', MODELLOCATION='/models/x.bin', TOPK=3, THRESHOLD=0.5)` | fastText-классификация как термы | `classification.test_slow:16-21` |
| `nearest_neighbors` | `(template='nearest_neighbors', MODELLOCATION=..., TOPK=2)` | расширение по эмбеддингам fastText | `nearest-neighbors.test_slow:36-39` |
| `pipeline` | см. ниже | цепочка шагов | `pipeline/index.test` |
| `copy_from` | см. ниже | наследование с переопределением | `copy-from.test` |

### 3.5 `pipeline` — цепочка токенизаторов

```sql
CREATE TEXT SEARCH DICTIONARY syn (
    template = 'pipeline',
    step1_template = 'text', step1_locale = 'en_US.UTF-8', step1_case = 'lower', step1_stemming = false,
    step2_template = 'solr_synonyms', step2_synonyms = 'tv, television, telly\nlaptop => notebook',
    frequency = true, position = true
);
```
`cookbook/search/synonyms.test:6-17`. Вложенность допускается:
`STEP2_TEMPLATE='pipeline', STEP2_STEP1_TEMPLATE='delimiter', ...` (`pipeline/index.test:56-69`).

### 3.6 `copy_from` — вариант существующего словаря

```sql
CREATE TEXT SEARCH DICTIONARY english_no_stem (
    template = 'copy_from', from = 'english_dict', stemming = false );
```
Наследует всё, переопределяет указанное; можно **дописать шаг** в pipeline
(`STEP3_TEMPLATE = 'stopwords', STEP3_STOPWORDS = '"bar","foo"'`).
`copy-from.test:26-30, 85-90`. Так же делается запросный вариант sparse_ngram:
`(template='copy_from', from='code_grams', covering=true)` (`sparse-ngram.test:94-98`).

---

## 4. Запросный язык полнотекста

### 4.1 Оператор `@@` и тип `TSQUERY`

`<колонка> @@ <tsquery>`. Строковый литерал приводится к `TSQUERY` неявно:
`WHERE genre @@ 'sci-fi'`, `WHERE title @@ 'refund'`.
`cookbook/search/exact-value-matching.test:49`, `cookbook/search/boosting.test:35`.

### 4.2 Строители запросов (всё **да (каталог + запрос)**)

| Функция | Сигнатуры в 26.07.3 | Что делает |
|---|---|---|
| `ts_phrase(text)` | `[VARCHAR]`, `[BLOB]` | фраза/терм |
| `ts_phrase(a, gap, b, ...)` | вариадическая | фраза со слопом: `ts_phrase('plot', ARRAY[0,3], 'twist')` |
| `ts_starts_with(p)` | `[VARCHAR]`, `[BLOB]` | префикс |
| `ts_like(p)` | `[VARCHAR]`, `[BLOB]` | wildcard `%`/`_` |
| `ts_regexp(p [, flags])` | `[VARCHAR]`, `[VARCHAR,VARCHAR]` | регулярка по терму |
| `ts_levenshtein(t, d [, transpositions [, prefix]])` | 1..4 арг. | фаззи; `transpositions=false` выключает перестановки; `prefix` — обязательный неизменяемый префикс |
| `ts_ngram(t [, threshold])` | 1..2 арг. | Jaccard по n-граммам |
| `ts_lt/le/gt/ge(v)` | `[ANY]` | диапазон по терму (числа, даты, строки) |
| `ts_between(lo, hi, inc_lo, inc_hi)` | `[ANY,ANY,BOOLEAN,BOOLEAN]` | диапазон |
| `ts_any(list [, k])` | `TSQUERY[]` | ИЛИ; `k` = «минимум k из n» (terms-set) |
| `ts_all(list)` | `TSQUERY[]` | И |
| `ts_compound(must, must_not, should [, min_should])` | 16 перегрузок | ES-подобный bool-запрос |
| `ts_tokenize(txt [, dict])` | скаляр и массивный вариант | токенизировать строку словарём → `TSQUERY`/`TSQUERY[]` |

Примеры: `site_docs/sql/functions/full_text_search.test:212-350`;
`ts_phrase` со слопом — `demo3/demo.sql:68`; `ts_levenshtein` с префиксом —
`cookbook/search/fuzzy-search.test:79`.

Живая проверка (индекс `search_idx`, 97 965 док.):
`ts_starts_with('догов')`→2613, `ts_like('дого%р')`→565, `ts_levenshtein('дoговор',2)`→2057,
`ts_levenshtein('овор',1,true,'дог')`→2055, `ts_phrase('договор',ARRAY[0,3],'поставки')`→157,
`ts_any(['договор','счет','акт']::tsquery[],2)`→103, `ts_all([...])`→157.

### 4.3 Операторы над TSQUERY

| Оператор | Смысл | Пример |
|---|---|---|
| `&&` | AND | `ts_phrase('quick') && ts_phrase('brown')` |
| `\|\|` | OR | `ts_phrase('brown') \|\| ts_phrase('grey')` |
| `!!` | NOT (только внутри конъюнкции) | `ts_phrase('quick') && !!ts_phrase('brown')` |
| `##` | фраза-цепочка со слопом | `'quick' ## 1 ## 'fox'`, `'quick' ## [0,2] ## 'fox'` |
| `^` | буст скора | `('refund'::tsquery ^ 5.0)` |

`site_docs/sql/indexes/inverted/full-text-search.test:58-83, 163-177, 206-210`;
`cookbook/search/boosting.test:46`.

`##` склеивает **разнородные** части: `bare 'word'`, `ts_starts_with`, `ts_like`,
`ts_levenshtein`, `ts_phrase`, `ts_any`, `ts_between` — с индивидуальным окном
между каждой парой (`demo3/demo.sql:177-203`):
```sql
WHERE text @@ ( ts_levenshtein('tarintino', 2) ## ARRAY[1,5]
                ## ts_starts_with('direct')    ## ARRAY[0,8] ## 'film' )
```
Все операторы проверены на инстансе (`SELECT (…)::text` и реальные счётчики).

### 4.4 PostgreSQL-совместимые парсеры запроса

| Функция | Синтаксис входа | Файл |
|---|---|---|
| `to_tsquery(s)` | `'quick AND brown'`, а также Lucene-стиль `'+fox -red'`, `'"plot twist" OR "happy ending" -boring'` | `full_text_search.test:397, 405`; `demo3/demo.sql:85` |
| `plainto_tsquery(s)` | все слова через AND | `full_text_search.test:413` |
| `phraseto_tsquery(s)` | вся строка как фраза | `:421` |
| `websearch_to_tsquery(s)` | веб-синтаксис с кавычками/OR | `:430` |
| `tsquery_phrase(a, b [, distance])` | фраза из двух tsquery с дистанцией | `:439` |

Все — **да (каталог + запрос)**.
`ts_rank`, `ts_rank_cd`, `ts_rewrite`, `ts_parse`, `ts_token_type`, `to_tsvector`
перечислены в `site_docs/compatibility/core_sql_claims.test:1897-1934` как
PG-совместимость; **в `duckdb_functions()` сборки 26.07.3 их нет** — ранжирование
делается скорерами (раздел 5), а не `ts_rank`.

### 4.5 Булевы функции-предикаты (без `@@`)

```sql
WHERE phrase_matches(body, 'quick brown')
WHERE ngram_matches(title, 'hello', 0.3)
WHERE levenshtein_matches(body, 'quikc', 2 [, transpositions [, prefix]])
WHERE has_all_tokens(body, ['quick', 'brown'])
WHERE has_any_tokens(skills, ['java','sql','rust'], 2)
```
`full_text_search.test:448-484`, `cookbook/search/terms-set.test:65`.
Все — **да (каталог)**; `has_all_tokens` проверен запросом (157, совпало с `ts_all`).

### 4.6 NULL-семантика

`WHERE dual IS NULL` / `IS NOT NULL` работают прямо по индексу через
null-marker поле (`full_text_search.test:492-505`). Трёхзначная логика при
отрицаниях разбирается в `index/null_semantics.test:1-11`.

### 4.7 Параметризация

`PREPARE ... AS SELECT a FROM tqp_idx WHERE b @@ $1` — параметр подставляется
как константа при каждом EXECUTE, фильтр компилируется полноценно.
`index/tsquery_params.test:36-56`. Вектор через bind-параметр:
`ORDER BY d.embedding <=> $1::FLOAT[1536]` (`demo4/demo.sql:56-60`).

---

## 5. Модели ранжирования (скореры)

Все принимают `<index>.tableoid` первым аргументом. **Все семь есть в 26.07.3
и проверены запросом на `search_idx`.**

| Функция | Сигнатуры | Значение на живом индексе (топ-1 по `ts_phrase('договор')`) |
|---|---|---|
| `bm25(oid)` / `bm25(oid, k1, b)` | `[BIGINT]`, `[BIGINT,DOUBLE,DOUBLE]` | 9.385 |
| `tfidf(oid)` / `tfidf(oid, with_norms)` | `[BIGINT]`, `[BIGINT,BOOLEAN]` | 10.319 |
| `lm_jm(oid [, lambda])` | `[BIGINT]`, `[BIGINT,DOUBLE]` | 9.307 |
| `lm_dirichlet(oid [, mu])` | `[BIGINT]`, `[BIGINT,DOUBLE]` | 6.736 |
| `indri_dirichlet(oid [, mu])` | `[BIGINT]`, `[BIGINT,DOUBLE]` | −6.147 |
| `dfi(oid [, measure])` | `[BIGINT]`, `[BIGINT,VARCHAR]` | 5.944 |
| `raw_tf` / `raw_dl` / `raw_boost` | `[BIGINT]` | сырые tf / длина документа / буст |

`site_docs/sql/functions/full_text_search.test:507-635`; `demo3/demo.sql:125-143`.

`dfi` принимает меру: `'standardized'` (умолчание), `'saturated'`, `'chi_squared'`
— `index/inverted_index_dfi.test:49-113`. Неизвестная мера → ошибка (`:122`).

`bm25(oid, 1.2, 0)` = BM15 (без нормализации длины);
`bm25(oid, 0.5, 0)` — ослабленное насыщение tf. `cookbook/search/ranking.test:60-107`.

**Ограничение сборки (проверено запросом):** в одном запросе к одному
инвертированному индексу допускается **ровно один скорер**:
```
ERROR: Only one scorer function is allowed per inverted index
HINT: Use UNION to combine different score functions for the same inverted index
```

### 5.1 Пост-скоринг в SQL

Скор — обычное выражение, его можно комбинировать:
```sql
ORDER BY BM25(idx.tableoid) * LOG(runtime + 1) DESC          -- cookbook/search/ranking.test:186
ORDER BY BM25(idx.tableoid) * (1.0 / (1 + age_days)) DESC     -- recency-and-decay.test:50
ORDER BY BM25(idx.tableoid) * (popularity/(popularity+10)) DESC -- :63
ORDER BY CASE WHEN id IN (2,5) THEN 0 ELSE 1 END, BM25(...) DESC  -- pinned-results.test:65
ORDER BY array_position(ARRAY[5,2,7], id) NULLS LAST, BM25(...) DESC -- :86
```

### 5.2 RRF (Reciprocal Rank Fusion)

```sql
WITH fused AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY s DESC) AS rank FROM (
    SELECT id, BM25(idx.tableoid) AS s FROM idx WHERE title @@ ts_phrase('alien')
    ORDER BY s DESC LIMIT 100) t
  UNION ALL
  SELECT id, ROW_NUMBER() OVER (ORDER BY dist) AS rank FROM (
    SELECT id, emb <-> [1.0,0,0]::FLOAT[3] AS dist FROM idx ORDER BY dist LIMIT 100) v
)
SELECT id, SUM(1.0/(60+rank)) AS rrf FROM fused GROUP BY id ORDER BY rrf DESC;
```
`cookbook/search/reciprocal-rank-fusion.test:47-62`, `cookbook/search/hybrid-search.test:81-99`.
Это же — штатный обход ограничения «один скорер на запрос».

---

## 6. Подсветка и смещения

Требуют `offset = true` в словаре.

| Форма | Сигнатура | Что делает |
|---|---|---|
| `ts_offsets(col)` | `[ANY]` | байтовые пары `{начало,конец}` всех совпадений |
| `ts_offsets(col, n)` | `[ANY, INTEGER]` | ограничение количества |
| `ts_offsets(dict, text, tsquery [, n])` | `[VARCHAR,VARCHAR,TSQUERY[,INTEGER]]` | offline, без индекса |
| `ts_highlight(col)` | `[ANY]` | готовый сниппет `<b>…</b>` прямо из индекса |
| `ts_highlight(col, opts)` | `[ANY, VARCHAR]` | с опциями |
| `ts_highlight(text, int[] [, opts])` | `[VARCHAR,'INTEGER[]'[,VARCHAR]]` | по готовым смещениям |
| `ts_highlight(dict, text, tsquery [, opts])` | | offline |

Опции (строка вида `'Key=Val, Key=Val'`), все проверены запросом на инстансе:
* `StartSel=<mark>, StopSel=</mark>` → `the <mark>quick</mark> brown fox`;
* `MaxWords=9` → окно вокруг совпадения;
* `MaxFragments=2` → `A <b>quick fox</b> runs ... Another <b>quick fox</b>`;
* `HighlightAll=true` → весь документ с обёрнутыми совпадениями.

`cookbook/search/highlighting.test:38-124`; `full_text_search.test:637-718`;
`index/headline.test:20-60`; `demo3/demo.sql:152`.

Конвейер «смещения → подсветка»: `ts_highlight(body, ts_offsets(body))`
(`full_text_search.test:665`).

---

## 7. Словарь термов (term dictionary) — фасеты, автодополнение, орфография

Агрегаты, читающие **словарь термов сегмента**, а не документы. Все — **да (каталог + запрос)**.

| Агрегат | Возврат | Смысл |
|---|---|---|
| `ts_dict_agg(col)` | `VARCHAR[]` | список термов |
| `ts_dict_count(col)` | `INTEGER[]` | документов на терм |
| `ts_dict_freq(col)` | `BIGINT[]` | вхождений на терм |
| `ts_dict_score(col)` | `FLOAT[]` | схожесть терма с запросом (для `ts_levenshtein`/`ts_ngram`) |
| `ts_dict_min(col)` / `ts_dict_max(col)` | `VARCHAR` | границы словаря |
| `ts_dict_raw_agg(col)` | `BLOB[]` | сырые байты термов |

Списки **выровнены поэлементно**, штатный приём — параллельный `unnest`:
```sql
SELECT unnest(ts_dict_agg(category)) AS category,
       unnest(ts_dict_count(category)) AS n
FROM products_idx WHERE title @@ 'running' ORDER BY n DESC;
```
`cookbook/search/faceted-search.test:63-72`; `site_docs/sql/functions/term_dictionary.test:37-54`.

Применения из кукбука:
* **фасеты** — `faceted-search.test`;
* **автодополнение** — `WHERE query LIKE 'run%'` + `ts_dict_agg` (`autocomplete.test:34-58`);
* **исправление опечаток** — `ts_levenshtein('jaket',2)` + `ts_dict_score` (`spell-correction.test:31-40`);
* **облако тегов** — `ts_dict_freq` (`tag-cloud.test:38-68`);
* **значимые термы (significant terms)** — foreground/background lift на CTE (`significant-terms.test:87-117`);
* **сохранённые поиски / percolator** — `a.term IN (SELECT unnest(ts_dict_agg(body)) FROM doc_idx)` (`saved-searches.test:55-63`).

**Ограничения (важно):**
1. Работает только по колонкам с текстовым/keyword словарём. Для числовой колонки:
   `ERROR: ts_dict_agg(): column has no text term dictionary` (`index/ts_dict_numeric.test:25-28`).
2. **`WHERE` ограничивает множество документов, а не множество термов.** Проверено
   на инстансе: `ts_dict_agg(doc) ... WHERE doc @@ ts_starts_with('договор')` возвращает
   *все* термы подошедших документов (`false`, `deletionmark`, …), а не только начинающиеся
   на «договор». Тот же эффект зафиксирован в `term_dictionary.test:86-101`.
   Приёмы кукбука работают потому, что колонка там однотокенная (`term`, `query`).
   Фильтровать надо снаружи: `SELECT t FROM (SELECT unnest(ts_dict_agg(body)) t FROM idx) WHERE t LIKE 'g%'`
   (`term_dictionary.test:103-111`).

### 7.1 `GROUP BY` как настоящий фасет

`SELECT col, count(*) FROM idx GROUP BY col` по **keyword NOT NULL** колонке
исполняется из словаря термов (группы = живые термы, размер = live doc count),
а не сканом документов. Nullable-колонка тоже конвертируется — NULL-группа
берётся из null-marker поля. `GROUPING SETS` из одиночных keyword-ключей
конвертируется, если не более одного ключа nullable.
`index/ts_dict_facets.test:6-27`.
Пример GROUPING SETS: `cookbook/search/faceted-search.test:160-168`.

---

## 8. Векторный поиск

### 8.1 Опкласс `ivf`

```sql
CREATE INDEX idx ON t USING inverted (id, emb ivf (
    metric = 'l2' | 'cosine' | 'ip' | 'l1',
    quant  = 'none' | 'sq8' | 'sq4' | 'pq' | 'rabitq',
    pq_m = 4,            -- только для quant='pq', должен делить размерность
    rabitq_bits = 8      -- только для quant='rabitq', 1..8
));
```
`site_docs/sql/indexes/inverted/vector-search.test:9`;
`index/inverted_index_ivf_pq.test`, `_sq8`, `_sq4`, `_rabitq`, `_levels`.
Тип колонки обязан быть `ARRAY(FLOAT, N)` = `FLOAT[N]`
(`server/catalog/inverted_index.cpp:329-336`).

Ограничения из тестов: `sq4`/`sq8`/`rabitq` не работают с `metric='l1'`;
`rabitq` не работает с `metric='cosine'`; `rabitq_bits` вне 1..8 отвергается
(`inverted_index_ivf_*.test`).

Опкласс `ivf` в сборке: **да (каталог)** — есть в `pg_opclass`.
**Опкласса `hnsw` в сборке 26.07.3 НЕТ** (проверено: `pg_opclass` содержит только
`ivf`/`included`/словари; строки `hnsw` в бинарнике нет). В репозитории `main`
он используется в `demo4/demo.sql:41` и `demo5/demo.sql:18` — этот SQL у нас не пойдёт.

Один индекс может нести несколько векторных колонок с разными метриками:
`USING inverted(pk, a ivf(metric='l2'), b ivf(metric='cosine'))`
(`index/inverted_index_multi_vector_ivf.test:19`).

### 8.2 Операторы и функции расстояния

| Оператор | Метрика | Функция |
|---|---|---|
| `<->` | L2 | `l2_distance`, `l2_sqr_distance` |
| `<=>` | cosine | `cosine_distance`, `cosine_similarity` |
| `<#>` | inner product (отрицательный) | `inner_product`, `negative_inner_product` |
| `<+>` | L1 | `l1_distance` |

Плюс `l2_norm`, `l1_norm`, `l2_normalize`, `l1_normalize`.
`full_text_search.test:720-867`. Все — **да (каталог)**, `l2_normalize`/`cosine_distance`
проверены запросом.

Формы запроса:
* top-K ANN: `ORDER BY emb <-> $1::FLOAT[N] LIMIT k` → план `IRESEARCH_ANN_SCAN`;
* range: `WHERE emb <-> $1::FLOAT[N] < 0.3` → `IRESEARCH_ANN_RANGE_SCAN`;
* гибрид: `WHERE text @@ (…) ORDER BY emb <=> $1::FLOAT[N] LIMIT k` — один проход по одному индексу.
`demo4/demo.sql:56-94`; `site_docs/sql/indexes/inverted/hybrid-search.test:39-63`.

### 8.3 Настройки поиска по векторам (все **да (каталог)**)

| Настройка | Умолчание | Смысл |
|---|---|---|
| `sdb_nprobe` | 8 | сколько IVF-списков сканировать (recall vs latency) |
| `sdb_rerank_factor` | 4 | пул для переоценки точными расстояниями = factor × k; 0 = выключить |
| `sdb_ivf_posting_size` | 1024 | целевой размер листа (t) дерева центроидов, фиксируется на CREATE INDEX |
| `sdb_ivf_sample_factor` | 0 (адаптивно) | доля строк для обучения центроидов |

Реранка нет при `quant='none'` независимо от `sdb_rerank_factor`.

---

## 9. Геопоиск

Словарь `geojson` (опция `coding='s2point'`) или `geopoint`; тип колонки
обязан быть `JSON` или `GEOMETRY`, обычный `VARCHAR` отвергается
(`index/geo_search.test:5-7`).

```sql
CREATE TEXT SEARCH DICTIONARY geo_s2 (template = 'geojson', coding = 's2point');
CREATE INDEX shops_idx ON shops USING inverted (id, name, geo geo_s2);

WHERE ST_Distance_Centroid(geo, 'POINT(-122.4 37.79)'::GEOMETRY('OGC:CRS84')) < 1000
WHERE (geo <-> 'POINT(37.6 55.7)'::GEOMETRY('OGC:CRS84')) < 5000     -- то же оператором
WHERE ST_Distance_Between(geo, <point>, 1000, 10000)                  -- кольцо
WHERE ST_Intersects(geo, <geometry|geojson-строка>)
WHERE ST_Contains(<polygon>, shape)  /  ST_Contains(shape, <point>)
```
`cookbook/search/geospatial-search.test:36-66`; `full_text_search.test:869-1000`.

В сборке: `ST_*` функций 32 шт. (**да (каталог)**), `ST_AsText` работает;
`ST_Distance_Centroid` вне индексного контекста осознанно падает:
`ERROR: Inverted index function called outside inverted index context.` (проверено запросом).

---

## 10. Агрегация и аналитика прямо по индексу

Индекс — отношение, поэтому доступен весь SQL:

```sql
SELECT genre, count(*), avg(runtime) FROM movies_idx
WHERE description @@ ts_phrase('film') GROUP BY genre;                    -- exact-value-matching.test:109

SELECT count(*) AS hits, approx_count_distinct(brand) FROM products_idx
WHERE title @@ 'running';                                                 -- result-cardinality.test:47

SELECT lang, count(*), min(time_ms), round(approx_quantile(time_ms,0.5)) AS p50
FROM solutions_idx WHERE task_id = '4/A' GROUP BY lang;                    -- demo6/demo.sql:66-75

SELECT p.title, sum(o.amount) FROM products_idx p JOIN orders o ON o.product_id=p.id
WHERE p.title @@ 'running' GROUP BY p.title;                               -- search-with-joins.test:49-54

SELECT ... FROM (SELECT ..., ROW_NUMBER() OVER (PARTITION BY category
       ORDER BY BM25(products_idx.tableoid) DESC) rn FROM products_idx
       WHERE title @@ 'running') s WHERE rn = 1;                           -- grouping-results.test:47-54

SUMMARIZE smz_idx;   -- min/max/approx_unique/avg/std/q25/q50/q75/count/null_percentage
                     -- index/inverted_index_summarize.test:34-40
```
Живая проверка: `GROUP BY src_table` + `count(*)` по 97 965 документам — 4.8 мс;
`SUMMARIZE search_idx` отрабатывает.

INCLUDE-колонки дают оптимизатору min/max статистику: `SUM` над BIGINT
планируется как `sum_no_overflow`, когда границы это доказывают
(`index/inverted_index_statistics.test:1-8`).

`sdb_scored_terms_limit` (умолчание 1024) — сколько термов участвует в
IDF-скоринге многотермовых фильтров; 0 полностью отключает сбор.

---

## 11. Внешние источники и Zero-ETL

### 11.1 Индекс поверх вьюхи над файлами

```sql
CREATE VIEW imdb_v AS
  SELECT * FROM read_parquet('hf://datasets/stanfordnlp/imdb@~parquet/plain_text/**/*.parquet');
CREATE INDEX imdb_idx ON imdb_v USING inverted(text imdb_en, label);
```
`demo0/demo.sql:39-43`. Поддержаны `hf://`, `s3://`, `https://`, локальный glob,
`read_csv`, `read_json_auto` (`cookbook/search/indexing-external-data.test:20-41`).
`SELECT * FROM read_parquet(<один строковый литерал>)` распознаётся как fast-path
источник, PK `(file_index, file_row_number)` строится автоматически.

**Ограничение fast-path:** чтобы материализовать реальные колонки из
view-backed индекса, тело вьюхи должно быть плоской проекцией из одного
`read_*(литерал)` — без join, без WHERE, только касты и алиасы. Иначе:
```
ERROR: materialising real columns from this view-backed inverted index is not yet supported
```
`site_docs/sql/indexes/inverted/views.test:83-90`, `demo4/bootstrap_view.sql:12-19`.
При этом `count(*)`, BM25-скоринг и ANN-дистанция по такому индексу работают
без материализации (`views.test:31-52`).

**Обход:** переложить нужные колонки в `INCLUDE` — тогда индекс самодостаточен
и после сборки к файлам не обращается вовсе (шаблон demo6:
`USING inverted(...) INCLUDE (каждая нужная колонка)`, `demo6/bootstrap.sql:108-131`).

Параметры ридера во вьюхе (dialect/format) должны совпадать при стриминге и
материализации; сжатый JSON, явные `column_types`/`names` для CSV и hive-partitioning
fast-path не поддерживает (`index/inverted_index_view_params.test:4-13`).

Настройки сетевого чтения: `SET http_retries = 10; SET http_retry_wait_ms = 3000;`
(`demo6/bootstrap.sql:28-29`; в сборке — **да (каталог)**, умолчания 3 и 100).

**Совет по производительности из demo6:** не использовать
`row_number() OVER ()` для генерации id во вьюхе — глобальная оконная функция
сериализует весь конвейер в один поток; с естественным ключом параллельный
sink работает на всех ядрах (**17× на сборке 11.5 млн строк**), `demo6/README.md:34-39`.

### 11.2 ATTACH

```sql
ATTACH 'file.db' [AS alias] [(READ_ONLY | BLOCK_SIZE 16_384 | ROW_GROUP_SIZE 2048
                              | RECOVERY_MODE no_wal_writes | TYPE postgres)];
ATTACH IF NOT EXISTS ...;  DETACH [IF EXISTS] alias;
```
`site_docs/sql/statements/attach/index.test:29-120`.

* **PostgreSQL** — работает: `ATTACH 'host=… dbname=… user=…' AS pg (TYPE postgres)`,
  затем `CREATE SCHEMA pg.app`, `CREATE TABLE pg.app.users`, обычные SELECT/INSERT.
  `cookbook/database_integration/postgres_pgscan.test_slow:20-50`.
  В сборке: **да (каталог)** — `postgres_scan`, `postgres_query` есть в `duckdb_functions()`.
* **MySQL / SQLite** — **нет**: расширения не собраны в бинарник, ошибка
  `LOAD is not supported by SereneDB: extensions are compiled into the server binary`
  (`cookbook/database_integration/mysql.test:8-11`, `sqlite.test:15-33`).
* **Iceberg** — `iceberg_scan` есть в `duckdb_functions()` (**да (каталог)**);
  индекс поверх iceberg-вьюхи — `index/inverted_index_view_iceberg.test_slow`.

### 11.3 Логическая репликация

`CREATE PUBLICATION` / `CREATE SUBSCRIPTION` **парсятся, но не реализованы**:
`ERROR: Pragma Function with name create_publication does not exist!`
`ddl/create_publication.test:1-6`, `ddl/create_subscription.test:1-5`.

### 11.4 Форматы файлов

`COPY ... TO/FROM` c `(FORMAT parquet|csv|json|xlsx)`, чтение `read_parquet`,
`read_csv`, `read_csv_auto`, `read_json`, `read_json_auto`, `read_text`, `read_blob`,
`glob`, `query`, `query_table`. Все — **да (каталог)**.
Cookbook: `site_docs/cookbook/file_formats/*` (csv/json/parquet/excel import-export,
`read_duckdb`, `query_parquet`), `network_cloud_storage/*` (S3, S3 Express One,
GCS, Cloudflare R2, Tigris, Fastly, HTTP, Iceberg-on-S3).
Parquet: метаданные, шифрование, hive-партиционирование, partitioned writes —
`site_docs/data_import_and_export/parquet/*`, `partitioning/*`.

---

## 12. `ai_embed()` — эмбеддинги прямо в SQL

```sql
CREATE SECRET gemini (
    TYPE openai,
    api_key 'API_KEY',
    base_url 'https://generativelanguage.googleapis.com',
    embeddings_path '/v1beta/openai/embeddings'
);

-- на приёме
INSERT INTO arxiv SELECT id, title, abstract, …,
       ai_embed(abstract, 'gemini-embedding-001', 'gemini')::FLOAT[3072]
FROM read_parquet('…');

-- в запросе
SELECT title FROM arxiv_idx a
ORDER BY a.embedding <=> ai_embed('LLM agents using tools',
                                  'gemini-embedding-001', 'gemini')::FLOAT[3072]
LIMIT 5;
```
`demo5/bootstrap.sql:5-33`, `demo5/demo.sql:27-31`.
Сигнатура в сборке: `ai_embed(VARCHAR, VARCHAR, VARCHAR) -> FLOAT[]` — **да (каталог)**.
`ai_embed(NULL, …)` возвращает NULL, строка пропускается — на этом строится
`count(*) FILTER (WHERE e IS NULL)` (`site_docs/sql/functions/ai_ollama.test_slow:41-76`).
Провайдер-агностично: любой OpenAI-совместимый endpoint (Ollama:
`base_url 'http://host:11434', embeddings_path '/v1/embeddings'`).

### Секреты
```sql
CREATE [PERSISTENT] SECRET name (TYPE s3|openai, KEY_ID …, SECRET …, REGION …, SCOPE 's3://bucket');
DROP [PERSISTENT] SECRET name;   SET secret_directory = '…';
FROM duckdb_secrets();           FROM which_secret('s3://…/f.parquet', 's3');
```
`site_docs/configuration/secrets_manager.test`. `duckdb_secrets`, `which_secret` — **да (каталог)**.

---

## 13. ES-совместимый слой

ES-индекс = таблица в схеме `es` (`_id` PK, типизированные колонки по properties,
`_source`, инвертированный индекс `"<name>$text"` над text-полями).

```sql
CALL es_create_index('books', '{"mappings":{"properties":{"title":{"type":"text"},
                                "author":{"type":"keyword"},"year":{"type":"integer"}}}}');
CALL es_mapping('books');
CALL es_refresh('books');        -- '' = обновить все ES-индексы
CALL es_drop_index('books');
SELECT * FROM es_cat_indices();

INSERT INTO es.books SELECT * FROM es_doc('books', 'a', '{"title":"hello"}');
INSERT INTO es.books SELECT * FROM es_bulk('books', '{"index":{"_id":"b"}}
{"title":"quick brown fox"}
{"create":{}}
{"title":"lazy dog"}
');

SELECT "_id" FROM es."books$text" WHERE "title" @@ ts_tokenize('QUICK dog');
SELECT "_id" FROM es."books$text" WHERE "title" @@ plainto_tsquery('quick fox'); -- operator=and
SELECT "_id" FROM es."books$text" AS t WHERE "title" @@ ts_tokenize('quick')
ORDER BY BM25(t.tableoid) DESC;
```
`es/index_functions.test:7-106`, `es/write_path.test:113-203`, `es/search.test:8-67`.
Все семь функций (`es_create_index`, `es_drop_index`, `es_mapping`, `es_refresh`,
`es_cat_indices`, `es_doc`, `es_bulk`) — **да (каталог)** в 26.07.3.
Схема `es` на нашем инстансе ещё не создана (появляется при первом `es_create_index`).
Из bulk поддержаны только действия `create` и `index` (`update` — ошибка).

---

## 14. DML

### 14.1 MERGE

```sql
MERGE INTO target [AS t]
USING <source> [AS s]
  ON (<условие>)  |  USING (<колонки>)
WHEN MATCHED [AND <усл>] THEN UPDATE [SET …]
WHEN MATCHED [AND <усл>] THEN DELETE
WHEN NOT MATCHED [BY TARGET] THEN INSERT [BY NAME] [(<cols>) VALUES (…)]
WHEN NOT MATCHED BY SOURCE THEN UPDATE SET … | DELETE
RETURNING merge_action, *;
```
`site_docs/sql/statements/merge_into/index.test:16-140`;
SCD-2 пример: `cookbook/sql_features/merge.test:56-77`.
`USING (id)` — краткая форма для равенства по одноимённым колонкам.
`merge_action` в RETURNING отдаёт `UPDATE`/`DELETE`/`INSERT`.

### 14.2 INSERT ... ON CONFLICT

`DO NOTHING`, `DO UPDATE SET`, `DO UPDATE BY NAME`, conflict target с `WHERE`,
`INSERT OR REPLACE`, `INSERT ... BY NAME`, `BY POSITION`.
`site_docs/sql/statements/insert/*.test` (18 файлов).
`RETURNING` для INSERT/UPDATE/DELETE/UPSERT, в т.ч. `rowid`:
`dml/returning.test`, `dml/upsert_returning_rowid.test`, `dml/merge_returning_rowid.test`.

### 14.3 Транзакционность индекса

Инвертированный индекс обновляется транзакционно вместе с таблицей, переживает
рестарт, восстанавливается по WAL (`demo2/README.md:8`).
Изоляция: `index/inverted_index_isolation.test`, `index/inverted_index_view_isolation.test`,
`index/ts_offsets_isolation.test`, `index/vector_search_isolation.test`;
пиннинг снапшотов при DROP — `index/drop_table_snapshot_pinning.test`,
`index/iresearch_snapshot_pinning.test`.
Онлайн-создание индекса с ротацией — `index/online_create_index_rotation.test`.

### 14.4 Прочий DDL/DML

`ALTER TABLE` (add/rename/set default/set not null/add PK/struct fields),
`CREATE OR REPLACE TABLE/VIEW/SEQUENCE`, `CREATE MACRO`, `CREATE TYPE`,
`CREATE SEQUENCE` (START/INCREMENT BY/MAXVALUE/CYCLE/currval/nextval),
`TRUNCATE`, `COMMENT ON`, `EXPORT/IMPORT DATABASE`, `COPY DATABASE`,
`CALL`, `CHECKPOINT`, `USE`, `SET VARIABLE`, `PIVOT`/`UNPIVOT`, `ASOF JOIN`,
`QUALIFY`, `SAMPLE`, `GROUPING SETS`, оконные функции, лямбды, `TRY`,
`VARIANT`/`UNION`/`MAP`/`STRUCT`/`ENUM`/`BITSTRING`/`INET`/`GEOMETRY` типы.
Каталог: `site_docs/sql/statements/*`, `site_docs/sql/data_types/*`,
`site_docs/sql/query_syntax/*`.
`CREATE TABLE ... (col GENERATED ALWAYS AS (expr) STORED)` — используется как
«одно поле для всего поиска» (`cookbook/search/one-search-box.test:23-25`).

---

## 15. VACUUM: обслуживание индексов

Расширенные опции (`index/vacuum_options.test`, `site_docs/.../vacuum/index.test`):

| Команда | Смысл |
|---|---|
| `VACUUM (REFRESH_INDEX) idx` | опубликовать записи одного индекса для читателей |
| `VACUUM (REFRESH_TABLE) tbl` | все инвертированные индексы таблицы |
| `VACUUM (REFRESH_SCHEMA) s` | все индексы схемы |
| `VACUUM (REFRESH_DATABASE)` / `(REFRESH_ALL)` | база / всё |
| `VACUUM (COMPACT_INDEX\|COMPACT_TABLE\|COMPACT_SCHEMA\|COMPACT_DATABASE\|COMPACT_ALL)` | слияние сегментов |
| `VACUUM (RECOMPUTE_STATS_COLUMN\|_TABLE\|_SCHEMA\|_DATABASE\|_ALL)` | пересчёт статистики |
| `VACUUM`, `VACUUM ANALYZE`, `VACUUM tbl(col)` | стандартный PG |

**`REFRESH_*` — это то, что делает свежие записи видимыми поиску.** Практически
каждый тест кукбука после INSERT делает `VACUUM (REFRESH_TABLE) t;`.
Комбинировать SereneDB-опции со стандартными нельзя:
`ERROR: VACUUM SereneDB option 'refresh_table' cannot be combined with standard VACUUM options`.
`VACUUM FULL` не реализован. `SET vacuum_rebuild_indexes` нельзя менять на работающей БД.
Фон: `refresh_interval`/`compaction_interval` в опциях индекса (умолчание 1000 мс).

---

## 16. Наблюдаемость и системный каталог

| Объект | Что даёт | Проверено |
|---|---|---|
| `sdb_metrics` | по `relation_id` индекса: `num_docs`, `num_live_docs`, `num_segments`, `num_files`, `index_size`, `num_buffered_docs`, `avg_commit_time_ms`, `avg_consolidation_time_ms`, `avg_cleanup_time_ms`, `num_failed_*` | **да (запрос)**: `search_idx` → 97 965 док., 1 сегмент, 6 файлов, 13 057 057 байт |
| `duckdb_indexes()` | список индексов | да (запрос) |
| `duckdb_settings()` | 297 настроек | да (запрос) |
| `duckdb_functions()` | сигнатуры всех функций | да (запрос) |
| `duckdb_databases()` | `memory`/`postgres`/`system`/`temp` | да (запрос) |
| `duckdb_logs()` + `SET enable_logging=true; SET logging_storage='memory'` | SQL-доступные логи (по умолчанию логи идут в stdout) | `system/sdb_log.test:1-16` |
| `pg_class.reloptions`, `pg_am`, `pg_index`, `pg_indexes`, `pg_opclass` | PG-нативная интроспекция индексов | да (запрос) |
| `stats(col)` | статистика колонки, включая `approx_unique` при `hyperloglog=true` | `index/inverted_index_hyperloglog_option.test:37-45` |
| `EXPLAIN` / `EXPLAIN ANALYZE` | план; узлы `IRESEARCH_SCAN`, `IRESEARCH_RANGE_SCAN`, `IRESEARCH_COUNT`, `IRESEARCH_ANN_SCAN`, `IRESEARCH_ANN_RANGE_SCAN`; аннотации источника колонки `(i)` = columnstore, `(l)` = rocksdb lookup, строка `Lookup: rocksdb` | `index/inverted_index_explain_source.test:1-6`, `cookbook/performance/explain_analyze.test` |

Настройки оптимизатора: `index_scan_max_count` (2048), `index_scan_percentage`
(0.001) — порог выбора index scan против table scan; `sdb_strict_ddl` — DDL внутри
транзакции падает вместо неявного коммита.

---

## 17. Безопасность и роли

`CREATE ROLE`, `ALTER ROLE`, `DROP ROLE`, `GRANT`/`REVOKE` (в т.ч. колоночные права),
`SET ROLE`, членство в ролях с опциями, `VALID UNTIL`, prehashed-пароли, HBA.
Тесты энфорсмента: `rbac/enf_*.test` (14 файлов), `rbac/div_*.test`,
`rbac/gb_column_granted_by_membership.test`, `rbac/xsess_revoke_drop_matrix.test`;
документация: `site_docs/security/*`.
`has_table_privilege`, `has_column_privilege`, `has_schema_privilege` — присутствуют.
Отдельно: `rbac/div_vacuum_maintain.test` — право на обслуживающий VACUUM;
`rbac/enf_merge_privilege.test` — права для MERGE.

---

## 18. Драйверы, протокол, клиенты

Wire-протокол — PostgreSQL 18.3, включая extended query protocol (bind-параметры:
`\bind :qvec \g` в `demo4/demo.sql:60`) и `PREPARE`/`EXECUTE`.
Клиентские проверки: `site_docs/clients/psql.test`, `site_docs/clients/grafana.test`.
Соответствие системным таблицам PG: `site_docs/compatibility/system-table-compatibility.test`,
`system_table_claims.test`, `core_sql_claims.test` (~1900 строк заявлений о
совместимости), `sql_quirks*`, `postgresql_comparisons_pgscan.test_slow`.
Типы через pgwire: `conformance/extension_types_pgwire.test`.
Расширения **вкомпилированы**, `LOAD` не поддерживается (`simple/unsupported_extensions.test`).

---

## Второй проход

Дополнения, найденные при повторном, целенаправленном проходе.

### 18.1 `CREATE TABLE ... WITH (storage = 'search')` — второй движок хранения

Помимо инвертированного индекса поверх обычной таблицы, таблицу можно
целиком положить в iresearch-шард:
```sql
CREATE TABLE t (pk BIGINT PRIMARY KEY, r BIGINT, s TEXT)
  WITH (storage = 'search', compaction_interval = 0);
-- альтернатива: storage = 'transactional' (умолчание)
```
`simple/search_table.test:1-70`; использование: `index/search_table_rle_filter.test:9-10`,
`search_table_alp_filter.test:9-11`, `search_table_isnull_validity.test:7-9`,
`search_table_scan_10k.test`, `search_table_stats_propagation.test`.
Ошибка при неверном значении: `WITH option "storage" must be 'transactional' or 'search'`.
Косвенное подтверждение в сборке: в `pg_am` присутствует метод доступа
`iresearch` с `amtype='t'` (табличный) — **да (каталог)**.
Смысл: columnstore-хранение с кодеками (RLE, ALP, bitpacking, dict_fsst) и
проталкиванием фильтров прямо в кодек через zonemap блоков.

### 18.2 Кодеки columnstore и проталкивание фильтров

Фильтры по INCLUDE/`.col` колонкам вычисляются **внутри кодека**, не декодируя блок:
* RLE — фильтр вычисляется один раз на run (`search_table_rle_filter.test:1-6`);
* ALP (float/double) — по границам вектора из 1024 значений через
  `CompressionFunction::zonemap`, вердикты AND-комбинируются (`search_table_alp_filter.test:1-7`);
* `IS [NOT] NULL` — по одному validity-потомку, без декодирования значений
  (`search_table_isnull_validity.test:1-5`);
* `dict_fsst` — самоописывающиеся блоки, фильтр по кодеку авторитетен.
Явно зафиксировать кодек: `INCLUDE (col included (compression = 'uncompressed'))`.
Прочие покрытые кодеки: `index/inverted_index_columnstore_codecs.test`,
`inverted_index_zstd_multipage.test`, `inverted_index_dict_fsst_multirow_uaf.test`.

### 18.3 Режимы `count(*)` — три разных пути исполнения

`index/inverted_index_count_filter_modes.test:1-12`:
1. нет предиката и нет фильтров → ответ из **метаданных ридера** (узел `IRESEARCH_COUNT`);
2. фильтры по `.col`/INCLUDE-колонкам → посегментная классификация: статистика
   целиком убивает или целиком принимает файл сегмента, остальное считается через обёртку фильтра;
3. фильтр по скору или по lookup-колонке → поток с материализацией и подсчётом выживших.

**Практический вывод:** `count(*)` с предикатами только по INCLUDE-колонкам
**никогда не трогает rocksdb/parquet**. Добавление в фильтр не-INCLUDE колонки
переводит запрос в самый дорогой режим.

### 18.4 `store_pk` — как хранится первичный ключ

```sql
WITH (store_pk = 'none' | 'i64' | 'i64i64' | 'i256' | false)
```
`index/inverted_index_store_pk.test:1-6, 46`. Для fast-path вьюх PK хранится
типизированной columnstore-колонкой (BIGINT или STRUCT(hi,lo)), без PK-термов;
`'none'`/`false` не хранит PK вовсе — годится, когда индекс нужен только для
`count`/скоринга/фасетов. Опция create-time-only (`ALTER INDEX` её отвергает).

### 18.5 `ts_dict_score` — оценка похожести терма

Возвращает `FLOAT[]`, выровненный с `ts_dict_agg`. Для `ts_levenshtein` это
нормированная близость: `jaket`→`jacket` 0.8, `basket` 0.6, `racket` 0.6
(`cookbook/search/spell-correction.test:31-40`). Годится как готовая функция
«предложить исправление», без клиентского Левенштейна.
**Оговорка (см. §7):** осмысленно только для однотокенной колонки.

### 18.6 `ts_offsets` и `ts_highlight` без индекса

```sql
SELECT ts_offsets('passages_en', 'the quick brown fox', 'quick'::TSQUERY);   -- {4,9}
SELECT ts_highlight('the quick brown fox', [4, 9], 'StartSel=[, StopSel=]');
```
`full_text_search.test:712-718`, `index/headline.test:20-40`.
То есть подсветку можно считать по произвольной строке любым словарём —
например, подсветить в тексте, который в индекс не попал.

### 18.7 `ts_lexize` с массивом

Сигнатура `ts_lexize(VARCHAR, VARCHAR[]) -> VARCHAR[]` (**да (каталог)**) —
токенизация списка строк одним вызовом.
`ts_tokenize` имеет 12 перегрузок, включая `BLOB` и массивные варианты,
возвращающие `TSQUERY[]` — именно это скармливается в `ts_all`/`ts_any`
(`demo6/demo.sql:32`).

### 18.8 `ts_regexp` — байтовая семантика (критично для кириллицы)

Проверено на живом индексе `search_idx` (термы русские):

| Паттерн | Совпадений |
|---|---|
| `ts_regexp('договор')` | 565 |
| `ts_regexp('дого.ор')` | **0** |
| `ts_regexp('дого..ор')` | 0 |
| `ts_regexp('дого[вб]ор')` | **0** |
| `ts_regexp('дого(в)ор')` | **0** |
| `ts_regexp('дого.*ор')` | 565 |
| `ts_regexp('догово.')` | 0 |
| `ts_regexp('догово..')` | 1678 |
| латиница: `ts_regexp('delet.onmark')` | 39376 |
| латиница: `ts_regexp('delet[il]onmark')` | 39376 |
| латиница: `ts_regexp('delet(i\|l)onmark')` | 39376 |

Вывод: `.`, классы `[...]` и группы-альтернативы `(a|b)` работают **на байтах** и
для многобайтовых символов дают неверный/нулевой результат; надёжно работает
только `.*` и литералы. Для кириллицы вместо `ts_regexp` использовать
`ts_like` / `ts_starts_with` / `ts_levenshtein` / sparse_ngram.
Это наблюдение сделано запросом; в тестах репозитория регулярки только ASCII.

### 18.9 Одна колонка — два анализатора в одном индексе

Приём demo3: во вьюхе колонка проецируется дважды под разными именами,
и каждая привязывается к своему словарю:
```sql
CREATE VIEW imdb_fts AS SELECT text, label, text AS text_ngram FROM read_parquet('…');
CREATE INDEX imdb_fts_idx ON imdb_fts USING inverted (
  text imdb_fts_en, text_ngram imdb_fts_ngram, label);
…
WHERE text @@ (ts_regexp('osc[ae]r') && ts_levenshtein('tarintino', 2))
  AND text_ngram @@ ts_ngram('directur', 0.6) AND label = 1
ORDER BY BM25(imdb_fts_idx.tableoid) DESC;
```
`demo3/demo.sql:49-57, 167-174`. Дублирование виртуальное, индексный проход один.

### 18.10 `ts_compound` — bool-запрос в стиле Elasticsearch

```sql
ts_compound(must, must_not, should [, min_should_match])
```
16 перегрузок: каждый из трёх аргументов может быть `TSQUERY` или `TSQUERY[]`,
плюс необязательный `INTEGER`. `full_text_search.test:345`,
`site_docs/sql/indexes/inverted/full-text-search.test:262-266`.
Прямой аналог `bool { must / must_not / should / minimum_should_match }`.

### 18.11 `ts_any(list, k)` — terms-set / minimum_should_match

`WHERE skills @@ ts_any(['java','sql','rust'], 2)` — минимум 2 из 3.
Эквивалент без `@@`: `has_any_tokens(skills, ['java','sql','rust'], 2)`.
`cookbook/search/terms-set.test:35-72`. На массивной колонке `VARCHAR[]`
работает без словаря вообще.

### 18.12 Автодополнение через `LIKE` по индексу

`SELECT unnest(ts_dict_agg(query)) FROM searches_idx WHERE query LIKE 'run%'` —
`LIKE` на keyword-колонке индекса **проталкивается в словарь термов**
и ограничивает перечисление (`cookbook/search/autocomplete.test:34-58`,
`site_docs/sql/functions/term_dictionary.test:66-84`). Это единственный
случай, когда WHERE реально сужает набор термов, а не только документов.

### 18.13 Два индекса на одной таблице с разными словарями

```sql
CREATE INDEX movies_idx       ON movies USING inverted (id, title basic_dict, description basic_dict, genre);
CREATE INDEX movies_exact_idx ON movies USING inverted (id, title exact_dict, description exact_dict);
```
Запрос выбирает регистро-/диакритико-чувствительность выбором индекса
в `FROM`. `cookbook/search/case-sensitivity-and-diacritics.test:49-54, 109-124`.

### 18.14 Прочие тонкости, зафиксированные тестами

* `count(DISTINCT col)` и `approx_count_distinct(col)` по индексу
  (`cookbook/search/result-cardinality.test:47-65`); на живом `search_idx`:
  точное 226, приближённое 232.
* `ts_between(2, 3, true, true)` — включающие/исключающие границы отдельными флагами.
* `ts_le/ge` работают и по числовым/датным ключам индекса, включая
  GENERATED-колонки (`cookbook/search/computed-values.test:33-47`) и
  JSON-пути (`json-search.test:73`).
* `NOT (genre @@ 'sci-fi')` и `NOT (genre @@ ts_le('drama'))` корректно
  исполняются по индексу (`exact-value-matching.test:81`, `range-queries.test:98`).
* Индексируется массив: `(doc['tags']::VARCHAR[]) @@ ts_all(['sale','new'])`
  (`json-search.test:63`).
* `dfi` требует `frequency`; `lm_*` — тоже; без `norm` BM25 с `b>0` теряет смысл
  (`index/inverted_index_document_length.test`, `inverted_index_raw_tf.test`).
* Многотермовый скоринг ограничивается `sdb_scored_terms_limit`
  (`index/inverted_index_multiterm_score.test`, `inverted_index_wildcard_score.test`).
* Уникальный/обычный B-tree индекс — отдельный метод доступа `secondary`
  (`pg_am`), опции инвертированного к нему неприменимы
  (`ERROR: "opt_sec" is not an inverted index`).
* `hash-threshold`, `onlyif serenedb`, `control substitution on` — директивы
  раннера тестов, а не SQL.

---

## Чего в сборке 26.07.3 НЕТ

| Возможность | Где встречается в репозитории | Статус в 26.07.3 | Как проверено |
|---|---|---|---|
| Опкласс **`hnsw`** для векторов | `demo4/demo.sql:41`, `demo5/demo.sql:18`, `demo4/README.md` | **нет**, доступен только `ivf` | `pg_opclass` содержит `ivf`/`included`/словари; строки `hnsw` в бинарнике нет |
| Сканер **MySQL** (`ATTACH … (TYPE mysql)`, `mysql_scan`) | `cookbook/database_integration/mysql.test` | **нет** — расширение не вкомпилировано | сам тест ожидает ошибку `LOAD is not supported`; в `duckdb_functions()` отсутствует |
| Сканер **SQLite** (`ATTACH … (TYPE sqlite)`, `sqlite_scan`) | `cookbook/database_integration/sqlite.test` | **нет** | то же |
| `CREATE PUBLICATION` / `CREATE SUBSCRIPTION` | `ddl/create_publication.test`, `ddl/create_subscription.test` | **парсится, не работает** — `Pragma Function … does not exist` | зафиксировано самими тестами |
| `VACUUM FULL` | `site_docs/.../vacuum/index.test:41` | **нет** — `FULL is not yet implemented` | тест |
| `ts_rank`, `ts_rank_cd`, `ts_rewrite`, `ts_parse`, `ts_token_type`, `to_tsvector`/`tsvector` | `site_docs/compatibility/core_sql_claims.test:1897-1934` | **нет в `duckdb_functions()`** | запрос к каталогу функций |
| Два разных скорера в одном запросе к одному индексу | — | **нет** — `Only one scorer function is allowed per inverted index`, штатный обход через `UNION`/RRF | запрос на инстансе |
| Материализация «настоящих» колонок из view-backed индекса поверх сложной вьюхи (join/WHERE/UNION) | `site_docs/sql/indexes/inverted/views.test:83-90` | **нет** — обход: `INCLUDE (…)` | тест + README demo6 |
| Runtime-`LOAD` расширений | `simple/unsupported_extensions.test` | **нет** by design | тест |
| `SET vacuum_rebuild_indexes` на работающей БД | `vacuum/index.test:46` | **нет** — только через ATTACH-опцию | тест |
| Схема `es` на нашем инстансе | — | появится при первом `es_create_index` (сами функции есть) | `pg_namespace` |

---

## Что показалось неочевидным

1. **`WHERE` в `ts_dict_*` фильтрует документы, а не термы.** Самая опасная
   ловушка раздела «словарь термов»: `ts_dict_agg(doc) … WHERE doc @@ ts_starts_with('дог')`
   вернёт все термы подошедших документов. Кукбук выглядит иначе только потому,
   что там колонки однотокенные. Исключение — `LIKE` по keyword-колонке (§18.12),
   который действительно проталкивается в перечисление словаря.

2. **`GROUP BY` по keyword-колонке — это фасет из словаря термов, а не скан.**
   Условия конвертации жёсткие (одиночный keyword-ключ, не более одного nullable
   в GROUPING SETS, все конъюнкты WHERE claimable). Иначе — тихий откат на
   скан документов с той же семантикой, но другой ценой.
   `index/ts_dict_facets.test:6-27`.

3. **Один скорер на запрос.** Сравнить BM25 и TFIDF в одном SELECT нельзя;
   движок сам подсказывает `UNION`. Это делает RRF не «трюком», а штатным
   способом комбинировать сигналы.

4. **`optimize_top_k` требует совпадения скорера.** Индекс, построенный с
   `'bm25(1.2, 0.75)'`, не ускорит `ORDER BY tfidf(...)`. Опция create-time-only —
   поменять можно только пересозданием индекса.

5. **`ts_regexp` байтовый.** Для кириллицы `.` и `[...]` дают 0 совпадений.
   В тестах репозитория этого не видно — они все на ASCII.

6. **`VACUUM (REFRESH_*)` — не «уборка», а публикация.** Без него свежие
   INSERT просто не видны поиску до срабатывания `refresh_interval` (1000 мс).
   В тестах он стоит после каждой вставки; в проде это либо интервал, либо
   явный вызов после батча.

7. **`INCLUDE` делает индекс самодостаточным** — и это единственный способ
   получить материализацию колонок из индекса над сложной (UNION ALL) вьюхой.
   Побочный эффект: `count(*)` с фильтрами только по INCLUDE-колонкам вообще
   не открывает rocksdb.

8. **`row_number() OVER ()` во вьюхе-источнике убивает параллелизм сборки**
   (17× разницы на 11.5 млн строк). Естественный ключ вместо синтетического —
   не стилистика, а производительность.

9. **`store_pk = 'none'`** — индекс без хранения PK. Для чисто аналитических
   индексов (счётчики, фасеты, скоринг) экономит место и время сборки.

10. **`sparse_ngram` — это две разные словарные конфигурации**, индексная
    (`covering=false`, все грамы) и запросная (`covering=true`, минимальная
    цепочка). Вторая никогда не привязана к индексу; она живёт только как
    аргумент `ts_tokenize`/`ts_lexize`. Без пары `ts_all(...) + LIKE`-постфильтра
    результат неточен.

11. **`ts_phrase` в каталоге функций объявлена как одноаргументная**, но
    вариадическая форма со слопом (`ts_phrase('plot', ARRAY[0,3], 'twist')`)
    работает — `duckdb_functions()` её не показывает. То же для `##`.
    Каталог функций не полон; проверять надо выполнением.

12. **`ST_*` работают только внутри индексного контекста** — вне `WHERE`
    по индексированной гео-колонке `ST_Distance_Centroid` осознанно падает.

13. **`storage = 'search'` для таблицы** — отдельный, почти не разрекламированный
    движок хранения (в `pg_am` он виден как табличный метод `iresearch`).
    В демках его нет вообще; он есть только в низкоуровневых тестах кодеков.

14. **Опции индекса продублированы как сессионные настройки** с теми же именами.
    `SET refresh_interval = 0` до `CREATE INDEX` даёт тот же эффект, что
    `WITH (refresh_interval = 0)`, и `ALTER INDEX ... RESET` возвращает именно
    сессионное значение, а не заводское.
