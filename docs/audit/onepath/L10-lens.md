# L10 — независимая линза: полный аудит промптов тракта ask

**Дата:** 12.09.2026  
**Метод:** свой grep-реестр по `/srv/1c/ubuntu/serenedb/ask/*.py` → чтение каждого
system/user вызова → оценка качества / лишнего / недостающего / опасного →
ранжирование по тяжести. Чужие отчёты `docs/audit/onepath/*` не читались.  
**Ограничение:** только чтение исходников; код не менялся; модель не звалась.

---

## 0. Метод поиска (реестр независимый)

Искал:

1. Константы `*_SYS` / `*_PROMPT` / `*_HINT`.
2. Литералы `role: system` / `system=` / inline `sys_msg`.
3. Все вызовы `ds_chat(` и их обёртки (`parse_intent`, `compose`, `clarify_text`,
   `refuse_text`, `arbitrate`, `rank_axis_pick`, `wiki_*`, `_coverage_answer`).
4. Потребителей обёрток по зонам (кто реально зовёт).

**Найдено system-промптов: 9** (8 именованных + 1 inline у арбитра).  
**`*_HINT` / `*_PROMPT` как LLM-констант: 0** (`hint` в clarify — поле данных меню, не промпт).  
**Доп. user-фраза без system:** `"Return the JSON object."` (retry в `z02`).

---

## 1. Реестр промптов

| Имя | файл:строка | длина (симв.) | Вызовы | Тракт | жив/мёртв | Поля ответа, читаемые кодом |
|---|---|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3227 | `parse_intent` ← z20 new + legacy | оба | **жив** | JSON: `terms`, `amount{op,value,value2}`, `period{from,to}`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` (+ код принимает `period2`, нормализует типы) |
| `ARBITRATE` (inline `sys_msg`) | `z01_infra_trace_llm.py:607` | 391 | `arbitrate()` — **вызовов в ask/ нет** | — | **мёртв** | одна цифра → индекс ответа; иначе `None` |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 | только внутри `clarify_text`; **вызовов `clarify_text(` в ask/ нет** | — | **мёртв** | весь текст ответа (строка уточнения) |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 282 | `refuse_text` ← z20 new/legacy, z21, z13, z04 | оба | **жив** | весь текст; код режет, если есть цифры (`_norm_numbers`) |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 | `rank_axis_pick` ← `rank_axis_resolve` ← **только legacy** `z20_…_legacy.py:3609` | legacy | **жив (legacy)** | JSON `axes: [1-based…]` (до 3); fallback — любые цифры |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 | `compose` ← **только legacy** `:4109`, `:4186` | legacy | **жив (legacy)** | JSON `text`, `ask` (через `_ask_back`), `claims` (игнор по промту; гейт на числах текста) |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` **и** `…_legacy.py:742` (бит-идентичны) | 891×2 | `_coverage_answer` ← оба z20 | оба | **жив** | `text` + `claims` (`_split_answer` + `check_claims` + `gate`) |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 247 | `wiki_pick_from_cards` ← каскад при `len(cards)>1` | оба | **жив** | `choice` (int), `separable` (bool; AND с kNN gap) |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 443 | `wiki_verify_candidates` ← каскад (всегда при непустом пуле) | оба | **жив** | `verdicts[{index, fit, why}]`; `fit` ∈ yes/no/unsure (+ RU-синонимы в коде) |
| *(retry user)* | `z02_intent.py:576` | 24 | при сбое разбора intent | оба | **жив** | тот же JSON intent |

### 1.1. Транспорт модели

| Функция | файл | роль |
|---|---|---|
| `ds_chat` / `ds_chat_post` | `z01:564–579` | единственный chat-API DeepSeek |
| `embed_one` / `rerank` | `z01` / `z07` | **не** chat-промпты (вектор / реранкер) |

### 1.2. Что уходит в user рядом с каждым промптом

| Промпт | User-часть |
|---|---|
| INTENT | `today=YYYY-MM-DD\n\nQuestion: …` |
| INTENT retry | прежний assistant-срез ≤400 + `Return the JSON object.` |
| AXIS | вопрос `(+ kind)` + нумерованный список меток осей |
| CLARIFY *(мёртв)* | `Question` + `Options: - label (typical: …)` |
| REFUSE | сырой вопрос |
| ANSWER | `QUESTION` + ROWS/GROUPS + слоты COMPUTED/PAIRS + опц. coverage/folders/corrections |
| COVERAGE | вопрос + перепись (`rows in source…`, потерянные entity) |
| WIKI_PICK | вопрос `(+ kind)` + карточки: name/description/platform/axes/measures |
| WIKI_VERIFY | вопрос `(+ kind)` + паспорта до `WIKI_PASSPORT_N`×`BODY_MAX` (умолч. 8×1500) |
| ARBITRATE *(мёртв)* | опц. context≤2000 + Question + Answers `1)…` |

### 1.3. Карта «один путь» (новый `z20_ask_main_http.py`) vs legacy

| Шаг нового тракта | Модельные промпты |
|---|---|
| intent | INTENT ✓ |
| wiki-каскад | WIKI_PICK + WIKI_VERIFY ✓ |
| меню прочтений | **без модели** (`clarify_say` / `format_clarify_options`) |
| coverage | COVERAGE ✓ (после wiki) |
| SQL / ответ числом | **заглушка B4** — `ANSWER_SYS` / `compose` **не подключены** |
| отказ | REFUSE ✓ |

Legacy дополнительно: AXIS_PICK, ANSWER (`compose` + мёртвый на практике `ask_back`).

### 1.4. `OUR_PROMPTS` / `prompt_leak`

Список (`z20` new+legacy `:755`/`:761`):  
`INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS`.

**Нет в списке:** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, ARBITRATE.  
**Есть мёртвый:** `CLARIFY_SYS`.  
Утечка ловится точным совпадением строки ≥40 символов (`z19:205`).

---

## 2. Анализ по аспекту (полный, без узкой специализации)

Критерии: соответствие TARGET (п.12/19/21), правилу 03.08 (формат/роль, не запреты в промте),
контракту «один путь», живости, риску регрессии приёмки.

### 2.1. Тяжесть (ранг)

#### T1 — высокий: расхождение контракта ответа с живым кодом (`ANSWER_SYS.ask`)

Дословно в `ANSWER_SYS`:

> `"ask": "one clarifying question, or null"`  
> `"ask" is the middle road between answering and giving up…`

В legacy после compose:

- `_ask_back` читает `ask`;
- затем **всегда** сбрасывается: `diag["ask_back_dropped"] = "bare_clarify_forbidden"`  
  (`z20_…_legacy.py:4325–4327`).

Итог: модель тратит токены на поле, которое код **запрещает** выпускать; контракт
«меню ДО SQL / без ask_back в новом тракте» уже держится кодом, а промпт всё ещё учит
другому. Для волны B4 (подключение compose) это прямой источник регрессии, если кто-то
ослабит сброс.

**Вердикт:** чистить (убрать поле `ask` и абзацы про middle road) **перед** подключением
compose к новому тракту.  
**Риск правки для живых ответов:** средний на legacy (модель может чуть иначе заполнять
`text`); низкий, если оставить сброс `ask_back` до замера. Без замера на приёмке —
не выкатывать.

#### T2 — высокий: `OUR_PROMPTS` не покрывает живые wiki-промпты

`WIKI_*` — самые частые LLM-шаги выбора сущности; их длинные строки **не** в
`prompt_leak`. CLARIFY (мёртвый) в списке есть.

**Вердикт:** чистить список (добавить WIKI_*, убрать или оставить CLARIFY осознанно).  
**Риск:** низкий (только гейт утечки; false-positive маловероятен при `min_len=40`).

#### T3 — высокий: `INTENT_SYS` — раздутый «Rules:» блок (формат + политика в одном)

Дословно начинается нормально (`Convert… Reply with JSON only`), затем ~15 строк
долженствований:

> `- Never invent concepts that are not in the question.`  
> `- "terms" holds only VALUES… NEVER put the KIND…`

Это одновременно: (а) нужная семантика полей JSON, (б) запреты в духе правила 03.08.
Код уже нормализует типы/lost/assumed (`z01` комментарий + `z02._normalize_intent`) —
то есть защита не в промте. Промпт при этом:

- самый длинный (3227);
- **не согласован со схемой кода по `amount.op`:** в промте нет `"="`, в `_AMOUNT_OPS`
  есть `"="` (замер 04.08 про нулевые документы). Модель может избегать `=` или
  класть равенство в `terms`.

**Вердикт:** чистить точечно: (1) добавить `"="` в схему JSON; (2) не резать семантику
полей без замера `INTENT_SAMPLES`; массовое урезание Rules — только после бенча.  
**Риск:** высокий при агрессивной чистке (разброс kind/terms уже измерялся 18/58).

#### T4 — средний: `ANSWER_SYS` держит запрет цифр словами + 🔴 в тексте

Дословно:

> `🔴 NEVER WRITE A COMPUTED FIGURE YOURSELF…`

Комментарий в `copied_figures` прямо говорит: промт срабатывает «почти», защищает гейт.
Правило 03.08 формально нарушено, но гейт/подстановка уже есть. Эмодзи в system —
шум для модели.

**Вердикт:** оставить смысл (плейсхолдеры) как описание формата; формулировки-запреты
можно смягчить до «use only placeholders listed below» **после** замера step6.  
**Риск:** высокий без замера (известен класс F285).

#### T5 — средний: `COVERAGE_SYS` требует цифры в тексте (противоположность ANSWER)

Дословно:

> `State figures in DIGITS, copied from the census — never recompute`  
> `Put the number of missing rows in "claims.total"…`

Гейт + `check_claims` закрывают выдумку. Для coverage это осознанный путь
(перепись короткая). Дубль константы в new+legacy — риск рассинхрона.

**Вердикт:** оставить поведение; свести к одной константе при рефакторе.  
**Риск слияния:** низкий (сейчас identical).

#### T6 — средний: мёртвые `CLARIFY_SYS` и ARBITRATE

Меню живое через `clarify_say` (код, без LLM) — верно для «один путь».  
`CLARIFY_SYS` всё ещё в `OUR_PROMPTS`.  
`arbitrate` — промпт + функция без вызовов (fork outcomes вытеснили).

**Вердикт:** снести вызовы/константы после подтверждения тестами «0 вызовов»; либо
пометить DEPRECATED. Не возвращать model-clarify в новый тракт.  
**Риск:** низкий.

#### T7 — средний: объём user у `WIKI_VERIFY`

Умолч. до ~8×1500 символов wiki + axes/measures/distinct. Ограничено env, не растёт
с размером базы линейно (пул фиксирован) — п.19 формально ок. Но при длинных
паспортах растёт латентность/обрезка (`max_tokens=2048`, salvage-парсер).

**Вердикт:** оставить; не раздувать `WIKI_PASSPORT_*` без замера.  
**Риск увеличения:** средний (уже был кейс truncation → salvage).

#### T8 — низкий/средний: wiki показывает `platform` / `axes` / `measures` модели

Это не «схема колонок SQL», а вики-карточки. Меню человеку строится отдельно
(`wiki_menu_captions` без имён метаданных в идеале). Риск: если caption упадёт на
сырой label с `src_table` — это уже код меню, не промпт.

Промпты pick/verify **короткие и форматные** — лучший образец в тракте.

**Вердикт:** оставить как есть.

#### T9 — низкий: `REFUSE_SYS` / `AXIS_PICK_SYS`

REFUSE: роль ясная; цифры режет код — хорошо.  
AXIS: формат JSON indices; жив только в legacy rank; в новом тракте ось/окно — меню
без модели (`readings_menu`). Для onepath AXIS может стать не нужен, если оси всегда
идут через readings_menu.

**Вердикт:** REFUSE — не трогать. AXIS — не трогать, пока legacy на проде; в B4 решить
единый путь осей.

#### T10 — наблюдение для B4: новый тракт ещё без `ANSWER_SYS`

`answer()` нового z20 после wiki возвращает stub `unavailable` / «волна B4».  
Любая правка ANSWER сейчас бьёт **только legacy**. Планировать чистку `ask` до flip.

---

## 3. Вердикты по каждому промпту

| Промпт | Вердикт | Дословные строки / зачем | Риск правки |
|---|---|---|---|
| INTENT_SYS | **чистить точечно** | добавить `"="` в `"amount"."op"`; Rules не вырезать пакетом | высокий без бенча intent |
| ARBITRATE | **снести** (мёртв) | весь inline sys_msg | низкий |
| CLARIFY_SYS | **снести** (мёртв) + убрать из OUR_PROMPTS или оставить только как leak-якорь | «Ask the person ONE short question…» | низкий |
| REFUSE_SYS | **оставить** | «State no facts, no figures…» + код режет цифры | — |
| AXIS_PICK_SYS | **оставить** (legacy); в onepath — решить при B4 | `{"axes": [numbers]}` | средний, если менять индексы |
| ANSWER_SYS | **чистить** поле `ask` и middle-road; формат `{total}` оставить | строки 59–69 про `ask` | средний→высокий без step6 |
| COVERAGE_SYS | **оставить**; дедуп new/legacy | DIGITS + claims | низкий при merge |
| WIKI_PICK_SYS | **оставить** | `{"choice", "separable"}` | — |
| WIKI_VERIFY_SYS | **оставить** | `verdicts[{index,fit,why}]` | — |
| retry «Return the JSON object.» | **оставить** | узкий repair | — |

---

## 4. Итог

### 4.1. Кандидаты на правку

| # | Промпт | Строка (ориентир) | Действие | Риск для живых ответов |
|---|---|---|---|---|
| 1 | ANSWER_SYS | `z18:59–69` (`"ask"` / middle road) | Удалить поле и абзацы; JSON оставить `text`+`claims` | Средний на legacy; **сделать до B4-compose** |
| 2 | OUR_PROMPTS | `z20:755` / legacy `:761` | Добавить `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`; убрать мёртвый CLARIFY (или оставить с пометкой) | Низкий |
| 3 | INTENT_SYS | схема `amount.op` ~`:805` | Добавить `"="` в перечень | Низкий/средний (лучше с прогоном intent) |
| 4 | CLARIFY_SYS + `clarify_text` | `z07:285–311` | Снести мёртвый путь после теста «0 callers» | Низкий |
| 5 | ARBITRATE `sys_msg` + `arbitrate` | `z01:602–628` | Снести или вынести в архив; 0 callers | Низкий |
| 6 | COVERAGE_SYS | дубль z20/legacy | Одна константа (импорт) | Низкий |
| 7 | ANSWER_SYS | `z18:71–73` (NEVER WRITE / 🔴) | Смягчить до описания плейсхолдеров **после** замера | Высокий без замера — **не первым** |

### 4.2. Не трогать

- `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` (короткие, форматные, живые, парсер+salvage есть).
- `REFUSE_SYS` (роль + код против цифр).
- `AXIS_PICK_SYS` до решения по осям в onepath / пока legacy на проде.
- Семантику полей INTENT (`kind` vs `terms`, `about`, `action_*`) — без бенча.
- Механику плейсхолдеров `{total}` / gate / `copied_figures` — это защита чисел кодом.
- Живое меню `clarify_say` (не промпт) — соответствует «один путь».

### 4.3. Сводка по живости (ask/)

```
ЖИВЫ:     INTENT, REFUSE, WIKI_PICK, WIKI_VERIFY, COVERAGE
ЖИВЫ legacy-only: AXIS_PICK, ANSWER
МЁРТВЫ:   CLARIFY (clarify_text), ARBITRATE
НОВЫЙ z20 без compose: ANSWER пока не на пути answer()
```

### 4.4. Главный вывод линзы

Промпты **выбора** (wiki) и **отказа** в порядке: короткие, JSON/цифра, разбор кодом.  
Главный долг — **формулировка ответа** (`ANSWER_SYS`): устаревший контракт `ask` +
запреты в промте при уже существующем коде-гейте; плюс дыра `prompt_leak` вокруг wiki.  
Intent раздут, но «хирургия» опаснее точечного `"="`. Мёртвые CLARIFY/ARBITRATE —
безопасная уборка. Новый тракт ещё не дошёл до compose: чистку `ask` логично сделать
**до** волны B4, а не после flip.
