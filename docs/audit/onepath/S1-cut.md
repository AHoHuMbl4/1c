# S1-cut — снос мёртвого груза, шаг 1

Дата: 12.09.2026. Реестр: `W2-A1` + поправки `W2-R1`/`W2-R2`/`W2-R3`.
Код: `ubuntu/serenedb/ask/`. Git-мутаций нет (оркестратор). Полигон/прод не трогались.

---

## 1. Щели (вынесены дословно)

| символ | откуда | куда | строк (AST) |
|---|---|---|---:|
| `fork_labels_of` | fork-detector | `z21_wiki_choice.py` | 23 |
| `fork_labels_covering` | fork-detector | `z21_wiki_choice.py` | 30 |
| `_fork_headline_doc_measures` | fork-detector | `z11_sales.py` | 6 |
| `_fork_sum_headline_pool` | fork-detector | `z11_sales.py` | 14 |
| `atom_terminal_gate_text` | fork-outcomes | `z15_answer_atoms.py` | 14 |
| `stock_balance_is_sales_noise` | fork-outcomes | `z15_answer_atoms.py` | 13 |
| `_fork_figures_of` | fork-outcomes | `z15_answer_atoms.py` | 26 |
| `pair_slots_only` | veto-pick | `z02_intent.py` | 6 |
| `_NON_DATA_MARKERS` | veto-pick | уже был в `z02_intent.py` (идентичен) | — |
| `question_expects_accounting_data` | veto-pick | уже был в `z02` (superset с conversational; после сноса тени z16 — он и есть runtime) | — |
| `_measures_by_src` | fork-detector | `z08_measures_totals.py` (кэш `_fork_meas_cache` уже там) | 23 |

**Почему headline / `_measures_by_src` / `_fork_figures_of` сверх списка задачи:**  
W2-R2 P0 — `_fork_sum_headline_pool` жив через `sales_money_measure` (~62 строки щели z09 вместе с labels). Без выноса `NameError` на горячем пути.  
`_measures_by_src` / `_fork_figures_of` — call-sites в смешанных z05/z12 (S3 не трогаем); иначе `test_zone_names_resolvable` красный и отложенный NameError.

Имена вызовов не менялись (общий `ns`).

---

## 2. Снесено (rm)

| файл | строк (было) |
|---|---:|
| `z09_fork_detector.py` | 1018 |
| `z13_fork_outcomes.py` | 925 |
| `z16_veto_pick_entity.py` | 625 |
| `z20_ask_main_http_legacy.py` | 5103 |
| **Σ файлов** | **7671** |

---

## 3. `_bootstrap.py`

- `_ZONE_FILES`: без трёх почти-мёртвых зон и без legacy z20; осталось **20** зон.
- `_Z20_FILE = "z20_ask_main_http.py"` безусловно; `ASK_LEGACY` / `_ONEPATH` сняты.
- `_patch_z20_wiki_primary` → `return text` (identity; ссылка W2/B7).
- Ветка патча в `_exec_zone` снята.
- Объём: **264 → 141** (−123).

---

## 4. Дифф-статистика (оценка)

| | строк |
|---|---:|
| − файлы сноса | −7671 |
| − bootstrap | −123 |
| + щели (сумма тел) | ≈+155 |
| **Σ нетто** | **≈ −7639** |

На диске `ask/z*.py`: было 23 файла (с legacy), стало **20**.

---

## 5. Замки

### Тракт (прогон S1) — **32/0 зелёные**

`test_one_path`, `test_zone_names_resolvable`, `test_enough`, `test_final_stock_route_filters_absent`, `test_early_clarify_atom_fps_hashable`, `test_measure_hatch_luk`, `test_measure_menu_not_silent`, `test_wiki_leader_not_overridden`, `test_axis_count_plain`, `test_no_pre_wiki_reorders`, `test_sales_canon_prefer`, `test_ask_choice_memory`, `test_fork_*` (некрологи), `test_atom_terminal`, `test_answer_atom`, `test_step4_guards`, `test_leader_hatch`, `test_wiki_card_hybrid`, `test_rank_leader_path`, `test_action_class`, `test_gate`, `test_calendar_axis`, `test_currency_axis`, `test_axis_focus` (некролог W2), `test_intent`, `test_stock_balance_path`, `test_k4_clarify_vs_nodata`, `test_warehouse_axis_autonomy`.

Правки замков: path legacy→новый z20; fork/veto-замки → некрологи «символа нет» + smoke щелей; `test_zone_names_resolvable` — один тракт / identity-патч.

### Окруженческие (помечены, не чинить)

| замок | причина |
|---|---|
| `test_ask_embed_native` | эмбеддер недоступен (`KeyError` / RuntimeError) |
| `test_focus_loop` | нет модуля `mcp` (`ModuleNotFoundError`) |

### Проверки

- `py_compile` правленых — OK  
- `load_all()` — OK (783 символа в ns)  
- `grep` имён снесённых файлов в `ask/` + `test_*.py` — **чисто**

---

## 6. Не в этом шаге

Смешанные зоны (z05/z12/…) — волна S3. Скрытые выбиратели (`measure_choice`, `stock_net_register_pair`, …) — продуктовый долг, не снос. Выкат на прод — оркестратор.
