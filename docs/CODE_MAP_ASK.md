# Карта `ubuntu/serenedb/serene_ask.py`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **16699**. Функций: **488**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **34**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/serene_ask.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–920`)
- [02 intent](ubuntu/serenedb/serene_ask.py:921) — Intent (якорь `_json_blocks` … `_first_intent_object`; `921–1384`)
- [03 period-windows](ubuntu/serenedb/serene_ask.py:1385) — Периоды и окна (якорь `_num_pred` … `apply_period_leader`; `1385–1821`)
- [04 calendar-axis](ubuntu/serenedb/serene_ask.py:1822) — Календарная ось (якорь `_sql_ident` … `_working_day_doc_preds`; `1822–2005`)
- [05 entity-form](ubuntu/serenedb/serene_ask.py:2006) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `2006–2755`)
- [06 entity-search](ubuntu/serenedb/serene_ask.py:2756) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `2756–3294`)
- [07 rrf-vectors](ubuntu/serenedb/serene_ask.py:3295) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `3295–3888`)
- [08 measures-totals](ubuntu/serenedb/serene_ask.py:3889) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `3889–4139`)
- [09 fork-detector](ubuntu/serenedb/serene_ask.py:4140) — Детектор развилки (якорь `_measures_by_src` … `_class_label_lookup`; `4140–4920`)
- [10 rank](ubuntu/serenedb/serene_ask.py:4921) — Ранг (якорь `count_question_skips_axis` … `prefer_entity_for_rank`; `4921–5405`)
- [11 sales](ubuntu/serenedb/serene_ask.py:5406) — Продажи (якорь `sales_sum_intent` … `period_zero_why_question`; `5406–6163`)
- [12 stock-balance](ubuntu/serenedb/serene_ask.py:6164) — Остатки (якорь `grain_dec_from_axis_ticket` … `balance_bridge_clarify`; `6164–6458`)
- [13 fork-outcomes](ubuntu/serenedb/serene_ask.py:6459) — Исходы развилки (якорь `stock_balance_is_sales_noise` … `fork_outcome_c`; `6459–6945`)
- [14 clarify-memory](ubuntu/serenedb/serene_ask.py:6946) — Уточнение и память (якорь `_alias_parts` … `guards_skip_for_choice`; `6946–7644`)
- [15 answer-atoms](ubuntu/serenedb/serene_ask.py:7645) — Атомы ответа (якорь `stop2_active` … `fill_atom_pairs`; `7645–8065`)
- [16 veto-pick-entity](ubuntu/serenedb/serene_ask.py:8066) — Вето и выбор сущности (якорь `pair_slots_only` … `pick_entity`; `8066–8896`)
- [17 aggregate-groups](ubuntu/serenedb/serene_ask.py:8897) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `8897–9400`)
- [18 compose](ubuntu/serenedb/serene_ask.py:9401) — Формулировка (якорь `merge_period2_groups` … `compose`; `9401–10289`)
- [19 answer-check](ubuntu/serenedb/serene_ask.py:10290) — Проверка ответа (якорь `_readings` … `_filter_values`; `10290–10691`)
- [20 ask-main-http](ubuntu/serenedb/serene_ask.py:10692) — ask / HTTP (якорь `_filter_dates` … `Handler`; `10692–16699`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 920 | 32 | 19 | 0 | 13 |
| 02 | intent | `_json_blocks` | 464 | 15 | 4 | 1 | 10 |
| 03 | period-windows | `_num_pred` | 437 | 21 | 6 | 4 | 5 |
| 04 | calendar-axis | `_sql_ident` | 184 | 11 | 3 | 2 | 7 |
| 05 | entity-form | `entity_form_rank_single_window` | 750 | 26 | 2 | 9 | 17 |
| 06 | entity-search | `_predicates` | 539 | 16 | 3 | 3 | 4 |
| 07 | rrf-vectors | `_corpus_ivf_ready` | 594 | 18 | 8 | 4 | 7 |
| 08 | measures-totals | `_shares_chars` | 251 | 4 | 5 | 3 | 0 |
| 09 | fork-detector | `_measures_by_src` | 781 | 32 | 4 | 9 | 19 |
| 10 | rank | `count_question_skips_axis` | 485 | 15 | 5 | 7 | 6 |
| 11 | sales | `sales_sum_intent` | 758 | 28 | 5 | 7 | 7 |
| 12 | stock-balance | `grain_dec_from_axis_ticket` | 295 | 17 | 4 | 6 | 7 |
| 13 | fork-outcomes | `stock_balance_is_sales_noise` | 487 | 17 | 2 | 7 | 8 |
| 14 | clarify-memory | `_alias_parts` | 699 | 35 | 9 | 3 | 16 |
| 15 | answer-atoms | `stop2_active` | 421 | 15 | 6 | 4 | 4 |
| 16 | veto-pick-entity | `pair_slots_only` | 831 | 29 | 3 | 11 | 5 |
| 17 | aggregate-groups | `_vec` | 504 | 16 | 10 | 3 | 2 |
| 18 | compose | `merge_period2_groups` | 889 | 23 | 6 | 9 | 2 |
| 19 | answer-check | `_readings` | 402 | 14 | 3 | 2 | 5 |
| 20 | ask-main-http | `_filter_dates` | 6008 | 104 | 6 | 19 | 97 |

## 01. infra-trace-llm — Инфра, TRACE, LLM

Якорь: `_new_rid`, end `embed_one`. Участок: [`ubuntu/serenedb/serene_ask.py:1`](ubuntu/serenedb/serene_ask.py:1)–`920`.

Функций: 32. Входящие зоны: 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20. Исходящие зоны: —.

Функции:

- [`_new_rid`](ubuntu/serenedb/serene_ask.py:130) `130–131` len=2
- [`_rid_norm`](ubuntu/serenedb/serene_ask.py:134) `134–139` len=6
- [`_rid_get`](ubuntu/serenedb/serene_ask.py:142) `142–143` len=2
- [`_rid_enter`](ubuntu/serenedb/serene_ask.py:146) `146–149` len=4
- [`_trace_write`](ubuntu/serenedb/serene_ask.py:152) `152–156` len=5
- [`_embed_secret_name_from_env`](ubuntu/serenedb/serene_ask.py:292) `292–296` len=5
- [`_reload_embed_native_env`](ubuntu/serenedb/serene_ask.py:306) `306–312` len=7
- [`psql`](ubuntu/serenedb/serene_ask.py:331) `331–365` len=35
- [`lit`](ubuntu/serenedb/serene_ask.py:368) `368–369` len=2
- [`_embed_host_base`](ubuntu/serenedb/serene_ask.py:372) `372–375` len=4
- [`embed_model_live`](ubuntu/serenedb/serene_ask.py:395) `395–425` len=31
- [`emb_ready`](ubuntu/serenedb/serene_ask.py:428) `428–446` len=19
- [`_fmt`](ubuntu/serenedb/serene_ask.py:449) `449–455` len=7
- [`_src_tag`](ubuntu/serenedb/serene_ask.py:458) `458–462` len=5
- [`_fmt_gate_bad`](ubuntu/serenedb/serene_ask.py:465) `465–471` len=7
- [`_gate_bad_preview`](ubuntu/serenedb/serene_ask.py:474) `474–478` len=5
- [`_fmt_human`](ubuntu/serenedb/serene_ask.py:481) `481–495` len=15
- [`_TokenAcc.__init__`](ubuntu/serenedb/serene_ask.py:505) `505–512` len=8 (влож.)
- [`_TokenAcc.add`](ubuntu/serenedb/serene_ask.py:514) `514–523` len=10 (влож.)
- [`_TokenAcc.diag_dict`](ubuntu/serenedb/serene_ask.py:525) `525–531` len=7 (влож.)
- [`_token_acc_start`](ubuntu/serenedb/serene_ask.py:534) `534–535` len=2
- [`_token_acc_record`](ubuntu/serenedb/serene_ask.py:538) `538–552` len=15
- [`_diag_pack`](ubuntu/serenedb/serene_ask.py:555) `555–561` len=7
- [`_ds_chat_content`](ubuntu/serenedb/serene_ask.py:564) `564–577` len=14
- [`_ds_chat_body`](ubuntu/serenedb/serene_ask.py:580) `580–588` len=9
- [`ds_chat_post`](ubuntu/serenedb/serene_ask.py:591) `591–599` len=9
- [`ds_chat`](ubuntu/serenedb/serene_ask.py:602) `602–603` len=2
- [`arbitrate`](ubuntu/serenedb/serene_ask.py:626) `626–652` len=27
- [`_embed_request`](ubuntu/serenedb/serene_ask.py:655) `655–668` len=14
- [`_ensure_embed_secret`](ubuntu/serenedb/serene_ask.py:684) `684–715` len=32
- [`_embed_one_native`](ubuntu/serenedb/serene_ask.py:718) `718–752` len=35
- [`embed_one`](ubuntu/serenedb/serene_ask.py:755) `755–817` len=63

Зовут снаружи зоны: `_TokenAcc.add`, `_diag_pack`, `_fmt`, `_fmt_gate_bad`, `_fmt_human`, `_gate_bad_preview`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_src_tag`, `_token_acc_start`, `_trace_write`, `arbitrate`, `ds_chat`, `emb_ready`, `embed_model_live`, `embed_one`, `lit`, `psql`

## 02. intent — Intent

Якорь: `_json_blocks`, end `_first_intent_object`. Участок: [`ubuntu/serenedb/serene_ask.py:921`](ubuntu/serenedb/serene_ask.py:921)–`1384`.

Функций: 15. Входящие зоны: 12, 14, 16, 20. Исходящие зоны: 01.

Функции:

- [`_json_blocks`](ubuntu/serenedb/serene_ask.py:921) `921–948` len=28
- [`_intent_text`](ubuntu/serenedb/serene_ask.py:951) `951–962` len=12
- [`_intent_number`](ubuntu/serenedb/serene_ask.py:965) `965–981` len=17
- [`_intent_date`](ubuntu/serenedb/serene_ask.py:984) `984–997` len=14
- [`_intent_terms`](ubuntu/serenedb/serene_ask.py:1000) `1000–1036` len=37
- [`_intent_word`](ubuntu/serenedb/serene_ask.py:1039) `1039–1041` len=3
- [`same_concept_groups`](ubuntu/serenedb/serene_ask.py:1068) `1068–1107` len=40
- [`_stem_set`](ubuntu/serenedb/serene_ask.py:1110) `1110–1117` len=8
- [`_normalize_intent`](ubuntu/serenedb/serene_ask.py:1120) `1120–1236` len=117
- [`_one_intent`](ubuntu/serenedb/serene_ask.py:1239) `1239–1255` len=17
- [`_field_key`](ubuntu/serenedb/serene_ask.py:1258) `1258–1259` len=2
- [`_field_lead`](ubuntu/serenedb/serene_ask.py:1262) `1262–1270` len=9
- [`_merge_intents`](ubuntu/serenedb/serene_ask.py:1273) `1273–1297` len=25
- [`parse_intent`](ubuntu/serenedb/serene_ask.py:1300) `1300–1359` len=60
- [`_first_intent_object`](ubuntu/serenedb/serene_ask.py:1362) `1362–1381` len=20

Зовут снаружи зоны: `_intent_number`, `_intent_text`, `_intent_word`, `_stem_set`, `parse_intent`

## 03. period-windows — Периоды и окна

Якорь: `_num_pred`, end `apply_period_leader`. Участок: [`ubuntu/serenedb/serene_ask.py:1385`](ubuntu/serenedb/serene_ask.py:1385)–`1821`.

Функций: 21. Входящие зоны: 04, 05, 06, 09, 18, 20. Исходящие зоны: 01, 04, 18, 20.

Функции:

- [`_num_pred`](ubuntu/serenedb/serene_ask.py:1385) `1385–1403` len=19
- [`period_preds`](ubuntu/serenedb/serene_ask.py:1406) `1406–1422` len=17
- [`_calendar_date`](ubuntu/serenedb/serene_ask.py:1453) `1453–1458` len=6
- [`_month_range`](ubuntu/serenedb/serene_ask.py:1461) `1461–1468` len=8
- [`_week_range_monday`](ubuntu/serenedb/serene_ask.py:1471) `1471–1475` len=5
- [`_prev_week_range`](ubuntu/serenedb/serene_ask.py:1478) `1478–1486` len=9
- [`_is_seven_day_span`](ubuntu/serenedb/serene_ask.py:1489) `1489–1493` len=5
- [`_is_current_calendar_week`](ubuntu/serenedb/serene_ask.py:1496) `1496–1503` len=8
- [`_assumed_sliding_week_not_calendar`](ubuntu/serenedb/serene_ask.py:1506) `1506–1516` len=11
- [`_iso_date`](ubuntu/serenedb/serene_ask.py:1519) `1519–1520` len=2
- [`_period_origin`](ubuntu/serenedb/serene_ask.py:1523) `1523–1534` len=12
- [`window_fp_of`](ubuntu/serenedb/serene_ask.py:1537) `1537–1548` len=12
- [`_period_form_id`](ubuntu/serenedb/serene_ask.py:1551) `1551–1575` len=25
- [`_window_reading`](ubuntu/serenedb/serene_ask.py:1578) `1578–1600` len=23
- [`period_readings`](ubuntu/serenedb/serene_ask.py:1603) `1603–1691` len=89
- [`period_readings._add`](ubuntu/serenedb/serene_ask.py:1647) `1647–1652` len=6 (влож.)
- [`render_window_label`](ubuntu/serenedb/serene_ask.py:1694) `1694–1712` len=19
- [`prefer_window_leader`](ubuntu/serenedb/serene_ask.py:1719) `1719–1735` len=17
- [`period_relative_forms`](ubuntu/serenedb/serene_ask.py:1738) `1738–1767` len=30
- [`period_form_from_question`](ubuntu/serenedb/serene_ask.py:1770) `1770–1780` len=11
- [`apply_period_leader`](ubuntu/serenedb/serene_ask.py:1783) `1783–1819` len=37

Зовут снаружи зоны: `_calendar_date`, `_iso_date`, `_month_range`, `_num_pred`, `_prev_week_range`, `_week_range_monday`, `_window_reading`, `apply_period_leader`, `period_form_from_question`, `period_preds`, `period_readings`, `period_readings._add`, `period_relative_forms`, `prefer_window_leader`, `render_window_label`, `window_fp_of`

## 04. calendar-axis — Календарная ось

Якорь: `_sql_ident`, end `_working_day_doc_preds`. Участок: [`ubuntu/serenedb/serene_ask.py:1822`](ubuntu/serenedb/serene_ask.py:1822)–`2005`.

Функций: 11. Входящие зоны: 03, 09, 20. Исходящие зоны: 01, 03.

Функции:

- [`_sql_ident`](ubuntu/serenedb/serene_ask.py:1822) `1822–1824` len=3
- [`calendar_registers`](ubuntu/serenedb/serene_ask.py:1827) `1827–1840` len=14
- [`calendar_working_day_keys`](ubuntu/serenedb/serene_ask.py:1843) `1843–1857` len=15
- [`calendar_map_rows`](ubuntu/serenedb/serene_ask.py:1860) `1860–1888` len=29
- [`calendar_axis_open`](ubuntu/serenedb/serene_ask.py:1891) `1891–1896` len=6
- [`calendar_day_basis_prefer`](ubuntu/serenedb/serene_ask.py:1899) `1899–1917` len=19
- [`_day_basis_reading`](ubuntu/serenedb/serene_ask.py:1920) `1920–1926` len=7
- [`calendar_axis_readings`](ubuntu/serenedb/serene_ask.py:1929) `1929–1944` len=16
- [`expand_readings_calendar_axis`](ubuntu/serenedb/serene_ask.py:1947) `1947–1959` len=13
- [`prefer_day_basis_leader`](ubuntu/serenedb/serene_ask.py:1962) `1962–1972` len=11
- [`_working_day_doc_preds`](ubuntu/serenedb/serene_ask.py:1975) `1975–2003` len=29

Зовут снаружи зоны: `_working_day_doc_preds`, `calendar_axis_open`, `calendar_day_basis_prefer`, `expand_readings_calendar_axis`

## 05. entity-form — Форма сущности

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/serene_ask.py:2006`](ubuntu/serenedb/serene_ask.py:2006)–`2755`.

Функций: 26. Входящие зоны: 11, 20. Исходящие зоны: 01, 03, 06, 09, 10, 11, 13, 15, 17.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/serene_ask.py:2006) `2006–2033` len=28
- [`_months_mentioned`](ubuntu/serenedb/serene_ask.py:2053) `2053–2071` len=19
- [`_yoy_compare_marker`](ubuntu/serenedb/serene_ask.py:2074) `2074–2079` len=6
- [`_shift_date_years`](ubuntu/serenedb/serene_ask.py:2082) `2082–2087` len=6
- [`_shift_period_years`](ubuntu/serenedb/serene_ask.py:2090) `2090–2100` len=11
- [`sales_compare_split_month_pair`](ubuntu/serenedb/serene_ask.py:2103) `2103–2124` len=22
- [`sales_compare_split_month_pair._full`](ubuntu/serenedb/serene_ask.py:2118) `2118–2122` len=5 (влож.)
- [`sales_compare_intent`](ubuntu/serenedb/serene_ask.py:2127) `2127–2193` len=67
- [`sales_compare_windows`](ubuntu/serenedb/serene_ask.py:2196) `2196–2280` len=85
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/serene_ask.py:2284) `2284–2315` len=32
- [`entity_form_movements_for_kind`](ubuntu/serenedb/serene_ask.py:2318) `2318–2355` len=38
- [`entity_form_count_target_is_movement`](ubuntu/serenedb/serene_ask.py:2358) `2358–2393` len=36
- [`entity_form_expand_pool`](ubuntu/serenedb/serene_ask.py:2396) `2396–2416` len=21
- [`entity_form_rolling_year`](ubuntu/serenedb/serene_ask.py:2419) `2419–2429` len=11
- [`entity_form_applicable`](ubuntu/serenedb/serene_ask.py:2432) `2432–2464` len=33
- [`entity_form_collapse_guard`](ubuntu/serenedb/serene_ask.py:2467) `2467–2480` len=14
- [`entity_form_pre_entity_ok`](ubuntu/serenedb/serene_ask.py:2483) `2483–2497` len=15
- [`entity_form_atom_distinct`](ubuntu/serenedb/serene_ask.py:2500) `2500–2510` len=11
- [`entity_form_atom_complement`](ubuntu/serenedb/serene_ask.py:2513) `2513–2529` len=17
- [`aggregate_distinct_axis`](ubuntu/serenedb/serene_ask.py:2532) `2532–2559` len=28
- [`entity_form_axis_on_sales`](ubuntu/serenedb/serene_ask.py:2562) `2562–2591` len=30
- [`entity_form_structs`](ubuntu/serenedb/serene_ask.py:2594) `2594–2652` len=59
- [`entity_form_pick`](ubuntu/serenedb/serene_ask.py:2655) `2655–2665` len=11
- [`entity_form_compute`](ubuntu/serenedb/serene_ask.py:2668) `2668–2692` len=25
- [`try_entity_form_answer`](ubuntu/serenedb/serene_ask.py:2695) `2695–2726` len=32
- [`aggregate_compare_sales`](ubuntu/serenedb/serene_ask.py:2729) `2729–2753` len=25

Зовут снаружи зоны: `_months_mentioned`, `_yoy_compare_marker`, `aggregate_compare_sales`, `entity_form_applicable`, `entity_form_catalogs_for_kind`, `entity_form_collapse_guard`, `sales_compare_intent`, `sales_compare_windows`, `try_entity_form_answer`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/serene_ask.py:2756`](ubuntu/serenedb/serene_ask.py:2756)–`3294`.

Функций: 16. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/serene_ask.py:2756) `2756–2764` len=9
- [`_fetch`](ubuntu/serenedb/serene_ask.py:2767) `2767–2779` len=13
- [`_like_pattern`](ubuntu/serenedb/serene_ask.py:2782) `2782–2802` len=21
- [`probe`](ubuntu/serenedb/serene_ask.py:2805) `2805–2907` len=103
- [`matched_group_count`](ubuntu/serenedb/serene_ask.py:2910) `2910–2920` len=11
- [`with_refs`](ubuntu/serenedb/serene_ask.py:2923) `2923–2931` len=9
- [`match_expr`](ubuntu/serenedb/serene_ask.py:2934) `2934–2964` len=31
- [`children_by_parent`](ubuntu/serenedb/serene_ask.py:2967) `2967–3017` len=51
- [`partial_tables`](ubuntu/serenedb/serene_ask.py:3020) `3020–3097` len=78
- [`tables_of`](ubuntu/serenedb/serene_ask.py:3100) `3100–3116` len=17
- [`date_only_kind_filter`](ubuntu/serenedb/serene_ask.py:3119) `3119–3135` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/serene_ask.py:3138) `3138–3153` len=16
- [`alias_hits`](ubuntu/serenedb/serene_ask.py:3156) `3156–3187` len=32
- [`card_hits`](ubuntu/serenedb/serene_ask.py:3190) `3190–3228` len=39
- [`question_exprs`](ubuntu/serenedb/serene_ask.py:3231) `3231–3249` len=19
- [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3252) `3252–3292` len=41

Зовут снаружи зоны: `_predicates`, `alias_hits`, `children_by_parent`, `date_only_kind_filter`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `partial_tables`, `probe`, `question_exprs`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/serene_ask.py:3295`](ubuntu/serenedb/serene_ask.py:3295)–`3888`.

Функций: 18. Входящие зоны: 06, 08, 10, 12, 13, 16, 17, 20. Исходящие зоны: 01, 08, 17, 19.

Функции:

- [`_corpus_ivf_ready`](ubuntu/serenedb/serene_ask.py:3295) `3295–3309` len=15
- [`_resolver_ivf_ready`](ubuntu/serenedb/serene_ask.py:3312) `3312–3331` len=20
- [`_rrf_entity_branches`](ubuntu/serenedb/serene_ask.py:3334) `3334–3365` len=32
- [`_rrf_corpus_branch`](ubuntu/serenedb/serene_ask.py:3368) `3368–3375` len=8
- [`_fused_sql_rrf`](ubuntu/serenedb/serene_ask.py:3378) `3378–3383` len=6
- [`_fused_python_rrf`](ubuntu/serenedb/serene_ask.py:3386) `3386–3402` len=17
- [`_fused_candidates`](ubuntu/serenedb/serene_ask.py:3405) `3405–3456` len=52
- [`near_tables`](ubuntu/serenedb/serene_ask.py:3459) `3459–3497` len=39
- [`rows_of`](ubuntu/serenedb/serene_ask.py:3500) `3500–3532` len=33
- [`signal_terms`](ubuntu/serenedb/serene_ask.py:3567) `3567–3600` len=34
- [`clarify_text`](ubuntu/serenedb/serene_ask.py:3613) `3613–3629` len=17
- [`refuse_text`](ubuntu/serenedb/serene_ask.py:3641) `3641–3663` len=23
- [`rerank`](ubuntu/serenedb/serene_ask.py:3666) `3666–3721` len=56
- [`_resolver_psql`](ubuntu/serenedb/serene_ask.py:3724) `3724–3742` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/serene_ask.py:3749) `3749–3793` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/serene_ask.py:3796) `3796–3817` len=22
- [`resolve_values`](ubuntu/serenedb/serene_ask.py:3822) `3822–3879` len=58
- [`_ngrams`](ubuntu/serenedb/serene_ask.py:3882) `3882–3886` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`, `signal_terms`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/serene_ask.py:3889`](ubuntu/serenedb/serene_ask.py:3889)–`4139`.

Функций: 4. Входящие зоны: 07, 09, 16, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/serene_ask.py:3889) `3889–3906` len=18
- [`measures_of`](ubuntu/serenedb/serene_ask.py:4027) `4027–4040` len=14
- [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:4043) `4043–4052` len=10
- [`totals_of`](ubuntu/serenedb/serene_ask.py:4055) `4055–4098` len=44

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 09. fork-detector — Детектор развилки

Якорь: `_measures_by_src`, end `_class_label_lookup`. Участок: [`ubuntu/serenedb/serene_ask.py:4140`](ubuntu/serenedb/serene_ask.py:4140)–`4920`.

Функций: 32. Входящие зоны: 05, 11, 13, 20. Исходящие зоны: 01, 03, 04, 08, 14, 15, 16, 17, 18.

Функции:

- [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:4140) `4140–4161` len=22
- [`_aliases_by_src`](ubuntu/serenedb/serene_ask.py:4164) `4164–4180` len=17
- [`_fork_headline_doc_measures`](ubuntu/serenedb/serene_ask.py:4183) `4183–4185` len=3
- [`_fork_word_names_measure`](ubuntu/serenedb/serene_ask.py:4188) `4188–4201` len=14
- [`_fork_sum_headline_pool`](ubuntu/serenedb/serene_ask.py:4204) `4204–4214` len=11
- [`_fork_relevant`](ubuntu/serenedb/serene_ask.py:4217) `4217–4263` len=47
- [`_fork_relevant._sum_fallback`](ubuntu/serenedb/serene_ask.py:4234) `4234–4236` len=3 (влож.)
- [`_fork_relevant._with_doc_hdr`](ubuntu/serenedb/serene_ask.py:4244) `4244–4251` len=8 (влож.)
- [`_fork_pool_excluded`](ubuntu/serenedb/serene_ask.py:4266) `4266–4270` len=5
- [`fork_scan`](ubuntu/serenedb/serene_ask.py:4273) `4273–4347` len=75
- [`fork_scan_readings`](ubuntu/serenedb/serene_ask.py:4350) `4350–4392` len=43
- [`fork_classes_windowed`](ubuntu/serenedb/serene_ask.py:4395) `4395–4424` len=30
- [`fork_detector_scan`](ubuntu/serenedb/serene_ask.py:4427) `4427–4464` len=38
- [`_window_tuple_from_period`](ubuntu/serenedb/serene_ask.py:4467) `4467–4478` len=12
- [`_fork_atom_equiv_fp`](ubuntu/serenedb/serene_ask.py:4481) `4481–4510` len=30
- [`_fork_fp_diag`](ubuntu/serenedb/serene_ask.py:4513) `4513–4522` len=10
- [`fork_classes`](ubuntu/serenedb/serene_ask.py:4525) `4525–4544` len=20
- [`fork_key_of`](ubuntu/serenedb/serene_ask.py:4547) `4547–4556` len=10
- [`_window_fp_base`](ubuntu/serenedb/serene_ask.py:4559) `4559–4563` len=5
- [`_fork_key_for_period`](ubuntu/serenedb/serene_ask.py:4566) `4566–4576` len=11
- [`_fork_day_basis_groups`](ubuntu/serenedb/serene_ask.py:4579) `4579–4596` len=18
- [`_fork_log_day_basis`](ubuntu/serenedb/serene_ask.py:4599) `4599–4616` len=18
- [`_fork_log`](ubuntu/serenedb/serene_ask.py:4619) `4619–4656` len=38
- [`fork_labels_of`](ubuntu/serenedb/serene_ask.py:4659) `4659–4678` len=20
- [`fork_labels_covering`](ubuntu/serenedb/serene_ask.py:4683) `4683–4710` len=28
- [`fork_label_siblings`](ubuntu/serenedb/serene_ask.py:4713) `4713–4720` len=8
- [`_fork_answering_sums`](ubuntu/serenedb/serene_ask.py:4723) `4723–4744` len=22
- [`_fork_headline_measure`](ubuntu/serenedb/serene_ask.py:4747) `4747–4814` len=68
- [`_fork_headline_measure._pick_sum_headline`](ubuntu/serenedb/serene_ask.py:4767) `4767–4780` len=14 (влож.)
- [`_fork_atom_of`](ubuntu/serenedb/serene_ask.py:4817) `4817–4876` len=60
- [`_class_branch_label`](ubuntu/serenedb/serene_ask.py:4879) `4879–4885` len=7
- [`_class_label_lookup`](ubuntu/serenedb/serene_ask.py:4888) `4888–4918` len=31

Зовут снаружи зоны: `_aliases_by_src`, `_class_label_lookup`, `_fork_atom_of`, `_fork_fp_diag`, `_fork_log`, `_fork_pool_excluded`, `_fork_relevant`, `_fork_sum_headline_pool`, `_measures_by_src`, `fork_detector_scan`, `fork_key_of`, `fork_labels_covering`, `fork_labels_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `prefer_entity_for_rank`. Участок: [`ubuntu/serenedb/serene_ask.py:4921`](ubuntu/serenedb/serene_ask.py:4921)–`5405`.

Функций: 15. Входящие зоны: 05, 11, 12, 16, 20. Исходящие зоны: 01, 07, 11, 14, 15, 17, 18.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4921) `4921–4938` len=18
- [`question_wants_breakdown`](ubuntu/serenedb/serene_ask.py:4941) `4941–4953` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4956) `4956–4974` len=19
- [`rank_question_text`](ubuntu/serenedb/serene_ask.py:4979) `4979–4997` len=19
- [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:5000) `5000–5013` len=14
- [`rank_leader_answer_text`](ubuntu/serenedb/serene_ask.py:5018) `5018–5038` len=21
- [`rank_axis_label_rows`](ubuntu/serenedb/serene_ask.py:5056) `5056–5079` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/serene_ask.py:5082) `5082–5093` len=12
- [`rank_axis_pick`](ubuntu/serenedb/serene_ask.py:5096) `5096–5142` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/serene_ask.py:5145) `5145–5207` len=63
- [`rank_product_axis_col`](ubuntu/serenedb/serene_ask.py:5210) `5210–5213` len=4
- [`rank_leader_atom`](ubuntu/serenedb/serene_ask.py:5216) `5216–5247` len=32
- [`rank_deterministic_answer`](ubuntu/serenedb/serene_ask.py:5250) `5250–5328` len=79
- [`rank_gate_fallback_answer`](ubuntu/serenedb/serene_ask.py:5331) `5331–5337` len=7
- [`prefer_entity_for_rank`](ubuntu/serenedb/serene_ask.py:5340) `5340–5403` len=64

Зовут снаружи зоны: `count_question_skips_axis`, `prefer_entity_for_rank`, `rank_axes_rerank`, `rank_axis_resolve`, `rank_deterministic_answer`, `rank_gate_fallback_answer`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `period_zero_why_question`. Участок: [`ubuntu/serenedb/serene_ask.py:5406`](ubuntu/serenedb/serene_ask.py:5406)–`6163`.

Функций: 28. Входящие зоны: 05, 10, 16, 18, 20. Исходящие зоны: 01, 05, 09, 10, 12, 14, 17.

Функции:

- [`sales_sum_intent`](ubuntu/serenedb/serene_ask.py:5406) `5406–5453` len=48
- [`_sales_register_score`](ubuntu/serenedb/serene_ask.py:5456) `5456–5471` len=16
- [`sales_lift_possible`](ubuntu/serenedb/serene_ask.py:5474) `5474–5518` len=45
- [`sales_rank_engaged`](ubuntu/serenedb/serene_ask.py:5521) `5521–5548` len=28
- [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5552) `5552–5584` len=33
- [`rank_groups_answer_text`](ubuntu/serenedb/serene_ask.py:5587) `5587–5615` len=29
- [`prefer_entity_for_sales`](ubuntu/serenedb/serene_ask.py:5618) `5618–5721` len=104
- [`sales_canon_src`](ubuntu/serenedb/serene_ask.py:5724) `5724–5736` len=13
- [`sales_money_measure`](ubuntu/serenedb/serene_ask.py:5739) `5739–5758` len=20
- [`sales_qty_measure`](ubuntu/serenedb/serene_ask.py:5762) `5762–5772` len=11
- [`_alias_role_in_question`](ubuntu/serenedb/serene_ask.py:5775) `5775–5794` len=20
- [`_sales_product_rank_qty`](ubuntu/serenedb/serene_ask.py:5797) `5797–5816` len=20
- [`sales_rank_product_axis`](ubuntu/serenedb/serene_ask.py:5819) `5819–5863` len=45
- [`sales_rank_resolve_measure`](ubuntu/serenedb/serene_ask.py:5866) `5866–5921` len=56
- [`sales_rank_canon_measure`](ubuntu/serenedb/serene_ask.py:5924) `5924–5955` len=32
- [`sales_force_money_measure`](ubuntu/serenedb/serene_ask.py:5958) `5958–5980` len=23
- [`sales_canon_force_pool`](ubuntu/serenedb/serene_ask.py:5983) `5983–5991` len=9
- [`sales_canon_engaged`](ubuntu/serenedb/serene_ask.py:5994) `5994–6011` len=18
- [`_zero_period_not_missing`](ubuntu/serenedb/serene_ask.py:6014) `6014–6021` len=8
- [`sales_ticket_hatch`](ubuntu/serenedb/serene_ask.py:6024) `6024–6030` len=7
- [`sales_noncanon_focus`](ubuntu/serenedb/serene_ask.py:6033) `6033–6041` len=9
- [`sales_refuse_sticky_focus`](ubuntu/serenedb/serene_ask.py:6044) `6044–6076` len=33
- [`_is_price_list_noise`](ubuntu/serenedb/serene_ask.py:6079) `6079–6083` len=5
- [`_is_product_catalog`](ubuntu/serenedb/serene_ask.py:6086) `6086–6092` len=7
- [`catalog_count_question`](ubuntu/serenedb/serene_ask.py:6095) `6095–6111` len=17
- [`prefer_entity_for_catalog_count`](ubuntu/serenedb/serene_ask.py:6114) `6114–6137` len=24
- [`catalog_count_src`](ubuntu/serenedb/serene_ask.py:6140) `6140–6148` len=9
- [`period_zero_why_question`](ubuntu/serenedb/serene_ask.py:6151) `6151–6160` len=10

Зовут снаружи зоны: `_is_product_catalog`, `_sales_rank_top_n`, `_sales_register_score`, `_zero_period_not_missing`, `catalog_count_question`, `catalog_count_src`, `period_zero_why_question`, `prefer_entity_for_catalog_count`, `prefer_entity_for_sales`, `rank_groups_answer_text`, `sales_canon_engaged`, `sales_canon_force_pool`, `sales_canon_src`, `sales_force_money_measure`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_rank_engaged`, `sales_rank_resolve_measure`, `sales_refuse_sticky_focus`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `balance_bridge_clarify`. Участок: [`ubuntu/serenedb/serene_ask.py:6164`](ubuntu/serenedb/serene_ask.py:6164)–`6458`.

Функций: 17. Входящие зоны: 11, 13, 16, 20. Исходящие зоны: 01, 02, 07, 10, 14, 20.

Функции:

- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/serene_ask.py:6164) `6164–6170` len=7
- [`_rank_wants_quantity`](ubuntu/serenedb/serene_ask.py:6173) `6173–6177` len=5
- [`rank_measure_hint`](ubuntu/serenedb/serene_ask.py:6180) `6180–6207` len=28
- [`balance_registers`](ubuntu/serenedb/serene_ask.py:6221) `6221–6234` len=14
- [`balance_map_rows`](ubuntu/serenedb/serene_ask.py:6237) `6237–6260` len=24
- [`balance_capable_sources`](ubuntu/serenedb/serene_ask.py:6263) `6263–6265` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/serene_ask.py:6268) `6268–6273` len=6
- [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6276) `6276–6281` len=6
- [`balance_registers_with_goods`](ubuntu/serenedb/serene_ask.py:6284) `6284–6297` len=14
- [`_stems_of_text`](ubuntu/serenedb/serene_ask.py:6300) `6300–6315` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/serene_ask.py:6318) `6318–6331` len=14
- [`stock_asks_named_product`](ubuntu/serenedb/serene_ask.py:6334) `6334–6359` len=26
- [`stock_asks_named_product._is_named_term`](ubuntu/serenedb/serene_ask.py:6341) `6341–6350` len=10 (влож.)
- [`stock_balance_named_no_data`](ubuntu/serenedb/serene_ask.py:6362) `6362–6369` len=8
- [`_balance_map_by_src`](ubuntu/serenedb/serene_ask.py:6372) `6372–6378` len=7
- [`filter_balance_structural`](ubuntu/serenedb/serene_ask.py:6381) `6381–6420` len=40
- [`balance_bridge_clarify`](ubuntu/serenedb/serene_ask.py:6423) `6423–6456` len=34

Зовут снаружи зоны: `_rank_wants_quantity`, `balance_bridge_clarify`, `balance_capable_or_registers`, `balance_registers_with_goods`, `filter_balance_structural`, `grain_dec_from_axis_ticket`, `question_asks_stock_balance`, `rank_measure_hint`, `stock_asks_named_product`, `stock_balance_named_no_data`

## 13. fork-outcomes — Исходы развилки

Якорь: `stock_balance_is_sales_noise`, end `fork_outcome_c`. Участок: [`ubuntu/serenedb/serene_ask.py:6459`](ubuntu/serenedb/serene_ask.py:6459)–`6945`.

Функций: 17. Входящие зоны: 05, 20. Исходящие зоны: 01, 07, 09, 12, 14, 15, 20.

Функции:

- [`stock_balance_is_sales_noise`](ubuntu/serenedb/serene_ask.py:6459) `6459–6468` len=10
- [`filter_stock_balance_sales_noise`](ubuntu/serenedb/serene_ask.py:6471) `6471–6478` len=8
- [`_dedupe_fork_classes`](ubuntu/serenedb/serene_ask.py:6482) `6482–6503` len=22
- [`_class_window_form`](ubuntu/serenedb/serene_ask.py:6510) `6510–6516` len=7
- [`_class_day_basis`](ubuntu/serenedb/serene_ask.py:6519) `6519–6526` len=8
- [`fork_leader_class`](ubuntu/serenedb/serene_ask.py:6529) `6529–6575` len=47
- [`ordered_fork_classes`](ubuntu/serenedb/serene_ask.py:6578) `6578–6596` len=19
- [`_fork_applicable_classes`](ubuntu/serenedb/serene_ask.py:6599) `6599–6602` len=4
- [`resolve_fork_outcome`](ubuntu/serenedb/serene_ask.py:6605) `6605–6654` len=50
- [`_fork_figures_of`](ubuntu/serenedb/serene_ask.py:6657) `6657–6680` len=24
- [`fork_outcome_a`](ubuntu/serenedb/serene_ask.py:6683) `6683–6703` len=21
- [`fork_outcome_unique`](ubuntu/serenedb/serene_ask.py:6707) `6707–6732` len=26
- [`_rivals_figures_empty`](ubuntu/serenedb/serene_ask.py:6735) `6735–6753` len=19
- [`prefer_mute_computed_over_clarify`](ubuntu/serenedb/serene_ask.py:6756) `6756–6784` len=29
- [`atom_terminal_gate_text`](ubuntu/serenedb/serene_ask.py:6787) `6787–6797` len=11
- [`fork_outcome_b`](ubuntu/serenedb/serene_ask.py:6801) `6801–6850` len=50
- [`fork_outcome_c`](ubuntu/serenedb/serene_ask.py:6853) `6853–6943` len=91

Зовут снаружи зоны: `_fork_figures_of`, `atom_terminal_gate_text`, `filter_stock_balance_sales_noise`, `fork_outcome_a`, `fork_outcome_b`, `fork_outcome_c`, `fork_outcome_unique`, `prefer_mute_computed_over_clarify`, `resolve_fork_outcome`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `guards_skip_for_choice`. Участок: [`ubuntu/serenedb/serene_ask.py:6946`](ubuntu/serenedb/serene_ask.py:6946)–`7644`.

Функций: 35. Входящие зоны: 09, 10, 11, 12, 13, 15, 16, 18, 20. Исходящие зоны: 01, 02, 20.

Функции:

- [`_alias_parts`](ubuntu/serenedb/serene_ask.py:6946) `6946–6950` len=5
- [`_word_hits_text`](ubuntu/serenedb/serene_ask.py:6953) `6953–6957` len=5
- [`split_ident`](ubuntu/serenedb/serene_ask.py:6960) `6960–6964` len=5
- [`measure_choice`](ubuntu/serenedb/serene_ask.py:6967) `6967–7020` len=54
- [`measure_captions`](ubuntu/serenedb/serene_ask.py:7023) `7023–7041` len=19
- [`resolve_measure`](ubuntu/serenedb/serene_ask.py:7044) `7044–7076` len=33
- [`slot_measure_uncovered`](ubuntu/serenedb/serene_ask.py:7079) `7079–7087` len=9
- [`clarify_complete`](ubuntu/serenedb/serene_ask.py:7090) `7090–7106` len=17
- [`_slot_fp`](ubuntu/serenedb/serene_ask.py:7123) `7123–7141` len=19
- [`answers_diverge`](ubuntu/serenedb/serene_ask.py:7144) `7144–7177` len=34
- [`answers_src_conflict`](ubuntu/serenedb/serene_ask.py:7179) `7179–7194` len=16
- [`question_fingerprint`](ubuntu/serenedb/serene_ask.py:7209) `7209–7212` len=4
- [`db_fingerprint`](ubuntu/serenedb/serene_ask.py:7215) `7215–7229` len=15
- [`options_version`](ubuntu/serenedb/serene_ask.py:7232) `7232–7245` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/serene_ask.py:7248) `7248–7257` len=10
- [`_new_decision_id`](ubuntu/serenedb/serene_ask.py:7260) `7260–7262` len=3
- [`_purge_decisions`](ubuntu/serenedb/serene_ask.py:7265) `7265–7280` len=16
- [`_resolved_key`](ubuntu/serenedb/serene_ask.py:7283) `7283–7285` len=3
- [`peek_resolved`](ubuntu/serenedb/serene_ask.py:7288) `7288–7294` len=7
- [`accumulate_resolution`](ubuntu/serenedb/serene_ask.py:7297) `7297–7314` len=18
- [`issue_decision`](ubuntu/serenedb/serene_ask.py:7317) `7317–7353` len=37
- [`seal_clarify`](ubuntu/serenedb/serene_ask.py:7356) `7356–7408` len=53
- [`consume_decision`](ubuntu/serenedb/serene_ask.py:7411) `7411–7438` len=28
- [`peek_decision`](ubuntu/serenedb/serene_ask.py:7441) `7441–7461` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/serene_ask.py:7464) `7464–7488` len=25
- [`reissue_clarify`](ubuntu/serenedb/serene_ask.py:7491) `7491–7509` len=19
- [`choice_error_response`](ubuntu/serenedb/serene_ask.py:7512) `7512–7530` len=19
- [`reset_decisions_for_tests`](ubuntu/serenedb/serene_ask.py:7533) `7533–7538` len=6
- [`attach_memory_shadow`](ubuntu/serenedb/serene_ask.py:7541) `7541–7552` len=12
- [`choice_proven`](ubuntu/serenedb/serene_ask.py:7555) `7555–7561` len=7
- [`choice_levels_proven`](ubuntu/serenedb/serene_ask.py:7564) `7564–7578` len=15
- [`measure_already_proven`](ubuntu/serenedb/serene_ask.py:7581) `7581–7585` len=5
- [`entity_choice_locked`](ubuntu/serenedb/serene_ask.py:7588) `7588–7590` len=3
- [`hold_settled_entity`](ubuntu/serenedb/serene_ask.py:7593) `7593–7627` len=35
- [`guards_skip_for_choice`](ubuntu/serenedb/serene_ask.py:7630) `7630–7642` len=13

Зовут снаружи зоны: `accumulate_resolution`, `answers_diverge`, `answers_src_conflict`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `guards_skip_for_choice`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `slot_measure_uncovered`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `stop2_active`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/serene_ask.py:7645`](ubuntu/serenedb/serene_ask.py:7645)–`8065`.

Функций: 15. Входящие зоны: 05, 09, 10, 13, 16, 20. Исходящие зоны: 01, 14, 17, 18.

Функции:

- [`stop2_active`](ubuntu/serenedb/serene_ask.py:7645) `7645–7655` len=11
- [`determined_answer_rivals`](ubuntu/serenedb/serene_ask.py:7658) `7658–7693` len=36
- [`determined_answer_rivals.family`](ubuntu/serenedb/serene_ask.py:7669) `7669–7670` len=2 (влож.)
- [`determined_answer_rivals.add`](ubuntu/serenedb/serene_ask.py:7675) `7675–7678` len=4 (влож.)
- [`answer_money`](ubuntu/serenedb/serene_ask.py:7698) `7698–7707` len=10
- [`answer_slot_mode`](ubuntu/serenedb/serene_ask.py:7710) `7710–7736` len=27
- [`compose_slot_values`](ubuntu/serenedb/serene_ask.py:7739) `7739–7810` len=72
- [`atom_operation`](ubuntu/serenedb/serene_ask.py:7825) `7825–7839` len=15
- [`_atom_exact_value`](ubuntu/serenedb/serene_ask.py:7842) `7842–7861` len=20
- [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7864) `7864–7907` len=44
- [`atom_from_agg`](ubuntu/serenedb/serene_ask.py:7910) `7910–7965` len=56
- [`_period_window_human`](ubuntu/serenedb/serene_ask.py:7968) `7968–7975` len=8
- [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7978) `7978–8031` len=54
- [`fill_atom_pairs`](ubuntu/serenedb/serene_ask.py:8034) `8034–8063` len=30
- [`fill_atom_pairs.one`](ubuntu/serenedb/serene_ask.py:8045) `8045–8061` len=17 (влож.)

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `build_answer_atom`, `compose_slot_values`, `determined_answer_rivals`, `fill_atom_pairs`, `fill_atom_pairs.one`, `render_atom_pair`, `stop2_active`

## 16. veto-pick-entity — Вето и выбор сущности

Якорь: `pair_slots_only`, end `pick_entity`. Участок: [`ubuntu/serenedb/serene_ask.py:8066`](ubuntu/serenedb/serene_ask.py:8066)–`8896`.

Функций: 29. Входящие зоны: 09, 18, 20. Исходящие зоны: 01, 02, 07, 08, 10, 11, 12, 14, 15, 18, 20.

Функции:

- [`pair_slots_only`](ubuntu/serenedb/serene_ask.py:8066) `8066–8068` len=3
- [`atom_whitelist_labels`](ubuntu/serenedb/serene_ask.py:8071) `8071–8080` len=10
- [`atom_whitelist_numbers`](ubuntu/serenedb/serene_ask.py:8083) `8083–8099` len=17
- [`arbiter_figures`](ubuntu/serenedb/serene_ask.py:8102) `8102–8108` len=7
- [`alias_supported`](ubuntu/serenedb/serene_ask.py:8111) `8111–8179` len=69
- [`not_for_excludes`](ubuntu/serenedb/serene_ask.py:8182) `8182–8217` len=36
- [`pair_unanswered`](ubuntu/serenedb/serene_ask.py:8220) `8220–8230` len=11
- [`single_is_rival`](ubuntu/serenedb/serene_ask.py:8233) `8233–8241` len=9
- [`veto_top_without`](ubuntu/serenedb/serene_ask.py:8244) `8244–8252` len=9
- [`figures_numbers`](ubuntu/serenedb/serene_ask.py:8255) `8255–8272` len=18
- [`same_number`](ubuntu/serenedb/serene_ask.py:8275) `8275–8299` len=25
- [`k6_dual_atom_clarify_return`](ubuntu/serenedb/serene_ask.py:8302) `8302–8327` len=26
- [`src_supports_question`](ubuntu/serenedb/serene_ask.py:8332) `8332–8392` len=61
- [`any_live_src_supports_question`](ubuntu/serenedb/serene_ask.py:8395) `8395–8406` len=12
- [`question_expects_accounting_data`](ubuntu/serenedb/serene_ask.py:8415) `8415–8442` len=28
- [`canon_claims_question`](ubuntu/serenedb/serene_ask.py:8445) `8445–8458` len=14
- [`kind_has_corpus_support`](ubuntu/serenedb/serene_ask.py:8461) `8461–8480` len=20
- [`measure_class_alts`](ubuntu/serenedb/serene_ask.py:8483) `8483–8495` len=13
- [`unresolved_quantity`](ubuntu/serenedb/serene_ask.py:8498) `8498–8518` len=21
- [`mute_measure_blocks`](ubuntu/serenedb/serene_ask.py:8521) `8521–8536` len=16
- [`measure_row_all_zero`](ubuntu/serenedb/serene_ask.py:8539) `8539–8546` len=8
- [`alive_measure_names`](ubuntu/serenedb/serene_ask.py:8549) `8549–8551` len=3
- [`filter_dead_measure_alts`](ubuntu/serenedb/serene_ask.py:8554) `8554–8562` len=9
- [`measure_asked_explicitly`](ubuntu/serenedb/serene_ask.py:8565) `8565–8573` len=9
- [`format_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8576) `8576–8594` len=19
- [`build_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8597) `8597–8650` len=54
- [`measure_ambiguous`](ubuntu/serenedb/serene_ask.py:8653) `8653–8669` len=17
- [`pick_measure`](ubuntu/serenedb/serene_ask.py:8672) `8672–8717` len=46
- [`pick_entity`](ubuntu/serenedb/serene_ask.py:8720) `8720–8894` len=175

Зовут снаружи зоны: `alias_supported`, `arbiter_figures`, `build_measure_empty_pivot`, `canon_claims_question`, `figures_numbers`, `filter_dead_measure_alts`, `k6_dual_atom_clarify_return`, `kind_has_corpus_support`, `measure_ambiguous`, `measure_asked_explicitly`, `measure_class_alts`, `measure_row_all_zero`, `mute_measure_blocks`, `not_for_excludes`, `pair_slots_only`, `pair_unanswered`, `pick_entity`, `pick_measure`, `question_expects_accounting_data`, `same_number`, `single_is_rival`, `src_supports_question`, `unresolved_quantity`, `veto_top_without`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/serene_ask.py:8897`](ubuntu/serenedb/serene_ask.py:8897)–`9400`.

Функций: 16. Входящие зоны: 05, 07, 08, 09, 10, 11, 15, 18, 19, 20. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/serene_ask.py:8897) `8897–8898` len=2
- [`_num`](ubuntu/serenedb/serene_ask.py:8901) `8901–8905` len=5
- [`_numN`](ubuntu/serenedb/serene_ask.py:8908) `8908–8921` len=14
- [`aggregate`](ubuntu/serenedb/serene_ask.py:8924) `8924–9039` len=116
- [`src_is_child`](ubuntu/serenedb/serene_ask.py:9043) `9043–9052` len=10
- [`refcols_of`](ubuntu/serenedb/serene_ask.py:9055) `9055–9069` len=15
- [`holders_of_target`](ubuntu/serenedb/serene_ask.py:9072) `9072–9089` len=18
- [`measures_of_many`](ubuntu/serenedb/serene_ask.py:9092) `9092–9107` len=16
- [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:9110) `9110–9141` len=32
- [`kind_axis_rerank`](ubuntu/serenedb/serene_ask.py:9144) `9144–9167` len=24
- [`term_ref_owners`](ubuntu/serenedb/serene_ask.py:9170) `9170–9196` len=27
- [`term_axis_hits`](ubuntu/serenedb/serene_ask.py:9199) `9199–9238` len=40
- [`resolve_member_names`](ubuntu/serenedb/serene_ask.py:9241) `9241–9268` len=28
- [`_group_leader`](ubuntu/serenedb/serene_ask.py:9271) `9271–9280` len=10
- [`_group_fold`](ubuntu/serenedb/serene_ask.py:9283) `9283–9289` len=7
- [`aggregate_groups`](ubuntu/serenedb/serene_ask.py:9292) `9292–9398` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `holders_of_target`, `kind_axis_hits`, `kind_axis_rerank`, `measures_of_many`, `refcols_of`, `src_is_child`, `term_axis_hits`, `term_ref_owners`

## 18. compose — Формулировка

Якорь: `merge_period2_groups`, end `compose`. Участок: [`ubuntu/serenedb/serene_ask.py:9401`](ubuntu/serenedb/serene_ask.py:9401)–`10289`.

Функций: 23. Входящие зоны: 03, 09, 10, 15, 16, 20. Исходящие зоны: 01, 03, 08, 11, 14, 16, 17, 19, 20.

Функции:

- [`merge_period2_groups`](ubuntu/serenedb/serene_ask.py:9401) `9401–9416` len=16
- [`axis_clarify_options`](ubuntu/serenedb/serene_ask.py:9419) `9419–9443` len=25
- [`_split_answer`](ubuntu/serenedb/serene_ask.py:9490) `9490–9520` len=31
- [`_group_value_by_name`](ubuntu/serenedb/serene_ask.py:9540) `9540–9556` len=17
- [`_fill_figures`](ubuntu/serenedb/serene_ask.py:9559) `9559–9680` len=122
- [`_fill_figures.one`](ubuntu/serenedb/serene_ask.py:9637) `9637–9678` len=42 (влож.)
- [`ensure_n_groups_named`](ubuntu/serenedb/serene_ask.py:9683) `9683–9701` len=19
- [`ensure_count_named`](ubuntu/serenedb/serene_ask.py:9704) `9704–9722` len=19
- [`_measure_dimension`](ubuntu/serenedb/serene_ask.py:9727) `9727–9745` len=19
- [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9748) `9748–9766` len=19
- [`postprocess_money_answer_text`](ubuntu/serenedb/serene_ask.py:9769) `9769–9777` len=9
- [`build_answer_passport`](ubuntu/serenedb/serene_ask.py:9779) `9779–9839` len=61
- [`build_answer_passport._add`](ubuntu/serenedb/serene_ask.py:9794) `9794–9800` len=7 (влож.)
- [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9842) `9842–9851` len=10
- [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9854) `9854–9863` len=10
- [`_table_label`](ubuntu/serenedb/serene_ask.py:9866) `9866–9877` len=12
- [`_passport_axis_label`](ubuntu/serenedb/serene_ask.py:9880) `9880–9891` len=12
- [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9894) `9894–9901` len=8
- [`formulation_flaws`](ubuntu/serenedb/serene_ask.py:9904) `9904–9931` len=28
- [`copied_figures`](ubuntu/serenedb/serene_ask.py:9934) `9934–10001` len=68
- [`_filled_ask`](ubuntu/serenedb/serene_ask.py:10004) `10004–10022` len=19
- [`_ask_back`](ubuntu/serenedb/serene_ask.py:10025) `10025–10039` len=15
- [`compose`](ubuntu/serenedb/serene_ask.py:10042) `10042–10264` len=223

Зовут снаружи зоны: `_ask_back`, `_fill_figures`, `_fill_figures.one`, `_filled_ask`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `build_answer_passport._add`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `merge_period2_groups`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/serene_ask.py:10290`](ubuntu/serenedb/serene_ask.py:10290)–`10691`.

Функций: 14. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/serene_ask.py:10290) `10290–10330` len=41
- [`_plausible`](ubuntu/serenedb/serene_ask.py:10333) `10333–10342` len=10
- [`_dates`](ubuntu/serenedb/serene_ask.py:10345) `10345–10365` len=21
- [`_date2_readings`](ubuntu/serenedb/serene_ask.py:10368) `10368–10379` len=12
- [`_date_spans`](ubuntu/serenedb/serene_ask.py:10382) `10382–10402` len=21
- [`_tokens`](ubuntu/serenedb/serene_ask.py:10405) `10405–10435` len=31
- [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:10438) `10438–10443` len=6
- [`check_claims`](ubuntu/serenedb/serene_ask.py:10449) `10449–10482` len=34
- [`claims_in_text`](ubuntu/serenedb/serene_ask.py:10488) `10488–10527` len=40
- [`prompt_leak`](ubuntu/serenedb/serene_ask.py:10530) `10530–10549` len=20
- [`asked_figure_missing`](ubuntu/serenedb/serene_ask.py:10552) `10552–10639` len=88
- [`stale_note`](ubuntu/serenedb/serene_ask.py:10642) `10642–10657` len=16
- [`_threshold_values`](ubuntu/serenedb/serene_ask.py:10660) `10660–10664` len=5
- [`_filter_values`](ubuntu/serenedb/serene_ask.py:10667) `10667–10689` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/serene_ask.py:10692`](ubuntu/serenedb/serene_ask.py:10692)–`16699`.

Функций: 104. Входящие зоны: 03, 12, 13, 14, 16, 18. Исходящие зоны: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19.

Функции:

- [`_filter_dates`](ubuntu/serenedb/serene_ask.py:10692) `10692–10701` len=10
- [`without_list_markers`](ubuntu/serenedb/serene_ask.py:10712) `10712–10726` len=15
- [`rows_seen`](ubuntu/serenedb/serene_ask.py:10729) `10729–10753` len=25
- [`gate`](ubuntu/serenedb/serene_ask.py:10756) `10756–10917` len=162
- [`gate.allow`](ubuntu/serenedb/serene_ask.py:10775) `10775–10793` len=19 (влож.)
- [`count_figures`](ubuntu/serenedb/serene_ask.py:10920) `10920–10934` len=15
- [`gate_out`](ubuntu/serenedb/serene_ask.py:10937) `10937–10955` len=19
- [`_opt_values`](ubuntu/serenedb/serene_ask.py:10958) `10958–10973` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/serene_ask.py:10976) `10976–10991` len=16
- [`clarify_choice_line`](ubuntu/serenedb/serene_ask.py:10994) `10994–11001` len=8
- [`format_clarify_options`](ubuntu/serenedb/serene_ask.py:11004) `11004–11022` len=19
- [`clarify_say`](ubuntu/serenedb/serene_ask.py:11025) `11025–11047` len=23
- [`_entity_counts_objects`](ubuntu/serenedb/serene_ask.py:11060) `11060–11077` len=18
- [`_vitrina_objects`](ubuntu/serenedb/serene_ask.py:11080) `11080–11093` len=14
- [`_coverage_of`](ubuntu/serenedb/serene_ask.py:11104) `11104–11165` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/serene_ask.py:11192) `11192–11227` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/serene_ask.py:11230) `11230–11232` len=3
- [`_measure_health_gap`](ubuntu/serenedb/serene_ask.py:11235) `11235–11250` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/serene_ask.py:11254) `11254–11268` len=15
- [`_classify_health_gap`](ubuntu/serenedb/serene_ask.py:11271) `11271–11301` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/serene_ask.py:11304) `11304–11309` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/serene_ask.py:11312) `11312–11361` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/serene_ask.py:11364) `11364–11376` len=13
- [`_health_gap`](ubuntu/serenedb/serene_ask.py:11379) `11379–11391` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/serene_ask.py:11394) `11394–11402` len=9
- [`_coverage_answer`](ubuntu/serenedb/serene_ask.py:11426) `11426–11510` len=85
- [`looks_like_src_table`](ubuntu/serenedb/serene_ask.py:11570) `11570–11575` len=6
- [`human_table_label`](ubuntu/serenedb/serene_ask.py:11578) `11578–11590` len=13
- [`label_has_meta_src`](ubuntu/serenedb/serene_ask.py:11593) `11593–11605` len=13
- [`kind_word`](ubuntu/serenedb/serene_ask.py:11608) `11608–11611` len=4
- [`label_with_kind`](ubuntu/serenedb/serene_ask.py:11614) `11614–11625` len=12
- [`ambiguous_labels`](ubuntu/serenedb/serene_ask.py:11631) `11631–11653` len=23
- [`disambiguate_labels`](ubuntu/serenedb/serene_ask.py:11656) `11656–11673` len=18
- [`opts_hints`](ubuntu/serenedb/serene_ask.py:11685) `11685–11744` len=60
- [`mk_opts`](ubuntu/serenedb/serene_ask.py:11747) `11747–11775` len=29
- [`live_src_counts`](ubuntu/serenedb/serene_ask.py:11778) `11778–11810` len=33
- [`empty_after_period_action`](ubuntu/serenedb/serene_ask.py:11813) `11813–11828` len=16
- [`period_empty_outcome`](ubuntu/serenedb/serene_ask.py:11831) `11831–11855` len=25
- [`_period_day_label`](ubuntu/serenedb/serene_ask.py:11858) `11858–11873` len=16
- [`_period_day_label.one`](ubuntu/serenedb/serene_ask.py:11860) `11860–11865` len=6 (влож.)
- [`sales_period_empty`](ubuntu/serenedb/serene_ask.py:11878) `11878–11893` len=16
- [`sales_period_window_active`](ubuntu/serenedb/serene_ask.py:11896) `11896–11908` len=13
- [`sales_fork_canon_empty_src`](ubuntu/serenedb/serene_ask.py:11911) `11911–11936` len=26
- [`try_sales_fork_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11939) `11939–11964` len=26
- [`sales_fork_blocks_clarify`](ubuntu/serenedb/serene_ask.py:11967) `11967–11978` len=12
- [`dates_outside_period_filter`](ubuntu/serenedb/serene_ask.py:11981) `11981–11995` len=15
- [`format_period_empty_text`](ubuntu/serenedb/serene_ask.py:11998) `11998–12046` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/serene_ask.py:12049) `12049–12101` len=53
- [`drop_period_preds`](ubuntu/serenedb/serene_ask.py:12104) `12104–12110` len=7
- [`_term_stems`](ubuntu/serenedb/serene_ask.py:12113) `12113–12128` len=16
- [`_src_covers_term_stems`](ubuntu/serenedb/serene_ask.py:12131) `12131–12143` len=13
- [`align_picked_to_terms`](ubuntu/serenedb/serene_ask.py:12146) `12146–12173` len=28
- [`resolve_focus`](ubuntu/serenedb/serene_ask.py:12176) `12176–12310` len=135
- [`_word_hits_measure`](ubuntu/serenedb/serene_ask.py:12314) `12314–12326` len=13
- [`axis_focus_plan`](ubuntu/serenedb/serene_ask.py:12329) `12329–12397` len=69
- [`_day_ord`](ubuntu/serenedb/serene_ask.py:12400) `12400–12405` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/serene_ask.py:12408) `12408–12432` len=25
- [`period_assumed_needs_clarify`](ubuntu/serenedb/serene_ask.py:12435) `12435–12456` len=22
- [`stock_subject_needs_clarify`](ubuntu/serenedb/serene_ask.py:12459) `12459–12474` len=16
- [`warehouse_axis_values`](ubuntu/serenedb/serene_ask.py:12477) `12477–12556` len=80
- [`warehouse_axis_values._take`](ubuntu/serenedb/serene_ask.py:12500) `12500–12512` len=13 (влож.)
- [`warehouse_clarify`](ubuntu/serenedb/serene_ask.py:12559) `12559–12573` len=15
- [`period_slot_for_inherit`](ubuntu/serenedb/serene_ask.py:12576) `12576–12587` len=12
- [`apply_prior_period`](ubuntu/serenedb/serene_ask.py:12590) `12590–12618` len=29
- [`answer`](ubuntu/serenedb/serene_ask.py:12621) `12621–15843` len=3223
- [`answer.шаг`](ubuntu/serenedb/serene_ask.py:12657) `12657–12662` len=6 (влож.)
- [`answer._k6_mk_clarify`](ubuntu/serenedb/serene_ask.py:13020) `13020–13023` len=4 (влож.)
- [`answer._family`](ubuntu/serenedb/serene_ask.py:13771) `13771–13772` len=2 (влож.)
- [`answer._alias_verdict`](ubuntu/serenedb/serene_ask.py:13774) `13774–13927` len=154 (влож.)
- [`answer._alias_verdict._место`](ubuntu/serenedb/serene_ask.py:13885) `13885–13889` len=5 (влож.)
- [`answer._alias_verdict._probe`](ubuntu/serenedb/serene_ask.py:13891) `13891–13902` len=12 (влож.)
- [`answer._alias_clarify`](ubuntu/serenedb/serene_ask.py:13929) `13929–13957` len=29 (влож.)
- [`answer._checked`](ubuntu/serenedb/serene_ask.py:14227) `14227–14243` len=17 (влож.)
- [`question_facts`](ubuntu/serenedb/serene_ask.py:15866) `15866–15892` len=27
- [`entity_has_dates`](ubuntu/serenedb/serene_ask.py:15895) `15895–15916` len=22
- [`_gate_need`](ubuntu/serenedb/serene_ask.py:15919) `15919–15932` len=14
- [`_need_clarify`](ubuntu/serenedb/serene_ask.py:15935) `15935–15951` len=17
- [`_journal_keep_n`](ubuntu/serenedb/serene_ask.py:15954) `15954–15968` len=15
- [`_journal_code_md5`](ubuntu/serenedb/serene_ask.py:15971) `15971–15978` len=8
- [`_journal_build_ts`](ubuntu/serenedb/serene_ask.py:15981) `15981–15992` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/serene_ask.py:15995) `15995–16008` len=14
- [`_journal_sql_int`](ubuntu/serenedb/serene_ask.py:16011) `16011–16017` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/serene_ask.py:16020) `16020–16023` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/serene_ask.py:16026) `16026–16054` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/serene_ask.py:16057) `16057–16079` len=23
- [`_journal_doubt`](ubuntu/serenedb/serene_ask.py:16082) `16082–16091` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/serene_ask.py:16094) `16094–16107` len=14
- [`_journal_intent`](ubuntu/serenedb/serene_ask.py:16110) `16110–16112` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/serene_ask.py:16115) `16115–16123` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/serene_ask.py:16126) `16126–16145` len=20
- [`_ask_journal_write`](ubuntu/serenedb/serene_ask.py:16148) `16148–16262` len=115
- [`_ask_journal_write._insert_row`](ubuntu/serenedb/serene_ask.py:16192) `16192–16241` len=50 (влож.)
- [`_answer_checked_core`](ubuntu/serenedb/serene_ask.py:16266) `16266–16308` len=43
- [`_answer_checked_core.plain`](ubuntu/serenedb/serene_ask.py:16270) `16270–16272` len=3 (влож.)
- [`_try_memory_apply`](ubuntu/serenedb/serene_ask.py:16313) `16313–16338` len=26
- [`answer_checked`](ubuntu/serenedb/serene_ask.py:16340) `16340–16425` len=86
- [`_build_ask_scope`](ubuntu/serenedb/serene_ask.py:16430) `16430–16471` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/serene_ask.py:16474) `16474–16493` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/serene_ask.py:16496) `16496–16507` len=12
- [`Handler.log_message`](ubuntu/serenedb/serene_ask.py:16513) `16513–16514` len=2 (влож.)
- [`Handler._send`](ubuntu/serenedb/serene_ask.py:16516) `16516–16522` len=7 (влож.)
- [`Handler.do_GET`](ubuntu/serenedb/serene_ask.py:16524) `16524–16590` len=67 (влож.)
- [`Handler.do_POST`](ubuntu/serenedb/serene_ask.py:16592) `16592–16683` len=92 (влож.)
- [`main`](ubuntu/serenedb/serene_ask.py:16686) `16686–16695` len=10

Зовут снаружи зоны: `_period_day_label`, `clarify_say`, `disambiguate_labels`, `format_clarify_options`, `human_table_label`, `kind_word`, `mk_opts`

## Сквозные функции

Функции, которые вызывают из трёх и более других зон.

| функция | зона | вызывающих зон | зоны |
|---|---|---:|---|
| [`psql`](ubuntu/serenedb/serene_ask.py:331) | 01 | 17 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17, 18, 20 |
| [`lit`](ubuntu/serenedb/serene_ask.py:368) | 01 | 16 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 16, 17, 18, 20 |
| [`_fmt`](ubuntu/serenedb/serene_ask.py:449) | 01 | 6 | 05, 13, 15, 18, 19, 20 |
| [`_diag_pack`](ubuntu/serenedb/serene_ask.py:555) | 01 | 6 | 05, 10, 12, 13, 16, 20 |
| [`ds_chat`](ubuntu/serenedb/serene_ask.py:602) | 01 | 6 | 02, 07, 10, 16, 18, 20 |
| [`measure_choice`](ubuntu/serenedb/serene_ask.py:6967) | 14 | 5 | 09, 11, 12, 16, 20 |
| [`_num`](ubuntu/serenedb/serene_ask.py:8901) | 17 | 5 | 05, 08, 09, 18, 20 |
| [`_fmt_human`](ubuntu/serenedb/serene_ask.py:481) | 01 | 4 | 10, 11, 16, 18 |
| [`period_preds`](ubuntu/serenedb/serene_ask.py:1406) | 03 | 4 | 05, 06, 09, 20 |
| [`rerank`](ubuntu/serenedb/serene_ask.py:3666) | 07 | 4 | 10, 16, 17, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:4043) | 08 | 4 | 09, 16, 18, 20 |
| [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:5000) | 10 | 4 | 05, 11, 12, 20 |
| [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6276) | 12 | 4 | 11, 13, 16, 20 |
| [`split_ident`](ubuntu/serenedb/serene_ask.py:6960) | 14 | 4 | 09, 13, 18, 20 |
| [`refcols_of`](ubuntu/serenedb/serene_ask.py:9055) | 17 | 4 | 05, 10, 11, 20 |
| [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3252) | 06 | 3 | 05, 17, 20 |
| [`refuse_text`](ubuntu/serenedb/serene_ask.py:3641) | 07 | 3 | 12, 13, 20 |
| [`measures_of`](ubuntu/serenedb/serene_ask.py:4027) | 08 | 3 | 16, 18, 20 |
| [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:4140) | 09 | 3 | 05, 11, 20 |
| [`rank_question_text`](ubuntu/serenedb/serene_ask.py:4979) | 10 | 3 | 05, 11, 16 |
| [`sales_sum_intent`](ubuntu/serenedb/serene_ask.py:5406) | 11 | 3 | 05, 16, 20 |
| [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5552) | 11 | 3 | 05, 10, 20 |
| [`sales_money_measure`](ubuntu/serenedb/serene_ask.py:5739) | 11 | 3 | 16, 18, 20 |
| [`sales_qty_measure`](ubuntu/serenedb/serene_ask.py:5762) | 11 | 3 | 16, 18, 20 |
| [`measure_captions`](ubuntu/serenedb/serene_ask.py:7023) | 14 | 3 | 16, 18, 20 |
| [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7864) | 15 | 3 | 05, 09, 10 |
| [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7978) | 15 | 3 | 05, 13, 20 |
| [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:9110) | 17 | 3 | 10, 11, 20 |
| [`_group_leader`](ubuntu/serenedb/serene_ask.py:9271) | 17 | 3 | 10, 15, 19 |
| [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9748) | 18 | 3 | 10, 15, 20 |
| [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9842) | 18 | 3 | 10, 16, 20 |
| [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9854) | 18 | 3 | 09, 10, 20 |
| [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9894) | 18 | 3 | 10, 16, 20 |
| [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:10438) | 19 | 3 | 07, 18, 20 |

## Внутренние функции зоны

Функции, которые никто снаружи своей зоны не вызывает (включая ни разу не вызванные из других зон).

### 01 infra-trace-llm (13/32)

- `_TokenAcc.__init__`
- `_TokenAcc.diag_dict`
- `_ds_chat_body`
- `_ds_chat_content`
- `_embed_host_base`
- `_embed_one_native`
- `_embed_request`
- `_embed_secret_name_from_env`
- `_ensure_embed_secret`
- `_new_rid`
- `_reload_embed_native_env`
- `_token_acc_record`
- `ds_chat_post`

### 02 intent (10/15)

- `_field_key`
- `_field_lead`
- `_first_intent_object`
- `_intent_date`
- `_intent_terms`
- `_json_blocks`
- `_merge_intents`
- `_normalize_intent`
- `_one_intent`
- `same_concept_groups`

### 03 period-windows (5/21)

- `_assumed_sliding_week_not_calendar`
- `_is_current_calendar_week`
- `_is_seven_day_span`
- `_period_form_id`
- `_period_origin`

### 04 calendar-axis (7/11)

- `_day_basis_reading`
- `_sql_ident`
- `calendar_axis_readings`
- `calendar_map_rows`
- `calendar_registers`
- `calendar_working_day_keys`
- `prefer_day_basis_leader`

### 05 entity-form (17/26)

- `_shift_date_years`
- `_shift_period_years`
- `aggregate_distinct_axis`
- `entity_form_atom_complement`
- `entity_form_atom_distinct`
- `entity_form_axis_on_sales`
- `entity_form_compute`
- `entity_form_count_target_is_movement`
- `entity_form_expand_pool`
- `entity_form_movements_for_kind`
- `entity_form_pick`
- `entity_form_pre_entity_ok`
- `entity_form_rank_single_window`
- `entity_form_rolling_year`
- `entity_form_structs`
- `sales_compare_split_month_pair`
- `sales_compare_split_month_pair._full`

### 06 entity-search (4/16)

- `_fetch`
- `_like_pattern`
- `card_hits`
- `with_refs`

### 07 rrf-vectors (7/18)

- `_corpus_ivf_ready`
- `_fused_python_rrf`
- `_fused_sql_rrf`
- `_resolver_ivf_ready`
- `_rrf_corpus_branch`
- `_rrf_entity_branches`
- `clarify_text`

### 08 measures-totals (0/4)

—

### 09 fork-detector (19/32)

- `_class_branch_label`
- `_fork_answering_sums`
- `_fork_atom_equiv_fp`
- `_fork_day_basis_groups`
- `_fork_headline_doc_measures`
- `_fork_headline_measure`
- `_fork_headline_measure._pick_sum_headline`
- `_fork_key_for_period`
- `_fork_log_day_basis`
- `_fork_relevant._sum_fallback`
- `_fork_relevant._with_doc_hdr`
- `_fork_word_names_measure`
- `_window_fp_base`
- `_window_tuple_from_period`
- `fork_classes`
- `fork_classes_windowed`
- `fork_label_siblings`
- `fork_scan`
- `fork_scan_readings`

### 10 rank (6/15)

- `question_wants_breakdown`
- `rank_axis_label_rows`
- `rank_axis_pick`
- `rank_leader_answer_text`
- `rank_leader_atom`
- `rank_product_axis_col`

### 11 sales (7/28)

- `_alias_role_in_question`
- `_is_price_list_noise`
- `_sales_product_rank_qty`
- `sales_lift_possible`
- `sales_rank_canon_measure`
- `sales_rank_product_axis`
- `sales_ticket_hatch`

### 12 stock-balance (7/17)

- `_balance_map_by_src`
- `_stems_of_text`
- `_stock_scaffold_stems`
- `balance_capable_sources`
- `balance_map_rows`
- `balance_registers`
- `stock_asks_named_product._is_named_term`

### 13 fork-outcomes (8/17)

- `_class_day_basis`
- `_class_window_form`
- `_dedupe_fork_classes`
- `_fork_applicable_classes`
- `_rivals_figures_empty`
- `fork_leader_class`
- `ordered_fork_classes`
- `stock_balance_is_sales_noise`

### 14 clarify-memory (16/35)

- `_alias_parts`
- `_new_decision_id`
- `_purge_decisions`
- `_resolved_key`
- `_slot_fp`
- `_word_hits_text`
- `ambiguity_of_options`
- `choice_error_response`
- `choice_levels_proven`
- `clarify_complete`
- `db_fingerprint`
- `issue_decision`
- `options_version`
- `peek_decision`
- `question_fingerprint`
- `reset_decisions_for_tests`

### 15 answer-atoms (4/15)

- `_atom_exact_value`
- `_period_window_human`
- `determined_answer_rivals.add`
- `determined_answer_rivals.family`

### 16 veto-pick-entity (5/29)

- `alive_measure_names`
- `any_live_src_supports_question`
- `atom_whitelist_labels`
- `atom_whitelist_numbers`
- `format_measure_empty_pivot`

### 17 aggregate-groups (2/16)

- `_group_fold`
- `resolve_member_names`

### 18 compose (2/23)

- `_group_value_by_name`
- `_measure_dimension`

### 19 answer-check (5/14)

- `_date_spans`
- `_plausible`
- `_readings`
- `_threshold_values`
- `claims_in_text`

### 20 ask-main-http (97/104)

- `Handler._send`
- `Handler.do_GET`
- `Handler.do_POST`
- `Handler.log_message`
- `_answer_checked_core`
- `_answer_checked_core.plain`
- `_ask_journal_write`
- `_ask_journal_write._insert_row`
- `_assemble_health_gap`
- `_attach_native_freshness`
- `_build_ask_scope`
- `_classify_health_gap`
- `_coverage_answer`
- `_coverage_of`
- `_day_ord`
- `_ensure_ask_scope_table`
- `_entity_counts_objects`
- `_filter_dates`
- `_gate_need`
- `_health_gap`
- `_health_period_relative_forms`
- `_health_search_idx_name`
- `_journal_alias_ver`
- `_journal_atoms_slim`
- `_journal_build_ts`
- `_journal_clarify_options`
- `_journal_code_md5`
- `_journal_doubt`
- `_journal_fork_keys`
- `_journal_intent`
- `_journal_keep_n`
- `_journal_sql_bool`
- `_journal_sql_int`
- `_journal_ticket_variant`
- `_journal_uncounted_truncated`
- `_measure_health_gap`
- `_measure_native_index_freshness`
- `_need_clarify`
- `_opt_values`
- `_period_day_label.one`
- `_persist_ask_scope`
- `_real_corpus_object_gaps`
- `_src_covers_term_stems`
- `_table_has_ref_key`
- `_term_stems`
- `_try_memory_apply`
- `_vitrina_objects`
- `_word_hits_measure`
- `align_picked_to_terms`
- `ambiguous_labels`
- `answer`
- `answer._alias_clarify`
- `answer._alias_verdict`
- `answer._alias_verdict._probe`
- `answer._alias_verdict._место`
- `answer._checked`
- `answer._family`
- `answer._k6_mk_clarify`
- `answer.шаг`
- `answer_checked`
- `apply_prior_period`
- `axis_focus_plan`
- `build_period_empty_answer`
- `clarify_choice_line`
- `clarify_choice_prompt`
- `count_figures`
- `dates_outside_period_filter`
- `drop_period_preds`
- `empty_after_period_action`
- `entity_has_dates`
- `format_period_empty_text`
- `gate`
- `gate.allow`
- `gate_out`
- `label_has_meta_src`
- `label_with_kind`
- `live_src_counts`
- `looks_like_src_table`
- `main`
- `opts_hints`
- `period_assumed_needs_clarify`
- `period_empty_outcome`
- `period_is_canon_guess`
- `period_slot_for_inherit`
- `question_facts`
- `resolve_focus`
- `rows_seen`
- `sales_fork_blocks_clarify`
- `sales_fork_canon_empty_src`
- `sales_period_empty`
- `sales_period_window_active`
- `stock_subject_needs_clarify`
- `try_sales_fork_period_empty_answer`
- `warehouse_axis_values`
- `warehouse_axis_values._take`
- `warehouse_clarify`
- `without_list_markers`

## Чтение окружения

Всего: 109.

| переменная | строка | умолчание | функция |
|---|---:|---|---|
| `SERENEDB_DSN_RO` | [67](ubuntu/serenedb/serene_ask.py:67) | — | `(модуль)` |
| `PGPASSWORD` | [68](ubuntu/serenedb/serene_ask.py:68) | "" | `(модуль)` |
| `RESOLVER_DSN` | [74](ubuntu/serenedb/serene_ask.py:74) | "" | `(модуль)` |
| `RESOLVER_PW` | [75](ubuntu/serenedb/serene_ask.py:75) | "" | `(модуль)` |
| `ASK_LISTEN_HOST` | [76](ubuntu/serenedb/serene_ask.py:76) | "127.0.0.1" | `(модуль)` |
| `ASK_LISTEN_PORT` | [77](ubuntu/serenedb/serene_ask.py:77) | "8091" | `(модуль)` |
| `ASK_TOKEN` | [78](ubuntu/serenedb/serene_ask.py:78) | "" | `(модуль)` |
| `ASK_MONEY_UNIT` | [79](ubuntu/serenedb/serene_ask.py:79) | "" | `(модуль)` |
| `ASK_CARD_TABLE` | [90](ubuntu/serenedb/serene_ask.py:90) | "search_entity_card" | `(модуль)` |
| `ASK_PICK_BUDGET_CHARS` | [96](ubuntu/serenedb/serene_ask.py:96) | "8000" | `(модуль)` |
| `ASK_ROWS_BUDGET_CHARS` | [103](ubuntu/serenedb/serene_ask.py:103) | "24000" | `(модуль)` |
| `ASK_TERMS_FOR` | [107](ubuntu/serenedb/serene_ask.py:107) | "3" | `(модуль)` |
| `ASK_COVERAGE_TOP` | [111](ubuntu/serenedb/serene_ask.py:111) | "15" | `(модуль)` |
| `ASK_STALE_WARN_SEC` | [115](ubuntu/serenedb/serene_ask.py:115) | "3600" | `(модуль)` |
| `ASK_TERMS_TOP` | [116](ubuntu/serenedb/serene_ask.py:116) | "6" | `(модуль)` |
| `ASK_TOPK` | [117](ubuntu/serenedb/serene_ask.py:117) | "40" | `(модуль)` |
| `ASK_TRACE` | [121](ubuntu/serenedb/serene_ask.py:121) | "1" | `(модуль)` |
| `ASK_ROWS_TO_MODEL` | [122](ubuntu/serenedb/serene_ask.py:122) | "25" | `(модуль)` |
| `ASK_SCORER` | [187](ubuntu/serenedb/serene_ask.py:187) | "bm25" | `(модуль)` |
| `ASK_REFS_BOOST` | [199](ubuntu/serenedb/serene_ask.py:199) | "8.0" | `(модуль)` |
| `ASK_ORDER_BY_MEANING` | [206](ubuntu/serenedb/serene_ask.py:206) | "1" | `(модуль)` |
| `RERANK_URL` | [222](ubuntu/serenedb/serene_ask.py:222) | — | `(модуль)` |
| `ALIBABA_RERANK_URL` | [223](ubuntu/serenedb/serene_ask.py:223) | — | `(модуль)` |
| `RERANK_MODEL` | [225](ubuntu/serenedb/serene_ask.py:225) | — | `(модуль)` |
| `ALIBABA_RERANK_MODEL` | [226](ubuntu/serenedb/serene_ask.py:226) | — | `(модуль)` |
| `RERANK_API` | [227](ubuntu/serenedb/serene_ask.py:227) | "<expr>" | `(модуль)` |
| `ASK_RERANK_TOP` | [232](ubuntu/serenedb/serene_ask.py:232) | "60" | `(модуль)` |
| `DEEPSEEK_BASE` | [240](ubuntu/serenedb/serene_ask.py:240) | "https://api.deepseek.com" | `(модуль)` |
| `DEEPSEEK_API_KEY` | [241](ubuntu/serenedb/serene_ask.py:241) | "" | `(модуль)` |
| `DEEPSEEK_MODEL` | [249](ubuntu/serenedb/serene_ask.py:249) | "deepseek-v4-pro" | `(модуль)` |
| `DEEPSEEK_THINKING` | [250](ubuntu/serenedb/serene_ask.py:250) | "disabled" | `(модуль)` |
| `ASK_THINKING_OFF_BODY` | [253](ubuntu/serenedb/serene_ask.py:253) | "" | `(модуль)` |
| `EMBED_BASE_URL` | [262](ubuntu/serenedb/serene_ask.py:262) | — | `(модуль)` |
| `ALIBABA_EMBED_URL` | [263](ubuntu/serenedb/serene_ask.py:263) | "" | `(модуль)` |
| `EMBED_API` | [269](ubuntu/serenedb/serene_ask.py:269) | "openai" | `(модуль)` |
| `EMBED_QUERY_PATH` | [270](ubuntu/serenedb/serene_ask.py:270) | "/embed" | `(модуль)` |
| `EMBED_UA` | [273](ubuntu/serenedb/serene_ask.py:273) | "curl/8.5.0" | `(модуль)` |
| `EMBED_HEALTH_URL` | [275](ubuntu/serenedb/serene_ask.py:275) | — | `(модуль)` |
| `EMBED_API_KEY` | [276](ubuntu/serenedb/serene_ask.py:276) | — | `(модуль)` |
| `ALIBABA_API_KEY` | [276](ubuntu/serenedb/serene_ask.py:276) | "" | `(модуль)` |
| `EMBED_MODEL` | [277](ubuntu/serenedb/serene_ask.py:277) | "text-embedding-v4" | `(модуль)` |
| `RERANK_API_KEY` | [280](ubuntu/serenedb/serene_ask.py:280) | — | `(модуль)` |
| `EMBED_DIM` | [288](ubuntu/serenedb/serene_ask.py:288) | "1024" | `(модуль)` |
| `EMBED_PATH` | [300](ubuntu/serenedb/serene_ask.py:300) | "/v1/embeddings" | `(модуль)` |
| `ASK_EMBED_NATIVE` | [301](ubuntu/serenedb/serene_ask.py:301) | "0" | `(модуль)` |
| `ASK_NO_DATA_TEXT` | [321](ubuntu/serenedb/serene_ask.py:321) | "" | `(модуль)` |
| `ASK_TOTAL_TEXT` | [322](ubuntu/serenedb/serene_ask.py:322) | "" | `(модуль)` |
| `ASK_STALE_TEXT` | [325](ubuntu/serenedb/serene_ask.py:325) | "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад." | `(модуль)` |
| `ASK_EMB_CACHE` | [675](ubuntu/serenedb/serene_ask.py:675) | "256" | `(модуль)` |
| `ASK_EMB_RETRY` | [679](ubuntu/serenedb/serene_ask.py:679) | "2" | `(модуль)` |
| `ASK_EMB_RETRY_PAUSE` | [680](ubuntu/serenedb/serene_ask.py:680) | "0.4" | `(модуль)` |
| `ASK_EMB_TIMEOUT` | [681](ubuntu/serenedb/serene_ask.py:681) | "60" | `(модуль)` |
| `ASK_INTENT_MAX_TOKENS` | [899](ubuntu/serenedb/serene_ask.py:899) | "400" | `(модуль)` |
| `ASK_INTENT_SAMPLES` | [900](ubuntu/serenedb/serene_ask.py:900) | "5" | `(модуль)` |
| `ASK_INTENT_LEAD` | [901](ubuntu/serenedb/serene_ask.py:901) | "3" | `(модуль)` |
| `ASK_INTENT_MEMO` | [903](ubuntu/serenedb/serene_ask.py:903) | "512" | `(модуль)` |
| `ASK_INTENT_GROUPS` | [910](ubuntu/serenedb/serene_ask.py:910) | "6" | `(модуль)` |
| `ASK_INTENT_ALTS` | [911](ubuntu/serenedb/serene_ask.py:911) | "6" | `(модуль)` |
| `ASK_STEM_DICT` | [914](ubuntu/serenedb/serene_ask.py:914) | "search_dict_stem" | `(модуль)` |
| `ASK_SOLR_SYNONYMS` | [917](ubuntu/serenedb/serene_ask.py:917) | "0" | `(модуль)` |
| `ASK_SOLR_SYNONYMS_DICT` | [918](ubuntu/serenedb/serene_ask.py:918) | "" | `(модуль)` |
| `ASK_CALENDAR_AXIS` | [1435](ubuntu/serenedb/serene_ask.py:1435) | "0" | `(модуль)` |
| `ASK_SALES_RANK_CANON` | [1437](ubuntu/serenedb/serene_ask.py:1437) | "0" | `(модуль)` |
| `ASK_ATOM_TERMINAL` | [1439](ubuntu/serenedb/serene_ask.py:1439) | "0" | `(модуль)` |
| `ASK_ENTITY_FORM` | [1442](ubuntu/serenedb/serene_ask.py:1442) | "0" | `(модуль)` |
| `ASK_RESOLVE_NEAR` | [3745](ubuntu/serenedb/serene_ask.py:3745) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [3746](ubuntu/serenedb/serene_ask.py:3746) | "3" | `(модуль)` |
| `ASK_ALIAS_TOP` | [3912](ubuntu/serenedb/serene_ask.py:3912) | "8" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [3915](ubuntu/serenedb/serene_ask.py:3915) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [3920](ubuntu/serenedb/serene_ask.py:3920) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [3925](ubuntu/serenedb/serene_ask.py:3925) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [3928](ubuntu/serenedb/serene_ask.py:3928) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [3929](ubuntu/serenedb/serene_ask.py:3929) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [3934](ubuntu/serenedb/serene_ask.py:3934) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [3935](ubuntu/serenedb/serene_ask.py:3935) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_ALIAS_VETO` | [3948](ubuntu/serenedb/serene_ask.py:3948) | "1" | `(модуль)` |
| `ASK_PROBE` | [3955](ubuntu/serenedb/serene_ask.py:3955) | "0" | `(модуль)` |
| `ASK_SKIP_SERVICE_RIVALS` | [3959](ubuntu/serenedb/serene_ask.py:3959) | "1" | `(модуль)` |
| `ASK_ALIAS_BY_CONCEPTS` | [3971](ubuntu/serenedb/serene_ask.py:3971) | "0" | `(модуль)` |
| `ASK_VETO_NEEDS_RANK` | [3986](ubuntu/serenedb/serene_ask.py:3986) | "0" | `(модуль)` |
| `ASK_VETO_HEAD_WINS` | [3996](ubuntu/serenedb/serene_ask.py:3996) | "1" | `(модуль)` |
| `ASK_MEANING_TOP` | [4022](ubuntu/serenedb/serene_ask.py:4022) | "0" | `(модуль)` |
| `ASK_FORK_DETECT` | [4114](ubuntu/serenedb/serene_ask.py:4114) | "1" | `(модуль)` |
| `ASK_FORK_OUTCOMES` | [4115](ubuntu/serenedb/serene_ask.py:4115) | "1" | `(модуль)` |
| `ASK_JOURNAL` | [4118](ubuntu/serenedb/serene_ask.py:4118) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [4123](ubuntu/serenedb/serene_ask.py:4123) | "1" | `(модуль)` |
| `ASK_MEMORY_APPLY` | [4125](ubuntu/serenedb/serene_ask.py:4125) | "0" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [4136](ubuntu/serenedb/serene_ask.py:4136) | "600" | `(модуль)` |
| `ASK_RAW_FOCUS_TRUST` | [7200](ubuntu/serenedb/serene_ask.py:7200) | "0" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [7201](ubuntu/serenedb/serene_ask.py:7201) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [11179](ubuntu/serenedb/serene_ask.py:11179) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [11187](ubuntu/serenedb/serene_ask.py:11187) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [11188](ubuntu/serenedb/serene_ask.py:11188) | "search_idx" | `(модуль)` |
| `ASK_SIGNAL_DISAGREE` | [11516](ubuntu/serenedb/serene_ask.py:11516) | "1" | `(модуль)` |
| `ASK_REQUIRE_SUPPORT` | [11518](ubuntu/serenedb/serene_ask.py:11518) | "1" | `(модуль)` |
| `ASK_ARBITER_MAX` | [11521](ubuntu/serenedb/serene_ask.py:11521) | "3" | `(модуль)` |
| `ASK_ARBITER_DETECTS` | [11527](ubuntu/serenedb/serene_ask.py:11527) | "1" | `(модуль)` |
| `ASK_NOT_FOR` | [11529](ubuntu/serenedb/serene_ask.py:11529) | "1" | `(модуль)` |
| `ASK_STEM_DICT` | [11532](ubuntu/serenedb/serene_ask.py:11532) | "search_dict_stem" | `(модуль)` |
| `ASK_AMBIG_TTL` | [11535](ubuntu/serenedb/serene_ask.py:11535) | "300" | `(модуль)` |
| `ASK_ENOUGH` | [15858](ubuntu/serenedb/serene_ask.py:15858) | "1" | `(модуль)` |
| `ASK_SLOT_COVER` | [15860](ubuntu/serenedb/serene_ask.py:15860) | "0" | `(модуль)` |
| `EMBED_SECRET` | [293](ubuntu/serenedb/serene_ask.py:293) | — | `_embed_secret_name_from_env` |
| `EMBED_SECRETS` | [293](ubuntu/serenedb/serene_ask.py:293) | — | `_embed_secret_name_from_env` |
| `EMBED_PATH` | [309](ubuntu/serenedb/serene_ask.py:309) | "/v1/embeddings" | `_reload_embed_native_env` |
| `ASK_EMBED_NATIVE` | [310](ubuntu/serenedb/serene_ask.py:310) | "0" | `_reload_embed_native_env` |
| `EMBED_DIM` | [311](ubuntu/serenedb/serene_ask.py:311) | "1024" | `_reload_embed_native_env` |
| `EMBED_HOST` | [373](ubuntu/serenedb/serene_ask.py:373) | — | `_embed_host_base` |
| `ASK_JOURNAL_KEEP` | [15957](ubuntu/serenedb/serene_ask.py:15957) | — | `_journal_keep_n` |

## Обращения наружу

Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`.

### psql (158)

- [`ubuntu/serenedb/serene_ask.py:439`](ubuntu/serenedb/serene_ask.py:439) в `emb_ready`
- [`ubuntu/serenedb/serene_ask.py:695`](ubuntu/serenedb/serene_ask.py:695) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:710`](ubuntu/serenedb/serene_ask.py:710) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:729`](ubuntu/serenedb/serene_ask.py:729) в `_embed_one_native`
- [`ubuntu/serenedb/serene_ask.py:1080`](ubuntu/serenedb/serene_ask.py:1080) в `same_concept_groups`
- [`ubuntu/serenedb/serene_ask.py:1746`](ubuntu/serenedb/serene_ask.py:1746) в `period_relative_forms`
- [`ubuntu/serenedb/serene_ask.py:1834`](ubuntu/serenedb/serene_ask.py:1834) в `calendar_registers`
- [`ubuntu/serenedb/serene_ask.py:1850`](ubuntu/serenedb/serene_ask.py:1850) в `calendar_working_day_keys`
- [`ubuntu/serenedb/serene_ask.py:1870`](ubuntu/serenedb/serene_ask.py:1870) в `calendar_map_rows`
- [`ubuntu/serenedb/serene_ask.py:2295`](ubuntu/serenedb/serene_ask.py:2295) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2329`](ubuntu/serenedb/serene_ask.py:2329) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2546`](ubuntu/serenedb/serene_ask.py:2546) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/serene_ask.py:2776`](ubuntu/serenedb/serene_ask.py:2776) в `_fetch`
- [`ubuntu/serenedb/serene_ask.py:2848`](ubuntu/serenedb/serene_ask.py:2848) в `probe`
- [`ubuntu/serenedb/serene_ask.py:2951`](ubuntu/serenedb/serene_ask.py:2951) в `match_expr`
- [`ubuntu/serenedb/serene_ask.py:2990`](ubuntu/serenedb/serene_ask.py:2990) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:3009`](ubuntu/serenedb/serene_ask.py:3009) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:3079`](ubuntu/serenedb/serene_ask.py:3079) в `partial_tables`
- [`ubuntu/serenedb/serene_ask.py:3111`](ubuntu/serenedb/serene_ask.py:3111) в `tables_of`
- [`ubuntu/serenedb/serene_ask.py:3181`](ubuntu/serenedb/serene_ask.py:3181) в `alias_hits`
- [`ubuntu/serenedb/serene_ask.py:3221`](ubuntu/serenedb/serene_ask.py:3221) в `card_hits`
- [`ubuntu/serenedb/serene_ask.py:3303`](ubuntu/serenedb/serene_ask.py:3303) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/serene_ask.py:3383`](ubuntu/serenedb/serene_ask.py:3383) в `_fused_sql_rrf`
- [`ubuntu/serenedb/serene_ask.py:3391`](ubuntu/serenedb/serene_ask.py:3391) в `_fused_python_rrf`
- [`ubuntu/serenedb/serene_ask.py:3492`](ubuntu/serenedb/serene_ask.py:3492) в `near_tables`
- [`ubuntu/serenedb/serene_ask.py:3528`](ubuntu/serenedb/serene_ask.py:3528) в `rows_of`
- [`ubuntu/serenedb/serene_ask.py:3582`](ubuntu/serenedb/serene_ask.py:3582) в `signal_terms`
- [`ubuntu/serenedb/serene_ask.py:3811`](ubuntu/serenedb/serene_ask.py:3811) в `_resolve_values_corpus`
- [`ubuntu/serenedb/serene_ask.py:4035`](ubuntu/serenedb/serene_ask.py:4035) в `measures_of`
- [`ubuntu/serenedb/serene_ask.py:4046`](ubuntu/serenedb/serene_ask.py:4046) в `measure_aliases_of`
- [`ubuntu/serenedb/serene_ask.py:4087`](ubuntu/serenedb/serene_ask.py:4087) в `totals_of`
- [`ubuntu/serenedb/serene_ask.py:4151`](ubuntu/serenedb/serene_ask.py:4151) в `_measures_by_src`
- [`ubuntu/serenedb/serene_ask.py:4170`](ubuntu/serenedb/serene_ask.py:4170) в `_aliases_by_src`
- [`ubuntu/serenedb/serene_ask.py:4308`](ubuntu/serenedb/serene_ask.py:4308) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4331`](ubuntu/serenedb/serene_ask.py:4331) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4608`](ubuntu/serenedb/serene_ask.py:4608) в `_fork_log_day_basis`
- [`ubuntu/serenedb/serene_ask.py:4648`](ubuntu/serenedb/serene_ask.py:4648) в `_fork_log`
- [`ubuntu/serenedb/serene_ask.py:4668`](ubuntu/serenedb/serene_ask.py:4668) в `fork_labels_of`
- [`ubuntu/serenedb/serene_ask.py:4693`](ubuntu/serenedb/serene_ask.py:4693) в `fork_labels_covering`
- [`ubuntu/serenedb/serene_ask.py:5065`](ubuntu/serenedb/serene_ask.py:5065) в `rank_axis_label_rows`
- [`ubuntu/serenedb/serene_ask.py:5353`](ubuntu/serenedb/serene_ask.py:5353) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5371`](ubuntu/serenedb/serene_ask.py:5371) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5488`](ubuntu/serenedb/serene_ask.py:5488) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5512`](ubuntu/serenedb/serene_ask.py:5512) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5636`](ubuntu/serenedb/serene_ask.py:5636) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5660`](ubuntu/serenedb/serene_ask.py:5660) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5692`](ubuntu/serenedb/serene_ask.py:5692) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5672`](ubuntu/serenedb/serene_ask.py:5672) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:6122`](ubuntu/serenedb/serene_ask.py:6122) в `prefer_entity_for_catalog_count`
- [`ubuntu/serenedb/serene_ask.py:6230`](ubuntu/serenedb/serene_ask.py:6230) в `balance_registers`
- [`ubuntu/serenedb/serene_ask.py:6248`](ubuntu/serenedb/serene_ask.py:6248) в `balance_map_rows`
- [`ubuntu/serenedb/serene_ask.py:6293`](ubuntu/serenedb/serene_ask.py:6293) в `balance_registers_with_goods`
- [`ubuntu/serenedb/serene_ask.py:6307`](ubuntu/serenedb/serene_ask.py:6307) в `_stems_of_text`
- [`ubuntu/serenedb/serene_ask.py:6396`](ubuntu/serenedb/serene_ask.py:6396) в `filter_balance_structural`
- [`ubuntu/serenedb/serene_ask.py:6432`](ubuntu/serenedb/serene_ask.py:6432) в `balance_bridge_clarify`
- [`ubuntu/serenedb/serene_ask.py:6909`](ubuntu/serenedb/serene_ask.py:6909) в `fork_outcome_c`
- [`ubuntu/serenedb/serene_ask.py:7225`](ubuntu/serenedb/serene_ask.py:7225) в `db_fingerprint`
- [`ubuntu/serenedb/serene_ask.py:8309`](ubuntu/serenedb/serene_ask.py:8309) в `k6_dual_atom_clarify_return`
- [`ubuntu/serenedb/serene_ask.py:8473`](ubuntu/serenedb/serene_ask.py:8473) в `kind_has_corpus_support`
- [`ubuntu/serenedb/serene_ask.py:8739`](ubuntu/serenedb/serene_ask.py:8739) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8777`](ubuntu/serenedb/serene_ask.py:8777) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8999`](ubuntu/serenedb/serene_ask.py:8999) в `aggregate`
- [`ubuntu/serenedb/serene_ask.py:9048`](ubuntu/serenedb/serene_ask.py:9048) в `src_is_child`
- [`ubuntu/serenedb/serene_ask.py:9060`](ubuntu/serenedb/serene_ask.py:9060) в `refcols_of`
- [`ubuntu/serenedb/serene_ask.py:9077`](ubuntu/serenedb/serene_ask.py:9077) в `holders_of_target`
- [`ubuntu/serenedb/serene_ask.py:9097`](ubuntu/serenedb/serene_ask.py:9097) в `measures_of_many`
- [`ubuntu/serenedb/serene_ask.py:9119`](ubuntu/serenedb/serene_ask.py:9119) в `kind_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:9154`](ubuntu/serenedb/serene_ask.py:9154) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:9181`](ubuntu/serenedb/serene_ask.py:9181) в `term_ref_owners`
- [`ubuntu/serenedb/serene_ask.py:9215`](ubuntu/serenedb/serene_ask.py:9215) в `term_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:9253`](ubuntu/serenedb/serene_ask.py:9253) в `resolve_member_names`
- [`ubuntu/serenedb/serene_ask.py:9362`](ubuntu/serenedb/serene_ask.py:9362) в `aggregate_groups`
- [`ubuntu/serenedb/serene_ask.py:9428`](ubuntu/serenedb/serene_ask.py:9428) в `axis_clarify_options`
- [`ubuntu/serenedb/serene_ask.py:9871`](ubuntu/serenedb/serene_ask.py:9871) в `_table_label`
- [`ubuntu/serenedb/serene_ask.py:11063`](ubuntu/serenedb/serene_ask.py:11063) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:11071`](ubuntu/serenedb/serene_ask.py:11071) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:11083`](ubuntu/serenedb/serene_ask.py:11083) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:11091`](ubuntu/serenedb/serene_ask.py:11091) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:11115`](ubuntu/serenedb/serene_ask.py:11115) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:11152`](ubuntu/serenedb/serene_ask.py:11152) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:11125`](ubuntu/serenedb/serene_ask.py:11125) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:11242`](ubuntu/serenedb/serene_ask.py:11242) в `_measure_health_gap`
- [`ubuntu/serenedb/serene_ask.py:11262`](ubuntu/serenedb/serene_ask.py:11262) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/serene_ask.py:11283`](ubuntu/serenedb/serene_ask.py:11283) в `_classify_health_gap`
- [`ubuntu/serenedb/serene_ask.py:11338`](ubuntu/serenedb/serene_ask.py:11338) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/serene_ask.py:11435`](ubuntu/serenedb/serene_ask.py:11435) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:11444`](ubuntu/serenedb/serene_ask.py:11444) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:11647`](ubuntu/serenedb/serene_ask.py:11647) в `ambiguous_labels`
- [`ubuntu/serenedb/serene_ask.py:11693`](ubuntu/serenedb/serene_ask.py:11693) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11700`](ubuntu/serenedb/serene_ask.py:11700) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11710`](ubuntu/serenedb/serene_ask.py:11710) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11720`](ubuntu/serenedb/serene_ask.py:11720) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11800`](ubuntu/serenedb/serene_ask.py:11800) в `live_src_counts`
- [`ubuntu/serenedb/serene_ask.py:11989`](ubuntu/serenedb/serene_ask.py:11989) в `dates_outside_period_filter`
- [`ubuntu/serenedb/serene_ask.py:12121`](ubuntu/serenedb/serene_ask.py:12121) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:12124`](ubuntu/serenedb/serene_ask.py:12124) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:12136`](ubuntu/serenedb/serene_ask.py:12136) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:12139`](ubuntu/serenedb/serene_ask.py:12139) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:12159`](ubuntu/serenedb/serene_ask.py:12159) в `align_picked_to_terms`
- [`ubuntu/serenedb/serene_ask.py:12215`](ubuntu/serenedb/serene_ask.py:12215) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:12220`](ubuntu/serenedb/serene_ask.py:12220) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:12239`](ubuntu/serenedb/serene_ask.py:12239) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:12279`](ubuntu/serenedb/serene_ask.py:12279) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:12376`](ubuntu/serenedb/serene_ask.py:12376) в `axis_focus_plan`
- [`ubuntu/serenedb/serene_ask.py:12515`](ubuntu/serenedb/serene_ask.py:12515) в `warehouse_axis_values`
- [`ubuntu/serenedb/serene_ask.py:12549`](ubuntu/serenedb/serene_ask.py:12549) в `warehouse_axis_values`
- [`ubuntu/serenedb/serene_ask.py:12967`](ubuntu/serenedb/serene_ask.py:12967) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13108`](ubuntu/serenedb/serene_ask.py:13108) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13676`](ubuntu/serenedb/serene_ask.py:13676) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13753`](ubuntu/serenedb/serene_ask.py:13753) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13800`](ubuntu/serenedb/serene_ask.py:13800) в `answer`
- [`ubuntu/serenedb/serene_ask.py:15057`](ubuntu/serenedb/serene_ask.py:15057) в `answer`
- [`ubuntu/serenedb/serene_ask.py:15401`](ubuntu/serenedb/serene_ask.py:15401) в `answer`
- [`ubuntu/serenedb/serene_ask.py:15422`](ubuntu/serenedb/serene_ask.py:15422) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13117`](ubuntu/serenedb/serene_ask.py:13117) в `answer`
- [`ubuntu/serenedb/serene_ask.py:15192`](ubuntu/serenedb/serene_ask.py:15192) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13154`](ubuntu/serenedb/serene_ask.py:13154) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13193`](ubuntu/serenedb/serene_ask.py:13193) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13358`](ubuntu/serenedb/serene_ask.py:13358) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13387`](ubuntu/serenedb/serene_ask.py:13387) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13409`](ubuntu/serenedb/serene_ask.py:13409) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13428`](ubuntu/serenedb/serene_ask.py:13428) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13452`](ubuntu/serenedb/serene_ask.py:13452) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13605`](ubuntu/serenedb/serene_ask.py:13605) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13739`](ubuntu/serenedb/serene_ask.py:13739) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13938`](ubuntu/serenedb/serene_ask.py:13938) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14611`](ubuntu/serenedb/serene_ask.py:14611) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14791`](ubuntu/serenedb/serene_ask.py:14791) в `answer`
- [`ubuntu/serenedb/serene_ask.py:15214`](ubuntu/serenedb/serene_ask.py:15214) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13138`](ubuntu/serenedb/serene_ask.py:13138) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13850`](ubuntu/serenedb/serene_ask.py:13850) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14474`](ubuntu/serenedb/serene_ask.py:14474) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13289`](ubuntu/serenedb/serene_ask.py:13289) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13765`](ubuntu/serenedb/serene_ask.py:13765) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13873`](ubuntu/serenedb/serene_ask.py:13873) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14512`](ubuntu/serenedb/serene_ask.py:14512) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14578`](ubuntu/serenedb/serene_ask.py:14578) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14593`](ubuntu/serenedb/serene_ask.py:14593) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13800`](ubuntu/serenedb/serene_ask.py:13800) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13850`](ubuntu/serenedb/serene_ask.py:13850) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13873`](ubuntu/serenedb/serene_ask.py:13873) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13938`](ubuntu/serenedb/serene_ask.py:13938) в `answer._alias_clarify`
- [`ubuntu/serenedb/serene_ask.py:15909`](ubuntu/serenedb/serene_ask.py:15909) в `entity_has_dates`
- [`ubuntu/serenedb/serene_ask.py:15963`](ubuntu/serenedb/serene_ask.py:15963) в `_journal_keep_n`
- [`ubuntu/serenedb/serene_ask.py:15987`](ubuntu/serenedb/serene_ask.py:15987) в `_journal_build_ts`
- [`ubuntu/serenedb/serene_ask.py:16000`](ubuntu/serenedb/serene_ask.py:16000) в `_journal_alias_ver`
- [`ubuntu/serenedb/serene_ask.py:16234`](ubuntu/serenedb/serene_ask.py:16234) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16255`](ubuntu/serenedb/serene_ask.py:16255) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16248`](ubuntu/serenedb/serene_ask.py:16248) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16250`](ubuntu/serenedb/serene_ask.py:16250) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16257`](ubuntu/serenedb/serene_ask.py:16257) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16189`](ubuntu/serenedb/serene_ask.py:16189) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16238`](ubuntu/serenedb/serene_ask.py:16238) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16251`](ubuntu/serenedb/serene_ask.py:16251) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:16234`](ubuntu/serenedb/serene_ask.py:16234) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:16238`](ubuntu/serenedb/serene_ask.py:16238) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:16527`](ubuntu/serenedb/serene_ask.py:16527) в `Handler.do_GET`
- [`ubuntu/serenedb/serene_ask.py:16654`](ubuntu/serenedb/serene_ask.py:16654) в `Handler.do_POST`

### ds_chat (10)

- [`ubuntu/serenedb/serene_ask.py:642`](ubuntu/serenedb/serene_ask.py:642) в `arbitrate`
- [`ubuntu/serenedb/serene_ask.py:1241`](ubuntu/serenedb/serene_ask.py:1241) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:1249`](ubuntu/serenedb/serene_ask.py:1249) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:3626`](ubuntu/serenedb/serene_ask.py:3626) в `clarify_text`
- [`ubuntu/serenedb/serene_ask.py:3659`](ubuntu/serenedb/serene_ask.py:3659) в `refuse_text`
- [`ubuntu/serenedb/serene_ask.py:5117`](ubuntu/serenedb/serene_ask.py:5117) в `rank_axis_pick`
- [`ubuntu/serenedb/serene_ask.py:8842`](ubuntu/serenedb/serene_ask.py:8842) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:10263`](ubuntu/serenedb/serene_ask.py:10263) в `compose`
- [`ubuntu/serenedb/serene_ask.py:11464`](ubuntu/serenedb/serene_ask.py:11464) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:15881`](ubuntu/serenedb/serene_ask.py:15881) в `question_facts`

### embed_one (1)

- [`ubuntu/serenedb/serene_ask.py:8898`](ubuntu/serenedb/serene_ask.py:8898) в `_vec`

### rerank (5)

- [`ubuntu/serenedb/serene_ask.py:3877`](ubuntu/serenedb/serene_ask.py:3877) в `resolve_values`
- [`ubuntu/serenedb/serene_ask.py:5090`](ubuntu/serenedb/serene_ask.py:5090) в `rank_axes_rerank`
- [`ubuntu/serenedb/serene_ask.py:8702`](ubuntu/serenedb/serene_ask.py:8702) в `pick_measure`
- [`ubuntu/serenedb/serene_ask.py:9164`](ubuntu/serenedb/serene_ask.py:9164) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:13364`](ubuntu/serenedb/serene_ask.py:13364) в `answer`

### urlopen (4)

- [`ubuntu/serenedb/serene_ask.py:415`](ubuntu/serenedb/serene_ask.py:415) в `embed_model_live`
- [`ubuntu/serenedb/serene_ask.py:598`](ubuntu/serenedb/serene_ask.py:598) в `ds_chat_post`
- [`ubuntu/serenedb/serene_ask.py:800`](ubuntu/serenedb/serene_ask.py:800) в `embed_one`
- [`ubuntu/serenedb/serene_ask.py:3700`](ubuntu/serenedb/serene_ask.py:3700) в `rerank`
