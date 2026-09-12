# L5 — независимая линза: user-части промптов ask и п.19

Срез: 12.09 (статический аудит исходников `ubuntu/serenedb/ask/`).  
Аспект: **что уходит в user рядом с каждым SYS** — техимена 1С, рост размера с базой, лимиты.  
Чужие отчёты `docs/audit/onepath/*` не читались. Код не менялся.

Тракт загрузки: `_bootstrap.py` грузит **`z20_ask_main_http_legacy.py`** (живой ответ до flip).  
`z20_ask_main_http.py` (новый «один путь», stub B4) на диске есть, в `_ZONE_FILES` **нет** — в рантайме не подменяет `answer`.

Единая точка LLM: `ds_chat` → `z01_infra_trace_llm.py` (DeepSeek chat/completions).  
Эмбеддер / rerank — не chat-промпты; в реестр SYS не входят (упомянуты, где дают user-контекст рядом).

---

## 1. Реестр промптов (свой grep)

| Имя | файл:строка | len SYS (симв.) | Вызовы | Тракт | Жив/мёртв | Поля ответа, читаемые кодом |
|---|---|---:|---|---|---|---|
| **INTENT_SYS** | `z01_infra_trace_llm.py:800` | 3239 | `parse_intent` → `_one_intent` (`z02_intent.py:666–567`) | legacy + новый (оба зовут `parse_intent`) | **жив** | JSON: `terms`, `amount`, `period`/`period2`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form`; повтор «Return the JSON object.» при сбое разбора |
| **WIKI_PICK_SYS** | `z21_wiki_choice.py:45` | 247 | `wiki_pick_from_cards` (`:799`) из `wiki_primary_entity_cascade` | legacy + новый (wiki-каскад) | **жив** | JSON `choice` (int), `separable` (bool); иначе 0 / unparseable |
| **WIKI_VERIFY_SYS** | `z21_wiki_choice.py:50` | 443 | `wiki_verify_candidates` (`:738`) | legacy + новый | **жив** | JSON `verdicts[]`: `index`, `fit` (yes/no/unsure), `why` (обрезка 200); salvage-разбор |
| **AXIS_PICK_SYS** | `z10_rank.py:136` | 598 | `rank_axis_pick` (`:211`) ← `rank_axis_resolve` | legacy (rank-ветка); новый — после B4 | **жив в legacy** | JSON `axes` (1-based индексы) или цифры regex; макс. 3 col |
| **ANSWER_SYS** | `z18_compose.py:55` | 2456 | `compose` (`:876`) ← legacy `answer` (~4109, retry ~4186) | **только legacy** (новый stub B4 без compose) | **жив в legacy** | `_split_answer`: `text`, `claims` (игнор ролей); `_ask_back`: `ask` |
| **COVERAGE_SYS** | `z20_…_legacy.py:742` и `z20_ask_main_http.py:736` (дубль) | 891 | `_coverage_answer` | оба файла; в bootstrap — legacy | **жив** | `_split_answer`: `text` (+ `claims` для check_claims) |
| **REFUSE_SYS** | `z07_rrf_vectors.py:317` | 282 | `refuse_text` (`:341`) — fallback no_data / отказы | оба тракта | **жив** | весь текст; цифры вырезаются кодом (`_norm_numbers`) |
| **CLARIFY_SYS** | `z07_rrf_vectors.py:285` | 439 | только `clarify_text` (`:308`) | — | **мёртв** (вызовов `clarify_text(` в репо нет; меню — `clarify_say` кодом) | текст фразы |
| **ARBITRATE** (inline `sys_msg`) | `z01_infra_trace_llm.py:607` | 391 | `arbitrate` (`:618`) | — | **мёртв** (вызовов нет; тест `test_no_pre_wiki_reorders` ждёт 0 вызовов в z20) | одна цифра → индекс ответа |

Констант `*_PROMPT` / `*_HINT` в `ask/*.py` **нет**.  
`OUR_PROMPTS` (leak-гейт): INTENT, AXIS, CLARIFY, REFUSE, ANSWER, COVERAGE — **без** WIKI_PICK / WIKI_VERIFY / ARBITRATE.

Лимиты env (рядом с вызовами):  
`INTENT_MAX_TOKENS` (400), `WIKI_VERIFY_MAX_TOKENS` (2048), axis 80, clarify 120, refuse 60, compose 800, arbitrate 8;  
контекст user: `ROWS_TO_MODEL`=25, `ROWS_BUDGET`=24000, `COVERAGE_TOP`=15, `WIKI_PICK_N`/`WIKI_PASSPORT_N`=8, `WIKI_PASSPORT_BODY_MAX`=1500, `PICK_BUDGET`=8000 (кандидатный LIMIT, не chat-user wiki).

---

## 2. User-части по каждому вызову (п.19)

### 2.1 INTENT — эталон п.19

**User** (`z02:667`):

```text
today=<YYYY-MM-DD>

Question: <вопрос человека>
```

Схемы, таблиц, строк корпуса нет. Размер = дата + вопрос.  
**Вердикт:** оставить. Чистить нечего.

---

### 2.2 WIKI_PICK — сильная утечка схемы в user

**User** (`z21:801`):

```text
<вопрос> [(kind из intent)]

Cards:
1. name: …
   description: …[:200]
   platform: …          # kind_word / префикс типа
   axes: …              # БЕЗ обрезки
   measures: …          # БЕЗ обрезки
```

Источник `axes` / `measures` — сборка карточек (`wiki_card_build.sql`):

```sql
string_agg(r.col || ' -> ' || r.target_src, ', ' …) AS axes
string_agg(m.measure || ': ' || coalesce(m.aliases, ''), '; ' …) AS measures
```

Дословный смысл утечки: в модель уходят **имена OData-колонок** (`col`) и **`target_src`** вида `catalog_…` / `document_…`, плюс имена мер из `search_measure_alias`.  
`src_table` кандидата в листинг карточки **не** печатается (хорошо), но оси/меры — это уже схема связей сущности.

Лимиты: число карточек ≤ `WIKI_PICK_N` (8) — **не растёт с числом таблиц базы**.  
Длина **одной** строки `axes`/`measures` **не лимитирована** в форматтере — растёт с числом refcols/мер **этой** сущности (сложность метаданных, не «вся база»).

**Вердикт:** чистить user-сборку (не SYS): не слать `col -> target_src` сырьём; для pick достаточно human `name` + `description` (+ при необходимости человеческие оси/меры без OData-имён).  
**Риск правки:** падение точности выбора при близких карточках, где модель сейчас опирается на оси; нужен замер wiki-каскада / L-match до/после.

---

### 2.3 WIKI_VERIFY — та же утечка + крупный wiki body

**User** (`z21:740`):

```text
<вопрос> [(kind)]

Passports:
1. passport
   name: …
   wiki: …[:WIKI_PASSPORT_BODY_MAX=1500]
   platform: …
   axes: … / measures: …   # снова сырые
   distinct: axes: <col…>; measures: <…>
   [doesNotAnswer: …]
Other pool names only: … | fallback на src_table если name пуст
```

`distinct` (`wiki_passport_distinct`) парсит **левые части** `col -> …` и кладёт имена колонок ещё раз.  
Хвост пула: `name or src_table` — прямой риск техимени при пустом `name`.

Лимиты: ≤8 полных паспортов; body ≤1500; description в card ≤200.  
Худший порядок user ≈ 8×(1500 + axes/measures) — **ограничен числом кандидатов**, не размером корпуса; axes снова дыра по длине.

Код читает только индексы/`fit`/`why` — длинный `why` в клиент не идёт, но модель может **выучить** техимена и протащить их в другие ответы (coverage/compose), если они попадут в её контекст на том же запросе или в привычку формулировок.

**Вердикт:** чистить: (1) axes/measures → человеческие подписи или убрать из verify user; (2) `distinct` без сырых col; (3) хвост — никогда `src_table`.  
**Риск:** verify «yes/no» на близких регистрах/документах; обязателен замер на корпусе, где сейчас держится лидер.

---

### 2.4 AXIS_PICK — техимена колонок в скобках

**User** (`z10:214`):

```text
<вопрос> [(kind)]

Axes:
1. <label из search_tables.target_src>
   или «label (col)» если label ≠ col   # rank_axis_label_rows :170-171
```

Дословно из кода:

```python
lab = "%s (%s)" % (lab, col)   # когда есть target_src и lab != col
```

Список осей — только у **уже выбранной** сущности → размер не растёт с базой; растёт с числом осей одной сущности (обычно мало).

**Вердикт:** чистить: в listing только человеческая метка, без `(col)`. Индексы для кода достаточны.  
**Риск низкий:** модель выбирает номер; col резолвится кодом. Регрессия возможна, если две оси с одинаковой меткой — тогда нужен различитель **не** OData-именем (например, краткое wiki/роль).

---

### 2.5 ANSWER / compose — строки и имена величин; схема таблиц не уходит

**User** (`compose` `z18:719+`):

- `QUESTION: …`
- до `ROWS_TO_MODEL` примеров строк корпуса (`doc` + опционально `amount=` / `date=`), бюджет `ROWS_BUDGET`
- слоты `{total}`, `{count}`, `{total:NAME}`… — **значения чисел модели не показываются**
- имена величин из `totals` / `agg.measure` / `measure_used`
- `kind_word(src)` только как подсказка слота `{count_kind}` (человеческий тип: «документ», …)
- coverage warning с плейсхолдерами `{in_1c}`…
- retry: текст причин гейта

Схему колонок / `src_table` в user compose **не кладёт**.  
Размер **ограничен** константами — п.19 по росту с базой соблюдён для строк.

Риски утечки в ответы клиенту (смежно):

- текст строк корпуса может содержать служебные ярлыки, если они попали в `content` при сборке — это данные, не схема;
- **ANSWER_SYS** учит поле `"ask"` (ask_back) — в новом тракте запрещено; в legacy после гейта ask_back **сбрасывается** (`ask_back_dropped`), но user/SYS всё ещё провоцируют модель задавать уточнение.

**Вердикт:** лимиты строк — не трогать. Кандидат: убрать/`null`-only `"ask"` из SYS+разбора при flip (контракт меню до SQL).  
**Риск правки ask:** средний на legacy до полной замены меню; на новом тракте — желательно до включения compose.

---

### 2.6 COVERAGE — техимена сущностей в census

**User** (`_coverage_answer`):

```text
<вопрос>

Census:
rows in source system: N
…
<entity>: A in source, B in search — <причина>   # entity = search_coverage.entity ≈ src_table
```

Поимённо ≤ `COVERAGE_TOP` (15) — **бюджет п.19 по размеру явный** (комментарий в z01:52–55).  
Но строки вида `document_реализациятмц: …` — **техимена в модель**; SYS велит «Name the kinds of records that are missing» → модель часто **эхом** отдаёт их человеку.

**Вердикт:** чистить user: в census — `human_table_label` / label из `search_tables`, не сырой `entity`. Лимит TOP оставить.  
**Риск низкий** на числах (гейт по цифрам переписи); риск формулировок — нужен прогон coverage-вопросов приёмки.

---

### 2.7 REFUSE — только вопрос

**User:** голый `question`. Данных/схемы нет.  
**Вердикт:** оставить.

---

### 2.8 CLARIFY (мёртв) — на случай воскрешения

**User** был бы: `Question` + `Options: - label (typical: distinct_by)`.  
`distinct_by` в живых меню часто = `a["col"]` (`axis_clarify_options`) — при возврате LLM-clarify это снова утечка. Сейчас меню кодом (`clarify_say`) — LLM не зовётся.

**Вердикт:** не воскрешать без чистки `distinct_by`; либо снести мёртвый путь.

---

### 2.9 ARBITRATE (мёртв)

**User:** вопрос + готовые тексты ответов (+ `context[-2000:]`).  
П.19 по счёту соблюдён (числа уже в ответах). Рост — с длиной готовых фраз, не с базой.  
**Вердикт:** не трогать / можно снести позже как мёртвый код (вне scope L5).

---

## 3. Сводка по аспекту п.19

| Критерий | Оценка |
|---|---|
| Рост user с **числом таблиц/строк базы** | В основном **закрыт** лимитами (wiki N, rows budget, coverage TOP, intent = вопрос). Старый entity-list в модель через chat **убран** (wiki); `PICK_BUDGET` режет SQL-кандидатов, не chat-user wiki. |
| Утечка **техимён 1С / схемы** в user | **Есть, системно:** wiki axes/measures (`col -> target_src`), passport `distinct`, axis listing `(col)`, coverage `entity`, хвост passport → `src_table`. |
| Лимиты на месте | Да для числа кандидатов/строк/body; **нет** для длины axes/measures одной карточки. |
| Новый тракт vs legacy | Новый уже зовёт intent+wiki(+coverage); compose/axis — ещё legacy/B4. Чистка wiki user бьёт **оба** тракта сразу. |

---

## 4. Правки-кандидаты (промт / место | действие | риск)

| # | Где | Действие | Риск для живых ответов |
|---|---|---|---|
| **C1** | `wiki_format_card_lines` / данные `axes` | Не слать сырой `col -> target_src`; human label цели или опустить axes на pick | **Высокий** на близких сущностях — только с замером wiki |
| **C2** | `wiki_format_passport_lines` + `wiki_passport_distinct` | То же + не класть raw col в `distinct`; хвост без `src_table` | **Высокий** (verify) — замер обязателен |
| **C3** | `rank_axis_label_rows` `:170-171` | Убрать суффикс `(col)` из user listing | **Низкий** |
| **C4** | `_coverage_answer` census | `entity` → человеческая метка | **Низкий/средний** (формулировки coverage) |
| **C5** | `ANSWER_SYS` поле `ask` + `_ask_back` | При flip «один путь» — убрать ask_back из контракта модели | **Средний** на legacy до полного меню; на новом — желательно до B4 compose |
| **C6** | `OUR_PROMPTS` | Добавить WIKI_* в leak-гейт (не user, но дыра зеркала) | **Низкий** |
| **C7** | Опционально: cap длины `axes`/`measures` в форматтере | Жёсткий truncate + «…» | **Средний** — режет сигнал; лучше C1/C2 |

Рекомендовать правки **только с замером**; живые промпты проверены приёмкой — «почистить оси» без прогона = риск п.21 (no_data при живых данных).

---

## 5. Не трогать (по аспекту L5)

| Что | Почему |
|---|---|
| **INTENT_SYS** + user `today`+вопрос | Чистый п.19; разбор держится кодом |
| **REFUSE_SYS** + user=вопрос | Нет данных/схемы |
| Лимиты `ROWS_*`, `COVERAGE_TOP`, `WIKI_*_N`, `WIKI_PASSPORT_BODY_MAX` | Уже держат рост с базой |
| Подстановка чисел слотами в compose (значения скрыты) | Устройство п.19 «модель не считает» |
| Мёртвые CLARIFY_SYS / ARBITRATE — **поведение** | Сейчас не в пути; снос — отдельная уборка, не срочная чистка user |
| Содержимое ANSWER_SYS про placeholders / язык | Не user-утечка схемы; менять только с гейт-замером |
| Меню `clarify_say` / `wiki_menu_captions` | Не LLM-user; подписи из wiki name/body (отдельный UX-трек) |

---

## 6. Итог линзы L5

Главный дефект аспекта: **не «промпт слишком длинный с базой»**, а **в user wiki/axis/coverage систематически попадает схема 1С (колонки, target_src, src_table)**, при том что число кандидатов уже урезано.  
Самый выгодный первый шаг с точки зрения п.19+подписей: **C1+C2 (wiki user без OData-осей) + C3 + C4**, под замком wiki/coverage-прогона. Intent и refuse — эталон «не трогать».
