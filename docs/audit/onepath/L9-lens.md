# L9 — независимая линза: полный аудит промптов тракта ask

**Дата:** 12.09.2026  
**Метод:** статический разбор исходников `ubuntu/serenedb/ask/*.py` (grep → чтение каждого
промпта и вызова → разбор полей ответа кодом). Чужие отчёты `docs/audit/onepath/*` не
читались. Модель и БД не вызывались. Код не менялся.

**Аспект:** качество / лишнее / недостающее / опасное по всему набору; ранжирование по
тяжести относительно TARGET п.12/19/21 и правила 03.08 (запреты — кодом, не промтом).

---

## 0. Метод реестра (независимый)

Поиск по `ubuntu/serenedb/ask/`:

1. константы `*_SYS` / `*_PROMPT` / `*_HINT`;
2. литералы `role: system` / `ds_chat(`;
3. inline `sys_msg` в `arbitrate`;
4. потребители `parse_intent` / `compose` / `refuse_text` / `clarify_text` /
   `rank_axis_pick` / `wiki_*` / `_coverage_answer`.

Не-промптовые вызовы моделей (вне реестра system-промптов, но учтены как соседний
контур): `rerank()` (внешний `/v1/rerank`), `embed_one` (эмбеддер). Текста system у них
нет.

---

## 1. Реестр промптов

Длины — символы тела литерала (без кавычек). «Тракт»: **legacy** =
`z20_ask_main_http_legacy.py` (живой до flip); **новый** = `z20_ask_main_http.py`
(скелет B3, SQL-заглушка). Зоны z01–z22 общие.

| Имя | файл:строка | длина | Вызовы | жив/мёртв | Тракт | Поля ответа, читаемые кодом |
|---|---|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3239 | `parse_intent` → `_one_intent` (`z02:566+`); до `INTENT_SAMPLES` (умолч. 5) прогонов + retry JSON | **жив** | оба (`answer` зовёт `parse_intent`) | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` (+ нормализация/`lost`/`assumed`/`unstable` в коде) |
| `ARBITRATE` (inline `sys_msg`) | `z01_infra_trace_llm.py:607` | 391 | `arbitrate()` | **мёртв** | — | только цифры → индекс ответа; иначе `None`. **Вызовов `arbitrate(` в ask/ нет** |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 | `rank_axis_pick` ← `rank_axis_resolve` | **жив** (legacy rank/SQL; в новом `answer` SQL ещё stub — путь rank не доезжает) | legacy (+ код общего ранга) | `{"axes":[N…]}` → индексы 1-based → `col`; fallback — все цифры из текста |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 247 | `wiki_pick_from_cards` | **жив** | оба (wiki-каскад) | `choice` (int), `separable` (bool ∧ knn-gap) |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 443 | `wiki_verify_candidates` | **жив** | оба | `verdicts[]`: `index`, `fit`∈{yes,no,unsure}; `why` парсится/режется, **на исход не влияет** (только `fit`) |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 | `clarify_text` | **мёртв** | — | сырая строка. **Вызовов `clarify_text(` в ask/ нет**; живое меню — `clarify_say` / `format_clarify_options` **без модели** |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 282 | `refuse_text` ← z20×оба, z21, z13, z04, coverage fallback | **жив** | оба | вся строка; если `_norm_numbers(t)` находит цифры → `""` (цифры режет код) |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 | `compose` ← только legacy `answer` (2 попытки) | **жив в legacy**; в новом `answer` **ещё не зовётся** (stub B4) | legacy | `_split_answer` → `text`; `_ask_back` → `ask` (см. §2.1 — далее **всегда сбрасывается**); `claims` игнорируются промтом и гейтом ролей |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` и `_legacy.py:742` (дубль) | 891×2 | `_coverage_answer` | **жив** | оба (после wiki при `about=coverage`) | `_split_answer` → `text` + `claims`; сверка `check_claims` + `gate(text)` + `prompt_leak` |

### Сопутствующие «промптоподобные» куски (не `*_SYS`, но уходят в user к модели)

| Место | Что | Кто читает ответ |
|---|---|---|
| `compose` user-body (`z18:719–875`) | `COMPUTED`/`GROUPS`/`PAIRS` плейсхолдеры; блоки `DATA INCOMPLETE` / `QUANTITY USED` / `GROUPS EXCLUDED` / `PREVIOUS ANSWER REJECTED` с формулировками MUST | тот же `compose` → гейт |
| `parse_intent` user | `today=…\n\nQuestion: …` | нормализатор intent |
| `wiki_format_card_lines` / `wiki_format_passport_lines` | name, description/wiki, **platform**, **axes**, **measures**, distinct, doesNotAnswer | pick/verify парсеры |
| `rank_axis_label_rows` | метка + при наличии target **имя колонки в скобках** | axis-pick / rerank docs |
| `_coverage_answer` user | census-строки с entity/причинами | `_split_answer` + gate |

### `OUR_PROMPTS` (детектор утечки)

Оба z20: `[INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS]`.

**Нет в списке:** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, inline ARBITRATE. Утечка wiki-инструкции
`prompt_leak` не поймает.

### Бюджеты вызова (справка)

| Вызов | max_tokens (умолч.) |
|---|---|
| intent | `ASK_INTENT_MAX_TOKENS`=400 × до 5 семплов + 1 retry |
| axis-pick | 80 |
| wiki-pick | 120 |
| wiki-verify | `WIKI_VERIFY_MAX_TOKENS`=2048 |
| clarify (мёртв) | 120 |
| refuse | 60 |
| compose | 800 |
| coverage | 900 (дефолт `ds_chat`) |
| arbitrate (мёртв) | 8 |

---

## 2. Анализ по аспекту (все промпты)

### 2.1 `ANSWER_SYS` — тяжесть **высокая** (контракт «один путь» + мёртвое поле)

Дословно:

```
"ask": "one clarifying question, or null",
…
"ask" is the middle road between answering and giving up. Fill it ONLY when …
```

и

```
🔴 NEVER WRITE A COMPUTED FIGURE YOURSELF. …
"claims" — leave every role null. It exists only for compatibility and is ignored.
```

**Факт кода (legacy):** после разбора `_ask_back(raw)` стоит безусловный сброс:

```
if ask_back:
    diag["ask_back_dropped"] = "bare_clarify_forbidden"
    ask_back = ""
```

Поле `ask` модель всё ещё учит заполнять; код всегда выбрасывает. Это (а) расход
токенов и внимания модели, (б) прямое противоречие приказу «меню единым
построителем ДО SQL; модельных ask_back в новом тракте нет», (в) нарушение духа
03.08 — запрет «не пиши числа» живёт словами в промте, а держится плейсхолдерами +
гейтом (что правильно), но промт раздут запретами.

**Вердикт:** чистить. Снести блок про `"ask"` и абзац middle-road; оставить формат
`{text, claims}` или сузить до `{text}` если код готов. Риск: **средний** на legacy
(приёмка могла косвенно опираться на то, что модель «думает» об ask) → нужен прогон
после правки. Для нового тракта — **обязательный** выкид до включения compose.

---

### 2.2 `CLARIFY_SYS` + `clarify_text` — тяжесть **средняя** (мёртвый контур)

Дословно:

```
Ask the person ONE short question…
Never show table names, codes or internal identifiers.
```

Живое уточнение — `clarify_say` / `format_clarify_options` (нумерованные строки из
данных, без LLM). `CLARIFY_SYS` всё ещё в `OUR_PROMPTS`.

**Вердикт:** снести промт + функцию после подтверждения тестами; убрать из
`OUR_PROMPTS`. Риск: **низкий** (нет вызовов).

---

### 2.3 `ARBITRATE` inline — тяжесть **низкая/средняя** (мёртвый)

Дословно: «Choose the ONE answer… Reply with a single digit». Защита номером — хорошая
(текст не уходит клиенту). Вызовов нет.

**Вердикт:** снести или оставить за флагом только если fork-outcomes снова понадобится.
Риск удаления: **низкий**.

---

### 2.4 Wiki-промпты — тяжесть **высокая** (п.19 + утечка) / качество **хорошее**

`WIKI_PICK_SYS` (короткий, форматный) — образец «формат и роль, не запреты».

`WIKI_VERIFY_SYS` — тоже формат; просит `why`, но исход смотрит только `fit`.
Дословно: `"why": <one line>` — лишний объём при `max_tokens=2048` и риске
обрезания JSON (есть salvage — хорошо).

**User-payload опасность (п.19):**

```
axes: … measures: …
```

и в axis-pick метки вида `«человеческое» (имя_колонки)`. Это не полная схема БД, но
это **имена осей/мер/колонок** в модель. Контракт: «схема базы/колонки в модель не
отправляются». Wiki-меню для человека строится из name/description (правильно);
модели же отдаётся богаче.

**Вердикт:**

- pick/verify system — **оставить** (с лёгкой чисткой `why` → опционально убрать из
  схемы ответа; риск **низкий/средний**, нужен замер wiki-каскада);
- **добавить** оба в `OUR_PROMPTS` (риск **низкий**);
- сократить user-карточки: для pick достаточно name+description+platform; axes/measures
  — только в verify или только `distinct`. Риск **высокий** без замера (различимость
  сущностей).

---

### 2.5 `INTENT_SYS` — тяжесть **средняя** (объём + рассинхрон схемы)

Плюсы: язык-нейтрален; чёткий JSON; код нормализует типы (комментарии в z01/z02
честно описывают, почему нельзя верить промту).

Минусы:

1. Блок `Rules:` — длинные запреты («NEVER put the KIND…») — дух 03.08; часть уже
   дублируется нормализатором.
2. Схема `amount.op` **без `"="`**, а код `_AMOUNT_ops` принимает `"="` (замер 04.08 в
   комментарии). Модель иногда шлёт `=`; код чинит — ок, но схема врёт модели.
3. 3239 символов × до 5 семплов — главный расход токенов тракта; оправдан замерами
   согласия — **не трогать без нового бенча**.

**Вердикт:** оставить ядро; точечно добавить `"="` в перечень op (риск **низкий**);
крупную чистку Rules — только с `intent_parse_bench` / приёмкой (риск **высокий**).

---

### 2.6 `AXIS_PICK_SYS` — тяжесть **средняя**

Короткий, форматный — хорошо. User получает колонки в скобках (`rank_axis_label_rows`)
— снова п.19. В новом тракте rank пока не доезжает до ответа.

**Вердикт:** оставить SYS; при этапе SQL «одного пути» — не слать сырой `col` в label
(риск **средний**, нужен замер rank-меню).

---

### 2.7 `REFUSE_SYS` — тяжесть **низкая**

Коротко, роль ясна; цифры режет код. Нужен для мультиязычности отказа.

**Вердикт:** **не трогать**.

---

### 2.8 `COVERAGE_SYS` — тяжесть **средняя**

Просит писать цифры в текст и заполнять `claims` — противоположная философия
`ANSWER_SYS` (плейсхолдеры). Держится `gate` + `check_claims` — правильно по коду,
но две школы в одном тракте.

Комментарий в `_coverage_answer` («промт велит оставлять claims пустыми») **врёт**:
это про ANSWER, не COVERAGE. Документ/комментарий отстаёт.

Дубль константы в новом и legacy z20 — риск рассинхрона правок.

**Вердикт:** оставить поведение; вынести одну константу в общий модуль при рефакторе
(риск **низкий**); не убирать цифры из coverage без замены на плейсхолдеры+подстановку
(риск **высокий**).

---

### 2.9 User-добавки `compose` (MUST / warn)

Дословно фрагменты:

```
You MUST warn the user about this…
You MUST say this in your answer…
```

Правила в user-сообщении. Защита — гейт и плейсхолдеры `{missing}`/`{folders}`. Для
нового тракта лучше: код дописывает оговорку после модели (на языке? — проблема п.9)
или оставляет MUST до замены механизмом.

**Вердикт:** не трогать в legacy без замера; в дизайне «одного пути» — перенос
оговорок в код/шаблон после ответа.

---

### 2.10 Сводка качества (ранг проблем)

| # | Проблема | Тяжесть |
|---|---|---|
| 1 | `ANSWER_SYS.ask` жив в промте, мёртв в коде; конфликт с «одним путём» | **P0** |
| 2 | Wiki/axis user несут axes/measures/col → модель (п.19) | **P1** |
| 3 | `WIKI_*` нет в `OUR_PROMPTS` | **P1** |
| 4 | `CLARIFY_SYS` / `arbitrate` мёртвы, но занимают поверхность | **P2** |
| 5 | `INTENT` схема без `=`; раздутые Rules | **P2** |
| 6 | `WIKI_VERIFY.why` не влияет на исход | **P2** |
| 7 | Две школы чисел: ANSWER=плейсхолдеры vs COVERAGE=цифры | **P2** |
| 8 | MUST в user-compose | **P3** |
| 9 | Дубль `COVERAGE_SYS` в двух z20 | **P3** |

---

## 3. Вердикт по каждому промпту

| Промпт | Вердикт | Риск правки для живых ответов |
|---|---|---|
| `INTENT_SYS` | оставить; точечно `"="` в op | низкий (`=`); высокий — массовая чистка Rules |
| `ARBITRATE` | снести (нет вызовов) | низкий |
| `AXIS_PICK_SYS` | оставить SYS; чистить user labels (col) отдельно | средний |
| `WIKI_PICK_SYS` | оставить; в `OUR_PROMPTS`; ужать card fields осторожно | средний/высокий на fields |
| `WIKI_VERIFY_SYS` | оставить; убрать/ослабить `why`; в `OUR_PROMPTS` | низкий/средний |
| `CLARIFY_SYS` | снести (+ `clarify_text`, из `OUR_PROMPTS`) | низкий |
| `REFUSE_SYS` | **не трогать** | — |
| `ANSWER_SYS` | чистить: снести `ask`-блок; NEVER-абзац не раздувать дальше | средний (legacy compose) |
| `COVERAGE_SYS` | оставить; один экземпляр; поправить вводящий комментарий | низкий |

---

## 4. Итог: правки-кандидаты

| Промпт | Строка / место | Действие | Риск |
|---|---|---|---|
| `ANSWER_SYS` | `z18:59–69` (`"ask"` + middle-road) | **снести** из схемы и текста; перестать парсить ask_back или оставить парсер мёртвым явно | средний (legacy) / обязателен до compose в новом |
| `ANSWER_SYS` | `z18:71–73` NEVER WRITE… | не усиливать; при рефакторе «одного пути» опереться только на плейсхолдеры+gate | высокий, если выкинуть без замера |
| `CLARIFY_SYS` | `z07:285–292` + `clarify_text` | **снести**; убрать из `OUR_PROMPTS` | низкий |
| `ARBITRATE` | `z01:607–613` + `arbitrate` | **снести** или архив за флагом | низкий |
| `OUR_PROMPTS` | оба z20 `:755`/`:761` | **добавить** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`; убрать мёртвые | низкий |
| `WIKI_VERIFY_SYS` | `z21:55–56` поле `why` | убрать из контракта ответа или сделать необязательным | низкий/средний |
| `wiki_format_*` | `z21:365–375`, `536–556` | кандидат: не слать полный axes/measures в pick | **высокий** без wiki-замера |
| `rank_axis_label_rows` | `z10:170–171` | кандидат: не добавлять `(col)` в label модели | средний |
| `INTENT_SYS` | `z01:805` amount.op | добавить `"="` в перечень | низкий |
| `COVERAGE_SYS` | дубль z20/legacy | вынести в один модуль | низкий |
| комментарий coverage | `z20*:804–807` | поправить ложь про «пустые claims» | нулевой на ответы |

---

## 5. Список «не трогать»

| Что | Почему |
|---|---|
| `REFUSE_SYS` + цифровой фильтр в `refuse_text` | Короткий; язык вопроса; запрет цифр кодом |
| Ядро `INTENT_SYS` (поля JSON, want/kind/about/action_*) | Держит весь тракт; согласие семплов замерялось |
| Механика плейсхолдеров в `compose` user (`{total}`, `{count}`, pairs) | Числа вне модели — inv. п.19; замена словами — регрессия |
| `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` как короткие format-only system | Соответствуют правилу 03.08 лучше остальных |
| `AXIS_PICK_SYS` (system-текст) | Уже формат indices; не раздувать |
| `temperature=0` + memo intent | Детерминизм п.3; не ослаблять |
| Живой `clarify_say` (не промт) | Единый построитель меню без модели — канон «одного пути» |
| Гейты `gate` / `prompt_leak` / `_norm_numbers` на refuse | Защита не промтом |

---

## 6. Карта «какой промпт в каком тракте сейчас»

```
вопрос
  ├─ INTENT_SYS          [оба]
  ├─ readings (без LLM)
  ├─ WIKI_PICK / VERIFY  [оба]
  ├─ меню clarify_say    [без LLM; оба]
  ├─ about=coverage → COVERAGE_SYS [оба]
  ├─ legacy only:
  │     AXIS_PICK / rerank / SQL / ANSWER_SYS(+мёртвый ask)
  │     REFUSE_SYS при отказах
  └─ новый answer:
        SQL stub B4 → ANSWER_SYS ещё не подключён
```

---

## 7. Заключение линзы

Набор живых system-промптов **небольшой** (6 живых + 2 мёртвых + 1 inline мёртвый).
Главный дефект качества — не «плохие формулировки wiki», а **наслоение устаревших
ролей**: `ask` в ANSWER, `CLARIFY_SYS`, `arbitrate` — при том что меню и отказы уже
сделаны кодом. Второй дефект — **п.19 на user-payload** (оси/меры/колонки), при
аккуратных system-текстах wiki. Третий — **дыра `OUR_PROMPTS`** без wiki.

Рекомендуемый порядок правок (когда разрешат код): (1) снести ask из ANSWER + мёртвые
CLARIFY/arbitrate + wiki в OUR_PROMPTS; (2) `=` в INTENT; (3) только с замером —
ужать wiki/axis payload и NEVER-простыни ANSWER.

Конец отчёта L9.
