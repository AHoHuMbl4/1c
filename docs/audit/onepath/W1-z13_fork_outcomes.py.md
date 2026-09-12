# W1 — карта живости `ask/z13_fork_outcomes.py`

Дата: 12.09.2026. Зона: `ubuntu/serenedb/ask/z13_fork_outcomes.py` (925 строк файла; 839 строк в определениях верхнего уровня).
Метод: AST top-level + grep по голым именам в `ask/z*.py`, `_bootstrap.py`, `_imports.py`, `_wire.py`, `ubuntu/serenedb/test_*.py`; getattr/строковый диспетч по именам зоны в новом/legacy z20 — **не найден**. Импорт-структуры нет — только фактические вызовы из общего namespace.

**Итог зоны:** одному пути нужна **тонкая щель** (21 строка: `atom_terminal_gate_text` + `stock_balance_is_sales_noise`). Основной fork-тракт A/B/C (744 строки) жив **только legacy**. После flip и сноса legacy — мёртв, кроме двух символов нового и замков. Скрытый выбиратель источника по подстрокам имени **тащится в новый** через z12.

| Вердикт | Строк определений | Символов |
|---|---:|---:|
| ЖИВА НОВОМУ | 21 | 2 |
| ЖИВА ТОЛЬКО LEGACY | 744 | 28 |
| МЁРТВА | 74 | 7 |
| **Всего в def/const** | **839** | **37** |
| Прочее в файле (шапка, пустые, `register_zone`) | 86 | — |

---

## Таблица символов

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `stock_balance_is_sales_noise` | 10 | **зоны:** `z12_stock_balance.py:734` (`register_is_balance_noise`), `:904` (`_stock_register_rank_key`), `:992,:996` (`stock_net_register_pair`); внутри зоны: `filter_stock_balance_sales_noise:25`. **новый z20:** нет прямо; транзитивно через z12 (см. цепочки). **legacy:** тот же z12. **тесты:** `test_rank_axis_anchor.py:73`, `test_stock_balance_path.py:329,331,333`. **wire:** нет | **ЖИВА НОВОМУ** (транзитивно) |
| `filter_stock_balance_sales_noise` | 8 | только тесты: `test_final_stock_route_filters_absent.py` (замок «orphan … lives in tree»), `test_stock_balance_path.py:334`. Никто в ask/ не зовёт | **МЁРТВА** |
| `_dedupe_fork_classes` | 22 | только внутри зоны: `_fork_resolve_partial_b:252`, `resolve_fork_outcome:337` | **ЖИВА ТОЛЬКО LEGACY** (через `resolve_fork_outcome`) |
| `FORK_OTHER_READING` | 1 | внутри: `fork_outcome_c:683` (+ коммент `:648`). тесты: `test_action_class.py:188`, `test_calendar_axis.py:242-243`, `test_fork_label_daybasis.py:137-138`, `test_leader_hatch.py:6,64`, `test_measure_hatch_luk.py:38` (замок «0 в z20») | **ЖИВА ТОЛЬКО LEGACY** |
| `_class_window_form` | 7 | внутри: `fork_leader_class:106`. тест: `test_fork_window_readings.py:285` | **ЖИВА ТОЛЬКО LEGACY** |
| `_class_day_basis` | 8 | внутри: `fork_leader_class`, `_fork_clarify_axis_kind`, `_fork_axis_option_label`, `_fork_clarify_opts`. тесты: `test_calendar_axis.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_leader_class` | 56 | внутри: `fork_outcome_c:660,720`. тесты: `test_calendar_axis.py`, `test_fork_outcomes.py`, `test_fork_window_readings.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_classes_window_only` | 7 | внутри: `rank_defer_fork_outcome_b:148`. тесты: `test_rank_leader_path.py:216-219` | **ЖИВА ТОЛЬКО LEGACY** |
| `rank_defer_fork_outcome_b` | 4 | **legacy** `z20_ask_main_http_legacy.py:3001`. тесты: `test_rank_leader_path.py:220-225`. новый — нет | **ЖИВА ТОЛЬКО LEGACY** |
| `ordered_fork_classes` | 19 | внутри: `resolve_fork_outcome:301`, `fork_outcome_c:659,698`. тесты: `test_fork_outcomes.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_applicable_classes` | 4 | внутри: `resolve_fork_outcome:303`, `fork_outcome_c:658` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_class_is_uncounted` | 5 | внутри: `_fork_class_axis_unavailable:187`, `resolve_fork_outcome:307` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_class_axis_unavailable` | 15 | внутри: `_fork_resolve_partial_b:236` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_window_label_fallback` | 4 | внутри: `_fork_day_basis_branch_label:223` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_day_basis_branch_label` | 17 | внутри: `_fork_resolve_partial_b:240`, `_fork_axis_option_label:580` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_resolve_partial_b` | 35 | внутри: `resolve_fork_outcome:310` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_complement_outcome_block` | 20 | внутри: `resolve_fork_outcome:319` | **ЖИВА ТОЛЬКО LEGACY** |
| `resolve_fork_outcome` | 59 | **legacy** `:2970`. тесты: `test_fork_outcomes.py`, `test_fork_detector.py`, `test_calendar_axis.py`, `test_currency_axis.py`, `test_action_class.py`, `test_atom_terminal.py`, `test_fork_label_daybasis.py`, `test_leader_hatch.py`, … Новый z20 — **нет** | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_figures_of` | 24 | **legacy** `:3759`; зоны: `z05_entity_form.py:1204` (`try_entity_form_answer` — только legacy z20), `z12_stock_balance.py:1250` (`stock_breakdown_leader_fallback` — только тесты, не z20). тесты: `test_compare_sales.py`. Новый — нет | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_outcome_a` | 3 | stub `return None`. тесты: `test_action_class.py`, `test_fork_outcomes.py`, `test_leader_hatch.py`, `test_one_path.py:46` (имя в списке запретов). Runtime ask — нет | **МЁРТВА** |
| `fork_outcome_unique` | 3 | stub. тесты: `test_atom_terminal.py`. Runtime — нет | **МЁРТВА** |
| `_rivals_figures_empty` | 19 | **нигде** вне определения | **МЁРТВА** |
| `prefer_mute_computed_over_clarify` | 4 | stub `return None`. тесты: `test_atom_terminal.py`, `test_leader_hatch.py`. Runtime — нет | **МЁРТВА** |
| `atom_terminal_gate_text` | 11 | **новый** `z20_ask_main_http.py:1807` (из `_onepath_compose_gate`); **legacy** `:4281`. тесты: `test_atom_terminal.py:168,183` | **ЖИВА НОВОМУ** |
| `fork_outcome_b` | 4 | stub `return None`. legacy только **комментарий** `:2914`. тесты: множество + `test_one_path.py:45`. Runtime-вызова нет | **МЁРТВА** |
| `_fork_question_cyrillic` | 2 | внутри: `_fork_human_measure_label`, `_fork_human_place_label` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_applicable_ordered` | 3 | внутри: `_fork_clarify_axis_kind`, `_fork_clarify_opts` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_clarify_axis_kind` | 47 | внутри: `fork_outcome_c:717`. тесты: `test_fork_detector.py`, `test_fork_outcomes.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_human_measure_label` | 29 | внутри: `_fork_axis_option_label:574` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_place_axis_label_from_items` | 38 | внутри: `_fork_human_place_label:561` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_human_place_label` | 6 | внутри: `_fork_axis_option_label:576`. тесты: `test_fork_outcomes.py:301,303` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_axis_option_label` | 23 | внутри: `_fork_clarify_opts:617` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_clarify_opts` | 46 | внутри: `fork_outcome_c:752`. тесты: `test_fork_outcomes.py`, `test_fork_atom_aggregate.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_outcome_c` | 177 | **legacy** `:3023`. тесты: `test_action_class`, `test_calendar_axis`, `test_currency_axis`, `test_fork_label_daybasis`, `test_fork_outcomes`, `test_leader_hatch`, коммент в `test_wiki_leader_not_overridden`. Новый — нет | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_clarify_from_wiki_pool` | 48 | **legacy** `:3012`; внутри: `resolve_fork_wiki_gate:913` (сам gate мёртв для runtime). тесты: `test_wiki_leader_not_overridden.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `fork_c_options_without_left_srcs` | 18 | **legacy** `:3032`. тесты: `test_wiki_leader_not_overridden.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `resolve_fork_wiki_gate` | 33 | только тесты: `test_fork_outcomes.py`, `test_wiki_leader_not_overridden.py`. Legacy встроил ту же логику inline (`wiki_leader_alive` + `fork_clarify_from_wiki_pool`), функцию не зовёт. Новый — нет | **МЁРТВА** (для runtime; жива замкам) |

### Wire / bootstrap

| Файл | Упоминание зоны |
|---|---|
| `_bootstrap.py:36` | строка `"z13_fork_outcomes.py"` в списке загрузки зон (exec в общий namespace) |
| `_imports.py` | символов зоны нет |
| `_wire.py` | символов зоны нет; зона сама зовёт `register_zone('ask.z13_fork_outcomes', …)` в конце файла |

getattr / f-строки / словари с именами символов зоны в новом и legacy z20: **не обнаружены** (кроме комментария с `fork_outcome_b` в legacy).

---

## Транзитивные цепочки

### К новому z20 (`z20_ask_main_http.py`)

1. `atom_terminal_gate_text` ← `_onepath_compose_gate` ← `answer` (новый z20:1807)
2. `stock_balance_is_sales_noise` ← `stock_net_register_pair` ← `aggregate_stock_net_distinct` ← новый z20:2159  
   (короткий путь; есть параллельные через `_stock_register_rank_key` / `register_is_balance_noise` ← `_stock_eligible_product_registers` ← … ← `aggregate_stock_net_distinct` / `stock_count_aggregate_without_subject` ← новый:2157–2159)

Других путей из нового z20 в символы z13 **нет** (в т.ч. нет `resolve_fork_outcome` / `fork_outcome_*` / wiki-fork меню).

### К legacy z20 (`z20_ask_main_http_legacy.py`)

1. `resolve_fork_outcome` ← `answer` legacy:2970  
   → `_dedupe_fork_classes`, `ordered_fork_classes`, `_fork_applicable_classes`, `_fork_class_is_uncounted`, `_fork_resolve_partial_b` → (`_fork_class_axis_unavailable`, `_fork_day_basis_branch_label` → `_fork_window_label_fallback`), `_fork_complement_outcome_block`
2. `rank_defer_fork_outcome_b` ← legacy:3001 → `fork_classes_window_only`
3. `fork_clarify_from_wiki_pool` ← legacy:3012
4. `fork_outcome_c` ← legacy:3023  
   → `FORK_OTHER_READING`, `ordered_fork_classes`, `_fork_applicable_classes`, `fork_leader_class` → (`_class_window_form`, `_class_day_basis`), `_fork_clarify_axis_kind` → `_fork_applicable_ordered`, `_fork_clarify_opts` → (`_fork_axis_option_label` → `_fork_human_measure_label` / `_fork_human_place_label` → `_fork_place_axis_label_from_items`, `_fork_question_cyrillic`, `_fork_day_basis_branch_label`)
5. `fork_c_options_without_left_srcs` ← legacy:3032
6. `_fork_figures_of` ← legacy:3759; также ← `try_entity_form_answer` (`z05:1204`) ← legacy (новый `try_entity_form_answer` не зовёт)
7. `atom_terminal_gate_text` ← legacy:4281
8. `stock_balance_is_sales_noise` ← z12 ← те же stock-корни, что и у legacy

`fork_outcome_b` в legacy **не зовётся** (только комментарий) → **МЁРТВА**.

---

## Скрытые выбиратели, доступные НОВОМУ тракту

| Символ | Что выбирает кодом | В новом? |
|---|---|---|
| `stock_balance_is_sales_noise` | отсев src по подстрокам имени (`книгапродаж`, `актсверки`/`reconciliation`, `реализац`+`accumulationregister_`) | **ДА** — через z12 / `aggregate_stock_net_distinct` |
| `filter_stock_balance_sales_noise` | обёртка-фильтр кандидатов тем же правилом | **НЕТ** (мертва; замок orphan) |
| `fork_leader_class` | лидер среди классов по осям W / day_basis / amount_basis | нет (только legacy через C) |
| `_fork_clarify_axis_kind` | ось clarify: measure / place / period | нет |
| `_fork_clarify_opts` / `_fork_human_*` | подписи и варианты меню по оси | нет |
| `rank_defer_fork_outcome_b` | отложить исход B при rank+только-окна | нет |
| `resolve_fork_outcome` | исход A/B/C/unique/empty | нет |

**Вывод по выбирателям:** в новый тракт из z13 протаскивается **один** скрытый выбиратель источника — `stock_balance_is_sales_noise`. Вся развилка исходов и меню по осям в новый **не** входит.

---

## Вердикт по зоне

- **Нужна одному пути — частично (21/839 строк определений).** Прямо: форматтер отказа гейта. Транзитивно: шумовой отсев «продажных» регистров для stock-net.
- **До flip** основная масса зоны обязана legacy (детектор исходов + меню C + wiki_pool clarify).
- **После flip и сноса legacy** без переноса вызовов в onepath: ~744 строки fork-логики станут мёртвыми; останутся 21 строка нового + 74 уже мёртвых stubs/orphan + замки тестов.
- Stubs В4 (`fork_outcome_a/b/unique`, `prefer_mute_…`) и `resolve_fork_wiki_gate` уже **не** на hot-path ни нового, ни legacy (gate продублирован inline в legacy).
