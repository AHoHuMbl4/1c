# W1 — карта живости `z01_infra_trace_llm.py`

Зона: `ubuntu/serenedb/ask/z01_infra_trace_llm.py` (файл **883** строки; **112** символов верхнего уровня; сумма тел символов **556**; остальное — импорты, комментарии, `csv.field_size_limit`, `register_zone`).

## Метод

- Фактические имена в общем namespace: `ask/z*.py`, `_bootstrap.py` / `_imports.py` / `_wire.py` / `_ctx.py`, `ubuntu/serenedb/test_*.py`.
- Import-структуры нет — только упоминания имён.
- Семена нового/legacy z20: AST `Name` Load (без рёбер из строковых литералов вроде статуса `'rerank'`).
- Транзитив: граф вызовов зон по AST `Name` Load в телах `def`/`class`.
- Модульные константы других зон (`MEANING_TOP ← PICK_BUDGET`) — если константу читает достижимая функция.
- Внутренние зависимости z01 — AST Load внутри тел символов.
- Индекс «кто зовёт» по code-строкам (комментарии отброшены); строки в литералах bootstrap (`"DSN ="`) могут попасть в индекс.

## Итог зоны

| Вердикт | Символов | Строк (тела) |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 106 | 540 |
| **ЖИВА ТОЛЬКО LEGACY** | 1 | 5 |
| **МЁРТВА** | 5 | 11 |
| сумма | 112 | 556 |

**Вердикт зоны:** нужна одному пути. Новый `z20_ask_main_http.py` прямо держит ядро (psql/lit/ds_chat/rid/deadline/бюджеты/NO_DATA/INTENT_SYS/…) и транзитивно тянет embed/RRF/intent-константы/wiki-секреты/реранкер. После flip+сноса legacy из зоны уходит по существу только `_gate_bad_preview` (5 строк). Уже мёртвы 5 символов (11 строк).

Прямые семена нового z20: `ASK_TOKEN`, `AskDeadline`, `CORPUS`, `COVERAGE_TOP`, `INDEX`, `INTENT_SYS`, `LISTEN_HOST`, `LISTEN_PORT`, `NO_DATA_TEXT`, `RESOLVER_DSN`, `ROWS_BUDGET`, `ROWS_TO_MODEL`, `STALE_TEXT`, `STALE_WARN_SEC`, `TABLES`, `TOPK`, `_diag_pack`, `_fmt`, `_fmt_gate_bad`, `_req_t0_clear`, `_rid_enter`, `_rid_get`, `_rid_norm`, `_src_tag`, `_token_acc`, `_token_acc_start`, `_trace_write`, `deadline_hit`, `ds_chat`, `lit`, `psql`.

`_bootstrap.py` загружает зону списком файлов и строково сторожит шапку (`DSN`/`SCORER`); `_imports.py` / `_wire.py` символов z01 не упоминают.

## Таблица символов

| Символ | Стр. | Кто зовёт | Вердикт |
|---|---:|---|---|
| `DSN` | 1 | зоны: `z14_clarify_memory.py`×3, `_bootstrap.py`×1, `z16_veto_pick_entity.py`×1; цепь: `DSN` ← `db_fingerprint` ← `consume_decision`; тесты: `test_ask_choice_memory.py`, `test_ask_journal.py`, `test_build_alloc_bg_threads.py` +9 | ЖИВА НОВОМУ |
| `PGPASSWORD` | 1 | зоны: `z07_rrf_vectors.py`×1; цепь: `PGPASSWORD` ← `psql`; тесты: `test_ask_choice_memory.py`, `test_ask_journal.py`, `test_corpus_chunk_identity.py` +4 | ЖИВА НОВОМУ |
| `RESOLVER_DSN` | 1 | new `2727`; legacy `4878`; зоны: `z07_rrf_vectors.py`×2; тесты: `test_integrity.py` | ЖИВА НОВОМУ |
| `RESOLVER_PW` | 1 | зоны: `z07_rrf_vectors.py`×2; цепь: `RESOLVER_PW` ← `_resolver_psql`; тесты: `test_integrity.py` | ЖИВА НОВОМУ |
| `LISTEN_HOST` | 1 | new `2942,2944`; legacy `5093,5095` | ЖИВА НОВОМУ |
| `LISTEN_PORT` | 1 | new `2942,2944`; legacy `5093,5095` | ЖИВА НОВОМУ |
| `ASK_DEADLINE_SEC` | 1 | цепь: `ASK_DEADLINE_SEC` ← `deadline_hit` | ЖИВА НОВОМУ |
| `ASK_TOKEN` | 1 | new `2835,2938,2939`; legacy `4986,5089,5090`; тесты: `test_a3_passport.py`, `test_action_class.py`, `test_aggregate_live_flags.py` +58 | ЖИВА НОВОМУ |
| `MONEY_UNIT` | 1 | зоны: `z13_fork_outcomes.py`×1, `z18_compose.py`×1; цепь: `MONEY_UNIT` ← `_unit_for_measure`; тесты: `test_rank_axis_anchor.py`, `test_unit_from_data.py` | ЖИВА НОВОМУ |
| `CORPUS` | 1 | new `459,1013,1095,1108+4`; legacy `464,1037,1119+12`; зоны: `z12_stock_balance.py`×7, `z17_aggregate_groups.py`×4, `z06_entity_search.py`×3; тесты: `test_axis_focus.py`, `test_sql_rrf.py`, `test_step2.py` | ЖИВА НОВОМУ |
| `INDEX` | 1 | new `1095,1108,1194,2210+1`; legacy `1119,1132,1220+4`; зоны: `z06_entity_search.py`×6, `z07_rrf_vectors.py`×4, `z08_measures_totals.py`×1; тесты: `test_axis_focus.py`, `test_inverted_index_guard.py`, `test_morph_dict_pipeline.py` +1 | ЖИВА НОВОМУ |
| `TABLES` | 1 | new `960,1024,1493,2268`; legacy `984,1048,1399+16`; зоны: `z07_rrf_vectors.py`×4, `z17_aggregate_groups.py`×3, `z05_entity_form.py`×2; тесты: `test_ask_journal.py`, `test_journal_fields.py`, `test_named_type_filter.py` +3 | ЖИВА НОВОМУ |
| `CLASS_TABLE` | 1 | legacy `2597`; зоны: `z02_intent.py`×1; цепь: `CLASS_TABLE` ← `_base_business_topic_words` ← `_enrich_conversational_business` ← `parse_intent` | ЖИВА НОВОМУ |
| `CARD` | 1 | зоны: `z07_rrf_vectors.py`×4; цепь: `CARD` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`; тесты: `test_sql_rrf.py` | ЖИВА НОВОМУ |
| `PICK_BUDGET` | 1 | legacy `2298`; зоны: `z08_measures_totals.py`×1; mod: `PICK_BUDGET` ← `MEANING_TOP` ← `entity_form_catalogs_for_kind` | ЖИВА НОВОМУ |
| `ROWS_BUDGET` | 1 | new `65`; legacy `69`; зоны: `z18_compose.py`×1; тесты: `test_gate.py` | ЖИВА НОВОМУ |
| `TERMS_FOR` | 1 | — | МЁРТВА |
| `COVERAGE_TOP` | 1 | new `779`; legacy `784` | ЖИВА НОВОМУ |
| `STALE_WARN_SEC` | 1 | new `2902`; legacy `5053` | ЖИВА НОВОМУ |
| `TERMS_TOP` | 1 | — | МЁРТВА |
| `TOPK` | 1 | new `54,2147`; legacy `58,2075,3838`; зоны: `z07_rrf_vectors.py`×1 | ЖИВА НОВОМУ |
| `TRACE` | 1 | цепь: `TRACE` ← `_trace_write`; тесты: `test_ds_tokens.py`, `test_trace_rid.py` | ЖИВА НОВОМУ |
| `ROWS_TO_MODEL` | 1 | new `55,64,2128`; legacy `59,68,3777+1`; зоны: `z11_sales.py`×6, `z18_compose.py`×3, `z17_aggregate_groups.py`×2; тесты: `test_gate.py` | ЖИВА НОВОМУ |
| `_rid_ctx` | 1 | цепь: `_rid_ctx` ← `_rid_enter`; тесты: `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_REQ_T0` | 1 | цепь: `_REQ_T0` ← `_req_t0_clear` | ЖИВА НОВОМУ |
| `AskDeadline` | 2 | new `1880,1928,2067,2238+1`; legacy `2373,2419,2910+2`; зоны: `z07_rrf_vectors.py`×1 | ЖИВА НОВОМУ |
| `_new_rid` | 2 | цепь: `_new_rid` ← `_rid_norm` | ЖИВА НОВОМУ |
| `_rid_norm` | 6 | new `2495`; legacy `4643`; тесты: `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_rid_get` | 2 | new `2495`; legacy `4643`; тесты: `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_rid_enter` | 5 | new `2584`; legacy `4733`; тесты: `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_req_t0_clear` | 4 | new `2656`; legacy `4805` | ЖИВА НОВОМУ |
| `deadline_hit` | 7 | new `1879,1927,2066,2237`; legacy `2372,2909`; зоны: `z07_rrf_vectors.py`×1 | ЖИВА НОВОМУ |
| `_trace_write` | 5 | new `1870`; legacy `1753`; тесты: `test_trace_rid.py` | ЖИВА НОВОМУ |
| `SCORERS` | 8 | зоны: `z07_rrf_vectors.py`×6, `z06_entity_search.py`×4; цепь: `SCORERS` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits` | ЖИВА НОВОМУ |
| `SCORER` | 1 | зоны: `z07_rrf_vectors.py`×3, `z06_entity_search.py`×2, `_bootstrap.py`×1; цепь: `SCORER` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`; тесты: `test_compare_sales.py` | ЖИВА НОВОМУ |
| `REFS_BOOST` | 1 | зоны: `z06_entity_search.py`×2; цепь: `REFS_BOOST` ← `with_refs` ← `match_expr`; тесты: `test_step2.py` | ЖИВА НОВОМУ |
| `ORDER_BY_MEANING` | 1 | тесты: `test_stock_balance_path.py` | МЁРТВА |
| `RERANK_URL` | 3 | зоны: `z07_rrf_vectors.py`×1; цепь: `RERANK_URL` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve` | ЖИВА НОВОМУ |
| `RERANK_MODEL` | 2 | зоны: `z07_rrf_vectors.py`×2; цепь: `RERANK_MODEL` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve` | ЖИВА НОВОМУ |
| `RERANK_API` | 2 | зоны: `z07_rrf_vectors.py`×3; цепь: `RERANK_API` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve` | ЖИВА НОВОМУ |
| `RERANK_TOP` | 1 | — | МЁРТВА |
| `DS_BASE` | 1 | цепь: `DS_BASE` ← `ds_chat_post` ← `ds_chat` | ЖИВА НОВОМУ |
| `DS_KEY` | 1 | цепь: `DS_KEY` ← `ds_chat_post` ← `ds_chat` | ЖИВА НОВОМУ |
| `DS_MODEL` | 1 | цепь: `DS_MODEL` ← `_ds_chat_body` ← `ds_chat` | ЖИВА НОВОМУ |
| `DS_THINKING` | 1 | цепь: `DS_THINKING` ← `_ds_chat_body` ← `ds_chat` | ЖИВА НОВОМУ |
| `ASK_THINKING_OFF_BODY` | 1 | цепь: `ASK_THINKING_OFF_BODY` ← `_ds_chat_body` ← `ds_chat`; тесты: `test_ds_tokens.py` | ЖИВА НОВОМУ |
| `DS_REASONING_OFF` | 1 | цепь: `DS_REASONING_OFF` ← `_ds_chat_body` ← `ds_chat` | ЖИВА НОВОМУ |
| `EMBED_URL` | 2 | цепь: `EMBED_URL` ← `_embed_host_base` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` | ЖИВА НОВОМУ |
| `EMBED_API` | 1 | цепь: `EMBED_API` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_ai_embed_question.py` | ЖИВА НОВОМУ |
| `EMBED_QUERY_PATH` | 1 | цепь: `EMBED_QUERY_PATH` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMBED_UA` | 1 | зоны: `z07_rrf_vectors.py`×1; цепь: `EMBED_UA` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMBED_HEALTH_URL` | 1 | цепь: `EMBED_HEALTH_URL` ← `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMBED_KEY` | 1 | цепь: `EMBED_KEY` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMBED_MODEL` | 1 | зоны: `z21_wiki_choice.py`×1; цепь: `EMBED_MODEL` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_a3_passport.py`, `test_aggregate_live_flags.py`, `test_ai_embed_question.py` +48 | ЖИВА НОВОМУ |
| `RERANK_KEY` | 1 | зоны: `z07_rrf_vectors.py`×3; цепь: `RERANK_KEY` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve`; тесты: `test_resolver_ivf.py` | ЖИВА НОВОМУ |
| `EMBED_DIM` | 1 | зоны: `z17_aggregate_groups.py`×1, `z21_wiki_choice.py`×1; цепь: `EMBED_DIM` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py`, `test_integrity.py` +3 | ЖИВА НОВОМУ |
| `_embed_secret_name_from_env` | 5 | внутр z01 ← `EMBED_SECRET_NAME`, `_reload_embed_native_env` | ЖИВА НОВОМУ |
| `EMBED_SECRET_NAME` | 1 | зоны: `z21_wiki_choice.py`×1; цепь: `EMBED_SECRET_NAME` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_named_type_filter.py`, `test_wiki_candidate_verify.py`, `test_wiki_card_hybrid.py` | ЖИВА НОВОМУ |
| `EMBED_PATH` | 1 | цепь: `EMBED_PATH` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`; тесты: `test_box_tune.py` | ЖИВА НОВОМУ |
| `ASK_EMBED_NATIVE` | 1 | цепь: `ASK_EMBED_NATIVE` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py` | ЖИВА НОВОМУ |
| `_EMBED_SECRET_LOCK` | 1 | цепь: `_EMBED_SECRET_LOCK` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` | ЖИВА НОВОМУ |
| `_EMBED_SECRET_READY` | 1 | цепь: `_EMBED_SECRET_READY` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`; тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py` | ЖИВА НОВОМУ |
| `_reload_embed_native_env` | 7 | тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py` | МЁРТВА |
| `NO_DATA_TEXT` | 1 | new `783,787,1813,1965+4`; legacy `788,792,1934+9`; зоны: `z21_wiki_choice.py`×2, `z04_calendar_axis.py`×1, `z13_fork_outcomes.py`×1; тесты: `test_named_type_filter.py`, `test_wiki_candidate_verify.py`, `test_wiki_card_hybrid.py` | ЖИВА НОВОМУ |
| `TOTAL_TEXT` | 1 | зоны: `z13_fork_outcomes.py`×3; цепь: `TOTAL_TEXT` ← `atom_terminal_gate_text` | ЖИВА НОВОМУ |
| `STALE_TEXT` | 3 | new `2902`; legacy `5053` | ЖИВА НОВОМУ |
| `psql` | 35 | new `395,403,415,423+34`; legacy `400,408,420+60`; зоны: `z12_stock_balance.py`×17, `z17_aggregate_groups.py`×16, `z04b_currency_axis.py`×12; тесты: `test_ab_calendar_axis_set.py`, `test_ab_scorer_v2_modes.py`, `test_acceptance_ut_tsv.py` +60 | ЖИВА НОВОМУ |
| `lit` | 2 | new `397,406,417,422+33`; legacy `402,411,422+71`; зоны: `z17_aggregate_groups.py`×35, `z12_stock_balance.py`×25, `z09_fork_detector.py`×16; тесты: `test_etalon_1c.py`, `test_named_type_filter.py`, `test_verify_threshold_menu.py` +3 | ЖИВА НОВОМУ |
| `_embed_host_base` | 4 | цепь: `_embed_host_base` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade` | ЖИВА НОВОМУ |
| `_EMB_OK_CACHE` | 1 | цепь: `_EMB_OK_CACHE` ← `emb_ready` ← `resolve_values` ← `probe`; тесты: `test_resolver_ivf.py`, `test_sql_rrf.py` | ЖИВА НОВОМУ |
| `_EMB_LIVE_CACHE` | 1 | цепь: `_EMB_LIVE_CACHE` ← `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe`; тесты: `test_sql_rrf.py` | ЖИВА НОВОМУ |
| `embed_model_live` | 31 | цепь: `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe`; тесты: `test_stock_balance_path.py` | ЖИВА НОВОМУ |
| `emb_ready` | 19 | legacy `2058,2290`; зоны: `z07_rrf_vectors.py`×7; цепь: `emb_ready` ← `_corpus_ivf_ready` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`; тесты: `test_resolver_ivf.py`, `test_sql_rrf.py`, `test_stock_balance_path.py` | ЖИВА НОВОМУ |
| `_fmt` | 7 | new `1228,1250`; legacy `1254,1276,3714+1`; зоны: `z15_answer_atoms.py`×9, `z19_answer_check.py`×4, `z18_compose.py`×3 | ЖИВА НОВОМУ |
| `_src_tag` | 5 | new `1793`; legacy `4037,4283,4289`; тесты: `test_post_gate_none_src.py` | ЖИВА НОВОМУ |
| `_fmt_gate_bad` | 7 | new `221,1744,1746`; legacy `225,4185,4187` | ЖИВА НОВОМУ |
| `_gate_bad_preview` | 5 | legacy `4175`; тесты: `test_rank_axis_anchor.py` | ЖИВА ТОЛЬКО LEGACY |
| `_fmt_human` | 15 | зоны: `z10_rank.py`×2, `z11_sales.py`×2, `z16_veto_pick_entity.py`×1; цепь: `_fmt_human` ← `_fill_figures` | ЖИВА НОВОМУ |
| `_token_acc` | 1 | new `1854`; legacy `1725` | ЖИВА НОВОМУ |
| `_TokenAcc` | 31 | цепь: `_TokenAcc` ← `_token_acc_start` | ЖИВА НОВОМУ |
| `_token_acc_start` | 2 | new `1855,2573`; legacy `1726,4722`; тесты: `test_ds_tokens.py`, `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_token_acc_record` | 15 | цепь: `_token_acc_record` ← `_ds_chat_content` ← `ds_chat`; тесты: `test_ds_tokens.py`, `test_trace_rid.py` | ЖИВА НОВОМУ |
| `_diag_pack` | 7 | new `378,784,788,836+11`; legacy `383,789,793+29`; зоны: `z13_fork_outcomes.py`×6, `z21_wiki_choice.py`×3, `z05_entity_form.py`×2; тесты: `test_ds_tokens.py`, `test_named_type_filter.py`, `test_wiki_candidate_verify.py` +1 | ЖИВА НОВОМУ |
| `_ds_chat_content` | 14 | цепь: `_ds_chat_content` ← `ds_chat`; тесты: `test_ds_tokens.py` | ЖИВА НОВОМУ |
| `_ds_chat_body` | 13 | цепь: `_ds_chat_body` ← `ds_chat`; тесты: `test_ds_tokens.py` | ЖИВА НОВОМУ |
| `ds_chat_post` | 12 | цепь: `ds_chat_post` ← `ds_chat` | ЖИВА НОВОМУ |
| `ds_chat` | 2 | new `796`; legacy `801`; зоны: `z02_intent.py`×2, `z21_wiki_choice.py`×2, `z07_rrf_vectors.py`×1; тесты: `test_action_class.py`, `test_answer_atom.py`, `test_compose.py` +8 | ЖИВА НОВОМУ |
| `_embed_request` | 14 | цепь: `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_gate.py` | ЖИВА НОВОМУ |
| `_EMB_ONE_CACHE` | 1 | цепь: `_EMB_ONE_CACHE` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py` | ЖИВА НОВОМУ |
| `EMB_ONE_CACHE_MAX` | 1 | цепь: `EMB_ONE_CACHE_MAX` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMB_RETRY` | 1 | цепь: `EMB_RETRY` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMB_RETRY_PAUSE` | 1 | цепь: `EMB_RETRY_PAUSE` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `EMB_TIMEOUT` | 1 | цепь: `EMB_TIMEOUT` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `_ensure_embed_secret` | 32 | зоны: `z21_wiki_choice.py`×1; цепь: `_ensure_embed_secret` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_named_type_filter.py`, `test_wiki_candidate_verify.py`, `test_wiki_card_hybrid.py` | ЖИВА НОВОМУ |
| `_embed_one_native` | 35 | цепь: `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe` | ЖИВА НОВОМУ |
| `embed_one` | 63 | зоны: `z17_aggregate_groups.py`×1; цепь: `embed_one` ← `_vec` ← `resolve_values` ← `probe`; тесты: `test_ai_embed_question.py`, `test_ask_embed_native.py`, `test_gate.py` | ЖИВА НОВОМУ |
| `INTENT_SYS` | 47 | new `755`; legacy `761`; зоны: `z02_intent.py`×1 | ЖИВА НОВОМУ |
| `_WANT_OK` | 1 | зоны: `z02_intent.py`×1; цепь: `_WANT_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`; тесты: `test_intent.py` | ЖИВА НОВОМУ |
| `_ABOUT_OK` | 1 | зоны: `z02_intent.py`×1; цепь: `_ABOUT_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`; тесты: `test_intent.py` | ЖИВА НОВОМУ |
| `_AMOUNT_OPS` | 1 | зоны: `z02_intent.py`×1; цепь: `_AMOUNT_OPS` ← `_normalize_intent` ← `_one_intent` ← `parse_intent` | ЖИВА НОВОМУ |
| `_ACTION_CLASS_OK` | 1 | зоны: `z02_intent.py`×1; цепь: `_ACTION_CLASS_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent` | ЖИВА НОВОМУ |
| `_INTENT_FIELDS` | 2 | зоны: `z02_intent.py`×3; цепь: `_INTENT_FIELDS` ← `_merge_intents` ← `parse_intent` | ЖИВА НОВОМУ |
| `INTENT_MAX_TOKENS` | 1 | зоны: `z02_intent.py`×2; цепь: `INTENT_MAX_TOKENS` ← `_one_intent` ← `parse_intent` | ЖИВА НОВОМУ |
| `INTENT_SAMPLES` | 1 | зоны: `z02_intent.py`×1; цепь: `INTENT_SAMPLES` ← `parse_intent`; тесты: `test_action_class.py`, `test_intent.py` | ЖИВА НОВОМУ |
| `INTENT_LEAD` | 1 | зоны: `z02_intent.py`×2; цепь: `INTENT_LEAD` ← `parse_intent`; тесты: `test_action_class.py`, `test_intent.py` | ЖИВА НОВОМУ |
| `INTENT_MEMO` | 1 | зоны: `z02_intent.py`×4; цепь: `INTENT_MEMO` ← `parse_intent`; тесты: `test_action_class.py`, `test_intent.py` | ЖИВА НОВОМУ |
| `_INTENT_MEMO` | 1 | зоны: `z02_intent.py`×4; цепь: `_INTENT_MEMO` ← `parse_intent`; тесты: `test_intent.py` | ЖИВА НОВОМУ |
| `INTENT_GROUPS` | 1 | зоны: `z02_intent.py`×3; цепь: `INTENT_GROUPS` ← `_intent_terms` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`; тесты: `test_intent.py` | ЖИВА НОВОМУ |
| `INTENT_ALTS` | 1 | зоны: `z02_intent.py`×3; цепь: `INTENT_ALTS` ← `_intent_terms` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`; тесты: `test_intent.py` | ЖИВА НОВОМУ |
| `STEM_DICT` | 1 | legacy `868,2139,2166+5`; зоны: `z17_aggregate_groups.py`×8, `z05_entity_form.py`×4, `z12_stock_balance.py`×4; цепь: `STEM_DICT` ← `_base_knows_kind_or_measure` ← `stock_asks_named_product` ← `stock_count_aggregate_without_subject`; тесты: `test_named_type_filter.py`, `test_solr_synonyms_apply.py`, `test_wiki_candidate_verify.py` +1 | ЖИВА НОВОМУ |
| `ASK_SOLR_SYNONYMS` | 1 | зоны: `z02_intent.py`×1; цепь: `ASK_SOLR_SYNONYMS` ← `same_concept_groups` ← `parse_intent`; тесты: `test_f6_rollout_measure.py`, `test_solr_synonyms_apply.py` | ЖИВА НОВОМУ |
| `ASK_SOLR_SYNONYMS_DICT` | 1 | зоны: `z02_intent.py`×2; цепь: `ASK_SOLR_SYNONYMS_DICT` ← `same_concept_groups` ← `parse_intent`; тесты: `test_build_solr_synonyms.py`, `test_solr_synonyms_apply.py` | ЖИВА НОВОМУ |

## Транзитивные цепочки (не прямое семя нового z20)

Формат: `символ` ← функция-потребитель ← … ← вход с нового тракта.

- `DSN` ← `db_fingerprint` ← `consume_decision`
- `PGPASSWORD` ← `psql`
- `RESOLVER_PW` ← `_resolver_psql`
- `ASK_DEADLINE_SEC` ← `deadline_hit`
- `MONEY_UNIT` ← `_unit_for_measure`
- `CLASS_TABLE` ← `_base_business_topic_words` ← `_enrich_conversational_business` ← `parse_intent`
- `CARD` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`
- `PICK_BUDGET` ← `MEANING_TOP` ← `entity_form_catalogs_for_kind`
- `TRACE` ← `_trace_write`
- `_rid_ctx` ← `_rid_enter`
- `_REQ_T0` ← `_req_t0_clear`
- `_new_rid` ← `_rid_norm`
- `SCORERS` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`
- `SCORER` ← `_rrf_entity_branches` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`
- `REFS_BOOST` ← `with_refs` ← `match_expr`
- `RERANK_URL` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve`
- `RERANK_MODEL` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve`
- `RERANK_API` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve`
- `DS_BASE` ← `ds_chat_post` ← `ds_chat`
- `DS_KEY` ← `ds_chat_post` ← `ds_chat`
- `DS_MODEL` ← `_ds_chat_body` ← `ds_chat`
- `DS_THINKING` ← `_ds_chat_body` ← `ds_chat`
- `ASK_THINKING_OFF_BODY` ← `_ds_chat_body` ← `ds_chat`
- `DS_REASONING_OFF` ← `_ds_chat_body` ← `ds_chat`
- `EMBED_URL` ← `_embed_host_base` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`
- `EMBED_API` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMBED_QUERY_PATH` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMBED_UA` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMBED_HEALTH_URL` ← `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe`
- `EMBED_KEY` ← `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMBED_MODEL` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `RERANK_KEY` ← `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve`
- `EMBED_DIM` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_embed_secret_name_from_env` ← `EMBED_SECRET_NAME`, `_reload_embed_native_env` (внутри z01)
- `EMBED_SECRET_NAME` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMBED_PATH` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`
- `ASK_EMBED_NATIVE` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_EMBED_SECRET_LOCK` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`
- `_EMBED_SECRET_READY` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`
- `TOTAL_TEXT` ← `atom_terminal_gate_text`
- `_embed_host_base` ← `_ensure_embed_secret` ← `wiki_hybrid_pool` ← `try_wiki_hybrid_entity_pick` ← `wiki_primary_entity_cascade`
- `_EMB_OK_CACHE` ← `emb_ready` ← `resolve_values` ← `probe`
- `_EMB_LIVE_CACHE` ← `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe`
- `embed_model_live` ← `emb_ready` ← `resolve_values` ← `probe`
- `emb_ready` ← `_corpus_ivf_ready` ← `_fused_candidates` ← `meaning_candidates` ← `kind_axis_hits`
- `_fmt_human` ← `_fill_figures`
- `_TokenAcc` ← `_token_acc_start`
- `_token_acc_record` ← `_ds_chat_content` ← `ds_chat`
- `_ds_chat_content` ← `ds_chat`
- `_ds_chat_body` ← `ds_chat`
- `ds_chat_post` ← `ds_chat`
- `_embed_request` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_EMB_ONE_CACHE` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMB_ONE_CACHE_MAX` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMB_RETRY` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMB_RETRY_PAUSE` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `EMB_TIMEOUT` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_ensure_embed_secret` ← `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_embed_one_native` ← `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `embed_one` ← `_vec` ← `resolve_values` ← `probe`
- `_WANT_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `_ABOUT_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `_AMOUNT_OPS` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `_ACTION_CLASS_OK` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `_INTENT_FIELDS` ← `_merge_intents` ← `parse_intent`
- `INTENT_MAX_TOKENS` ← `_one_intent` ← `parse_intent`
- `INTENT_SAMPLES` ← `parse_intent`
- `INTENT_LEAD` ← `parse_intent`
- `INTENT_MEMO` ← `parse_intent`
- `_INTENT_MEMO` ← `parse_intent`
- `INTENT_GROUPS` ← `_intent_terms` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `INTENT_ALTS` ← `_intent_terms` ← `_normalize_intent` ← `_one_intent` ← `parse_intent`
- `STEM_DICT` ← `_base_knows_kind_or_measure` ← `stock_asks_named_product` ← `stock_count_aggregate_without_subject`
- `ASK_SOLR_SYNONYMS` ← `same_concept_groups` ← `parse_intent`
- `ASK_SOLR_SYNONYMS_DICT` ← `same_concept_groups` ← `parse_intent`

## Скрытые выбиратели, доступные новому тракту

В z01 нет функций «выбери сущность/меру/период/ось». Есть переключатели инфры и контракт intent. Новый z20 всё ещё зовёт `parse_intent` рядом с `wiki_primary_entity_cascade`, плюс `measure_choice` / `rank_axis_resolve`.

| Символ | Что выбирает | Путь в новый | Для «одного пути» |
|---|---|---|---|
| `SCORER` / `SCORERS` | модель ранжирования (env) | `_rrf_entity_branches` / `alias_hits` / `card_hits` / `rows_of` | не мера/ось; A/B скорер |
| `ASK_EMBED_NATIVE` / `EMBED_API` | канал эмбеддинга вопроса | `embed_one` ← probe/wiki | не бизнес-выбор |
| `INTENT_SYS`, `_WANT_OK`, `_ABOUT_OK`, `_AMOUNT_OPS`, `_ACTION_CLASS_OK`, `_INTENT_FIELDS`, `INTENT_*` | want/measure/period/about/action_* | `parse_intent` **прямо в новом z20** | да: старый LLM-intent на горячем пути параллельно wiki |
| `RERANK_URL` / `MODEL` / `API` / `KEY` | внешний реранкер | `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve` (новый z20:~1597); также `resolve_values`/`kind_axis_rerank` | да: реранкер на пути выбора оси/разрешения значений (не сам выбиратель, но кормит его) |
| `ORDER_BY_MEANING` | порядок «по смыслу» | **МЁРТВА** | не тащит |
| `RERANK_TOP` | бюджет имён в реранкер | **МЁРТВА** | не тащит |

**Вывод:** скрытых выбирателей *внутри* z01 нет. Зона **питает** живые выбиратели других зон (`parse_intent`, `rank_axis_resolve`→`rerank`, `measure_choice` — последний статус `'rerank'` строкой, без вызова `rerank()`). Мёртвые `ORDER_BY_MEANING` / `RERANK_TOP` в новый не протекают.

## Замки (тесты)

Упоминания символов зоны в **100** тестовых файлах. Топ:

- `test_wiki_card_hybrid.py` — 12 символов
- `test_intent.py` — 11 символов
- `test_trace_rid.py` — 11 символов
- `test_named_type_filter.py` — 11 символов
- `test_wiki_candidate_verify.py` — 11 символов
- `test_ai_embed_question.py` — 10 символов
- `test_ask_embed_native.py` — 9 символов
- `test_sql_rrf.py` — 8 символов
- `test_ds_tokens.py` — 8 символов
- `test_ask_journal.py` — 6 символов
- `test_gate.py` — 6 символов
- `test_stock_balance_path.py` — 6 символов
- `test_ask_choice_memory.py` — 5 символов
- `test_integrity.py` — 5 символов
- `test_action_class.py` — 5 символов

- `_gate_bad_preview` — `test_rank_axis_anchor.py`
- `_reload_embed_native_env` — `test_ai_embed_question.py`, `test_ask_embed_native.py`
- `ORDER_BY_MEANING` — `test_stock_balance_path.py`
- rid/TRACE/tokens — `test_trace_rid.py`, `test_ds_tokens.py`
- intent — `test_intent.py`, `test_action_class.py`

## Исключения

| Символ | Вердикт | Почему |
|---|---|---|
| `_gate_bad_preview` | только legacy | `z20_ask_main_http_legacy.py:4175`; новый не зовёт |
| `TERMS_FOR`, `TERMS_TOP` | мертва | нет ссылок вне определения |
| `ORDER_BY_MEANING` | мертва | только тест |
| `RERANK_TOP` | мертва | в ask только комментарии |
| `_reload_embed_native_env` | мертва | только тесты |
| `PICK_BUDGET` | жива новому | legacy напрямую; новому через `MEANING_TOP` ← `kind_axis_hits` / `entity_form_*` |

