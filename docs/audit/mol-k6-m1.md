# M1: молекулы K6 — куда уходят ~52 с (код + модель)

Режим: **только чтение кода**. БД не трогалась. Живые EXPLAIN — оркестратору (лист ниже).
Вход: rid `e7be82cd`, вопрос «сколько продали вчера и чего продали. полный отчет»;
полигон `:8092`; K6 v2 = **52449 мс** (накопл.), «кандидаты собраны» = **73921 мс**;
транспорт `psql` ≈ **35 мс/вызов**.

---

## Вердикт одной строкой

**Транспорта не хватает:** при 15–30 вызовах × 35 мс ≈ **0.5–1.0 с**. Остальное —
**исполнение SQL по `search_corpus` (1.67M)** без захода в inverted-индекс
(`FROM search_corpus WHERE src_table IN …`, не `FROM search_idx WHERE src_table @@ …`).
Главный подозреваемый внутри K6: **live-скан всех `accumulationregister_%`** +
**двойной/тройной агрегат по IN-списку ~77 таблиц** (corp + `unnest(map_keys(nums))` ± axis).
Вторая молекула (~21.5 с): **не K6**, а код между `шаг("K6 v2")` и `шаг("кандидаты собраны")` —
повторный `stock_question_engaged` (± тело stock-фильтров с `EXISTS` по корпусу).

---

## Карта пути (файл:строка)

```
z20_ask_main_http.py:2254  K6R.apply_to_candidates(...)
  entity_rank_v2.py:804    apply_to_candidates
    :816–821               kind_from_alias_overlap          [0–3 psql, если kind пуст]
    :828–830               expand_holders                   [1 + N_cat]
    :831–833               expand_stem_and_live             [4 stem + 1 LIVE]
    :844–846               features_table                   [6–11 psql]
    :645                   reorder_v2                       [0 SQL]
    :862                   dual_atom_pair                   [0 SQL]
z20:2267–2269              cands ← result; шаг("K6 v2")
z20:2270–2286              stock_question_engaged / фильтры  ← молекула ~21 с
z20:2287                   шаг("кандидаты собраны")
```

`шаг` пишет **накопленное** wall от `t0` (`z20:1844–1847`).

---

## Карта SQL (точное число вызовов на пути K6)

Условие для sales-вопроса: `sales_sum_intent` → `form∈{sum,name}` (`infer_rank_form:771–772`);
`event_path_active` = False → `catalogs_for_kind=None` (`z20:2259–2260`);
`kind` обычно уже из parse → ветка `kind_from_alias_overlap` **не** зовётся.

| # | Функция | Файл:строка | Форма SQL | Константа / цикл | Оценка стоимости |
|---|---------|-------------|-----------|------------------|------------------|
| H1 | `expand_holders` → `stem_overlap_srcs` | `:711–712` / `:667–675` | `search_tables ⋈ alias`, `list_has_any(ts_lexize…)` по `catalog_%` | **1 const** | лёгкий (сотни строк метаданных) |
| H2 | `expand_holders` holders | `:720–723` | `search_refcols WHERE target_src=$cat AND LIKE accum%` | **цикл N_cat** (обычно 1–5) | лёгкий |
| S1–S4 | `expand_stem_and_live` ×4 prefix | `:735–738` | тот же stem-overlap на 4 префикса | **4 const** | лёгкий ×4 |
| **L1** | **live sales/movement** | **`:745–755`** | **`FROM search_corpus` WHERE `LIKE 'accumulationregister_%'` AND doc_date/nums/EXISTS refcols `GROUP BY src_table` — без IN-пула** | **1 const** | **ТЯЖЁЛЫЙ: скан всех строк регистров накопления в корпусе** |
| F1 | corp aggregates | `:370–378` | `count(*)` + 3× `FILTER` (doc_date / IsFolder / nums) `WHERE src_table IN (≤77) GROUP BY 1` | **1 const** | **ТЯЖЁЛЫЙ: table-scan корпуса по IN** |
| F2 | class | `:391–393` | `search_entity_class WHERE IN` | **1** | лёгкий |
| F3 | kind catalogs | `:401–409` | stem-overlap все `catalog_%` | **0–1** (если kind) | средний |
| F4 | holders among cands | `:419–425` | `search_refcols` IN cats ∩ IN cands | **0–1** | лёгкий |
| **F5** | **axis DISTINCT** | **`:436–457`** | **CTE cards + JOIN corpus↔refcols, `count(DISTINCT map_extract_value(refs_map,col))`, фильтр периода** | **0–1** (если holders∧kind_cats) | **ТЯЖЁЛЫЙ при срабатывании** |
| M1 | meas keys | `:133–136` | `DISTINCT src_table, unnest(map_keys(nums)) WHERE IN AND nums IS NOT NULL` | **1** | **ТЯЖЁЛЫЙ** (повторный проход строк с nums) |
| M2 | measure_alias | `:141–143` | `search_measure_alias WHERE IN` | **1** | лёгкий |
| M3 | n_ref_axes | `:151–156` | `search_refcols GROUP BY` | **1** | лёгкий |
| Q1 | q_meta | `:296–306` | stem вопроса ↔ label/aliases, IN cands | **1** | средний (метаданные) |
| Q2 | q_row (только small≤1000) | `:318–326` | `ts_lexize` на **каждую** `doc` строки `GROUP BY` | **0–1** | тяжёлый на «малых», на sales-гигантах обычно **скип** (`:335–337`) |

### Итого по K6 (типичный sales + period + kind)

| Класс | Число `psql` |
|-------|-------------|
| Константные | **~14–16** (4 stem + 1 live + 1 holders-stem + ~9 features) |
| Цикл | **N_cat** (refcols holders), обычно **1–5** |
| **Сумма** | **≈ 15–21 вызов** |

**Транспортный потолок:** 21 × 35 мс ≈ **735 мс** ≪ **51700 мс**.
Вывод: **>98 % фазы K6 — исполнение SQL (и CPU движка), не fork `psql`.**

Опционально (не в типичном sales):
- `kind_from_alias_overlap` `:681–698` — +1…3;
- `catalogs_for_kind` (`entity_form_catalogs_for_kind` `z05:315`) — только при `action_class=event`.

`reorder_v2` / `dual_atom_pair` / `rank_key_v2` — чистый Python, 0 SQL.

---

## Подозреваемые (ранг)

### P1 — `expand_stem_and_live` live-скан (`entity_rank_v2.py:745–755`)

```sql
SELECT c.src_table FROM search_corpus c
WHERE c.src_table LIKE 'accumulationregister_%'
  AND c.doc_date IS NOT NULL
  AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0
  AND EXISTS (SELECT 1 FROM search_refcols r
              WHERE r.src_table = c.src_table
                AND r.target_src LIKE 'catalog_%' AND r.col IS NOT NULL)
GROUP BY c.src_table
```

- Нет ограничения текущим пулом кандидатов.
- На sales-форме (`form in sum/name`) **всегда** (`:742–744`).
- Индекс `search_idx` **не используется** (запрос от имени таблицы + `LIKE`, не `@@`).

### P2 — `features_table` corp-агрегат (`:370–378`) на IN ≈77

```sql
SELECT src_table, count(*)::BIGINT,
  count(*) FILTER (WHERE doc_date IS NOT NULL),
  count(*) FILTER (WHERE NOT coalesce(map_extract_value(flags,'IsFolder'), false)),
  count(*) FILTER (WHERE nums IS NOT NULL AND len(map_keys(nums)) > 0)
FROM search_corpus WHERE src_table IN (<≤77>) GROUP BY 1
```

**Full scan?** Для движка это **скан базовой таблицы** (возможно, с min/max по зонам),
не posting-lookup индекса. Доки: keyword/`@@` работает при **`FROM <index_name>`**
([Querying an inverted index](https://serenedb.com/docs/sql/indexes/inverted#querying-an-inverted-index)).
У нас: `FROM search_corpus` + `IN` — тот же класс, что в `CHECK1_REVIEW_3.md`:
`IN` двух каталогов ≈ **253 мс** на ~27k строк. Экстраполяция на долю 1.67M
(крупные регистры продаж в пуле из 77) → **секунды…десятки секунд** на один проход.
`FILTER` + `map_extract`/`map_keys` заставляют материализовать строки, не только ключи.

### P3 — `_meas_profile_from_dict` M1 (`:133–136`)

Повторный проход тех же строк с `unnest(map_keys(nums))`. Аналог cold
`_measures_by_src` в `LATENCY_AUDIT.md` — «до секунд на большой базе».

### P4 — axis DISTINCT F5 (`:436–457`)

Срабатывает только при `holders∧kind_cats`. JOIN корпуса с периодом +
`count(DISTINCT map_extract_value(refs_map,col))` — потенциально сравнимо с P2.
На чистом sum без kind-holders может быть 0.

### P5 — индекс не покрывает этот путь

`corpus_init.sql:420–422`:

```sql
CREATE INDEX IF NOT EXISTS search_idx ON search_corpus
  USING inverted(doc search_dict, refs search_dict, src_table)
  INCLUDE (src_table, row_key, doc_date);
```

- `src_table` в индексе = **verbatim keyword** (коммент `:347–348`, `serene_search_build.py:881–882`).
- Помогает запросам вида `FROM search_idx WHERE src_table @@ 'document_…'`.
- **Не подхватывается** текущими `FROM search_corpus WHERE src_table IN (…)`.
- Отдельного ART/B-tree только по `src_table` **нет**.
- Агрегаты `count`/`FILTER` по `flags`/`nums` индексом **не покрыты** (`nums`/`flags` не в INCLUDE).

---

## Молекула 2: «кандидаты собраны» − K6 ≈ 21.5 с

Интервал кода (`z20:2269–2287`):

```python
шаг("K6 v2", ...)           # 52449
if stock_question_engaged(...):   # ← ВСЕГДА вычисляется
    balance_capable_or_registers()
    filter_stock_balance_sales_noise(...)   # снова stock_question_engaged!
    filter_stock_goods_registers(...)       # снова + stock_goods_pool
    … filter_balance_structural / named …
шаг("кандидаты собраны", ...)  # 73921
```

Между маркерами **нет** продолжения `apply_to_candidates`. Это **вторая молекула**.

### Что дорого в предикате (даже при `return False`)

`stock_question_engaged` (`z12:416–437`) **всегда** считает:

1. `_kind_is_stock_scoped` → `_catalogs_for_axis_word(kind)` → `entity_form_catalogs_for_kind`
   (`z05:315`, stem SQL; при пустом результате и `allow_meaning` из периода —
   `meaning_candidates` / embed+kNN).
2. `question_mentions_warehouse_axis` → `resolved_warehouse_axis_word` (`:190–200`):
   **цикл по словам вопроса** (`_question_dictionary_axis_candidates`), на каждое —
   снова catalogs + `_catalogs_are_warehouse_axis` → `_stock_place_axis_catalogs` /
   `_catalog_on_stock_eligible_register`.

Период «вчера» → `allow_meaning=True` → при промахе stem возможен **embed ≈0.45 с/текст**
(`embed_one`, кэш процесса).

### Если kind резолвится в product-catalog («чего» / товар)

Тогда `stock_kind=True` на **sales-вопросе**, тело фильтра **входит**, и дополнительно:

| Вызов | Где | Риск |
|-------|-----|------|
| `stock_question_engaged` ×3 | if + `filter_stock_balance_sales_noise:23` + `filter_stock_goods_registers:869` | тройной word-loop |
| `stock_goods_pool` → `registers_for_kind_axes` | `z12:457–466` | **`EXISTS (SELECT 1 FROM search_corpus c WHERE c.src_table=r.src_table AND nums…)`** — коррелированный зонд корпуса |
| `filter_balance_structural` | `z12:1283–1287` | ещё один `GROUP BY` по корпусу IN |

Симметрия: **тот же блок уже был до K6** (`z20:2232–2239`). Его время входит в
накопленные 52 с «до маркера K6» вместе с настоящим K6 → **часть «52 с K6» может быть
stock#1, а не `entity_rank_v2`**. Нужны субмаркеры (EXPLAIN-лист / TRACE).

---

## EXPLAIN-лист (оркестратор снимает на живой okna)

Подставить реальный IN-список из diag/`answer_fit_v2` rid `e7be82cd` (77 имён).
Везде: `EXPLAIN` и при возможности `EXPLAIN ANALYZE` (осторожно с ANALYZE на full scan).

### E1 — live expand (P1)

```sql
EXPLAIN SELECT c.src_table
FROM search_corpus c
WHERE c.src_table LIKE 'accumulationregister_%'
  AND c.doc_date IS NOT NULL
  AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0
  AND EXISTS (
    SELECT 1 FROM search_refcols r
    WHERE r.src_table = c.src_table
      AND r.target_src LIKE 'catalog_%' AND r.col IS NOT NULL)
GROUP BY c.src_table;
```

Смотреть: `TABLE_SCAN search_corpus` vs index; число строк до GROUP BY.

### E2 — corp aggregates (P2) — как в коде

```sql
EXPLAIN SELECT src_table,
  count(*)::BIGINT,
  count(*) FILTER (WHERE doc_date IS NOT NULL)::BIGINT,
  count(*) FILTER (WHERE NOT coalesce(map_extract_value(flags,'IsFolder'), false))::BIGINT,
  count(*) FILTER (WHERE nums IS NOT NULL AND len(map_keys(nums)) > 0)::BIGINT
FROM search_corpus
WHERE src_table IN (/* 77 литералов */)
GROUP BY 1;
```

### E3 — тот же фильтр через индекс (гипотеза фикса)

```sql
EXPLAIN SELECT src_table, count(*)::BIGINT
FROM search_idx
WHERE src_table @@ 'accumulationregister_xxx'   -- по одному / OR-дизъюнкция
GROUP BY 1;
-- либо OR: src_table @@ 'a' OR src_table @@ 'b' …
```

Сверить wall E2 vs E3 (исторически index OR выигрывал у table IN — `CHECK1_REVIEW_3`).

### E4 — meas unnest (P3)

```sql
EXPLAIN SELECT DISTINCT src_table, unnest(map_keys(nums)) AS k
FROM search_corpus
WHERE src_table IN (/* 77 */) AND nums IS NOT NULL;
```

### E5 — axis DISTINCT (P4), если в diag есть holders

```sql
EXPLAIN
WITH cards AS (
  SELECT src_table AS cat,
    count(*) FILTER (WHERE NOT coalesce(map_extract_value(flags,'IsFolder'), false))::BIGINT AS n_cards
  FROM search_corpus WHERE src_table IN (/* kind_cats */) GROUP BY 1
), axes AS (
  SELECT r.src_table, r.target_src AS cat, r.col,
    count(DISTINCT map_extract_value(c.refs_map, r.col))::BIGINT AS n_ax
  FROM search_refcols r
  JOIN search_corpus c ON c.src_table = r.src_table
  WHERE r.target_src IN (/* kind_cats */)
    AND r.src_table IN (/* holders */)
    AND r.col IS NOT NULL AND r.col <> ''
    AND c.doc_date >= DATE '…' AND c.doc_date < (DATE '…' + INTERVAL 1 day)
  GROUP BY 1, 2, 3
)
SELECT a.src_table, a.cat, a.n_ax, coalesce(cards.n_cards, 0)
FROM axes a LEFT JOIN cards ON cards.cat = a.cat;
```

### E6 — stock EXISTS (молекула 2)

```sql
EXPLAIN SELECT DISTINCT r.src_table
FROM search_refcols r
WHERE r.src_table LIKE 'accumulationregister_%'
  AND r.col IS NOT NULL AND r.col <> ''
  AND r.target_src IN (/* kind/action catalogs */)
  AND EXISTS (
    SELECT 1 FROM search_corpus c
    WHERE c.src_table = r.src_table
      AND c.nums IS NOT NULL AND len(map_keys(c.nums)) > 0);
```

### E7 — калибровка транспорта

```sql
EXPLAIN SELECT 1;   -- + 30× wall SELECT 1 через тот же ps()-обёртку сервиса
```

### E8 — субмаркеры TRACE (не SQL, но обязательны ко второму кругу)

Временно (или одноразовым зондом) вокруг:

1. `t_before_stock1` / `t_after_stock1` (`z20:2232`)
2. `t_before_k6` / `t_after_k6` (`:2254`)
3. внутри K6: после `expand_holders`, после `expand_stem_and_live`, после `features_table`
4. `t_stock2_pred` / `t_stock2_body` (`:2270`)

Без (3)–(4) нельзя честно разрезать 52 с на P1/P2/P3 и 21 с на stock.

---

## Вердикт: молекула → мс → доказательство → фикс

| Молекула | ≈ мс (факт / оценка) | Доказательство [код] | Фикс (не внедрять в M1) |
|----------|----------------------|----------------------|-------------------------|
| **K6 / L1 live expand** | **оценка 5–25 с** из 52 | `:745–755` полный скан accum; form=sum всегда | Батч: ограничить `src_table IN (pool)` или предвычисленный `search_live_accum` / meta; не `LIKE` по 1.67M |
| **K6 / F1 corp agg** | **оценка 5–20 с** | `:370–378` `FROM search_corpus IN(77)` + FILTER maps; индекс не задействован | Запрос от `search_idx` с `src_table @@` **или** ART/`GROUP BY` витрина `src_table→(n_rows,n_dated,n_cards,n_nums)` на такте сборки; один проход вместо F1+M1 |
| **K6 / M1 unnest nums** | **оценка 2–10 с** | `:133–136` второй проход тех же строк | Слить с F1 в один SQL; или читать `search_measure_alias` + кэш ключей без unnest корпуса |
| **K6 / F5 axis** | **0 или 3–15 с** | `:436–457` если holders | Считать axis_fit лениво / по top-N после reorder; периодный preagg |
| **K6 / stem×5 + meta** | **≲0.5–2 с** | H1,S1–4,F2–4,Q1 | Мелочь; батчить 4 stem в один `UNION ALL` |
| **K6 / транспорт psql** | **≲0.7 с** | 15–21 × 35 мс | Не главный рычаг; keep-alive/psycopg позже |
| **M2 stock между маркерами** | **≈21472 мс факт** | `z20:2270–2287`; pred всегда; при engage — ×3 pred + EXISTS E6 | Кэш результата `stock_question_engaged` на `(q,intent)` в запросе; не звать pred внутри фильтров; EXISTS заменить антисемом/`n_with_nums` из F1; **не** гонять stock-тело на sales_sum |
| **Атрибуция «всё в K6»** | часть 52 с может быть stock#1 | stock блок **до** маркера `:2232` | Субмаркеры E8 |

### Хватает ли psql-вызовов на 52 с при 35 мс?

**Нет.** 21 × 35 мс ≈ 0.7 с. Даже 100 вызовов дали бы 3.5 с.
**Главный подозреваемый — сами SQL (P1–P3), не число round-trip.**

### Индекс: мог бы помочь?

| Идея | Покрывает? |
|------|------------|
| Текущий `search_idx` keyword `src_table` | Да, **если** переписать на `FROM search_idx WHERE src_table @@ …` |
| Тот же индекс при текущем SQL | **Нет** (table scan) |
| INCLUDE уже имеет `doc_date` | Не спасает `count`/`FILTER` по `flags`/`nums` |
| Отдельный ART `(src_table)` / витрина агрегатов | Да для F1/M1; лучший фикс по масштабу |
| IVF | Не про этот путь |

---

## Что снять вторым кругом (оркестратор)

1. Wall E1, E2, E4 (± E5/E6) на проде/полигоне с IN=77 из rid.
2. Доля строк корпуса, попадающих в IN-77 (`sum(count) / 1675751`).
3. TRACE субмаркеры E8 на том же вопросе — разрезать 52 с и 21 с.
4. Факт: сработал ли stock engage на rid (diag `stock_*` / `balance_*`).

---

## Источники

- `ubuntu/serenedb/ask/z20_ask_main_http.py:1844–1847, 2232–2287`
- `ubuntu/serenedb/entity_rank_v2.py:130–182, 281–514, 645–867`
- `ubuntu/serenedb/ask/z12_stock_balance.py:20–110, 190–200, 416–437, 440–469, 847–882, 1268–1307`
- `ubuntu/serenedb/corpus_init.sql:347–348, 420–422`
- Доки SereneDB: Inverted Index › Querying (`FROM index` + `@@`)
- Прежние замеры: `docs/CHECK1_REVIEW_3.md` (IN 253 мс / index OR 169 мс на ~27k);
  `docs/LATENCY_AUDIT.md` (unnest map_keys cold)
