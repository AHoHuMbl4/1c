# L2: независимая линза — дубли «промт ↔ код» в тракте ask

**Дата:** 12.09.2026  
**Аспект:** какие инструкции промтов уже держатся кодом; где подсказка снижает возвраты гейта, где текст мёртв.  
**Метод:** свой grep по `ubuntu/serenedb/ask/*.py` (константы `*_SYS`/`*_PROMPT`/`*_HINT`, `role: system`, `ds_chat`); чужие `docs/audit/onepath/*` не читались. Код не менялся; модель не звалась.

---

## 0. Карта вызовов модели (инфра)

| Функция | Файл | Роль |
|---|---|---|
| `ds_chat` / `ds_chat_post` / `_ds_chat_body` | `z01_infra_trace_llm.py:549–579` | единственный chat DeepSeek; `max_tokens`/`temperature` |
| `embed_one` / rerank | `z01` / `z07` | не промпты чата; эмбеддер / `/v1/rerank` |
| Потребители `ds_chat` | см. реестр ниже | |

Тракты:

- **legacy** — `z20_ask_main_http_legacy.py` + зоны z01–z19/z21 (живой до flip).
- **новый (B3 скелет)** — `z20_ask_main_http.py`: `answer()` зовёт `parse_intent`, wiki-каскад, coverage; `compose`/SQL — заглушка до B4. Константы `ANSWER_SYS`/`AXIS_PICK_SYS`/`CLARIFY_SYS` всё ещё в `OUR_PROMPTS` через импорт зон.

---

## 1. Реестр промптов (свой)

Длина — число символов литерала system-текста (без кавычек), по содержимому файла.

| Имя | файл:строка | длина ≈ | Вызовы | Тракт | Жив/мёртв | Поля ответа, которые читает код |
|---|---|---|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | ~2700 | `parse_intent` → `_one_intent` (`z02:565–581`, msgs `z02:666–667`) | оба (шаг 1) | **жив** | JSON: `terms`, `amount`, `period`/`period2`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` — через `_normalize_intent` / `_merge_intents` |
| `ARBITRATE` (inline `sys_msg`) | `z01:607–613` | ~390 | `arbitrate()` | — | **мёртв** (определение есть, вызовов `arbitrate(` в ask/ нет) | только цифры → индекс ответа; иначе `None` |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | ~520 | `rank_axis_pick` (`z10:211`) ← `rank_axis_resolve` | legacy (+ зоны, если rank жив) | **жив** на rank-пути | `{"axes":[int…]}` или salvage цифр; индексы 1-based → `col`, cap 3 |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | ~390 | `clarify_text` | — | **мёртв** (вызовов `clarify_text(` нет; меню — `clarify_say`) | сырой текст; раньше уходил бы как clarify |
| `REFUSE_SYS` | `z07:317` | ~280 | `refuse_text` ← no_data / coverage fallback / fork | оба | **жив** | одна фраза; если `_norm_numbers(t)` непусто → `""` |
| `ANSWER_SYS` | `z18_compose.py:55` | ~1850 | `compose` ← legacy `answer` (~4110) | **legacy** (новый B3 compose ещё не зовёт) | **жив** в legacy | `_split_answer` → `text`,`claims`; `_ask_back` → `ask` (далее всегда сбрасывается) |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` **и** `_legacy.py:742` (дубль) | ~780 | `_coverage_answer` | оба | **жив** | `text` + `claims` (`check_claims` + `gate`) |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | ~220 | `wiki_pick_from_cards` | оба (wiki-каскад) | **жив** | `choice` (int), `separable` (bool) — AND с kNN |
| `WIKI_VERIFY_SYS` | `z21:50` | ~380 | `wiki_verify_candidates` | оба | **жив** | `verdicts[].index`, `.fit`; `.why` парсится, на исход **не влияет** |

`*_PROMPT` / `*_HINT` констант в ask/ **нет**.

### User-части (рядом с промтом)

| Промт | User-сборка | Где |
|---|---|---|
| INTENT | `today=%s\n\nQuestion: %s` (+ retry `"Return the JSON object."`) | `z02:666–676` |
| AXIS | `ask_text` (+ kind) + `Axes:\n1. …` | `z10:204–214` |
| CLARIFY | `Question` + `Options: - label (typical: …)` | `z07:303–309` — мёртвый путь |
| REFUSE | сырой `question` | `z07:341–342` |
| ANSWER | динамический body: ROWS/GROUPS/COMPUTED/PAIRS/coverage MUST/folders MUST/corrections | `z18:compose` → `ds_chat` `:876` |
| COVERAGE | `question` + `Census:\n…` | `z20*:795–797` |
| WIKI_PICK | `ask_text` (+ kind) + `Cards:\n…` | `z21:793–801` |
| WIKI_VERIFY | `ask_text` + `Passports:\n…` | `z21:733–741` |
| ARBITRATE | `Question` + `Answers:\n1)…` | `z01:614–619` — мёртвый путь |

### Не промпты, но тексты «для человека без модели»

| Механизм | Файл | Замечание |
|---|---|---|
| `clarify_say` / `format_clarify_options` | `z20*:309–352` | меню кодом; `gate_out` на числах вариантов |
| `human_table_label` / `label_has_meta_src` | `z20*:889–` | запрет метаданных 1С в подписях — **кодом** |

### Дыра `OUR_PROMPTS` / `prompt_leak`

`OUR_PROMPTS` = INTENT, AXIS_PICK, CLARIFY, REFUSE, ANSWER, COVERAGE.  
**Не входят:** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, inline ARBITRATE. Утечка длинной строки wiki-инструкции в клиентский текст `prompt_leak` не поймает.

---

## 2. Аспект: пары «строка промта ↔ код-двойник»

Легенда вердикта: **оставить** / **чистить** / **снести** + риск для живых ответов.

### 2.1 `INTENT_SYS` — форма JSON + правила terms/kind

| Строка промта (дословно, фрагмент) | Код-двойник | Полезность подсказки |
|---|---|---|
| `Reply with JSON only` + схема полей | `_first_intent_object`, `_normalize_intent`, типы/`lost`/`fixed`; retry при пустом JSON | полезна: меньше слепых разборов |
| `NEVER put the KIND of records [in terms]` / role words | `_normalize_intent` вычищает kind/measure из terms **только если** `_base_knows_kind_or_measure` (`z02:445–475`) | полезна: код чинит поздно; без подсказки чаще мусорный probe |
| `Never invent concepts…` | нет полного двойника; `assumed` period по цифрам в вопросе (`z02:557–561`) | частично: догадка периода ловится, «выдуманные terms» — нет |
| `want = sum\|count\|list` | `_WANT_OK`; чужой want → `list` + `fixed` | полезна |
| `about`: data\|coverage | `_ABOUT_OK` | полезна |
| `action_class`: event\|object\|none | `_ACTION_CLASS_OK` | полезна |
| `Unknown fields are null. No text outside the JSON` | разбор терпимый к болтовне; лучший JSON-блок по score полей | мягкая; код уже salvage |

**Вердикт:** оставить как есть (чистка только косметическая). Риск правок схемы полей — высокий (шаг 1 расходится → весь ответ).

### 2.2 `ANSWER_SYS` — главный очаг дублей

| Строка промта | Код-двойник | Вердикт |
|---|---|---|
| `NEVER WRITE A COMPUTED FIGURE YOURSELF… placeholders` | `_fill_figures` + `SLOT`/`LEFTOVER` + `copied_figures` + `formulation_flaws` + `gate` + `asked_figure_missing` | **оставить текст** (снижает рукопись и возвраты 2-й попытки); правило уже в коде. Чистить формулировку «even by copying from the figures below» — средний риск регрессии формулировок |
| `"claims" — leave every role null… ignored` | на основном пути `check_claims` **не зовётся**; claims в diag кладутся, но роль не сверяется | **чистить** схему claims из ANSWER (или снести поле из промта): мёртвый контракт + путает с COVERAGE, где claims живы. Риск низкий на основном пути; проверить, что `_split_answer` не ломается |
| `"ask" is the middle road…` (~8 строк) | `_ask_back` читает поле, затем **всегда** `ask_back=""` (`bare_clarify_forbidden`, legacy ~4325–4327); контракт «одного пути» — меню до SQL, без ask_back | **снести** блок про `ask` из ANSWER_SYS при B4/flip. Риск: модель может начать класть сомнение в `text`; нужен прогон приёмки |
| `Never invent numbers, dates or names…` | `gate` / `gate_out` / даты known | оставить кратко (снижает gate rejects) |
| `Reply in the SAME language…` | нет жёсткого кода | оставить (иначе своя проза) |
| `When … amount … state the computed total with {total}` | `asked_figure_missing` | оставить: подсказка ↓ отказов «есть данные — нет цифры» |
| user-часть `You MUST warn… missing` / folders | числа в `extra` слотах; без MUST модель забывает — гейт не требует наличия предупреждения | оставить: полезно; не дубль гейта |

**Итог по ANSWER:** живой смысл — форма `text` + плейсхолдеры + язык. Мёртвый объём — `ask` и (почти) `claims`.

### 2.3 `COVERAGE_SYS`

| Строка | Код | Вердикт |
|---|---|---|
| `State figures in DIGITS, copied from the census` | `gate(text, [], None, allowed)` по переписи | оставить (↓ gate) |
| `Put … in claims.total / claims.count` | `check_claims` **здесь зовётся** | оставить; это единственный живой claims-путь |
| дубль константы в `z20` и `z20_legacy` | — | **чистить** при B4: один модуль-источник. Риск низкий при bit-identical переносе |

### 2.4 `CLARIFY_SYS` (весь промт)

| Строка | Код | Вердикт |
|---|---|---|
| весь `CLARIFY_SYS` + `clarify_text` | `clarify_say` строит меню без модели; `label_has_meta_src` / `human_table_label` режут метаданные; `gate_out` | **снести** константу и функцию после подтверждения grep «0 callers» в тестах/вне ask. Риск нулевой для прод-ответов (путь мёртв); убрать из `OUR_PROMPTS` |

Дословно промт: *«Never show table names, codes or internal identifiers»* — полный двойник уже в `format_clarify_options` (meta → `human_table_label` / hint wipe).

### 2.5 `REFUSE_SYS`

| Строка | Код | Вердикт |
|---|---|---|
| `State no facts, no figures…` | `return "" if _norm_numbers(t) else t` | оставить 1 фразу про «no figures» (↓ пустых отказов из-за вырезания); остальное — роль модели (язык) |
| `Write ONE short sentence…` | нет длины-гейта | оставить |

### 2.6 `AXIS_PICK_SYS`

| Строка | Код | Вердикт |
|---|---|---|
| `Reply with indices only; naming totals or inventing axis names is outside…` | парсер берёт только индексы ∈ [1..N], cap 3; имена осей моделью не принимаются | оставить коротко: снижает мусор в JSON; запрет «invent names» уже структурой ответа |
| `Empty list when no axis fits` | пустой `picked` → fallback rerank/hits | оставить |

### 2.7 `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS`

| Строка | Код | Вердикт |
|---|---|---|
| `{"choice": …, "separable": …}` | `choice` → лидер; `separable = bool(model) and k_sep` — **модель не может форсировать clarify против большого kNN gap**, но может **смягчить** separable при уже близком gap | `separable` в промте — слабый рычаг; **чистить осторожно**: убрать просьбу separable и оставить только choice → clarify только по `wiki_knn_separable`. Риск средний (меню vs лидер на близких карточках) |
| verify `"why": <one line>` | парсится в verdict, `wiki_outcome_from_verify` смотрит только `fit` | **чистить** why из промта (экономия токенов). Риск низкий; diag/отладка потеряет текст |
| `Include one verdict per passport` | пропуск вердикта ≠ `no` → не пускает в единственного лидера | оставить: иначе чаще clarify/degraded |

### 2.8 `ARBITRATE` inline

Весь блок мёртв. Код-двойник «только номер» (`digits` → индекс) идеален — но **вызовов нет**.  
**Вердикт:** снести вместе с `arbitrate` при уборке мёртвого, либо оставить до отдельного решения владельца про арбитра. Риск 0 для текущих ответов.

### 2.9 Динамические MUST в user `compose` (не `*_SYS`, но «промт»)

Фразы `You MUST warn…` / `You MUST say this…` / `YOUR PREVIOUS ANSWER WAS REJECTED…` — не запреты контракта в system, а задания на этот ответ. Двойник частичный: слоты `{missing}`/`{folders}` подставляет код, но **наличие** предупреждения в тексте кодом не требуется.  
**Вердикт:** оставить (полезны); не путать с правилом «не писать запреты в промт» — это форма ответа на конкретные числа.

---

## 3. Сводка по каждому промту

| Промт | Вердикт линзы | Главный дубль |
|---|---|---|
| INTENT_SYS | оставить | нормализация типов/terms vs правила промта |
| ANSWER_SYS | чистить `ask` + claims-схему; оставить placeholders/язык | `_fill_figures`/`gate`/`copied_figures` vs NEVER WRITE; ask_back vs bare_clarify_forbidden |
| COVERAGE_SYS | оставить; слить дубль файлов позже | gate+check_claims vs «digits/claims» |
| CLARIFY_SYS | **снести** (мёртвый) | `clarify_say`+meta labels |
| REFUSE_SYS | оставить | `_norm_numbers` |
| AXIS_PICK_SYS | оставить | индексный парсер |
| WIKI_PICK_SYS | чистить `separable` (кандидат) | AND с `wiki_knn_separable` |
| WIKI_VERIFY_SYS | чистить `why` (кандидат) | исход только по `fit` |
| ARBITRATE | **снести** или отложить | мёртвый путь |

---

## 4. Кандидаты правок

| # | Промт | Что / где | Действие | Риск для живых ответов |
|---|---|---|---|---|
| 1 | ANSWER_SYS | блок `"ask" is the middle road…` и поле `"ask"` в JSON-схеме (`z18:59–69`, `88`) | снести при выравнивании с «одним путём» | **средний**: сомнение может уехать в `text`; нужен gold/приёмка |
| 2 | ANSWER_SYS | `"claims": …` + «leave every role null» | убрать из схемы ответа (оставить только `text`) **или** явно не слать claims в legacy path | **низкий** на answer-пути (`check_claims` не зовётся); не трогать COVERAGE |
| 3 | CLARIFY_SYS + `clarify_text` | `z07:285–311` + запись в `OUR_PROMPTS` | снести | **нулевой** (0 callers) |
| 4 | ARBITRATE `sys_msg` + `arbitrate` | `z01:602–628` | снести или пометить deprecated до решения | **нулевой** |
| 5 | WIKI_VERIFY_SYS | `"why": <one line>` | убрать из формата | **низкий** |
| 6 | WIKI_PICK_SYS | поле `separable` | убрать; clarify только по kNN gap | **средний** на tie/clarify |
| 7 | COVERAGE_SYS | дубль z20 / z20_legacy | один источник после flip | **низкий** |
| 8 | `OUR_PROMPTS` | нет WIKI_* | добавить в список leak (не правка промта модели) | **низкий**; ловит утечки wiki |

Правки 1–2 — только с замером; промпты живые и держат приёмку.

---

## 5. Не трогать

| Что | Почему |
|---|---|
| Ядро INTENT_SYS (схема + terms/kind/want/about/action_*) | шаг 1 = развилка всего тракта; код чинит форму, но не смысл |
| ANSWER_SYS: NEVER WRITE + плейсхолдеры + язык + «how much → {total}» | снижает рукопись; код ловит, но поздно (2-я попытка / refuse) |
| COVERAGE_SYS целиком (кроме дубля файла) | claims здесь реально сверяются |
| REFUSE_SYS | единственный мультиязычный отказ; цифры режет код |
| AXIS_PICK_SYS форма `{"axes":[…]}` | короткий; индексный контракт рабочий |
| WIKI_VERIFY правила leader (один yes + остальные no) | логика в коде завязана на полноту verdicts |
| user MUST coverage/folders в compose | нет кодового «обязан сказать»; без текста клиент не видит неполноту |
| `gate` / `_fill_figures` / `prompt_leak` / meta-label код | это не промпты; трогать взамен «укоротить промт» нельзя |

---

## 6. Метод и границы линзы

- Реестр построен grep’ом по ask/; worktree `work/z21wt` не входил в scope задачи.
- Shell-подсчёт длин в сессии был недоступен (таймаут хуков) — длины ≈ по литералам; при сверке оркестратором допустим `len()`.
- Не оценивались: качество формулировок для качества retrieval, стоимость токенов как отдельная метрика, содержимое чужих P1/P2/P3.
- Фокус линзы — **дубли с кодом**, не полнота тракта «один путь».

---

*Конец L2-lens.*
