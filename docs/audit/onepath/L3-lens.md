# L3 — независимая линза: промпты тракта ask vs контракт «один путь»

**Дата:** 12.09.2026  
**Аспект:** противоречия формуле «вики → SQL → меню до SQL → ответ»; приглашения модели выбрать / спросить / дать второе число / назвать источник / продолжить диалог после ответа; тихий multi-choice.  
**Метод:** свой grep по `ubuntu/serenedb/ask/*.py` (без чужих отчётов `docs/audit/onepath/*`); чтение каждого system-промпта и парсера ответа целиком; статически. Код не менялся.

**Тракты:**
- **legacy (живой до flip):** `_bootstrap.py` грузит `z20_ask_main_http_legacy.py`.
- **новый «один путь»:** `z20_ask_main_http.py` — скелет B3 (SQL/compose — B4); в bootstrap до flip **не** грузится.

Единый транспорт модели: `ds_chat` / `ds_chat_post` в `z01_infra_trace_llm.py`. Отдельных `*_HINT` / `*_PROMPT` в ask/ нет.

---

## 1. Реестр промптов

| Имя | файл:строка | длина (симв.) | Вызовы | Тракт | Жив/мёртв | Поля ответа, которые читает код |
|---|---|---:|---|---|---|---|
| **INTENT_SYS** | `z01_infra_trace_llm.py:800` | 3240 | `parse_intent` → `_one_intent` (`z02_intent.py:666–676`); user: `today=…\nQuestion: …` | оба (разбор до ветвления) | **жив** | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` (+ нормализация `period2`); повтор «Return the JSON object.» при сбое разбора |
| **ARBITRATE** (`sys_msg` inline) | `z01_infra_trace_llm.py:607` | ~391 | `arbitrate()` (`:602`); **вызовов в ask/ нет** | — | **мёртв** | только цифры → индекс ответа `0…n-1` или `None` |
| **CLARIFY_SYS** | `z07_rrf_vectors.py:285` | 440 | только `clarify_text()` (`:295`); **вызовов нет** (меню — `clarify_say` / `format_clarify_options` без LLM) | — | **мёртв** | весь текст ответа как фраза уточнения |
| **REFUSE_SYS** | `z07_rrf_vectors.py:317` | 283 | `refuse_text()` → no_data / отказы в z20 (оба), z21, z13, z04 | оба | **жив** | одна фраза; цифры вырезаются кодом (`_norm_numbers`) |
| **AXIS_PICK_SYS** | `z10_rank.py:136` | 599 | `rank_axis_pick` ← `rank_axis_resolve` (legacy `z20_…_legacy.py` ~3609); в новом z20 **ещё нет** SQL/rank | legacy сейчас; новый — после B4 | **жив в legacy** | JSON `{"axes":[N…]}` → список `col` (≤3); ≥2 оси → меню кодом (`return None, picked`) |
| **ANSWER_SYS** | `z18_compose.py:55` | 2457 | `compose()` ← legacy answer (~4109, ~4186); новый z20 **не** зовёт (stub B4) | legacy | **жив в legacy** | `_split_answer`: `text` (+ `claims` игнор/совместимость); `_ask_back`: поле `ask` — **сейчас всегда сбрасывается** (`bare_clarify_forbidden`) |
| **WIKI_PICK_SYS** | `z21_wiki_choice.py:45` | 248 | `wiki_pick_from_cards` (`:799`) | оба (каскад z21) | **жив** | `choice` (int), `separable` (bool ∧ kNN gap) |
| **WIKI_VERIFY_SYS** | `z21_wiki_choice.py:50` | 444 | `wiki_verify_candidates` (`:738`) | оба | **жив** | `verdicts[]`: `index`, `fit`∈{yes,no,unsure}; `why` парсится, на исход **не влияет** |
| **COVERAGE_SYS** | `z20_ask_main_http.py:736` и **дубль** `…_legacy.py:742` | ~892 | `_coverage_answer` (оба z20) | оба | **жив** | `_split_answer`: `text`, `claims` → `check_claims` + числовой `gate` по переписи |

**Не промпты, но зовут модель иначе:** `rerank()` (`z07`) — HTTP re-ranker, не chat; `embed_one` — эмбеддер. В реестр chat-промптов не входят.

**OUR_PROMPTS** (leak-гейт, оба z20):  
`INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS`.  
**Нет:** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, текст `arbitrate` — утечка этих инструкций `prompt_leak` не ловит.

**User-части (рядом с system):**

| Промпт | User (сборка) |
|---|---|
| INTENT | `today=%s\n\nQuestion: %s` |
| ARBITRATE | опц. `Conversation so far` (≤2000) + `Question` + `Answers:\n1)…` |
| CLARIFY | `Question` + `Options:` label / distinct_by |
| REFUSE | сырой `question` |
| AXIS_PICK | вопрос (+ kind) + `Axes:\n1. label…` |
| ANSWER | `QUESTION` + ROWS/GROUPS + COMPUTED placeholders + опц. coverage/measure/folders/corrections |
| WIKI_PICK | вопрос (+ kind) + `Cards:` name/description/**platform**/axes/measures |
| WIKI_VERIFY | вопрос (+ kind) + `Passports:` name/wiki/**platform**/axes/measures/distinct/doesNotAnswer |
| COVERAGE | вопрос + `Census:` агрегаты + до `COVERAGE_TOP` строк entity |

---

## 2. Анализ по аспекту «один путь»

Формула контракта: **вопрос → интерпретация из вики → SQL → меню с описаниями из вики (если прочтений >1) → выбор человека → ответ.**  
Модельных ask_back после ответа нет; одно число; меню — единый построитель **до** SQL.

### 2.1 Прямые противоречия (приглашения / обходы формулы)

#### A. `ANSWER_SYS` — поле `"ask"` (главный удар по аспекту)

Дословно (фрагмент):

> `"ask": "one clarifying question, or null"`  
> `"ask" is the middle road between answering and giving up. Fill it ONLY when…`  
> `…put in "text" what the rows DO show, and in "ask" a single short question…`

Это **явное** приглашение модели продолжить диалог / уточнить **после** (или вместо чистого) ответа по строкам — ровно запрещённый в новом тракте ask_back.

В legacy код читает `ask`, гоняет гейт, затем **безусловно** гасит:

```text
diag["ask_back_dropped"] = "bare_clarify_forbidden"
ask_back = ""
```

Итог: поведение уже «без ask_back», но промпт **всё ещё учит** модель писать `ask` → лишние токены, риск регрессии, если когда-нибудь снимут дроп. Для «одного пути» / B4 compose: поле и абзацы про ask — кандидат на вырезание из схемы JSON.

**Вердикт:** чистить (снести `"ask"` и абзацы 62–69, 88 «ask too») при переносе compose в новый тракт; до flip — низкий runtime-риск из‑за дропа, средний риск «оживления» при правке legacy.

#### B. `CLARIFY_SYS` — модельное уточнение вместо построителя меню

> `Ask the person ONE short question to find out which they meant.`  
> `Describe each option in plain business words…`

Контракт: подписи меню — **кодом** (`clarify_say` / `wiki_menu_captions`), не прозой модели. Функция `clarify_text` **нигде не зовётся** — промпт мёртв, но лежит как ложный путь «вернуть модель в меню».

**Вердикт:** снести вместе с `clarify_text` (или оставить мёртвым до отдельной чистки мёртвого кода). Риск для живых ответов: **нулевой** (нет вызовов).

#### C. `ARBITRATE` — тихий выбор моделью между готовыми ответами

> `Choose the ONE answer that actually answers the question…`  
> `If none… or two answer it equally well, reply 0.`

Это выбиратель **после** SQL (между посчитанными ответами), мимо вики-меню и выбора человека. Вызовов нет (арбитр-цикл снесён; замок `test_no_pre_wiki_reorders`).

**Вердикт:** снести `arbitrate` + inline `sys_msg` в волне мёртвого кода. Риск runtime: **нулевой**.

#### D. `AXIS_PICK_SYS` — «несколько номеров» = ранжирование осей моделью

> `Several numbers when different axes would answer different readings… (at most three).`

Промпт просит **упорядоченный** multi-pick. Код при ≥2 осях отдаёт меню (`rank_axis_resolve` → `None, picked`), не молчаливый лидер — с аспектом меню **согласовано на стороне кода**. Остаточный риск: модель всё же вернёт один индекс при двух равноправных прочтениях → тихий выбор оси (догадка, п.12), если не сработают rerank/hatch.

В новом тракте оси/окна уже задуманы как **readings → меню до SQL**; зов AXIS_PICK из нового z20 пока отсутствует.

**Вердикт:** оставить механизм, но при B4 **подчистить формулировку** («при сомнении — пустой/несколько равных индексов; выбор человека снаружи») или не звать модель, если readings уже построены кодом. Риск правки: средний (rank-вопросы в приёмке).

### 2.2 Согласованные с формулой (не трогать по аспекту)

#### E. `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS`

> Pick: `Map … to one numbered entity card, or 0` + `separable`  
> Verify: `fit: yes|no|unsure` → код: один yes → лидер; несколько / unsure → **clarify**; все no → none.

Это как раз **интерпретация из вики** до ответа. Меню человеку при неоднозначности — исход `clarify` каскада, подписи без LLM (`wiki_menu_captions`). Поля `platform` / имена осей уходят **в модель** (не в подпись меню) — для аспекта «подписи человеку» ок; для п.19 — короткий паспортный контекст, не схема БД.

**Вердикт:** оставить как есть. Чистка формулировок не требуется аспектом.

#### F. `INTENT_SYS`

Структура отбора; без приглашения спросить человека или выбрать источник из списка. `about=coverage` — ветка полноты. Правила «NEVER put KIND in terms» — формат/роль разбора (живут давно); не ask_back.

**Вердикт:** не трогать из‑за аспекта L3.

#### G. `REFUSE_SYS`

Одна фраза отказа без фактов/цифр. Нужен, пока `NO_DATA_TEXT` пуст. Не multi-choice.

**Вердикт:** не трогать.

#### H. `COVERAGE_SYS`

Ответ о полноте по переписи; JSON без `ask`. В новом z20 зовётся **после** wiki (порядок формулы соблюдён скелетом).  
Натяжка с «одно число»: перепись естественно несёт несколько цифр (missing / kinds) — это другой класс вопроса, не второй ответ после бизнес-числа.  
Натяжка с п.19: модель **копирует цифры в текст** (не placeholders как в ANSWER) — держится гейтом; не предмет аспекта «меню/ask_back», но при унификации compose — кандидат на placeholders.

**Вердикт по аспекту L3:** оставить; унификация цифр — отдельная тема, не блокер одного пути.

### 2.3 User-часть `compose` (не `*_SYS`, но влияет)

В user к ANSWER: `DATA COMPLETENESS WARNING… You MUST warn… stating the number of missing rows`, `QUANTITY USED…`, `GROUPS EXCLUDED… You MUST say…`.  
Это толкает к **дополнительным числам/оговоркам в том же ответе** рядом с `{total}` — напряжение с «один ответ — одно число». Сейчас gated + placeholders. Для нового тракта лучше держать оговорки **кодом** после текста, не MUST в промте (и правило 03.08: запреты/обязанности — кодом).

**Вердикт:** чистить осторожно при B4 (перенос MUST → код); риск регрессии полноты/папок — высокий без замера.

---

## 3. Вердикты по каждому промпту (сводка)

| Промпт | Вердикт | Что именно | Риск правки для живых ответов |
|---|---|---|---|
| INTENT_SYS | **оставить** | — | — |
| ARBITRATE | **снести** | мёртвый выбиратель после SQL | нулевой |
| CLARIFY_SYS | **снести** | мёртвое модельное меню | нулевой |
| REFUSE_SYS | **оставить** | — | — |
| AXIS_PICK_SYS | **чистить (мягко) / оставить роль** | убрать акцент «несколько номеров = ранжирование»; меню — код | средний (rank) |
| ANSWER_SYS | **чистить** | вырезать `"ask"` и абзацы про clarifying question | низкий сейчас (дроп); средний если уберут дроп без чистки промпта |
| WIKI_PICK_SYS | **оставить** | — | — |
| WIKI_VERIFY_SYS | **оставить** | — | — |
| COVERAGE_SYS | **оставить** (по аспекту) | дубль в двух z20 — слить при flip | низкий при bit-identical |
| compose user MUST* | **чистить позже (B4)** | оговорки → код | высокий без приёмки |

---

## 4. Итог: правки-кандидаты и «не трогать»

### Кандидаты (промпт | место | действие | риск)

1. **ANSWER_SYS** | `z18_compose.py:58–69,88` | Удалить поле `"ask"` из JSON-схемы и все инструкции Fill/Do not ask; убрать `_ask_back` / ветку ask_back в compose-хвосте при B4 | **средний→низкий** после замера: модель перестанет эмитить ask; убедиться, что JSON всё ещё стабильно парсится |
2. **CLARIFY_SYS + clarify_text** | `z07_rrf_vectors.py:285–311` | Снести; убрать из `OUR_PROMPTS` | **нулевой** |
3. **ARBITRATE sys_msg + arbitrate()** | `z01_infra_trace_llm.py:582–628` | Снести мёртвый код | **нулевой** |
4. **AXIS_PICK_SYS** | `z10_rank.py:144–145` | Переформулировать: при нескольких прочтениях не «лучший порядок», а сигнал неоднозначности (пустой/`axes` длины≥2 без ранжирования как выбора) **или** не звать LLM, если readings уже есть | **средний** — нужен замер rank/axis-clarify |
5. **OUR_PROMPTS** | оба z20 `:755/:761` | Добавить WIKI_* (и не добавлять мёртвый ARBITRATE); убрать CLARIFY после сноса | **низкий** (только leak-гейт) |
6. **compose user MUST (coverage/folders/measure)** | `z18_compose.py:~839–861` | Вынести оговорки в код после подстановки слотов | **высокий** без `REGRESSION`/`ACCEPTANCE` |

### Не трогать (по аспекту L3)

- **INTENT_SYS** — разбор смысла, не диалог после ответа.  
- **WIKI_PICK_SYS / WIKI_VERIFY_SYS** — канон ступени «интерпретация из вики».  
- **REFUSE_SYS** — язык отказа.  
- **COVERAGE_SYS** — не ask_back; порядок «после wiki» в новом скелете верный.  
- Живой путь меню **`clarify_say` / `wiki_menu_captions` / `readings_menu`** — не промпты; их не подменять возвратом `CLARIFY_SYS`.

### Замечание оркестратору (сходимость)

Единственный **живой** промпт, который по тексту всё ещё противоречит контракту одного пути, пока ответы идут через legacy compose: **`ANSWER_SYS` + `"ask"`**. Остальные противоречия аспекта либо уже убиты кодом (ask_back drop, меню без LLM), либо лежат в мёртвом коде (arbitrate / clarify_text). Новый z20 до B4 compose почти не использует ANSWER — чистку логично совместить с волной B4, не отдельным выкатом в прод.

---

*Конец L3. Чужие отчёты O*/B* не читались.*
