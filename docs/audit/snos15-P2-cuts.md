# СНОС-15 P2: механическая нарезка по коду (2026-09-11)

Вход: `docs/audit/snos15-MERGE.md` §2 (16 целей), сверка с M1–M4.
Источник строк: живое дерево `/srv/1c/ubuntu/serenedb/ask/` + поиск call-sites
(`rg`), не слепое копирование MERGE. Нумерация целей = MERGE §2.

**Ядро не трогать (MERGE §1):** HTTP/`answer_checked` билеты (z14),
`wiki_primary_entity_cascade` пул→pick→verify (z21:199/601/539; зов
z20:2808–2815) **без** collapse/sales-bypass, поиск/SQL (z06/z07 core/z08/z17),
меню при >1 (включая A-ранний clarify z20:3595–3686), compose+gate+passport
(z18; z20 compose ~5043, gate ~5105), B-дедлайн (z01 + z20:6178).

**Разрешённая новая функция (не в этом файле как diff):** единый построитель
меню с вики-подписями (MERGE §1 замечание M2) — упоминается только как
приёмник потока после сноса молчаливых выбирателей.

Обозначения: **цел.** = удалить целиком; **част.** = вырезать ветки/строки;
**ОСТАВИТЬ** = ядро/ступень 4.

---

## Цель 1 — sales-канон целиком

### (а) Что удаляется

| кусок | где | режим |
|---|---|---|
| модуль канона продаж | `ask/z11_sales.py` целиком (824 строки; `register_zone` в конце файла) | **цел.** (после выреза call-sites) |
| helper-ответы period_empty / fork-empty в z20 | `z20:1206–1285+` (`sales_period_empty`, `sales_period_window_active`, `sales_fork_canon_empty_src`, `try_sales_fork_period_empty_answer` — lock на `:1278`) | **цел.** вместе с каноном |
| pre-wiki prefer sales | `z20:2229` | call-site |
| fork-pool prefer sales | `z20:2660–2665` (вложенный `prefer_entity_for_sales`) | call-site |
| arb_pool prefer + force_pool ×2 | `z20:3270–3278`, `:3378–3380` | call-site |
| post-src lock | `z20:4077–4086` (`diag["sales_canon_locked"]=…`) | **част.** |
| money/qty канон меры (связка с целью 3) | `z20:4230–4265`, `:4326–4332`; рантайм-патч `_bootstrap` sales_canon_post | см. цель 3 |
| bypass вики | `z21:671–673` (`if diag.get("sales_canon_locked"): return picked=[locked]`) | **част.** |
| `period_zero_why` → want=sum | `z20:3217–3220` (+ coverage-отвод `:1934–1938`) | **част.** (также цель 9/15) |
| YoY clarify «какие продажи?» | `z20:1859–1871` (опора на `sales_sum_intent`) | **част.** или переписать без канона |
| early-clarify ban `_ec_sales_cold` / `_ec_locks` sales | `z20:3620–3650` | **част.** (A-clarify **оставить**, убрать опору на lock/cold) |
| fork sales period_empty перехват | `z20:3536–3543`, `:4070–4075` | **цел.** с helpers |
| ask_back drop by canon | `z20:5262–5264` | **част.** (цель 15/16) |

Публичные defs z11 (все на снос вместе с модулем): `prefer_entity_for_sales:236`,
`sales_canon_src:371`, `sales_money_measure:386`, `sales_force_money_measure:613`,
`sales_canon_force_pool:638`, `sales_canon_engaged:649`, `prefer_entity_for_catalog_count:759`
(catalog — цель 2, но живёт в z11), `period_zero_why_question:810`,
`sales_rank_*`, `catalog_count_*`, hardcode `_is_product_catalog:707` и т.д.

**Не путать с ядром:** `wiki_primary_entity_cascade` тело `z21:659–705` — оставить;
вырезать только ранний return `:671–673`.

### (б) Call-sites (проверено поиском)

- `prefer_entity_for_sales`: z20:2229, 2661, 3272–3273; тесты
  `test_sales_canon_prefer.py`, stubs в `test_stock_balance_path.py:443`.
- `sales_canon_force_pool`: z20:3276–3278, 3378–3380; тест
  `test_sales_canon_prefer.py:214+`.
- `sales_canon_src` / lock: z20:1251–1252, 1278, 3646–3648, 4083–4086;
  z21:671–673 (чтение).
- `sales_sum_intent` / `sales_rank_engaged` / `sales_canon_engaged`: десятки
  мест в z20 (1206–1285, 1859+, 2223+, 3270+, 3615+, 4077+, 4230+, 5262);
  z05:879 (`sales_canon_intent` через `globals().get`); z16:370+
  (`canon_claims_question`).
- `sales_money_measure` / `sales_force_money_measure`: z20:1283–1284 (в
  period_empty helper), 4254–4255, 4327–4328; z21 collapse
  `_wiki_collapse_resolve_measure:798–804`; z16:408.

### (в) Поток после удаления

1. Пул сущностей: `by+extra` → (без prefer sales) → K6/фильтры или сразу
   `wiki_primary_entity_cascade` (`z20:2808`).
2. Lock больше не ставится → вики не короткого замыкания на register;
   `doubt`/`arb_pool` не схлопываются force_pool.
3. Мера: без `sales_measure_canon` — путь clarify `measure_alts`
   (`z20:4386–4443`) или `pick_measure` (пока цель 3 не срезана).
4. «Продали ноль» / fork excluded → больше не авто `period_empty` с lock;
   либо обычный aggregate/period_empty без канона, либо меню/вики.

### (г) `_bootstrap._patch_z20_wiki_primary`

Живые якоря на диске (проба 11.09: `disk→patched` Δ+2395 байт):

| якорь `_bootstrap.py` | связан с целью 1? | действие |
|---|---|---|
| sales_force insert `:198–219` (`sales_canon_post`) | да (мера после lock) | **удалить патч** вместе со сносом меры/канона; иначе патч вставит мёртвый код / упадёт на отсутствие символов |
| fork_b sales_money `:221–237` | да | **удалить патч** |
| stock/cat/net/meas/rank_fold | опосредованно (`sales_canon_locked` в условиях) | чистить OR/`sales_*` из вставляемого текста (цель 16) |
| `entity_form_gate_open` `:239–245` | нет (цель 11) | — |

Якоря `stock_old` / `cat_old` на текущем диске **уже отсутствуют**
(склад-фильтры изъяты) — патчи no-op.

### (д) Замки-тесты

| файл | действие |
|---|---|
| `test_sales_canon_prefer.py` | **удалить** или заменить негативными «символ отсутствует / call-site нет» |
| `test_sales_rank_canon.py` | **удалить/переписать** под меню меры |
| `test_wiki_card_hybrid.py` (патч wiki, отсутствие `sales_canon_src(cands` в patched) | **обновить** ожидания bootstrap |
| `test_wiki_candidate_verify.py` (stubs sales_force/money; collapse) | **обновить** (цель 7/3) |
| `test_stock_balance_path.py` stubs prefer_sales | упростить stubs |
| `test_no_domain_wordlists.py` / hardcode | усилить: z11 уходит |

### (е) Связности (нельзя рвать по волнам)

- **1∥2** — catalog prefer в том же z11 и соседние строки z20:2228–2230.
- **1∥3** — `sales_measure_canon` требует `sales_canon_locked` / `sales_*_measure`.
- **1∥5** — force_pool меняет `arb_pool`/`doubt` до арбитра.
- **1∥6** — `_checked`/alias/`writer_pair` гейты на `sales_canon_locked`.
- **1∥7** — early-clarify `_ec_locks` / cold `sales_canon_src`; fork period_empty.
- **1∥16** — мёртвые OR `catalog/stock/register_count_locked` в тех же force_pool.

---

## Цель 2 — prefer-перестановщики

### (а)

| кусок | где | режим |
|---|---|---|
| `prefer_entity_for_rank` | `z10_rank.py:428–491` | **цел.** функция |
| `prefer_entity_for_catalog_count` (+ hardcode catalog_*) | `z11:759–794` (+ `catalog_count_src:797`) | **цел.** с целью 1/z11 |
| call-sites pre-wiki | `z20:2228–2230` (rank, sales, catalog) | все три строки |
| fork-pool | `z20:2660–2665` | вложенные prefer×3 |
| arb prefer | `z20:3272–3274` | sales+catalog |

`event_kind_catalog_expand_pool` (`z20:2223–2227`, z05:478–518) — **не prefer**;
M3: техника пула → **ОСТАВИТЬ** (вред только в связке с prefer/lock).

### (б)

- `prefer_entity_for_rank`: z20:2228, 2662; stubs `test_stock_balance_path.py:444`.
- `prefer_entity_for_catalog_count`: z20:2230, 2660, 3274;
  `test_sales_canon_prefer.py:189+`, `test_final_stock_route_filters_absent.py:101`
  (уже проверяет отсутствие части маршрута).

### (в)

После сноса: `cands = by + extra` (+ optional event expand) → следующий слой
(K6 или сразу фильтры/вики). Порядок для wiki = порядок отбора probe/meaning,
без lift register/catalog_[0].

### (г)

Прямых якорей prefer в `_bootstrap` нет. Косвенно: всё, что предполагает
«голова пула = канон» после prefer — см. цель 1.

### (д)

`test_sales_canon_prefer.py` (catalog/rank ветки), `test_rank_leader_path.py`
(если зовёт prefer), stubs stock — обновить/удалить.

### (е)

- **2∥1** (один файл z11 + тройной call-site).
- **2∥4** — K6 переставляет уже prefer-упорядоченный список; снос 2 без 4
  оставляет тяжёлый SQL-выбор; снос 4 без 2 — prefer всё ещё двигает голову до вики.
- **2∥14** — rerank-сито ниже по тракту тоже переставляет; отдельная цель.

---

## Цель 3 — авто-мера

### (а)

| кусок | где | режим |
|---|---|---|
| блок канонов меры в answer | `z20:4230–4265` (sales_rank_resolve / force_money / qty) | **част.** |
| удержание мёртвой меры через sales_money | `z20:4326–4332` | **част.** |
| stock auto qty + skip clarify | `z20:4360–4379` (`stock_measure_canon`, `stock_skip_measure_clarify`) | **част.** (эвристика склада) |
| `pick_measure` ветка `how=='rerank'` → top | `z16:589–634` (возврат `(top,[], 'rerank')` / base) | **част.**: при rerank → `how='ask'` / alts, не winner |
| `unresolved_quantity` → `names[0]` | `z16:415–435` | **част.**: при !ambiguous всё равно меню, если >1 имя |
| sales money helpers | z11:386–414, 613–635 (+ rank resolve 521–610) | с целью 1 |
| rank_measure_hint авто | `z20:4144–4170` (`_mhint` → measure без меню) | **част.** |
| `_bootstrap` sales_force post + rank_fold stock qty | `_bootstrap:171–219` | **удалить/сузить** |
| collapse measure path | z21:727–850 (зовёт pick_measure + sales_force) | цель 7 |

**ОСТАВИТЬ:** `measure_choice` ambiguous→ask (`z14`); путь
`measure_alts`→clarify (`z20:4386–4443`); `measure_pick` с билета (`:4220–4228`);
`measure_class_alts` как меню классов (уже ступень 4).

### (б)

- `pick_measure`: z20:4172; z21:741–751; тесты measure/k4.
- `sales_force_money_measure` / `sales_money_measure`: см. цель 1.
- `rank_measure_hint`: z20:4144 (из z12/stock helpers — проверить импорт).

### (в)

Пока человек не выбрал:

1. Если `measure_alts` непуст → **меню** (`kind=clarify`, options с measure).
2. Если мера не названа и want≠sum → `totals_of` всем именам → compose
   (`z20:4444–4447`) — это не «winner ranked[0]», но модель видит все итоги
   (ступени 3/6; не замена меню при >1 прочтении меры).
3. После decision_id: `measure_pick` / trusted — ступень 5, без авто-канона.

### (г)

- Удалить insert `sales_canon_post` (`_bootstrap:198–219`).
- Удалить/не вставлять rank_fold stock auto-qty (`:171–196`) — это авто-мера.
- `meas_old`/`skip_old` (`:145–166`) — авто-пропуск clarify → снести с целью 3/12-stock.

### (д)

`test_sales_rank_canon.py`, `test_k4_guess_vs_clarify.py`,
`test_measure_empty.py`, `test_memory_collisions_measure.py`,
`test_f6_rollout_measure.py` — обновить: авто-мера запрещена, ожидать clarify.

### (е)

- **3∥1**, **3∥14** (rerank как победитель меры/оси).
- **3∥7** (collapse считает меру теми же helper’ами).
- **3∥11** (entity_form может вернуть ответ с мерой до общего пути).

---

## Цель 4 — K6-ранг сущностей

### (а)

| кусок | где | режим |
|---|---|---|
| блок apply | `z20:2232–2261` (`if K6R: … apply_to_candidates`) | **цел.** блок |
| модуль | `ubuntu/serenedb/entity_rank_v2.py` (867 строк; импорт `ask/_imports.py:42–44`) | вывести из тракта (модуль можно оставить файлом до чистки, но `K6R=None` / не звать) |
| `event_filter_pool` → `K6R.event_movement_pool` | `z05:1006–1008` | **част.**: без K6 filter no-op или удалить filter |
| `K6R.stem_overlap_srcs` | `z16:392–393` | **част.** fallback без K6 |

### (б)

- z20:2232–2261; z05:1006–1008; z16:392–393; `_imports.py:42–44`;
  `test_k6_rank_v2.py`, `test_action_class.py:16`, stubs
  `test_stock_balance_path.py:393,438`.

### (в)

Вход в wiki-каскад: `cands` после prefer/фильтров **без** SQL-перестановки
answer_fit_v2. Порядок = probe/meaning (+сито цели 14, пока живо).
Риск (MERGE §3.3): больше clarify — приемлемо; молчаливый wrong — нет.
MOL ускорение K6 (M4) — **отменяется** для тракта.

### (г)

Якорей K6 в `_patch_z20_wiki_primary` нет.

### (д)

`test_k6_rank_v2.py` — **удалить** или пометить «модуль вне тракта»;
`test_action_class.py` — убрать зависимость K6 где только для ранга сущностей;
event-tier тесты — пересмотреть.

### (е)

- **4∥2** (порядок до вики).
- **4∥11** (`event_filter_pool` сужает arb_pool).
- Не связывать с ядром wiki: каскад читает `cands`, не K6 напрямую.

---

## Цель 5 — арбитр-цикл

### (а)

| кусок | где | режим |
|---|---|---|
| цикл `answer(..., no_arbiter=True)` + выбор | `z20:3688–3918` (тихое `cand_src[0]` при FORK_OUTCOMES `:3854–3861`; `arbitrate` `:3862–3870`) | **цел.** цикл как выбиратель |
| сборка `arb_pool`/doubt соперников | `z20:3235–3382` (часть — цель 6) | см. ниже |

**ОСТАВИТЬ из соседства:** A-ранний clarify **перед** циклом
(`z20:3595–3686`) — это ступень 4; после сноса цикла он становится основным
меню при `len(arb_pool)>1`.

Clarify-ветки **внутри** цикла при diverge (`:3797–3848`) — по формуле это
меню; при сносе цикла их надо **перенести** на простой путь
`len(picked)>1 → mk_opts` (уже есть `:3920–3933`), не оставлять только
через дорогой N×answer.

### (б)

- Рекурсия `answer(..., no_arbiter=True)`: z20:3705–3706 (и другие
  no_arbiter гейты по файлу).
- `answers_diverge` / `arbiter_figures`: внутри блока.
- `prefer_mute_computed_over_clarify`: z20:3839 — цель 7.

### (в)

При >1 src после вики: **не** считать N полных ответов → сравнить числа →
взять [0]. Вместо этого: early-clarify / ambiguous clarify / wiki-tie меню.
Одиночный `picked` после wiki_verify → сразу мера/aggregate (ступени 3–6).

### (г)

Нет прямого патча на тело цикла. `deadline_hit` в цикле (`:3697`) — защита
остаётся в Handler; ранний clarify уже «побеждает deadline» (коммент Speed A).

### (д)

`test_step4_guards.py`, `test_action_class.py` (arbiter/diverge),
`test_early_clarify_atom_fps_hashable.py` — обновить: цикл отсутствует,
меню без N-подисчётов.

### (е)

- **5∥6** (signals/writer/stop2 наполняют arb_pool).
- **5∥7** (fork outcomes до цикла; mute внутри).
- **5∥1** (force_pool обнуляет смысл цикла).
- **Нельзя** сносить early-clarify (3595–3686) «в одной волне с циклом» как
  мусор — это замена цикла.

---

## Цель 6 — сигналы / alias-veto

### (а)

| кусок | где | режим |
|---|---|---|
| `signals_disagree` + append picked | `z20:3149–3169` | **цел.** блок выбора/расширения |
| writer_pair / doubt / arb_pool набор | `z20:3221–3333` (кроме кусков цели 1 prefer/force) | **част.**: убрать «второй судья»; writer_pair как *добавление в меню* можно оставить только если сразу clarify без авто-ответа |
| stop2 + `_alias_verdict` | `z20:3340–3376`, nested `_alias_verdict:2923–3076` | **цел.** veto-судья |
| `_checked` alias на ответе | `z20:3407–3433`, повтор `:3992–4009` | **цел.** |
| REQUIRE_SUPPORT путь | условия в `_checked` | снести вместе |

**ОСТАВИТЬ:** wiki passport verify (z21) — единственный судья сущности.

### (б)

- `_alias_verdict`: определения/зовы z20:2923, 3350, 3429, 4005.
- `alias_supported` / `veto_top_without`: z16; косвенно.
- `SIGNAL_DISAGREE`, `ALIAS_VETO`, `stop2_active`, `determined_answer_rivals`.

### (в)

Wiki cascade уже вернул `picked` / clarify / no_data. Без alias-veto ответ
не переспрашивается «словарь vs pick». Без signals_disagree не раздувается
`picked` вершиной вектора → меньше ложных clarify **и** меньше обходов в арбитр.

### (г)

Нет. Условия `not sales_canon_locked` вокруг writer_pair станут мёртвыми
после цели 1 — вычистить (цель 16).

### (д)

`test_step4_guards.py` (много alias/stop2), `test_leader_hatch.py`,
ветки wiki «не оспаривать verify» в комментариях — обновить/сузить.

### (е)

- **6∥5**, **6∥1**.
- **6∥14**: `top_by_question` из сита emb — сигнал для disagree; при сносе
  сита (цель 14) блок 3149 теряет вход.

---

## Цель 7 — fork-автоответы и лидеры

### (а)

| кусок | где | режим |
|---|---|---|
| исходы A / unique / B-лидер в z20 | `z20:3451–3593` (вызовы `fork_outcome_a/unique/b`, defer) | **част.**: **снести A/unique/B-авто**; |
| `fork_outcome_c` | z13 + зов z20:3575–3585 | **ОСТАВИТЬ** как меню (подписи → вики-билдер) |
| `fork_leader_class` defaults | `z13:79–134` | **снести** лидер; детект классов оставить |
| `prefer_mute_computed_over_clarify` | `z13:446–474`; зов z20:3839 | **цел.** |
| `_wiki_clarify_collapse_answer` | `z21:820+`; зов `:980–983` | **цел.** (+ helpers 709–818) |
| `resolve_fork_outcome` ветки A/unique | `z13:286+`, `fork_outcome_a:373`, `unique:397`, `b:491` | A/unique/B-авто **снести**; C **оставить** |

**ОСТАВИТЬ (MERGE §3.1):** `z09_fork_detector` / `fork_detector_scan` /
`fork_labels_*` — детектор прочтений ступени 4.

Ранний fork detect `z20:2638–2719` — сам по себе не ответ; кормит classes.
Вердикт: детектор **оставить**; не строить A/unique из early scan.

### (б)

- `resolve_fork_outcome`: z20:3526; `test_fork_outcomes.py`, `test_action_class.py`.
- `fork_outcome_*`: z20:3549–3585.
- collapse: z21:980; `test_wiki_candidate_verify.py:589+`.

### (в)

classes>1 → всегда меню (C / wiki-tie / early-clarify), никогда answer из
атома/equal numbers. classes==1 → обычный путь ответа (одно прочтение) —
это не «исход A-пакет», а просто продолжение тракта.

### (г)

Патч fork_b sales_money (`_bootstrap:221–237`) — удалить с целью 1/7.

### (д)

`test_fork_outcomes.py`, `test_atom_terminal.py`, `test_fork_detector.py`
(не ломать детект), `test_wiki_candidate_verify.py` collapse — **удалить
ожидания equal→answer**; ждать clarify.

### (е)

- **7∥8** (day/amount/window prefer в scan и leader_class).
- **7∥5** (порядок: outcomes до arbiter).
- **7∥3** (collapse measure).
- Вопрос владельцу (MERGE §4.1): equal numbers — меню или ответ; код сейчас
  collapse=answer → по сплошному сносу → меню.

---

## Цель 8 — период-догадки

### (а)

| кусок | где | режим |
|---|---|---|
| `prefer_window_leader` | `z03:377–393` | **цел.** функция |
| `apply_period_leader` | `z03:581–611`; зов z20:1873–1874 | **цел.** / не писать лидер в intent |
| diag leader + prefer_form | `z20:1896–1903` | **част.** |
| `calendar_day_basis_prefer` / apply working | `z04:186+`; z20:1875, 1881–1885 | **снести prefer**; expand readings **оставить** для меню |
| `currency_amount_basis_prefer` | `z04b:158+`; z20:1876, 1878–1879 | то же |
| `period_assumed_needs_clarify` exempt sales/canon | `z20:1715–1743` (`sales_sum`/`canon_claims` → False) | **част.**: снять exempt |
| `period_form_from_question` first-hit | `z03:427–437` | **част.**: не выбирать form_id молча |
| assumed-period clarify блок | `z20:1972–1999` | **ОСТАВИТЬ** (ступень 4) |
| `apply_prior_period` | `z20:1777–1805`; зов `:1857–1858` | спорно: наследование без меню — M3 medium; в сплошном сносе → меню/явность |

### (б)

- `apply_period_leader` / `prefer_window_leader`: z20:1873, 1901;
  `test_fork_window_readings.py`, `test_period_*`.
- prefer day/currency: z20:1875–1876; `test_calendar_axis.py`,
  `test_currency_axis.py`.

### (в)

Несколько `period_readings` / day_basis / amount_basis → **меню**
(уже есть assumed clarify и fork C), preds без молчаливого MTD/WTD-лидера.
Одно чтение / билет trusted — preds как сейчас.

### (г)

Нет прямых period-якорей в `_patch_z20_*`.

### (д)

`test_period_empty.py`, `test_period_bounds.py`,
`test_period_relative_forms_ready.py`, `test_fork_window_readings.py`,
`test_calendar_axis.py`, `test_currency_axis.py` — убрать ожидания silent
leader; оставить expand/labels.

### (е)

- **8∥7**, **8∥9** (exempt через `canon_claims`/`sales_sum`).
- **8∥1** (sales exempt assumed).

---

## Цель 9 — intent-суждения

### (а)

| кусок | где | режим |
|---|---|---|
| majority `_merge_intents` / цикл SAMPLES | `z02:588–623`, `:669–673`; константы `z01:889–890` | **част.**: убрать голосование как выбор; при distinct>1 → не silent winner (меню вики-разбора — вне пакета, MERGE §3.4) |
| `_intent_text` list→[0] | `z02:39–50`, `:430–434` | **част.** |
| `period_zero_why`→sum | `z11:810–819`; z20:1934–1938, 3217–3220 | **цел.** с целью 1 |
| `canon_claims_question` | `z16:359–375` | **цел.** |

**ОСТАВИТЬ (MERGE §3.4):** `parse_intent` как техника слотов для SQL (не полная
замена вики в этом пакете). Вопрос владельцу — отдельно.

### (б)

- `parse_intent`: z20:1854, 1858, 5776; z21:928.
- `INTENT_SAMPLES`/`LEAD`: z01:889–890; Speed/MOL планы.
- `test_intent.py`.

### (в)

Пока z02 жив: один проход LLM или явная нестабильность в `parse.unstable`
без «победителя голосования», который ветвит kind/measure. Финальная
интерпретация сущности — вики (цель ядра).

### (г)

Нет.

### (д)

`test_intent.py` — переписать критерий согласия; не требовать majority winner.

### (е)

- **9∥8**, **9∥1**, **9∥13** (`serene_enough` зовёт `parse_intent` в
  `_answer_checked_core:5776`).

---

## Цель 10 — серый bypass

### (а)

| кусок | где | режим |
|---|---|---|
| `stock_bypass_empty_by` | `z20:2185–2192` | **цел.** ветку: всегда `no_data` при пустом by/extra |

```2186:2192:ubuntu/serenedb/ask/z20_ask_main_http.py
    if not by and not extra:
        if stock_question_engaged(question, intent):
            diag["stock_bypass_empty_by"] = True
            ...
        else:
            return {..., "kind": "no_data", ...}
```

После сноса: обе ветки → `no_data` (как else).

### (б)

Единственный write: z20:2188. Чтение/тест:
`test_final_stock_route_filters_absent.py:6,58–78` (описывает bypass как
серый край; замок уже умеет вырезать).

### (в)

Stock-вопрос с пустым отбором → честный `no_data`, без ухода в stock-path
с пустыми cands.

### (г)

Нет (складские патчи bootstrap — про canon/net/measure, не про эту строку).

### (д)

`test_final_stock_route_filters_absent.py` — усилить: bypass должен исчезнуть;
оставить как регрессию «нет stock_bypass».

### (е)

Слабо связана; можно вырезать рано. Рядом эпизод изъятия склад-фильтров
(prefer_stock уже orphan — цель 16/z12).

---

## Цель 11 — z05 авто-путь

### (а)

| кусок | где | режим |
|---|---|---|
| `try_entity_form_answer` зов | `z20:3384–3405` (+ bootstrap pre_entity insert) | **цел.** early-return |
| авто rolling_year / form pick | `z05:521–531`, `entity_form_pick:1135`, compute/answer path | **цел.** авто |
| `try_event_count_period_clarify` | z05:866; zovy z20:3394–3398, 4355–4358; boot ecp0 | **ОСТАВИТЬ** (ступень 4 период события) |
| `event_kind_catalog_expand_pool` | z20:2223–2227 | **ОСТАВИТЬ** (техника пула) |
| `event_filter_pool` | z20:3250–3254; z05:1005–1008 | снести сужение doubt=False при len==1 в связке K6 (цель 4) |
| флаги `ASK_ENTITY_FORM` / `entity_form_gate_open` | z05:534; boot `:239–298` | default off + удалить патч gate |

Большой файл z05 (1242) — смешанный: не удалять файл целиком, пока живы
period-clarify и expand_pool; вырезать авто-answer API.

### (б)

- `try_entity_form_answer`: z20:3400; boot строки с `_ef0`;
  `test_entity_form.py` (78 совпадений).
- `try_event_count_period_clarify`: z20:3394, 4355.

### (в)

Нет параллельного ответа формой до вики/меры. Период события при
неоднозначности → clarify (A-ранний / ecp). Счёт — общий aggregate.

### (г)

- Заменить/удалить `entity_form_gate_open` патч (`_bootstrap:239–298`).
- На диске сейчас `if ASK_ENTITY_FORM and not no_arbiter` (1 место) — патч
  расширяет гейт при load; снос = убрать и диск, и патч.

### (д)

`test_entity_form.py` — выкинуть авто-answer кейсы; оставить period-clarify.
FIX 4A «включить ENTITY_FORM» (M4) — **отменить**.

### (е)

- **11∥1** (`sales_canon_intent`/`locked` внутри z05).
- **11∥4** (K6 event pool).
- **11∥3** (мера внутри формы).
- **11∥7** (`entity_form_collapse_guard` / early_classes).

---

## Цель 12 — память auto-apply

### (а)

| кусок | где | режим |
|---|---|---|
| `_try_memory_apply` | `z20:5810–5835`; зов из `answer_checked` ~5912 | **цел.** apply |
| `ACM.probe_memory_apply` / `finish_apply` | `ask_choice_mem.py:161–183` | отключить вход |

**ОСТАВИТЬ:** `seal_clarify` / `consume_decision` / `peek_resolved` (ступень 5);
shadow-память без APPLY (diag only) — безобидна.

Флаг `ASK_MEMORY_APPLY` (default 0 в z08) — держать 0; код apply удалить,
чтобы не включили env.

### (б)

z20:5810, 5912; `test_ask_choice_memory.py`, `test_decision_id.py`.

### (в)

Повторный вопрос с user → снова меню при неоднозначности; билет decision_id
по-прежнему применяет явный выбор.

### (г)

Нет.

### (д)

`test_ask_choice_memory.py` — apply-кейсы → удалить/негатив; decision_id
оставить.

### (е)

Слабо; можно отдельно. Не смешивать с билетами z14.

---

## Цель 13 — enough-слой

### (а)

| кусок | где | режим |
|---|---|---|
| `_answer_checked_core` enough до/после | `z20:5763–5805` | **цел.** слой: оставить только `plain()`→`answer` |
| `_need_clarify` / `question_facts` helpers | рядом в z20 (~5367–5441) | **цел.** если только для enough |
| импорт `serene_enough` | `_imports` / z01 | вывести |

`answer_checked` оболочка журнала/билетов — **ОСТАВИТЬ**; убрать ветвление
ENOUGH_ON.

### (б)

z20:1148–1154 (period helpers), 1728, 5763–5805, 5367+;
`test_enough.py`.

### (в)

Нет уточнений «достаточности» вне вики-меню ступени 4. Дыры слотов → либо
вики/period clarify, либо ответ/отказ по данным.

### (г)

Нет.

### (д)

`test_enough.py` — **удалить** или негатив «слой отсутствует».

### (е)

- **13∥9** (parse_intent внутри enough).
- Не трогает compose/gate.

---

## Цель 14 — реранк как победитель

### (а)

| кусок | где | режим |
|---|---|---|
| сито emb ORDER BY + `rerank` голова | `z20:2394–2543` (`diag["order_by"]="rerank"`) | **част.**: либо снести как финальный порядок до вики, либо оставить **только** как технику входа в LLM **без** взятия [0] как сущности (MERGE §3.2) |
| `rank_axis_resolve` `ordered[0]` при >2 осях | `z10:233–295` (ветка `:273–284`) | **част.**: ≥2 → меню осей, не auto col |
| зов auto axis | `z20:4467–4471` (`diag["rank_axis_auto"]`) | **част.** |
| `rank_deterministic_answer` | `z10:338+`; зов z20:4994 | **цел.** обход compose |
| `pick_measure` rerank winner | z16 — цель 3 | — |

**ОСТАВИТЬ по MERGE §3.2:** `rerank` как HTTP-техника порядка кандидатов для
модели **если** финал — wiki clarify/verify, не `cands[0]` ответ.

Практически для сплошного сноса до вики: блок 2394–2543 **убрать из пути
сущности** (вики сама ранжирует карточки). `top_by_question` тогда не
кормит цель 6.

### (б)

- `rerank`: z20:2539; z07 def; z16 pick_measure; z10 rank_axes_rerank.
- `rank_axis_resolve`: z20:4467, 4518; `test_rank_axis_anchor.py`.
- `rank_deterministic_answer`: z20:4994; `test_rank_leader_path.py`.

### (в)

Сущность: wiki pool/pick. Ось: clarify `axis_clarify_options` (z18) при >1.
Мера: цель 3. Без ranked[0]→answer.

### (г)

Нет.

### (д)

`test_rank_leader_path.py`, `test_rank_axis_anchor.py`, Speed C замеры —
обновить критерий «реранк не вердикт».

### (е)

- **14∥3**, **14∥6**, **14∥2/4** (все про порядок до выбора).
- parent-before-child (цель 15) идёт сразу после сита (`:2544`).

---

## Цель 15 — прочий хвост

### (а) по кускам MERGE

| кусок | где | режим |
|---|---|---|
| parent-before-child reorder | `z20:2544–2577` | **цел.** |
| not_for / without_value / money filters | `z20:2263–2637` (not_for `:2280–2355`; without_value ветки `:2376`, `:2611`, `:2635`) | **снести как молчаливый отсев**; спорно для not_for как знания установки — в сплошном сносе вне формулы → убрать из маршрута |
| ask_back | `z20:5253–5281` (уже почти всегда drop `:5265–5267`) | **цел.** мёртвый путь + сбор raw |
| coverage-ветка | `z20:1931–1941`, `_coverage_answer:754` | **решить с владельцем** (MERGE §4.2); до решения — вынести из основного тракта / флаг |
| терминалы канонов в хвосте aggregate | `z20:4611–5362` минус чистый aggregate/compose/gate | вырезать sales/stock/rank_det ветки; **сохранить** aggregate/rows_of/compose/gate/passport |
| инертные функции (M2 список) | z07 `clarify_text`/`signal_terms`; z12 orphan prefer/filter; z11 `sales_ticket_hatch`; … | **цел.** мусор |
| `warehouse_clarify` | `z20:1746–1760` (0 живых зовов по M2/M4) | **цел.** |
| `merge_compare_term_groups` | z20:2001–2012 | снести эвристику оси |

### (б)

Проверено: ask_back только хвост compose; coverage — early return;
parent-before-child — один блок; not_for связан с `_alias_verdict`
(`:3014–3018`) — при сносе 6 отсев в alias тоже уходит.

### (в)

Меньше молчаливых отсевов → шире пул в вики (больше clarify — ок).
Coverage: если оставят — отдельный endpoint, не ступени 1–6.

### (г)

Net-distinct / stock_canon inserts в aggregate (`_bootstrap:97–143`) —
хвост канона склада: удалить с целью 16/3.

### (д)

См. цель 16 + `test_compose.py` ask_back, coverage-приборы.

### (е)

- **15∥14** (порядок блоков в отборе).
- **15∥1/12-stock** (терминалы канонов).
- Coverage — **изолировать** вопросом владельцу, не смешивать с 1–14.

---

## Цель 16 — мёртвые замки / патчи

### (а)

| кусок | где | режим |
|---|---|---|
| OR `catalog_count_locked` / `stock_canon_locked` / `register_count_locked` | z20:3277, 3379, 3414, 3621–3624, 5262; z16:262+; **присваиваний в текущем z20 нет** (rg `diag["…_locked"]=` только `sales_canon_locked`) | вычистить мёртвые чтения |
| orphan z12 | `prefer_entity_for_stock`, `filter_stock_*`, `balance_bridge_clarify` | **цел.** API + тесты-сироты |
| `_bootstrap` мёртвые/канонные вставки | stock_override (якорь уже мёртв), cat_old (мёртв), net/meas/rank_fold/sales_force/fork_b/ef_gate (ещё живы на load) | после сноса 1/3/11 — **удалить соответствующие ветки патча**; не оставлять RuntimeError на net_anchor |
| `test_*` на снесённое поведение как «правильный silent pick» | список ниже | обновить на «отсутствует» |

### (б)

Чтения dead locks: z20 (см. rg выше). Assign stock/catalog/register —
**0** в ask/*.py.

### (в)

Нет смены потока; меньше ложных «запретов early-clarify» и путаницы аудита.

### (г)

Это и есть зачистка `_patch_z20_wiki_primary`. После сноса символов
`stock_count_aggregate_without_subject` / `sales_force_money_measure` патч
**обязан** быть урезан в том же коммите, иначе load z20 упадёт или вставит
NameError-код.

Проба якорей на диске 11.09:

| якорь | на диске? | патч срабатывает? |
|---|---|---|
| stock_old / cat_old | нет | no-op |
| net_anchor | да | да (+stock_net_distinct) |
| meas_old / skip_old / rank_fold_old | да | да |
| sales_force_anchor / fork_b_old / ef_gate_old | да | да |

### (д)

`test_final_stock_route_filters_absent.py` — расширить на bypass+locks;
`test_wiki_card_hybrid.py` bootstrap; `test_zone_names_resolvable.py`
(патч); orphan-тесты stock filters — удалить с API;
все `test_sales_*` / `test_enough` / collapse — см. цели 1–13.

### (е)

Делать **последней волной** или тем же коммитом, что вырезает символы
патча (1/3/11). Не отделять «удалили sales_force из z20, патч оставили».

---

## Сводная таблица

| # | цель | строки диффа (ядро выреза) | зависимости (пары) | замки |
|---|---|---|---|---|
| 1 | sales-канон | z11 целиком; z20:1206–1285, 2229, 2660–2665, 3270–3278, 3378–3380, 4077–4086, 4230–4265, 4326–4332, 3536–3543; z21:671–673; boot sales/fork_b | 1∥2,1∥3,1∥5,1∥6,1∥7,1∥16 | `test_sales_canon_prefer`, `test_sales_rank_canon`, wiki hybrid/verify stubs |
| 2 | prefer_* | z10:428–491; z11:759–794; z20:2228–2230, 2660–2665, 3272–3274 | 2∥1,2∥4,2∥14 | sales_canon_prefer, stock stubs, final_stock_route |
| 3 | авто-мера | z20:4144–4170, 4230–4265, 4326–4332, 4360–4379; z16:415–435, 589–634; z11 money; boot sales_force/rank_fold/meas | 3∥1,3∥14,3∥7,3∥11 | sales_rank_canon, k4_guess, measure_* |
| 4 | K6 | z20:2232–2261; entity_rank_v2 вне тракта; z05:1006–1008; z16:392–393 | 4∥2,4∥11 | `test_k6_rank_v2`, action_class |
| 5 | арбитр-цикл | z20:3688–3918 (сохранить 3595–3686) | 5∥6,5∥7,5∥1 | step4_guards, early_clarify, action_class |
| 6 | signals/alias | z20:2923–3076, 3149–3382, 3407–3433, 3992–4009 | 6∥5,6∥1,6∥14 | step4_guards, leader_hatch |
| 7 | fork-авто / collapse | z20:3451–3593 (A/unique/B); z13 A/unique/mute/leader; z21:820–900, 980–983; **C+detector оставить** | 7∥8,7∥5,7∥3 | fork_outcomes, atom_terminal, wiki_candidate_verify |
| 8 | период-догадки | z03:377–393, 427–437, 581–611; z04/z04b prefer; z20:1715–1743, 1873–1903, 1881–1885; **1972–1999 оставить** | 8∥7,8∥9,8∥1 | period_*, calendar/currency_axis, fork_window |
| 9 | intent-суждения | z01:889–890; z02:39–50, 430–434, 588–623, 669–673; z16:359–375; period_zero_why | 9∥8,9∥1,9∥13 | test_intent |
| 10 | серый bypass | z20:2185–2192 | слабо | final_stock_route_filters_absent |
| 11 | z05 авто | z20:3384–3405; z05 auto-answer/rolling_year/pick; boot ef_gate/ecp order; **ecp clarify оставить** | 11∥1,11∥4,11∥3,11∥7 | test_entity_form |
| 12 | memory apply | z20:5810–5835 (+ зов); ask_choice_mem apply | изолированно от билетов | ask_choice_memory |
| 13 | enough | z20:5763–5805 (+ helpers enough) | 13∥9 | test_enough |
| 14 | реранк-победитель | z20:2394–2543; z10:233–295, 338+; z20:4467–4471, 4994 | 14∥3,14∥6,14∥2/4 | rank_leader, rank_axis |
| 15 | хвост | z20:2544–2577, 2263–2637, 5253–5281, 1931–1941?, канон-терминалы 4611–5362∖ядро; инерт M2 | 15∥14,15∥1; coverage→владелец | compose/coverage приборы |
| 16 | мёртвые locks/патчи | OR dead locks; z12 orphans; урезать `_patch_z20_wiki_primary` | последняя / тем же коммитом что 1/3/11 | final_stock, wiki_card_hybrid, zone_names |

### Рекомендуемые неделимые пакеты волн (для P3)

1. **P2-A:** цели **10** (bypass) + мёртвые OR-чтения (**16** частично) — низкий риск.
2. **P2-B:** **1+2+3** + boot sales/measure + z21:671–673 (канон сущности/меры).
3. **P2-C:** **4** (K6) + обновить вход wiki.
4. **P2-D:** **6+5** (сначала убрать наполнение/цикл; early-clarify оставить).
5. **P2-E:** **7** (fork-авто + collapse; detector/C оставить).
6. **P2-F:** **8+9** (период/intent-суждения; слоты z02 пока жить).
7. **P2-G:** **11** авто-формы (ecp оставить) + boot ef.
8. **P2-H:** **12+13** (memory apply + enough).
9. **P2-I:** **14+15** (порядок/хвост; coverage — после ответа владельца).
10. **P2-J:** **16** финальная зачистка патча/orphans/тестов.

---

## Неясное (честно)

1. **`not_for` / without_value** (цель 15): знание установки vs эвристика выбора —
   сплошной снос требует убрать из маршрута, но это может раздуть пул вики;
   нужен замер clarify-rate после P2-I.
2. **Coverage** (`z20:1931–1941`): ждёт MERGE §4.2 / стоп-точку владельца.
3. **`apply_prior_period`**: диалоговое наследование окна — формула не
   детализирует; в отчёте помечено на снос/меню, но это не ядро MERGE §2.8.
4. **`parse_intent` целиком** vs только majority (цель 9): MERGE §3.4 запрещает
   полную замену в этом пакете — граница «суждение» vs «слот SQL» на полях
   kind/want требует отдельной нарезки в P3.
5. **Один wiki yes при pool>1** (ядро): не цель сноса MERGE §2; риск скрытых
   прочтений — красной команде (MERGE §3.3 аналогично K6).
6. **Рантайм ≠ диск:** после load `_patch_z20_wiki_primary` вставляет
   stock_net / sales_canon_post / fork_b_sales / entity_form_gate — карта
   call-sites по диску **занижает** живой текст; любой снос символов без
   правки патча ломает импорт.
7. **`catalog_count_src` на диске:** якорь boot cat_old уже не находится
   (0 вхождений) — поздний замок прайса в z20, видимо, вырезан ранее; force_pool
   всё ещё читает `catalog_count_locked` из diag впустую.
8. **Подписи меню из wiki-passport** — единственная разрешённая *новая*
   функция; без неё после сноса авто-исходов меню останется на `label`
   таблицы (M2) — это дыра ступени 4, не закрытая одним удалением.
9. Граф MCP `memory` по запросу ask/snos — пуст; связи в этом файле только из
   кода/MERGE.

---

*Планировщик волны P, фокус P2. Код не менялся, кроме этого отчёта. Коммитов нет.
Серверы/БД не трогались. Срез: 2026-09-11.*
