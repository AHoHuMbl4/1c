# OPT-S: stock-блок 50,6 с + prefer_catalog/rank 9,5 с

Дата: 11.09. Режим: **только чтение кода**. Коммитов нет.
Вход: зонд оркестратора rid `b11dac07`, вопрос «сколько продали вчера и чего
продали. полный отчет»; полигон. Числа зонда — истина (K6-apply = 1,3 с;
corp-агрегат EXPLAIN = 40 мс; M1-атрибуция «52 с = K6» устарела).

Контекст: `MOL_PLAN_2026-09-11.md` §0–§3; mol-k6/red (гипотеза stock#1/#2 —
частично подтверждена кодом, сдвиг атрибуции: тяжёлое **до** K6, не внутри).

---

## Вердикт одной строкой

На sales+«полный отчет» **50,6 с = if-тело stock-фильтров** (`z20:2232–2237`),
не else→`prefer_entity_for_stock`→`stock_canon_src`. Детектор
`stock_question_engaged` даёт **ложное True**: kind резолвится в product-catalog
(«чего»/товар), `want=list`/breakdown («полный отчет») включает
`balance_routing_core`, а **`sales_sum_intent` (текст «продали») в гейт не входит**
— в отличие от `balance_path_engaged`. Плюс каждый вызов детектора гоняет
SQL/word-loop (и внутри фильтров — ещё раз). **9,5 с prefer_catalog(+rank)** —
в основном тот же warehouse word-loop внутри `catalog_kind_total_question`,
даже когда ответ False. План: быстрый negative по уже существующему
`sales_sum_intent` / полям intent без SQL-проб; один кэш на запрос; складской
путь для настоящих остатков не трогать. Ожидание **−58…−65 с**.

---

## 1. Карта блока (файл:строка)

```
z20:2228  prefer_entity_for_rank          ┐
z20:2229  prefer_entity_for_sales         ├  зонд: sales 0,8 с; catalog+rank 9,5 с
z20:2230  prefer_entity_for_catalog_count ┘
z20:2232  if stock_question_engaged:      ⎫
z20:2233      balance_capable_or_registers⎫
z20:2234      filter_stock_balance_sales_noise  ⎬  Z4→Z6 = 50,6 с
z20:2235      filter_stock_goods_registers      ⎪
z20:2236–37   (stock_canon_locked убран)        ⎭
z20:2238  else:
z20:2239      prefer_entity_for_stock → stock_canon_src:1066 (engaged снова)
z20:2254  K6R.apply_to_candidates         → Z6→Z7 = 1,3 с
z20:2270  if stock_question_engaged: …    → входит в хвост до «собраны» (роль C)
```

Симметрия post-K6 (`2270–2286`) — тот же контур; на этом rid зонд отдаёт 25,3 с
роли C (counts). Здесь разбираем **pre-K6 stock#1 = 50,6 с**.

---

## 2. Какая ветка: if-тело, не else→canon

### 2.1 Почему engaged=True на sales-вопросе

`stock_question_engaged` (`z12:416–437`):

| Шаг | Код | На rid (логика полей) |
|---|---|---|
| `catalog_count_question` | `:420–422` | False («прода» в q режет прайс; kind-total — ниже) |
| `catalog_kind_total_question` | `:423–425` | False, но **уже платит** warehouse-loop |
| `_kind_is_stock_scoped` | `:426` | **True**, если kind→product-catalog (`:113–126`: `_catalogs_for_axis_word` + `_is_product_catalog_target`) — типично для «чего»/товар |
| `question_mentions_warehouse_axis` | `:427` | опционально; word-loop по всем словам q |
| `balance_routing_core` | `:430–431` | **True**, если `question_wants_breakdown` (`want=list` от «полный отчет» / list-ось) **и** `intent_axis_words` непуст (`:366–367`) |
| `sales_kind_in_intent` | внутри routing `:359–360` | смотрит **только** kind/measure на подстроки «продаж»… — **не** текст вопроса «продали» |
| `sales_sum_intent` | — | **не вызывается** из `stock_question_engaged` |

Контраст — уже есть правильный гейт, но stock его не использует:

```383:387:ubuntu/serenedb/ask/z12_stock_balance.py
def balance_path_engaged(intent, plan=None, question=""):
    """Balance-path: routing по intent; sales-sum исключается."""
    if sales_sum_intent(intent or {}, question):
        return False
    return balance_routing_core(intent, plan, question)
```

`question_asks_stock_balance` → `balance_path_engaged` (с отсечением sales).
`stock_question_engaged` идёт в `balance_routing_core` напрямую → sales+breakdown+product
kind = **ложный складской**.

Маркеры «всего» сами по себе тут ни при чём (`question_has_aggregate_total_marker`
требует уже `balance_routing_core`). Ложный вход даёт связка:

1. **product-kind** (ось «чего»/товар → catalog ТМЦ), не «остаток»-лексика;
2. **breakdown/list** (`question_wants_breakdown`: `want=list` — `z10:35–36`), что
   даёт «полный отчет» / «и чего»;
3. **дыра:** нет `sales_sum_intent` в начале `stock_question_engaged`.

### 2.2 Следствие: if-тело, не else

При `engaged=True` выполняется `2232–2237`, **else `2238–2239` не берётся**.
Значит 50,6 с — не «мгновенный» `stock_canon_src` с повторным False, а тело
фильтров (+ повторные вычисления предиката внутри них).

Паттерн «дважды: if + stock_canon_src:1066» из ТЗ — это **архитектура** для
случая `engaged=False` (else). На данном классе вопросов срабатывает другая
двойственность: **if pre-K6 + if post-K6**, и внутри каждого — ещё pred в
`filter_*`.

---

## 3. SQL и число вызовов в if-теле (один проход pre-K6)

### 3.1 Предикат `stock_question_engaged` (дорого даже до return)

На **каждый** вызов (без кэша):

| # | Подфункция | SQL / работа | Файл:строка |
|---|---|---|---|
| P0a | `catalog_kind_total_question` → `question_mentions_warehouse_axis` | цикл слов q → `entity_form_catalogs_for_kind` (+ при period `allow_meaning` → `meaning_candidates`/embed) | `z11:716–721`, `z12:190–200`, `z05:315+` |
| P0b | то же → иногда `balance_routing_core` | при `state_path`: `registers_for_kind_axes` + EXISTS по корпусу | `z12:353–368`, `:457–466` |
| P1 | `_kind_is_stock_scoped` | catalogs по kind; `_stock_place_axis_catalogs` (кэш 300 с, первый раз — тяжёлый EXISTS) | `z12:113–126`, `:54–81` |
| P2 | `question_mentions_warehouse_axis` | **второй** word-loop (если P0a не закэшировал оси) | `z12:395–401` |

Вызовы pred на одном if-теле pre-K6:

| Сайт | Строка |
|---|---|
| `z20` if | `2232` |
| `filter_stock_balance_sales_noise` | `z13:23` |
| `filter_stock_goods_registers` | `z12:869` |

**= 3× полный pred** на один вход в блок (и ещё столько же post-K6 при True).

### 3.2 Тело при True

| Функция | SQL | Вызовов / заметка |
|---|---|---|
| `balance_capable_or_registers` | `search_balance_map` (кэш `_BALANCE_MAP` 300 с) | 1; дёшево после прогрева (`:719–729`) |
| `filter_stock_balance_sales_noise` | **0** (имя src); но снова pred | `z13:21–28` |
| `filter_stock_goods_registers` → `stock_goods_pool` | `registers_for_kind_axes`: refcols + **`EXISTS (… search_corpus … nums…)`** (`:457–466`); затем `_stock_registers_with_product_axis` (refcols IN) | **1× тяжёлый EXISTS-зонд корпуса** — главный кандидат на десятки секунд |
| `filter_balance_structural` | в pre-K6 **нет**; только post-K6 (`2279/2284`) → `GROUP BY` корпус IN (`:1283–1287`) | относится к хвосту после K6 |

`stock_asks_named_product` / `stock_goods_pool(capable)` — только named-ветка
post-K6 (`2275–2278`); на «полный отчет» без именованного товара обычно else-ветка
с `filter_balance_structural`.

### 3.3 Оценка разложения 50,6 с (по коду, не EXPLAIN)

| Кусок | Оценка |
|---|---|
| 3× pred (word-loop ± meaning при period «вчера») | существенная доля; mol-k6: embed ≈0,45 с/текст × слова |
| 1× `registers_for_kind_axes` EXISTS по корпусу | доминирует, если pred уже True |
| `balance_capable_*` / noise filter по имени | ≪1 с |

Итог: **ложная ветка if + дорогой pool**, не «пустой else».

---

## 4. Плюс 9,5 с: prefer_catalog + rank

Порядок в коде: **rank → sales → catalog** (`2228–2230`). Зонд группирует
«prefer_catalog+rank» = 9,5 с отдельно от sales 0,8 с — берём числа зонда.

### 4.1 `prefer_entity_for_rank` (`z10:428–491`)

- Гейт: `rank_intent_from` — при `want=list` **True сразу** (`:93–94`), без SQL.
- Тело: 1–2 лёгких запроса к `search_tables` (parent/written_by + lift).
- **Не объясняет 9 с**, если только rank.

### 4.2 `prefer_entity_for_catalog_count` (`z11:759–794`)

```743:746:ubuntu/serenedb/ask/z11_sales.py
def catalog_count_question(intent, question):
    """Канон count по справочнику: прайс (лексика) или kind→catalog без stock-path."""
    if catalog_kind_total_question(intent, question):
        return True
```

`catalog_kind_total_question` **всегда** сначала зовёт
`question_mentions_warehouse_axis` (`z11:719–721`) — тот же word-loop по
«сколько/продали/вчера/чего/полный/отчет…», даже когда итог False из‑за
`balance_routing_core` или product-kind.

На sales-q с периодом это и есть правдоподобный источник **~9,5 с** до stock-блока.
Сам reorder catalog на этом Q не нужен (`catalog_count_question` → False после
оплаты гейта).

### 4.3 `prefer_entity_for_sales` = 0,8 с (зонд)

Согласуется: TABLES + lift; `_measures_by_src` при холодном кэше — полный
unnest корпуса (`z09:116–117`), но зонд уже видит 0,8 с → кэш тёплый или путь
без cold full-scan.

---

## 5. ПЛАН правок (файл:строка) — только оптимизация существующего

Складской путь для **истинных** остатков не менять (фильтры, pool, canon, bridge).

### S1 — быстрый negative в `stock_question_engaged` (главный выигрыш)

**Где:** `z12:416` — первые строки тела, **до** `_kind_is_stock_scoped` /
warehouse-loop.

**Что:** если `sales_sum_intent(intent, question)` → `return False`.
Уже существующая функция (`z11:21+`), читает intent+вопрос, **без SQL**.
Зеркало уже принятого правила в `balance_path_engaged:385–386`.

**Не** новый доменный список под okna: переиспользуем тот же sales-детектор,
что режет balance-path и включает prefer_sales.

**Ожидание:** на rid-классе engaged=False → if-тело **не входит** →
−50,6 с (Z4→Z6) + симметрично облегчается post-K6 stock#2.

### S2 — кэш результата на запрос (одиночный вызов)

**Где:** `z12:416` (обёртка) + опционально `diag["_stock_engaged"]` /
weak key `(id(intent), question)` в модульном dict с clear на границе `answer`.

**Что:** первый расчёт пишет bool; `filter_stock_*`, `stock_canon_src:1066`,
вторые `z20:2270/2187/…` читают кэш. Убрать повторный word-loop ×3–6.

**Ожидание:** на **настоящих** stock-q — −дорогость pred×(N−1); на sales после S1 —
кэш держит False за ~0.

### S3 — дешёвый pred по полям intent (без SQL-проб), до word-loop

**Где:** `z12:416` после S1; вспомогательно не трогать тела
`_kind_is_stock_scoped` / `registers_for_kind_axes` для positive path.

**Что (порядок):**

1. S1 sales_sum → False.
2. `sales_kind_in_intent(intent)` → False (уже есть; сейчас только внутри routing).
3. Если нет candidate-сигналов из **полей** intent без SQL:
   - нет `kind` и нет `action_axis`, и не `state_path_active`, и не
     `question_wants_breakdown` → False **без** warehouse word-loop.
4. Только если остался кандидат в stock — тогда нынешние SQL-пробы kind/оси
   (складской путь как сейчас).

**Важно:** не добавлять лексику «полный отчет» как deny-list (п.0 /
no_domain_wordlists). Разрез уже кодируется `want=list` /
`question_wants_breakdown` — универсально.

### S4 — short-circuit в `catalog_kind_total_question` / `catalog_count_question`

**Где:** `z11:716` / `:743`.

**Что:** до `question_mentions_warehouse_axis` — если `sales_sum_intent` → False
(catalog-count канон и так не про продажи). Снимает **9,5 с** гейта на этом Q.

**Ожидание:** −8…−9,5 с из Z3→Z4.

### S5 — не трогать

- Тела `filter_stock_goods_registers` / `stock_goods_pool` / EXISTS для
  **engaged=True** настоящих остатков (это MOL §4c / витрина п.3 — другой пакет).
- Wiki-каскад, K6 SQL (уже 1,3 с на зонде).
- `prefer_entity_for_sales` / sales-canon.

### S6 — опционально позже (не в бюджет −58…−65)

Передавать `engaged`/`plan` вниз, чтобы `filter_*` не звали pred вовсе
(сейчас `plan=` есть, но pred всё равно полный). После S2 достаточно кэша.

---

## 6. Сводка ожиданий (анти-двойной счёт)

| Правка | Класс Q | −сек | Зависимость |
|---|---|---|---|
| S1 | sales+list/полный путь | **−50…−51** (Z4→Z6) | — |
| S4 | тот же | **−8…−9,5** (catalog-gate) | независим от S1 |
| S2 | любой с многократным pred | −остаток повторов; на sales после S1 ≈0 | после S1 |
| S3 | non-stock без kind/axis | доп. страховка мгновенного выхода | после S1 |
| **Σ на rid-классе** | | **≈ −58…−65** | S1+S4 (± хвост post-K6 stock) |

Не суммировать с выигрышем K6-индекса (уже 1,3 с) и не с ролью C (counts 25,3 с).

---

## 7. Приёмка (для исполнителя / красной роли)

1. **Негатив (этот Q и siblings sales_sum):** `stock_question_engaged` = False за
   <50 мс; diag без `stock_non_goods_drop` / stock-фильтров; Z4→Z6 ≈ 0.
2. **Позитив (настоящий остаток):** тот же путь фильтров/pool/bridge; замки stock;
   L67 stock-группы без регресса.
3. **Универсальность:** гейт = `sales_sum_intent` + поля intent, без словаря
   «полный отчет»/okna.
4. **Кэш:** N вызовов pred в одном `answer` → 1 расчёт (счётчик/diag).
5. Тайминг 3 классов после внедрения — с ролью R / оркестратором.

---

## 8. Связь с MOL / устаревшей атрибуцией

| Было (mol-k6/m4) | Стало (зонд b11dac07) |
|---|---|
| ~52 с ≈ K6 SQL | K6-apply **1,3 с**; corp 40 мс |
| stock#1 «внутри 52» гипотеза | stock#1 **выделен**: Z4→Z6 **50,6 с** |
| stock#2 ≈ 21,5 с до «собраны» | хвост 25,3 с → роль C (counts); stock#2 после S1 должен схлопнуться |

Пункт плана MOL §4c (витрина вместо EXISTS) остаётся полезен для **истинных**
stock-q; для sales-ложного входа **достаточен S1** и дешевле витрины.

---

*Конец OPT-S. Внедрение — после сверки с opt-c / opt-p / opt-r и стоп-точки.*
