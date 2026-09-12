# W1 — карта живости `ask/z17_aggregate_groups.py`

Дата: 12.09.2026. Метод: AST Call-граф по `ask/*.py` (имена в общем namespace
после `_bootstrap`); new/legacy z20 разобраны **отдельными** корнями (одинаковые
имена функций в двух файлах не смешивались); плюс grep на `getattr`/строковую
передачу имён. Код не менялся.

Файл зоны: 698 строк. Тела 23 определений верхнего уровня: **640** строк.
Обвязка вне тел (docstring модуля, `from ask._imports`, `apply_bindings`,
пустые строки, `register_zone`): 58 строк — в вердикты символов не входит.
Переопределений тех же имён в других `z*.py` **нет** (зона — единственный
владелец всех 23 символов в namespace).

---

## Итог зоны

| Вердикт | Символов | Строк тел |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 17 | **509** |
| **ЖИВА ТОЛЬКО LEGACY** | 6 | **131** |
| **МЁРТВА** | 0 | **0** |
| **Всего определений** | 23 | **640** |

Зона **нужна одному пути**: ядро счёта (`aggregate` / `aggregate_groups`),
осевой settle (`refcols_of`, `kind_axis_hits`, `term_axis_hits`, `src_is_child`)
и служебные `_num`/`_numN`/`_vec` входят в новый `answer`. После flip и сноса
legacy останутся мёртвыми 6 символов (131 строк) — в основном live-count
каталога через fork-атом и holders/measures/term_ref для старого focus-плана.

---

## Таблица символов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---|---|---|
| `_vec` | L9–10 (2) | **new:** транзитивно `answer`→`probe`→`resolve_values` (z06:127 / z07:508). **legacy:** прямо `answer` 2059, 2297. **др. зоны:** `_rrf_entity_branches` z07:72; `_fused_candidates` z07:149; `near_tables` z07:209; `resolve_values` z07:508. **тесты:** `test_sql_rrf`, `test_resolver_ivf`, `test_ai_embed_question`, `test_ask_embed_native`. **boot/imports/wire:** нет | ЖИВА НОВОМУ |
| `_num` | L13–17 (5) | **new:** прямо health/coverage (`_entity_counts_objects` 398/407, `_vitrina_objects` 418/423, `_coverage_of` 450–457, `_measure_health_gap` 579, `_real_corpus_object_gaps` 597, `_coverage_answer` 789/816, module 2894); из `answer`→`_coverage_answer`. **legacy:** те же helper'ы + module 5045. **др.:** `currency_fx_probe` z04b:385–387; `aggregate_distinct_axis` z05:1032; `totals_of` z08:234; `fork_scan` z09:285/289 (только LEG reach); `compose` z18:661–663; `_measure_tick_status` z22:30. **внутри z17:** `aggregate_live_row_count`/`header_count`. **тесты/boot:** нет прямых | ЖИВА НОВОМУ |
| `_numN` | L20–33 (14) | **new:** прямо `_measure_native_index_freshness` 681/687; из `answer`→`aggregate`→`_numN`. **legacy:** `_measure_native_index_freshness` 687/693. **др.:** `fork_scan` z09:307 (LEG). **внутри z17:** `aggregate_live_column`, `aggregate`, `aggregate_groups`. **тесты/boot:** нет | ЖИВА НОВОМУ |
| `_sql_ident_col` | L36–37 (2) | только внутри z17: `_live_std_excl_preds`:82; `aggregate_live_column`:179,195. Жива через `aggregate`←new `answer`:2177 | ЖИВА НОВОМУ |
| `_live_measure_date_col` | L40–56 (17) | только `aggregate_live_column`:172 → `aggregate`←new `answer` | ЖИВА НОВОМУ |
| `_live_column_exists` | L59–69 (11) | `_live_std_excl_preds`:79; `aggregate_live_column`:170 → new через `aggregate` | ЖИВА НОВОМУ |
| `_live_std_excl_preds` | L72–83 (12) | `aggregate_live_row_count`:114; `aggregate_live_header_count`:146; `aggregate_live_column`:193. New-путь: через `aggregate_live_column`←`aggregate` | ЖИВА НОВОМУ |
| `_live_ref_key_col` | L86–99 (14) | только `aggregate_live_header_count`:144 ← `_fork_atom_of` z09:953 ← **только legacy** `answer` (в new z20 `_fork_atom_of` не зовётся) | ЖИВА ТОЛЬКО LEGACY |
| `aggregate_live_row_count` | L102–127 (26) | **др.:** `_fork_atom_of` z09:947,950 — LEG reach only. **тесты:** `test_aggregate_live_flags` 114,117. **new/legacy прямо:** нет | ЖИВА ТОЛЬКО LEGACY |
| `aggregate_live_header_count` | L130–159 (30) | **др.:** `_fork_atom_of` z09:953 — LEG only. **тесты:** `test_aggregate_live_flags` 101,109 | ЖИВА ТОЛЬКО LEGACY |
| `aggregate_live_column` | L162–228 (67) | **внутри:** `aggregate`:320,351. **тесты:** `test_aggregate_live_flags` 67,91. Прямо из z20 нет; new через `aggregate`←`answer`:2177 | ЖИВА НОВОМУ |
| `aggregate` | L231–354 (124) | **new:** `answer`:2177. **legacy:** `answer`:3826,3872. **др.:** `entity_form_compute` z05:1166 (LEG); `aggregate_compare_sales` z05:1215–1216 (NEW+LEG); `stock_breakdown_leader_fallback` z12:1226 (ни new, ни leg reach). **тесты:** `test_fork_atom_aggregate`, `test_compose`, `test_compare_sales`, `test_step4_guards`, `test_stock_balance_path`, `test_warehouse_aggregate_breakdown`, имя в `test_one_path`. **boot:** комментарий `_bootstrap.py`:61 | ЖИВА НОВОМУ |
| `src_is_child` | L358–367 (10) | **new:** `_settle_axis`:1614. **legacy:** `answer`:3237,3626. **тесты/boot:** нет | ЖИВА НОВОМУ |
| `refcols_of` | L370–384 (15) | **new:** `_settle_axis`:1561; `answer`:2015. **legacy:** `answer`:3471,3584,4081. **др.:** z05 (`live_axis_col_for_count`:731 и др.); `rank_axis_resolve` z10:253; `_stock_product_axis_col` z12:930; `_fork_place_axis_label_from_items` z13:538 (LEG). **тесты:** `test_action_class`, `test_compose`, `test_stock_balance_path` | ЖИВА НОВОМУ |
| `holders_of_target` | L387–404 (18) | **legacy прямо:** `axis_focus_plan`:1527; `answer`:2436,2475. **new прямо:** нет. **др.:** z05 expand/clarify/axis_on_sales — caller'ы **не** в NEW reach. **тесты:** `test_action_class`, `test_stock_balance_path` | ЖИВА ТОЛЬКО LEGACY |
| `measures_of_many` | L407–422 (16) | **legacy:** `axis_focus_plan`:1535. **new / др. зоны / тесты:** нет | ЖИВА ТОЛЬКО LEGACY |
| `kind_axis_hits` | L425–466 (42) | **new:** `_settle_axis`:1593. **legacy:** `answer`:3598. **др.:** `_pick_kind_axis_col` z05:688 (NEW через `live_axis_col_for_count`←`answer`:2169); `rank_axis_resolve` z10:267/280/287. **тесты:** `test_action_class`, `test_rank_leader_path` | ЖИВА НОВОМУ |
| `kind_axis_rerank` | L469–492 (24) | **new прямо:** нет; транзитивно `rank_axis_resolve` z10:282 ← `_settle_axis`:1597; также `_pick_kind_axis_col` z05:684/694 ← `live_axis_col_for_count`. **legacy прямо:** `answer`:3618. **тесты:** `test_action_class`, `test_rank_leader_path`; имя в `test_one_path` (список сносимых) | ЖИВА НОВОМУ |
| `term_ref_owners` | L495–521 (27) | **legacy:** `answer`:1903. **new:** нет. **тесты:** `test_stock_balance_path` (mock/имя) | ЖИВА ТОЛЬКО LEGACY |
| `term_axis_hits` | L524–563 (40) | **new:** `_settle_axis`:1606. **legacy:** `answer`:3619. **др./тесты/boot:** нет | ЖИВА НОВОМУ |
| `_group_leader` | L567–576 (10) | **new:** `asked_figure_missing` z19:264 ← `_onepath_compose_gate`:1731/1774 ← `answer`:2240; также `compose_slot_values` / `_atom_exact_value` z15:154/216 (NEW). **др. без reach:** `rank_leader_*` z10:125/320. **legacy:** те же z15/z19 пути. **тесты/boot:** нет | ЖИВА НОВОМУ |
| `_group_fold` | L579–585 (7) | только `aggregate_groups`:627 ← new `answer`:2130 / legacy `answer`:3789 | ЖИВА НОВОМУ |
| `aggregate_groups` | L588–694 (107) | **new:** `answer`:2130. **legacy:** `answer`:3789,3806. **тесты:** SQL-контракт `test_rank_leader_path` 161+; имя в `test_one_path` | ЖИВА НОВОМУ |

`getattr` / передача имени строкой по символам зоны в `ask/*.py` — **не найдено**
(кроме тестовых списков имён в `test_one_path` / `test_stock_balance_path`).

---

## Транзитивные цепочки (к корню тракта)

### ЖИВА НОВОМУ (краткий канон)

```
_vec ← resolve_values@z07 ← probe@z06 ← answer@z20_new
_num ← _coverage_answer@z20_new ← answer@z20_new
     (+ прямо из health/coverage helper'ов new z20)
_numN ← aggregate@z17 ← answer@z20_new
_sql_ident_col / _live_measure_date_col / _live_column_exists / _live_std_excl_preds
     ← aggregate_live_column@z17 ← aggregate@z17 ← answer@z20_new
aggregate_live_column ← aggregate ← answer@z20_new
aggregate ← answer@z20_new:2177
aggregate_groups ← answer@z20_new:2130
_group_fold ← aggregate_groups ← answer@z20_new
src_is_child ← _settle_axis@z20_new:1614 ← answer@z20_new:2043
refcols_of ← _settle_axis:1561 / answer:2015
kind_axis_hits ← _settle_axis:1593
           (+ _pick_kind_axis_col@z05 ← live_axis_col_for_count ← answer:2169)
           (+ rank_axis_resolve@z10 ← _settle_axis:1597)
kind_axis_rerank ← rank_axis_resolve@z10 ← _settle_axis:1597
                 (+ _pick_kind_axis_col@z05 ← live_axis_col_for_count)
term_axis_hits ← _settle_axis:1606
_group_leader ← asked_figure_missing@z19 ← _onepath_compose_gate ← answer:2240
```

### ЖИВА ТОЛЬКО LEGACY

```
_live_ref_key_col ← aggregate_live_header_count ← _fork_atom_of@z09 ← answer@z20_legacy
aggregate_live_row_count ← _fork_atom_of@z09 ← answer@z20_legacy
aggregate_live_header_count ← _fork_atom_of@z09 ← answer@z20_legacy
holders_of_target ← axis_focus_plan / answer@z20_legacy
                  (+ z05 expand/clarify — тоже только LEG reach)
measures_of_many ← axis_focus_plan@z20_legacy:1535
term_ref_owners ← answer@z20_legacy:1903
```

### `_bootstrap` / `_imports` / `_wire`

- `_bootstrap.py`: зона в списке загрузки (`"z17_aggregate_groups.py"`); символ
  `aggregate` — только в комментарии (:61).
- `_imports.py`, `_wire.py`: упоминаний символов зоны нет (только общий
  `register_zone` / `apply_bindings` в шапке самой зоны).

---

## Скрытые выбиратели, доступные НОВОМУ тракту

Через прямые/транзитивные вызовы из new `answer` / `_settle_axis` зона **тащит**
в один путь следующие выбиратели (источник/мера/период/ось кодом, не меню вики):

| # | Символ | Что выбирает | Как попадает в new |
|---|---|---|---|
| S-z17-1 | `kind_axis_hits` | ось по `action_axis` / `kind` (stem; fallback `meaning_candidates`) | прямо `_settle_axis`; также `_pick_kind_axis_col` / `rank_axis_resolve` |
| S-z17-2 | `kind_axis_rerank` | одна ось реранкером по label `target_src` | `rank_axis_resolve`←`_settle_axis`; `_pick_kind_axis_col`←`live_axis_col_for_count` |
| S-z17-3 | `term_axis_hits` | оси по term-группам вопроса | прямо `_settle_axis` |
| S-z17-4 | `_live_measure_date_col` | колонка даты витрины: Period→Date→DateTime | `aggregate`→`aggregate_live_column` |
| S-z17-5 | `_group_fold` | свёртка группы: count/avg/sum от `compute` | `aggregate_groups`←`answer` |

Не выбиратели, но участвуют в осевом контуре new: `refcols_of` (чтение каталога
осей), `src_is_child` (флаг child→`serene_axis.decide_grain`).

**Не** доступны новому (только legacy): `holders_of_target`, `measures_of_many`,
`term_ref_owners` — старый focus/holder/nums каскад.

---

## Вердикт для этапа-2

- Зону **нельзя выкинуть** целиком при flip: 509/640 строк тел живы одному пути.
- Кандидаты на снос после legacy: `_live_ref_key_col`, `aggregate_live_row_count`,
  `aggregate_live_header_count`, `holders_of_target`, `measures_of_many`,
  `term_ref_owners` (131 строк) — если `_fork_atom_of` / `axis_focus_plan` уйдут
  вместе с legacy.
- Для «одного пути без скрытых выбирателей» в зоне критичны **S-z17-1…3**
  (`kind_axis_*`, `term_axis_hits`) в `_settle_axis`: они выбирают ось кодом до
  SQL, в обход вики-меню.
