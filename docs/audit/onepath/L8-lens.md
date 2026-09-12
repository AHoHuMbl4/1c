# L8 — независимая линза: история и замеры промптов тракта ask

**Дата:** 12.09.2026  
**Аспект:** что переживало приёмки/замки/L-прогоны (трогать нельзя); что менялось наощупь; что осталось от снесённых механизмов (ask_back, fork-арбитр, verify-порог в коде, entity_form без промпта).  
**Метод:** свой grep по `ubuntu/serenedb/ask/*.py`; чтение каждого system + user/вызова; `git log -L` / `-S` / blame по строкам. Чужие отчёты `docs/audit/onepath/*` не читались. Код не менялся.

---

## 0. Граница реестра

Единственный канал модели в ask — `ds_chat` (`z01_infra_trace_llm.py`).  
Именованные `*_SYS`: 8 констант + 1 inline system у `arbitrate`.  
Других `*_PROMPT` / `*_HINT` (как system к модели) нет.  
`clarify_say` / `format_clarify_options` / `wiki_menu_captions` — **код**, не промпты.  
`entity_form` (z05) — **без** вызова модели.  
Рерanker (`rerank` в z07) — отдельный HTTP, не DeepSeek-промпт; в реестр не входит.

Тракты:
- **legacy** = живой до flip (`z20_ask_main_http_legacy.py` + зоны) — прод 14aec85.
- **новый** = `z20_ask_main_http.py` (скелет «один путь» B3): уже зовёт `parse_intent`, wiki-каскад, coverage, `refuse_text`; `compose`/`ANSWER_SYS` в `answer()` ещё нет.

---

## 1. Реестр промптов

| Имя | файл:строка | длина (симв.) | Вызовы | Тракт | Жив/мёртв | Поля ответа, которые читает код |
|---|---|---:|---|---|---|---|
| **INTENT_SYS** | `z01_infra_trace_llm.py:800` | 3239 | `parse_intent` → `_one_intent` → `ds_chat` (×SAMPLES); user: `today=…\nQuestion:…`; retry «Return the JSON object.» | оба | **жив** | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` → `_normalize_intent` / `_INTENT_FIELDS` |
| **ANSWER_SYS** | `z18_compose.py:55` | 2456 | `compose` → `ds_chat`; user собирает ROWS/GROUPS/COMPUTED/… | **legacy** (новый пока без compose) | **жив в legacy** | `text` (`_split_answer`); `ask` (`_ask_back` → затем **глушится**); `claims` парсятся, в compose-пути **не сверяются** |
| **CLARIFY_SYS** | `z07_rrf_vectors.py:285` | 439 | только внутри `clarify_text` | — | **мёртв** (`clarify_text(` — 0 вызовов с 178ce51) | был бы сырой текст; сейчас никто |
| **REFUSE_SYS** | `z07_rrf_vectors.py:317` | 282 | `refuse_text` → много no_data/отказов (legacy+новый+z21/z13/z04) | оба | **жив** | вся строка; цифры вырезаются кодом (`_norm_numbers`) |
| **AXIS_PICK_SYS** | `z10_rank.py:136` | 598 | `rank_axis_pick` ← `rank_axis_resolve` | legacy (+новый, когда дойдёт rank) | **жив** | JSON `axes: [int…]` (fallback — любые цифры); до 3 индексов |
| **WIKI_PICK_SYS** | `z21_wiki_choice.py:45` | 247 | `wiki_pick_from_cards` (пул ≥2) | оба (каскад) | **жив** | `choice` (int); `separable` (bool, **AND** с kNN-gap) |
| **WIKI_VERIFY_SYS** | `z21_wiki_choice.py:50` | 443 | `wiki_verify_candidates` | оба | **жив** | `verdicts[].index`, `.fit` (`yes`/`no`/`unsure`); `.why` парсится, **на исход не влияет** |
| **COVERAGE_SYS** | `z20_ask_main_http.py:736` (=legacy:742) | 891 | `_coverage_answer` | оба | **жив** | `text` + `claims` → `check_claims` + `gate` |
| **ARBITRATE** (inline) | `z01_infra_trace_llm.py:607` | 391 | `arbitrate` — **определение есть, вызовов нет** (снят 14aec85) | — | **мёртв** | был бы один номер (цифры из ответа) |

`OUR_PROMPTS` (leak-гейт): `INTENT`, `AXIS_PICK`, `CLARIFY`, `REFUSE`, `ANSWER`, `COVERAGE`.  
**Нет** `WIKI_PICK` / `WIKI_VERIFY` / ARBITRATE — утечка wiki-system в клиентский текст не ловится этим списком.

Инфраструктура вызова (не промпт): `ds_chat` / `_ds_chat_body` — model/thinking/timeout; эмбеддер — отдельно.

---

## 2. Анализ по аспекту (история × замер)

### 2.1 INTENT_SYS — оставить как есть

**История с замером:**
- Ядро (terms/kind/want/measure/period/amount/about) — линия от чистки промптов `4a53882` (31.07, «только задача, запреты держит код») и калькулятора/гейта (`e8c4332`, `8e89dfa`).
- Нормализация типов и «`=` в amount» — код с `[замер 04.08]` в комментариях z01/z02; замок intent **162/0**.
- Согласие нескольких samples (`INTENT_SAMPLES`/`LEAD`) — `[замер 04.08, intent_parse_bench]`: 18/58 расхождений без согласия; живёт в коде вокруг промпта, не в тексте.
- `action_class` / `action_axis` — `2e42e61` (К9), замок action_class **48/0**.
- `search_form` — **единственная** правка текста промпта после нарезки: `708e6a7` (01.09), с числами (карточка в пуле, замки 162/0). Дословно добавлено:

```
"search_form": "the question as a short search phrase in its own language: what the
             question is about, with the entity names kept exactly as the user wrote
             them. Dates, time periods and numeric thresholds stay out — they live in
             period/amount"
```

**Вердикт:** не трогать. Поле `search_form` — измеренное расширение схемы, не «наощупь». Правила в промпте — описание формата JSON (роль), не новые запреты продукта.

**Риск правки:** высокий — ломает разбор входа всего тракта и wiki-пул.

---

### 2.2 ANSWER_SYS — чистить (хвост ask_back + мёртвые claims)

**История с замером (ядро — не трогать):**
- Placeholder-калькулятор и запрет рукописных чисел выросли из `e8c4332` / `4a53882` / контрольного `f79424a` («промты были ни при чём»). Комментарии в `compose` ссылаются на `[замер 04.08, step6_live.py]`: модель 7/8 оставляет `{total}`, иногда пишет цифры — поэтому значения модели **не показывают**.
- Замок compose **92/0**; L67 на живом legacy опирается на этот путь.

**Хвост без работы (снесённый механизм ask_back):**
Дословно в system:

```
 "ask": "one clarifying question, or null",
…
"ask" is the middle road between answering and giving up. Fill it ONLY when the rows do
not answer exactly what was asked, …
```

Появилось с `bfd3ba2` (28.07, средний рубеж п.21). С `e87b598` в live путь глушится кодом:

```
diag["ask_back_dropped"] = "bare_clarify_forbidden"
ask_back = ""
```

В контракте «одного пути» модельных ask_back после ответа нет; меню — единый построитель **до** SQL.

Также дословно:

```
"claims" — leave every role null. It exists only for compatibility and is ignored.
```

В legacy compose-пути `check_claims(claims, …)` для ответа **убран** (комментарий у 4157+); claims ещё живут у COVERAGE.

**Вердикт:**  
- **оставить:** блок про placeholders / NEVER WRITE / язык / no invent — измеренная опора п.19.  
- **чистить (кандидат):** схему `"ask"` + абзац middle road; опционально убрать `"claims"` из ANSWER_schema, если sync с `_split_answer`/leak не сломает (claims у coverage отдельные).

**Риск чистки ask:** низкий на поведении (уже drop), средний на формате JSON модели → нужен L67 после.  
**Риск трогать NEVER WRITE / placeholders:** высокий.

---

### 2.3 CLARIFY_SYS — снести (мёртвый)

Дословно:

```
The question can be answered from several kinds of records, and the
answers would differ. Ask the person ONE short question…
Never show table names, codes or internal identifiers.
```

**История:** `dba951d` (27.07, золото 8/8) → вызовы сняты `178ce51` (18.08): `clarify_text` → `format_clarify_options` / `clarify_say` (нумерованные строки из данных). Подписи меню с 14aec85 — wiki-captions **без LLM**. Константа и функция остались; в `OUR_PROMPTS` всё ещё числятся.

**Вердикт:** снести константу + `clarify_text` (или оставить функцию мёртвой до пакета чистки) и убрать из `OUR_PROMPTS`. Это не «наощупь» — callers=0 уже месяц+.

**Риск:** низкий (нет вызовов); проверить, что тесты не импортируют ожидаемый вызов модели для clarify prose.

---

### 2.4 REFUSE_SYS — оставить

Дословно короткая роль: одна фраза «verified answer cannot be given», без фактов/цифр.  
Цифры режет код. Живые вызовы на обоих трактах. Появился с языковой нейтрализацией отказов (`b2f8485` линия); стабилен с нарезки 8d5f51c.

**Вердикт:** не трогать. Риск правки — средний (отказы на приёмке видны клиенту).

---

### 2.5 AXIS_PICK_SYS — оставить ядро; «several» — спорный хвост под меню

Дословно:

```
One number when one axis fits the question clearly.
Several numbers when different axes would answer different readings of the same
question (at most three).
Empty list when no axis fits.
```

**История:** введён с rank-треком (`6ef0bca` / нарезка); код `rank_axis_resolve` после В3 при ≥2 правдоподобных осях ведёт в **меню**, не в молчаливый лидер. Промпт по-прежнему просит несколько индексов — это согласовано с меню, не с «выбери одну».

**Вердикт:** не трогать без замера rank/L67. Узкая чистка формулировки «several» возможна только если продукт решит «модель всегда одно число, меню строит только код» — сейчас код уже умеет меню из списка; правка промпта без замера — риск регрессии осей.

---

### 2.6 WIKI_PICK_SYS — оставить; поле separable — полумёртвое

Дословно schema:

```
{"choice": <1-based card index or 0>, "separable": <true|false>}
```

`ec579bf` (29.08) с замками; тесты `test_wiki_card_hybrid` мокают оба поля.  
Код: `separable = bool(model) and k_sep` — модель **не может** ослабить kNN-gap, только ужесточить. Итог clarify при неразделимости в основном от **кода** (gap) + verify-порога.

**Вердикт:** оставить. Чистка `separable` из schema — только с замком hybrid + L-прогоном: тесты и ветка clarify завязаны на поле.

---

### 2.7 WIKI_VERIFY_SYS — оставить; why — декоратив; порог — в коде

Текст:
- база `1404c34` (31.08, замки verify);
- добавка doesNotAnswer: `324641c` (01.09, живой SQL + замки) — дословно:

```
doesNotAnswer lists topics marked outside entity coverage.
```

Порог лидера «ровно один yes, остальные no» — **код** `wiki_outcome_from_verify` (14aec85 В4, замок verify_threshold), не строка промпта. Промпт лишь просит fit ∈ yes|no|unsure.

Поле `why`: парсится (`[:200]`), в ветвлении исхода **не используется** — диагностический хвост.

**Вердикт:** не трогать schema fit/index/doesNotAnswer (измеренные). Кандидат низкой ценности: убрать требование `why` — экономия токенов, риск только на salvage/parse; без замера не обязателен.

---

### 2.8 COVERAGE_SYS — оставить

Дословный перенос в новый z20: `5beb605` (люк check-prompt-rules: поведение не меняется).  
Claims **используются** (`check_claims` + числовой `gate`) — в отличие от ANSWER.  
Промпт велит копировать цифры census — согласовано с гейтом (история F128 в комментарии).

**Вердикт:** не трогать.

---

### 2.9 ARBITRATE inline — снести

Дословно роль «Choose the ONE answer… Reply with a single digit».  
Замысел владельца 30.07 (`d46079e`); вызов снят пакетом В4 `14aec85` («снос арбитра…», L67 22/41/4/0 vs якорь). Функция и system-строка остались.

**Вердикт:** снести `arbitrate` + sys_msg (мёртвый код под снесённый fork/арбитр). Риск: низкий при grep=0 callers.

---

### 2.10 Связанные снесённые механизмы (без отдельных промптов)

| Механизм | След в промптах |
|---|---|
| **ask_back** | живой текст в ANSWER_SYS + парсер `_ask_back`; runtime drop |
| **fork-авто / арбитр** | ARBITRATE мёртв; fork-меню без LLM |
| **verify-порог** | только код; промпт не описывает «ровно один yes» |
| **entity_form** | промптов нет |
| **clarify LLM** | CLARIFY_SYS мёртв; заменён `clarify_say` + wiki captions |

---

## 3. Итог

### 3.1 Кандидаты на правку

| Промпт | Строки / фрагмент | Действие | Риск для живых ответов |
|---|---|---|---|
| **ANSWER_SYS** | schema `"ask"` + абзац «middle road…» (z18:59–69, 88) | **чистить** — ask_back снесён, в live drop | низкий на цифрах; средний на JSON-форме → **только с L67** |
| **ANSWER_SYS** | `"claims": …` + «leave every role null» | **чистить осторожно** (совместимость `_split_answer`; COVERAGE claims не трогать) | средний без замера гейта/compose |
| **CLARIFY_SYS** + `clarify_text` | z07:285–311 | **снести**; убрать из `OUR_PROMPTS` | низкий (0 вызовов) |
| **ARBITRATE** | z01:602–628 | **снести** функцию+inline system | низкий (0 вызовов с 14aec85) |
| **OUR_PROMPTS** | z20(+legacy): список | добавить **WIKI_*** в leak-список *или* оставить как долг (не правка текста промпта) | низкий; улучшает п.13 leak |
| **WIKI_VERIFY** | поле `why` | опционально урезать | низкий/средний на parse; **не приоритет** |
| **WIKI_PICK** | `separable` | не чистить без hybrid-замка | средний |
| **AXIS_PICK** | «Several numbers…» | не чистить без решения «один индекс всегда» + rank-замер | средний |

### 3.2 Не трогать

| Промпт | Почему |
|---|---|
| **INTENT_SYS** (включая search_form, action_*, about) | приёмка intent 162/0; search_form с замером 708e6a7; samples/нормализация кодом |
| **ANSWER_SYS** placeholders / NEVER WRITE / язык / no invent | калькулятор + `[замер 04.08]`; compose 92/0; L67 на legacy |
| **REFUSE_SYS** | короткая роль; цифры режет код; живые отказы |
| **COVERAGE_SYS** | дословный перенос; claims+gate работают |
| **WIKI_VERIFY_SYS** fit/index/doesNotAnswer | цепочка классов 4–9 + В4 порог в коде; verify-замки |
| **WIKI_PICK_SYS** choice-схема | hybrid/pick замки и тесты |
| **AXIS_PICK_SYS** индексная schema | rank-меню завязано на список осей |

### 3.3 Одна фраза линзы

Промпты, пережившие приёмку (INTENT, compose-ядро, REFUSE, COVERAGE, wiki fit/pick), трогать нельзя; главный долг истории — **висячий ask_back внутри ANSWER_SYS** и два **мёртвых** вызова модели (**CLARIFY_SYS**, **ARBITRATE**), оставшиеся после сноса clarify-LLM и арбитра без удаления system-текста.
