# Карта `ubuntu/serenedb/ask/`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **13322**. Функций: **474**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **18**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/ask/z01_infra_trace_llm.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–862`)
- [02 intent](ubuntu/serenedb/ask/z02_intent.py:1) — Intent (якорь `_json_blocks` … `_first_intent_object`; `1–722`)
- [03 period-windows](ubuntu/serenedb/ask/z03_period_windows.py:1) — Периоды и окна (якорь `_num_pred` … `repair_period_from_question`; `1–540`)
- [04 calendar-axis](ubuntu/serenedb/ask/z04_calendar_axis.py:1) — Календарная ось (якорь `calendar_registers` … `_working_day_doc_preds`; `1–255`)
- [04b currency-axis](ubuntu/serenedb/ask/z04b_currency_axis.py:1) — Валютная ось (якорь `_sql_ident` … `currency_mismatch_blocks_answer`; `1–484`)
- [05 entity-form](ubuntu/serenedb/ask/z05_entity_form.py:1) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `1–570`)
- [06 entity-search](ubuntu/serenedb/ask/z06_entity_search.py:1) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `1–381`)
- [07 rrf-vectors](ubuntu/serenedb/ask/z07_rrf_vectors.py:1) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `1–511`)
- [08 measures-totals](ubuntu/serenedb/ask/z08_measures_totals.py:1) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `1–291`)
- [10 rank](ubuntu/serenedb/ask/z10_rank.py:1) — Ранг (якорь `count_question_skips_axis` … `rank_axis_resolve`; `1–276`)
- [11 sales](ubuntu/serenedb/ask/z11_sales.py:1) — Продажи (якорь `sales_sum_intent` … `catalog_count_question`; `1–249`)
- [12 stock-balance](ubuntu/serenedb/ask/z12_stock_balance.py:1) — Остатки (якорь `grain_dec_from_axis_ticket` … `stock_asks_named_product`; `1–1004`)
- [14 clarify-memory](ubuntu/serenedb/ask/z14_clarify_memory.py:1) — Уточнение и память (якорь `_alias_parts` … `hold_settled_entity`; `1–556`)
- [15 answer-atoms](ubuntu/serenedb/ask/z15_answer_atoms.py:1) — Атомы ответа (якорь `answer_money` … `fill_atom_pairs`; `1–442`)
- [17 aggregate-groups](ubuntu/serenedb/ask/z17_aggregate_groups.py:1) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `1–552`)
- [18 compose](ubuntu/serenedb/ask/z18_compose.py:1) — Формулировка (якорь `axis_clarify_options` … `compose`; `1–851`)
- [19 answer-check](ubuntu/serenedb/ask/z19_answer_check.py:1) — Проверка ответа (якорь `_readings` … `_filter_values`; `1–368`)
- [20 ask-main-http](ubuntu/serenedb/ask/z20_ask_main_http.py:1) — ask / HTTP (якорь `_filter_dates` … `Handler`; `1–3010`)
- [21 wiki-choice](ubuntu/serenedb/ask/z21_wiki_choice.py:1) — Вики-выбор (якорь `_wiki_hybrid_sql` … `wiki_measure_carried`; `1–1340`)
- [22 health-tick](ubuntu/serenedb/ask/z22_health_tick.py:1) — Health и тик (якорь `_parse_tick_status_note` … `_measure_tick_status`; `1–58`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 862 | 28 | 18 | 0 | 10 |
| 02 | intent | `_json_blocks` | 722 | 25 | 4 | 5 | 18 |
| 03 | period-windows | `_num_pred` | 540 | 23 | 5 | 2 | 12 |
| 04 | calendar-axis | `calendar_registers` | 255 | 13 | 2 | 4 | 10 |
| 04b | currency-axis | `_sql_ident` | 484 | 20 | 2 | 4 | 16 |
| 05 | entity-form | `entity_form_rank_single_window` | 570 | 19 | 4 | 6 | 7 |
| 06 | entity-search | `_predicates` | 381 | 12 | 3 | 3 | 5 |
| 07 | rrf-vectors | `_corpus_ivf_ready` | 511 | 16 | 8 | 4 | 6 |
| 08 | measures-totals | `_shares_chars` | 291 | 5 | 4 | 3 | 1 |
| 10 | rank | `count_question_skips_axis` | 276 | 9 | 5 | 4 | 3 |
| 11 | sales | `sales_sum_intent` | 249 | 12 | 5 | 3 | 5 |
| 12 | stock-balance | `grain_dec_from_axis_ticket` | 1004 | 55 | 4 | 10 | 48 |
| 14 | clarify-memory | `_alias_parts` | 556 | 27 | 5 | 1 | 12 |
| 15 | answer-atoms | `answer_money` | 442 | 13 | 2 | 4 | 5 |
| 17 | aggregate-groups | `_vec` | 552 | 17 | 11 | 3 | 6 |
| 18 | compose | `axis_clarify_options` | 851 | 19 | 2 | 8 | 2 |
| 19 | answer-check | `_readings` | 368 | 13 | 3 | 2 | 4 |
| 20 | ask-main-http | `_filter_dates` | 3010 | 75 | 3 | 19 | 70 |
| 21 | wiki-choice | `_wiki_hybrid_sql` | 1340 | 52 | 2 | 6 | 49 |
| 22 | health-tick | `_parse_tick_status_note` | 58 | 2 | 1 | 2 | 1 |

## 01. infra-trace-llm — Инфра, TRACE, LLM

Якорь: `_new_rid`, end `embed_one`. Участок: [`ubuntu/serenedb/ask/z01_infra_trace_llm.py:1`](ubuntu/serenedb/ask/z01_infra_trace_llm.py:1)–`862`.

Функций: 28. Входящие зоны: 02, 03, 04, 04b, 05, 06, 07, 08, 10, 12, 14, 15, 17, 18, 19, 20, 21, 22. Исходящие зоны: —.

Функции:

- [`_new_rid`](ubuntu/serenedb/ask/:80) `80–81` len=2
- [`_rid_norm`](ubuntu/serenedb/ask/:84) `84–89` len=6
- [`_rid_get`](ubuntu/serenedb/ask/:92) `92–93` len=2
- [`_rid_enter`](ubuntu/serenedb/ask/:96) `96–100` len=5
- [`_req_t0_clear`](ubuntu/serenedb/ask/:103) `103–106` len=4
- [`deadline_hit`](ubuntu/serenedb/ask/:109) `109–115` len=7
- [`_trace_write`](ubuntu/serenedb/ask/:118) `118–122` len=5
- [`_embed_secret_name_from_env`](ubuntu/serenedb/ask/:257) `257–261` len=5
- [`psql`](ubuntu/serenedb/ask/:287) `287–321` len=35
- [`lit`](ubuntu/serenedb/ask/:324) `324–325` len=2
- [`_embed_host_base`](ubuntu/serenedb/ask/:328) `328–331` len=4
- [`embed_model_live`](ubuntu/serenedb/ask/:351) `351–381` len=31
- [`emb_ready`](ubuntu/serenedb/ask/:384) `384–402` len=19
- [`_fmt`](ubuntu/serenedb/ask/:405) `405–411` len=7
- [`_src_tag`](ubuntu/serenedb/ask/:414) `414–418` len=5
- [`_fmt_gate_bad`](ubuntu/serenedb/ask/:421) `421–427` len=7
- [`_fmt_human`](ubuntu/serenedb/ask/:430) `430–444` len=15
- [`_token_acc_start`](ubuntu/serenedb/ask/:483) `483–484` len=2
- [`_token_acc_record`](ubuntu/serenedb/ask/:487) `487–501` len=15
- [`_diag_pack`](ubuntu/serenedb/ask/:504) `504–510` len=7
- [`_ds_chat_content`](ubuntu/serenedb/ask/:513) `513–526` len=14
- [`_ds_chat_body`](ubuntu/serenedb/ask/:529) `529–541` len=13
- [`ds_chat_post`](ubuntu/serenedb/ask/:544) `544–555` len=12
- [`ds_chat`](ubuntu/serenedb/ask/:558) `558–559` len=2
- [`_embed_request`](ubuntu/serenedb/ask/:583) `583–596` len=14
- [`_ensure_embed_secret`](ubuntu/serenedb/ask/:612) `612–643` len=32
- [`_embed_one_native`](ubuntu/serenedb/ask/:646) `646–680` len=35
- [`embed_one`](ubuntu/serenedb/ask/:683) `683–745` len=63

Зовут снаружи зоны: `_diag_pack`, `_ensure_embed_secret`, `_fmt`, `_fmt_gate_bad`, `_fmt_human`, `_req_t0_clear`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_src_tag`, `_token_acc_start`, `_trace_write`, `deadline_hit`, `ds_chat`, `emb_ready`, `embed_one`, `lit`, `psql`

## 02. intent — Intent

Якорь: `_json_blocks`, end `_first_intent_object`. Участок: [`ubuntu/serenedb/ask/z02_intent.py:1`](ubuntu/serenedb/ask/z02_intent.py:1)–`722`.

Функций: 25. Входящие зоны: 12, 18, 20, 21. Исходящие зоны: 01, 05, 10, 11, 12.

Функции:

- [`_json_blocks`](ubuntu/serenedb/ask/:9) `9–36` len=28
- [`_intent_text`](ubuntu/serenedb/ask/:39) `39–50` len=12
- [`_intent_number`](ubuntu/serenedb/ask/:53) `53–69` len=17
- [`_intent_date`](ubuntu/serenedb/ask/:72) `72–85` len=14
- [`_intent_terms`](ubuntu/serenedb/ask/:88) `88–124` len=37
- [`_intent_word`](ubuntu/serenedb/ask/:127) `127–129` len=3
- [`same_concept_groups`](ubuntu/serenedb/ask/:156) `156–195` len=40
- [`_stem_set`](ubuntu/serenedb/ask/:198) `198–205` len=8
- [`pair_slots_only`](ubuntu/serenedb/ask/:214) `214–219` len=6
- [`_creative_non_data_question`](ubuntu/serenedb/ask/:228) `228–230` len=3
- [`_accounting_word_known_to_base`](ubuntu/serenedb/ask/:233) `233–238` len=6
- [`_intent_has_known_accounting_anchor`](ubuntu/serenedb/ask/:241) `241–256` len=16
- [`_intent_coordinates_empty`](ubuntu/serenedb/ask/:259) `259–273` len=15
- [`_base_business_topic_words`](ubuntu/serenedb/ask/:276) `276–307` len=32
- [`conversational_business_vague`](ubuntu/serenedb/ask/:310) `310–346` len=37
- [`_enrich_conversational_business`](ubuntu/serenedb/ask/:349) `349–367` len=19
- [`question_expects_accounting_data`](ubuntu/serenedb/ask/:370) `370–403` len=34
- [`_base_knows_kind_or_measure`](ubuntu/serenedb/ask/:406) `406–430` len=25
- [`_normalize_intent`](ubuntu/serenedb/ask/:433) `433–571` len=139
- [`_one_intent`](ubuntu/serenedb/ask/:574) `574–590` len=17
- [`_field_key`](ubuntu/serenedb/ask/:593) `593–594` len=2
- [`_field_lead`](ubuntu/serenedb/ask/:597) `597–605` len=9
- [`_merge_intents`](ubuntu/serenedb/ask/:608) `608–632` len=25
- [`parse_intent`](ubuntu/serenedb/ask/:635) `635–695` len=61
- [`_first_intent_object`](ubuntu/serenedb/ask/:698) `698–717` len=20

Зовут снаружи зоны: `_base_knows_kind_or_measure`, `_intent_text`, `_intent_word`, `_stem_set`, `pair_slots_only`, `parse_intent`, `question_expects_accounting_data`

## 03. period-windows — Периоды и окна

Якорь: `_num_pred`, end `repair_period_from_question`. Участок: [`ubuntu/serenedb/ask/z03_period_windows.py:1`](ubuntu/serenedb/ask/z03_period_windows.py:1)–`540`.

Функций: 23. Входящие зоны: 04, 04b, 05, 06, 20. Исходящие зоны: 01, 04.

Функции:

- [`_num_pred`](ubuntu/serenedb/ask/:9) `9–27` len=19
- [`period_preds`](ubuntu/serenedb/ask/:30) `30–46` len=17
- [`_calendar_date`](ubuntu/serenedb/ask/:78) `78–83` len=6
- [`_month_range`](ubuntu/serenedb/ask/:86) `86–93` len=8
- [`_quarter_range`](ubuntu/serenedb/ask/:96) `96–105` len=10
- [`_week_range_monday`](ubuntu/serenedb/ask/:108) `108–112` len=5
- [`_prev_week_range`](ubuntu/serenedb/ask/:115) `115–123` len=9
- [`_is_seven_day_span`](ubuntu/serenedb/ask/:126) `126–130` len=5
- [`_is_current_calendar_week`](ubuntu/serenedb/ask/:133) `133–140` len=8
- [`_assumed_sliding_week_not_calendar`](ubuntu/serenedb/ask/:143) `143–153` len=11
- [`_iso_date`](ubuntu/serenedb/ask/:156) `156–157` len=2
- [`_period_origin`](ubuntu/serenedb/ask/:160) `160–171` len=12
- [`window_fp_of`](ubuntu/serenedb/ask/:174) `174–191` len=18
- [`_period_form_id`](ubuntu/serenedb/ask/:194) `194–218` len=25
- [`_window_reading`](ubuntu/serenedb/ask/:221) `221–252` len=32
- [`period_readings`](ubuntu/serenedb/ask/:255) `255–349` len=95
- [`period_relative_forms`](ubuntu/serenedb/ask/:355) `355–383` len=29
- [`period_form_from_question`](ubuntu/serenedb/ask/:386) `386–396` len=11
- [`month_day_range_from_question`](ubuntu/serenedb/ask/:404) `404–431` len=28
- [`_apply_period_form_window`](ubuntu/serenedb/ask/:434) `434–469` len=36
- [`_strip_period_assumed`](ubuntu/serenedb/ask/:472) `472–482` len=11
- [`_clear_month_day_parse_noise`](ubuntu/serenedb/ask/:485) `485–507` len=23
- [`repair_period_from_question`](ubuntu/serenedb/ask/:510) `510–537` len=28

Зовут снаружи зоны: `_calendar_date`, `_iso_date`, `_month_range`, `_num_pred`, `_prev_week_range`, `_week_range_monday`, `_window_reading`, `period_preds`, `period_readings`, `period_relative_forms`, `repair_period_from_question`

## 04. calendar-axis — Календарная ось

Якорь: `calendar_registers`, end `_working_day_doc_preds`. Участок: [`ubuntu/serenedb/ask/z04_calendar_axis.py:1`](ubuntu/serenedb/ask/z04_calendar_axis.py:1)–`255`.

Функций: 13. Входящие зоны: 03, 20. Исходящие зоны: 01, 03, 04b, 07.

Функции:

- [`calendar_registers`](ubuntu/serenedb/ask/:10) `10–23` len=14
- [`calendar_working_day_keys`](ubuntu/serenedb/ask/:26) `26–40` len=15
- [`calendar_map_rows`](ubuntu/serenedb/ask/:43) `43–71` len=29
- [`calendar_axis_map_ready`](ubuntu/serenedb/ask/:79) `79–82` len=4
- [`calendar_day_basis_phrases`](ubuntu/serenedb/ask/:85) `85–114` len=30
- [`day_basis_from_question`](ubuntu/serenedb/ask/:117) `117–130` len=14
- [`calendar_day_basis_needed`](ubuntu/serenedb/ask/:133) `133–150` len=18
- [`calendar_axis_unavailable_block`](ubuntu/serenedb/ask/:153) `153–171` len=19
- [`calendar_axis_open`](ubuntu/serenedb/ask/:174) `174–179` len=6
- [`_day_basis_reading`](ubuntu/serenedb/ask/:182) `182–188` len=7
- [`calendar_axis_readings`](ubuntu/serenedb/ask/:191) `191–206` len=16
- [`expand_readings_calendar_axis`](ubuntu/serenedb/ask/:209) `209–221` len=13
- [`_working_day_doc_preds`](ubuntu/serenedb/ask/:224) `224–252` len=29

Зовут снаружи зоны: `_working_day_doc_preds`, `calendar_axis_unavailable_block`, `expand_readings_calendar_axis`

## 04b. currency-axis — Валютная ось

Якорь: `_sql_ident`, end `currency_mismatch_blocks_answer`. Участок: [`ubuntu/serenedb/ask/z04b_currency_axis.py:1`](ubuntu/serenedb/ask/z04b_currency_axis.py:1)–`484`.

Функций: 20. Входящие зоны: 04, 20. Исходящие зоны: 01, 03, 17, 21.

Функции:

- [`_sql_ident`](ubuntu/serenedb/ask/:20) `20–21` len=2
- [`currency_catalogs`](ubuntu/serenedb/ask/:24) `24–37` len=14
- [`currency_rate_registers`](ubuntu/serenedb/ask/:40) `40–53` len=14
- [`accounting_currency_key`](ubuntu/serenedb/ask/:56) `56–69` len=14
- [`currency_map_rows`](ubuntu/serenedb/ask/:72) `72–107` len=36
- [`currency_rate_map_rows`](ubuntu/serenedb/ask/:110) `110–140` len=31
- [`currency_map_for_src`](ubuntu/serenedb/ask/:143) `143–147` len=5
- [`currency_axis_open`](ubuntu/serenedb/ask/:150) `150–155` len=6
- [`currency_basis_from_labels`](ubuntu/serenedb/ask/:158) `158–176` len=19
- [`_amount_basis_reading`](ubuntu/serenedb/ask/:179) `179–186` len=8
- [`currency_axis_applies`](ubuntu/serenedb/ask/:189) `189–212` len=24
- [`currency_axis_readings`](ubuntu/serenedb/ask/:215) `215–224` len=10
- [`expand_readings_currency_axis`](ubuntu/serenedb/ask/:227) `227–242` len=16
- [`_currency_period_where`](ubuntu/serenedb/ask/:245) `245–253` len=9
- [`_currency_rate_subquery`](ubuntu/serenedb/ask/:256) `256–280` len=25
- [`currency_fx_probe`](ubuntu/serenedb/ask/:283) `283–352` len=70
- [`currency_unit_for_ref`](ubuntu/serenedb/ask/:355) `355–374` len=20
- [`currency_unit_for_reading`](ubuntu/serenedb/ask/:377) `377–403` len=27
- [`currency_ref_requested`](ubuntu/serenedb/ask/:406) `406–446` len=41
- [`currency_mismatch_blocks_answer`](ubuntu/serenedb/ask/:449) `449–481` len=33

Зовут снаружи зоны: `_sql_ident`, `currency_mismatch_blocks_answer`, `currency_unit_for_reading`, `expand_readings_currency_axis`

## 05. entity-form — Форма сущности

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/ask/z05_entity_form.py:1`](ubuntu/serenedb/ask/z05_entity_form.py:1)–`570`.

Функций: 19. Входящие зоны: 02, 11, 12, 20. Исходящие зоны: 01, 03, 06, 10, 11, 17.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/ask/:15) `15–42` len=28
- [`_months_mentioned`](ubuntu/serenedb/ask/:62) `62–80` len=19
- [`_yoy_compare_marker`](ubuntu/serenedb/ask/:83) `83–88` len=6
- [`_shift_date_years`](ubuntu/serenedb/ask/:91) `91–96` len=6
- [`_shift_period_years`](ubuntu/serenedb/ask/:99) `99–109` len=11
- [`sales_compare_split_month_pair`](ubuntu/serenedb/ask/:112) `112–133` len=22
- [`sales_compare_intent`](ubuntu/serenedb/ask/:136) `136–202` len=67
- [`sales_compare_windows`](ubuntu/serenedb/ask/:205) `205–289` len=85
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/ask/:292) `292–334` len=43
- [`entity_form_movements_for_kind`](ubuntu/serenedb/ask/:337) `337–374` len=38
- [`_kind_axis_col_candidates`](ubuntu/serenedb/ask/:377) `377–409` len=33
- [`_pick_kind_axis_col`](ubuntu/serenedb/ask/:412) `412–417` len=6
- [`live_axis_col_candidates`](ubuntu/serenedb/ask/:420) `420–446` len=27
- [`live_axis_col_for_count`](ubuntu/serenedb/ask/:449) `449–465` len=17
- [`count_defer_measure_clarify`](ubuntu/serenedb/ask/:468) `468–485` len=18
- [`apply_proven_period`](ubuntu/serenedb/ask/:488) `488–506` len=19
- [`event_path_active`](ubuntu/serenedb/ask/:509) `509–510` len=2
- [`aggregate_distinct_axis`](ubuntu/serenedb/ask/:513) `513–540` len=28
- [`aggregate_compare_sales`](ubuntu/serenedb/ask/:543) `543–567` len=25

Зовут снаружи зоны: `_months_mentioned`, `aggregate_compare_sales`, `aggregate_distinct_axis`, `apply_proven_period`, `count_defer_measure_clarify`, `entity_form_catalogs_for_kind`, `entity_form_movements_for_kind`, `event_path_active`, `live_axis_col_candidates`, `live_axis_col_for_count`, `sales_compare_intent`, `sales_compare_windows`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/ask/z06_entity_search.py:1`](ubuntu/serenedb/ask/z06_entity_search.py:1)–`381`.

Функций: 12. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/ask/:9) `9–17` len=9
- [`_like_pattern`](ubuntu/serenedb/ask/:20) `20–40` len=21
- [`probe`](ubuntu/serenedb/ask/:43) `43–145` len=103
- [`matched_group_count`](ubuntu/serenedb/ask/:148) `148–158` len=11
- [`with_refs`](ubuntu/serenedb/ask/:161) `161–169` len=9
- [`match_expr`](ubuntu/serenedb/ask/:172) `172–202` len=31
- [`tables_of`](ubuntu/serenedb/ask/:205) `205–221` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/ask/:224) `224–239` len=16
- [`alias_hits`](ubuntu/serenedb/ask/:242) `242–273` len=32
- [`card_hits`](ubuntu/serenedb/ask/:276) `276–314` len=39
- [`question_exprs`](ubuntu/serenedb/ask/:317) `317–335` len=19
- [`meaning_candidates`](ubuntu/serenedb/ask/:338) `338–378` len=41

Зовут снаружи зоны: `_predicates`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `probe`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/ask/z07_rrf_vectors.py:1`](ubuntu/serenedb/ask/z07_rrf_vectors.py:1)–`511`.

Функций: 16. Входящие зоны: 04, 06, 08, 10, 15, 17, 20, 21. Исходящие зоны: 01, 08, 17, 19.

Функции:

- [`_corpus_ivf_ready`](ubuntu/serenedb/ask/:9) `9–23` len=15
- [`_resolver_ivf_ready`](ubuntu/serenedb/ask/:26) `26–45` len=20
- [`_rrf_entity_branches`](ubuntu/serenedb/ask/:48) `48–79` len=32
- [`_rrf_corpus_branch`](ubuntu/serenedb/ask/:82) `82–89` len=8
- [`_fused_sql_rrf`](ubuntu/serenedb/ask/:92) `92–97` len=6
- [`_fused_python_rrf`](ubuntu/serenedb/ask/:100) `100–116` len=17
- [`_fused_candidates`](ubuntu/serenedb/ask/:119) `119–170` len=52
- [`near_tables`](ubuntu/serenedb/ask/:173) `173–211` len=39
- [`rows_of`](ubuntu/serenedb/ask/:214) `214–246` len=33
- [`refuse_text`](ubuntu/serenedb/ask/:262) `262–284` len=23
- [`rerank`](ubuntu/serenedb/ask/:287) `287–345` len=59
- [`_resolver_psql`](ubuntu/serenedb/ask/:348) `348–366` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/ask/:373) `373–417` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/ask/:420) `420–441` len=22
- [`resolve_values`](ubuntu/serenedb/ask/:444) `444–501` len=58
- [`_ngrams`](ubuntu/serenedb/ask/:504) `504–508` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/ask/z08_measures_totals.py:1`](ubuntu/serenedb/ask/z08_measures_totals.py:1)–`291`.

Функций: 5. Входящие зоны: 07, 12, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/ask/:9) `9–26` len=18
- [`measures_of`](ubuntu/serenedb/ask/:139) `139–169` len=31
- [`measure_aliases_of`](ubuntu/serenedb/ask/:172) `172–181` len=10
- [`totals_of`](ubuntu/serenedb/ask/:184) `184–227` len=44
- [`_measures_by_src`](ubuntu/serenedb/ask/:266) `266–288` len=23

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `rank_axis_resolve`. Участок: [`ubuntu/serenedb/ask/z10_rank.py:1`](ubuntu/serenedb/ask/z10_rank.py:1)–`276`.

Функций: 9. Входящие зоны: 02, 05, 12, 20, 21. Исходящие зоны: 01, 07, 14, 17.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/ask/:9) `9–32` len=24
- [`question_wants_breakdown`](ubuntu/serenedb/ask/:35) `35–47` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/ask/:50) `50–68` len=19
- [`rank_question_text`](ubuntu/serenedb/ask/:71) `71–89` len=19
- [`rank_intent_from`](ubuntu/serenedb/ask/:92) `92–105` len=14
- [`rank_axis_label_rows`](ubuntu/serenedb/ask/:123) `123–146` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/ask/:149) `149–160` len=12
- [`rank_axis_pick`](ubuntu/serenedb/ask/:163) `163–209` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/ask/:212) `212–273` len=62

Зовут снаружи зоны: `count_question_skips_axis`, `question_wants_breakdown`, `rank_axis_resolve`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `catalog_count_question`. Участок: [`ubuntu/serenedb/ask/z11_sales.py:1`](ubuntu/serenedb/ask/z11_sales.py:1)–`249`.

Функций: 12. Входящие зоны: 02, 05, 12, 18, 20. Исходящие зоны: 05, 12, 14.

Функции:

- [`sales_kind_in_intent`](ubuntu/serenedb/ask/:15) `15–23` len=9
- [`sales_sum_intent`](ubuntu/serenedb/ask/:26) `26–76` len=51
- [`_sales_rank_top_n`](ubuntu/serenedb/ask/:79) `79–111` len=33
- [`_fork_headline_doc_measures`](ubuntu/serenedb/ask/:114) `114–119` len=6
- [`_fork_sum_headline_pool`](ubuntu/serenedb/ask/:122) `122–135` len=14
- [`sales_money_measure`](ubuntu/serenedb/ask/:138) `138–160` len=23
- [`sales_qty_measure`](ubuntu/serenedb/ask/:163) `163–173` len=11
- [`_zero_period_not_missing`](ubuntu/serenedb/ask/:176) `176–183` len=8
- [`sales_noncanon_focus`](ubuntu/serenedb/ask/:186) `186–194` len=9
- [`_is_product_catalog`](ubuntu/serenedb/ask/:197) `197–203` len=7
- [`catalog_kind_total_question`](ubuntu/serenedb/ask/:206) `206–230` len=25
- [`catalog_count_question`](ubuntu/serenedb/ask/:233) `233–246` len=14

Зовут снаружи зоны: `_sales_rank_top_n`, `_zero_period_not_missing`, `sales_kind_in_intent`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `stock_asks_named_product`. Участок: [`ubuntu/serenedb/ask/z12_stock_balance.py:1`](ubuntu/serenedb/ask/z12_stock_balance.py:1)–`1004`.

Функций: 55. Входящие зоны: 02, 11, 20, 21. Исходящие зоны: 01, 02, 05, 08, 10, 11, 14, 15, 17, 20.

Функции:

- [`_intent_period_has_meaning`](ubuntu/serenedb/ask/:15) `15–17` len=3
- [`_catalogs_for_axis_word`](ubuntu/serenedb/ask/:20) `20–33` len=14
- [`_non_product_ref_targets`](ubuntu/serenedb/ask/:36) `36–41` len=6
- [`_stock_eligible_product_registers`](ubuntu/serenedb/ask/:44) `44–51` len=8
- [`_stock_place_axis_catalogs`](ubuntu/serenedb/ask/:54) `54–81` len=28
- [`_catalog_on_stock_eligible_register`](ubuntu/serenedb/ask/:84) `84–110` len=27
- [`_kind_is_stock_scoped`](ubuntu/serenedb/ask/:113) `113–126` len=14
- [`_catalogs_are_warehouse_axis`](ubuntu/serenedb/ask/:129) `129–143` len=15
- [`_catalogs_for_warehouse_axis_word`](ubuntu/serenedb/ask/:146) `146–158` len=13
- [`_question_dictionary_axis_candidates`](ubuntu/serenedb/ask/:161) `161–187` len=27
- [`resolved_warehouse_axis_word`](ubuntu/serenedb/ask/:190) `190–200` len=11
- [`_word_names_documentjournal`](ubuntu/serenedb/ask/:203) `203–219` len=17
- [`resolved_unaccounted_slice_axis_word`](ubuntu/serenedb/ask/:222) `222–253` len=32
- [`intent_axis_words`](ubuntu/serenedb/ask/:256) `256–274` len=19
- [`state_path_active`](ubuntu/serenedb/ask/:277) `277–279` len=3
- [`aggregate_count_intent`](ubuntu/serenedb/ask/:282) `282–297` len=16
- [`secondary_axis_known`](ubuntu/serenedb/ask/:300) `300–310` len=11
- [`balance_axis_registers_confirmed`](ubuntu/serenedb/ask/:313) `313–322` len=10
- [`balance_routing_core`](ubuntu/serenedb/ask/:325) `325–340` len=16
- [`_stock_intent_signal`](ubuntu/serenedb/ask/:343) `343–352` len=10
- [`balance_path_engaged`](ubuntu/serenedb/ask/:355) `355–359` len=5
- [`question_mentions_warehouse_axis`](ubuntu/serenedb/ask/:362) `362–368` len=7
- [`question_has_aggregate_total_marker`](ubuntu/serenedb/ask/:371) `371–375` len=5
- [`question_wants_per_axis_breakdown`](ubuntu/serenedb/ask/:378) `378–380` len=3
- [`stock_question_engaged`](ubuntu/serenedb/ask/:383) `383–404` len=22
- [`registers_for_kind_axes`](ubuntu/serenedb/ask/:407) `407–436` len=30
- [`stock_count_aggregate_without_subject`](ubuntu/serenedb/ask/:439) `439–469` len=31
- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/ask/:472) `472–478` len=7
- [`balance_registers`](ubuntu/serenedb/ask/:481) `481–494` len=14
- [`balance_map_rows`](ubuntu/serenedb/ask/:497) `497–520` len=24
- [`balance_capable_sources`](ubuntu/serenedb/ask/:523) `523–525` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/ask/:528) `528–533` len=6
- [`register_is_balance_noise`](ubuntu/serenedb/ask/:536) `536–538` len=3
- [`stock_balance_is_reversal_noise`](ubuntu/serenedb/ask/:541) `541–545` len=5
- [`_is_product_catalog_target`](ubuntu/serenedb/ask/:548) `548–552` len=5
- [`_stock_registers_with_product_axis`](ubuntu/serenedb/ask/:555) `555–574` len=20
- [`_stock_product_targets_by_src`](ubuntu/serenedb/ask/:577) `577–595` len=19
- [`_stock_refs_by_src`](ubuntu/serenedb/ask/:598) `598–614` len=17
- [`_stock_cost_side_penalty`](ubuntu/serenedb/ask/:617) `617–629` len=13
- [`_stock_corpus_receipt_side_penalty`](ubuntu/serenedb/ask/:632) `632–643` len=12
- [`_stock_corpus_counts`](ubuntu/serenedb/ask/:646) `646–656` len=11
- [`_stock_register_rank_key`](ubuntu/serenedb/ask/:659) `659–671` len=13
- [`_sort_stock_pool`](ubuntu/serenedb/ask/:674) `674–682` len=9
- [`_stock_product_axis_cols`](ubuntu/serenedb/ask/:685) `685–701` len=17
- [`_stock_product_axis_col`](ubuntu/serenedb/ask/:704) `704–707` len=4
- [`_stock_qty_measure_candidates`](ubuntu/serenedb/ask/:710) `710–732` len=23
- [`_stock_qty_measure_name`](ubuntu/serenedb/ask/:735) `735–738` len=4
- [`_stock_receipt_candidates`](ubuntu/serenedb/ask/:741) `741–758` len=18
- [`stock_net_pair_candidates`](ubuntu/serenedb/ask/:761) `761–820` len=60
- [`stock_net_register_menu_opts`](ubuntu/serenedb/ask/:823) `823–880` len=58
- [`stock_net_register_pair`](ubuntu/serenedb/ask/:883) `883–888` len=6
- [`aggregate_stock_net_distinct`](ubuntu/serenedb/ask/:891) `891–939` len=49
- [`_stems_of_text`](ubuntu/serenedb/ask/:942) `942–957` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/ask/:960) `960–971` len=12
- [`stock_asks_named_product`](ubuntu/serenedb/ask/:974) `974–1001` len=28

Зовут снаружи зоны: `aggregate_stock_net_distinct`, `balance_routing_core`, `grain_dec_from_axis_ticket`, `intent_axis_words`, `stock_count_aggregate_without_subject`, `stock_net_register_menu_opts`, `stock_question_engaged`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `hold_settled_entity`. Участок: [`ubuntu/serenedb/ask/z14_clarify_memory.py:1`](ubuntu/serenedb/ask/z14_clarify_memory.py:1)–`556`.

Функций: 27. Входящие зоны: 10, 11, 12, 18, 20. Исходящие зоны: 01.

Функции:

- [`_alias_parts`](ubuntu/serenedb/ask/:9) `9–13` len=5
- [`_word_hits_text`](ubuntu/serenedb/ask/:16) `16–20` len=5
- [`split_ident`](ubuntu/serenedb/ask/:23) `23–27` len=5
- [`measure_choice`](ubuntu/serenedb/ask/:30) `30–71` len=42
- [`measure_captions`](ubuntu/serenedb/ask/:74) `74–92` len=19
- [`resolve_measure`](ubuntu/serenedb/ask/:95) `95–127` len=33
- [`question_fingerprint`](ubuntu/serenedb/ask/:153) `153–156` len=4
- [`db_fingerprint`](ubuntu/serenedb/ask/:159) `159–173` len=15
- [`options_version`](ubuntu/serenedb/ask/:176) `176–189` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/ask/:192) `192–203` len=12
- [`_new_decision_id`](ubuntu/serenedb/ask/:206) `206–208` len=3
- [`_purge_decisions`](ubuntu/serenedb/ask/:211) `211–226` len=16
- [`_resolved_key`](ubuntu/serenedb/ask/:229) `229–231` len=3
- [`peek_resolved`](ubuntu/serenedb/ask/:234) `234–240` len=7
- [`accumulate_resolution`](ubuntu/serenedb/ask/:243) `243–262` len=20
- [`issue_decision`](ubuntu/serenedb/ask/:265) `265–306` len=42
- [`seal_clarify`](ubuntu/serenedb/ask/:309) `309–361` len=53
- [`consume_decision`](ubuntu/serenedb/ask/:364) `364–391` len=28
- [`peek_decision`](ubuntu/serenedb/ask/:394) `394–414` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/ask/:417) `417–441` len=25
- [`reissue_clarify`](ubuntu/serenedb/ask/:444) `444–462` len=19
- [`attach_memory_shadow`](ubuntu/serenedb/ask/:465) `465–476` len=12
- [`choice_proven`](ubuntu/serenedb/ask/:479) `479–485` len=7
- [`choice_levels_proven`](ubuntu/serenedb/ask/:488) `488–504` len=17
- [`measure_already_proven`](ubuntu/serenedb/ask/:507) `507–511` len=5
- [`entity_choice_locked`](ubuntu/serenedb/ask/:514) `514–516` len=3
- [`hold_settled_entity`](ubuntu/serenedb/ask/:519) `519–553` len=35

Зовут снаружи зоны: `accumulate_resolution`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `answer_money`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/ask/z15_answer_atoms.py:1`](ubuntu/serenedb/ask/z15_answer_atoms.py:1)–`442`.

Функций: 13. Входящие зоны: 12, 20. Исходящие зоны: 01, 07, 17, 18.

Функции:

- [`answer_money`](ubuntu/serenedb/ask/:10) `10–19` len=10
- [`answer_slot_mode`](ubuntu/serenedb/ask/:22) `22–48` len=27
- [`compose_slot_values`](ubuntu/serenedb/ask/:51) `51–122` len=72
- [`atom_operation`](ubuntu/serenedb/ask/:136) `136–150` len=15
- [`_atom_exact_value`](ubuntu/serenedb/ask/:153) `153–172` len=20
- [`build_answer_atom`](ubuntu/serenedb/ask/:175) `175–218` len=44
- [`atom_from_agg`](ubuntu/serenedb/ask/:221) `221–276` len=56
- [`_period_window_human`](ubuntu/serenedb/ask/:279) `279–286` len=8
- [`render_atom_pair`](ubuntu/serenedb/ask/:289) `289–348` len=60
- [`fill_atom_pairs`](ubuntu/serenedb/ask/:351) `351–380` len=30
- [`atom_terminal_gate_text`](ubuntu/serenedb/ask/:383) `383–396` len=14
- [`stock_balance_is_sales_noise`](ubuntu/serenedb/ask/:399) `399–411` len=13
- [`_fork_figures_of`](ubuntu/serenedb/ask/:414) `414–439` len=26

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `atom_terminal_gate_text`, `compose_slot_values`, `fill_atom_pairs`, `stock_balance_is_sales_noise`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/ask/z17_aggregate_groups.py:1`](ubuntu/serenedb/ask/z17_aggregate_groups.py:1)–`552`.

Функций: 17. Входящие зоны: 04b, 05, 07, 08, 10, 12, 15, 18, 19, 20, 22. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/ask/:9) `9–10` len=2
- [`_num`](ubuntu/serenedb/ask/:13) `13–17` len=5
- [`_numN`](ubuntu/serenedb/ask/:20) `20–33` len=14
- [`_sql_ident_col`](ubuntu/serenedb/ask/:36) `36–37` len=2
- [`_live_measure_date_col`](ubuntu/serenedb/ask/:40) `40–56` len=17
- [`_live_column_exists`](ubuntu/serenedb/ask/:59) `59–69` len=11
- [`_live_std_excl_preds`](ubuntu/serenedb/ask/:72) `72–83` len=12
- [`aggregate_live_column`](ubuntu/serenedb/ask/:86) `86–152` len=67
- [`aggregate`](ubuntu/serenedb/ask/:155) `155–278` len=124
- [`src_is_child`](ubuntu/serenedb/ask/:281) `281–290` len=10
- [`refcols_of`](ubuntu/serenedb/ask/:293) `293–307` len=15
- [`kind_axis_hits`](ubuntu/serenedb/ask/:310) `310–351` len=42
- [`kind_axis_rerank`](ubuntu/serenedb/ask/:354) `354–377` len=24
- [`term_axis_hits`](ubuntu/serenedb/ask/:380) `380–419` len=40
- [`_group_leader`](ubuntu/serenedb/ask/:422) `422–431` len=10
- [`_group_fold`](ubuntu/serenedb/ask/:434) `434–440` len=7
- [`aggregate_groups`](ubuntu/serenedb/ask/:443) `443–549` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `kind_axis_hits`, `kind_axis_rerank`, `refcols_of`, `src_is_child`, `term_axis_hits`

## 18. compose — Формулировка

Якорь: `axis_clarify_options`, end `compose`. Участок: [`ubuntu/serenedb/ask/z18_compose.py:1`](ubuntu/serenedb/ask/z18_compose.py:1)–`851`.

Функций: 19. Входящие зоны: 15, 20. Исходящие зоны: 01, 02, 08, 11, 14, 17, 19, 20.

Функции:

- [`axis_clarify_options`](ubuntu/serenedb/ask/:10) `10–49` len=40
- [`_split_answer`](ubuntu/serenedb/ask/:86) `86–116` len=31
- [`_group_value_by_name`](ubuntu/serenedb/ask/:136) `136–152` len=17
- [`_fill_figures`](ubuntu/serenedb/ask/:155) `155–276` len=122
- [`ensure_n_groups_named`](ubuntu/serenedb/ask/:279) `279–297` len=19
- [`ensure_count_named`](ubuntu/serenedb/ask/:300) `300–318` len=19
- [`_measure_dimension`](ubuntu/serenedb/ask/:321) `321–339` len=19
- [`_unit_for_measure`](ubuntu/serenedb/ask/:342) `342–360` len=19
- [`postprocess_money_answer_text`](ubuntu/serenedb/ask/:363) `363–371` len=9
- [`build_answer_passport`](ubuntu/serenedb/ask/:373) `373–432` len=60
- [`ensure_answer_passport`](ubuntu/serenedb/ask/:435) `435–444` len=10
- [`measure_label_of`](ubuntu/serenedb/ask/:447) `447–456` len=10
- [`_table_label`](ubuntu/serenedb/ask/:459) `459–470` len=12
- [`_passport_axis_label`](ubuntu/serenedb/ask/:473) `473–484` len=12
- [`_passport_axis_col`](ubuntu/serenedb/ask/:487) `487–490` len=4
- [`_passport_origin`](ubuntu/serenedb/ask/:493) `493–500` len=8
- [`formulation_flaws`](ubuntu/serenedb/ask/:503) `503–530` len=28
- [`copied_figures`](ubuntu/serenedb/ask/:533) `533–600` len=68
- [`compose`](ubuntu/serenedb/ask/:603) `603–825` len=223

Зовут снаружи зоны: `_fill_figures`, `_passport_axis_col`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/ask/z19_answer_check.py:1`](ubuntu/serenedb/ask/z19_answer_check.py:1)–`368`.

Функций: 13. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/ask/:9) `9–49` len=41
- [`_plausible`](ubuntu/serenedb/ask/:52) `52–61` len=10
- [`_dates`](ubuntu/serenedb/ask/:64) `64–84` len=21
- [`_date2_readings`](ubuntu/serenedb/ask/:87) `87–98` len=12
- [`_date_spans`](ubuntu/serenedb/ask/:101) `101–121` len=21
- [`_tokens`](ubuntu/serenedb/ask/:124) `124–154` len=31
- [`_norm_numbers`](ubuntu/serenedb/ask/:157) `157–162` len=6
- [`check_claims`](ubuntu/serenedb/ask/:168) `168–201` len=34
- [`prompt_leak`](ubuntu/serenedb/ask/:205) `205–224` len=20
- [`asked_figure_missing`](ubuntu/serenedb/ask/:227) `227–314` len=88
- [`stale_note`](ubuntu/serenedb/ask/:317) `317–332` len=16
- [`_threshold_values`](ubuntu/serenedb/ask/:335) `335–339` len=5
- [`_filter_values`](ubuntu/serenedb/ask/:342) `342–364` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/ask/z20_ask_main_http.py:1`](ubuntu/serenedb/ask/z20_ask_main_http.py:1)–`3010`.

Функций: 75. Входящие зоны: 12, 18, 21. Исходящие зоны: 01, 02, 03, 04, 04b, 05, 06, 07, 08, 10, 11, 12, 14, 15, 17, 18, 19, 21, 22.

Функции:

- [`_filter_dates`](ubuntu/serenedb/ask/:14) `14–23` len=10
- [`without_list_markers`](ubuntu/serenedb/ask/:34) `34–48` len=15
- [`rows_seen`](ubuntu/serenedb/ask/:51) `51–75` len=25
- [`gate`](ubuntu/serenedb/ask/:78) `78–239` len=162
- [`gate_out`](ubuntu/serenedb/ask/:242) `242–260` len=19
- [`_opt_values`](ubuntu/serenedb/ask/:263) `263–278` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/ask/:281) `281–296` len=16
- [`clarify_choice_line`](ubuntu/serenedb/ask/:299) `299–306` len=8
- [`format_clarify_options`](ubuntu/serenedb/ask/:309) `309–327` len=19
- [`clarify_say`](ubuntu/serenedb/ask/:330) `330–352` len=23
- [`clarify_opts_response`](ubuntu/serenedb/ask/:355) `355–379` len=25
- [`_entity_counts_objects`](ubuntu/serenedb/ask/:392) `392–409` len=18
- [`_vitrina_objects`](ubuntu/serenedb/ask/:412) `412–425` len=14
- [`_coverage_of`](ubuntu/serenedb/ask/:436) `436–497` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/ask/:524) `524–559` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/ask/:562) `562–564` len=3
- [`_measure_health_gap`](ubuntu/serenedb/ask/:567) `567–582` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/ask/:585) `585–599` len=15
- [`_classify_health_gap`](ubuntu/serenedb/ask/:602) `602–632` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/ask/:635) `635–640` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/ask/:643) `643–692` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/ask/:695) `695–707` len=13
- [`_health_gap`](ubuntu/serenedb/ask/:710) `710–722` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/ask/:725) `725–733` len=9
- [`_coverage_answer`](ubuntu/serenedb/ask/:758) `758–842` len=85
- [`looks_like_src_table`](ubuntu/serenedb/ask/:882) `882–887` len=6
- [`human_table_label`](ubuntu/serenedb/ask/:890) `890–902` len=13
- [`label_has_meta_src`](ubuntu/serenedb/ask/:905) `905–917` len=13
- [`kind_word`](ubuntu/serenedb/ask/:920) `920–923` len=4
- [`label_with_kind`](ubuntu/serenedb/ask/:926) `926–937` len=12
- [`ambiguous_labels`](ubuntu/serenedb/ask/:943) `943–965` len=23
- [`disambiguate_labels`](ubuntu/serenedb/ask/:968) `968–985` len=18
- [`opts_hints`](ubuntu/serenedb/ask/:997) `997–1056` len=60
- [`mk_opts`](ubuntu/serenedb/ask/:1059) `1059–1087` len=29
- [`live_src_counts`](ubuntu/serenedb/ask/:1090) `1090–1122` len=33
- [`empty_after_period_action`](ubuntu/serenedb/ask/:1125) `1125–1140` len=16
- [`period_empty_outcome`](ubuntu/serenedb/ask/:1143) `1143–1167` len=25
- [`_period_day_label`](ubuntu/serenedb/ask/:1170) `1170–1185` len=16
- [`dates_outside_period_filter`](ubuntu/serenedb/ask/:1188) `1188–1202` len=15
- [`format_period_empty_text`](ubuntu/serenedb/ask/:1205) `1205–1253` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/ask/:1256) `1256–1310` len=55
- [`_day_ord`](ubuntu/serenedb/ask/:1313) `1313–1318` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/ask/:1321) `1321–1345` len=25
- [`period_slot_for_inherit`](ubuntu/serenedb/ask/:1348) `1348–1359` len=12
- [`apply_prior_period`](ubuntu/serenedb/ask/:1362) `1362–1390` len=29
- [`readings_menu`](ubuntu/serenedb/ask/:1393) `1393–1406` len=14
- [`_reading_human_label`](ubuntu/serenedb/ask/:1409) `1409–1431` len=23
- [`_readings_to_opts`](ubuntu/serenedb/ask/:1434) `1434–1455` len=22
- [`_apply_sole_reading`](ubuntu/serenedb/ask/:1458) `1458–1475` len=18
- [`_wiki_named_entity`](ubuntu/serenedb/ask/:1478) `1478–1482` len=5
- [`_measure_menu_opts`](ubuntu/serenedb/ask/:1485) `1485–1498` len=14
- [`_settle_measure`](ubuntu/serenedb/ask/:1501) `1501–1550` len=50
- [`_settle_axis`](ubuntu/serenedb/ask/:1553) `1553–1627` len=75
- [`_onepath_compose_gate`](ubuntu/serenedb/ask/:1630) `1630–1843` len=214
- [`answer`](ubuntu/serenedb/ask/:1846) `1846–2310` len=465
- [`_journal_keep_n`](ubuntu/serenedb/ask/:2316) `2316–2330` len=15
- [`_journal_code_md5`](ubuntu/serenedb/ask/:2333) `2333–2340` len=8
- [`_journal_build_ts`](ubuntu/serenedb/ask/:2343) `2343–2354` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/ask/:2357) `2357–2370` len=14
- [`_journal_sql_int`](ubuntu/serenedb/ask/:2373) `2373–2379` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/ask/:2382) `2382–2385` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/ask/:2388) `2388–2416` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/ask/:2419) `2419–2441` len=23
- [`_journal_doubt`](ubuntu/serenedb/ask/:2444) `2444–2453` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/ask/:2456) `2456–2469` len=14
- [`_journal_intent`](ubuntu/serenedb/ask/:2472) `2472–2474` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/ask/:2477) `2477–2485` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/ask/:2488) `2488–2507` len=20
- [`_ask_journal_write`](ubuntu/serenedb/ask/:2510) `2510–2624` len=115
- [`_answer_checked_core`](ubuntu/serenedb/ask/:2627) `2627–2632` len=6
- [`answer_checked`](ubuntu/serenedb/ask/:2634) `2634–2713` len=80
- [`_build_ask_scope`](ubuntu/serenedb/ask/:2716) `2716–2757` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/ask/:2760) `2760–2779` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/ask/:2782) `2782–2793` len=12
- [`main`](ubuntu/serenedb/ask/:2994) `2994–3003` len=10

Зовут снаружи зоны: `human_table_label`, `kind_word`, `looks_like_src_table`, `mk_opts`, `readings_menu`

## 21. wiki-choice — Вики-выбор

Якорь: `_wiki_hybrid_sql`, end `wiki_measure_carried`. Участок: [`ubuntu/serenedb/ask/z21_wiki_choice.py:1`](ubuntu/serenedb/ask/z21_wiki_choice.py:1)–`1340`.

Функций: 52. Входящие зоны: 04b, 20. Исходящие зоны: 01, 02, 07, 10, 12, 20.

Функции:

- [`_wiki_hybrid_sql`](ubuntu/serenedb/ask/:31) `31–35` len=5
- [`_wiki_passport_sql`](ubuntu/serenedb/ask/:38) `38–42` len=5
- [`wiki_aggregate_want`](ubuntu/serenedb/ask/:60) `60–73` len=14
- [`wiki_action_class`](ubuntu/serenedb/ask/:76) `76–79` len=4
- [`wiki_action_axis`](ubuntu/serenedb/ask/:82) `82–83` len=2
- [`wiki_platform_kind`](ubuntu/serenedb/ask/:86) `86–91` len=6
- [`_norm_ye`](ubuntu/serenedb/ask/:148) `148–149` len=2
- [`_named_type_phrase_patterns`](ubuntu/serenedb/ask/:152) `152–173` len=22
- [`named_platform_kinds`](ubuntu/serenedb/ask/:176) `176–188` len=13
- [`_card_odata_kind`](ubuntu/serenedb/ask/:191) `191–194` len=4
- [`filter_pool_by_named_type`](ubuntu/serenedb/ask/:197) `197–215` len=19
- [`wiki_axis_phrase`](ubuntu/serenedb/ask/:218) `218–247` len=30
- [`_wiki_axis_has_carriers`](ubuntu/serenedb/ask/:253) `253–278` len=26
- [`_wiki_hybrid_vars`](ubuntu/serenedb/ask/:281) `281–308` len=28
- [`_wiki_substitute_sql`](ubuntu/serenedb/ask/:311) `311–320` len=10
- [`wiki_hybrid_pool`](ubuntu/serenedb/ask/:323) `323–362` len=40
- [`wiki_format_card_lines`](ubuntu/serenedb/ask/:365) `365–376` len=12
- [`wiki_strip_passport_yaml`](ubuntu/serenedb/ask/:393) `393–411` len=19
- [`wiki_caption_leaks`](ubuntu/serenedb/ask/:414) `414–425` len=12
- [`wiki_human_menu_caption`](ubuntu/serenedb/ask/:428) `428–461` len=34
- [`wiki_human_menu_hint`](ubuntu/serenedb/ask/:464) `464–473` len=10
- [`fork_labels_of`](ubuntu/serenedb/ask/:476) `476–498` len=23
- [`fork_labels_covering`](ubuntu/serenedb/ask/:501) `501–530` len=30
- [`wiki_menu_captions`](ubuntu/serenedb/ask/:533) `533–567` len=35
- [`wiki_captions_map_from_cards`](ubuntu/serenedb/ask/:570) `570–579` len=10
- [`_wiki_substitute_passport_sql`](ubuntu/serenedb/ask/:582) `582–594` len=13
- [`_wiki_parse_axes_set`](ubuntu/serenedb/ask/:597) `597–605` len=9
- [`_wiki_parse_measures_set`](ubuntu/serenedb/ask/:608) `608–616` len=9
- [`wiki_passport_distinct`](ubuntu/serenedb/ask/:619) `619–636` len=18
- [`wiki_passport_enrich`](ubuntu/serenedb/ask/:639) `639–681` len=43
- [`wiki_format_passport_lines`](ubuntu/serenedb/ask/:684) `684–710` len=27
- [`_wiki_sanitize_why`](ubuntu/serenedb/ask/:720) `720–724` len=5
- [`_wiki_verdicts_for_diag`](ubuntu/serenedb/ask/:727) `727–742` len=16
- [`_wiki_row_to_verdict`](ubuntu/serenedb/ask/:745) `745–761` len=17
- [`_wiki_verdicts_from_rows`](ubuntu/serenedb/ask/:764) `764–772` len=9
- [`_wiki_salvage_verdicts`](ubuntu/serenedb/ask/:775) `775–812` len=38
- [`wiki_parse_verify_response`](ubuntu/serenedb/ask/:815) `815–841` len=27
- [`_homonym_norm`](ubuntu/serenedb/ask/:844) `844–846` len=3
- [`_homonym_keys`](ubuntu/serenedb/ask/:849) `849–869` len=21
- [`wiki_homonym_kind_peers`](ubuntu/serenedb/ask/:872) `872–893` len=22
- [`wiki_outcome_from_verify`](ubuntu/serenedb/ask/:896) `896–956` len=61
- [`wiki_verify_candidates`](ubuntu/serenedb/ask/:959) `959–996` len=38
- [`wiki_knn_separable`](ubuntu/serenedb/ask/:999) `999–1006` len=8
- [`wiki_validate_leader_axes`](ubuntu/serenedb/ask/:1009) `1009–1021` len=13
- [`wiki_pick_from_cards`](ubuntu/serenedb/ask/:1024) `1024–1079` len=56
- [`wiki_primary_entity_cascade`](ubuntu/serenedb/ask/:1082) `1082–1123` len=42
- [`try_wiki_hybrid_entity_pick`](ubuntu/serenedb/ask/:1126) `1126–1209` len=84
- [`wiki_intent_named_measures`](ubuntu/serenedb/ask/:1212) `1212–1232` len=21
- [`wiki_axis_is_question_subject`](ubuntu/serenedb/ask/:1235) `1235–1244` len=10
- [`wiki_leader_carries_axis`](ubuntu/serenedb/ask/:1247) `1247–1278` len=32
- [`wiki_leader_post_verify`](ubuntu/serenedb/ask/:1281) `1281–1311` len=31
- [`wiki_measure_carried`](ubuntu/serenedb/ask/:1314) `1314–1337` len=24

Зовут снаружи зоны: `fork_labels_covering`, `fork_labels_of`, `wiki_primary_entity_cascade`

## 22. health-tick — Health и тик

Якорь: `_parse_tick_status_note`, end `_measure_tick_status`. Участок: [`ubuntu/serenedb/ask/z22_health_tick.py:1`](ubuntu/serenedb/ask/z22_health_tick.py:1)–`58`.

Функций: 2. Входящие зоны: 20. Исходящие зоны: 01, 17.

Функции:

- [`_parse_tick_status_note`](ubuntu/serenedb/ask/:12) `12–19` len=8
- [`_measure_tick_status`](ubuntu/serenedb/ask/:22) `22–55` len=34

Зовут снаружи зоны: `_measure_tick_status`

## Сквозные функции

Функции, которые вызывают из трёх и более других зон.

| функция | зона | вызывающих зон | зоны |
|---|---|---:|---|
| [`psql`](ubuntu/serenedb/ask/:287) | 01 | 16 | 02, 03, 04, 04b, 05, 06, 07, 08, 10, 12, 14, 17, 18, 20, 21, 22 |
| [`lit`](ubuntu/serenedb/ask/:324) | 01 | 14 | 02, 03, 04, 04b, 05, 06, 07, 08, 10, 12, 17, 18, 20, 21 |
| [`_num`](ubuntu/serenedb/ask/:13) | 17 | 6 | 04b, 05, 08, 18, 20, 22 |
| [`ds_chat`](ubuntu/serenedb/ask/:558) | 01 | 6 | 02, 07, 10, 18, 20, 21 |
| [`rank_intent_from`](ubuntu/serenedb/ask/:92) | 10 | 4 | 05, 12, 20, 21 |
| [`refuse_text`](ubuntu/serenedb/ask/:262) | 07 | 4 | 04, 15, 20, 21 |
| [`refcols_of`](ubuntu/serenedb/ask/:293) | 17 | 4 | 05, 10, 12, 20 |
| [`_fmt`](ubuntu/serenedb/ask/:405) | 01 | 4 | 15, 18, 19, 20 |
| [`sales_sum_intent`](ubuntu/serenedb/ask/:26) | 11 | 3 | 02, 05, 12 |
| [`period_preds`](ubuntu/serenedb/ask/:30) | 03 | 3 | 04b, 05, 06 |
| [`measure_choice`](ubuntu/serenedb/ask/:30) | 14 | 3 | 11, 12, 20 |
| [`measures_of`](ubuntu/serenedb/ask/:139) | 08 | 3 | 12, 18, 20 |
| [`_norm_numbers`](ubuntu/serenedb/ask/:157) | 19 | 3 | 07, 18, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/ask/:172) | 08 | 3 | 12, 18, 20 |
| [`entity_form_catalogs_for_kind`](ubuntu/serenedb/ask/:292) | 05 | 3 | 02, 11, 12 |
| [`kind_axis_hits`](ubuntu/serenedb/ask/:310) | 17 | 3 | 05, 10, 20 |
| [`_diag_pack`](ubuntu/serenedb/ask/:504) | 01 | 3 | 04, 20, 21 |
| [`kind_word`](ubuntu/serenedb/ask/:920) | 20 | 3 | 12, 18, 21 |

## Внутренние функции зоны

Функции, которые никто снаружи своей зоны не вызывает (включая ни разу не вызванные из других зон).

### 01 infra-trace-llm (10/28)

- `_ds_chat_body`
- `_ds_chat_content`
- `_embed_host_base`
- `_embed_one_native`
- `_embed_request`
- `_embed_secret_name_from_env`
- `_new_rid`
- `_token_acc_record`
- `ds_chat_post`
- `embed_model_live`

### 02 intent (18/25)

- `_accounting_word_known_to_base`
- `_base_business_topic_words`
- `_creative_non_data_question`
- `_enrich_conversational_business`
- `_field_key`
- `_field_lead`
- `_first_intent_object`
- `_intent_coordinates_empty`
- `_intent_date`
- `_intent_has_known_accounting_anchor`
- `_intent_number`
- `_intent_terms`
- `_json_blocks`
- `_merge_intents`
- `_normalize_intent`
- `_one_intent`
- `conversational_business_vague`
- `same_concept_groups`

### 03 period-windows (12/23)

- `_apply_period_form_window`
- `_assumed_sliding_week_not_calendar`
- `_clear_month_day_parse_noise`
- `_is_current_calendar_week`
- `_is_seven_day_span`
- `_period_form_id`
- `_period_origin`
- `_quarter_range`
- `_strip_period_assumed`
- `month_day_range_from_question`
- `period_form_from_question`
- `window_fp_of`

### 04 calendar-axis (10/13)

- `_day_basis_reading`
- `calendar_axis_map_ready`
- `calendar_axis_open`
- `calendar_axis_readings`
- `calendar_day_basis_needed`
- `calendar_day_basis_phrases`
- `calendar_map_rows`
- `calendar_registers`
- `calendar_working_day_keys`
- `day_basis_from_question`

### 04b currency-axis (16/20)

- `_amount_basis_reading`
- `_currency_period_where`
- `_currency_rate_subquery`
- `accounting_currency_key`
- `currency_axis_applies`
- `currency_axis_open`
- `currency_axis_readings`
- `currency_basis_from_labels`
- `currency_catalogs`
- `currency_fx_probe`
- `currency_map_for_src`
- `currency_map_rows`
- `currency_rate_map_rows`
- `currency_rate_registers`
- `currency_ref_requested`
- `currency_unit_for_ref`

### 05 entity-form (7/19)

- `_kind_axis_col_candidates`
- `_pick_kind_axis_col`
- `_shift_date_years`
- `_shift_period_years`
- `_yoy_compare_marker`
- `entity_form_rank_single_window`
- `sales_compare_split_month_pair`

### 06 entity-search (5/12)

- `_like_pattern`
- `alias_hits`
- `card_hits`
- `question_exprs`
- `with_refs`

### 07 rrf-vectors (6/16)

- `_corpus_ivf_ready`
- `_fused_python_rrf`
- `_fused_sql_rrf`
- `_resolver_ivf_ready`
- `_rrf_corpus_branch`
- `_rrf_entity_branches`

### 08 measures-totals (1/5)

- `_measures_by_src`

### 10 rank (3/9)

- `rank_axes_rerank`
- `rank_axis_label_rows`
- `rank_axis_pick`

### 11 sales (5/12)

- `_fork_headline_doc_measures`
- `_fork_sum_headline_pool`
- `_is_product_catalog`
- `catalog_count_question`
- `catalog_kind_total_question`

### 12 stock-balance (48/55)

- `_catalog_on_stock_eligible_register`
- `_catalogs_are_warehouse_axis`
- `_catalogs_for_axis_word`
- `_catalogs_for_warehouse_axis_word`
- `_intent_period_has_meaning`
- `_is_product_catalog_target`
- `_kind_is_stock_scoped`
- `_non_product_ref_targets`
- `_question_dictionary_axis_candidates`
- `_sort_stock_pool`
- `_stems_of_text`
- `_stock_corpus_counts`
- `_stock_corpus_receipt_side_penalty`
- `_stock_cost_side_penalty`
- `_stock_eligible_product_registers`
- `_stock_intent_signal`
- `_stock_place_axis_catalogs`
- `_stock_product_axis_col`
- `_stock_product_axis_cols`
- `_stock_product_targets_by_src`
- `_stock_qty_measure_candidates`
- `_stock_qty_measure_name`
- `_stock_receipt_candidates`
- `_stock_refs_by_src`
- `_stock_register_rank_key`
- `_stock_registers_with_product_axis`
- `_stock_scaffold_stems`
- `_word_names_documentjournal`
- `aggregate_count_intent`
- `balance_axis_registers_confirmed`
- `balance_capable_or_registers`
- `balance_capable_sources`
- `balance_map_rows`
- `balance_path_engaged`
- `balance_registers`
- `question_has_aggregate_total_marker`
- `question_mentions_warehouse_axis`
- `question_wants_per_axis_breakdown`
- `register_is_balance_noise`
- `registers_for_kind_axes`
- `resolved_unaccounted_slice_axis_word`
- `resolved_warehouse_axis_word`
- `secondary_axis_known`
- `state_path_active`
- `stock_asks_named_product`
- `stock_balance_is_reversal_noise`
- `stock_net_pair_candidates`
- `stock_net_register_pair`

### 14 clarify-memory (12/27)

- `_alias_parts`
- `_new_decision_id`
- `_purge_decisions`
- `_resolved_key`
- `_word_hits_text`
- `ambiguity_of_options`
- `choice_levels_proven`
- `db_fingerprint`
- `issue_decision`
- `options_version`
- `peek_decision`
- `question_fingerprint`

### 15 answer-atoms (5/13)

- `_atom_exact_value`
- `_fork_figures_of`
- `_period_window_human`
- `build_answer_atom`
- `render_atom_pair`

### 17 aggregate-groups (6/17)

- `_group_fold`
- `_live_column_exists`
- `_live_measure_date_col`
- `_live_std_excl_preds`
- `_sql_ident_col`
- `aggregate_live_column`

### 18 compose (2/19)

- `_group_value_by_name`
- `_measure_dimension`

### 19 answer-check (4/13)

- `_date_spans`
- `_plausible`
- `_readings`
- `_threshold_values`

### 20 ask-main-http (70/75)

- `_answer_checked_core`
- `_apply_sole_reading`
- `_ask_journal_write`
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
- `_measure_menu_opts`
- `_measure_native_index_freshness`
- `_onepath_compose_gate`
- `_opt_values`
- `_period_day_label`
- `_persist_ask_scope`
- `_reading_human_label`
- `_readings_to_opts`
- `_real_corpus_object_gaps`
- `_settle_axis`
- `_settle_measure`
- `_table_has_ref_key`
- `_vitrina_objects`
- `_wiki_named_entity`
- `ambiguous_labels`
- `answer`
- `answer_checked`
- `apply_prior_period`
- `build_period_empty_answer`
- `clarify_choice_line`
- `clarify_choice_prompt`
- `clarify_opts_response`
- `clarify_say`
- `dates_outside_period_filter`
- `disambiguate_labels`
- `empty_after_period_action`
- `format_clarify_options`
- `format_period_empty_text`
- `gate`
- `gate_out`
- `label_has_meta_src`
- `label_with_kind`
- `live_src_counts`
- `main`
- `opts_hints`
- `period_empty_outcome`
- `period_is_canon_guess`
- `period_slot_for_inherit`
- `rows_seen`
- `without_list_markers`

### 21 wiki-choice (49/52)

- `_card_odata_kind`
- `_homonym_keys`
- `_homonym_norm`
- `_named_type_phrase_patterns`
- `_norm_ye`
- `_wiki_axis_has_carriers`
- `_wiki_hybrid_sql`
- `_wiki_hybrid_vars`
- `_wiki_parse_axes_set`
- `_wiki_parse_measures_set`
- `_wiki_passport_sql`
- `_wiki_row_to_verdict`
- `_wiki_salvage_verdicts`
- `_wiki_sanitize_why`
- `_wiki_substitute_passport_sql`
- `_wiki_substitute_sql`
- `_wiki_verdicts_for_diag`
- `_wiki_verdicts_from_rows`
- `filter_pool_by_named_type`
- `named_platform_kinds`
- `try_wiki_hybrid_entity_pick`
- `wiki_action_axis`
- `wiki_action_class`
- `wiki_aggregate_want`
- `wiki_axis_is_question_subject`
- `wiki_axis_phrase`
- `wiki_caption_leaks`
- `wiki_captions_map_from_cards`
- `wiki_format_card_lines`
- `wiki_format_passport_lines`
- `wiki_homonym_kind_peers`
- `wiki_human_menu_caption`
- `wiki_human_menu_hint`
- `wiki_hybrid_pool`
- `wiki_intent_named_measures`
- `wiki_knn_separable`
- `wiki_leader_carries_axis`
- `wiki_leader_post_verify`
- `wiki_measure_carried`
- `wiki_menu_captions`
- `wiki_outcome_from_verify`
- `wiki_parse_verify_response`
- `wiki_passport_distinct`
- `wiki_passport_enrich`
- `wiki_pick_from_cards`
- `wiki_platform_kind`
- `wiki_strip_passport_yaml`
- `wiki_validate_leader_axes`
- `wiki_verify_candidates`

### 22 health-tick (1/2)

- `_parse_tick_status_note`

## Чтение окружения

Всего: 91.

| переменная | строка | умолчание | функция |
|---|---:|---|---|
| `SERENEDB_DSN_RO` | [7](ubuntu/serenedb/ask/:7) | — | `(модуль)` |
| `PGPASSWORD` | [8](ubuntu/serenedb/ask/:8) | "" | `(модуль)` |
| `RESOLVER_DSN` | [14](ubuntu/serenedb/ask/:14) | "" | `(модуль)` |
| `RESOLVER_PW` | [15](ubuntu/serenedb/ask/:15) | "" | `(модуль)` |
| `ASK_LISTEN_HOST` | [16](ubuntu/serenedb/ask/:16) | "127.0.0.1" | `(модуль)` |
| `ASK_LISTEN_PORT` | [17](ubuntu/serenedb/ask/:17) | "8091" | `(модуль)` |
| `ASK_DEADLINE_SEC` | [21](ubuntu/serenedb/ask/:21) | "88" | `(модуль)` |
| `ASK_TOKEN` | [22](ubuntu/serenedb/ask/:22) | "" | `(модуль)` |
| `ASK_MONEY_UNIT` | [23](ubuntu/serenedb/ask/:23) | "" | `(модуль)` |
| `ASK_CARD_TABLE` | [34](ubuntu/serenedb/ask/:34) | "search_entity_card" | `(модуль)` |
| `ASK_PICK_BUDGET_CHARS` | [40](ubuntu/serenedb/ask/:40) | "8000" | `(модуль)` |
| `ASK_ROWS_BUDGET_CHARS` | [47](ubuntu/serenedb/ask/:47) | "24000" | `(модуль)` |
| `ASK_COVERAGE_TOP` | [54](ubuntu/serenedb/ask/:54) | "15" | `(модуль)` |
| `ASK_STALE_WARN_SEC` | [58](ubuntu/serenedb/ask/:58) | "3600" | `(модуль)` |
| `ASK_TOPK` | [59](ubuntu/serenedb/ask/:59) | "40" | `(модуль)` |
| `ASK_TRACE` | [63](ubuntu/serenedb/ask/:63) | "1" | `(модуль)` |
| `ASK_ROWS_TO_MODEL` | [64](ubuntu/serenedb/ask/:64) | "25" | `(модуль)` |
| `ASK_SCORER` | [153](ubuntu/serenedb/ask/:153) | "bm25" | `(модуль)` |
| `ASK_REFS_BOOST` | [165](ubuntu/serenedb/ask/:165) | "8.0" | `(модуль)` |
| `RERANK_URL` | [187](ubuntu/serenedb/ask/:187) | — | `(модуль)` |
| `ALIBABA_RERANK_URL` | [188](ubuntu/serenedb/ask/:188) | — | `(модуль)` |
| `RERANK_MODEL` | [190](ubuntu/serenedb/ask/:190) | — | `(модуль)` |
| `ALIBABA_RERANK_MODEL` | [191](ubuntu/serenedb/ask/:191) | — | `(модуль)` |
| `RERANK_API` | [192](ubuntu/serenedb/ask/:192) | "<expr>" | `(модуль)` |
| `DEEPSEEK_BASE` | [204](ubuntu/serenedb/ask/:204) | "https://api.deepseek.com" | `(модуль)` |
| `DEEPSEEK_API_KEY` | [205](ubuntu/serenedb/ask/:205) | "" | `(модуль)` |
| `DEEPSEEK_MODEL` | [213](ubuntu/serenedb/ask/:213) | "deepseek-v4-pro" | `(модуль)` |
| `DEEPSEEK_THINKING` | [214](ubuntu/serenedb/ask/:214) | "disabled" | `(модуль)` |
| `ASK_THINKING_OFF_BODY` | [217](ubuntu/serenedb/ask/:217) | "" | `(модуль)` |
| `DS_REASONING_OFF` | [218](ubuntu/serenedb/ask/:218) | "" | `(модуль)` |
| `EMBED_BASE_URL` | [227](ubuntu/serenedb/ask/:227) | — | `(модуль)` |
| `ALIBABA_EMBED_URL` | [228](ubuntu/serenedb/ask/:228) | "" | `(модуль)` |
| `EMBED_API` | [234](ubuntu/serenedb/ask/:234) | "openai" | `(модуль)` |
| `EMBED_QUERY_PATH` | [235](ubuntu/serenedb/ask/:235) | "/embed" | `(модуль)` |
| `EMBED_UA` | [238](ubuntu/serenedb/ask/:238) | "curl/8.5.0" | `(модуль)` |
| `EMBED_HEALTH_URL` | [240](ubuntu/serenedb/ask/:240) | — | `(модуль)` |
| `EMBED_API_KEY` | [241](ubuntu/serenedb/ask/:241) | — | `(модуль)` |
| `ALIBABA_API_KEY` | [241](ubuntu/serenedb/ask/:241) | "" | `(модуль)` |
| `EMBED_MODEL` | [242](ubuntu/serenedb/ask/:242) | "text-embedding-v4" | `(модуль)` |
| `RERANK_API_KEY` | [245](ubuntu/serenedb/ask/:245) | — | `(модуль)` |
| `EMBED_DIM` | [253](ubuntu/serenedb/ask/:253) | "1024" | `(модуль)` |
| `EMBED_PATH` | [265](ubuntu/serenedb/ask/:265) | "/v1/embeddings" | `(модуль)` |
| `ASK_EMBED_NATIVE` | [266](ubuntu/serenedb/ask/:266) | "0" | `(модуль)` |
| `ASK_NO_DATA_TEXT` | [277](ubuntu/serenedb/ask/:277) | "" | `(модуль)` |
| `ASK_TOTAL_TEXT` | [278](ubuntu/serenedb/ask/:278) | "" | `(модуль)` |
| `ASK_STALE_TEXT` | [281](ubuntu/serenedb/ask/:281) | "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад." | `(модуль)` |
| `ASK_EMB_CACHE` | [603](ubuntu/serenedb/ask/:603) | "256" | `(модуль)` |
| `ASK_EMB_RETRY` | [607](ubuntu/serenedb/ask/:607) | "2" | `(модуль)` |
| `ASK_EMB_RETRY_PAUSE` | [608](ubuntu/serenedb/ask/:608) | "0.4" | `(модуль)` |
| `ASK_EMB_TIMEOUT` | [609](ubuntu/serenedb/ask/:609) | "60" | `(модуль)` |
| `ASK_INTENT_MAX_TOKENS` | [840](ubuntu/serenedb/ask/:840) | "400" | `(модуль)` |
| `ASK_INTENT_SAMPLES` | [841](ubuntu/serenedb/ask/:841) | "5" | `(модуль)` |
| `ASK_INTENT_LEAD` | [842](ubuntu/serenedb/ask/:842) | "3" | `(модуль)` |
| `ASK_INTENT_MEMO` | [844](ubuntu/serenedb/ask/:844) | "512" | `(модуль)` |
| `ASK_INTENT_GROUPS` | [851](ubuntu/serenedb/ask/:851) | "6" | `(модуль)` |
| `ASK_INTENT_ALTS` | [852](ubuntu/serenedb/ask/:852) | "6" | `(модуль)` |
| `ASK_STEM_DICT` | [855](ubuntu/serenedb/ask/:855) | "search_dict_stem" | `(модуль)` |
| `ASK_SOLR_SYNONYMS` | [858](ubuntu/serenedb/ask/:858) | "0" | `(модуль)` |
| `ASK_SOLR_SYNONYMS_DICT` | [859](ubuntu/serenedb/ask/:859) | "" | `(модуль)` |
| `ASK_CALENDAR_AXIS` | [59](ubuntu/serenedb/ask/:59) | "0" | `(модуль)` |
| `ASK_CURRENCY_AXIS` | [60](ubuntu/serenedb/ask/:60) | "0" | `(модуль)` |
| `ASK_SALES_RANK_CANON` | [62](ubuntu/serenedb/ask/:62) | "0" | `(модуль)` |
| `ASK_ATOM_TERMINAL` | [64](ubuntu/serenedb/ask/:64) | "0" | `(модуль)` |
| `ASK_ENTITY_FORM` | [67](ubuntu/serenedb/ask/:67) | "0" | `(модуль)` |
| `ASK_RESOLVE_NEAR` | [369](ubuntu/serenedb/ask/:369) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [370](ubuntu/serenedb/ask/:370) | "3" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [34](ubuntu/serenedb/ask/:34) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [39](ubuntu/serenedb/ask/:39) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [44](ubuntu/serenedb/ask/:44) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [47](ubuntu/serenedb/ask/:47) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [48](ubuntu/serenedb/ask/:48) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [53](ubuntu/serenedb/ask/:53) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [54](ubuntu/serenedb/ask/:54) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_MEANING_TOP` | [135](ubuntu/serenedb/ask/:135) | "0" | `(модуль)` |
| `ASK_JOURNAL` | [245](ubuntu/serenedb/ask/:245) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [250](ubuntu/serenedb/ask/:250) | "1" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [262](ubuntu/serenedb/ask/:262) | "600" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [145](ubuntu/serenedb/ask/:145) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [511](ubuntu/serenedb/ask/:511) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [519](ubuntu/serenedb/ask/:519) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [520](ubuntu/serenedb/ask/:520) | "search_idx" | `(модуль)` |
| `ASK_AMBIG_TTL` | [847](ubuntu/serenedb/ask/:847) | "300" | `(модуль)` |
| `ASK_SLOT_COVER` | [2314](ubuntu/serenedb/ask/:2314) | "0" | `(модуль)` |
| `WIKI_KNN_N` | [9](ubuntu/serenedb/ask/:9) | "15" | `(модуль)` |
| `WIKI_PICK_N` | [14](ubuntu/serenedb/ask/:14) | "8" | `(модуль)` |
| `WIKI_ALIAS_TOP` | [15](ubuntu/serenedb/ask/:15) | "3" | `(модуль)` |
| `WIKI_PASSPORT_N` | [21](ubuntu/serenedb/ask/:21) | "8" | `(модуль)` |
| `WIKI_VERIFY_MAX_TOKENS` | [22](ubuntu/serenedb/ask/:22) | "2048" | `(модуль)` |
| `WIKI_PASSPORT_BODY_MAX` | [23](ubuntu/serenedb/ask/:23) | "1500" | `(модуль)` |
| `WIKI_SEP_GAP` | [24](ubuntu/serenedb/ask/:24) | "0.04" | `(модуль)` |
| `WIKI_EMBED_MAXLEN` | [25](ubuntu/serenedb/ask/:25) | "20000" | `(модуль)` |

## Обращения наружу

Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`.

### psql (118)

- [`ubuntu/serenedb/ask/:395`](ubuntu/serenedb/ask/:395) в `emb_ready`
- [`ubuntu/serenedb/ask/:623`](ubuntu/serenedb/ask/:623) в `_ensure_embed_secret`
- [`ubuntu/serenedb/ask/:638`](ubuntu/serenedb/ask/:638) в `_ensure_embed_secret`
- [`ubuntu/serenedb/ask/:657`](ubuntu/serenedb/ask/:657) в `_embed_one_native`
- [`ubuntu/serenedb/ask/:168`](ubuntu/serenedb/ask/:168) в `same_concept_groups`
- [`ubuntu/serenedb/ask/:286`](ubuntu/serenedb/ask/:286) в `_base_business_topic_words`
- [`ubuntu/serenedb/ask/:422`](ubuntu/serenedb/ask/:422) в `_base_knows_kind_or_measure`
- [`ubuntu/serenedb/ask/:363`](ubuntu/serenedb/ask/:363) в `period_relative_forms`
- [`ubuntu/serenedb/ask/:17`](ubuntu/serenedb/ask/:17) в `calendar_registers`
- [`ubuntu/serenedb/ask/:33`](ubuntu/serenedb/ask/:33) в `calendar_working_day_keys`
- [`ubuntu/serenedb/ask/:53`](ubuntu/serenedb/ask/:53) в `calendar_map_rows`
- [`ubuntu/serenedb/ask/:93`](ubuntu/serenedb/ask/:93) в `calendar_day_basis_phrases`
- [`ubuntu/serenedb/ask/:31`](ubuntu/serenedb/ask/:31) в `currency_catalogs`
- [`ubuntu/serenedb/ask/:47`](ubuntu/serenedb/ask/:47) в `currency_rate_registers`
- [`ubuntu/serenedb/ask/:63`](ubuntu/serenedb/ask/:63) в `accounting_currency_key`
- [`ubuntu/serenedb/ask/:79`](ubuntu/serenedb/ask/:79) в `currency_map_rows`
- [`ubuntu/serenedb/ask/:117`](ubuntu/serenedb/ask/:117) в `currency_rate_map_rows`
- [`ubuntu/serenedb/ask/:165`](ubuntu/serenedb/ask/:165) в `currency_basis_from_labels`
- [`ubuntu/serenedb/ask/:339`](ubuntu/serenedb/ask/:339) в `currency_fx_probe`
- [`ubuntu/serenedb/ask/:365`](ubuntu/serenedb/ask/:365) в `currency_unit_for_ref`
- [`ubuntu/serenedb/ask/:389`](ubuntu/serenedb/ask/:389) в `currency_unit_for_reading`
- [`ubuntu/serenedb/ask/:416`](ubuntu/serenedb/ask/:416) в `currency_ref_requested`
- [`ubuntu/serenedb/ask/:434`](ubuntu/serenedb/ask/:434) в `currency_ref_requested`
- [`ubuntu/serenedb/ask/:425`](ubuntu/serenedb/ask/:425) в `currency_ref_requested`
- [`ubuntu/serenedb/ask/:314`](ubuntu/serenedb/ask/:314) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/ask/:348`](ubuntu/serenedb/ask/:348) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/ask/:527`](ubuntu/serenedb/ask/:527) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/ask/:86`](ubuntu/serenedb/ask/:86) в `probe`
- [`ubuntu/serenedb/ask/:189`](ubuntu/serenedb/ask/:189) в `match_expr`
- [`ubuntu/serenedb/ask/:216`](ubuntu/serenedb/ask/:216) в `tables_of`
- [`ubuntu/serenedb/ask/:267`](ubuntu/serenedb/ask/:267) в `alias_hits`
- [`ubuntu/serenedb/ask/:307`](ubuntu/serenedb/ask/:307) в `card_hits`
- [`ubuntu/serenedb/ask/:17`](ubuntu/serenedb/ask/:17) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/ask/:97`](ubuntu/serenedb/ask/:97) в `_fused_sql_rrf`
- [`ubuntu/serenedb/ask/:105`](ubuntu/serenedb/ask/:105) в `_fused_python_rrf`
- [`ubuntu/serenedb/ask/:206`](ubuntu/serenedb/ask/:206) в `near_tables`
- [`ubuntu/serenedb/ask/:242`](ubuntu/serenedb/ask/:242) в `rows_of`
- [`ubuntu/serenedb/ask/:435`](ubuntu/serenedb/ask/:435) в `_resolve_values_corpus`
- [`ubuntu/serenedb/ask/:150`](ubuntu/serenedb/ask/:150) в `measures_of`
- [`ubuntu/serenedb/ask/:160`](ubuntu/serenedb/ask/:160) в `measures_of`
- [`ubuntu/serenedb/ask/:175`](ubuntu/serenedb/ask/:175) в `measure_aliases_of`
- [`ubuntu/serenedb/ask/:216`](ubuntu/serenedb/ask/:216) в `totals_of`
- [`ubuntu/serenedb/ask/:278`](ubuntu/serenedb/ask/:278) в `_measures_by_src`
- [`ubuntu/serenedb/ask/:132`](ubuntu/serenedb/ask/:132) в `rank_axis_label_rows`
- [`ubuntu/serenedb/ask/:65`](ubuntu/serenedb/ask/:65) в `_stock_place_axis_catalogs`
- [`ubuntu/serenedb/ask/:100`](ubuntu/serenedb/ask/:100) в `_catalog_on_stock_eligible_register`
- [`ubuntu/serenedb/ask/:209`](ubuntu/serenedb/ask/:209) в `_word_names_documentjournal`
- [`ubuntu/serenedb/ask/:424`](ubuntu/serenedb/ask/:424) в `registers_for_kind_axes`
- [`ubuntu/serenedb/ask/:490`](ubuntu/serenedb/ask/:490) в `balance_registers`
- [`ubuntu/serenedb/ask/:508`](ubuntu/serenedb/ask/:508) в `balance_map_rows`
- [`ubuntu/serenedb/ask/:561`](ubuntu/serenedb/ask/:561) в `_stock_registers_with_product_axis`
- [`ubuntu/serenedb/ask/:582`](ubuntu/serenedb/ask/:582) в `_stock_product_targets_by_src`
- [`ubuntu/serenedb/ask/:603`](ubuntu/serenedb/ask/:603) в `_stock_refs_by_src`
- [`ubuntu/serenedb/ask/:651`](ubuntu/serenedb/ask/:651) в `_stock_corpus_counts`
- [`ubuntu/serenedb/ask/:863`](ubuntu/serenedb/ask/:863) в `stock_net_register_menu_opts`
- [`ubuntu/serenedb/ask/:842`](ubuntu/serenedb/ask/:842) в `stock_net_register_menu_opts`
- [`ubuntu/serenedb/ask/:929`](ubuntu/serenedb/ask/:929) в `aggregate_stock_net_distinct`
- [`ubuntu/serenedb/ask/:949`](ubuntu/serenedb/ask/:949) в `_stems_of_text`
- [`ubuntu/serenedb/ask/:169`](ubuntu/serenedb/ask/:169) в `db_fingerprint`
- [`ubuntu/serenedb/ask/:45`](ubuntu/serenedb/ask/:45) в `_live_measure_date_col`
- [`ubuntu/serenedb/ask/:63`](ubuntu/serenedb/ask/:63) в `_live_column_exists`
- [`ubuntu/serenedb/ask/:122`](ubuntu/serenedb/ask/:122) в `aggregate_live_column`
- [`ubuntu/serenedb/ask/:230`](ubuntu/serenedb/ask/:230) в `aggregate`
- [`ubuntu/serenedb/ask/:286`](ubuntu/serenedb/ask/:286) в `src_is_child`
- [`ubuntu/serenedb/ask/:298`](ubuntu/serenedb/ask/:298) в `refcols_of`
- [`ubuntu/serenedb/ask/:327`](ubuntu/serenedb/ask/:327) в `kind_axis_hits`
- [`ubuntu/serenedb/ask/:364`](ubuntu/serenedb/ask/:364) в `kind_axis_rerank`
- [`ubuntu/serenedb/ask/:396`](ubuntu/serenedb/ask/:396) в `term_axis_hits`
- [`ubuntu/serenedb/ask/:513`](ubuntu/serenedb/ask/:513) в `aggregate_groups`
- [`ubuntu/serenedb/ask/:22`](ubuntu/serenedb/ask/:22) в `axis_clarify_options`
- [`ubuntu/serenedb/ask/:464`](ubuntu/serenedb/ask/:464) в `_table_label`
- [`ubuntu/serenedb/ask/:395`](ubuntu/serenedb/ask/:395) в `_entity_counts_objects`
- [`ubuntu/serenedb/ask/:403`](ubuntu/serenedb/ask/:403) в `_entity_counts_objects`
- [`ubuntu/serenedb/ask/:415`](ubuntu/serenedb/ask/:415) в `_vitrina_objects`
- [`ubuntu/serenedb/ask/:423`](ubuntu/serenedb/ask/:423) в `_vitrina_objects`
- [`ubuntu/serenedb/ask/:447`](ubuntu/serenedb/ask/:447) в `_coverage_of`
- [`ubuntu/serenedb/ask/:484`](ubuntu/serenedb/ask/:484) в `_coverage_of`
- [`ubuntu/serenedb/ask/:457`](ubuntu/serenedb/ask/:457) в `_coverage_of`
- [`ubuntu/serenedb/ask/:574`](ubuntu/serenedb/ask/:574) в `_measure_health_gap`
- [`ubuntu/serenedb/ask/:593`](ubuntu/serenedb/ask/:593) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/ask/:614`](ubuntu/serenedb/ask/:614) в `_classify_health_gap`
- [`ubuntu/serenedb/ask/:669`](ubuntu/serenedb/ask/:669) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/ask/:767`](ubuntu/serenedb/ask/:767) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:776`](ubuntu/serenedb/ask/:776) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:959`](ubuntu/serenedb/ask/:959) в `ambiguous_labels`
- [`ubuntu/serenedb/ask/:1005`](ubuntu/serenedb/ask/:1005) в `opts_hints`
- [`ubuntu/serenedb/ask/:1012`](ubuntu/serenedb/ask/:1012) в `opts_hints`
- [`ubuntu/serenedb/ask/:1022`](ubuntu/serenedb/ask/:1022) в `opts_hints`
- [`ubuntu/serenedb/ask/:1032`](ubuntu/serenedb/ask/:1032) в `opts_hints`
- [`ubuntu/serenedb/ask/:1112`](ubuntu/serenedb/ask/:1112) в `live_src_counts`
- [`ubuntu/serenedb/ask/:1196`](ubuntu/serenedb/ask/:1196) в `dates_outside_period_filter`
- [`ubuntu/serenedb/ask/:1492`](ubuntu/serenedb/ask/:1492) в `_measure_menu_opts`
- [`ubuntu/serenedb/ask/:2266`](ubuntu/serenedb/ask/:2266) в `answer`
- [`ubuntu/serenedb/ask/:2282`](ubuntu/serenedb/ask/:2282) в `answer`
- [`ubuntu/serenedb/ask/:2325`](ubuntu/serenedb/ask/:2325) в `_journal_keep_n`
- [`ubuntu/serenedb/ask/:2349`](ubuntu/serenedb/ask/:2349) в `_journal_build_ts`
- [`ubuntu/serenedb/ask/:2362`](ubuntu/serenedb/ask/:2362) в `_journal_alias_ver`
- [`ubuntu/serenedb/ask/:2596`](ubuntu/serenedb/ask/:2596) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2617`](ubuntu/serenedb/ask/:2617) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2610`](ubuntu/serenedb/ask/:2610) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2612`](ubuntu/serenedb/ask/:2612) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2619`](ubuntu/serenedb/ask/:2619) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2551`](ubuntu/serenedb/ask/:2551) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2600`](ubuntu/serenedb/ask/:2600) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2613`](ubuntu/serenedb/ask/:2613) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:2596`](ubuntu/serenedb/ask/:2596) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/ask/:2600`](ubuntu/serenedb/ask/:2600) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/ask/:2813`](ubuntu/serenedb/ask/:2813) в `Handler.do_GET`
- [`ubuntu/serenedb/ask/:2950`](ubuntu/serenedb/ask/:2950) в `Handler.do_POST`
- [`ubuntu/serenedb/ask/:338`](ubuntu/serenedb/ask/:338) в `wiki_hybrid_pool`
- [`ubuntu/serenedb/ask/:488`](ubuntu/serenedb/ask/:488) в `fork_labels_of`
- [`ubuntu/serenedb/ask/:513`](ubuntu/serenedb/ask/:513) в `fork_labels_covering`
- [`ubuntu/serenedb/ask/:651`](ubuntu/serenedb/ask/:651) в `wiki_passport_enrich`
- [`ubuntu/serenedb/ask/:1133`](ubuntu/serenedb/ask/:1133) в `try_wiki_hybrid_entity_pick`
- [`ubuntu/serenedb/ask/:1189`](ubuntu/serenedb/ask/:1189) в `try_wiki_hybrid_entity_pick`
- [`ubuntu/serenedb/ask/:1271`](ubuntu/serenedb/ask/:1271) в `wiki_leader_carries_axis`
- [`ubuntu/serenedb/ask/:1323`](ubuntu/serenedb/ask/:1323) в `wiki_measure_carried`
- [`ubuntu/serenedb/ask/:25`](ubuntu/serenedb/ask/:25) в `_measure_tick_status`

### ds_chat (8)

- [`ubuntu/serenedb/ask/:576`](ubuntu/serenedb/ask/:576) в `_one_intent`
- [`ubuntu/serenedb/ask/:584`](ubuntu/serenedb/ask/:584) в `_one_intent`
- [`ubuntu/serenedb/ask/:280`](ubuntu/serenedb/ask/:280) в `refuse_text`
- [`ubuntu/serenedb/ask/:184`](ubuntu/serenedb/ask/:184) в `rank_axis_pick`
- [`ubuntu/serenedb/ask/:824`](ubuntu/serenedb/ask/:824) в `compose`
- [`ubuntu/serenedb/ask/:796`](ubuntu/serenedb/ask/:796) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:974`](ubuntu/serenedb/ask/:974) в `wiki_verify_candidates`
- [`ubuntu/serenedb/ask/:1038`](ubuntu/serenedb/ask/:1038) в `wiki_pick_from_cards`

### embed_one (1)

- [`ubuntu/serenedb/ask/:10`](ubuntu/serenedb/ask/:10) в `_vec`

### rerank (3)

- [`ubuntu/serenedb/ask/:499`](ubuntu/serenedb/ask/:499) в `resolve_values`
- [`ubuntu/serenedb/ask/:157`](ubuntu/serenedb/ask/:157) в `rank_axes_rerank`
- [`ubuntu/serenedb/ask/:374`](ubuntu/serenedb/ask/:374) в `kind_axis_rerank`

### urlopen (4)

- [`ubuntu/serenedb/ask/:371`](ubuntu/serenedb/ask/:371) в `embed_model_live`
- [`ubuntu/serenedb/ask/:554`](ubuntu/serenedb/ask/:554) в `ds_chat_post`
- [`ubuntu/serenedb/ask/:728`](ubuntu/serenedb/ask/:728) в `embed_one`
- [`ubuntu/serenedb/ask/:324`](ubuntu/serenedb/ask/:324) в `rerank`
