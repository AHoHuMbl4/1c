# Каталог возможностей SereneDB

Составлен по репозиторию `/srv/data/cursor/cursor/1/serenedb-src` (ветка `main`)
и проверен на живом инстансе `192.168.56.42:7890`, сборка **26.07.3**
(`/opt/serenedb-dist/serenedb-26.07.3-linux-amd64/usr/bin/serened`).

Обозначения в конце каждого пункта:
- **[ЕСТЬ]** — проверено запросом на нашем инстансе 26.07.3;
- **[РЕПО]** — есть в исходниках/тестах, на инстансе отдельно не проверялось
  (обычно потому, что проверка требует DDL, а менять сервер запрещено);
- **[НЕТ]** — проверено, что в нашей сборке отсутствует.

Проверочные команды, которыми пользовался:

```bash
ssh -i /home/ahohum/.ssh/id_ed25519_1c root@192.168.56.42
D="host=127.0.0.1 port=7890 user=postgres dbname=postgres"
psql "$D" -tAF' | ' -c "SELECT function_name, parameter_types, return_type FROM duckdb_functions() WHERE function_name LIKE 'ts\_%'"
psql "$D" -tAF' | ' -c "SELECT name, value, description FROM duckdb_settings() WHERE name LIKE 'sdb%'"
psql "$D" -c "CREATE TEXT SEARCH DICTIONARY zz(help);"   # печатает полный справочник опций словаря и падает
```

---

# 1. Модель объектов

| Объект | Что это | Доказательство |
|---|---|---|
| `TEXT SEARCH DICTIONARY` | токенизатор/анализатор; является одновременно **опклассом** для `CREATE INDEX` | `server/pg/commands/create_tsdictionary.cpp:146` |
| `CREATE INDEX ... USING inverted(...)` | инвертированный индекс IResearch: постинги + типизированный columnstore + IVF-граф | `tests/sqllogic/sdb/pg/site_docs/sql/indexes/inverted/index.test:22` |
| индекс как **отношение** | `FROM <index_name>` — обязательная форма для поиска; от имени таблицы `@@` не работает | `.../inverted/index.test:33`, ошибка `TSQUERY expression evaluated outside an @@ match` |
| `USING secondary` | обычный ART-индекс (b-tree-подобный), `CREATE INDEX i ON t(col)` | `tests/sqllogic/sdb/pg/index/secondary_index_point_lookup.test:19` |
| таблица `WITH (storage='search')` | таблица, чей storage — сам iresearch (без rocksdb-строк) | `tests/sqllogic/sdb/pg/simple/search_table.test:10` |
| `es.<index>` / `es."<index>$text"` | ES-совместимый слой поверх обычных таблиц и индексов | `tests/sqllogic/sdb/pg/es/index_functions.test:35` |

Access-methods в нашей сборке **[ЕСТЬ]**:
```sql
SELECT amname, amtype FROM pg_am;   -- inverted|i, iresearch|t, secondary|i
```
Опклассы в нашей сборке **[ЕСТЬ]**: `ivf` (real[]), `included` (any) + по одному
опклассу на каждый созданный словарь.
```sql
SELECT opcname, opcintype::regtype FROM pg_opclass;
```

---

# 2. Полнотекстовый поиск

## 2.1 Оператор `@@`

```sql
SELECT ... FROM <index_name> WHERE <indexed_col> @@ <tsquery_expr>;
```
Левая часть обязана быть проиндексированной колонкой этого индекса, иначе:
`@@ requires an inverted-indexed column on one side`. **[ЕСТЬ]**

Строковый литерал справа неявно приводится к `TSQUERY`
(`WHERE body @@ 'search'`) — `.../inverted/index.test:33`. **[ЕСТЬ]**

## 2.2 Функции построения `tsquery`

Все проверены в нашей сборке через `duckdb_functions()`. **[ЕСТЬ]**

| Функция | Сигнатуры | Что делает | Доказательство |
|---|---|---|---|
| `ts_phrase` | `(VARCHAR)`, `(BLOB)`, `(part, gap, part, ...)` | точная фраза; варианты со слопом: `ts_phrase('plot', ARRAY[0,3], 'twist')` | `examples/demo3/demo.sql:70`, `site_docs/sql/functions/full_text_search.test` |
| `ts_tokenize` | `(text)`, `(text, dict)`, `(VARCHAR[])`, `(VARCHAR[], dict)` | токенизирует строку выбранным словарём и строит из токенов запрос; массив → массив `TSQUERY` | `examples/demo6/demo.sql:33` |
| `ts_starts_with` | `(VARCHAR)`, `(BLOB)` | префиксный поиск по терму | `examples/demo3/demo.sql:96` |
| `ts_like` | `(VARCHAR)`, `(BLOB)` | wildcard `%` и `_` по терму | `examples/demo3/demo.sql:100` |
| `ts_regexp` | `(VARCHAR)`, `(VARCHAR, VARCHAR)` | regex по терму; 2-й аргумент — диалект (`'posix'`) | `full_text_search.test` секция `ts_regexp_posix` |
| `ts_levenshtein` | `(t)`, `(t,dist)`, `(t,dist,transpositions)`, `(t,dist,transp,prefix)` | фаззи по терму; 3-й — учитывать перестановки, 4-й — обязательный точный префикс | `cookbook/search/fuzzy-search.test:60..` |
| `ts_ngram` | `(t)`, `(t, threshold DOUBLE)` | нечёткое совпадение по Жаккару над ngram-словарём | `cookbook/search/fuzzy-search.test:110..` |
| `ts_lt/le/gt/ge` | `(ANY)` | диапазон по значению колонки из индекса | `full_text_search.test` |
| `ts_between` | `(lo, hi, incl_lo BOOL, incl_hi BOOL)` | диапазон | `.../inverted/full-text-search.test:example_014` |
| `ts_any` | `(TSQUERY[])`, `(TSQUERY[], k INTEGER)` | ИЛИ; с `k` — «минимум k из списка» (Elastic `terms_set`) | `cookbook/search/terms-set.test:33` |
| `ts_all` | `(TSQUERY[])` | И по списку | `examples/demo6/demo.sql:33` |
| `ts_compound` | `(must, should, must_not[, min_should INTEGER])`, каждый аргумент — `TSQUERY` или `TSQUERY[]` | прямой аналог Elastic `bool` | `full_text_search.test` секция `ts_compound` |
| `to_tsquery` | `(VARCHAR)` | Lucene/PG-синтаксис: `AND`, `OR`, `+term`, `-term`, `"фраза"` | `.../full-text-search.test:example_019` |
| `plainto_tsquery` | `(VARCHAR)` | все слова через И | `example_017` |
| `phraseto_tsquery` | `(VARCHAR)` | все слова как фраза | `example_018` |
| `websearch_to_tsquery` | `(VARCHAR)` | «как в гугле»: кавычки, `OR`, `-` | `example_020` |
| `tsquery_phrase` | `(TSQUERY, TSQUERY[, slop INTEGER])` | функциональная форма `##` | `full_text_search.test` секция `tsquery_phrase` |
| `ts_lexize` | `(dict, text)`, `(dict, VARCHAR[])` → `VARCHAR[]` | показать токены словаря (отладка) | `.../inverted/text-analysis.test:12` |
| `ts_split_by_non_alpha` | `(VARCHAR)`, `(VARCHAR, BOOLEAN)` → `VARCHAR[]` | разбить строку по не-буквам | `tests/sqllogic/sdb/pg/simple/ts_split_by_non_alpha.test` |

Проверено на инстансе **[ЕСТЬ]** (на нашем `search_idx`, колонка `doc`):
```
ts_phrase('счет')                        -> 2639
ts_levenshtein('счёт', 2)                -> 4427
ts_starts_with('счет')                   -> 6002
ts_like('%счет%')                        -> 10591
ts_regexp('сч[её]т')                     -> 2639
ts_phrase('единый', ARRAY[0,3], 'счет')  -> 11
```

## 2.3 Булевы функции-предикаты (без `@@`)

Работают только внутри `WHERE` над индексом, возвращают `BOOLEAN`. **[ЕСТЬ]**

| Функция | Сигнатура |
|---|---|
| `phrase_matches(col, 'фраза')` | `(ANY, VARCHAR)` |
| `ngram_matches(col, 'слово'[, threshold])` | `(ANY, VARCHAR[, DOUBLE])` |
| `levenshtein_matches(col, 'слово', dist[, transp[, prefix]])` | `(ANY, VARCHAR, INTEGER, ...)` |
| `has_all_tokens(col, ['a','b'])` | `(ANY, VARCHAR[])` |
| `has_any_tokens(col, ['a','b'][, k])` | `(ANY, VARCHAR[], INTEGER)` |

Доказательство: `site_docs/sql/functions/full_text_search.test` (секции
`phrase_matches`, `has_any_tokens`), `cookbook/search/terms-set.test:60`.

## 2.4 Операторы `tsquery`

| Оператор | Смысл | Пример |
|---|---|---|
| `\|\|` | ИЛИ | `ts_phrase('a') \|\| ts_phrase('b')` |
| `&&` | И | `ts_phrase('a') && ts_phrase('b')` |
| `!!` | НЕ (унарный) | `ts_phrase('a') && !!ts_phrase('b')` |
| `##` | фразовая последовательность | `'quick' ## 'brown'` |
| `## N ##` / `## ARRAY[min,max] ##` | слоп между частями | `'quick' ## [0,2] ## 'fox'` |
| `^ N` | буст скоринга поддерева | `('refund'::tsquery ^ 5.0)` |

`##` склеивает **разнородные** части: голое слово, `ts_starts_with`,
`ts_like`, `ts_levenshtein`, `ts_phrase`, `ts_any`, `ts_between` —
`examples/demo3/demo.sql:186..200`. **[ЕСТЬ]** (проверен разбор выражения
`((('plot' ## 'twist') ^ 3) || 'surprise ending')::text`).

## 2.5 Обычные SQL-предикаты по индексу

Внутри `FROM <index>` работают и обычные предикаты — они пушатся в скан:
`WHERE query LIKE 'run%'` (`cookbook/search/autocomplete.test:44`),
`WHERE amount >= 1000`, `WHERE doc_date >= TIMESTAMP '2024-01-01'`,
`WHERE id < 5`, `IS NULL` / `IS NOT NULL`. **[ЕСТЬ]**

Важное различие:
- колонка в списке `inverted(...)` → фильтр уходит в постинги;
- колонка только в `INCLUDE (...)` → фильтр становится residual FILTER над сканом.
`tests/sqllogic/sdb/pg/index/inverted_index_include_pushdown.test:1`.

---

# 3. Модели ранжирования

Все скореры вызываются как `<scorer>(<index>.tableoid[, params])`.

| Функция | Параметры | Смысл |
|---|---|---|
| `bm25(oid)` | `bm25(oid, k1 DOUBLE, b DOUBLE)` | BM25; `b=0` → BM15 |
| `tfidf(oid)` | `tfidf(oid, with_norms BOOLEAN)` | классический TF-IDF |
| `lm_jm(oid)` | `lm_jm(oid, lambda DOUBLE)` | Jelinek–Mercer, `lambda ∈ (0,1]` |
| `lm_dirichlet(oid)` | `lm_dirichlet(oid, mu DOUBLE)` | LM Dirichlet |
| `indri_dirichlet(oid)` | `indri_dirichlet(oid, mu DOUBLE)` | Indri Dirichlet |
| `dfi(oid)` | `dfi(oid, measure VARCHAR)` — `standardized` (умолч.), `saturated`, `chi_squared` | Divergence From Independence |
| `raw_tf(oid)` | — | сырая частота терма в документе |
| `raw_dl(oid)` | — | длина документа в токенах |
| `raw_boost(oid)` | — | только буст запроса |

Доказательство: `server/catalog/scorer_options.cpp:55..198`,
`site_docs/sql/functions/full_text_search.test` (секции `bm25`..`raw_dl`).

Проверено на нашем `search_idx` **[ЕСТЬ]**:
```
bm25=3.3226285  bm25(1.2,0.0)=3.6140308  tfidf=3.640433  lm_jm=5.551916
lm_dirichlet(5.0)=3.2287781  indri_dirichlet=-6.5562735  dfi('chi_squared')=4.7845416
raw_tf=1  raw_dl=37
```

**Жёсткое ограничение движка (проверено на инстансе):** в одном запросе к одному
инвертированному индексу допустим **ровно один** скорер.
```
ERROR:  Only one scorer function is allowed per inverted index
HINT:  Use UNION to combine different score functions for the same inverted index
```
Т.е. сравнение моделей делается через `UNION ALL` подзапросов. **[ЕСТЬ]**

Комбинирование ранга с бизнес-сигналами — обычная арифметика SQL:
`ORDER BY BM25(idx.tableoid) * popularity DESC` (`cookbook/search/boosting.test:78`),
`... * (1.0/(1+age_days))` (`cookbook/search/recency-and-decay.test:47`),
`... * LOG(runtime+1)` (`cookbook/search/ranking.test:167`).

Пинning результатов: `ORDER BY array_position(ARRAY[5,2,7], id) NULLS LAST, BM25(...) DESC`
(`cookbook/search/pinned-results.test:253`).

RRF-слияние текстового и векторного списков — чистый SQL с `ROW_NUMBER()` и
`SUM(1.0/(60+rank))` (`cookbook/search/reciprocal-rank-fusion.test:380`,
`cookbook/search/hybrid-search.test:88`).

---

# 4. Подсветка и офсеты

## 4.1 `ts_highlight`

Пять перегрузок (все **[ЕСТЬ]**):

```sql
-- 1) виртуальная колонка индекса: берёт офсеты текущего матча
SELECT ts_highlight(body) FROM articles_idx WHERE body @@ 'search';
-- 2) то же + опции
SELECT ts_highlight(body, 'StartSel=<mark>, StopSel=</mark>') FROM ...;
-- 3) произвольный текст + готовые байтовые офсеты
SELECT ts_highlight('the quick brown fox', [4,9]);          -- the <b>quick</b> brown fox
-- 4) то же + опции
SELECT ts_highlight('the quick brown fox', [4,9], 'StartSel=[, StopSel=]');
-- 5) БЕЗ индекса вообще: словарь + текст + tsquery
SELECT ts_highlight('search_dict', 'the quick brown fox', 'quick'::tsquery);
SELECT ts_highlight('search_dict', 'the quick brown fox', 'quick'::tsquery, 'StartSel=[, StopSel=]');
```

Порядок аргументов в форме 5 — **сначала имя словаря**, потом текст, потом запрос.
Проверено на инстансе (форма `(text, dict, query)` даёт
`text search dictionary not found: <текст>`).

Опции (`server/connector/highlight/highlight_options.cpp:34..51`):

| Опция | Умолчание | Смысл |
|---|---|---|
| `StartSel` | `<b>` | открывающая обёртка |
| `StopSel` | `</b>` | закрывающая обёртка |
| `MaxWords` | `35` | предел токенов во фрагменте |
| `HighlightAll` | `false` | отдать весь документ, без выбора пассажа |
| `MaxFragments` | `0` | `0` = один лучший фрагмент; `>0` — до N лучших |
| `FragmentDelimiter` | ` ... ` | склейка фрагментов |
| `MaxOffsets` | `0` | предел пар офсетов (0 = без предела) |

Синтаксис — `Key=Value` через запятую в одной строке.
Проверено на нашем индексе **[ЕСТЬ]**:
`ts_highlight(doc, 'MaxWords=12')` вернул
`... Единый налоговый <b>счет</b> / 68.90 / ...`.

Выбор пассажа границами предложений — ICU-сегментация; `.`, `!`, `?`, перевод
строки считаются границами, `:` — нет (`tests/sqllogic/sdb/pg/index/headline.test:60..96`).

## 4.2 `ts_offsets`

```sql
SELECT ts_offsets(body)                                   FROM idx WHERE body @@ 'x'; -- {start,end,start,end,...}
SELECT ts_offsets(body, 6)                                FROM idx WHERE ...;         -- предел пар
SELECT ts_offsets('dict_name', 'произвольный текст', 'q'::tsquery);                   -- standalone
SELECT ts_offsets('dict_name', 'текст', 'q'::tsquery, 3);
```
Возвращает `INTEGER[]` — байтовые диапазоны. Комбинируется:
`ts_highlight(body, ts_offsets(body))`
(`site_docs/sql/functions/full_text_search.test` секция `ts_highlight_pipeline`). **[ЕСТЬ]**

Для офсетов словарь должен быть создан с `offset = true`
(`examples/demo3/demo.sql:38`). На нашем `search_dict` `ts_offsets` работает — **[ЕСТЬ]**
(`{109,117}`).

---

# 5. Словари и токенизаторы

## 5.1 Синтаксис

```sql
CREATE TEXT SEARCH DICTIONARY <name> ( template = '<tmpl>', <опции...> );
DROP TEXT SEARCH DICTIONARY [IF EXISTS] <name>;
```
Словарь резолвится из схемы **целевой таблицы** — для каждой схемы нужен свой
экземпляр (`tests/sqllogic/sdb/pg/index/vacuum_options.test:17`).

Полный справочник опций печатает сам движок:
```sql
CREATE TEXT SEARCH DICTIONARY zz(help);   -- падает с ошибкой-справкой
```
Проверено — вывод в 26.07.3 совпадает с репозиторием байт в байт.

## 5.2 Флаги индексных фич (общие для всех шаблонов)

| Опция | Умолчание | Смысл |
|---|---|---|
| `norm` | `false` | хранить нормы длины документа (нужны BM25/TFIDF-with-norms) |
| `frequency` | `false` | частоты термов (нужны любому скореру) |
| `position` | `false` | позиции (нужны фразам и слопу) |
| `offset` | `false` | байтовые офсеты (нужны `ts_offsets`/`ts_highlight`) |
| `norm_row_group_size` | `DEFAULT_ROW_GROUP_SIZE` | размер row-group для колонки норм |

`server/pg/tokenizer_options.h:63..84`.

## 5.3 Все шаблоны (`template = ...`)

Проверено `strings` по бинарнику 26.07.3 — **все 23 присутствуют**. **[ЕСТЬ]**

| Шаблон | Опции | Назначение |
|---|---|---|
| `text` | `locale`, `case` (`none/lower/upper`), `accent`, `stemming`, `stopwords`, `stopwordspath` + подгруппа edge-ngram: `mingram`, `maxgram`, `preserveoriginal` (имена БЕЗ префикса) | основной анализатор естественного языка |
| `keyword` | — | значение целиком как один терм (точное совпадение/фасеты) |
| `ngram` | `mingram`, `maxgram`, `preserveoriginal`, `inputtype` (`utf8/binary`), `startmarker`, `endmarker` | подстрочный / опечаточный поиск |
| `sparse_ngram` | `maxngramlength` (≥3, умолч. 16), `covering` | схема GitHub code search: индексная сторона `covering=false`, запросная `covering=true` |
| `norm` | `locale`, `case`, `accent` | только нормализация, без разбиения |
| `stem` | `locale` | только стемминг |
| `stopwords` | `stopwords`, `hex` | удаление стоп-слов |
| `delimiter` | `delimiter` (обяз.) | разбиение по строке-разделителю |
| `multi_delimiter` | `delimiters` (обяз.) | несколько разделителей |
| `pattern` | `pattern` (обяз., RE2), `group` (`-1` split, `0` весь матч, `N` группа) | regex-токенизация |
| `path_hierarchy` | `delimiter` (`/`), `replacement`, `reverse`, `skip`, `buffersize` | иерархия путей / доменов |
| `segmentation` | `case`, `break` (`all/graphic/alpha`) | ICU word-break |
| `collation` | `locale` | ICU collation key как терм |
| `wildcard` | `ngramsize` (≥2, умолч. 3) | ускорение wildcard-запросов |
| `minhash` | `numhashes` | LSH-подпись документа |
| `classification` | `modellocation`, `topk`, `threshold` | fastText-классификатор как источник термов |
| `nearest_neighbors` | `modellocation`, `topk` | расширение запроса ближайшими словами модели |
| `solr_synonyms` | `synonyms` (обяз., инлайн Solr-формат: `tv, television, telly` и `laptop => notebook`) | синонимы |
| `wordnet_synonyms` | `synonyms` (обяз., инлайн WordNet Prolog `s(...)`) | синонимы через synset-id |
| `pipeline` | подопции `stepN_*` | последовательная цепочка токенизаторов |
| `union` | подопции `tokenizerN_*` | объединение выходов нескольких токенизаторов |
| `copy_from` | `from` (обяз.) + переопределяемые опции источника | клон существующего словаря с правками |
| `geopoint` | `latitude`, `longitude`, + `options_{maxcells,minlevel,maxlevel,levelmod,optimizeforspace}` | S2-индекс точки из JSON |
| `geojson` | `type` (`shape/centroid/point`), `coding` (`source/s2point/s2latlngf64/s2latlngu32`), + те же `options_*` | S2-индекс произвольной GeoJSON-геометрии |

Доказательства: `server/pg/tokenizer_options.h:105..433`,
`libs/iresearch/include/iresearch/analysis/*.hpp` (`type_name()`),
`tests/sqllogic/sdb/pg/simple/tokenizers/text_tokenizer.test` (все шаблоны),
`tests/sqllogic/sdb/pg/site_docs/sql/indexes/inverted/text-analysis.test`.

## 5.4 Примеры точного синтаксиса

```sql
-- «Эталонный» английский анализатор из демок
CREATE TEXT SEARCH DICTIONARY imdb_en(
    template = 'text', locale = 'en_US.UTF-8', case = 'lower',
    stemming = false, accent = false,
    frequency = true, position = true, norm = true, offset = true);

-- 3-граммы
CREATE TEXT SEARCH DICTIONARY imdb_ngram(
    template = 'ngram', mingram = 3, maxgram = 3,
    preserveoriginal = false, frequency = true, position = true);

-- sparse_ngram: индексная и запросная стороны — ДВА разных словаря
CREATE TEXT SEARCH DICTIONARY code_grams  (template='sparse_ngram', frequency=true, norm=true);
CREATE TEXT SEARCH DICTIONARY code_grams_q(template='sparse_ngram', covering=true);

-- pipeline: нормализация -> синонимы
CREATE TEXT SEARCH DICTIONARY syn (
    template = 'pipeline',
    step1_template = 'text', step1_locale='en_US.UTF-8',
    step1_case='lower', step1_stemming=false,
    step2_template = 'solr_synonyms',
    step2_synonyms = 'tv, television, telly
laptop => notebook',
    frequency = true, position = true);

-- union: один и тот же текст двумя анализаторами в одну колонку
CREATE TEXT SEARCH DICTIONARY union_text_ngram3(
    template = 'union',
    tokenizer1_template='text', tokenizer1_locale='en_US.UTF-8',
    tokenizer1_case='lower', tokenizer1_stemming=true,
    tokenizer2_template='ngram', tokenizer2_mingram=3, tokenizer2_maxgram=3,
    frequency = true, position = true);

-- вложенный pipeline (шаг сам является pipeline)
CREATE TEXT SEARCH DICTIONARY nested(
    template='pipeline',
    step1_template='norm', step1_locale='en_US.UTF-8', step1_case='lower',
    step2_template='pipeline',
      step2_step1_template='delimiter', step2_step1_delimiter='|',
      step2_step2_template='norm', step2_step2_locale='en_US.UTF-8', step2_step2_case='upper');

-- клон с правкой
CREATE TEXT SEARCH DICTIONARY copy_geopoint_override(
    template='copy_from', from='geopoint_basic', latitude='x', longitude='y');
```
Источники: `examples/demo3/demo.sql:26..46`, `examples/demo6/bootstrap.sql:33..56`,
`cookbook/search/synonyms.test:7`, `simple/tokenizers/text_tokenizer.test:1181..1553,2216`.

## 5.5 Ограничения шаблонов

- `sparse_ngram` **не поддерживает** `position` и `offset`:
  `ERROR: Unsupported index features are specified: 3 / 7`
  (`simple/tokenizers/sparse_ngram_tokenizer.test:31..50`).
- `maxngramlength` < 3 отвергается.
- Опции чужого шаблона отвергаются с
  `option "X" is not applicable in this context / HINT: Use WITH (HELP)`.
- Гео-словари требуют колонку типа `JSON` или `GEOMETRY`, `VARCHAR` отвергается
  (`tests/sqllogic/sdb/pg/index/geo_search.test:5`).

---

# 6. `CREATE INDEX ... USING inverted`

## 6.1 Полная грамматика

```sql
CREATE INDEX <name> ON <table|view>
USING inverted (
    <col>,                       -- без словаря: типизированный/keyword терм
    <col> <dictionary>,          -- анализируемая колонка
    (<expression>),              -- индекс по выражению
    (<expression>) <dictionary>,
    <vec_col> ivf (metric='cosine', quant='sq8', ...)
)
[ INCLUDE ( <col>, <col> included (compression='zstd', hyperloglog=true), ... ) ]
[ WITH ( <опции> ) ]
[ WHERE <предикат> ]            -- частичный индекс
;
```

## 6.2 `INCLUDE` — колонки в columnstore индекса

Колонки в `INCLUDE` хранятся в типизированном columnstore самого индекса и
отдаются без похода в таблицу. Колонка может быть **и** в списке ключей, **и** в
`INCLUDE` — тогда есть и постинги (пушдаун фильтров), и быстрая проекция
(`index/inverted_index_indexed_vs_included.test:1..20`).

Per-column опции опкласса `included` (`server/catalog/index.cpp:114`):

| Опция | Значения | Смысл |
|---|---|---|
| `compression` | `auto` (умолч.), `uncompressed`, `rle`, `bitpacking`, `zstd`, `alp`, `alprd`, `roaring`, `dict_fsst` | принудительный кодек столбца |
| `hyperloglog` | `true/false` (умолч. `false`) | считать NDV в HLL, отдавать оптимизатору как `approx_unique` |

```sql
CREATE INDEX i ON t USING inverted(txt en)
  INCLUDE (pk, big_int included (compression = 'uncompressed'),
           v included (hyperloglog = true));
```
`index/inverted_index_compression_option.test:38`,
`index/inverted_index_hyperloglog_option.test:24`.

Полностью самодостаточный индекс (demo6): каждая извлекаемая колонка попадает в
`INCLUDE`, после сборки запросы не трогают источник вообще —
`examples/demo6/bootstrap.sql:105..131`.

## 6.3 `WITH (...)` — опции индекса

`server/connector/inverted_index_options_util.h:42..75`,
проверены `strings` в бинарнике 26.07.3 **[ЕСТЬ]**.

| Опция | Умолчание (наш инстанс) | ALTER | Смысл |
|---|---|---|---|
| `row_group_size` | `122880` | нет | row-group columnstore |
| `norm_row_group_size` | `122880` | нет | row-group колонки норм |
| `refresh_interval` | `1000` | да | мс до публикации новых сегментов (0 = выключить фон) |
| `compaction_interval` | `1000` | да | мс между компакциями (0 = выключить) |
| `cleanup_interval_step` | `1` | да | шаг фоновой чистки (0 = выключить) |
| `segment_memory_max` | `268435456` | да | память на сегмент |
| `segment_docs_max` | `0` (= без предела) | да | документов на сегмент |
| `compaction_max_segments` | `10` | да | |
| `compaction_max_segments_bytes` | `5368709120` | да | |
| `compaction_floor_segment_bytes` | `2097152` | да | |
| `optimize_top_k` | не задан | нет | включает WAND-прунинг под указанный скорер |
| `store_pk` | `auto` | нет | `none`/`auto`/`i64`/`i64i64` (или `true`/`false`) |

Значения видно так **[ЕСТЬ]**:
```sql
SELECT relname, reloptions FROM pg_class WHERE relname = 'search_idx';
```

`refresh_interval` и `compaction_interval` есть и как **сессионные** переменные:
`SET refresh_interval = 0; SHOW refresh_interval;` — проверено **[ЕСТЬ]**.

`ALTER INDEX i SET (segment_memory_max = 33554432, compaction_max_segments = 5);`
`ALTER INDEX i RESET (segment_memory_max);`
`ALTER INDEX IF EXISTS i SET (...)` — `index/inverted_index_options.test:50,63,171`.

### `optimize_top_k` — WAND / Block-Max top-K

```sql
CREATE INDEX movies_idx ON movies USING inverted (...)
  WITH (optimize_top_k = 'bm25(1.2, 0.75)');
```
Значение — **выражение скорера**: `bm25`, `tfidf`, `lm_jm`, `lm_dirichlet`,
`indri_dirichlet`, `dfi`, `raw_boost`, `raw_tf`, `raw_dl`
(`server/catalog/scorer_options.cpp:198`).

WAND срабатывает только когда: индекс собран с `optimize_top_k`, запрос имеет
форму `WHERE <фильтр> ORDER BY <тот же скорер>(idx.tableoid) DESC LIMIT k`, и
фильтр компилируется в итератор с per-block max-impact (одиночный `Term` или
`ByTerms`-дизъюнкция) — `index/inverted_index_wand.test:1..17`.

Глобальный выключатель: `SET sdb_disable_top_k_optimization = true`. **[ЕСТЬ]**

### `store_pk`

`none` — не хранить PK вообще: индекс годится только для `count`, скоринга и
`INCLUDE`-колонок; попытка вытащить колонку из источника даёт
`inverted index "..." was created WITH (store_pk = 'none'), so it does not store
row PKs`. `i64` — однокомпонентный ключ, `i64i64` — пара `(file_index, row)`
для view над глобом файлов. `index/inverted_index_store_pk.test:43,111,121`.

## 6.4 Частичный индекс

```sql
CREATE INDEX pt_live ON t USING inverted(label) WHERE live;
```
Предикат становится фильтром в плане backfill; при DML строки мигрируют в индекс
и из него; `NULL` считается `false`. `index/inverted_index_partial.test:1..40`.

## 6.5 Индекс по выражению

```sql
CREATE INDEX i ON products USING inverted (id, (lower(name)), price_with_tax);
CREATE INDEX i ON people   USING inverted (id, (first || ' ' || last));
CREATE INDEX i ON orders   USING inverted (id, (CASE WHEN amount>=100 THEN 'big' ELSE 'small' END));
```
Запрос обязан повторить выражение дословно:
`WHERE lower(name) @@ 'widget'` (`cookbook/search/computed-values.test:736..825`).
Запрещены агрегаты (`aggregate functions are not allowed in index expressions`) и
выражения с побочными эффектами (`random()`) — `.../inverted/modeling.test:example_006,007`.

Также индексируются `GENERATED ALWAYS AS (...) STORED` колонки
(`cookbook/search/one-search-box.test:24` — «одна строка поиска» через
`concat_ws(' ', ...)`).

## 6.6 JSON / VARIANT

```sql
CREATE TABLE products (id INTEGER PRIMARY KEY, doc VARIANT);
CREATE INDEX products_idx ON products USING inverted (
    id,
    (doc['name']::VARCHAR) jtext,
    (doc['attrs']['brand']::VARCHAR),
    (doc['tags']::VARCHAR[]),
    (doc['price']::INTEGER));

SELECT id FROM products_idx WHERE (doc['tags']::VARCHAR[]) @@ ts_all(['sale','new']);
SELECT id FROM products_idx WHERE (doc['price']::INTEGER) @@ ts_ge(40);
```
`cookbook/search/json-search.test:836..917`, `index/inverted_index_json.test`.

## 6.7 Массивы и списки

`TEXT[]` индексируется поэлементно: `WHERE tags @@ 'blue'`
(`.../inverted/modeling.test:example_004`). `INCLUDE` умеет `LIST<VARCHAR>`,
`ARRAY`, `STRUCT`, `UNION`, `VARIANT`, `INET`
(`index/inverted_index_list_include.test`, `..._variant_include.test`,
`..._union_struct_include.test`, `..._inet_include.test`).

## 6.8 ALTER TABLE и индекс

- `RENAME COLUMN` / `RENAME TABLE` / `ALTER INDEX ... RENAME` — индекс следует за
  переименованием (ключ по id колонки);
- `ADD COLUMN [DEFAULT]` — нейтрально, существующие строки добираются;
- `DROP COLUMN`, покрытой индексом → каскадно удаляет индекс;
- `ALTER COLUMN TYPE` на проиндексированной колонке запрещён.

`tests/sqllogic/sdb/pg/ddl/alter_table_inverted_index.test:1..10`.

---

# 7. Настройки движка

## 7.1 `sdb_*` (сессионные, `duckdb_settings()`) — все **[ЕСТЬ]** в 26.07.3

| Настройка | Умолч. | Смысл |
|---|---|---|
| `sdb_disable_top_k_optimization` | `off` | выключить WAND-прунинг |
| `sdb_scored_terms_limit` | `1024` | сколько термов мультитермового фильтра участвуют в скоринге; `0` — не собирать |
| `sdb_nprobe` | `8` | сколько IVF-списков сканировать на запрос (recall vs latency) |
| `sdb_rerank_factor` | `4` | пул кандидатов = `k * factor` для точного переранжирования квантованного IVF; `0` — без переранжирования |
| `sdb_ivf_posting_size` | `1024` | целевой размер postings-листа IVF (фиксируется в CREATE INDEX) |
| `sdb_ivf_sample_factor` | `0` | доля строк для обучения дерева центроидов; `0` = авто |
| `sdb_strict_ddl` | `off` | DDL в транзакции падает вместо немедленного коммита |

## 7.2 Другие полезные сессионные

`refresh_interval`, `compaction_interval` (те же, что и опции индекса; `SET` задаёт
умолчание для создаваемых индексов), `threads`, `memory_limit`,
`http_retries`, `http_retry_wait_ms` (важно для Hugging Face — `examples/demo6/bootstrap.sql:29`),
`preserve_identifier_case`, `secret_directory`, `enable_logging`, `logging_storage`,
`profiling_renderer_settings`. Всего в `duckdb_settings()` 297 записей. **[ЕСТЬ]**

## 7.3 Серверные (`sdb_settings`, только чтение/флаги старта) **[ЕСТЬ]**

`listen`, `cpu_threads`, `io_threads`, `background_threads`, `max_connections`,
`pg_max_message_bytes`, `idle_session_timeout`, `auth_timeout`,
`auth_api_key`, `auth_bearer_token`, `hba_config`, `http_cors_origins`,
`http_body_timeout`, `tls_cert`, `tls_key`, `tls_ca`, `tls_ciphers`, `tls_groups`,
`tls_min_version`, `log_level`, `log_storage`, `log_path`, `server_directory`,
`flagfile`, плюс блок настроек S2 (`s2*`).

```sql
SELECT name, setting, vartype, short_desc FROM sdb_settings ORDER BY name;
```

`listen` понимает `postgres://host:port[?sslmode=...]`, `http(s)://host:port?api=es`,
`postgres:///path/to.sock`.

---

# 8. Словарь термов, фасеты, статистика

## 8.1 Агрегаты словаря термов (все **[ЕСТЬ]**)

| Функция | Возврат | Смысл |
|---|---|---|
| `ts_dict_agg(col)` | `VARCHAR[]` | все живые термы колонки (в байтовом порядке) |
| `ts_dict_raw_agg(col)` | `BLOB[]` | то же в сырых байтах |
| `ts_dict_count(col)` | `INTEGER[]` | документов на терм (aligned с `ts_dict_agg`) |
| `ts_dict_freq(col)` | `BIGINT[]` | суммарная частота терма |
| `ts_dict_score(col)` | `FLOAT[]` | скор терма (напр. similarity при фаззи-`WHERE`) |
| `ts_dict_min(col)` | `VARCHAR` | минимальный терм |
| `ts_dict_max(col)` | `VARCHAR` | максимальный терм |

Все списки выровнены — типовой приём:
```sql
SELECT unnest(ts_dict_agg(body))   AS term,
       unnest(ts_dict_count(body)) AS docs,
       unnest(ts_dict_freq(body))  AS freq
FROM posts_idx ORDER BY freq DESC;
```
`site_docs/sql/functions/term_dictionary.test:33`, `cookbook/search/tag-cloud.test:40`.

Проверено на нашем `search_idx` **[ЕСТЬ]**:
```
ts_dict_min(src_table)  -> accountingregister_хозрасчетный_recordtype
ts_dict_max(src_table)  -> informationregister_хранилищеданных
ts_dict_agg/count       -> {catalog_вариантыотчетов,...} / {955,123,6,43,38}
ts_dict_score(doc) при WHERE doc @@ ts_levenshtein('счёт',2) -> {1,1,1}
```

Семантика: `WHERE` фильтрует **документы**, агрегат возвращает **все термы этих
документов**. Ограничение по термам выражается внешним фильтром — он пушится в
перечисление термов (`index/ts_dict_fuzzy.test:1..8`,
`site_docs/sql/functions/term_dictionary.test:66..96`):
```sql
SELECT unnest(ts_dict_agg(body)) AS term FROM idx WHERE body LIKE 'g%';
```

Не работает для числовых колонок: `column has no text term dictionary`
(`index/ts_dict_numeric.test:31`). Нужна текстовая или `keyword` VARCHAR-колонка
(или массив таких).

## 8.2 Фасеты через `GROUP BY`

`SELECT col, count(*) FROM idx GROUP BY col` над keyword-колонкой обслуживается
прямо из словаря термов, без материализации документов
(`index/ts_dict_facets.test:1..14`). Работает и `GROUPING SETS`:
```sql
SELECT ... FROM products_idx
GROUP BY GROUPING SETS ((category), (brand), (price_band));
```
`cookbook/search/faceted-search.test:160`. Проверено на нашем индексе **[ЕСТЬ]**:
`SELECT src_table, count(*) FROM search_idx GROUP BY src_table` — мгновенно.

## 8.3 Прочая аналитика из индекса **[ЕСТЬ]**

- `count(*)`, `min`, `max`, `avg`, `sum` по `INCLUDE`-колонкам;
- `approx_quantile(col, 0.5)` — медиана (demo6 Q5/Q7);
- `approx_count_distinct(col)` и `count(DISTINCT col)`
  (`cookbook/search/result-cardinality.test:447`); проверено: 232 (approx) vs 226 (exact);
- `stats(col)` → `{"has_no_null":..,"min":..,"max":..[,"approx_unique":..]}`
  (`index/inverted_index_hyperloglog_option.test:33`);
- оконные функции поверх результата поиска: `ROW_NUMBER() OVER (PARTITION BY ...)`
  для «лучший в группе» (`cookbook/search/grouping-results.test:693`);
- `JOIN` результата поиска с обычными таблицами и с **другим индексом**
  (`examples/demo6/demo.sql:41`, `cookbook/search/search-with-joins.test:966`).

Значимые термы (significant terms Elastic) — считаются SQL-ом из двух
`ts_dict_count` (фон и передний план) — `cookbook/search/significant-terms.test:100`.

---

# 9. Векторный поиск

## 9.1 Опкласс

**В нашей сборке доступен только `ivf`.** `hnsw` отсутствует в `pg_opclass`
и вообще не встречается в исходниках `server/` — он остался только в
`examples/demo4|demo5` и `scripts/perf/*`. **[НЕТ]**

```sql
CREATE INDEX i ON t USING inverted (id, emb ivf (metric = 'cosine'));
```

Опции `ivf` (`server/catalog/index.cpp:56..59, 313..410`):

| Опция | Значения |
|---|---|
| `metric` | `l2`, `l1`, `cosine`, `ip` (обязательна) |
| `quant` | `none`, `sq8`, `sq4`, `pq`, `rabitq` |
| `pq_m` | число подпространств, только при `quant='pq'` |
| `rabitq_bits` | биты, только при `quant='rabitq'` |

Тюнинг — сессионными `sdb_nprobe`, `sdb_rerank_factor`, `sdb_ivf_posting_size`,
`sdb_ivf_sample_factor`.

Тесты: `index/inverted_index_ivf_pq.test`, `..._ivf_sq8.test`, `..._ivf_sq4.test`,
`..._ivf_rabitq.test`, `..._ivf_levels.test`, `..._ivf_filter.test`,
`..._ivf_exact_distance.test`, `..._ivf_nulls.test`.

Колонка должна быть типизированным фиксированным вектором `FLOAT[N]`.

## 9.2 Операторы дистанции **[ЕСТЬ]**

| Оператор | Метрика |
|---|---|
| `<->` | L2 |
| `<+>` | L1 |
| `<=>` | cosine |
| `<#>` | negative inner product |

Скалярные функции: `l2_distance`, `l2_sqr_distance`, `l1_distance`,
`cosine_distance`, `cosine_similarity`, `inner_product`,
`negative_inner_product`, `l2_norm`, `l1_norm`, `l2_normalize`, `l1_normalize`,
`array_distance`, `array_cosine_similarity`. **[ЕСТЬ]**

## 9.3 Формы запроса

```sql
-- top-K ANN (план IRESEARCH_ANN_SCAN)
SELECT title FROM idx ORDER BY emb <=> $1::FLOAT[1536] LIMIT 5;

-- range search (план IRESEARCH_ANN_RANGE_SCAN)
SELECT title FROM idx WHERE emb <=> $1::FLOAT[1536] < 0.3 LIMIT 10;

-- гибрид: текстовый фильтр + векторное ранжирование
SELECT title FROM idx
WHERE text @@ (ts_phrase('physicist') && !!ts_phrase('philosophy'))
ORDER BY emb <=> $1::FLOAT[1536] LIMIT 5;
```
`examples/demo4/demo.sql:56..96`. Вектор передаётся bind-параметром расширенного
протокола (`\bind`), приведение `$1::FLOAT[N]` сворачивается на этапе плана.

Дополнительно: `ivf`-колонка неявно получает `store_values=true`, т.е. вектор
доступен для проекции из индекса (`index/inverted_index_indexed_vs_included.test`).

---

# 10. Гео-поиск

Словари `geojson` / `geopoint` (см. 5.3). Тип колонки — `GEOMETRY(...)` или `JSON`.

Предикаты, понимаемые сканом индекса **[ЕСТЬ]** (вне индекса выдают
`Inverted index function called outside inverted index context`):

| Предикат | Смысл |
|---|---|
| `ST_Intersects(field, shape)` | пересечение (коммутативно) |
| `ST_Contains(a, b)` | вхождение (в любом порядке аргументов) |
| `ST_Distance_Centroid(field, point) < D` | радиус |
| `field <-> point < D` | то же оператором |
| `ST_Distance_Between(field, point, min, max)` | кольцо |

`site_docs/sql/functions/full_text_search.test` (секции `st_*`),
`cookbook/search/geospatial-search.test:1270..1305`,
`server/connector/geo_filter_builder.cpp:155,335`.

`ST_AsText`, литералы `'POINT(...)'::GEOMETRY('OGC:CRS84')` — **[ЕСТЬ]**.

---

# 11. Индексирование внешних данных (Zero-ETL)

## 11.1 View как цель индекса

```sql
CREATE VIEW imdb_v AS
  SELECT * FROM read_parquet('hf://datasets/stanfordnlp/imdb@~parquet/plain_text/**/*.parquet');
CREATE INDEX imdb_idx ON imdb_v USING inverted(text imdb_en, label);
```
Движок распознаёт `SELECT * FROM read_parquet(<один строковый литерал>)` как
fast-path источник и сам строит составной PK `(file_index, file_row_number)`
(`examples/demo0/demo.sql:35..44`).

Ограничение fast-path (для **материализации** колонок): тело view должно быть
плоской проекцией колонок из одного `read_*(<один VARCHAR>)`, без JOIN, без
`WHERE`, только касты и алиасы. Иначе `count(*)`, скоринг и ANN всё равно
работают, а проекция реальных колонок падает с
`materialising real columns from this view-backed inverted index is not yet supported`
(`.../inverted/views.test:generic_error`, `examples/demo4/bootstrap_view.sql:14..27`).

Обход: положить все нужные колонки в `INCLUDE` — тогда источник не нужен вовсе
(паттерн demo6). Тогда допустимы и `UNION ALL` мега-view над разными схемами,
и `CASE`, и `row_number()`, и `array_to_string(...)`
(`examples/demo6/bootstrap.sql:58..131`).

Совет из demo6, подтверждённый цифрой: **не использовать `row_number() OVER ()`**
как id — глобальное окно сериализует конвейер в один поток; с натуральным ключом
параллельный sink даёт **17x** на сборке 11.5M строк (`examples/demo6/README.md:33`).

## 11.2 Источники, доступные в нашей сборке **[ЕСТЬ]**

```sql
SELECT extension_name FROM duckdb_extensions() WHERE installed;
```
`autocomplete, avro, core_functions, httpfs, iceberg, icu, inet, json,
parquet, postgres_scanner, tpcds, tpch`.

Табличные функции **[ЕСТЬ]**: `read_parquet`, `read_csv`, `read_json`,
`read_json_auto`, `read_duckdb`, `read_text`, `read_blob`, `iceberg_scan`,
`postgres_scan`, `postgres_query`, `parquet_metadata`, `query`, `query_table`.

Протоколы через `httpfs`: `http(s)://`, `s3://`, `gcs://`, `r2://`, `hf://`
(cookbook `network_cloud_storage/*`).

`ATTACH '<path>.duckdb' AS db;` и индекс над view к присоединённой БД —
`index/inverted_index_view_attached.test:12..60`. **[РЕПО]**

## 11.3 Экспорт

`COPY (SELECT ...) TO '<path>' (FORMAT PARQUET|CSV|JSON)` — включая серверную
выкачку с Hugging Face (`examples/demo1/bootstrap.sql:11`). **[РЕПО]**
Partitioned writes и hive partitioning — `site_docs/data_import_and_export/partitioning/*`.

---

# 12. DML

- `INSERT`, `UPDATE`, `DELETE` — индекс обновляется транзакционно вместе с таблицей
  (`examples/demo2/README.md:8`).
- `INSERT ... ON CONFLICT` (upsert) — `tests/sqllogic/sdb/pg/simple/insert_conflict.test`,
  `index/inverted_index_insert_conflict_include.test`.
- `MERGE INTO ... USING ... ON ...` с ветками
  `WHEN MATCHED [AND ...] THEN UPDATE SET`,
  `WHEN NOT MATCHED BY SOURCE THEN UPDATE SET`,
  `WHEN NOT MATCHED BY TARGET THEN INSERT (...) VALUES (...)`,
  `RETURNING merge_action, *`
  (`site_docs/cookbook/sql_features/merge.test:55..78`). **[РЕПО]**
- `RETURNING` для `INSERT/UPDATE/DELETE/MERGE` — `dml/returning.test`,
  `dml/merge_returning_rowid.test`.
- `TRUNCATE`, `COPY ... FROM`, `CREATE TABLE AS` (атомарный) — `ddl/ctas_atomic.test`.
- Кросс-БД запись — `dml/cross_database_write.test`.
- `CREATE SEQUENCE` / `nextval()` — используется в merge-рецепте.

Видимость: записи становятся видимыми поиску после публикации сегмента
(`refresh_interval` или явный `VACUUM (REFRESH_*)`) —
`index/vacuum_options.test:76..96`.

---

# 13. Обслуживание: `VACUUM`

Расширенные опции (ровно одна на команду, нельзя смешивать со стандартными
опциями `VACUUM`) — `index/vacuum_options.test`. Грамматика проверена на
инстансе **[ЕСТЬ]** (по текстам ошибок).

| Команда | Аргумент | Действие |
|---|---|---|
| `VACUUM (REFRESH_INDEX) <idx>` | обяз. | опубликовать сегменты одного индекса |
| `VACUUM (REFRESH_TABLE) <tbl>` | обяз. | все индексы таблицы |
| `VACUUM (REFRESH_SCHEMA) [<db>.]<schema>` | обяз. | |
| `VACUUM (REFRESH_DATABASE) <db>` | обяз. | |
| `VACUUM (REFRESH_ALL)` | запрещён | всё в инстансе |
| `VACUUM (COMPACT_INDEX\|COMPACT_TABLE\|COMPACT_SCHEMA\|COMPACT_DATABASE) <obj>` | обяз. | слить сегменты |
| `VACUUM (COMPACT_ALL)` | запрещён | |
| `VACUUM (RECOMPUTE_STATS_TABLE) <tbl>` | обяз. | пересчитать статистику |
| `VACUUM (RECOMPUTE_STATS_COLUMN) [<schema>.]<tbl>.<col>` | обяз. | |
| `VACUUM (RECOMPUTE_STATS_SCHEMA\|_DATABASE) <obj>` | обяз. | |
| `VACUUM (RECOMPUTE_STATS_ALL)` | запрещён | |

Имена принимают полную квалификацию `<db>.<schema>.<obj>`.

## Метрики обслуживания — `sdb_metrics` **[ЕСТЬ]**

```sql
SELECT * FROM sdb_metrics;
```
Даёт: `pg_connections`, `http_connections`, `refresh_active/pending`,
`compaction_active/pending`, `cleanup_active/pending`, и **на каждый индекс**:
`num_docs`, `num_live_docs`, `num_buffered_docs`, `num_segments`, `num_files`,
`index_size` (байты), `num_failed_commits/cleanups/consolidations`,
`avg_commit_time_ms`, `avg_cleanup_time_ms`, `avg_consolidation_time_ms`.

На нашем инстансе: `num_docs=97965`, `num_segments=1`, `index_size=13057057`,
`avg_commit_time_ms=180`.

---

# 14. ES-совместимый слой

Table/procedure-функции **[ЕСТЬ]** (`duckdb_functions()`):
`es_create_index`, `es_drop_index`, `es_mapping`, `es_cat_indices`,
`es_refresh`, `es_doc`, `es_bulk`.

```sql
CALL es_create_index('books', '{"mappings":{"properties":{
       "title":{"type":"text"},"author":{"type":"keyword"},"year":{"type":"integer"}}}}');
INSERT INTO es.books SELECT * FROM es_doc('books','a','{"title":"hello","year":7}');
INSERT INTO es.books SELECT * FROM es_bulk('books', '{"index":{"_id":"1"}}
{"title":"The Quick Brown Fox"}
{"create":{}}
{"title":"lazy dog"}
');
CALL es_refresh('books');
SELECT "_id" FROM es."books$text" WHERE "title" @@ ts_tokenize('QUICK dog');
SELECT "_id" FROM es."books$text" AS t WHERE "title" @@ ts_tokenize('quick')
ORDER BY BM25(t.tableoid) DESC;
CALL es_mapping('books');
SELECT * FROM es_cat_indices();
CALL es_drop_index('books');
```
`tests/sqllogic/sdb/pg/es/index_functions.test`, `es/search.test`, `es/write_path.test`.

Устройство: ES-индекс = таблица в схеме `es` (`_id` PK, типизированные колонки по
properties, `_source`) + инвертированный индекс `<index>$text`. Типы `text`
(инвертированный VARCHAR) и `keyword`; анализатор — `es."standard"`
(lowercase, без стемминга, `server/connector/functions/es.cpp:247`).
`match` = `@@ ts_tokenize(...)` (operator=or) или `plainto_tsquery` (operator=and).
`geo_shape` не поддержан.

HTTP-слушатель для ES API поднимается через `--listen http://host:port?api=es`.

---

# 15. `ai_embed` и секреты

```sql
CREATE SECRET gemini (
    TYPE openai,
    api_key '...',
    base_url 'https://generativelanguage.googleapis.com',
    embeddings_path '/v1beta/openai/embeddings');

INSERT INTO arxiv SELECT ..., ai_embed(abstract, 'gemini-embedding-001', 'gemini')::FLOAT[3072] ...;

SELECT title FROM arxiv_idx a
ORDER BY a.embedding <=> ai_embed('LLM agents using tools','gemini-embedding-001','gemini')::FLOAT[3072]
LIMIT 5;
```

- Сигнатура: `ai_embed(text VARCHAR, model VARCHAR, secret_name VARCHAR) -> FLOAT[]`.
  **[ЕСТЬ]** (в `duckdb_functions()`).
- Аргументы `model` и `secret_name` должны быть **константными выражениями**
  (`server/connector/functions/embedding/embedding.cpp:92`).
- Тип секрета — только `openai`; поля `api_key`, `base_url`, `embeddings_path`;
  `api_key` редактируется в выводе. Умолчания: `https://api.openai.com` +
  `/v1/embeddings` (`provider_openai.cpp:41`).
  Другие протоколы: `Unknown embedding protocol '...' (supported: openai)`.
- Секреты общего назначения: `CREATE [PERSISTENT] SECRET name (TYPE s3, KEY_ID,
  SECRET, REGION, SCOPE ...)`, `DROP [PERSISTENT] SECRET`, `SET secret_directory`,
  интроспекция `duckdb_secrets()`, `which_secret(path, type)` **[ЕСТЬ]**.
  `site_docs/configuration/secrets_manager.test`.
  На инстансе `secret_directory = /home/serenedb/.duckdb/stored_secrets`.

`ai_embed` — сетевой вызов внутри SQL: при `INSERT ... SELECT` он делается на
сервере, без выгрузки текста клиенту.

---

# 16. Интроспекция, план, отладка

- `duckdb_indexes()`, `duckdb_settings()`, `duckdb_functions()`,
  `duckdb_extensions()`, `duckdb_secrets()`, `duckdb_logs()` **[ЕСТЬ]**;
- PG-каталог: `pg_class` (в т.ч. `reloptions`, `relam`), `pg_index`, `pg_am`,
  `pg_opclass`, `pg_ts_dict`, `pg_indexes`, `pg_roles`, `pg_attribute` **[ЕСТЬ]**;
- `sdb_settings`, `sdb_metrics` **[ЕСТЬ]**;
- `pg_stat_progress_copy`, `pg_stat_progress_create_index` **[РЕПО]**;
- `EXPLAIN` / `EXPLAIN ANALYZE`; узлы: `IRESEARCH_SCAN`, `IRESEARCH_ANN_SCAN`,
  `IRESEARCH_ANN_RANGE_SCAN`, `TABLE_SCAN (Index Scan / Sequential Scan)`.
  `EXPLAIN` печатает дерево `Index Filter`, строку `Score: bm25(k1=1.2, b=0.75)`,
  `Top: k`, `Projections:` и `Lookup:` **[ЕСТЬ]** — проверено на `search_idx`;
- аннотации источника колонки в плане: `(i)` = columnstore индекса,
  `(l)` = lookup в rocksdb (`index/inverted_index_explain_source.test:1`);
- `SET profiling_renderer_settings = {'deterministic': true}`;
- `DESCRIBE`, `SUMMARIZE TABLE t`, `SUMMARIZE <query>` (`cookbook/meta/*`);
- логи: `SET enable_logging = true; SET logging_storage='memory'; SELECT * FROM duckdb_logs();`
  или `CALL enable_logging(storage='file', storage_path='...')`.

---

# 17. Безопасность, доступ, протокол

- Роли: `CREATE ROLE r LOGIN PASSWORD '...'`, `CREATE USER`, `ALTER ROLE`,
  `DROP ROLE`, `GRANT ... TO`, членство, `SET ROLE`, `VALID UNTIL`
  (`site_docs/security/roles.test`, `managing_roles.test`, `role_membership.test`).
- Привилегии: `GRANT SELECT/INSERT/... ON <obj> TO <role>`, колоночные гранты,
  `has_table_privilege()` (`site_docs/security/privileges.test`,
  `privileges_advanced.test`, `rbac/gb_column_granted_by_membership.test`).
- `pg_hba.conf` (флаг `hba_config`), `pg_hba_file_rules`,
  тесты `rbac/enf_password_auth.test`, `enf_password_prehashed.test`,
  `enf_set_hba_superuser.test`.
- TLS: `tls_cert/key/ca/ciphers/groups/min_version`, `?sslmode=` в `listen`.
- HTTP-аутентификация: `auth_api_key` (`id:key`), `auth_bearer_token`;
  пустые значения означают «отвергать».
- Протоколы: pg-wire (простой и расширенный, `\bind`, `PREPARE/EXECUTE`),
  HTTP ES API, unix-сокет. Клиенты — любой PG-драйвер; в тестах есть psql и
  Grafana (`site_docs/clients/*`).
- `pg_max_message_bytes = 67108864`: крупные данные грузить через `COPY`.

---

# 18. Восстановление и WAL

Отдельный корпус `tests/sqllogic/recovery/` (≈90 файлов). Покрыто:
восстановление инвертированного индекса из WAL после падения
(`wal_index_recovery*.test` — include-колонки, гибрид, IVF/IVF-SQ8, гео,
wildcard, variant, union, multicolumn, multi-index, длинные строки, unicode,
частичное отставание, `refresh` до/после checkpoint, TRUNCATE-цепочки,
переиспользование rowid, stress-loop), восстановление каталога
(`catalog_*.test`: таблицы, view, схемы, функции, секвенции, токенизаторы,
вторичные индексы, ATTACH), `drop_cascade_*_recovery`, `faults.test`,
`crash_on_packet.test`, `hba_persist.test`, `database_size.test`,
`zstd_segment_stats.test`.

Практический вывод: инвертированный индекс — обычный вторичный индекс,
durable и восстанавливаемый; отдельного «переиндексируй после рестарта» не нужно.

---

# 19. SQL-диалект: что доступно сверх обычного PG

- Trailing comma в `SELECT`, списковые литералы `['a','b']`,
  `max(val, N)` → топ-N как список, `SELECT * EXCLUDE (...) / REPLACE (...)`,
  `COLUMNS(...)`, лямбды, `list_*`/`map`/`struct`-функции
  (`site_docs/sql/dialect/sql_extensions.test`, `sql/expressions/star/*`).
- Типы: `VARIANT`, `UNION`, `MAP`, `STRUCT`, `LIST`, `ARRAY`, `GEOMETRY`,
  `INET`, `BITSTRING`, `ENUM`, `TSQUERY` (`site_docs/sql/data_types/*`).
- `ASOF JOIN` (`cookbook/sql_features/asof_join.test`).
- `query()` / `query_table()` — динамический SQL **[ЕСТЬ]**.
- `GROUPING SETS`, `ROLLUP`, `CUBE`, оконные функции, `QUALIFY`.
- `CREATE OR REPLACE TABLE/VIEW`, `COMMENT ON`.
- Ограничение: `LOAD <extension>` запрещён — расширения вкомпилированы в бинарник
  (`cookbook/database_integration/mysql.test:9`).

---

# 20. Соответствие «Elastic-фича → SereneDB»

| Elastic | SereneDB |
|---|---|
| `match` | `col @@ ts_tokenize('...')` / `plainto_tsquery` |
| `match_phrase` | `col @@ ts_phrase('...')` |
| `match_phrase` + `slop` | `ts_phrase('a', ARRAY[0,N], 'b')` или `'a' ## [0,N] ## 'b'` |
| `bool{must,should,must_not,minimum_should_match}` | `ts_compound(must, should, must_not, k)` или `&&`/`\|\|`/`!!` |
| `term` / `terms` | `col @@ 'value'` / `ts_any(['a','b'])` |
| `terms_set` | `ts_any([...], k)` / `has_any_tokens(col, [...], k)` |
| `range` | `ts_lt/le/gt/ge/between` или обычный SQL-предикат |
| `prefix` | `ts_starts_with` |
| `wildcard` | `ts_like` |
| `regexp` | `ts_regexp` |
| `fuzzy` | `ts_levenshtein(t, dist, transpositions, prefix)` |
| `boost` | `^ N` |
| `highlight` | `ts_highlight` + `ts_offsets` |
| `terms` aggregation / facets | `GROUP BY` или `ts_dict_agg`+`ts_dict_count` |
| `significant_terms` | два `ts_dict_count` + SQL |
| `cardinality` | `approx_count_distinct` |
| `percentiles` | `approx_quantile` |
| `top_hits` per group | `ROW_NUMBER() OVER (PARTITION BY ...)` |
| `knn` | `ORDER BY emb <=> $1 LIMIT k` (IVF) |
| RRF | `UNION ALL` + `SUM(1.0/(60+rank))` |
| `_search` REST | HTTP-listener `?api=es` + `es_*` функции |

`.../inverted/migrating-from-elasticsearch.test`, `examples/demo3/README.md`.

---

# Второй проход

Ниже — то, что не попало в первый проход и было найдено при повторном чтении
исходников `server/`, тестов `index/`/`simple/tokenizers/` и при прямых пробах
на инстансе.

## П2.1 Встроенный справочник опций — `(HELP)`

Любой блок опций умеет напечатать себя:

```sql
CREATE TEXT SEARCH DICTIONARY zz(help);           -- полный список шаблонов и опций
COPY t FROM 'f.csv' WITH (HELP);                  -- опции COPY
```
Это не «фича из доков», а рабочий способ узнать точный набор опций **своей**
сборки. Проверено: вывод 26.07.3 совпадает с репозиторием. Механизм —
`server/pg/option_help.cpp`, ошибка-подсказка
`HINT: Use WITH (HELP) to see available options`.
Для `ts_highlight` HELP **не** поддержан (`option "HELP" has no value`). **[ЕСТЬ]**

## П2.2 Один скорер на запрос

Не описано ни в одной демке; выяснено пробой:
```
SELECT bm25(i.tableoid), tfidf(i.tableoid) FROM i WHERE ... ;
ERROR:  Only one scorer function is allowed per inverted index
HINT:   Use UNION to combine different score functions for the same inverted index
```
Значит демка demo3 «четыре модели рядом» — это четыре **отдельных** запроса,
а не один. Для A/B моделей нужен `UNION ALL`. **[ЕСТЬ]**

## П2.3 Standalone-подсветка без индекса

Форма `ts_highlight(<имя словаря>, <текст>, <tsquery>[, <опции>])` и
`ts_offsets(<имя словаря>, <текст>, <tsquery>[, <лимит>])` работают над
**произвольной строкой**, индекс не нужен. Порядок аргументов — словарь первым.
Это даёт подсветку для текста, который пришёл не из индекса (например,
склеенного фрагмента). **[ЕСТЬ]**

## П2.4 `edgengram` внутри `text`

У шаблона `text` есть **вложенная подгруппа** `edgengram` с опциями
`mingram` / `maxgram` / `preserveoriginal`. В HELP она печатается с отступом
внутри `text:`, но в DDL имена пишутся **без префикса** — проверено на инстансе:
`edgengram_mingram` даёт `option "edgengram_mingram" not recognized`, а
голое `mingram` внутри `template='text'` принимается.

```sql
CREATE TEXT SEARCH DICTIONARY text_edge_ngram(
    template = 'text', locale = 'en_US.UTF-8', case = 'lower',
    stemming = false, mingram = 2, maxgram = 4);
SELECT ts_lexize('text_edge_ngram', 'hello');   -- {he,hel,hell}
```
`simple/tokenizers/text_tokenizer.test:452..487`, `server/pg/tokenizer_options.h:281..302`.
То есть edge-ngram-автокомплит делается одним словарём `text`, без отдельного
ngram-словаря; порядок — стемминг сначала, ngram потом. **[ЕСТЬ]** (имя опции
подтверждено пробой на 26.07.3.)

## П2.5 `copy_from` — наследование словаря

`template = 'copy_from', from = '<другой словарь>'` создаёт копию с
возможностью переопределить отдельные опции. Удобно, чтобы держать
«индексный» и «запросный» варианты одного анализатора в синхроне
(`simple/tokenizers/text_tokenizer.test:1341,2216`). **[РЕПО]**

## П2.6 `union`-словарь: два анализатора в одну колонку

`template='union'` с `tokenizerN_*` подопциями пишет термы **обоих**
анализаторов в одну колонку — альтернатива приёму demo3 «продублировать
колонку в теле view». Меньше места в индексе, но нельзя адресовать анализаторы
раздельно в запросе (`text_tokenizer.test:1499..1553`). **[РЕПО]**

## П2.7 Синонимы как штатный механизм

Два шаблона — `solr_synonyms` (инлайн Solr-формат, поддерживает
одностороннее `=>`) и `wordnet_synonyms` (инлайн WordNet Prolog, термом
становится synset-id). Обычно ставятся вторым шагом `pipeline` после `text`.
`cookbook/search/synonyms.test`. **[РЕПО]** (шаблоны присутствуют в бинарнике 26.07.3).

## П2.8 Частичный индекс и индекс по выражению

`CREATE INDEX ... USING inverted(...) WHERE <предикат>` — предикат уходит в
план backfill как column filter, строки мигрируют при DML.
`index/inverted_index_partial.test`. Индексы по выражению
(`(lower(name))`, `(a || ' ' || b)`, `(CASE ...)`) с обязательным дословным
повтором выражения в `WHERE`. **[РЕПО]**

## П2.9 `store_pk` — индекс без строк

`WITH (store_pk = 'none')` строит индекс, который умеет только `count`, скоринг
и `INCLUDE`-колонки, но экономит место на PK. Варианты `i64` / `i64i64` —
явный контроль формы ключа для view над одним файлом / над глобом.
`index/inverted_index_store_pk.test`. **[РЕПО]**

## П2.10 Per-column `compression` и `hyperloglog` в `INCLUDE`

`INCLUDE (v included (compression='zstd', hyperloglog=true))`. HLL даёт
оптимизатору `approx_unique` для оценки кардинальности join-ов; без опции
`stats(col)` вернёт только min/max/null-флаги. **[РЕПО]**
(Проверено на нашем индексе: `stats(amount)` возвращает
`{"has_no_null":true,"has_null":true,"max":5000000.0,"min":0.0}` — без
`approx_unique`, т.е. HLL у нас не включён.) **[ЕСТЬ]**

## П2.11 WAND — не «включено по умолчанию»

Прунинг top-K требует, чтобы индекс был **создан** с
`WITH (optimize_top_k = '<скорер>')` и запрос использовал **тот же** скорер в
`ORDER BY ... DESC LIMIT k`. Наш `search_idx` создан без `optimize_top_k`
(видно в `pg_class.reloptions`), значит WAND у нас не работает.
Дополнительно фильтр должен быть одиночным `Term` или дизъюнкцией термов —
фраза/фаззи/regex под WAND не попадают (`index/inverted_index_wand.test:1..17`). **[ЕСТЬ]**

## П2.12 `sdb_scored_terms_limit`

Мультитермовые фильтры (префикс, wildcard, regex, фаззи) скорят не более
`sdb_scored_terms_limit` термов (умолч. 1024). Значение `0` полностью
отключает сбор скоринговых термов. То есть у широких `ts_like('%x%')` ранг
может быть усечён — это настраивается. **[ЕСТЬ]**

## П2.13 `sdb_strict_ddl`

По умолчанию DDL **не транзакционен**: внутри `BEGIN ... ROLLBACK` он всё равно
коммитится. `SET sdb_strict_ddl = true` заставляет DDL в транзакционном блоке
падать вместо тихого коммита. Существенно для миграций. **[ЕСТЬ]**

## П2.14 `sdb_metrics` — наблюдаемость индекса

Не упоминается в демках. Даёт размер индекса на диске, число сегментов,
буферизованных документов, счётчики фоновых задач и средние времена коммита/
консолидации — то, чем меряется, «успевает ли refresh». **[ЕСТЬ]**

## П2.15 Термовые агрегаты умеют ещё три вещи

- `ts_dict_score` — скор терма; при `WHERE col @@ ts_levenshtein(...)`
  это готовая **similarity для spell-correction**
  (`cookbook/search/spell-correction.test:40..60`);
- `ts_dict_raw_agg` — сырые байты термов (`BLOB[]`), нужно для не-UTF8 и для
  sparse-ngram-грамм;
- `ts_dict_min` / `ts_dict_max` — границы словаря без полного перечисления.
Все три **[ЕСТЬ]** — проверены на `search_idx`.

## П2.16 Автокомплит по keyword-колонке

`CREATE INDEX i ON searches USING inverted (query)` (без словаря → keyword) и
затем `SELECT unnest(ts_dict_agg(query)), unnest(ts_dict_count(query))
FROM i WHERE query LIKE 'run%'` — готовый suggest с частотами, целиком в индексе
(`cookbook/search/autocomplete.test`). Ключевая деталь: `LIKE` тут фильтрует
**термы**, а не документы, потому что колонка keyword и фильтр пушится в
перечисление термов. **[РЕПО]**

## П2.17 Точность vs. регистр/диакритика — двумя индексами

Штатный приём: два индекса на одной таблице с разными словарями
(`case='lower', accent=false` и `case='none', accent=true`) и выбор индекса в
запросе (`cookbook/search/case-sensitivity-and-diacritics.test:1230..1236`).
Никакой «второй колонки» не нужно. **[РЕПО]**

## П2.18 `IS NULL` / `IS NOT NULL` и трёхзначная логика

Индекс хранит null-маркер как отдельный терм; `IS NULL`/`IS NOT NULL` работают
из постингов, а отрицания получают автоматический guard-конъюнкт, чтобы NULL не
возвращались (`index/null_semantics.test:1..11`). Значит фильтры по
необязательным полям безопасны без ручного `COALESCE`.

## П2.19 Prepared statements и параметры в `@@`

Параметры расширенного протокола подставляются как константы при каждом
`EXECUTE`, поэтому фильтр компилируется так же, как для инлайн-запроса
(`index/tsquery_params.test:1..5`). Для векторного поиска это единственный
приемлемый способ передать 1536/3072-мерный вектор (`examples/demo4/demo.sql:60`).

## П2.20 `storage = 'search'` таблицы

`CREATE TABLE t (...) WITH (storage = 'search')` — таблица, чей storage сам
iresearch (без rocksdb-строк). Допустимые значения: `transactional` (умолч.) и
`search`. `simple/search_table.test:1..48`. **[РЕПО]**

## П2.21 Мультидокументные ограничения view-индексов

Кроме известного «fast-path только `SELECT * FROM read_x(literal)`», есть список
параметров ридера, которые ломают материализацию: сжатый JSON, явные
`column_types`/`names` для CSV, hive-partitioning для parquet. Детектирующие
knobs (`auto_detect`, `sample_size`, `files_to_sniff`, ...) на материализацию не
влияют (`index/inverted_index_view_params.test:1..14`).
Также: строки, удалённые в источнике после `CREATE INDEX`, материализуются как
NULL — индекс «пиннит» то, что проиндексировал
(`index/inverted_index_view_attached.test:1..7`).

## П2.22 Логическая репликация не реализована

`CREATE PUBLICATION` / `CREATE SUBSCRIPTION` разбираются грамматикой, но
исполнения нет: `Pragma Function with name create_publication does not exist!`
(`ddl/create_publication.test`, `ddl/create_subscription.test`). **[НЕТ]**

## П2.23 `ts_compound` — полный аналог Elastic `bool`

4-аргументная форма `ts_compound(must, should, must_not, minimum_should_match)`;
каждый из первых трёх может быть как одиночным `TSQUERY`, так и `TSQUERY[]`
(16 перегрузок в `duckdb_functions()`). Это то, чем заменяется ручная сборка
`&&`/`||`/`!!`, когда «должно совпасть хотя бы k из should». **[ЕСТЬ]**

## П2.24 `ts_regexp` с диалектом и `ts_levenshtein` с префиксом

`ts_regexp('gr[ae]y', 'posix')` — второй аргумент выбирает диалект regex.
`ts_levenshtein('X', 1, true, 'quic')` — обязательный точный префикс `quic`,
фаззи только по хвосту. Резко сужает автоматный обход словаря термов —
практический способ сделать фаззи-поиск дешёвым.
`full_text_search.test` секции `ts_regexp_posix`, `ts_levenshtein_prefix`. **[ЕСТЬ]**

## П2.25 Индекс над `UNION ALL` view из разных схем

demo6 показывает, что мега-view может склеивать источники с совершенно разными
схемами (Codeforces parquet + DeepMind parquet), каждый со своей SQL-нормализацией,
и один индекс покрывает объединение. Работает и с `read_json_auto`.
`examples/demo6/README.md:9..27`.

## П2.26 Постфильтр `LIKE` как штатная часть sparse-ngram-поиска

Подстрочный поиск через `ts_all(ts_tokenize(ARRAY['подстрока'], '<covering-словарь>'))`
даёт **надмножество** (конъюнкция грамм). Точность обеспечивается
`AND col LIKE '%подстрока%'` — это не костыль, а описанный контракт
(`examples/demo6/README.md:60..72`). Baseline в demo6 показывает, во сколько
раз это быстрее голого `LIKE` без постингов.

## П2.27 `has_any_tokens` / `phrase_matches` — булева форма без `@@`

Полезно, когда предикат нужно положить в `CASE`, `HAVING` или в выражение:
`@@` там не сработает, а `phrase_matches(body, 'quick brown')` — да.
Ограничение: всё равно только внутри `WHERE` над индексом
(вне индекса — `Inverted index function called outside inverted index context`). **[ЕСТЬ]**

## П2.28 `refresh_interval = 0` как сессионная настройка

`SET refresh_interval = 0;` перед `CREATE INDEX` даёт индекс с выключенным
фоновым refresh — тесты используют это для детерминизма, а в проде это способ
управлять «когда именно записи станут видимыми» вручную через `VACUUM (REFRESH_*)`.
Проверено: `SET refresh_interval = 0; SHOW refresh_interval;` → `0`. **[ЕСТЬ]**

## П2.29 `DFI` имеет три меры

`dfi(oid)` = `standardized`, плюс `dfi(oid,'saturated')` и `dfi(oid,'chi_squared')`
(`server/catalog/persistence/scorer_options.h:76..88`). Проверено на инстансе. **[ЕСТЬ]**

## П2.30 Гео-предикаты — не просто функции

`ST_Intersects` / `ST_Contains` / `ST_Distance_Centroid` / `ST_Distance_Between`
существуют только как **распознаваемые сканом формы**; вне `WHERE` над
инвертированным индексом они падают. `ST_AsText` — обычная функция. **[ЕСТЬ]**

---

# Чего в сборке 26.07.3 НЕТ

Проверено запросами на инстансе.

1. **Опкласс `hnsw`.** `pg_opclass` содержит только `ivf` и `included`.
   В `server/` слова `hnsw` нет вообще — оно осталось только в
   `examples/demo4/demo.sql`, `examples/demo5/demo.sql` и `scripts/perf/*`.
   Любой синтаксис вида `emb hnsw (metric=..., m=..., ef_construction=...)`
   из demo4/demo5 у нас **не применим**; заменять на
   `emb ivf (metric = 'cosine')` + тюнинг `sdb_nprobe`/`sdb_rerank_factor`.
2. **Логическая репликация.** `CREATE PUBLICATION` / `CREATE SUBSCRIPTION`
   парсятся, но не исполняются.
3. **Сканеры MySQL и SQLite.** `mysql_scanner`, `sqlite_scanner` не вкомпилированы;
   `ATTACH ... (TYPE mysql|sqlite)` падает с
   `LOAD is not supported by SereneDB: extensions are compiled into the server binary`.
4. **`LOAD <extension>` вообще.** Набор расширений фиксирован на этапе сборки.
   Установлены: `autocomplete, avro, core_functions, httpfs, iceberg, icu, inet,
   json, parquet, postgres_scanner, tpcds, tpch`.
5. **Excel.** `read_xlsx` / `write_xlsx` отсутствуют (рецепты
   `cookbook/file_formats/excel_*` не применимы).
6. **Delta Lake.** `delta_scan` отсутствует (Iceberg — есть).
7. **Несколько скореров в одном запросе к одному индексу** — запрещено движком
   (не «отсутствует фича», а осознанное ограничение; обход — `UNION`).
8. **`sparse_ngram` + `position`/`offset`** — комбинация отвергается;
   значит по sparse-ngram-колонке нельзя ни фразы, ни подсветку офсетами.
9. **`ts_dict_*` по числовым колонкам** — `column has no text term dictionary`.
10. **`geo_shape` в ES-маппинге** — `no handler for type [geo_shape]`.
11. **HELP у `ts_highlight`** — опция `HELP` не поддержана в парсере опций
    подсветки (только `Key=Value`).

Не проверено (требует DDL, а менять сервер запрещено), но с высокой
достоверностью присутствует по бинарнику: `optimize_top_k`, `store_pk`,
`hyperloglog`, `compression`, все 23 шаблона словарей, частичные индексы.

---

# Что показалось неочевидным

1. **Подсветка не требует индекса.** `ts_highlight('<словарь>', '<текст>',
   '<tsquery>')` подсвечивает любую строку. То есть можно подсвечивать
   склеенный/обрезанный фрагмент, а не только колонку из индекса. И порядок
   аргументов в этой форме — словарь первым, что нигде в доках не подчёркнуто.

2. **`ts_offsets` возвращает БАЙТОВЫЕ смещения, не символьные.** Для кириллицы
   это вдвое больше, чем длина в символах. Наш `ts_offsets(doc)` вернул
   `{109,117}` для восьмибайтового «счет» (4 символа). Резать строку в Python
   по этим числам можно только по `bytes`, не по `str`.

3. **`WHERE` в термовых агрегатах фильтрует документы, а не термы.**
   `SELECT unnest(ts_dict_agg(body)) FROM idx WHERE body @@ ts_starts_with('g')`
   вернёт **все** термы документов, где есть слово на `g`, а не термы на `g`.
   Чтобы фильтровать термы, фильтр ставится **снаружи**:
   `WHERE body LIKE 'g%'` (для keyword-колонки) или подзапросом.
   Разница на реальном примере видна в
   `site_docs/sql/functions/term_dictionary.test:66..96`.

4. **`optimize_top_k` — свойство индекса, а не запроса.** Без него WAND не
   включается никогда, сколько ни пиши `ORDER BY bm25 ... LIMIT k`. И скорер в
   запросе должен совпасть со скорером индекса. У нас индекс собран без него.

5. **`store_pk = 'none'` — не оптимизация «по умолчанию хорошо».** Индекс
   перестаёт уметь отдавать что-либо, кроме `INCLUDE`-колонок, счётчиков и
   скоров. Это ровно паттерн demo6, где `INCLUDE` покрывает всё.

6. **`row_number() OVER ()` в теле view убивает параллелизм сборки индекса**
   (глобальное окно = один поток). 17x разницы на 11.5M строк по замеру авторов.
   Натуральный ключ обязателен.

7. **Опции индекса всегда материализуются в `reloptions` целиком** — даже те,
   что не задавались. Поэтому `pg_class.reloptions` — надёжный способ узнать,
   что реально применилось, включая значения, унаследованные из сессионных
   настроек на момент `CREATE INDEX`.

8. **Словарь резолвится из схемы таблицы, а не из `search_path`.** Одинаковый
   словарь придётся создать в каждой схеме, где есть индексируемые таблицы.

9. **`sdb_scored_terms_limit` тихо усекает ранжирование** широких мультитермовых
   запросов (wildcard/regex/фаззи) — 1024 терма по умолчанию. Если фаззи-поиск
   даёт «странный» порядок, это первый подозреваемый.

10. **DDL по умолчанию не транзакционен** — `sdb_strict_ddl = off`. Внутри
    `BEGIN ... ROLLBACK` создание индекса всё равно останется.

11. **`ivf`-колонка автоматически становится `store_values=true`** — вектор
    хранится в columnstore индекса и доступен для проекции без похода в таблицу.
    Это объясняет размер IVF-индексов.

12. **`approx_count_distinct` заметно врёт на нашей кардинальности**: 232 против
    точных 226 (`count(DISTINCT src_table)`). Для фасетов с малым числом значений
    надо брать точный вариант.

13. **`@@` и гео-предикаты — синтаксис, понимаемый только сканом индекса.**
    Их нельзя вычислить в `SELECT`-списке, в `CASE`, в `HAVING`. Булева форма
    (`phrase_matches`, `has_any_tokens`) снимает часть, но тоже только в `WHERE`.

14. **`text` умеет edge-ngram внутри себя** — просто добавить `mingram`/`maxgram`
    в словарь `template='text'`. HELP печатает их с заголовком `edgengram:`, но
    префикс `edgengram_` в DDL **не принимается** (проверено). Отдельный
    ngram-словарь для автокомплита не нужен.

15. **`VACUUM` расширенные опции нельзя комбинировать** — ни две своих, ни свою
    со стандартной (`VACUUM (REFRESH_TABLE, ANALYZE)` → ошибка).
