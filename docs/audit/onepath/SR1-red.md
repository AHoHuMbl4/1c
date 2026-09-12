# SR1 — КРАСНАЯ: снёс ли S1 что-то живое

Дата: 12.09.2026. Режим: read-only + локальные прогоны замков + один отчёт.
Код/git/psql/полигон/прод не трогались. Чужие `SR*-*.md` не читались.

Цель атаки: **найти снесённое-живое**, а не подтвердить снос.

Реестры: `W1-X1.md`, `W2-A1.md` (§жива / щели), поправки `W2-R1/R2/R3.md`.
Рабочее дерево (не коммит): `ask/` 10 файлов, +177/−7799.

---

## Вердикт одной строкой

**Снос чист для нового тракта.** Символы «жива новому» / щели W2-A1+R*
и все 149 внешних имён W1-X1 на месте (часть — вынесена в другие зоны).
Список снесённого-живого: **пуст**.

Красный `test_measure_empty` — не контрпример: падает на
`measure_row_all_zero`, в W1-z16 помеченном **ЖИВА ТОЛЬКО LEGACY**
(зов только из снесённого legacy z20). Замок не сужен под S1 — это долг
замка, не вырез живого пути.

---

## 1. Прогон замков тракта

Запуск: `python3 test_*.py` из `ubuntu/serenedb` (`PYTHONPATH=.`).
pytest ломается на `sys.exit` harness — не использовался.

| замок | итог | примечание |
|---|---|---|
| `test_one_path` | **41/0** EC=0 | |
| `test_zone_names_resolvable` | **96/0** EC=0 | S1: нет ASK_LEGACY; patch identity |
| `test_enough` | 9 ok EC=0 | |
| `test_no_pre_wiki_reorders` | **39/0** EC=0 | |
| `test_measure_hatch_luk` | 16 ok EC=0 | |
| `test_measure_menu_not_silent` | **11/0** EC=0 | |
| `test_axis_count_plain` | 13 ok EC=0 | |
| `test_wiki_leader_not_overridden` | **10/0** EC=0 | |
| `test_wiki_card_hybrid` | 65/0 EC=0 | |
| `test_ask_choice_memory` | 45/0 EC=0 | |
| `test_ask_journal` | 11/0 EC=0 | |
| `test_journal_fields` | 22/0 EC=0 | |
| `test_gate` | 56/0 EC=0 | |
| `test_compose` | **93** ok EC=0 | |
| `test_period_empty` | **30** ok EC=0 | |
| `test_health_gap` | 23/0 EC=0 | |
| `test_health_native_freshness` | 32/0 EC=0 | |
| `test_health_tick_status` | 14/0 EC=0 | |
| `test_intent` | 162/0 EC=0 | |
| `test_final_stock_route_filters_absent` | 9/0 EC=0 | slit noise жив |
| `test_sales_canon_prefer` | 29/0 EC=0 | |
| `test_rank_leader_path` | 28/0 EC=0 | |
| `test_early_clarify_atom_fps_hashable` | 4/0 EC=0 | |
| `test_verify_threshold` | **имя файла другое** | канон: `test_verify_threshold_menu.py` → **4/0** |
| `test_named_type_filter` | 16/0 EC=0 | |
| `test_wiki_candidate_verify` | 64/0 EC=0 | |
| `test_wiki_captions_builder` | 24/0 EC=0 | |
| `test_k4_meta_names` | 15/0 EC=0 | |
| `test_decision_id` | 30 ok EC=0 | |
| `test_answer_atom` | 5/0 EC=0 | |
| `test_atom_terminal` | 5/0 EC=0 | |
| `test_caveat` | PASS EC=0 | |
| `test_b9_routing` | 7 ok EC=0 | |
| `test_rank_axis_anchor` | 66/0 EC=0 | |
| `test_sales_rank_canon` | 18/0 EC=0 | |
| `test_trace_rid` | 10 ok EC=0 | |
| `test_terminal_round` | 24 ok EC=0 | |
| `test_action_class` | 8/0 EC=0 | slit fork_labels |
| `test_k4_guess_vs_clarify` | 12/0 EC=0 | |
| `test_k4_clarify_vs_nodata` | 7/0 EC=0 | |
| `test_axis_focus` | 3/0 EC=0 | |
| `test_stock_balance_path` | 36/0 EC=0 | |
| `test_step4_guards` | 27/0 EC=0 | некролог-щели |
| `test_step2` | 38/0 EC=0 | |
| `test_measure_empty` | **RED EC=1** | см. §1.1 |
| `test_post_gate_none_src` | 6/0 EC=0 | |
| `test_fork_label_daybasis` | 27/0 EC=0 | некролог |
| `test_fork_atom_aggregate` | 27/0 EC=0 | некролог |
| `test_warehouse_axis_autonomy` | 4/0 EC=0 | |
| `test_warehouse_aggregate_breakdown` | 5/0 EC=0 | |
| `test_leader_hatch` | 27/0 EC=0 | некролог |
| `test_compare_sales` | 47 ok EC=0 | |
| `test_ask_embed_native` | **ENV** EC=1 | помечен, не чинить |
| `test_focus_loop` | **ENV** EC=1 | помечен, не чинить |

### 1.1 Красные — последние 5 строк

**`test_measure_empty`** (тракт-замок, не ENV):

```
Traceback (most recent call last):
  File ".../test_measure_empty.py", line 41, in <module>
    t("row all-zero: Сумма", A.measure_row_all_zero(totals[0]))
AttributeError: module 'serene_ask' has no attribute 'measure_row_all_zero'
```

Разбор: `measure_row_all_zero` жил в `z16_veto_pick_entity.py:453`.
W1-z16: **ЖИВА ТОЛЬКО LEGACY** (legacy z20:3442/3445). В новом
`z20_ask_main_http.py` и прочих зонах ask/ после S1 — **0** упоминаний.
Атака «снесённое-живое» **не** подтверждается. Красный замок = не сужен
под вырез legacy-меры (W2-A1 §S2 foresaw `test_measure_empty`).

**`test_ask_embed_native`** (ENV):

```
    vec = A.embed_one("тестовый вопрос")
  File ".../z01_infra_trace_llm.py", line 761, in embed_one
    raise RuntimeError("эмбеддер недоступен: %s" % type(last).__name__)
RuntimeError: эмбеддер недоступен: KeyError
```

**`test_focus_loop`** (ENV):

```
    import mcp_ask as M
  File ".../openclaw/mcp_ask.py", line 42, in <module>
    from mcp.server.fastmcp import FastMCP
ModuleNotFoundError: No module named 'mcp'
```

---

## 2. Сверка «жива новому» (W2-A1 + X1 + R*)

Сводная таблица W2-A1 даёт **числа** тел по зонам, не поимённый список всех
живых. Атака свела обязательный набор к: (а) щели §1 W2-A1; (б) ложные
«мёртвые» W2-R1/R2; (в) внешние Load нового z20 из W1-X1.

### 2.1 Щели W2-A1 + R-поправки — все на диске

| символ | реестр | после S1 |
|---|---|---|
| `fork_labels_of` | W2-A1 z09 щель | `z21_wiki_choice.py:476` |
| `fork_labels_covering` | W2-R1/R2: ложный L → жив | `z21_wiki_choice.py:501` |
| `atom_terminal_gate_text` | W2-A1 z13 | `z15_answer_atoms.py:436` |
| `stock_balance_is_sales_noise` | W2-A1 z13 | `z15_answer_atoms.py:452` |
| `pair_slots_only` | W2-A1 z16 | `z02_intent.py:214` |
| `_NON_DATA_MARKERS` | W2-A1 z16 | `z02_intent.py:208` |
| `question_expects_accounting_data` | W2-A1 z16 | `z02_intent.py:370` |
| `_fork_sum_headline_pool` | W2-R2 ложный L | `z11_sales.py:277` |
| `_fork_headline_doc_measures` | W2-R2 ложный L | `z11_sales.py:269` |
| `_measures_by_src` | S1 вынос | `z08_measures_totals.py:277` |
| `_fork_figures_of` | S1 вынос | `z15_answer_atoms.py:467` |
| `mk_opts` / wiki captions / `render_atom_pair` / … | W2-R2 | на месте (z20/z21/z15) |

MISS по этому набору: **0**. Runtime `load_all`: все hasattr=True.

### 2.2 W1-X1 — 149 внешних символов нового z20

- `_imports`/stdlib: 13 (на месте в `_imports.py`).
- zone-owned: **0 missing**.
- Relocated (бывший владелец снесён — тело вынесено):
  - `atom_terminal_gate_text`: было `z13:411` → `z15:436`
  - `fork_labels_covering`: было `z09:721` → `z21:501`
- `CORPUS`/`INDEX`/`TABLES`: tuple-assign `z01:25` (ложный MISS у Name-only AST).

### 2.3 Умышленно снесённое (не живое новому)

Файлы GONE: `z09_fork_detector.py`, `z13_fork_outcomes.py`,
`z16_veto_pick_entity.py`, `z20_ask_main_http_legacy.py`.
Образцы только-legacy/мёртвых (`fork_detector_scan`, `resolve_fork_outcome`,
`pick_measure`, `fork_outcome_*`, `measure_row_all_zero`) — **отсутствуют**
в ns. Согласуется с реестром сноса, не с «жива новому».

---

## 3. Транзитивные щели — фактические вызовы

| щель | def | кто зовёт (Call Name) |
|---|---|---|
| `fork_labels_of` / `covering` | **в** `z21` | `of` ← `z04b_currency_axis.py:548+`; `covering` ← `z20.mk_opts:1076`. Из тела z21 **Call нет** (только def) — норма: щель вынесена *в* z21, потребители снаружи |
| `question_expects_accounting_data` | `z02` | **из z21** `:1055` (wiki hybrid) |
| `atom_terminal_gate_text` | `z15` | `z20` `:1807` (`_onepath_compose_gate`) |
| `stock_balance_is_sales_noise` | `z15` | `z12` `:734,:904,:992,:996` |
| `pair_slots_only` | `z02` | `z18_compose.py:646` |
| headline-pool | `z11` | внутри `z11` (`sales_money_measure` ← `_fork_sum_headline_pool`) |
| `_measures_by_src` | `z08` | `z05_entity_form.py:1062` |

Цепочки W2-R* (wiki→covering, compose→terminal, currency→labels,
sales_money→headline) **не порваны**.

---

## 4. `_bootstrap` и флаги

- `_ZONE_FILES`: z01…z08, z10–z12, z14–z15, z17–z19, z21–z22, один `_Z20_FILE`
  (`z20_ask_main_http.py`). **Без** z09/z13/z16/legacy.
- `_exec_zone`: только AST-срез + `exec`; **нет** условия патча /
  ветки legacy (патч-вызов из load убран).
- `_patch_z20_wiki_primary`: остаётся **identity** (`return text`) — зовут
  замки (`test_wiki_*`, `zone_names`); не ветвит тракт.
- `ASK_LEGACY` / `ASK_ONEPATH` / `_ONEPATH`:
  - в `ask/_bootstrap.py` — **нет**;
  - в `ubuntu/serenedb/**/*.py` — только *строка ожидания* в
    `test_zone_names_resolvable` («не должно быть»);
  - в `ubuntu/serenedb/systemd/*` и env.example — **нет**;
  - упоминания в `docs/audit/onepath/*` / графе — история аудита, не runtime.

Слово «legacy» в bootstrap — только комментарий S1.

---

## 5. Вердикт атаки

| вопрос | ответ |
|---|---|
| Снесённое-живое (новый тракт)? | **Нет. Список пуст.** |
| Щели вынесены и зовутся? | Да (таблица §3) |
| X1 внешние имена? | 149/149 резолвятся |
| Bootstrap без legacy-ветки? | Да |
| ASK_LEGACY/ONEPATH в коде/юнитах? | Нет (runtime) |

**Не путать с долгом замков:** `test_measure_empty` красный на
legacy-only символе (`W1-z16.md:47` `measure_row_all_zero`). Это не
доказательство сноса живого пути; чинить замок — вне scope SR1.

ENV (помечены, не чинить): `test_ask_embed_native`, `test_focus_loop`.

Имя в списке задачи `test_verify_threshold` → фактически
`test_verify_threshold_menu.py` (**4/0**).

---

## Источники замера

- `docs/audit/onepath/W1-X1.md`, `W2-A1.md`, `W2-R1.md`, `W2-R2.md`, `W2-R3.md`,
  `W1-z16_veto_pick_entity.py.md` (только для квалификации `measure_row_all_zero`)
- `ubuntu/serenedb/ask/*` (AST def + Call; `load_all` smoke)
- прогоны `/tmp/sr1-red/*.out` (локально, 12.09)
