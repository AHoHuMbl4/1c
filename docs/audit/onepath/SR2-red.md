# SR2 — КРАСНАЯ: снёс ли S1 что-то живое

Дата: 12.09.2026. Режим: read-only + локальные прогоны замков + один отчёт.
Код/git/psql/полигон/прод не трогались. Чужие `SR*.md` не читались.

Цель атаки: найти **снесённое-живое**, а не подтвердить снос.

Реестры: `W1-X1.md` (внешние Load нового z20), `W2-A1.md` §жива/щели,
поправки `W2-R1`/`W2-R2`/`W2-R3`.

---

## Вердикт одной строкой

**Снос чист для нового тракта.** Снесённого-живого по реестрам X1 / щелям W2 /
R1–R3 **не найдено**. Красные замки — долг окружения или некролог-legacy, не дыра
в hot-path.

---

## 1. Прогон замков тракта

Запуск: `python3 <test_*.py>` из `ubuntu/serenedb/` (не pytest-pipe — иначе
exit-код глушится `tail`). Логи: `/tmp/sr2-red2/`.

| файл | итог | хвост при красном / примечание |
|---|---|---|
| `test_one_path.py` | **41/0** | |
| `test_zone_names_resolvable.py` | **96/0** | |
| `test_enough.py` | PASS (9 ok) | |
| `test_no_pre_wiki_reorders.py` | **39/0** | |
| `test_measure_hatch_luk.py` | PASS (16 ok) | |
| `test_measure_menu_not_silent.py` | **11/0** | |
| `test_axis_count_plain.py` | PASS (13 ok) | |
| `test_wiki_leader_not_overridden.py` | **10/0** | |
| `test_wiki_card_hybrid.py` | PASS (65 ok) | |
| `test_ask_choice_memory.py` | PASS (45 ok) | |
| `test_ask_journal.py` | PASS | live-кусок skip (нет движка) |
| `test_journal_fields.py` | PASS (22 ok) | |
| `test_gate.py` | PASS (56 ok) | |
| `test_compose.py` | PASS (93 ok) | |
| `test_period_empty.py` | **30/0** | явно: `build_measure_empty_pivot` снесён |
| `test_health_gap.py` | **23/0** | |
| `test_health_native_freshness.py` | **32/0** | |
| `test_health_tick_status.py` | **14/0** | |
| `test_intent.py` | **162/0** | |
| `test_final_stock_route_filters_absent.py` | **9/0** | slit noise жив |
| `test_sales_canon_prefer.py` | **29/0** | |
| `test_rank_leader_path.py` | PASS (28 ok) | |
| `test_early_clarify_atom_fps_hashable.py` | **4/0** | некролог early-clarify |
| `test_verify_threshold*` | **4/0** | имя на диске: `test_verify_threshold_menu.py` (не `test_verify_threshold.py`) |
| `test_named_type_filter.py` | PASS (16 ok) | |
| `test_wiki_candidate_verify.py` | PASS (64 ok) | |
| `test_wiki_captions_builder.py` | **24/0** | |
| `test_k4_meta_names.py` | **15/0** | |
| `test_decision_id.py` | PASS (30 ok) | |
| `test_answer_atom.py` | **5/0** | |
| `test_atom_terminal.py` | **5/0** | |
| `test_caveat.py` | PASS | |
| `test_b9_routing.py` | PASS (7 ok) | |
| `test_rank_axis_anchor.py` | PASS (66 ok) | |
| `test_sales_rank_canon.py` | **18/0** | |
| `test_trace_rid.py` | PASS (10 ok) | |
| `test_terminal_round.py` | **24/0** | |
| `test_action_class.py` | **8/0** | |
| `test_k4_guess_vs_clarify.py` | **12/0** (+3 pending) | |
| `test_k4_clarify_vs_nodata.py` | **7/0** | |
| `test_axis_focus.py` | **3/0** | некролог axis_focus |
| `test_stock_balance_path.py` | **36/0** | |
| `test_step4_guards.py` | **27/0** | |
| `test_step2.py` | **38/0** | |
| `test_measure_empty.py` | **FAIL** | см. §1.1 |
| `test_post_gate_none_src.py` | **6/0** | |
| `test_fork_label_daybasis.py` | **27/0** | некролог+щели |
| `test_fork_atom_aggregate.py` | **27/0** | некролог S1 |
| `test_warehouse_axis_autonomy.py` | **4/0** | |
| `test_warehouse_aggregate_breakdown.py` | PASS (5 ok) | |
| `test_leader_hatch.py` | **27/0** | |
| `test_compare_sales.py` | **47/0** | |
| `test_ask_embed_native.py` | **FAIL (env)** | помечено, не чинить |
| `test_focus_loop.py` | **FAIL (env)** | помечено, не чинить |

### 1.1 Красные — разбор атаки

**`test_measure_empty.py`** — AttributeError: нет `measure_row_all_zero` (и далее
семейство `alive_measure_names` / `filter_dead_measure_alts` /
`build_measure_empty_pivot` / …).

Атака: это **не** снесённое-живое тракта.

| источник | вердикт символу |
|---|---|
| `W1-z16` | `measure_row_all_zero` = **ЖИВА ТОЛЬКО LEGACY** |
| `W2-A1` §2.1 z16 | «Снести: … measure_empty/…» |
| новый `ask/` | 0 call-site этих имён; в `ns` отсутствуют |
| `test_period_empty` | зелёный и сам фиксирует снос пивота |

Итог: замок не переписан в некролог (в отличие от `test_fork_*` / `test_step4_guards`).
Долг замка, не дыра hot-path.

**`test_ask_embed_native.py`** — последние 5:

```
ok  - ASK_EMBED_NATIVE exists
ok  - default ASK_EMBED_NATIVE off
…
RuntimeError: эмбеддер недоступен: KeyError
  (z01 embed_one)
```

**`test_focus_loop.py`** — последние 5:

```
ModuleNotFoundError: No module named 'mcp'
  (import mcp_ask → openclaw/mcp_ask.py)
```

Оба — окружение сессии, не следствие сноса зон.

---

## 2. Сверка «жива новому»

### 2.1 W1-X1 — все 149 внешних символов

`load_all()` → каждый символ реестра X1 **присутствует в `ns`**.
Бывшие владельцы z09/z13 для Load нового z20 переехали:

| символ (X1) | было | сейчас |
|---|---|---|
| `fork_labels_covering` | `z09:721` | `z21_wiki_choice.py:501` |
| `atom_terminal_gate_text` | `z13:411` | `z15_answer_atoms.py:436` |

Прочие владельцы X1 не сносились (зоны на диске). `_imports`-seed
(`ACM`, `PV`, `serene_axis`, …) и константы z01 (`CORPUS`/`INDEX`/`TABLES`) —
в `ns` через seed/exec.

### 2.2 W2-A1 тонкие щели + правки R1/R2

| символ | реестр | def после S1 | отсутствие? |
|---|---|---|---|
| `fork_labels_of` | W2-A1 щель z09; R2 жив | `z21:476` | нет |
| `fork_labels_covering` | X1 + R1/R2 (через mk_opts←wiki) | `z21:501` | нет |
| `atom_terminal_gate_text` | щель z13 | `z15:436` | нет |
| `stock_balance_is_sales_noise` | щель z13 | `z15:452` | нет |
| `pair_slots_only` | щель z16 | `z02:214` | нет |
| `_NON_DATA_MARKERS` | щель z16 | `z02:208` | нет |
| `question_expects_accounting_data` | щель z16 | `z02:370` | нет |
| `_fork_sum_headline_pool` | R2 (было L в W1-z09) | `z11:277` | нет |
| `_fork_headline_doc_measures` | R2 | `z11:269` | нет |
| `_measures_by_src` | S1 вынос | `z08:277` | нет |
| `_fork_figures_of` | S1 вынос | `z15:467` | нет |
| `mk_opts` | R1/R2 callee wiki | `z20:1059` | нет |
| `wiki_menu_captions` / `wiki_captions_map_from_cards` / `wiki_passport_enrich` | R1/R2 | z21 | нет |
| `render_atom_pair` | R2 | z15 | нет |

Сводная «жива новому» по зонам W2-A1 (представители critical-path X1 §4 +
щели): **missing = NONE**. Снесённые файлы на диске отсутствуют:
`z09`/`z13`/`z16`/`z20_*_legacy.py`.

---

## 3. Транзитивные щели (фактические зовы)

| щель | кто зовёт (grep Call, не def) | ок? |
|---|---|---|
| `fork_labels_of` | `z04b_currency_axis.py:548,551` (валютные подписи) | да — дом z21, потребитель оси |
| `fork_labels_covering` | `z20.mk_opts:1076` ← `z21.try_wiki_hybrid_entity_pick:1106` | да — цепь R1/R2 жива |
| `atom_terminal_gate_text` | `z20:1807` (`_onepath_compose_gate`) | да |
| `stock_balance_is_sales_noise` | `z12:734,904,992,996` | да |
| `pair_slots_only` | `z18_compose.py:646` | да |
| `question_expects_accounting_data` | `z21:1055` (wiki) | да |
| `_fork_sum_headline_pool` / `_fork_headline_doc_measures` | внутри `z11` (`sales_money_measure`) | да |
| `_measures_by_src` | `z05_entity_form.py:1062` | да |
| `_fork_figures_of` | `z05:1204`, `z12:1250` | да |

Вопрос задания «вызываются ли labels из z21?»: covering — **да** (wiki→mk_opts);
`fork_labels_of` живёт в z21, зов с z04b (не из тела z21) — для щели достаточно.

---

## 4. `_bootstrap` / флаги

| проверка | факт |
|---|---|
| `_ZONE_FILES` без z09/z13/z16/legacy | да (20 зон + новый z20) |
| `_Z20_FILE` безусловно `z20_ask_main_http.py` | да |
| `_exec_zone` без условия/зова патча | да (только slice+compile+exec) |
| `_patch_z20_wiki_primary` | identity `return text` (тесты ещё дергают) |
| `ASK_LEGACY` / `ASK_ONEPATH` в `ask/` | **0** |
| то же в `*.service`/`*.timer` репо | **0** |
| то же в `/etc/systemd/system/1c-*` | **0** |

Исторические упоминания флагов остаются в старых audit-доках (`V2`/`V3`/`V4`) —
не в рантайме и не в юнитах.

---

## 5. Список снесённого-живого

**Пуст.**

Кандидат атаки `measure_row_all_zero` (+ measure_empty-семейство) **отклонён**:
реестр W1 = только-legacy; W2-A1 = на снос с z16; в новом тракте 0 зовов;
`test_period_empty` зелёный без них. Красный `test_measure_empty` =
непереписанный замок (файл:строка реестра W2-A1:~392 «S2 … `test_measure_empty`»,
не пункт «жива новому»).

---

## Источники замера

- `ubuntu/serenedb/ask/*.py`, `_bootstrap.py` (диск после S1)
- `docs/audit/onepath/W1-X1.md`, `W2-A1.md`, `W2-R1.md`, `W2-R2.md`, `W2-R3.md`
- прогон замков → `/tmp/sr2-red2/results.tsv` + `*.log`
- `load_all()` smoke щелей
