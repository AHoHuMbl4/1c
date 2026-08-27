# Карта `ubuntu/serenedb/serene_ask.py`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **15931**. Функций: **463**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **30**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/serene_ask.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–910`)
- [02 intent](ubuntu/serenedb/serene_ask.py:911) — Intent (якорь `_json_blocks` … `_first_intent_object`; `911–1374`)
- [03 period-windows](ubuntu/serenedb/serene_ask.py:1375) — Периоды и окна (якорь `_num_pred` … `apply_period_leader`; `1375–1811`)
- [04 calendar-axis](ubuntu/serenedb/serene_ask.py:1812) — Календарная ось (якорь `_sql_ident` … `_working_day_doc_preds`; `1812–1995`)
- [05 entity-form](ubuntu/serenedb/serene_ask.py:1996) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `1996–2591`)
- [06 entity-search](ubuntu/serenedb/serene_ask.py:2592) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `2592–3130`)
- [07 rrf-vectors](ubuntu/serenedb/serene_ask.py:3131) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `3131–3724`)
- [08 measures-totals](ubuntu/serenedb/serene_ask.py:3725) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `3725–3968`)
- [09 fork-detector](ubuntu/serenedb/serene_ask.py:3969) — Детектор развилки (якорь `_measures_by_src` … `_class_label_lookup`; `3969–4749`)
- [10 rank](ubuntu/serenedb/serene_ask.py:4750) — Ранг (якорь `count_question_skips_axis` … `prefer_entity_for_rank`; `4750–5234`)
- [11 sales](ubuntu/serenedb/serene_ask.py:5235) — Продажи (якорь `sales_sum_intent` … `period_zero_why_question`; `5235–5952`)
- [12 stock-balance](ubuntu/serenedb/serene_ask.py:5953) — Остатки (якорь `grain_dec_from_axis_ticket` … `balance_bridge_clarify`; `5953–6245`)
- [13 fork-outcomes](ubuntu/serenedb/serene_ask.py:6246) — Исходы развилки (якорь `stock_balance_is_sales_noise` … `fork_outcome_c`; `6246–6723`)
- [14 clarify-memory](ubuntu/serenedb/serene_ask.py:6724) — Уточнение и память (якорь `_alias_parts` … `guards_skip_for_choice`; `6724–7422`)
- [15 answer-atoms](ubuntu/serenedb/serene_ask.py:7423) — Атомы ответа (якорь `stop2_active` … `fill_atom_pairs`; `7423–7804`)
- [16 veto-pick-entity](ubuntu/serenedb/serene_ask.py:7805) — Вето и выбор сущности (якорь `pair_slots_only` … `pick_entity`; `7805–8438`)
- [17 aggregate-groups](ubuntu/serenedb/serene_ask.py:8439) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `8439–8942`)
- [18 compose](ubuntu/serenedb/serene_ask.py:8943) — Формулировка (якорь `merge_period2_groups` … `compose`; `8943–9831`)
- [19 answer-check](ubuntu/serenedb/serene_ask.py:9832) — Проверка ответа (якорь `_readings` … `_filter_values`; `9832–10233`)
- [20 ask-main-http](ubuntu/serenedb/serene_ask.py:10234) — ask / HTTP (якорь `_filter_dates` … `Handler`; `10234–15931`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 910 | 31 | 19 | 0 | 13 |
| 02 | intent | `_json_blocks` | 464 | 15 | 4 | 1 | 10 |
| 03 | period-windows | `_num_pred` | 437 | 21 | 6 | 4 | 5 |
| 04 | calendar-axis | `_sql_ident` | 184 | 11 | 3 | 2 | 7 |
| 05 | entity-form | `entity_form_rank_single_window` | 596 | 20 | 2 | 9 | 14 |
| 06 | entity-search | `_predicates` | 539 | 16 | 3 | 3 | 4 |
| 07 | rrf-vectors | `_corpus_ivf_ready` | 594 | 18 | 8 | 4 | 7 |
| 08 | measures-totals | `_shares_chars` | 244 | 4 | 5 | 3 | 0 |
| 09 | fork-detector | `_measures_by_src` | 781 | 32 | 4 | 9 | 19 |
| 10 | rank | `count_question_skips_axis` | 485 | 15 | 4 | 7 | 6 |
| 11 | sales | `sales_sum_intent` | 718 | 27 | 4 | 7 | 7 |
| 12 | stock-balance | `grain_dec_from_axis_ticket` | 293 | 17 | 3 | 6 | 7 |
| 13 | fork-outcomes | `stock_balance_is_sales_noise` | 478 | 17 | 2 | 7 | 8 |
| 14 | clarify-memory | `_alias_parts` | 699 | 35 | 9 | 3 | 16 |
| 15 | answer-atoms | `stop2_active` | 382 | 14 | 6 | 4 | 3 |
| 16 | veto-pick-entity | `pair_slots_only` | 634 | 22 | 3 | 8 | 4 |
| 17 | aggregate-groups | `_vec` | 504 | 16 | 10 | 3 | 2 |
| 18 | compose | `merge_period2_groups` | 889 | 23 | 6 | 9 | 2 |
| 19 | answer-check | `_readings` | 402 | 14 | 3 | 2 | 5 |
| 20 | ask-main-http | `_filter_dates` | 5698 | 95 | 6 | 19 | 89 |

## 01. infra-trace-llm — Инфра, TRACE, LLM

Якорь: `_new_rid`, end `embed_one`. Участок: [`ubuntu/serenedb/serene_ask.py:1`](ubuntu/serenedb/serene_ask.py:1)–`910`.

Функций: 31. Входящие зоны: 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20. Исходящие зоны: —.

Функции:

- [`_new_rid`](ubuntu/serenedb/serene_ask.py:127) `127–128` len=2
- [`_rid_norm`](ubuntu/serenedb/serene_ask.py:131) `131–136` len=6
- [`_rid_get`](ubuntu/serenedb/serene_ask.py:139) `139–140` len=2
- [`_rid_enter`](ubuntu/serenedb/serene_ask.py:143) `143–146` len=4
- [`_trace_write`](ubuntu/serenedb/serene_ask.py:149) `149–153` len=5
- [`_embed_secret_name_from_env`](ubuntu/serenedb/serene_ask.py:289) `289–293` len=5
- [`_reload_embed_native_env`](ubuntu/serenedb/serene_ask.py:303) `303–309` len=7
- [`psql`](ubuntu/serenedb/serene_ask.py:328) `328–362` len=35
- [`lit`](ubuntu/serenedb/serene_ask.py:365) `365–366` len=2
- [`_embed_host_base`](ubuntu/serenedb/serene_ask.py:369) `369–372` len=4
- [`embed_model_live`](ubuntu/serenedb/serene_ask.py:392) `392–422` len=31
- [`emb_ready`](ubuntu/serenedb/serene_ask.py:425) `425–443` len=19
- [`_fmt`](ubuntu/serenedb/serene_ask.py:446) `446–452` len=7
- [`_fmt_gate_bad`](ubuntu/serenedb/serene_ask.py:455) `455–461` len=7
- [`_gate_bad_preview`](ubuntu/serenedb/serene_ask.py:464) `464–468` len=5
- [`_fmt_human`](ubuntu/serenedb/serene_ask.py:471) `471–485` len=15
- [`_TokenAcc.__init__`](ubuntu/serenedb/serene_ask.py:495) `495–502` len=8 (влож.)
- [`_TokenAcc.add`](ubuntu/serenedb/serene_ask.py:504) `504–513` len=10 (влож.)
- [`_TokenAcc.diag_dict`](ubuntu/serenedb/serene_ask.py:515) `515–521` len=7 (влож.)
- [`_token_acc_start`](ubuntu/serenedb/serene_ask.py:524) `524–525` len=2
- [`_token_acc_record`](ubuntu/serenedb/serene_ask.py:528) `528–542` len=15
- [`_diag_pack`](ubuntu/serenedb/serene_ask.py:545) `545–551` len=7
- [`_ds_chat_content`](ubuntu/serenedb/serene_ask.py:554) `554–567` len=14
- [`_ds_chat_body`](ubuntu/serenedb/serene_ask.py:570) `570–578` len=9
- [`ds_chat_post`](ubuntu/serenedb/serene_ask.py:581) `581–589` len=9
- [`ds_chat`](ubuntu/serenedb/serene_ask.py:592) `592–593` len=2
- [`arbitrate`](ubuntu/serenedb/serene_ask.py:616) `616–642` len=27
- [`_embed_request`](ubuntu/serenedb/serene_ask.py:645) `645–658` len=14
- [`_ensure_embed_secret`](ubuntu/serenedb/serene_ask.py:674) `674–705` len=32
- [`_embed_one_native`](ubuntu/serenedb/serene_ask.py:708) `708–742` len=35
- [`embed_one`](ubuntu/serenedb/serene_ask.py:745) `745–807` len=63

Зовут снаружи зоны: `_TokenAcc.add`, `_diag_pack`, `_fmt`, `_fmt_gate_bad`, `_fmt_human`, `_gate_bad_preview`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_token_acc_start`, `_trace_write`, `arbitrate`, `ds_chat`, `emb_ready`, `embed_model_live`, `embed_one`, `lit`, `psql`

## 02. intent — Intent

Якорь: `_json_blocks`, end `_first_intent_object`. Участок: [`ubuntu/serenedb/serene_ask.py:911`](ubuntu/serenedb/serene_ask.py:911)–`1374`.

Функций: 15. Входящие зоны: 12, 14, 16, 20. Исходящие зоны: 01.

Функции:

- [`_json_blocks`](ubuntu/serenedb/serene_ask.py:911) `911–938` len=28
- [`_intent_text`](ubuntu/serenedb/serene_ask.py:941) `941–952` len=12
- [`_intent_number`](ubuntu/serenedb/serene_ask.py:955) `955–971` len=17
- [`_intent_date`](ubuntu/serenedb/serene_ask.py:974) `974–987` len=14
- [`_intent_terms`](ubuntu/serenedb/serene_ask.py:990) `990–1026` len=37
- [`_intent_word`](ubuntu/serenedb/serene_ask.py:1029) `1029–1031` len=3
- [`same_concept_groups`](ubuntu/serenedb/serene_ask.py:1058) `1058–1097` len=40
- [`_stem_set`](ubuntu/serenedb/serene_ask.py:1100) `1100–1107` len=8
- [`_normalize_intent`](ubuntu/serenedb/serene_ask.py:1110) `1110–1226` len=117
- [`_one_intent`](ubuntu/serenedb/serene_ask.py:1229) `1229–1245` len=17
- [`_field_key`](ubuntu/serenedb/serene_ask.py:1248) `1248–1249` len=2
- [`_field_lead`](ubuntu/serenedb/serene_ask.py:1252) `1252–1260` len=9
- [`_merge_intents`](ubuntu/serenedb/serene_ask.py:1263) `1263–1287` len=25
- [`parse_intent`](ubuntu/serenedb/serene_ask.py:1290) `1290–1349` len=60
- [`_first_intent_object`](ubuntu/serenedb/serene_ask.py:1352) `1352–1371` len=20

Зовут снаружи зоны: `_intent_number`, `_intent_text`, `_intent_word`, `_stem_set`, `parse_intent`

## 03. period-windows — Периоды и окна

Якорь: `_num_pred`, end `apply_period_leader`. Участок: [`ubuntu/serenedb/serene_ask.py:1375`](ubuntu/serenedb/serene_ask.py:1375)–`1811`.

Функций: 21. Входящие зоны: 04, 05, 06, 09, 18, 20. Исходящие зоны: 01, 04, 18, 20.

Функции:

- [`_num_pred`](ubuntu/serenedb/serene_ask.py:1375) `1375–1393` len=19
- [`period_preds`](ubuntu/serenedb/serene_ask.py:1396) `1396–1412` len=17
- [`_calendar_date`](ubuntu/serenedb/serene_ask.py:1443) `1443–1448` len=6
- [`_month_range`](ubuntu/serenedb/serene_ask.py:1451) `1451–1458` len=8
- [`_week_range_monday`](ubuntu/serenedb/serene_ask.py:1461) `1461–1465` len=5
- [`_prev_week_range`](ubuntu/serenedb/serene_ask.py:1468) `1468–1476` len=9
- [`_is_seven_day_span`](ubuntu/serenedb/serene_ask.py:1479) `1479–1483` len=5
- [`_is_current_calendar_week`](ubuntu/serenedb/serene_ask.py:1486) `1486–1493` len=8
- [`_assumed_sliding_week_not_calendar`](ubuntu/serenedb/serene_ask.py:1496) `1496–1506` len=11
- [`_iso_date`](ubuntu/serenedb/serene_ask.py:1509) `1509–1510` len=2
- [`_period_origin`](ubuntu/serenedb/serene_ask.py:1513) `1513–1524` len=12
- [`window_fp_of`](ubuntu/serenedb/serene_ask.py:1527) `1527–1538` len=12
- [`_period_form_id`](ubuntu/serenedb/serene_ask.py:1541) `1541–1565` len=25
- [`_window_reading`](ubuntu/serenedb/serene_ask.py:1568) `1568–1590` len=23
- [`period_readings`](ubuntu/serenedb/serene_ask.py:1593) `1593–1681` len=89
- [`period_readings._add`](ubuntu/serenedb/serene_ask.py:1637) `1637–1642` len=6 (влож.)
- [`render_window_label`](ubuntu/serenedb/serene_ask.py:1684) `1684–1702` len=19
- [`prefer_window_leader`](ubuntu/serenedb/serene_ask.py:1709) `1709–1725` len=17
- [`period_relative_forms`](ubuntu/serenedb/serene_ask.py:1728) `1728–1757` len=30
- [`period_form_from_question`](ubuntu/serenedb/serene_ask.py:1760) `1760–1770` len=11
- [`apply_period_leader`](ubuntu/serenedb/serene_ask.py:1773) `1773–1809` len=37

Зовут снаружи зоны: `_calendar_date`, `_iso_date`, `_month_range`, `_num_pred`, `_prev_week_range`, `_week_range_monday`, `_window_reading`, `apply_period_leader`, `period_form_from_question`, `period_preds`, `period_readings`, `period_readings._add`, `period_relative_forms`, `prefer_window_leader`, `render_window_label`, `window_fp_of`

## 04. calendar-axis — Календарная ось

Якорь: `_sql_ident`, end `_working_day_doc_preds`. Участок: [`ubuntu/serenedb/serene_ask.py:1812`](ubuntu/serenedb/serene_ask.py:1812)–`1995`.

Функций: 11. Входящие зоны: 03, 09, 20. Исходящие зоны: 01, 03.

Функции:

- [`_sql_ident`](ubuntu/serenedb/serene_ask.py:1812) `1812–1814` len=3
- [`calendar_registers`](ubuntu/serenedb/serene_ask.py:1817) `1817–1830` len=14
- [`calendar_working_day_keys`](ubuntu/serenedb/serene_ask.py:1833) `1833–1847` len=15
- [`calendar_map_rows`](ubuntu/serenedb/serene_ask.py:1850) `1850–1878` len=29
- [`calendar_axis_open`](ubuntu/serenedb/serene_ask.py:1881) `1881–1886` len=6
- [`calendar_day_basis_prefer`](ubuntu/serenedb/serene_ask.py:1889) `1889–1907` len=19
- [`_day_basis_reading`](ubuntu/serenedb/serene_ask.py:1910) `1910–1916` len=7
- [`calendar_axis_readings`](ubuntu/serenedb/serene_ask.py:1919) `1919–1934` len=16
- [`expand_readings_calendar_axis`](ubuntu/serenedb/serene_ask.py:1937) `1937–1949` len=13
- [`prefer_day_basis_leader`](ubuntu/serenedb/serene_ask.py:1952) `1952–1962` len=11
- [`_working_day_doc_preds`](ubuntu/serenedb/serene_ask.py:1965) `1965–1993` len=29

Зовут снаружи зоны: `_working_day_doc_preds`, `calendar_axis_open`, `calendar_day_basis_prefer`, `expand_readings_calendar_axis`

## 05. entity-form — Форма сущности

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/serene_ask.py:1996`](ubuntu/serenedb/serene_ask.py:1996)–`2591`.

Функций: 20. Входящие зоны: 11, 20. Исходящие зоны: 01, 03, 06, 09, 10, 11, 13, 15, 17.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/serene_ask.py:1996) `1996–2023` len=28
- [`sales_compare_intent`](ubuntu/serenedb/serene_ask.py:2026) `2026–2057` len=32
- [`sales_compare_windows`](ubuntu/serenedb/serene_ask.py:2060) `2060–2116` len=57
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/serene_ask.py:2120) `2120–2151` len=32
- [`entity_form_movements_for_kind`](ubuntu/serenedb/serene_ask.py:2154) `2154–2191` len=38
- [`entity_form_count_target_is_movement`](ubuntu/serenedb/serene_ask.py:2194) `2194–2229` len=36
- [`entity_form_expand_pool`](ubuntu/serenedb/serene_ask.py:2232) `2232–2252` len=21
- [`entity_form_rolling_year`](ubuntu/serenedb/serene_ask.py:2255) `2255–2265` len=11
- [`entity_form_applicable`](ubuntu/serenedb/serene_ask.py:2268) `2268–2300` len=33
- [`entity_form_collapse_guard`](ubuntu/serenedb/serene_ask.py:2303) `2303–2316` len=14
- [`entity_form_pre_entity_ok`](ubuntu/serenedb/serene_ask.py:2319) `2319–2333` len=15
- [`entity_form_atom_distinct`](ubuntu/serenedb/serene_ask.py:2336) `2336–2346` len=11
- [`entity_form_atom_complement`](ubuntu/serenedb/serene_ask.py:2349) `2349–2365` len=17
- [`aggregate_distinct_axis`](ubuntu/serenedb/serene_ask.py:2368) `2368–2395` len=28
- [`entity_form_axis_on_sales`](ubuntu/serenedb/serene_ask.py:2398) `2398–2427` len=30
- [`entity_form_structs`](ubuntu/serenedb/serene_ask.py:2430) `2430–2488` len=59
- [`entity_form_pick`](ubuntu/serenedb/serene_ask.py:2491) `2491–2501` len=11
- [`entity_form_compute`](ubuntu/serenedb/serene_ask.py:2504) `2504–2528` len=25
- [`try_entity_form_answer`](ubuntu/serenedb/serene_ask.py:2531) `2531–2562` len=32
- [`aggregate_compare_sales`](ubuntu/serenedb/serene_ask.py:2565) `2565–2589` len=25

Зовут снаружи зоны: `aggregate_compare_sales`, `entity_form_applicable`, `entity_form_collapse_guard`, `sales_compare_intent`, `sales_compare_windows`, `try_entity_form_answer`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/serene_ask.py:2592`](ubuntu/serenedb/serene_ask.py:2592)–`3130`.

Функций: 16. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/serene_ask.py:2592) `2592–2600` len=9
- [`_fetch`](ubuntu/serenedb/serene_ask.py:2603) `2603–2615` len=13
- [`_like_pattern`](ubuntu/serenedb/serene_ask.py:2618) `2618–2638` len=21
- [`probe`](ubuntu/serenedb/serene_ask.py:2641) `2641–2743` len=103
- [`matched_group_count`](ubuntu/serenedb/serene_ask.py:2746) `2746–2756` len=11
- [`with_refs`](ubuntu/serenedb/serene_ask.py:2759) `2759–2767` len=9
- [`match_expr`](ubuntu/serenedb/serene_ask.py:2770) `2770–2800` len=31
- [`children_by_parent`](ubuntu/serenedb/serene_ask.py:2803) `2803–2853` len=51
- [`partial_tables`](ubuntu/serenedb/serene_ask.py:2856) `2856–2933` len=78
- [`tables_of`](ubuntu/serenedb/serene_ask.py:2936) `2936–2952` len=17
- [`date_only_kind_filter`](ubuntu/serenedb/serene_ask.py:2955) `2955–2971` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/serene_ask.py:2974) `2974–2989` len=16
- [`alias_hits`](ubuntu/serenedb/serene_ask.py:2992) `2992–3023` len=32
- [`card_hits`](ubuntu/serenedb/serene_ask.py:3026) `3026–3064` len=39
- [`question_exprs`](ubuntu/serenedb/serene_ask.py:3067) `3067–3085` len=19
- [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3088) `3088–3128` len=41

Зовут снаружи зоны: `_predicates`, `alias_hits`, `children_by_parent`, `date_only_kind_filter`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `partial_tables`, `probe`, `question_exprs`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/serene_ask.py:3131`](ubuntu/serenedb/serene_ask.py:3131)–`3724`.

Функций: 18. Входящие зоны: 06, 08, 10, 12, 13, 16, 17, 20. Исходящие зоны: 01, 08, 17, 19.

Функции:

- [`_corpus_ivf_ready`](ubuntu/serenedb/serene_ask.py:3131) `3131–3145` len=15
- [`_resolver_ivf_ready`](ubuntu/serenedb/serene_ask.py:3148) `3148–3167` len=20
- [`_rrf_entity_branches`](ubuntu/serenedb/serene_ask.py:3170) `3170–3201` len=32
- [`_rrf_corpus_branch`](ubuntu/serenedb/serene_ask.py:3204) `3204–3211` len=8
- [`_fused_sql_rrf`](ubuntu/serenedb/serene_ask.py:3214) `3214–3219` len=6
- [`_fused_python_rrf`](ubuntu/serenedb/serene_ask.py:3222) `3222–3238` len=17
- [`_fused_candidates`](ubuntu/serenedb/serene_ask.py:3241) `3241–3292` len=52
- [`near_tables`](ubuntu/serenedb/serene_ask.py:3295) `3295–3333` len=39
- [`rows_of`](ubuntu/serenedb/serene_ask.py:3336) `3336–3368` len=33
- [`signal_terms`](ubuntu/serenedb/serene_ask.py:3403) `3403–3436` len=34
- [`clarify_text`](ubuntu/serenedb/serene_ask.py:3449) `3449–3465` len=17
- [`refuse_text`](ubuntu/serenedb/serene_ask.py:3477) `3477–3499` len=23
- [`rerank`](ubuntu/serenedb/serene_ask.py:3502) `3502–3557` len=56
- [`_resolver_psql`](ubuntu/serenedb/serene_ask.py:3560) `3560–3578` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/serene_ask.py:3585) `3585–3629` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/serene_ask.py:3632) `3632–3653` len=22
- [`resolve_values`](ubuntu/serenedb/serene_ask.py:3658) `3658–3715` len=58
- [`_ngrams`](ubuntu/serenedb/serene_ask.py:3718) `3718–3722` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`, `signal_terms`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/serene_ask.py:3725`](ubuntu/serenedb/serene_ask.py:3725)–`3968`.

Функций: 4. Входящие зоны: 07, 09, 16, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/serene_ask.py:3725) `3725–3735` len=11
- [`measures_of`](ubuntu/serenedb/serene_ask.py:3856) `3856–3869` len=14
- [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3872) `3872–3881` len=10
- [`totals_of`](ubuntu/serenedb/serene_ask.py:3884) `3884–3927` len=44

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 09. fork-detector — Детектор развилки

Якорь: `_measures_by_src`, end `_class_label_lookup`. Участок: [`ubuntu/serenedb/serene_ask.py:3969`](ubuntu/serenedb/serene_ask.py:3969)–`4749`.

Функций: 32. Входящие зоны: 05, 11, 13, 20. Исходящие зоны: 01, 03, 04, 08, 14, 15, 16, 17, 18.

Функции:

- [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3969) `3969–3990` len=22
- [`_aliases_by_src`](ubuntu/serenedb/serene_ask.py:3993) `3993–4009` len=17
- [`_fork_headline_doc_measures`](ubuntu/serenedb/serene_ask.py:4012) `4012–4014` len=3
- [`_fork_word_names_measure`](ubuntu/serenedb/serene_ask.py:4017) `4017–4030` len=14
- [`_fork_sum_headline_pool`](ubuntu/serenedb/serene_ask.py:4033) `4033–4043` len=11
- [`_fork_relevant`](ubuntu/serenedb/serene_ask.py:4046) `4046–4092` len=47
- [`_fork_relevant._sum_fallback`](ubuntu/serenedb/serene_ask.py:4063) `4063–4065` len=3 (влож.)
- [`_fork_relevant._with_doc_hdr`](ubuntu/serenedb/serene_ask.py:4073) `4073–4080` len=8 (влож.)
- [`_fork_pool_excluded`](ubuntu/serenedb/serene_ask.py:4095) `4095–4099` len=5
- [`fork_scan`](ubuntu/serenedb/serene_ask.py:4102) `4102–4176` len=75
- [`fork_scan_readings`](ubuntu/serenedb/serene_ask.py:4179) `4179–4221` len=43
- [`fork_classes_windowed`](ubuntu/serenedb/serene_ask.py:4224) `4224–4253` len=30
- [`fork_detector_scan`](ubuntu/serenedb/serene_ask.py:4256) `4256–4293` len=38
- [`_window_tuple_from_period`](ubuntu/serenedb/serene_ask.py:4296) `4296–4307` len=12
- [`_fork_atom_equiv_fp`](ubuntu/serenedb/serene_ask.py:4310) `4310–4339` len=30
- [`_fork_fp_diag`](ubuntu/serenedb/serene_ask.py:4342) `4342–4351` len=10
- [`fork_classes`](ubuntu/serenedb/serene_ask.py:4354) `4354–4373` len=20
- [`fork_key_of`](ubuntu/serenedb/serene_ask.py:4376) `4376–4385` len=10
- [`_window_fp_base`](ubuntu/serenedb/serene_ask.py:4388) `4388–4392` len=5
- [`_fork_key_for_period`](ubuntu/serenedb/serene_ask.py:4395) `4395–4405` len=11
- [`_fork_day_basis_groups`](ubuntu/serenedb/serene_ask.py:4408) `4408–4425` len=18
- [`_fork_log_day_basis`](ubuntu/serenedb/serene_ask.py:4428) `4428–4445` len=18
- [`_fork_log`](ubuntu/serenedb/serene_ask.py:4448) `4448–4485` len=38
- [`fork_labels_of`](ubuntu/serenedb/serene_ask.py:4488) `4488–4507` len=20
- [`fork_labels_covering`](ubuntu/serenedb/serene_ask.py:4512) `4512–4539` len=28
- [`fork_label_siblings`](ubuntu/serenedb/serene_ask.py:4542) `4542–4549` len=8
- [`_fork_answering_sums`](ubuntu/serenedb/serene_ask.py:4552) `4552–4573` len=22
- [`_fork_headline_measure`](ubuntu/serenedb/serene_ask.py:4576) `4576–4643` len=68
- [`_fork_headline_measure._pick_sum_headline`](ubuntu/serenedb/serene_ask.py:4596) `4596–4609` len=14 (влож.)
- [`_fork_atom_of`](ubuntu/serenedb/serene_ask.py:4646) `4646–4705` len=60
- [`_class_branch_label`](ubuntu/serenedb/serene_ask.py:4708) `4708–4714` len=7
- [`_class_label_lookup`](ubuntu/serenedb/serene_ask.py:4717) `4717–4747` len=31

Зовут снаружи зоны: `_aliases_by_src`, `_class_label_lookup`, `_fork_atom_of`, `_fork_fp_diag`, `_fork_log`, `_fork_pool_excluded`, `_fork_relevant`, `_fork_sum_headline_pool`, `_measures_by_src`, `fork_detector_scan`, `fork_key_of`, `fork_labels_covering`, `fork_labels_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `prefer_entity_for_rank`. Участок: [`ubuntu/serenedb/serene_ask.py:4750`](ubuntu/serenedb/serene_ask.py:4750)–`5234`.

Функций: 15. Входящие зоны: 05, 11, 12, 20. Исходящие зоны: 01, 07, 11, 14, 15, 17, 18.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4750) `4750–4767` len=18
- [`question_wants_breakdown`](ubuntu/serenedb/serene_ask.py:4770) `4770–4782` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4785) `4785–4803` len=19
- [`rank_question_text`](ubuntu/serenedb/serene_ask.py:4808) `4808–4826` len=19
- [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4829) `4829–4842` len=14
- [`rank_leader_answer_text`](ubuntu/serenedb/serene_ask.py:4847) `4847–4867` len=21
- [`rank_axis_label_rows`](ubuntu/serenedb/serene_ask.py:4885) `4885–4908` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/serene_ask.py:4911) `4911–4922` len=12
- [`rank_axis_pick`](ubuntu/serenedb/serene_ask.py:4925) `4925–4971` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/serene_ask.py:4974) `4974–5036` len=63
- [`rank_product_axis_col`](ubuntu/serenedb/serene_ask.py:5039) `5039–5042` len=4
- [`rank_leader_atom`](ubuntu/serenedb/serene_ask.py:5045) `5045–5076` len=32
- [`rank_deterministic_answer`](ubuntu/serenedb/serene_ask.py:5079) `5079–5157` len=79
- [`rank_gate_fallback_answer`](ubuntu/serenedb/serene_ask.py:5160) `5160–5166` len=7
- [`prefer_entity_for_rank`](ubuntu/serenedb/serene_ask.py:5169) `5169–5232` len=64

Зовут снаружи зоны: `count_question_skips_axis`, `prefer_entity_for_rank`, `rank_axes_rerank`, `rank_axis_resolve`, `rank_deterministic_answer`, `rank_gate_fallback_answer`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `period_zero_why_question`. Участок: [`ubuntu/serenedb/serene_ask.py:5235`](ubuntu/serenedb/serene_ask.py:5235)–`5952`.

Функций: 27. Входящие зоны: 05, 10, 18, 20. Исходящие зоны: 01, 05, 09, 10, 12, 14, 17.

Функции:

- [`sales_sum_intent`](ubuntu/serenedb/serene_ask.py:5235) `5235–5263` len=29
- [`_sales_register_score`](ubuntu/serenedb/serene_ask.py:5266) `5266–5281` len=16
- [`sales_lift_possible`](ubuntu/serenedb/serene_ask.py:5284) `5284–5328` len=45
- [`sales_rank_engaged`](ubuntu/serenedb/serene_ask.py:5331) `5331–5358` len=28
- [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5362) `5362–5394` len=33
- [`rank_groups_answer_text`](ubuntu/serenedb/serene_ask.py:5397) `5397–5425` len=29
- [`prefer_entity_for_sales`](ubuntu/serenedb/serene_ask.py:5428) `5428–5531` len=104
- [`sales_canon_src`](ubuntu/serenedb/serene_ask.py:5534) `5534–5546` len=13
- [`sales_money_measure`](ubuntu/serenedb/serene_ask.py:5549) `5549–5568` len=20
- [`sales_qty_measure`](ubuntu/serenedb/serene_ask.py:5572) `5572–5582` len=11
- [`_alias_role_in_question`](ubuntu/serenedb/serene_ask.py:5585) `5585–5604` len=20
- [`_sales_product_rank_qty`](ubuntu/serenedb/serene_ask.py:5607) `5607–5626` len=20
- [`sales_rank_product_axis`](ubuntu/serenedb/serene_ask.py:5629) `5629–5673` len=45
- [`sales_rank_resolve_measure`](ubuntu/serenedb/serene_ask.py:5676) `5676–5722` len=47
- [`sales_rank_canon_measure`](ubuntu/serenedb/serene_ask.py:5725) `5725–5756` len=32
- [`sales_force_money_measure`](ubuntu/serenedb/serene_ask.py:5759) `5759–5781` len=23
- [`sales_canon_force_pool`](ubuntu/serenedb/serene_ask.py:5784) `5784–5792` len=9
- [`sales_canon_engaged`](ubuntu/serenedb/serene_ask.py:5795) `5795–5812` len=18
- [`_zero_period_not_missing`](ubuntu/serenedb/serene_ask.py:5815) `5815–5822` len=8
- [`sales_ticket_hatch`](ubuntu/serenedb/serene_ask.py:5825) `5825–5831` len=7
- [`sales_noncanon_focus`](ubuntu/serenedb/serene_ask.py:5834) `5834–5842` len=9
- [`sales_refuse_sticky_focus`](ubuntu/serenedb/serene_ask.py:5845) `5845–5877` len=33
- [`_is_price_list_noise`](ubuntu/serenedb/serene_ask.py:5880) `5880–5884` len=5
- [`_is_product_catalog`](ubuntu/serenedb/serene_ask.py:5887) `5887–5893` len=7
- [`prefer_entity_for_catalog_count`](ubuntu/serenedb/serene_ask.py:5896) `5896–5926` len=31
- [`catalog_count_src`](ubuntu/serenedb/serene_ask.py:5929) `5929–5937` len=9
- [`period_zero_why_question`](ubuntu/serenedb/serene_ask.py:5940) `5940–5949` len=10

Зовут снаружи зоны: `_is_product_catalog`, `_sales_rank_top_n`, `_sales_register_score`, `_zero_period_not_missing`, `catalog_count_src`, `period_zero_why_question`, `prefer_entity_for_catalog_count`, `prefer_entity_for_sales`, `rank_groups_answer_text`, `sales_canon_engaged`, `sales_canon_force_pool`, `sales_canon_src`, `sales_force_money_measure`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_rank_engaged`, `sales_rank_resolve_measure`, `sales_refuse_sticky_focus`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `balance_bridge_clarify`. Участок: [`ubuntu/serenedb/serene_ask.py:5953`](ubuntu/serenedb/serene_ask.py:5953)–`6245`.

Функций: 17. Входящие зоны: 11, 13, 20. Исходящие зоны: 01, 02, 07, 10, 14, 20.

Функции:

- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/serene_ask.py:5953) `5953–5959` len=7
- [`_rank_wants_quantity`](ubuntu/serenedb/serene_ask.py:5962) `5962–5966` len=5
- [`rank_measure_hint`](ubuntu/serenedb/serene_ask.py:5969) `5969–5996` len=28
- [`balance_registers`](ubuntu/serenedb/serene_ask.py:6008) `6008–6021` len=14
- [`balance_map_rows`](ubuntu/serenedb/serene_ask.py:6024) `6024–6047` len=24
- [`balance_capable_sources`](ubuntu/serenedb/serene_ask.py:6050) `6050–6052` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/serene_ask.py:6055) `6055–6060` len=6
- [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6063) `6063–6068` len=6
- [`balance_registers_with_goods`](ubuntu/serenedb/serene_ask.py:6071) `6071–6084` len=14
- [`_stems_of_text`](ubuntu/serenedb/serene_ask.py:6087) `6087–6102` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/serene_ask.py:6105) `6105–6118` len=14
- [`stock_asks_named_product`](ubuntu/serenedb/serene_ask.py:6121) `6121–6146` len=26
- [`stock_asks_named_product._is_named_term`](ubuntu/serenedb/serene_ask.py:6128) `6128–6137` len=10 (влож.)
- [`stock_balance_named_no_data`](ubuntu/serenedb/serene_ask.py:6149) `6149–6156` len=8
- [`_balance_map_by_src`](ubuntu/serenedb/serene_ask.py:6159) `6159–6165` len=7
- [`filter_balance_structural`](ubuntu/serenedb/serene_ask.py:6168) `6168–6207` len=40
- [`balance_bridge_clarify`](ubuntu/serenedb/serene_ask.py:6210) `6210–6243` len=34

Зовут снаружи зоны: `_rank_wants_quantity`, `balance_bridge_clarify`, `balance_capable_or_registers`, `balance_registers_with_goods`, `filter_balance_structural`, `grain_dec_from_axis_ticket`, `question_asks_stock_balance`, `rank_measure_hint`, `stock_asks_named_product`, `stock_balance_named_no_data`

## 13. fork-outcomes — Исходы развилки

Якорь: `stock_balance_is_sales_noise`, end `fork_outcome_c`. Участок: [`ubuntu/serenedb/serene_ask.py:6246`](ubuntu/serenedb/serene_ask.py:6246)–`6723`.

Функций: 17. Входящие зоны: 05, 20. Исходящие зоны: 01, 07, 09, 12, 14, 15, 20.

Функции:

- [`stock_balance_is_sales_noise`](ubuntu/serenedb/serene_ask.py:6246) `6246–6255` len=10
- [`filter_stock_balance_sales_noise`](ubuntu/serenedb/serene_ask.py:6258) `6258–6265` len=8
- [`_dedupe_fork_classes`](ubuntu/serenedb/serene_ask.py:6269) `6269–6290` len=22
- [`_class_window_form`](ubuntu/serenedb/serene_ask.py:6297) `6297–6303` len=7
- [`_class_day_basis`](ubuntu/serenedb/serene_ask.py:6306) `6306–6313` len=8
- [`fork_leader_class`](ubuntu/serenedb/serene_ask.py:6316) `6316–6362` len=47
- [`ordered_fork_classes`](ubuntu/serenedb/serene_ask.py:6365) `6365–6383` len=19
- [`_fork_applicable_classes`](ubuntu/serenedb/serene_ask.py:6386) `6386–6389` len=4
- [`resolve_fork_outcome`](ubuntu/serenedb/serene_ask.py:6392) `6392–6441` len=50
- [`_fork_figures_of`](ubuntu/serenedb/serene_ask.py:6444) `6444–6458` len=15
- [`fork_outcome_a`](ubuntu/serenedb/serene_ask.py:6461) `6461–6481` len=21
- [`fork_outcome_unique`](ubuntu/serenedb/serene_ask.py:6485) `6485–6510` len=26
- [`_rivals_figures_empty`](ubuntu/serenedb/serene_ask.py:6513) `6513–6531` len=19
- [`prefer_mute_computed_over_clarify`](ubuntu/serenedb/serene_ask.py:6534) `6534–6562` len=29
- [`atom_terminal_gate_text`](ubuntu/serenedb/serene_ask.py:6565) `6565–6575` len=11
- [`fork_outcome_b`](ubuntu/serenedb/serene_ask.py:6579) `6579–6628` len=50
- [`fork_outcome_c`](ubuntu/serenedb/serene_ask.py:6631) `6631–6721` len=91

Зовут снаружи зоны: `_fork_figures_of`, `atom_terminal_gate_text`, `filter_stock_balance_sales_noise`, `fork_outcome_a`, `fork_outcome_b`, `fork_outcome_c`, `fork_outcome_unique`, `prefer_mute_computed_over_clarify`, `resolve_fork_outcome`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `guards_skip_for_choice`. Участок: [`ubuntu/serenedb/serene_ask.py:6724`](ubuntu/serenedb/serene_ask.py:6724)–`7422`.

Функций: 35. Входящие зоны: 09, 10, 11, 12, 13, 15, 16, 18, 20. Исходящие зоны: 01, 02, 20.

Функции:

- [`_alias_parts`](ubuntu/serenedb/serene_ask.py:6724) `6724–6728` len=5
- [`_word_hits_text`](ubuntu/serenedb/serene_ask.py:6731) `6731–6735` len=5
- [`split_ident`](ubuntu/serenedb/serene_ask.py:6738) `6738–6742` len=5
- [`measure_choice`](ubuntu/serenedb/serene_ask.py:6745) `6745–6798` len=54
- [`measure_captions`](ubuntu/serenedb/serene_ask.py:6801) `6801–6819` len=19
- [`resolve_measure`](ubuntu/serenedb/serene_ask.py:6822) `6822–6854` len=33
- [`slot_measure_uncovered`](ubuntu/serenedb/serene_ask.py:6857) `6857–6865` len=9
- [`clarify_complete`](ubuntu/serenedb/serene_ask.py:6868) `6868–6884` len=17
- [`_slot_fp`](ubuntu/serenedb/serene_ask.py:6901) `6901–6919` len=19
- [`answers_diverge`](ubuntu/serenedb/serene_ask.py:6922) `6922–6955` len=34
- [`answers_src_conflict`](ubuntu/serenedb/serene_ask.py:6957) `6957–6972` len=16
- [`question_fingerprint`](ubuntu/serenedb/serene_ask.py:6987) `6987–6990` len=4
- [`db_fingerprint`](ubuntu/serenedb/serene_ask.py:6993) `6993–7007` len=15
- [`options_version`](ubuntu/serenedb/serene_ask.py:7010) `7010–7023` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/serene_ask.py:7026) `7026–7035` len=10
- [`_new_decision_id`](ubuntu/serenedb/serene_ask.py:7038) `7038–7040` len=3
- [`_purge_decisions`](ubuntu/serenedb/serene_ask.py:7043) `7043–7058` len=16
- [`_resolved_key`](ubuntu/serenedb/serene_ask.py:7061) `7061–7063` len=3
- [`peek_resolved`](ubuntu/serenedb/serene_ask.py:7066) `7066–7072` len=7
- [`accumulate_resolution`](ubuntu/serenedb/serene_ask.py:7075) `7075–7092` len=18
- [`issue_decision`](ubuntu/serenedb/serene_ask.py:7095) `7095–7131` len=37
- [`seal_clarify`](ubuntu/serenedb/serene_ask.py:7134) `7134–7186` len=53
- [`consume_decision`](ubuntu/serenedb/serene_ask.py:7189) `7189–7216` len=28
- [`peek_decision`](ubuntu/serenedb/serene_ask.py:7219) `7219–7239` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/serene_ask.py:7242) `7242–7266` len=25
- [`reissue_clarify`](ubuntu/serenedb/serene_ask.py:7269) `7269–7287` len=19
- [`choice_error_response`](ubuntu/serenedb/serene_ask.py:7290) `7290–7308` len=19
- [`reset_decisions_for_tests`](ubuntu/serenedb/serene_ask.py:7311) `7311–7316` len=6
- [`attach_memory_shadow`](ubuntu/serenedb/serene_ask.py:7319) `7319–7330` len=12
- [`choice_proven`](ubuntu/serenedb/serene_ask.py:7333) `7333–7339` len=7
- [`choice_levels_proven`](ubuntu/serenedb/serene_ask.py:7342) `7342–7356` len=15
- [`measure_already_proven`](ubuntu/serenedb/serene_ask.py:7359) `7359–7363` len=5
- [`entity_choice_locked`](ubuntu/serenedb/serene_ask.py:7366) `7366–7368` len=3
- [`hold_settled_entity`](ubuntu/serenedb/serene_ask.py:7371) `7371–7405` len=35
- [`guards_skip_for_choice`](ubuntu/serenedb/serene_ask.py:7408) `7408–7420` len=13

Зовут снаружи зоны: `accumulate_resolution`, `answers_diverge`, `answers_src_conflict`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `guards_skip_for_choice`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `slot_measure_uncovered`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `stop2_active`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/serene_ask.py:7423`](ubuntu/serenedb/serene_ask.py:7423)–`7804`.

Функций: 14. Входящие зоны: 05, 09, 10, 13, 16, 20. Исходящие зоны: 01, 14, 17, 18.

Функции:

- [`stop2_active`](ubuntu/serenedb/serene_ask.py:7423) `7423–7433` len=11
- [`determined_answer_rivals`](ubuntu/serenedb/serene_ask.py:7436) `7436–7471` len=36
- [`determined_answer_rivals.family`](ubuntu/serenedb/serene_ask.py:7447) `7447–7448` len=2 (влож.)
- [`determined_answer_rivals.add`](ubuntu/serenedb/serene_ask.py:7453) `7453–7456` len=4 (влож.)
- [`answer_money`](ubuntu/serenedb/serene_ask.py:7476) `7476–7485` len=10
- [`answer_slot_mode`](ubuntu/serenedb/serene_ask.py:7488) `7488–7514` len=27
- [`compose_slot_values`](ubuntu/serenedb/serene_ask.py:7517) `7517–7588` len=72
- [`atom_operation`](ubuntu/serenedb/serene_ask.py:7603) `7603–7617` len=15
- [`_atom_exact_value`](ubuntu/serenedb/serene_ask.py:7620) `7620–7639` len=20
- [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7642) `7642–7685` len=44
- [`atom_from_agg`](ubuntu/serenedb/serene_ask.py:7688) `7688–7729` len=42
- [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7732) `7732–7770` len=39
- [`fill_atom_pairs`](ubuntu/serenedb/serene_ask.py:7773) `7773–7802` len=30
- [`fill_atom_pairs.one`](ubuntu/serenedb/serene_ask.py:7784) `7784–7800` len=17 (влож.)

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `build_answer_atom`, `compose_slot_values`, `determined_answer_rivals`, `fill_atom_pairs`, `fill_atom_pairs.one`, `render_atom_pair`, `stop2_active`

## 16. veto-pick-entity — Вето и выбор сущности

Якорь: `pair_slots_only`, end `pick_entity`. Участок: [`ubuntu/serenedb/serene_ask.py:7805`](ubuntu/serenedb/serene_ask.py:7805)–`8438`.

Функций: 22. Входящие зоны: 09, 18, 20. Исходящие зоны: 01, 02, 07, 08, 14, 15, 18, 20.

Функции:

- [`pair_slots_only`](ubuntu/serenedb/serene_ask.py:7805) `7805–7807` len=3
- [`atom_whitelist_labels`](ubuntu/serenedb/serene_ask.py:7810) `7810–7819` len=10
- [`atom_whitelist_numbers`](ubuntu/serenedb/serene_ask.py:7822) `7822–7838` len=17
- [`arbiter_figures`](ubuntu/serenedb/serene_ask.py:7841) `7841–7847` len=7
- [`alias_supported`](ubuntu/serenedb/serene_ask.py:7850) `7850–7918` len=69
- [`not_for_excludes`](ubuntu/serenedb/serene_ask.py:7921) `7921–7956` len=36
- [`pair_unanswered`](ubuntu/serenedb/serene_ask.py:7959) `7959–7969` len=11
- [`single_is_rival`](ubuntu/serenedb/serene_ask.py:7972) `7972–7980` len=9
- [`veto_top_without`](ubuntu/serenedb/serene_ask.py:7983) `7983–7991` len=9
- [`figures_numbers`](ubuntu/serenedb/serene_ask.py:7994) `7994–8011` len=18
- [`same_number`](ubuntu/serenedb/serene_ask.py:8014) `8014–8038` len=25
- [`unresolved_quantity`](ubuntu/serenedb/serene_ask.py:8040) `8040–8060` len=21
- [`mute_measure_blocks`](ubuntu/serenedb/serene_ask.py:8063) `8063–8078` len=16
- [`measure_row_all_zero`](ubuntu/serenedb/serene_ask.py:8081) `8081–8088` len=8
- [`alive_measure_names`](ubuntu/serenedb/serene_ask.py:8091) `8091–8093` len=3
- [`filter_dead_measure_alts`](ubuntu/serenedb/serene_ask.py:8096) `8096–8104` len=9
- [`measure_asked_explicitly`](ubuntu/serenedb/serene_ask.py:8107) `8107–8115` len=9
- [`format_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8118) `8118–8136` len=19
- [`build_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8139) `8139–8192` len=54
- [`measure_ambiguous`](ubuntu/serenedb/serene_ask.py:8195) `8195–8211` len=17
- [`pick_measure`](ubuntu/serenedb/serene_ask.py:8214) `8214–8259` len=46
- [`pick_entity`](ubuntu/serenedb/serene_ask.py:8262) `8262–8436` len=175

Зовут снаружи зоны: `alias_supported`, `arbiter_figures`, `build_measure_empty_pivot`, `figures_numbers`, `filter_dead_measure_alts`, `measure_ambiguous`, `measure_asked_explicitly`, `measure_row_all_zero`, `mute_measure_blocks`, `not_for_excludes`, `pair_slots_only`, `pair_unanswered`, `pick_entity`, `pick_measure`, `same_number`, `single_is_rival`, `unresolved_quantity`, `veto_top_without`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/serene_ask.py:8439`](ubuntu/serenedb/serene_ask.py:8439)–`8942`.

Функций: 16. Входящие зоны: 05, 07, 08, 09, 10, 11, 15, 18, 19, 20. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/serene_ask.py:8439) `8439–8440` len=2
- [`_num`](ubuntu/serenedb/serene_ask.py:8443) `8443–8447` len=5
- [`_numN`](ubuntu/serenedb/serene_ask.py:8450) `8450–8463` len=14
- [`aggregate`](ubuntu/serenedb/serene_ask.py:8466) `8466–8581` len=116
- [`src_is_child`](ubuntu/serenedb/serene_ask.py:8585) `8585–8594` len=10
- [`refcols_of`](ubuntu/serenedb/serene_ask.py:8597) `8597–8611` len=15
- [`holders_of_target`](ubuntu/serenedb/serene_ask.py:8614) `8614–8631` len=18
- [`measures_of_many`](ubuntu/serenedb/serene_ask.py:8634) `8634–8649` len=16
- [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8652) `8652–8683` len=32
- [`kind_axis_rerank`](ubuntu/serenedb/serene_ask.py:8686) `8686–8709` len=24
- [`term_ref_owners`](ubuntu/serenedb/serene_ask.py:8712) `8712–8738` len=27
- [`term_axis_hits`](ubuntu/serenedb/serene_ask.py:8741) `8741–8780` len=40
- [`resolve_member_names`](ubuntu/serenedb/serene_ask.py:8783) `8783–8810` len=28
- [`_group_leader`](ubuntu/serenedb/serene_ask.py:8813) `8813–8822` len=10
- [`_group_fold`](ubuntu/serenedb/serene_ask.py:8825) `8825–8831` len=7
- [`aggregate_groups`](ubuntu/serenedb/serene_ask.py:8834) `8834–8940` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `holders_of_target`, `kind_axis_hits`, `kind_axis_rerank`, `measures_of_many`, `refcols_of`, `src_is_child`, `term_axis_hits`, `term_ref_owners`

## 18. compose — Формулировка

Якорь: `merge_period2_groups`, end `compose`. Участок: [`ubuntu/serenedb/serene_ask.py:8943`](ubuntu/serenedb/serene_ask.py:8943)–`9831`.

Функций: 23. Входящие зоны: 03, 09, 10, 15, 16, 20. Исходящие зоны: 01, 03, 08, 11, 14, 16, 17, 19, 20.

Функции:

- [`merge_period2_groups`](ubuntu/serenedb/serene_ask.py:8943) `8943–8958` len=16
- [`axis_clarify_options`](ubuntu/serenedb/serene_ask.py:8961) `8961–8985` len=25
- [`_split_answer`](ubuntu/serenedb/serene_ask.py:9032) `9032–9062` len=31
- [`_group_value_by_name`](ubuntu/serenedb/serene_ask.py:9082) `9082–9098` len=17
- [`_fill_figures`](ubuntu/serenedb/serene_ask.py:9101) `9101–9222` len=122
- [`_fill_figures.one`](ubuntu/serenedb/serene_ask.py:9179) `9179–9220` len=42 (влож.)
- [`ensure_n_groups_named`](ubuntu/serenedb/serene_ask.py:9225) `9225–9243` len=19
- [`ensure_count_named`](ubuntu/serenedb/serene_ask.py:9246) `9246–9264` len=19
- [`_measure_dimension`](ubuntu/serenedb/serene_ask.py:9269) `9269–9287` len=19
- [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9290) `9290–9308` len=19
- [`postprocess_money_answer_text`](ubuntu/serenedb/serene_ask.py:9311) `9311–9319` len=9
- [`build_answer_passport`](ubuntu/serenedb/serene_ask.py:9321) `9321–9381` len=61
- [`build_answer_passport._add`](ubuntu/serenedb/serene_ask.py:9336) `9336–9342` len=7 (влож.)
- [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9384) `9384–9393` len=10
- [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9396) `9396–9405` len=10
- [`_table_label`](ubuntu/serenedb/serene_ask.py:9408) `9408–9419` len=12
- [`_passport_axis_label`](ubuntu/serenedb/serene_ask.py:9422) `9422–9433` len=12
- [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9436) `9436–9443` len=8
- [`formulation_flaws`](ubuntu/serenedb/serene_ask.py:9446) `9446–9473` len=28
- [`copied_figures`](ubuntu/serenedb/serene_ask.py:9476) `9476–9543` len=68
- [`_filled_ask`](ubuntu/serenedb/serene_ask.py:9546) `9546–9564` len=19
- [`_ask_back`](ubuntu/serenedb/serene_ask.py:9567) `9567–9581` len=15
- [`compose`](ubuntu/serenedb/serene_ask.py:9584) `9584–9806` len=223

Зовут снаружи зоны: `_ask_back`, `_fill_figures`, `_fill_figures.one`, `_filled_ask`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `build_answer_passport._add`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `merge_period2_groups`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/serene_ask.py:9832`](ubuntu/serenedb/serene_ask.py:9832)–`10233`.

Функций: 14. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/serene_ask.py:9832) `9832–9872` len=41
- [`_plausible`](ubuntu/serenedb/serene_ask.py:9875) `9875–9884` len=10
- [`_dates`](ubuntu/serenedb/serene_ask.py:9887) `9887–9907` len=21
- [`_date2_readings`](ubuntu/serenedb/serene_ask.py:9910) `9910–9921` len=12
- [`_date_spans`](ubuntu/serenedb/serene_ask.py:9924) `9924–9944` len=21
- [`_tokens`](ubuntu/serenedb/serene_ask.py:9947) `9947–9977` len=31
- [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9980) `9980–9985` len=6
- [`check_claims`](ubuntu/serenedb/serene_ask.py:9991) `9991–10024` len=34
- [`claims_in_text`](ubuntu/serenedb/serene_ask.py:10030) `10030–10069` len=40
- [`prompt_leak`](ubuntu/serenedb/serene_ask.py:10072) `10072–10091` len=20
- [`asked_figure_missing`](ubuntu/serenedb/serene_ask.py:10094) `10094–10181` len=88
- [`stale_note`](ubuntu/serenedb/serene_ask.py:10184) `10184–10199` len=16
- [`_threshold_values`](ubuntu/serenedb/serene_ask.py:10202) `10202–10206` len=5
- [`_filter_values`](ubuntu/serenedb/serene_ask.py:10209) `10209–10231` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/serene_ask.py:10234`](ubuntu/serenedb/serene_ask.py:10234)–`15931`.

Функций: 95. Входящие зоны: 03, 12, 13, 14, 16, 18. Исходящие зоны: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19.

Функции:

- [`_filter_dates`](ubuntu/serenedb/serene_ask.py:10234) `10234–10243` len=10
- [`without_list_markers`](ubuntu/serenedb/serene_ask.py:10254) `10254–10268` len=15
- [`rows_seen`](ubuntu/serenedb/serene_ask.py:10271) `10271–10295` len=25
- [`gate`](ubuntu/serenedb/serene_ask.py:10298) `10298–10459` len=162
- [`gate.allow`](ubuntu/serenedb/serene_ask.py:10317) `10317–10335` len=19 (влож.)
- [`count_figures`](ubuntu/serenedb/serene_ask.py:10462) `10462–10476` len=15
- [`gate_out`](ubuntu/serenedb/serene_ask.py:10479) `10479–10497` len=19
- [`_opt_values`](ubuntu/serenedb/serene_ask.py:10500) `10500–10515` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/serene_ask.py:10518) `10518–10533` len=16
- [`clarify_choice_line`](ubuntu/serenedb/serene_ask.py:10536) `10536–10543` len=8
- [`format_clarify_options`](ubuntu/serenedb/serene_ask.py:10546) `10546–10554` len=9
- [`clarify_say`](ubuntu/serenedb/serene_ask.py:10557) `10557–10579` len=23
- [`_entity_counts_objects`](ubuntu/serenedb/serene_ask.py:10592) `10592–10609` len=18
- [`_vitrina_objects`](ubuntu/serenedb/serene_ask.py:10612) `10612–10625` len=14
- [`_coverage_of`](ubuntu/serenedb/serene_ask.py:10636) `10636–10697` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/serene_ask.py:10724) `10724–10759` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/serene_ask.py:10762) `10762–10764` len=3
- [`_measure_health_gap`](ubuntu/serenedb/serene_ask.py:10767) `10767–10782` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/serene_ask.py:10786) `10786–10800` len=15
- [`_classify_health_gap`](ubuntu/serenedb/serene_ask.py:10803) `10803–10833` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/serene_ask.py:10836) `10836–10841` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/serene_ask.py:10844) `10844–10893` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/serene_ask.py:10896) `10896–10908` len=13
- [`_health_gap`](ubuntu/serenedb/serene_ask.py:10911) `10911–10923` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/serene_ask.py:10926) `10926–10934` len=9
- [`_coverage_answer`](ubuntu/serenedb/serene_ask.py:10958) `10958–11042` len=85
- [`kind_word`](ubuntu/serenedb/serene_ask.py:11099) `11099–11102` len=4
- [`label_with_kind`](ubuntu/serenedb/serene_ask.py:11105) `11105–11116` len=12
- [`ambiguous_labels`](ubuntu/serenedb/serene_ask.py:11122) `11122–11144` len=23
- [`disambiguate_labels`](ubuntu/serenedb/serene_ask.py:11147) `11147–11164` len=18
- [`opts_hints`](ubuntu/serenedb/serene_ask.py:11176) `11176–11235` len=60
- [`mk_opts`](ubuntu/serenedb/serene_ask.py:11238) `11238–11265` len=28
- [`live_src_counts`](ubuntu/serenedb/serene_ask.py:11268) `11268–11300` len=33
- [`empty_after_period_action`](ubuntu/serenedb/serene_ask.py:11303) `11303–11318` len=16
- [`period_empty_outcome`](ubuntu/serenedb/serene_ask.py:11321) `11321–11345` len=25
- [`_period_day_label`](ubuntu/serenedb/serene_ask.py:11348) `11348–11363` len=16
- [`_period_day_label.one`](ubuntu/serenedb/serene_ask.py:11350) `11350–11355` len=6 (влож.)
- [`sales_period_empty`](ubuntu/serenedb/serene_ask.py:11368) `11368–11383` len=16
- [`sales_period_window_active`](ubuntu/serenedb/serene_ask.py:11386) `11386–11398` len=13
- [`sales_fork_canon_empty_src`](ubuntu/serenedb/serene_ask.py:11401) `11401–11426` len=26
- [`try_sales_fork_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11429) `11429–11454` len=26
- [`sales_fork_blocks_clarify`](ubuntu/serenedb/serene_ask.py:11457) `11457–11468` len=12
- [`dates_outside_period_filter`](ubuntu/serenedb/serene_ask.py:11471) `11471–11485` len=15
- [`format_period_empty_text`](ubuntu/serenedb/serene_ask.py:11488) `11488–11536` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11539) `11539–11591` len=53
- [`drop_period_preds`](ubuntu/serenedb/serene_ask.py:11594) `11594–11600` len=7
- [`_term_stems`](ubuntu/serenedb/serene_ask.py:11603) `11603–11618` len=16
- [`_src_covers_term_stems`](ubuntu/serenedb/serene_ask.py:11621) `11621–11633` len=13
- [`align_picked_to_terms`](ubuntu/serenedb/serene_ask.py:11636) `11636–11663` len=28
- [`resolve_focus`](ubuntu/serenedb/serene_ask.py:11666) `11666–11800` len=135
- [`_word_hits_measure`](ubuntu/serenedb/serene_ask.py:11804) `11804–11816` len=13
- [`axis_focus_plan`](ubuntu/serenedb/serene_ask.py:11819) `11819–11887` len=69
- [`_day_ord`](ubuntu/serenedb/serene_ask.py:11890) `11890–11895` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/serene_ask.py:11898) `11898–11922` len=25
- [`period_slot_for_inherit`](ubuntu/serenedb/serene_ask.py:11925) `11925–11936` len=12
- [`apply_prior_period`](ubuntu/serenedb/serene_ask.py:11939) `11939–11967` len=29
- [`answer`](ubuntu/serenedb/serene_ask.py:11970) `11970–15075` len=3106
- [`answer.шаг`](ubuntu/serenedb/serene_ask.py:12006) `12006–12011` len=6 (влож.)
- [`answer._family`](ubuntu/serenedb/serene_ask.py:13026) `13026–13027` len=2 (влож.)
- [`answer._alias_verdict`](ubuntu/serenedb/serene_ask.py:13029) `13029–13182` len=154 (влож.)
- [`answer._alias_verdict._место`](ubuntu/serenedb/serene_ask.py:13140) `13140–13144` len=5 (влож.)
- [`answer._alias_verdict._probe`](ubuntu/serenedb/serene_ask.py:13146) `13146–13157` len=12 (влож.)
- [`answer._alias_clarify`](ubuntu/serenedb/serene_ask.py:13184) `13184–13212` len=29 (влож.)
- [`answer._checked`](ubuntu/serenedb/serene_ask.py:13482) `13482–13498` len=17 (влож.)
- [`question_facts`](ubuntu/serenedb/serene_ask.py:15098) `15098–15124` len=27
- [`entity_has_dates`](ubuntu/serenedb/serene_ask.py:15127) `15127–15148` len=22
- [`_gate_need`](ubuntu/serenedb/serene_ask.py:15151) `15151–15164` len=14
- [`_need_clarify`](ubuntu/serenedb/serene_ask.py:15167) `15167–15183` len=17
- [`_journal_keep_n`](ubuntu/serenedb/serene_ask.py:15186) `15186–15200` len=15
- [`_journal_code_md5`](ubuntu/serenedb/serene_ask.py:15203) `15203–15210` len=8
- [`_journal_build_ts`](ubuntu/serenedb/serene_ask.py:15213) `15213–15224` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/serene_ask.py:15227) `15227–15240` len=14
- [`_journal_sql_int`](ubuntu/serenedb/serene_ask.py:15243) `15243–15249` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/serene_ask.py:15252) `15252–15255` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/serene_ask.py:15258) `15258–15286` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/serene_ask.py:15289) `15289–15311` len=23
- [`_journal_doubt`](ubuntu/serenedb/serene_ask.py:15314) `15314–15323` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/serene_ask.py:15326) `15326–15339` len=14
- [`_journal_intent`](ubuntu/serenedb/serene_ask.py:15342) `15342–15344` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/serene_ask.py:15347) `15347–15355` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/serene_ask.py:15358) `15358–15377` len=20
- [`_ask_journal_write`](ubuntu/serenedb/serene_ask.py:15380) `15380–15494` len=115
- [`_ask_journal_write._insert_row`](ubuntu/serenedb/serene_ask.py:15424) `15424–15473` len=50 (влож.)
- [`_answer_checked_core`](ubuntu/serenedb/serene_ask.py:15498) `15498–15540` len=43
- [`_answer_checked_core.plain`](ubuntu/serenedb/serene_ask.py:15502) `15502–15504` len=3 (влож.)
- [`_try_memory_apply`](ubuntu/serenedb/serene_ask.py:15545) `15545–15570` len=26
- [`answer_checked`](ubuntu/serenedb/serene_ask.py:15572) `15572–15657` len=86
- [`_build_ask_scope`](ubuntu/serenedb/serene_ask.py:15662) `15662–15703` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/serene_ask.py:15706) `15706–15725` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/serene_ask.py:15728) `15728–15739` len=12
- [`Handler.log_message`](ubuntu/serenedb/serene_ask.py:15745) `15745–15746` len=2 (влож.)
- [`Handler._send`](ubuntu/serenedb/serene_ask.py:15748) `15748–15754` len=7 (влож.)
- [`Handler.do_GET`](ubuntu/serenedb/serene_ask.py:15756) `15756–15822` len=67 (влож.)
- [`Handler.do_POST`](ubuntu/serenedb/serene_ask.py:15824) `15824–15915` len=92 (влож.)
- [`main`](ubuntu/serenedb/serene_ask.py:15918) `15918–15927` len=10

Зовут снаружи зоны: `_period_day_label`, `clarify_say`, `disambiguate_labels`, `format_clarify_options`, `kind_word`, `mk_opts`

## Сквозные функции

Функции, которые вызывают из трёх и более других зон.

| функция | зона | вызывающих зон | зоны |
|---|---|---:|---|
| [`psql`](ubuntu/serenedb/serene_ask.py:328) | 01 | 17 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17, 18, 20 |
| [`lit`](ubuntu/serenedb/serene_ask.py:365) | 01 | 16 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 16, 17, 18, 20 |
| [`_fmt`](ubuntu/serenedb/serene_ask.py:446) | 01 | 6 | 05, 13, 15, 18, 19, 20 |
| [`_diag_pack`](ubuntu/serenedb/serene_ask.py:545) | 01 | 6 | 05, 10, 12, 13, 16, 20 |
| [`ds_chat`](ubuntu/serenedb/serene_ask.py:592) | 01 | 6 | 02, 07, 10, 16, 18, 20 |
| [`measure_choice`](ubuntu/serenedb/serene_ask.py:6745) | 14 | 5 | 09, 11, 12, 16, 20 |
| [`_num`](ubuntu/serenedb/serene_ask.py:8443) | 17 | 5 | 05, 08, 09, 18, 20 |
| [`_fmt_human`](ubuntu/serenedb/serene_ask.py:471) | 01 | 4 | 10, 11, 16, 18 |
| [`period_preds`](ubuntu/serenedb/serene_ask.py:1396) | 03 | 4 | 05, 06, 09, 20 |
| [`rerank`](ubuntu/serenedb/serene_ask.py:3502) | 07 | 4 | 10, 16, 17, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3872) | 08 | 4 | 09, 16, 18, 20 |
| [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4829) | 10 | 4 | 05, 11, 12, 20 |
| [`refcols_of`](ubuntu/serenedb/serene_ask.py:8597) | 17 | 4 | 05, 10, 11, 20 |
| [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3088) | 06 | 3 | 05, 17, 20 |
| [`refuse_text`](ubuntu/serenedb/serene_ask.py:3477) | 07 | 3 | 12, 13, 20 |
| [`measures_of`](ubuntu/serenedb/serene_ask.py:3856) | 08 | 3 | 16, 18, 20 |
| [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3969) | 09 | 3 | 05, 11, 20 |
| [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5362) | 11 | 3 | 05, 10, 20 |
| [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6063) | 12 | 3 | 11, 13, 20 |
| [`split_ident`](ubuntu/serenedb/serene_ask.py:6738) | 14 | 3 | 09, 13, 18 |
| [`measure_captions`](ubuntu/serenedb/serene_ask.py:6801) | 14 | 3 | 16, 18, 20 |
| [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7642) | 15 | 3 | 05, 09, 10 |
| [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7732) | 15 | 3 | 05, 13, 20 |
| [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8652) | 17 | 3 | 10, 11, 20 |
| [`_group_leader`](ubuntu/serenedb/serene_ask.py:8813) | 17 | 3 | 10, 15, 19 |
| [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9290) | 18 | 3 | 10, 15, 20 |
| [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9384) | 18 | 3 | 10, 16, 20 |
| [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9396) | 18 | 3 | 09, 10, 20 |
| [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9436) | 18 | 3 | 10, 16, 20 |
| [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9980) | 19 | 3 | 07, 18, 20 |

## Внутренние функции зоны

Функции, которые никто снаружи своей зоны не вызывает (включая ни разу не вызванные из других зон).

### 01 infra-trace-llm (13/31)

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

### 05 entity-form (14/20)

- `aggregate_distinct_axis`
- `entity_form_atom_complement`
- `entity_form_atom_distinct`
- `entity_form_axis_on_sales`
- `entity_form_catalogs_for_kind`
- `entity_form_compute`
- `entity_form_count_target_is_movement`
- `entity_form_expand_pool`
- `entity_form_movements_for_kind`
- `entity_form_pick`
- `entity_form_pre_entity_ok`
- `entity_form_rank_single_window`
- `entity_form_rolling_year`
- `entity_form_structs`

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

### 11 sales (7/27)

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

### 15 answer-atoms (3/14)

- `_atom_exact_value`
- `determined_answer_rivals.add`
- `determined_answer_rivals.family`

### 16 veto-pick-entity (4/22)

- `alive_measure_names`
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

### 20 ask-main-http (89/95)

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
- `label_with_kind`
- `live_src_counts`
- `main`
- `opts_hints`
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
- `try_sales_fork_period_empty_answer`
- `without_list_markers`

## Чтение окружения

Всего: 109.

| переменная | строка | умолчание | функция |
|---|---:|---|---|
| `SERENEDB_DSN_RO` | [64](ubuntu/serenedb/serene_ask.py:64) | — | `(модуль)` |
| `PGPASSWORD` | [65](ubuntu/serenedb/serene_ask.py:65) | "" | `(модуль)` |
| `RESOLVER_DSN` | [71](ubuntu/serenedb/serene_ask.py:71) | "" | `(модуль)` |
| `RESOLVER_PW` | [72](ubuntu/serenedb/serene_ask.py:72) | "" | `(модуль)` |
| `ASK_LISTEN_HOST` | [73](ubuntu/serenedb/serene_ask.py:73) | "127.0.0.1" | `(модуль)` |
| `ASK_LISTEN_PORT` | [74](ubuntu/serenedb/serene_ask.py:74) | "8091" | `(модуль)` |
| `ASK_TOKEN` | [75](ubuntu/serenedb/serene_ask.py:75) | "" | `(модуль)` |
| `ASK_MONEY_UNIT` | [76](ubuntu/serenedb/serene_ask.py:76) | "" | `(модуль)` |
| `ASK_CARD_TABLE` | [87](ubuntu/serenedb/serene_ask.py:87) | "search_entity_card" | `(модуль)` |
| `ASK_PICK_BUDGET_CHARS` | [93](ubuntu/serenedb/serene_ask.py:93) | "8000" | `(модуль)` |
| `ASK_ROWS_BUDGET_CHARS` | [100](ubuntu/serenedb/serene_ask.py:100) | "24000" | `(модуль)` |
| `ASK_TERMS_FOR` | [104](ubuntu/serenedb/serene_ask.py:104) | "3" | `(модуль)` |
| `ASK_COVERAGE_TOP` | [108](ubuntu/serenedb/serene_ask.py:108) | "15" | `(модуль)` |
| `ASK_STALE_WARN_SEC` | [112](ubuntu/serenedb/serene_ask.py:112) | "3600" | `(модуль)` |
| `ASK_TERMS_TOP` | [113](ubuntu/serenedb/serene_ask.py:113) | "6" | `(модуль)` |
| `ASK_TOPK` | [114](ubuntu/serenedb/serene_ask.py:114) | "40" | `(модуль)` |
| `ASK_TRACE` | [118](ubuntu/serenedb/serene_ask.py:118) | "1" | `(модуль)` |
| `ASK_ROWS_TO_MODEL` | [119](ubuntu/serenedb/serene_ask.py:119) | "25" | `(модуль)` |
| `ASK_SCORER` | [184](ubuntu/serenedb/serene_ask.py:184) | "bm25" | `(модуль)` |
| `ASK_REFS_BOOST` | [196](ubuntu/serenedb/serene_ask.py:196) | "8.0" | `(модуль)` |
| `ASK_ORDER_BY_MEANING` | [203](ubuntu/serenedb/serene_ask.py:203) | "1" | `(модуль)` |
| `RERANK_URL` | [219](ubuntu/serenedb/serene_ask.py:219) | — | `(модуль)` |
| `ALIBABA_RERANK_URL` | [220](ubuntu/serenedb/serene_ask.py:220) | — | `(модуль)` |
| `RERANK_MODEL` | [222](ubuntu/serenedb/serene_ask.py:222) | — | `(модуль)` |
| `ALIBABA_RERANK_MODEL` | [223](ubuntu/serenedb/serene_ask.py:223) | — | `(модуль)` |
| `RERANK_API` | [224](ubuntu/serenedb/serene_ask.py:224) | "<expr>" | `(модуль)` |
| `ASK_RERANK_TOP` | [229](ubuntu/serenedb/serene_ask.py:229) | "60" | `(модуль)` |
| `DEEPSEEK_BASE` | [237](ubuntu/serenedb/serene_ask.py:237) | "https://api.deepseek.com" | `(модуль)` |
| `DEEPSEEK_API_KEY` | [238](ubuntu/serenedb/serene_ask.py:238) | "" | `(модуль)` |
| `DEEPSEEK_MODEL` | [246](ubuntu/serenedb/serene_ask.py:246) | "deepseek-v4-pro" | `(модуль)` |
| `DEEPSEEK_THINKING` | [247](ubuntu/serenedb/serene_ask.py:247) | "disabled" | `(модуль)` |
| `ASK_THINKING_OFF_BODY` | [250](ubuntu/serenedb/serene_ask.py:250) | "" | `(модуль)` |
| `EMBED_BASE_URL` | [259](ubuntu/serenedb/serene_ask.py:259) | — | `(модуль)` |
| `ALIBABA_EMBED_URL` | [260](ubuntu/serenedb/serene_ask.py:260) | "" | `(модуль)` |
| `EMBED_API` | [266](ubuntu/serenedb/serene_ask.py:266) | "openai" | `(модуль)` |
| `EMBED_QUERY_PATH` | [267](ubuntu/serenedb/serene_ask.py:267) | "/embed" | `(модуль)` |
| `EMBED_UA` | [270](ubuntu/serenedb/serene_ask.py:270) | "curl/8.5.0" | `(модуль)` |
| `EMBED_HEALTH_URL` | [272](ubuntu/serenedb/serene_ask.py:272) | — | `(модуль)` |
| `EMBED_API_KEY` | [273](ubuntu/serenedb/serene_ask.py:273) | — | `(модуль)` |
| `ALIBABA_API_KEY` | [273](ubuntu/serenedb/serene_ask.py:273) | "" | `(модуль)` |
| `EMBED_MODEL` | [274](ubuntu/serenedb/serene_ask.py:274) | "text-embedding-v4" | `(модуль)` |
| `RERANK_API_KEY` | [277](ubuntu/serenedb/serene_ask.py:277) | — | `(модуль)` |
| `EMBED_DIM` | [285](ubuntu/serenedb/serene_ask.py:285) | "1024" | `(модуль)` |
| `EMBED_PATH` | [297](ubuntu/serenedb/serene_ask.py:297) | "/v1/embeddings" | `(модуль)` |
| `ASK_EMBED_NATIVE` | [298](ubuntu/serenedb/serene_ask.py:298) | "0" | `(модуль)` |
| `ASK_NO_DATA_TEXT` | [318](ubuntu/serenedb/serene_ask.py:318) | "" | `(модуль)` |
| `ASK_TOTAL_TEXT` | [319](ubuntu/serenedb/serene_ask.py:319) | "" | `(модуль)` |
| `ASK_STALE_TEXT` | [322](ubuntu/serenedb/serene_ask.py:322) | "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад." | `(модуль)` |
| `ASK_EMB_CACHE` | [665](ubuntu/serenedb/serene_ask.py:665) | "256" | `(модуль)` |
| `ASK_EMB_RETRY` | [669](ubuntu/serenedb/serene_ask.py:669) | "2" | `(модуль)` |
| `ASK_EMB_RETRY_PAUSE` | [670](ubuntu/serenedb/serene_ask.py:670) | "0.4" | `(модуль)` |
| `ASK_EMB_TIMEOUT` | [671](ubuntu/serenedb/serene_ask.py:671) | "60" | `(модуль)` |
| `ASK_INTENT_MAX_TOKENS` | [889](ubuntu/serenedb/serene_ask.py:889) | "400" | `(модуль)` |
| `ASK_INTENT_SAMPLES` | [890](ubuntu/serenedb/serene_ask.py:890) | "5" | `(модуль)` |
| `ASK_INTENT_LEAD` | [891](ubuntu/serenedb/serene_ask.py:891) | "3" | `(модуль)` |
| `ASK_INTENT_MEMO` | [893](ubuntu/serenedb/serene_ask.py:893) | "512" | `(модуль)` |
| `ASK_INTENT_GROUPS` | [900](ubuntu/serenedb/serene_ask.py:900) | "6" | `(модуль)` |
| `ASK_INTENT_ALTS` | [901](ubuntu/serenedb/serene_ask.py:901) | "6" | `(модуль)` |
| `ASK_STEM_DICT` | [904](ubuntu/serenedb/serene_ask.py:904) | "search_dict_stem" | `(модуль)` |
| `ASK_SOLR_SYNONYMS` | [907](ubuntu/serenedb/serene_ask.py:907) | "0" | `(модуль)` |
| `ASK_SOLR_SYNONYMS_DICT` | [908](ubuntu/serenedb/serene_ask.py:908) | "" | `(модуль)` |
| `ASK_CALENDAR_AXIS` | [1425](ubuntu/serenedb/serene_ask.py:1425) | "0" | `(модуль)` |
| `ASK_SALES_RANK_CANON` | [1427](ubuntu/serenedb/serene_ask.py:1427) | "0" | `(модуль)` |
| `ASK_ATOM_TERMINAL` | [1429](ubuntu/serenedb/serene_ask.py:1429) | "0" | `(модуль)` |
| `ASK_ENTITY_FORM` | [1432](ubuntu/serenedb/serene_ask.py:1432) | "0" | `(модуль)` |
| `ASK_RESOLVE_NEAR` | [3581](ubuntu/serenedb/serene_ask.py:3581) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [3582](ubuntu/serenedb/serene_ask.py:3582) | "3" | `(модуль)` |
| `ASK_ALIAS_TOP` | [3741](ubuntu/serenedb/serene_ask.py:3741) | "8" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [3744](ubuntu/serenedb/serene_ask.py:3744) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [3749](ubuntu/serenedb/serene_ask.py:3749) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [3754](ubuntu/serenedb/serene_ask.py:3754) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [3757](ubuntu/serenedb/serene_ask.py:3757) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [3758](ubuntu/serenedb/serene_ask.py:3758) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [3763](ubuntu/serenedb/serene_ask.py:3763) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [3764](ubuntu/serenedb/serene_ask.py:3764) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_ALIAS_VETO` | [3777](ubuntu/serenedb/serene_ask.py:3777) | "1" | `(модуль)` |
| `ASK_PROBE` | [3784](ubuntu/serenedb/serene_ask.py:3784) | "0" | `(модуль)` |
| `ASK_SKIP_SERVICE_RIVALS` | [3788](ubuntu/serenedb/serene_ask.py:3788) | "1" | `(модуль)` |
| `ASK_ALIAS_BY_CONCEPTS` | [3800](ubuntu/serenedb/serene_ask.py:3800) | "0" | `(модуль)` |
| `ASK_VETO_NEEDS_RANK` | [3815](ubuntu/serenedb/serene_ask.py:3815) | "0" | `(модуль)` |
| `ASK_VETO_HEAD_WINS` | [3825](ubuntu/serenedb/serene_ask.py:3825) | "1" | `(модуль)` |
| `ASK_MEANING_TOP` | [3851](ubuntu/serenedb/serene_ask.py:3851) | "0" | `(модуль)` |
| `ASK_FORK_DETECT` | [3943](ubuntu/serenedb/serene_ask.py:3943) | "1" | `(модуль)` |
| `ASK_FORK_OUTCOMES` | [3944](ubuntu/serenedb/serene_ask.py:3944) | "1" | `(модуль)` |
| `ASK_JOURNAL` | [3947](ubuntu/serenedb/serene_ask.py:3947) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [3952](ubuntu/serenedb/serene_ask.py:3952) | "1" | `(модуль)` |
| `ASK_MEMORY_APPLY` | [3954](ubuntu/serenedb/serene_ask.py:3954) | "0" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [3965](ubuntu/serenedb/serene_ask.py:3965) | "600" | `(модуль)` |
| `ASK_RAW_FOCUS_TRUST` | [6978](ubuntu/serenedb/serene_ask.py:6978) | "0" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [6979](ubuntu/serenedb/serene_ask.py:6979) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [10711](ubuntu/serenedb/serene_ask.py:10711) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [10719](ubuntu/serenedb/serene_ask.py:10719) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [10720](ubuntu/serenedb/serene_ask.py:10720) | "search_idx" | `(модуль)` |
| `ASK_SIGNAL_DISAGREE` | [11048](ubuntu/serenedb/serene_ask.py:11048) | "1" | `(модуль)` |
| `ASK_REQUIRE_SUPPORT` | [11050](ubuntu/serenedb/serene_ask.py:11050) | "1" | `(модуль)` |
| `ASK_ARBITER_MAX` | [11053](ubuntu/serenedb/serene_ask.py:11053) | "3" | `(модуль)` |
| `ASK_ARBITER_DETECTS` | [11059](ubuntu/serenedb/serene_ask.py:11059) | "1" | `(модуль)` |
| `ASK_NOT_FOR` | [11061](ubuntu/serenedb/serene_ask.py:11061) | "1" | `(модуль)` |
| `ASK_STEM_DICT` | [11064](ubuntu/serenedb/serene_ask.py:11064) | "search_dict_stem" | `(модуль)` |
| `ASK_AMBIG_TTL` | [11067](ubuntu/serenedb/serene_ask.py:11067) | "300" | `(модуль)` |
| `ASK_ENOUGH` | [15090](ubuntu/serenedb/serene_ask.py:15090) | "1" | `(модуль)` |
| `ASK_SLOT_COVER` | [15092](ubuntu/serenedb/serene_ask.py:15092) | "0" | `(модуль)` |
| `EMBED_SECRET` | [290](ubuntu/serenedb/serene_ask.py:290) | — | `_embed_secret_name_from_env` |
| `EMBED_SECRETS` | [290](ubuntu/serenedb/serene_ask.py:290) | — | `_embed_secret_name_from_env` |
| `EMBED_PATH` | [306](ubuntu/serenedb/serene_ask.py:306) | "/v1/embeddings" | `_reload_embed_native_env` |
| `ASK_EMBED_NATIVE` | [307](ubuntu/serenedb/serene_ask.py:307) | "0" | `_reload_embed_native_env` |
| `EMBED_DIM` | [308](ubuntu/serenedb/serene_ask.py:308) | "1024" | `_reload_embed_native_env` |
| `EMBED_HOST` | [370](ubuntu/serenedb/serene_ask.py:370) | — | `_embed_host_base` |
| `ASK_JOURNAL_KEEP` | [15189](ubuntu/serenedb/serene_ask.py:15189) | — | `_journal_keep_n` |

## Обращения наружу

Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`.

### psql (154)

- [`ubuntu/serenedb/serene_ask.py:436`](ubuntu/serenedb/serene_ask.py:436) в `emb_ready`
- [`ubuntu/serenedb/serene_ask.py:685`](ubuntu/serenedb/serene_ask.py:685) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:700`](ubuntu/serenedb/serene_ask.py:700) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:719`](ubuntu/serenedb/serene_ask.py:719) в `_embed_one_native`
- [`ubuntu/serenedb/serene_ask.py:1070`](ubuntu/serenedb/serene_ask.py:1070) в `same_concept_groups`
- [`ubuntu/serenedb/serene_ask.py:1736`](ubuntu/serenedb/serene_ask.py:1736) в `period_relative_forms`
- [`ubuntu/serenedb/serene_ask.py:1824`](ubuntu/serenedb/serene_ask.py:1824) в `calendar_registers`
- [`ubuntu/serenedb/serene_ask.py:1840`](ubuntu/serenedb/serene_ask.py:1840) в `calendar_working_day_keys`
- [`ubuntu/serenedb/serene_ask.py:1860`](ubuntu/serenedb/serene_ask.py:1860) в `calendar_map_rows`
- [`ubuntu/serenedb/serene_ask.py:2131`](ubuntu/serenedb/serene_ask.py:2131) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2165`](ubuntu/serenedb/serene_ask.py:2165) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2382`](ubuntu/serenedb/serene_ask.py:2382) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/serene_ask.py:2612`](ubuntu/serenedb/serene_ask.py:2612) в `_fetch`
- [`ubuntu/serenedb/serene_ask.py:2684`](ubuntu/serenedb/serene_ask.py:2684) в `probe`
- [`ubuntu/serenedb/serene_ask.py:2787`](ubuntu/serenedb/serene_ask.py:2787) в `match_expr`
- [`ubuntu/serenedb/serene_ask.py:2826`](ubuntu/serenedb/serene_ask.py:2826) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2845`](ubuntu/serenedb/serene_ask.py:2845) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2915`](ubuntu/serenedb/serene_ask.py:2915) в `partial_tables`
- [`ubuntu/serenedb/serene_ask.py:2947`](ubuntu/serenedb/serene_ask.py:2947) в `tables_of`
- [`ubuntu/serenedb/serene_ask.py:3017`](ubuntu/serenedb/serene_ask.py:3017) в `alias_hits`
- [`ubuntu/serenedb/serene_ask.py:3057`](ubuntu/serenedb/serene_ask.py:3057) в `card_hits`
- [`ubuntu/serenedb/serene_ask.py:3139`](ubuntu/serenedb/serene_ask.py:3139) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/serene_ask.py:3219`](ubuntu/serenedb/serene_ask.py:3219) в `_fused_sql_rrf`
- [`ubuntu/serenedb/serene_ask.py:3227`](ubuntu/serenedb/serene_ask.py:3227) в `_fused_python_rrf`
- [`ubuntu/serenedb/serene_ask.py:3328`](ubuntu/serenedb/serene_ask.py:3328) в `near_tables`
- [`ubuntu/serenedb/serene_ask.py:3364`](ubuntu/serenedb/serene_ask.py:3364) в `rows_of`
- [`ubuntu/serenedb/serene_ask.py:3418`](ubuntu/serenedb/serene_ask.py:3418) в `signal_terms`
- [`ubuntu/serenedb/serene_ask.py:3647`](ubuntu/serenedb/serene_ask.py:3647) в `_resolve_values_corpus`
- [`ubuntu/serenedb/serene_ask.py:3864`](ubuntu/serenedb/serene_ask.py:3864) в `measures_of`
- [`ubuntu/serenedb/serene_ask.py:3875`](ubuntu/serenedb/serene_ask.py:3875) в `measure_aliases_of`
- [`ubuntu/serenedb/serene_ask.py:3916`](ubuntu/serenedb/serene_ask.py:3916) в `totals_of`
- [`ubuntu/serenedb/serene_ask.py:3980`](ubuntu/serenedb/serene_ask.py:3980) в `_measures_by_src`
- [`ubuntu/serenedb/serene_ask.py:3999`](ubuntu/serenedb/serene_ask.py:3999) в `_aliases_by_src`
- [`ubuntu/serenedb/serene_ask.py:4137`](ubuntu/serenedb/serene_ask.py:4137) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4160`](ubuntu/serenedb/serene_ask.py:4160) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4437`](ubuntu/serenedb/serene_ask.py:4437) в `_fork_log_day_basis`
- [`ubuntu/serenedb/serene_ask.py:4477`](ubuntu/serenedb/serene_ask.py:4477) в `_fork_log`
- [`ubuntu/serenedb/serene_ask.py:4497`](ubuntu/serenedb/serene_ask.py:4497) в `fork_labels_of`
- [`ubuntu/serenedb/serene_ask.py:4522`](ubuntu/serenedb/serene_ask.py:4522) в `fork_labels_covering`
- [`ubuntu/serenedb/serene_ask.py:4894`](ubuntu/serenedb/serene_ask.py:4894) в `rank_axis_label_rows`
- [`ubuntu/serenedb/serene_ask.py:5182`](ubuntu/serenedb/serene_ask.py:5182) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5200`](ubuntu/serenedb/serene_ask.py:5200) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5298`](ubuntu/serenedb/serene_ask.py:5298) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5322`](ubuntu/serenedb/serene_ask.py:5322) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5446`](ubuntu/serenedb/serene_ask.py:5446) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5470`](ubuntu/serenedb/serene_ask.py:5470) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5502`](ubuntu/serenedb/serene_ask.py:5502) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5482`](ubuntu/serenedb/serene_ask.py:5482) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5911`](ubuntu/serenedb/serene_ask.py:5911) в `prefer_entity_for_catalog_count`
- [`ubuntu/serenedb/serene_ask.py:6017`](ubuntu/serenedb/serene_ask.py:6017) в `balance_registers`
- [`ubuntu/serenedb/serene_ask.py:6035`](ubuntu/serenedb/serene_ask.py:6035) в `balance_map_rows`
- [`ubuntu/serenedb/serene_ask.py:6080`](ubuntu/serenedb/serene_ask.py:6080) в `balance_registers_with_goods`
- [`ubuntu/serenedb/serene_ask.py:6094`](ubuntu/serenedb/serene_ask.py:6094) в `_stems_of_text`
- [`ubuntu/serenedb/serene_ask.py:6183`](ubuntu/serenedb/serene_ask.py:6183) в `filter_balance_structural`
- [`ubuntu/serenedb/serene_ask.py:6219`](ubuntu/serenedb/serene_ask.py:6219) в `balance_bridge_clarify`
- [`ubuntu/serenedb/serene_ask.py:6687`](ubuntu/serenedb/serene_ask.py:6687) в `fork_outcome_c`
- [`ubuntu/serenedb/serene_ask.py:7003`](ubuntu/serenedb/serene_ask.py:7003) в `db_fingerprint`
- [`ubuntu/serenedb/serene_ask.py:8281`](ubuntu/serenedb/serene_ask.py:8281) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8319`](ubuntu/serenedb/serene_ask.py:8319) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8541`](ubuntu/serenedb/serene_ask.py:8541) в `aggregate`
- [`ubuntu/serenedb/serene_ask.py:8590`](ubuntu/serenedb/serene_ask.py:8590) в `src_is_child`
- [`ubuntu/serenedb/serene_ask.py:8602`](ubuntu/serenedb/serene_ask.py:8602) в `refcols_of`
- [`ubuntu/serenedb/serene_ask.py:8619`](ubuntu/serenedb/serene_ask.py:8619) в `holders_of_target`
- [`ubuntu/serenedb/serene_ask.py:8639`](ubuntu/serenedb/serene_ask.py:8639) в `measures_of_many`
- [`ubuntu/serenedb/serene_ask.py:8661`](ubuntu/serenedb/serene_ask.py:8661) в `kind_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8696`](ubuntu/serenedb/serene_ask.py:8696) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:8723`](ubuntu/serenedb/serene_ask.py:8723) в `term_ref_owners`
- [`ubuntu/serenedb/serene_ask.py:8757`](ubuntu/serenedb/serene_ask.py:8757) в `term_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8795`](ubuntu/serenedb/serene_ask.py:8795) в `resolve_member_names`
- [`ubuntu/serenedb/serene_ask.py:8904`](ubuntu/serenedb/serene_ask.py:8904) в `aggregate_groups`
- [`ubuntu/serenedb/serene_ask.py:8970`](ubuntu/serenedb/serene_ask.py:8970) в `axis_clarify_options`
- [`ubuntu/serenedb/serene_ask.py:9413`](ubuntu/serenedb/serene_ask.py:9413) в `_table_label`
- [`ubuntu/serenedb/serene_ask.py:10595`](ubuntu/serenedb/serene_ask.py:10595) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10603`](ubuntu/serenedb/serene_ask.py:10603) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10615`](ubuntu/serenedb/serene_ask.py:10615) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10623`](ubuntu/serenedb/serene_ask.py:10623) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10647`](ubuntu/serenedb/serene_ask.py:10647) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10684`](ubuntu/serenedb/serene_ask.py:10684) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10657`](ubuntu/serenedb/serene_ask.py:10657) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10774`](ubuntu/serenedb/serene_ask.py:10774) в `_measure_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10794`](ubuntu/serenedb/serene_ask.py:10794) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/serene_ask.py:10815`](ubuntu/serenedb/serene_ask.py:10815) в `_classify_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10870`](ubuntu/serenedb/serene_ask.py:10870) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/serene_ask.py:10967`](ubuntu/serenedb/serene_ask.py:10967) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:10976`](ubuntu/serenedb/serene_ask.py:10976) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:11138`](ubuntu/serenedb/serene_ask.py:11138) в `ambiguous_labels`
- [`ubuntu/serenedb/serene_ask.py:11184`](ubuntu/serenedb/serene_ask.py:11184) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11191`](ubuntu/serenedb/serene_ask.py:11191) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11201`](ubuntu/serenedb/serene_ask.py:11201) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11211`](ubuntu/serenedb/serene_ask.py:11211) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11290`](ubuntu/serenedb/serene_ask.py:11290) в `live_src_counts`
- [`ubuntu/serenedb/serene_ask.py:11479`](ubuntu/serenedb/serene_ask.py:11479) в `dates_outside_period_filter`
- [`ubuntu/serenedb/serene_ask.py:11611`](ubuntu/serenedb/serene_ask.py:11611) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11614`](ubuntu/serenedb/serene_ask.py:11614) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11626`](ubuntu/serenedb/serene_ask.py:11626) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11629`](ubuntu/serenedb/serene_ask.py:11629) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11649`](ubuntu/serenedb/serene_ask.py:11649) в `align_picked_to_terms`
- [`ubuntu/serenedb/serene_ask.py:11705`](ubuntu/serenedb/serene_ask.py:11705) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11710`](ubuntu/serenedb/serene_ask.py:11710) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11729`](ubuntu/serenedb/serene_ask.py:11729) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11769`](ubuntu/serenedb/serene_ask.py:11769) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11866`](ubuntu/serenedb/serene_ask.py:11866) в `axis_focus_plan`
- [`ubuntu/serenedb/serene_ask.py:12271`](ubuntu/serenedb/serene_ask.py:12271) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12363`](ubuntu/serenedb/serene_ask.py:12363) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12931`](ubuntu/serenedb/serene_ask.py:12931) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13008`](ubuntu/serenedb/serene_ask.py:13008) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13055`](ubuntu/serenedb/serene_ask.py:13055) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14290`](ubuntu/serenedb/serene_ask.py:14290) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14632`](ubuntu/serenedb/serene_ask.py:14632) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14653`](ubuntu/serenedb/serene_ask.py:14653) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12372`](ubuntu/serenedb/serene_ask.py:12372) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14425`](ubuntu/serenedb/serene_ask.py:14425) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12409`](ubuntu/serenedb/serene_ask.py:12409) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12448`](ubuntu/serenedb/serene_ask.py:12448) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12613`](ubuntu/serenedb/serene_ask.py:12613) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12642`](ubuntu/serenedb/serene_ask.py:12642) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12664`](ubuntu/serenedb/serene_ask.py:12664) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12683`](ubuntu/serenedb/serene_ask.py:12683) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12707`](ubuntu/serenedb/serene_ask.py:12707) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12860`](ubuntu/serenedb/serene_ask.py:12860) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12994`](ubuntu/serenedb/serene_ask.py:12994) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13193`](ubuntu/serenedb/serene_ask.py:13193) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13866`](ubuntu/serenedb/serene_ask.py:13866) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14046`](ubuntu/serenedb/serene_ask.py:14046) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14447`](ubuntu/serenedb/serene_ask.py:14447) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12393`](ubuntu/serenedb/serene_ask.py:12393) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13105`](ubuntu/serenedb/serene_ask.py:13105) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13729`](ubuntu/serenedb/serene_ask.py:13729) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12544`](ubuntu/serenedb/serene_ask.py:12544) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13020`](ubuntu/serenedb/serene_ask.py:13020) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13128`](ubuntu/serenedb/serene_ask.py:13128) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13767`](ubuntu/serenedb/serene_ask.py:13767) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13833`](ubuntu/serenedb/serene_ask.py:13833) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13848`](ubuntu/serenedb/serene_ask.py:13848) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13055`](ubuntu/serenedb/serene_ask.py:13055) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13105`](ubuntu/serenedb/serene_ask.py:13105) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13128`](ubuntu/serenedb/serene_ask.py:13128) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13193`](ubuntu/serenedb/serene_ask.py:13193) в `answer._alias_clarify`
- [`ubuntu/serenedb/serene_ask.py:15141`](ubuntu/serenedb/serene_ask.py:15141) в `entity_has_dates`
- [`ubuntu/serenedb/serene_ask.py:15195`](ubuntu/serenedb/serene_ask.py:15195) в `_journal_keep_n`
- [`ubuntu/serenedb/serene_ask.py:15219`](ubuntu/serenedb/serene_ask.py:15219) в `_journal_build_ts`
- [`ubuntu/serenedb/serene_ask.py:15232`](ubuntu/serenedb/serene_ask.py:15232) в `_journal_alias_ver`
- [`ubuntu/serenedb/serene_ask.py:15466`](ubuntu/serenedb/serene_ask.py:15466) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15487`](ubuntu/serenedb/serene_ask.py:15487) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15480`](ubuntu/serenedb/serene_ask.py:15480) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15482`](ubuntu/serenedb/serene_ask.py:15482) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15489`](ubuntu/serenedb/serene_ask.py:15489) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15421`](ubuntu/serenedb/serene_ask.py:15421) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15470`](ubuntu/serenedb/serene_ask.py:15470) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15483`](ubuntu/serenedb/serene_ask.py:15483) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15466`](ubuntu/serenedb/serene_ask.py:15466) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15470`](ubuntu/serenedb/serene_ask.py:15470) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15759`](ubuntu/serenedb/serene_ask.py:15759) в `Handler.do_GET`
- [`ubuntu/serenedb/serene_ask.py:15886`](ubuntu/serenedb/serene_ask.py:15886) в `Handler.do_POST`

### ds_chat (10)

- [`ubuntu/serenedb/serene_ask.py:632`](ubuntu/serenedb/serene_ask.py:632) в `arbitrate`
- [`ubuntu/serenedb/serene_ask.py:1231`](ubuntu/serenedb/serene_ask.py:1231) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:1239`](ubuntu/serenedb/serene_ask.py:1239) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:3462`](ubuntu/serenedb/serene_ask.py:3462) в `clarify_text`
- [`ubuntu/serenedb/serene_ask.py:3495`](ubuntu/serenedb/serene_ask.py:3495) в `refuse_text`
- [`ubuntu/serenedb/serene_ask.py:4946`](ubuntu/serenedb/serene_ask.py:4946) в `rank_axis_pick`
- [`ubuntu/serenedb/serene_ask.py:8384`](ubuntu/serenedb/serene_ask.py:8384) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:9805`](ubuntu/serenedb/serene_ask.py:9805) в `compose`
- [`ubuntu/serenedb/serene_ask.py:10996`](ubuntu/serenedb/serene_ask.py:10996) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:15113`](ubuntu/serenedb/serene_ask.py:15113) в `question_facts`

### embed_one (1)

- [`ubuntu/serenedb/serene_ask.py:8440`](ubuntu/serenedb/serene_ask.py:8440) в `_vec`

### rerank (5)

- [`ubuntu/serenedb/serene_ask.py:3713`](ubuntu/serenedb/serene_ask.py:3713) в `resolve_values`
- [`ubuntu/serenedb/serene_ask.py:4919`](ubuntu/serenedb/serene_ask.py:4919) в `rank_axes_rerank`
- [`ubuntu/serenedb/serene_ask.py:8244`](ubuntu/serenedb/serene_ask.py:8244) в `pick_measure`
- [`ubuntu/serenedb/serene_ask.py:8706`](ubuntu/serenedb/serene_ask.py:8706) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:12619`](ubuntu/serenedb/serene_ask.py:12619) в `answer`

### urlopen (4)

- [`ubuntu/serenedb/serene_ask.py:412`](ubuntu/serenedb/serene_ask.py:412) в `embed_model_live`
- [`ubuntu/serenedb/serene_ask.py:588`](ubuntu/serenedb/serene_ask.py:588) в `ds_chat_post`
- [`ubuntu/serenedb/serene_ask.py:790`](ubuntu/serenedb/serene_ask.py:790) в `embed_one`
- [`ubuntu/serenedb/serene_ask.py:3536`](ubuntu/serenedb/serene_ask.py:3536) в `rerank`
