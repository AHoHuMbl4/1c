# FINAL-A: точный дифф изъятия stock-фильтров из маршрутизации выбора сущности

Дата: 11.09. Роль: **A** (аудитор/проектировщик). Режим: **только чтение**.
Основание: решение владельца «вообще убрать фильтры. Это хардкод»; решения №1 / №2 / №10 / п.0.
Граница: только маршрутизация выбора сущности в `z20`. Счётные слои (z16/z17,
`balance_capable_or_registers` при подсчёте **уже выбранной** сущности, balance-разборки)
не трогаются.

Файлы истины: `ubuntu/serenedb/ask/z20_ask_main_http.py`, `z12_stock_balance.py`,
`z13_fork_outcomes.py`, `z11_sales.py`, `z21_wiki_choice.py`, `wiki_card_hybrid.sql`.
Контекст зондов: `docs/audit/opt-s.md`, `opt-c.md`, `burn-x.md`.

---

## Вердикт одной строкой

Изъять **три** куска в z20: (1) pre-K6 блок `2231–2239` целиком вместе с `plan={}`;
(2) post-K6 stock#2 `2270–2286` целиком; (3) два хвоста `prefer_entity_for_stock` на
fork-пуле (`2685`) и arb_pool (`3302`). Вики-каскад **уже** не читает `cands` —
фильтры были дорогим хардкодом-судьёй рядом с единственным судьёй (паспорт).
Catalog word-loop **9,5 с** — **не** внутри блока фильтров; закрывается отдельно
(burn-x X14), иначе −85 с не соберутся.

---

## 1. Блок z20:2227–2238 — точный дифф

Актуальные строки (файл, не устаревшие номера из промта):

```2231:2239:ubuntu/serenedb/ask/z20_ask_main_http.py
    plan = {}
    if stock_question_engaged(question, intent):
        capable = balance_capable_or_registers()
        cands = filter_stock_balance_sales_noise(cands, question, diag)
        cands = filter_stock_goods_registers(cands, question, diag, intent=intent, plan=plan)
        # [01.09 «один путь»] постановка stock_canon_locked убрана: замок —
        # обходной выбор сущности. Пул чистится фильтрами, выбирает вики.
    else:
        cands = prefer_entity_for_stock(cands, question, intent)
```

### Что удалить

| Строки | Что | Зачем |
|---|---|---|
| `2231` | `plan = {}` | жил **только** ради `plan=` в filter_*; до вики `plan` больше нигде не читается (`rg`: 2231/2235/2273 → потом 2811/2842). После изъятия #1+#2 инициализация не нужна: focus/`wiki` сами ставят `plan` |
| `2232–2237` | `if stock_question_engaged` + `balance_capable` + два `filter_stock_*` | чистка пула = предметный судья; зонд **50,6 с** ложного срабатывания (opt-s) |
| `2238–2239` | `else: prefer_entity_for_stock` | тот же предметный подъём канона через `stock_canon_src` |

`capable` в #1 **мертв** сразу после присваивания (нигде не используется) — уходит с блоком.

### Что остаётся перед блоком (не трогать)

```2222:2230:ubuntu/serenedb/ask/z20_ask_main_http.py
    cands = list(by) + [t for t in extra if t not in by]
    ...
    cands = prefer_entity_for_rank(cands, intent, question)
    cands = prefer_entity_for_sales(cands, intent, question)
    cands = prefer_entity_for_catalog_count(cands, intent, question)
```

Пул после изъятия: буквально (`by`) + смысл/синонимы (`extra`) + event-expand +
`prefer_rank` / `prefer_sales` / `prefer_catalog` + K6-ранг — **без** складской чистки.

### Псевдо-дифф

```diff
     cands = prefer_entity_for_catalog_count(cands, intent, question)
-    plan = {}
-    if stock_question_engaged(question, intent):
-        capable = balance_capable_or_registers()
-        cands = filter_stock_balance_sales_noise(cands, question, diag)
-        cands = filter_stock_goods_registers(cands, question, diag, intent=intent, plan=plan)
-        # [01.09 «один путь»] …
-    else:
-        cands = prefer_entity_for_stock(cands, question, intent)
     if K6R:
```

---

## 2. Все вызовы в маршрутизации (z20 grep)

### 2.1 Таблица call-site

| Локус | Вызов | Слой | Вердикт изъятия |
|---|---|---|---|
| `2187` | `stock_question_engaged` → bypass `no_data` при пустом `by` | ворота до пула | **серый**: не filter_*, но маршрутный гейт. Для grep-замка роли B («нет `stock_question_engaged` в маршрутизации») — убрать или заменить на `balance_path_engaged` / `question_expects_accounting_data`. Иначе пустой отбор на складском Q сразу `no_data` и **не дойдёт** до вики |
| `2232–2239` | engaged + filter_stock_* / prefer_stock | сборка пула #1 | **изъять** (§1) |
| `2270–2286` | engaged + filter_stock_* + named + `filter_balance_structural` | сборка пула #2 post-K6 | **изъять** (§3) |
| `2685–2692` | `prefer_entity_for_stock(_fork_pool…)` | fork-детектор | **изъять** prefer-обёртку; оставить `prefer_rank/sales/catalog` как у остального пула |
| `2670–2674` | `_skip_stock_fork` через engaged + `stock_canon_locked` | fork-ворота | **серый**: `stock_canon_locked` **нигде не ставится** (grep assign = 0 с 01.09) → ветка фактически мертва. Упростить до удаления `_skip_stock_fork` или оставить no-op |
| `3302` | `arb_pool = prefer_entity_for_stock(...)` | круг арбитра **после** вики | **изъять обязательно** — это обход «одного судьи» (уже фиксировали td1: prefer после `wiki_arbiter_locked` может подменить голову каноном) |
| `3305` | `sales_canon_force_pool(... stock_canon_locked ...)` | lock-коллапс | **не трогать тело** force_pool; `stock_canon_locked` мёртв как постановка. Чистка имени — косметика |
| `4384–4399`, `4785` | engaged / stock_canon_locked | мера / оси / aggregate | **оставить** — счётный слой (граница ТЗ) |
| `z12:1065` `stock_canon_src` | только из `prefer_entity_for_stock` | — | прямых зовов в z20 **нет**; уходит вместе с prefer |

`stock_canon_src` в z20 **не зовётся напрямую** — только через `prefer_entity_for_stock`
(`z12:1080–1082`).

### 2.2 Catalog-гейт word-loop (burn-x «ранний wh») — тоже?

**Нет, не автоматически этим диффом.**

Цепочка 9,5 с (opt-s):

```
z20:2230 prefer_entity_for_catalog_count
  → z11:761 catalog_count_question
    → z11:745 catalog_kind_total_question
      → z11:719–720 question_mentions_warehouse_axis   ← word-loop ПЕРВЫМ
```

Плюс **второй** платёж того же loop внутри `stock_question_engaged` (`z12:423–427`),
который уходит с блоком #1/#2.

Итог по бюджету зонда:

| Кусок | Закрывается изъятием фильтров? |
|---|---|
| 50,6 с stock#1 | **да** |
| 25,3 с stock#2 | **да** |
| 9,5 с catalog+rank wh | **частично**: повтор через engaged — да; **ранний** wh в `catalog_kind_total` — **нет** |

Чтобы добрать 9,5 с: burn-x **X14** — дешёвые поля intent (`want`/`period`/`kind`) **до**
`question_mentions_warehouse_axis`; wh не звать, пока не нужен. Это правка `z11:716–740`,
не фильтра маршрута. В скоуп FINAL-изъятия фильтров **не смешивать**, но в том же
выкате/спринте — иначе «~85 с» не сходится.

---

## 3. После «кандидаты собраны»: stock#2

```2270:2287:ubuntu/serenedb/ask/z20_ask_main_http.py
    if stock_question_engaged(question, intent):
        capable = balance_capable_or_registers()
        cands = filter_stock_balance_sales_noise(cands, question, diag)
        cands = filter_stock_goods_registers(cands, question, diag, intent=intent, plan=plan)
        # …
        named = stock_asks_named_product(question, intent)
        if named:
            _goods_cap = stock_goods_pool(capable)
            cands = [c for c in cands if c in _goods_cap or c in capable]
            cands = filter_balance_structural(cands, diag)
        else:
            _stock_locked = diag.get("stock_canon_locked")
            ...
            cands = filter_balance_structural(cands, diag)
            ...
    шаг("кандидаты собраны", всего=len(cands))
```

### Что происходит по коду сейчас

1. Снова `stock_question_engaged` (дорого без кэша — opt-c: **25,3 с** на том же rid).
2. Те же `filter_stock_*` (повтор EXISTS/`stock_goods_pool`).
3. Named-ветка: пересечение с `stock_goods_pool` ∪ capable + `filter_balance_structural`.
4. Else: попытка воткнуть мёртвый `stock_canon_locked` + structural.
5. Только потом шаг «кандидаты собраны» → not_for → focus/wiki.

### Дифф изъятия

Удалить **весь** `if stock_question_engaged` `2270–2286`. После K6 сразу:

```diff
         шаг("K6 v2", кандидатов=len(cands))
-    if stock_question_engaged(question, intent):
-        ... весь блок ...
     шаг("кандидаты собраны", всего=len(cands))
```

`filter_balance_structural` здесь — ещё одна **предметная чистка пула до выбора**, не
подсчёт выбранной сущности. По решению владельца («фильтры = хардкод») уходит вместе
с #2. Функция в z12 **остаётся** (тесты / возможный счётный reuse).

---

## 4. Сироты z12/z13 после изъятия из маршрутизации

### 4.1 Станут неиспользуемыми **из z20-маршрута** (список)

| Функция | Файл | После изъятия | Вердикт |
|---|---|---|---|
| `filter_stock_balance_sales_noise` | z13:21 | только тесты | **оставить в дереве** (тесты + возможный счётный reuse); из маршрута dead |
| `filter_stock_goods_registers` | z12:868 | только тесты | то же |
| `prefer_entity_for_stock` | z12:1080 | только тесты | то же |
| `stock_canon_src` | z12:1065 | только через prefer + тесты | то же |
| `filter_balance_structural` | z12:1268 | только тесты (был только #2) | то же |

### 4.2 Живут дальше (не сироты) — счётные / вспомогательные

| Функция | Кто зовёт после изъятия |
|---|---|
| `stock_question_engaged` | z20 счётные ветки `4384+` / `4399` / `4785`; z13 fork; тесты; catalog-гейты косвенно |
| `balance_capable_or_registers` | z12 внутри `stock_goods_pool` / net-distinct / breakdown; bootstrap-патчи net |
| `stock_goods_pool` | `_resolve_breakdown_balance_src`, net-aggregate path, тесты |
| `stock_asks_named_product` | bootstrap / measure-skip / тесты |
| `stock_balance_is_sales_noise` | filter (сирота-маршрут) + rank-key + тесты |
| `stock_breakdown_leader_fallback` | z20 после выбора src (счётный) |
| `question_mentions_warehouse_axis` / `resolved_warehouse_*` | catalog_kind_total, warehouse clarify, z21 axis carriers |

**Не удалять** тела из дерева в этом пакете: решение №10 = удаление **маршрутных вызовов**,
не выжигание складского счётного API. Dead-code sweep — отдельный коммит после красных
тестов, которые ещё зовут API юнитом.

---

## 5. Новый путь складского вопроса по коду

### 5.1 Цепочка после изъятия

```
вопрос
  → разбор intent
  → буквальный/смысл отбор → cands (БЕЗ stock-чистки)
  → prefer_rank / prefer_sales / prefer_catalog   # sales/catalog prefer остаются
  → K6 rank
  → шаг «кандидаты собраны»
  → not_for (по cands)
  → wiki_primary_entity_cascade (z21)
        try_wiki_hybrid_entity_pick
          wiki_hybrid_pool  ← search_wiki_entity_card (kNN ∪ struct), НЕ cands!
          wiki_pick_from_cards (LLM)
          wiki_verify_candidates (паспорта)
        → leader | clarify | no_data
  → (если wiki_verify == leader) wiki_arbiter_locked, doubt=False
  → arb_pool = picked   # без prefer_entity_for_stock
  → арбитр только при сомнении
  → подсчёт выбранной сущности (z16/z17; balance_* при нужде)
```

Ключевой факт кода: **`cands` не входят в вики-пул.**

```913:924:ubuntu/serenedb/ask/z21_wiki_choice.py
def try_wiki_hybrid_entity_pick(question, intent, diag, cut, t0,
                                by=None, match="", preds=None):
    ...
    cards = wiki_hybrid_pool(question, intent)
```

`wiki_primary_entity_cascade` принимает `cands`, но в тело hybrid-pick **не передаёт**.
Фильтры на `cands` меняли fork/арбитр/not_for и **время**, а не состав карточек вики.

### 5.2 Попадёт ли баланс-регистр в пул?

**A. Буквальный/смысл `cands`:** зависит от корпуса/алиасов/эмбеддингов таблиц.
Слова «остатки»/`склад` в вопросе могут подтянуть `accumulationregister_*` через
индекс/`TABLES` label — **не гарантировано** и **не обязательно** для выбора
(вики независима). После изъятия в `cands` также останутся sales-регистры —
раньше их резал `filter_stock_balance_sales_noise`.

**B. Вики-пул (`wiki_card_hybrid.sql`):**

| Вход | Условие появления баланс-регистра |
|---|---|
| `knn` / `knn_raw` | есть карточка в `search_wiki_entity_card` с `emb`, близкая к вопросу |
| `struct_register` | `accumulationregister_%` + непустой `action_axis` + refcol stems ∩ оси |
| alias-слой | join `search_entity_alias` (aliases / best_used_for) |

Нет отдельной метки «это баланс-остаток» в SQL пула — отбор **смысловой/осевой**,
не `balance_registers` из `search_meta`.

**C. Выбор карточки:** LLM по полям name/description/axes/measures → verify по
паспортам (`doesNotAnswer` / fit yes|no|unsure).

**D. Арбитр:** при `wiki_arbiter_locked` круг из одного — ответ. Без
`prefer_entity_for_stock` канон больше не вытесняет лидера.

**E. Паспорт / подсчёт:** уже на **выбранном** src; `balance_capable_or_registers`
здесь законен (граница ТЗ).

### 5.3 Где споткнуться

| Риск | По коду | Симптом |
|---|---|---|
| **Нет карточки** у баланс-регистра | `wiki_hybrid_pool` → `[]` → `wiki_empty_pool` / `no_data` | honest_no (сейчас gold остатков = `no_data` — совпадает с приёмкой burn-y) |
| Карточка есть, но kNN тянет **продажи** | verify должен дать fit=no по паспорту; если yes → **confident_wrong** | главный регресс изъятия; роль C |
| `action_axis` пуст | `struct_register` молчит; остаётся только kNN | слабее гарантия «регистр с осью склад» |
| Пустой `by` без bypass `2187` | early `no_data` **до** вики | сломать путь «вики спасёт» |
| `prefer_entity_for_stock` на `3302` оставлен | обход паспортного замка | вернуть хардкод-судью |
| Catalog «сколько организаций» | идёт через `prefer_catalog` / `catalog_kind_total`, не через stock-фильтры | изъятие фильтров **не** ломает; X14 — отдельный риск/выигрыш |

### 5.4 Ответ на «выбирает ли вики баланс-регистр?»

Код **не** форсирует баланс-регистр. Выбор = карточка+паспорт. Если у регистра
остатков нет wiki-карточки / emb / адекватного `best_used_for` — вики **не** «знает»
остатки лучше sales; фильтры раньше **подсовывали** capable в `cands`/голову, маскируя
дыру. Изъятие **вскрывает** дыру данных установки, а не чинит её маршрутом
(решение №2: чинить начало = вики/паспорт/корпус карточек, не filter_*).

---

## 6. Чеклист исполнителя (один коммит маршрута)

1. Удалить `z20:2231–2239` (включая `plan={}`).
2. Удалить `z20:2270–2286` (stock#2 целиком).
3. Убрать `prefer_entity_for_stock` с fork (`2685`) и arb_pool (`3302`).
4. Решить `2187` bypass: заменить на не-filter предикат **или** оставить временно и
   ослабить grep-замок роли B до «нет filter_stock_*/prefer_entity_for_stock».
5. Не трогать `4384+` / net-distinct / `stock_breakdown_*`.
6. Не удалять функции z12/z13 в том же коммите.
7. Companion (тот же выкат или следующий): X14 catalog_kind_total — иначе −9,5 с не будет.
8. Приёмка — роль B (L67 stock slice, grep-ratchet, 3 класса таймингов).

---

## 7. Связь с решениями владельца

| Решение | Как закрывает этот дифф |
|---|---|
| №1 один судья = паспорт | убираем filter/prefer как второго судью пула и arb_pool |
| №2 чинить начало | дыра «нет карточки баланса» чинится вики/установкой, не filter_* |
| №10 удаление вместо заплаток | вырезаем блоки, не кэшируем engaged вокруг них |
| п.0 нет предметной маршрутизации | stock_sales_noise / goods_registers / canon_src — ровно она |

---

*Конец final-a.md. Код не менялся.*
