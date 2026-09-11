# S1 — Реранк-цикл ~30 вызовов на вопрос: карта и план ≤5

**Режим:** только чтение. Код/БД/коммиты не трогались.  
**Дата:** 11.09.2026.  
**Живой факт:** в срезе `.claude/state/webui-slow/ask-units.log` — **31×** `rerank отработал` (06:40:28–06:43:13); пачки 1 / 4 / 9–12 кандидатов; ~1–2 с на вызов к `.11:8005`. Ask → clarify 78–153 с; rerank — главный тормоз после разбора.  
**Стык:** `docs/audit/webui-slow-w1.md` §2 (точки), `w4.md` №4 / S1; приёмка любых правок — замки + L-метрика (п.10: ослабление проверки только с прогоном, wrong=0).

---

## Вердикт

Единая HTTP-точка — `rerank()` в `z07_rrf_vectors.py:348`. Вызывающих обёрток **пять** (entity / measure / axes×2 / resolve); на типовом тяжёлом вопросе они **умножаются**:

1. полный префикс `answer()` (отбор + entity-rerank) идёт **до** wiki-выбора и **до** применения `focus`;
2. круг арбитра (`z20:3621–3629`) зовёт `answer(..., focus=c, no_arbiter=True)` до `ASK_ARBITER_MAX` (**умолч. 3**) раз — каждый подвызов снова гоняет отбор+rerank;
3. оси: `rank_axis_resolve` + запасной `rank_axes_rerank`/`kind_axis_rerank` в grain-ветке; плюс `live_axis_col_for_count` → `kind_axis_rerank`;
4. `resolve_values` — по нерешённому терму (`RESOLVE_NEAR=12` → ровно «12 кандидатов» в журнале).

`serene_ask.py` rerank **не зовёт** (тонкий loader зон). После wiki-каскада (01.09) entity-rerank **больше не выбирает сущность**, но HTTP всё равно платится — порядок `cands` для arbiter/fork.

Цель ≤5 HTTP на вопрос достижима без отмены смыслового сигнала: кэш по входу в пределах запроса + short-circuit `len≤1` + не гонять entity-rerank в arbiter-подвызовах / при wiki-only pick + схлопнуть дубли осей. Доказать — счётчик HTTP + L-прогон (wrong не растёт).

---

## Карта вызовов (все точки → `rerank()`)

Единственный сетевой POST: `z07_rrf_vectors.py:348–403` (stderr: `rerank отработал: N кандидатов…`).  
`serene_ask.py` — без совпадений. Канон: `ubuntu/serenedb/ask/` (не `work/z21wt/`).

| # | Файл:строка | Обёртка / фаза | Кто зовёт | Раз на вопрос (по коду) | Входы |
|---|---|---|---|---|---|
| A | `z07:559` | `resolve_values` — фолбэк резолвера значений | `z06_entity_search.py:127` в `probe`, цикл по `alt` групп **без** буквального hit | 0…G×A: только если term-группа не найдена буквально; G=число пустых групп, A=альты до первого hit | `query=term`, `docs=keep` (после `_shares_chars`), потолок `ASK_RESOLVE_NEAR` **умолч. 12** |
| B | `z20:2562` | порядок кандидатов-сущностей (голова `RERANK_TOP`, умолч. 60) | `answer()` после смысла/`prefer_*`, **до** focus/wiki (`~2477–2566`) | **1× на каждый вход в `answer()`**, если `ORDER_BY_MEANING` и `len(cands)>1` и есть labels | `query=question`, `docs=label(src)` для `keys` головы |
| C | `z16:619` | `pick_measure` — величина, когда `measure_choice` → `how=='rerank'` | `z20:4093` (после выбора src); также `z21:745/751` (wiki collapse tied) | 0–1 на src; × число arbiter-подвызовов; ×2 в wiki-collapse при пустом/непустом word | `query=word` (intent.measure), `docs=measures_of(src)` |
| D | `z10:178` | `rank_axes_rerank` — порядок осей GROUP BY по вопросу | `rank_axis_resolve` `z10:263` и/или `:281`; запас `z20:4399`; также `z11:503` (`sales_rank_product_axis` → resolve) | 0–2 на вызов resolve; +0–1 запас grain; × подвызовы | `query=question`, `docs=метки осей` (`rank_axis_label_rows`) |
| E | `z17:489` | `kind_axis_rerank` — род → ось по меткам `target_src` | `rank_axis_resolve` `z10:277` (kind без q); `z20:4402`; `z05:684/694` ← `_pick_kind_axis_col` ← `live_axis_col_for_count` (`z20:4632/4679/4828`) | 0–2 на grain/count-ось; × подвызовы | `query=kind_text` / `axis_word`, `docs=метки target_src` |

Не HTTP (строка `'rerank'` как тег выбора, без POST): `z14:83` (`measure_choice` → how), `z20:4101+` (отказ догадки `rank_rerank` / `measure_guess_refused`), `z09` комментарии.

### Умножитель arbiter (главный источник «десятков»)

```text
answer()                          # B + (A?) + wiki + …
  └─ for c in arb_pool[:ARBITER_MAX]:          # z20:3621, ARBITER_MAX=3
       answer(focus=c, no_arbiter=True)        # снова полный префикс → снова B (+C/D/E)
```

`focus` применяется только на `z20:2748+`, **после** блока entity-rerank. Подвызов с уже известной сущностью всё равно платит HTTP за перестановку пула.

---

## Сверка со срезом (31 вызов)

Источник: `ask-units.log`. MCP TRACE rid=`3e8368047ba2dcfb`. Сервисный процесс `python[1693891]` — без per-call id у stderr rerank (ThreadingHTTPServer → потоки перемешаны, см. W1).

| Окно | MCP | Rerank stderr | Оценка по размеру пачки |
|---|---|---|---|
| 06:40:28–06:42:22 | ask#2 → TimeoutError 300080 мс | **14×** (1×4 + 9–12) | хвост тяжёлого list/rank до обрыва клиента |
| 06:42:45 | ask#4 после clarify 15 с | **1×** (1 канд.) | short-list / resolve-1 / пересечение с orphan#2 |
| 06:42:55–06:43:13 | ask#4: разбор→буквально→смысл (`тип=оптовые продажи`, `понятий=0`, `считать=list`) | **≥16×** (в основном **12**) | после `сущностей=16`+`добавлено=57` — цикл B×(1+arb) и/или D/E на ~12 осях; `понятий=0` → путь A маловероятен |

Распределение N в 31 строке:

| N кандидатов | Раз | Типичный код-путь |
|---:|---:|---|
| 1 | 8 | HTTP впустую: `rerank` не short-circuit при `len(docs)==1` (`z07:354` только пустой/ключ) |
| 4 | 3 | мало осей / мер (`D`/`E`/`C`) |
| 9–11 | 5 | урезанный пул sales/`prefer_*` или оси |
| **12** | **15** | либо голова entity после prefer (~12 sales), либо `RESOLVE_NEAR=12` (`A`), либо ~12 refcols (`D`/`E`) |

Итого «~30 на вопрос» в срезе = **сумма окон ask#2+#4 (+orphan)**, не один чистый rid. На одном тяжёлом проходе реалистично **~15–20 HTTP**; с arbiter×3 легко выйти к тому же порядку.

Карта фаз → оценка вызовов (типовой list/sales без resolve):

| Фаза | Точки | Оценка HTTP |
|---|---|---|
| `probe` / буквально | A | 0 (при `понятий=0`) … несколько |
| Порядок кандидатов | B | 1 + до `ARBITER_MAX` в подвызовах |
| Wiki pick/verify | — | 0 rerank (свой LLM; `z21:924+`) |
| Величина | C | 0–1 (+отказ догадки на sum всё равно после HTTP, `z20:4119–4124`) |
| Ось / grain / count DISTINCT | D, E, `z05` | 1–3 (+дубль `z20:4399` после уже званого resolve) |
| **Сумма на 1 cold ask** | | **часто 8–20; цель ≤5** |

---

## Классификация

### (а) Оправданные (трогать только с L-прогоном)

| Точка | Почему |
|---|---|
| **D** `rank_axes_rerank` / **E** `kind_axis_rerank` при реальном выборе оси | Меняют GROUP BY / rank grain; п.10+12 |
| **C** `pick_measure` когда результат **принимается** (`how=='rerank'` и нет `measure_guess_refused`) | Выбор величины |
| **A** `resolve_values` | «Питер»→«Санкт-Петербург»; без порядка — мусор в match (п.21) |
| **B** пока порядок `cands` кормит arbiter/doubt/fork | После wiki pick сущность не берётся из rerank (`z21:689–694`), но порядок соперников ещё от `cands` |

### (б) Дублирующиеся (кэш по `(query, tuple(docs))` в пределах одного HTTP-/ask)

| Паттерн | Где |
|---|---|
| Один и тот же пул ~12 labels × question | B во внешнем `answer` и в каждом arbiter-подвызове |
| `rank_axes_rerank(q, axes)` дважды | `z10:263` и `:281` (разные ветки, но при смене условий — повтор); плюс `z20:4399` после уже вызванного `rank_axis_resolve` (`:4388`) |
| `kind_axis_rerank` / оси | resolve + grain backup (`:4402`) + `live_axis_col_for_count` |
| `pick_measure` | внешний + подвызовы с тем же src/word |

### (в) Лишние / почти лишние

| Что | Почему |
|---|---|
| HTTP при **N=1** | Порядок единственный; 8/31 в срезе — чистая потеря ~8–16 с |
| **B при `focus` / `no_arbiter`** | Сущность уже задана; перестановка пула до `focus_forced` не нужна для ответа |
| **B как «выбор сущности»** | С 01.09 выбор — wiki (`wiki_hybrid_pool`, не reranked `cands`) |
| **C при sum**, затем `measure_guess_refused` | `z20:4119–4124`: HTTP оплачен, величина всё равно сбрасывается в clarify |
| Запас **D/E** на `:4399–4402`, если `_kh` уже из `rank_axis_resolve` | Мёртвый хвост при успешном resolve |

---

## План сокращения до ≤5 HTTP/вопрос

Оценки секунд: медиана **~1,5 с** на вызов (срез 1–2 с). Приёмка: оффлайн-замки ниже + L-прогон (`i2_runner`, wrong не↑, honest_no/match в допуске).

| # | Механизм | Где править (ориентир) | Экономия | Риск качества | Чем доказать |
|---|---|---|---|---|---|
| **P1** | Short-circuit: `len(docs)≤1` → `[0]` без HTTP | `z07:348` в начале `rerank` | ~1,5 с × число N=1 (в срезе до ~12 с) | Нулевой | `test_gate`/`test_step2` + счётчик stderr; L не обязателен, но дёшев |
| **P2** | Кэш запроса: ключ `(query, docs_tuple)` → order; ContextVar/на `diag` на время `answer` | обёртка вокруг `rerank` | Схлопывает arbiter×3 + дубли осей: часто **−10…20 с** | Нулевой при hit | Тот же ответ при повторном ключе; L smoke |
| **P3** | Не звать entity-rerank (B), если `focus` или `no_arbiter` (оставить vector sieve / `top_by_question`) | `z20:2481–2566` guard | **−1…3×B** ≈ 1,5–6+ с; главный рычаг arbiter | Низкий на focus-пути; на `no_arbiter` rival-order слабее → смотреть diverge/clarify | `test_rank_leader_path`, fork/arbiter замки; **L19/L-след**, wrong=0 |
| **P4** | Не звать B, когда wiki — единственный entity-pick и arbiter не будет (уже `picked`/locked) — или перенести B **после** решения «нужен ли arb_pool» | `z20` порядок фаз | **−1×B** на clarify-раннем выходе (~1,5 с); на полном — больше если arbiter не нужен | Средний: порядок соперников | Сравнить `diag.order_by` / arb_pool; L |
| **P5** | Убрать мёртвый запас `:4399–4402`, если `rank_axis_resolve` уже дал `_kh`; не звать D второй раз в resolve | `z20:4395–4402`, `z10:258–291` | −1…2 HTTP (~1,5–3 с) | Средний (ось) | `test_rank_leader_path`, `test_action_class`; L на rank/list |
| **P6** | Не звать C-rerank, если заранее известно, что sum → refuse guess (`compute` in sum/max/… и `len(measures)>1`) | `z16`/`z20:4093+` | −0…1 HTTP; качество то же (и так clarify) | Нулевой для sum-ветки | `test_gate.py` measure_choice; L sum-вопросы |
| **P7** | Батч: один POST с большим `documents` вместо N одинаковых query — **только если** API позволяет и вызывающие ждут разные подмножества; иначе P2 достаточнее | `z07` + callers | спорно | Смена контракта API | отдельный замер latency N=12 vs N=60 |

**Рекомендуемый порядок внедрения:** P1 → P2 → P3 → P6 → P5 → P4.  
Ожидаемый итог на классе «полный отчёт / list sales»: с ~15–20 HTTP до **≤5** (типично: 1×B outer + 1×D + ≤1×C/E + кэш на остальное), wall **−20…60 с** на тяжёлых (согласуется с w4 −30…90 с).

Не делать без отдельного решения: выкинуть B полностью «потому что wiki» — arbiter/doubt ещё читают порядок; только после замера rival-набора.

---

## Чем доказывать после правки

### Уже пишется (без нового TRACE)

| Сигнал | Где | Что даёт |
|---|---|---|
| `rerank отработал: N…` | stderr `z07:391–394` | **счётчик HTTP** (фильтр по pid/окну ask_start…ask_reply; rid у stderr нет) |
| `diag.selection_budget.reranked` / `reranked_of` | `z20:2552–2554` | размер головы B (не число вызовов) |
| `diag.order_by == "rerank"` | `z20:2566` | B сработал |
| `diag.шаги[].мс` | `z20:1844–1846`, `_diag_pack` | фазы; Δ соседних — длительности (W1: TRACE пишет elapsed от t0) |
| `diag.measure_guess_refused` / `measure_rank_*` | `z20:4101+` | C зря / отказ |
| `diag.rank_axis_auto` / `rank_axis_alts` | `z20:4392+` | путь осей |
| `diag.tokens.calls` | `_token_acc` / `_diag_pack` | chat, не rerank |
| L-метрика | `activeContext` L19: match/honest_no/**wrong**; `i2_runner` + `client-gold-okna.tsv` | качество ответов |

`search_quality` — служебные k/v сборки (`build_ts`, `emb_model_*`, `tick_status`), **не** счётчик rerank.

### Чего нет (и что добавить при разрешённой правке)

В `diag` нет `rerank_calls` / caller-tag. Минимальный прибор: в `rerank()` инкремент ContextVar + поле в `_diag_pack` (`calls`, `cache_hits`, `by_caller`). До этого — `grep -c 'rerank отработал'` на журнал одного прогона.

### Замки (оффлайн, без GPU)

`test_gate.py` (measure_choice/rerank-how), `test_step2.py` / `test_b9_routing.py` (resolve), `test_rank_leader_path.py`, `test_action_class.py` (kind_axis), wiki-замки если трогали порядок до cascade.

### L-прогон (обязателен при P3–P5)

Как в `activeContext`: `i2_runner` workers 16, эталон выката; смотреть **wrong** (не↑, цель 0 новых) и класс rank/list/sales. П.10: ослабление проверки порядка/оси без этого прогона — дефект приёмки.

---

## Исчерпывающий grep (канон `ubuntu/serenedb`)

Прямой `rerank(`: `z07:348` (def), `z07:559`, `z16:619`, `z10:178`, `z17:489`, `z20:2562`.  
Через обёртки: `z10:263,277,281`, `z20:4399,4402`, `z05:684,694`, `z11:503`→resolve, `z06:127`→`resolve_values`.  
`serene_ask.py`: 0.
