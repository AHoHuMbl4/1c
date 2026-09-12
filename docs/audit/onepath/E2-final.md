# E2-final — снос 2160 мёртвых строк + полный test_one_path

Дата: 12.09.2026. Код изменён; **git-мутаций нет**; psql / полигон / прод не трогались.
Опора: `S2-a.md` (снос), `S2-d.md` (замок), E1 уже закрыл silent/homonym/builder.

---

## 1. Снос по S2-a

| метрика | значение |
|---|---|
| символов удалено | **119** (все из §1.2–1.3) |
| строк тел (AST) | **2160** |
| пересечение с 149 X1 | **0** |
| KEEP-щели / silent-тройка | не тронуты (§2) |

### По файлам (символов / −строк тел)

| зона | # | −строк | сейчас L |
|---|---:|---:|---:|
| `z05_entity_form.py` | 27 | 625 | 570 |
| `z12_stock_balance.py` | 20 | 417 | 1004 |
| `z06_entity_search.py` | 6 | 211 | 381 |
| `z10_rank.py` | 7 | 176 | 276 |
| `z11_sales.py` | 6 | 152 | 249 |
| `z17_aggregate_groups.py` | 6 | 131 | 552 |
| `z14_clarify_memory.py` | 9 | 100 | 556 |
| `z04b_currency_axis.py` | 5 | 73 | 484 |
| `z03_period_windows.py` | 4 | 68 | 540 |
| `z15_answer_atoms.py` | 3 | 48 | 442 |
| `z07_rrf_vectors.py` | 3 | 38 | 511 |
| `z18_compose.py` | 3 | 38 | 851 |
| `z04_calendar_axis.py` | 3 | 36 | 255 |
| `z21_wiki_choice.py` | 1 | 21 | 1312 |
| `z01_infra_trace_llm.py` | 6 | 16 | 862 |
| `z08_measures_totals.py` | 10 | 10 | 291 |
| **Σ** | **119** | **2160** | |

После каждого файла — `py_compile`. Итог: `python3 -m py_compile ask/*.py` OK;
`load_all` OK; DEL-имена отсутствуют; KEEP на месте
(`_pick_kind_axis_col`, `measure_choice`, `stock_net_register_pair`,
`live_axis_col_for_count`, `entity_form_catalogs_for_kind`,
`aggregate_compare_sales`, `aggregate_stock_net_distinct`, `_sql_ident` в z04b).

### wc -l ask/

| срез | строк |
|---|---:|
| ask/z*.py до E2 | ~15895 (срез старта сессии) |
| ask/z*.py после E2 | **13281** |
| Δ | **≈ −2614** (2160 тел + пустые строки/склейки) |

Ожидание «~10.4k» из ТЗ завышено относительно текущего состава 20 зон
(z20 один ≈3k); фактический итог после S1+E2 — **~13.3k** по z*.

---

## 2. Полный `test_one_path.py` (S2-d)

Проверки: (а) clarify только `readings_menu`/`clarify_opts_response`
(+ journal exclude; z21 hybrid через builder); (б) second-number /
hatch / `render_atom_pair`; (в) SQL_CALLS после wiki + ticket-guards;
(г) FORBIDDEN + silent-тройка контракт; (д) `wiki_homonym_kind_peers` в
`wiki_outcome_from_verify`; (е) identity `_patch_z20_wiki_primary`.

**Итог: 77/0 зелёные.**

---

## 3. Замки (полный список прогона)

| Замок | Итог | примечание |
|---|---|---|
| `test_one_path.py` | **77/0** | полный S2-d |
| `test_zone_names_resolvable.py` | **96/0** | |
| `test_entity_form.py` | 27/0 | сужен до GONE + catalogs/compare/axis |
| `test_compare_sales.py` | 47/0 | |
| `test_sales_canon_prefer.py` | 29/0 | sales_rank_engaged → GONE |
| `test_sales_rank_canon.py` | 16/0 | |
| `test_stock_balance_path.py` | 33/0 | DEL-ветки закомментированы |
| `test_final_stock_route_filters_absent.py` | 11/0 | orphans → GONE |
| `test_warehouse_aggregate_breakdown.py` | 7/0 | |
| `test_warehouse_axis_autonomy.py` | 4/0 | |
| `test_aggregate_live_flags.py` | 11/0 | header/row_count → GONE; column жив |
| `test_step2.py` | OK | children_by_parent → GONE |
| `test_k4_axis_and_names.py` | 9/0 | |
| `test_k4_guess_vs_clarify.py` | 13/0 (+2 pending) | |
| `test_k4_meta_names.py` | 13/0 | |
| `test_k6_rank_v2.py` | 14/0 | |
| `test_action_class.py` | 8/0 | event_duel → GONE |
| `test_no_pre_wiki_reorders.py` | 41/0 | |
| `test_rank_leader_path.py` | 27/0 | |
| `test_rank_axis_anchor.py` | 60/0 | |
| `test_unit_from_data.py` | 31/0 | |
| `test_compose.py` | 91/0 | answers_diverge/_ask_back → GONE |
| `test_a3_passport.py` | 4/0 | |
| `test_gate.py` | 56/0 | |
| `test_decision_id.py` | 24/0 | stop2/guards → GONE; reset — тест-хелпер |
| `test_ask_choice_memory.py` | 45/0 | |
| `test_ask_journal.py` | 11/0 | |
| `test_terminal_round.py` | OK | |
| `test_wiki_leader_not_overridden.py` | 9/0 | wiki_leader_alive → GONE |
| `test_wiki_card_hybrid.py` | 67/0 | |
| `test_ai_embed_question.py` | 14/0 | reload — тест-хелпер |
| `test_ab_ambiguous_set.py` | 19/0 | |
| `test_ab_calendar_axis_set.py` | 24/0 | |
| `test_measure_menu_not_silent.py` | 12/0 | |
| `test_wiki_captions_builder.py` | 24/0 | |
| `test_wiki_homonym_menu.py` | 10/0 | |
| `test_wiki_candidate_verify.py` | 64/0 | |
| `test_verify_threshold_menu.py` | 4/0 | |
| `test_intent.py` | 162/0 | |
| `test_axis_count_plain.py` | 13/0 | |

### Окруженческие (не дефект кода E2)

| Замок | Причина |
|---|---|
| `test_ask_embed_native.py` | `RuntimeError: эмбеддер недоступен: KeyError` (нет живого embed-секрета) |
| `test_focus_loop.py` | `ModuleNotFoundError: No module named 'mcp'` |

---

## 4. Что дальше (оркестратор)

1. Коммит/push пат-спеком (этот шаг — без git по заданию).
2. L67 + выкат на окно (scp + md5).
3. Известная не-задача: документ-vs-регистр «реализациятмц» — качество
   verify/меню; заплатки запрещены.

---

## 5. Файлы диффа (без коммита)

Код ask/: z01, z03, z04, z04b, z05, z06, z07, z08, z10, z11, z12, z14, z15,
z17, z18, z21 (z20 не сносился в E2 — правки E1).

Замки: `test_one_path.py` (полный), плюс сужение/GONE по списку S2-a §3
(~30 файлов `test_*.py`).

Отчёт: `docs/audit/onepath/E2-final.md`.
