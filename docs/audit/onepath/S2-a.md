# S2-a — Поимённый план сноса мёртвого (смешанные зоны после S1)

Дата: 12.09.2026. Режим: **read-only**. Код / git / psql / полигон / прод не
менялись. Чужие `S2-*.md` не читались.

Источники: `W2-A1.md` §4 шаги **S3–S5** + поимённый cut §2.1; сверка
`W2-A2`/`W2-A3` §2.2; правки живости `W2-R1`/`R2`/`R3`; красные
`SR1-red`/`SR2-red` (**149/149** внешних X1 на месте); замки — `W1-X3`.
Доказательства мёртвости — AST + grep Name/Call/`getattr`/`globals().get` по
`ubuntu/serenedb/ask/*.py` и `test_*.py`, BFS от внешних имён `W1-X1` +
`answer` / wiki-cascade.

---

## Вердикт одной строкой

После S1 (legacy z20 + z09/z13/z16 снесены) в смешанных/живых зонах остаётся
**119 символов / 2160 строк тел** к посимвольному удалению (S3+S4). Не трогать:
щели SR1/X1, три silent-выбирателя (отдельный контракт), живые соседи в z05/z12.
S5 — только замки (`test_zone_names_resolvable`, `test_one_path`) + прогон.

---

## 0. Рамка задачи

| шаг W2-A1 §4 | содержание для S2-a |
|---|---|
| **S3** | Крупные смешанные: z05, z06, z11, z12, z17 |
| **S4** | Мелочь «нужных» зон: z01, z03, z04/z04b, z07, z08, z10, z14, z15, z18, z21 |
| **S5** | Правка замков / чёрных списков; полный `test_one_path` (не вырез кода) |

Уже сделано S1 (не повторять): `z20_*_legacy`, `_patch_z20_wiki_primary`, файлы
z09/z13/z16; щели вынесены (см. §2 «не трогать»).

Сверка объёма с реестром W2 (~2.2k L+D смешанных): кандидаты на диске **2200**
строк тел → минус живые тела z02 (38, бывшие «затенения») и минус щель
`_FORK_MEAS_*` (2, см. §2) → **2160** к удалению.

Пересечений списка удаления с **149** внешними X1: **0**.

---

## 1. Итоговый список к удалению

### 1.1 Сводка

| волна | зоны | символов | строк тел (AST) |
|---|---|---:|---:|
| **S3** | z05, z06, z11, z12, z17 | 65 | **1536** |
| **S4** | z01, z03, z04, z04b, z07, z08, z10, z14, z15, z18, z21 | 54 | **624** |
| **Σ** | | **119** | **2160** |

По файлам:

| зона | # | строк | доказательство (класс) |
|---|---:|---:|---|
| `z05_entity_form.py` | 27 | 625 | нет live-caller из X1/`answer`; зовы только внутри мёртвой entity-form/event-цепи + замки |
| `z12_stock_balance.py` | 20 | 417 | warehouse/goods/breakdown/bridge — вне `aggregate_stock_net_*` / settle |
| `z06_entity_search.py` | 6 | 211 | children/partial/date_only + model-suffix; `_fetch` только из мёртвого `signal_terms` |
| `z10_rank.py` | 7 | 176 | leader/period-clarify/theme-pick; только тесты / мёртвые соседи |
| `z11_sales.py` | 6 | 152 | lift/rank/canon/ticket/groups; live sales = money/qty/headline щели |
| `z17_aggregate_groups.py` | 6 | 131 | holders/live-count/measures_of_many — только мёртвый entity_form |
| `z14_clarify_memory.py` | 9 | 100 | diverge/fp/guards/reset — прод не зовёт; suite зовёт напрямую |
| `z04b_currency_axis.py` | 5 | 73 | prefer/patch/sum/class basis — legacy fork; live `_sql_ident` z04b **оставить** |
| `z03_period_windows.py` | 4 | 68 | window/prefer/apply leaders |
| `z15_answer_atoms.py` | 3 | 48 | stop2/rivals/PROOF_NA |
| `z07_rrf_vectors.py` | 3 | 38 | signal_terms + пустые CLARIFY_SYS/clarify_text (0 callers; z20 — только комментарий) |
| `z18_compose.py` | 3 | 38 | merge_period2 / _filled_ask / _ask_back |
| `z04_calendar_axis.py` | 3 | 36 | day_basis prefer + **затёртый** `_sql_ident` (тело z04; runtime — z04b) |
| `z21_wiki_choice.py` | 1 | 21 | `wiki_leader_alive` |
| `z01_infra_trace_llm.py` | 6 | 16 | мёртвые константы + test-only reload/preview |
| `z08_measures_totals.py` | 10 | 10 | осиротевшие флаги fork/veto/alias (нет Load в ask/) |

### 1.2 Поимённо — S3

Формат: `символ | зона:строки | строк | кто НЕ зовёт / кто зовёт мёртвое`

#### z05_entity_form.py — 625

| символ | строки | n | доказательство мёртвости |
|---|---|---:|---|
| `register_count_src` | 378–414 | 37 | нет live-caller; упоминания в мёртвых `sales_canon_intent` / `count_theme_code_pick_applies` + тесты |
| `entity_form_count_target_is_movement` | 417–452 | 36 | только `entity_form_applicable` / `register_count_src` (оба DEL) |
| `entity_form_expand_pool` | 455–475 | 21 | только `test_entity_form` |
| `event_kind_catalog_expand_pool` | 478–518 | 41 | только `test_no_pre_wiki_reorders` |
| `entity_form_rolling_year` | 521–531 | 11 | только self-цепь entity_form |
| `entity_form_gate_open` | 534–552 | 19 | тесты + name в `test_one_path` |
| `entity_form_applicable` | 555–593 | 39 | только `test_entity_form` |
| `entity_form_collapse_guard` | 596–609 | 14 | только `test_entity_form` |
| `entity_form_pre_entity_ok` | 612–626 | 15 | только `try_entity_form_answer` (DEL) + getattr в тесте |
| `entity_form_atom_distinct` | 629–639 | 11 | только тесты |
| `entity_form_atom_complement` | 642–658 | 17 | только тесты |
| `event_count_has_explicit_period` | 759–769 | 11 | self-цепь event-clarify |
| `event_count_period_unspecified` | 772–777 | 6 | self |
| `event_count_has_live_axis` | 780–801 | 22 | self |
| `event_count_period_clarify_applies` | 804–814 | 11 | self |
| `event_count_period_option_readings` | 817–837 | 21 | `event_count_period_clarify` / `try_rank_period_clarify` (оба DEL) |
| `event_count_period_clarify` | 840–863 | 24 | self-цепь |
| `try_event_count_period_clarify` | 866–922 | 57 | только `test_one_path` (чёрный список) |
| `event_duel_applies` | 946–962 | 17 | `test_action_class` |
| `_event_distinct_fork_rows` | 965–992 | 28 | никто вне файла |
| `event_movement_feats` | 999–1000 | 2 | никто |
| `event_filter_pool` | 1003–1005 | 3 | никто |
| `entity_form_axis_on_sales` | 1039–1068 | 30 | тесты; единственный caller `_measures_by_src` (щель — не в DEL, §2) |
| `entity_form_structs` | 1071–1129 | 59 | `entity_form_pick` / `try_entity_form_answer` |
| `entity_form_pick` | 1132–1142 | 11 | тесты |
| `entity_form_compute` | 1145–1174 | 30 | тесты |
| `try_entity_form_answer` | 1177–1208 | 32 | тесты + `test_one_path` |

**Рядом, но НЕ удалять (живые в том же файле):** `_pick_kind_axis_col` (663+),
`live_axis_col_for_count` (698+, X1), `entity_form_catalogs_for_kind` (293+,
wiki/`kind_axis`/stock), `aggregate_compare_sales` (1211+).

#### z06_entity_search.py — 211

| символ | строки | n | доказательство |
|---|---|---:|---|
| `_fetch` | 20–32 | 13 | Load только из мёртвого `signal_terms` (z07) |
| `children_by_parent` | 220–270 | 51 | только `test_step2` |
| `partial_tables` | 273–350 | 78 | никто в ask/тестах |
| `date_only_kind_filter` | 372–388 | 17 | никто |
| `entity_pick_counts_for_model` | 548–577 | 30 | `test_k6_rank_v2` |
| `entity_matching_records_suffix` | 580–601 | 22 | `test_k6_rank_v2` |

#### z11_sales.py — 152

| символ | строки | n | доказательство |
|---|---|---:|---|
| `_sales_register_score` | 79–94 | 16 | только `entity_form_axis_on_sales` (DEL) |
| `sales_lift_possible` | 97–141 | 45 | self / legacy |
| `sales_rank_engaged` | 144–171 | 28 | только `test_sales_*` |
| `rank_groups_answer_text` | 209–237 | 29 | `test_unit_from_data` |
| `sales_canon_intent` | 240–266 | 27 | нет live-caller |
| `sales_ticket_hatch` | 341–347 | 7 | никто |

**Не трогать в z11:** `_fork_sum_headline_pool`, `_fork_headline_doc_measures`,
`sales_money_measure` / `sales_qty_measure` (SR1 щели / live settle).

#### z12_stock_balance.py — 417

| символ | строки | n | доказательство |
|---|---|---:|---|
| `_catalogs_joint_with_kind` | 203–228 | 26 | никто |
| `question_asks_stock_balance` | 390–392 | 3 | только тесты k4/rank_axis |
| `axis_catalog_values` | 472–549 | 78 | `test_warehouse_aggregate_breakdown` |
| `warehouse_axis_values` | 552–562 | 11 | `test_warehouse_axis_autonomy` |
| `warehouse_axis_is_live` | 565–571 | 7 | self |
| `stock_skips_warehouse_clarify` | 574–586 | 13 | warehouse-тест |
| `stock_subject_needs_clarify` | 622–633 | 12 | только k4-тесты (getattr) |
| `_rank_wants_quantity` | 645–657 | 13 | `test_rank_axis_anchor` |
| `rank_measure_hint` | 660–674 | 15 | тесты (зовёт `measure_choice` — сам measure_choice жив) |
| `_stock_expense_side_penalty` | 842–844 | 3 | никто |
| `stock_goods_pool` | 847–865 | 19 | self |
| `filter_stock_goods_registers` | 868–882 | 15 | `test_final_stock_route_filters_absent` |
| `stock_canon_src` | 1065–1077 | 13 | stock/wiki тесты |
| `prefer_entity_for_stock` | 1080–1094 | 15 | final_stock-тест |
| `_resolve_breakdown_balance_src` | 1160–1179 | 20 | self breakdown |
| `_breakdown_fallback_measure` | 1182–1200 | 19 | self |
| `stock_breakdown_leader_fallback` | 1203–1256 | 54 | warehouse / no_pre_wiki тесты |
| `_balance_map_by_src` | 1259–1265 | 7 | self |
| `filter_balance_structural` | 1268–1307 | 40 | `test_stock_balance_path` |
| `balance_bridge_clarify` | 1310–1343 | 34 | `test_k4_meta_names` |

**Не трогать в z12:** `stock_net_register_pair` (962+), `aggregate_stock_net_distinct`
(X1), `stock_balance_is_sales_noise` (живёт в z15 после S1), живые stock settle.

#### z17_aggregate_groups.py — 131

| символ | строки | n | доказательство |
|---|---|---:|---|
| `_live_ref_key_col` | 86–99 | 14 | self live-count |
| `aggregate_live_row_count` | 102–127 | 26 | `test_aggregate_live_flags` |
| `aggregate_live_header_count` | 130–159 | 30 | `test_aggregate_live_flags` |
| `holders_of_target` | 387–404 | 18 | только мёртвые entity_form_* (W2-R1 soft-ложь «жив») |
| `measures_of_many` | 407–422 | 16 | никто |
| `term_ref_owners` | 495–521 | 27 | никто |

**Не трогать:** `kind_axis_hits`, `term_axis_hits` (X1 / `_settle_axis`).

### 1.3 Поимённо — S4

#### z01 — 16

| символ | строки | n | доказательство |
|---|---|---:|---|
| `TERMS_FOR` | 51 | 1 | нет Load |
| `TERMS_TOP` | 60 | 1 | нет Load |
| `ORDER_BY_MEANING` | 174 | 1 | нет Load |
| `RERANK_TOP` | 200 | 1 | только комментарий в z08 |
| `_reload_embed_native_env` | 275–281 | 7 | только embed-тесты |
| `_gate_bad_preview` | 443–447 | 5 | `test_rank_axis_anchor` |

#### z03 — 68

| символ | строки | n | доказательство |
|---|---|---:|---|
| `render_window_label` | 352–370 | 19 | только мёртвые event/rank period-clarify |
| `_WINDOW_LEADER_FORMS` | 374 | 1 | self prefer |
| `prefer_window_leader` | 377–393 | 17 | `test_one_path` blacklist |
| `apply_period_leader` | 581–611 | 31 | `test_one_path` blacklist |

#### z04 — 36

| символ | строки | n | доказательство |
|---|---|---:|---|
| `_sql_ident` | 9–11 | 3 | **затёрт** z04b; live тело — z04b:20 (KEEP) |
| `calendar_day_basis_prefer` | 186–207 | 22 | нет live-caller |
| `prefer_day_basis_leader` | 252–262 | 11 | нет live-caller |

#### z04b — 73 (без live `_sql_ident`)

| символ | строки | n | доказательство |
|---|---|---:|---|
| `currency_amount_basis_prefer` | 158–183 | 26 | legacy |
| `prefer_amount_basis_leader` | 273–283 | 11 | мёртва |
| `currency_sum_for_basis` | 396–403 | 8 | legacy |
| `currency_patch_fork_scan` | 406–425 | 20 | legacy fork |
| `_class_amount_basis` | 557–564 | 8 | legacy |

#### z07 — 38

| символ | строки | n | доказательство |
|---|---|---:|---|
| `signal_terms` | 249–282 | 34 | 0 callers (кроме мёртвого `_fetch`) |
| `CLARIFY_SYS` | 287 | 1 | `=""`; `test_one_path`; комментарий в z20 ≠ Call |
| `clarify_text` | 290–292 | 3 | stub `return ""`; 0 Call |

#### z08 — 10 (флаги без `_FORK_MEAS_*`)

| символ | строки | n | доказательство |
|---|---|---:|---|
| `ALIAS_TOP` | 32 | 1 | нет Load в ask/ |
| `ALIAS_VETO` | 68 | 1 | нет Load |
| `PROBE` | 75 | 1 | только ab-тесты |
| `SKIP_SERVICE_RIVALS` | 79 | 1 | нет Load |
| `ALIAS_BY_CONCEPTS` | 91 | 1 | нет Load |
| `VETO_NEEDS_RANK` | 106 | 1 | нет Load |
| `VETO_HEAD_WINS` | 116 | 1 | нет Load |
| `FORK_DETECT` | 251 | 1 | нет Load |
| `FORK_OUTCOMES` | 252 | 1 | нет Load |
| `ASK_MEMORY_APPLY` | 262 | 1 | нет Load |

#### z10 — 176

| символ | строки | n | доказательство |
|---|---|---:|---|
| `rank_leader_answer_text` | 112–132 | 21 | unit/rank тесты |
| `rank_product_axis_col` | 303–306 | 4 | никто live |
| `rank_leader_atom` | 309–340 | 32 | unit/rank тесты |
| `count_theme_code_pick_applies` | 343–398 | 56 | entity_form/k6 тесты |
| `rank_period_unspecified` | 402–413 | 12 | self clarify |
| `rank_period_clarify_applies` | 416–439 | 24 | rank_leader/k6 тесты |
| `try_rank_period_clarify` | 442–468 | 27 | никто live |

#### z14 — 100

| символ | строки | n | доказательство |
|---|---|---:|---|
| `slot_measure_uncovered` | 142–150 | 9 | legacy |
| `_FP_SKIP` | 163 | 1 | self `_slot_fp` |
| `_FP_STR` | 164 | 1 | self |
| `_slot_fp` | 167–185 | 19 | только `answers_diverge` (DEL) + a3-тест |
| `answers_diverge` | 188–221 | 34 | compose/a3/gate тесты |
| `answers_src_conflict` | 223–238 | 16 | a3-тест |
| `RAW_FOCUS_TRUST` | 244 | 1 | `test_decision_id` |
| `reset_decisions_for_tests` | 565–570 | 6 | suite-хелпер (прод 0) |
| `guards_skip_for_choice` | 664–676 | 13 | только `stop2_active` (DEL) + decision_id |

**Не трогать:** `measure_choice` (30+, X1 / `_settle_measure`).

#### z15 — 48

| символ | строки | n | доказательство |
|---|---|---:|---|
| `stop2_active` | 9–19 | 11 | только decision_id-тесты |
| `determined_answer_rivals` | 22–57 | 36 | никто live |
| `PROOF_NA` | 184 | 1 | legacy |

**Не трогать:** `atom_terminal_gate_text`, `stock_balance_is_sales_noise`,
`_fork_figures_of` (щели S1).

#### z18 — 38

| символ | строки | n | доказательство |
|---|---|---:|---|
| `merge_period2_groups` | 9–24 | 16 | legacy |
| `_filled_ask` | 607–625 | 19 | legacy |
| `_ask_back` | 628–630 | 3 | `test_compose` |

#### z21 — 21

| символ | строки | n | доказательство |
|---|---|---:|---|
| `wiki_leader_alive` | 1227–1247 | 21 | wiki/no_pre_wiki тесты; cascade жив без него |

---

## 2. Подозрительные, но не трогать

| символ | где | причина |
|---|---|---|
| `question_expects_accounting_data` | z02:370–403 | **Щель S1** (бывш. z16). Live ← `try_wiki_hybrid_entity_pick` (z21). W2-A1 «мёртва затенением» **устарело** после выноса. SR1/SR2. |
| `_NON_DATA_MARKERS` | z02:208–211 | То же; кормит accounting_data / non-data. |
| `pair_slots_only` | z02:214+ | Щель S1; live ← z18 compose. |
| `fork_labels_of` / `fork_labels_covering` | z21 | Щели + **ложный L** W2-R1/R2; live wiki/`mk_opts`/currency. |
| `atom_terminal_gate_text` / `stock_balance_is_sales_noise` | z15 | Щели z13; live z20/z12. |
| `_fork_sum_headline_pool` / `_fork_headline_doc_measures` | z11 | Щели SR1; live sales_money. |
| `_measures_by_src` | z08:277+ | Щель S1. Сейчас единственный Call — мёртвый `entity_form_axis_on_sales`, но **не вырезать** в той же волне без отдельного решения (SR1 держит щель; риск getattr/`entity_form_catalogs`). |
| `_FORK_MEAS_TTL` / `_fork_meas_cache` | z08:273–274 | Кэш щели `_measures_by_src`. W2-A* помечал L — после S1 это инфраструктура щели. |
| `_sql_ident` (**z04b**) | z04b:20 | Live currency/calendar SQL. Удалять только копию **z04:9–11**. |
| `measure_choice` | z14:30 | **Silent-выбиратель** (>1 → silent). X1 / `_settle_measure`. Контракт → меню (не снос). |
| `_pick_kind_axis_col` | z05:663+ | Silent при >1 (rerank/`matched[0]`). Live ← `live_axis_col_for_count` (X1). |
| `stock_net_register_pair` | z12:962+ | Silent выбор регистра. Live ← `aggregate_stock_net_distinct` (X1). |
| `entity_form_catalogs_for_kind` | z05:293+ | Live wiki/stock/intent/kind_axis; сосед мёртвого блока. |
| `live_axis_col_for_count` | z05:698+ | X1. |
| `aggregate_compare_sales` (+ compare-хвост z05) | z05:1211+ | Живой compare; `test_compare_sales` — сужать, не сносить зону. |
| `kind_axis_hits` / `term_axis_hits` / `rank_axis_resolve` | z17/z10 | X1 settle. |
| `ASK_JOURNAL` | z08/z20 | Live журнал ответа. |
| Весь набор **149** X1 | — | SR1/SR2: 0 missing. Любое имя из X1 вне этой таблицы — стоп. |

Опечатки в реестре W2 (activeContext: «не считать») в объём 2160 не входили.

---

## 3. Порядок правки замков (по W1-X3 + факты grep)

Правило: сначала сузить/вырезать assert'ы на DEL-символы, потом код зоны,
потом S5-прогон. Пат-спек коммитов — по зонам S3→S4→S5.

### 3.1 Перед/вместе с S3 (крупные смешанные)

| порядок | замок | что править | X3 / факт |
|---:|---|---|---|
| 1 | `test_entity_form.py` | 15 DEL-имён (gate/applicable/structs/compute/try_*/expand/…); **оставить** compare + `entity_form_catalogs` / axis helpers | X3 z05; сильнейший замок волны |
| 2 | `test_compare_sales.py` | не удалять файл; убрать только entity_form-terminal, если остались | X3: z05+atoms |
| 3 | `test_sales_canon_prefer.py`, `test_sales_rank_canon.py` | снять `sales_rank_engaged` / legacy path | X3 §Б |
| 4 | `test_stock_balance_path.py` | `filter_balance_structural`, `stock_canon_src`, stubs subject | X3 z12 |
| 5 | `test_final_stock_route_filters_absent.py` | `filter_stock_goods_registers`, `prefer_entity_for_stock` — файл про «absent»: сузить до slit noise / удалить устаревшие assert'ы | X3 §В |
| 6 | `test_warehouse_aggregate_breakdown.py`, `test_warehouse_axis_autonomy.py` | axis_catalog / warehouse_values / breakdown_fallback / skips | X3 z12 |
| 7 | `test_aggregate_live_flags.py` | `aggregate_live_*` | X3 z17 |
| 8 | `test_step2.py` | `children_by_parent` | X3 z06 |
| 9 | `test_k4_axis_and_names.py`, `test_k4_guess_vs_clarify.py`, `test_k4_meta_names.py` | stock_subject / question_asks / balance_bridge | X3 §Б/В |
| 10 | `test_k6_rank_v2.py` | entity_pick_counts / matching_suffix / theme_pick / period_clarify | X3 z06/z10 |
| 11 | `test_action_class.py` | `event_duel_applies` (и уже выхолощенные fork-части) | X3 |
| 12 | `test_no_pre_wiki_reorders.py` | `event_kind_catalog_expand_pool`, `stock_breakdown_leader_fallback`, `wiki_leader_alive` | X3 §В — часть ещё про wiki |

`test_fork_*` / veto-армия: после S1 уже без z09/z13/z16; при S3 не
расширять — только если всплывут имя из DEL.

### 3.2 Вместе с S4 (мелочь)

| порядок | замок | DEL-символы |
|---:|---|---|
| 13 | `test_rank_leader_path.py`, `test_rank_axis_anchor.py` | rank_leader_*, period_clarify, rank_measure_hint, question_asks_stock, _gate_bad_preview, _rank_wants_quantity |
| 14 | `test_unit_from_data.py` | rank_leader_*, rank_groups_answer_text |
| 15 | `test_compose.py`, `test_a3_passport.py`, `test_gate.py` (точечно) | answers_diverge / _slot_fp / _ask_back |
| 16 | `test_decision_id.py`, `test_ask_choice_memory.py`, `test_ask_journal.py`, `test_terminal_round.py` | reset_decisions_for_tests, stop2_active, RAW_FOCUS_TRUST, guards_skip |
| 17 | `test_wiki_leader_not_overridden.py`, `test_wiki_card_hybrid.py` | wiki_leader_alive; register_count_src / stock_canon_src (если ещё) |
| 18 | `test_ai_embed_question.py`, `test_ask_embed_native.py` | `_reload_embed_native_env` — переписать на публичный API или снять |
| 19 | `test_ab_ambiguous_set.py`, `test_ab_calendar_axis_set.py` | `PROBE` (если assert на константу) |

### 3.3 S5 — финал замков

| порядок | замок | действие |
|---:|---|---|
| 20 | `test_zone_names_resolvable.py` | Вычеркнуть снесённые имена (X3 §Г). После S1 уже без z09/13/16/legacy — дочистить S3/S4 имена. |
| 21 | `test_one_path.py` | Обновить чёрные списки / упоминания: `try_entity_form_answer`, `try_event_count_period_clarify`, `entity_form_gate_open`, `prefer_window_leader`, `apply_period_leader`, `CLARIFY_SYS`; проверки (а)–(г) контракта — полные. X3 §Д: замок жив. |
| 22 | Прогон | `test_one_path` + контрольные L67; замки one_path/zone/compose/captions — зелёные до выката. |

### 3.4 Чего не делать в S2-a

- Не удалять / не «чинить меню» для `measure_choice`, `_pick_kind_axis_col`,
  `stock_net_register_pair` — это **следующий** эпизод (silent→меню).
- Не трогать 149 X1 и щели §2.
- Не сносить целиком z05/z12 — только поимённые тела из §1.

---

## 4. Метод замера (воспроизводимость)

1. Список кандидатов = W2-A1 §2.1 ∩ (S3∪S4 зоны) минус уже снесённые файлы.
2. AST span top-level def/assign на текущем дереве `ask/`.
3. BFS live от `W1-X1` ∪ `answer` ∪ wiki-cascade ∪ `mk_opts`.
4. Grep `(?<!\w)name(?!\w)` + `getattr`/`globals().get('name')` по ask/ + `test_*.py`.
5. Вердикт DEL: не в live-множестве **и** не в таблице §2.
6. Строки: сумма AST span тел DEL = **2160**; символов = **119**.

---

## 5. Итог для исполнителя S2-b (код)

1. Править замки по §3.1 → вырезать S3 (§1.2) пат-спеком по файлам.
2. Замки §3.2 → вырезать S4 (§1.3).
3. S5: `test_zone_names_resolvable` + полный `test_one_path` (а–г).
4. Красная сверка: снова 149/149 X1; щели §2 hasattr; L67.

**Числа:** DEL **119** символов / **2160** строк тел; KEEP-щели и выбиратели — §2;
замков с прямыми ссылками на DEL — **≥31** (таблица §3).
