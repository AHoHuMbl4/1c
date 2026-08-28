# Карта `ubuntu/serenedb/ask/`

Сгенерировано `ubuntu/serenedb/code_map.py`. Строк файла: **17449**. Функций: **511**. Зон: **20**. Сквозных (≥3 зон-вызывающих): **38**.

Границы зон — по якорям (`start`[/`end`] в `docs/audit/zones.json`), номера строк вычисляются при каждом прогоне.

## Оглавление зон

- [01 infra-trace-llm](ubuntu/serenedb/ask/z01_infra_trace_llm.py:1) — Инфра, TRACE, LLM (якорь `_new_rid` … `embed_one`; `1–871`)
- [02 intent](ubuntu/serenedb/ask/z02_intent.py:1) — Intent (якорь `_json_blocks` … `_first_intent_object`; `1–478`)
- [03 period-windows](ubuntu/serenedb/ask/z03_period_windows.py:1) — Периоды и окна (якорь `_num_pred` … `apply_period_leader`; `1–459`)
- [04 calendar-axis](ubuntu/serenedb/ask/z04_calendar_axis.py:1) — Календарная ось (якорь `_sql_ident` … `_working_day_doc_preds`; `1–194`)
- [05 entity-form](ubuntu/serenedb/ask/z05_entity_form.py:1) — Форма сущности (якорь `entity_form_rank_single_window` … `aggregate_compare_sales`; `1–1147`)
- [06 entity-search](ubuntu/serenedb/ask/z06_entity_search.py:1) — Поиск сущностей (якорь `_predicates` … `meaning_candidates`; `1–549`)
- [07 rrf-vectors](ubuntu/serenedb/ask/z07_rrf_vectors.py:1) — RRF и векторы (якорь `_corpus_ivf_ready` … `_ngrams`; `1–604`)
- [08 measures-totals](ubuntu/serenedb/ask/z08_measures_totals.py:1) — Меры и итоги (якорь `_shares_chars` … `totals_of`; `1–261`)
- [09 fork-detector](ubuntu/serenedb/ask/z09_fork_detector.py:1) — Детектор развилки (якорь `_measures_by_src` … `_class_label_lookup`; `1–807`)
- [10 rank](ubuntu/serenedb/ask/z10_rank.py:1) — Ранг (якорь `count_question_skips_axis` … `prefer_entity_for_rank`; `1–495`)
- [11 sales](ubuntu/serenedb/ask/z11_sales.py:1) — Продажи (якорь `sales_sum_intent` … `period_zero_why_question`; `1–768`)
- [12 stock-balance](ubuntu/serenedb/ask/z12_stock_balance.py:1) — Остатки (якорь `grain_dec_from_axis_ticket` … `balance_bridge_clarify`; `1–305`)
- [13 fork-outcomes](ubuntu/serenedb/ask/z13_fork_outcomes.py:1) — Исходы развилки (якорь `stock_balance_is_sales_noise` … `fork_outcome_c`; `1–511`)
- [14 clarify-memory](ubuntu/serenedb/ask/z14_clarify_memory.py:1) — Уточнение и память (якорь `_alias_parts` … `guards_skip_for_choice`; `1–717`)
- [15 answer-atoms](ubuntu/serenedb/ask/z15_answer_atoms.py:1) — Атомы ответа (якорь `stop2_active` … `fill_atom_pairs`; `1–437`)
- [16 veto-pick-entity](ubuntu/serenedb/ask/z16_veto_pick_entity.py:1) — Вето и выбор сущности (якорь `pair_slots_only` … `pick_entity`; `1–841`)
- [17 aggregate-groups](ubuntu/serenedb/ask/z17_aggregate_groups.py:1) — Агрегаты и группы (якорь `_vec` … `aggregate_groups`; `1–514`)
- [18 compose](ubuntu/serenedb/ask/z18_compose.py:1) — Формулировка (якорь `merge_period2_groups` … `compose`; `1–904`)
- [19 answer-check](ubuntu/serenedb/ask/z19_answer_check.py:1) — Проверка ответа (якорь `_readings` … `_filter_values`; `1–412`)
- [20 ask-main-http](ubuntu/serenedb/ask/z20_ask_main_http.py:1) — ask / HTTP (якорь `_filter_dates` … `Handler`; `1–6175`)

## Таблица зон

| id | slug | start | строк | функций | входящих зон | исходящих зон | внутренних |
|---|---|---|---:|---:|---:|---:|---:|
| 01 | infra-trace-llm | `_new_rid` | 871 | 29 | 19 | 0 | 11 |
| 02 | intent | `_json_blocks` | 478 | 15 | 4 | 1 | 10 |
| 03 | period-windows | `_num_pred` | 459 | 21 | 5 | 3 | 5 |
| 04 | calendar-axis | `_sql_ident` | 194 | 11 | 3 | 2 | 7 |
| 05 | entity-form | `entity_form_rank_single_window` | 1147 | 43 | 3 | 12 | 22 |
| 06 | entity-search | `_predicates` | 549 | 16 | 3 | 3 | 4 |
| 07 | rrf-vectors | `_corpus_ivf_ready` | 604 | 18 | 9 | 4 | 7 |
| 08 | measures-totals | `_shares_chars` | 261 | 4 | 5 | 3 | 0 |
| 09 | fork-detector | `_measures_by_src` | 807 | 29 | 4 | 10 | 16 |
| 10 | rank | `count_question_skips_axis` | 495 | 15 | 6 | 7 | 6 |
| 11 | sales | `sales_sum_intent` | 768 | 28 | 5 | 7 | 7 |
| 12 | stock-balance | `grain_dec_from_axis_ticket` | 305 | 16 | 4 | 6 | 6 |
| 13 | fork-outcomes | `stock_balance_is_sales_noise` | 511 | 19 | 2 | 8 | 9 |
| 14 | clarify-memory | `_alias_parts` | 717 | 35 | 9 | 3 | 16 |
| 15 | answer-atoms | `stop2_active` | 437 | 12 | 6 | 4 | 2 |
| 16 | veto-pick-entity | `pair_slots_only` | 841 | 29 | 3 | 11 | 5 |
| 17 | aggregate-groups | `_vec` | 514 | 16 | 10 | 3 | 2 |
| 18 | compose | `merge_period2_groups` | 904 | 22 | 6 | 8 | 2 |
| 19 | answer-check | `_readings` | 412 | 14 | 3 | 2 | 5 |
| 20 | ask-main-http | `_filter_dates` | 6175 | 87 | 7 | 19 | 80 |

## 01. infra-trace-llm — Инфра, TRACE, LLM

Якорь: `_new_rid`, end `embed_one`. Участок: [`ubuntu/serenedb/ask/z01_infra_trace_llm.py:1`](ubuntu/serenedb/ask/z01_infra_trace_llm.py:1)–`871`.

Функций: 29. Входящие зоны: 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20. Исходящие зоны: —.

Функции:

- [`_new_rid`](ubuntu/serenedb/ask/:70) `70–71` len=2
- [`_rid_norm`](ubuntu/serenedb/ask/:74) `74–79` len=6
- [`_rid_get`](ubuntu/serenedb/ask/:82) `82–83` len=2
- [`_rid_enter`](ubuntu/serenedb/ask/:86) `86–89` len=4
- [`_trace_write`](ubuntu/serenedb/ask/:92) `92–96` len=5
- [`_embed_secret_name_from_env`](ubuntu/serenedb/ask/:232) `232–236` len=5
- [`_reload_embed_native_env`](ubuntu/serenedb/ask/:246) `246–252` len=7
- [`psql`](ubuntu/serenedb/ask/:271) `271–305` len=35
- [`lit`](ubuntu/serenedb/ask/:308) `308–309` len=2
- [`_embed_host_base`](ubuntu/serenedb/ask/:312) `312–315` len=4
- [`embed_model_live`](ubuntu/serenedb/ask/:335) `335–365` len=31
- [`emb_ready`](ubuntu/serenedb/ask/:368) `368–386` len=19
- [`_fmt`](ubuntu/serenedb/ask/:389) `389–395` len=7
- [`_src_tag`](ubuntu/serenedb/ask/:398) `398–402` len=5
- [`_fmt_gate_bad`](ubuntu/serenedb/ask/:405) `405–411` len=7
- [`_gate_bad_preview`](ubuntu/serenedb/ask/:414) `414–418` len=5
- [`_fmt_human`](ubuntu/serenedb/ask/:421) `421–435` len=15
- [`_token_acc_start`](ubuntu/serenedb/ask/:474) `474–475` len=2
- [`_token_acc_record`](ubuntu/serenedb/ask/:478) `478–492` len=15
- [`_diag_pack`](ubuntu/serenedb/ask/:495) `495–501` len=7
- [`_ds_chat_content`](ubuntu/serenedb/ask/:504) `504–517` len=14
- [`_ds_chat_body`](ubuntu/serenedb/ask/:520) `520–528` len=9
- [`ds_chat_post`](ubuntu/serenedb/ask/:531) `531–539` len=9
- [`ds_chat`](ubuntu/serenedb/ask/:542) `542–543` len=2
- [`arbitrate`](ubuntu/serenedb/ask/:566) `566–592` len=27
- [`_embed_request`](ubuntu/serenedb/ask/:595) `595–608` len=14
- [`_ensure_embed_secret`](ubuntu/serenedb/ask/:624) `624–655` len=32
- [`_embed_one_native`](ubuntu/serenedb/ask/:658) `658–692` len=35
- [`embed_one`](ubuntu/serenedb/ask/:695) `695–757` len=63

Зовут снаружи зоны: `_diag_pack`, `_fmt`, `_fmt_gate_bad`, `_fmt_human`, `_gate_bad_preview`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_src_tag`, `_token_acc_start`, `_trace_write`, `arbitrate`, `ds_chat`, `emb_ready`, `embed_model_live`, `embed_one`, `lit`, `psql`

## 02. intent — Intent

Якорь: `_json_blocks`, end `_first_intent_object`. Участок: [`ubuntu/serenedb/ask/z02_intent.py:1`](ubuntu/serenedb/ask/z02_intent.py:1)–`478`.

Функций: 15. Входящие зоны: 12, 14, 16, 20. Исходящие зоны: 01.

Функции:

- [`_json_blocks`](ubuntu/serenedb/ask/:9) `9–36` len=28
- [`_intent_text`](ubuntu/serenedb/ask/:39) `39–50` len=12
- [`_intent_number`](ubuntu/serenedb/ask/:53) `53–69` len=17
- [`_intent_date`](ubuntu/serenedb/ask/:72) `72–85` len=14
- [`_intent_terms`](ubuntu/serenedb/ask/:88) `88–124` len=37
- [`_intent_word`](ubuntu/serenedb/ask/:127) `127–129` len=3
- [`same_concept_groups`](ubuntu/serenedb/ask/:156) `156–195` len=40
- [`_stem_set`](ubuntu/serenedb/ask/:198) `198–205` len=8
- [`_normalize_intent`](ubuntu/serenedb/ask/:208) `208–328` len=121
- [`_one_intent`](ubuntu/serenedb/ask/:331) `331–347` len=17
- [`_field_key`](ubuntu/serenedb/ask/:350) `350–351` len=2
- [`_field_lead`](ubuntu/serenedb/ask/:354) `354–362` len=9
- [`_merge_intents`](ubuntu/serenedb/ask/:365) `365–389` len=25
- [`parse_intent`](ubuntu/serenedb/ask/:392) `392–451` len=60
- [`_first_intent_object`](ubuntu/serenedb/ask/:454) `454–473` len=20

Зовут снаружи зоны: `_intent_number`, `_intent_text`, `_intent_word`, `_stem_set`, `parse_intent`

## 03. period-windows — Периоды и окна

Якорь: `_num_pred`, end `apply_period_leader`. Участок: [`ubuntu/serenedb/ask/z03_period_windows.py:1`](ubuntu/serenedb/ask/z03_period_windows.py:1)–`459`.

Функций: 21. Входящие зоны: 04, 05, 06, 09, 20. Исходящие зоны: 01, 04, 20.

Функции:

- [`_num_pred`](ubuntu/serenedb/ask/:9) `9–27` len=19
- [`period_preds`](ubuntu/serenedb/ask/:30) `30–46` len=17
- [`_calendar_date`](ubuntu/serenedb/ask/:77) `77–82` len=6
- [`_month_range`](ubuntu/serenedb/ask/:85) `85–92` len=8
- [`_quarter_range`](ubuntu/serenedb/ask/:95) `95–104` len=10
- [`_week_range_monday`](ubuntu/serenedb/ask/:107) `107–111` len=5
- [`_prev_week_range`](ubuntu/serenedb/ask/:114) `114–122` len=9
- [`_is_seven_day_span`](ubuntu/serenedb/ask/:125) `125–129` len=5
- [`_is_current_calendar_week`](ubuntu/serenedb/ask/:132) `132–139` len=8
- [`_assumed_sliding_week_not_calendar`](ubuntu/serenedb/ask/:142) `142–152` len=11
- [`_iso_date`](ubuntu/serenedb/ask/:155) `155–156` len=2
- [`_period_origin`](ubuntu/serenedb/ask/:159) `159–170` len=12
- [`window_fp_of`](ubuntu/serenedb/ask/:173) `173–184` len=12
- [`_period_form_id`](ubuntu/serenedb/ask/:187) `187–211` len=25
- [`_window_reading`](ubuntu/serenedb/ask/:214) `214–236` len=23
- [`period_readings`](ubuntu/serenedb/ask/:239) `239–327` len=89
- [`render_window_label`](ubuntu/serenedb/ask/:330) `330–348` len=19
- [`prefer_window_leader`](ubuntu/serenedb/ask/:355) `355–371` len=17
- [`period_relative_forms`](ubuntu/serenedb/ask/:374) `374–403` len=30
- [`period_form_from_question`](ubuntu/serenedb/ask/:406) `406–416` len=11
- [`apply_period_leader`](ubuntu/serenedb/ask/:419) `419–455` len=37

Зовут снаружи зоны: `_calendar_date`, `_iso_date`, `_month_range`, `_num_pred`, `_prev_week_range`, `_quarter_range`, `_week_range_monday`, `_window_reading`, `apply_period_leader`, `period_form_from_question`, `period_preds`, `period_readings`, `period_relative_forms`, `prefer_window_leader`, `render_window_label`, `window_fp_of`

## 04. calendar-axis — Календарная ось

Якорь: `_sql_ident`, end `_working_day_doc_preds`. Участок: [`ubuntu/serenedb/ask/z04_calendar_axis.py:1`](ubuntu/serenedb/ask/z04_calendar_axis.py:1)–`194`.

Функций: 11. Входящие зоны: 03, 09, 20. Исходящие зоны: 01, 03.

Функции:

- [`_sql_ident`](ubuntu/serenedb/ask/:9) `9–11` len=3
- [`calendar_registers`](ubuntu/serenedb/ask/:14) `14–27` len=14
- [`calendar_working_day_keys`](ubuntu/serenedb/ask/:30) `30–44` len=15
- [`calendar_map_rows`](ubuntu/serenedb/ask/:47) `47–75` len=29
- [`calendar_axis_open`](ubuntu/serenedb/ask/:78) `78–83` len=6
- [`calendar_day_basis_prefer`](ubuntu/serenedb/ask/:86) `86–104` len=19
- [`_day_basis_reading`](ubuntu/serenedb/ask/:107) `107–113` len=7
- [`calendar_axis_readings`](ubuntu/serenedb/ask/:116) `116–131` len=16
- [`expand_readings_calendar_axis`](ubuntu/serenedb/ask/:134) `134–146` len=13
- [`prefer_day_basis_leader`](ubuntu/serenedb/ask/:149) `149–159` len=11
- [`_working_day_doc_preds`](ubuntu/serenedb/ask/:162) `162–190` len=29

Зовут снаружи зоны: `_working_day_doc_preds`, `calendar_axis_open`, `calendar_day_basis_prefer`, `expand_readings_calendar_axis`

## 05. entity-form — Форма сущности

Якорь: `entity_form_rank_single_window`, end `aggregate_compare_sales`. Участок: [`ubuntu/serenedb/ask/z05_entity_form.py:1`](ubuntu/serenedb/ask/z05_entity_form.py:1)–`1147`.

Функций: 43. Входящие зоны: 09, 11, 20. Исходящие зоны: 01, 03, 06, 07, 09, 10, 11, 13, 15, 17, 18, 20.

Функции:

- [`entity_form_rank_single_window`](ubuntu/serenedb/ask/:9) `9–36` len=28
- [`_months_mentioned`](ubuntu/serenedb/ask/:56) `56–74` len=19
- [`_yoy_compare_marker`](ubuntu/serenedb/ask/:77) `77–82` len=6
- [`_shift_date_years`](ubuntu/serenedb/ask/:85) `85–90` len=6
- [`_shift_period_years`](ubuntu/serenedb/ask/:93) `93–103` len=11
- [`sales_compare_split_month_pair`](ubuntu/serenedb/ask/:106) `106–127` len=22
- [`sales_compare_intent`](ubuntu/serenedb/ask/:130) `130–196` len=67
- [`sales_compare_windows`](ubuntu/serenedb/ask/:199) `199–283` len=85
- [`entity_form_catalogs_for_kind`](ubuntu/serenedb/ask/:287) `287–318` len=32
- [`entity_form_movements_for_kind`](ubuntu/serenedb/ask/:321) `321–358` len=38
- [`entity_form_count_target_is_movement`](ubuntu/serenedb/ask/:361) `361–396` len=36
- [`entity_form_expand_pool`](ubuntu/serenedb/ask/:399) `399–419` len=21
- [`event_kind_catalog_expand_pool`](ubuntu/serenedb/ask/:422) `422–462` len=41
- [`entity_form_rolling_year`](ubuntu/serenedb/ask/:465) `465–475` len=11
- [`entity_form_applicable`](ubuntu/serenedb/ask/:478) `478–512` len=35
- [`entity_form_collapse_guard`](ubuntu/serenedb/ask/:515) `515–528` len=14
- [`entity_form_pre_entity_ok`](ubuntu/serenedb/ask/:531) `531–545` len=15
- [`entity_form_atom_distinct`](ubuntu/serenedb/ask/:548) `548–558` len=11
- [`entity_form_atom_complement`](ubuntu/serenedb/ask/:561) `561–577` len=17
- [`_pick_kind_axis_col`](ubuntu/serenedb/ask/:582) `582–614` len=33
- [`live_axis_col_for_count`](ubuntu/serenedb/ask/:617) `617–642` len=26
- [`count_defer_measure_clarify`](ubuntu/serenedb/ask/:645) `645–653` len=9
- [`event_count_has_explicit_period`](ubuntu/serenedb/ask/:656) `656–666` len=11
- [`event_count_period_unspecified`](ubuntu/serenedb/ask/:669) `669–674` len=6
- [`event_count_has_live_axis`](ubuntu/serenedb/ask/:677) `677–698` len=22
- [`event_count_period_clarify_applies`](ubuntu/serenedb/ask/:701) `701–711` len=11
- [`event_count_period_option_readings`](ubuntu/serenedb/ask/:714) `714–734` len=21
- [`event_count_period_clarify`](ubuntu/serenedb/ask/:737) `737–760` len=24
- [`try_event_count_period_clarify`](ubuntu/serenedb/ask/:763) `763–772` len=10
- [`apply_proven_period`](ubuntu/serenedb/ask/:775) `775–793` len=19
- [`event_duel_applies`](ubuntu/serenedb/ask/:796) `796–812` len=17
- [`_event_distinct_fork_rows`](ubuntu/serenedb/ask/:815) `815–842` len=28
- [`event_path_active`](ubuntu/serenedb/ask/:845) `845–846` len=2
- [`event_movement_feats`](ubuntu/serenedb/ask/:849) `849–850` len=2
- [`event_filter_pool`](ubuntu/serenedb/ask/:853) `853–856` len=4
- [`try_event_code_entity_pick`](ubuntu/serenedb/ask/:859) `859–914` len=56
- [`aggregate_distinct_axis`](ubuntu/serenedb/ask/:917) `917–944` len=28
- [`entity_form_axis_on_sales`](ubuntu/serenedb/ask/:947) `947–976` len=30
- [`entity_form_structs`](ubuntu/serenedb/ask/:979) `979–1037` len=59
- [`entity_form_pick`](ubuntu/serenedb/ask/:1040) `1040–1050` len=11
- [`entity_form_compute`](ubuntu/serenedb/ask/:1053) `1053–1082` len=30
- [`try_entity_form_answer`](ubuntu/serenedb/ask/:1085) `1085–1116` len=32
- [`aggregate_compare_sales`](ubuntu/serenedb/ask/:1119) `1119–1143` len=25

Зовут снаружи зоны: `_event_distinct_fork_rows`, `_months_mentioned`, `_yoy_compare_marker`, `aggregate_compare_sales`, `aggregate_distinct_axis`, `apply_proven_period`, `count_defer_measure_clarify`, `entity_form_applicable`, `entity_form_catalogs_for_kind`, `entity_form_collapse_guard`, `event_count_has_explicit_period`, `event_filter_pool`, `event_kind_catalog_expand_pool`, `event_movement_feats`, `event_path_active`, `live_axis_col_for_count`, `sales_compare_intent`, `sales_compare_windows`, `try_entity_form_answer`, `try_event_code_entity_pick`, `try_event_count_period_clarify`

## 06. entity-search — Поиск сущностей

Якорь: `_predicates`, end `meaning_candidates`. Участок: [`ubuntu/serenedb/ask/z06_entity_search.py:1`](ubuntu/serenedb/ask/z06_entity_search.py:1)–`549`.

Функций: 16. Входящие зоны: 05, 17, 20. Исходящие зоны: 01, 03, 07.

Функции:

- [`_predicates`](ubuntu/serenedb/ask/:9) `9–17` len=9
- [`_fetch`](ubuntu/serenedb/ask/:20) `20–32` len=13
- [`_like_pattern`](ubuntu/serenedb/ask/:35) `35–55` len=21
- [`probe`](ubuntu/serenedb/ask/:58) `58–160` len=103
- [`matched_group_count`](ubuntu/serenedb/ask/:163) `163–173` len=11
- [`with_refs`](ubuntu/serenedb/ask/:176) `176–184` len=9
- [`match_expr`](ubuntu/serenedb/ask/:187) `187–217` len=31
- [`children_by_parent`](ubuntu/serenedb/ask/:220) `220–270` len=51
- [`partial_tables`](ubuntu/serenedb/ask/:273) `273–350` len=78
- [`tables_of`](ubuntu/serenedb/ask/:353) `353–369` len=17
- [`date_only_kind_filter`](ubuntu/serenedb/ask/:372) `372–388` len=17
- [`keep_empty_period_opts`](ubuntu/serenedb/ask/:391) `391–406` len=16
- [`alias_hits`](ubuntu/serenedb/ask/:409) `409–440` len=32
- [`card_hits`](ubuntu/serenedb/ask/:443) `443–481` len=39
- [`question_exprs`](ubuntu/serenedb/ask/:484) `484–502` len=19
- [`meaning_candidates`](ubuntu/serenedb/ask/:505) `505–545` len=41

Зовут снаружи зоны: `_predicates`, `alias_hits`, `children_by_parent`, `date_only_kind_filter`, `keep_empty_period_opts`, `match_expr`, `matched_group_count`, `meaning_candidates`, `partial_tables`, `probe`, `question_exprs`, `tables_of`

## 07. rrf-vectors — RRF и векторы

Якорь: `_corpus_ivf_ready`, end `_ngrams`. Участок: [`ubuntu/serenedb/ask/z07_rrf_vectors.py:1`](ubuntu/serenedb/ask/z07_rrf_vectors.py:1)–`604`.

Функций: 18. Входящие зоны: 05, 06, 08, 10, 12, 13, 16, 17, 20. Исходящие зоны: 01, 08, 17, 19.

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
- [`signal_terms`](ubuntu/serenedb/ask/:281) `281–314` len=34
- [`clarify_text`](ubuntu/serenedb/ask/:327) `327–343` len=17
- [`refuse_text`](ubuntu/serenedb/ask/:355) `355–377` len=23
- [`rerank`](ubuntu/serenedb/ask/:380) `380–435` len=56
- [`_resolver_psql`](ubuntu/serenedb/ask/:438) `438–456` len=19
- [`_resolve_values_literal`](ubuntu/serenedb/ask/:463) `463–507` len=45
- [`_resolve_values_corpus`](ubuntu/serenedb/ask/:510) `510–531` len=22
- [`resolve_values`](ubuntu/serenedb/ask/:536) `536–593` len=58
- [`_ngrams`](ubuntu/serenedb/ask/:596) `596–600` len=5

Зовут снаружи зоны: `_fused_candidates`, `_ngrams`, `_resolve_values_corpus`, `_resolve_values_literal`, `_resolver_psql`, `near_tables`, `refuse_text`, `rerank`, `resolve_values`, `rows_of`, `signal_terms`

## 08. measures-totals — Меры и итоги

Якорь: `_shares_chars`, end `totals_of`. Участок: [`ubuntu/serenedb/ask/z08_measures_totals.py:1`](ubuntu/serenedb/ask/z08_measures_totals.py:1)–`261`.

Функций: 4. Входящие зоны: 07, 09, 16, 18, 20. Исходящие зоны: 01, 07, 17.

Функции:

- [`_shares_chars`](ubuntu/serenedb/ask/:9) `9–26` len=18
- [`measures_of`](ubuntu/serenedb/ask/:147) `147–160` len=14
- [`measure_aliases_of`](ubuntu/serenedb/ask/:163) `163–172` len=10
- [`totals_of`](ubuntu/serenedb/ask/:175) `175–218` len=44

Зовут снаружи зоны: `_shares_chars`, `measure_aliases_of`, `measures_of`, `totals_of`

## 09. fork-detector — Детектор развилки

Якорь: `_measures_by_src`, end `_class_label_lookup`. Участок: [`ubuntu/serenedb/ask/z09_fork_detector.py:1`](ubuntu/serenedb/ask/z09_fork_detector.py:1)–`807`.

Функций: 29. Входящие зоны: 05, 11, 13, 20. Исходящие зоны: 01, 03, 04, 05, 08, 14, 15, 16, 17, 18.

Функции:

- [`_measures_by_src`](ubuntu/serenedb/ask/:9) `9–30` len=22
- [`_aliases_by_src`](ubuntu/serenedb/ask/:33) `33–49` len=17
- [`_fork_headline_doc_measures`](ubuntu/serenedb/ask/:52) `52–54` len=3
- [`_fork_word_names_measure`](ubuntu/serenedb/ask/:57) `57–70` len=14
- [`_fork_sum_headline_pool`](ubuntu/serenedb/ask/:73) `73–83` len=11
- [`_fork_relevant`](ubuntu/serenedb/ask/:86) `86–132` len=47
- [`_fork_pool_excluded`](ubuntu/serenedb/ask/:135) `135–139` len=5
- [`fork_scan`](ubuntu/serenedb/ask/:142) `142–216` len=75
- [`fork_scan_readings`](ubuntu/serenedb/ask/:219) `219–261` len=43
- [`fork_classes_windowed`](ubuntu/serenedb/ask/:264) `264–293` len=30
- [`fork_detector_scan`](ubuntu/serenedb/ask/:296) `296–336` len=41
- [`_window_tuple_from_period`](ubuntu/serenedb/ask/:339) `339–350` len=12
- [`_fork_atom_equiv_fp`](ubuntu/serenedb/ask/:353) `353–382` len=30
- [`_fork_fp_diag`](ubuntu/serenedb/ask/:385) `385–394` len=10
- [`fork_classes`](ubuntu/serenedb/ask/:397) `397–416` len=20
- [`fork_key_of`](ubuntu/serenedb/ask/:419) `419–428` len=10
- [`_window_fp_base`](ubuntu/serenedb/ask/:431) `431–435` len=5
- [`_fork_key_for_period`](ubuntu/serenedb/ask/:438) `438–448` len=11
- [`_fork_day_basis_groups`](ubuntu/serenedb/ask/:451) `451–468` len=18
- [`_fork_log_day_basis`](ubuntu/serenedb/ask/:471) `471–488` len=18
- [`_fork_log`](ubuntu/serenedb/ask/:491) `491–528` len=38
- [`fork_labels_of`](ubuntu/serenedb/ask/:531) `531–550` len=20
- [`fork_labels_covering`](ubuntu/serenedb/ask/:555) `555–582` len=28
- [`fork_label_siblings`](ubuntu/serenedb/ask/:585) `585–592` len=8
- [`_fork_answering_sums`](ubuntu/serenedb/ask/:595) `595–616` len=22
- [`_fork_headline_measure`](ubuntu/serenedb/ask/:619) `619–686` len=68
- [`_fork_atom_of`](ubuntu/serenedb/ask/:689) `689–761` len=73
- [`_class_branch_label`](ubuntu/serenedb/ask/:764) `764–770` len=7
- [`_class_label_lookup`](ubuntu/serenedb/ask/:773) `773–803` len=31

Зовут снаружи зоны: `_aliases_by_src`, `_class_label_lookup`, `_fork_atom_of`, `_fork_fp_diag`, `_fork_log`, `_fork_pool_excluded`, `_fork_relevant`, `_fork_sum_headline_pool`, `_measures_by_src`, `fork_detector_scan`, `fork_key_of`, `fork_labels_covering`, `fork_labels_of`

## 10. rank — Ранг

Якорь: `count_question_skips_axis`, end `prefer_entity_for_rank`. Участок: [`ubuntu/serenedb/ask/z10_rank.py:1`](ubuntu/serenedb/ask/z10_rank.py:1)–`495`.

Функций: 15. Входящие зоны: 05, 11, 12, 13, 16, 20. Исходящие зоны: 01, 07, 11, 14, 15, 17, 18.

Функции:

- [`count_question_skips_axis`](ubuntu/serenedb/ask/:9) `9–26` len=18
- [`question_wants_breakdown`](ubuntu/serenedb/ask/:29) `29–41` len=13
- [`total_question_skips_axis`](ubuntu/serenedb/ask/:44) `44–62` len=19
- [`rank_question_text`](ubuntu/serenedb/ask/:67) `67–85` len=19
- [`rank_intent_from`](ubuntu/serenedb/ask/:88) `88–101` len=14
- [`rank_leader_answer_text`](ubuntu/serenedb/ask/:106) `106–126` len=21
- [`rank_axis_label_rows`](ubuntu/serenedb/ask/:144) `144–167` len=24
- [`rank_axes_rerank`](ubuntu/serenedb/ask/:170) `170–181` len=12
- [`rank_axis_pick`](ubuntu/serenedb/ask/:184) `184–230` len=47
- [`rank_axis_resolve`](ubuntu/serenedb/ask/:233) `233–295` len=63
- [`rank_product_axis_col`](ubuntu/serenedb/ask/:298) `298–301` len=4
- [`rank_leader_atom`](ubuntu/serenedb/ask/:304) `304–335` len=32
- [`rank_deterministic_answer`](ubuntu/serenedb/ask/:338) `338–416` len=79
- [`rank_gate_fallback_answer`](ubuntu/serenedb/ask/:419) `419–425` len=7
- [`prefer_entity_for_rank`](ubuntu/serenedb/ask/:428) `428–491` len=64

Зовут снаружи зоны: `count_question_skips_axis`, `prefer_entity_for_rank`, `rank_axes_rerank`, `rank_axis_resolve`, `rank_deterministic_answer`, `rank_gate_fallback_answer`, `rank_intent_from`, `rank_question_text`, `total_question_skips_axis`

## 11. sales — Продажи

Якорь: `sales_sum_intent`, end `period_zero_why_question`. Участок: [`ubuntu/serenedb/ask/z11_sales.py:1`](ubuntu/serenedb/ask/z11_sales.py:1)–`768`.

Функций: 28. Входящие зоны: 05, 10, 16, 18, 20. Исходящие зоны: 01, 05, 09, 10, 12, 14, 17.

Функции:

- [`sales_sum_intent`](ubuntu/serenedb/ask/:9) `9–56` len=48
- [`_sales_register_score`](ubuntu/serenedb/ask/:59) `59–74` len=16
- [`sales_lift_possible`](ubuntu/serenedb/ask/:77) `77–121` len=45
- [`sales_rank_engaged`](ubuntu/serenedb/ask/:124) `124–151` len=28
- [`_sales_rank_top_n`](ubuntu/serenedb/ask/:155) `155–187` len=33
- [`rank_groups_answer_text`](ubuntu/serenedb/ask/:190) `190–218` len=29
- [`prefer_entity_for_sales`](ubuntu/serenedb/ask/:221) `221–324` len=104
- [`sales_canon_src`](ubuntu/serenedb/ask/:327) `327–339` len=13
- [`sales_money_measure`](ubuntu/serenedb/ask/:342) `342–361` len=20
- [`sales_qty_measure`](ubuntu/serenedb/ask/:365) `365–375` len=11
- [`_alias_role_in_question`](ubuntu/serenedb/ask/:378) `378–397` len=20
- [`_sales_product_rank_qty`](ubuntu/serenedb/ask/:400) `400–419` len=20
- [`sales_rank_product_axis`](ubuntu/serenedb/ask/:422) `422–466` len=45
- [`sales_rank_resolve_measure`](ubuntu/serenedb/ask/:469) `469–524` len=56
- [`sales_rank_canon_measure`](ubuntu/serenedb/ask/:527) `527–558` len=32
- [`sales_force_money_measure`](ubuntu/serenedb/ask/:561) `561–583` len=23
- [`sales_canon_force_pool`](ubuntu/serenedb/ask/:586) `586–594` len=9
- [`sales_canon_engaged`](ubuntu/serenedb/ask/:597) `597–614` len=18
- [`_zero_period_not_missing`](ubuntu/serenedb/ask/:617) `617–624` len=8
- [`sales_ticket_hatch`](ubuntu/serenedb/ask/:627) `627–633` len=7
- [`sales_noncanon_focus`](ubuntu/serenedb/ask/:636) `636–644` len=9
- [`sales_refuse_sticky_focus`](ubuntu/serenedb/ask/:647) `647–679` len=33
- [`_is_price_list_noise`](ubuntu/serenedb/ask/:682) `682–686` len=5
- [`_is_product_catalog`](ubuntu/serenedb/ask/:689) `689–695` len=7
- [`catalog_count_question`](ubuntu/serenedb/ask/:698) `698–714` len=17
- [`prefer_entity_for_catalog_count`](ubuntu/serenedb/ask/:717) `717–740` len=24
- [`catalog_count_src`](ubuntu/serenedb/ask/:743) `743–751` len=9
- [`period_zero_why_question`](ubuntu/serenedb/ask/:754) `754–763` len=10

Зовут снаружи зоны: `_is_product_catalog`, `_sales_rank_top_n`, `_sales_register_score`, `_zero_period_not_missing`, `catalog_count_question`, `catalog_count_src`, `period_zero_why_question`, `prefer_entity_for_catalog_count`, `prefer_entity_for_sales`, `rank_groups_answer_text`, `sales_canon_engaged`, `sales_canon_force_pool`, `sales_canon_src`, `sales_force_money_measure`, `sales_money_measure`, `sales_noncanon_focus`, `sales_qty_measure`, `sales_rank_engaged`, `sales_rank_resolve_measure`, `sales_refuse_sticky_focus`, `sales_sum_intent`

## 12. stock-balance — Остатки

Якорь: `grain_dec_from_axis_ticket`, end `balance_bridge_clarify`. Участок: [`ubuntu/serenedb/ask/z12_stock_balance.py:1`](ubuntu/serenedb/ask/z12_stock_balance.py:1)–`305`.

Функций: 16. Входящие зоны: 11, 13, 16, 20. Исходящие зоны: 01, 02, 07, 10, 14, 20.

Функции:

- [`grain_dec_from_axis_ticket`](ubuntu/serenedb/ask/:9) `9–15` len=7
- [`_rank_wants_quantity`](ubuntu/serenedb/ask/:18) `18–22` len=5
- [`rank_measure_hint`](ubuntu/serenedb/ask/:25) `25–52` len=28
- [`balance_registers`](ubuntu/serenedb/ask/:66) `66–79` len=14
- [`balance_map_rows`](ubuntu/serenedb/ask/:82) `82–105` len=24
- [`balance_capable_sources`](ubuntu/serenedb/ask/:108) `108–110` len=3
- [`balance_capable_or_registers`](ubuntu/serenedb/ask/:113) `113–118` len=6
- [`question_asks_stock_balance`](ubuntu/serenedb/ask/:121) `121–126` len=6
- [`balance_registers_with_goods`](ubuntu/serenedb/ask/:129) `129–142` len=14
- [`_stems_of_text`](ubuntu/serenedb/ask/:145) `145–160` len=16
- [`_stock_scaffold_stems`](ubuntu/serenedb/ask/:163) `163–176` len=14
- [`stock_asks_named_product`](ubuntu/serenedb/ask/:179) `179–204` len=26
- [`stock_balance_named_no_data`](ubuntu/serenedb/ask/:207) `207–214` len=8
- [`_balance_map_by_src`](ubuntu/serenedb/ask/:217) `217–223` len=7
- [`filter_balance_structural`](ubuntu/serenedb/ask/:226) `226–265` len=40
- [`balance_bridge_clarify`](ubuntu/serenedb/ask/:268) `268–301` len=34

Зовут снаружи зоны: `_rank_wants_quantity`, `balance_bridge_clarify`, `balance_capable_or_registers`, `balance_registers_with_goods`, `filter_balance_structural`, `grain_dec_from_axis_ticket`, `question_asks_stock_balance`, `rank_measure_hint`, `stock_asks_named_product`, `stock_balance_named_no_data`

## 13. fork-outcomes — Исходы развилки

Якорь: `stock_balance_is_sales_noise`, end `fork_outcome_c`. Участок: [`ubuntu/serenedb/ask/z13_fork_outcomes.py:1`](ubuntu/serenedb/ask/z13_fork_outcomes.py:1)–`511`.

Функций: 19. Входящие зоны: 05, 20. Исходящие зоны: 01, 07, 09, 10, 12, 14, 15, 20.

Функции:

- [`stock_balance_is_sales_noise`](ubuntu/serenedb/ask/:9) `9–18` len=10
- [`filter_stock_balance_sales_noise`](ubuntu/serenedb/ask/:21) `21–28` len=8
- [`_dedupe_fork_classes`](ubuntu/serenedb/ask/:32) `32–53` len=22
- [`_class_window_form`](ubuntu/serenedb/ask/:60) `60–66` len=7
- [`_class_day_basis`](ubuntu/serenedb/ask/:69) `69–76` len=8
- [`fork_leader_class`](ubuntu/serenedb/ask/:79) `79–125` len=47
- [`fork_classes_window_only`](ubuntu/serenedb/ask/:127) `127–133` len=7
- [`rank_defer_fork_outcome_b`](ubuntu/serenedb/ask/:136) `136–139` len=4
- [`ordered_fork_classes`](ubuntu/serenedb/ask/:142) `142–160` len=19
- [`_fork_applicable_classes`](ubuntu/serenedb/ask/:163) `163–166` len=4
- [`resolve_fork_outcome`](ubuntu/serenedb/ask/:169) `169–218` len=50
- [`_fork_figures_of`](ubuntu/serenedb/ask/:221) `221–244` len=24
- [`fork_outcome_a`](ubuntu/serenedb/ask/:247) `247–267` len=21
- [`fork_outcome_unique`](ubuntu/serenedb/ask/:271) `271–296` len=26
- [`_rivals_figures_empty`](ubuntu/serenedb/ask/:299) `299–317` len=19
- [`prefer_mute_computed_over_clarify`](ubuntu/serenedb/ask/:320) `320–348` len=29
- [`atom_terminal_gate_text`](ubuntu/serenedb/ask/:351) `351–361` len=11
- [`fork_outcome_b`](ubuntu/serenedb/ask/:365) `365–414` len=50
- [`fork_outcome_c`](ubuntu/serenedb/ask/:417) `417–507` len=91

Зовут снаружи зоны: `_fork_figures_of`, `atom_terminal_gate_text`, `filter_stock_balance_sales_noise`, `fork_outcome_a`, `fork_outcome_b`, `fork_outcome_c`, `fork_outcome_unique`, `prefer_mute_computed_over_clarify`, `rank_defer_fork_outcome_b`, `resolve_fork_outcome`

## 14. clarify-memory — Уточнение и память

Якорь: `_alias_parts`, end `guards_skip_for_choice`. Участок: [`ubuntu/serenedb/ask/z14_clarify_memory.py:1`](ubuntu/serenedb/ask/z14_clarify_memory.py:1)–`717`.

Функций: 35. Входящие зоны: 09, 10, 11, 12, 13, 15, 16, 18, 20. Исходящие зоны: 01, 02, 20.

Функции:

- [`_alias_parts`](ubuntu/serenedb/ask/:9) `9–13` len=5
- [`_word_hits_text`](ubuntu/serenedb/ask/:16) `16–20` len=5
- [`split_ident`](ubuntu/serenedb/ask/:23) `23–27` len=5
- [`measure_choice`](ubuntu/serenedb/ask/:30) `30–83` len=54
- [`measure_captions`](ubuntu/serenedb/ask/:86) `86–104` len=19
- [`resolve_measure`](ubuntu/serenedb/ask/:107) `107–139` len=33
- [`slot_measure_uncovered`](ubuntu/serenedb/ask/:142) `142–150` len=9
- [`clarify_complete`](ubuntu/serenedb/ask/:153) `153–169` len=17
- [`_slot_fp`](ubuntu/serenedb/ask/:186) `186–204` len=19
- [`answers_diverge`](ubuntu/serenedb/ask/:207) `207–240` len=34
- [`answers_src_conflict`](ubuntu/serenedb/ask/:242) `242–257` len=16
- [`question_fingerprint`](ubuntu/serenedb/ask/:272) `272–275` len=4
- [`db_fingerprint`](ubuntu/serenedb/ask/:278) `278–292` len=15
- [`options_version`](ubuntu/serenedb/ask/:295) `295–308` len=14
- [`ambiguity_of_options`](ubuntu/serenedb/ask/:311) `311–322` len=12
- [`_new_decision_id`](ubuntu/serenedb/ask/:325) `325–327` len=3
- [`_purge_decisions`](ubuntu/serenedb/ask/:330) `330–345` len=16
- [`_resolved_key`](ubuntu/serenedb/ask/:348) `348–350` len=3
- [`peek_resolved`](ubuntu/serenedb/ask/:353) `353–359` len=7
- [`accumulate_resolution`](ubuntu/serenedb/ask/:362) `362–381` len=20
- [`issue_decision`](ubuntu/serenedb/ask/:384) `384–422` len=39
- [`seal_clarify`](ubuntu/serenedb/ask/:425) `425–477` len=53
- [`consume_decision`](ubuntu/serenedb/ask/:480) `480–507` len=28
- [`peek_decision`](ubuntu/serenedb/ask/:510) `510–530` len=21
- [`lookup_clarify_batch`](ubuntu/serenedb/ask/:533) `533–557` len=25
- [`reissue_clarify`](ubuntu/serenedb/ask/:560) `560–578` len=19
- [`choice_error_response`](ubuntu/serenedb/ask/:581) `581–599` len=19
- [`reset_decisions_for_tests`](ubuntu/serenedb/ask/:602) `602–607` len=6
- [`attach_memory_shadow`](ubuntu/serenedb/ask/:610) `610–621` len=12
- [`choice_proven`](ubuntu/serenedb/ask/:624) `624–630` len=7
- [`choice_levels_proven`](ubuntu/serenedb/ask/:633) `633–649` len=17
- [`measure_already_proven`](ubuntu/serenedb/ask/:652) `652–656` len=5
- [`entity_choice_locked`](ubuntu/serenedb/ask/:659) `659–661` len=3
- [`hold_settled_entity`](ubuntu/serenedb/ask/:664) `664–698` len=35
- [`guards_skip_for_choice`](ubuntu/serenedb/ask/:701) `701–713` len=13

Зовут снаружи зоны: `accumulate_resolution`, `answers_diverge`, `answers_src_conflict`, `attach_memory_shadow`, `choice_proven`, `consume_decision`, `entity_choice_locked`, `guards_skip_for_choice`, `hold_settled_entity`, `lookup_clarify_batch`, `measure_already_proven`, `measure_captions`, `measure_choice`, `peek_resolved`, `reissue_clarify`, `resolve_measure`, `seal_clarify`, `slot_measure_uncovered`, `split_ident`

## 15. answer-atoms — Атомы ответа

Якорь: `stop2_active`, end `fill_atom_pairs`. Участок: [`ubuntu/serenedb/ask/z15_answer_atoms.py:1`](ubuntu/serenedb/ask/z15_answer_atoms.py:1)–`437`.

Функций: 12. Входящие зоны: 05, 09, 10, 13, 16, 20. Исходящие зоны: 01, 14, 17, 18.

Функции:

- [`stop2_active`](ubuntu/serenedb/ask/:9) `9–19` len=11
- [`determined_answer_rivals`](ubuntu/serenedb/ask/:22) `22–57` len=36
- [`answer_money`](ubuntu/serenedb/ask/:62) `62–71` len=10
- [`answer_slot_mode`](ubuntu/serenedb/ask/:74) `74–100` len=27
- [`compose_slot_values`](ubuntu/serenedb/ask/:103) `103–174` len=72
- [`atom_operation`](ubuntu/serenedb/ask/:189) `189–203` len=15
- [`_atom_exact_value`](ubuntu/serenedb/ask/:206) `206–225` len=20
- [`build_answer_atom`](ubuntu/serenedb/ask/:228) `228–271` len=44
- [`atom_from_agg`](ubuntu/serenedb/ask/:274) `274–329` len=56
- [`_period_window_human`](ubuntu/serenedb/ask/:332) `332–339` len=8
- [`render_atom_pair`](ubuntu/serenedb/ask/:342) `342–401` len=60
- [`fill_atom_pairs`](ubuntu/serenedb/ask/:404) `404–433` len=30

Зовут снаружи зоны: `answer_money`, `answer_slot_mode`, `atom_from_agg`, `atom_operation`, `build_answer_atom`, `compose_slot_values`, `determined_answer_rivals`, `fill_atom_pairs`, `render_atom_pair`, `stop2_active`

## 16. veto-pick-entity — Вето и выбор сущности

Якорь: `pair_slots_only`, end `pick_entity`. Участок: [`ubuntu/serenedb/ask/z16_veto_pick_entity.py:1`](ubuntu/serenedb/ask/z16_veto_pick_entity.py:1)–`841`.

Функций: 29. Входящие зоны: 09, 18, 20. Исходящие зоны: 01, 02, 07, 08, 10, 11, 12, 14, 15, 18, 20.

Функции:

- [`pair_slots_only`](ubuntu/serenedb/ask/:9) `9–11` len=3
- [`atom_whitelist_labels`](ubuntu/serenedb/ask/:14) `14–23` len=10
- [`atom_whitelist_numbers`](ubuntu/serenedb/ask/:26) `26–42` len=17
- [`arbiter_figures`](ubuntu/serenedb/ask/:45) `45–51` len=7
- [`alias_supported`](ubuntu/serenedb/ask/:54) `54–122` len=69
- [`not_for_excludes`](ubuntu/serenedb/ask/:125) `125–160` len=36
- [`pair_unanswered`](ubuntu/serenedb/ask/:163) `163–173` len=11
- [`single_is_rival`](ubuntu/serenedb/ask/:176) `176–184` len=9
- [`veto_top_without`](ubuntu/serenedb/ask/:187) `187–195` len=9
- [`figures_numbers`](ubuntu/serenedb/ask/:198) `198–215` len=18
- [`same_number`](ubuntu/serenedb/ask/:218) `218–242` len=25
- [`k6_dual_atom_clarify_return`](ubuntu/serenedb/ask/:245) `245–270` len=26
- [`src_supports_question`](ubuntu/serenedb/ask/:275) `275–335` len=61
- [`any_live_src_supports_question`](ubuntu/serenedb/ask/:338) `338–349` len=12
- [`question_expects_accounting_data`](ubuntu/serenedb/ask/:358) `358–385` len=28
- [`canon_claims_question`](ubuntu/serenedb/ask/:388) `388–401` len=14
- [`kind_has_corpus_support`](ubuntu/serenedb/ask/:404) `404–423` len=20
- [`measure_class_alts`](ubuntu/serenedb/ask/:426) `426–438` len=13
- [`unresolved_quantity`](ubuntu/serenedb/ask/:441) `441–461` len=21
- [`mute_measure_blocks`](ubuntu/serenedb/ask/:464) `464–479` len=16
- [`measure_row_all_zero`](ubuntu/serenedb/ask/:482) `482–489` len=8
- [`alive_measure_names`](ubuntu/serenedb/ask/:492) `492–494` len=3
- [`filter_dead_measure_alts`](ubuntu/serenedb/ask/:497) `497–505` len=9
- [`measure_asked_explicitly`](ubuntu/serenedb/ask/:508) `508–516` len=9
- [`format_measure_empty_pivot`](ubuntu/serenedb/ask/:519) `519–537` len=19
- [`build_measure_empty_pivot`](ubuntu/serenedb/ask/:540) `540–593` len=54
- [`measure_ambiguous`](ubuntu/serenedb/ask/:596) `596–612` len=17
- [`pick_measure`](ubuntu/serenedb/ask/:615) `615–660` len=46
- [`pick_entity`](ubuntu/serenedb/ask/:663) `663–837` len=175

Зовут снаружи зоны: `alias_supported`, `arbiter_figures`, `build_measure_empty_pivot`, `canon_claims_question`, `figures_numbers`, `filter_dead_measure_alts`, `k6_dual_atom_clarify_return`, `kind_has_corpus_support`, `measure_ambiguous`, `measure_asked_explicitly`, `measure_class_alts`, `measure_row_all_zero`, `mute_measure_blocks`, `not_for_excludes`, `pair_slots_only`, `pair_unanswered`, `pick_entity`, `pick_measure`, `question_expects_accounting_data`, `same_number`, `single_is_rival`, `src_supports_question`, `unresolved_quantity`, `veto_top_without`

## 17. aggregate-groups — Агрегаты и группы

Якорь: `_vec`, end `aggregate_groups`. Участок: [`ubuntu/serenedb/ask/z17_aggregate_groups.py:1`](ubuntu/serenedb/ask/z17_aggregate_groups.py:1)–`514`.

Функций: 16. Входящие зоны: 05, 07, 08, 09, 10, 11, 15, 18, 19, 20. Исходящие зоны: 01, 06, 07.

Функции:

- [`_vec`](ubuntu/serenedb/ask/:9) `9–10` len=2
- [`_num`](ubuntu/serenedb/ask/:13) `13–17` len=5
- [`_numN`](ubuntu/serenedb/ask/:20) `20–33` len=14
- [`aggregate`](ubuntu/serenedb/ask/:36) `36–151` len=116
- [`src_is_child`](ubuntu/serenedb/ask/:155) `155–164` len=10
- [`refcols_of`](ubuntu/serenedb/ask/:167) `167–181` len=15
- [`holders_of_target`](ubuntu/serenedb/ask/:184) `184–201` len=18
- [`measures_of_many`](ubuntu/serenedb/ask/:204) `204–219` len=16
- [`kind_axis_hits`](ubuntu/serenedb/ask/:222) `222–253` len=32
- [`kind_axis_rerank`](ubuntu/serenedb/ask/:256) `256–279` len=24
- [`term_ref_owners`](ubuntu/serenedb/ask/:282) `282–308` len=27
- [`term_axis_hits`](ubuntu/serenedb/ask/:311) `311–350` len=40
- [`resolve_member_names`](ubuntu/serenedb/ask/:353) `353–380` len=28
- [`_group_leader`](ubuntu/serenedb/ask/:383) `383–392` len=10
- [`_group_fold`](ubuntu/serenedb/ask/:395) `395–401` len=7
- [`aggregate_groups`](ubuntu/serenedb/ask/:404) `404–510` len=107

Зовут снаружи зоны: `_group_leader`, `_num`, `_numN`, `_vec`, `aggregate`, `aggregate_groups`, `holders_of_target`, `kind_axis_hits`, `kind_axis_rerank`, `measures_of_many`, `refcols_of`, `src_is_child`, `term_axis_hits`, `term_ref_owners`

## 18. compose — Формулировка

Якорь: `merge_period2_groups`, end `compose`. Участок: [`ubuntu/serenedb/ask/z18_compose.py:1`](ubuntu/serenedb/ask/z18_compose.py:1)–`904`.

Функций: 22. Входящие зоны: 05, 09, 10, 15, 16, 20. Исходящие зоны: 01, 08, 11, 14, 16, 17, 19, 20.

Функции:

- [`merge_period2_groups`](ubuntu/serenedb/ask/:9) `9–24` len=16
- [`axis_clarify_options`](ubuntu/serenedb/ask/:27) `27–51` len=25
- [`_split_answer`](ubuntu/serenedb/ask/:98) `98–128` len=31
- [`_group_value_by_name`](ubuntu/serenedb/ask/:148) `148–164` len=17
- [`_fill_figures`](ubuntu/serenedb/ask/:167) `167–288` len=122
- [`ensure_n_groups_named`](ubuntu/serenedb/ask/:291) `291–309` len=19
- [`ensure_count_named`](ubuntu/serenedb/ask/:312) `312–330` len=19
- [`_measure_dimension`](ubuntu/serenedb/ask/:335) `335–353` len=19
- [`_unit_for_measure`](ubuntu/serenedb/ask/:356) `356–374` len=19
- [`postprocess_money_answer_text`](ubuntu/serenedb/ask/:377) `377–385` len=9
- [`build_answer_passport`](ubuntu/serenedb/ask/:387) `387–446` len=60
- [`ensure_answer_passport`](ubuntu/serenedb/ask/:449) `449–458` len=10
- [`measure_label_of`](ubuntu/serenedb/ask/:461) `461–470` len=10
- [`_table_label`](ubuntu/serenedb/ask/:473) `473–484` len=12
- [`_passport_axis_label`](ubuntu/serenedb/ask/:487) `487–498` len=12
- [`_passport_axis_col`](ubuntu/serenedb/ask/:501) `501–504` len=4
- [`_passport_origin`](ubuntu/serenedb/ask/:507) `507–514` len=8
- [`formulation_flaws`](ubuntu/serenedb/ask/:517) `517–544` len=28
- [`copied_figures`](ubuntu/serenedb/ask/:547) `547–614` len=68
- [`_filled_ask`](ubuntu/serenedb/ask/:617) `617–635` len=19
- [`_ask_back`](ubuntu/serenedb/ask/:638) `638–652` len=15
- [`compose`](ubuntu/serenedb/ask/:655) `655–877` len=223

Зовут снаружи зоны: `_ask_back`, `_fill_figures`, `_filled_ask`, `_passport_axis_col`, `_passport_axis_label`, `_passport_origin`, `_split_answer`, `_table_label`, `_unit_for_measure`, `axis_clarify_options`, `build_answer_passport`, `compose`, `copied_figures`, `ensure_answer_passport`, `ensure_count_named`, `ensure_n_groups_named`, `formulation_flaws`, `measure_label_of`, `merge_period2_groups`, `postprocess_money_answer_text`

## 19. answer-check — Проверка ответа

Якорь: `_readings`, end `_filter_values`. Участок: [`ubuntu/serenedb/ask/z19_answer_check.py:1`](ubuntu/serenedb/ask/z19_answer_check.py:1)–`412`.

Функций: 14. Входящие зоны: 07, 18, 20. Исходящие зоны: 01, 17.

Функции:

- [`_readings`](ubuntu/serenedb/ask/:9) `9–49` len=41
- [`_plausible`](ubuntu/serenedb/ask/:52) `52–61` len=10
- [`_dates`](ubuntu/serenedb/ask/:64) `64–84` len=21
- [`_date2_readings`](ubuntu/serenedb/ask/:87) `87–98` len=12
- [`_date_spans`](ubuntu/serenedb/ask/:101) `101–121` len=21
- [`_tokens`](ubuntu/serenedb/ask/:124) `124–154` len=31
- [`_norm_numbers`](ubuntu/serenedb/ask/:157) `157–162` len=6
- [`check_claims`](ubuntu/serenedb/ask/:168) `168–201` len=34
- [`claims_in_text`](ubuntu/serenedb/ask/:207) `207–246` len=40
- [`prompt_leak`](ubuntu/serenedb/ask/:249) `249–268` len=20
- [`asked_figure_missing`](ubuntu/serenedb/ask/:271) `271–358` len=88
- [`stale_note`](ubuntu/serenedb/ask/:361) `361–376` len=16
- [`_threshold_values`](ubuntu/serenedb/ask/:379) `379–383` len=5
- [`_filter_values`](ubuntu/serenedb/ask/:386) `386–408` len=23

Зовут снаружи зоны: `_date2_readings`, `_dates`, `_filter_values`, `_norm_numbers`, `_tokens`, `asked_figure_missing`, `check_claims`, `prompt_leak`, `stale_note`

## 20. ask-main-http — ask / HTTP

Якорь: `_filter_dates`, end `Handler`. Участок: [`ubuntu/serenedb/ask/z20_ask_main_http.py:1`](ubuntu/serenedb/ask/z20_ask_main_http.py:1)–`6175`.

Функций: 87. Входящие зоны: 03, 05, 12, 13, 14, 16, 18. Исходящие зоны: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19.

Функции:

- [`_filter_dates`](ubuntu/serenedb/ask/:9) `9–18` len=10
- [`without_list_markers`](ubuntu/serenedb/ask/:29) `29–43` len=15
- [`rows_seen`](ubuntu/serenedb/ask/:46) `46–70` len=25
- [`gate`](ubuntu/serenedb/ask/:73) `73–234` len=162
- [`count_figures`](ubuntu/serenedb/ask/:237) `237–251` len=15
- [`gate_out`](ubuntu/serenedb/ask/:254) `254–272` len=19
- [`_opt_values`](ubuntu/serenedb/ask/:275) `275–290` len=16
- [`clarify_choice_prompt`](ubuntu/serenedb/ask/:293) `293–308` len=16
- [`clarify_choice_line`](ubuntu/serenedb/ask/:311) `311–318` len=8
- [`format_clarify_options`](ubuntu/serenedb/ask/:321) `321–339` len=19
- [`clarify_say`](ubuntu/serenedb/ask/:342) `342–364` len=23
- [`_entity_counts_objects`](ubuntu/serenedb/ask/:377) `377–394` len=18
- [`_vitrina_objects`](ubuntu/serenedb/ask/:397) `397–410` len=14
- [`_coverage_of`](ubuntu/serenedb/ask/:421) `421–482` len=62
- [`_assemble_health_gap`](ubuntu/serenedb/ask/:509) `509–544` len=36
- [`_table_has_ref_key`](ubuntu/serenedb/ask/:547) `547–549` len=3
- [`_measure_health_gap`](ubuntu/serenedb/ask/:552) `552–567` len=16
- [`_real_corpus_object_gaps`](ubuntu/serenedb/ask/:571) `571–585` len=15
- [`_classify_health_gap`](ubuntu/serenedb/ask/:588) `588–618` len=31
- [`_health_search_idx_name`](ubuntu/serenedb/ask/:621) `621–626` len=6
- [`_measure_native_index_freshness`](ubuntu/serenedb/ask/:629) `629–678` len=50
- [`_attach_native_freshness`](ubuntu/serenedb/ask/:681) `681–693` len=13
- [`_health_gap`](ubuntu/serenedb/ask/:696) `696–708` len=13
- [`_health_period_relative_forms`](ubuntu/serenedb/ask/:711) `711–719` len=9
- [`_coverage_answer`](ubuntu/serenedb/ask/:743) `743–827` len=85
- [`looks_like_src_table`](ubuntu/serenedb/ask/:887) `887–892` len=6
- [`human_table_label`](ubuntu/serenedb/ask/:895) `895–907` len=13
- [`label_has_meta_src`](ubuntu/serenedb/ask/:910) `910–922` len=13
- [`kind_word`](ubuntu/serenedb/ask/:925) `925–928` len=4
- [`label_with_kind`](ubuntu/serenedb/ask/:931) `931–942` len=12
- [`ambiguous_labels`](ubuntu/serenedb/ask/:948) `948–970` len=23
- [`disambiguate_labels`](ubuntu/serenedb/ask/:973) `973–990` len=18
- [`opts_hints`](ubuntu/serenedb/ask/:1002) `1002–1061` len=60
- [`mk_opts`](ubuntu/serenedb/ask/:1064) `1064–1092` len=29
- [`live_src_counts`](ubuntu/serenedb/ask/:1095) `1095–1127` len=33
- [`empty_after_period_action`](ubuntu/serenedb/ask/:1130) `1130–1145` len=16
- [`period_empty_outcome`](ubuntu/serenedb/ask/:1148) `1148–1172` len=25
- [`_period_day_label`](ubuntu/serenedb/ask/:1175) `1175–1190` len=16
- [`sales_period_empty`](ubuntu/serenedb/ask/:1195) `1195–1210` len=16
- [`sales_period_window_active`](ubuntu/serenedb/ask/:1213) `1213–1225` len=13
- [`sales_fork_canon_empty_src`](ubuntu/serenedb/ask/:1228) `1228–1253` len=26
- [`try_sales_fork_period_empty_answer`](ubuntu/serenedb/ask/:1256) `1256–1281` len=26
- [`sales_fork_blocks_clarify`](ubuntu/serenedb/ask/:1284) `1284–1295` len=12
- [`dates_outside_period_filter`](ubuntu/serenedb/ask/:1298) `1298–1312` len=15
- [`format_period_empty_text`](ubuntu/serenedb/ask/:1315) `1315–1363` len=49
- [`build_period_empty_answer`](ubuntu/serenedb/ask/:1366) `1366–1418` len=53
- [`drop_period_preds`](ubuntu/serenedb/ask/:1421) `1421–1427` len=7
- [`_term_stems`](ubuntu/serenedb/ask/:1430) `1430–1445` len=16
- [`_src_covers_term_stems`](ubuntu/serenedb/ask/:1448) `1448–1460` len=13
- [`align_picked_to_terms`](ubuntu/serenedb/ask/:1463) `1463–1490` len=28
- [`resolve_focus`](ubuntu/serenedb/ask/:1493) `1493–1627` len=135
- [`_word_hits_measure`](ubuntu/serenedb/ask/:1631) `1631–1643` len=13
- [`axis_focus_plan`](ubuntu/serenedb/ask/:1646) `1646–1714` len=69
- [`_day_ord`](ubuntu/serenedb/ask/:1717) `1717–1722` len=6
- [`period_is_canon_guess`](ubuntu/serenedb/ask/:1725) `1725–1749` len=25
- [`period_assumed_needs_clarify`](ubuntu/serenedb/ask/:1752) `1752–1776` len=25
- [`stock_subject_needs_clarify`](ubuntu/serenedb/ask/:1779) `1779–1794` len=16
- [`warehouse_axis_values`](ubuntu/serenedb/ask/:1797) `1797–1876` len=80
- [`warehouse_clarify`](ubuntu/serenedb/ask/:1879) `1879–1893` len=15
- [`period_slot_for_inherit`](ubuntu/serenedb/ask/:1896) `1896–1907` len=12
- [`apply_prior_period`](ubuntu/serenedb/ask/:1910) `1910–1938` len=29
- [`answer`](ubuntu/serenedb/ask/:1941) `1941–5314` len=3374
- [`question_facts`](ubuntu/serenedb/ask/:5337) `5337–5363` len=27
- [`entity_has_dates`](ubuntu/serenedb/ask/:5366) `5366–5387` len=22
- [`_gate_need`](ubuntu/serenedb/ask/:5390) `5390–5403` len=14
- [`_need_clarify`](ubuntu/serenedb/ask/:5406) `5406–5422` len=17
- [`_journal_keep_n`](ubuntu/serenedb/ask/:5425) `5425–5439` len=15
- [`_journal_code_md5`](ubuntu/serenedb/ask/:5442) `5442–5449` len=8
- [`_journal_build_ts`](ubuntu/serenedb/ask/:5452) `5452–5463` len=12
- [`_journal_alias_ver`](ubuntu/serenedb/ask/:5466) `5466–5479` len=14
- [`_journal_sql_int`](ubuntu/serenedb/ask/:5482) `5482–5488` len=7
- [`_journal_sql_bool`](ubuntu/serenedb/ask/:5491) `5491–5494` len=4
- [`_journal_atoms_slim`](ubuntu/serenedb/ask/:5497) `5497–5525` len=29
- [`_journal_clarify_options`](ubuntu/serenedb/ask/:5528) `5528–5550` len=23
- [`_journal_doubt`](ubuntu/serenedb/ask/:5553) `5553–5562` len=10
- [`_journal_ticket_variant`](ubuntu/serenedb/ask/:5565) `5565–5578` len=14
- [`_journal_intent`](ubuntu/serenedb/ask/:5581) `5581–5583` len=3
- [`_journal_fork_keys`](ubuntu/serenedb/ask/:5586) `5586–5594` len=9
- [`_journal_uncounted_truncated`](ubuntu/serenedb/ask/:5597) `5597–5616` len=20
- [`_ask_journal_write`](ubuntu/serenedb/ask/:5619) `5619–5733` len=115
- [`_answer_checked_core`](ubuntu/serenedb/ask/:5737) `5737–5779` len=43
- [`_try_memory_apply`](ubuntu/serenedb/ask/:5784) `5784–5809` len=26
- [`answer_checked`](ubuntu/serenedb/ask/:5811) `5811–5899` len=89
- [`_build_ask_scope`](ubuntu/serenedb/ask/:5904) `5904–5945` len=42
- [`_persist_ask_scope`](ubuntu/serenedb/ask/:5948) `5948–5967` len=20
- [`_ensure_ask_scope_table`](ubuntu/serenedb/ask/:5970) `5970–5981` len=12
- [`main`](ubuntu/serenedb/ask/:6160) `6160–6169` len=10

Зовут снаружи зоны: `_period_day_label`, `clarify_say`, `disambiguate_labels`, `format_clarify_options`, `human_table_label`, `kind_word`, `mk_opts`

## Сквозные функции

Функции, которые вызывают из трёх и более других зон.

| функция | зона | вызывающих зон | зоны |
|---|---|---:|---|
| [`psql`](ubuntu/serenedb/ask/:271) | 01 | 17 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17, 18, 20 |
| [`lit`](ubuntu/serenedb/ask/:308) | 01 | 16 | 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 16, 17, 18, 20 |
| [`_fmt`](ubuntu/serenedb/ask/:389) | 01 | 6 | 05, 13, 15, 18, 19, 20 |
| [`_diag_pack`](ubuntu/serenedb/ask/:495) | 01 | 6 | 05, 10, 12, 13, 16, 20 |
| [`ds_chat`](ubuntu/serenedb/ask/:542) | 01 | 6 | 02, 07, 10, 16, 18, 20 |
| [`_num`](ubuntu/serenedb/ask/:13) | 17 | 5 | 05, 08, 09, 18, 20 |
| [`measure_choice`](ubuntu/serenedb/ask/:30) | 14 | 5 | 09, 11, 12, 16, 20 |
| [`rank_intent_from`](ubuntu/serenedb/ask/:88) | 10 | 5 | 05, 11, 12, 13, 20 |
| [`split_ident`](ubuntu/serenedb/ask/:23) | 14 | 4 | 09, 13, 18, 20 |
| [`period_preds`](ubuntu/serenedb/ask/:30) | 03 | 4 | 05, 06, 09, 20 |
| [`question_asks_stock_balance`](ubuntu/serenedb/ask/:121) | 12 | 4 | 11, 13, 16, 20 |
| [`measure_aliases_of`](ubuntu/serenedb/ask/:163) | 08 | 4 | 09, 16, 18, 20 |
| [`refcols_of`](ubuntu/serenedb/ask/:167) | 17 | 4 | 05, 10, 11, 20 |
| [`kind_axis_hits`](ubuntu/serenedb/ask/:222) | 17 | 4 | 05, 10, 11, 20 |
| [`refuse_text`](ubuntu/serenedb/ask/:355) | 07 | 4 | 05, 12, 13, 20 |
| [`rerank`](ubuntu/serenedb/ask/:380) | 07 | 4 | 10, 16, 17, 20 |
| [`_fmt_human`](ubuntu/serenedb/ask/:421) | 01 | 4 | 10, 11, 16, 18 |
| [`sales_sum_intent`](ubuntu/serenedb/ask/:9) | 11 | 3 | 05, 16, 20 |
| [`_measures_by_src`](ubuntu/serenedb/ask/:9) | 09 | 3 | 05, 11, 20 |
| [`rank_question_text`](ubuntu/serenedb/ask/:67) | 10 | 3 | 05, 11, 16 |
| [`measure_captions`](ubuntu/serenedb/ask/:86) | 14 | 3 | 16, 18, 20 |
| [`measures_of`](ubuntu/serenedb/ask/:147) | 08 | 3 | 16, 18, 20 |
| [`_sales_rank_top_n`](ubuntu/serenedb/ask/:155) | 11 | 3 | 05, 10, 20 |
| [`_norm_numbers`](ubuntu/serenedb/ask/:157) | 19 | 3 | 07, 18, 20 |
| [`build_answer_atom`](ubuntu/serenedb/ask/:228) | 15 | 3 | 05, 09, 10 |
| [`kind_axis_rerank`](ubuntu/serenedb/ask/:256) | 17 | 3 | 05, 10, 20 |
| [`clarify_say`](ubuntu/serenedb/ask/:342) | 20 | 3 | 05, 13, 16 |
| [`render_atom_pair`](ubuntu/serenedb/ask/:342) | 15 | 3 | 05, 13, 20 |
| [`sales_money_measure`](ubuntu/serenedb/ask/:342) | 11 | 3 | 16, 18, 20 |
| [`_unit_for_measure`](ubuntu/serenedb/ask/:356) | 18 | 3 | 10, 15, 20 |
| [`sales_qty_measure`](ubuntu/serenedb/ask/:365) | 11 | 3 | 16, 18, 20 |
| [`_group_leader`](ubuntu/serenedb/ask/:383) | 17 | 3 | 10, 15, 19 |
| [`ensure_answer_passport`](ubuntu/serenedb/ask/:449) | 18 | 3 | 10, 16, 20 |
| [`measure_label_of`](ubuntu/serenedb/ask/:461) | 18 | 3 | 09, 10, 20 |
| [`_passport_axis_label`](ubuntu/serenedb/ask/:487) | 18 | 3 | 05, 10, 20 |
| [`meaning_candidates`](ubuntu/serenedb/ask/:505) | 06 | 3 | 05, 17, 20 |
| [`_passport_origin`](ubuntu/serenedb/ask/:507) | 18 | 3 | 10, 16, 20 |
| [`mk_opts`](ubuntu/serenedb/ask/:1064) | 20 | 3 | 05, 13, 16 |

## Внутренние функции зоны

Функции, которые никто снаружи своей зоны не вызывает (включая ни разу не вызванные из других зон).

### 01 infra-trace-llm (11/29)

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

### 05 entity-form (22/43)

- `_pick_kind_axis_col`
- `_shift_date_years`
- `_shift_period_years`
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
- `event_count_has_live_axis`
- `event_count_period_clarify`
- `event_count_period_clarify_applies`
- `event_count_period_option_readings`
- `event_count_period_unspecified`
- `event_duel_applies`
- `sales_compare_split_month_pair`

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

### 09 fork-detector (16/29)

- `_class_branch_label`
- `_fork_answering_sums`
- `_fork_atom_equiv_fp`
- `_fork_day_basis_groups`
- `_fork_headline_doc_measures`
- `_fork_headline_measure`
- `_fork_key_for_period`
- `_fork_log_day_basis`
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

### 12 stock-balance (6/16)

- `_balance_map_by_src`
- `_stems_of_text`
- `_stock_scaffold_stems`
- `balance_capable_sources`
- `balance_map_rows`
- `balance_registers`

### 13 fork-outcomes (9/19)

- `_class_day_basis`
- `_class_window_form`
- `_dedupe_fork_classes`
- `_fork_applicable_classes`
- `_rivals_figures_empty`
- `fork_classes_window_only`
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

### 15 answer-atoms (2/12)

- `_atom_exact_value`
- `_period_window_human`

### 16 veto-pick-entity (5/29)

- `alive_measure_names`
- `any_live_src_supports_question`
- `atom_whitelist_labels`
- `atom_whitelist_numbers`
- `format_measure_empty_pivot`

### 17 aggregate-groups (2/16)

- `_group_fold`
- `resolve_member_names`

### 18 compose (2/22)

- `_group_value_by_name`
- `_measure_dimension`

### 19 answer-check (5/14)

- `_date_spans`
- `_plausible`
- `_readings`
- `_threshold_values`
- `claims_in_text`

### 20 ask-main-http (80/87)

- `_answer_checked_core`
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
- `warehouse_clarify`
- `without_list_markers`

## Чтение окружения

Всего: 102.

| переменная | строка | умолчание | функция |
|---|---:|---|---|
| `SERENEDB_DSN_RO` | [7](ubuntu/serenedb/ask/:7) | — | `(модуль)` |
| `PGPASSWORD` | [8](ubuntu/serenedb/ask/:8) | "" | `(модуль)` |
| `RESOLVER_DSN` | [14](ubuntu/serenedb/ask/:14) | "" | `(модуль)` |
| `RESOLVER_PW` | [15](ubuntu/serenedb/ask/:15) | "" | `(модуль)` |
| `ASK_LISTEN_HOST` | [16](ubuntu/serenedb/ask/:16) | "127.0.0.1" | `(модуль)` |
| `ASK_LISTEN_PORT` | [17](ubuntu/serenedb/ask/:17) | "8091" | `(модуль)` |
| `ASK_TOKEN` | [18](ubuntu/serenedb/ask/:18) | "" | `(модуль)` |
| `ASK_MONEY_UNIT` | [19](ubuntu/serenedb/ask/:19) | "" | `(модуль)` |
| `ASK_CARD_TABLE` | [30](ubuntu/serenedb/ask/:30) | "search_entity_card" | `(модуль)` |
| `ASK_PICK_BUDGET_CHARS` | [36](ubuntu/serenedb/ask/:36) | "8000" | `(модуль)` |
| `ASK_ROWS_BUDGET_CHARS` | [43](ubuntu/serenedb/ask/:43) | "24000" | `(модуль)` |
| `ASK_TERMS_FOR` | [47](ubuntu/serenedb/ask/:47) | "3" | `(модуль)` |
| `ASK_COVERAGE_TOP` | [51](ubuntu/serenedb/ask/:51) | "15" | `(модуль)` |
| `ASK_STALE_WARN_SEC` | [55](ubuntu/serenedb/ask/:55) | "3600" | `(модуль)` |
| `ASK_TERMS_TOP` | [56](ubuntu/serenedb/ask/:56) | "6" | `(модуль)` |
| `ASK_TOPK` | [57](ubuntu/serenedb/ask/:57) | "40" | `(модуль)` |
| `ASK_TRACE` | [61](ubuntu/serenedb/ask/:61) | "1" | `(модуль)` |
| `ASK_ROWS_TO_MODEL` | [62](ubuntu/serenedb/ask/:62) | "25" | `(модуль)` |
| `ASK_SCORER` | [127](ubuntu/serenedb/ask/:127) | "bm25" | `(модуль)` |
| `ASK_REFS_BOOST` | [139](ubuntu/serenedb/ask/:139) | "8.0" | `(модуль)` |
| `ASK_ORDER_BY_MEANING` | [146](ubuntu/serenedb/ask/:146) | "1" | `(модуль)` |
| `RERANK_URL` | [162](ubuntu/serenedb/ask/:162) | — | `(модуль)` |
| `ALIBABA_RERANK_URL` | [163](ubuntu/serenedb/ask/:163) | — | `(модуль)` |
| `RERANK_MODEL` | [165](ubuntu/serenedb/ask/:165) | — | `(модуль)` |
| `ALIBABA_RERANK_MODEL` | [166](ubuntu/serenedb/ask/:166) | — | `(модуль)` |
| `RERANK_API` | [167](ubuntu/serenedb/ask/:167) | "<expr>" | `(модуль)` |
| `ASK_RERANK_TOP` | [172](ubuntu/serenedb/ask/:172) | "60" | `(модуль)` |
| `DEEPSEEK_BASE` | [180](ubuntu/serenedb/ask/:180) | "https://api.deepseek.com" | `(модуль)` |
| `DEEPSEEK_API_KEY` | [181](ubuntu/serenedb/ask/:181) | "" | `(модуль)` |
| `DEEPSEEK_MODEL` | [189](ubuntu/serenedb/ask/:189) | "deepseek-v4-pro" | `(модуль)` |
| `DEEPSEEK_THINKING` | [190](ubuntu/serenedb/ask/:190) | "disabled" | `(модуль)` |
| `ASK_THINKING_OFF_BODY` | [193](ubuntu/serenedb/ask/:193) | "" | `(модуль)` |
| `EMBED_BASE_URL` | [202](ubuntu/serenedb/ask/:202) | — | `(модуль)` |
| `ALIBABA_EMBED_URL` | [203](ubuntu/serenedb/ask/:203) | "" | `(модуль)` |
| `EMBED_API` | [209](ubuntu/serenedb/ask/:209) | "openai" | `(модуль)` |
| `EMBED_QUERY_PATH` | [210](ubuntu/serenedb/ask/:210) | "/embed" | `(модуль)` |
| `EMBED_UA` | [213](ubuntu/serenedb/ask/:213) | "curl/8.5.0" | `(модуль)` |
| `EMBED_HEALTH_URL` | [215](ubuntu/serenedb/ask/:215) | — | `(модуль)` |
| `EMBED_API_KEY` | [216](ubuntu/serenedb/ask/:216) | — | `(модуль)` |
| `ALIBABA_API_KEY` | [216](ubuntu/serenedb/ask/:216) | "" | `(модуль)` |
| `EMBED_MODEL` | [217](ubuntu/serenedb/ask/:217) | "text-embedding-v4" | `(модуль)` |
| `RERANK_API_KEY` | [220](ubuntu/serenedb/ask/:220) | — | `(модуль)` |
| `EMBED_DIM` | [228](ubuntu/serenedb/ask/:228) | "1024" | `(модуль)` |
| `EMBED_PATH` | [240](ubuntu/serenedb/ask/:240) | "/v1/embeddings" | `(модуль)` |
| `ASK_EMBED_NATIVE` | [241](ubuntu/serenedb/ask/:241) | "0" | `(модуль)` |
| `ASK_NO_DATA_TEXT` | [261](ubuntu/serenedb/ask/:261) | "" | `(модуль)` |
| `ASK_TOTAL_TEXT` | [262](ubuntu/serenedb/ask/:262) | "" | `(модуль)` |
| `ASK_STALE_TEXT` | [265](ubuntu/serenedb/ask/:265) | "\n\n⚠ Данные могли устареть: последнее обновление из 1С было %d мин назад." | `(модуль)` |
| `ASK_EMB_CACHE` | [615](ubuntu/serenedb/ask/:615) | "256" | `(модуль)` |
| `ASK_EMB_RETRY` | [619](ubuntu/serenedb/ask/:619) | "2" | `(модуль)` |
| `ASK_EMB_RETRY_PAUSE` | [620](ubuntu/serenedb/ask/:620) | "0.4" | `(модуль)` |
| `ASK_EMB_TIMEOUT` | [621](ubuntu/serenedb/ask/:621) | "60" | `(модуль)` |
| `ASK_INTENT_MAX_TOKENS` | [848](ubuntu/serenedb/ask/:848) | "400" | `(модуль)` |
| `ASK_INTENT_SAMPLES` | [849](ubuntu/serenedb/ask/:849) | "5" | `(модуль)` |
| `ASK_INTENT_LEAD` | [850](ubuntu/serenedb/ask/:850) | "3" | `(модуль)` |
| `ASK_INTENT_MEMO` | [852](ubuntu/serenedb/ask/:852) | "512" | `(модуль)` |
| `ASK_INTENT_GROUPS` | [859](ubuntu/serenedb/ask/:859) | "6" | `(модуль)` |
| `ASK_INTENT_ALTS` | [860](ubuntu/serenedb/ask/:860) | "6" | `(модуль)` |
| `ASK_STEM_DICT` | [863](ubuntu/serenedb/ask/:863) | "search_dict_stem" | `(модуль)` |
| `ASK_SOLR_SYNONYMS` | [866](ubuntu/serenedb/ask/:866) | "0" | `(модуль)` |
| `ASK_SOLR_SYNONYMS_DICT` | [867](ubuntu/serenedb/ask/:867) | "" | `(модуль)` |
| `ASK_CALENDAR_AXIS` | [59](ubuntu/serenedb/ask/:59) | "0" | `(модуль)` |
| `ASK_SALES_RANK_CANON` | [61](ubuntu/serenedb/ask/:61) | "0" | `(модуль)` |
| `ASK_ATOM_TERMINAL` | [63](ubuntu/serenedb/ask/:63) | "0" | `(модуль)` |
| `ASK_ENTITY_FORM` | [66](ubuntu/serenedb/ask/:66) | "0" | `(модуль)` |
| `ASK_RESOLVE_NEAR` | [459](ubuntu/serenedb/ask/:459) | "12" | `(модуль)` |
| `ASK_RESOLVE_KEEP` | [460](ubuntu/serenedb/ask/:460) | "3" | `(модуль)` |
| `ASK_ALIAS_TOP` | [32](ubuntu/serenedb/ask/:32) | "8" | `(модуль)` |
| `ASK_ALIAS_INDEX` | [35](ubuntu/serenedb/ask/:35) | "alias_idx" | `(модуль)` |
| `ASK_CARD_INDEX` | [40](ubuntu/serenedb/ask/:40) | "entity_card_idx" | `(модуль)` |
| `ASK_RRF_K` | [45](ubuntu/serenedb/ask/:45) | "60" | `(модуль)` |
| `ASK_SQL_RRF` | [48](ubuntu/serenedb/ask/:48) | "0" | `(модуль)` |
| `ASK_CORPUS_IVF_IDX` | [49](ubuntu/serenedb/ask/:49) | "corpus_ivf_idx" | `(модуль)` |
| `ASK_RESOLVER_IVF` | [54](ubuntu/serenedb/ask/:54) | "0" | `(модуль)` |
| `ASK_RESOLVER_IVF_IDX` | [55](ubuntu/serenedb/ask/:55) | "resolver_ivf_idx" | `(модуль)` |
| `ASK_ALIAS_VETO` | [68](ubuntu/serenedb/ask/:68) | "1" | `(модуль)` |
| `ASK_PROBE` | [75](ubuntu/serenedb/ask/:75) | "0" | `(модуль)` |
| `ASK_SKIP_SERVICE_RIVALS` | [79](ubuntu/serenedb/ask/:79) | "1" | `(модуль)` |
| `ASK_ALIAS_BY_CONCEPTS` | [91](ubuntu/serenedb/ask/:91) | "0" | `(модуль)` |
| `ASK_VETO_NEEDS_RANK` | [106](ubuntu/serenedb/ask/:106) | "0" | `(модуль)` |
| `ASK_VETO_HEAD_WINS` | [116](ubuntu/serenedb/ask/:116) | "1" | `(модуль)` |
| `ASK_MEANING_TOP` | [142](ubuntu/serenedb/ask/:142) | "0" | `(модуль)` |
| `ASK_FORK_DETECT` | [234](ubuntu/serenedb/ask/:234) | "1" | `(модуль)` |
| `ASK_FORK_OUTCOMES` | [235](ubuntu/serenedb/ask/:235) | "1" | `(модуль)` |
| `ASK_JOURNAL` | [238](ubuntu/serenedb/ask/:238) | "1" | `(модуль)` |
| `ASK_CHOICE_MEMORY` | [243](ubuntu/serenedb/ask/:243) | "1" | `(модуль)` |
| `ASK_MEMORY_APPLY` | [245](ubuntu/serenedb/ask/:245) | "0" | `(модуль)` |
| `ASK_FORK_MEAS_TTL` | [256](ubuntu/serenedb/ask/:256) | "600" | `(модуль)` |
| `ASK_RAW_FOCUS_TRUST` | [263](ubuntu/serenedb/ask/:263) | "0" | `(модуль)` |
| `ASK_DECISION_TTL_SEC` | [264](ubuntu/serenedb/ask/:264) | "3600" | `(модуль)` |
| `ASK_HEALTH_GAP_TTL` | [496](ubuntu/serenedb/ask/:496) | "300" | `(модуль)` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | [504](ubuntu/serenedb/ask/:504) | "0" | `(модуль)` |
| `ASK_HEALTH_SEARCH_IDX` | [505](ubuntu/serenedb/ask/:505) | "search_idx" | `(модуль)` |
| `ASK_SIGNAL_DISAGREE` | [833](ubuntu/serenedb/ask/:833) | "1" | `(модуль)` |
| `ASK_REQUIRE_SUPPORT` | [835](ubuntu/serenedb/ask/:835) | "1" | `(модуль)` |
| `ASK_ARBITER_MAX` | [838](ubuntu/serenedb/ask/:838) | "3" | `(модуль)` |
| `ASK_ARBITER_DETECTS` | [844](ubuntu/serenedb/ask/:844) | "1" | `(модуль)` |
| `ASK_NOT_FOR` | [846](ubuntu/serenedb/ask/:846) | "1" | `(модуль)` |
| `ASK_STEM_DICT` | [849](ubuntu/serenedb/ask/:849) | "search_dict_stem" | `(модуль)` |
| `ASK_AMBIG_TTL` | [852](ubuntu/serenedb/ask/:852) | "300" | `(модуль)` |
| `ASK_ENOUGH` | [5329](ubuntu/serenedb/ask/:5329) | "1" | `(модуль)` |
| `ASK_SLOT_COVER` | [5331](ubuntu/serenedb/ask/:5331) | "0" | `(модуль)` |

## Обращения наружу

Вызовы `psql` / `ds_chat` / `embed_one` / `rerank` / `urlopen`.

### psql (159)

- [`ubuntu/serenedb/ask/:379`](ubuntu/serenedb/ask/:379) в `emb_ready`
- [`ubuntu/serenedb/ask/:635`](ubuntu/serenedb/ask/:635) в `_ensure_embed_secret`
- [`ubuntu/serenedb/ask/:650`](ubuntu/serenedb/ask/:650) в `_ensure_embed_secret`
- [`ubuntu/serenedb/ask/:669`](ubuntu/serenedb/ask/:669) в `_embed_one_native`
- [`ubuntu/serenedb/ask/:168`](ubuntu/serenedb/ask/:168) в `same_concept_groups`
- [`ubuntu/serenedb/ask/:382`](ubuntu/serenedb/ask/:382) в `period_relative_forms`
- [`ubuntu/serenedb/ask/:21`](ubuntu/serenedb/ask/:21) в `calendar_registers`
- [`ubuntu/serenedb/ask/:37`](ubuntu/serenedb/ask/:37) в `calendar_working_day_keys`
- [`ubuntu/serenedb/ask/:57`](ubuntu/serenedb/ask/:57) в `calendar_map_rows`
- [`ubuntu/serenedb/ask/:298`](ubuntu/serenedb/ask/:298) в `entity_form_catalogs_for_kind`
- [`ubuntu/serenedb/ask/:332`](ubuntu/serenedb/ask/:332) в `entity_form_movements_for_kind`
- [`ubuntu/serenedb/ask/:894`](ubuntu/serenedb/ask/:894) в `try_event_code_entity_pick`
- [`ubuntu/serenedb/ask/:931`](ubuntu/serenedb/ask/:931) в `aggregate_distinct_axis`
- [`ubuntu/serenedb/ask/:29`](ubuntu/serenedb/ask/:29) в `_fetch`
- [`ubuntu/serenedb/ask/:101`](ubuntu/serenedb/ask/:101) в `probe`
- [`ubuntu/serenedb/ask/:204`](ubuntu/serenedb/ask/:204) в `match_expr`
- [`ubuntu/serenedb/ask/:243`](ubuntu/serenedb/ask/:243) в `children_by_parent`
- [`ubuntu/serenedb/ask/:262`](ubuntu/serenedb/ask/:262) в `children_by_parent`
- [`ubuntu/serenedb/ask/:332`](ubuntu/serenedb/ask/:332) в `partial_tables`
- [`ubuntu/serenedb/ask/:364`](ubuntu/serenedb/ask/:364) в `tables_of`
- [`ubuntu/serenedb/ask/:434`](ubuntu/serenedb/ask/:434) в `alias_hits`
- [`ubuntu/serenedb/ask/:474`](ubuntu/serenedb/ask/:474) в `card_hits`
- [`ubuntu/serenedb/ask/:17`](ubuntu/serenedb/ask/:17) в `_corpus_ivf_ready`
- [`ubuntu/serenedb/ask/:97`](ubuntu/serenedb/ask/:97) в `_fused_sql_rrf`
- [`ubuntu/serenedb/ask/:105`](ubuntu/serenedb/ask/:105) в `_fused_python_rrf`
- [`ubuntu/serenedb/ask/:206`](ubuntu/serenedb/ask/:206) в `near_tables`
- [`ubuntu/serenedb/ask/:242`](ubuntu/serenedb/ask/:242) в `rows_of`
- [`ubuntu/serenedb/ask/:296`](ubuntu/serenedb/ask/:296) в `signal_terms`
- [`ubuntu/serenedb/ask/:525`](ubuntu/serenedb/ask/:525) в `_resolve_values_corpus`
- [`ubuntu/serenedb/ask/:155`](ubuntu/serenedb/ask/:155) в `measures_of`
- [`ubuntu/serenedb/ask/:166`](ubuntu/serenedb/ask/:166) в `measure_aliases_of`
- [`ubuntu/serenedb/ask/:207`](ubuntu/serenedb/ask/:207) в `totals_of`
- [`ubuntu/serenedb/ask/:20`](ubuntu/serenedb/ask/:20) в `_measures_by_src`
- [`ubuntu/serenedb/ask/:39`](ubuntu/serenedb/ask/:39) в `_aliases_by_src`
- [`ubuntu/serenedb/ask/:177`](ubuntu/serenedb/ask/:177) в `fork_scan`
- [`ubuntu/serenedb/ask/:200`](ubuntu/serenedb/ask/:200) в `fork_scan`
- [`ubuntu/serenedb/ask/:480`](ubuntu/serenedb/ask/:480) в `_fork_log_day_basis`
- [`ubuntu/serenedb/ask/:520`](ubuntu/serenedb/ask/:520) в `_fork_log`
- [`ubuntu/serenedb/ask/:540`](ubuntu/serenedb/ask/:540) в `fork_labels_of`
- [`ubuntu/serenedb/ask/:565`](ubuntu/serenedb/ask/:565) в `fork_labels_covering`
- [`ubuntu/serenedb/ask/:153`](ubuntu/serenedb/ask/:153) в `rank_axis_label_rows`
- [`ubuntu/serenedb/ask/:441`](ubuntu/serenedb/ask/:441) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/ask/:459`](ubuntu/serenedb/ask/:459) в `prefer_entity_for_rank`
- [`ubuntu/serenedb/ask/:91`](ubuntu/serenedb/ask/:91) в `sales_lift_possible`
- [`ubuntu/serenedb/ask/:115`](ubuntu/serenedb/ask/:115) в `sales_lift_possible`
- [`ubuntu/serenedb/ask/:239`](ubuntu/serenedb/ask/:239) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/ask/:263`](ubuntu/serenedb/ask/:263) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/ask/:295`](ubuntu/serenedb/ask/:295) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/ask/:275`](ubuntu/serenedb/ask/:275) в `prefer_entity_for_sales`
- [`ubuntu/serenedb/ask/:725`](ubuntu/serenedb/ask/:725) в `prefer_entity_for_catalog_count`
- [`ubuntu/serenedb/ask/:75`](ubuntu/serenedb/ask/:75) в `balance_registers`
- [`ubuntu/serenedb/ask/:93`](ubuntu/serenedb/ask/:93) в `balance_map_rows`
- [`ubuntu/serenedb/ask/:138`](ubuntu/serenedb/ask/:138) в `balance_registers_with_goods`
- [`ubuntu/serenedb/ask/:152`](ubuntu/serenedb/ask/:152) в `_stems_of_text`
- [`ubuntu/serenedb/ask/:241`](ubuntu/serenedb/ask/:241) в `filter_balance_structural`
- [`ubuntu/serenedb/ask/:277`](ubuntu/serenedb/ask/:277) в `balance_bridge_clarify`
- [`ubuntu/serenedb/ask/:473`](ubuntu/serenedb/ask/:473) в `fork_outcome_c`
- [`ubuntu/serenedb/ask/:288`](ubuntu/serenedb/ask/:288) в `db_fingerprint`
- [`ubuntu/serenedb/ask/:252`](ubuntu/serenedb/ask/:252) в `k6_dual_atom_clarify_return`
- [`ubuntu/serenedb/ask/:416`](ubuntu/serenedb/ask/:416) в `kind_has_corpus_support`
- [`ubuntu/serenedb/ask/:682`](ubuntu/serenedb/ask/:682) в `pick_entity`
- [`ubuntu/serenedb/ask/:720`](ubuntu/serenedb/ask/:720) в `pick_entity`
- [`ubuntu/serenedb/ask/:111`](ubuntu/serenedb/ask/:111) в `aggregate`
- [`ubuntu/serenedb/ask/:160`](ubuntu/serenedb/ask/:160) в `src_is_child`
- [`ubuntu/serenedb/ask/:172`](ubuntu/serenedb/ask/:172) в `refcols_of`
- [`ubuntu/serenedb/ask/:189`](ubuntu/serenedb/ask/:189) в `holders_of_target`
- [`ubuntu/serenedb/ask/:209`](ubuntu/serenedb/ask/:209) в `measures_of_many`
- [`ubuntu/serenedb/ask/:231`](ubuntu/serenedb/ask/:231) в `kind_axis_hits`
- [`ubuntu/serenedb/ask/:266`](ubuntu/serenedb/ask/:266) в `kind_axis_rerank`
- [`ubuntu/serenedb/ask/:293`](ubuntu/serenedb/ask/:293) в `term_ref_owners`
- [`ubuntu/serenedb/ask/:327`](ubuntu/serenedb/ask/:327) в `term_axis_hits`
- [`ubuntu/serenedb/ask/:365`](ubuntu/serenedb/ask/:365) в `resolve_member_names`
- [`ubuntu/serenedb/ask/:474`](ubuntu/serenedb/ask/:474) в `aggregate_groups`
- [`ubuntu/serenedb/ask/:36`](ubuntu/serenedb/ask/:36) в `axis_clarify_options`
- [`ubuntu/serenedb/ask/:478`](ubuntu/serenedb/ask/:478) в `_table_label`
- [`ubuntu/serenedb/ask/:380`](ubuntu/serenedb/ask/:380) в `_entity_counts_objects`
- [`ubuntu/serenedb/ask/:388`](ubuntu/serenedb/ask/:388) в `_entity_counts_objects`
- [`ubuntu/serenedb/ask/:400`](ubuntu/serenedb/ask/:400) в `_vitrina_objects`
- [`ubuntu/serenedb/ask/:408`](ubuntu/serenedb/ask/:408) в `_vitrina_objects`
- [`ubuntu/serenedb/ask/:432`](ubuntu/serenedb/ask/:432) в `_coverage_of`
- [`ubuntu/serenedb/ask/:469`](ubuntu/serenedb/ask/:469) в `_coverage_of`
- [`ubuntu/serenedb/ask/:442`](ubuntu/serenedb/ask/:442) в `_coverage_of`
- [`ubuntu/serenedb/ask/:559`](ubuntu/serenedb/ask/:559) в `_measure_health_gap`
- [`ubuntu/serenedb/ask/:579`](ubuntu/serenedb/ask/:579) в `_real_corpus_object_gaps`
- [`ubuntu/serenedb/ask/:600`](ubuntu/serenedb/ask/:600) в `_classify_health_gap`
- [`ubuntu/serenedb/ask/:655`](ubuntu/serenedb/ask/:655) в `_measure_native_index_freshness`
- [`ubuntu/serenedb/ask/:752`](ubuntu/serenedb/ask/:752) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:761`](ubuntu/serenedb/ask/:761) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:964`](ubuntu/serenedb/ask/:964) в `ambiguous_labels`
- [`ubuntu/serenedb/ask/:1010`](ubuntu/serenedb/ask/:1010) в `opts_hints`
- [`ubuntu/serenedb/ask/:1017`](ubuntu/serenedb/ask/:1017) в `opts_hints`
- [`ubuntu/serenedb/ask/:1027`](ubuntu/serenedb/ask/:1027) в `opts_hints`
- [`ubuntu/serenedb/ask/:1037`](ubuntu/serenedb/ask/:1037) в `opts_hints`
- [`ubuntu/serenedb/ask/:1117`](ubuntu/serenedb/ask/:1117) в `live_src_counts`
- [`ubuntu/serenedb/ask/:1306`](ubuntu/serenedb/ask/:1306) в `dates_outside_period_filter`
- [`ubuntu/serenedb/ask/:1438`](ubuntu/serenedb/ask/:1438) в `_term_stems`
- [`ubuntu/serenedb/ask/:1441`](ubuntu/serenedb/ask/:1441) в `_term_stems`
- [`ubuntu/serenedb/ask/:1453`](ubuntu/serenedb/ask/:1453) в `_src_covers_term_stems`
- [`ubuntu/serenedb/ask/:1456`](ubuntu/serenedb/ask/:1456) в `_src_covers_term_stems`
- [`ubuntu/serenedb/ask/:1476`](ubuntu/serenedb/ask/:1476) в `align_picked_to_terms`
- [`ubuntu/serenedb/ask/:1532`](ubuntu/serenedb/ask/:1532) в `resolve_focus`
- [`ubuntu/serenedb/ask/:1537`](ubuntu/serenedb/ask/:1537) в `resolve_focus`
- [`ubuntu/serenedb/ask/:1556`](ubuntu/serenedb/ask/:1556) в `resolve_focus`
- [`ubuntu/serenedb/ask/:1596`](ubuntu/serenedb/ask/:1596) в `resolve_focus`
- [`ubuntu/serenedb/ask/:1693`](ubuntu/serenedb/ask/:1693) в `axis_focus_plan`
- [`ubuntu/serenedb/ask/:1835`](ubuntu/serenedb/ask/:1835) в `warehouse_axis_values`
- [`ubuntu/serenedb/ask/:1869`](ubuntu/serenedb/ask/:1869) в `warehouse_axis_values`
- [`ubuntu/serenedb/ask/:2288`](ubuntu/serenedb/ask/:2288) в `answer`
- [`ubuntu/serenedb/ask/:2445`](ubuntu/serenedb/ask/:2445) в `answer`
- [`ubuntu/serenedb/ask/:3027`](ubuntu/serenedb/ask/:3027) в `answer`
- [`ubuntu/serenedb/ask/:3104`](ubuntu/serenedb/ask/:3104) в `answer`
- [`ubuntu/serenedb/ask/:3151`](ubuntu/serenedb/ask/:3151) в `answer`
- [`ubuntu/serenedb/ask/:4463`](ubuntu/serenedb/ask/:4463) в `answer`
- [`ubuntu/serenedb/ask/:4820`](ubuntu/serenedb/ask/:4820) в `answer`
- [`ubuntu/serenedb/ask/:4841`](ubuntu/serenedb/ask/:4841) в `answer`
- [`ubuntu/serenedb/ask/:2454`](ubuntu/serenedb/ask/:2454) в `answer`
- [`ubuntu/serenedb/ask/:4599`](ubuntu/serenedb/ask/:4599) в `answer`
- [`ubuntu/serenedb/ask/:2491`](ubuntu/serenedb/ask/:2491) в `answer`
- [`ubuntu/serenedb/ask/:2530`](ubuntu/serenedb/ask/:2530) в `answer`
- [`ubuntu/serenedb/ask/:2695`](ubuntu/serenedb/ask/:2695) в `answer`
- [`ubuntu/serenedb/ask/:2724`](ubuntu/serenedb/ask/:2724) в `answer`
- [`ubuntu/serenedb/ask/:2746`](ubuntu/serenedb/ask/:2746) в `answer`
- [`ubuntu/serenedb/ask/:2765`](ubuntu/serenedb/ask/:2765) в `answer`
- [`ubuntu/serenedb/ask/:2789`](ubuntu/serenedb/ask/:2789) в `answer`
- [`ubuntu/serenedb/ask/:2948`](ubuntu/serenedb/ask/:2948) в `answer`
- [`ubuntu/serenedb/ask/:3090`](ubuntu/serenedb/ask/:3090) в `answer`
- [`ubuntu/serenedb/ask/:3289`](ubuntu/serenedb/ask/:3289) в `answer`
- [`ubuntu/serenedb/ask/:3981`](ubuntu/serenedb/ask/:3981) в `answer`
- [`ubuntu/serenedb/ask/:4180`](ubuntu/serenedb/ask/:4180) в `answer`
- [`ubuntu/serenedb/ask/:4621`](ubuntu/serenedb/ask/:4621) в `answer`
- [`ubuntu/serenedb/ask/:2475`](ubuntu/serenedb/ask/:2475) в `answer`
- [`ubuntu/serenedb/ask/:3201`](ubuntu/serenedb/ask/:3201) в `answer`
- [`ubuntu/serenedb/ask/:3844`](ubuntu/serenedb/ask/:3844) в `answer`
- [`ubuntu/serenedb/ask/:2626`](ubuntu/serenedb/ask/:2626) в `answer`
- [`ubuntu/serenedb/ask/:3116`](ubuntu/serenedb/ask/:3116) в `answer`
- [`ubuntu/serenedb/ask/:3224`](ubuntu/serenedb/ask/:3224) в `answer`
- [`ubuntu/serenedb/ask/:3882`](ubuntu/serenedb/ask/:3882) в `answer`
- [`ubuntu/serenedb/ask/:3948`](ubuntu/serenedb/ask/:3948) в `answer`
- [`ubuntu/serenedb/ask/:3963`](ubuntu/serenedb/ask/:3963) в `answer`
- [`ubuntu/serenedb/ask/:3151`](ubuntu/serenedb/ask/:3151) в `answer._alias_verdict`
- [`ubuntu/serenedb/ask/:3201`](ubuntu/serenedb/ask/:3201) в `answer._alias_verdict`
- [`ubuntu/serenedb/ask/:3224`](ubuntu/serenedb/ask/:3224) в `answer._alias_verdict`
- [`ubuntu/serenedb/ask/:3289`](ubuntu/serenedb/ask/:3289) в `answer._alias_clarify`
- [`ubuntu/serenedb/ask/:5380`](ubuntu/serenedb/ask/:5380) в `entity_has_dates`
- [`ubuntu/serenedb/ask/:5434`](ubuntu/serenedb/ask/:5434) в `_journal_keep_n`
- [`ubuntu/serenedb/ask/:5458`](ubuntu/serenedb/ask/:5458) в `_journal_build_ts`
- [`ubuntu/serenedb/ask/:5471`](ubuntu/serenedb/ask/:5471) в `_journal_alias_ver`
- [`ubuntu/serenedb/ask/:5705`](ubuntu/serenedb/ask/:5705) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5726`](ubuntu/serenedb/ask/:5726) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5719`](ubuntu/serenedb/ask/:5719) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5721`](ubuntu/serenedb/ask/:5721) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5728`](ubuntu/serenedb/ask/:5728) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5660`](ubuntu/serenedb/ask/:5660) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5709`](ubuntu/serenedb/ask/:5709) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5722`](ubuntu/serenedb/ask/:5722) в `_ask_journal_write`
- [`ubuntu/serenedb/ask/:5705`](ubuntu/serenedb/ask/:5705) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/ask/:5709`](ubuntu/serenedb/ask/:5709) в `_ask_journal_write._insert_row`
- [`ubuntu/serenedb/ask/:6001`](ubuntu/serenedb/ask/:6001) в `Handler.do_GET`
- [`ubuntu/serenedb/ask/:6128`](ubuntu/serenedb/ask/:6128) в `Handler.do_POST`

### ds_chat (10)

- [`ubuntu/serenedb/ask/:582`](ubuntu/serenedb/ask/:582) в `arbitrate`
- [`ubuntu/serenedb/ask/:333`](ubuntu/serenedb/ask/:333) в `_one_intent`
- [`ubuntu/serenedb/ask/:341`](ubuntu/serenedb/ask/:341) в `_one_intent`
- [`ubuntu/serenedb/ask/:340`](ubuntu/serenedb/ask/:340) в `clarify_text`
- [`ubuntu/serenedb/ask/:373`](ubuntu/serenedb/ask/:373) в `refuse_text`
- [`ubuntu/serenedb/ask/:205`](ubuntu/serenedb/ask/:205) в `rank_axis_pick`
- [`ubuntu/serenedb/ask/:785`](ubuntu/serenedb/ask/:785) в `pick_entity`
- [`ubuntu/serenedb/ask/:876`](ubuntu/serenedb/ask/:876) в `compose`
- [`ubuntu/serenedb/ask/:781`](ubuntu/serenedb/ask/:781) в `_coverage_answer`
- [`ubuntu/serenedb/ask/:5352`](ubuntu/serenedb/ask/:5352) в `question_facts`

### embed_one (1)

- [`ubuntu/serenedb/ask/:10`](ubuntu/serenedb/ask/:10) в `_vec`

### rerank (5)

- [`ubuntu/serenedb/ask/:591`](ubuntu/serenedb/ask/:591) в `resolve_values`
- [`ubuntu/serenedb/ask/:178`](ubuntu/serenedb/ask/:178) в `rank_axes_rerank`
- [`ubuntu/serenedb/ask/:645`](ubuntu/serenedb/ask/:645) в `pick_measure`
- [`ubuntu/serenedb/ask/:276`](ubuntu/serenedb/ask/:276) в `kind_axis_rerank`
- [`ubuntu/serenedb/ask/:2701`](ubuntu/serenedb/ask/:2701) в `answer`

### urlopen (4)

- [`ubuntu/serenedb/ask/:355`](ubuntu/serenedb/ask/:355) в `embed_model_live`
- [`ubuntu/serenedb/ask/:538`](ubuntu/serenedb/ask/:538) в `ds_chat_post`
- [`ubuntu/serenedb/ask/:740`](ubuntu/serenedb/ask/:740) в `embed_one`
- [`ubuntu/serenedb/ask/:414`](ubuntu/serenedb/ask/:414) в `rerank`
