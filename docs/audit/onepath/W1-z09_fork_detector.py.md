# W1 — карта живости `ask/z09_fork_detector.py`

Дата: 12.09.2026. Только чтение кода. Метод: AST верхнего уровня зоны +
`rg`/`ast` по `ask/*.py`, `z20_ask_main_http.py`, `z20_ask_main_http_legacy.py`,
`test_*.py`, `_bootstrap.py` / `_imports.py` / `_wire.py`. Импорт-структуры нет —
только фактические имена в общем namespace (в т.ч. `getattr`).

Файл зоны: 1018 строк. Символов верхнего уровня: 39 (3 константы + 36 `def`).
Сумма тел символов по AST: 930 строк; остаток ~88 — шапка, `register_zone`,
пустые строки между определениями.

---

## Итог зоны

| Вердикт | Символов | Строк тел (AST) |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 1 | **20** |
| **ЖИВА ТОЛЬКО LEGACY** | 37 | **902** |
| **МЁРТВА** | 1 | **8** |
| **Всего** | 39 | 930 |

**Вердикт по зоне:** почти целиком **жива только legacy** (детектор развилки /
исходы A/B/C). Одному пути нужна **одна** функция — `fork_labels_of` (подписи
валютных вариантов в currency-clarify). После flip и сноса legacy зона как
детектор **не нужна**; останется точечная зависимость подписей (или её вынести).

**Скрытые выбиратели, доступные новому тракту:** **нет.** Единственный живой
символ — чтение подписей из `search_fork_label`, не выбор источника/меры/
периода/оси. Выбиратели меры (`_fork_relevant`, `_fork_headline_measure`,
`_fork_sum_headline_pool`) и пула (`fork_detector_scan` / `fork_scan`) до нового
`answer` **не дотягиваются**.

---

## Таблица символов

Легенда вердикта: **Н** = жива новому; **L** = только legacy; **М** = мертва.
«Кто зовёт» — внешние call-site’ы (не тело самой зоны), плюс краткая пометка
внутренней роли.

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_FACT_NEG_CYR` | 2 | только `_question_has_fact_negation` (внутри зоны) | **L** |
| `_FACT_NEG_LAT` | 2 | только `_question_has_fact_negation` | **L** |
| `_MEASURE_WORD_STEM` | 4 | только `_fork_word_names_measure` | **L** |
| `_question_has_fact_negation` | 8 | `intent_fact_complement` (внутри) | **L** |
| `intent_fact_complement` | 11 | z09: `_complement_fork_rows`/`_fork_enrich_event_rows`; **z13:**266 `_fork_complement_outcome_block` → `resolve_fork_outcome` → **legacy** z20:2970; тесты: `test_fork_detector.py` | **L** |
| `_strip_distinct_on_movement` | 12 | только `_complement_fork_rows` | **L** |
| `_complement_fork_rows` | 35 | только `_fork_enrich_event_rows` | **L** |
| `_fork_enrich_event_rows` | 8 | `fork_detector_scan` (z09:437,449); тесты: `test_fork_detector.py` | **L** |
| `_measures_by_src` | 22 | **legacy** z20:2375,2919; **z05:**1062 `entity_form_axis_on_sales` → `entity_form_structs` → complement-путь `fork_detector_scan` (legacy); тесты: `test_fork_atom_aggregate.py` | **L** |
| `_aliases_by_src` | 17 | **legacy** z20:2376,2920; тесты: `test_fork_atom_aggregate.py` | **L** |
| `_fork_headline_doc_measures` | 3 | только `_fork_sum_headline_pool` | **L** |
| `_fork_word_names_measure` | 18 | `_fork_relevant`, `_fork_headline_measure` (внутри) | **L** |
| `_fork_sum_headline_pool` | 11 | `_fork_relevant` (внутри); **z11:**274 `sales_money_measure` → `measure_class_alts` → **legacy** z20:3390,3499; тесты: `test_measure_hatch_luk.py`, `test_measure_menu_not_silent.py` (запрет в z20), `test_one_path.py` (имя в списке запретов) | **L** |
| `_fork_relevant` | 47 | **legacy** z20:2377,2921; тесты: `test_fork_detector.py`, `test_fork_atom_aggregate.py` | **L** |
| `_fork_pool_excluded` | 5 | **legacy** z20:2407,2947; тесты: `test_fork_detector.py` | **L** |
| `fork_scan` | 75 | `fork_scan_readings`, `fork_detector_scan` (внутри); тесты: `test_entity_form.py`, `test_fork_window_readings.py`, `test_fork_atom_aggregate.py`. (z04b/z05 — только docstring / имя `currency_patch_fork_scan`, не вызов) | **L** |
| `fork_scan_readings` | 47 | `fork_detector_scan` (внутри); тесты: `test_entity_form.py`, `test_fork_window_readings.py` | **L** |
| `fork_classes_windowed` | 34 | `fork_detector_scan` (внутри); тесты: `test_calendar_axis.py`, `test_currency_axis.py`, `test_fork_window_readings.py`, `test_fork_label_daybasis.py` | **L** |
| `fork_detector_scan` | 52 | **legacy** z20:2380,2924; **новый z20: 0**. Тесты: `test_entity_form.py` (имя в списке) | **L** |
| `_window_tuple_from_period` | 12 | только `_fork_atom_equiv_fp` | **L** |
| `_fork_atom_equiv_fp` | 30 | `fork_classes`, `fork_classes_windowed`; тесты: `test_entity_form.py`, `test_fork_window_readings.py` | **L** |
| `_fork_fp_diag` | 10 | **legacy** z20:2397,2944; тесты: `test_early_clarify_atom_fps_hashable.py` | **L** |
| `fork_classes` | 20 | `fork_detector_scan`; **getattr** `_meta_by_fp`: legacy z20:2387,2934; **z13:**154 `ordered_fork_classes` → resolve/outcome (legacy); тесты: много (`test_fork_*`, `test_atom_terminal`, `test_leader_hatch`, `test_action_class`, …) | **L** |
| `fork_key_of` | 10 | `_fork_key_for_period`, `_fork_log_*` (внутри); **z13:**711 `fork_outcome_c` → **legacy** z20:3023; тесты: `test_fork_label_daybasis.py` | **L** |
| `_window_fp_base` | 6 | `_fork_key_for_period`, `_fork_*_basis_groups`; тесты: `test_fork_label_daybasis.py` | **L** |
| `_fork_key_for_period` | 14 | `_fork_log`, `_class_label_lookup`; **z13:**217,247; тесты: `test_fork_label_daybasis.py` | **L** |
| `_fork_amount_basis_groups` | 18 | `_fork_log`, `_fork_log_amount_basis` | **L** |
| `_fork_log_amount_basis` | 17 | `_fork_log` | **L** |
| `_fork_day_basis_groups` | 18 | `_fork_log`, `_fork_log_day_basis`; тесты: `test_fork_label_daybasis.py` | **L** |
| `_fork_log_day_basis` | 18 | `_fork_log`; тесты: `test_fork_label_daybasis.py` | **L** |
| `_fork_log` | 42 | **legacy** z20:2418,2932; тесты: `test_fork_label_daybasis.py` | **L** |
| `fork_labels_of` | 20 | **НОВЫЙ** путь: `z04b_currency_axis.py:548,551` `currency_mismatch_blocks_answer` ← `z20_ask_main_http.py:1821` `_onepath_compose_gate` ← `answer:2240`. Также **legacy** z20 (тот же currency + исходы); **z13:**218,712; `_class_label_lookup` (внутри); тесты: `test_fork_outcomes`, `test_calendar_axis`, `test_currency_axis`, … | **Н** |
| `fork_labels_covering` | 28 | **legacy** `mk_opts` z20_legacy:1100 (+ живые вызовы mk_opts:2465,3102,3133); **z13:**220; `_class_label_lookup` (внутри). В **новом** z20 стоит вызов в `mk_opts:1076`, но **`mk_opts` из нового тракта не зовётся** (0 call-site в `answer`/соседях; mk_opts жив только legacy + z13/z21 на legacy-цепи). | **L** |
| `fork_label_siblings` | 8 | **нигде** (stub `return []`; устаревшее расширение пула) | **М** |
| `_fork_answering_sums` | 22 | только `_fork_atom_of`; тесты: `test_fork_detector.py` | **L** |
| `_fork_headline_measure` | 68 | только `_fork_atom_of`; тесты: `test_fork_detector.py`, `test_measure_hatch_luk.py`; `test_one_path.py` — имя в blacklist молчаливых выбирателей | **L** |
| `_fork_atom_of` | 109 | `fork_classes`/`fork_classes_windowed`; **legacy** z20:2393,2940; **z13:**163 `ordered_fork_classes`; тесты: много | **L** |
| `_class_branch_label` | 7 | только `_class_label_lookup` | **L** |
| `_class_label_lookup` | 40 | **z13:**329 `resolve_fork_outcome` → **legacy** z20:2970 | **L** |

---

## Прямые вызовы из z20

### Новый `z20_ask_main_http.py`

| Имя | Строка | Контекст |
|---|---:|---|
| `fork_labels_covering` | 1076 | внутри **мёртвого** `mk_opts` (определён в файле, из `answer` не зовётся) |
| *(через z04b)* `fork_labels_of` | 1821→z04b | `_onepath_compose_gate` → `currency_mismatch_blocks_answer` → `fork_labels_of` — **живой** путь `answer` |

Других имён зоны (в т.ч. `fork_detector_scan`, `_fork_relevant`, `_fork_atom_of`,
`resolve_fork_*`) в новом z20 **нет** (ни вызовов, ни getattr/строк).

Строки журнала `fork_outcome` / `fork_keys` / `search_fork_label` — колонки БД и
локальный `_journal_fork_keys`, **не** символы z09.

### Legacy `z20_ask_main_http_legacy.py`

Прямо: `_measures_by_src`, `_aliases_by_src`, `_fork_relevant`,
`fork_detector_scan`, `fork_classes` (getattr `_meta_by_fp`), `_fork_atom_of`,
`_fork_fp_diag`, `_fork_pool_excluded`, `_fork_log`, `fork_labels_covering`
(через `mk_opts`), плюс исходы z13 (`resolve_fork_outcome`, `fork_outcome_c`, …),
которые транзитивно тянут остальное.

---

## Транзитивные цепочки

### До нового z20 (единственная)

```
fork_labels_of
  ← currency_mismatch_blocks_answer          (z04b_currency_axis.py:548/551)
  ← _onepath_compose_gate                    (z20_ask_main_http.py:1821)
  ← answer                                   (z20_ask_main_http.py:2240)
```

### До legacy z20 (основные)

```
fork_detector_scan
  ← answer (legacy) early+late forks         (z20_…_legacy.py:2380, 2924)
  ← _fork_enrich_event_rows
      ← intent_fact_complement / _complement_fork_rows / …
  ← fork_scan / fork_scan_readings
  ← fork_classes / fork_classes_windowed
      ← _fork_atom_of ← _fork_headline_measure / _fork_answering_sums
      ← _fork_atom_equiv_fp ← _window_tuple_from_period

_measures_by_src / _aliases_by_src / _fork_relevant / _fork_log /
_fork_atom_of / _fork_fp_diag / _fork_pool_excluded
  ← answer (legacy) напрямую                 (:2375–2418, :2919–2947)

_class_label_lookup / intent_fact_complement / fork_key_of /
fork_labels_of / fork_labels_covering / _fork_key_for_period / _fork_atom_of
  ← z13 resolve_fork_outcome / fork_outcome_c / ordered_fork_classes / …
  ← resolve_fork_outcome / fork_outcome_c    (legacy :2970, :3023)

_fork_sum_headline_pool
  ← sales_money_measure (z11:274)
  ← measure_class_alts (z16)
  ← answer (legacy)                          (:3390, :3499)

fork_labels_covering
  ← mk_opts (legacy, живые вызовы)
  ← _fork_clarify_opts / fork_clarify_from_wiki_pool (z13) → legacy
```

### Никуда (мертва)

```
fork_label_siblings  — определение есть, вызовов в ask/ и test_*.py нет
```

---

## Другие зоны, bootstrap, тесты

| Место | Роль |
|---|---|
| `_bootstrap.py:32` | грузит `"z09_fork_detector.py"` в общий namespace (всегда) |
| `_imports.py` / `_wire.py` | имён зоны нет (только `register_zone` в конце файла зоны) |
| `z13_fork_outcomes.py` | главный потребитель атомов/подписей/ключей — **только legacy**-тракт исходов |
| `z11_sales.py` | `_fork_sum_headline_pool` через `sales_money_measure` — **legacy** |
| `z05_entity_form.py` | `_measures_by_src` в `entity_form_axis_on_sales` — цепь complement/`fork_detector_scan` → **legacy** |
| `z04b_currency_axis.py` | `fork_labels_of` — **и new, и legacy**; `currency_patch_fork_scan` зовётся из `fork_scan_readings` → **legacy** |

### Замки / тесты (упоминают символы зоны)

`test_fork_detector.py`, `test_fork_outcomes.py`, `test_fork_atom_aggregate.py`,
`test_fork_window_readings.py`, `test_fork_label_daybasis.py`,
`test_calendar_axis.py`, `test_currency_axis.py`, `test_entity_form.py`,
`test_atom_terminal.py`, `test_leader_hatch.py`, `test_action_class.py`,
`test_early_clarify_atom_fps_hashable.py`, `test_measure_hatch_luk.py`,
`test_measure_menu_not_silent.py`, `test_rank_leader_path.py` (соседние fork_* z13),
`test_one_path.py` — `_fork_headline_measure` в списке **запрещённых** молчаливых
выбирателей (не вызов).

---

## Скрытые выбиратели

| Кандидат в зоне | Что выбирает | Доступен новому? |
|---|---|---|
| `_fork_relevant` + `measure_choice` | мера по слову вопроса | **нет** (только legacy / тесты) |
| `_fork_headline_measure` / `_fork_sum_headline_pool` | «головная» / headline-мера | **нет** |
| `fork_detector_scan` / `fork_scan*` / `fork_classes*` | круг источников и классы развилки | **нет** |
| `_fork_enrich_event_rows` / complement | форма count (complement vs distinct) | **нет** |
| `fork_labels_of` | только label из БД | **да**, но **не выбиратель** источника/меры/периода/оси |

---

## Вывод для «одного пути»

Зона **не является опорой** нового тракта. Детектор и почти все 900+ строк —
наследство legacy-исходов A/B/C. Для onepath достаточно либо оставить
`fork_labels_of` (и таблицу подписей) как общий helper подписей валютных
вариантов, либо заменить чтение подписей локально в z04b и после flip снести
остальное вместе с legacy.
