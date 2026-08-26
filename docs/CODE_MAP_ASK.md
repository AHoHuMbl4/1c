# Карта `ubuntu/serenedb/serene_ask.py`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **15851**. Функций: **461**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **29**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/serene_ask.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–909`)
- [02 intent](ubuntu/serenedb/serene_ask.py:910) — Intent (якорь `_json_blocks` … `_first_intent_object`; `910–1373`)
- [03 period-windows](ubuntu/serenedb/serene_ask.py:1374) — Периоды и окна (якорь `_num_pred` … `apply_period_leader`; `1374–1810`)
- [04 calendar-axis](ubuntu/serenedb/serene_ask.py:1811) — Календарная ось (якорь `_sql_ident` … `_working_day_doc_preds`; `1811–1994`)
- [05 entity-form](ubuntu/serenedb/serene_ask.py:1995) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `1995–2596`)
- [06 entity-search](ubuntu/serenedb/serene_ask.py:2597) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `2597–3135`)
- [07 rrf-vectors](ubuntu/serenedb/serene_ask.py:3136) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `3136–3729`)
- [08 measures-totals](ubuntu/serenedb/serene_ask.py:3730) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `3730–3973`)
- [09 fork-detector](ubuntu/serenedb/serene_ask.py:3974) — Детектор развилки (якорь `_measures_by_src` … `_class_label_lookup`; `3974–4754`)
- [10 rank](ubuntu/serenedb/serene_ask.py:4755) — Ранг (якорь `count_question_skips_axis` … `prefer_entity_for_rank`; `4755–5239`)
- [11 sales](ubuntu/serenedb/serene_ask.py:5240) — Продажи (якорь `sales_sum_intent` … `period_zero_why_question`; `5240–5900`)
- [12 stock-balance](ubuntu/serenedb/serene_ask.py:5901) — Остатки (якорь `grain_dec_from_axis_ticket` … `balance_bridge_clarify`; `5901–6193`)
- [13 fork-outcomes](ubuntu/serenedb/serene_ask.py:6194) — Исходы развилки (якорь `stock_balance_is_sales_noise` … `fork_outcome_c`; `6194–6671`)
- [14 clarify-memory](ubuntu/serenedb/serene_ask.py:6672) — Уточнение и память (якорь `_alias_parts` … `guards_skip_for_choice`; `6672–7370`)
- [15 answer-atoms](ubuntu/serenedb/serene_ask.py:7371) — Атомы ответа (якорь `stop2_active` … `fill_atom_pairs`; `7371–7752`)
- [16 veto-pick-entity](ubuntu/serenedb/serene_ask.py:7753) — Вето и выбор сущности (якорь `pair_slots_only` … `pick_entity`; `7753–8386`)
- [17 aggregate-groups](ubuntu/serenedb/serene_ask.py:8387) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `8387–8890`)
- [18 compose](ubuntu/serenedb/serene_ask.py:8891) — Формулировка (якорь `merge_period2_groups` … `compose`; `8891–9750`)
- [19 answer-check](ubuntu/serenedb/serene_ask.py:9751) — Проверка ответа (якорь `_readings` … `_filter_values`; `9751–10139`)
- [20 ask-main-http](ubuntu/serenedb/serene_ask.py:10140) — ask / HTTP (якорь `_filter_dates` … `Handler`; `10140–15851`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 909 | 31 | 19 | 0 | 13 |
| 02 | intent | `_json_blocks` | 464 | 15 | 4 | 1 | 10 |
| 03 | period-windows | `_num_pred` | 437 | 21 | 6 | 4 | 5 |
| 04 | calendar-axis | `_sql_ident` | 184 | 11 | 3 | 2 | 7 |
| 05 | entity-form | `entity_form_rank_single_window` | 602 | 20 | 1 | 9 | 14 |
| 06 | entity-search | `_predicates` | 539 | 16 | 3 | 3 | 4 |
| 07 | rrf-vectors | `_corpus_ivf_ready` | 594 | 18 | 8 | 4 | 7 |
| 08 | measures-totals | `_shares_chars` | 244 | 4 | 5 | 3 | 0 |
| 09 | fork-detector | `_measures_by_src` | 781 | 32 | 4 | 9 | 19 |
| 10 | rank | `count_question_skips_axis` | 485 | 15 | 4 | 7 | 6 |
| 11 | sales | `sales_sum_intent` | 661 | 26 | 3 | 6 | 5 |
| 12 | stock-balance | `grain_dec_from_axis_ticket` | 293 | 17 | 3 | 6 | 7 |
| 13 | fork-outcomes | `stock_balance_is_sales_noise` | 478 | 17 | 2 | 7 | 8 |
| 14 | clarify-memory | `_alias_parts` | 699 | 35 | 9 | 3 | 16 |
| 15 | answer-atoms | `stop2_active` | 382 | 14 | 6 | 4 | 3 |
| 16 | veto-pick-entity | `pair_slots_only` | 634 | 22 | 3 | 8 | 4 |
| 17 | aggregate-groups | `_vec` | 504 | 16 | 10 | 3 | 2 |
| 18 | compose | `merge_period2_groups` | 860 | 22 | 6 | 8 | 1 |
| 19 | answer-check | `_readings` | 389 | 14 | 3 | 2 | 5 |
| 20 | ask-main-http | `_filter_dates` | 5712 | 95 | 6 | 19 | 89 |

## 01. infra-trace-llm — Инфра, TRACE, LLM

Якорь: `_new_rid`, end `embed_one`. Участок: [`ubuntu/serenedb/serene_ask.py:1`](ubuntu/serenedb/serene_ask.py:1)–`909`.

Функций: 31. Входящие зоны: 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20. Исходящие зоны: —.

Функции:

- [`_new_rid`](ubuntu/serenedb/serene_ask.py:126) `126–127` len=2
- [`_rid_norm`](ubuntu/serenedb/serene_ask.py:130) `130–135` len=6
- [`_rid_get`](ubuntu/serenedb/serene_ask.py:138) `138–139` len=2
- [`_rid_enter`](ubuntu/serenedb/serene_ask.py:142) `142–145` len=4
- [`_trace_write`](ubuntu/serenedb/serene_ask.py:148) `148–152` len=5
- [`_embed_secret_name_from_env`](ubuntu/serenedb/serene_ask.py:288) `288–292` len=5
- [`_reload_embed_native_env`](ubuntu/serenedb/serene_ask.py:302) `302–308` len=7
- [`psql`](ubuntu/serenedb/serene_ask.py:327) `327–361` len=35
- [`lit`](ubuntu/serenedb/serene_ask.py:364) `364–365` len=2
- [`_embed_host_base`](ubuntu/serenedb/serene_ask.py:368) `368–371` len=4
- [`embed_model_live`](ubuntu/serenedb/serene_ask.py:391) `391–421` len=31
- [`emb_ready`](ubuntu/serenedb/serene_ask.py:424) `424–442` len=19
- [`_fmt`](ubuntu/serenedb/serene_ask.py:445) `445–451` len=7
- [`_fmt_gate_bad`](ubuntu/serenedb/serene_ask.py:454) `454–460` len=7
- [`_gate_bad_preview`](ubuntu/serenedb/serene_ask.py:463) `463–467` len=5
- [`_fmt_human`](ubuntu/serenedb/serene_ask.py:470) `470–484` len=15
- [`_TokenAcc.__init__`](ubuntu/serenedb/serene_ask.py:494) `494–501` len=8 (влож.)
- [`_TokenAcc.add`](ubuntu/serenedb/serene_ask.py:503) `503–512` len=10 (влож.)
- [`_TokenAcc.diag_dict`](ubuntu/serenedb/serene_ask.py:514) `514–520` len=7 (влож.)
- [`_token_acc_start`](ubuntu/serenedb/serene_ask.py:523) `523–524` len=2
- [`_token_acc_record`](ubuntu/serenedb/serene_ask.py:527) `527–541` len=15
- [`_diag_pack`](ubuntu/serenedb/serene_ask.py:544) `544–550` len=7
- [`_ds_chat_content`](ubuntu/serenedb/serene_ask.py:553) `553–566` len=14
- [`_ds_chat_body`](ubuntu/serenedb/serene_ask.py:569) `569–577` len=9
- [`ds_chat_post`](ubuntu/serenedb/serene_ask.py:580) `580–588` len=9
- [`ds_chat`](ubuntu/serenedb/serene_ask.py:591) `591–592` len=2
- [`arbitrate`](ubuntu/serenedb/serene_ask.py:615) `615–641` len=27
- [`_embed_request`](ubuntu/serenedb/serene_ask.py:644) `644–657` len=14
- [`_ensure_embed_secret`](ubuntu/serenedb/serene_ask.py:673) `673–704` len=32
- [`_embed_one_native`](ubuntu/serenedb/serene_ask.py:707) `707–741` len=35
- [`embed_one`](ubuntu/serenedb/serene_ask.py:744) `744–806` len=63

Зовут снаружи зоны: `_TokenAcc.add`, `_diag_pack`, `_fmt`, `_fmt_gate_bad`, `_fmt_human`, `_gate_bad_preview`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_token_acc_start`, `_trace_write`, `arbitrate`, `ds_chat`, `emb_ready`, `embed_model_live`, `embed_one`, `lit`, `psql`

## 02. intent — Intent

Якорь: `_json_blocks`, end `_first_intent_object`. Участок: [`ubuntu/serenedb/serene_ask.py:910`](ubuntu/serenedb/serene_ask.py:910)–`1373`.

Функций: 15. Входящие зоны: 12, 14, 16, 20. Исходящие зоны: 01.

Функции:

- [`_json_blocks`](ubuntu/serenedb/serene_ask.py:910) `910–937` len=28
- [`_intent_text`](ubuntu/serenedb/serene_ask.py:940) `940–951` len=12
- [`_intent_number`](ubuntu/serenedb/serene_ask.py:954) `954–970` len=17
- [`_intent_date`](ubuntu/serenedb/serene_ask.py:973) `973–986` len=14
- [`_intent_terms`](ubuntu/serenedb/serene_ask.py:989) `989–1025` len=37
- [`_intent_word`](ubuntu/serenedb/serene_ask.py:1028) `1028–1030` len=3
- [`same_concept_groups`](ubuntu/serenedb/serene_ask.py:1057) `1057–1096` len=40
- [`_stem_set`](ubuntu/serenedb/serene_ask.py:1099) `1099–1106` len=8
- [`_normalize_intent`](ubuntu/serenedb/serene_ask.py:1109) `1109–1225` len=117
- [`_one_intent`](ubuntu/serenedb/serene_ask.py:1228) `1228–1244` len=17
- [`_field_key`](ubuntu/serenedb/serene_ask.py:1247) `1247–1248` len=2
- [`_field_lead`](ubuntu/serenedb/serene_ask.py:1251) `1251–1259` len=9
- [`_merge_intents`](ubuntu/serenedb/serene_ask.py:1262) `1262–1286` len=25
- [`parse_intent`](ubuntu/serenedb/serene_ask.py:1289) `1289–1348` len=60
- [`_first_intent_object`](ubuntu/serenedb/serene_ask.py:1351) `1351–1370` len=20

Зовут снаружи зоны: `_intent_number`, `_intent_text`, `_intent_word`, `_stem_set`, `parse_intent`

## 03. period-windows — Периоды и окна

Якорь: `_num_pred`, end `apply_period_leader`. Участок: [`ubuntu/serenedb/serene_ask.py:1374`](ubuntu/serenedb/serene_ask.py:1374)–`1810`.

Функций: 21. Входящие зоны: 04, 05, 06, 09, 18, 20. Исходящие зоны: 01, 04, 18, 20.

Функции:

- [`_num_pred`](ubuntu/serenedb/serene_ask.py:1374) `1374–1392` len=19
- [`period_preds`](ubuntu/serenedb/serene_ask.py:1395) `1395–1411` len=17
- [`_calendar_date`](ubuntu/serenedb/serene_ask.py:1442) `1442–1447` len=6
- [`_month_range`](ubuntu/serenedb/serene_ask.py:1450) `1450–1457` len=8
- [`_week_range_monday`](ubuntu/serenedb/serene_ask.py:1460) `1460–1464` len=5
- [`_prev_week_range`](ubuntu/serenedb/serene_ask.py:1467) `1467–1475` len=9
- [`_is_seven_day_span`](ubuntu/serenedb/serene_ask.py:1478) `1478–1482` len=5
- [`_is_current_calendar_week`](ubuntu/serenedb/serene_ask.py:1485) `1485–1492` len=8
- [`_assumed_sliding_week_not_calendar`](ubuntu/serenedb/serene_ask.py:1495) `1495–1505` len=11
- [`_iso_date`](ubuntu/serenedb/serene_ask.py:1508) `1508–1509` len=2
- [`_period_origin`](ubuntu/serenedb/serene_ask.py:1512) `1512–1523` len=12
- [`window_fp_of`](ubuntu/serenedb/serene_ask.py:1526) `1526–1537` len=12
- [`_period_form_id`](ubuntu/serenedb/serene_ask.py:1540) `1540–1564` len=25
- [`_window_reading`](ubuntu/serenedb/serene_ask.py:1567) `1567–1589` len=23
- [`period_readings`](ubuntu/serenedb/serene_ask.py:1592) `1592–1680` len=89
- [`period_readings._add`](ubuntu/serenedb/serene_ask.py:1636) `1636–1641` len=6 (влож.)
- [`render_window_label`](ubuntu/serenedb/serene_ask.py:1683) `1683–1701` len=19
- [`prefer_window_leader`](ubuntu/serenedb/serene_ask.py:1708) `1708–1724` len=17
- [`period_relative_forms`](ubuntu/serenedb/serene_ask.py:1727) `1727–1756` len=30
- [`period_form_from_question`](ubuntu/serenedb/serene_ask.py:1759) `1759–1769` len=11
- [`apply_period_leader`](ubuntu/serenedb/serene_ask.py:1772) `1772–1808` len=37

Зовут снаружи зоны: `_calendar_date`, `_iso_date`, `_month_range`, `_num_pred`, `_prev_week_range`, `_week_range_monday`, `_window_reading`, `apply_period_leader`, `period_form_from_question`, `period_preds`, `period_readings`, `period_readings._add`, `period_relative_forms`, `prefer_window_leader`, `render_window_label`, `window_fp_of`

## 04. calendar-axis — Календарная ось

Якорь: `_sql_ident`, end `_working_day_doc_preds`. Участок: [`ubuntu/serenedb/serene_ask.py:1811`](ubuntu/serenedb/serene_ask.py:1811)–`1994`.

Функций: 11. Входящие зоны: 03, 09, 20. Исходящие зоны: 01, 03.

Функции:

- [`_sql_ident`](ubuntu/serenedb/serene_ask.py:1811) `1811–1813` len=3
- [`calendar_registers`](ubuntu/serenedb/serene_ask.py:1816) `1816–1829` len=14
- [`calendar_working_day_keys`](ubuntu/serenedb/serene_ask.py:1832) `1832–1846` len=15
- [`calendar_map_rows`](ubuntu/serenedb/serene_ask.py:1849) `1849–1877` len=29
- [`calendar_axis_open`](ubuntu/serenedb/serene_ask.py:1880) `1880–1885` len=6
- [`calendar_day_basis_prefer`](ubuntu/serenedb/serene_ask.py:1888) `1888–1906` len=19
- [`_day_basis_reading`](ubuntu/serenedb/serene_ask.py:1909) `1909–1915` len=7
- [`calendar_axis_readings`](ubuntu/serenedb/serene_ask.py:1918) `1918–1933` len=16
- [`expand_readings_calendar_axis`](ubuntu/serenedb/serene_ask.py:1936) `1936–1948` len=13
- [`prefer_day_basis_leader`](ubuntu/serenedb/serene_ask.py:1951) `1951–1961` len=11
- [`_working_day_doc_preds`](ubuntu/serenedb/serene_ask.py:1964) `1964–1992` len=29

Зовут снаружи зоны: `_working_day_doc_preds`, `calendar_axis_open`, `calendar_day_basis_prefer`, `expand_readings_calendar_axis`

## 05. entity-form — Форма сущности

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/serene_ask.py:1995`](ubuntu/serenedb/serene_ask.py:1995)–`2596`.

Функций: 20. Входящие зоны: 20. Исходящие зоны: 01, 03, 06, 09, 10, 11, 13, 15, 17.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/serene_ask.py:1995) `1995–2022` len=28
- [`sales_compare_intent`](ubuntu/serenedb/serene_ask.py:2025) `2025–2056` len=32
- [`sales_compare_windows`](ubuntu/serenedb/serene_ask.py:2059) `2059–2121` len=63
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/serene_ask.py:2125) `2125–2156` len=32
- [`entity_form_movements_for_kind`](ubuntu/serenedb/serene_ask.py:2159) `2159–2196` len=38
- [`entity_form_count_target_is_movement`](ubuntu/serenedb/serene_ask.py:2199) `2199–2234` len=36
- [`entity_form_expand_pool`](ubuntu/serenedb/serene_ask.py:2237) `2237–2257` len=21
- [`entity_form_rolling_year`](ubuntu/serenedb/serene_ask.py:2260) `2260–2270` len=11
- [`entity_form_applicable`](ubuntu/serenedb/serene_ask.py:2273) `2273–2305` len=33
- [`entity_form_collapse_guard`](ubuntu/serenedb/serene_ask.py:2308) `2308–2321` len=14
- [`entity_form_pre_entity_ok`](ubuntu/serenedb/serene_ask.py:2324) `2324–2338` len=15
- [`entity_form_atom_distinct`](ubuntu/serenedb/serene_ask.py:2341) `2341–2351` len=11
- [`entity_form_atom_complement`](ubuntu/serenedb/serene_ask.py:2354) `2354–2370` len=17
- [`aggregate_distinct_axis`](ubuntu/serenedb/serene_ask.py:2373) `2373–2400` len=28
- [`entity_form_axis_on_sales`](ubuntu/serenedb/serene_ask.py:2403) `2403–2432` len=30
- [`entity_form_structs`](ubuntu/serenedb/serene_ask.py:2435) `2435–2493` len=59
- [`entity_form_pick`](ubuntu/serenedb/serene_ask.py:2496) `2496–2506` len=11
- [`entity_form_compute`](ubuntu/serenedb/serene_ask.py:2509) `2509–2533` len=25
- [`try_entity_form_answer`](ubuntu/serenedb/serene_ask.py:2536) `2536–2567` len=32
- [`aggregate_compare_sales`](ubuntu/serenedb/serene_ask.py:2570) `2570–2594` len=25

Зовут снаружи зоны: `aggregate_compare_sales`, `entity_form_applicable`, `entity_form_collapse_guard`, `sales_compare_intent`, `sales_compare_windows`, `try_entity_form_answer`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/serene_ask.py:2597`](ubuntu/serenedb/serene_ask.py:2597)–`3135`.

Функций: 16. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/serene_ask.py:2597) `2597–2605` len=9
- [`_fetch`](ubuntu/serenedb/serene_ask.py:2608) `2608–2620` len=13
- [`_like_pattern`](ubuntu/serenedb/serene_ask.py:2623) `2623–2643` len=21
- [`probe`](ubuntu/serenedb/serene_ask.py:2646) `2646–2748` len=103
- [`matched_group_count`](ubuntu/serenedb/serene_ask.py:2751) `2751–2761` len=11
- [`with_refs`](ubuntu/serenedb/serene_ask.py:2764) `2764–2772` len=9
- [`match_expr`](ubuntu/serenedb/serene_ask.py:2775) `2775–2805` len=31
- [`children_by_parent`](ubuntu/serenedb/serene_ask.py:2808) `2808–2858` len=51
- [`partial_tables`](ubuntu/serenedb/serene_ask.py:2861) `2861–2938` len=78
- [`tables_of`](ubuntu/serenedb/serene_ask.py:2941) `2941–2957` len=17
- [`date_only_kind_filter`](ubuntu/serenedb/serene_ask.py:2960) `2960–2976` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/serene_ask.py:2979) `2979–2994` len=16
- [`alias_hits`](ubuntu/serenedb/serene_ask.py:2997) `2997–3028` len=32
- [`card_hits`](ubuntu/serenedb/serene_ask.py:3031) `3031–3069` len=39
- [`question_exprs`](ubuntu/serenedb/serene_ask.py:3072) `3072–3090` len=19
- [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3093) `3093–3133` len=41

Зовут снаружи зоны: `_predicates`, `alias_hits`, `children_by_parent`, `date_only_kind_filter`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `partial_tables`, `probe`, `question_exprs`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/serene_ask.py:3136`](ubuntu/serenedb/serene_ask.py:3136)–`3729`.

Функций: 18. Входящие зоны: 06, 08, 10, 12, 13, 16, 17, 20. Исходящие зоны: 01, 08, 17, 19.

Функции:

- [`_corpus_ivf_ready`](ubuntu/serenedb/serene_ask.py:3136) `3136–3150` len=15
- [`_resolver_ivf_ready`](ubuntu/serenedb/serene_ask.py:3153) `3153–3172` len=20
- [`_rrf_entity_branches`](ubuntu/serenedb/serene_ask.py:3175) `3175–3206` len=32
- [`_rrf_corpus_branch`](ubuntu/serenedb/serene_ask.py:3209) `3209–3216` len=8
- [`_fused_sql_rrf`](ubuntu/serenedb/serene_ask.py:3219) `3219–3224` len=6
- [`_fused_python_rrf`](ubuntu/serenedb/serene_ask.py:3227) `3227–3243` len=17
- [`_fused_candidates`](ubuntu/serenedb/serene_ask.py:3246) `3246–3297` len=52
- [`near_tables`](ubuntu/serenedb/serene_ask.py:3300) `3300–3338` len=39
- [`rows_of`](ubuntu/serenedb/serene_ask.py:3341) `3341–3373` len=33
- [`signal_terms`](ubuntu/serenedb/serene_ask.py:3408) `3408–3441` len=34
- [`clarify_text`](ubuntu/serenedb/serene_ask.py:3454) `3454–3470` len=17
- [`refuse_text`](ubuntu/serenedb/serene_ask.py:3482) `3482–3504` len=23
- [`rerank`](ubuntu/serenedb/serene_ask.py:3507) `3507–3562` len=56
- [`_resolver_psql`](ubuntu/serenedb/serene_ask.py:3565) `3565–3583` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/serene_ask.py:3590) `3590–3634` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/serene_ask.py:3637) `3637–3658` len=22
- [`resolve_values`](ubuntu/serenedb/serene_ask.py:3663) `3663–3720` len=58
- [`_ngrams`](ubuntu/serenedb/serene_ask.py:3723) `3723–3727` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`, `signal_terms`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/serene_ask.py:3730`](ubuntu/serenedb/serene_ask.py:3730)–`3973`.

Функций: 4. Входящие зоны: 07, 09, 16, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/serene_ask.py:3730) `3730–3740` len=11
- [`measures_of`](ubuntu/serenedb/serene_ask.py:3861) `3861–3874` len=14
- [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3877) `3877–3886` len=10
- [`totals_of`](ubuntu/serenedb/serene_ask.py:3889) `3889–3932` len=44

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 09. fork-detector — Детектор развилки

Якорь: `_measures_by_src`, end `_class_label_lookup`. Участок: [`ubuntu/serenedb/serene_ask.py:3974`](ubuntu/serenedb/serene_ask.py:3974)–`4754`.

Функций: 32. Входящие зоны: 05, 11, 13, 20. Исходящие зоны: 01, 03, 04, 08, 14, 15, 16, 17, 18.

Функции:

- [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3974) `3974–3995` len=22
- [`_aliases_by_src`](ubuntu/serenedb/serene_ask.py:3998) `3998–4014` len=17
- [`_fork_headline_doc_measures`](ubuntu/serenedb/serene_ask.py:4017) `4017–4019` len=3
- [`_fork_word_names_measure`](ubuntu/serenedb/serene_ask.py:4022) `4022–4035` len=14
- [`_fork_sum_headline_pool`](ubuntu/serenedb/serene_ask.py:4038) `4038–4048` len=11
- [`_fork_relevant`](ubuntu/serenedb/serene_ask.py:4051) `4051–4097` len=47
- [`_fork_relevant._sum_fallback`](ubuntu/serenedb/serene_ask.py:4068) `4068–4070` len=3 (влож.)
- [`_fork_relevant._with_doc_hdr`](ubuntu/serenedb/serene_ask.py:4078) `4078–4085` len=8 (влож.)
- [`_fork_pool_excluded`](ubuntu/serenedb/serene_ask.py:4100) `4100–4104` len=5
- [`fork_scan`](ubuntu/serenedb/serene_ask.py:4107) `4107–4181` len=75
- [`fork_scan_readings`](ubuntu/serenedb/serene_ask.py:4184) `4184–4226` len=43
- [`fork_classes_windowed`](ubuntu/serenedb/serene_ask.py:4229) `4229–4258` len=30
- [`fork_detector_scan`](ubuntu/serenedb/serene_ask.py:4261) `4261–4298` len=38
- [`_window_tuple_from_period`](ubuntu/serenedb/serene_ask.py:4301) `4301–4312` len=12
- [`_fork_atom_equiv_fp`](ubuntu/serenedb/serene_ask.py:4315) `4315–4344` len=30
- [`_fork_fp_diag`](ubuntu/serenedb/serene_ask.py:4347) `4347–4356` len=10
- [`fork_classes`](ubuntu/serenedb/serene_ask.py:4359) `4359–4378` len=20
- [`fork_key_of`](ubuntu/serenedb/serene_ask.py:4381) `4381–4390` len=10
- [`_window_fp_base`](ubuntu/serenedb/serene_ask.py:4393) `4393–4397` len=5
- [`_fork_key_for_period`](ubuntu/serenedb/serene_ask.py:4400) `4400–4410` len=11
- [`_fork_day_basis_groups`](ubuntu/serenedb/serene_ask.py:4413) `4413–4430` len=18
- [`_fork_log_day_basis`](ubuntu/serenedb/serene_ask.py:4433) `4433–4450` len=18
- [`_fork_log`](ubuntu/serenedb/serene_ask.py:4453) `4453–4490` len=38
- [`fork_labels_of`](ubuntu/serenedb/serene_ask.py:4493) `4493–4512` len=20
- [`fork_labels_covering`](ubuntu/serenedb/serene_ask.py:4517) `4517–4544` len=28
- [`fork_label_siblings`](ubuntu/serenedb/serene_ask.py:4547) `4547–4554` len=8
- [`_fork_answering_sums`](ubuntu/serenedb/serene_ask.py:4557) `4557–4578` len=22
- [`_fork_headline_measure`](ubuntu/serenedb/serene_ask.py:4581) `4581–4648` len=68
- [`_fork_headline_measure._pick_sum_headline`](ubuntu/serenedb/serene_ask.py:4601) `4601–4614` len=14 (влож.)
- [`_fork_atom_of`](ubuntu/serenedb/serene_ask.py:4651) `4651–4710` len=60
- [`_class_branch_label`](ubuntu/serenedb/serene_ask.py:4713) `4713–4719` len=7
- [`_class_label_lookup`](ubuntu/serenedb/serene_ask.py:4722) `4722–4752` len=31

Зовут снаружи зоны: `_aliases_by_src`, `_class_label_lookup`, `_fork_atom_of`, `_fork_fp_diag`, `_fork_log`, `_fork_pool_excluded`, `_fork_relevant`, `_fork_sum_headline_pool`, `_measures_by_src`, `fork_detector_scan`, `fork_key_of`, `fork_labels_covering`, `fork_labels_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `prefer_entity_for_rank`. Участок: [`ubuntu/serenedb/serene_ask.py:4755`](ubuntu/serenedb/serene_ask.py:4755)–`5239`.

Функций: 15. Входящие зоны: 05, 11, 12, 20. Исходящие зоны: 01, 07, 11, 14, 15, 17, 18.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4755) `4755–4772` len=18
- [`question_wants_breakdown`](ubuntu/serenedb/serene_ask.py:4775) `4775–4787` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4790) `4790–4808` len=19
- [`rank_question_text`](ubuntu/serenedb/serene_ask.py:4813) `4813–4831` len=19
- [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4834) `4834–4847` len=14
- [`rank_leader_answer_text`](ubuntu/serenedb/serene_ask.py:4852) `4852–4872` len=21
- [`rank_axis_label_rows`](ubuntu/serenedb/serene_ask.py:4890) `4890–4913` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/serene_ask.py:4916) `4916–4927` len=12
- [`rank_axis_pick`](ubuntu/serenedb/serene_ask.py:4930) `4930–4976` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/serene_ask.py:4979) `4979–5041` len=63
- [`rank_product_axis_col`](ubuntu/serenedb/serene_ask.py:5044) `5044–5047` len=4
- [`rank_leader_atom`](ubuntu/serenedb/serene_ask.py:5050) `5050–5081` len=32
- [`rank_deterministic_answer`](ubuntu/serenedb/serene_ask.py:5084) `5084–5162` len=79
- [`rank_gate_fallback_answer`](ubuntu/serenedb/serene_ask.py:5165) `5165–5171` len=7
- [`prefer_entity_for_rank`](ubuntu/serenedb/serene_ask.py:5174) `5174–5237` len=64

Зовут снаружи зоны: `count_question_skips_axis`, `prefer_entity_for_rank`, `rank_axes_rerank`, `rank_axis_resolve`, `rank_deterministic_answer`, `rank_gate_fallback_answer`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `period_zero_why_question`. Участок: [`ubuntu/serenedb/serene_ask.py:5240`](ubuntu/serenedb/serene_ask.py:5240)–`5900`.

Функций: 26. Входящие зоны: 05, 10, 20. Исходящие зоны: 01, 09, 10, 12, 14, 17.

Функции:

- [`sales_sum_intent`](ubuntu/serenedb/serene_ask.py:5240) `5240–5268` len=29
- [`_sales_register_score`](ubuntu/serenedb/serene_ask.py:5271) `5271–5286` len=16
- [`sales_lift_possible`](ubuntu/serenedb/serene_ask.py:5289) `5289–5333` len=45
- [`sales_rank_engaged`](ubuntu/serenedb/serene_ask.py:5336) `5336–5358` len=23
- [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5362) `5362–5394` len=33
- [`rank_groups_answer_text`](ubuntu/serenedb/serene_ask.py:5397) `5397–5425` len=29
- [`prefer_entity_for_sales`](ubuntu/serenedb/serene_ask.py:5428) `5428–5531` len=104
- [`sales_canon_src`](ubuntu/serenedb/serene_ask.py:5534) `5534–5546` len=13
- [`sales_money_measure`](ubuntu/serenedb/serene_ask.py:5549) `5549–5568` len=20
- [`sales_qty_measure`](ubuntu/serenedb/serene_ask.py:5572) `5572–5582` len=11
- [`_alias_role_in_question`](ubuntu/serenedb/serene_ask.py:5585) `5585–5604` len=20
- [`_sales_product_rank_qty`](ubuntu/serenedb/serene_ask.py:5607) `5607–5626` len=20
- [`sales_rank_product_axis`](ubuntu/serenedb/serene_ask.py:5629) `5629–5672` len=44
- [`sales_rank_canon_measure`](ubuntu/serenedb/serene_ask.py:5675) `5675–5706` len=32
- [`sales_force_money_measure`](ubuntu/serenedb/serene_ask.py:5709) `5709–5729` len=21
- [`sales_canon_force_pool`](ubuntu/serenedb/serene_ask.py:5732) `5732–5740` len=9
- [`sales_canon_engaged`](ubuntu/serenedb/serene_ask.py:5743) `5743–5760` len=18
- [`_zero_period_not_missing`](ubuntu/serenedb/serene_ask.py:5763) `5763–5770` len=8
- [`sales_ticket_hatch`](ubuntu/serenedb/serene_ask.py:5773) `5773–5779` len=7
- [`sales_noncanon_focus`](ubuntu/serenedb/serene_ask.py:5782) `5782–5790` len=9
- [`sales_refuse_sticky_focus`](ubuntu/serenedb/serene_ask.py:5793) `5793–5825` len=33
- [`_is_price_list_noise`](ubuntu/serenedb/serene_ask.py:5828) `5828–5832` len=5
- [`_is_product_catalog`](ubuntu/serenedb/serene_ask.py:5835) `5835–5841` len=7
- [`prefer_entity_for_catalog_count`](ubuntu/serenedb/serene_ask.py:5844) `5844–5874` len=31
- [`catalog_count_src`](ubuntu/serenedb/serene_ask.py:5877) `5877–5885` len=9
- [`period_zero_why_question`](ubuntu/serenedb/serene_ask.py:5888) `5888–5897` len=10

Зовут снаружи зоны: `_is_product_catalog`, `_sales_rank_top_n`, `_sales_register_score`, `_zero_period_not_missing`, `catalog_count_src`, `period_zero_why_question`, `prefer_entity_for_catalog_count`, `prefer_entity_for_sales`, `rank_groups_answer_text`, `sales_canon_engaged`, `sales_canon_force_pool`, `sales_canon_src`, `sales_force_money_measure`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_rank_canon_measure`, `sales_rank_engaged`, `sales_rank_product_axis`, `sales_refuse_sticky_focus`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `balance_bridge_clarify`. Участок: [`ubuntu/serenedb/serene_ask.py:5901`](ubuntu/serenedb/serene_ask.py:5901)–`6193`.

Функций: 17. Входящие зоны: 11, 13, 20. Исходящие зоны: 01, 02, 07, 10, 14, 20.

Функции:

- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/serene_ask.py:5901) `5901–5907` len=7
- [`_rank_wants_quantity`](ubuntu/serenedb/serene_ask.py:5910) `5910–5914` len=5
- [`rank_measure_hint`](ubuntu/serenedb/serene_ask.py:5917) `5917–5944` len=28
- [`balance_registers`](ubuntu/serenedb/serene_ask.py:5956) `5956–5969` len=14
- [`balance_map_rows`](ubuntu/serenedb/serene_ask.py:5972) `5972–5995` len=24
- [`balance_capable_sources`](ubuntu/serenedb/serene_ask.py:5998) `5998–6000` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/serene_ask.py:6003) `6003–6008` len=6
- [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6011) `6011–6016` len=6
- [`balance_registers_with_goods`](ubuntu/serenedb/serene_ask.py:6019) `6019–6032` len=14
- [`_stems_of_text`](ubuntu/serenedb/serene_ask.py:6035) `6035–6050` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/serene_ask.py:6053) `6053–6066` len=14
- [`stock_asks_named_product`](ubuntu/serenedb/serene_ask.py:6069) `6069–6094` len=26
- [`stock_asks_named_product._is_named_term`](ubuntu/serenedb/serene_ask.py:6076) `6076–6085` len=10 (влож.)
- [`stock_balance_named_no_data`](ubuntu/serenedb/serene_ask.py:6097) `6097–6104` len=8
- [`_balance_map_by_src`](ubuntu/serenedb/serene_ask.py:6107) `6107–6113` len=7
- [`filter_balance_structural`](ubuntu/serenedb/serene_ask.py:6116) `6116–6155` len=40
- [`balance_bridge_clarify`](ubuntu/serenedb/serene_ask.py:6158) `6158–6191` len=34

Зовут снаружи зоны: `_rank_wants_quantity`, `balance_bridge_clarify`, `balance_capable_or_registers`, `balance_registers_with_goods`, `filter_balance_structural`, `grain_dec_from_axis_ticket`, `question_asks_stock_balance`, `rank_measure_hint`, `stock_asks_named_product`, `stock_balance_named_no_data`

## 13. fork-outcomes — Исходы развилки

Якорь: `stock_balance_is_sales_noise`, end `fork_outcome_c`. Участок: [`ubuntu/serenedb/serene_ask.py:6194`](ubuntu/serenedb/serene_ask.py:6194)–`6671`.

Функций: 17. Входящие зоны: 05, 20. Исходящие зоны: 01, 07, 09, 12, 14, 15, 20.

Функции:

- [`stock_balance_is_sales_noise`](ubuntu/serenedb/serene_ask.py:6194) `6194–6203` len=10
- [`filter_stock_balance_sales_noise`](ubuntu/serenedb/serene_ask.py:6206) `6206–6213` len=8
- [`_dedupe_fork_classes`](ubuntu/serenedb/serene_ask.py:6217) `6217–6238` len=22
- [`_class_window_form`](ubuntu/serenedb/serene_ask.py:6245) `6245–6251` len=7
- [`_class_day_basis`](ubuntu/serenedb/serene_ask.py:6254) `6254–6261` len=8
- [`fork_leader_class`](ubuntu/serenedb/serene_ask.py:6264) `6264–6310` len=47
- [`ordered_fork_classes`](ubuntu/serenedb/serene_ask.py:6313) `6313–6331` len=19
- [`_fork_applicable_classes`](ubuntu/serenedb/serene_ask.py:6334) `6334–6337` len=4
- [`resolve_fork_outcome`](ubuntu/serenedb/serene_ask.py:6340) `6340–6389` len=50
- [`_fork_figures_of`](ubuntu/serenedb/serene_ask.py:6392) `6392–6406` len=15
- [`fork_outcome_a`](ubuntu/serenedb/serene_ask.py:6409) `6409–6429` len=21
- [`fork_outcome_unique`](ubuntu/serenedb/serene_ask.py:6433) `6433–6458` len=26
- [`_rivals_figures_empty`](ubuntu/serenedb/serene_ask.py:6461) `6461–6479` len=19
- [`prefer_mute_computed_over_clarify`](ubuntu/serenedb/serene_ask.py:6482) `6482–6510` len=29
- [`atom_terminal_gate_text`](ubuntu/serenedb/serene_ask.py:6513) `6513–6523` len=11
- [`fork_outcome_b`](ubuntu/serenedb/serene_ask.py:6527) `6527–6576` len=50
- [`fork_outcome_c`](ubuntu/serenedb/serene_ask.py:6579) `6579–6669` len=91

Зовут снаружи зоны: `_fork_figures_of`, `atom_terminal_gate_text`, `filter_stock_balance_sales_noise`, `fork_outcome_a`, `fork_outcome_b`, `fork_outcome_c`, `fork_outcome_unique`, `prefer_mute_computed_over_clarify`, `resolve_fork_outcome`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `guards_skip_for_choice`. Участок: [`ubuntu/serenedb/serene_ask.py:6672`](ubuntu/serenedb/serene_ask.py:6672)–`7370`.

Функций: 35. Входящие зоны: 09, 10, 11, 12, 13, 15, 16, 18, 20. Исходящие зоны: 01, 02, 20.

Функции:

- [`_alias_parts`](ubuntu/serenedb/serene_ask.py:6672) `6672–6676` len=5
- [`_word_hits_text`](ubuntu/serenedb/serene_ask.py:6679) `6679–6683` len=5
- [`split_ident`](ubuntu/serenedb/serene_ask.py:6686) `6686–6690` len=5
- [`measure_choice`](ubuntu/serenedb/serene_ask.py:6693) `6693–6746` len=54
- [`measure_captions`](ubuntu/serenedb/serene_ask.py:6749) `6749–6767` len=19
- [`resolve_measure`](ubuntu/serenedb/serene_ask.py:6770) `6770–6802` len=33
- [`slot_measure_uncovered`](ubuntu/serenedb/serene_ask.py:6805) `6805–6813` len=9
- [`clarify_complete`](ubuntu/serenedb/serene_ask.py:6816) `6816–6832` len=17
- [`_slot_fp`](ubuntu/serenedb/serene_ask.py:6849) `6849–6867` len=19
- [`answers_diverge`](ubuntu/serenedb/serene_ask.py:6870) `6870–6903` len=34
- [`answers_src_conflict`](ubuntu/serenedb/serene_ask.py:6905) `6905–6920` len=16
- [`question_fingerprint`](ubuntu/serenedb/serene_ask.py:6935) `6935–6938` len=4
- [`db_fingerprint`](ubuntu/serenedb/serene_ask.py:6941) `6941–6955` len=15
- [`options_version`](ubuntu/serenedb/serene_ask.py:6958) `6958–6971` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/serene_ask.py:6974) `6974–6983` len=10
- [`_new_decision_id`](ubuntu/serenedb/serene_ask.py:6986) `6986–6988` len=3
- [`_purge_decisions`](ubuntu/serenedb/serene_ask.py:6991) `6991–7006` len=16
- [`_resolved_key`](ubuntu/serenedb/serene_ask.py:7009) `7009–7011` len=3
- [`peek_resolved`](ubuntu/serenedb/serene_ask.py:7014) `7014–7020` len=7
- [`accumulate_resolution`](ubuntu/serenedb/serene_ask.py:7023) `7023–7040` len=18
- [`issue_decision`](ubuntu/serenedb/serene_ask.py:7043) `7043–7079` len=37
- [`seal_clarify`](ubuntu/serenedb/serene_ask.py:7082) `7082–7134` len=53
- [`consume_decision`](ubuntu/serenedb/serene_ask.py:7137) `7137–7164` len=28
- [`peek_decision`](ubuntu/serenedb/serene_ask.py:7167) `7167–7187` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/serene_ask.py:7190) `7190–7214` len=25
- [`reissue_clarify`](ubuntu/serenedb/serene_ask.py:7217) `7217–7235` len=19
- [`choice_error_response`](ubuntu/serenedb/serene_ask.py:7238) `7238–7256` len=19
- [`reset_decisions_for_tests`](ubuntu/serenedb/serene_ask.py:7259) `7259–7264` len=6
- [`attach_memory_shadow`](ubuntu/serenedb/serene_ask.py:7267) `7267–7278` len=12
- [`choice_proven`](ubuntu/serenedb/serene_ask.py:7281) `7281–7287` len=7
- [`choice_levels_proven`](ubuntu/serenedb/serene_ask.py:7290) `7290–7304` len=15
- [`measure_already_proven`](ubuntu/serenedb/serene_ask.py:7307) `7307–7311` len=5
- [`entity_choice_locked`](ubuntu/serenedb/serene_ask.py:7314) `7314–7316` len=3
- [`hold_settled_entity`](ubuntu/serenedb/serene_ask.py:7319) `7319–7353` len=35
- [`guards_skip_for_choice`](ubuntu/serenedb/serene_ask.py:7356) `7356–7368` len=13

Зовут снаружи зоны: `accumulate_resolution`, `answers_diverge`, `answers_src_conflict`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `guards_skip_for_choice`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `slot_measure_uncovered`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `stop2_active`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/serene_ask.py:7371`](ubuntu/serenedb/serene_ask.py:7371)–`7752`.

Функций: 14. Входящие зоны: 05, 09, 10, 13, 16, 20. Исходящие зоны: 01, 14, 17, 18.

Функции:

- [`stop2_active`](ubuntu/serenedb/serene_ask.py:7371) `7371–7381` len=11
- [`determined_answer_rivals`](ubuntu/serenedb/serene_ask.py:7384) `7384–7419` len=36
- [`determined_answer_rivals.family`](ubuntu/serenedb/serene_ask.py:7395) `7395–7396` len=2 (влож.)
- [`determined_answer_rivals.add`](ubuntu/serenedb/serene_ask.py:7401) `7401–7404` len=4 (влож.)
- [`answer_money`](ubuntu/serenedb/serene_ask.py:7424) `7424–7433` len=10
- [`answer_slot_mode`](ubuntu/serenedb/serene_ask.py:7436) `7436–7462` len=27
- [`compose_slot_values`](ubuntu/serenedb/serene_ask.py:7465) `7465–7536` len=72
- [`atom_operation`](ubuntu/serenedb/serene_ask.py:7551) `7551–7565` len=15
- [`_atom_exact_value`](ubuntu/serenedb/serene_ask.py:7568) `7568–7587` len=20
- [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7590) `7590–7633` len=44
- [`atom_from_agg`](ubuntu/serenedb/serene_ask.py:7636) `7636–7677` len=42
- [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7680) `7680–7718` len=39
- [`fill_atom_pairs`](ubuntu/serenedb/serene_ask.py:7721) `7721–7750` len=30
- [`fill_atom_pairs.one`](ubuntu/serenedb/serene_ask.py:7732) `7732–7748` len=17 (влож.)

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `build_answer_atom`, `compose_slot_values`, `determined_answer_rivals`, `fill_atom_pairs`, `fill_atom_pairs.one`, `render_atom_pair`, `stop2_active`

## 16. veto-pick-entity — Вето и выбор сущности

Якорь: `pair_slots_only`, end `pick_entity`. Участок: [`ubuntu/serenedb/serene_ask.py:7753`](ubuntu/serenedb/serene_ask.py:7753)–`8386`.

Функций: 22. Входящие зоны: 09, 18, 20. Исходящие зоны: 01, 02, 07, 08, 14, 15, 18, 20.

Функции:

- [`pair_slots_only`](ubuntu/serenedb/serene_ask.py:7753) `7753–7755` len=3
- [`atom_whitelist_labels`](ubuntu/serenedb/serene_ask.py:7758) `7758–7767` len=10
- [`atom_whitelist_numbers`](ubuntu/serenedb/serene_ask.py:7770) `7770–7786` len=17
- [`arbiter_figures`](ubuntu/serenedb/serene_ask.py:7789) `7789–7795` len=7
- [`alias_supported`](ubuntu/serenedb/serene_ask.py:7798) `7798–7866` len=69
- [`not_for_excludes`](ubuntu/serenedb/serene_ask.py:7869) `7869–7904` len=36
- [`pair_unanswered`](ubuntu/serenedb/serene_ask.py:7907) `7907–7917` len=11
- [`single_is_rival`](ubuntu/serenedb/serene_ask.py:7920) `7920–7928` len=9
- [`veto_top_without`](ubuntu/serenedb/serene_ask.py:7931) `7931–7939` len=9
- [`figures_numbers`](ubuntu/serenedb/serene_ask.py:7942) `7942–7959` len=18
- [`same_number`](ubuntu/serenedb/serene_ask.py:7962) `7962–7986` len=25
- [`unresolved_quantity`](ubuntu/serenedb/serene_ask.py:7988) `7988–8008` len=21
- [`mute_measure_blocks`](ubuntu/serenedb/serene_ask.py:8011) `8011–8026` len=16
- [`measure_row_all_zero`](ubuntu/serenedb/serene_ask.py:8029) `8029–8036` len=8
- [`alive_measure_names`](ubuntu/serenedb/serene_ask.py:8039) `8039–8041` len=3
- [`filter_dead_measure_alts`](ubuntu/serenedb/serene_ask.py:8044) `8044–8052` len=9
- [`measure_asked_explicitly`](ubuntu/serenedb/serene_ask.py:8055) `8055–8063` len=9
- [`format_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8066) `8066–8084` len=19
- [`build_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8087) `8087–8140` len=54
- [`measure_ambiguous`](ubuntu/serenedb/serene_ask.py:8143) `8143–8159` len=17
- [`pick_measure`](ubuntu/serenedb/serene_ask.py:8162) `8162–8207` len=46
- [`pick_entity`](ubuntu/serenedb/serene_ask.py:8210) `8210–8384` len=175

Зовут снаружи зоны: `alias_supported`, `arbiter_figures`, `build_measure_empty_pivot`, `figures_numbers`, `filter_dead_measure_alts`, `measure_ambiguous`, `measure_asked_explicitly`, `measure_row_all_zero`, `mute_measure_blocks`, `not_for_excludes`, `pair_slots_only`, `pair_unanswered`, `pick_entity`, `pick_measure`, `same_number`, `single_is_rival`, `unresolved_quantity`, `veto_top_without`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/serene_ask.py:8387`](ubuntu/serenedb/serene_ask.py:8387)–`8890`.

Функций: 16. Входящие зоны: 05, 07, 08, 09, 10, 11, 15, 18, 19, 20. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/serene_ask.py:8387) `8387–8388` len=2
- [`_num`](ubuntu/serenedb/serene_ask.py:8391) `8391–8395` len=5
- [`_numN`](ubuntu/serenedb/serene_ask.py:8398) `8398–8411` len=14
- [`aggregate`](ubuntu/serenedb/serene_ask.py:8414) `8414–8529` len=116
- [`src_is_child`](ubuntu/serenedb/serene_ask.py:8533) `8533–8542` len=10
- [`refcols_of`](ubuntu/serenedb/serene_ask.py:8545) `8545–8559` len=15
- [`holders_of_target`](ubuntu/serenedb/serene_ask.py:8562) `8562–8579` len=18
- [`measures_of_many`](ubuntu/serenedb/serene_ask.py:8582) `8582–8597` len=16
- [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8600) `8600–8631` len=32
- [`kind_axis_rerank`](ubuntu/serenedb/serene_ask.py:8634) `8634–8657` len=24
- [`term_ref_owners`](ubuntu/serenedb/serene_ask.py:8660) `8660–8686` len=27
- [`term_axis_hits`](ubuntu/serenedb/serene_ask.py:8689) `8689–8728` len=40
- [`resolve_member_names`](ubuntu/serenedb/serene_ask.py:8731) `8731–8758` len=28
- [`_group_leader`](ubuntu/serenedb/serene_ask.py:8761) `8761–8770` len=10
- [`_group_fold`](ubuntu/serenedb/serene_ask.py:8773) `8773–8779` len=7
- [`aggregate_groups`](ubuntu/serenedb/serene_ask.py:8782) `8782–8888` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `holders_of_target`, `kind_axis_hits`, `kind_axis_rerank`, `measures_of_many`, `refcols_of`, `src_is_child`, `term_axis_hits`, `term_ref_owners`

## 18. compose — Формулировка

Якорь: `merge_period2_groups`, end `compose`. Участок: [`ubuntu/serenedb/serene_ask.py:8891`](ubuntu/serenedb/serene_ask.py:8891)–`9750`.

Функций: 22. Входящие зоны: 03, 09, 10, 15, 16, 20. Исходящие зоны: 01, 03, 08, 14, 16, 17, 19, 20.

Функции:

- [`merge_period2_groups`](ubuntu/serenedb/serene_ask.py:8891) `8891–8906` len=16
- [`axis_clarify_options`](ubuntu/serenedb/serene_ask.py:8909) `8909–8933` len=25
- [`_split_answer`](ubuntu/serenedb/serene_ask.py:8980) `8980–9010` len=31
- [`_group_value_by_name`](ubuntu/serenedb/serene_ask.py:9030) `9030–9046` len=17
- [`_fill_figures`](ubuntu/serenedb/serene_ask.py:9049) `9049–9170` len=122
- [`_fill_figures.one`](ubuntu/serenedb/serene_ask.py:9127) `9127–9168` len=42 (влож.)
- [`ensure_n_groups_named`](ubuntu/serenedb/serene_ask.py:9173) `9173–9191` len=19
- [`ensure_count_named`](ubuntu/serenedb/serene_ask.py:9194) `9194–9212` len=19
- [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9217) `9217–9227` len=11
- [`postprocess_money_answer_text`](ubuntu/serenedb/serene_ask.py:9230) `9230–9238` len=9
- [`build_answer_passport`](ubuntu/serenedb/serene_ask.py:9240) `9240–9300` len=61
- [`build_answer_passport._add`](ubuntu/serenedb/serene_ask.py:9255) `9255–9261` len=7 (влож.)
- [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9303) `9303–9312` len=10
- [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9315) `9315–9324` len=10
- [`_table_label`](ubuntu/serenedb/serene_ask.py:9327) `9327–9338` len=12
- [`_passport_axis_label`](ubuntu/serenedb/serene_ask.py:9341) `9341–9352` len=12
- [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9355) `9355–9362` len=8
- [`formulation_flaws`](ubuntu/serenedb/serene_ask.py:9365) `9365–9392` len=28
- [`copied_figures`](ubuntu/serenedb/serene_ask.py:9395) `9395–9462` len=68
- [`_filled_ask`](ubuntu/serenedb/serene_ask.py:9465) `9465–9483` len=19
- [`_ask_back`](ubuntu/serenedb/serene_ask.py:9486) `9486–9500` len=15
- [`compose`](ubuntu/serenedb/serene_ask.py:9503) `9503–9725` len=223

Зовут снаружи зоны: `_ask_back`, `_fill_figures`, `_fill_figures.one`, `_filled_ask`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `build_answer_passport._add`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `merge_period2_groups`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/serene_ask.py:9751`](ubuntu/serenedb/serene_ask.py:9751)–`10139`.

Функций: 14. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/serene_ask.py:9751) `9751–9791` len=41
- [`_plausible`](ubuntu/serenedb/serene_ask.py:9794) `9794–9803` len=10
- [`_dates`](ubuntu/serenedb/serene_ask.py:9806) `9806–9826` len=21
- [`_date2_readings`](ubuntu/serenedb/serene_ask.py:9829) `9829–9840` len=12
- [`_date_spans`](ubuntu/serenedb/serene_ask.py:9843) `9843–9863` len=21
- [`_tokens`](ubuntu/serenedb/serene_ask.py:9866) `9866–9896` len=31
- [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9899) `9899–9904` len=6
- [`check_claims`](ubuntu/serenedb/serene_ask.py:9910) `9910–9943` len=34
- [`claims_in_text`](ubuntu/serenedb/serene_ask.py:9949) `9949–9988` len=40
- [`prompt_leak`](ubuntu/serenedb/serene_ask.py:9991) `9991–10010` len=20
- [`asked_figure_missing`](ubuntu/serenedb/serene_ask.py:10013) `10013–10087` len=75
- [`stale_note`](ubuntu/serenedb/serene_ask.py:10090) `10090–10105` len=16
- [`_threshold_values`](ubuntu/serenedb/serene_ask.py:10108) `10108–10112` len=5
- [`_filter_values`](ubuntu/serenedb/serene_ask.py:10115) `10115–10137` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/serene_ask.py:10140`](ubuntu/serenedb/serene_ask.py:10140)–`15851`.

Функций: 95. Входящие зоны: 03, 12, 13, 14, 16, 18. Исходящие зоны: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19.

Функции:

- [`_filter_dates`](ubuntu/serenedb/serene_ask.py:10140) `10140–10149` len=10
- [`without_list_markers`](ubuntu/serenedb/serene_ask.py:10160) `10160–10174` len=15
- [`rows_seen`](ubuntu/serenedb/serene_ask.py:10177) `10177–10201` len=25
- [`gate`](ubuntu/serenedb/serene_ask.py:10204) `10204–10365` len=162
- [`gate.allow`](ubuntu/serenedb/serene_ask.py:10223) `10223–10241` len=19 (влож.)
- [`count_figures`](ubuntu/serenedb/serene_ask.py:10368) `10368–10382` len=15
- [`gate_out`](ubuntu/serenedb/serene_ask.py:10385) `10385–10403` len=19
- [`_opt_values`](ubuntu/serenedb/serene_ask.py:10406) `10406–10421` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/serene_ask.py:10424) `10424–10439` len=16
- [`clarify_choice_line`](ubuntu/serenedb/serene_ask.py:10442) `10442–10449` len=8
- [`format_clarify_options`](ubuntu/serenedb/serene_ask.py:10452) `10452–10460` len=9
- [`clarify_say`](ubuntu/serenedb/serene_ask.py:10463) `10463–10485` len=23
- [`_entity_counts_objects`](ubuntu/serenedb/serene_ask.py:10498) `10498–10515` len=18
- [`_vitrina_objects`](ubuntu/serenedb/serene_ask.py:10518) `10518–10531` len=14
- [`_coverage_of`](ubuntu/serenedb/serene_ask.py:10542) `10542–10603` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/serene_ask.py:10630) `10630–10665` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/serene_ask.py:10668) `10668–10670` len=3
- [`_measure_health_gap`](ubuntu/serenedb/serene_ask.py:10673) `10673–10688` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/serene_ask.py:10692) `10692–10706` len=15
- [`_classify_health_gap`](ubuntu/serenedb/serene_ask.py:10709) `10709–10739` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/serene_ask.py:10742) `10742–10747` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/serene_ask.py:10750) `10750–10799` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/serene_ask.py:10802) `10802–10814` len=13
- [`_health_gap`](ubuntu/serenedb/serene_ask.py:10817) `10817–10829` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/serene_ask.py:10832) `10832–10840` len=9
- [`_coverage_answer`](ubuntu/serenedb/serene_ask.py:10864) `10864–10948` len=85
- [`kind_word`](ubuntu/serenedb/serene_ask.py:11005) `11005–11008` len=4
- [`label_with_kind`](ubuntu/serenedb/serene_ask.py:11011) `11011–11022` len=12
- [`ambiguous_labels`](ubuntu/serenedb/serene_ask.py:11028) `11028–11050` len=23
- [`disambiguate_labels`](ubuntu/serenedb/serene_ask.py:11053) `11053–11070` len=18
- [`opts_hints`](ubuntu/serenedb/serene_ask.py:11082) `11082–11141` len=60
- [`mk_opts`](ubuntu/serenedb/serene_ask.py:11144) `11144–11171` len=28
- [`live_src_counts`](ubuntu/serenedb/serene_ask.py:11174) `11174–11206` len=33
- [`empty_after_period_action`](ubuntu/serenedb/serene_ask.py:11209) `11209–11224` len=16
- [`period_empty_outcome`](ubuntu/serenedb/serene_ask.py:11227) `11227–11251` len=25
- [`_period_day_label`](ubuntu/serenedb/serene_ask.py:11254) `11254–11269` len=16
- [`_period_day_label.one`](ubuntu/serenedb/serene_ask.py:11256) `11256–11261` len=6 (влож.)
- [`sales_period_empty`](ubuntu/serenedb/serene_ask.py:11274) `11274–11289` len=16
- [`sales_period_window_active`](ubuntu/serenedb/serene_ask.py:11292) `11292–11304` len=13
- [`sales_fork_canon_empty_src`](ubuntu/serenedb/serene_ask.py:11307) `11307–11332` len=26
- [`try_sales_fork_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11335) `11335–11360` len=26
- [`sales_fork_blocks_clarify`](ubuntu/serenedb/serene_ask.py:11363) `11363–11374` len=12
- [`dates_outside_period_filter`](ubuntu/serenedb/serene_ask.py:11377) `11377–11391` len=15
- [`format_period_empty_text`](ubuntu/serenedb/serene_ask.py:11394) `11394–11442` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11445) `11445–11497` len=53
- [`drop_period_preds`](ubuntu/serenedb/serene_ask.py:11500) `11500–11506` len=7
- [`_term_stems`](ubuntu/serenedb/serene_ask.py:11509) `11509–11524` len=16
- [`_src_covers_term_stems`](ubuntu/serenedb/serene_ask.py:11527) `11527–11539` len=13
- [`align_picked_to_terms`](ubuntu/serenedb/serene_ask.py:11542) `11542–11569` len=28
- [`resolve_focus`](ubuntu/serenedb/serene_ask.py:11572) `11572–11706` len=135
- [`_word_hits_measure`](ubuntu/serenedb/serene_ask.py:11710) `11710–11722` len=13
- [`axis_focus_plan`](ubuntu/serenedb/serene_ask.py:11725) `11725–11793` len=69
- [`_day_ord`](ubuntu/serenedb/serene_ask.py:11796) `11796–11801` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/serene_ask.py:11804) `11804–11828` len=25
- [`period_slot_for_inherit`](ubuntu/serenedb/serene_ask.py:11831) `11831–11842` len=12
- [`apply_prior_period`](ubuntu/serenedb/serene_ask.py:11845) `11845–11873` len=29
- [`answer`](ubuntu/serenedb/serene_ask.py:11876) `11876–14999` len=3124
- [`answer.шаг`](ubuntu/serenedb/serene_ask.py:11912) `11912–11917` len=6 (влож.)
- [`answer._family`](ubuntu/serenedb/serene_ask.py:12932) `12932–12933` len=2 (влож.)
- [`answer._alias_verdict`](ubuntu/serenedb/serene_ask.py:12935) `12935–13088` len=154 (влож.)
- [`answer._alias_verdict._место`](ubuntu/serenedb/serene_ask.py:13046) `13046–13050` len=5 (влож.)
- [`answer._alias_verdict._probe`](ubuntu/serenedb/serene_ask.py:13052) `13052–13063` len=12 (влож.)
- [`answer._alias_clarify`](ubuntu/serenedb/serene_ask.py:13090) `13090–13118` len=29 (влож.)
- [`answer._checked`](ubuntu/serenedb/serene_ask.py:13388) `13388–13404` len=17 (влож.)
- [`question_facts`](ubuntu/serenedb/serene_ask.py:15022) `15022–15048` len=27
- [`entity_has_dates`](ubuntu/serenedb/serene_ask.py:15051) `15051–15072` len=22
- [`_gate_need`](ubuntu/serenedb/serene_ask.py:15075) `15075–15088` len=14
- [`_need_clarify`](ubuntu/serenedb/serene_ask.py:15091) `15091–15107` len=17
- [`_journal_keep_n`](ubuntu/serenedb/serene_ask.py:15110) `15110–15124` len=15
- [`_journal_code_md5`](ubuntu/serenedb/serene_ask.py:15127) `15127–15134` len=8
- [`_journal_build_ts`](ubuntu/serenedb/serene_ask.py:15137) `15137–15148` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/serene_ask.py:15151) `15151–15164` len=14
- [`_journal_sql_int`](ubuntu/serenedb/serene_ask.py:15167) `15167–15173` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/serene_ask.py:15176) `15176–15179` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/serene_ask.py:15182) `15182–15210` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/serene_ask.py:15213) `15213–15235` len=23
- [`_journal_doubt`](ubuntu/serenedb/serene_ask.py:15238) `15238–15247` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/serene_ask.py:15250) `15250–15263` len=14
- [`_journal_intent`](ubuntu/serenedb/serene_ask.py:15266) `15266–15268` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/serene_ask.py:15271) `15271–15279` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/serene_ask.py:15282) `15282–15301` len=20
- [`_ask_journal_write`](ubuntu/serenedb/serene_ask.py:15304) `15304–15418` len=115
- [`_ask_journal_write._insert_row`](ubuntu/serenedb/serene_ask.py:15348) `15348–15397` len=50 (влож.)
- [`_answer_checked_core`](ubuntu/serenedb/serene_ask.py:15422) `15422–15464` len=43
- [`_answer_checked_core.plain`](ubuntu/serenedb/serene_ask.py:15426) `15426–15428` len=3 (влож.)
- [`_try_memory_apply`](ubuntu/serenedb/serene_ask.py:15469) `15469–15494` len=26
- [`answer_checked`](ubuntu/serenedb/serene_ask.py:15496) `15496–15577` len=82
- [`_build_ask_scope`](ubuntu/serenedb/serene_ask.py:15582) `15582–15623` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/serene_ask.py:15626) `15626–15645` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/serene_ask.py:15648) `15648–15659` len=12
- [`Handler.log_message`](ubuntu/serenedb/serene_ask.py:15665) `15665–15666` len=2 (влож.)
- [`Handler._send`](ubuntu/serenedb/serene_ask.py:15668) `15668–15674` len=7 (влож.)
- [`Handler.do_GET`](ubuntu/serenedb/serene_ask.py:15676) `15676–15742` len=67 (влож.)
- [`Handler.do_POST`](ubuntu/serenedb/serene_ask.py:15744) `15744–15835` len=92 (влож.)
- [`main`](ubuntu/serenedb/serene_ask.py:15838) `15838–15847` len=10

Зовут снаружи зоны: `_period_day_label`, `clarify_say`, `disambiguate_labels`, `format_clarify_options`, `kind_word`, `mk_opts`

## Сквозные функции

Функции, которые вызывают из трёх и более других зон.

| функция | зона | вызывающих зон | зоны |
|---|---|---:|---|
| [`psql`](ubuntu/serenedb/serene_ask.py:327) | 01 | 17 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17, 18, 20 |
| [`lit`](ubuntu/serenedb/serene_ask.py:364) | 01 | 16 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 16, 17, 18, 20 |
| [`_fmt`](ubuntu/serenedb/serene_ask.py:445) | 01 | 6 | 05, 13, 15, 18, 19, 20 |
| [`_diag_pack`](ubuntu/serenedb/serene_ask.py:544) | 01 | 6 | 05, 10, 12, 13, 16, 20 |
| [`ds_chat`](ubuntu/serenedb/serene_ask.py:591) | 01 | 6 | 02, 07, 10, 16, 18, 20 |
| [`measure_choice`](ubuntu/serenedb/serene_ask.py:6693) | 14 | 5 | 09, 11, 12, 16, 20 |
| [`_num`](ubuntu/serenedb/serene_ask.py:8391) | 17 | 5 | 05, 08, 09, 18, 20 |
| [`_fmt_human`](ubuntu/serenedb/serene_ask.py:470) | 01 | 4 | 10, 11, 16, 18 |
| [`period_preds`](ubuntu/serenedb/serene_ask.py:1395) | 03 | 4 | 05, 06, 09, 20 |
| [`rerank`](ubuntu/serenedb/serene_ask.py:3507) | 07 | 4 | 10, 16, 17, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3877) | 08 | 4 | 09, 16, 18, 20 |
| [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4834) | 10 | 4 | 05, 11, 12, 20 |
| [`refcols_of`](ubuntu/serenedb/serene_ask.py:8545) | 17 | 4 | 05, 10, 11, 20 |
| [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3093) | 06 | 3 | 05, 17, 20 |
| [`refuse_text`](ubuntu/serenedb/serene_ask.py:3482) | 07 | 3 | 12, 13, 20 |
| [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3974) | 09 | 3 | 05, 11, 20 |
| [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5362) | 11 | 3 | 05, 10, 20 |
| [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6011) | 12 | 3 | 11, 13, 20 |
| [`split_ident`](ubuntu/serenedb/serene_ask.py:6686) | 14 | 3 | 09, 13, 18 |
| [`measure_captions`](ubuntu/serenedb/serene_ask.py:6749) | 14 | 3 | 16, 18, 20 |
| [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7590) | 15 | 3 | 05, 09, 10 |
| [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7680) | 15 | 3 | 05, 13, 20 |
| [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8600) | 17 | 3 | 10, 11, 20 |
| [`_group_leader`](ubuntu/serenedb/serene_ask.py:8761) | 17 | 3 | 10, 15, 19 |
| [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9217) | 18 | 3 | 10, 15, 20 |
| [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9303) | 18 | 3 | 10, 16, 20 |
| [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9315) | 18 | 3 | 09, 10, 20 |
| [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9355) | 18 | 3 | 10, 16, 20 |
| [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9899) | 19 | 3 | 07, 18, 20 |

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

### 11 sales (5/26)

- `_alias_role_in_question`
- `_is_price_list_noise`
- `_sales_product_rank_qty`
- `sales_lift_possible`
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

### 18 compose (1/22)

- `_group_value_by_name`

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
| `SERENEDB_DSN_RO` | [63](ubuntu/serenedb/serene_ask.py:63) | — | `(модуль)` |
| `PGPASSWORD` | [64](ubuntu/serenedb/serene_ask.py:64) | "" | `(модуль)` |
| `RESOLVER_DSN` | [70](ubuntu/serenedb/serene_ask.py:70) | "" | `(модуль)` |
| `RESOLVER_PW` | [71](ubuntu/serenedb/serene_ask.py:71) | "" | `(модуль)` |
| `ASK_LISTEN_HOST` | [72](ubuntu/serenedb/serene_ask.py:72) | "127.0.0.1" | `(модуль)` |
| `ASK_LISTEN_PORT` | [73](ubuntu/serenedb/serene_ask.py:73) | "8091" | `(модуль)` |
| `ASK_TOKEN` | [74](ubuntu/serenedb/serene_ask.py:74) | "" | `(модуль)` |
| `ASK_MONEY_UNIT` | [75](ubuntu/serenedb/serene_ask.py:75) | "" | `(модуль)` |
| `ASK_CARD_TABLE` | [86](ubuntu/serenedb/serene_ask.py:86) | "search_entity_card" | `(модуль)` |
| `ASK_PICK_BUDGET_CHARS` | [92](ubuntu/serenedb/serene_ask.py:92) | "8000" | `(модуль)` |
| `ASK_ROWS_BUDGET_CHARS` | [99](ubuntu/serenedb/serene_ask.py:99) | "24000" | `(модуль)` |
| `ASK_TERMS_FOR` | [103](ubuntu/serenedb/serene_ask.py:103) | "3" | `(модуль)` |
| `ASK_COVERAGE_TOP` | [107](ubuntu/serenedb/serene_ask.py:107) | "15" | `(модуль)` |
| `ASK_STALE_WARN_SEC` | [111](ubuntu/serenedb/serene_ask.py:111) | "3600" | `(модуль)` |
| `ASK_TERMS_TOP` | [112](ubuntu/serenedb/serene_ask.py:112) | "6" | `(модуль)` |
| `ASK_TOPK` | [113](ubuntu/serenedb/serene_ask.py:113) | "40" | `(модуль)` |
| `ASK_TRACE` | [117](ubuntu/serenedb/serene_ask.py:117) | "1" | `(модуль)` |
| `ASK_ROWS_TO_MODEL` | [118](ubuntu/serenedb/serene_ask.py:118) | "25" | `(модуль)` |
| `ASK_SCORER` | [183](ubuntu/serenedb/serene_ask.py:183) | "bm25" | `(модуль)` |
| `ASK_REFS_BOOST` | [195](ubuntu/serenedb/serene_ask.py:195) | "8.0" | `(модуль)` |
| `ASK_ORDER_BY_MEANING` | [202](ubuntu/serenedb/serene_ask.py:202) | "1" | `(модуль)` |
| `RERANK_URL` | [218](ubuntu/serenedb/serene_ask.py:218) | — | `(модуль)` |
| `ALIBABA_RERANK_URL` | [219](ubuntu/serenedb/serene_ask.py:219) | — | `(модуль)` |
| `RERANK_MODEL` | [221](ubuntu/serenedb/serene_ask.py:221) | — | `(модуль)` |
| `ALIBABA_RERANK_MODEL` | [222](ubuntu/serenedb/serene_ask.py:222) | — | `(модуль)` |
| `RERANK_API` | [223](ubuntu/serenedb/serene_ask.py:223) | "<expr>" | `(модуль)` |
| `ASK_RERANK_TOP` | [228](ubuntu/serenedb/serene_ask.py:228) | "60" | `(модуль)` |
| `DEEPSEEK_BASE` | [236](ubuntu/serenedb/serene_ask.py:236) | "https://api.deepseek.com" | `(модуль)` |
| `DEEPSEEK_API_KEY` | [237](ubuntu/serenedb/serene_ask.py:237) | "" | `(модуль)` |
| `DEEPSEEK_MODEL` | [245](ubuntu/serenedb/serene_ask.py:245) | "deepseek-v4-pro" | `(модуль)` |
| `DEEPSEEK_THINKING` | [246](ubuntu/serenedb/serene_ask.py:246) | "disabled" | `(модуль)` |
| `ASK_THINKING_OFF_BODY` | [249](ubuntu/serenedb/serene_ask.py:249) | "" | `(модуль)` |
| `EMBED_BASE_URL` | [258](ubuntu/serenedb/serene_ask.py:258) | — | `(модуль)` |
| `ALIBABA_EMBED_URL` | [259](ubuntu/serenedb/serene_ask.py:259) | "" | `(модуль)` |
| `EMBED_API` | [265](ubuntu/serenedb/serene_ask.py:265) | "openai" | `(модуль)` |
| `EMBED_QUERY_PATH` | [266](ubuntu/serenedb/serene_ask.py:266) | "/embed" | `(модуль)` |
| `EMBED_UA` | [269](ubuntu/serenedb/serene_ask.py:269) | "curl/8.5.0" | `(модуль)` |
| `EMBED_HEALTH_URL` | [271](ubuntu/serenedb/serene_ask.py:271) | — | `(модуль)` |
| `EMBED_API_KEY` | [272](ubuntu/serenedb/serene_ask.py:272) | — | `(модуль)` |
| `ALIBABA_API_KEY` | [272](ubuntu/serenedb/serene_ask.py:272) | "" | `(модуль)` |
| `EMBED_MODEL` | [273](ubuntu/serenedb/serene_ask.py:273) | "text-embedding-v4" | `(модуль)` |
| `RERANK_API_KEY` | [276](ubuntu/serenedb/serene_ask.py:276) | — | `(модуль)` |
| `EMBED_DIM` | [284](ubuntu/serenedb/serene_ask.py:284) | "1024" | `(модуль)` |
| `EMBED_PATH` | [296](ubuntu/serenedb/serene_ask.py:296) | "/v1/embeddings" | `(модуль)` |
| `ASK_EMBED_NATIVE` | [297](ubuntu/serenedb/serene_ask.py:297) | "0" | `(модуль)` |
| `ASK_NO_DATA_TEXT` | [317](ubuntu/serenedb/serene_ask.py:317) | "" | `(модуль)` |
| `ASK_TOTAL_TEXT` | [318](ubuntu/serenedb/serene_ask.py:318) | "" | `(модуль)` |
| `ASK_STALE_TEXT` | [321](ubuntu/serenedb/serene_ask.py:321) | "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад." | `(модуль)` |
| `ASK_EMB_CACHE` | [664](ubuntu/serenedb/serene_ask.py:664) | "256" | `(модуль)` |
| `ASK_EMB_RETRY` | [668](ubuntu/serenedb/serene_ask.py:668) | "2" | `(модуль)` |
| `ASK_EMB_RETRY_PAUSE` | [669](ubuntu/serenedb/serene_ask.py:669) | "0.4" | `(модуль)` |
| `ASK_EMB_TIMEOUT` | [670](ubuntu/serenedb/serene_ask.py:670) | "60" | `(модуль)` |
| `ASK_INTENT_MAX_TOKENS` | [888](ubuntu/serenedb/serene_ask.py:888) | "400" | `(модуль)` |
| `ASK_INTENT_SAMPLES` | [889](ubuntu/serenedb/serene_ask.py:889) | "5" | `(модуль)` |
| `ASK_INTENT_LEAD` | [890](ubuntu/serenedb/serene_ask.py:890) | "3" | `(модуль)` |
| `ASK_INTENT_MEMO` | [892](ubuntu/serenedb/serene_ask.py:892) | "512" | `(модуль)` |
| `ASK_INTENT_GROUPS` | [899](ubuntu/serenedb/serene_ask.py:899) | "6" | `(модуль)` |
| `ASK_INTENT_ALTS` | [900](ubuntu/serenedb/serene_ask.py:900) | "6" | `(модуль)` |
| `ASK_STEM_DICT` | [903](ubuntu/serenedb/serene_ask.py:903) | "search_dict_stem" | `(модуль)` |
| `ASK_SOLR_SYNONYMS` | [906](ubuntu/serenedb/serene_ask.py:906) | "0" | `(модуль)` |
| `ASK_SOLR_SYNONYMS_DICT` | [907](ubuntu/serenedb/serene_ask.py:907) | "" | `(модуль)` |
| `ASK_CALENDAR_AXIS` | [1424](ubuntu/serenedb/serene_ask.py:1424) | "0" | `(модуль)` |
| `ASK_SALES_RANK_CANON` | [1426](ubuntu/serenedb/serene_ask.py:1426) | "0" | `(модуль)` |
| `ASK_ATOM_TERMINAL` | [1428](ubuntu/serenedb/serene_ask.py:1428) | "0" | `(модуль)` |
| `ASK_ENTITY_FORM` | [1431](ubuntu/serenedb/serene_ask.py:1431) | "0" | `(модуль)` |
| `ASK_RESOLVE_NEAR` | [3586](ubuntu/serenedb/serene_ask.py:3586) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [3587](ubuntu/serenedb/serene_ask.py:3587) | "3" | `(модуль)` |
| `ASK_ALIAS_TOP` | [3746](ubuntu/serenedb/serene_ask.py:3746) | "8" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [3749](ubuntu/serenedb/serene_ask.py:3749) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [3754](ubuntu/serenedb/serene_ask.py:3754) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [3759](ubuntu/serenedb/serene_ask.py:3759) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [3762](ubuntu/serenedb/serene_ask.py:3762) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [3763](ubuntu/serenedb/serene_ask.py:3763) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [3768](ubuntu/serenedb/serene_ask.py:3768) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [3769](ubuntu/serenedb/serene_ask.py:3769) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_ALIAS_VETO` | [3782](ubuntu/serenedb/serene_ask.py:3782) | "1" | `(модуль)` |
| `ASK_PROBE` | [3789](ubuntu/serenedb/serene_ask.py:3789) | "0" | `(модуль)` |
| `ASK_SKIP_SERVICE_RIVALS` | [3793](ubuntu/serenedb/serene_ask.py:3793) | "1" | `(модуль)` |
| `ASK_ALIAS_BY_CONCEPTS` | [3805](ubuntu/serenedb/serene_ask.py:3805) | "0" | `(модуль)` |
| `ASK_VETO_NEEDS_RANK` | [3820](ubuntu/serenedb/serene_ask.py:3820) | "0" | `(модуль)` |
| `ASK_VETO_HEAD_WINS` | [3830](ubuntu/serenedb/serene_ask.py:3830) | "1" | `(модуль)` |
| `ASK_MEANING_TOP` | [3856](ubuntu/serenedb/serene_ask.py:3856) | "0" | `(модуль)` |
| `ASK_FORK_DETECT` | [3948](ubuntu/serenedb/serene_ask.py:3948) | "1" | `(модуль)` |
| `ASK_FORK_OUTCOMES` | [3949](ubuntu/serenedb/serene_ask.py:3949) | "1" | `(модуль)` |
| `ASK_JOURNAL` | [3952](ubuntu/serenedb/serene_ask.py:3952) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [3957](ubuntu/serenedb/serene_ask.py:3957) | "1" | `(модуль)` |
| `ASK_MEMORY_APPLY` | [3959](ubuntu/serenedb/serene_ask.py:3959) | "0" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [3970](ubuntu/serenedb/serene_ask.py:3970) | "600" | `(модуль)` |
| `ASK_RAW_FOCUS_TRUST` | [6926](ubuntu/serenedb/serene_ask.py:6926) | "0" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [6927](ubuntu/serenedb/serene_ask.py:6927) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [10617](ubuntu/serenedb/serene_ask.py:10617) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [10625](ubuntu/serenedb/serene_ask.py:10625) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [10626](ubuntu/serenedb/serene_ask.py:10626) | "search_idx" | `(модуль)` |
| `ASK_SIGNAL_DISAGREE` | [10954](ubuntu/serenedb/serene_ask.py:10954) | "1" | `(модуль)` |
| `ASK_REQUIRE_SUPPORT` | [10956](ubuntu/serenedb/serene_ask.py:10956) | "1" | `(модуль)` |
| `ASK_ARBITER_MAX` | [10959](ubuntu/serenedb/serene_ask.py:10959) | "3" | `(модуль)` |
| `ASK_ARBITER_DETECTS` | [10965](ubuntu/serenedb/serene_ask.py:10965) | "1" | `(модуль)` |
| `ASK_NOT_FOR` | [10967](ubuntu/serenedb/serene_ask.py:10967) | "1" | `(модуль)` |
| `ASK_STEM_DICT` | [10970](ubuntu/serenedb/serene_ask.py:10970) | "search_dict_stem" | `(модуль)` |
| `ASK_AMBIG_TTL` | [10973](ubuntu/serenedb/serene_ask.py:10973) | "300" | `(модуль)` |
| `ASK_ENOUGH` | [15014](ubuntu/serenedb/serene_ask.py:15014) | "1" | `(модуль)` |
| `ASK_SLOT_COVER` | [15016](ubuntu/serenedb/serene_ask.py:15016) | "0" | `(модуль)` |
| `EMBED_SECRET` | [289](ubuntu/serenedb/serene_ask.py:289) | — | `_embed_secret_name_from_env` |
| `EMBED_SECRETS` | [289](ubuntu/serenedb/serene_ask.py:289) | — | `_embed_secret_name_from_env` |
| `EMBED_PATH` | [305](ubuntu/serenedb/serene_ask.py:305) | "/v1/embeddings" | `_reload_embed_native_env` |
| `ASK_EMBED_NATIVE` | [306](ubuntu/serenedb/serene_ask.py:306) | "0" | `_reload_embed_native_env` |
| `EMBED_DIM` | [307](ubuntu/serenedb/serene_ask.py:307) | "1024" | `_reload_embed_native_env` |
| `EMBED_HOST` | [369](ubuntu/serenedb/serene_ask.py:369) | — | `_embed_host_base` |
| `ASK_JOURNAL_KEEP` | [15113](ubuntu/serenedb/serene_ask.py:15113) | — | `_journal_keep_n` |

## Обращения наружу

Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`.

### psql (154)

- [`ubuntu/serenedb/serene_ask.py:435`](ubuntu/serenedb/serene_ask.py:435) в `emb_ready`
- [`ubuntu/serenedb/serene_ask.py:684`](ubuntu/serenedb/serene_ask.py:684) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:699`](ubuntu/serenedb/serene_ask.py:699) в `_ensure_embed_secret`
- [`ubuntu/serenedb/serene_ask.py:718`](ubuntu/serenedb/serene_ask.py:718) в `_embed_one_native`
- [`ubuntu/serenedb/serene_ask.py:1069`](ubuntu/serenedb/serene_ask.py:1069) в `same_concept_groups`
- [`ubuntu/serenedb/serene_ask.py:1735`](ubuntu/serenedb/serene_ask.py:1735) в `period_relative_forms`
- [`ubuntu/serenedb/serene_ask.py:1823`](ubuntu/serenedb/serene_ask.py:1823) в `calendar_registers`
- [`ubuntu/serenedb/serene_ask.py:1839`](ubuntu/serenedb/serene_ask.py:1839) в `calendar_working_day_keys`
- [`ubuntu/serenedb/serene_ask.py:1859`](ubuntu/serenedb/serene_ask.py:1859) в `calendar_map_rows`
- [`ubuntu/serenedb/serene_ask.py:2136`](ubuntu/serenedb/serene_ask.py:2136) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2170`](ubuntu/serenedb/serene_ask.py:2170) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2387`](ubuntu/serenedb/serene_ask.py:2387) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/serene_ask.py:2617`](ubuntu/serenedb/serene_ask.py:2617) в `_fetch`
- [`ubuntu/serenedb/serene_ask.py:2689`](ubuntu/serenedb/serene_ask.py:2689) в `probe`
- [`ubuntu/serenedb/serene_ask.py:2792`](ubuntu/serenedb/serene_ask.py:2792) в `match_expr`
- [`ubuntu/serenedb/serene_ask.py:2831`](ubuntu/serenedb/serene_ask.py:2831) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2850`](ubuntu/serenedb/serene_ask.py:2850) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2920`](ubuntu/serenedb/serene_ask.py:2920) в `partial_tables`
- [`ubuntu/serenedb/serene_ask.py:2952`](ubuntu/serenedb/serene_ask.py:2952) в `tables_of`
- [`ubuntu/serenedb/serene_ask.py:3022`](ubuntu/serenedb/serene_ask.py:3022) в `alias_hits`
- [`ubuntu/serenedb/serene_ask.py:3062`](ubuntu/serenedb/serene_ask.py:3062) в `card_hits`
- [`ubuntu/serenedb/serene_ask.py:3144`](ubuntu/serenedb/serene_ask.py:3144) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/serene_ask.py:3224`](ubuntu/serenedb/serene_ask.py:3224) в `_fused_sql_rrf`
- [`ubuntu/serenedb/serene_ask.py:3232`](ubuntu/serenedb/serene_ask.py:3232) в `_fused_python_rrf`
- [`ubuntu/serenedb/serene_ask.py:3333`](ubuntu/serenedb/serene_ask.py:3333) в `near_tables`
- [`ubuntu/serenedb/serene_ask.py:3369`](ubuntu/serenedb/serene_ask.py:3369) в `rows_of`
- [`ubuntu/serenedb/serene_ask.py:3423`](ubuntu/serenedb/serene_ask.py:3423) в `signal_terms`
- [`ubuntu/serenedb/serene_ask.py:3652`](ubuntu/serenedb/serene_ask.py:3652) в `_resolve_values_corpus`
- [`ubuntu/serenedb/serene_ask.py:3869`](ubuntu/serenedb/serene_ask.py:3869) в `measures_of`
- [`ubuntu/serenedb/serene_ask.py:3880`](ubuntu/serenedb/serene_ask.py:3880) в `measure_aliases_of`
- [`ubuntu/serenedb/serene_ask.py:3921`](ubuntu/serenedb/serene_ask.py:3921) в `totals_of`
- [`ubuntu/serenedb/serene_ask.py:3985`](ubuntu/serenedb/serene_ask.py:3985) в `_measures_by_src`
- [`ubuntu/serenedb/serene_ask.py:4004`](ubuntu/serenedb/serene_ask.py:4004) в `_aliases_by_src`
- [`ubuntu/serenedb/serene_ask.py:4142`](ubuntu/serenedb/serene_ask.py:4142) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4165`](ubuntu/serenedb/serene_ask.py:4165) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4442`](ubuntu/serenedb/serene_ask.py:4442) в `_fork_log_day_basis`
- [`ubuntu/serenedb/serene_ask.py:4482`](ubuntu/serenedb/serene_ask.py:4482) в `_fork_log`
- [`ubuntu/serenedb/serene_ask.py:4502`](ubuntu/serenedb/serene_ask.py:4502) в `fork_labels_of`
- [`ubuntu/serenedb/serene_ask.py:4527`](ubuntu/serenedb/serene_ask.py:4527) в `fork_labels_covering`
- [`ubuntu/serenedb/serene_ask.py:4899`](ubuntu/serenedb/serene_ask.py:4899) в `rank_axis_label_rows`
- [`ubuntu/serenedb/serene_ask.py:5187`](ubuntu/serenedb/serene_ask.py:5187) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5205`](ubuntu/serenedb/serene_ask.py:5205) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5303`](ubuntu/serenedb/serene_ask.py:5303) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5327`](ubuntu/serenedb/serene_ask.py:5327) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5446`](ubuntu/serenedb/serene_ask.py:5446) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5470`](ubuntu/serenedb/serene_ask.py:5470) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5502`](ubuntu/serenedb/serene_ask.py:5502) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5482`](ubuntu/serenedb/serene_ask.py:5482) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5859`](ubuntu/serenedb/serene_ask.py:5859) в `prefer_entity_for_catalog_count`
- [`ubuntu/serenedb/serene_ask.py:5965`](ubuntu/serenedb/serene_ask.py:5965) в `balance_registers`
- [`ubuntu/serenedb/serene_ask.py:5983`](ubuntu/serenedb/serene_ask.py:5983) в `balance_map_rows`
- [`ubuntu/serenedb/serene_ask.py:6028`](ubuntu/serenedb/serene_ask.py:6028) в `balance_registers_with_goods`
- [`ubuntu/serenedb/serene_ask.py:6042`](ubuntu/serenedb/serene_ask.py:6042) в `_stems_of_text`
- [`ubuntu/serenedb/serene_ask.py:6131`](ubuntu/serenedb/serene_ask.py:6131) в `filter_balance_structural`
- [`ubuntu/serenedb/serene_ask.py:6167`](ubuntu/serenedb/serene_ask.py:6167) в `balance_bridge_clarify`
- [`ubuntu/serenedb/serene_ask.py:6635`](ubuntu/serenedb/serene_ask.py:6635) в `fork_outcome_c`
- [`ubuntu/serenedb/serene_ask.py:6951`](ubuntu/serenedb/serene_ask.py:6951) в `db_fingerprint`
- [`ubuntu/serenedb/serene_ask.py:8229`](ubuntu/serenedb/serene_ask.py:8229) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8267`](ubuntu/serenedb/serene_ask.py:8267) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8489`](ubuntu/serenedb/serene_ask.py:8489) в `aggregate`
- [`ubuntu/serenedb/serene_ask.py:8538`](ubuntu/serenedb/serene_ask.py:8538) в `src_is_child`
- [`ubuntu/serenedb/serene_ask.py:8550`](ubuntu/serenedb/serene_ask.py:8550) в `refcols_of`
- [`ubuntu/serenedb/serene_ask.py:8567`](ubuntu/serenedb/serene_ask.py:8567) в `holders_of_target`
- [`ubuntu/serenedb/serene_ask.py:8587`](ubuntu/serenedb/serene_ask.py:8587) в `measures_of_many`
- [`ubuntu/serenedb/serene_ask.py:8609`](ubuntu/serenedb/serene_ask.py:8609) в `kind_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8644`](ubuntu/serenedb/serene_ask.py:8644) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:8671`](ubuntu/serenedb/serene_ask.py:8671) в `term_ref_owners`
- [`ubuntu/serenedb/serene_ask.py:8705`](ubuntu/serenedb/serene_ask.py:8705) в `term_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8743`](ubuntu/serenedb/serene_ask.py:8743) в `resolve_member_names`
- [`ubuntu/serenedb/serene_ask.py:8852`](ubuntu/serenedb/serene_ask.py:8852) в `aggregate_groups`
- [`ubuntu/serenedb/serene_ask.py:8918`](ubuntu/serenedb/serene_ask.py:8918) в `axis_clarify_options`
- [`ubuntu/serenedb/serene_ask.py:9332`](ubuntu/serenedb/serene_ask.py:9332) в `_table_label`
- [`ubuntu/serenedb/serene_ask.py:10501`](ubuntu/serenedb/serene_ask.py:10501) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10509`](ubuntu/serenedb/serene_ask.py:10509) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10521`](ubuntu/serenedb/serene_ask.py:10521) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10529`](ubuntu/serenedb/serene_ask.py:10529) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10553`](ubuntu/serenedb/serene_ask.py:10553) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10590`](ubuntu/serenedb/serene_ask.py:10590) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10563`](ubuntu/serenedb/serene_ask.py:10563) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10680`](ubuntu/serenedb/serene_ask.py:10680) в `_measure_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10700`](ubuntu/serenedb/serene_ask.py:10700) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/serene_ask.py:10721`](ubuntu/serenedb/serene_ask.py:10721) в `_classify_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10776`](ubuntu/serenedb/serene_ask.py:10776) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/serene_ask.py:10873`](ubuntu/serenedb/serene_ask.py:10873) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:10882`](ubuntu/serenedb/serene_ask.py:10882) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:11044`](ubuntu/serenedb/serene_ask.py:11044) в `ambiguous_labels`
- [`ubuntu/serenedb/serene_ask.py:11090`](ubuntu/serenedb/serene_ask.py:11090) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11097`](ubuntu/serenedb/serene_ask.py:11097) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11107`](ubuntu/serenedb/serene_ask.py:11107) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11117`](ubuntu/serenedb/serene_ask.py:11117) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11196`](ubuntu/serenedb/serene_ask.py:11196) в `live_src_counts`
- [`ubuntu/serenedb/serene_ask.py:11385`](ubuntu/serenedb/serene_ask.py:11385) в `dates_outside_period_filter`
- [`ubuntu/serenedb/serene_ask.py:11517`](ubuntu/serenedb/serene_ask.py:11517) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11520`](ubuntu/serenedb/serene_ask.py:11520) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11532`](ubuntu/serenedb/serene_ask.py:11532) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11535`](ubuntu/serenedb/serene_ask.py:11535) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11555`](ubuntu/serenedb/serene_ask.py:11555) в `align_picked_to_terms`
- [`ubuntu/serenedb/serene_ask.py:11611`](ubuntu/serenedb/serene_ask.py:11611) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11616`](ubuntu/serenedb/serene_ask.py:11616) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11635`](ubuntu/serenedb/serene_ask.py:11635) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11675`](ubuntu/serenedb/serene_ask.py:11675) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11772`](ubuntu/serenedb/serene_ask.py:11772) в `axis_focus_plan`
- [`ubuntu/serenedb/serene_ask.py:12177`](ubuntu/serenedb/serene_ask.py:12177) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12269`](ubuntu/serenedb/serene_ask.py:12269) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12837`](ubuntu/serenedb/serene_ask.py:12837) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12914`](ubuntu/serenedb/serene_ask.py:12914) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12961`](ubuntu/serenedb/serene_ask.py:12961) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14215`](ubuntu/serenedb/serene_ask.py:14215) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14557`](ubuntu/serenedb/serene_ask.py:14557) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14578`](ubuntu/serenedb/serene_ask.py:14578) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12278`](ubuntu/serenedb/serene_ask.py:12278) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14350`](ubuntu/serenedb/serene_ask.py:14350) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12315`](ubuntu/serenedb/serene_ask.py:12315) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12354`](ubuntu/serenedb/serene_ask.py:12354) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12519`](ubuntu/serenedb/serene_ask.py:12519) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12548`](ubuntu/serenedb/serene_ask.py:12548) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12570`](ubuntu/serenedb/serene_ask.py:12570) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12589`](ubuntu/serenedb/serene_ask.py:12589) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12613`](ubuntu/serenedb/serene_ask.py:12613) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12766`](ubuntu/serenedb/serene_ask.py:12766) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12900`](ubuntu/serenedb/serene_ask.py:12900) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13099`](ubuntu/serenedb/serene_ask.py:13099) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13772`](ubuntu/serenedb/serene_ask.py:13772) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13952`](ubuntu/serenedb/serene_ask.py:13952) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14372`](ubuntu/serenedb/serene_ask.py:14372) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12299`](ubuntu/serenedb/serene_ask.py:12299) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13011`](ubuntu/serenedb/serene_ask.py:13011) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13635`](ubuntu/serenedb/serene_ask.py:13635) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12450`](ubuntu/serenedb/serene_ask.py:12450) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12926`](ubuntu/serenedb/serene_ask.py:12926) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13034`](ubuntu/serenedb/serene_ask.py:13034) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13673`](ubuntu/serenedb/serene_ask.py:13673) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13739`](ubuntu/serenedb/serene_ask.py:13739) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13754`](ubuntu/serenedb/serene_ask.py:13754) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12961`](ubuntu/serenedb/serene_ask.py:12961) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13011`](ubuntu/serenedb/serene_ask.py:13011) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13034`](ubuntu/serenedb/serene_ask.py:13034) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13099`](ubuntu/serenedb/serene_ask.py:13099) в `answer._alias_clarify`
- [`ubuntu/serenedb/serene_ask.py:15065`](ubuntu/serenedb/serene_ask.py:15065) в `entity_has_dates`
- [`ubuntu/serenedb/serene_ask.py:15119`](ubuntu/serenedb/serene_ask.py:15119) в `_journal_keep_n`
- [`ubuntu/serenedb/serene_ask.py:15143`](ubuntu/serenedb/serene_ask.py:15143) в `_journal_build_ts`
- [`ubuntu/serenedb/serene_ask.py:15156`](ubuntu/serenedb/serene_ask.py:15156) в `_journal_alias_ver`
- [`ubuntu/serenedb/serene_ask.py:15390`](ubuntu/serenedb/serene_ask.py:15390) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15411`](ubuntu/serenedb/serene_ask.py:15411) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15404`](ubuntu/serenedb/serene_ask.py:15404) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15406`](ubuntu/serenedb/serene_ask.py:15406) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15413`](ubuntu/serenedb/serene_ask.py:15413) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15345`](ubuntu/serenedb/serene_ask.py:15345) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15394`](ubuntu/serenedb/serene_ask.py:15394) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15407`](ubuntu/serenedb/serene_ask.py:15407) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15390`](ubuntu/serenedb/serene_ask.py:15390) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15394`](ubuntu/serenedb/serene_ask.py:15394) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15679`](ubuntu/serenedb/serene_ask.py:15679) в `Handler.do_GET`
- [`ubuntu/serenedb/serene_ask.py:15806`](ubuntu/serenedb/serene_ask.py:15806) в `Handler.do_POST`

### ds_chat (10)

- [`ubuntu/serenedb/serene_ask.py:631`](ubuntu/serenedb/serene_ask.py:631) в `arbitrate`
- [`ubuntu/serenedb/serene_ask.py:1230`](ubuntu/serenedb/serene_ask.py:1230) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:1238`](ubuntu/serenedb/serene_ask.py:1238) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:3467`](ubuntu/serenedb/serene_ask.py:3467) в `clarify_text`
- [`ubuntu/serenedb/serene_ask.py:3500`](ubuntu/serenedb/serene_ask.py:3500) в `refuse_text`
- [`ubuntu/serenedb/serene_ask.py:4951`](ubuntu/serenedb/serene_ask.py:4951) в `rank_axis_pick`
- [`ubuntu/serenedb/serene_ask.py:8332`](ubuntu/serenedb/serene_ask.py:8332) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:9724`](ubuntu/serenedb/serene_ask.py:9724) в `compose`
- [`ubuntu/serenedb/serene_ask.py:10902`](ubuntu/serenedb/serene_ask.py:10902) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:15037`](ubuntu/serenedb/serene_ask.py:15037) в `question_facts`

### embed_one (1)

- [`ubuntu/serenedb/serene_ask.py:8388`](ubuntu/serenedb/serene_ask.py:8388) в `_vec`

### rerank (5)

- [`ubuntu/serenedb/serene_ask.py:3718`](ubuntu/serenedb/serene_ask.py:3718) в `resolve_values`
- [`ubuntu/serenedb/serene_ask.py:4924`](ubuntu/serenedb/serene_ask.py:4924) в `rank_axes_rerank`
- [`ubuntu/serenedb/serene_ask.py:8192`](ubuntu/serenedb/serene_ask.py:8192) в `pick_measure`
- [`ubuntu/serenedb/serene_ask.py:8654`](ubuntu/serenedb/serene_ask.py:8654) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:12525`](ubuntu/serenedb/serene_ask.py:12525) в `answer`

### urlopen (4)

- [`ubuntu/serenedb/serene_ask.py:411`](ubuntu/serenedb/serene_ask.py:411) в `embed_model_live`
- [`ubuntu/serenedb/serene_ask.py:587`](ubuntu/serenedb/serene_ask.py:587) в `ds_chat_post`
- [`ubuntu/serenedb/serene_ask.py:789`](ubuntu/serenedb/serene_ask.py:789) в `embed_one`
- [`ubuntu/serenedb/serene_ask.py:3541`](ubuntu/serenedb/serene_ask.py:3541) в `rerank`
