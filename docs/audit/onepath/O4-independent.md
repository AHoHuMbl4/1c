# O4 — независимый аудит z20: пути к ответу мимо wiki-каскада

Источник: только `/srv/1c/ubuntu/serenedb/ask/z20_ask_main_http.py` +
инжект `_patch_z20_wiki_primary` в `/srv/1c/ubuntu/serenedb/ask/_bootstrap.py`,
с точечным чтением вызываемых функций в z21/z05/z03/z04/z04b/z13/z16/z17/z07/z08/z18
для идентификации терминалов. Чужие отчёты `docs/audit/onepath/` не читались.

Вершинный контракт (приказ 12.09):  
`вопрос → wiki-каскад → SQL → меню при >1 прочтении любого рода → ответ`.  
Критерий «мимо вики»: путь к SQL/ответу/clarify без решения `wiki_primary_entity_cascade`
(или с выбором источника/меры/периода/оси кодом вне вики).

Инжект-патч рантайма (не меняет порядок wiki на диске):
1. `aggregate_stock_net_distinct` в ветке `no_axis_member` (якорь ~3808–3811) —
   расширенный гейт `stock_canon_locked | stock_count_aggregate…` + запрет named product.
2. Тот же расширенный гейт в общем `elif agg is None` (~3839).
3. Гейт формы сущности: `ASK_ENTITY_FORM or entity_form_gate_open(intent, diag)`
   вместо голого `ASK_ENTITY_FORM` (~2853).
4. Блок ecp0/`pre_entity` в патче — **no-op** на текущем диске (якорей нет).

---

## 1. Фактический порядок шагов `answer()` (z20:1703–4391)

| # | Строки | Шаг | Может завершить ДО wiki? |
|---|--------|-----|--------------------------|
| 1 | 1716–1750 | `resolved`/`focus`/`measure_pick`; `parse_intent`; `apply_proven_period`; prior-period | нет (кроме подготовки) |
| 2 | 1756–1766 | YoY без окна → clarify «Сравнить какие продажи?» | **да** |
| 3 | 1768–1803 | `apply_period_leader` + day/currency prefer; preds | нет (но выбирает период) |
| 4 | 1808–1813 | `calendar_axis_unavailable_block` → no_data | **да** |
| 5 | 1826–1830 | `about=coverage` → `_coverage_answer` | **да** |
| 6 | 1861–1888 | assumed-period → period-clarify | **да** |
| 7 | 1902–1927 | `probe` терминов; unmatched → no_data | **да** (no_data) |
| 8 | 1932–2348 | кандидаты: `tables_of` / смысл / vector / not_for / sum-фильтры | нет ответа, но **SQL до wiki** |
| 9 | 2351–2415 | ранний `fork_detector_scan` (SQL-счёт по пулу) | нет ответа, **SQL до wiki** |
| 10 | 2423–2478 | `resolve_focus` / hold; `axis_focus_plan` → clarify/holder | **да** (clarify) |
| 11 | 2479–2502 | если `focus` — **wiki НЕ зовётся**, `picked=[focus]` | обход wiki |
| 12 | **2504–2511** | **`wiki_primary_entity_cascade`** (z21) — иначе | терминал из z21 или continue |
| 13 | 2512–2538 | code-holders в `picked` (если не wiki_hybrid_pick) | нет |
| 14 | 2564–2849 | doubt / writer_pair / arb_pool / locks (чтение) | нет |
| 15 | 2853–2872 | `try_event_count_period_clarify` (ecp1) + `try_entity_form_answer` | **да** (после wiki или focus) |
| 16 | 2891–3045 | fork outcomes A/B/C (повторный scan); C→меню/no_data | **да** |
| 17 | 3063–3137 | early entity-clarify / `picked>1` clarify | **да** |
| 18 | 3185–3239 | `src=picked[0]`; probe `rows_of`; возможен `max(by)` swap | нет терминала |
| 19 | 3257–3469 | выбор меры (`pick_measure` / gate / dead); ecp2 | **да** (pivot/ecp) |
| 20 | 3471–3566 | measure-clarify меню | **да** |
| 21 | 3570–3712 | grain/axis; axis-clarify; rank-measure clarify | **да** |
| 22 | 3720–3873 | SQL ответа: compare / `aggregate_groups` / distinct / `rows_of`+`aggregate` | ответ/no_data |
| 23 | 3976–4036 | period_empty / distinct_axis terminal | **да** |
| 24 | 4064–4083 | rank без оси → axis-clarify | **да** |
| 25 | 4100–4391 | `compose`+gate → answer / figures / (мёртвый ask_back) / currency clarify | финал |

Wiki-каскад стоит на шаге **12**. Всё выше — либо ранний терминал, либо подготовка/SQL без интерпретации вики.

---

## 2. Таблица терминалов ответа

«Через вики?» = до этого return вызывался `wiki_primary_entity_cascade` на этом запросе  
(ветка `else` без `focus`). `условный` = зависит от `focus` / раннего выхода.

| Строки | kind / механизм | Ветка | Через вики? |
|--------|-----------------|-------|-------------|
| 1761–1766 | clarify (YoY, options=[]) | `_yoy_compare_marker`, нет окна | **нет** |
| 1813 | no_data (`_cal_blk`) | calendar axis needed, карта пуста | **нет** |
| 1830 → 754–835 | answer/figures/no_data | `about=coverage` | **нет** |
| 1884–1888 | clarify (`clarify_opts_response`) | assumed long period | **нет** |
| 1924–1927 | no_data | unmatched term groups | **нет** |
| 2075–2076 | no_data | пустые кандидаты | **нет** |
| 2459–2463 | clarify (`mk_opts`+`clarify_say`) | axis_focus >1 holder | **нет** (до wiki; нужен focus) |
| 2508 | *из z21* clarify/no_data/answer | return `_ep` из cascade | **да** (это сам каскад) |
| 2866 | clarify (ecp1 period chips) | `try_event_count_period_clarify` | условный |
| 2872 | answer (entity_form F) | `try_entity_form_answer` | условный; форма **не** из вики |
| 3009 | clarify | `fork_clarify_from_wiki_pool` | условный (после wiki/focus) |
| 3026 | no_data | C без wiki_pool меню | условный |
| 3033 | clarify/figures/… | `fork_outcome_c` | условный |
| 3035–3040 | unavailable | fork scan fail | условный |
| 3108–3112 | clarify | early entity-clarify | условный |
| 3134–3137 | clarify | `len(picked)>1` | условный |
| 3441–3443 | answer (pivot) | `build_measure_empty_pivot` | условный |
| 3469 | clarify | ecp2 period | условный |
| 3482–3485 | no_data | subject unsupported before measure menu | условный |
| 3520–3524 | clarify | measure_ambiguous (live totals) | условный |
| 3562–3566 | clarify | measure_alts меню | условный |
| 3647–3652 | clarify | grain_dec clarify=axis | условный |
| 3707–3712 | clarify | rank_fold measure menu | условный |
| 3747–3756 | answer (compare atom) | `sales_compare` terminal | условный |
| 3785–3788 | no_data | empty group agg | условный |
| 3805–3807 | no_data | empty group rows | условный |
| 3821–3824 | no_data | empty no_axis agg | условный |
| 3835–3838 | no_data | empty rows_of | условный |
| 3870–3873 | no_data | aggregate None | условный |
| 3977–3979 | answer | `build_period_empty_answer` | условный |
| 4030–4036 | answer | distinct_axis terminal (код, не compose) | условный |
| 4078–4083 | clarify | rank без group axis | условный |
| 4244–4247 | answer | period_empty после gate-fail | условный |
| 4271–4276 | figures | gate отверг, agg есть | условный |
| 4277–4278 | no_data | gate fail, нет agg | условный |
| 4321–4332 | clarify | ask_back (на диске **недостижим**: 4316–4318 обнуляет) | мёртвый |
| 4373 | clarify | `currency_mismatch_blocks_answer` | условный |
| 4382–4391 | answer | финал compose+gate ok | условный |

Терминалы **строго до wiki** (физически без cascade):  
1761, 1813, 1830, 1888, 1924, 2075, 2459.

---

## 3. Точки SQL (выбор источника / мера / период)

### 3.1. До wiki-каскада (контракт: SQL только после интерпретации — нарушение порядка)

| Строки | Вызов | Кто выбрал источник/меру/период |
|--------|-------|----------------------------------|
| 1902 | `probe(terms)` | код отбора значений |
| 1932 | `tables_of(match, preds)` | код; период уже из `apply_period_leader` |
| 2049–2068 | corpus `emb <=>` (vector fallback) | код при пустом `by` |
| 2071 | `tables_of("", preds)` period-fill | код |
| 2128–2184 | not_for / stem SQL | фильтр кандидатов |
| 2215–2334 | nums/money existence | сужение cands |
| 2285–2289 | TABLES emb fallback | код |
| 2351–2407 | `fork_detector_scan` → `fork_scan*` | **скрытый**: период-лидер + счёт по src до wiki |
| 2445–2456 | `axis_focus_plan` / `live_src_counts` / labels | focus→держатели оси кодом |

### 3.2. Wiki-каскад (z21, вызов 2504)

| Место | Что | Выбор |
|-------|-----|-------|
| z21 `wiki_hybrid_pool` / verify / pick | карточки + LLM + passport verify | **вики** (целевой путь) |
| z21 clarify 963–968 | меню tied candidates | вики-outcome |

### 3.3. После выбора сущности (ответный SQL)

| Строки | Вызов | Кто выбрал источник/меру/период |
|--------|-------|----------------------------------|
| 3214, 3238 | `rows_of` probe | src: wiki **или** focus **или** `max(by)` (3219) |
| 3323, 3358, 3423, 3497, 3542, 3548 | `totals_of` (z08) | мера: `pick_measure` / plan / alts — **код**, не вики |
| 3725 | `aggregate_compare_sales` | окна: `sales_compare_windows` — **код** |
| 3780–3800 | `aggregate_groups` (z17) | ось: `decide_grain` / rank_axis — **код** |
| 3813, 3859, 3995 | `aggregate_distinct_axis` | ось: `live_axis_col_for_count` — **код** |
| 3817, 3863 | `aggregate` | src+measure уже выбраны выше |
| 3829 | `rows_of` (z07) | TOPK строк |
| 3841–3842 | `aggregate_stock_net_distinct` (+патч) | stock-путь — **код** |
| 3910–3934 | undated/outside_period counts | диагностика |
| 4100, 4177 | `compose` (z18) | формулировка после SQL |

Прямые `psql` в helpers (`_coverage_*`, `resolve_focus`, `mk_opts`/hints, labels) — служебные, не ответные, кроме coverage-ветки.

---

## 4. Построители clarify (не один)

Единого построителя меню нет. Список механизмов, реально отдающих `kind=clarify`:

| # | Построитель | Где | Подписи |
|---|-------------|-----|---------|
| 1 | `clarify_opts_response` → `clarify_say` → `format_clarify_options` | z20:351–371, 1884 | period labels `render_window_label` |
| 2 | inline YoY clarify | z20:1761 | текст без options |
| 3 | `mk_opts` + `clarify_say` | axis_focus 2456; early 3093; picked>1 3124 | human_table_label; опц. `wiki_menu_captions` |
| 4 | z21 wiki verify clarify | z21:~958–968 | `wiki_menu_captions` из паспортов |
| 5 | `fork_clarify_from_wiki_pool` | z13:820 + z20:3003 | wiki_pool + `wiki_menu_captions` |
| 6 | `fork_outcome_c` | z13:641 + z20:3014 | fork_labels / mk_opts; может figures без меню |
| 7 | `try_event_count_period_clarify` → period chips | z05:866; ecp1/ecp2 | window readings |
| 8 | measure opts inline | z20:3517–3524, 3559–3566, 3697–3712 | `measure_captions` (z14) |
| 9 | `axis_clarify_options` | z18:27; z20:3646, 4075 | labels target_src |
| 10 | `currency_mismatch_blocks_answer` | z04b:522; z20:4368 | amount_basis options |
| 11 | `warehouse_clarify` | z20:1641 | **определён, из `answer()` не вызывается** |

Общий текстовый слой: `clarify_say` / `format_clarify_options` — но **сборка options** разная (1–10).

---

## 5. Пути мимо вики (итог)

Условие входа + строки + размер ветки (LOC ≈ end−start+1).

### 5.1. Терминалы / обходы ДО `wiki_primary_entity_cascade`

| # | Условие входа | Строки | LOC | Суть |
|---|---------------|--------|-----|------|
| M1 | YoY-маркер, нет окна периода | 1756–1766 | 11 | clarify без вики |
| M2 | нужен day_basis, карта календаря не готова | 1808–1813 | 6 | no_data |
| M3 | `intent.about == coverage` | 1826–1830 (+754–835) | 5+82 | ответ по переписи, не wiki |
| M4 | assumed long period, нет ticket/prior | 1865–1888 | 24 | period-меню до вики |
| M5 | не все term-группы найдены | 1917–1927 | 11 | no_data |
| M6 | нет кандидатов by/extra | 2070–2076 | 7 | no_data |
| M7 | `focus` задан (человек/resolved) | 2479–2502 | 24 | **wiki не вызывается** |
| M8 | focus = ось, >1 держатель | 2448–2463 | 16 | clarify до wiki |

### 5.2. SQL / интерпретация до вики (не терминал, но «мимо» по контракту)

| # | Условие | Строки | LOC | Суть |
|---|---------|--------|-----|------|
| M9 | всегда после parse | 1768–1803 | 36 | `apply_period_leader` молча ставит period |
| M10 | FORK_DETECT, >1 cand | 2351–2415 | 65 | fork SQL-счёт **до** wiki |
| M11 | отбор кандидатов | 1932–2338 | ~400 | probe/tables/vector/filters до wiki |

### 5.3. После wiki/focus: ответ без wiki-решения о мере/оси/форме

| # | Условие | Строки | LOC | Суть |
|---|---------|--------|-----|------|
| M12 | ASK_ENTITY_FORM (+патч gate_open) | 2853–2872 | 20 | `try_entity_form_answer` — форма/SQL вне вики |
| M13 | fork C без wiki_leader_alive | 3001–3033 | 33 | меню/figures из fork, не из wiki-verify |
| M14 | early entity clarify при >1 picked/arb | 3063–3112 | 50 | меню из arb_pool (подписи вики опциональны) |
| M15 | `picked>1` | 3117–3137 | 21 | то же |
| M16 | probe пуст, нет wiki_lock | 3213–3219 | 7 | **src = max(by)** — скрытая смена источника |
| M17 | мера в kin, wiki_verify≠block | 3275–3297 | 23 | смена src на kin owner |
| M18 | нет plan.quantity | 3328–3339 | 12 | `pick_measure` выбирает/ask |
| M19 | measure_alts / ambiguous | 3476–3566 | ~90 | measure-меню (не wiki-каскад) |
| M20 | decide_grain → axis clarify | 3644–3652 | 9 | ось кодом |
| M21 | sales_compare terminal | 3721–3756 | 36 | ответ без compose-вики |
| M22 | distinct_axis terminal | 3980–4036 | 57 | ось `live_axis_col_for_count` |
| M23 | currency mismatch | 4368–4373 | 6 | clarify amount_basis |

---

## 6. Скрытые выбиратели (код выбирает сам)

| # | Что выбирает | Где | Строки (z20 / зона) | LOC≈ |
|---|--------------|-----|---------------------|------|
| S1 | период (MTD/WTD/…) | `apply_period_leader` / `prefer_window_leader` | 1768–1798; z03:581 | 36 |
| S2 | day_basis лидер | `calendar_day_basis_prefer` | 1770; z04 | — |
| S3 | amount_basis лидер | `currency_amount_basis_prefer` | 1771; z04b | — |
| S4 | сущность при focus | `resolve_focus` / hold | 2423–2435 | — |
| S5 | держатель оси | `axis_focus_plan` → holder | 2444–2478; 1504–1572 | ~70 |
| S6 | сущность без wiki | ветка `focus` → picked=[focus] | 2479–2502 | 24 |
| S7 | src при пустом probe | `max(by.items())` | 3215–3219 | 5 |
| S8 | src → tabular kin | `measure_in_kin` owners==1 | 3275–3295 | 21 |
| S9 | мера | `pick_measure` / `measure_choice` / plan.quantity | 3305–3339; z16:586 | 41 |
| S10 | ось группы | `serene_axis.decide_grain` / `rank_axis_resolve` | 3596–3618 | — |
| S11 | ось COUNT DISTINCT | `live_axis_col_for_count` (+kind fallback) | 3810–3815, 3847–3861, 3988–3993; z05:698 | — |
| S12 | stock net-distinct | `aggregate_stock_net_distinct` (+bootstrap) | 3839–3846; патч | — |
| S13 | compare-окна | `sales_compare_windows` | 3721–3725 | — |
| S14 | entity_form (catalog+sales) | `try_entity_form_answer` / `entity_form_structs` | 2867–2872; z05 | 20 |
| S15 | locks catalog/stock/register | **чтение** 2781–2848, 3067… | — | **на диске нигде не пишутся** (мёртвые гейты) |

---

## 7. Вердикт по контракту «один путь»

1. **Wiki не единственный вход.** Ранние терминалы M1–M8 и обход `focus` (M7) завершают или выбирают сущность до/без cascade.
2. **Порядок «вики → SQL» нарушен:** period-лидер (S1), отбор кандидатов и `fork_detector_scan` (M10) делают SQL и интерпретацию окна **до** z21.
3. **Clarify не единый построитель** — ≥10 механизмов; общие только `clarify_say`/`mk_opts` как кирпичи.
4. **После (или вместо) вики** мера/ось/форма/сравнение часто выбираются кодом (S9–S14): это скрытые выбиратели относительно контракта «прочтение любого рода — из вики / меню».
5. **Инжект `_bootstrap`** усиливает stock net-distinct и расширяет гейт entity_form; **не** закрывает обходы wiki и **не** ставит wiki раньше period/fork.

Число явных «мимо вики» терминальных/обходных веток в z20: **8 до-wiki (M1–M8)** + **≥10 пост-выборных (M12–M23)** + **3 до-wiki SQL-интерпретации (M9–M11)**.  
Скрытых выбирателей: **14 живых (S1–S14)** + 1 мёртвый набор locks (S15).
