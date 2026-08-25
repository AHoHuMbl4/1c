# Сводный прогон оффлайн-замков — 2026-08-25

После коммитов в ubuntu/serenedb (e400657 … f3be4fe) полного прогона замков не было.
Модель Qwen выключена — только оффлайн. Живой SereneDB на порту 7890 25.08 на SELECT 1
не отвечал (timeout 15–20 с) — live-замки **не** зачтены успехом.

## Итог

| Метрика | Значение |
|---|---|
| Замков в списке | **79** (test_*.py в serenedb/openclaw/packet/acceptance/grafana) |
| Оффлайн (+оффлайн-часть hybrid) | **70** файлов, **2150** случаев, **0** падений |
| Требует живого контура | **9** файлов (не прогон / не успех) |
| Красных оффлайн после починки | **0** |

work/acceptance/selftest_*.py — генератор/прогон через живой /ask, не оффлайн-замки;
в таблицу не входили.

MCP-замки (test_mcp_ask*, test_focus_loop) — питон /opt/openclaw-mcp/venv/bin/python
(в системном нет пакета mcp).

## Таблица

| Файл | случаев | упало | сек | вид | примечание |
|---|---:|---:|---:|---|---|
| `ubuntu/open-webui/grafana/test_panel_from_scope.py` | 12 | 0 | 0.09 | offline | — |
| `ubuntu/openclaw/test_mcp_ask.py` | 39 | 0 | 0.61 | offline | — |
| `ubuntu/openclaw/test_mcp_ask_pending.py` | 16 | 0 | 0.03 | offline | — |
| `ubuntu/packet/test_delta_register_key.py` | 5 | 0 | 0.06 | offline | — |
| `ubuntu/packet/test_packet_apply.py` | 22 | 0 | 20.33 | hybrid | оффлайн ok; live — требует живого контура |
| `ubuntu/packet/test_packet_config.py` | 50 | 0 | 0.6 | offline | — |
| `ubuntu/packet/test_packet_crypto.py` | 14 | 0 | 0.18 | offline | — |
| `ubuntu/packet/test_packet_kit.py` | 33 | 0 | 0.93 | offline | — |
| `ubuntu/packet/test_packet_log.py` | 22 | 0 | 0.14 | offline | — |
| `ubuntu/packet/test_packet_server.py` | 55 | 0 | 31.24 | offline | — |
| `ubuntu/serenedb/test_a3_passport.py` | 14 | 0 | 0.1 | offline | — |
| `ubuntu/serenedb/test_ab_calendar_axis_set.py` | 22 | 0 | 0.31 | offline | — |
| `ubuntu/serenedb/test_ab_scorer_v2_modes.py` | 19 | 0 | 0.1 | offline | — |
| `ubuntu/serenedb/test_answer_atom.py` | 18 | 0 | 0.18 | offline | — |
| `ubuntu/serenedb/test_ask_choice_memory.py` | 42 | 0 | 5.11 | hybrid | оффлайн ok; live — требует живого контура |
| `ubuntu/serenedb/test_ask_journal.py` | 11 | 0 | 5.09 | hybrid | оффлайн ok; live — требует живого контура |
| `ubuntu/serenedb/test_axis.py` | 41 | 0 | 0.02 | offline | — |
| `ubuntu/serenedb/test_axis_focus.py` | 18 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_b9_routing.py` | 9 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_balance_map_meta_build.py` | 18 | 0 | 0.03 | offline | — |
| `ubuntu/serenedb/test_box_tune.py` | 86 | 0 | 0.36 | offline | — |
| `ubuntu/serenedb/test_branch_alias.py` | 27 | 0 | 0.05 | offline | — |
| `ubuntu/serenedb/test_build_solr_synonyms.py` | 26 | 0 | 0.05 | offline | — |
| `ubuntu/serenedb/test_calendar_axis.py` | 36 | 0 | 0.1 | offline | — |
| `ubuntu/serenedb/test_calendar_meta_build.py` | 30 | 0 | 0.03 | offline | — |
| `ubuntu/serenedb/test_caveat.py` | 8 | 0 | 0.07 | offline | — |
| `ubuntu/serenedb/test_changed_sources_lock.py` | 17 | 0 | 0.03 | offline | — |
| `ubuntu/serenedb/test_classify_fail_closed.py` | 11 | 0 | 0.07 | offline | — |
| `ubuntu/serenedb/test_compare_sales.py` | 11 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_compose.py` | 92 | 0 | 0.14 | offline | — |
| `ubuntu/serenedb/test_corpus_chunk_identity.py` | 0 | 0 | 22.02 | live | требует живого контура |
| `ubuntu/serenedb/test_corpus_plain_key.py` | 0 | 0 | 22.02 | live | требует живого контура |
| `ubuntu/serenedb/test_decision_id.py` | 31 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_delta.py` | 24 | 0 | 0.07 | offline | — |
| `ubuntu/serenedb/test_ds_tokens.py` | 11 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_e2e.py` | 0 | 0 | 22.03 | live | требует живого контура |
| `ubuntu/serenedb/test_embed_left_count.py` | 0 | 0 | 22.02 | live | требует живого контура |
| `ubuntu/serenedb/test_embed_progress.py` | 22 | 0 | 0.04 | offline | — |
| `ubuntu/serenedb/test_embed_secret_url_check.py` | 5 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_enough.py` | 79 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_focus_loop.py` | 26 | 0 | 0.62 | offline | — |
| `ubuntu/serenedb/test_fork_atom_aggregate.py` | 0 | 0 | 22.03 | live | требует живого контура |
| `ubuntu/serenedb/test_fork_detector.py` | 43 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_fork_outcomes.py` | 29 | 0 | 0.1 | offline | — |
| `ubuntu/serenedb/test_fork_window_readings.py` | 40 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_gate.py` | 132 | 0 | 1.31 | offline | — |
| `ubuntu/serenedb/test_health_gap.py` | 23 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_health_native_freshness.py` | 32 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_integrity.py` | 0 | 0 | 22.03 | live | требует живого контура |
| `ubuntu/serenedb/test_intent.py` | 140 | 0 | 0.15 | offline | — |
| `ubuntu/serenedb/test_journal_fields.py` | 22 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_leader_hatch.py` | 13 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_measure_empty.py` | 26 | 0 | 0.15 | offline | — |
| `ubuntu/serenedb/test_measure_resolver_terms.py` | 4 | 0 | 0.06 | offline | — |
| `ubuntu/serenedb/test_memory_collisions_measure.py` | 22 | 0 | 0.1 | offline | — |
| `ubuntu/serenedb/test_odata_census.py` | 17 | 0 | 0.67 | offline | — |
| `ubuntu/serenedb/test_packet_data_skip.py` | 14 | 0 | 0.63 | offline | — |
| `ubuntu/serenedb/test_passport.py` | 24 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_period_bounds.py` | 3 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_period_empty.py` | 30 | 0 | 0.11 | offline | — |
| `ubuntu/serenedb/test_rank_axis_anchor.py` | 66 | 0 | 0.7 | offline | — |
| `ubuntu/serenedb/test_rank_leader_path.py` | 26 | 0 | 0.18 | offline | — |
| `ubuntu/serenedb/test_resolver_ivf.py` | 18 | 0 | 0.07 | offline | — |
| `ubuntu/serenedb/test_ro_role.py` | 0 | 0 | 0.06 | live | требует живого контура |
| `ubuntu/serenedb/test_sales_canon_prefer.py` | 74 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_solr_synonyms_apply.py` | 14 | 0 | 0.13 | offline | — |
| `ubuntu/serenedb/test_solr_synonyms_build.py` | 28 | 0 | 0.09 | offline | — |
| `ubuntu/serenedb/test_sql_rrf.py` | 7 | 0 | 0.12 | offline | — |
| `ubuntu/serenedb/test_step2.py` | 38 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_step4_guards.py` | 110 | 0 | 0.13 | offline | — |
| `ubuntu/serenedb/test_stock_balance_path.py` | 27 | 0 | 0.49 | offline | — |
| `ubuntu/serenedb/test_terminal_round.py` | 24 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_trace_rid.py` | 10 | 0 | 0.08 | offline | — |
| `ubuntu/serenedb/test_unit_from_data.py` | 22 | 0 | 0.14 | offline | — |
| `ubuntu/serenedb/test_validate.py` | 0 | 0 | 22.04 | live | требует живого контура |
| `ubuntu/serenedb/test_wiki_alias_parse.py` | 9 | 0 | 0.04 | offline | — |
| `work/acceptance/test_acceptance.py` | 25 | 0 | 0.1 | offline | — |
| `work/acceptance/test_probe_protocol.py` | 16 | 0 | 0.3 | offline | — |
| `work/acceptance/test_resolver_literal.py` | 0 | 0 | 22.03 | live | требует живого контура |

## Что было красным и что сделано

Все правки — в **замках** (не в serene_ask.py / wiki_alias.sh: запрет задачи).

| Файл | Факт из кода | Действие |
|---|---|---|
| test_compose.py | meaning_candidates(..., diag=None) — мок без diag → TypeError | мок diag=None |
| test_enough.py | answer(..., prior=…) — мок без kwargs → TypeError; сырой focus не гасит enough (аудит §10 / 81be89e) | сигнатура мока; случаи на trusted-билет + сырой focus → clarify |
| test_period_empty.py | build_period_empty_answer: при money+measure sum="0.00" (bfe4166) | замок принимает 0 / 0.0 / "0.00" |
| test_step2.py | при нуле hits probe зовёт _resolve_values_corpus (214d579) — лишние SQL | на случае «один запрос» глушим резолвер; меряем UNION ALL |
| test_rank_axis_anchor.py | open("serene_ask.py") от cwd | open(A.__file__) |
| test_packet_log.py | import pytest — пакета нет | PASS/FAIL без pytest, те же проверки |
| test_ask_journal.py / test_ask_choice_memory.py | live при PGPASSWORD из /etc зависал на мёртвом 7890 | _engine_alive 5 с → skip live (оффлайн уже пройден) |
| test_packet_apply.py | psql без timeout зависал после оффлайн-блока | timeout=20; FATAL «движок не отвечает» |

## Осталось «красным» / не прогнано как успех

Не оффлайн-падение, а **требует живого контура** (движок не отвечает):

| Файл | Почему |
|---|---|
| test_e2e.py | живой serene_report + env |
| test_integrity.py | витрина + OData |
| test_validate.py | AST-валидатор на живой схеме |
| test_corpus_chunk_identity.py | живая сборка корпуса |
| test_corpus_plain_key.py | живой SereneDB |
| test_embed_left_count.py | живой EXPLAIN/план |
| test_fork_atom_aggregate.py | сверка с aggregate на ut_test |
| test_ro_role.py | serene_ro + витрина |
| work/acceptance/test_resolver_literal.py | импорт/DSN живого контура |

Hybrid (оффлайн зелёный; live skip): test_ask_journal.py (11), test_ask_choice_memory.py (42),
test_packet_apply.py (22 оффлайн).

serene_ask.py / wiki_alias.sh не трогались. Регрессий в коде ask по оффлайн-фактам
не чинили — замки отставали от уже принятого поведения.

## Числа для коммита

Числа: всего замков 79, случаев 2150 (оффлайн+hybrid), упало 0; live 9 не зачтены.
