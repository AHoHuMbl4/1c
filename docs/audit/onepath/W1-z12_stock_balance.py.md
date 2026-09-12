# W1 — карта живости `ask/z12_stock_balance.py`

**Зона:** `ubuntu/serenedb/ask/z12_stock_balance.py` (1346 строк файла; 74 символа верхнего уровня = 1194 строк тел; остальное — импорты/`register_zone`/пустые).

**Метод:** AST-инвентаризация символов; поиск упоминаний с границами слова по `ask/*.py` + `test_*.py` (включая `getattr`/`globals().get`/строки); замыкание вызовов внутри зоны от входных точек; подъём чужих зон до `z20_ask_main_http.py` (новый) / `z20_ask_main_http_legacy.py` (legacy). Код не менялся.

**Вердикты:**
- **ЖИВА НОВОМУ** — прямо или транзитивно нужна `ASK_ONEPATH=1` тракту;
- **ЖИВА ТОЛЬКО LEGACY** — нужна бывшему тракту; после flip+сноса legacy станет мёртвой;
- **МЁРТВА** — не зовётся живым трактом (только тесты / комментарии / мёртвые соседи / никого).

---

## Итог зоны

| Вердикт | Символов | Строк тел |
|---|---:|---:|
| ЖИВА НОВОМУ | 54 | **777** |
| ЖИВА ТОЛЬКО LEGACY | 4 | **115** |
| МЁРТВА | 16 | **302** |
| **Всего символов** | **74** | **1194** |

**Вывод для одного пути:** зона **нужна** новому тракту (~65% строк). Прямые входы нового z20 узкие (3 вызова), но wiki-каскад z21 + `parse_intent`/`sales_sum_intent` тянут большую остатковую инфраструктуру. После flip останутся лишними ~115 строк legacy-only (складское clarify/меню значений + `_rank_wants_quantity`) и ~302 строки уже мёртвых фильтров/fallback’ов.

**Bootstrap:** `_bootstrap.py` грузит зону в общем списке (`z12_stock_balance.py`). Патч `_patch_z20_wiki_primary` (вставки `stock_count_aggregate_without_subject` / `aggregate_stock_net_distinct` / `stock_asks_named_product`) применяется **только** к `z20_ask_main_http_legacy.py`. Новый z20 уже содержит net-distinct на диске (без гейта `stock_asks_named_product` из патча). `_imports.py` / `_wire.py` имён зоны не упоминают (только `register_zone` в хвосте файла).

---

## Таблица символов

| Символ | Стр. | Кто зовёт (файл:строка[/функция]) | Вердикт |
|---|---:|---|---|
| `_BALANCE_REGS` | 1 | z12:`balance_registers`; тесты `test_stock_balance_path`, `test_warehouse_aggregate_breakdown` | ЖИВА НОВОМУ |
| `_BALANCE_MAP` | 1 | z12:`balance_map_rows`; тесты | ЖИВА НОВОМУ |
| `_STOCK_PLACE_AXIS` | 1 | z12:`_stock_place_axis_catalogs`; тесты | ЖИВА НОВОМУ |
| `_STOCK_PLACE_REF` | 1 | z12:`_catalog_on_stock_eligible_register`; тесты | ЖИВА НОВОМУ |
| `_intent_period_has_meaning` | 3 | только z12 (оси/kind/registers) | ЖИВА НОВОМУ |
| `_catalogs_for_axis_word` | 14 | z12; `test_warehouse_axis_autonomy` | ЖИВА НОВОМУ |
| `_non_product_ref_targets` | 6 | z12:`_stock_cost_side_penalty` | ЖИВА НОВОМУ |
| `_stock_eligible_product_registers` | 8 | z12 place-axis helpers | ЖИВА НОВОМУ |
| `_stock_place_axis_catalogs` | 28 | z12 kind/warehouse/unaccounted (+ мёртвый `_catalogs_joint_with_kind`) | ЖИВА НОВОМУ |
| `_catalog_on_stock_eligible_register` | 27 | z12 warehouse/unaccounted | ЖИВА НОВОМУ |
| `_kind_is_stock_scoped` | 14 | z12:`stock_question_engaged`; тест | ЖИВА НОВОМУ |
| `_catalogs_are_warehouse_axis` | 15 | z12:`_catalogs_for_warehouse_axis_word` | ЖИВА НОВОМУ |
| `_catalogs_for_warehouse_axis_word` | 13 | z12 resolved/mentions | ЖИВА НОВОМУ |
| `_question_dictionary_axis_candidates` | 27 | z12 resolved warehouse/unaccounted | ЖИВА НОВОМУ |
| `resolved_warehouse_axis_word` | 11 | z12; **z21:`_wiki_axis_has_carriers`:265** (`globals().get`); тесты | ЖИВА НОВОМУ |
| `_catalogs_joint_with_kind` | 26 | — | МЁРТВА |
| `_word_names_documentjournal` | 17 | z12:`resolved_unaccounted_slice_axis_word` | ЖИВА НОВОМУ |
| `resolved_unaccounted_slice_axis_word` | 32 | **z21:`wiki_leader_post_verify`:1058** (`globals().get`); тесты | ЖИВА НОВОМУ |
| `intent_axis_words` | 19 | z12; **z21:`wiki_axis_phrase`:238–242**; тесты | ЖИВА НОВОМУ |
| `state_path_active` | 3 | z12 routing | ЖИВА НОВОМУ |
| `aggregate_count_intent` | 16 | z12 count/skips/subject | ЖИВА НОВОМУ |
| `secondary_axis_known` | 11 | z12 count/skips/subject; тест | ЖИВА НОВОМУ |
| `balance_axis_registers_confirmed` | 10 | z12:`balance_routing_core` | ЖИВА НОВОМУ |
| `balance_routing_core` | 16 | **z11:`sales_sum_intent`:72**; z11:`catalog_kind_total_question`:352 (`globals().get`); z12 | ЖИВА НОВОМУ |
| `_stock_intent_signal` | 10 | z12:`stock_question_engaged` | ЖИВА НОВОМУ |
| `balance_path_engaged` | 5 | z12 count/asks/product; тесты | ЖИВА НОВОМУ |
| `question_asks_stock_balance` | 3 | только тесты (`test_rank_axis_anchor`, `test_k4_*`) | МЁРТВА |
| `question_mentions_warehouse_axis` | 7 | z12; z13 fork; z11 catalog_kind (`globals().get`); тест | ЖИВА НОВОМУ |
| `question_has_aggregate_total_marker` | 5 | z12; **legacy z20:`answer`:2358** | ЖИВА НОВОМУ |
| `question_wants_per_axis_breakdown` | 3 | z12; **legacy z20:`answer`:2359**; тест | ЖИВА НОВОМУ |
| `stock_question_engaged` | 22 | **z02:`question_expects_accounting_data`:388**; z11/z13/z16; **legacy z20:2357,3859**; z12 мёртвые фильтры; тесты | ЖИВА НОВОМУ |
| `registers_for_kind_axes` | 30 | z12; **z21:272,773** (`globals().get` / validate); комментарий z21:229; тест | ЖИВА НОВОМУ |
| `axis_catalog_values` | 78 | z12:`warehouse_axis_values` (+ мёртвый breakdown); тесты | ЖИВА ТОЛЬКО LEGACY |
| `warehouse_axis_values` | 11 | **z13:`fork_outcome_c`/opts:598,732**; legacy `warehouse_clarify`:1652 (сама `warehouse_clarify` с прод-пути не зовётся — только тесты); мёртвый breakdown | ЖИВА ТОЛЬКО LEGACY |
| `warehouse_axis_is_live` | 7 | только мёртвый `stock_breakdown_leader_fallback` | МЁРТВА |
| `stock_skips_warehouse_clarify` | 13 | **z13:`fork_outcome_c`:719**; тест | ЖИВА ТОЛЬКО LEGACY |
| `stock_count_aggregate_without_subject` | 31 | **новый z20:`answer`:2157**; legacy:3849; `_bootstrap` патч-строки (только legacy); z12 subject; тесты | ЖИВА НОВОМУ |
| `stock_subject_needs_clarify` | 12 | только тесты | МЁРТВА |
| `grain_dec_from_axis_ticket` | 7 | **новый z20:`_settle_axis`:1570**; legacy:`answer`:3645; тесты | ЖИВА НОВОМУ |
| `_rank_wants_quantity` | 13 | **legacy z20:`answer`:3339**; мёртвый `rank_measure_hint`; тесты | ЖИВА ТОЛЬКО LEGACY |
| `rank_measure_hint` | 15 | legacy — **только комментарии** :3313,:3666; живых вызовов нет; тесты | МЁРТВА |
| `balance_registers` | 14 | z12:`balance_capable_or_registers`; z04 — **только docstring** (:15,:179), не вызов; тесты | ЖИВА НОВОМУ |
| `balance_map_rows` | 24 | z12 capable / мёртвый `_balance_map_by_src`; тесты | ЖИВА НОВОМУ |
| `balance_capable_sources` | 3 | z12; z13 fork label (legacy-цепь); тесты | ЖИВА НОВОМУ |
| `balance_capable_or_registers` | 6 | z12 net/eligible/… | ЖИВА НОВОМУ |
| `register_is_balance_noise` | 3 | z12 | ЖИВА НОВОМУ |
| `stock_balance_is_reversal_noise` | 5 | z12 | ЖИВА НОВОМУ |
| `_is_product_catalog_target` | 5 | z12; тесты | ЖИВА НОВОМУ |
| `_stock_registers_with_product_axis` | 20 | z12 net/goods | ЖИВА НОВОМУ |
| `_stock_product_targets_by_src` | 19 | z12 sort/net | ЖИВА НОВОМУ |
| `_stock_refs_by_src` | 17 | z12:`_sort_stock_pool` | ЖИВА НОВОМУ |
| `_stock_cost_side_penalty` | 13 | z12 rank (+ мёртвый `_stock_expense_side_penalty`) | ЖИВА НОВОМУ |
| `_stock_corpus_receipt_side_penalty` | 12 | z12:`_stock_register_rank_key` | ЖИВА НОВОМУ |
| `_stock_expense_side_penalty` | 3 | — (никто не зовёт) | МЁРТВА |
| `stock_goods_pool` | 19 | только мёртвые stock_canon/prefer/filter/breakdown; тесты | МЁРТВА |
| `filter_stock_goods_registers` | 15 | только тесты (`test_final_stock_route_filters_absent` — замок «отсутствует в тракте») | МЁРТВА |
| `_stock_corpus_counts` | 11 | z12 sort/net | ЖИВА НОВОМУ |
| `_stock_register_rank_key` | 13 | z12 sort (+ мёртвый resolve breakdown) | ЖИВА НОВОМУ |
| `_sort_stock_pool` | 9 | z12:`stock_net_register_pair` (+ мёртвый canon) | ЖИВА НОВОМУ |
| `_stock_product_axis_col` | 15 | z12:`stock_net_register_pair` | ЖИВА НОВОМУ |
| `_stock_qty_measure_name` | 19 | z12:`stock_net_register_pair` | ЖИВА НОВОМУ |
| `stock_net_register_pair` | 50 | z12:`aggregate_stock_net_distinct`; тест | ЖИВА НОВОМУ |
| `aggregate_stock_net_distinct` | 49 | **новый z20:`answer`:2159**; legacy:3850; `_bootstrap` патч (legacy); `test_one_path`, `test_stock_balance_path` | ЖИВА НОВОМУ |
| `stock_canon_src` | 13 | мёртвый `prefer_entity_for_stock`; тесты/моки wiki | МЁРТВА |
| `prefer_entity_for_stock` | 15 | только тесты (`test_final_stock_route_filters_absent`) | МЁРТВА |
| `_stems_of_text` | 16 | z12:`stock_asks_named_product` | ЖИВА НОВОМУ |
| `_stock_scaffold_stems` | 12 | z12:`stock_asks_named_product` | ЖИВА НОВОМУ |
| `stock_asks_named_product` | 28 | z12:`stock_count_aggregate_without_subject` (→ новый); `_bootstrap` патч-строки (legacy); тесты | ЖИВА НОВОМУ |
| `_resolve_breakdown_balance_src` | 20 | только мёртвый `stock_breakdown_leader_fallback` | МЁРТВА |
| `_breakdown_fallback_measure` | 19 | только мёртвый breakdown | МЁРТВА |
| `stock_breakdown_leader_fallback` | 54 | только тесты (`test_no_pre_wiki_reorders`, `test_warehouse_aggregate_breakdown`) | МЁРТВА |
| `_balance_map_by_src` | 7 | только мёртвый `filter_balance_structural` | МЁРТВА |
| `filter_balance_structural` | 40 | только тест `test_stock_balance_path` | МЁРТВА |
| `balance_bridge_clarify` | 34 | только тесты (`test_k4_meta_names`, `test_stock_balance_path`) | МЁРТВА |

---

## Транзитивные цепочки до z20

### Прямо из нового `z20_ask_main_http.py`

```
grain_dec_from_axis_ticket
  ← z20:_settle_axis:1570 ← answer

stock_count_aggregate_without_subject
  ← z20:answer:2157
  → (внутри) balance_path_engaged, stock_asks_named_product, secondary_axis_known,
     question_mentions_warehouse_axis, aggregate_count_intent, …

aggregate_stock_net_distinct
  ← z20:answer:2159
  → stock_net_register_pair → _sort_stock_pool / _stock_qty_measure_name /
     _stock_product_axis_col / registers_for_kind_axes / balance_capable_or_registers …
```

### Транзитивно в новый через другие зоны

```
intent_axis_words
  ← z21:wiki_axis_phrase ← … ← wiki_primary_entity_cascade
  ← z20:answer:1951

registers_for_kind_axes
  ← z21:_wiki_axis_has_carriers / wiki_validate_leader_axes
  ← … ← wiki_primary_entity_cascade ← z20:answer:1951

resolved_warehouse_axis_word
  ← z21:_wiki_axis_has_carriers:265 (getattr-стиль globals().get)
  ← … ← z20:answer:1951

resolved_unaccounted_slice_axis_word
  ← z21:wiki_leader_post_verify:1058
  ← try_wiki_hybrid_entity_pick ← wiki_primary_entity_cascade ← z20:answer:1951

stock_question_engaged
  ← z02:question_expects_accounting_data:388
  ← _enrich_conversational_business ← parse_intent ← z20:answer:1873

balance_routing_core
  ← z11:sales_sum_intent:72
  ← _zero_period_not_missing (и др.) ← z20:answer:2134/2150
```

### Только legacy

```
warehouse_axis_values (+ axis_catalog_values)
  ← z13:_fork_clarify_opts / fork_outcome_c
  ← legacy z20:answer:3023
  (legacy warehouse_clarify:1652 зовёт warehouse_axis_values, но warehouse_clarify
   с прод-пути не вызывается — только тесты)

stock_skips_warehouse_clarify
  ← z13:fork_outcome_c:719 ← legacy z20:answer:3023

_rank_wants_quantity
  ← legacy z20:answer:3339

question_has_aggregate_total_marker / question_wants_per_axis_breakdown
  ← legacy z20:answer:2358–2359  (для нового уже покрыты через stock_question_engaged)

stock_question_engaged / stock_count / aggregate_stock_net / grain_dec
  ← также legacy answer (дублируют новый)

_bootstrap._patch_z20_wiki_primary
  ← строки stock_count / aggregate_stock_net / stock_asks_named_product
  ← применяются только при загрузке legacy z20
```

### Ложные/пустые «связи»

| Упоминание | Почему не цепочка |
|---|---|
| `balance_registers` в z04 docstring | текст «как balance_registers», не вызов |
| `rank_measure_hint` в legacy | комментарии о сносе; вызовов нет |
| `filter_stock_balance_sales_noise` (z13) | сама ниоткуда не зовётся (мёртвая обёртка над `stock_question_engaged`) |
| `warehouse_clarify` (в legacy файле) | определение есть; прод-вызовов нет |

---

## Скрытые выбиратели, доступные новому тракту

Через прямые и транзитивные вызовы новый тракт **получает** кодовый выбор источника/оси/меры (не wiki-меню человека):

| Выбиратель | Что выбирает кодом | Как попадает в новый |
|---|---|---|
| `resolved_warehouse_axis_word` | слово оси места | z21 wiki carriers |
| `resolved_unaccounted_slice_axis_word` | ось «неучтённого» среза | z21 post_verify |
| `intent_axis_words` | набор осей из intent | z21 wiki_axis_phrase + routing |
| `registers_for_kind_axes` | какие регистры под оси | z21 + `stock_net_register_pair` |
| `_catalogs_for_*` / `_stock_place_axis_catalogs` / `_catalog_on_stock_eligible_register` | каталоги-оси по метаданным | замыкание осей |
| `balance_routing_core` / `balance_path_engaged` / `stock_question_engaged` | остатковый vs иной маршрут | sales_sum / parse_intent / count |
| `stock_net_register_pair` | пара приход/расход + product col | `aggregate_stock_net_distinct` ← z20 |
| `_sort_stock_pool` / `_stock_register_rank_key` (+ cost/receipt penalties) | ранжирование регистров | net pair |
| `_stock_qty_measure_name` | имя меры количества | net pair |
| `_stock_product_axis_col` | колонка товарной оси | net pair |
| `aggregate_stock_net_distinct` | путь net-distinct агрегата вместо обычного | z20:answer напрямую |
| `grain_dec_from_axis_ticket` | grain из уже выбранного axis-ticket | z20:`_settle_axis` |
| `stock_asks_named_product` | гейт «названный товар» (стемы) | внутри `stock_count_…` ← z20 |

**Не тащатся в новый** (legacy-only или мёртвые выбиратели): `axis_catalog_values` / `warehouse_axis_values` (меню складов), `stock_skips_warehouse_clarify`, `_rank_wants_quantity` / мёртвый `rank_measure_hint`, `stock_canon_src` / `prefer_entity_for_stock` / `filter_stock_goods_registers` / `stock_breakdown_leader_fallback` / `filter_balance_structural` / `balance_bridge_clarify`.

---

## Замки (тесты), трогающие зону

| Тест | Что фиксирует |
|---|---|
| `test_stock_balance_path.py` | кэш, net-pair, canon/pool, place-axis, structural |
| `test_one_path.py` | имя `aggregate_stock_net_distinct` в списке |
| `test_final_stock_route_filters_absent.py` | `filter_stock_goods_registers` / `prefer_entity_for_stock` **отсутствуют** в тракте |
| `test_no_pre_wiki_reorders.py` | `stock_breakdown_leader_fallback` в запрещённых pre-wiki |
| `test_warehouse_aggregate_breakdown.py` | skips/breakdown/axis values |
| `test_warehouse_axis_autonomy.py` | axis catalogs / warehouse_clarify |
| `test_fork_outcomes.py` | `warehouse_axis_values` |
| `test_rank_axis_anchor.py` | grain_dec / rank_measure / asks_stock |
| `test_wiki_candidate_verify.py` / `test_wiki_card_hybrid.py` | z21 ↔ resolved/intent/registers |
| `test_k4_*` | asks/subject/bridge/warehouse_clarify |
| `test_calendar_meta_build.py` | упоминание `balance_registers` в SQL-строке |

---

## Краткая рекомендация для этапа-2

1. **Оставлять** для одного пути: net-distinct + grain ticket + wiki-оси (`resolved_*`, `intent_axis_words`, `registers_for_kind_axes`) + routing/`stock_question_engaged` и их замыкание (~777 строк).
2. **Не тащить** в новый без нужды: legacy fork-склад (`warehouse_axis_values`/`axis_catalog_values`/`stock_skips_warehouse_clarify`) и `_rank_wants_quantity`.
3. **Кандидаты на снос после flip:** 16 мёртвых символов (302 строки), особенно бывшие pre-wiki reorder/filters (`stock_breakdown_*`, `prefer_entity_for_stock`, `filter_stock_goods_registers`, `filter_balance_structural`, `balance_bridge_clarify`, `stock_canon_src`, `stock_goods_pool`).
4. **Риск скрытых выбирателей:** новый тракт уже исполняет кодовый выбор регистра/меры/оси через `stock_net_register_pair` и wiki-resolved оси — это S-класс для сверки с приказом «варианты из вики, выбор человека».
