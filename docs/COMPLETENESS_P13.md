# П. 13 TARGET — полнота данных до клиента (Э4)

**Дата:** 26.08.2026  
**Режим:** офлайн-аудит; код `serene_ask.py` не менялся (правки — другому агенту).  
**Опора:** [`TARGET.md`](../TARGET.md) п. 13; [`PLAN_TO_TARGET.md`](PLAN_TO_TARGET.md) Э4;
[`AUDIT_CORRECTNESS_2026-08-25.md`](AUDIT_CORRECTNESS_2026-08-25.md);
[`COMPLEXITY_AUDIT_2026-08-25.md`](COMPLEXITY_AUDIT_2026-08-25.md);
[`PLAN_P13_COMPLETENESS.md`](PLAN_P13_COMPLETENESS.md);
`work/silent-refusal-fix-design.md`; мост `ubuntu/openclaw/mcp_ask.py`.

Контракт: *молчаливая потеря данных = дефект*. Обрезал — покажи **в ответе
клиенту**, не только в журнале / `diag` / stderr.

---

## 1. Два числа аудита 25.08 — источник и смысл

Источник: [`docs/AUDIT_CORRECTNESS_2026-08-25.md`](AUDIT_CORRECTNESS_2026-08-25.md)
§1.1 (пересчёт журнала okna `ask_journal`, порт 17890, **1 705** строк).
Первый срез — [`COMPLEXITY_AUDIT_2026-08-25.md`](COMPLEXITY_AUDIT_2026-08-25.md)
H3/H4 (1 687 строк; +1/+3 от роста журнала).

### 1.1. «47 из 67» — как считается

| Поле журнала | Условие | Число |
|---|---|---:|
| `fork_outcome` | `= 'unique'` | **67** |
| из них `outcome` | `= 'clarify'` | **47** (~70 %) |
| unique → answer / figures | | 18 / 2 |

Это **не** «единственный готовый ответ человеку». Это исход детектора
`fork_outcome='unique'` (один applicable-класс / один src), после которого путь
часто **не** делает early-return и уходит в арбитр → clarify.

Разбивка 47 unique→clarify (тот же аудит, верна **она**, не краткая формулировка
«ответ был — человек не получил»):

| Корзина | n | Смысл для п. 13 |
|---|---:|---|
| `computed` + есть `clarify_options` | **16** | атом есть; человеку предложены варианты (часто законное уточнение п. 12) |
| пустые `atoms` (`[]`), без options | **31** | unique зафиксирован, наружу clarify **без** атома — исход не терминален |

### 1.2. «180 figures при уже посчитанном атоме» — как считается

Среди строк с `outcome ∈ {clarify, figures}` и `"proof_status":"computed"` в
JSON `atoms` — всего **249**:

| outcome | n | с `clarify_options` | с `doubt` |
|---|---:|---:|---:|
| clarify | 69 | 52 | 27 |
| figures | **180** | 20 | 9 |

**180** — класс K5 / «молчаливый отказ при наличии числа» (C2): атомы уже
`computed`, клиенту уходит `kind=figures` (часто пустой/refuse-текст), а не
ответ с числом. Пример аудита: id 1686, atom compare ≈1 755 883,45,
`clarify_options` пуст.

### 1.3. Вердикт по выкладке задачи Э4

Краткая фраза «47/67 ушли в уточнение» и «180 figures при атоме» **совпадает с
журнальными счётчиками**, но смысл 47 уточнён аудитом: ~⅔ — clarify без атома,
~⅓ — clarify с options. Дороже для клиента — **180 figures с computed**.

Часть чинится флагом `ASK_ATOM_TERMINAL` (поток В); остальное — отдельные места
ниже.

---

## 2. Реестр мест, где множество/выдача могут уменьшиться

Строки — по текущему дереву `ubuntu/serenedb/serene_ask.py` (только чтение).
«Молчаливое» = клиент **не** видит пометку о потере/сокрытии в тексте ответа
или в PARTIAL моста.

| # | Место | Что теряется | Клиенту видно? | Чем заменить | ASK_ATOM_TERMINAL |
|---|---|---|---|---|---|
| **L1** | `:3856–3857` `MEANING_TOP`; RRF/kNN `LIMIT` (`:3185+`, `:3214`, `:3335`) | кандидаты сущностей за бюджетом перечня | **нет** (только порядок дальше) | в ответе/PARTIAL: «рассмотрено N видов из M» числом | нет |
| **L2** | `:12188–12198` `fit[:MEANING_TOP]` partial-кандидаты | сущности с частью понятий | **нет** — пишется в `diag.selection_budget`, не в `partial` (комментарий про partial устарел) | ключи `partial_shown`/`partial_total` в `partial` + PARTIAL моста **или** явная фраза | нет |
| **L3** | `:8363–8377` `PICK_BUDGET` обрезка перечня типов | виды записей не дошли до выбора модели | **нет** — stderr + `diag.selection_budget.entities_*` | то же: shown/total в PARTIAL или в тексте clarify | нет |
| **L4** | `:12562–12566` `RERANK_TOP` head/tail | хвост кандидатов не реранжируется | **нет** (`reranked`/`reranked_of` только diag; мост `PARTIAL_BUDGET_KEYS` намеренно не показывает) | либо не считать потерей множества (бюджет отбора), либо отдельная метка «отбор видов» | нет |
| **L5** | `:11008` `ARBITER_MAX` (умолч. 3); круг `:13599` | полные под-ответы только у головы пула | частично: rivals → clarify; mute может скрыть число | mute+computed → терминальная выдача | **да** (`prefer_mute_computed_over_clarify` `:6531–6559`) |
| **L6** | `:13551–13590` unique без early-return → арбитр/clarify | готовый unique-атом не уходит как ответ | **да как дефект** (человек видит уточнение вместо числа) | early `fork_outcome_unique` при computed | **да** |
| **L7** | `:14905–14928` gate-fail → `kind=figures` + `atom_terminal_gate_text` | число в атоме есть; текст refuse/пусто | **да как дефект** (отказ при данных) | `render_atom_pair` в text | **да** (`:6562–6572`) |
| **L8** | `:7503–7504` `answer_slot_mode`: `form=compare` → `rank` при флаге 0 | compare-слоты/figures; гейт режет → L7 | дефект выдачи | `slot_mode=compare` | **да** |
| **L9** | `:3341–3373` `rows_of` `LIMIT` (=`TOPK` `:113`, вызов `:14530`) | строки-примеры; **не** счёт множества | счёт — `{count}` / `ensure_count_named`; риск подмены TOPK за count закрыт формулировкой compose `:9586–9593` | держать: примеры ≠ count; при list без agg — явная пометка «показаны первые K» | нет (уже частично закрыто) |
| **L10** | `:9556–9577` `rows[:ROWS_TO_MODEL]` + обрезка `doc[:per_row]…` | хвост строк / хвост текста реквизита | обрезка текста — **да** (`…`); усечение числа строк — через count/n_groups | не ослаблять маркер `…`; list без count — «показано K из …» | нет |
| **L11** | `:8845`, `:8896` `aggregate_groups` `LIMIT k` | в ответе топ-K групп; `n_groups` по всему base | **да**, если путь answer: `ensure_n_groups_named` `:9222` + `asked_figure_missing` `:10128–10135` | figures/refuse без текста — дыра; чинить выдачей атома (L7) | косвенно (через L7) |
| **L12** | folders: `rows_of`/`aggregate` `IsFolder`; слот `{folders}` `:9753` | папки не в счёте | **да** на answer (`asked_figure_missing` `:10123–10127`) | то же число в figures-text | косвенно |
| **L13** | `:14591–14596` undated → `cut["undated_excluded"]` | строки без даты вне периода | **да** через мост `PARTIAL_LOSS_KEYS` (`mcp_ask.py:335–337`) | — | нет |
| **L14** | `:13974–13978` `_coverage_of` → `cut["coverage_missing"]` + предупреждение compose `:9731–9742` | строки 1С/витрины не в корпусе | **да** PARTIAL + обязанность цифр в тексте | гейт должен требовать `{missing}` в answer (сейчас — промт+claims) | нет |
| **L15** | `:10931–10934` `_coverage_answer` `LIMIT COVERAGE_TOP` | поимённый список потерянных видов | итоги missing **да**; имена сверх TOP — **нет** | «ещё N видов не названы» числом | нет |
| **L16** | `:12734–12735` / `:13522–13523` `atoms[:10]` / `atoms_truncated` | диагностические атомы fork в diag/журнале | **не** потеря счёта клиенту (C5 аудита) | не чинить как п. 13 ответа | нет |
| **L17** | валюта документа без ×`Курс` (C1; кода умножения нет) | учётная сумма подменяется суммой в валюте документа | **нет** (число выглядит полным) | ось валют / люк B; до неё — не смешивать валюты без пометки | нет |
| **L18** | `mcp_ask.py:327–337` PARTIAL: только LOSS-ключи | budget/assumption не уходят человеку | **намеренно** (F251); отбор видов молчит | решить: budget — не п. 13 множества **или** отдельный канал «отбор» | нет |
| **L19** | `:3695–3704` / fail-open rerank `:2932` (по аудиту C9) | пустой сигнал поиска/реранка | хуже выбор; клиент не видит «сигнал потерян» | статус uncounted / unavailable, не тихий `[]` | нет |
| **L20** | `_num`/`float` после DECIMAL (C4, ~aggregate/fork) | копеечная потеря точности на огромных суммах | латентно | сравнение на Decimal/строке | нет |

### Уже не молчаливые (для границы реестра)

- `partial_tables` `:2861+` — снимает прежнюю молчаливую отсечку порогом `match_expr` (замер 04.08 в docstring).
- `stale_note` `:10139` — возраст корпуса в тексте ответа.
- Исход B `:6576+` — лидер + options (люк), не молчаливый выбор.

---

## 3. Разбивка: закрыто флагом / не закрыто

### Закрывается `ASK_ATOM_TERMINAL` (поток В; дефолт `"0"`, бой выкл.)

| Места | Механизм |
|---|---|
| L5 (частично), L6, L7, L8, косвенно L11 | `prefer_mute_computed…`, early unique, `atom_terminal_gate_text`, `slot_mode=compare` |

После выката флага перемер: доли §1.1–1.2 (unique→clarify; figures+computed)
должны упасть на боевом журнале. **Не** закрывает покрытие 1С→корпус, FX,
бюджет отбора сущностей, TOPK-примеры.

### Требует отдельной работы

| Кластер | Места | Направление |
|---|---|---|
| Бюджет отбора видов | L1–L4, L18 | либо честный PARTIAL «отбор», либо явная политика «не п. 13» |
| Полнота корпуса | L14–L15 | уже есть coverage; дожать именование missing в answer-гейте |
| Валюта | L17 | `work/currency-axis-design.md` (К3) |
| Сигналы поиска | L19–L20 | fail-visible, Decimal |
| Примеры строк | L9–L10 | держать маркеры; list без count |

---

## 4. Замер полноты до клиента

Скрипт: [`work/acceptance/measure_completeness_p13.py`](../work/acceptance/measure_completeness_p13.py)
(первый запуск — 26.08.2026, см. §6).

### Вход

JSONL-дамп строк `ask_journal`, CSV-экспорт той же таблицы, или совместимый
дамп ответа `/ask` / selftest, поля как в `ask_journal.sql` + опционально
полный JSON ответа:

- `outcome`, `fork_outcome`, `atoms`, `clarify_options`, `partial_flag`,
  `truncated`, `text` / `kind` (если есть тело ответа);
- при отсутствии top-level `atoms`/`fork_outcome` скрипт читает
  `diag.fork.atoms` / `diag.fork.outcome` (дампы selftest и AB-прогонов).

### Что считает (те же определения, что §1)

1. **H3:** `unique_clarify / unique` и доли корзин (computed+options / empty atoms).
2. **H4/C2:** `figures_with_computed`, `clarify_with_computed`; из figures —
   доля без options.
3. **Silent cut:** ответы `kind=answer`, где в `partial`/`diag` есть
   `coverage_missing` / `undated_excluded` / `folders` / `n_groups>shown` /
   `selection_budget.*`, а в `text` нет цифры этой величины и нет PARTIAL-хвоста.
4. **Ложная тревога C5:** `truncated>0` ∧ `partial_flag=false` — **не** входит в
   silent-cut (обрезка diag-атомов).

### Критерий «п. 13 закрыт» (путь ответа)

П. 13 в контракте — ещё и цепочка 1С→поиск (перепись); для **выдачи до клиента**
после Э4/В2 считать закрытым, когда на живом журнале контура:

| Метрика | Порог |
|---|---|
| unique ∧ computed → `outcome=clarify` без options | **0** (или только явный п. 12 с options) |
| `outcome=figures` ∧ atom `computed` ∧ пустой/refuse text без числа атома | **0** |
| answer с LOSS-ключом в partial без цифры потери в text и без PARTIAL моста | **0** |
| coverage gap сущности в ответе без цифры `missing` | **0** |

Цепочка 1С→корпус (`search_coverage`, `/health` gap) — отдельный критерий из
[`PLAN_P13_COMPLETENESS.md`](PLAN_P13_COMPLETENESS.md); на okna gap **0/0** уже
замерялся, но **не** отменяет дыру выдачи K5.

---

## 5. Сводка счёта

| | Число |
|---|---:|
| Мест в реестре (L1–L20) | **20** |
| Из них молчаливые или дефект «данные есть — клиент не видит» | **14** (L1–L8, L14 частично, L15 имена, L17–L19; L9–L13/L16 в основном закрыты или не клиентские) |
| Явно закрываются `ASK_ATOM_TERMINAL` | **4** (+ косвенно L5/L11): L5·L6·L7·L8 |
| Требуют отдельной работы | **остальные** молчаливые |
| Скрипт замера | `work/acceptance/measure_completeness_p13.py` |
| Живой замер журнала okna 18–26.08 (§7) | **245** молчаливых из **386** с потерей |
| Мест, где пометка теряется/не доходит до клиента (§8) | **8** кластеров |
| Замок инварианта | `ubuntu/serenedb/test_partial_flag_propagation.py` |
| Э4 27.08: модуль + замок | `partial_visible.py`; замок **19/1** (S6 ждёт ask) |

---

## 6. Замер от 26.08.2026 (офлайн AB-дамп) — слабый вход

**Режим:** офлайн, только локальные файлы; `/ask` и БД не трогались;
`serene_ask.py` не менялся. Скрипт после первого прогона принял CSV и
нормализацию `diag.fork.*` — **формулы §4 не менялись**.

> Этот срез **не затирается**: ниже (§6.6 и §7) разобрано, чем он был слаб
> относительно живого журнала. Правило проекта — опровергнутое объясняется,
> а не стирается.

### 6.1. Что искали во входах

| Кандидат | Дата содержимого | Строк | Годен для §4? |
|---|---|---:|---|
| Журнал okna `ask_journal` из аудита 25.08 (порт 17890, **1 705**) | 25.08 | — | **нет в дереве** (только числа в `AUDIT_CORRECTNESS`) |
| `work/acceptance/runs/ask-journal-okna.jsonl` (пример в скрипте) | — | — | **отсутствует** |
| Полные ответы AB okna b7/b8/b9 → собранный JSONL | **18.08.2026** | **72** | **да** (есть `text`, `atoms`/`diag.fork`, `selection_budget`) |
| `selftest-ut_test-results-tier2.jsonl` | **17.08.2026** | **336** | частично (есть text+fork.atoms; `selection_budget` нет) |
| `public_ask_journal.csv` (sandbox export, db=`postgres`) | строки **17.08**; файл **22.08** | **592** | слабо: нет `text`/`diag`/`clarify_options`, `fork_outcome` пуст |
| `selftest-okna-results-tier2.jsonl` | ~17.08 | 138 | слабо: atoms/fork в теле часто нет |
| `docs/audit/**` | — | — | карты кода, не журнал ответов |

**Основной вход замера:**  
[`work/acceptance/runs/2026-08-18-okna-b789-ask-responses.jsonl`](../work/acceptance/runs/2026-08-18-okna-b789-ask-responses.jsonl)  
— склейка локальных дампов `2026-08-18-okna-b{7,8,9}-*-run*.json` (прогоны **18.08.2026**).

Команда:

```bash
python3 work/acceptance/measure_completeness_p13.py \
  work/acceptance/runs/2026-08-18-okna-b789-ask-responses.jsonl
```

### 6.2. Числа (основной вход, okna AB 18.08, 72 строки)

Исходы: answer **12**, clarify **24**, figures **27**, no_data **9**.

| Метрика | Число |
|---|---:|
| Ответов (строк) | **72** |
| С обрезкой/потерей данных | **63** (87,5 %) |
| … видно клиенту (LOSS с цифрой/PARTIAL) | **0** |
| … молчаливая потеря | **63** (87,5 %) |
| · из них LOSS без цифры/PARTIAL | **0** |
| · бюджет отбора `selection_budget` (L1–L4) | **63** |
| · figures: text скрывает atom | **0** / 27 с текстом |
| H3 `fork_outcome=unique` | **0** (на этом входе unique нет) |
| H4 clarify∪figures с `computed` | **51** (clarify **24** + figures **27**) |
| figures с computed без options | **0** |
| C5 `truncated>0` ∧ `partial_flag=false` | **0** |

### 6.3. Контрольные прогоны (не основной вердикт)

| Вход | n | молчаливая потеря | figures+computed | unique |
|---|---:|---:|---:|---:|
| `selftest-ut_test-results-tier2.jsonl` (17.08) | 336 | **1** (figures скрывает atom) | **135** (clarify 18 + figures 117; figures без options **1**) | 0 |
| `public_ask_journal.csv` postgres (строки 17.08) | 592 | **0** (нет text/diag — silent-cut и budget не видны) | **0** | 0 |

### 6.4. Вердикт по п. 13

**Пункт 13 (путь выдачи до клиента) — не закрыт.**

По критерию §4 на имеющемся честном локальном входе:

1. **Бюджет отбора молчит:** **63/72** ответов с обрезкой
   `entities_*` / `reranked_*` только в `diag`, клиенту **0** видимых пометок —
   это молчаливая потеря L1–L4 / L18.
2. **H4/C2:** **27** figures и **24** clarify уже с `computed` атомом на выборке
   AB (на живом журнале 25.08 было **180** figures+computed — здесь выборка
   другая и меньше, но класс не исчез).
3. **H3 unique→clarify** на локальных дампах **не измерим** (`unique=0`);
   закрыть «0 unique∧computed→clarify без options» по этому входу нельзя.
4. LOSS-ключи (`coverage_missing` / …) в этих 72 ответах не встретились —
   **0/0** silent LOSS не доказывает закрытие покрытия, только отсутствие
   сигнала в AB-дампе.

Журналы в репозитории **старше аудита 25.08** (18.08 AB / 17.08 selftest) и
**не** являются дампом боевого `ask_journal` okna на **1 705** строк — числу
для закрытия контракта на всём контуре **верить рано**.

### 6.5. Что нужно оркестратору для честного замера

1. Снять JSONL (или CSV+тело ответа) с **okna `ask_journal`** того же контура,
   что в `AUDIT_CORRECTNESS_2026-08-25.md` (порт **17890**, порядок **≥1 700**
   строк), поля минимум: `outcome`, `fork_outcome`, `atoms`,
   `clarify_options`, `partial_flag`, `truncated`; для silent-cut LOSS —
   ещё `text` и/или `partial`/`diag` ответа.
2. Положить как `work/acceptance/runs/ask-journal-okna.jsonl` (дата в имени)
   и снова вызвать `measure_completeness_p13.py`.
3. После выката `ASK_ATOM_TERMINAL` / правок L1–L4 — перемер на свежем
   журнале; пороги §4: unique∧computed→clarify без options **0**;
   figures∧computed∧refuse/пусто без числа атома **0**; LOSS без цифры/PARTIAL
   **0**.

### 6.6. Чем этот замер был слаб (не затирать)

Автор среза сам отметил слабый вход. Конкретно:

| Слабость | Факт §6 | Почему врёт про контур |
|---|---|---|
| Объём | **72** ответа AB 18.08 | на живом журнале 18–26.08 — **2192** (§7) |
| Состав | почти все «молчания» = `selection_budget` в diag | не видит `uncounted` / `truncated` / `discarded_before` журнала |
| LOSS-ключи | **0** встреч `coverage_missing`/… | на AB-дампе класс покрытия просто не попал в выборку |
| H3 | `unique=0` | нельзя судить unique→clarify |
| partial_flag | silent-cut считался по text/PARTIAL, не по журнальному флагу | оркестратор меряет `partial_flag` против `(truncated\|uncounted\|discarded_before)>0` |

Итог: доля **63/72 ≈ 87 %** — честна для AB-бюджета отбора, но **не** масштаб
и не определение «молчаливой» из живого журнала. Живые числа — §7; этот срез
остаётся как замер L1–L4 на локальном входе.

---

## 7. Замер от 26.08.2026 (живой `ask_journal` okna)

**Источник:** оркестратор, SQL к журналу `ask_journal`, контур **okna**, порт
**17890**. `serene_ask.py` этой сессией не менялся.

Определение корзины оркестратора:

- *с потерей* = `truncated > 0` OR `uncounted > 0` OR `discarded_before > 0`;
- *молчаливая* = с потерей AND `partial_flag = false` (нет флага частичности
  в ответе, который журнал снимает с `bool(out.partial)` —
  `serene_ask.py:15399`);
- *показанная* = с потерей AND `partial_flag = true`.

### 7.1. Числа

| Срез | Ответов | С потерей | Молчаливых | Показанных клиенту (флаг) |
|---|---:|---:|---:|---:|
| 18–26.08 (весь) | **2192** | **386** | **245** | **141** |
| последние 3 дня | **1349** | **186** | **83** | **103** (=186−83) |

Дополнительно за период 18–26.08: версий кода в журнале — **86**.

Доли: молчаливых среди ответов с потерей — **245/386 ≈ 63 %**; среди всех
ответов — **245/2192 ≈ 11 %**. За 3 дня: **83/186 ≈ 45 %** молчаливых среди
потерь.

### 7.2. Как читать поля журнала (код)

| Поле | Откуда (`serene_ask.py`) | Это потеря счёта клиенту? |
|---|---|---|
| `uncounted` | `_journal_uncounted_truncated` ← `partial.fork_limitation.uncounted_classes` или `diag.fork.uncounted` (`:15349–15368`) | да, класс развилки не посчитан |
| `truncated` | то же ← `diag.fork.atoms_truncated` / `lim.truncated` (`:12771`, `:13559`) | **часто нет** — обрезка diag-атомов до 10 (C5 аудита); в §4 silent-cut **не** входит |
| `discarded_before` | счётчик `_JOURNAL_LOST` при сбое записи журнала (`:15484–15485`) | **нет** — это потеря строки журнала, не ответа человеку |
| `partial_flag` | `bool(out.get("partial"))` (`:15399`) | любой непустой `partial`; мост человеку показывает только LOSS-ключи |

Следствие: живой «молчаливый» счёт **245** смешивает (а) реальную молчаливую
потерю счёта, (б) C5 `atoms_truncated` без `partial`, (в) сбои записи журнала.
Он сильнее §6 по объёму и по боевому контуру, но определение корзины шире
п. 13 «обрезал множество — скажи человеку». Развести корзины на SQL —
следующий замер оркестратора (фильтр: `uncounted>0` отдельно от
`truncated`/`discarded_before`).

### 7.3. Вердикт

**П. 13 на боевом контуре не закрыт:** при любом чтении корзины **245** (или
даже только доля `uncounted` внутри неё) — ответы с признаком потери уходят
без `partial_flag`. Прежний срез §6 это не опровергает и не заменяет: он
локально доказал молчание бюджета отбора (L1–L4); §7 доказал масштаб на
журнале.

---

## 8. Где потеря становится молчаливой (только чтение `serene_ask.py`)

Якоря — текущее дерево. «Молчаливое» = признак потери есть в diag/атоме/журнале,
а клиентский текст и/или `partial` (то, что мост превратит в PARTIAL) его не несут.

### 8.1. Признак выставляется, но в `partial` ответа не попадает

| # | Якорь | Что происходит |
|---|---|---|
| S1 | `serene_ask.py:8371–8380` | Обрезка перечня типов по `PICK_BUDGET`: комментарий п. 13 есть, пишется только `diag.selection_budget.entities_*` (+ stderr). В `cut`/`partial` — нет. |
| S2 | `serene_ask.py:12228–12234` | Комментарий: «сколько их было всего, видно в `partial`»; код кладёт `partial_shown`/`partial_total` в **`diag.selection_budget`**, не в `partial`. Комментарий устарел. |
| S3 | `serene_ask.py:12598–12602` | Хвост `RERANK_TOP`: `reranked`/`reranked_of` только в diag. |
| S4 | `serene_ask.py:12771`, `:13559` | `atoms_truncated` только в `diag.fork` → журнал `truncated`, `partial_flag` часто false (C5). |

### 8.2. Признак в `partial` / атоме есть, в тексте ответа может не быть

| # | Якорь | Что происходит |
|---|---|---|
| S5 | `serene_ask.py:14014` + compose `:9772–9778` | `cut["coverage_missing"]` выставляется; предупреждение — **промтом** модели (`DATA COMPLETENESS WARNING`). `asked_figure_missing` (`:10098–10172`) **не** требует цифру `missing` (только folders / n_groups). Без слота `{missing}` в тексте — цифра только у моста PARTIAL. |
| S6 | `serene_ask.py:14632` + `:9707–9708` | `cut["undated_excluded"]` + слот `{undated}`; гейт `asked_figure_missing` undated **не** проверяет. Нет `ensure_*` для undated (есть только `ensure_n_groups_named` `:9229`, `ensure_count_named` `:9250`). |
| S7 | `serene_ask.py:7736–7774` `render_atom_pair` | Оговорки `undated=` / `missing=` попадают в текст **только** если compose поставил `{pair:pN}` и сработала `fill_atom_pairs`. На основном пути пар может не быть — атом несёт excluded/completeness, проза — нет. |

### 8.3. Мост режет класс «бюджет» намеренно; журнал считает иначе

| # | Якорь | Что происходит |
|---|---|---|
| S8 | `ubuntu/openclaw/mcp_ask.py:327–378` | `PARTIAL_HINT` только для `PARTIAL_LOSS_KEYS` (`coverage_missing`, `undated_excluded`, `intent_lost`). Бюджетные ключи и `fork_limitation` человеку **не** показываются (F251). Даже если S1–S3 починить переносом в `partial`, мост их по-прежнему скроет — нужна согласованная правка моста **или** явная фраза/цифра в `text`. |
| S9 | `serene_ask.py:6704–6723` `fork_outcome_c` | `uncounted` → `partial.fork_limitation` + текстовая нота «часть прочтений не удалось посчитать». Здесь пометка **есть**. Молчание — когда `uncounted` остаётся только в `diag.fork` без этого исхода (журнал всё равно может увидеть список через `_journal_uncounted_truncated`). |

### 8.4. Уже держат пометку (граница класса)

- `intent_lost` → `cut` `:12081`; LOSS-ключ моста.
- Слияние partial под-ответов арбитра `:13653–13658` (`setdefault`, не замена).
- `ensure_n_groups_named` / folders в `asked_figure_missing` — число отброшенного в тексте на answer-пути.
- `stale_note` `:10175` / Handler `:15882` — образец **единой** пост-обработки ответа (свежесть); для п. 13 такого ещё нет.

**Итого мест, где пометка теряется или не доходит:** **S1–S8** (8 кластеров; S9 — контрпример рабочего пути). Из них S1–S3 — один механизм (budget→diag), S5–S7 — один механизм (нет кодового ensure цифры потери в text).

---

## 9. Единый механизм закрытия класса (без правки кода здесь)

Чинить ветки по одной (S1, S2, S3…) не закрывает класс: новый early-return снова
уйдёт мимо. Нужна **одна точка**, через которую ответ не может выйти, если в
атоме/`diag`/накопленном `cut` есть признак потери, а пометки клиенту нет.

### 9.1. Где ставить

Функция-образец уже есть: `stale_note` (`:10175`) — вызывается в `Handler` после
`answer_checked` (`:15882`). Для п. 13 этого **мало**: журнал пишется раньше, в
`finally` у `answer_checked` (`:15642–15644`), с `partial_flag` с текущего
`out.partial` (`:15399`). Пост-правка только в Handler опоздает к журналу.

**Точка:** новая функция `ensure_partial_visible(out) -> out` (рядом со
`stale_note`), вызов **в `answer_checked`, в `finally`, до `_ask_journal_write`**,
мутация того же dict. Тогда и клиентский JSON, и `partial_flag`/`uncounted` в
журнале видят один результат. Handler по-прежнему может звать её повторно
идемпотентно (как страховочную), но источником истины должен быть `finally`.

### 9.2. Что функция обязана сделать (класс целиком)

1. **Собрать признаки потери** из `out.partial`, `out.atom`/`atoms`
   (`excluded`, `completeness.missing`), `diag.selection_budget` (shown&lt;total),
   `diag.fork` (`uncounted`, не C5-only truncated), `diag.incomplete`.
2. **Перенести в `out.partial`** всё, чего там ещё нет: LOSS-ключи и (если
   политика п. 13 включает отбор видов) budget-ключи; `fork_limitation` при
   uncounted.
3. **Гарантировать видимость клиенту:** если в `partial` есть LOSS (или budget —
   по решению) и в `text` нет цифры этой величины — дописать машинный хвост
   кодом (как `ensure_n_groups_named`), не промтом. Мост `mcp_ask._with_partial`
   остаётся вторым поясом для LOSS; budget либо получает имя в мосте, либо
   живёт только в тексте.
4. **Не трогать** C5 `atoms_truncated` и `_JOURNAL_LOST` как «потерю счёта».

Инвариант замка: `has_loss_signal(out) ⇒ client_mark_present(out)`.

---

## 10. Замок

Файл: [`ubuntu/serenedb/test_partial_flag_propagation.py`](../ubuntu/serenedb/test_partial_flag_propagation.py).

Офлайн, без сети и базы: фикстуры ответов + живые хелперы
(`render_atom_pair`, `ensure_n_groups_named`, `asked_figure_missing`,
`_journal_uncounted_truncated`). Падает, когда признак потери есть, а пометки
в ответе нет.

**Прогон 26.08.2026:** `passed: 13` / `failed: 5` (exit 1). Пять красных —
открытый класс до `ensure_partial_visible`: silent `selection_budget`,
silent atom missing/undated, silent `diag.fork.uncounted`, silent
`diag.incomplete`, гейт не ловит `undated`.

**Прогон 27.08.2026 (Э4):** `passed: 19` / `failed: 1`. Дыры 1–4 закрыты
модулем `partial_visible.ensure_partial_visible` (замок зовёт ensure до
инварианта; pre-ensure контроль молчания бюджета остаётся). Красный один —
S6 `asked_figure_missing` + undated; патч — §11.2 (ждёт правки
`serene_ask.py` оркестратором). Проводка ensure в `answer_checked` —
§11.1.

---

## 11. Закрытие дыр 27.08 (Э4)

| # | Дыра | Корень (файл:якорь) | Статус 27.08 |
|---|---|---|---|
| 1 | `selection_budget` только в diag | запись в diag: `serene_ask.py` S1–S3 (`PICK_BUDGET` / partial fit / `RERANK_TOP`); клиенту молчит, т.к. нет единой пост-обработки | **закрыта кодом** вне ask: `ubuntu/serenedb/partial_visible.py` → `ensure_partial_visible` зеркалит budget в `partial` и дописывает «· рассмотрено shown/total» в `text` (мост budget не показывает — S8). **Проводка в боевой путь** — патч §11.1 |
| 2 | missing/undated в атоме без пометки | атом несёт `completeness`/`excluded`; текст — только через `render_atom_pair`/`fill_atom_pairs` (S5–S7) | **закрыта кодом** в `ensure_partial_visible`: `coverage_missing` / `undated_excluded` в `partial` + хвост `missing=`/`undated=` при отсутствии цифр. Проводка — §11.1 |
| 3 | uncounted только в `diag.fork` | `fork_outcome_c` уже пишет ноту; молчание — когда uncounted остался в diag без исхода C (S9) | **закрыта кодом** в `ensure_partial_visible`: `partial.fork_limitation` + нота «часть прочтений не удалось посчитать». Проводка — §11.1 |
| 4 | `diag.incomplete.missing` без partial | incomplete только в diag | **закрыта кодом** в `ensure_partial_visible` → `coverage_missing` (+ хвост). Проводка — §11.1 |
| 5 | `asked_figure_missing` не ловит undated (S6) | `serene_ask.py` `asked_figure_missing` (~`:10093`): после `folders` нет проверки `agg.undated` | **ждёт правки `serene_ask.py`** — готовый патч §11.2; замок красный **1** кейс намеренно |

Замок: до **13/5** → после **19/1** (добавлены pre-ensure контроль и journal after/raw).

### 11.1. Патч оркестратора: проводка `ensure_partial_visible` в `serene_ask.py`

**Файл:** `ubuntu/serenedb/serene_ask.py`  
**Не применять из этой сессии Э4** — правит оркестратор.

1) Рядом с `import ask_choice_mem as ACM` (~стр. 57):

```python
import partial_visible as PV
```

2) В `answer_checked`, блок `finally` (~`:15637`), **до** `_ask_journal_write`:

Было:
```python
    finally:
        _ask_journal_write(question, out, t0, trusted=trusted, user=user,
                           channel=channel, decision_id=decision_id, rid=rid)
```

Стало:
```python
    finally:
        if isinstance(out, dict):
            PV.ensure_partial_visible(out)
        _ask_journal_write(question, out, t0, trusted=trusted, user=user,
                           channel=channel, decision_id=decision_id, rid=rid)
```

Опционально (идемпотентно): после `stale_note` в Handler (~`:15877`) —
ещё один `PV.ensure_partial_visible(out)`.

### 11.2. Патч оркестратора: undated в `asked_figure_missing` (S6)

**Якорь:** функция `asked_figure_missing` (~`:10093`), сразу **после** блока
`if folders:` (~`:10154–10158`) и **до** блока `grain == "group"` / `n_groups`.

Вставить:

```python
    undated = (agg or {}).get("undated")
    if undated:
        if have is None:
            have = _norm_numbers(text)
        try:
            uf = float(undated)
        except (TypeError, ValueError):
            uf = None
        if uf is not None and uf not in have and round(uf, 2) not in have:
            return "без даты %s — не названо в ответе" % _fmt(uf)
```

После влива замок `asked_figure_missing требует undated (S6)` обязан стать
зелёным → **20/0** (при том же наборе кейсов).
