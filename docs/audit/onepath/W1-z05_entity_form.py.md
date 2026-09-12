# W1 — карта живости `z05_entity_form.py`

Зона: `ubuntu/serenedb/ask/z05_entity_form.py` (файл **1239** строк; сумма span определений верхнего уровня **1131**).

## Метод

1. Символы — AST top-level (`def` / константы-`Assign`); строки = span определения.
2. Упоминания — grep по границам слова: все `ask/z*.py`, `_bootstrap.py`, `_imports.py`, `_wire.py`, `ubuntu/serenedb/test_*.py`.
3. Граф вызовов — только `Call(Name)` и `getattr(..., "лит")`; старт `answer`/`main` **раздельно** для нового и legacy z20 (иначе тела `answer` сливаются в один граф).
4. Bootstrap: `ASK_ONEPATH=1` → грузится `z20_ask_main_http.py`; runtime-патч с `try_entity_form_answer` / `try_event_count_period_clarify` — **только legacy**.
5. `_imports.py` / `_wire.py` — символов z05 не упоминают.

## Итог зоны

| Вердикт | Строк | Символов |
|---|---:|---:|
| ЖИВА НОВОМУ | **506** | 19 |
| ЖИВА ТОЛЬКО LEGACY | **517** | 22 |
| МЁРТВА | **108** | 5 |
| Всего | 1131 | 46 |

**Зона нужна одному пути частично.** Прямо из нового `answer` зовутся compare/ось/agg/period; весь терминал «форма сущности» и event-period-clarify — только legacy (и уйдут после flip+сноса legacy).

## Таблица символов

| Символ | Строки | Span | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|---|
| `_RANK_SUPERLATIVE` | 3 | 10–12 | internal← sales_compare_intent | ЖИВА НОВОМУ (internal) |
| `entity_form_rank_single_window` | 28 | 15–42 | internal← sales_compare_intent, sales_compare_windows | ЖИВА НОВОМУ (транзитивно) |
| `_MONTH_NAME_FORMS` | 14 | 46–59 | internal← _months_mentioned | ЖИВА НОВОМУ (internal) |
| `_months_mentioned` | 19 | 62–80 | zone: z11_sales.py:43, z11_sales.py:58<br>internal← sales_compare_intent, sales_compare_split_month_pair | ЖИВА НОВОМУ (транзитивно) |
| `_yoy_compare_marker` | 6 | 83–88 | legacy: z20_ask_main_http_legacy.py:1765<br>test: test_compare_sales.py:183<br>internal← sales_compare_intent, sales_compare_windows | ЖИВА НОВОМУ (транзитивно) |
| `_shift_date_years` | 6 | 91–96 | internal← _shift_period_years | ЖИВА НОВОМУ (транзитивно) |
| `_shift_period_years` | 11 | 99–109 | internal← sales_compare_windows | ЖИВА НОВОМУ (транзитивно) |
| `sales_compare_split_month_pair` | 22 | 112–133 | test: test_compare_sales.py:190<br>internal← sales_compare_windows | ЖИВА НОВОМУ (транзитивно) |
| `sales_compare_intent` | 67 | 136–202 | new: z20_ask_main_http.py:1997<br>legacy: z20_ask_main_http_legacy.py:2890, z20_ask_main_http_legacy.py:3730<br>zone: z11_sales.py:45, z11_sales.py:156, z10_rank.py:423<br>test: test_compare_sales.py:46, test_compare_sales.py:47, test_compare_sales.py:60, test_compare_sales.py:61, test_compare_sales.py:169, test_compare_sales.py:174 (+16) | ЖИВА НОВОМУ (прямо) |
| `sales_compare_windows` | 85 | 205–289 | new: z20_ask_main_http.py:1999<br>legacy: z20_ask_main_http_legacy.py:3731, z20_ask_main_http_legacy.py:3746<br>test: test_compare_sales.py:48, test_compare_sales.py:63, test_compare_sales.py:109, test_compare_sales.py:120, test_compare_sales.py:128, test_compare_sales.py:198 (+13) | ЖИВА НОВОМУ (прямо) |
| `entity_form_catalogs_for_kind` | 43 | 293–335 | zone: z11_sales.py:365, z02_intent.py:409, z12_stock_balance.py:30, z12_stock_balance.py:482, z12_stock_balance.py:615, z21_wiki_choice.py:1027<br>test: test_fork_outcomes.py:273, test_fork_outcomes.py:274, test_fork_outcomes.py:280, test_entity_form.py:340, test_entity_form.py:342, test_entity_form.py:355 (+41)<br>internal← _pick_kind_axis_col, entity_form_expand_pool, entity_form_structs, event_kind_catalog_expand_pool, try_event_count_period_clarify | ЖИВА НОВОМУ (транзитивно) |
| `entity_form_movements_for_kind` | 38 | 338–375 | zone: z10_rank.py:367, z02_intent.py:411<br>test: test_entity_form.py:407, test_entity_form.py:416, test_entity_form.py:436, test_entity_form.py:466, test_entity_form.py:468, test_entity_form.py:479<br>internal← entity_form_count_target_is_movement, register_count_src | ЖИВА НОВОМУ (транзитивно) |
| `register_count_src` | 37 | 378–414 | zone: z11_sales.py:257, z10_rank.py:359<br>test: test_entity_form.py:465, test_entity_form.py:473, test_entity_form.py:474, test_entity_form.py:476, test_wiki_card_hybrid.py:279 | МЁРТВА (тесты/infra) |
| `entity_form_count_target_is_movement` | 36 | 417–452 | zone: z11_sales.py:254, z10_rank.py:356<br>test: test_entity_form.py:467, test_entity_form.py:470, test_entity_form.py:480<br>internal← entity_form_applicable, register_count_src | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_expand_pool` | 21 | 455–475 | zone: z09_fork_detector.py:68<br>test: test_entity_form.py:190, test_entity_form.py:197, test_entity_form.py:245, test_entity_form.py:338, test_entity_form.py:341, test_entity_form.py:363 (+9)<br>internal← entity_form_applicable, entity_form_structs, try_entity_form_answer | ЖИВА ТОЛЬКО LEGACY |
| `event_kind_catalog_expand_pool` | 41 | 478–518 | test: test_action_class.py:409, test_action_class.py:413, test_action_class.py:416, test_action_class.py:428, test_no_pre_wiki_reorders.py:49, test_no_pre_wiki_reorders.py:50 (+1) | МЁРТВА (тесты/infra) |
| `entity_form_rolling_year` | 11 | 521–531 | internal← entity_form_structs, event_count_period_option_readings, try_event_count_period_clarify | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_gate_open` | 19 | 534–552 | infra: _bootstrap.py:111, _bootstrap.py:114, _bootstrap.py:116, _bootstrap.py:126, _bootstrap.py:153<br>test: test_entity_form.py:263, test_entity_form.py:268, test_one_path.py:73, test_one_path.py:223<br>internal← entity_form_applicable, try_entity_form_answer | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_applicable` | 39 | 555–593 | legacy: z20_ask_main_http_legacy.py:2894<br>zone: z09_fork_detector.py:69<br>test: test_entity_form.py:253, test_entity_form.py:254, test_entity_form.py:307, test_entity_form.py:310, test_entity_form.py:313, test_entity_form.py:316 (+6)<br>internal← entity_form_structs | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_collapse_guard` | 14 | 596–609 | legacy: z20_ask_main_http_legacy.py:2891<br>test: test_entity_form.py:171, test_entity_form.py:175, test_entity_form.py:180 | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_pre_entity_ok` | 15 | 612–626 | test: test_entity_form.py:207<br>internal← try_entity_form_answer | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_atom_distinct` | 11 | 629–639 | test: test_entity_form.py:95, test_entity_form.py:201, test_entity_form.py:413<br>internal← entity_form_compute | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_atom_complement` | 17 | 642–658 | test: test_entity_form.py:109, test_fork_detector.py:283<br>internal← entity_form_compute | ЖИВА ТОЛЬКО LEGACY |
| `_pick_kind_axis_col` | 33 | 663–695 | internal← live_axis_col_for_count | ЖИВА НОВОМУ (транзитивно) |
| `live_axis_col_for_count` | 40 | 698–737 | new: z20_ask_main_http.py:2169<br>legacy: z20_ask_main_http_legacy.py:3819, z20_ask_main_http_legacy.py:3856, z20_ask_main_http_legacy.py:4000<br>zone: z21_wiki_choice.py:235<br>infra: _bootstrap.py:68, _bootstrap.py:84<br>test: test_action_class.py:99, test_action_class.py:105, test_action_class.py:109, test_action_class.py:141, test_action_class.py:142, test_action_class.py:154 (+8)<br>internal← _event_distinct_fork_rows, count_defer_measure_clarify, event_count_has_live_axis, event_duel_applies | ЖИВА НОВОМУ (прямо) |
| `count_defer_measure_clarify` | 17 | 740–756 | new: z20_ask_main_http.py:2019<br>legacy: z20_ask_main_http_legacy.py:3482, z20_ask_main_http_legacy.py:3543<br>test: test_action_class.py:122, test_action_class.py:123, test_action_class.py:129, test_action_class.py:133, test_one_path.py:290 | ЖИВА НОВОМУ (прямо) |
| `event_count_has_explicit_period` | 11 | 759–769 | legacy: z20_ask_main_http_legacy.py:1624, z20_ask_main_http_legacy.py:1630<br>test: test_action_class.py:343, test_action_class.py:344 | ЖИВА ТОЛЬКО LEGACY |
| `event_count_period_unspecified` | 6 | 772–777 | test: test_action_class.py:274, test_action_class.py:275, test_action_class.py:276, test_action_class.py:277, test_action_class.py:278, test_action_class.py:279<br>internal← event_count_period_clarify_applies | ЖИВА ТОЛЬКО LEGACY |
| `event_count_has_live_axis` | 22 | 780–801 | internal← event_count_period_clarify_applies | ЖИВА ТОЛЬКО LEGACY |
| `event_count_period_clarify_applies` | 11 | 804–814 | test: test_action_class.py:285, test_action_class.py:286, test_action_class.py:288, test_action_class.py:289<br>internal← try_event_count_period_clarify | ЖИВА ТОЛЬКО LEGACY |
| `event_count_period_option_readings` | 21 | 817–837 | legacy: z20_ask_main_http_legacy.py:1881<br>zone: z10_rank.py:446<br>test: test_action_class.py:291<br>internal← event_count_period_clarify | ЖИВА ТОЛЬКО LEGACY |
| `event_count_period_clarify` | 24 | 840–863 | infra: _bootstrap.py:121<br>test: test_action_class.py:298<br>internal← try_event_count_period_clarify | ЖИВА ТОЛЬКО LEGACY |
| `try_event_count_period_clarify` | 57 | 866–922 | legacy: z20_ask_main_http_legacy.py:2870, z20_ask_main_http_legacy.py:3474<br>infra: _bootstrap.py:142, _bootstrap.py:148<br>test: test_stock_balance_path.py:423, test_stock_balance_path.py:448, test_one_path.py:39 | ЖИВА ТОЛЬКО LEGACY |
| `apply_proven_period` | 19 | 925–943 | new: z20_ask_main_http.py:1874<br>legacy: z20_ask_main_http_legacy.py:1759 | ЖИВА НОВОМУ (прямо) |
| `event_duel_applies` | 17 | 946–962 | test: test_action_class.py:144, test_action_class.py:145, test_action_class.py:149, test_action_class.py:150 | МЁРТВА (тесты/infra) |
| `_event_distinct_fork_rows` | 28 | 965–992 | zone: z09_fork_detector.py:102<br>test: test_action_class.py:213 | ЖИВА ТОЛЬКО LEGACY |
| `event_path_active` | 2 | 995–996 | legacy: z20_ask_main_http_legacy.py:2772, z20_ask_main_http_legacy.py:2811, z20_ask_main_http_legacy.py:3997<br>zone: z10_rank.py:354, z12_stock_balance.py:357, z12_stock_balance.py:374<br>internal← _event_distinct_fork_rows, entity_form_applicable, entity_form_gate_open, event_count_has_explicit_period, event_count_has_live_axis, event_duel_applies, event_kind_catalog_expand_pool | ЖИВА НОВОМУ (транзитивно) |
| `event_movement_feats` | 2 | 999–1000 | — | МЁРТВА |
| `event_filter_pool` | 3 | 1003–1005 | legacy: z20_ask_main_http_legacy.py:2371, z20_ask_main_http_legacy.py:2773, z20_ask_main_http_legacy.py:2812<br>test: test_stock_balance_path.py:422, test_stock_balance_path.py:445 | ЖИВА ТОЛЬКО LEGACY |
| `aggregate_distinct_axis` | 28 | 1009–1036 | new: z20_ask_main_http.py:1659, z20_ask_main_http.py:2173<br>legacy: z20_ask_main_http_legacy.py:3822, z20_ask_main_http_legacy.py:3868, z20_ask_main_http_legacy.py:4004<br>test: test_action_class.py:92, test_action_class.py:95, test_action_class.py:115, test_action_class.py:197, test_action_class.py:203, test_action_class.py:207 (+8)<br>internal← _event_distinct_fork_rows, entity_form_compute | ЖИВА НОВОМУ (прямо) |
| `entity_form_axis_on_sales` | 30 | 1039–1068 | test: test_entity_form.py:339, test_entity_form.py:344, test_entity_form.py:364, test_entity_form.py:375, test_entity_form.py:379, test_entity_form.py:396 (+3)<br>internal← entity_form_structs | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_structs` | 59 | 1071–1129 | zone: z09_fork_detector.py:72<br>test: test_entity_form.py:191, test_entity_form.py:199, test_entity_form.py:236, test_entity_form.py:247, test_fork_detector.py:270, test_fork_detector.py:276 (+1)<br>internal← entity_form_pick, try_entity_form_answer | ЖИВА ТОЛЬКО LEGACY |
| `entity_form_pick` | 11 | 1132–1142 | test: test_entity_form.py:350, test_entity_form.py:357, test_entity_form.py:387, test_entity_form.py:425 | МЁРТВА (тесты/infra) |
| `entity_form_compute` | 30 | 1145–1174 | zone: z09_fork_detector.py:78<br>test: test_entity_form.py:192, test_entity_form.py:201, test_entity_form.py:248, test_entity_form.py:406, test_entity_form.py:413, test_entity_form.py:435 (+6)<br>internal← try_entity_form_answer | ЖИВА ТОЛЬКО LEGACY |
| `try_entity_form_answer` | 32 | 1177–1208 | legacy: z20_ask_main_http_legacy.py:2876<br>infra: _bootstrap.py:134, _bootstrap.py:161<br>test: test_entity_form.py:216, test_entity_form.py:223, test_entity_form.py:229, test_entity_form.py:240, test_entity_form.py:257, test_entity_form.py:258 (+4) | ЖИВА ТОЛЬКО LEGACY |
| `aggregate_compare_sales` | 25 | 1211–1235 | new: z20_ask_main_http.py:2112<br>legacy: z20_ask_main_http_legacy.py:3734<br>test: test_compare_sales.py:88, test_compare_sales.py:91 | ЖИВА НОВОМУ (прямо) |

## Транзитивные цепочки до z20

### A. Живы новому

```
# прямые из answer@new
sales_compare_intent          ← answer (z20_ask_main_http.py:1997)
sales_compare_windows         ← answer (z20_ask_main_http.py:1999)
aggregate_compare_sales       ← answer (z20_ask_main_http.py:2112)
count_defer_measure_clarify   ← answer (z20_ask_main_http.py:2019)
live_axis_col_for_count       ← answer (z20_ask_main_http.py:2169)
aggregate_distinct_axis       ← answer (z20_ask_main_http.py:1659, 2173)
apply_proven_period           ← answer (z20_ask_main_http.py:1874)

# compare-каскад
_RANK_SUPERLATIVE ← sales_compare_intent ← answer@new
entity_form_rank_single_window ← sales_compare_intent / sales_compare_windows ← answer@new
_MONTH_NAME_FORMS ← _months_mentioned ← sales_compare_* / sales_sum_intent(z11) ← answer@new
_yoy_compare_marker ← sales_compare_* ← answer@new  (также прямо legacy:1765)
_shift_date_years ← _shift_period_years ← sales_compare_windows ← answer@new
sales_compare_split_month_pair ← sales_compare_windows ← answer@new

# ось / kind
_pick_kind_axis_col ← live_axis_col_for_count ← answer@new
                     ← wiki_axis_phrase (z21:235) ← answer@new
entity_form_catalogs_for_kind ← _pick_kind_axis_col
  ← _base_knows_kind_or_measure (z02:409)
  ← _catalogs_for_axis_word / stock_count_aggregate_without_subject (z12)
  ← wiki_leader_carries_axis (z21:1027)
entity_form_movements_for_kind ← _base_knows_kind_or_measure (z02:411) ← answer@new

# event gate (не терминал clarify)
event_path_active ← balance_routing_core / _stock_intent_signal (z12:357,374) ← answer@new
```

### B. Живы только legacy

```
try_entity_form_answer ← answer@legacy:2876
  → entity_form_gate_open / entity_form_pre_entity_ok / entity_form_structs
  → entity_form_expand_pool / entity_form_compute
  → entity_form_atom_distinct / entity_form_atom_complement
entity_form_collapse_guard ← answer@legacy:2891
entity_form_applicable ← answer@legacy:2894
  ← _complement_fork_rows (z09:69) ← fork_* ← answer@legacy
    → entity_form_structs / entity_form_compute / entity_form_expand_pool
    → entity_form_rolling_year / entity_form_axis_on_sales
    → entity_form_count_target_is_movement
try_event_count_period_clarify ← answer@legacy:2870,3474
  → event_count_period_clarify_applies → event_count_period_unspecified
                                      → event_count_has_live_axis
  → event_count_period_clarify → event_count_period_option_readings
                              → entity_form_rolling_year
event_count_has_explicit_period ← answer@legacy:1624,1630
event_count_period_option_readings ← answer@legacy:1881
event_filter_pool ← answer@legacy:2371,2773,2812
_event_distinct_fork_rows ← _fork_enrich_event_rows (z09:102) ← answer@legacy

# bootstrap (только при загрузке legacy):
#   _patch_z20_wiki_primary вставляет try_entity_form_answer /
#   try_event_count_period_clarify / entity_form_gate_open
```

### C. Мёртвые (или только из недостижимых)

```
register_count_src ← sales_canon_intent (z11:257), count_theme_code_pick_applies (z10:359)
  — оба caller НЕ в reach(answer@new) и НЕ в reach(answer@legacy)
event_kind_catalog_expand_pool — только тесты
event_duel_applies — только тесты
entity_form_pick — только тесты (не зовётся из try_entity_form_answer напрямую в графе Call:
  try → structs; pick зовёт structs, но pick сам снаружи мёртв)
event_movement_feats — никто
```

## Скрытые выбиратели, доступные НОВОМУ тракту

Функции зоны, которые **кодом** (не меню wiki-прочтений) выбирают источник / меру / период / ось и достижимы из `answer@new`:

| Символ | Что выбирает кодом | Как попадает в new |
|---|---|---|
| `sales_compare_intent` | Включает ветку compare по маркерам текста (месяцы, YoY, «лучше/больше»+прошл*) | прямо z20:1997 |
| `sales_compare_windows` | Два окна period/period2 (WTD/MTD vs полный prior; YoY shift; month-pair) | прямо z20:1999 |
| `sales_compare_split_month_pair` | Пара календарных месяцев из текста | ← windows |
| `_months_mentioned` / `_MONTH_NAME_FORMS` | Какие месяцы «нашлись» в вопросе | ← compare / sales_sum_intent |
| `_yoy_compare_marker` | Маркер YoY follow-up | ← compare |
| `_shift_period_years` / `_shift_date_years` | Сдвиг окна на год | ← windows |
| `entity_form_rank_single_window` | Гейт: rank/top-N + одно окно → не compare | ← compare |
| `live_axis_col_for_count` | Колонка оси COUNT(DISTINCT) по kind/action_axis | прямо + wiki_axis_phrase |
| `_pick_kind_axis_col` | Какой refcol оси среди кандидатов (rerank) | ← live_axis |
| `entity_form_catalogs_for_kind` | Какие `catalog_*` подходят слову kind | ← axis / intent / wiki / stock |
| `entity_form_movements_for_kind` | Какие document_/accum_* подходят kind | ← intent `_base_knows_*` |
| `count_defer_measure_clarify` | Откладывать ли clarify меры (want/rank/ось) | прямо z20:2019 |
| `event_path_active` | Ветвление по `action_class==event` | ← z12 stock routing |

**Не считаем выбирателями (для этой зоны):** `apply_proven_period` — применяет уже доказанный wiki/trusted period; `aggregate_distinct_axis` / `aggregate_compare_sales` — считают, не выбирают прочтение.

**Итог по выбирателям:** да, зона **тащит скрытые выбиратели в новый тракт** — прежде всего **окна compare** и **ось count** (`live_axis_col_for_count` / `_pick_kind_axis_col`). Это согласуется с замком `test_one_path.py` (B4: `sales_compare_windows` как расчёт окон ок, терминал-return до compose — нет; `count_defer_measure_clarify` обязан зваться).

## Тесты (замки), ссылающиеся на зону

| Тест | Что трогает из z05 |
|---|---|
| `test_compare_sales.py` | `sales_compare_*`, `_yoy_compare_marker`, `aggregate_compare_sales` |
| `test_entity_form.py` | почти весь F-каскад + compare gates |
| `test_action_class.py` | event_count_*, live_axis, count_defer, aggregate_distinct, event_duel, event_kind_catalog |
| `test_rank_leader_path.py` | `sales_compare_intent` / `windows` |
| `test_fork_detector.py` / `test_fork_outcomes.py` | structs/compute/catalogs |
| `test_stock_balance_path.py` | stubs: `try_entity_form_answer`, `try_event_count_period_clarify`, `event_filter_pool` |
| `test_one_path.py` | запрет терминалов `try_entity_form_answer` / `try_event_count_period_clarify`; контроль `sales_compare_windows` / `count_defer` / `entity_form_gate_open` |
| `test_no_pre_wiki_reorders.py` | `event_kind_catalog_expand_pool` |
| `test_wiki_card_hybrid.py` | `register_count_src` |
| `test_warehouse_axis_autonomy.py` | `entity_form_catalogs_for_kind` |

## Краткие выводы для этапа-2

1. **Не сносить зону целиком** при flip: new нуждается в compare + live_axis + catalogs/movements kind + `apply_proven_period` + aggs (~506 строк span).
2. **После сноса legacy** можно выкинуть/изолировать F-терминал и ecp-clarify (~517 строк) + 5 мёртвых символов (~108 строк), если нет внешних замков.
3. **Риск one-path:** скрытые выбиратели периода (compare) и оси (live_axis) уже в new — это не wiki-меню; их судьба — отдельное решение владельца (оставить как расчёт окон/оси vs вынести в readings).

---

Метод зафиксирован; замер графа: `reach(answer@new)=427` имён, `reach(answer@legacy)=561` (Call-only, z20-disambiguated).
