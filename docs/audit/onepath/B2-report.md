# B2: новый z20_ask_main_http.py — перенос инфраструктуры bit-identical

Срез: 12.09. Источник: `ubuntu/serenedb/ask/z20_ask_main_http_legacy.py`.
Новый файл: `ubuntu/serenedb/ask/z20_ask_main_http.py` (не в `_bootstrap` до B6).
Git/база не трогались. Legacy / тесты / остальные зоны не правились.

## Что сделано

Перенесены секции O2 §2.1 (§1–§5, §7–§8) **без изменений тел**.
`answer()` — временная заглушка `kind=unavailable` («тракт переписывается (волна B3)»).
Вызов `_coverage_answer` из тракта **не** переносился (дыра O3 №9 → B3).

Доп. helpers (без них перенесённое не работает):
`_filter_dates`, `LIST_MARKER`/`INLINE_MARKER`, `without_list_markers`, `rows_seen`,
`_opt_values`, `AMBIG_TTL`, `live_src_counts` (зовётся из `mk_opts`),
`_day_ord`, `period_is_canon_guess`.

## Таблица сравнения тел

| Символ | Строки legacy | Строки нового | Сравнение тел |
|---|---|---|---|
| `_filter_dates` | 18-27 | 14-23 | bit-identical |
| `without_list_markers` | 38-52 | 34-48 | bit-identical |
| `rows_seen` | 55-79 | 51-75 | bit-identical |
| `gate` | 82-243 | 78-239 | bit-identical |
| `gate_out` | 247-265 | 242-260 | bit-identical |
| `_opt_values` | 268-283 | 263-278 | bit-identical |
| `clarify_choice_prompt` | 286-301 | 281-296 | bit-identical |
| `clarify_choice_line` | 304-311 | 299-306 | bit-identical |
| `format_clarify_options` | 314-332 | 309-327 | bit-identical |
| `clarify_say` | 335-357 | 330-352 | bit-identical |
| `clarify_opts_response` | 360-384 | 355-379 | bit-identical |
| `_entity_counts_objects` | 397-414 | 392-409 | bit-identical |
| `_vitrina_objects` | 417-430 | 412-425 | bit-identical |
| `_coverage_of` | 441-502 | 436-497 | bit-identical |
| `_assemble_health_gap` | 529-564 | 524-559 | bit-identical |
| `_table_has_ref_key` | 567-569 | 562-564 | bit-identical |
| `_measure_health_gap` | 572-587 | 567-582 | bit-identical |
| `_real_corpus_object_gaps` | 591-605 | 585-599 | bit-identical |
| `_classify_health_gap` | 608-638 | 602-632 | bit-identical |
| `_health_search_idx_name` | 641-646 | 635-640 | bit-identical |
| `_measure_native_index_freshness` | 649-698 | 643-692 | bit-identical |
| `_attach_native_freshness` | 701-713 | 695-707 | bit-identical |
| `_health_gap` | 716-728 | 710-722 | bit-identical |
| `_health_period_relative_forms` | 731-739 | 725-733 | bit-identical |
| `_coverage_answer` | 763-847 | 757-841 | bit-identical |
| `looks_like_src_table` | 906-911 | 881-886 | bit-identical |
| `human_table_label` | 914-926 | 889-901 | bit-identical |
| `label_has_meta_src` | 929-941 | 904-916 | bit-identical |
| `kind_word` | 944-947 | 919-922 | bit-identical |
| `label_with_kind` | 950-961 | 925-936 | bit-identical |
| `ambiguous_labels` | 967-989 | 942-964 | bit-identical |
| `disambiguate_labels` | 992-1009 | 967-984 | bit-identical |
| `opts_hints` | 1021-1080 | 996-1055 | bit-identical |
| `mk_opts` | 1083-1111 | 1058-1086 | bit-identical |
| `live_src_counts` | 1114-1146 | 1089-1121 | bit-identical |
| `empty_after_period_action` | 1149-1164 | 1124-1139 | bit-identical |
| `period_empty_outcome` | 1167-1191 | 1142-1166 | bit-identical |
| `_period_day_label` | 1194-1209 | 1169-1184 | bit-identical |
| `dates_outside_period_filter` | 1214-1228 | 1187-1201 | bit-identical |
| `format_period_empty_text` | 1231-1279 | 1204-1252 | bit-identical |
| `build_period_empty_answer` | 1282-1336 | 1255-1309 | bit-identical |
| `_day_ord` | 1584-1589 | 1312-1317 | bit-identical |
| `period_is_canon_guess` | 1592-1616 | 1320-1344 | bit-identical |
| `period_slot_for_inherit` | 1667-1678 | 1347-1358 | bit-identical |
| `apply_prior_period` | 1681-1709 | 1361-1389 | bit-identical |
| `_journal_keep_n` | 4407-4421 | 1410-1424 | bit-identical |
| `_journal_code_md5` | 4424-4431 | 1427-1434 | bit-identical |
| `_journal_build_ts` | 4434-4445 | 1437-1448 | bit-identical |
| `_journal_alias_ver` | 4448-4461 | 1451-1464 | bit-identical |
| `_journal_sql_int` | 4464-4470 | 1467-1473 | bit-identical |
| `_journal_sql_bool` | 4473-4476 | 1476-1479 | bit-identical |
| `_journal_atoms_slim` | 4479-4507 | 1482-1510 | bit-identical |
| `_journal_clarify_options` | 4510-4532 | 1513-1535 | bit-identical |
| `_journal_doubt` | 4535-4544 | 1538-1547 | bit-identical |
| `_journal_ticket_variant` | 4547-4560 | 1550-1563 | bit-identical |
| `_journal_intent` | 4563-4565 | 1566-1568 | bit-identical |
| `_journal_fork_keys` | 4568-4576 | 1571-1579 | bit-identical |
| `_journal_uncounted_truncated` | 4579-4598 | 1582-1601 | bit-identical |
| `_ask_journal_write` | 4601-4715 | 1604-1718 | bit-identical |
| `_answer_checked_core` | 4719-4724 | 1721-1726 | bit-identical |
| `answer_checked` | 4726-4805 | 1728-1807 | bit-identical |
| `_build_ask_scope` | 4810-4851 | 1810-1851 | bit-identical |
| `_persist_ask_scope` | 4854-4873 | 1854-1873 | bit-identical |
| `_ensure_ask_scope_table` | 4876-4887 | 1876-1887 | bit-identical |
| `Handler` | 4890-5085 | 1890-2085 | bit-identical |
| `main` | 5088-5097 | 2088-2097 | bit-identical |
| `LIST_MARKER` | 30-30 | 26-26 | bit-identical |
| `INLINE_MARKER` | 35-35 | 31-31 | bit-identical |
| `_HEALTH_GAP_TTL` | 516-516 | 511-511 | bit-identical |
| `_health_gap_cache` | 517-517 | 512-512 | bit-identical |
| `_health_gap_lock` | 518-518 | 513-513 | bit-identical |
| `ASK_HEALTH_NATIVE_FRESHNESS` | 523-524 | 518-519 | bit-identical |
| `ASK_HEALTH_SEARCH_IDX` | 525-525 | 520-520 | bit-identical |
| `_HEALTH_RELNAME_RE` | 526-526 | 521-521 | bit-identical |
| `COVERAGE_SYS` | 742-756 | 736-750 | bit-identical |
| `OUR_PROMPTS` | 761-761 | 755-755 | bit-identical |
| `AMBIG_TTL` | 871-871 | 846-846 | bit-identical |
| `_KIND_WORD` | 884-900 | 859-875 | bit-identical |
| `_META_SRC_PREFIXES` | 903-903 | 878-878 | bit-identical |
| `_AMBIG_CACHE` | 964-964 | 939-939 | bit-identical |
| `SLOT_COVER` | 4405-4405 | 1408-1408 | bit-identical |

| `answer` | (legacy 1712–4400, НЕ перенесено) | stub в новом | **заглушка B2** |

## Итоговые числа

| Метрика | Значение |
|---|---|
| Строк нового файла | 2104 |
| Строк legacy (эталон) | 5103 |
| Символов сравнено | 81 |
| Тел совпало bit-identical | 81/81 |
| Несовпадений | 0 |

Оценка задачи «~800–1100» — по коду без нарративных комментариев health/coverage;
фактический размер выше из‑за bit-identical переноса комментариев вместе с телами.

## Проверки (обязательные)

| # | Проверка | Результат |
|---|---|---|
| 1 | `python3 -m py_compile` + `ast.parse` | **OK** |
| 2 | Сравнение тел AST (`/tmp/b2_body_compare.json`) | **OK** — 81/81 |
| 3 | Grep-негатив запрещённых имён | **OK** |

Запрещённые имена (отсутствуют): `period_assumed_needs_clarify`, `warehouse_clarify`,
`axis_focus_plan`, `try_entity_form_answer`, `try_event_count_period_clarify`,
`arb_pool`, `_ec_atom_fps`.

Заметка: в `_journal_*` остаётся чтение поля `fork_outcome` из diag журнала
(инфра записи, не scan исходов в `answer`) — тело журнала bit-identical с legacy.

## Не переносилось (намеренно)

- Тело старого `answer()` и все до-вики/arbiter/fork/early-clarify/ask_back/YoY ветки
- `period_assumed_needs_clarify`, `warehouse_clarify`, `axis_focus_plan`, `resolve_focus`
- Константы арбитра: `SIGNAL_DISAGREE`, `ARBITER_*`, `FORK_PAIR_MAX`, `NOT_FOR`, `STEM_DICT`
- `_bootstrap.py` / runtime-путь (новый файл не в списке зон)

## Дальше

Волна **B3**: линейный skeleton `answer` (intent → wiki → no_data/clarify/leader).

