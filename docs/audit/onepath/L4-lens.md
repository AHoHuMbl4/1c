# L4 — независимая линза: исполняемость промптов тракта ask

**Дата:** 12.09.2026  
**Аспект:** исполняемость моделью (длинные списки правил не исполняются; перегруз, внутренние противоречия, что ядро / что вырезать безопасно).  
**Метод:** свой grep по `ubuntu/serenedb/ask/*.py`; чтение каждого system/user-вызова целиком; чужие отчёты `docs/audit/onepath/*` не читались.  
**Ограничения:** только чтение кода + этот файл; модель не звалась; правки — кандидаты с риском, не патч.

---

## 1. Реестр промптов (полный, независимый)

Инфраструктура вызова: `ds_chat` / `ds_chat_post` в `z01_infra_trace_llm.py:564–579`. Констант `*_HINT` / `*_PROMPT` в ask/ **нет**. Единственный inline-system без константы — арбитр.

| Имя | файл:строка | длина (симв. / строк) | Кто вызывает | Тракт | Жив/мёртв | Поля ответа, читаемые кодом |
|---|---|---|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3227 / 47 | `parse_intent` → `_one_intent` (`z02_intent.py:565–667`) | legacy + новый (оба зовут `parse_intent`) | **жив** | JSON: `terms`, `kind`, `measure`, `want`, `period`, `amount`, `about`, `action_class`, `action_axis`, `search_form`; `period2` код ждёт, в schema промта **нет**; повтор при не-JSON |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 / 41 | `compose` (`z18:876`) ← только legacy `answer` (`z20_…_legacy.py:4109+`) | **только legacy** (новый z20: compose/SQL — волна B4, заглушка) | **жив в legacy** | `_split_answer` → `text`, `claims`; `_ask_back` → `ask` (далее **всегда** гасится `bare_clarify_forbidden`, :4325–4327) |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` и `_legacy.py:742` (дубль) | 891 / 15 | `_coverage_answer` (оба z20) | оба | **жив** | `text` + `claims` через `_split_answer`; сверка `check_claims` + `gate` |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 / 12 | `rank_axis_pick` ← `rank_axis_resolve` (`z10:265`) | **legacy** (новый answer ось не зовёт) | **жив в legacy** | JSON `axes` (1-based индексы) или regex цифр; max 3 |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 / 8 | только внутри `clarify_text` (`z07:308`) | — | **мёртв** (вызовов `clarify_text(` в дереве ask/ubuntu **0**; меню — код `clarify_say` / `wiki_menu_captions`) | был бы сырой текст фразы |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 443 / 8 | `wiki_verify_candidates` (`z21:738`) ← каскад | оба (каскад z21) | **жив** | `verdicts[].index`, `fit` (`yes`/`no`/`unsure`); `why` парсится в dict, на исход **не влияет** |
| `ARBITRATE` (inline) | `z01_infra_trace_llm.py:607–613` | 391 / ~6 | `arbitrate` (`z01:602`) | — | **мёртв** (вызовов в ask/ нет; тест `test_no_pre_wiki_reorders` требует 0 в z20) | только цифры → индекс ответа |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 282 / 4 | `refuse_text` (`z07:341`) — много терминалов no_data | оба | **жив** | весь текст; цифры вырезаются `_norm_numbers` → пусто |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 247 / 4 | `wiki_pick_from_cards` (`z21:799`) — ветка каскада | оба | **жив** (не единственный путь: verify-first) | `choice` (int); `separable` (bool) **AND** с kNN-gap кодом |

`OUR_PROMPTS` (leak-детектор, оба z20 `:755`/`:761`): INTENT, AXIS_PICK, CLARIFY, REFUSE, ANSWER, COVERAGE. **Нет** WIKI_PICK / WIKI_VERIFY / ARBITRATE.

### User-части (рядом с каждым вызовом)

| Промт | Сборка user |
|---|---|
| INTENT | `"today=%s\n\nQuestion: %s"` (`z02:667`); retry: `"Return the JSON object."` |
| ANSWER | большой body в `compose`: QUESTION + ROWS/GROUPS + COMPUTED-слоты + опц. coverage/folders/measure/corrections (`z18:719–875`) |
| COVERAGE | `"%s\n\nCensus:\n…"` (`z20:797`) |
| AXIS | вопрос `(kind)` + `"Axes:\n1. …"` (`z10:214`) |
| CLARIFY | `"Question: …\n\nOptions:\n- label (typical: …)"` — мёртв |
| REFUSE | сырой `question` |
| WIKI_VERIFY | вопрос `(kind)` + `"Passports:\n…"` (`wiki_format_passport_lines`) |
| WIKI_PICK | вопрос `(kind)` + `"Cards:\n…"` (`wiki_format_card_lines`) |
| ARBITRATE | context + Question + Answers + `"Number:"` — мёртв |

### Прочий «модельный» контур (не system-промт)

- Эмбеддер (`embed_one`) — не chat-промт.  
- `rerank` (`z07`) — отдельный HTTP API, без SYS-текста в ask.  
- Меню clarify в живом тракте — **без** LLM.

---

## 2. Анализ по аспекту «исполняемость»

Критерий линзы: модель читает длинный список правил и **не исполняет** их надёжно (замер проекта 03.08; в коде уже есть комментарии `[замер 04.08]` про дырявость слов ANSWER). Ранжирование внутри каждого промта: **ядро** (формат + 1–2 смысловых различения, без которых шаг ломается) → **полезное, но вторичное** → **шум / мёртвое / противоречие** (кандидат выреза).

### 2.1 `INTENT_SYS` — чистить (сильнейший перегруз)

**Вердикт:** оставить роль и JSON-схему; **сильно укоротить Rules**; часть полей-описаний свернуть.

**Ранг инструкций**

| Приоритет | Что | Почему |
|---|---|---|
| Ядро | «JSON only» + перечень ключей | без формы шаг 1 падает / retry; код жёстко нормализует |
| Ядро | `terms` = значения в записи; `kind` = род; не путать | прямо влияет на отбор; код дополнительно чистит, но модель всё равно кормит пул |
| Ядро | `want` ∈ sum/count/list; period/amount не в terms; не выдумывать | маршрутизация счёта |
| Вторичное | `about` data/coverage; `action_class`/`action_axis`; `search_form`; группировка альтернатив | живые поля, но длинные абзацы внутри schema модель схлопывает |
| Шум | многострочные определения внутри JSON-примера (`measure`, `kind`, `about`, `action_class`) | правила **внутри** псевдо-JSON — худший формат для исполнения |
| Дыра | `period2` в `_INTENT_FIELDS`, **в промте нет** | модель не инструктирована → поле нестабильно / пусто |
| Дыра | `amount.op` в промте без `"="`, код принимает `"="` (`z01:881`) | промт врёт схеме; модель уже шлёт `=` по замеру |

**Дословные перегрузы / противоречия**

```
"kind":   "ALWAYS fill this: a short noun naming WHAT kind of records …
           … Only null if the question names no kind of records at all"
```
«ALWAYS» vs «Only null» в одной фразе — классический сигнал «пропустить абзац».

```
Rules:
- "terms" holds only VALUES …
- A word for a ROLE of a party …
- Group alternatives …
- Never invent concepts …
- want = "sum" when …
- A numeric threshold belongs in "amount" …
- A time range belongs in "period" …
- Unknown fields are null. No text outside the JSON.
```
Восемь буллетов поверх уже раздутых описаний полей: по правилу проекта длинный список **не держит** поведение (нормализация — в `_normalize_intent`).

**Кандидаты выреза (безопасно для формата, риск — качество kind/terms):**
1. Сжать вложенные эссе в schema до одной строки на поле.  
2. Rules свести к 3: terms≠kind; want; no invent + period/amount.  
3. Добавить в schema `period2` и `"="` в amount **одной строкой** (это не «новое правило-запрет», а выравнивание формы с кодом).  
4. Не добавлять запретов «never put X» сверх terms/kind — код уже режет.

**Риск правки:** средний. Intent — корень ответа; любой срез → прогон `intent_parse_bench` / приёмка. Без замера не выкатывать.

---

### 2.2 `ANSWER_SYS` — чистить (противоречие с кодом + мёртвый `ask`)

**Вердикт:** ядро формата + placeholders оставить; блок `ask` и «claims null» — вычистить или упростить под один путь.

**Ранг**

| Приоритет | Что |
|---|---|
| Ядро | ответ только по данным; JSON `text`; язык вопроса; краткость |
| Ядро (слова слабые) | «NEVER WRITE A COMPUTED FIGURE» + placeholders | **замер 04.08**: 1/8 раз цифры руками; держит `_fill_figures` + `copied_figures` + gate |
| Мёртвое | весь абзац `"ask" is the middle road…` (:62–69) | legacy всегда `ask_back_dropped=bare_clarify_forbidden`; новый тракт: ask_back запрещён контрактом |
| Шум / конфликт | schema с `"ask"` и `"claims"` при «leave every role null» | модель тратит capacity на поля, которые код игнорирует или гасит |
| Вторичное | «list + total, not instead»; «no data if unrelated» | полезно, но дублирует user-часть MUST (coverage/folders) |

**Дословно мёртвое (можно вырезать без смены живого поведения):**

```
"ask": "one clarifying question, or null",
…
"ask" is the middle road between answering and giving up. Fill it ONLY when …
Never ask about our database, tables or fields: …
```

и

```
"claims" — leave every role null. It exists only for compatibility and is ignored.
```

**Конфликт с user-частью `compose`:** system говорит «не пиши цифры», user для coverage/folders говорит «stating the number … in digits» / MUST warn — модель получает два режима в одном вызове. Для исполняемости лучше: либо слоты `{missing}`/`{folders}` везде (как уже для coverage в body), либо короткая одна фраза в system «цифры только через {…}». Сейчас MUST в user конкурирует с NEVER в system.

**Риск:** средний на вырез `ask` (низкий для deliverable: путь уже мёртв); высокий на смену политики цифр без замера step6/gate.

---

### 2.3 `COVERAGE_SYS` — оставить ядро; выровнять с ANSWER

**Вердикт:** короткий, в целом исполним; конфликт паттерна с ANSWER.

Дословно:

```
- State figures in DIGITS, copied from the census — never recompute, never estimate.
- Put the number of missing rows in "claims.total" …
```

Здесь модель **обязана** писать цифры и claims — противоположность ANSWER. Это осознанно (отдельный путь + gate), но для модели два соседних system-стиля; путаница маловероятна (разные вызовы), но при унификации «одного пути» лучше один паттерн: слоты или digits+gate, не оба в разных SYS.

**Риск чистки claims-инструкции:** низкий-средний (check_claims всё ещё зовётся; пустые claims → soft path).

---

### 2.4 `AXIS_PICK_SYS` — оставить как есть

Короткий, одна задача, JSON `{"axes":[…]}`. Фраза «naming totals or inventing axis names is outside this step» — мягкий запрет; код принимает только индексы → **исполняется устройством**. Вырезать нечего без выгоды.

**Риск правки:** любой срез без нужды — лишний.

---

### 2.5 `CLARIFY_SYS` — снести из живого контура (уже мёртв)

Идеально короткий для модели, но **не зовётся**. Меню строит код. Держать в `OUR_PROMPTS` имеет смысл только как якорь leak для текста, которого модель больше не видит.

**Вердикт:** кандидат удаления константы + `clarify_text` + записи в OUR_PROMPTS **отдельным** шагом уборки; на ответы риск **нулевой**, пока вызовов нет.

---

### 2.6 `WIKI_VERIFY_SYS` — чистить поле `why`

**Вердикт:** формат оставить; `why` вырезать из инструкции (и опционально из парсера).

Дословно:

```
{"verdicts": [{"index": <1-based passport index>, "fit": <"yes"|"no"|"unsure">,
               "why": <one line>}]}
```

Исход `wiki_outcome_from_verify` смотрит только `fit`/`index`. `why` пишется в dict (`_wiki_row_to_verdict`) и дальше **ни на clarify, ни на leader не влияет**. Модель тратит tokens на prose → при лимите `WIKI_VERIFY_MAX_TOKENS` риск обрезания массива (есть salvage) **растёт** из-за бесполезного поля.

Описание входа («traits present… doesNotAnswer…») — полезный контекст формата карточки, не список запретов; оставить кратко.

**Риск выреза why:** низкий (поведение исходов то же); проверить salvage/parse тесты wiki.

---

### 2.7 `WIKI_PICK_SYS` — оставить; уточнить `separable`

Короткий, хорошая исполняемость. Нюанс кода:

```python
separable = bool(j.get("separable")) and k_sep
```

Модель может только **ужесточить** (false → clarify при большом gap), не ослабить kNN. Инструкция не объясняет, что separable — доп. голос. Для исполняемости: либо убрать `separable` из JSON и решать clarify только кодом (kNN), либо одной фразой «set separable false only if two cards equally fit». Сейчас поле — полумёртвый рычаг.

**Риск сноса separable:** средний (ветка clarify при спорных карточках).

---

### 2.8 `REFUSE_SYS` — не трогать

Эталон исполняемости: 4 строки, одна задача, запрет фактов/цифр **дублируется кодом** (`_norm_numbers`). Ядро = весь промт.

---

### 2.9 `ARBITRATE` inline — не трогать текст; контур мёртв

Короткий, правильный паттерн «только цифра / код режет». Возвращать в тракт без нужды нельзя (против wiki-first / one path). Снос мёртвого кода — отдельная уборка, не правка промта.

---

### 2.10 Сквозные наблюдения линзы

1. **Два стиля «держится промтом» vs «держится кодом»:** INTENT/ANSWER всё ещё содержат длинные Rules, хотя комментарии в тех же файлах прямо говорят, что промт форму не обеспечивает. Это главный дефект исполняемости.  
2. **Мёртвые инструкции внутри живых промтов** (`ask` в ANSWER, `why` в VERIFY, `CLARIFY_SYS` целиком) — хуже мёртвых файлов: модель всё ещё читает их в живом вызове.  
3. **Новый тракт** уже зовёт INTENT + wiki + REFUSE + COVERAGE; ANSWER пока не на линии — чистить ANSWER можно до flip, но регрессию ловить на **legacy**, пока он прод.  
4. **Не добавлять** новых «Never…» в промты (правило 03.08); любая чистка — укорочение формата, не новые запреты.

---

## 3. Итог

### 3.1 Правки-кандидаты

| # | Промт | Строка / фрагмент | Действие | Риск для живых ответов |
|---|---|---|---|---|
| L4-1 | `ANSWER_SYS` | `:59–69` schema/`ask` абзац | **Вырезать** поле `ask` и весь middle-road абзац (код уже гасит ask_back) | **Низкий** на legacy deliverable; средний только если кто-то снимет `bare_clarify_forbidden` без правки |
| L4-2 | `ANSWER_SYS` | `:60`, `:86` claims | Убрать `claims` из schema **или** одну строку «omit claims»; согласовать с `_split_answer` | **Низкий** (claims на основном пути уже «null») |
| L4-3 | `WIKI_VERIFY_SYS` | `:55–56` `"why"` | Убрать `why` из JSON-инструкции; парсер может оставить ignore | **Низкий**; плюс к полноте verdicts при truncate |
| L4-4 | `INTENT_SYS` | `:811–828` эссе в schema | Сжать описания полей до 1 строки; Rules → ≤3 буллета | **Средний** — только с `intent`-прогоном |
| L4-5 | `INTENT_SYS` | schema amount / period2 | Дописать `"="` и `period2` в форму (выравнивание с кодом) | **Низкий-средний**; может стабилизировать, не ухудшить |
| L4-6 | `CLARIFY_SYS` | `z07:285–311` + OUR_PROMPTS | **Снести** константу/`clarify_text`/элемент списка leak | **Нулевой** на ответы (0 вызовов); проверить тесты leak |
| L4-7 | `WIKI_PICK_SYS` | `separable` | Либо убрать поле (clarify = только kNN), либо одна фраза про false | **Средний** на частоту clarify |
| L4-8 | `COVERAGE_SYS` ↔ `ANSWER_SYS` | digits vs placeholders | При «одном пути» унифицировать паттерн чисел | **Средний** — отдельный замер coverage gate |
| L4-9 | `OUR_PROMPTS` | оба z20 | Добавить WIKI_* в leak-список (не текст промта модели) | **Нулевой** на ответы; защита от утечки wiki-SYS |

### 3.2 Не трогать

| Промт | Почему |
|---|---|
| `REFUSE_SYS` целиком | короткий, исполним, запрет цифр в коде |
| `AXIS_PICK_SYS` целиком | короткая задача; индексы режет код |
| `ARBITRATE` текст | мёртв; правильный образец; не возвращать без приказа |
| Ядро INTENT: terms≠kind, want, JSON | без этого ломается разбор |
| Ядро ANSWER: ONLY rows + placeholders + язык | даже при дырявости NEVER — формат слотов нужен compose |
| WIKI_VERIFY: `fit` tri-state + index | единственное читаемое решение |
| WIKI_PICK: `choice` 0..N | единственный сигнал выбора |

### 3.3 Порядок, если чистить

1. Мёртвое в живых вызовах без смены семантики: **L4-1, L4-3** (+ опц. L4-2).  
2. Уборка мёртвого контура: **L4-6**, L4-9.  
3. INTENT сжатие (**L4-4/5**) — только с замером согласия полей.  
4. Унификация цифр coverage/answer (**L4-8**) — после решения этапа-2 one-path, не «заодно».

---

*Конец L4. Сходимость с другими линзами — у оркестратора.*
