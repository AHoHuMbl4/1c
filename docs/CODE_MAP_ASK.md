# Карта `ubuntu/serenedb/serene_ask.py`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **15913**. Функций: **463**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **30**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/serene_ask.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–909`)
- [02 intent](ubuntu/serenedb/serene_ask.py:910) — Intent (якорь `_json_blocks` … `_first_intent_object`; `910–1373`)
- [03 period-windows](ubuntu/serenedb/serene_ask.py:1374) — Периоды и окна (якорь `_num_pred` … `apply_period_leader`; `1374–1810`)
- [04 calendar-axis](ubuntu/serenedb/serene_ask.py:1811) — Календарная ось (якорь `_sql_ident` … `_working_day_doc_preds`; `1811–1994`)
- [05 entity-form](ubuntu/serenedb/serene_ask.py:1995) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `1995–2590`)
- [06 entity-search](ubuntu/serenedb/serene_ask.py:2591) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `2591–3129`)
- [07 rrf-vectors](ubuntu/serenedb/serene_ask.py:3130) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `3130–3723`)
- [08 measures-totals](ubuntu/serenedb/serene_ask.py:3724) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `3724–3967`)
- [09 fork-detector](ubuntu/serenedb/serene_ask.py:3968) — Детектор развилки (якорь `_measures_by_src` … `_class_label_lookup`; `3968–4748`)
- [10 rank](ubuntu/serenedb/serene_ask.py:4749) — Ранг (якорь `count_question_skips_axis` … `prefer_entity_for_rank`; `4749–5233`)
- [11 sales](ubuntu/serenedb/serene_ask.py:5234) — Продажи (якорь `sales_sum_intent` … `period_zero_why_question`; `5234–5951`)
- [12 stock-balance](ubuntu/serenedb/serene_ask.py:5952) — Остатки (якорь `grain_dec_from_axis_ticket` … `balance_bridge_clarify`; `5952–6244`)
- [13 fork-outcomes](ubuntu/serenedb/serene_ask.py:6245) — Исходы развилки (якорь `stock_balance_is_sales_noise` … `fork_outcome_c`; `6245–6722`)
- [14 clarify-memory](ubuntu/serenedb/serene_ask.py:6723) — Уточнение и память (якорь `_alias_parts` … `guards_skip_for_choice`; `6723–7421`)
- [15 answer-atoms](ubuntu/serenedb/serene_ask.py:7422) — Атомы ответа (якорь `stop2_active` … `fill_atom_pairs`; `7422–7803`)
- [16 veto-pick-entity](ubuntu/serenedb/serene_ask.py:7804) — Вето и выбор сущности (якорь `pair_slots_only` … `pick_entity`; `7804–8437`)
- [17 aggregate-groups](ubuntu/serenedb/serene_ask.py:8438) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `8438–8941`)
- [18 compose](ubuntu/serenedb/serene_ask.py:8942) — Формулировка (якорь `merge_period2_groups` … `compose`; `8942–9830`)
- [19 answer-check](ubuntu/serenedb/serene_ask.py:9831) — Проверка ответа (якорь `_readings` … `_filter_values`; `9831–10219`)
- [20 ask-main-http](ubuntu/serenedb/serene_ask.py:10220) — ask / HTTP (якорь `_filter_dates` … `Handler`; `10220–15913`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 909 | 31 | 19 | 0 | 13 |
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
| 19 | answer-check | `_readings` | 389 | 14 | 3 | 2 | 5 |
| 20 | ask-main-http | `_filter_dates` | 5694 | 95 | 6 | 19 | 89 |

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

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/serene_ask.py:1995`](ubuntu/serenedb/serene_ask.py:1995)–`2590`.

Функций: 20. Входящие зоны: 11, 20. Исходящие зоны: 01, 03, 06, 09, 10, 11, 13, 15, 17.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/serene_ask.py:1995) `1995–2022` len=28
- [`sales_compare_intent`](ubuntu/serenedb/serene_ask.py:2025) `2025–2056` len=32
- [`sales_compare_windows`](ubuntu/serenedb/serene_ask.py:2059) `2059–2115` len=57
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/serene_ask.py:2119) `2119–2150` len=32
- [`entity_form_movements_for_kind`](ubuntu/serenedb/serene_ask.py:2153) `2153–2190` len=38
- [`entity_form_count_target_is_movement`](ubuntu/serenedb/serene_ask.py:2193) `2193–2228` len=36
- [`entity_form_expand_pool`](ubuntu/serenedb/serene_ask.py:2231) `2231–2251` len=21
- [`entity_form_rolling_year`](ubuntu/serenedb/serene_ask.py:2254) `2254–2264` len=11
- [`entity_form_applicable`](ubuntu/serenedb/serene_ask.py:2267) `2267–2299` len=33
- [`entity_form_collapse_guard`](ubuntu/serenedb/serene_ask.py:2302) `2302–2315` len=14
- [`entity_form_pre_entity_ok`](ubuntu/serenedb/serene_ask.py:2318) `2318–2332` len=15
- [`entity_form_atom_distinct`](ubuntu/serenedb/serene_ask.py:2335) `2335–2345` len=11
- [`entity_form_atom_complement`](ubuntu/serenedb/serene_ask.py:2348) `2348–2364` len=17
- [`aggregate_distinct_axis`](ubuntu/serenedb/serene_ask.py:2367) `2367–2394` len=28
- [`entity_form_axis_on_sales`](ubuntu/serenedb/serene_ask.py:2397) `2397–2426` len=30
- [`entity_form_structs`](ubuntu/serenedb/serene_ask.py:2429) `2429–2487` len=59
- [`entity_form_pick`](ubuntu/serenedb/serene_ask.py:2490) `2490–2500` len=11
- [`entity_form_compute`](ubuntu/serenedb/serene_ask.py:2503) `2503–2527` len=25
- [`try_entity_form_answer`](ubuntu/serenedb/serene_ask.py:2530) `2530–2561` len=32
- [`aggregate_compare_sales`](ubuntu/serenedb/serene_ask.py:2564) `2564–2588` len=25

Зовут снаружи зоны: `aggregate_compare_sales`, `entity_form_applicable`, `entity_form_collapse_guard`, `sales_compare_intent`, `sales_compare_windows`, `try_entity_form_answer`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/serene_ask.py:2591`](ubuntu/serenedb/serene_ask.py:2591)–`3129`.

Функций: 16. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/serene_ask.py:2591) `2591–2599` len=9
- [`_fetch`](ubuntu/serenedb/serene_ask.py:2602) `2602–2614` len=13
- [`_like_pattern`](ubuntu/serenedb/serene_ask.py:2617) `2617–2637` len=21
- [`probe`](ubuntu/serenedb/serene_ask.py:2640) `2640–2742` len=103
- [`matched_group_count`](ubuntu/serenedb/serene_ask.py:2745) `2745–2755` len=11
- [`with_refs`](ubuntu/serenedb/serene_ask.py:2758) `2758–2766` len=9
- [`match_expr`](ubuntu/serenedb/serene_ask.py:2769) `2769–2799` len=31
- [`children_by_parent`](ubuntu/serenedb/serene_ask.py:2802) `2802–2852` len=51
- [`partial_tables`](ubuntu/serenedb/serene_ask.py:2855) `2855–2932` len=78
- [`tables_of`](ubuntu/serenedb/serene_ask.py:2935) `2935–2951` len=17
- [`date_only_kind_filter`](ubuntu/serenedb/serene_ask.py:2954) `2954–2970` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/serene_ask.py:2973) `2973–2988` len=16
- [`alias_hits`](ubuntu/serenedb/serene_ask.py:2991) `2991–3022` len=32
- [`card_hits`](ubuntu/serenedb/serene_ask.py:3025) `3025–3063` len=39
- [`question_exprs`](ubuntu/serenedb/serene_ask.py:3066) `3066–3084` len=19
- [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3087) `3087–3127` len=41

Зовут снаружи зоны: `_predicates`, `alias_hits`, `children_by_parent`, `date_only_kind_filter`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `partial_tables`, `probe`, `question_exprs`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/serene_ask.py:3130`](ubuntu/serenedb/serene_ask.py:3130)–`3723`.

Функций: 18. Входящие зоны: 06, 08, 10, 12, 13, 16, 17, 20. Исходящие зоны: 01, 08, 17, 19.

Функции:

- [`_corpus_ivf_ready`](ubuntu/serenedb/serene_ask.py:3130) `3130–3144` len=15
- [`_resolver_ivf_ready`](ubuntu/serenedb/serene_ask.py:3147) `3147–3166` len=20
- [`_rrf_entity_branches`](ubuntu/serenedb/serene_ask.py:3169) `3169–3200` len=32
- [`_rrf_corpus_branch`](ubuntu/serenedb/serene_ask.py:3203) `3203–3210` len=8
- [`_fused_sql_rrf`](ubuntu/serenedb/serene_ask.py:3213) `3213–3218` len=6
- [`_fused_python_rrf`](ubuntu/serenedb/serene_ask.py:3221) `3221–3237` len=17
- [`_fused_candidates`](ubuntu/serenedb/serene_ask.py:3240) `3240–3291` len=52
- [`near_tables`](ubuntu/serenedb/serene_ask.py:3294) `3294–3332` len=39
- [`rows_of`](ubuntu/serenedb/serene_ask.py:3335) `3335–3367` len=33
- [`signal_terms`](ubuntu/serenedb/serene_ask.py:3402) `3402–3435` len=34
- [`clarify_text`](ubuntu/serenedb/serene_ask.py:3448) `3448–3464` len=17
- [`refuse_text`](ubuntu/serenedb/serene_ask.py:3476) `3476–3498` len=23
- [`rerank`](ubuntu/serenedb/serene_ask.py:3501) `3501–3556` len=56
- [`_resolver_psql`](ubuntu/serenedb/serene_ask.py:3559) `3559–3577` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/serene_ask.py:3584) `3584–3628` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/serene_ask.py:3631) `3631–3652` len=22
- [`resolve_values`](ubuntu/serenedb/serene_ask.py:3657) `3657–3714` len=58
- [`_ngrams`](ubuntu/serenedb/serene_ask.py:3717) `3717–3721` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`, `signal_terms`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/serene_ask.py:3724`](ubuntu/serenedb/serene_ask.py:3724)–`3967`.

Функций: 4. Входящие зоны: 07, 09, 16, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/serene_ask.py:3724) `3724–3734` len=11
- [`measures_of`](ubuntu/serenedb/serene_ask.py:3855) `3855–3868` len=14
- [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3871) `3871–3880` len=10
- [`totals_of`](ubuntu/serenedb/serene_ask.py:3883) `3883–3926` len=44

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 09. fork-detector — Детектор развилки

Якорь: `_measures_by_src`, end `_class_label_lookup`. Участок: [`ubuntu/serenedb/serene_ask.py:3968`](ubuntu/serenedb/serene_ask.py:3968)–`4748`.

Функций: 32. Входящие зоны: 05, 11, 13, 20. Исходящие зоны: 01, 03, 04, 08, 14, 15, 16, 17, 18.

Функции:

- [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3968) `3968–3989` len=22
- [`_aliases_by_src`](ubuntu/serenedb/serene_ask.py:3992) `3992–4008` len=17
- [`_fork_headline_doc_measures`](ubuntu/serenedb/serene_ask.py:4011) `4011–4013` len=3
- [`_fork_word_names_measure`](ubuntu/serenedb/serene_ask.py:4016) `4016–4029` len=14
- [`_fork_sum_headline_pool`](ubuntu/serenedb/serene_ask.py:4032) `4032–4042` len=11
- [`_fork_relevant`](ubuntu/serenedb/serene_ask.py:4045) `4045–4091` len=47
- [`_fork_relevant._sum_fallback`](ubuntu/serenedb/serene_ask.py:4062) `4062–4064` len=3 (влож.)
- [`_fork_relevant._with_doc_hdr`](ubuntu/serenedb/serene_ask.py:4072) `4072–4079` len=8 (влож.)
- [`_fork_pool_excluded`](ubuntu/serenedb/serene_ask.py:4094) `4094–4098` len=5
- [`fork_scan`](ubuntu/serenedb/serene_ask.py:4101) `4101–4175` len=75
- [`fork_scan_readings`](ubuntu/serenedb/serene_ask.py:4178) `4178–4220` len=43
- [`fork_classes_windowed`](ubuntu/serenedb/serene_ask.py:4223) `4223–4252` len=30
- [`fork_detector_scan`](ubuntu/serenedb/serene_ask.py:4255) `4255–4292` len=38
- [`_window_tuple_from_period`](ubuntu/serenedb/serene_ask.py:4295) `4295–4306` len=12
- [`_fork_atom_equiv_fp`](ubuntu/serenedb/serene_ask.py:4309) `4309–4338` len=30
- [`_fork_fp_diag`](ubuntu/serenedb/serene_ask.py:4341) `4341–4350` len=10
- [`fork_classes`](ubuntu/serenedb/serene_ask.py:4353) `4353–4372` len=20
- [`fork_key_of`](ubuntu/serenedb/serene_ask.py:4375) `4375–4384` len=10
- [`_window_fp_base`](ubuntu/serenedb/serene_ask.py:4387) `4387–4391` len=5
- [`_fork_key_for_period`](ubuntu/serenedb/serene_ask.py:4394) `4394–4404` len=11
- [`_fork_day_basis_groups`](ubuntu/serenedb/serene_ask.py:4407) `4407–4424` len=18
- [`_fork_log_day_basis`](ubuntu/serenedb/serene_ask.py:4427) `4427–4444` len=18
- [`_fork_log`](ubuntu/serenedb/serene_ask.py:4447) `4447–4484` len=38
- [`fork_labels_of`](ubuntu/serenedb/serene_ask.py:4487) `4487–4506` len=20
- [`fork_labels_covering`](ubuntu/serenedb/serene_ask.py:4511) `4511–4538` len=28
- [`fork_label_siblings`](ubuntu/serenedb/serene_ask.py:4541) `4541–4548` len=8
- [`_fork_answering_sums`](ubuntu/serenedb/serene_ask.py:4551) `4551–4572` len=22
- [`_fork_headline_measure`](ubuntu/serenedb/serene_ask.py:4575) `4575–4642` len=68
- [`_fork_headline_measure._pick_sum_headline`](ubuntu/serenedb/serene_ask.py:4595) `4595–4608` len=14 (влож.)
- [`_fork_atom_of`](ubuntu/serenedb/serene_ask.py:4645) `4645–4704` len=60
- [`_class_branch_label`](ubuntu/serenedb/serene_ask.py:4707) `4707–4713` len=7
- [`_class_label_lookup`](ubuntu/serenedb/serene_ask.py:4716) `4716–4746` len=31

Зовут снаружи зоны: `_aliases_by_src`, `_class_label_lookup`, `_fork_atom_of`, `_fork_fp_diag`, `_fork_log`, `_fork_pool_excluded`, `_fork_relevant`, `_fork_sum_headline_pool`, `_measures_by_src`, `fork_detector_scan`, `fork_key_of`, `fork_labels_covering`, `fork_labels_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `prefer_entity_for_rank`. Участок: [`ubuntu/serenedb/serene_ask.py:4749`](ubuntu/serenedb/serene_ask.py:4749)–`5233`.

Функций: 15. Входящие зоны: 05, 11, 12, 20. Исходящие зоны: 01, 07, 11, 14, 15, 17, 18.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4749) `4749–4766` len=18
- [`question_wants_breakdown`](ubuntu/serenedb/serene_ask.py:4769) `4769–4781` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/serene_ask.py:4784) `4784–4802` len=19
- [`rank_question_text`](ubuntu/serenedb/serene_ask.py:4807) `4807–4825` len=19
- [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4828) `4828–4841` len=14
- [`rank_leader_answer_text`](ubuntu/serenedb/serene_ask.py:4846) `4846–4866` len=21
- [`rank_axis_label_rows`](ubuntu/serenedb/serene_ask.py:4884) `4884–4907` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/serene_ask.py:4910) `4910–4921` len=12
- [`rank_axis_pick`](ubuntu/serenedb/serene_ask.py:4924) `4924–4970` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/serene_ask.py:4973) `4973–5035` len=63
- [`rank_product_axis_col`](ubuntu/serenedb/serene_ask.py:5038) `5038–5041` len=4
- [`rank_leader_atom`](ubuntu/serenedb/serene_ask.py:5044) `5044–5075` len=32
- [`rank_deterministic_answer`](ubuntu/serenedb/serene_ask.py:5078) `5078–5156` len=79
- [`rank_gate_fallback_answer`](ubuntu/serenedb/serene_ask.py:5159) `5159–5165` len=7
- [`prefer_entity_for_rank`](ubuntu/serenedb/serene_ask.py:5168) `5168–5231` len=64

Зовут снаружи зоны: `count_question_skips_axis`, `prefer_entity_for_rank`, `rank_axes_rerank`, `rank_axis_resolve`, `rank_deterministic_answer`, `rank_gate_fallback_answer`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `period_zero_why_question`. Участок: [`ubuntu/serenedb/serene_ask.py:5234`](ubuntu/serenedb/serene_ask.py:5234)–`5951`.

Функций: 27. Входящие зоны: 05, 10, 18, 20. Исходящие зоны: 01, 05, 09, 10, 12, 14, 17.

Функции:

- [`sales_sum_intent`](ubuntu/serenedb/serene_ask.py:5234) `5234–5262` len=29
- [`_sales_register_score`](ubuntu/serenedb/serene_ask.py:5265) `5265–5280` len=16
- [`sales_lift_possible`](ubuntu/serenedb/serene_ask.py:5283) `5283–5327` len=45
- [`sales_rank_engaged`](ubuntu/serenedb/serene_ask.py:5330) `5330–5357` len=28
- [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5361) `5361–5393` len=33
- [`rank_groups_answer_text`](ubuntu/serenedb/serene_ask.py:5396) `5396–5424` len=29
- [`prefer_entity_for_sales`](ubuntu/serenedb/serene_ask.py:5427) `5427–5530` len=104
- [`sales_canon_src`](ubuntu/serenedb/serene_ask.py:5533) `5533–5545` len=13
- [`sales_money_measure`](ubuntu/serenedb/serene_ask.py:5548) `5548–5567` len=20
- [`sales_qty_measure`](ubuntu/serenedb/serene_ask.py:5571) `5571–5581` len=11
- [`_alias_role_in_question`](ubuntu/serenedb/serene_ask.py:5584) `5584–5603` len=20
- [`_sales_product_rank_qty`](ubuntu/serenedb/serene_ask.py:5606) `5606–5625` len=20
- [`sales_rank_product_axis`](ubuntu/serenedb/serene_ask.py:5628) `5628–5672` len=45
- [`sales_rank_resolve_measure`](ubuntu/serenedb/serene_ask.py:5675) `5675–5721` len=47
- [`sales_rank_canon_measure`](ubuntu/serenedb/serene_ask.py:5724) `5724–5755` len=32
- [`sales_force_money_measure`](ubuntu/serenedb/serene_ask.py:5758) `5758–5780` len=23
- [`sales_canon_force_pool`](ubuntu/serenedb/serene_ask.py:5783) `5783–5791` len=9
- [`sales_canon_engaged`](ubuntu/serenedb/serene_ask.py:5794) `5794–5811` len=18
- [`_zero_period_not_missing`](ubuntu/serenedb/serene_ask.py:5814) `5814–5821` len=8
- [`sales_ticket_hatch`](ubuntu/serenedb/serene_ask.py:5824) `5824–5830` len=7
- [`sales_noncanon_focus`](ubuntu/serenedb/serene_ask.py:5833) `5833–5841` len=9
- [`sales_refuse_sticky_focus`](ubuntu/serenedb/serene_ask.py:5844) `5844–5876` len=33
- [`_is_price_list_noise`](ubuntu/serenedb/serene_ask.py:5879) `5879–5883` len=5
- [`_is_product_catalog`](ubuntu/serenedb/serene_ask.py:5886) `5886–5892` len=7
- [`prefer_entity_for_catalog_count`](ubuntu/serenedb/serene_ask.py:5895) `5895–5925` len=31
- [`catalog_count_src`](ubuntu/serenedb/serene_ask.py:5928) `5928–5936` len=9
- [`period_zero_why_question`](ubuntu/serenedb/serene_ask.py:5939) `5939–5948` len=10

Зовут снаружи зоны: `_is_product_catalog`, `_sales_rank_top_n`, `_sales_register_score`, `_zero_period_not_missing`, `catalog_count_src`, `period_zero_why_question`, `prefer_entity_for_catalog_count`, `prefer_entity_for_sales`, `rank_groups_answer_text`, `sales_canon_engaged`, `sales_canon_force_pool`, `sales_canon_src`, `sales_force_money_measure`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_rank_engaged`, `sales_rank_resolve_measure`, `sales_refuse_sticky_focus`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `balance_bridge_clarify`. Участок: [`ubuntu/serenedb/serene_ask.py:5952`](ubuntu/serenedb/serene_ask.py:5952)–`6244`.

Функций: 17. Входящие зоны: 11, 13, 20. Исходящие зоны: 01, 02, 07, 10, 14, 20.

Функции:

- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/serene_ask.py:5952) `5952–5958` len=7
- [`_rank_wants_quantity`](ubuntu/serenedb/serene_ask.py:5961) `5961–5965` len=5
- [`rank_measure_hint`](ubuntu/serenedb/serene_ask.py:5968) `5968–5995` len=28
- [`balance_registers`](ubuntu/serenedb/serene_ask.py:6007) `6007–6020` len=14
- [`balance_map_rows`](ubuntu/serenedb/serene_ask.py:6023) `6023–6046` len=24
- [`balance_capable_sources`](ubuntu/serenedb/serene_ask.py:6049) `6049–6051` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/serene_ask.py:6054) `6054–6059` len=6
- [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6062) `6062–6067` len=6
- [`balance_registers_with_goods`](ubuntu/serenedb/serene_ask.py:6070) `6070–6083` len=14
- [`_stems_of_text`](ubuntu/serenedb/serene_ask.py:6086) `6086–6101` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/serene_ask.py:6104) `6104–6117` len=14
- [`stock_asks_named_product`](ubuntu/serenedb/serene_ask.py:6120) `6120–6145` len=26
- [`stock_asks_named_product._is_named_term`](ubuntu/serenedb/serene_ask.py:6127) `6127–6136` len=10 (влож.)
- [`stock_balance_named_no_data`](ubuntu/serenedb/serene_ask.py:6148) `6148–6155` len=8
- [`_balance_map_by_src`](ubuntu/serenedb/serene_ask.py:6158) `6158–6164` len=7
- [`filter_balance_structural`](ubuntu/serenedb/serene_ask.py:6167) `6167–6206` len=40
- [`balance_bridge_clarify`](ubuntu/serenedb/serene_ask.py:6209) `6209–6242` len=34

Зовут снаружи зоны: `_rank_wants_quantity`, `balance_bridge_clarify`, `balance_capable_or_registers`, `balance_registers_with_goods`, `filter_balance_structural`, `grain_dec_from_axis_ticket`, `question_asks_stock_balance`, `rank_measure_hint`, `stock_asks_named_product`, `stock_balance_named_no_data`

## 13. fork-outcomes — Исходы развилки

Якорь: `stock_balance_is_sales_noise`, end `fork_outcome_c`. Участок: [`ubuntu/serenedb/serene_ask.py:6245`](ubuntu/serenedb/serene_ask.py:6245)–`6722`.

Функций: 17. Входящие зоны: 05, 20. Исходящие зоны: 01, 07, 09, 12, 14, 15, 20.

Функции:

- [`stock_balance_is_sales_noise`](ubuntu/serenedb/serene_ask.py:6245) `6245–6254` len=10
- [`filter_stock_balance_sales_noise`](ubuntu/serenedb/serene_ask.py:6257) `6257–6264` len=8
- [`_dedupe_fork_classes`](ubuntu/serenedb/serene_ask.py:6268) `6268–6289` len=22
- [`_class_window_form`](ubuntu/serenedb/serene_ask.py:6296) `6296–6302` len=7
- [`_class_day_basis`](ubuntu/serenedb/serene_ask.py:6305) `6305–6312` len=8
- [`fork_leader_class`](ubuntu/serenedb/serene_ask.py:6315) `6315–6361` len=47
- [`ordered_fork_classes`](ubuntu/serenedb/serene_ask.py:6364) `6364–6382` len=19
- [`_fork_applicable_classes`](ubuntu/serenedb/serene_ask.py:6385) `6385–6388` len=4
- [`resolve_fork_outcome`](ubuntu/serenedb/serene_ask.py:6391) `6391–6440` len=50
- [`_fork_figures_of`](ubuntu/serenedb/serene_ask.py:6443) `6443–6457` len=15
- [`fork_outcome_a`](ubuntu/serenedb/serene_ask.py:6460) `6460–6480` len=21
- [`fork_outcome_unique`](ubuntu/serenedb/serene_ask.py:6484) `6484–6509` len=26
- [`_rivals_figures_empty`](ubuntu/serenedb/serene_ask.py:6512) `6512–6530` len=19
- [`prefer_mute_computed_over_clarify`](ubuntu/serenedb/serene_ask.py:6533) `6533–6561` len=29
- [`atom_terminal_gate_text`](ubuntu/serenedb/serene_ask.py:6564) `6564–6574` len=11
- [`fork_outcome_b`](ubuntu/serenedb/serene_ask.py:6578) `6578–6627` len=50
- [`fork_outcome_c`](ubuntu/serenedb/serene_ask.py:6630) `6630–6720` len=91

Зовут снаружи зоны: `_fork_figures_of`, `atom_terminal_gate_text`, `filter_stock_balance_sales_noise`, `fork_outcome_a`, `fork_outcome_b`, `fork_outcome_c`, `fork_outcome_unique`, `prefer_mute_computed_over_clarify`, `resolve_fork_outcome`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `guards_skip_for_choice`. Участок: [`ubuntu/serenedb/serene_ask.py:6723`](ubuntu/serenedb/serene_ask.py:6723)–`7421`.

Функций: 35. Входящие зоны: 09, 10, 11, 12, 13, 15, 16, 18, 20. Исходящие зоны: 01, 02, 20.

Функции:

- [`_alias_parts`](ubuntu/serenedb/serene_ask.py:6723) `6723–6727` len=5
- [`_word_hits_text`](ubuntu/serenedb/serene_ask.py:6730) `6730–6734` len=5
- [`split_ident`](ubuntu/serenedb/serene_ask.py:6737) `6737–6741` len=5
- [`measure_choice`](ubuntu/serenedb/serene_ask.py:6744) `6744–6797` len=54
- [`measure_captions`](ubuntu/serenedb/serene_ask.py:6800) `6800–6818` len=19
- [`resolve_measure`](ubuntu/serenedb/serene_ask.py:6821) `6821–6853` len=33
- [`slot_measure_uncovered`](ubuntu/serenedb/serene_ask.py:6856) `6856–6864` len=9
- [`clarify_complete`](ubuntu/serenedb/serene_ask.py:6867) `6867–6883` len=17
- [`_slot_fp`](ubuntu/serenedb/serene_ask.py:6900) `6900–6918` len=19
- [`answers_diverge`](ubuntu/serenedb/serene_ask.py:6921) `6921–6954` len=34
- [`answers_src_conflict`](ubuntu/serenedb/serene_ask.py:6956) `6956–6971` len=16
- [`question_fingerprint`](ubuntu/serenedb/serene_ask.py:6986) `6986–6989` len=4
- [`db_fingerprint`](ubuntu/serenedb/serene_ask.py:6992) `6992–7006` len=15
- [`options_version`](ubuntu/serenedb/serene_ask.py:7009) `7009–7022` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/serene_ask.py:7025) `7025–7034` len=10
- [`_new_decision_id`](ubuntu/serenedb/serene_ask.py:7037) `7037–7039` len=3
- [`_purge_decisions`](ubuntu/serenedb/serene_ask.py:7042) `7042–7057` len=16
- [`_resolved_key`](ubuntu/serenedb/serene_ask.py:7060) `7060–7062` len=3
- [`peek_resolved`](ubuntu/serenedb/serene_ask.py:7065) `7065–7071` len=7
- [`accumulate_resolution`](ubuntu/serenedb/serene_ask.py:7074) `7074–7091` len=18
- [`issue_decision`](ubuntu/serenedb/serene_ask.py:7094) `7094–7130` len=37
- [`seal_clarify`](ubuntu/serenedb/serene_ask.py:7133) `7133–7185` len=53
- [`consume_decision`](ubuntu/serenedb/serene_ask.py:7188) `7188–7215` len=28
- [`peek_decision`](ubuntu/serenedb/serene_ask.py:7218) `7218–7238` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/serene_ask.py:7241) `7241–7265` len=25
- [`reissue_clarify`](ubuntu/serenedb/serene_ask.py:7268) `7268–7286` len=19
- [`choice_error_response`](ubuntu/serenedb/serene_ask.py:7289) `7289–7307` len=19
- [`reset_decisions_for_tests`](ubuntu/serenedb/serene_ask.py:7310) `7310–7315` len=6
- [`attach_memory_shadow`](ubuntu/serenedb/serene_ask.py:7318) `7318–7329` len=12
- [`choice_proven`](ubuntu/serenedb/serene_ask.py:7332) `7332–7338` len=7
- [`choice_levels_proven`](ubuntu/serenedb/serene_ask.py:7341) `7341–7355` len=15
- [`measure_already_proven`](ubuntu/serenedb/serene_ask.py:7358) `7358–7362` len=5
- [`entity_choice_locked`](ubuntu/serenedb/serene_ask.py:7365) `7365–7367` len=3
- [`hold_settled_entity`](ubuntu/serenedb/serene_ask.py:7370) `7370–7404` len=35
- [`guards_skip_for_choice`](ubuntu/serenedb/serene_ask.py:7407) `7407–7419` len=13

Зовут снаружи зоны: `accumulate_resolution`, `answers_diverge`, `answers_src_conflict`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `guards_skip_for_choice`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `slot_measure_uncovered`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `stop2_active`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/serene_ask.py:7422`](ubuntu/serenedb/serene_ask.py:7422)–`7803`.

Функций: 14. Входящие зоны: 05, 09, 10, 13, 16, 20. Исходящие зоны: 01, 14, 17, 18.

Функции:

- [`stop2_active`](ubuntu/serenedb/serene_ask.py:7422) `7422–7432` len=11
- [`determined_answer_rivals`](ubuntu/serenedb/serene_ask.py:7435) `7435–7470` len=36
- [`determined_answer_rivals.family`](ubuntu/serenedb/serene_ask.py:7446) `7446–7447` len=2 (влож.)
- [`determined_answer_rivals.add`](ubuntu/serenedb/serene_ask.py:7452) `7452–7455` len=4 (влож.)
- [`answer_money`](ubuntu/serenedb/serene_ask.py:7475) `7475–7484` len=10
- [`answer_slot_mode`](ubuntu/serenedb/serene_ask.py:7487) `7487–7513` len=27
- [`compose_slot_values`](ubuntu/serenedb/serene_ask.py:7516) `7516–7587` len=72
- [`atom_operation`](ubuntu/serenedb/serene_ask.py:7602) `7602–7616` len=15
- [`_atom_exact_value`](ubuntu/serenedb/serene_ask.py:7619) `7619–7638` len=20
- [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7641) `7641–7684` len=44
- [`atom_from_agg`](ubuntu/serenedb/serene_ask.py:7687) `7687–7728` len=42
- [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7731) `7731–7769` len=39
- [`fill_atom_pairs`](ubuntu/serenedb/serene_ask.py:7772) `7772–7801` len=30
- [`fill_atom_pairs.one`](ubuntu/serenedb/serene_ask.py:7783) `7783–7799` len=17 (влож.)

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `build_answer_atom`, `compose_slot_values`, `determined_answer_rivals`, `fill_atom_pairs`, `fill_atom_pairs.one`, `render_atom_pair`, `stop2_active`

## 16. veto-pick-entity — Вето и выбор сущности

Якорь: `pair_slots_only`, end `pick_entity`. Участок: [`ubuntu/serenedb/serene_ask.py:7804`](ubuntu/serenedb/serene_ask.py:7804)–`8437`.

Функций: 22. Входящие зоны: 09, 18, 20. Исходящие зоны: 01, 02, 07, 08, 14, 15, 18, 20.

Функции:

- [`pair_slots_only`](ubuntu/serenedb/serene_ask.py:7804) `7804–7806` len=3
- [`atom_whitelist_labels`](ubuntu/serenedb/serene_ask.py:7809) `7809–7818` len=10
- [`atom_whitelist_numbers`](ubuntu/serenedb/serene_ask.py:7821) `7821–7837` len=17
- [`arbiter_figures`](ubuntu/serenedb/serene_ask.py:7840) `7840–7846` len=7
- [`alias_supported`](ubuntu/serenedb/serene_ask.py:7849) `7849–7917` len=69
- [`not_for_excludes`](ubuntu/serenedb/serene_ask.py:7920) `7920–7955` len=36
- [`pair_unanswered`](ubuntu/serenedb/serene_ask.py:7958) `7958–7968` len=11
- [`single_is_rival`](ubuntu/serenedb/serene_ask.py:7971) `7971–7979` len=9
- [`veto_top_without`](ubuntu/serenedb/serene_ask.py:7982) `7982–7990` len=9
- [`figures_numbers`](ubuntu/serenedb/serene_ask.py:7993) `7993–8010` len=18
- [`same_number`](ubuntu/serenedb/serene_ask.py:8013) `8013–8037` len=25
- [`unresolved_quantity`](ubuntu/serenedb/serene_ask.py:8039) `8039–8059` len=21
- [`mute_measure_blocks`](ubuntu/serenedb/serene_ask.py:8062) `8062–8077` len=16
- [`measure_row_all_zero`](ubuntu/serenedb/serene_ask.py:8080) `8080–8087` len=8
- [`alive_measure_names`](ubuntu/serenedb/serene_ask.py:8090) `8090–8092` len=3
- [`filter_dead_measure_alts`](ubuntu/serenedb/serene_ask.py:8095) `8095–8103` len=9
- [`measure_asked_explicitly`](ubuntu/serenedb/serene_ask.py:8106) `8106–8114` len=9
- [`format_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8117) `8117–8135` len=19
- [`build_measure_empty_pivot`](ubuntu/serenedb/serene_ask.py:8138) `8138–8191` len=54
- [`measure_ambiguous`](ubuntu/serenedb/serene_ask.py:8194) `8194–8210` len=17
- [`pick_measure`](ubuntu/serenedb/serene_ask.py:8213) `8213–8258` len=46
- [`pick_entity`](ubuntu/serenedb/serene_ask.py:8261) `8261–8435` len=175

Зовут снаружи зоны: `alias_supported`, `arbiter_figures`, `build_measure_empty_pivot`, `figures_numbers`, `filter_dead_measure_alts`, `measure_ambiguous`, `measure_asked_explicitly`, `measure_row_all_zero`, `mute_measure_blocks`, `not_for_excludes`, `pair_slots_only`, `pair_unanswered`, `pick_entity`, `pick_measure`, `same_number`, `single_is_rival`, `unresolved_quantity`, `veto_top_without`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/serene_ask.py:8438`](ubuntu/serenedb/serene_ask.py:8438)–`8941`.

Функций: 16. Входящие зоны: 05, 07, 08, 09, 10, 11, 15, 18, 19, 20. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/serene_ask.py:8438) `8438–8439` len=2
- [`_num`](ubuntu/serenedb/serene_ask.py:8442) `8442–8446` len=5
- [`_numN`](ubuntu/serenedb/serene_ask.py:8449) `8449–8462` len=14
- [`aggregate`](ubuntu/serenedb/serene_ask.py:8465) `8465–8580` len=116
- [`src_is_child`](ubuntu/serenedb/serene_ask.py:8584) `8584–8593` len=10
- [`refcols_of`](ubuntu/serenedb/serene_ask.py:8596) `8596–8610` len=15
- [`holders_of_target`](ubuntu/serenedb/serene_ask.py:8613) `8613–8630` len=18
- [`measures_of_many`](ubuntu/serenedb/serene_ask.py:8633) `8633–8648` len=16
- [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8651) `8651–8682` len=32
- [`kind_axis_rerank`](ubuntu/serenedb/serene_ask.py:8685) `8685–8708` len=24
- [`term_ref_owners`](ubuntu/serenedb/serene_ask.py:8711) `8711–8737` len=27
- [`term_axis_hits`](ubuntu/serenedb/serene_ask.py:8740) `8740–8779` len=40
- [`resolve_member_names`](ubuntu/serenedb/serene_ask.py:8782) `8782–8809` len=28
- [`_group_leader`](ubuntu/serenedb/serene_ask.py:8812) `8812–8821` len=10
- [`_group_fold`](ubuntu/serenedb/serene_ask.py:8824) `8824–8830` len=7
- [`aggregate_groups`](ubuntu/serenedb/serene_ask.py:8833) `8833–8939` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `holders_of_target`, `kind_axis_hits`, `kind_axis_rerank`, `measures_of_many`, `refcols_of`, `src_is_child`, `term_axis_hits`, `term_ref_owners`

## 18. compose — Формулировка

Якорь: `merge_period2_groups`, end `compose`. Участок: [`ubuntu/serenedb/serene_ask.py:8942`](ubuntu/serenedb/serene_ask.py:8942)–`9830`.

Функций: 23. Входящие зоны: 03, 09, 10, 15, 16, 20. Исходящие зоны: 01, 03, 08, 11, 14, 16, 17, 19, 20.

Функции:

- [`merge_period2_groups`](ubuntu/serenedb/serene_ask.py:8942) `8942–8957` len=16
- [`axis_clarify_options`](ubuntu/serenedb/serene_ask.py:8960) `8960–8984` len=25
- [`_split_answer`](ubuntu/serenedb/serene_ask.py:9031) `9031–9061` len=31
- [`_group_value_by_name`](ubuntu/serenedb/serene_ask.py:9081) `9081–9097` len=17
- [`_fill_figures`](ubuntu/serenedb/serene_ask.py:9100) `9100–9221` len=122
- [`_fill_figures.one`](ubuntu/serenedb/serene_ask.py:9178) `9178–9219` len=42 (влож.)
- [`ensure_n_groups_named`](ubuntu/serenedb/serene_ask.py:9224) `9224–9242` len=19
- [`ensure_count_named`](ubuntu/serenedb/serene_ask.py:9245) `9245–9263` len=19
- [`_measure_dimension`](ubuntu/serenedb/serene_ask.py:9268) `9268–9286` len=19
- [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9289) `9289–9307` len=19
- [`postprocess_money_answer_text`](ubuntu/serenedb/serene_ask.py:9310) `9310–9318` len=9
- [`build_answer_passport`](ubuntu/serenedb/serene_ask.py:9320) `9320–9380` len=61
- [`build_answer_passport._add`](ubuntu/serenedb/serene_ask.py:9335) `9335–9341` len=7 (влож.)
- [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9383) `9383–9392` len=10
- [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9395) `9395–9404` len=10
- [`_table_label`](ubuntu/serenedb/serene_ask.py:9407) `9407–9418` len=12
- [`_passport_axis_label`](ubuntu/serenedb/serene_ask.py:9421) `9421–9432` len=12
- [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9435) `9435–9442` len=8
- [`formulation_flaws`](ubuntu/serenedb/serene_ask.py:9445) `9445–9472` len=28
- [`copied_figures`](ubuntu/serenedb/serene_ask.py:9475) `9475–9542` len=68
- [`_filled_ask`](ubuntu/serenedb/serene_ask.py:9545) `9545–9563` len=19
- [`_ask_back`](ubuntu/serenedb/serene_ask.py:9566) `9566–9580` len=15
- [`compose`](ubuntu/serenedb/serene_ask.py:9583) `9583–9805` len=223

Зовут снаружи зоны: `_ask_back`, `_fill_figures`, `_fill_figures.one`, `_filled_ask`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `build_answer_passport._add`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `merge_period2_groups`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/serene_ask.py:9831`](ubuntu/serenedb/serene_ask.py:9831)–`10219`.

Функций: 14. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/serene_ask.py:9831) `9831–9871` len=41
- [`_plausible`](ubuntu/serenedb/serene_ask.py:9874) `9874–9883` len=10
- [`_dates`](ubuntu/serenedb/serene_ask.py:9886) `9886–9906` len=21
- [`_date2_readings`](ubuntu/serenedb/serene_ask.py:9909) `9909–9920` len=12
- [`_date_spans`](ubuntu/serenedb/serene_ask.py:9923) `9923–9943` len=21
- [`_tokens`](ubuntu/serenedb/serene_ask.py:9946) `9946–9976` len=31
- [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9979) `9979–9984` len=6
- [`check_claims`](ubuntu/serenedb/serene_ask.py:9990) `9990–10023` len=34
- [`claims_in_text`](ubuntu/serenedb/serene_ask.py:10029) `10029–10068` len=40
- [`prompt_leak`](ubuntu/serenedb/serene_ask.py:10071) `10071–10090` len=20
- [`asked_figure_missing`](ubuntu/serenedb/serene_ask.py:10093) `10093–10167` len=75
- [`stale_note`](ubuntu/serenedb/serene_ask.py:10170) `10170–10185` len=16
- [`_threshold_values`](ubuntu/serenedb/serene_ask.py:10188) `10188–10192` len=5
- [`_filter_values`](ubuntu/serenedb/serene_ask.py:10195) `10195–10217` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/serene_ask.py:10220`](ubuntu/serenedb/serene_ask.py:10220)–`15913`.

Функций: 95. Входящие зоны: 03, 12, 13, 14, 16, 18. Исходящие зоны: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19.

Функции:

- [`_filter_dates`](ubuntu/serenedb/serene_ask.py:10220) `10220–10229` len=10
- [`without_list_markers`](ubuntu/serenedb/serene_ask.py:10240) `10240–10254` len=15
- [`rows_seen`](ubuntu/serenedb/serene_ask.py:10257) `10257–10281` len=25
- [`gate`](ubuntu/serenedb/serene_ask.py:10284) `10284–10445` len=162
- [`gate.allow`](ubuntu/serenedb/serene_ask.py:10303) `10303–10321` len=19 (влож.)
- [`count_figures`](ubuntu/serenedb/serene_ask.py:10448) `10448–10462` len=15
- [`gate_out`](ubuntu/serenedb/serene_ask.py:10465) `10465–10483` len=19
- [`_opt_values`](ubuntu/serenedb/serene_ask.py:10486) `10486–10501` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/serene_ask.py:10504) `10504–10519` len=16
- [`clarify_choice_line`](ubuntu/serenedb/serene_ask.py:10522) `10522–10529` len=8
- [`format_clarify_options`](ubuntu/serenedb/serene_ask.py:10532) `10532–10540` len=9
- [`clarify_say`](ubuntu/serenedb/serene_ask.py:10543) `10543–10565` len=23
- [`_entity_counts_objects`](ubuntu/serenedb/serene_ask.py:10578) `10578–10595` len=18
- [`_vitrina_objects`](ubuntu/serenedb/serene_ask.py:10598) `10598–10611` len=14
- [`_coverage_of`](ubuntu/serenedb/serene_ask.py:10622) `10622–10683` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/serene_ask.py:10710) `10710–10745` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/serene_ask.py:10748) `10748–10750` len=3
- [`_measure_health_gap`](ubuntu/serenedb/serene_ask.py:10753) `10753–10768` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/serene_ask.py:10772) `10772–10786` len=15
- [`_classify_health_gap`](ubuntu/serenedb/serene_ask.py:10789) `10789–10819` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/serene_ask.py:10822) `10822–10827` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/serene_ask.py:10830) `10830–10879` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/serene_ask.py:10882) `10882–10894` len=13
- [`_health_gap`](ubuntu/serenedb/serene_ask.py:10897) `10897–10909` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/serene_ask.py:10912) `10912–10920` len=9
- [`_coverage_answer`](ubuntu/serenedb/serene_ask.py:10944) `10944–11028` len=85
- [`kind_word`](ubuntu/serenedb/serene_ask.py:11085) `11085–11088` len=4
- [`label_with_kind`](ubuntu/serenedb/serene_ask.py:11091) `11091–11102` len=12
- [`ambiguous_labels`](ubuntu/serenedb/serene_ask.py:11108) `11108–11130` len=23
- [`disambiguate_labels`](ubuntu/serenedb/serene_ask.py:11133) `11133–11150` len=18
- [`opts_hints`](ubuntu/serenedb/serene_ask.py:11162) `11162–11221` len=60
- [`mk_opts`](ubuntu/serenedb/serene_ask.py:11224) `11224–11251` len=28
- [`live_src_counts`](ubuntu/serenedb/serene_ask.py:11254) `11254–11286` len=33
- [`empty_after_period_action`](ubuntu/serenedb/serene_ask.py:11289) `11289–11304` len=16
- [`period_empty_outcome`](ubuntu/serenedb/serene_ask.py:11307) `11307–11331` len=25
- [`_period_day_label`](ubuntu/serenedb/serene_ask.py:11334) `11334–11349` len=16
- [`_period_day_label.one`](ubuntu/serenedb/serene_ask.py:11336) `11336–11341` len=6 (влож.)
- [`sales_period_empty`](ubuntu/serenedb/serene_ask.py:11354) `11354–11369` len=16
- [`sales_period_window_active`](ubuntu/serenedb/serene_ask.py:11372) `11372–11384` len=13
- [`sales_fork_canon_empty_src`](ubuntu/serenedb/serene_ask.py:11387) `11387–11412` len=26
- [`try_sales_fork_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11415) `11415–11440` len=26
- [`sales_fork_blocks_clarify`](ubuntu/serenedb/serene_ask.py:11443) `11443–11454` len=12
- [`dates_outside_period_filter`](ubuntu/serenedb/serene_ask.py:11457) `11457–11471` len=15
- [`format_period_empty_text`](ubuntu/serenedb/serene_ask.py:11474) `11474–11522` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/serene_ask.py:11525) `11525–11577` len=53
- [`drop_period_preds`](ubuntu/serenedb/serene_ask.py:11580) `11580–11586` len=7
- [`_term_stems`](ubuntu/serenedb/serene_ask.py:11589) `11589–11604` len=16
- [`_src_covers_term_stems`](ubuntu/serenedb/serene_ask.py:11607) `11607–11619` len=13
- [`align_picked_to_terms`](ubuntu/serenedb/serene_ask.py:11622) `11622–11649` len=28
- [`resolve_focus`](ubuntu/serenedb/serene_ask.py:11652) `11652–11786` len=135
- [`_word_hits_measure`](ubuntu/serenedb/serene_ask.py:11790) `11790–11802` len=13
- [`axis_focus_plan`](ubuntu/serenedb/serene_ask.py:11805) `11805–11873` len=69
- [`_day_ord`](ubuntu/serenedb/serene_ask.py:11876) `11876–11881` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/serene_ask.py:11884) `11884–11908` len=25
- [`period_slot_for_inherit`](ubuntu/serenedb/serene_ask.py:11911) `11911–11922` len=12
- [`apply_prior_period`](ubuntu/serenedb/serene_ask.py:11925) `11925–11953` len=29
- [`answer`](ubuntu/serenedb/serene_ask.py:11956) `11956–15061` len=3106
- [`answer.шаг`](ubuntu/serenedb/serene_ask.py:11992) `11992–11997` len=6 (влож.)
- [`answer._family`](ubuntu/serenedb/serene_ask.py:13012) `13012–13013` len=2 (влож.)
- [`answer._alias_verdict`](ubuntu/serenedb/serene_ask.py:13015) `13015–13168` len=154 (влож.)
- [`answer._alias_verdict._место`](ubuntu/serenedb/serene_ask.py:13126) `13126–13130` len=5 (влож.)
- [`answer._alias_verdict._probe`](ubuntu/serenedb/serene_ask.py:13132) `13132–13143` len=12 (влож.)
- [`answer._alias_clarify`](ubuntu/serenedb/serene_ask.py:13170) `13170–13198` len=29 (влож.)
- [`answer._checked`](ubuntu/serenedb/serene_ask.py:13468) `13468–13484` len=17 (влож.)
- [`question_facts`](ubuntu/serenedb/serene_ask.py:15084) `15084–15110` len=27
- [`entity_has_dates`](ubuntu/serenedb/serene_ask.py:15113) `15113–15134` len=22
- [`_gate_need`](ubuntu/serenedb/serene_ask.py:15137) `15137–15150` len=14
- [`_need_clarify`](ubuntu/serenedb/serene_ask.py:15153) `15153–15169` len=17
- [`_journal_keep_n`](ubuntu/serenedb/serene_ask.py:15172) `15172–15186` len=15
- [`_journal_code_md5`](ubuntu/serenedb/serene_ask.py:15189) `15189–15196` len=8
- [`_journal_build_ts`](ubuntu/serenedb/serene_ask.py:15199) `15199–15210` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/serene_ask.py:15213) `15213–15226` len=14
- [`_journal_sql_int`](ubuntu/serenedb/serene_ask.py:15229) `15229–15235` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/serene_ask.py:15238) `15238–15241` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/serene_ask.py:15244) `15244–15272` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/serene_ask.py:15275) `15275–15297` len=23
- [`_journal_doubt`](ubuntu/serenedb/serene_ask.py:15300) `15300–15309` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/serene_ask.py:15312) `15312–15325` len=14
- [`_journal_intent`](ubuntu/serenedb/serene_ask.py:15328) `15328–15330` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/serene_ask.py:15333) `15333–15341` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/serene_ask.py:15344) `15344–15363` len=20
- [`_ask_journal_write`](ubuntu/serenedb/serene_ask.py:15366) `15366–15480` len=115
- [`_ask_journal_write._insert_row`](ubuntu/serenedb/serene_ask.py:15410) `15410–15459` len=50 (влож.)
- [`_answer_checked_core`](ubuntu/serenedb/serene_ask.py:15484) `15484–15526` len=43
- [`_answer_checked_core.plain`](ubuntu/serenedb/serene_ask.py:15488) `15488–15490` len=3 (влож.)
- [`_try_memory_apply`](ubuntu/serenedb/serene_ask.py:15531) `15531–15556` len=26
- [`answer_checked`](ubuntu/serenedb/serene_ask.py:15558) `15558–15639` len=82
- [`_build_ask_scope`](ubuntu/serenedb/serene_ask.py:15644) `15644–15685` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/serene_ask.py:15688) `15688–15707` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/serene_ask.py:15710) `15710–15721` len=12
- [`Handler.log_message`](ubuntu/serenedb/serene_ask.py:15727) `15727–15728` len=2 (влож.)
- [`Handler._send`](ubuntu/serenedb/serene_ask.py:15730) `15730–15736` len=7 (влож.)
- [`Handler.do_GET`](ubuntu/serenedb/serene_ask.py:15738) `15738–15804` len=67 (влож.)
- [`Handler.do_POST`](ubuntu/serenedb/serene_ask.py:15806) `15806–15897` len=92 (влож.)
- [`main`](ubuntu/serenedb/serene_ask.py:15900) `15900–15909` len=10

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
| [`measure_choice`](ubuntu/serenedb/serene_ask.py:6744) | 14 | 5 | 09, 11, 12, 16, 20 |
| [`_num`](ubuntu/serenedb/serene_ask.py:8442) | 17 | 5 | 05, 08, 09, 18, 20 |
| [`_fmt_human`](ubuntu/serenedb/serene_ask.py:470) | 01 | 4 | 10, 11, 16, 18 |
| [`period_preds`](ubuntu/serenedb/serene_ask.py:1395) | 03 | 4 | 05, 06, 09, 20 |
| [`rerank`](ubuntu/serenedb/serene_ask.py:3501) | 07 | 4 | 10, 16, 17, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/serene_ask.py:3871) | 08 | 4 | 09, 16, 18, 20 |
| [`rank_intent_from`](ubuntu/serenedb/serene_ask.py:4828) | 10 | 4 | 05, 11, 12, 20 |
| [`refcols_of`](ubuntu/serenedb/serene_ask.py:8596) | 17 | 4 | 05, 10, 11, 20 |
| [`meaning_candidates`](ubuntu/serenedb/serene_ask.py:3087) | 06 | 3 | 05, 17, 20 |
| [`refuse_text`](ubuntu/serenedb/serene_ask.py:3476) | 07 | 3 | 12, 13, 20 |
| [`measures_of`](ubuntu/serenedb/serene_ask.py:3855) | 08 | 3 | 16, 18, 20 |
| [`_measures_by_src`](ubuntu/serenedb/serene_ask.py:3968) | 09 | 3 | 05, 11, 20 |
| [`_sales_rank_top_n`](ubuntu/serenedb/serene_ask.py:5361) | 11 | 3 | 05, 10, 20 |
| [`question_asks_stock_balance`](ubuntu/serenedb/serene_ask.py:6062) | 12 | 3 | 11, 13, 20 |
| [`split_ident`](ubuntu/serenedb/serene_ask.py:6737) | 14 | 3 | 09, 13, 18 |
| [`measure_captions`](ubuntu/serenedb/serene_ask.py:6800) | 14 | 3 | 16, 18, 20 |
| [`build_answer_atom`](ubuntu/serenedb/serene_ask.py:7641) | 15 | 3 | 05, 09, 10 |
| [`render_atom_pair`](ubuntu/serenedb/serene_ask.py:7731) | 15 | 3 | 05, 13, 20 |
| [`kind_axis_hits`](ubuntu/serenedb/serene_ask.py:8651) | 17 | 3 | 10, 11, 20 |
| [`_group_leader`](ubuntu/serenedb/serene_ask.py:8812) | 17 | 3 | 10, 15, 19 |
| [`_unit_for_measure`](ubuntu/serenedb/serene_ask.py:9289) | 18 | 3 | 10, 15, 20 |
| [`ensure_answer_passport`](ubuntu/serenedb/serene_ask.py:9383) | 18 | 3 | 10, 16, 20 |
| [`measure_label_of`](ubuntu/serenedb/serene_ask.py:9395) | 18 | 3 | 09, 10, 20 |
| [`_passport_origin`](ubuntu/serenedb/serene_ask.py:9435) | 18 | 3 | 10, 16, 20 |
| [`_norm_numbers`](ubuntu/serenedb/serene_ask.py:9979) | 19 | 3 | 07, 18, 20 |

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
| `ASK_RESOLVE_NEAR` | [3580](ubuntu/serenedb/serene_ask.py:3580) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [3581](ubuntu/serenedb/serene_ask.py:3581) | "3" | `(модуль)` |
| `ASK_ALIAS_TOP` | [3740](ubuntu/serenedb/serene_ask.py:3740) | "8" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [3743](ubuntu/serenedb/serene_ask.py:3743) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [3748](ubuntu/serenedb/serene_ask.py:3748) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [3753](ubuntu/serenedb/serene_ask.py:3753) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [3756](ubuntu/serenedb/serene_ask.py:3756) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [3757](ubuntu/serenedb/serene_ask.py:3757) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [3762](ubuntu/serenedb/serene_ask.py:3762) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [3763](ubuntu/serenedb/serene_ask.py:3763) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_ALIAS_VETO` | [3776](ubuntu/serenedb/serene_ask.py:3776) | "1" | `(модуль)` |
| `ASK_PROBE` | [3783](ubuntu/serenedb/serene_ask.py:3783) | "0" | `(модуль)` |
| `ASK_SKIP_SERVICE_RIVALS` | [3787](ubuntu/serenedb/serene_ask.py:3787) | "1" | `(модуль)` |
| `ASK_ALIAS_BY_CONCEPTS` | [3799](ubuntu/serenedb/serene_ask.py:3799) | "0" | `(модуль)` |
| `ASK_VETO_NEEDS_RANK` | [3814](ubuntu/serenedb/serene_ask.py:3814) | "0" | `(модуль)` |
| `ASK_VETO_HEAD_WINS` | [3824](ubuntu/serenedb/serene_ask.py:3824) | "1" | `(модуль)` |
| `ASK_MEANING_TOP` | [3850](ubuntu/serenedb/serene_ask.py:3850) | "0" | `(модуль)` |
| `ASK_FORK_DETECT` | [3942](ubuntu/serenedb/serene_ask.py:3942) | "1" | `(модуль)` |
| `ASK_FORK_OUTCOMES` | [3943](ubuntu/serenedb/serene_ask.py:3943) | "1" | `(модуль)` |
| `ASK_JOURNAL` | [3946](ubuntu/serenedb/serene_ask.py:3946) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [3951](ubuntu/serenedb/serene_ask.py:3951) | "1" | `(модуль)` |
| `ASK_MEMORY_APPLY` | [3953](ubuntu/serenedb/serene_ask.py:3953) | "0" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [3964](ubuntu/serenedb/serene_ask.py:3964) | "600" | `(модуль)` |
| `ASK_RAW_FOCUS_TRUST` | [6977](ubuntu/serenedb/serene_ask.py:6977) | "0" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [6978](ubuntu/serenedb/serene_ask.py:6978) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [10697](ubuntu/serenedb/serene_ask.py:10697) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [10705](ubuntu/serenedb/serene_ask.py:10705) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [10706](ubuntu/serenedb/serene_ask.py:10706) | "search_idx" | `(модуль)` |
| `ASK_SIGNAL_DISAGREE` | [11034](ubuntu/serenedb/serene_ask.py:11034) | "1" | `(модуль)` |
| `ASK_REQUIRE_SUPPORT` | [11036](ubuntu/serenedb/serene_ask.py:11036) | "1" | `(модуль)` |
| `ASK_ARBITER_MAX` | [11039](ubuntu/serenedb/serene_ask.py:11039) | "3" | `(модуль)` |
| `ASK_ARBITER_DETECTS` | [11045](ubuntu/serenedb/serene_ask.py:11045) | "1" | `(модуль)` |
| `ASK_NOT_FOR` | [11047](ubuntu/serenedb/serene_ask.py:11047) | "1" | `(модуль)` |
| `ASK_STEM_DICT` | [11050](ubuntu/serenedb/serene_ask.py:11050) | "search_dict_stem" | `(модуль)` |
| `ASK_AMBIG_TTL` | [11053](ubuntu/serenedb/serene_ask.py:11053) | "300" | `(модуль)` |
| `ASK_ENOUGH` | [15076](ubuntu/serenedb/serene_ask.py:15076) | "1" | `(модуль)` |
| `ASK_SLOT_COVER` | [15078](ubuntu/serenedb/serene_ask.py:15078) | "0" | `(модуль)` |
| `EMBED_SECRET` | [289](ubuntu/serenedb/serene_ask.py:289) | — | `_embed_secret_name_from_env` |
| `EMBED_SECRETS` | [289](ubuntu/serenedb/serene_ask.py:289) | — | `_embed_secret_name_from_env` |
| `EMBED_PATH` | [305](ubuntu/serenedb/serene_ask.py:305) | "/v1/embeddings" | `_reload_embed_native_env` |
| `ASK_EMBED_NATIVE` | [306](ubuntu/serenedb/serene_ask.py:306) | "0" | `_reload_embed_native_env` |
| `EMBED_DIM` | [307](ubuntu/serenedb/serene_ask.py:307) | "1024" | `_reload_embed_native_env` |
| `EMBED_HOST` | [369](ubuntu/serenedb/serene_ask.py:369) | — | `_embed_host_base` |
| `ASK_JOURNAL_KEEP` | [15175](ubuntu/serenedb/serene_ask.py:15175) | — | `_journal_keep_n` |

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
- [`ubuntu/serenedb/serene_ask.py:2130`](ubuntu/serenedb/serene_ask.py:2130) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2164`](ubuntu/serenedb/serene_ask.py:2164) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/serene_ask.py:2381`](ubuntu/serenedb/serene_ask.py:2381) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/serene_ask.py:2611`](ubuntu/serenedb/serene_ask.py:2611) в `_fetch`
- [`ubuntu/serenedb/serene_ask.py:2683`](ubuntu/serenedb/serene_ask.py:2683) в `probe`
- [`ubuntu/serenedb/serene_ask.py:2786`](ubuntu/serenedb/serene_ask.py:2786) в `match_expr`
- [`ubuntu/serenedb/serene_ask.py:2825`](ubuntu/serenedb/serene_ask.py:2825) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2844`](ubuntu/serenedb/serene_ask.py:2844) в `children_by_parent`
- [`ubuntu/serenedb/serene_ask.py:2914`](ubuntu/serenedb/serene_ask.py:2914) в `partial_tables`
- [`ubuntu/serenedb/serene_ask.py:2946`](ubuntu/serenedb/serene_ask.py:2946) в `tables_of`
- [`ubuntu/serenedb/serene_ask.py:3016`](ubuntu/serenedb/serene_ask.py:3016) в `alias_hits`
- [`ubuntu/serenedb/serene_ask.py:3056`](ubuntu/serenedb/serene_ask.py:3056) в `card_hits`
- [`ubuntu/serenedb/serene_ask.py:3138`](ubuntu/serenedb/serene_ask.py:3138) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/serene_ask.py:3218`](ubuntu/serenedb/serene_ask.py:3218) в `_fused_sql_rrf`
- [`ubuntu/serenedb/serene_ask.py:3226`](ubuntu/serenedb/serene_ask.py:3226) в `_fused_python_rrf`
- [`ubuntu/serenedb/serene_ask.py:3327`](ubuntu/serenedb/serene_ask.py:3327) в `near_tables`
- [`ubuntu/serenedb/serene_ask.py:3363`](ubuntu/serenedb/serene_ask.py:3363) в `rows_of`
- [`ubuntu/serenedb/serene_ask.py:3417`](ubuntu/serenedb/serene_ask.py:3417) в `signal_terms`
- [`ubuntu/serenedb/serene_ask.py:3646`](ubuntu/serenedb/serene_ask.py:3646) в `_resolve_values_corpus`
- [`ubuntu/serenedb/serene_ask.py:3863`](ubuntu/serenedb/serene_ask.py:3863) в `measures_of`
- [`ubuntu/serenedb/serene_ask.py:3874`](ubuntu/serenedb/serene_ask.py:3874) в `measure_aliases_of`
- [`ubuntu/serenedb/serene_ask.py:3915`](ubuntu/serenedb/serene_ask.py:3915) в `totals_of`
- [`ubuntu/serenedb/serene_ask.py:3979`](ubuntu/serenedb/serene_ask.py:3979) в `_measures_by_src`
- [`ubuntu/serenedb/serene_ask.py:3998`](ubuntu/serenedb/serene_ask.py:3998) в `_aliases_by_src`
- [`ubuntu/serenedb/serene_ask.py:4136`](ubuntu/serenedb/serene_ask.py:4136) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4159`](ubuntu/serenedb/serene_ask.py:4159) в `fork_scan`
- [`ubuntu/serenedb/serene_ask.py:4436`](ubuntu/serenedb/serene_ask.py:4436) в `_fork_log_day_basis`
- [`ubuntu/serenedb/serene_ask.py:4476`](ubuntu/serenedb/serene_ask.py:4476) в `_fork_log`
- [`ubuntu/serenedb/serene_ask.py:4496`](ubuntu/serenedb/serene_ask.py:4496) в `fork_labels_of`
- [`ubuntu/serenedb/serene_ask.py:4521`](ubuntu/serenedb/serene_ask.py:4521) в `fork_labels_covering`
- [`ubuntu/serenedb/serene_ask.py:4893`](ubuntu/serenedb/serene_ask.py:4893) в `rank_axis_label_rows`
- [`ubuntu/serenedb/serene_ask.py:5181`](ubuntu/serenedb/serene_ask.py:5181) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5199`](ubuntu/serenedb/serene_ask.py:5199) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/serene_ask.py:5297`](ubuntu/serenedb/serene_ask.py:5297) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5321`](ubuntu/serenedb/serene_ask.py:5321) в `sales_lift_possible`
- [`ubuntu/serenedb/serene_ask.py:5445`](ubuntu/serenedb/serene_ask.py:5445) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5469`](ubuntu/serenedb/serene_ask.py:5469) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5501`](ubuntu/serenedb/serene_ask.py:5501) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5481`](ubuntu/serenedb/serene_ask.py:5481) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/serene_ask.py:5910`](ubuntu/serenedb/serene_ask.py:5910) в `prefer_entity_for_catalog_count`
- [`ubuntu/serenedb/serene_ask.py:6016`](ubuntu/serenedb/serene_ask.py:6016) в `balance_registers`
- [`ubuntu/serenedb/serene_ask.py:6034`](ubuntu/serenedb/serene_ask.py:6034) в `balance_map_rows`
- [`ubuntu/serenedb/serene_ask.py:6079`](ubuntu/serenedb/serene_ask.py:6079) в `balance_registers_with_goods`
- [`ubuntu/serenedb/serene_ask.py:6093`](ubuntu/serenedb/serene_ask.py:6093) в `_stems_of_text`
- [`ubuntu/serenedb/serene_ask.py:6182`](ubuntu/serenedb/serene_ask.py:6182) в `filter_balance_structural`
- [`ubuntu/serenedb/serene_ask.py:6218`](ubuntu/serenedb/serene_ask.py:6218) в `balance_bridge_clarify`
- [`ubuntu/serenedb/serene_ask.py:6686`](ubuntu/serenedb/serene_ask.py:6686) в `fork_outcome_c`
- [`ubuntu/serenedb/serene_ask.py:7002`](ubuntu/serenedb/serene_ask.py:7002) в `db_fingerprint`
- [`ubuntu/serenedb/serene_ask.py:8280`](ubuntu/serenedb/serene_ask.py:8280) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8318`](ubuntu/serenedb/serene_ask.py:8318) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:8540`](ubuntu/serenedb/serene_ask.py:8540) в `aggregate`
- [`ubuntu/serenedb/serene_ask.py:8589`](ubuntu/serenedb/serene_ask.py:8589) в `src_is_child`
- [`ubuntu/serenedb/serene_ask.py:8601`](ubuntu/serenedb/serene_ask.py:8601) в `refcols_of`
- [`ubuntu/serenedb/serene_ask.py:8618`](ubuntu/serenedb/serene_ask.py:8618) в `holders_of_target`
- [`ubuntu/serenedb/serene_ask.py:8638`](ubuntu/serenedb/serene_ask.py:8638) в `measures_of_many`
- [`ubuntu/serenedb/serene_ask.py:8660`](ubuntu/serenedb/serene_ask.py:8660) в `kind_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8695`](ubuntu/serenedb/serene_ask.py:8695) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:8722`](ubuntu/serenedb/serene_ask.py:8722) в `term_ref_owners`
- [`ubuntu/serenedb/serene_ask.py:8756`](ubuntu/serenedb/serene_ask.py:8756) в `term_axis_hits`
- [`ubuntu/serenedb/serene_ask.py:8794`](ubuntu/serenedb/serene_ask.py:8794) в `resolve_member_names`
- [`ubuntu/serenedb/serene_ask.py:8903`](ubuntu/serenedb/serene_ask.py:8903) в `aggregate_groups`
- [`ubuntu/serenedb/serene_ask.py:8969`](ubuntu/serenedb/serene_ask.py:8969) в `axis_clarify_options`
- [`ubuntu/serenedb/serene_ask.py:9412`](ubuntu/serenedb/serene_ask.py:9412) в `_table_label`
- [`ubuntu/serenedb/serene_ask.py:10581`](ubuntu/serenedb/serene_ask.py:10581) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10589`](ubuntu/serenedb/serene_ask.py:10589) в `_entity_counts_objects`
- [`ubuntu/serenedb/serene_ask.py:10601`](ubuntu/serenedb/serene_ask.py:10601) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10609`](ubuntu/serenedb/serene_ask.py:10609) в `_vitrina_objects`
- [`ubuntu/serenedb/serene_ask.py:10633`](ubuntu/serenedb/serene_ask.py:10633) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10670`](ubuntu/serenedb/serene_ask.py:10670) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10643`](ubuntu/serenedb/serene_ask.py:10643) в `_coverage_of`
- [`ubuntu/serenedb/serene_ask.py:10760`](ubuntu/serenedb/serene_ask.py:10760) в `_measure_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10780`](ubuntu/serenedb/serene_ask.py:10780) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/serene_ask.py:10801`](ubuntu/serenedb/serene_ask.py:10801) в `_classify_health_gap`
- [`ubuntu/serenedb/serene_ask.py:10856`](ubuntu/serenedb/serene_ask.py:10856) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/serene_ask.py:10953`](ubuntu/serenedb/serene_ask.py:10953) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:10962`](ubuntu/serenedb/serene_ask.py:10962) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:11124`](ubuntu/serenedb/serene_ask.py:11124) в `ambiguous_labels`
- [`ubuntu/serenedb/serene_ask.py:11170`](ubuntu/serenedb/serene_ask.py:11170) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11177`](ubuntu/serenedb/serene_ask.py:11177) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11187`](ubuntu/serenedb/serene_ask.py:11187) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11197`](ubuntu/serenedb/serene_ask.py:11197) в `opts_hints`
- [`ubuntu/serenedb/serene_ask.py:11276`](ubuntu/serenedb/serene_ask.py:11276) в `live_src_counts`
- [`ubuntu/serenedb/serene_ask.py:11465`](ubuntu/serenedb/serene_ask.py:11465) в `dates_outside_period_filter`
- [`ubuntu/serenedb/serene_ask.py:11597`](ubuntu/serenedb/serene_ask.py:11597) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11600`](ubuntu/serenedb/serene_ask.py:11600) в `_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11612`](ubuntu/serenedb/serene_ask.py:11612) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11615`](ubuntu/serenedb/serene_ask.py:11615) в `_src_covers_term_stems`
- [`ubuntu/serenedb/serene_ask.py:11635`](ubuntu/serenedb/serene_ask.py:11635) в `align_picked_to_terms`
- [`ubuntu/serenedb/serene_ask.py:11691`](ubuntu/serenedb/serene_ask.py:11691) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11696`](ubuntu/serenedb/serene_ask.py:11696) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11715`](ubuntu/serenedb/serene_ask.py:11715) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11755`](ubuntu/serenedb/serene_ask.py:11755) в `resolve_focus`
- [`ubuntu/serenedb/serene_ask.py:11852`](ubuntu/serenedb/serene_ask.py:11852) в `axis_focus_plan`
- [`ubuntu/serenedb/serene_ask.py:12257`](ubuntu/serenedb/serene_ask.py:12257) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12349`](ubuntu/serenedb/serene_ask.py:12349) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12917`](ubuntu/serenedb/serene_ask.py:12917) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12994`](ubuntu/serenedb/serene_ask.py:12994) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13041`](ubuntu/serenedb/serene_ask.py:13041) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14276`](ubuntu/serenedb/serene_ask.py:14276) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14618`](ubuntu/serenedb/serene_ask.py:14618) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14639`](ubuntu/serenedb/serene_ask.py:14639) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12358`](ubuntu/serenedb/serene_ask.py:12358) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14411`](ubuntu/serenedb/serene_ask.py:14411) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12395`](ubuntu/serenedb/serene_ask.py:12395) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12434`](ubuntu/serenedb/serene_ask.py:12434) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12599`](ubuntu/serenedb/serene_ask.py:12599) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12628`](ubuntu/serenedb/serene_ask.py:12628) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12650`](ubuntu/serenedb/serene_ask.py:12650) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12669`](ubuntu/serenedb/serene_ask.py:12669) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12693`](ubuntu/serenedb/serene_ask.py:12693) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12846`](ubuntu/serenedb/serene_ask.py:12846) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12980`](ubuntu/serenedb/serene_ask.py:12980) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13179`](ubuntu/serenedb/serene_ask.py:13179) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13852`](ubuntu/serenedb/serene_ask.py:13852) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14032`](ubuntu/serenedb/serene_ask.py:14032) в `answer`
- [`ubuntu/serenedb/serene_ask.py:14433`](ubuntu/serenedb/serene_ask.py:14433) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12379`](ubuntu/serenedb/serene_ask.py:12379) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13091`](ubuntu/serenedb/serene_ask.py:13091) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13715`](ubuntu/serenedb/serene_ask.py:13715) в `answer`
- [`ubuntu/serenedb/serene_ask.py:12530`](ubuntu/serenedb/serene_ask.py:12530) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13006`](ubuntu/serenedb/serene_ask.py:13006) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13114`](ubuntu/serenedb/serene_ask.py:13114) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13753`](ubuntu/serenedb/serene_ask.py:13753) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13819`](ubuntu/serenedb/serene_ask.py:13819) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13834`](ubuntu/serenedb/serene_ask.py:13834) в `answer`
- [`ubuntu/serenedb/serene_ask.py:13041`](ubuntu/serenedb/serene_ask.py:13041) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13091`](ubuntu/serenedb/serene_ask.py:13091) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13114`](ubuntu/serenedb/serene_ask.py:13114) в `answer._alias_verdict`
- [`ubuntu/serenedb/serene_ask.py:13179`](ubuntu/serenedb/serene_ask.py:13179) в `answer._alias_clarify`
- [`ubuntu/serenedb/serene_ask.py:15127`](ubuntu/serenedb/serene_ask.py:15127) в `entity_has_dates`
- [`ubuntu/serenedb/serene_ask.py:15181`](ubuntu/serenedb/serene_ask.py:15181) в `_journal_keep_n`
- [`ubuntu/serenedb/serene_ask.py:15205`](ubuntu/serenedb/serene_ask.py:15205) в `_journal_build_ts`
- [`ubuntu/serenedb/serene_ask.py:15218`](ubuntu/serenedb/serene_ask.py:15218) в `_journal_alias_ver`
- [`ubuntu/serenedb/serene_ask.py:15452`](ubuntu/serenedb/serene_ask.py:15452) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15473`](ubuntu/serenedb/serene_ask.py:15473) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15466`](ubuntu/serenedb/serene_ask.py:15466) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15468`](ubuntu/serenedb/serene_ask.py:15468) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15475`](ubuntu/serenedb/serene_ask.py:15475) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15407`](ubuntu/serenedb/serene_ask.py:15407) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15456`](ubuntu/serenedb/serene_ask.py:15456) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15469`](ubuntu/serenedb/serene_ask.py:15469) в `_ask_journal_write`
- [`ubuntu/serenedb/serene_ask.py:15452`](ubuntu/serenedb/serene_ask.py:15452) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15456`](ubuntu/serenedb/serene_ask.py:15456) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/serene_ask.py:15741`](ubuntu/serenedb/serene_ask.py:15741) в `Handler.do_GET`
- [`ubuntu/serenedb/serene_ask.py:15868`](ubuntu/serenedb/serene_ask.py:15868) в `Handler.do_POST`

### ds_chat (10)

- [`ubuntu/serenedb/serene_ask.py:631`](ubuntu/serenedb/serene_ask.py:631) в `arbitrate`
- [`ubuntu/serenedb/serene_ask.py:1230`](ubuntu/serenedb/serene_ask.py:1230) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:1238`](ubuntu/serenedb/serene_ask.py:1238) в `_one_intent`
- [`ubuntu/serenedb/serene_ask.py:3461`](ubuntu/serenedb/serene_ask.py:3461) в `clarify_text`
- [`ubuntu/serenedb/serene_ask.py:3494`](ubuntu/serenedb/serene_ask.py:3494) в `refuse_text`
- [`ubuntu/serenedb/serene_ask.py:4945`](ubuntu/serenedb/serene_ask.py:4945) в `rank_axis_pick`
- [`ubuntu/serenedb/serene_ask.py:8383`](ubuntu/serenedb/serene_ask.py:8383) в `pick_entity`
- [`ubuntu/serenedb/serene_ask.py:9804`](ubuntu/serenedb/serene_ask.py:9804) в `compose`
- [`ubuntu/serenedb/serene_ask.py:10982`](ubuntu/serenedb/serene_ask.py:10982) в `_coverage_answer`
- [`ubuntu/serenedb/serene_ask.py:15099`](ubuntu/serenedb/serene_ask.py:15099) в `question_facts`

### embed_one (1)

- [`ubuntu/serenedb/serene_ask.py:8439`](ubuntu/serenedb/serene_ask.py:8439) в `_vec`

### rerank (5)

- [`ubuntu/serenedb/serene_ask.py:3712`](ubuntu/serenedb/serene_ask.py:3712) в `resolve_values`
- [`ubuntu/serenedb/serene_ask.py:4918`](ubuntu/serenedb/serene_ask.py:4918) в `rank_axes_rerank`
- [`ubuntu/serenedb/serene_ask.py:8243`](ubuntu/serenedb/serene_ask.py:8243) в `pick_measure`
- [`ubuntu/serenedb/serene_ask.py:8705`](ubuntu/serenedb/serene_ask.py:8705) в `kind_axis_rerank`
- [`ubuntu/serenedb/serene_ask.py:12605`](ubuntu/serenedb/serene_ask.py:12605) в `answer`

### urlopen (4)

- [`ubuntu/serenedb/serene_ask.py:411`](ubuntu/serenedb/serene_ask.py:411) в `embed_model_live`
- [`ubuntu/serenedb/serene_ask.py:587`](ubuntu/serenedb/serene_ask.py:587) в `ds_chat_post`
- [`ubuntu/serenedb/serene_ask.py:789`](ubuntu/serenedb/serene_ask.py:789) в `embed_one`
- [`ubuntu/serenedb/serene_ask.py:3535`](ubuntu/serenedb/serene_ask.py:3535) в `rerank`
