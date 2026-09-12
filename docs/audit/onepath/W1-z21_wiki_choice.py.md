# W1: карта живости `z21_wiki_choice.py`

Зона: `ubuntu/serenedb/ask/z21_wiki_choice.py` (1128 строк файла).
Метод: AST top-level + grep по слову (word-boundary) по `ask/*.py` и `ubuntu/serenedb/test_*.py`;
транзитивность — граф вызовов внутри зоны; getattr/globals().get/строки — отдельно.
Чужие отчёты onepath/ не читались. Код не менялся.

## Вердикт зоны

| Вердикт | Символов | Строк символов |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 58 | 984 |
| **ЖИВА ТОЛЬКО LEGACY** | 1 | 21 |
| **МЁРТВА** | 0 | 0 |
| сумма символов | 59 | 1005 |
| вне символов (шапка/пустоты/`register_zone`) | — | 123 |

**Итог:** зона **нужна одному пути**. Единственный вход нового тракта —
`wiki_primary_entity_cascade` (`z20_ask_main_http.py:1951`); через него транзитивно
жива почти вся зона (58/59 символов, 984 строк). После flip и сноса legacy
умрёт только `wiki_leader_alive` (21 строка) — гейт развилок В4 в legacy/z13.
`WIKI_PICK_SYS`/`WIKI_VERIFY_SYS` дополнительно стоят в `OUR_PROMPTS` нового z20
(`:756`, для `prompt_leak`).

`_bootstrap.py`: грузит файл зоны (`z21_wiki_choice.py` в списке); символы не зовёт.
Патч `_patch_z20_wiki_primary` применяется только к **legacy** z20 при exec.
`_imports.py` / `_wire.py`: упоминаний символов зоны нет (только `register_zone` в конце файла зоны).

## Таблица символов

| Символ | Стр. | Кто зовёт | Вердикт |
|---|---:|---|---|
| `WIKI_KNN_N` | 1 | внутр: _wiki_hybrid_vars | ЖИВА НОВОМУ |
| `WIKI_PICK_N` | 1 | внутр: _wiki_hybrid_vars<br>тест: test_wiki_candidate_verify.py:139,141,142 | ЖИВА НОВОМУ |
| `WIKI_ALIAS_TOP` | 1 | внутр: _wiki_hybrid_vars | ЖИВА НОВОМУ |
| `WIKI_PASSPORT_N` | 1 | внутр: _wiki_substitute_passport_sql, wiki_format_passport_lines, wiki_outcome_from_verify, wiki_passport_enrich, wiki_verify_candidates<br>тест: test_verify_threshold_menu.py:50, test_wiki_candidate_verify.py:141,142, test_wiki_captions_builder.py:50 | ЖИВА НОВОМУ |
| `WIKI_VERIFY_MAX_TOKENS` | 1 | внутр: wiki_verify_candidates<br>тест: test_wiki_candidate_verify.py:344,345 | ЖИВА НОВОМУ |
| `WIKI_PASSPORT_BODY_MAX` | 1 | внутр: _wiki_substitute_passport_sql, wiki_format_passport_lines<br>тест: test_verify_threshold_menu.py:51, test_wiki_captions_builder.py:51 | ЖИВА НОВОМУ |
| `WIKI_SEP_GAP` | 1 | внутр: wiki_knn_separable | ЖИВА НОВОМУ |
| `WIKI_EMBED_MAXLEN` | 1 | внутр: _wiki_hybrid_vars | ЖИВА НОВОМУ |
| `_HYBRID_SQL` | 1 | внутр: _wiki_hybrid_sql | ЖИВА НОВОМУ |
| `_PASSPORT_SQL` | 1 | внутр: _wiki_passport_sql | ЖИВА НОВОМУ |
| `_wiki_hybrid_sql` | 5 | внутр: wiki_hybrid_pool | ЖИВА НОВОМУ |
| `_wiki_passport_sql` | 5 | внутр: wiki_passport_enrich | ЖИВА НОВОМУ |
| `WIKI_PICK_SYS` | 4 | NEW: ask/z20_ask_main_http.py:756<br>внутр: wiki_pick_from_cards<br>тест: test_one_path.py:291 | ЖИВА НОВОМУ |
| `WIKI_VERIFY_SYS` | 8 | NEW: ask/z20_ask_main_http.py:756<br>внутр: wiki_verify_candidates<br>тест: test_wiki_candidate_verify.py:117,135 | ЖИВА НОВОМУ |
| `wiki_aggregate_want` | 14 | внутр: _wiki_hybrid_vars<br>тест: test_wiki_card_hybrid.py:149,150,151 | ЖИВА НОВОМУ |
| `wiki_action_class` | 4 | внутр: _wiki_hybrid_vars<br>тест: test_wiki_card_hybrid.py:152,153,154,155,156,157 | ЖИВА НОВОМУ |
| `wiki_action_axis` | 2 | внутр: wiki_axis_phrase | ЖИВА НОВОМУ |
| `wiki_platform_kind` | 6 | внутр: wiki_hybrid_pool, wiki_passport_enrich | ЖИВА НОВОМУ |
| `_NAMED_PLATFORM_TYPE_PHRASES` | 24 | внутр: _named_type_phrase_patterns | ЖИВА НОВОМУ |
| `_NAMED_TYPE_WORD_RE` | 20 | внутр: _named_type_phrase_patterns | ЖИВА НОВОМУ |
| `_NAMED_TYPE_PHRASE_RE` | 1 | внутр: _named_type_phrase_patterns | ЖИВА НОВОМУ |
| `_norm_ye` | 2 | внутр: _named_type_phrase_patterns, named_platform_kinds | ЖИВА НОВОМУ |
| `_named_type_phrase_patterns` | 22 | внутр: named_platform_kinds | ЖИВА НОВОМУ |
| `named_platform_kinds` | 13 | внутр: filter_pool_by_named_type<br>тест: test_named_type_filter.py:87,137 | ЖИВА НОВОМУ |
| `_card_odata_kind` | 4 | внутр: filter_pool_by_named_type | ЖИВА НОВОМУ |
| `filter_pool_by_named_type` | 19 | внутр: try_wiki_hybrid_entity_pick<br>тест: test_named_type_filter.py:88 | ЖИВА НОВОМУ |
| `wiki_axis_phrase` | 30 | внутр: _wiki_hybrid_vars | ЖИВА НОВОМУ |
| `_WIKI_AXIS_CARRIERS` | 1 | внутр: _wiki_axis_has_carriers | ЖИВА НОВОМУ |
| `_wiki_axis_has_carriers` | 26 | внутр: wiki_axis_phrase, wiki_leader_post_verify<br>тест: test_wiki_candidate_verify.py:368,429,471,549 | ЖИВА НОВОМУ |
| `_wiki_hybrid_vars` | 28 | внутр: wiki_hybrid_pool | ЖИВА НОВОМУ |
| `_wiki_substitute_sql` | 10 | внутр: wiki_hybrid_pool | ЖИВА НОВОМУ |
| `wiki_hybrid_pool` | 40 | внутр: try_wiki_hybrid_entity_pick<br>тест: test_named_type_filter.py:169, test_wiki_candidate_verify.py:264,391,411, test_wiki_card_hybrid.py:192 | ЖИВА НОВОМУ |
| `wiki_format_card_lines` | 12 | внутр: wiki_pick_from_cards<br>тест: test_wiki_card_hybrid.py:179 | ЖИВА НОВОМУ |
| `wiki_menu_captions` | 41 | LEG: ask/z20_ask_main_http_legacy.py:3109,3137<br>Z: ask/z13_fork_outcomes.py:798,848 (822 — docstring, не зов)<br>внутр: try_wiki_hybrid_entity_pick<br>тест: test_wiki_candidate_verify.py:568, test_wiki_captions_builder.py:2,62,63 | ЖИВА НОВОМУ (+прям. LEG/z13) |
| `wiki_captions_map_from_cards` | 10 | LEG: ask/z20_ask_main_http_legacy.py:3110, ask/z20_ask_main_http_legacy.py:3138<br>Z: ask/z13_fork_outcomes.py:800, ask/z13_fork_outcomes.py:849<br>внутр: try_wiki_hybrid_entity_pick | ЖИВА НОВОМУ (+прям. LEG/z13) |
| `_wiki_substitute_passport_sql` | 13 | внутр: wiki_passport_enrich | ЖИВА НОВОМУ |
| `_wiki_parse_axes_set` | 9 | внутр: wiki_passport_distinct | ЖИВА НОВОМУ |
| `_wiki_parse_measures_set` | 9 | внутр: wiki_passport_distinct | ЖИВА НОВОМУ |
| `wiki_passport_distinct` | 18 | внутр: wiki_passport_enrich<br>тест: test_wiki_candidate_verify.py:145 | ЖИВА НОВОМУ |
| `wiki_passport_enrich` | 43 | LEG: ask/z20_ask_main_http_legacy.py:3108, ask/z20_ask_main_http_legacy.py:3136<br>Z: ask/z13_fork_outcomes.py:796, ask/z13_fork_outcomes.py:797, ask/z13_fork_outcomes.py:847<br>внутр: wiki_verify_candidates<br>тест: test_fork_outcomes.py:457,458,467, test_wiki_candidate_verify.py:137,153, test_wiki_leader_not_overridden.py:101,102,115 | ЖИВА НОВОМУ (+прям. LEG/z13) |
| `wiki_format_passport_lines` | 27 | внутр: wiki_verify_candidates<br>тест: test_wiki_candidate_verify.py:157,173 | ЖИВА НОВОМУ |
| `_WIKI_VERIFY_FIT_MAP` | 5 | внутр: _wiki_row_to_verdict | ЖИВА НОВОМУ |
| `_wiki_row_to_verdict` | 17 | внутр: _wiki_salvage_verdicts, _wiki_verdicts_from_rows | ЖИВА НОВОМУ |
| `_wiki_verdicts_from_rows` | 9 | внутр: wiki_parse_verify_response | ЖИВА НОВОМУ |
| `_wiki_salvage_verdicts` | 38 | внутр: wiki_parse_verify_response | ЖИВА НОВОМУ |
| `wiki_parse_verify_response` | 27 | внутр: wiki_verify_candidates<br>тест: test_wiki_candidate_verify.py:177,189,198,206,214,318… | ЖИВА НОВОМУ |
| `wiki_outcome_from_verify` | 50 | внутр: wiki_verify_candidates<br>тест: test_verify_threshold_menu.py:73,83,94,106, test_wiki_candidate_verify.py:138,185,194,203,211 | ЖИВА НОВОМУ |
| `wiki_verify_candidates` | 35 | внутр: try_wiki_hybrid_entity_pick<br>тест: test_named_type_filter.py:170, test_wiki_candidate_verify.py:136,228,236,245,253,260…, test_wiki_card_hybrid.py:262 | ЖИВА НОВОМУ |
| `wiki_knn_separable` | 8 | внутр: wiki_pick_from_cards<br>тест: test_wiki_candidate_verify.py:118, test_wiki_card_hybrid.py:173,176 | ЖИВА НОВОМУ |
| `wiki_validate_leader_axes` | 13 | внутр: wiki_outcome_from_verify, wiki_pick_from_cards<br>тест: test_wiki_candidate_verify.py:227,244,333,392, test_wiki_card_hybrid.py:200,223 | ЖИВА НОВОМУ |
| `wiki_pick_from_cards` | 56 | внутр: try_wiki_hybrid_entity_pick<br>тест: test_named_type_filter.py:171, test_wiki_candidate_verify.py:280, test_wiki_card_hybrid.py:183,187,208,225 | ЖИВА НОВОМУ |
| `wiki_primary_entity_cascade` | 42 | NEW: ask/z20_ask_main_http.py:1951<br>LEG: ask/z20_ask_main_http_legacy.py:2513 (2450,2740 — комментарии)<br>тест: test_one_path.py:164,165,167,274,276,279, test_wiki_card_hybrid.py:234,250,257,258,272,291… | ЖИВА НОВОМУ (вход) |
| `try_wiki_hybrid_entity_pick` | 86 | внутр: wiki_primary_entity_cascade<br>тест: test_named_type_filter.py:174,188, test_wiki_candidate_verify.py:287,305,398,405,416, test_wiki_card_hybrid.py:107,196,231,247,301,314 | ЖИВА НОВОМУ |
| `wiki_intent_named_measures` | 21 | внутр: wiki_leader_post_verify<br>тест: test_wiki_candidate_verify.py:353,356 | ЖИВА НОВОМУ |
| `wiki_axis_is_question_subject` | 10 | внутр: wiki_leader_post_verify<br>тест: test_wiki_candidate_verify.py:354,359,362 | ЖИВА НОВОМУ |
| `wiki_leader_carries_axis` | 32 | внутр: wiki_leader_post_verify<br>тест: test_wiki_candidate_verify.py:354,458,472 | ЖИВА НОВОМУ |
| `wiki_leader_post_verify` | 31 | внутр: try_wiki_hybrid_entity_pick<br>тест: test_wiki_candidate_verify.py:353,425,461,481,491,500… | ЖИВА НОВОМУ |
| `wiki_leader_alive` | 21 | LEG: ask/z20_ask_main_http_legacy.py:2760, ask/z20_ask_main_http_legacy.py:2984, ask/z20_ask_main_http_legacy.py:3051, ask/z20_ask_main_http_legacy.py:3093<br>Z: ask/z13_fork_outcomes.py:902<br>тест: test_fork_outcomes.py:439,440,443,444, test_no_pre_wiki_reorders.py:122, test_wiki_leader_not_overridden.py:40,51,52,58,59,80… | ЖИВА ТОЛЬКО LEGACY |
| `wiki_measure_carried` | 24 | внутр: wiki_leader_post_verify<br>тест: test_wiki_candidate_verify.py:370,389,422,428, test_wiki_card_hybrid.py:163 | ЖИВА НОВОМУ |

## Транзитивные цепочки (к корню z20)

### Новый тракт

```
wiki_primary_entity_cascade  ←  z20_ask_main_http.py:1951
  └─ try_wiki_hybrid_entity_pick
       ├─ wiki_hybrid_pool
       │    ├─ _wiki_hybrid_sql → _HYBRID_SQL
       │    ├─ _wiki_hybrid_vars
       │    │    ├─ WIKI_ALIAS_TOP, WIKI_EMBED_MAXLEN, WIKI_KNN_N, WIKI_PICK_N
       │    │    ├─ wiki_action_class
       │    │    ├─ wiki_aggregate_want
       │    │    └─ wiki_axis_phrase → wiki_action_axis, _wiki_axis_has_carriers → _WIKI_AXIS_CARRIERS
       │    ├─ _wiki_substitute_sql
       │    └─ wiki_platform_kind
       ├─ filter_pool_by_named_type
       │    ├─ named_platform_kinds → _named_type_phrase_patterns
       │    │         → _NAMED_PLATFORM_TYPE_PHRASES, _NAMED_TYPE_WORD_RE, _NAMED_TYPE_PHRASE_RE, _norm_ye
       │    └─ _card_odata_kind
       ├─ wiki_verify_candidates
       │    ├─ wiki_passport_enrich → _wiki_passport_sql → _PASSPORT_SQL
       │    │                      → _wiki_substitute_passport_sql → WIKI_PASSPORT_BODY_MAX, WIKI_PASSPORT_N
       │    │                      → wiki_passport_distinct → _wiki_parse_axes_set, _wiki_parse_measures_set
       │    │                      → wiki_platform_kind
       │    ├─ wiki_format_passport_lines → WIKI_PASSPORT_BODY_MAX, WIKI_PASSPORT_N
       │    ├─ WIKI_VERIFY_SYS, WIKI_VERIFY_MAX_TOKENS, WIKI_PASSPORT_N
       │    ├─ wiki_parse_verify_response
       │    │    ├─ _wiki_verdicts_from_rows → _wiki_row_to_verdict → _WIKI_VERIFY_FIT_MAP
       │    │    └─ _wiki_salvage_verdicts → _wiki_row_to_verdict
       │    └─ wiki_outcome_from_verify → wiki_validate_leader_axes
       ├─ wiki_pick_from_cards
       │    ├─ wiki_knn_separable → WIKI_SEP_GAP
       │    ├─ wiki_format_card_lines
       │    ├─ WIKI_PICK_SYS
       │    └─ wiki_validate_leader_axes
       ├─ wiki_captions_map_from_cards / wiki_menu_captions  (clarify-меню)
       └─ wiki_leader_post_verify
            ├─ wiki_intent_named_measures
            ├─ wiki_measure_carried
            ├─ wiki_axis_is_question_subject
            ├─ _wiki_axis_has_carriers
            └─ wiki_leader_carries_axis

WIKI_PICK_SYS / WIKI_VERIFY_SYS  ←  также OUR_PROMPTS @ z20_ask_main_http.py:756
```

### Legacy (дополнительные прямые входы, кроме общего каскада)

```
wiki_primary_entity_cascade  ←  z20_ask_main_http_legacy.py:2513
wiki_leader_alive            ←  legacy:2760,2984,3051,3093
                               ←  z13 resolve_fork_wiki_gate:902  (зовётся только тестами)
wiki_passport_enrich         ←  legacy:3108,3136
  + wiki_menu_captions       ←  legacy:3109,3137
  + wiki_captions_map_…      ←  legacy:3110,3138
  те же три                 ←  z13 fork_outcome_c:796-800
                            ←  z13 fork_clarify_from_wiki_pool:847-849
                                 ↑ fork_clarify ← legacy:3012
                                 ↑ fork_outcome_c ← legacy:3023
                                 ↑ resolve_fork_wiki_gate → fork_clarify (тесты)
```

Новый z20 **не** зовёт `wiki_leader_alive`, `fork_outcome_c`,
`fork_clarify_from_wiki_pool`, `resolve_fork_wiki_gate` — прямых/косвенных
упоминаний в `z20_ask_main_http.py` нет.

## Скрытые выбиратели, доступные новому тракту

Через `wiki_primary_entity_cascade` новый тракт **получает** кодовые фильтры/гейты
внутри вики-каскада (не отдельные терминалы до вики, но выбор/отсев сущности/оси/меры кодом):

| Символ | Что выбирает/режет кодом |
|---|---|
| `named_platform_kinds` + `filter_pool_by_named_type` | тип источника (OData-kind) по роду метаданных в тексте вопроса — режет пул до LLM/verify |
| `wiki_aggregate_want` / `wiki_action_class` / `wiki_axis_phrase` → hybrid SQL | структурное сужение пула (agg/класс/ось/мера из intent) в `wiki_hybrid_pool` |
| `_wiki_axis_has_carriers` | включать ли ось в SQL-фильтр (есть ли носители в базе) |
| `wiki_validate_leader_axes` | allowlist префиксов src (`catalog`/`document`/`*register`/…) — отвергает лидера |
| `wiki_knn_separable` + gap в `wiki_pick_from_cards` | код форсирует clarify вместо лидера при малом kNN-зазоре |
| `wiki_outcome_from_verify` | код: leader / clarify / none по счёту yes/no/unsure (не «лучший из плохих») |
| `wiki_leader_post_verify` (+ `wiki_measure_carried`, `wiki_leader_carries_axis`) | пост-гейт: отвергнуть уже выбранного лидера, если не несёт названную меру/ось |

`wiki_leader_alive` — **не** в новом тракте: это гейт «уступить вики-лидеру» для
меню развилок legacy/z13; после сноса legacy для одного пути не нужен.

## Замки (тесты)

| Тест | Символы зоны |
|---|---|
| `test_one_path.py` | wiki_primary_entity_cascade, WIKI_PICK_SYS |
| `test_wiki_card_hybrid.py` | wiki_primary_entity_cascade, try_wiki_hybrid_entity_pick, wiki_hybrid_pool, wiki_pick_from_cards, wiki_verify_candidates, wiki_aggregate_want, wiki_action_class, wiki_format_card_lines, wiki_knn_separable, wiki_validate_leader_axes, wiki_measure_carried |
| `test_wiki_candidate_verify.py` | verify/passport/pick/post_verify семейство (см. таблицу) |
| `test_named_type_filter.py` | named_platform_kinds, filter_pool_by_named_type, try_wiki_hybrid_entity_pick, … |
| `test_wiki_captions_builder.py` | wiki_menu_captions, WIKI_PASSPORT_* |
| `test_verify_threshold_menu.py` | wiki_outcome_from_verify, WIKI_PASSPORT_* |
| `test_fork_outcomes.py` | wiki_leader_alive, wiki_passport_enrich |
| `test_wiki_leader_not_overridden.py` | wiki_leader_alive, wiki_passport_enrich |
| `test_no_pre_wiki_reorders.py` | wiki_leader_alive (проверка текста legacy z20) |

## getattr / строковые зовы

Единственный `globals().get("wiki_passport_enrich")` — `z13_fork_outcomes.py:796`
(перед прямым вызовом в `fork_outcome_c`). В новом z20 таких ссылок нет.

