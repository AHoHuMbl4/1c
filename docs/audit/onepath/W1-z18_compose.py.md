# W1 — карта живости зоны `ask/z18_compose.py`

Срез: 12.09.2026. Только чтение кода. Чужие отчёты onepath не читались.

Зона: формулировка ответа (`compose`) + подстановка чисел + паспорт +
вспомогательные regex для гейта. Файл 882 строки; top-level символов **29**
(сумма тел символов **790** строк; остальное — шапка/пробелы/комменты между ними).

Загрузка: `_bootstrap.py:41` включает `z18_compose.py` в `_ZONE_FILES` всегда
(и при `ASK_ONEPATH=1`, и на legacy). `_imports.py` / `_wire.py` символов зоны
не упоминают — только общий `register_zone` / `apply_bindings` в конце файла
(`register_zone('ask.z18_compose', globals())`).

---

## Итог зоны

| Вердикт | Символов | Строк (сумма тел) |
|---|---:|---:|
| **ЖИВА НОВОМУ** (прямо или транзитивно) | 26 | **752** |
| **ЖИВА ТОЛЬКО LEGACY** | 3 | **38** |
| **МЁРТВА** | 0 | **0** |
| Всего символов | 29 | 790 |

**Вердикт по зоне: нужна одному пути.** Ядро `compose` + fill/passport/gate-regex
зовётся из нового `z20_ask_main_http.py` (`_onepath_compose_gate`,
`build_period_empty_answer`, `_settle_axis` / меню оси, `OUR_PROMPTS`, `gate`).
После flip и сноса legacy из зоны уходят только `merge_period2_groups`,
`_filled_ask`, `_ask_back` (38 строк) — не блок формулировки.

---

## Таблица символов

Колонка «кто зовёт» — фактические упоминания имени в общем namespace
(`ask/*.py` + тесты). Комментарии/докстринги без вызова помечены `(коммент)`.

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `merge_period2_groups` | 16 | **legacy** `answer` 3809 | **ТОЛЬКО LEGACY** |
| `axis_clarify_options` | 25 | **new** `_settle_axis` 1622; **new** `answer` 2046; **legacy** `answer` 3655, 4084 | **ЖИВА НОВОМУ** |
| `ANSWER_SYS` | 31 | **new** `OUR_PROMPTS` 755; **legacy** `OUR_PROMPTS` 761; внутри `compose` 854 | **ЖИВА НОВОМУ** |
| `_split_answer` | 31 | **new** `_coverage_answer` 799; **new** `_onepath_compose_gate` 1702, 1751; **legacy** 804, 4112, 4192; `test_compose.py` | **ЖИВА НОВОМУ** |
| `SLOT` | 1 | внутри `_fill_figures` 278; **z15** `fill_atom_pairs` 433 → new `_onepath_compose_gate` 1713/1756 | **ЖИВА НОВОМУ** |
| `LEFTOVER` | 1 | внутри `formulation_flaws` 531 → new 1729/1772 | **ЖИВА НОВОМУ** (внутр.) |
| `_group_value_by_name` | 17 | внутри `_fill_figures` 253 → new 1710/1753 | **ЖИВА НОВОМУ** (внутр.) |
| `_fill_figures` | 122 | **new** `_onepath_compose_gate` 1710, 1753; **legacy** 4126, 4194; внутри `ensure_*`/`_filled_ask`; тесты `test_compose`/`test_period_empty`/`test_rank_axis_anchor` | **ЖИВА НОВОМУ** |
| `ensure_n_groups_named` | 19 | **new** 1715, 1758; **legacy** 4132, 4199; тесты | **ЖИВА НОВОМУ** |
| `ensure_count_named` | 19 | **new** 1742, 1786; **legacy** 4177, 4236; `test_gate`/`test_rank_axis_anchor`; (коммент z15:82) | **ЖИВА НОВОМУ** |
| `_measure_dimension` | 19 | внутри `_unit_for_measure` 362; **z13** `_fork_clarify_axis_kind` 461 / `_fork_human_measure_label` 511 (только legacy-fork); `test_unit_from_data` | **ЖИВА НОВОМУ** (через `_unit_for_measure`) |
| `_unit_for_measure` | 19 | **new** `_onepath_compose_gate` 1828; **legacy** 4383; **z15** `atom_from_agg` 309 → new 1289/1682; мёртвые обёртки z10 `rank_leader_*` (зовцов нет); тесты | **ЖИВА НОВОМУ** |
| `postprocess_money_answer_text` | 9 | **new** 1837; **legacy** 4389; тесты | **ЖИВА НОВОМУ** |
| `build_answer_passport` | 60 | **new** `build_period_empty_answer` 1267; **new** `_onepath_compose_gate` 1716, 1759; **legacy** 1293/4025/4135/4200; **z16** `build_measure_empty_pivot` 521 → только legacy 3450; тесты passport | **ЖИВА НОВОМУ** |
| `ensure_answer_passport` | 10 | **new** 1279, 1728, 1771; **legacy** 1305/4148/4214; **z16** 532 → legacy; `test_passport` | **ЖИВА НОВОМУ** |
| `measure_label_of` | 10 | **new** 1213, 1294, 1687; **legacy** много; **z09** `_fork_atom_of` → только legacy; **z10**/**z12** обёртки без зовущих; тесты | **ЖИВА НОВОМУ** |
| `_table_label` | 12 | **new** 1271, 1720, 1763; внутри `measure_label_of`/`_passport_axis_label`; **legacy**; **z13**/**z16** (legacy-цепочки); тесты | **ЖИВА НОВОМУ** |
| `_passport_axis_label` | 12 | **new** 1275, 1299, 1694, 1724, 1767; **legacy**; **z05**/**z10**/**z13** (частично без new-корня); тесты | **ЖИВА НОВОМУ** |
| `_passport_axis_col` | 4 | **new** 1276, 1300, 1725, 1768; **legacy** 1302/1326/4144/4209/4278/4374 | **ЖИВА НОВОМУ** |
| `_passport_origin` | 8 | **new** 1270, 1297, 1692, 1719, 1762; **legacy**; **z10**/**z16** (legacy/мёртвые обёртки); `test_passport` | **ЖИВА НОВОМУ** |
| `formulation_flaws` | 28 | **new** 1729, 1772; **legacy** 4154, 4215; внутри `_filled_ask`; `test_compose` | **ЖИВА НОВОМУ** |
| `copied_figures` | 68 | **new** 1703, 1752; **legacy** 4116, 4193; тесты | **ЖИВА НОВОМУ** |
| `_filled_ask` | 19 | **legacy** `answer` 4149, 4237 | **ТОЛЬКО LEGACY** |
| `_ask_back` | 3 | **legacy** `answer` 4113, 4237; stub `return ""`; `test_compose` | **ТОЛЬКО LEGACY** |
| `compose` | 223 | **new** `_onepath_compose_gate` 1699, 1745; **legacy** 4109, 4186; тесты (`test_compose`, `test_answer_atom`, …); `test_one_path` проверяет наличие `compose(` | **ЖИВА НОВОМУ** |
| `NUMTOK` | 1 | **z19** `_tokens` 132 → **new** `gate` 222 + `copied_figures` 594; (коммент new/legacy gate ~100) | **ЖИВА НОВОМУ** |
| `SEP` | 1 | **z19** `_readings` / `_tokens` → same | **ЖИВА НОВОМУ** |
| `DATE3` | 1 | **z19** `_dates` 72 / `_date_spans` 110 → `_tokens`/`gate` | **ЖИВА НОВОМУ** |
| `DATE2` | 1 | **z19** `_dates` 80 / `_date2_readings` 95 / `_date_spans` 117 → **new** `gate` 224/236 | **ЖИВА НОВОМУ** |

---

## Транзитивные цепочки (до корня z20)

### Живы новому `z20_ask_main_http.py`

```
compose ← _onepath_compose_gate ← answer
ANSWER_SYS ← compose; также OUR_PROMPTS (prompt_leak)
_split_answer ← _onepath_compose_gate; _coverage_answer
_fill_figures ← _onepath_compose_gate
  ← SLOT (внутри); _group_value_by_name (внутри)
ensure_n_groups_named / ensure_count_named ← _onepath_compose_gate
copied_figures ← _onepath_compose_gate
  ← _tokens(z19) ← NUMTOK, SEP, DATE* (через _date_spans)
formulation_flaws ← _onepath_compose_gate
  ← LEFTOVER (внутри)
build_answer_passport / ensure_answer_passport /
  _table_label / _passport_axis_label / _passport_axis_col /
  _passport_origin / measure_label_of
  ← _onepath_compose_gate; build_period_empty_answer
_unit_for_measure ← _onepath_compose_gate
  ← _measure_dimension (внутри)
  также: atom_from_agg(z15) ← _onepath_compose_gate / build_period_empty_answer
postprocess_money_answer_text ← _onepath_compose_gate
axis_clarify_options ← _settle_axis; answer (меню оси)
SLOT ← fill_atom_pairs(z15) ← _onepath_compose_gate
NUMTOK/SEP/DATE3/DATE2 ← _tokens/_dates/_date2_readings(z19) ← gate(new z20)
  ← _onepath_compose_gate / _coverage_answer
```

### Только legacy `z20_ask_main_http_legacy.py`

```
merge_period2_groups ← answer (period2 / aggregate_groups) :3809
_ask_back ← answer :4113, :4237
_filled_ask ← answer :4149, :4237
  (_filled_ask внутри зовёт _fill_figures + formulation_flaws —
   сами эти символы живы и новому другим путём)
```

### Цепочки других зон → legacy (символы при этом живы новому иначе)

```
measure_label_of ← _fork_atom_of(z09) ← answer(legacy) :2393/:2940
  [в new z20 fork_detector / _fork_atom_of нет]
build_answer_passport / ensure_answer_passport / _table_label / _passport_origin
  ← build_measure_empty_pivot(z16) ← answer(legacy) :3450
_measure_dimension / _passport_axis_label / _table_label
  ← fork_outcome_*(z13) ← answer(legacy) fork_outcome_c :3023
  [в new z20 fork_outcome_* нет]
_passport_axis_label ← entity_form_compute / _event_distinct_fork_rows(z05)
  ← z09; new z20 этих имён не зовёт
```

### Мёртвые обёртки (не дают живости, символы живы иначе)

```
rank_leader_answer_text / rank_leader_atom (z10) — зовут _unit_for_measure,
  measure_label_of, _passport_*; **внешних зовущих в ask/*.py нет**
stock_breakdown_leader_fallback (z12) — зовёт measure_label_of;
  **внешних зовущих нет**
```

---

## Bootstrap / imports / wire

| Файл | Роль для z18 |
|---|---|
| `_bootstrap.py:41` | имя файла в `_ZONE_FILES` — зона грузится всегда |
| `_imports.py` | символов z18 нет |
| `_wire.py` | символов z18 нет |
| конец `z18_compose.py` | `register_zone('ask.z18_compose', globals())` |

---

## Тесты (замки, где имя зоны реально дергается)

| Файл | Что трогает |
|---|---|
| `test_compose.py` | `compose`, `_split_answer`, `_fill_figures`, `_ask_back`, `formulation_flaws`, `copied_figures`, `ensure_n_groups_named`, `measure_label_of` |
| `test_passport.py` / `test_a3_passport.py` | `build_answer_passport`, `ensure_answer_passport`, `_passport_origin` |
| `test_unit_from_data.py` | `_unit_for_measure`, `_measure_dimension`, `postprocess_money_answer_text` |
| `test_rank_axis_anchor.py` | `_fill_figures`, `copied_figures`, `ensure_*`, `_unit_for_measure`, `postprocess_*`, compose-хвост |
| `test_gate.py` | `ensure_count_named` (+ контекст гейта) |
| `test_period_empty.py` | `_fill_figures`, `copied_figures` |
| `test_answer_atom.py` / `test_atom_terminal.py` | `compose`, `copied_figures` |
| `test_partial_flag_propagation.py` | `ensure_n_groups_named` |
| `test_action_class.py` / `test_measure_empty.py` | подмена `_table_label` / `_passport_axis_label`; compose |
| `test_one_path.py` | наличие `compose(` / шага compose+gate в тексте new z20 |

---

## Скрытые выбиратели, доступные новому тракту

| Символ | Что делает | Доступ с new z20 | Оценка |
|---|---|---|---|
| **`axis_clarify_options`** | Строит опции оси (`distinct_by`/label из `target_src`+`TABLES`) | Прямо: `_settle_axis` (clarify=axis) и `answer` → `readings_menu(..., "axis", ...)` | **Да — выбиратель оси (меню).** Не silent-pick: при >1 опции уходит в `readings_menu`. |
| **`_measure_dimension`** | Классифицирует меру как `money`/`qty`/`unknown` через `sales_money_measure` / `sales_qty_measure` | Только через `_unit_for_measure` (new:1828) и `atom_from_agg` | **Слабый скрытый выбор роли меры кодом** (не меню человеку; влияет на единицу/атом). Не выбирает src/period/axis. |
| Остальные символы зоны | Формулировка, слоты, паспорт, regex гейта | — | **Не выбиратели** источника/меры/периода/оси |

Итого: в новый тракт зона **тащит один явный осевой выбиратель-построитель**
(`axis_clarify_options`) и **кодовую классификацию роли меры**
(`_measure_dimension` → единица). Отдельных silent-выбирателей src/period из z18
в new path нет.

---

## Краткие выводы для этапа-2

1. **z18 целиком оставлять в одном пути** — 752/790 строк живы новому.
2. Кандидаты на снос **после** удаления legacy: `merge_period2_groups`,
   `_filled_ask`, `_ask_back` (38 строк). `_ask_back` уже stub (`return ""`).
3. При переносе/сжатии compose-хвоста сохранять связку
   `compose → _split_answer → _fill_figures/SLOT → ensure_* → passport →
   formulation_flaws/copied_figures → gate(NUMTOK…)` и
   `axis_clarify_options` для меню оси.
4. Замок `test_one_path` уже смотрит на вызов `compose(`; узкие замки —
   `test_compose` / `test_passport` / `test_unit_from_data`.
