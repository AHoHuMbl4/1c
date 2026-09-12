# L1 — независимая линза: потребители и жизнь промптов ask

**Аспект:** кто вызывает каждый промт; legacy vs новый тракт; какие поля ответа модели
код реально читает; мёртвые промпты и поля, парсимые и выбрасываемые.

**Метод:** статический grep по `/srv/1c/ubuntu/serenedb/ask/*.py` (без worktrees);
чтение каждого system-промта и обвязки вызова/разбора. Модель не звалась; чужие
отчёты `docs/audit/onepath/*` не читались. Дата среза: 12.09.2026.

**Тракты:**
- **legacy** — `z20_ask_main_http_legacy.py` (полный `answer` до flip);
- **новый** — `z20_ask_main_http.py` (скелет «один путь»: intent → wiki → меню/coverage;
  SQL/compose — заглушка B4, `kind=unavailable`).

Единая точка вызова модели: `ds_chat` в `z01_infra_trace_llm.py`. Констант `*_HINT` /
`*_PROMPT` в ask/ **нет** (кроме `*_SYS` и inline `sys_msg` арбитра).

---

## 1. Реестр промптов

| имя | файл:строка | длина (симв.) | вызовы | тракт | жив/мёртв | поля ответа, читаемые кодом |
|---|---|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3239 | `parse_intent` → `_one_intent` → `ds_chat` (`z02:567`, retry `:575`); вход: оба `answer` | legacy + новый | **жив** | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form`. Нормализация `z02._normalize_intent`. `period2` в схеме промта **нет**, но в `_INTENT_FIELDS` есть (см. §2.1). |
| `ARBITRATE` (inline `sys_msg`) | `z01:607–613` в `arbitrate()` | 391 | **0 вызовов** `arbitrate(` в ask/ и в z20 | — | **мёртв целиком** | цифры ответа → индекс; потребителей нет. Тест `test_no_pre_wiki_reorders` требует 0 вызовов в z20. |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 | `rank_axis_pick` → `rank_axis_resolve`; вызов resolve только из **legacy** `z20_legacy:3609` | legacy | **жив (legacy)**; в новом до B4 **не зовётся** | JSON `axes: [1-based]` → список `col` (≤3). Иные поля не читаются. |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 | только внутри `clarify_text`; **0 вызовов** `clarify_text(` в ask/ | — | **мёртв целиком** | был бы сырой текст предложения; живое меню — `clarify_say` **без модели**. |
| `REFUSE_SYS` | `z07:317` | 282 | `refuse_text` → `ds_chat`; много call-sites (z20/legacy/z21/z13/z04) | legacy + новый | **жив** (условно) | весь текст; цифры вырезаются `_norm_numbers` → пустая строка. Часто путь `NO_DATA_TEXT or refuse_text` — при непустом `ASK_NO_DATA_TEXT` модель **не зовётся**. |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 | `compose` → `ds_chat`; только **legacy** `answer` (`:4109`, retry `:4186`) | legacy | **жив (legacy)**; новый — stub без compose | `text` (обязателен); `ask` парсится → **всегда сбрасывается**; `claims` парсятся → в answer-пути **не сверяются** (см. §2.4). |
| `COVERAGE_SYS` | `z20:736` и `z20_legacy:742` (дубль) | 891×2 | `_coverage_answer` при `about=coverage` | legacy + новый (после wiki) | **жив** | `text` + `claims` (`check_claims` + числовой `gate`). |
| `WIKI_PICK_SYS` | `z21:45` | 247 | `wiki_pick_from_cards` при `len(cards)≥2` | legacy + новый (wiki-каскад) | **полумёртв** | `choice` → индекс; `separable` ∧ knn-gap. При успешном verify исход **перезаписывается** verify (см. §2.6). |
| `WIKI_VERIFY_SYS` | `z21:50` | 443 | `wiki_verify_candidates` (всегда при непустом пуле) | legacy + новый | **жив** | `verdicts[].index`, `verdicts[].fit` (`yes\|no\|unsure`). `why` парсится и **нигде не читается**. |

### Не-промпты, но «жизнь текста» рядом

| механизм | где | модель? | роль |
|---|---|---|---|
| `clarify_say` / `format_clarify_options` | z20 / legacy / z21 | нет | живое меню уточнений |
| `rerank` | z07 | отдельный Rerank API | порядок осей/доков; не DeepSeek chat |
| `embed_one` | z01 | Embed API | wiki hybrid / поиск |
| `OUR_PROMPTS` | z20 / legacy | — | leak-детектор: INTENT, AXIS, CLARIFY, REFUSE, ANSWER, COVERAGE; **нет** WIKI_* и ARBITRATE |

---

## 2. Анализ по аспекту (потребители и жизнь)

### 2.1 `INTENT_SYS` — жив; почти все поля живые

**Вызов:** оба тракта в начале `answer` (`parse_intent`). User: `today=…\n\nQuestion: …`.
До `INTENT_SAMPLES` / отрыва `INTENT_LEAD` — несколько `ds_chat` на вопрос.

**Читает код (живо):**
- `terms`, `kind`, `measure`, `want`, `period`, `amount`, `about` → отбор, coverage-ветка, want/slot;
- `action_class`, `action_axis` → wiki / fork-логика;
- `search_form` → hybrid-пул (`z21:289`), fallback на сырой вопрос.

**Мёртвое / полумёртвое вокруг промта:**
- В схеме промта **нет** `period2`, но `_INTENT_FIELDS` и `_normalize_intent` его ждут.
  На практике `period2` в legacy ставит **код** (`sales_compare_windows` →
  `intent["period2"]=…`, `z20_legacy:3738`), не модель. Поле в merge-согласии —
  защита от выдумки, не контракт промта.
- `_first_intent_object` скорит блоки без `search_form` / `period2` — на отбор «лучшего»
  JSON влияет слабо (поле всё равно нормализуется, если есть).

**Вердикт:** оставить как есть для жизни тракта. Чистка схемы/Rules — только с
замером intent-bench; риск высокий (вход всего ответа).

---

### 2.2 `ARBITRATE` — мёртв целиком

Функция и inline-промт в `z01` живы как код, **потребителей нет** (grep `arbitrate(` —
только определение + тест «0 вызовов»). В legacy цикл арбитра снесён (комментарий
«В4: арбитр-цикл снесён», меню через `clarify_say`).

**Вердикт:** кандидат на снос функции+промта после подтверждения, что тесты/импорты
не держат имя. Риск для живых ответов: **низкий** (не зовётся). Не трогать в том же
коммите, что меняет ветвление сущностей.

---

### 2.3 `CLARIFY_SYS` / `clarify_text` — мёртв целиком

Живое уточнение: `clarify_say` собирает нумерованные строки из `label`/`hint` **без**
LLM. Комментарий в `_opt_values` ещё ссылается на `clarify_text` — устаревшая док-строка.

**Вердикт:** снести `CLARIFY_SYS` + `clarify_text` (и убрать из `OUR_PROMPTS`) — косметика
leak-списка. Риск: **низкий**. Не путать с `clarify_say` — его не трогать.

Дословно мёртвый контракт промта (больше не исполняется):

> «Ask the person ONE short question… Describe each option in plain business words…»

---

### 2.4 `ANSWER_SYS` — жив в legacy; поля `ask` и `claims` для ответа — мёртвы

**Вызов:** только legacy `compose`. Новый тракт до B4 compose не зовёт.

**Живое поле:**
- `text` → `_split_answer` → `_fill_figures` / gate / passport.

**Парсится и выбрасывается:**
1. **`ask`** — `_ask_back(raw)` → `_filled_ask` → затем безусловно:
   - `ask_back_dropped = bare_clarify_forbidden` (`z20_legacy:4325–4327`);
   - ранее ещё `canon_locked`.
   Клиенту модельный ask_back **не уходит**. Промт всё ещё требует заполнять `ask`
   (строки 62–69 ANSWER_SYS) — модель тратит токены на мёртвое поле; код держит
  запрет (контракт «одного пути»: меню до SQL, не ask_back после ответа).

2. **`claims`** — `_split_answer` возвращает dict; в answer-пути комментарий явно:
   проверка через claims **убрана** (`z20_legacy:4157–4160`); смысл держит
   `asked_figure_missing`. `diag["claims"]` пишется для диагностики. Промт:
   *«"claims" — leave every role null. It exists only for compatibility and is ignored.»*
   — согласовано с кодом answer-пути; на coverage `claims` ещё живы (§2.5).

**Вердикт:**
- **не трогать** слоты/`text`/запрет рукописных цифр без замера compose/gate;
- кандидат **чистить:** блок про `ask` в ANSWER_SYS (или сменить схему JSON) + удалить
  мёртвый pipeline `_ask_back`/`_filled_ask` ask_back-ветки — **средний риск**
  (модель может изменить стиль `text`, если убрать «middle road»);
- `claims` в answer: оставить null-инструкцию или выкинуть из схемы вместе с
  `_split_answer` claims — низкий/средний; coverage всё ещё использует claims.

---

### 2.5 `COVERAGE_SYS` — жив; `claims` здесь живые

Одинаковый текст в новом и legacy z20. После wiki при `about=coverage`.

Читает: `text` + `claims.total`/`count` через `check_claims`, плюс `gate` по census.

**Вердикт:** оставить. Чистка JSON-схемы без замера coverage — риск среднего
(единственный путь, где claims ещё судят ответ).

---

### 2.6 Wiki: `WIKI_PICK_SYS` полумёртв; `WIKI_VERIFY_SYS` жив; `why` мёртв

Цепочка `try_wiki_hybrid_entity_pick` (оба тракта через `wiki_primary_entity_cascade`):

- 1 карточка → только **verify**;
- ≥2 → **pick**, затем **всегда** verify; если verify ∈ {leader, clarify, none} —
  `pick = verify` (`z21:932–933`) — исход pick **затирается**.

Следствия для жизни:
- вызов pick при ≥2 **жив** (токены/латентность), но **choice/separable** влияют на
  исход ответа только если verify `degraded` (тогда остаётся pick) или при раннем
  return на degrade pick (`:925–927`);
- `separable` модели: `bool(model) and knn_sep` — модель может лишь **ужесточить**
  (false→clarify), не ослабить knn; при overwrite verify это часто невидимо клиенту.

**`why` в verify** (дословно в промте: `"why": <one line>`):
- пишется в verdict (`:587`),
- `wiki_outcome_from_verify` смотрит только `fit`/`index` —
  **поле мёртво для управления**.

**Вердикт:**
- verify: **не трогать** fit-контракт без wiki-прогонов;
- кандидат: убрать `why` из промта/парсера (экономия токенов) — **низкий риск**;
- кандидат: не звать pick, когда всё равно идёт полный verify (или звать pick только
  при degrade-политике) — **средний/высокий** риск ветвления clarify/leader; только
  с замером wiki-каскада;
- добавить WIKI_* в `OUR_PROMPTS` — **низкий** риск, закрывает дыру leak.

---

### 2.7 `AXIS_PICK_SYS` — жив только в legacy rank-пути

Потребитель: `rank_axis_resolve` ← legacy при выборе оси GROUP BY. Новый скелет ось
через SQL/меню B4 ещё не подключил этот вызов.

Поля: только индексы `axes`. Fallback при сбое — пустой список → rerank/hits (не отказ).

**Вердикт:** не трогать до замера rank; в «одном пути» решить явно: ось из вики/меню
человека vs этот классификатор — иначе после flip останется скрытый выбиратель.

---

### 2.8 `REFUSE_SYS` — жив; часто короткозамкнут env

Промт минимальный; код режет цифры. При `ASK_NO_DATA_TEXT` непустом большинство
call-sites (`NO_DATA_TEXT or refuse_text`) **не зовут** модель (исключение:
`z21:911` — `refuse_text or NO_DATA_TEXT`, порядок обратный).

**Вердикт:** оставить. Снос — только если все отказы станут шаблонными кодом
(язык вопроса); иначе регресс п.18/п.9.

---

## 3. Сводка по трактам

| промт | legacy (живой прод-путь до flip) | новый (B3 скелет) |
|---|---|---|
| INTENT | да | да |
| WIKI_PICK / VERIFY | да | да |
| REFUSE | да | да |
| COVERAGE | да | да (после wiki) |
| ANSWER / compose | да | **нет** (stub B4) |
| AXIS_PICK | да (rank) | **нет** пока |
| CLARIFY_SYS | нет | нет |
| ARBITRATE | нет | нет |

---

## 4. Правки-кандидаты

| промт | где | действие | риск для живых ответов |
|---|---|---|---|
| `CLARIFY_SYS` + `clarify_text` | z07; `OUR_PROMPTS` | **снести** мёртвый код; меню не трогать | низкий |
| `ARBITRATE` / `arbitrate` | z01 | **снести** после сверки импортов/тестов | низкий |
| `ANSWER_SYS` блок `ask` | z18:62–69 | **чистить**: убрать требование ask (контракт без ask_back) | средний — может сдвинуть формулировки `text` |
| `_ask_back` / ветка ask_back в legacy | z18 + z20_legacy:4113–4327 | **снести** мёртвый pipeline после чистки промта | низкий/средний |
| `WIKI_VERIFY` поле `why` | z21 промт + парсер | **чистить**: не просить / не хранить | низкий |
| `WIKI_PICK` вызов при ≥2 | z21:922–933 | **рассмотреть**: не звать или не overwrite без политики | высокий без замера |
| `OUR_PROMPTS` | z20 / legacy | **добавить** WIKI_PICK/VERIFY (и убрать CLARIFY если снесён) | низкий |
| `INTENT` / `period2` в схеме | z01 | не добавлять в промт без нужды; код compare сам пишет period2 | — |
| AXIS в новом тракте | — | явно решить роль vs меню вики | продуктовый, не правка строки |

---

## 5. Не трогать (без отдельного замера)

- Текст и правила **`INTENT_SYS`** (кроме осознанного добавления `period2`, если решите
  что модель должна его давать — сейчас даёт код).
- Контракт **`WIKI_VERIFY` `fit`/`index`** и порог «ровно один yes + остальные no».
- **`ANSWER_SYS`**: запрет рукописных цифр, слоты `{total}`/`{count}`/…, язык ответа.
- **`COVERAGE_SYS`** целиком + `check_claims` на coverage.
- **`REFUSE_SYS`** (пока отказы формулирует модель).
- **`AXIS_PICK_SYS`** на legacy rank до замера осей.
- Живое **`clarify_say`** / wiki_menu_captions (это не промты, но замена CLARIFY).

---

## 6. Дословные якоря (мёртвое / выбрасываемое)

**ANSWER — ask ещё в контракте модели, код убивает:**

```text
"ask" is the middle road between answering and giving up. Fill it ONLY when …
```

и сразу в коде legacy: `diag["ask_back_dropped"] = "bare_clarify_forbidden"`.

**ANSWER — claims ignored (answer path):**

```text
"claims" — leave every role null. It exists only for compatibility and is ignored.
```

**VERIFY — why парсится, исход смотрит только fit:**

```text
{"verdicts": [{"index": …, "fit": …, "why": <one line>}]}
```

**CLARIFY — промт без вызывающего:**

```text
The question can be answered from several kinds of records…
Ask the person ONE short question…
```

**ARBITRATE — промт без вызывающего:**

```text
Choose the ONE answer that actually answers the question…
Reply with a single digit…
```

---

## 7. Итог линзы L1

Главная находка аспекта «потребители и жизнь»: из девяти chat-промптов **два мёртвы
целиком** (CLARIFY, ARBITRATE), **один полумёртв** (WIKI_PICK при успешном verify),
у живого ANSWER **два поля схемы мёртвы для клиента** (`ask` всегда, `claims` на
answer-пути), у VERIFY **`why` мёртв**. Новый тракт уже режет поверхность модели до
intent+wiki(+coverage/refuse); compose/axis ещё не подключены — чистить ANSWER/AXIS
имеет смысл в связке с волной B4 / flip, а не «впрок» без замера.
