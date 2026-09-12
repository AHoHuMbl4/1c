# O1: построчная карта z20 — ступени формулы vs остатки-нарушители

Срез: диск `ubuntu/serenedb/ask/z20_ask_main_http.py` (5094 строки) + инжект
`_patch_z20_wiki_primary` из `ubuntu/serenedb/ask/_bootstrap.py` (строки 47–165,
применяется в `_exec_zone` ~207). Код не менялся; вердикты — по формуле владельца
12.09 (`docs/audit/snos15-ONEPATH_PLAN.md`).

## Вершинный контракт (мера)

```
вопрос → интерпретация из вики → запрос в базу →
варианты с описаниями из вики (если прочтений >1) → выбор человека → ответ
```

- **СТУПЕНЬ ФОРМУЛЫ** — нужный шаг этого пути (включая единый построитель меню и
  compose+gate после SQL).
- **ИНФРАСТРУКТУРА** — HTTP/токен/decision_id/health/журнал/тайминги/дедлайн;
  сохраняется, не обсуждается.
- **НАРУШЕНИЕ / ЛИШНЕЕ** — не ступень и не инфра: кандидат на снос в «одном пути».

Критерий: код сам выбирает источник/меру/период/ось **без решения вики** или
отвечает/уточняет **до** wiki-каскада / мимо него → НАРУШЕНИЕ. Меню при >1
прочтении — ступень, **если** оно построено единым построителем по решению
каскада; отдельный механизм «clarify A / F / ecp / fork-исход» при том же
содержании — всё равно отдельный нарушитель-держатель.

---

## 0. Сводка числами

| Вердикт | Блоков в таблице | Оценка строк (диск) |
|---|---:|---:|
| СТУПЕНЬ ФОРМУЛЫ | 28 | ~2140 |
| ИНФРАСТРУКТУРА | 14 | ~980 |
| НАРУШЕНИЕ / ЛИШНЕЕ | 32 | ~1974 |
| **Итого диск** | **74** | **5094** |

Инжект-патч (не на диске, в рантайме): **+~25 строк net-distinct**, **1 правка
условия ef_gate**, **возможный reorder ecp0↔F** — все три **НАРУШЕНИЕ**.

**Итог сноса нарушителей (диск):** ≈ **1970 строк** уйдут или переедут в
тонкий pipeline (плюс удаление/обнуление инжекта в `_bootstrap`). Часть «меню
при >1» (~early clarify / fork C / measure menus) по смыслу **останется** как
ступень — в таблице помечена «нарушитель-держатель → слить в единый
построитель», не «выкинуть ответ человеку».

---

## 1. Инжект `_patch_z20_wiki_primary` (`_bootstrap.py`)

| Патч | Якорь в z20 | Что добавляет | Вердикт | Обоснование |
|---|---|---|---|---|
| **net-distinct #1** | ветка `elif agg is None and serene_axis and … no_axis_member(grain_dec)` (~3808) | до ordinary aggregate: если `stock_canon_locked` **или** `stock_count_aggregate_without_subject` и не named product → `aggregate_stock_net_distinct` | **НАРУШЕНИЕ** | Скрытый выбиратель меры/оси счёта: код сам берёт net-distinct без меню прочтений вики. Комментарий патча: «иначе гейт secondary_axis/warehouse молчит». |
| **net-distinct #2** | общий `elif agg is None` после `rows_of` (~3839) | расширяет узкий гейт `stock_count_aggregate_without_subject` теми же OR-условиями + `not stock_asks_named_product` | **НАРУШЕНИЕ** | Та же логика во второй точке SQL. |
| **ef_gate** | `if ASK_ENTITY_FORM and not no_arbiter` (~2853) | → `if (ASK_ENTITY_FORM or entity_form_gate_open(intent, diag)) and not no_arbiter` | **НАРУШЕНИЕ** | Расширяет вход в блок F (entity_form) при assumed-period на флаге 0 — отдельный путь ответа/меню мимо «только каскад». |
| **ecp0↔F reorder** | маркер `# z21-boot: entity_form before event_count_period_clarify` (если есть) | ставит `_ecp0 = try_event_count_period_clarify` **перед** pre_entity F | **НАРУШЕНИЕ** | Period-clarify до/рядом с F, до единого меню каскада; сейчас на диске маркер снят — ветка no-op, но патч жив. |
| Ветка A / catalog_count / sales_canon / V4c E–H | — | no-op (снесено волнами В2/W) | — | Не добавляет строк. |

При удалении инжекта: рантайм = диск; тесты
`test_wiki_card_hybrid.py :: bootstrap net-distinct in no_axis_member`,
`test_wiki_leader_not_overridden.py :: bootstrap: early-clarify гейт…`,
часть `test_stock_balance_path.py` (net pair) — ожидают патч или его эффекты.

---

## 2. Итоговая таблица блоков

Колонка «что ломается» — кто ссылается в z20 + имена тестов (`t("…")` / файл).

### 2.1. До `answer()` (1–1702)

| Блок | Строки | Вердикт | Обоснование | Что ломается при удалении |
|---|---|---|---|---|
| Заголовок зоны, imports, `apply_bindings` | 1–7 | ИНФРА | Загрузка зоны. | Зона не грузится. |
| `_filter_dates` | 9–18 | СТУПЕНЬ | Границы периода отбора для гейта (после SQL). | `gate` / белый список дат; `test_gate.py`. |
| `without_list_markers` + маркеры | 21–43 | СТУПЕНЬ | Гейт не считает нумерацию списка числом из данных. | `gate`; `test_gate.py`. |
| `rows_seen` | 46–70 | СТУПЕНЬ | Гейт только по показанным строкам. | `gate` в конце `answer`. |
| `gate` | 73–234 | СТУПЕНЬ | Сверка чисел ответа с базой (п.19/21). | Весь kind=answer/figures; `test_gate.py`. |
| `gate_out` | 238–256 | СТУПЕНЬ | Тот же гейт на clarify/ask_back. | Clarify с числами; `test_gate.py`. |
| Построитель меню: `_opt_values`…`clarify_opts_response` | 259–375 | СТУПЕНЬ | Единый построитель вариантов (подписи → строки → гейт). | Все clarify; `test_wiki_captions_builder.py`, `test_focus_loop.py`. |
| Замер витрины/coverage helpers | 378–493 | ИНФРА / СТУПЕНЬ* | Health + отметка неполноты на ответе. *`_coverage_of` в ответе — ступень п.13. | `/health`, `diag.incomplete`. |
| Health gap / native freshness | 496–730 | ИНФРА | GET /health, кэш разрыва. | Handler `/health`; health-тесты. |
| `_coverage_answer` + `COVERAGE_SYS` | 733–838 | **НАРУШЕНИЕ** | Отдельный путь «о полноте» → SQL переписи + LLM **без** wiki-каскада. | Вопросы `about=coverage`; живые прогоны coverage. |
| Константы ASK_* / ARBITER_* / FORK_* | 841–862 | ИНФРА+хвосты | Флаги; `ARBITER_*`/`FORK_*` кормят нарушителей. | Env-поведение; при сносе арбитра — вычистить. |
| `_KIND_WORD`…`disambiguate_labels` | 864–1000 | СТУПЕНЬ | Подписи без метаданных 1С (п.12/меню). | Меню; `test_k4_meta_names.py`. |
| `opts_hints` / `mk_opts` | 1012–1102 | СТУПЕНЬ | Сборка options единого вида. | Early/fork/measure menus. |
| `live_src_counts` | 1105–1137 | **НАРУШЕНИЕ*** | Живой SQL-счёт по кандидатам до/вместо решения вики (фильтр меню, axis_focus). *Нужен ли тонкий «счёт для подписи» — решить в O2; как сейчас — выбиратель. | `axis_focus_plan`, `mk_opts(live=)`; `test_axis_focus.py`. |
| Period-empty helpers | 1140–1336 | СТУПЕНЬ | Честный «0 за период» после SQL, не отказ. | `build_period_empty_answer`; `test_period_empty.py`. |
| `_wiki_named_entity` | 1339–1348 | СТУПЕНЬ | Замок «вики уже решила» для трёх точек после каскада. | Distinct/probe/undated ветки; wiki-тесты. |
| `resolve_focus` | 1351–1486 | СТУПЕНЬ | Сведение выбора человека к src (после меню). | Билеты/focus; `test_focus_loop.py`. |
| `axis_focus_plan` + `_word_hits_measure` | 1489–1572 | **НАРУШЕНИЕ** | Сам решает holder vs catalog vs clarify по live-счёту, не вики. | Вызов ~2445; `test_axis_focus.py` (держатель ПКО и др.). |
| `period_is_canon_guess` / `period_slot_for_inherit` / `apply_prior_period` | 1583–1701 | СТУПЕНЬ* | Наследование окна диалога для SQL-слотов. *Не меню. | Prior-period; k4/period тесты. |
| `period_assumed_needs_clarify` | 1610–1638 | **НАРУШЕНИЕ** | Датчик pre-wiki period-clarify. | Блок ~1861; `test_k4_guess_vs_clarify.py` P1–P4, `test_action_class.py`, `test_k4_axis_and_names.py`. |
| `warehouse_clarify` | 1641–1655 | **НАРУШЕНИЕ** | Отдельное склад-меню; в `answer()` **не зовётся** (мёртвый/внешний держатель в z20). | `test_warehouse_*.py`, `test_k4_axis_and_names.py` wh:*. |

### 2.2. `answer()` — вход и до вики (1703–2503)

| Блок | Строки | Вердикт | Обоснование | Что ломается |
|---|---|---|---|---|
| Сигнатура, `шаг`, token_acc, resolved→focus/measure | 1703–1745 | ИНФРА | Тайминги, decision_id→слоты. | Журнал/билеты. |
| `parse_intent` + prior period + preds | 1746–1806 | СТУПЕНЬ | Слоты периода/условий для SQL (не выбор сущности). | Весь путь; z02. |
| Bare YoY clarify без окна | 1754–1766 | **НАРУШЕНИЕ** | Clarify «Сравнить какие продажи?» **до** вики, options=[]. | YoY без контекста. |
| `calendar_axis_unavailable_block` | 1808–1813 | ИНФРА/ступень* | Отказ при неготовом словаре окон (п.13). | Calendar env. |
| Ветка `about=coverage` | 1815–1830 | **НАРУШЕНИЕ** | Уход в `_coverage_answer` мимо каскада. | Coverage Q. |
| Маркеры kind_unsupported / non_accounting (только diag) | 1846–1860 | ИНФРА | Наблюдаемость; на исход не влияют (коммент 01.09). | diag. |
| **assumed-period clarify** | 1861–1888 | **НАРУШЕНИЕ** | Меню окон **до** wiki-каскада (`reason=assumed-period`). Кандидат плана. | `period_assumed_*` тесты выше. |
| merge_compare_term_groups + `probe` | 1890–1908 | СТУПЕНЬ | Подготовка термов/match для отбора и SQL. | step2/probe. |
| **unmatched_terms → no_data** | 1910–1927 | **НАРУШЕНИЕ** | Отказ **до** вики при ненайденном значении. Кандидат плана. | `test_step2.py` (частично); L-сценарии «нет в данных». |
| match / tables_of / partial / meaning_candidates / children / vector fill | 1929–2109 | СТУПЕНЬ* | Сбор пула кандидатов **для** каскада. *Не выбирает лидера — кормит z21. | `wiki_primary_*`; meaning benches. |
| `not_for` отсев | 2110–2202 | **НАРУШЕНИЕ** | Код выкидывает кандидатов до вики по not_enough_for. | diag.not_for; entity-choice probes. |
| Двойной фильтр `want=sum` → only with nums/money (×2 копии) | 2203–2338 | **НАРУШЕНИЕ** | Скрытый отбор «у кого есть деньги» до вики; код дублирован. | Sum-вопросы; старые замеры «склады». |
| **fork_detector early** (`_fork_early`) | 2339–2415 | **НАРУШЕНИЕ** | Параллельный судья неоднозначности до/рядом с вики. | `test_fork_detector.py`, `test_fork_outcomes.py`, calendar/currency fork. |
| `resolve_focus` / `hold_settled_entity` | 2421–2435 | СТУПЕНЬ | Применение выбора человека / билета. | decision_id. |
| **`axis_focus_plan` в answer** | 2443–2478 | **НАРУШЕНИЕ** | Clarify/подмена focus→holder до каскада (если focus). | `test_axis_focus.py`. |
| Ветка `if focus:` (picked=[focus], code_filter) | 2479–2502 | СТУПЕНЬ* | После меню/билета — сразу SQL-путь. *Сырой focus без вики — обход; билет — ОК. | Focus replay. |
| **`wiki_primary_entity_cascade`** | 2504–2511 | **СТУПЕНЬ** | Ядро формулы: пул → LLM → verify. | `test_wiki_card_hybrid.py`, `test_wiki_candidate_verify.py`, `test_wiki_leader_not_overridden.py`. |

### 2.3. После каскада — соперники, F, fork, early A (2513–3137)

| Блок | Строки | Вердикт | Обоснование | Что ломается |
|---|---|---|---|---|
| **code_ambiguous** holders→picked | 2513–2538 | **НАРУШЕНИЕ** | Код дописывает регистры по `ts_starts_with` к picked (смягчено при wiki_hybrid). | `test_measure_hatch_luk.py :: code_ambiguous не растит picked…`. |
| Семья/writer/service load | 2567–2616 | ИНФРА* | Данные для меню-соперников. *Кормит нарушителей. | arb_pool. |
| `signals_disagree` → expand picked | 2664–2685 | **НАРУШЕНИЕ** | Второй сигнал расширяет picked без вики-меню. | (мало прямых t-имён; живые wiki-leader regressions). |
| doubt / **arb_pool** / writer_pair / kin rivals / locks | 2733–2849 | **НАРУШЕНИЕ** | Остатки арбитра: код собирает круг соперников и singleton-lock (`catalog_count_locked` и т.п.). | `test_fork_outcomes.py`, wiki_leader_not_overridden; entity_form collapse. |
| **ecp1 + try_entity_form (блок F)** | 2851–2872 | **НАРУШЕНИЕ** | Period-clarify и «форма сущности» отдельным механизмом; патч расширяет гейт. Кандидат «блок F». | `test_entity_form.py` (весь), `test_action_class.py` entity_form/period clarify, warehouse entity_form. |
| fork outcomes A/B/C / unavailable | 2874–3045 | **НАРУШЕНИЕ*** | Параллельный исходник меню. *`fork_clarify_from_wiki_pool` ближе к формуле — **слить**, не плодить. C→`fork_outcome_c` / no_wiki_pool no_data — обходы. | `test_fork_outcomes.py` (~много), calendar/currency/atom_terminal. |
| **Ранний entity-clarify A** | 3047–3112 | **НАРУШЕНИЕ→слить** | Меню при >1 src — **нужная ступень**, но **отдельный** механизм (`early_clarify_path=1`), не «просто меню каскада». | `test_wiki_leader_not_overridden.py`, fork A fall-through. |
| `len(picked)>1` mk_opts clarify | 3117–3137 | **НАРУШЕНИЕ→слить** | Второе entity-меню тем же построителем. | Те же + ambiguous. |

### 2.4. Src settle → мера → ось → SQL → compose (3185–4386)

| Блок | Строки | Вердикт | Обоснование | Что ломается |
|---|---|---|---|---|
| Выбор `src=picked[0]`, via_partial/parent | 3185–3231 | СТУПЕНЬ | После решения каскада/меню — один src для SQL. | — |
| **probe empty → `max(by)` подмена src** | 3203–3219 | **НАРУШЕНИЕ** | Код меняет сущность без вики (кроме `_wiki_named_entity`). | L12-класс; wiki_locked тесты. |
| period_window_empty probe | 3233–3240 | СТУПЕНЬ | Флаг пустого окна до меры. | period_empty. |
| `_coverage_of` на src | 3247–3255 | СТУПЕНЬ | П.13 на ответе. | incomplete. |
| **measure_in_kin** авто-смена src | 3274–3297 | **НАРУШЕНИЕ** | Код переносит сущность на kin с мерой (блок при wiki_verify). | step5/measure kin. |
| Выбор меры: plan / pick_measure / rank / unresolved / class | 3299–3388 | **смесь** | Одно прочтение → ответ (ступень). Угадывание rerank/`measure_class` без вики — **НАРУШЕНИЕ**. | `test_measure_*`, step4_guards. |
| Dead/zero measure → pivot или alts | 3389–3456 | СТУПЕНЬ* | Не молчать нулём; меню живых мер. | measure empty pivot. |
| **ecp2** period clarify | 3465–3469 | **НАРУШЕНИЕ** | Ещё один period-clarify **после** выбора src. | `test_action_class.py` event_count_period_*. |
| **Два блока measure-меню** (3471–3524 и 3543–3566) | 3471–3566 | **СТУПЕНЬ→слить** | >1 мера → clarify построителем — формула. Два входа — **нарушитель-дубль** (кандидат плана «два блока источников мерного меню»). Авто-leave `_live[0]` при «не ambiguous» — скрытый выбор. | `test_measure_menu_not_silent.py`, `test_measure_hatch_luk.py`, `test_no_pre_wiki_reorders.py`, gate №16. |
| subject_unsupported → no_data | 3478–3485 | **НАРУШЕНИЕ*** | Отказ до меню мер. *Может быть честный no_data после вики — сейчас страж B. | K4-2. |
| `decide_grain` / axis clarify / rank fold measure menu | 3567–3718 | **смесь** | >1 ось → меню (ступень). Авто `_kh` / rerank оси — **НАРУШЕНИЕ**. Третье measure-меню в rank_fold — дубль. | `test_axis_focus.py`, rank_leader, k4_axis. |
| sales_compare terminal answer | 3720–3756 | **НАРУШЕНИЕ*** | Отдельный SQL+ответ compare, минуя общий compose; сущность уже выбрана. *Окно/мера не из вики-меню. | `test_compare_sales.py`. |
| aggregate_groups / no_axis_member / rows_of+aggregate | 3758–3873 | СТУПЕНЬ* | SQL после решения. | — |
| **stock_net_distinct** (диск ~3839–3846) + патч | 3839–3857 | **НАРУШЕНИЕ** | Скрытый выбиратель агрегата. | `test_stock_balance_path.py :: net pair`, bootstrap hybrid. |
| undated/outside_period, slot_mode, period_empty return | 3874–3979 | СТУПЕНЬ | Объявление потерь + честный 0. | `test_period_empty.py`. |
| distinct_axis terminal (event count) | 3980–4036 | **смесь** | Рендер счёта по оси кодом. Авто `live_axis_col_for_count` без меню при >1 оси — **НАРУШЕНИЕ**. | action_class distinct. |
| rank без группы → axis clarify | 4064–4083 | СТУПЕНЬ→слить | Меню осей. | rank_axis_missing. |
| compose + gate + retry + figures/no_data | 4084–4278 | СТУПЕНЬ | Формула: формулировка → гейт → ответ. | `test_gate.py`, atom_terminal. |
| ask_back (сейчас гасится) | 4280–4332 | **НАРУШЕНИЕ (мертвый)** | Bare clarify forbidden — код мёртв, но путь был мимо меню. | — |
| Финальный kind=answer + atom | 4334–4386 | СТУПЕНЬ | Ответ. | — |

### 2.5. Журнал, scope, HTTP (4395–5094)

| Блок | Строки | Вердикт | Обоснование | Что ломается |
|---|---|---|---|---|
| `SLOT_COVER` flag | 4395–4396 | ИНФРА | Env. | — |
| Journal helpers + `_ask_journal_write` | 4398–4708 | ИНФРА | Журнал ask. | `test_journal_fields.py`. |
| `answer_checked` / scope persist | 4710–4879 | ИНФРА | Обёртка + память выбора. | `test_ask_choice_memory.py`. |
| `Handler` (token, /ask, /health, decision_id) | 4881–5077 | ИНФРА | HTTP-оболочка. | Живой сервис. |
| `main` | 5079–5094 | ИНФРА | Точка входа. | — |

---

## 3. Ожидаемые кандидаты — проверка

| Кандидат (план O1) | Вердикт | Где |
|---|---|---|
| Period-clarify до/мимо вики (ecp / assumed) | **ДА, НАРУШЕНИЕ** | assumed ~1861; ecp1 ~2861; ecp2 ~3465; патч ecp0 |
| unmatched/no_data до вики | **ДА** | ~1917–1927; также пустой by ~2074 |
| Ранний clarify A как отдельный механизм | **ДА (слить)** | ~3047–3112 (+ второй ~3117) |
| entity_form / блок F | **ДА** | ~2851–2872 + ef_gate патч |
| code_ambiguous | **ДА** | ~2513–2538 |
| live_srcs / arb_pool остатки | **ДА** | fork live_srcs; arb_pool ~2753–2840; early pool |
| Два блока мерного меню | **ДА (дубль ступени)** | ~3471–3524 и ~3543–3566 (+ rank_fold третье) |
| axis_focus_plan | **ДА** | def + ~2443 |
| secondary_axis / warehouse-гейты | **частично** | `warehouse_clarify` мёртв в answer; net-патч комментирует secondary_axis/warehouse; stock_product_axis ~3849 |
| return clarify/no_data/answer мимо каскада | **ДА** — см. §4 | — |
| Скрытые выбиратели (net/ef) | **ДА** | патч + диск net-distinct; ef_gate; max(by); measure_in_kin; not_for; sum-filter |

**Дополнительно найдены:** bare YoY clarify; `_coverage_answer`; двойной sum/money фильтр; fork detector+outcomes; signals_disagree; sales_compare terminal; probe→max(by); measure_class_clarify; ask_back-мертвец.

---

## 4. «Мимо вики физически некуда»

Точки, где путь даёт **SQL и/или kind∈{answer,figures,clarify,no_data,unavailable}** без
прохода через успешное решение `wiki_primary_entity_cascade` (нет
`wiki_hybrid_pick`/`wiki_verify` как судьи, либо возврат раньше вызова).

| # | Файл:строка | Что уходит | Почему мимо |
|---|---|---|---|
| 1 | `z20:1761` | clarify (YoY) | До каскада |
| 2 | `z20:1813` | calendar unavailable | До каскада |
| 3 | `z20:1830` → `_coverage_answer` | answer/figures/no_data + SQL coverage | Ветка about, без z21 |
| 4 | `z20:1887` | clarify assumed-period | До каскада |
| 5 | `z20:1924` | no_data unmatched | До каскада |
| 6 | `z20:2075` | no_data пустой пул | До каскада |
| 7 | `z20:2448–2463` | clarify axis_focus | Focus-путь до/без каскада |
| 8 | `z20:2479+` | дальше SQL | `focus` задан → **вызов каскада пропускается** (`else` на 2503) |
| 9 | `z20:2866 / 2872` | ecp1 / entity_form return | После каскада, но **свой** судья, не меню каскада |
| 10 | `z20:3009 / 3027 / 3033 / 3035` | fork C menu / no_data / unavailable | Fork-судья; wiki_pool только как источник подписей |
| 11 | `z20:3108 / 3134` | early / picked clarify | Меню из arb_pool/picked, не обязательный исход z21 |
| 12 | `z20:3219` | смена src | `max(by)` без вики |
| 13 | `z20:3441` | measure empty pivot answer | После src; мера не из вики-меню |
| 14 | `z20:3469` | ecp2 clarify | Period без вики-решения окна |
| 15 | `z20:3482` | no_data subject_unsupported | До measure-меню |
| 16 | `z20:3520 / 3562 / 3707` | measure clarify | Ступень формулы по смыслу, но **не** wiki-каскад сущностей |
| 17 | `z20:3647 / 4078` | axis clarify | То же для осей |
| 18 | `z20:3747` | answer compare | Отдельный терминал |
| 19 | `z20:3785+ / 3821+ / 3835+ / 3870` | no_data после SQL | SQL мог идти при src не из verify-yes |
| 20 | `z20:3841` (+патч) | net-distinct SQL | Выбор агрегата кодом |
| 21 | `z20:3977 / 4030 / 4271 / 4382` | period_empty / distinct / figures / answer | Нормальный хвост **после** src; «мимо» если src получен обходом выше |

Инжект: строки net-distinct в рантайм-копии якоря `no_axis_member` и второго
`agg is None` — те же пункты 19–20.

**Итог критерия плана:** сейчас **физически можно** не пройти вики (п.1–8
гарантированно; п.9–11 часто; focus-билет — исключение формулы «выбор человека»).

---

## 5. Карта `def`/`class` (диск)

| Символ | Строки | Вердикт (кратко) |
|---|---|---|
| `_filter_dates` | 9 | ступень |
| `without_list_markers` | 29 | ступень |
| `rows_seen` | 46 | ступень |
| `gate` | 73 | ступень |
| `gate_out` | 238 | ступень |
| `_opt_values`…`clarify_opts_response` | 259–351 | ступень (построитель) |
| `_entity_counts_objects`…`_health_gap`… | 388–730 | инфра (+coverage_of ступень) |
| `_coverage_answer` | 754 | **нарушение** |
| `looks_like_src_table`…`disambiguate_labels` | 897–983 | ступень |
| `opts_hints` / `mk_opts` | 1012 / 1074 | ступень |
| `live_src_counts` | 1105 | **нарушение*** |
| `empty_after_period_action`…`build_period_empty_answer` | 1140–1273 | ступень |
| `_wiki_named_entity` | 1339 | ступень |
| `resolve_focus` | 1351 | ступень |
| `axis_focus_plan` | 1504 | **нарушение** |
| `period_assumed_needs_clarify` | 1610 | **нарушение** |
| `warehouse_clarify` | 1641 | **нарушение** |
| `apply_prior_period` | 1672 | ступень |
| `answer` | 1703–4386 | см. §2.2–2.4 |
| `_journal_*` / `_ask_journal_write` | 4398–4592 | инфра |
| `answer_checked` / scope | 4710–4879 | инфра |
| `Handler` / `main` | 4881 / 5079 | инфра |

---

## 6. Заметки для O2 (не решение)

- Линейный скелет уже читается: слоты (parse) → **wiki_primary_entity_cascade** →
  SQL → меню мер/осей при >1 → compose+gate. Между ними ~2k строк
  нарушителей/дублей.
- Меню entity (early A / fork C / picked>1) и два measure-блока — **не
  выкидывать смысл**, а **один** вызов построителя после каскада.
- `_bootstrap` net/ef — обнулить вместе со сносом (план §2 этап-2).
- Focus/trusted без повторного каскада оставить как «выбор человека» только
  после decision_id из **этого** построителя.

---

## 7. Источники

- Диск: `/srv/1c/ubuntu/serenedb/ask/z20_ask_main_http.py`
- Патч: `/srv/1c/ubuntu/serenedb/ask/_bootstrap.py` `_patch_z20_wiki_primary`
- Контракт: `/srv/1c/docs/audit/snos15-ONEPATH_PLAN.md`
- Тесты: `/srv/1c/ubuntu/serenedb/test_*.py` (имена в колонке «что ломается»)
