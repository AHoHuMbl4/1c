# CHECK1_SCAN_3 — точный перебор по FLOAT[1536] в SereneDB 26.07.3: план, потоки, префильтр, пределы

Дата: 2026-07-27. Инстанс `host=127.0.0.1 port=7890 user=postgres dbname=postgres`
(psql запускался по ssh с 192.168.56.42 — локально psql нет).
Клон: `/srv/data/cursor/cursor/1/serenedb-src`.
Индексы НЕ создавались. Все запросы к движку — `SELECT` / `EXPLAIN` / `EXPLAIN ANALYZE` / каталоги.

Объект: `search_corpus` — 97 965 строк, колонки
`src_table, row_key, doc, refs, doc_hash VARCHAR, amount DOUBLE, doc_date TIMESTAMP, emb FLOAT[1536]` [вывод].
Индекс один: `search_idx ON search_corpus USING inverted(doc DICT, refs DICT, src_table) INCLUDE (src_table, row_key, amount, doc_date)`
(DDL — из нашего `ubuntu/serenedb/serene_search_build.py:879-880`; движок в `duckdb_indexes()` тело DDL не хранит [вывод]).
**`emb` в индекс НЕ входит — ни как `ivf`-поле, ни как `INCLUDE`.**

Объём данных: 97 965 × 1536 × 4 Б = **602 МБ** сырых float. Весь стор `postgres` — 1.3 GiB [вывод `pragma_database_size()`].

---

## 1. ФОРМА ЗАПРОСА И ПЛАН

### 1.1 План одинаков у всех форм

Снял `EXPLAIN (FORMAT JSON)` для семи форм (литерал вектора вшит в текст запроса) [вывод].
Планы **побитово одинаковы по форме** для `<=>`, `<#>`, `<->`, `array_cosine_similarity`,
`array_cosine_distance`, `array_inner_product`, `array_distance`:

```
ORDER_BY (#1)
└─ PROJECTION [row_key, (emb <=> <вектор>)]
   └─ HASH_JOIN  Join Type: SEMI, Conditions: rowid = rowid
      ├─ SEQ_SCAN search_corpus  Projections: [row_key, emb]        ← проход 2
      └─ TOP_N Top: 10, Order By: #0 ASC
         └─ PROJECTION [(emb <=> <вектор>), rowid]
            └─ SEQ_SCAN search_corpus  Projections: emb             ← проход 1
```

Это late materialization DuckDB: **проход 1** читает ТОЛЬКО колонку `emb`, считает расстояние
в `PROJECTION` поверх скана (повекторно, чанками), `TOP_N` держит кучу на 10; **проход 2**
достаёт `row_key` для победителей.

Проход 2 не является вторым полным чтением `emb`: `EXPLAIN ANALYZE` показывает на нём
динамический фильтр [вывод]:
```
TABLE_SCAN  Table: search_corpus
  Dynamic Column Filter:
    optional: (rowid IN (98539, 139795, 152844, 152869, 152878, 153107, 159931, 159933, 185155, 191418))
    AND optional: rowid IN PRF(rowid)
```
То есть проходов по данным фактически **один** + точечная дочитка 10 строк.
`EXPLAIN ANALYZE` Total Time: 0.304–0.381s [замер].

Литерал вектора сворачивается в константу на этапе планирования (в плане он виден как
`[-0.0064, 0.01279, ...]`, а не как `list_value(...)`) — одинаково во всех формах [вывод].

### 1.2 Почему `array_*` медленнее — и это НЕ план

`server/connector/functions/vector.cpp:373-445` (`RegisterDistance<D>`): SereneDB регистрирует
**свои** скалярные функции поверх SIMD-ядер iResearch
(`irs::vector::L2Space` / `L1Space` / `CosineDistanceImpl` / `DotProductImpl`,
vector.cpp:57-105) и вешает на них операторные алиасы (vector.cpp:438-441) [код]:

| функция (SereneDB) | оператор | метрика |
|---|---|---|
| `l2_distance` | `<->` | L2 |
| `l2_sqr_distance` | — | L2 без sqrt |
| `l1_distance` | `<+>` | L1 |
| `cosine_distance` | `<=>` | 1 − cos |
| `cosine_similarity` | — | cos, порядок DESC |
| `inner_product` | — | IP, порядок DESC |
| `negative_inner_product` | `<#>` | −IP |
| `l1_norm`, `l2_norm`, `l1_normalize`, `l2_normalize` | — | нормы/нормировка |

Все они есть в нашей сборке [вывод `duckdb_functions()`], сигнатуры `{FLOAT[ANY],FLOAT[ANY]}→FLOAT`
и `{DOUBLE[ANY],DOUBLE[ANY]}→DOUBLE`.

`array_cosine_distance` / `array_cosine_similarity` / `array_inner_product` / `array_distance`
(и весь набор `list_*`) — это **штатные функции DuckDB**, SereneDB их не переопределяет.

Чередующийся замер (4 круга, формы вперемешку, чтобы снять эффект прогрева) [замер]:

| форма | круг 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `SELECT count(emb)` (только скан) | 260 | 270 | 311 | 187 |
| `emb <=> v` | 338 | 270 | 434 | 291 |
| `cosine_distance(emb, v)` | 258 | 302 | 321 | 257 |
| `cosine_similarity(emb, v) DESC` | 333 | 283 | 267 | 278 |
| `l2_sqr_distance(emb, v)` | 279 | 270 | 317 | 265 |
| `negative_inner_product(emb, v)` | 260 | 293 | 268 | 257 |
| `l1_distance(emb, v)` | 271 | 297 | 312 | 289 |
| **`array_cosine_distance(emb, v)`** | **488** | **436** | **405** | **505** |
| **`array_cosine_similarity(emb, v) DESC`** | **434** | **433** | **458** | **402** |

Выводы:
- `<=>` и `cosine_distance` — **одна и та же функция**, разницы нет (в первом, непереслоённом
  прогоне казалось, что оператор быстрее — это был артефакт прогрева; при чередовании разницы нет).
- родные ядра ≈ **256–330 мс** ≈ стоимость голого скана `count(emb)` (187–311 мс) →
  **расстояние почти бесплатно, платим за чтение 602 МБ**;
- `array_*` — **+40 % (400–505 мс)**;
- 602 МБ / 0.27 с ≈ **2.2 ГБ/с** — упираемся в пропускную способность памяти, а не в арифметику.

`LIMIT` на время не влияет: k=1 → 305–328 мс, k=10 → 280–310, k=100 → 307–393 [замер].
Проекция `rowid` вместо `row_key` — 292 мс, тоже без разницы [замер].

### 1.3 Дополнительный вывод, важный на будущее

Родные функции несут `AnnFunctionInfo` (метрика + порядок + `ScoreEmit`), vector.cpp:434-437 [код].
Именно по нему планировщик умеет утащить `ORDER BY ... LIMIT k` внутрь ANN-скана индекса.
У `array_*` этого нет **никогда** → они не смогут воспользоваться индексом, даже когда он появится.
**Правило: в нашем коде — только `<=>` / `cosine_distance`, никаких `array_cosine_similarity`.**

### 1.4 Стоимость самого литерала — 31–46 мс на запрос

`SELECT array_length(<литерал 1536 float>)` без обращения к таблице: **31.1 / 38.9 / 31.9 / 45.8 / 37.2 мс**
(для сравнения `SELECT 1` — 0.34–0.97 мс) [замер].
Через bind-параметр расширенного протокола (`$1::FLOAT[1536]`, psql `\bind`): **1.12 / 1.18 / 1.29 мс** [замер].
Разбор текстового литерала стоит ~**30× дороже** передачи того же вектора параметром.
Так же это сделано в демке движка: `examples/demo4/demo.sql:56-58` — `ORDER BY d.embedding <=> $1::FLOAT[1536]`
с комментарием «the embedding arrives as a PostgreSQL bind parameter ($1) via the extended
protocol; the cast `$1::FLOAT[1536]` folds at plan time» [код].

На полном скане это 10 % времени, на префильтрованном запросе — **больше половины** (см. §3).

---

## 2. ПАРАЛЛЕЛЬНОСТЬ

### 2.1 Настройки в нашей сборке [вывод `duckdb_settings()`]

| настройка | значение | scope |
|---|---|---|
| `threads` | 6 | GLOBAL |
| `worker_threads` | 6 | GLOBAL |
| `external_threads` | 0 | — |
| `async_threads` | 12 | — |
| `row_group_size` | 122880 | GLOBAL — «Default column row-group size for INCLUDEd in newly created inverted indexes» |
| `sdb_disable_top_k_optimization` | off | — |
| `sdb_nprobe` / `sdb_rerank_factor` / `sdb_ivf_posting_size` / `sdb_ivf_sample_factor` | 8 / 4 / 1024 / 0 | только IVF |
| `disabled_optimizers` | пусто | GLOBAL, DEBUG |

`nproc` на сервере = 6 [вывод].

### 2.2 Замер: полный скан по вектору — ОДНОПОТОЧНЫЙ

Мерил CPU-время процесса `serened` (`/proc/<pid>/stat`, utime+stime) против wall-времени [замер]:

| запрос | wall | cpu | cpu/wall |
|---|---|---|---|
| `SELECT count(emb) FROM search_corpus` ×10 | 2154 мс | 1930 мс | **0.89** |
| `SELECT sum(array_cosine_similarity(emb,emb)) FROM search_corpus` ×3 | 1289 мс | 1100 мс | **0.85** |
| `SELECT row_key FROM search_corpus ORDER BY emb <=> v LIMIT 10` ×10 | 5949 мс | 11330 мс | 1.90 |

- Голый скан колонки `emb` — **cpu/wall ≈ 0.9, то есть один поток**.
- У top-k запроса ratio 1.9 не потому, что скан параллельный, а потому что план (§1.1) —
  это два конвейера (левый и правый вход SEMI-join), они идут одновременно.

Масштабирование по клиентам [замер]: 1 клиент — 3 запроса за 889 мс (3.4 q/s);
4 клиента параллельно — 12 запросов за 2293 мс (5.2 q/s). **Прирост 1.55× на 6 ядрах** —
упираемся в память, а не в потоки. Добавление потоков дало бы мало даже если бы работало.

### 2.3 Почему один поток — по коду

Базовая таблица `search_corpus` — обычная (не `TableEngine::Search`), поэтому
`SereneDBTableEntry::GetScanFunction` уходит в ветку `ResolveStoreEntry(context).GetScanFunction(...)`,
то есть в **штатный DuckDB-скан стора** (`server/connector/duckdb_table_entry.cpp:116-158`) [код].
DuckDB параллелит скан по row group'ам; размер row group у DuckDB — константа 122 880 строк.
97 965 < 122 880 → **одна row group → один поток**. Настройки, которая это меняет, в сборке нет:
`row_group_size`, видимая в `duckdb_settings()`, относится к INCLUDE-колонкам инвертированного индекса
(`server/query/config_variables.cpp:440-455`), а не к таблице [код+вывод].

### 2.4 Что параллелится штатно — скан ИНДЕКСА

`server/connector/duckdb_search_full_scan.hpp:242-256` [код]:
```cpp
duckdb::idx_t MaxThreads() const final {
  switch (mode) {
    case ScanMode::CountFast: return 1;
    case ScanMode::ColScan:   return std::max<idx_t>(1, col_scan.units.size());
    default:                  return std::max<idx_t>(1, scorer_obj ? total_segments : claimable_segments);
  }
}
```
Единицы работы `ColScan` строятся в `duckdb_search_full_scan.cpp:1290-1325` [код]:
```cpp
uint64_t rg_rows = bind_data.inverted_index->GetOptions().row_group_size;  // 0 -> DEFAULT_ROW_GROUP_SIZE
const uint64_t unit_rows = rg_rows >= DEFAULT_ROW_GROUP_SIZE
                             ? rg_rows
                             : DEFAULT_ROW_GROUP_SIZE / rg_rows * rg_rows;
for (uint32_t claimed = 0; claimed < state->claimable_segments; ++claimed) { ... }
```
Важно: **уменьшение `row_group_size` НЕ уменьшает единицу параллелизма** — она всё равно
округляется вверх до `DEFAULT_ROW_GROUP_SIZE` (122 880). Параллелизм ColScan-скана индекса
берётся из **числа сегментов** (`claimable_segments`), а не из row group'ов.
При 98 тыс. строк в одном сегменте это тоже один поток.

**Итог по 2: полный перебор по вектору у нас однопоточный, и штатной ручки, чтобы это изменить,
в сборке 26.07.3 нет.** Единственный штатный рычаг — не сканировать всё (§3).

---

## 3. ПРЕФИЛЬТР — ГЛАВНЫЙ ОТВЕТ: ДА, РАБОТАЕТ, ОДНИМ ЗАПРОСОМ

### 3.1 Текстовый префильтр: только от имени индекса

Штатная форма (демка движка `examples/demo4/demo.sql:70-93` [код]):
```sql
SELECT title FROM dbpedia_idx d
WHERE text @@ (ts_phrase('physicist') && !!ts_phrase('philosophy')
               && (ts_phrase('quantum mechanics') || ts_phrase('general relativity')))
ORDER BY d.embedding <=> $1::FLOAT[1536]
LIMIT 5;
```
И тест `tests/sqllogic/sdb/pg/index/inverted_index_hybrid_ivf.test:135-155` — раздел
«hybrid: text filter + vector ordering», включая два текстовых предиката через `AND` [код].

**Проверено на нашем инстансе, БЕЗ ivf на `emb`** [вывод, `EXPLAIN (FORMAT JSON)`]:
```
SELECT row_key FROM search_idx
WHERE doc @@ ts_phrase('СБЕРБАНК')
ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10;

TOP_N  Top: 10, Order By: #1 ASC
└─ PROJECTION [row_key, (emb <=> <вектор>)]        Estimated Cardinality: 19593
   └─ IRESEARCH_SCAN  Index: search_idx
        Index Filter: {"name":"Term","Field":"doc(string)","Value":"сбербанк"}
        Lookup: table
        Projections: ["row_key (i)", "emb (l)"]
```
Ни `SEQ_SCAN`, ни SEMI-join. Множество сужается **до** вычисления расстояний:
`PROJECTION` с расстоянием стоит НАД `IRESEARCH_SCAN`, который уже отдал только совпавшие строки.

Пометки `(i)` / `(l)` — `server/connector/duckdb_table_function.cpp:750-765` [код]:
`(i)` = колонка прочитана из колонкового хранилища индекса, `(l)` = точечный lookup в базовую
таблицу. У нас `emb (l)`, потому что `emb` не в `INCLUDE`.

От имени таблицы то же самое **не работает** [вывод]:
```
SELECT row_key FROM search_corpus WHERE doc @@ ts_phrase('СБЕРБАНК') ORDER BY emb <=> ... LIMIT 10;
ERROR:  TSQUERY expression evaluated outside an `@@` match against an inverted-indexed column.
```

### 3.2 Скалярный / датный префильтр: работает прямо по таблице

`WHERE amount > 1000`, `WHERE doc_date >= TIMESTAMP '2024-01-01'`, `WHERE src_table = '...'`
кладутся в `Column Filter` **внутрь того `SEQ_SCAN`, который питает PROJECTION с расстоянием** [вывод]:
```
TOP_N Top: 10
└─ PROJECTION [(emb <=> <вектор>), rowid]                       Estimated Cardinality: 19701
   └─ SEQ_SCAN search_corpus  Projections: emb
        Column Filter: (doc_date >= '2024-01-01 00:00:00'::TIMESTAMP)
```
То есть `emb` читается только у выживших строк.

**Осторожно с `IN (...)`**: для `src_table IN ('a','b')` план вырождается — фильтр становится
`optional:` и появляется отдельный `FILTER` над сканом, который проецирует `src_table, emb`
на все 98 508 строк [вывод]. Замер это подтверждает (см. таблицу ниже: 46 825 строк по `IN` —
272–357 мс, почти как полный скан). **Одно равенство `=` — быстро, `IN` — нет.**

### 3.3 Замеры (bind-параметр, если не сказано иное)

| запрос | строк после фильтра | время |
|---|---|---|
| `FROM search_corpus ORDER BY emb <=> $1 LIMIT 10` (полный скан) | 97 965 | **280–322 мс** |
| `FROM search_idx WHERE doc @@ ts_phrase('КАЗАНЬ') ...` | 56 | **~7 мс**\* |
| `FROM search_idx WHERE doc @@ ts_phrase('СБЕРБАНК') ...` | 151 | **6.5 / 7.2 / 7.4 мс** |
| `FROM search_idx WHERE src_table @@ 'catalog_классификаторбанков' ...` | 2 779 | **25.6 / 29.7 мс** |
| `FROM search_corpus WHERE src_table = 'catalog_поляформстатистики' ...` | 23 878 | **73 / 109 мс** |
| `FROM search_idx WHERE src_table @@ 'catalog_поляформстатистики' ...` | 23 878 | **132 / 144 мс** |
| `FROM search_corpus WHERE src_table IN ('a','b') ...` | 46 825 | 272 / 284 / 358 мс |
| `FROM search_idx` **без фильтра** | 97 965 | **541 мс** — хуже полного скана таблицы |

\* с литералом было 24–31 мс; 7 мс — с bind (см. §1.4).

Те же цифры с вшитым литералом (для сравнения) [замер]: 56 строк — 23.9/27.1/30.7 мс,
151 — 27.8/31.2/34.0 мс, 2779 — 37.6/46.4/51.8 мс, 23 878 — 155/159/162 мс, полный скан — 299–353 мс.

**Практический вывод и границы:**
- Типичный боевой запрос (сотни совпадений) — **300 мс → 7 мс, в ~43 раза быстрее**.
- Индексная форма деградирует линейно по числу совпадений (lookup `emb (l)` ≈ 5–6 мкс/строку):
  точка безубыточности против полного скана — примерно **45–50 тыс. строк (~50 % корпуса)**.
- **Без фильтра `FROM search_idx` использовать нельзя** — 541 мс против 300 мс.
- Скалярный фильтр по обычной колонке (`=`, `>`, `>=`) дешевле индексного при одинаковой
  селективности (73 мс против 132 мс на 23 878 строках), потому что читает `emb` последовательно,
  а не точечными lookup'ами.

### 3.4 Комбинирование фильтров в один скан — тоже штатно

Текст + число одним `IRESEARCH_SCAN` (число берётся из `INCLUDE`-колонки) [вывод]:
```
SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('СБЕРБАНК') AND amount > 0
ORDER BY emb <=> $1 LIMIT 10;

TOP_N Top: 10
└─ PROJECTION [row_key, (emb <=> <вектор>)]     Estimated Cardinality: 3918
   └─ IRESEARCH_SCAN Index: search_idx
        Index Filter: {"name":"Term","Field":"doc(string)","Value":"сбербанк"}
        Column Filter: (amount > 0)
        Projections: ["row_key (i)", "emb (l)"]
```
BM25 и вектор в одном скане [вывод]:
```
SELECT row_key, bm25(search_idx.tableoid) FROM search_idx WHERE doc @@ ts_phrase('СБЕРБАНК')
ORDER BY emb <=> $1 LIMIT 10;

└─ IRESEARCH_SCAN ... Score: bm25(k1=1.2, b=0.75)
     Projections: ["row_key (i)", "emb (l)", "sdb_inverted_index_score"]
```
То есть **гибрид «BM25 + косинус» считается за один проход индекса**, без второго запроса.

---

## 4. ЧТО ЕЩЁ ШТАТНО УСКОРЯЕТ ПЕРЕБОР

| механизм | что делает (по коду) | применимо к перебору БЕЗ ivf? |
|---|---|---|
| **bind-параметр `$1::FLOAT[1536]`** | вектор идёт бинарно расширенным протоколом, не парсится как текст; `examples/demo4/demo.sql:52-58` | **ДА, главный дешёвый выигрыш: −30…−45 мс на запрос** [замер] |
| **родные функции вместо `array_*`** | `vector.cpp:373-445`, SIMD-ядра iResearch | **ДА, −40 % на счётной части** [замер] |
| **`l2_sqr_distance`** | L2 без `sqrt` (`vector.cpp:107-112`, `Distance::L2Sqr`) | ДА, но на 1536 dim выигрыш в шуме (265–317 мс против 256–330) [замер] |
| **`l2_normalize` / `l2_norm`** | штатная нормировка вектора (`vector.cpp:139-152, 315-345`) — позволяет заменить косинус на `<#>` (−IP) | ДА, но на наших данных `<#>` и `<=>` неотличимы (§1.2) — узкое место не арифметика |
| **предикат по обычной колонке** | пушится в `Column Filter` скана ниже PROJECTION с расстоянием | **ДА, см. §3.2** |
| **текстовый предикат `FROM <index> WHERE col @@ ...`** | `IRESEARCH_SCAN` с `Index Filter` | **ДА, см. §3.1** |
| **`INCLUDE` числовых/датных колонок** | `Column Filter` применяется внутри `IRESEARCH_SCAN` (§3.4); у нас уже есть `amount`, `doc_date` | **ДА, уже используется** |
| **`INCLUDE (emb)` без ivf** | `FLOAT[N]` разрешён как INCLUDE-колонка: `tests/.../inverted_index_array_include.test:29`, `inverted_index_merge_include.test:30` — `USING inverted(pk, body en) INCLUDE (vec)` | **ДА по коду и тестам, у нас НЕ сделано.** Убрало бы `Lookup: table` (`emb (l)` → `emb (i)`). Замер обязателен — см. §«Что проверить» |
| **late materialization** | план §1.1 + `Dynamic Column Filter: rowid IN (...)`; **включён по умолчанию** | ДА, уже работает |
| **`sdb_disable_top_k_optimization`** | `config_variables.cpp:429-439`: «the optimizer skips pulling `ORDER BY <scorer>(...) DESC LIMIT k` into the inverted-index scan, so WAND (Block-Max top-K) pruning never engages» | **НЕТ.** Это про **текстовые скореры** (BM25/TFIDF), не про векторное расстояние. У нас `off` (оптимизация включена) — трогать не надо |
| **`optimize_top_k` в `WITH (...)` индекса** | `server/catalog/scorer_options.cpp:200-262`, пример `tests/.../site_docs/sql/indexes/inverted/ranking.test:32`: `WITH (optimize_top_k = 'bm25(1.2, 0.75)')` — предвычисленный порядок для WAND | **НЕТ для векторов**: принимает только скорер-функцию (BM25/TFIDF), не `<=>` |
| **`row_group_size`** | `config_variables.cpp:440-455` — только для INCLUDE-колонок индекса; в `ColScan` единица всё равно ≥ `DEFAULT_ROW_GROUP_SIZE` (`duckdb_search_full_scan.cpp:1299-1301`) | **НЕТ выигрыша по параллельности** (§2.4) |
| **`threads` / `worker_threads`** | 6/6 | **НЕТ**: скан однопоточный из-за одной row group (§2.3) |
| **`sdb_nprobe`, `sdb_rerank_factor`, `sdb_ivf_*`** | только IVF | НЕТ (ivf у нас заблокирован) |
| **FLOAT vs DOUBLE** | обе сигнатуры зарегистрированы (`vector.cpp:389-402`); DOUBLE — вдвое больше байт | **Держать FLOAT.** Скан упирается в память (2.2 ГБ/с), DOUBLE = 1.2 ГБ вместо 602 МБ |
| **сжатие колонки** | `pragma_storage_info('search_corpus')` возвращает пусто, стор SereneDB [вывод]; ручки нет | нет |
| **range-поиск `WHERE emb <=> q < 0.3`** | план: `SEQ_SCAN Column Filter: ((emb <=> <вектор>) < 0.3)` [вывод] — расстояние считается на всех строках | **Медленнее top-k: 577–604 мс** [замер]. Не использовать без ivf |

Отдельно: `ai_embed(VARCHAR, VARCHAR, VARCHAR)` **есть в нашей сборке** [вывод `duckdb_functions()`] —
вектор запроса можно получать прямо в SQL, не гоняя 14 КБ текста от Python. (Проверка сети/ключа
выходит за рамки этого файла.)

---

## 5. ЗАМЕРЫ ПЕРЕБОРА В САМОМ ДВИЖКЕ

**Есть, но маленькие по размерности и без опубликованных цифр.**

1. `tests/sqllogic/sdb/pg/index/vector_search.test_slow:1-40` — движок сам использует полный
   перебор как эталон для проверки recall'а ANN-индекса. Дословно:
   ```
   CREATE TABLE vecs (id INT, emb FLOAT[8]);
   INSERT INTO vecs SELECT s AS id, [sin(s*0.001)::FLOAT, ...] FROM generate_series(1, 50000) AS s;
   CREATE TABLE correct(id INT);
   INSERT INTO correct SELECT id FROM vecs ORDER BY emb <-> [0.0, 1.0, ...]::FLOAT[8] LIMIT 512;
   CREATE TABLE correct_filtered(id INT);
   INSERT INTO correct_filtered SELECT id FROM vecs WHERE id > 25000
     ORDER BY emb <-> [0.0, 1.0, ...]::FLOAT[8] LIMIT 512;
   ```
   **50 000 строк, размерность 8, top-512** — и полного, и отфильтрованного перебора.
   Времени в тесте не публикуется.

2. `scripts/perf/sweep_hnsw.sh:1-50` — прогоняет именно `vector_search.test_slow` под разные
   константы `hnsw.cpp` и печатает `elapsed ms` на конфигурацию. Это про HNSW (в нашей сборке нет),
   и это время всего теста, а не перебора.

3. `tests/bench/micro/vector_distances.cpp:33-45` — микробенч ядер расстояний
   («sdb::pg distance functions (iresearch SIMD-backed)» против Velox/FAISS), размерности
   `->Arg(64) ->Arg(128) ->Arg(256) ->Arg(512) ->Arg(1024) ->Arg(2048)`.
   **1536 в списке нет**; это чистая арифметика на двух векторах, без чтения колонки.

4. `tests/bench/micro/clustering.cpp:50-51` — единственное место с нашей размерностью:
   `constexpr uint32_t kDim = 1536; constexpr size_t kN = 16384;` — но это бенч кластеризации
   (обучение центроидов IVF), не перебор.

5. `examples/demo4/README.md:3` — «100K abstracts with 1536-dim OpenAI vectors», то есть
   **ровно наш объём и наша размерность**, но демка строит HNSW-индекс
   (`examples/demo4/demo.sql:41`), а не меряет перебор. HNSW в 26.07.3 нет.

6. `scripts/perf/gen_filtered_topk_report.sh` — единственный «A/B на живом сервере» в репозитории,
   но он про **текстовый** filtered top-k (WAND vs streaming+TopN), с `sdb_disable_top_k_optimization`
   как переключателем. К векторам отношения не имеет.

Файла с готовыми цифрами полного перебора по 1536-мерным векторам в репозитории **нет**.

---

## Что проверить замером (без создания индексов)

DSN: `D="host=127.0.0.1 port=7890 user=postgres dbname=postgres"` (psql — на 192.168.56.42).
`:qv` — текстовое представление вектора вида `[0.1,0.2,...]` (1536 чисел, без каста).

1. **Переход на bind-параметр в `serene_ask.py`.** Сейчас вектор вшивается в текст запроса.
   ```
   psql "$D" <<'EOF'
   \timing on
   \set qv '[...1536 чисел...]'
   SELECT row_key FROM search_idx WHERE doc @@ ts_phrase('СБЕРБАНК')
   ORDER BY emb <=> $1::FLOAT[1536] LIMIT 10 \bind :qv \g
   EOF
   ```
   Ожидание: 7 мс против 28 мс с литералом. В Python — `psycopg`/`asyncpg` с параметром,
   а не f-строка.

2. **Замена `array_cosine_similarity` на `<=>` везде, где он у нас есть.**
   ```
   psql "$D" -c "\timing on" -c "SELECT row_key FROM search_corpus ORDER BY array_cosine_similarity(emb, <лит>) DESC LIMIT 10"
   psql "$D" -c "\timing on" -c "SELECT row_key FROM search_corpus ORDER BY emb <=> <лит> LIMIT 10"
   ```
   Ожидание: 430 мс против 290 мс.

3. **Крайняя точка префильтра — где индексная форма проигрывает полному скану.**
   Прогнать `FROM search_idx WHERE src_table @@ '<таблица>' ORDER BY emb <=> $1 LIMIT 10`
   для нескольких `src_table` с 1k / 5k / 20k / 40k / 60k строк и найти пересечение с 290 мс.
   Мои точки: 2 779 → 26 мс, 11 688 → 90–102 мс, 23 878 → 132–144 мс, 97 965 → 541 мс.

4. **`IN (...)` против нескольких `=`.** У нас в коде фильтр по списку таблиц вполне вероятен.
   ```
   EXPLAIN (FORMAT JSON) SELECT row_key FROM search_corpus WHERE src_table IN ('a','b') ORDER BY emb <=> <лит> LIMIT 10;
   ```
   Если в плане `Column Filter: optional:` + отдельный `FILTER` — переписать на
   `FROM search_idx WHERE src_table @@ 'a' OR src_table @@ 'b'`.

5. **`INCLUDE (emb)` — единственное непроверенное, что может дать ещё раз в разы.**
   Требует создания индекса, поэтому **только на копии базы, не на 7890**:
   ```
   CREATE INDEX t_idx ON t USING inverted(doc DICT, refs DICT, src_table)
     INCLUDE (src_table, row_key, amount, doc_date, emb);   -- НИКАКОГО ivf
   ```
   Проверять: в `EXPLAIN` проекция должна стать `emb (i)` вместо `emb (l)`;
   сравнить время `FROM t_idx WHERE doc @@ ... ORDER BY emb <=> $1 LIMIT 10` при 2 779 и 23 878
   совпадениях против нынешних 26 мс и 132–144 мс. Отдельно замерить рост времени сборки индекса
   и размера стора (+602 МБ ожидаемо).

6. **`ai_embed()` в SQL вместо похода в облако из Python.**
   ```
   psql "$D" -tAF' | ' -c "SELECT function_name, parameters, parameter_types FROM duckdb_functions() WHERE function_name='ai_embed'"
   ```
   Функция в сборке есть (3 × VARCHAR). Проверить сигнатуру аргументов и сетевой доступ до
   нашего эндпойнта, затем A/B по `ubuntu/serenedb/ab_scorer.py`.

---

## Чего я не смог выяснить

1. **Сколько сегментов у `search_idx`.** Штатной интроспекции не нашёл: `duckdb_indexes()` тело DDL
   не хранит (пустые скобки), функций вида `*segment*` в `duckdb_functions()` нет.
   Поэтому не могу сказать, во сколько потоков пошёл бы `ColScan` при `INCLUDE (emb)`.
   По коду параллелизм = число сегментов (`duckdb_search_full_scan.hpp:242-256`), и при 98 тыс.
   строк в одном сегменте это был бы один поток.

2. **Сколько именно даст `INCLUDE (emb)`.** Есть только код и тесты, что это допустимо
   (`inverted_index_array_include.test:29`, `inverted_index_merge_include.test:30`),
   и что чтение станет `(i)` вместо `(l)`. Замера нет — индексы создавать запрещено.

3. **Влияние `disabled_optimizers='late_materialization'`.** Настройка GLOBAL и DEBUG;
   выставлять её на живом инстансе не стал. Поэтому вклад SEMI-join'а в 290 мс оценён только
   косвенно (через `Dynamic Column Filter: rowid IN (...)` в `EXPLAIN ANALYZE`).

4. **Влияние `SET threads`.** Настройка GLOBAL — снизить её на живом сервере и не восстановить
   было бы опасно. Однопоточность доказана измерением cpu/wall (0.85–0.89), а не отключением потоков.

5. **Исходники ядра DuckDB.** Сабмодуль `third_party/duckdb` в клоне не выкачан (`ls` пуст),
   поэтому про late materialization и про размер row group у DuckDB сужу по планам и по
   `duckdb_settings()`, а не по коду.

6. **`refs`-колонка индекса.** Она есть в DDL, но я её в замерах не трогал — префильтр по `refs @@ ...`
   не мерил.
