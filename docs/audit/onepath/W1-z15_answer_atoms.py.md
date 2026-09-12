# W1: карта живости `ask/z15_answer_atoms.py`

Дата: 12.09.2026. Зона: `ubuntu/serenedb/ask/z15_answer_atoms.py` (437 строк файла).
Метод: AST верхнего уровня + grep `\bсимвол\b` по `ask/*.py` (включая оба z20),
`_bootstrap.py` / `_imports.py` / `_wire.py`, `test_*.py`; вызовы через getattr/строку —
не найдены. Граф достижимости: BFS от всех `def` выбранного z20 **без** подмешивания
другого z20 (имя `answer` в двух файлах не сливается). Внутренние вызовы зоны
развёрнуты. Docstring/комментарии не считаются зовом.

Корни: `z20_ask_main_http.py` = НОВЫЙ (onepath); `z20_ask_main_http_legacy.py` = LEGACY.

---

## Итог зоны

| Метрика | Значение |
|---|---|
| Строк файла | 437 |
| Символов верхнего уровня | 17 |
| Сумма строк символов | 394 (остальное — шапка/пробелы/`register_zone`) |
| **ЖИВА НОВОМУ** | **346** строк (14 символов) |
| **ЖИВА ТОЛЬКО LEGACY** | **1** строка (1 символ: `PROOF_NA`) |
| **МЁРТВА** | **47** строк (2 символа: `stop2_active`, `determined_answer_rivals`) |

Вердикт зоны: **нужна одному пути** (ядро атомов ответа живёт в `_onepath_compose_gate` /
`build_period_empty_answer`). После сноса legacy останется мёртвым только
`PROOF_NA` (+ уже мёртвые стоп-2). Два символа стоп-2 уже мёртвы обоим трактам
(живут только в тестах).

---

## Таблица: символ | строки | кто зовёт | вердикт

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `stop2_active` | 11 | никто в ask/; тесты: `test_decision_id.py`, `test_step4_guards.py` | **МЁРТВА** |
| `determined_answer_rivals` | 36 | никто в ask/; тест: `test_step4_guards.py` | **МЁРТВА** |
| `answer_money` | 10 | **NEW** `z20_ask_main_http.py:1634` (`_onepath_compose_gate`); **LEG** `…_legacy.py:3969` (`answer`). Docstring: `z18_compose.py:349` (не зов) | **ЖИВА НОВОМУ** |
| `answer_slot_mode` | 27 | **NEW** `:1637`; **LEG** `:3972`; внутри зоны ← `atom_operation` | **ЖИВА НОВОМУ** |
| `compose_slot_values` | 72 | **NEW** `:1280`, `:1801`, `:1816`; **LEG** `:1306`, `:4023`, `:4261`, `:4336`, `:4357`. Коммент: `z14_clarify_memory.py:154` | **ЖИВА НОВОМУ** |
| `UNIT_UNKNOWN` | 1 | внутри ← `render_atom_pair`; внешне мёртвые: `z10_rank.py:129` (`rank_leader_answer_text`), `z11_sales.py:222` (`rank_groups_answer_text`) — не достижимы ни из NEW, ни из LEG | **ЖИВА НОВОМУ** (через `render_atom_pair`) |
| `PROOF_COMPUTED` | 1 | внутри ← `atom_from_agg` / `build_answer_atom`; **NEW+LEG** ещё `z13_fork_outcomes.py:414` (`atom_terminal_gate_text`); остальные внешние — только LEGACY fork/entity_form или мёртвый `rank_leader_atom` | **ЖИВА НОВОМУ** |
| `PROOF_NA` | 1 | только fork-путь LEGACY: `z09_fork_detector.py:484,880,887,892`; `z13_fork_outcomes.py:175,437`. Внутри z15 не используется. NEW fork не зовёт | **ЖИВА ТОЛЬКО LEGACY** |
| `PROOF_UNCOUNTED` | 1 | внутри ← `atom_from_agg` / `build_answer_atom` / `render_atom_pair`; внешне — LEGACY fork/entity_form | **ЖИВА НОВОМУ** |
| `_ATOM_OPS` | 1 | только внутри ← `atom_from_agg`, `build_answer_atom` | **ЖИВА НОВОМУ** |
| `atom_operation` | 15 | **NEW** `:1290`, `:1683`; **LEG** `:1316`, `:4095`, `:4267`, `:4363` | **ЖИВА НОВОМУ** |
| `_atom_exact_value` | 20 | только внутри ← `atom_from_agg` | **ЖИВА НОВОМУ** |
| `build_answer_atom` | 44 | внутри ← `atom_from_agg` (**NEW**); внешне: `z05`/`z09` — только LEGACY; `z10_rank.py:333` (`rank_leader_atom`) — мёртв обоим | **ЖИВА НОВОМУ** |
| `atom_from_agg` | 56 | **NEW** `:1289`, `:1682`; **LEG** `:1315`, `:3747`, `:4012`, `:4094`, `:4266`, `:4362`; `z16:547` (`build_measure_empty_pivot`) — только LEGACY; `z12:1236` (`stock_breakdown_leader_fallback`) — мёртв обоим | **ЖИВА НОВОМУ** |
| `_period_window_human` | 8 | только внутри ← `render_atom_pair` | **ЖИВА НОВОМУ** |
| `render_atom_pair` | 60 | внутри ← `fill_atom_pairs`; **NEW+LEG** `z13:416` (`atom_terminal_gate_text`); **LEG прямо** `…_legacy.py:3753`, `:4021`; LEG `z05:1195`, `z13:674,728`; мёртв `z12:1241`. Docstring `z18:368,372` | **ЖИВА НОВОМУ** (нет прямого вызова в NEW z20 — транзитивно) |
| `fill_atom_pairs` | 30 | **NEW** `:1713`, `:1756`; **LEG** `:4130`, `:4197` | **ЖИВА НОВОМУ** |

`_bootstrap.py:38` — только имя файла зоны в списке загрузки (не символ).
`_imports.py`, `_wire.py` — упоминаний символов нет. getattr/передача имени строкой — нет.

---

## Транзитивные цепочки (до корня z20)

### Прямо из НОВОГО z20

```
answer_money          ← _onepath_compose_gate ← answer ← _answer_checked_core ← answer_checked
answer_slot_mode      ← _onepath_compose_gate ← …
compose_slot_values   ← build_period_empty_answer ← _onepath_compose_gate ← …
                      ← _onepath_compose_gate (ещё :1801, :1816)
atom_operation        ← build_period_empty_answer ← _onepath_compose_gate ← …
                      ← _onepath_compose_gate (:1683)
atom_from_agg         ← build_period_empty_answer ← _onepath_compose_gate ← …
                      ← _onepath_compose_gate (:1682)
fill_atom_pairs       ← _onepath_compose_gate ← …
```

### Транзитивно новому (через зону / другие зоны)

```
build_answer_atom     ← atom_from_agg ← build_period_empty_answer ← _onepath_compose_gate@NEW
_atom_exact_value     ← atom_from_agg ← …
_ATOM_OPS             ← atom_from_agg / build_answer_atom ← …
PROOF_COMPUTED        ← atom_from_agg ← …          (и atom_terminal_gate_text ← _onepath_compose_gate@NEW)
PROOF_UNCOUNTED       ← atom_from_agg / render_atom_pair ← …
render_atom_pair      ← fill_atom_pairs ← _onepath_compose_gate@NEW
                      ← atom_terminal_gate_text@z13 ← _onepath_compose_gate@NEW
UNIT_UNKNOWN          ← render_atom_pair ← …
_period_window_human  ← render_atom_pair ← …
answer_slot_mode      ← atom_operation ← …          (доп. внутренний путь)
```

### Только LEGACY (доп. пути; для `PROOF_NA` — единственные)

```
PROOF_NA              ← _fork_atom_of@z09 ← answer@LEG
                      ← _fork_applicable_*@z13 ← … ← answer@LEG
build_answer_atom     ← _fork_atom_of / entity_form_atom_* ← try_entity_form_answer ← answer@LEG
atom_from_agg         ← build_measure_empty_pivot@z16 ← answer@LEG
render_atom_pair      ← answer@LEG (прямо :3753, :4021)
                      ← try_entity_form_answer / fork_outcome_c ← answer@LEG
```

NEW `answer()` **не** зовёт `try_entity_form_answer`, `_fork_atom_of`, `fork_outcome_c`,
`build_measure_empty_pivot` — эти ветки после flip не держат зону.

### Мёртвые цепочки (ни NEW, ни LEGACY)

```
stop2_active / determined_answer_rivals — нет вызывающих в ask/
UNIT_UNKNOWN ← rank_leader_answer_text@z10 / rank_groups_answer_text@z11  (хелперы недостижимы)
build_answer_atom ← rank_leader_atom@z10  (недостижим)
atom_from_agg / render_atom_pair ← stock_breakdown_leader_fallback@z12  (недостижим)
```

---

## Тесты (замки, упоминающие символы)

| Символ | test_*.py |
|---|---|
| `stop2_active` | `test_decision_id.py`, `test_step4_guards.py` |
| `determined_answer_rivals` | `test_step4_guards.py` |
| `answer_money` | `test_compose.py`, `test_rank_axis_anchor.py`, `test_step4_guards.py`, `test_unit_from_data.py` |
| `answer_slot_mode` | `test_atom_terminal.py`, `test_gate.py`, `test_rank_axis_anchor.py` |
| `compose_slot_values` | `test_a3_passport.py`, `test_atom_terminal.py`, `test_compose.py`, `test_gate.py`, `test_step4_guards.py` |
| `UNIT_UNKNOWN` | `test_atom_terminal.py`, `test_unit_from_data.py` |
| `PROOF_*` | `test_answer_atom.py`, `test_atom_terminal.py`, `test_fork_*`, `test_entity_form.py`, `test_action_class.py`, `test_b9_routing.py`, `test_leader_hatch.py`, `test_partial_flag_propagation.py`, … |
| `atom_operation` | `test_answer_atom.py`, `test_atom_terminal.py` |
| `build_answer_atom` | `test_answer_atom.py`, `test_atom_terminal.py`, `test_fork_*`, `test_entity_form.py`, `test_action_class.py`, `test_unit_from_data.py` |
| `atom_from_agg` | `test_answer_atom.py`, `test_action_class.py`, `test_compare_sales.py`, `test_unit_from_data.py` |
| `render_atom_pair` | `test_answer_atom.py`, `test_atom_terminal.py`, `test_one_path.py` (запрет early-терминала), `test_action_class.py`, `test_compare_sales.py`, `test_entity_form.py`, `test_partial_flag_propagation.py`, `test_rank_leader_path.py`, `test_unit_from_data.py` |
| `fill_atom_pairs` | `test_answer_atom.py` |
| `_ATOM_OPS`, `_atom_exact_value`, `_period_window_human` | прямых тестов нет (закрыты через `atom_from_agg` / `render_atom_pair`) |

---

## Скрытые выбиратели → новый тракт?

Критерий задачи: функции, **выбирающие источник / меру / период / ось кодом**.

| Кандидат | Доступен NEW? | Выбор источника/меры/периода/оси? | Замечание |
|---|---|---|---|
| `answer_slot_mode` | да, прямо | **нет** (не src/measure/period/axis) | Выбирает **форму слотов** `count/sum/rank/compare/list` из `want/compute/form/grain`; флаг `ASK_ATOM_TERMINAL` переключает compare↔rank |
| `atom_operation` | да, прямо | **нет** | Мапит mode/form → операция атома (`count/sum/max/…/compare`) |
| `answer_money` | да, прямо | **нет** (не выбор меры) | Булев «нужны ли деньги» от want/compute + наличия measure |
| `_atom_exact_value` | транзитивно | **нет** | Какое поле `agg` взять под операцию |
| `compose_slot_values` | да | **нет** | Какие числовые слоты открыть под mode |
| `stop2_active` / `determined_answer_rivals` | нет (мертвы) | соперники сущности — да по смыслу, но **не в NEW** | |

**Вывод:** в новый тракт зона **не** тащит выбирателей источника/меры/периода/оси.
Тащит выбиратели **формы ответа / операции атома / денежности** (`answer_slot_mode`,
`atom_operation`, `answer_money`) — они сидят в `_onepath_compose_gate` до compose/gate.
Отдельно: сразу после `answer_slot_mode` сам NEW z20 ещё раз переписывает
`slot_mode` через `rank_intent_from` (это уже z20, не z15).

---

## Краткие выводы

1. Зона **жива одному пути**: 346/394 строк символов нужны NEW (прямо или через
   `atom_from_agg` / `fill_atom_pairs` / `atom_terminal_gate_text`).
2. После flip+сноса legacy: убрать можно `PROOF_NA` (1 стр.) и уже мёртвые
   `stop2_active` + `determined_answer_rivals` (47 стр.); остальное ядро атомов
   остаётся.
3. Внешние зовы из z05/z09/z16 — legacy-only; z10 rank-leader / z12 stock-fallback —
   мёртвы обоим трактам уже сейчас.
4. Скрытых выбирателей src/measure/period/axis в NEW через z15 нет; есть
   form/operation-выбиратели в горячем хвосте onepath.
