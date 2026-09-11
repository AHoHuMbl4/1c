# Карта M2: модули z01–z19, z21 против формулы №15 (2026-09-11)

Линза M2 «модули-помощники». Код только читался. Связь зон — `register_zone` /
`apply_bindings` (`ubuntu/serenedb/ask/_wire.py`, загрузка `_bootstrap.py:16-40`);
обычных `import zNN` нет. Вызовы — по имени в общем namespace. z20 разобран **только
как вызывающий** (~6225 строк). z04b включён (рядом с z04, в `_ZONE_FILES`).

Формула №15: вопрос → интерпретация из вики → запрос в БД → варианты с вики-подписями
→ выбор человека → ответ. Молчаливый выбор меры/сущности/периода/ветки = догадка = ВНЕ.

| модуль | строки | назначение | откуда вызывается | ступень / ВНЕ | решает за человека молча | вердикт (снести / ступень N / инертный) | риск сноса |
|---|---:|---|---|---|---|---|---|
| z01_infra_trace_llm | 911 | Инфра: DSN/роли, `psql`/`lit`, TRACE/deadline 88с, embed, `ds_chat`, `arbitrate`; константы бюджета; **здесь же** `INTENT_SYS` / `INTENT_SAMPLES` (не в z02) | z20: `psql`/`lit` десятки раз; `deadline_hit` :2667,:3465,:3697; `embed_model_live` :2453; `emb_ready` :2160,:2441,:2580; `ds_chat` :792,:5378; `arbitrate` :3862. Соседи: почти все зоны через `psql`/`ds_chat`/`embed_one` | инфра всех ступеней (B-дедлайн — разрешён) | нет (транспорт/бюджет); `arbitrate` — выбор текста между ответами, не выбор оси вопроса | **оставить (инфра)** | высокий: без модуля нет SQL/LLM |
| z02_intent | 713 | `parse_intent`: LLM→JSON координат (terms/kind/want/measure/period…); согласие `INTENT_SAMPLES`×`INTENT_LEAD`; словарь `same_concept_groups`; гейт `question_expects_accounting_data` | z20: `parse_intent` :1854,:1858,:5776; `question_expects_accounting_data` :1970. z21:928 (тот же символ — см. z16). Внутри: `_merge_intents`←`parse_intent` :673 | **2** (интерпретация), но **не из вики** — структура без wiki-карточек | да: большинство сэмплов выбирает kind/measure/terms без человека (`_merge_intents` :599–623; цикл :669–672). Это не меню ступени 4 | **ступень 2 (кандидат на замену вики-разбором)** | средний: весь тракт ждёт `intent`; снос без замены ломает preds/wiki vars |
| z03_period_windows | 615 | Окна периода: `period_preds`, `period_readings`, подписи `render_window_label`; **лидер MTD/WTD** `prefer_window_leader` / `apply_period_leader` | z20: `apply_period_leader` :1873; `prefer_window_leader` :1901; `period_form_from_question` :1897; `period_relative_forms` :728; `period_preds` :4691,:4693; `render_window_label` :1989. z09/z13/z05/z10 — readings/labels | **3** (фильтр даты) + **ВНЕ** (молчаливый лидер окна) | **да**: `prefer_window_leader` берёт mtd/wtd или `readings[0]` (`z03:377-393`); `apply_period_leader` пишет лидер в `intent["period"]` (`:581-611`) до вопроса человеку | **снести молчаливый лидер; preds/readings — ступень 3/4** | средний: preds нужны; лидер — догадка периода |
| z04_calendar_axis | 297 | Ось «календарный / рабочий день»: expand readings, `calendar_axis_open`, блок unavailable | z20: `calendar_day_basis_prefer` :1875; `expand_readings_calendar_axis` :1877; `calendar_axis_open` :1881; `calendar_axis_unavailable_block` :1913. z09:412-413; z13:192,787 | **4** (конкурирующие прочтения) + **ВНЕ** (prefer) | **да**, если нет ticket: `calendar_day_basis_prefer` (`z04:186+`) задаёт предпочитаемую day-basis до clarify | **ступень 4 без prefer; prefer — снести** | низкий на prefer; средний на всю ось (fork day-basis) |
| z04b_currency_axis | 567 | Ось «сумма док / сумма учёта»: expand, unit, mismatch gate, patch fork_scan | z20: `currency_amount_basis_prefer` :1876; `expand_readings_currency_axis` :1878; `currency_axis_open` :1907; `currency_mismatch_blocks_answer` :5317; `currency_unit_for_reading` :5325. z09:353,416-417; z13:196 | **4** + **ВНЕ** (prefer) | **да**: `currency_amount_basis_prefer` (`z04b:158+`); дефолт `_AMOUNT_BASIS_LEADER_DEFAULT=doc_amount` (:12) | **как z04** | как z04 |
| z05_entity_form | 1242 | Параллельный «формный» путь: event/count/compare sales, axis-for-count, period-clarify для событий, `try_entity_form_answer` | z20: много (`event_path_active` :2223+; `try_entity_form_answer` :3400; `try_event_count_period_clarify` :3394,:4355; `aggregate_compare_sales` :4616; `apply_proven_period` :1855; …). z09/z10/z11/z12/_bootstrap | **смесь 3/4/6** + **ВНЕ** (авто-ответ формой) | **да**: `try_entity_form_answer` / compare / collapse_guard обходят общий вики→меню; `entity_form_pick` внутри форм | **снести авто-путь; clarify периода события — ступень 4 (A-ранний)** | высокий: сцеплен с fork/sales/stock; точечный снос |
| z06_entity_search | 604 | Поиск сущностей в корпусе/индексе: `probe`, `match_expr`, `tables_of`, `meaning_candidates` (RRF+карточки), `alias_hits` | z20: `probe` :2013; `matched_group_count` :2027; `match_expr` :2040; `tables_of` :2043,:2182; `partial_tables` :2053; `question_exprs` :2101; `meaning_candidates` :2106; `date_only_kind_filter` :2108; `children_by_parent` :2155; `entity_pick_counts_for_model` :2259; `alias_hits` :2997; `keep_empty_period_opts` :1091 | **3** | нет (отбор кандидатов, не финальный выбор человека); порядок кандидатов влияет на то, что увидит вики/модель | **ступень 3** | высокий |
| z07_rrf_vectors | 575 | RRF/IVF ветки; `near_tables`; `rows_of`; `rerank`; `resolve_values`; `refuse_text`; **мёртвый** `clarify_text` | z20: `rows_of` :4039,:4067,:4735; `rerank` :2539; `refuse_text` ×11. z06: `near_tables`/`resolve_values`. `clarify_text` — только комментарии в z20 (:262,:3094,:4437), **вызовов нет** | **3** + отказ; clarify LLM — инерт | `rerank` может молча переупорядочить имена/оси (используется из pick_measure/rank) | **ступень 3; `clarify_text`/`signal_terms` — инерт снести** | низкий на инерт; средний на rerank-зависимости |
| z08_measures_totals | 278 | `measures_of` / `measure_aliases_of` / `totals_of`; флаги FORK_*/MEMORY | z20: `measures_of`/`measure_aliases_of`/`totals_of` десятки раз (:1282,:4119–:4445…). z12/z16/z18/_bootstrap | **3** | нет (чтение метаданных величин) | **ступень 3** | высокий |
| z09_fork_detector | 1018 | Детектор развилок: `fork_detector_scan` → классы/атомы по источникам×мера×окно | z20: `fork_detector_scan` :2675,:3480; `fork_labels_covering` :1092. z13 — labels/keys; z04b — labels | **4** (обнаружение многих прочтений) | сам по себе нет; кормит z13, где исход A отвечает без выбора | **ступень 4 (детектор)** | средний: без него меню развилок пустеет |
| z10_rank | 622 | Rank/«лидер»: `prefer_entity_for_rank`, `rank_axis_resolve`, детерминированный ответ, period-clarify API | z20: `prefer_entity_for_rank` :2228,:2662; `rank_intent_from` ×8; `rank_axis_resolve` :4467,:4518; `rank_axes_rerank` :4478; `rank_deterministic_answer` :4994; `rank_gate_fallback_answer` :5180; skips axis :4498,:4511. Соседи z11/z12/z05 | **ВНЕ** (prefer/детерминированный ответ) + куски **4/6** | **да**: `prefer_entity_for_rank` (`z10:428+`) двигает сущность в голову пула; `rank_deterministic_answer` отвечает без меню | **снести prefer + auto-answer; axis resolve→меню** | высокий на прод-эталоны rank |
| z11_sales | 824 | Канон «продали»: lift регистра, `sales_canon_*`, денежная мера, catalog_count prefer | z20: `prefer_entity_for_sales` :2229,:2661,:3272; `sales_canon_src`/:force_pool/:engaged/:money_measure/:rank_* — десятки мест (:1210–:4327…). Подозрение на легаси **подтверждается**: параллельный канон рядом с wiki-primary | **ВНЕ** | **да, системно**: `prefer_entity_for_sales` молча ставит accumulationregister (`z11:236-339`); `sales_money_measure` / `sales_force_money_measure` фиксируют меру без clarify (`:386+`, `:613+`); `sales_canon_force_pool` схлопывает пул (`:638+`) | **снести** | высокий: много эталонов/замков `sales_canon_locked`; wiki уважает этот замок первым (`z21:671-673`) |
| z12_stock_balance | 1346 | Склад/остатки: сигналы `stock_question_engaged`, оси склада, net-distinct, breakdown fallback; **orphaned** filter/prefer_stock | z20: `stock_question_engaged` :2187,:2647,:4360…; `stock_breakdown_leader_fallback` ×6; `warehouse_axis_values` :1748; `aggregate_stock_net_distinct` :4752; `rank_measure_hint` :4144+. z13/z11/z21. **Нет вызовов** `prefer_entity_for_stock` / `filter_stock_goods_registers` / `filter_balance_structural` / `balance_bridge_clarify` в ask-рантайме (есть тесты + `test_final_stock_route_filters_absent.py`) | **ВНЕ** (каноны/эвристики) + обломки **3/4** | **да** там, где ещё жив breakdown/net и `stock_canon_*` через bootstrap-патчи z20; orphaned prefer/filter уже не в маршруте | **orphaned API — снести; живые stock-эвристики — снести по формуле** | средний: тесты stock; bootstrap патчит z20 |
| z13_fork_outcomes | 936 | Исходы развилки A/B/C: уникальный ответ, mute, **clarify с человеческими подписями осей** | z20: `resolve_fork_outcome` :3526; `fork_outcome_unique/a/b/c` :3549–:3577; `prefer_mute_computed_over_clarify` :3839; `rank_defer_fork_outcome_b` :3560; `atom_terminal_gate_text` :5221 | **4** (меню) + **6** (A/unique) + **ВНЕ** (A без выбора) | **да** на A/unique/mute: ответ без ступени 5. **C** — спрашивает (`_fork_clarify_opts` :728–767; подписи measure/place/period) | **оставить C как ступень 4; A/mute — снести** | средний |
| z14_clarify_memory | 680 | Билеты выбора: `seal_clarify`/`consume_decision`/`peek_resolved`; `measure_choice` (чистая); captions | z20: decision HTTP :5833–:5898,:6143–:6158; `measure_choice` :1598,:4161,:4368; `entity_choice_locked`/`hold_settled_entity`/`guards_skip_for_choice`; `choice_proven` :4503 | **5** (+ утилиты меры для 4/3) | нет на decision_id-пути; **да**, если `ASK_MEMORY_APPLY`/resolved применяют прошлый выбор без нового меню (`peek_resolved` :5833+) — зависит от флагов (`ASK_MEMORY_APPLY` default 0 в z08:262) | **ступень 5** | высокий на decision_id |
| z15_answer_atoms | 437 | Атомы/слоты ответа: `build_answer_atom`, `compose_slot_values`, stop2 rivals | z20: `compose_slot_values`/`atom_from_agg`/`atom_operation`/`fill_atom_pairs`/`answer_money`…; z09/z13/z12/z16 — `build_answer_atom`/`render_atom_pair` | **6** | нет (упаковка чисел) | **ступень 6** | высокий |
| z16_veto_pick_entity | 637 | Вето алиасов, поддержка src, **`pick_measure`**, пустой pivot меры, дубль `question_expects_accounting_data` (грузится после z02 → побеждает) | z20: `pick_measure` :4172; `measure_ambiguous` :4165; veto/figures/alias ×много (:3018–:4401). z18/z09/z21 | **3/4** (мера) + **ВНЕ** (rerank-pick) | **да** при `how=='rerank'`/`'base'`: `pick_measure` возвращает top без меню (`z16:589-634`), хотя docstring запрещает угадывать при нескольких fits — rerank-ветка всё ещё выбирает | **снести молчаливый pick; ambiguous→ступень 4** | средний |
| z17_aggregate_groups | 698 | Агрегаты SQL: `aggregate`/`aggregate_groups`, оси `kind_axis_*`, `refcols_of` | z20: `aggregate` :4718,:4774; `aggregate_groups` :4671,:4693; `refcols_of`/`holders_of_target`/`kind_axis_*`… z05/z09/z10/z12 | **3** | нет (считает база) | **ступень 3** | высокий |
| z18_compose | 904 | Формулировка ответа: `compose`, passport, `axis_clarify_options`, money postprocess | z20: `compose` :5043,:5120; `build_answer_passport`/`ensure_*`/`measure_label_of`/`axis_clarify_options` :4533,:5018… | **6** + кусок **4** (`axis_clarify_options`) | нет на compose; axis options — меню (ок) | **ступень 6 (+4 меню оси)** | высокий |
| z19_answer_check | 368 | Пост-гейты: `check_claims`, `prompt_leak`, `asked_figure_missing`, `stale_note` | z20: `prompt_leak` :253,:818,:5098,:5158,:5426; `check_claims` :799; `asked_figure_missing` :5095,:5155; `stale_note` :6175 | **вне ступеней 1–6**, но не «догадка» — контроль после ответа | нет | **оставить (контроль) / не формула** | низкий на смысл формулы; высокий на регрессии гейта |
| z21_wiki_choice | 1126 | Вики-каскад: hybrid pool → LLM pick → passport verify → leader/clarify/none; **ядро ступени 2+4 по формуле** | z20: `wiki_primary_entity_cascade` :2745,:2808,:3215. Внутри зоны — все wiki_* (снаружи «инертны», но живы через cascade/`try_wiki_hybrid_entity_pick`) | **2** (вики-интерпретация сущностей) + **4** (clarify tie) + **6** при collapse | **да, частично**: один `yes` verify → leader без меню (`wiki_outcome_from_verify` :513-519) — по формуле при одном прочтении это **ОК**; **`_wiki_clarify_collapse_answer`** (`:820+`, вызов :980-983) схлопывает tie в ответ без человека — **ВНЕ**; `sales_canon_locked` короткое замыкание (`:671-673`) — обход вики | **ступень 2+4 (ядро); снести collapse и sales_canon bypass** | высокий: единственный заявленный путь сущности (`z21:659-694`) |

---

## Инертные модули / функции (вызовов в ask-рантайме нет)

Целых инертных **модулей z01–z19/z21 нет** — у каждого есть хотя бы один внешний вход из z20 или соседа. Ниже — **публичные функции без вызовов** вне своего файла (поиск `\bname\s*\(` по `ubuntu/serenedb/ask/*.py`; только определение / комментарий / тесты снаружи ask).

| символ | файл:def | доказательство пустоты вызовов |
|---|---|---|
| `ds_chat_post` | z01:564 | нет вызовов в ask |
| `same_concept_groups` | z02:156 | только внутри `parse_intent` (z02:676) — снаружи нет |
| `conversational_business_vague` | z02:301 | нет внешних вызовов |
| `signal_terms` | z07:249 | единственное вхождение — def |
| `clarify_text` | z07:295 | в z20 только комментарии (:262,:3094,:4437); живое меню — `clarify_say` (z20:326) |
| `fork_label_siblings` | z09:751 | нет вызовов |
| `rank_product_axis_col` | z10:298 | нет вызовов |
| `count_theme_code_pick_applies` | z10:494 | нет вызовов |
| `try_rank_period_clarify` | z10:593 | нет вызовов (в отличие от `try_event_count_period_clarify`) |
| `sales_ticket_hatch` | z11:679 | нет вызовов |
| `prefer_entity_for_stock` | z12:1080 | нет в ask; тест `test_final_stock_route_filters_absent.py` зовёт «orphan» |
| `filter_stock_goods_registers` | z12:868 | то же |
| `filter_balance_structural` | z12:1268 | то же (есть unit-тесты `test_stock_balance_path.py`) |
| `balance_bridge_clarify` | z12:1310 | то же |
| `resolved_unaccounted_slice_axis_word` | z12:250 | нет внешних |
| `question_asks_stock_balance` | z12:390 | нет внешних |
| `stock_subject_needs_clarify` | z12:622 | нет внешних |
| `filter_stock_balance_sales_noise` | z13:21 | нет в ask-рантайме; orphan-тест |
| `peek_decision` | z14:494 | нет внешних (`consume_decision` жив) |
| `reset_decisions_for_tests` | z14:565 | нет в ask (только имя для тестов) |
| `aggregate_live_column` | z17:162 | нет внешних |
| `atom_whitelist_labels` / `_numbers` | z16:14,:26 | нет внешних |
| `any_live_src_supports_question` | z16:309 | нет внешних |
| `alive_measure_names` | z16:466 | нет внешних |
| `format_measure_empty_pivot` | z16:493 | нет внешних (`build_measure_empty_pivot` жив) |
| z04 публичные без внешнего входа | `calendar_registers`, `calendar_working_day_keys`, `calendar_map_rows`, `calendar_day_basis_phrases`, `day_basis_from_question`, `calendar_day_basis_needed`, `calendar_axis_readings`, `prefer_day_basis_leader` | только def / внутренние |
| z04b публичные без внешнего входа | `currency_catalogs`, `currency_rate_registers`, `accounting_currency_key`, `currency_map_*`, `currency_basis_from_labels`, `currency_axis_applies`, `currency_axis_readings`, `prefer_amount_basis_leader`, `currency_fx_probe`, `currency_sum_for_basis`, `currency_unit_for_ref`, `currency_ref_requested` | только def / внутренние |
| z05 ряд форм | `entity_form_rank_single_window`, `sales_compare_split_month_pair`, `register_count_src`, `entity_form_count_target_is_movement`, `entity_form_rolling_year`, `entity_form_pre_entity_ok`, `entity_form_atom_*`, `event_count_period_unspecified`/`has_live_axis`/`period_clarify_applies`/`period_clarify`, `event_duel_applies`, `event_movement_feats`, `entity_form_axis_on_sales`, `entity_form_pick` | нет внешних вызовов (часть дергается через `globals().get` из z11 — **не инертны динамически**: `register_count_src`/`entity_form_count_target_is_movement` в `sales_canon_intent` z11:356-361) |
| z21 «снаружи инертные» wiki_* | все кроме `wiki_primary_entity_cascade` | **не мёртвые**: зовутся из cascade / `try_wiki_hybrid_entity_pick` внутри z21 |

`month_day_range_from_question` / `repair_period_from_question` (z03) снаружи ask не зовутся, но `repair_*` вызывается из `apply_period_leader` (z03:588) — **не инертны**.

---

## (а) Сколько строк уйдёт при сносе всех «ВНЕ» и инертных

Грубая оценка по **модулям с доминирующим вердиктом «снести»** (не «ступень N»):

| блок | строки | комментарий |
|---|---:|---|
| z11_sales | 824 | целиком канон-легаси |
| z05_entity_form | 1242 | авто-формы; уточнения периода частично оставить |
| z10_rank | 622 | prefer + deterministic |
| z12_stock_balance | 1346 | эвристики+orphans; часть сигналов ещё в z20 |
| молчаливые куски z03/z04/z04b (оценка) | ~200–350 | prefer_* / leader, не весь модуль |
| fork A/mute в z13 (оценка) | ~250 | C/меню оставить |
| collapse + bypass в z21 (оценка) | ~120 | cascade оставить |
| инертные функции (оценка LOC) | ~400–600 | clarify_text, stock filters, мёртвые exports |

**Итого порядка ~4.5–5.5k строк** из ~15400 у helper-зон, если сносить «ВНЕ» агрессивно.  
**Не входит:** z01/z06/z07(core)/z08/z09/z14/z15/z17/z18/z19/z21(core) — это ступени или инфра.

Точный процент без построчной разметки «оставить/снести» внутри смешанных файлов — не считался (честно: смешанные модули).

---

## (б) Какие ступени 1–6 НЕ покрыты модулями M2

| ступень | покрытие helper-модулями | пробел |
|---|---|---|
| **1** вопрос | нет отдельного zNN — HTTP/`answer()` в **z20** | M2 не картографирует вход |
| **2** интерпретация из **вики** | **z21** (карточки/паспорта) частично; **z02** — LLM-структура **без** вики | нет модуля «словарь синонимов вики → человеческая интерпретация вопроса» отдельного от entity-pick; INTENT живёт в z01+z02, не в wiki |
| **3** запрос в БД | z06, z07, z08, z17 (+ preds z03) | покрыто |
| **4** варианты с **описаниями из вики** | z21 clarify (labels из `search_tables`/`mk_opts`, hint из `opts_hints` в **z20**, не обязательно текст wiki-passport); z13 C (подписи осей/fork_label); z18 `axis_clarify_options`; A-ранний clarify в **z20** | **меню с вики-подписями как паспортными описаниями** — слабо: wiki format_passport_lines уходит в LLM verify, а человеку в options чаще `label` таблицы + hint реквизитов (`z20:mk_opts` :1075+; `z21:978`), не «описание из вики» |
| **5** выбор человека | z14 (decision_id / memory) + HTTP-ветка z20 | покрыто механизмом; формула требует, чтобы до этого не выбирали молча |
| **6** ответ | z15, z18, z19 (+ атомы fork) | покрыто |

**Кто строит меню:** `clarify_say` / `format_clarify_options` / `mk_opts` (**z20**), `fork_outcome_c` → `_fork_clarify_opts` (**z13**), wiki-tie → `mk_opts` (**z21:978**), `axis_clarify_options` (**z18**), warehouse/period options в **z20** (`warehouse_clarify` :1746, period assumed :1995).

**Кто строит интерпретацию:** сейчас **z02 `parse_intent`** (координаты) + **z21 wiki hybrid** (сущность по карточкам). По формуле №15 интерпретация должна быть **средствами вики** словами человека — z02 этому не равен; z21 ближе, но сразу выбирает src_table.

---

## (в) Неясные места (честно)

1. **`question_expects_accounting_data` определён в z02:361 и снова в z16:329.** Порядок загрузки `_bootstrap.py` — z16 после z02 → в рантайме побеждает z16. Какая реализация реально на проде при расхождении тел — нужно diff двух defs (здесь не сливались построчно).
2. **z21 docstring «единственный путь» vs живые `prefer_entity_for_sales/rank/catalog` в z20:2228-2230 и `sales_canon_locked`.** Каскад вики формально primary, но каноны продаж/ранга **переставляют cands до** и **коротят** wiki. Формально ли wiki «единственный» — спорно.
3. **`_bootstrap._patch_z20_*`** меняет поведение stock/sales/net **при загрузке**, текст на диске z20 может не совпадать с рантаймом. Карта M2 смотрела файлы на диске; патчи — отдельный слой (`_bootstrap.py:48+`).
4. **Динамический `globals().get("register_count_src")` и т.п.** делает часть «INERT» по статическому поиску ложно-мёртвой.
5. **INTENT_SAMPLES** — константа в **z01:889**, логика цикла — **z02:669**. Картографировать «intent» одним файлом нельзя.
6. Не проверялись вызовы из `ubuntu/serenedb/test_*.py` и приборов вне `ask/` — инертность = «не зовёт ask-рантайм», не «нет нигде в репо».
7. Подписи clarify из wiki-passport body человеку — **не подтверждены** как основной путь; нужны ли `wiki_format_passport_lines` в options — открытый вопрос к формуле.

---

## Краткие вердикты по «разобрать особо»

| фокус | вывод |
|---|---|
| z02 + INTENT_SAMPLES | ступень 2, но не вики; majority-vote = молчаливый выбор полей; SAMPLES в z01 |
| z03/z04/z04b | readings/expand = ступень 4; **prefer/leader = ВНЕ** |
| z05 | параллельный авто-тракт; снос по формуле |
| z06/z07/z08/z17 | ступень 3; инерт: `clarify_text`, `signal_terms` |
| z09 | детектор ступени 4 |
| z10 | prefer/детерминизм = ВНЕ |
| z11 | **легаси-канон, снести**; главный молчаливый выбор сущности/меры |
| z12 | фильтры/prefer_stock уже orphan; оставшиеся эвристики = ВНЕ |
| z13 | C = ступень 4; A/mute = ВНЕ |
| z14 | ступень 5 |
| z15/z18 | ступень 6 |
| z16 `pick_measure` | да, выбор меры; ambiguous→меню, rerank→молча |
| z19 | не формула, контроль |
| z21 | ядро 2+4; убрать collapse и sales_canon bypass |

---

*Источник фактов: чтение `ubuntu/serenedb/ask/z0*.py`, `z1*.py`, `z21_wiki_choice.py`, поиск вызовов в `z20_ask_main_http.py` и соседних зонах; `_bootstrap.py` `_ZONE_FILES`. Дата среза кода: 2026-09-11.*
