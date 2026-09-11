# M2: карта последовательностей — где возможна параллельность в тракте вопроса

Режим: только чтение кода. Дата: 11.09.2026.  
Код: `ubuntu/serenedb/ask/z01,z02,z07,z09,z10,z16,z17,z20` + `entity_rank_v2.py`.  
Опора по числам: факты оркестратора 11.09; `docs/audit/webui-slow-w1.md` (TRACE: `шаг()` = накопленное мс от t0); `docs/audit/speed-s2/s3.md`.  
БД не трогалась.

---

## Вердикт в одну строку

Внутри одного `/ask` почти всё **последовательно**; `ThreadingHTTPServer` параллелит только **разные** HTTP-запросы. Крупнейшие независимые куски: (1) intent-сэмплы LLM, (2) readings×`fork_scan`, (3) арбитр×N полных `answer`, (4) серия HTTP-rerank по разным ролям. K6 ~52 с — уже **батч SQL**, не цикл по сущностям; выигрыш там — ускорение/кэш запроса, не ThreadPool.

---

## Карта (один тяжёлый вопрос, внешний `answer`, `no_arbiter=False`)

| # | Фаза | Код | Длит. (факт/оценка) | Зависит от предыдущей? | Можно параллелить / батчить? |
|---|---|---|---|---|---|
| 1 | Intent-сэмплы LLM | `z02:668-672` → `_one_intent` → `ds_chat`; потолок `ASK_INTENT_SAMPLES=5`, стоп при `INTENT_LEAD` | **факт орк.** 3–5 × ~2–3 с (in≈822); TRACE W1: 5× → **12,5 с** | Нет между собой (один и тот же `msgs`). Early-exit LEAD читает уже готовые | **Да:** пул всех N сразу + LEAD по мере прихода (см. §а). Env уже режет без пула |
| 2 | Memo / same_concept / enrich | `z02:674-685` | ≪0,1 с + 1 лёгкий SQL стеммов | Да, после merge | Нет смысла |
| 3 | Период / calendar / currency readings | `z20:1873-1879` → `z03/z04/z04b` | ≪0,1 с | Да, от intent | Нет (дешёво). Но **множит** фазу 14 |
| 4 | Probe FTS | `z06:58-100` | ~0,1 с (W1 Δ≈122 мс) | Да, от terms | Уже **один** `UNION ALL` — штатный батч |
| 5 | Resolve unmatched groups | `z06:122-142` → `resolve_values` `z07:507+` | 0…N × (embed + SQL + **1 rerank**) | Да, только для групп без FTS-хита; группы независимы | **Да:** ThreadPool по группам / один батч embed. Риск: порядок `break` на первом alt |
| 6 | Literal tables / partial | `z20:2043-2155` | ~0,1–0,5 с | Да | Уже SQL GROUP BY |
| 7 | Meaning: alias/card/near×2 | `z06:505+`, `z07:173` | W1 **Δ≈1,6 с** | Да (вход — exprs+kind). Поверхности независимы | **Да:** 4 поверхности параллельно; embed question∥kind. Риск гонки порядка fuse |
| 8 | Children / vector fallback | `z20:2155-2180` | редко; corpus kNN без IVF — **секунды** | Да, если `by` пуст | Нет (один запрос). IVF заблокирован |
| 9 | **K6 v2** `apply_to_candidates` | `z20:2240-2269` → `entity_rank_v2:804+` | **факт орк. ~51,7 с** | Да, нужен пул `cands` | См. §в: уже батч; узкое место — тяжёлый SQL, не Python-цикл |
| 10 | Stock-фильтры | `z20:2270-2286` | обычно ≪1 с | Да | Нет |
| 11 | «кандидаты собраны» | `z20:2287` | маркер | — | Оркестратор: **+21,5 с после K6**. В коде между K6 и маркером почти пусто → либо stock/иной маркер в TRACE, либо накопленное время чужого шага; уточнять по `diag.шаги` |
| 12 | Отсев «не отвечает» | `z20:2305-2380` | обычно <1 с; указатели — **цикл psql на rt** | Да, нужен `kind`+cands | Стемы уже батч `SELECT ts_lexize…`; указатели → один SQL `IN (…)`. См. §в |
| 13 | Order-by-meaning + entity rerank | `z20:2483-2568` | 2× (embed+SQL) **последовательно** (question, kind) + **1×** rerank HTTP ~1–2 с | Да | Embed×2 и kNN∥; rerank уже батч документов |
| 14 | **Детектор развилки** | `z20:2675-2738` → `fork_detector_scan` `z09:404+` | **факт орк. ~12 с** (`счёт_мс=11968` = wall самого блока) | Да: финальный `cands`+preds. **Не** зависит от wiki/арбитра | Readings сейчас **последовательны** (`fork_scan_readings`). См. §б |
| 15 | Wiki pick + verify | `z21:601+`, `539+` | 2× `ds_chat` ~2–5 с каждый | Да, после пула | Pick→verify **зависимы**. Два каскада в коде зовут verify дважды на разных путях — смотреть ветку |
| 16 | Сборка `arb_pool` / doubt / stop2 | `z20:3250-3404` | дёшево | Да | Нет |
| 17 | **Исходы A/B/C** | `z20:3479-3547` → снова `fork_detector_scan` | ещё раз **тот же класс SQL** (cost_ms **суммируется** с ранним) | Повторяет 14 на `arb_pool` | **Кэш/reuse** `_fork_early` вместо второго скана — главный дешёвый выигрыш |
| 18 | Early entity-clarify | `z20:3636-3710` | ≪1 с если сработал | Да | Уже env/гейт; режет арбитр |
| 19 | **Арбитр ×N** | `z20:3712-3730` `for c in arb_pool[:ARBITER_MAX]` → `answer(..., no_arbiter=True)` | N× (полный префикс без fork/арбитра; intent из memo) | Кандидаты **независимы** друг от друга; сравнение — после всех | **Да:** ThreadPool N≤3. Риск: N× нагрузка на SereneDB + LLM compose. Env: `ASK_ARBITER_MAX` |
| 20 | Measure / axis / grain | `z16:619` rerank; `z10:233+` LLM+rerank; `z17:469` | 0–несколько ×1–2 с | Да, после выбора src | Независимые rerank разных ролей (мера vs ось) редко пересекаются по времени на одном src |
| 21 | Aggregate / groups | `z08`, `z17` | SQL 0,1–несколько с | Да | Штатный один запрос |
| 22 | Compose + gate | `z18` `ds_chat`; `z19` | ~2–5 с | Да | Нет (нужны цифры) |

**Про psql:** каждый `psql()` = subprocess ~35 мс стартовый налог (`z01:300-334`) + время SQL. Много мелких вызовов дороже одного тяжёлого.

---

## Особые точки

### (а) 3–5 intent-сэмплов — параллель + LEAD

Сейчас: строго последовательный `while` (`z02:668-672`). Сэмплы **независимы** (одинаковый prompt, temperature=0, согласие по полям после факта).

Вариант:

1. Запустить `min(SAMPLES, max(LEAD+1, 2))`…`SAMPLES` вызовов в `ThreadPoolExecutor`.
2. По мере `Future.done` дописывать в `samples`, считать `_field_lead`; при `lead ≥ INTENT_LEAD` по всем полям — `cancel` остатка (best-effort: HTTP уже ушёл).
3. `_merge_intents` без смены семантики (при равенстве счётчиков побеждает «раньше» — зафиксировать порядок по индексу слота, не по wall-time).

| | |
|---|---|
| Выигрыш | Типично **~2×** на фазе: 5×2,5 с → ~2,5–3 с wall; орк. оценка **~6 с** с вопроса. При LEAD=3 и раннем согласии после 2 — пул всё равно платит за лишние in-flight, если стартовали все 5 |
| Риск | Гонка порядка при tie-break; orphan LLM после cancel; memo только после полного merge (уже так, Speed-Ask); нагрузка на DeepSeek ×N |
| Env без ядра | `ASK_INTENT_LEAD=2` + `ASK_INTENT_SAMPLES=3` → часто 2–3 вызова, **~5–7 с** экономии (speed-s2). Параллель — правка `z02` |

### (б) Детектор развилки ~12 с — что внутри

`счёт_мс` = `time.time()-_t_fork` вокруг блока `z20:2676-2732`, не внутренний таймер SQL.

Цепочка:

1. `_measures_by_src` — **один** SQL на весь корпус `unnest(map_keys(nums))`, кэш TTL `ASK_FORK_MEAS_TTL` (600 с). Холодный промах — дорого.
2. `_aliases_by_src` — один SQL по пулу.
3. `fork_detector_scan` → `period_readings` × `expand_readings_calendar_axis` (×2 day-basis) × `expand_readings_currency_axis` (×2 amount) → **до ~4–8 readings**.
4. `fork_scan_readings` (`z09:319-365`): **`for rd in readings: fork_scan(...)`** — строго последовательно.
5. Каждый `fork_scan` (`z09:242-316`): 2 SQL (count/folders GROUP BY; sums `unnest(map_entries)`). Докстринг: unnest ~**1,75 с** на ~623k (замер 15.08); на okna×1.6M и нескольких окнах → **~12 с** сходится.
6. Python `fork_classes*` — дёшево.
7. Позже **второй** такой же скан на исходах (`z20:3508`) — удваивает класс работ, если оба срабатывают.

Не LLM. Не цикл по строкам корпуса в Python.

Параллель readings: ThreadPool по `fork_scan` **или** один SQL с ключом окна в SELECT/GROUP BY (штатнее для п.20). Риск ThreadPool: N тяжёлых агрегатов одновременно на одном Duck/Serene → OOM/contention.

### (в) «Отсев не отвечает» + K6 features — батч?

**Отсев:** основной SELECT по `not_enough_for` уже батч; стемы — один `SELECT ts_lexize…, ts_lexize…`. Узкое место — **цикл указателей** `for rt in …: psql(count…)` (`z20:2348-2362`) → свернуть в один запрос по списку `rt`. Выигрыш: десятки×35 мс, не секунды K6.

**K6** (`features_table` + expand):

| Кусок | Уже батч? | Замечание |
|---|---|---|
| corpus aggregates | да, 1 SQL | |
| class / kind_cats / holders | да | |
| **axis DISTINCT JOIN** по корпусу+дате | да, 1 SQL | Главный кандидат на **~десятки секунд** |
| `_meas_profile_from_dict` | да (keys/alias/refcols) | |
| `_question_overlap_batch` | да; doc-scan только small≤1000 | |
| `expand_holders` | **нет:** `for cat: psql(refcols)` | Анти-паттерн п.20 → `WHERE target_src IN (…)` |
| `expand_stem_and_live` | 4× stem + 1 corpus scan | Последовательные префиксы; батч UNION |

Вывод: K6 — не «30 psql по сущностям»; параллелить Python-пулом почти нечего. Нужны: кэш features на (пул, period, kind), упрощение axis-JOIN, починка `expand_holders`. Ожидаемый выигрыш при удачном кэше/SQL — **десятки секунд** на повторных/похожих; на холодном — только оптимизация запроса.

### (г) Реранк-циклы — параллельны ли?

`rerank()` = **один** HTTP на список `documents` (`z07:348`). Внутри вызова параллели нет и не нужна.

Кто зовёт (последовательные роли на одном вопросе):

| Место | Сколько на вопрос |
|---|---|
| `z20:2564` entity head | **1×** |
| `z16:619` measure fallback | **1× на src**, где словарь не выбрал |
| `z10:178` / `z10:263,281` rank axes | 0–2× |
| `z17:489` / `z05:684` kind↔ось | 0–1× |
| `z07:562` resolve_values | **1× на нерезолвленный alt** |

«~30 вызовов» в W1 — **сумма ролей + арбитр×N (каждый под-`answer` снова measure/axis) + перемешивание stderr чужих потоков ThreadingHTTPServer**, не цикл `for doc in docs: rerank`.

Параллелить имеет смысл только **независимые** HTTP (например resolve по разным groups, или measure rerank разных src в арбитре). Риск: rate-limit реранкера; порядок merge.

---

## ТОП-5 параллельных / батчевых выигрышей

| # | Что | Выигрыш (с) | Как | Риск | Env без правки ядра? |
|---|---|---|---|---|---|
| **1** | Intent-сэмплы параллельно + LEAD | **~5–10** (фаза 12→~3–6) | ThreadPool в `parse_intent` | Tie-break; orphan LLM; квота API | Частично: `ASK_INTENT_LEAD=2`, `ASK_INTENT_SAMPLES=3` (~5–7 с без пула) |
| **2** | Не повторять `fork_detector_scan` на исходах | **~5–12** | Reuse `_fork_early` при совместимом пуле / инвалидировать только при смене pool | Неверный исход B/C если pool разъехался | Нет (код). Флаги `ASK_FORK_DETECT=0` режут качество |
| **3** | Readings×fork_scan: батч-SQL или пул | **~6–10** из ~12 | Один SQL multi-window **или** ThreadPool(readings) | Нагрузка движка; порядок cells | Частично: выкл. `ASK_CALENDAR_AXIS` / `ASK_CURRENCY_AXIS` → меньше readings |
| **4** | K6: кэш + батч `expand_holders` + ось SQL | **~20–50** на горячем/после оптимизации | Штатный SQL/кэш процесса, не пул | Устаревший кэш при смене корпуса | Нет готового флага; `K6R=None` отключает слой целиком (регресс ранга) |
| **5** | Арбитр ×N параллельно **или** ранний clarify | **N×(15–60)** или **-130** на clarify-пути (speed-s3) | ThreadPool `answer(focus=…)` **или** уже вшитый early-clarify | N× SQL+compose; ложный clarify | `ASK_ARBITER_MAX=2`; early-clarify уже в коде |

Дополнительно (меньше секунд, дёшево): батч указателей not_for; parallel meaning surfaces (~1 с); memo hit на повторе вопроса (`ASK_INTENT_MEMO`).

---

## Грань п.20

| Предложение | Класс | Допустимость |
|---|---|---|
| Один SQL на несколько окон / IN-список указателей / `expand_holders` IN | **Батч в базу** | Штатно. Предпочтительно |
| Кэш `_measures_by_src` / features на процесс | Кэш поверх уже посчитанного | Ок, если не вычитывать корпус в Python для пересчёта |
| ThreadPool вокруг `ds_chat` / `rerank` HTTP | Свой пул **вне** базы | Ок по п.20 (модель/сеть — свой контур) |
| ThreadPool вокруг нескольких `fork_scan` / тяжёлых `psql` | **Свой пул поверх базы** | Серая зона: не вынос данных в Python, но N параллельных агрегатов вместо одного штатного запроса. Сначала искать multi-window SQL; пул — только с лимитом и замером нагрузки |
| Parallel arbiter ×N полных `answer` | Пул поверх базы+LLM | Допустимо как оркестрация готовых путей; каждый путь уже «база считает». Риск — умножение нагрузки, не «считать в Python» |
| Вычитать корпус в Python и фильтровать | Запрещено п.20 | Не предлагается |

---

## Env-рычаги без правок ядра (сводка)

| Env | Эффект на время | Цена качества |
|---|---|---|
| `ASK_INTENT_SAMPLES` / `ASK_INTENT_LEAD` | Прямо режет LLM-префикс | Разброс kind/terms (замер 04.08) |
| `ASK_INTENT_MEMO` | Повтор вопроса ≈0 на разборе | Ок (ключ today+text) |
| `ASK_ARBITER_MAX` | Линейно режет хвост арбитра | Меньше соперников |
| `ASK_FORK_DETECT` / `ASK_FORK_OUTCOMES` | Убирает ~12 с×1–2 | Теряются исходы A/B/C |
| `ASK_CALENDAR_AXIS` / `ASK_CURRENCY_AXIS` | Меньше readings → быстрее fork | Меньше осей прочтения |
| `ASK_RERANK_TOP` | Меньше docs в entity-rerank (не число вызовов) | Хуже порядок головы |
| `ASK_DEADLINE_SEC` | Рвёт хвост, не ускоряет префикс | `unavailable` |

---

## Зависимости (сжато)

```
intent ──► probe/resolve ──► meaning ──► K6 ──► собраны ──► not_for/order/rerank
                                                              │
                                                              ▼
                                                    fork_scan×readings ──► wiki LLM
                                                              │              │
                                                              ▼              ▼
                                                    fork outcomes(reuse?)  arb_pool
                                                              │              │
                                                              └──── early clarify?
                                                                            │
                                                                            ▼
                                                                   arbiter×N answer
                                                                            │
                                                                            ▼
                                                                   measure/axis/agg/compose
```

Независимые «горизонтали»: samples intent; surfaces meaning; readings fork; sub-`answer` арбитра; HTTP rerank разных ролей (осторожно с квотой).

---

*Конец M2. Внедрение — отдельно; этот файл только карта и приоритеты.*
