# W1 — карта живости `ask/z11_sales.py`

Срез: 12.09.2026. Только чтение кода. Метод: AST верхнего уровня зоны +
grep/AST Call (включая `globals().get("…")` / `getattr`) по `ask/*.py`,
`z20_ask_main_http.py` (новый), `z20_ask_main_http_legacy.py`, `test_*.py`,
`_bootstrap.py` / `_imports.py` / `_wire.py`. Транзитив: граф вызовов с
раздельными корнями `NEW:answer…` и `LEG:answer…` (общее имя `answer` в двух
файлах не сливать).

Файл зоны: 389 строк; 16 символов верхнего уровня (только `def`, констант нет).
Загрузка: `_bootstrap._zone_path(11, "sales")` → exec в общий namespace;
в конце зоны `register_zone('ask.z11_sales', …)`. В `_imports.py` / `_wire.py`
имён зоны нет (кроме общего `register_zone`).

---

## Таблица символов

| Символ | Строки (диапазон / N) | Кто зовёт (файл:строка) | Вердикт |
|---|---|---|---|
| `sales_kind_in_intent` | 15–23 / **9** | **другие зоны:** `z12_stock_balance.py:359` (`balance_routing_core`), `:374` (`_stock_intent_signal`). Прямо из z20 — нет. Тесты / bootstrap / imports / wire — нет. | **ЖИВА НОВОМУ** (транзитивно) |
| `sales_sum_intent` | 26–76 / **51** | **new z20:** нет прямого. **legacy z20:** `z20_ask_main_http_legacy.py:1626` (`period_assumed_needs_clarify`). **зоны:** `z02_intent.py:386` / `z16_veto_pick_entity.py:350` (`question_expects_accounting_data`, z16 перекрывает z02), `z05_entity_form.py:155` (`sales_compare_intent`), `z12_stock_balance.py:385` (`balance_path_engaged`), `z16:368` (`canon_claims_question`); внутри z11: `sales_rank_engaged`, `sales_canon_intent`, `_zero_period_not_missing`. **тесты:** `test_sales_rank_canon.py`, `test_sales_canon_prefer.py`, `test_stock_balance_path.py`. | **ЖИВА НОВОМУ** (прямо через `_zero_period_not_missing` + транзитивно) |
| `_sales_register_score` | 79–94 / **16** | Только `z05_entity_form.py:1066` (`entity_form_axis_on_sales`); комментарий `:1042`. До new z20 цепочки нет (`try_entity_form_answer` в new не зовётся). | **ЖИВА ТОЛЬКО LEGACY** |
| `sales_lift_possible` | 97–141 / **45** | Только внутри z11: `sales_rank_engaged:171`, `sales_canon_intent:245`. Оба корня — legacy. | **ЖИВА ТОЛЬКО LEGACY** |
| `sales_rank_engaged` | 144–171 / **28** | **legacy z20:** `:3384`, `:3770` (`answer`). New — нет. Тесты: `test_sales_rank_canon.py`, `test_sales_canon_prefer.py`. | **ЖИВА ТОЛЬКО LEGACY** |
| `_sales_rank_top_n` | 174–206 / **33** | **legacy z20:** `:3773` (`answer`). **зоны:** `z05_entity_form.py:38` (`entity_form_rank_single_window` ← `sales_compare_intent` / `sales_compare_windows`). **new z20** зовёт `sales_compare_intent:1997`, `sales_compare_windows:1999`. Тест: `test_sales_rank_canon.py`. | **ЖИВА НОВОМУ** (транзитивно) |
| `rank_groups_answer_text` | 209–237 / **29** | Производственных вызовов нет. Только `test_unit_from_data.py:191`. | **МЁРТВА** |
| `sales_canon_intent` | 240–266 / **27** | `globals().get`: `z05:879` (`try_event_count_period_clarify`), `z16:370` (`canon_claims_question`). Оба — только с legacy-корня. New — нет. | **ЖИВА ТОЛЬКО LEGACY** |
| `sales_money_measure` | 269–291 / **23** | **зоны:** `z18_compose.py:340` (`_measure_dimension`), `z16:406` (`measure_class_alts`, legacy). **new:** `_onepath_compose_gate` → `_unit_for_measure` → `_measure_dimension`. Прямо в new z20 call-site нет (замок `test_measure_hatch_luk` это требует). `test_no_pre_wiki_reorders.py` — статическое имя. | **ЖИВА НОВОМУ** (транзитивно, compose) |
| `sales_qty_measure` | 294–304 / **11** | `z18:337` (`_measure_dimension`), `z16:407` (`measure_class_alts`). Тот же new-путь через compose. | **ЖИВА НОВОМУ** (транзитивно, compose) |
| `_zero_period_not_missing` | 307–314 / **8** | **new z20:** `:2134`, `:2150` (`answer`). **legacy:** `:3793`, `:3812`, `:3829`, `:3843`. Внутри зовёт `sales_sum_intent`. | **ЖИВА НОВОМУ** (прямо) |
| `sales_ticket_hatch` | 317–323 / **7** | Нигде. | **МЁРТВА** |
| `sales_noncanon_focus` | 326–334 / **9** | **зоны z05** (много): `entity_form_movements_for_kind`, `entity_form_count_target_is_movement`, `entity_form_expand_pool`, `event_kind_catalog_expand_pool`, `entity_form_applicable`, `try_event_count_period_clarify`, `entity_form_structs`; внутри z11: `sales_lift_possible:108`. New достигает через stock/intent-цепочки к `entity_form_movements_for_kind`. Тесты: `test_sales_canon_prefer.py`. | **ЖИВА НОВОМУ** (транзитивно) |
| `_is_product_catalog` | 337–343 / **7** | **legacy z20:** `:3862`. **зоны:** `z05:1102,1114` (`entity_form_structs`); `z12:745` (`globals().get` в `_is_product_catalog_target`); внутри z11: `catalog_kind_total_question:368`. New: `aggregate_stock_net_distinct` → `_is_product_catalog_target` и catalog-классификаторы. Тесты: `test_stock_balance_path.py` (моки). | **ЖИВА НОВОМУ** (транзитивно) |
| `catalog_kind_total_question` | 346–370 / **25** | `z12:423` (`globals().get` в `stock_question_engaged`); внутри z11: `sales_canon_intent`, `catalog_count_question:375`. New: wiki-каскад → `question_expects_accounting_data` → `stock_question_engaged`. Тест: `test_stock_balance_path.py`. | **ЖИВА НОВОМУ** (транзитивно) |
| `catalog_count_question` | 373–386 / **14** | `z12:420` (`stock_question_engaged`); `z16:373` (`canon_claims_question`, legacy); внутри z11: `sales_canon_intent`. New — через wiki → `stock_question_engaged`. Тесты: `test_stock_balance_path.py`, `test_k4_clarify_vs_nodata.py`. | **ЖИВА НОВОМУ** (транзитивно) |

---

## Итог зоны

| Вердикт | Символов | Строк (сумма тел) |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 10 | **190** |
| **ЖИВА ТОЛЬКО LEGACY** | 4 | **116** |
| **МЁРТВА** | 2 | **36** |
| Всего символов | 16 | **342** |
| Файл целиком | — | 389 (шапка + `register_zone`) |

**Зона в целом:** нужна одному пути — да, существенно (≈55% строк символов).
Прямой якорь в new z20 — только `_zero_period_not_missing`; остальное new-живое
тянется транзитивно (wiki/stock/compare/compose). После сноса legacy
останутся мёртвыми: `_sales_register_score`, `sales_lift_possible`,
`sales_rank_engaged`, `sales_canon_intent` (+ уже мёртвые
`rank_groups_answer_text`, `sales_ticket_hatch`).

---

## Транзитивные цепочки (сжато)

### Прямо из нового z20
- `_zero_period_not_missing` ← `new.answer:2134,2150`
- `_zero_period_not_missing` → `sales_sum_intent`

### Новый z20 → зоны → z11
- `sales_sum_intent` ← `sales_compare_intent` ← `new.answer:1997`
- `sales_sum_intent` ← `balance_path_engaged` ← `stock_count_aggregate_without_subject` ← `new.answer:2157`
- `sales_sum_intent` ← `question_expects_accounting_data` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` ← `new.answer:1951`
- `sales_kind_in_intent` ← `balance_routing_core` ← `balance_path_engaged` ← … ← `new.answer`
- `_sales_rank_top_n` ← `entity_form_rank_single_window` ← `sales_compare_intent` / `sales_compare_windows` ← `new.answer:1997/1999`
- `sales_money_measure` / `sales_qty_measure` ← `_measure_dimension` ← `_unit_for_measure` ← `new._onepath_compose_gate` (и `atom_from_agg` / `build_period_empty_answer`)
- `sales_noncanon_focus` ← `entity_form_movements_for_kind` ← … ← `stock_count_aggregate_without_subject` / `parse_intent` ← `new.answer`
- `_is_product_catalog` ← `_is_product_catalog_target` ← `stock_net_register_pair` ← `aggregate_stock_net_distinct` ← `new.answer:2159`
- `catalog_count_question` / `catalog_kind_total_question` ← `stock_question_engaged` ← `question_expects_accounting_data` ← wiki-каскад ← `new.answer`
- `catalog_kind_total_question` → `_is_product_catalog` (внутри z11)

### Только legacy z20
- `sales_rank_engaged` ← `leg.answer:3384,3770` → `sales_lift_possible` → `sales_noncanon_focus` / `sales_sum_intent`
- `_sales_rank_top_n` ← `leg.answer:3773` (плюс общий compare-путь, уже new)
- `sales_sum_intent` ← `leg.period_assumed_needs_clarify:1626`
- `_zero_period_not_missing` ← `leg.answer:3793+`
- `_is_product_catalog` ← `leg.answer:3862`
- `sales_canon_intent` ← `canon_claims_question` / `try_event_count_period_clarify` ← `leg.answer`
- `_sales_register_score` ← `entity_form_axis_on_sales` ← `entity_form_structs` ← `try_entity_form_answer` ← `leg.answer`
- `sales_money_measure` / `sales_qty_measure` ← `measure_class_alts` ← `leg.answer` (доп. к compose)

### Ниоткуда (runtime)
- `rank_groups_answer_text`, `sales_ticket_hatch`

---

## Скрытые выбиратели, доступные новому тракту

Да — зона тащит в один путь классификаторы/хелперы выбора (не wiki-меню):

| Символ | Что выбирает кодом | Как попадает в new |
|---|---|---|
| `sales_money_measure` | меру (денежное поле по лексике/алиасам) | `_measure_dimension` в compose/gate |
| `sales_qty_measure` | меру (количество) | то же |
| `sales_noncanon_focus` | отсев «неканон» регистров продаж (источник) | entity_form / stock-цепочки |
| `_is_product_catalog` | product-каталог по подстрокам имени (источник) | stock net-distinct / catalog-* |
| `_sales_rank_top_n` | K / top-N (ось rank) | через `sales_compare_*` |
| `sales_sum_intent` / `sales_kind_in_intent` | семантика «продажи» → маршрут/period_empty | compare, stock, wiki, `_zero_period_not_missing` |
| `catalog_*_question` | catalog vs stock path | `stock_question_engaged` в wiki-учёте |

Не выбиратели источника/меры, но гейт периода в new: `_zero_period_not_missing`
(пустое окно → не `no_data`).

Legacy-only выбиратели (после flip/сноса legacy отвалятся, если не останется
других корней): `_sales_register_score` (ранг регистра), `sales_lift_possible`
(подъём sales-register из кандидатов), `sales_canon_intent`, `sales_rank_engaged`.

---

## Инфра и тесты (сводка)

| Место | Роль для z11 |
|---|---|
| `_bootstrap.py:34` | грузит зону `_zone_path(11, "sales")` |
| `_imports.py` | символов z11 нет |
| `_wire.py` | только общий `register_zone`; зона саморегистрируется |
| `test_sales_rank_canon.py` | `sales_rank_engaged`, `sales_sum_intent`, `_sales_rank_top_n` |
| `test_sales_canon_prefer.py` | `sales_sum_intent`, `sales_rank_engaged`, `sales_noncanon_focus` |
| `test_stock_balance_path.py` | `sales_sum_intent`, `catalog_*`, моки `_is_product_catalog` |
| `test_measure_hatch_luk.py` | запрет call-site `sales_money_measure` в z20 |
| `test_no_pre_wiki_reorders.py` | читает файл зоны; имена money/qty в списке сноса |
| `test_unit_from_data.py` | единственный зов `rank_groups_answer_text` |
| `test_k4_clarify_vs_nodata.py` | `catalog_count_question` |

---

## Вердикт одной строкой

`z11_sales` **жива одному пути** (190 строк / 10 символов), якорь —
`_zero_period_not_missing` + каскад stock/wiki/compare/compose; **116 строк**
канон/rank/lift — только legacy; **36 строк** полностью мёртвы; в new
протекают скрытые выбиратели меры (`sales_money_measure` /
`sales_qty_measure`) и фильтры источника (`sales_noncanon_focus`,
`_is_product_catalog`).
