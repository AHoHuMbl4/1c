# L7 — независимая линза: промпты тракта ask (аспект «дыры нового тракта»)

Статический аудит. Источники: только `ubuntu/serenedb/ask/*.py`. Чужие
отчёты `docs/audit/onepath/*` не читались. Модель не вызывалась, БД не
трогалась, код не менялся.

Аспект линзы: что волнам B3/B4 нужно от модели (меню прочтений до SQL,
count без меры, один ответ — одно число), чего в промптах нет; где
нехватка уже закрыта кодом; где ещё нужен текст; формулировки-кандидаты
без долженствований.

Дата среза исходников: 12.09.2026.

---

## 1. Метод реестра

Grep по `ask/` на:

- константы `*_SYS` / `*_PROMPT` / `*_HINT`;
- `role`/`system` + `ds_chat(`;
- потребители `ds_chat` / `compose` / `parse_intent` / wiki-pick/verify /
  `rank_axis_pick` / `arbitrate` / `clarify_text` / `refuse_text`.

`*_HINT` / `*_PROMPT` в ask/ **нет**. Отдельно учтён inline-system у
`arbitrate` и динамический user-body у `compose` (он несёт инструкции
модели наравне с `ANSWER_SYS`).

Длины — число символов тела константы (без кавычек), посимвольно по тексту
в файле; для длинных (≥1k) — ±5 из-за переносов строк в литерале.

---

## 2. Реестр промптов

| имя | файл:строка | длина | вызовы | тракт | жив/мёртв | поля ответа, читаемые кодом |
|---|---|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 2687 | `parse_intent` → `_one_intent` (`z02:666–672`); оба `answer()` (новый + legacy) | оба | **жив** | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form`; код ещё нормализует `period2` (в схеме промта **нет**). Повтор при сбое: user `"Return the JSON object."` |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 238 | `wiki_pick_from_cards` (`z21:799`) ← каскад wiki | оба (каскад z21) | **жив** | `choice` (int), `separable` (bool); пересекается с kNN-gap кодом |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 368 | `wiki_verify_candidates` (`z21:738`) | оба | **жив** | `verdicts[]`: `index`, `fit`∈{yes,no,unsure}, `why` (why только в diag/salvage; исход — по `fit`) |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 518 | `rank_axis_pick` ← `rank_axis_resolve` ← legacy rank-путь (`z20_…_legacy` ~3609) | **legacy** | **жив в legacy**; в новом `answer()` **не зовётся** | JSON `axes: [1-based ints]` → список `col` (≤3) |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 405 | только внутри `clarify_text` (`z07:308`) | — | **мёртв** (вызовов `clarify_text(` в дереве ask/ **0**) | был бы весь текст ответа |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 278 | `refuse_text` ← no_data / coverage-fallback / fork / calendar-block / оба z20 | оба | **жив** | весь текст; код **отбрасывает**, если в нём есть цифры (`_norm_numbers`) |
| `ANSWER_SYS` | `z18_compose.py:55` | 1847 | `compose` (`z18:876`) ← только **legacy** `answer` (~4109, retry ~4186) | **legacy** (до B4) | **жив в legacy**; новый `answer()` compose **не зовёт** (заглушка B4) | `_split_answer`: `text`, `claims` (claims игнорируются по смыслу); `_ask_back`: поле `ask` |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` и дубль `z20_…_legacy.py:742` | 752 | `_coverage_answer` (оба z20) | оба | **жив** | `_split_answer`: `text`, `claims`; цифры ещё через `gate` по переписи |
| `ARBITRATE_SYS` (inline `sys_msg`) | `z01_infra_trace_llm.py:607` | 478 | `arbitrate` (`z01:618`) | — | **мёртв** (вызовов `arbitrate(` в ask/ и соседнем ubuntu/serenedb кроме тестов на отсутствие — **0**) | первая 1–2 цифры → номер ответа; иначе None |

### 2.1. Транспорт модели (не промпт)

| символ | файл | роль |
|---|---|---|
| `ds_chat` / `ds_chat_post` / `_ds_chat_body` | `z01:549–579` | единственный чат DeepSeek |
| `rerank` | `z07:348` | отдельный HTTP rerank (не chat-промпт) |
| `embed_one` | `z01` | эмбеддер, не chat |

### 2.2. User-части рядом с каждым живым промптом

| промпт | user (сборка) |
|---|---|
| INTENT | `"today=%s\n\nQuestion: %s"`; retry: assistant(raw)+`"Return the JSON object."` |
| WIKI_PICK | `"{question} ({kind}?)\n\nCards:\n"` + `wiki_format_card_lines` (name/description/platform/axes/measures) |
| WIKI_VERIFY | то же + `wiki_format_passport_lines` (wiki body, distinct, doesNotAnswer) |
| AXIS_PICK | `"{question} ({kind}?)\n\nAxes:\n1. label…"` |
| REFUSE | голый `question` |
| ANSWER | большой body `compose`: QUESTION + ROWS/GROUPS + COMPUTED placeholders + опционально DATA COMPLETENESS / QUANTITY USED / GROUPS EXCLUDED / PREVIOUS REJECTED |
| COVERAGE | `"{question}\n\nCensus:\n…"` |
| CLARIFY (мёртв) | `Question` + `Options: - label (typical: …)` |
| ARBITRATE (мёртв) | context? + Question + Answers listing + `Number:` |

### 2.3. Меню без модели (важно для аспекта)

В **новом** и уже в живом clarify-пути меню строит код, не промпт:

- `clarify_say` / `format_clarify_options` / `clarify_choice_prompt` — `z20_ask_main_http.py:281–352` (и зеркало в legacy);
- `readings_menu` → те же построители — новый `answer` B3 (`:1617–1624`);
- `wiki_menu_captions` — подписи из паспорта/карточки вики, без LLM (`z21:379`).

`CLARIFY_SYS` в этот путь **не входит**. Он остаётся только в `OUR_PROMPTS` для `prompt_leak`.

### 2.4. `OUR_PROMPTS` / утечки

`OUR_PROMPTS` (оба z20, ~755): INTENT, AXIS_PICK, CLARIFY, REFUSE, ANSWER, COVERAGE.

**Не входят:** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, inline арбитра. Утечка wiki-инструкции в ответ клиента `prompt_leak` не поймает.

---

## 3. Аспект: что нужно B3/B4 и что есть

Контракт нового тракта (из задачи):  
вопрос → вики → SQL → меню прочтений с описаниями из вики (если >1) → выбор → ответ;  
меню **единым построителем до SQL**; **ask_back нет**; count без меры; один ответ — одно число; подписи простыми словами; новые запреты — в код, не в промт.

### 3.1. Карта потребностей → закрытие

| потребность B3/B4 | нужно ли от модели | чем закрыто сейчас | дыра в промптах? |
|---|---|---|---|
| Меню прочтений окна/оси **до SQL** | нет (только язык подписей из данных) | код: `period_readings` → `_readings_to_opts` → `readings_menu`/`clarify_say`; B3 уже | **нет** — отдельный clarify-промпт не нужен |
| Подписи меню без имён метаданных | нет | `human_table_label` / `label_has_meta_src`; wiki captions = name+wiki body | **нет** текста; риск данных (если в wiki_body уже мета-имя) — не промпт |
| Выбор сущности | да (смысл карточек) | `WIKI_PICK` + `WIKI_VERIFY` | формат ОК ок; см. §3.2 |
| Count без меры | модель: `want=count`, `measure=null`; дальше код | INTENT уже: want=count; measure «null if no quantity»; compose user при `has_money=false` даёт только `{count}`; новый `answer` ставит `diag["count_no_measure_menu"]=True` и **ждёт B4** на меню мер | **нового промпта не нужно**; B4 обязана **не** звать measure-меню при count (код) |
| Один ответ — одно число | держится слотами/гейтом, не просьбой | `slot_mode` + `_fill_figures` + `asked_figure_missing` + `gate`; ANSWER_SYS **не** говорит «одно число» | формулировать в промте **не стоит** (правило 03.08); дыры нет, если B4 сохранит слоты |
| Нет ask_back | — | legacy всё ещё читает `ask`, потом **сбрасывает** (`ask_back_dropped`); новый тракт compose не зовёт | **да, текст ANSWER_SYS всё ещё учит поле `ask`** — конфликт с «в новом тракте ask_back нет» |
| Ответ после SQL | да, формулировка | `ANSWER_SYS` + user body | нужен к B4; чистить `ask` и MUST в user-body |
| Отказ / coverage | да | REFUSE / COVERAGE | живы; для one-path ок |

### 3.2. Дословные находки по аспекту

**A. Меню — промпт мёртв, путь живой в коде**

`CLARIFY_SYS` дословно:

> «Ask the person ONE short question… Describe each option in plain business words… Never show table names, codes or internal identifiers.»

Вызовов нет. Живое меню — нумерованные строки `N. {вопрос}: {подпись}? — {hint}` без модели. Для B3/B4 **возвращать модель в меню — регресс** относительно приказа «единый построитель ДО SQL».

**B. ANSWER_SYS всё ещё проектирует ask_back**

Дословно (`z18:58–69`):

> `"ask": "one clarifying question, or null"`  
> `"ask" is the middle road between answering and giving up. Fill it ONLY when…`

Код legacy читает это (`_ask_back`) и затем обнуляет. В новом тракте ask_back запрещён контрактом. Значит к B4: либо вычистить поле из схемы и абзац, либо перестать парсить `ask` (второе уже почти сделано сбросом — но промт продолжает тратить токены и провоцировать «уточнение после ответа»).

**C. «Одно число» в промте нет — и не должно появиться как запрет**

ANSWER_SYS говорит про placeholders и «listing … in addition to» total. Ограничение ролей — в `slot_mode` (`count` снимает sum/max/min из known). Кандидат «добавить в промт NEVER state two totals» — **против** правила 03.08. Закрытие — код B4 (тот же slot_mode / atoms).

**D. Count без меры — в INTENT уже описано форматом**

> `"measure": "… null if the question asks about no quantity"`  
> `want = "count" when they ask how many records`

Нехватка не в промте, а в проводке B4 (флаг `count_no_measure_menu` пока только diag).

**E. User-body compose несёт долженствования (не system, но уходит модели)**

Дословно (`z18:842–860`):

> `You MUST warn the user about this…`  
> `You MUST say this in your answer…`

Это правила в тексте для модели. Часть уже дублируется кодом (`ensure_answer_passport`, folders/coverage slots). Для B4: оставить **описание слотов** (`{missing}`, `{folders}`), убрать MUST — иначе снова «правило на промте».

**F. WIKI: модели дают platform kind (мета-слой 1С)**

User card lines: `platform: …` (`wiki_format_card_lines`). Это **не** клиентское меню (меню режет meta из label), а вход модели для выбора. Для аспекта меню — ок. Риск: модель выберет по слову «регистр» vs «документ»; это смысл вики, не подпись человеку.

**G. AXIS_PICK вне нового скелета**

Новый `answer()` ось через модель не выбирает; при >1 reading — меню. Если B4 сделает ось ещё одним видом reading из данных, `AXIS_PICK_SYS` может остаться legacy-only. Не чистить до замера rank на one-path.

**H. INTENT: «ALWAYS fill this» у kind**

> `"kind": "ALWAYS fill this: …"`

Долженствование в схеме. Код уже терпит null/мусор типами. Кандидат смягчения: убрать ALWAYS, оставить описание поля — низкий приоритет, не блокер B3.

**I. Нет отдельного промпта «опиши прочтения из вики»**

И не нужен: подписи readings — `_reading_human_label`; entity-меню — `wiki_menu_captions`. Текст модели здесь был бы второй построитель → против «один построитель».

---

## 4. Вердикты по каждому промпту

### `INTENT_SYS` — оставить (мелкий чистка-кандидат)

- Нужен обоим трактам; формат JSON проверен замерами intent.
- Аспект B3/B4: want/measure уже покрывают count-без-меры.
- Чистить (низкий приоритет): слово `ALWAYS` у kind; опционально добавить `period2` в схему (код уже читает — сейчас модель не инструктирована форматом period2).
- Риск правки: **высокий** на живых ответах (разбор входа). Без замера intent bench — не трогать.

### `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` — оставить

- Ядро one-path (шаг вики).
- Формат минимальный, без запретов клиенту.
- Чистить не по аспекту меню.
- Добавить в `OUR_PROMPTS` — отдельный safe-кандидат (leak), не меняя текст.
- Риск правки текста: **высокий** (каскад сущности).

### `AXIS_PICK_SYS` — оставить до решения по rank в one-path

- Жив только legacy rank.
- Для меню-прочтений не нужен.
- Снос после flip+замера, что ось = reading из данных.
- Риск правки сейчас: средний (ломает legacy rank).

### `CLARIFY_SYS` — снести (или пометить dead) вместе с `clarify_text`

- Аспект: **не возвращать**. Меню = код.
- Действие: удалить константу + функцию; убрать из `OUR_PROMPTS` (leak на мёртвый текст не нужен).
- Риск для живых ответов: **нулевой** (0 вызовов). Риск только если кто-то снова подключит LLM-clarify.

### `REFUSE_SYS` — оставить

- Нужен no_data на обоих трактах.
- Цифры режет код — согласовано с правилом промтов.
- Не трогать без замера отказов.

### `ANSWER_SYS` — чистить к B4 (не сейчас на живом legacy без плана)

Дословные кандидаты на вырезание:

1. Весь блок `"ask"` в JSON-схеме и абзацы `z18:62–69` про clarifying question.  
   Почему: новый тракт запрещает ask_back; меню — до SQL другим механизмом.
2. Смягчить `🔴 NEVER WRITE A COMPUTED FIGURE…` → описание формата: «aggregates only as placeholders listed under COMPUTED/GROUPS/PAIRS» (без NEVER как запрета; запрет уже в `_fill_figures`/`copied_figures`/`gate`).
3. Строка про listing «in addition to» total — при slot_mode=count/sum код и так ведёт; не усиливать вторым итогом в промте.

Риск правки на **текущем** legacy: **высокий** (приёмка на compose). На новом тракте до вызова compose — риск 0; править лучше **в волне B4** вместе с подключением compose, с замером.

Формулировка-кандидат (без долженствований), только формат:

```
You answer using ONLY the rows and placeholders given below.
Reply with JSON only:
{"text": "answer for the user",
 "claims": {"total": null, "count": null, "max": null, "min": null}}

"text" is in the same language as the question.
Aggregates appear only as the placeholders listed later (COMPUTED / GROUPS / PAIRS).
Values inside a single row (names, numbers, dates of that row) are copied from the row.
"claims" stay null (compatibility).
If the rows do not bear on the question, say there is no data.
Be short and businesslike.
```

Одно число / запрет ask_back / предупреждение о неполноте — **не** в этом тексте: слоты + пост-обработка кодом.

### User-body `compose` (не константа) — чистить MUST к B4

- Заменить `You MUST warn…` / `You MUST say…` на: «placeholders `{missing}` / `{folders}` are available for this answer shape».
- Риск: средний (часть ответов перестанет упоминать неполноту, если код не допишет) — сначала проверить, что passport/folders уже дописываются кодом.

### `COVERAGE_SYS` — оставить

- Отдельный путь about=coverage; в новом тракте после wiki.
- Просит цифры в тексте (не слоты) — исторически так; гейт по census. Не блокер меню/count.
- Не унифицировать со слотами без замера coverage.

### `ARBITRATE_SYS` (inline) — снести при уборке мёртвого кода

- 0 вызовов; one-path арбитром не пользуется (меню tie).
- Риск ответов: 0.

---

## 5. Итог

### 5.1. Правки-кандидаты

| # | промпт / место | строка (ориентир) | действие | риск для живых ответов |
|---|---|---|---|---|
| 1 | `ANSWER_SYS` | `z18:58–69` | вырезать поле `ask` и абзацы про clarifying ask_back | высокий на legacy; **делать в B4** с замером compose |
| 2 | `ANSWER_SYS` | `z18:71–73` | заменить NEVER-блок описанием placeholders (формат, не запрет) | высокий на legacy; B4 |
| 3 | `compose` user-body | `z18:842–860` | убрать MUST; оставить факт наличия слотов | средний; нужен замер coverage/folders в ответе |
| 4 | `CLARIFY_SYS` + `clarify_text` | `z07:285–311` | снести; убрать из `OUR_PROMPTS` | **нулевой** на ответы |
| 5 | `ARBITRATE` inline + `arbitrate` | `z01:602–627` | снести мёртвый код | **нулевой** |
| 6 | `OUR_PROMPTS` | оба z20 ~755 | добавить `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` | низкий (только leak-детектор) |
| 7 | `INTENT_SYS` | kind «ALWAYS fill» ~811 | убрать ALWAYS (описание поля) | средний; только с intent bench |
| 8 | `INTENT_SYS` | схема JSON | опционально описать `period2` как код уже парсит | средний |

**Не предлагается** (закрыто кодом или вредно правилом 03.08):

- новый промпт для readings-меню;
- новый промпт «одно число»;
- новый промпт «count без меры»;
- воскрешение `CLARIFY_SYS` для подписей;
- правила «Never show table names» в wiki/answer (меню уже чистит код).

### 5.2. Не трогать

| что | почему |
|---|---|
| `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` текст | живой каскад one-path; формат уже минимальный |
| `REFUSE_SYS` | живые отказы; цифры режет код |
| `COVERAGE_SYS` | живой coverage; гейт по census |
| `INTENT_SYS` ядро схемы (terms/want/measure/…) | вход всего тракта; без bench не трогать |
| `AXIS_PICK_SYS` до решения rank-on-one-path | legacy rank жив |
| Живой `clarify_say` / `wiki_menu_captions` / `readings_menu` | это и есть «один построитель»; не заменять промптом |
| Слотная механика `_fill_figures` / `slot_mode` | держат «одно число» и count без меры лучше любого текста |

### 5.3. Сжатый вывод линзы

Для B3/B4 **не хватает не новых промптов, а чистки старого хвоста ответа**: поле `ask` в `ANSWER_SYS` и MUST в user-body compose. Меню прочтений, подписи из вики, count-без-меры и «одно число» либо уже в коде, либо должны остаться в коде волны B4 — не в тексте для модели. Единственный мёртвый clarify-промпт можно снести без риска для ответов; вики-промпты — оставить и лишь включить в leak-список.
