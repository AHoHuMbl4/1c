# L6 — независимая линза: `prompt_leak` / `OUR_PROMPTS`

Статический аудит промптов тракта ask. Код не менялся. Чужие отчёты
`docs/audit/onepath/*` не читались. Дата среза исходников: 12.09.2026.

**Аспект:** полнота списка системных сообщений против реального множества;
какие `*_SYS` не в списке (утечка инструкции в ответ не ловится);
симметрия запретов метаданных 1С между промптами.

Метод `prompt_leak` (`z19_answer_check.py:205`): нормализует пробелы в
ответе клиенту, затем ищет **точное** вхождение любой строки из наших
system-промптов длиной ≥40 символов. Список якорей — `OUR_PROMPTS` в
`z20_ask_main_http.py:755` и зеркально в `_legacy.py:761`.

---

## 1. Реестр промптов (свой, по grep)

Поиск: константы `*_SYS` / `*_PROMPT` / `*_HINT`; `role: system`; вызовы
`ds_chat` в `ubuntu/serenedb/ask/*.py` (без `work/z21wt`).

`*_PROMPT` / `*_HINT` как system-константы **не найдены**. User-роли
собираются рядом с каждым вызовом (см. колонки).

| имя | файл:строка | длина (симв.) | leakable строк ≥40 | вызовы `ds_chat` | тракт | жив/мёртв | поля ответа, читаемые кодом |
|---|---|---:|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3239 | 39 | `parse_intent` → `_one_intent` (`z02:567/575`) | оба (новый z20 зовёт `parse_intent`) | **жив** | JSON: `terms`, `amount`, `period`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form` (+ retry user «Return the JSON object.») |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 | 8 | `rank_axis_pick` (`z10:211`) | legacy (+ rank, если дойдут); новый stub SQL ещё не доходит | **жив** (путь rank) | JSON `axes: [int]` → col; fallback цифры из текста |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 | 6 | только внутри `clarify_text` (`z07:308`) | — | **мёртв** | был бы сырой текст уточнения; **вызовов `clarify_text(` в дереве 0** (живое меню — `clarify_say`, без модели) |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 282 | 4 | `refuse_text` (`z07:341`) | оба | **жив** | одна фраза; цифры вырезаются кодом (`_norm_numbers`) |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 | 30 | `compose` (`z18:876`) | **legacy** (`z20_…_legacy` ~4109/4186); новый z20 `compose`/`ask_back` **не зовёт** (stub B4) | **жив в legacy** / ожидает SQL-волну в новом | `_split_answer` → `text`,`claims`; `_ask_back` → `ask` |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` (= legacy:742) | 891 | 11 | `_coverage_answer` (`z20:795` / legacy:801) | оба | **жив** | `_split_answer` → `text`,`claims`; затем `gate` + `prompt_leak` |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 247 | 3 | `wiki_pick_from_cards` (`z21:799`) | оба (wiki-каскад) | **жив** | JSON `choice`, `separable` → `src_table` / clarify |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 443 | 5 | `wiki_verify_candidates` (`z21:738`) | оба | **жив** | JSON `verdicts[]`: `index`,`fit`,`why` (why хранится, в клиентский `text` не кладётся) |
| `ARBITRATE` (inline `sys_msg`) | `z01_infra_trace_llm.py:607` | 391 | 1 (после склейки) | `arbitrate` (`z01:618`) | — | **мёртв** | только цифра 1…N; **вызовов `arbitrate(` вне определения нет** (`test_no_pre_wiki_reorders` это сторожит) |

### `OUR_PROMPTS` сейчас

```text
[INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS]
```

Одинаково в новом и legacy z20. Комментарий рядом: «Все НАШИ системные
сообщения в одном месте».

### Где `prompt_leak` реально зовётся

| место | что проверяет |
|---|---|
| `gate_out` (`z20:257` / legacy:262) | любой текст «словами модели» через общий гейт (в т.ч. `clarify_say`) |
| `_coverage_answer` (`z20:821` / legacy:827) | текст coverage после модели |
| legacy compose-ветка (`legacy:4164`, `:4224`) | `text` / retry `text2` ответа |
| новый `answer` stub | до compose не доходит; coverage и `gate_out` на clarify — да |

### Точки `ds_chat` (исчерпывающе в ask/)

1. `z01:618` — arbitrate (мёртв)
2. `z02:567/575` — intent
3. `z07:308` — clarify (мёртв)
4. `z07:341` — refuse
5. `z10:211` — axis pick
6. `z18:876` — compose/answer
7. `z20:795` / legacy:801 — coverage
8. `z21:738` — wiki verify
9. `z21:799` — wiki pick

Инфра: `ds_chat` / `ds_chat_post` / `_ds_chat_body` — `z01_infra_trace_llm.py:549+`.
Эмбеддер/реранкер — не промпты DeepSeek system; в реестр SYS не входят.

### User-части (рядом с каждым живым system)

| system | user-сборка |
|---|---|
| INTENT | `today=YYYY-MM-DD\n\nQuestion: …` (`z02:667`); retry assistant+user |
| AXIS | `{question} ({kind})\n\nAxes:\n1. label…` (`z10:214`) |
| REFUSE | сырой `question` (`z07:342`) |
| ANSWER | длинный body: `QUESTION` + `ROWS`/`GROUPS` + `COMPUTED…` + опц. coverage/folders/corrections (`z18:719–875`) |
| COVERAGE | `{question}\n\nCensus:\n…` (`z20:796`) — в census имена `entity` из `search_coverage` |
| WIKI_PICK | `{question} ({kind})\n\nCards:\n` + `wiki_format_card_lines` (name/description/**platform**/axes/measures) |
| WIKI_VERIFY | то же + `wiki_format_passport_lines` (wiki body до 1500, platform, doesNotAnswer; хвост может назвать `src_table`) |

---

## 2. Анализ по аспекту `prompt_leak` / `OUR_PROMPTS`

### 2.1 Дыра полноты списка

Комментарий обещает **все** наши system. Фактически вне списка:

| отсутствует | leakable ≥40 | клиентский текст из ответа модели? | риск необнаруженной утечки |
|---|---:|---|---|
| `WIKI_PICK_SYS` | 3 | нет (код читает только JSON-индекс) | **низкий по доставке**, **высокий по контракту детектора**: эхо инструкции в `text` clarify/refuse/coverage **не** поймается, если модель когда-нибудь смешает роли |
| `WIKI_VERIFY_SYS` | 5 | `why` не уходит в `text` ответа | то же |
| `ARBITRATE` inline | 1 | ответ — цифра, в выдачу не попадает; путь мёртв | сейчас нулевой; при оживлении без записи в `OUR_PROMPTS` — дыра |

Дословные leakable-якоря, которые **сейчас не мониторятся**:

```text
# WIKI_PICK_SYS
Map the user's question to one numbered entity card, or 0.
Each card shows: name, description, platform kind, axes, measures (same fields for all).
{"choice": <1-based card index or 0>, "separable": <true|false>}

# WIKI_VERIFY_SYS
Assess each numbered entity passport against the user question.
Each passport shows: name, wiki excerpt, platform kind, axes, measures,
traits present only in this passport vs pool neighbors;
doesNotAnswer lists topics marked outside entity coverage.
{"verdicts": [{"index": <1-based passport index>, "fit": <"yes"|"no"|"unsure">,
```

Замечание по порогу: короткий `"Reply with one JSON object only:"` (<40) и
аналоги в INTENT (`"Reply with JSON only."`) **намеренно** не ловятся —
это подтверждает `test_gate.py:191`. Детектор ловит характерные длинные
строки, не общие клише.

### 2.2 Мёртвый якорь внутри списка

`CLARIFY_SYS` **в** `OUR_PROMPTS`, но `clarify_text` нигде не вызывается.
Живое меню — `clarify_say` / `format_clarify_options` / `wiki_menu_captions`
(данные → строки → `gate_out`). Для leak-детектора мёртвый текст безвреден
(лишний якорь). Для «полноты vs реальность» он создаёт обратную асимметрию:
в списке есть то, чего модель больше не получает, и нет того, что получает
(wiki).

Дословный запрет метаданных в мёртвом промте (единственный явный среди SYS):

```text
Describe each option in plain business words, using its name and what is typical for
its records. Never show table names, codes or internal identifiers.
```

### 2.3 Симметрия запретов метаданных (п. подписи меню / п.19)

| промт | запрет table/codes/metadata в тексте для человека | что модель реально видит |
|---|---|---|
| `CLARIFY_SYS` | **да** («Never show table names…») | мёртв; живое меню держит **код** (`label_has_meta_src` / `human_table_label`) |
| `ANSWER_SYS` | **частично**: запрет только для поля `"ask"` — «Never ask about our database, tables or fields»; в `"text"` явного запрета имён таблиц **нет** | строки корпуса (`doc`), не схема |
| `COVERAGE_SYS` | **нет** | census с полем `entity` (может быть тех. именем) + «Name the kinds of records that are missing» |
| `REFUSE_SYS` | н/п (данных нет) | только вопрос |
| `INTENT` / `AXIS` / `WIKI_*` | н/п (не клиентская проза) | AXIS — метки осей; WIKI — **platform kind** («документ», «регистр накопления»…) и иногда `src_table` в хвосте паспортов |

Вывод по симметрии: запрет «не светить метаданные клиенту» **не**
равномерно размазан по промтам. Живое меню уже ушло в код (правильно по
правилу 03.08). Слабое место для **промтовой** симметрии — не меню, а
`COVERAGE_SYS` + user-census и user-часть wiki (platform/src_table в модель,
не в клиента). Добавлять новый запрет в промт **не** рекомендуется
(правило проекта: запреты — кодом). Кандидат — нормализация имён в census
**до** модели / до ответа, не правка текста SYS.

### 2.4 User-роль вне `OUR_PROMPTS` (смежный пробел детектора)

`prompt_leak` смотрит только system из списка. В `compose` в **user** уходят
длинные английские инструкции, которых в `OUR_PROMPTS` нет. Если модель
скопирует их в `"text"`, детектор **не** сработает. Примеры (≥40):

```text
COMPUTED OVER ALL MATCHING ROWS. The values are not shown; each
placeholder below is replaced by the system with the exact figure:
GROUPS EXCLUDED: … MUST say this in your answer…
YOUR PREVIOUS ANSWER WAS REJECTED BY A VERIFIER: …
QUANTITY USED: the figures above are computed over the quantity named …
```

Это не «дыра SYS-списка», но та же ось: утечка **нашей** инструкции.
Практический риск средний (гейт чисел часто режет мусор; фразы без цифр
могут пройти). Расширять `OUR_PROMPTS` user-литералами — отдельное решение
(сейчас API списка = system).

### 2.5 Вердикты по каждому промту (только аспект leak/запреты)

| промт | вердикт | почему | риск правки для живых ответов |
|---|---|---|---|
| `INTENT_SYS` | **оставить** | в списке; ответ не клиентский; живой разбор проверен приёмкой | любая чистка JSON-схемы — высокий регресс intent |
| `AXIS_PICK_SYS` | **оставить** | в списке; ответ — индексы | чистка формулировок — средний (rank) |
| `CLARIFY_SYS` | **кандидат сноса контура** (константа+`clarify_text`+запись в `OUR_PROMPTS`) | 0 вызовов; запрет метаданных дублирует код меню | **нулевой** для ответов, пока вызывающих нет; снос из `OUR_PROMPTS` без сноса функции — только косметика детектора |
| `REFUSE_SYS` | **оставить** | в списке; коротко; код режет цифры | правка тона — средний (язык отказа) |
| `ANSWER_SYS` | **оставить ядро; чистить блок `"ask"` при one-path** | в списке; ask_back в legacy ещё читается, но в новом тракте ask_back запрещён контрактом; запрет tables только у `ask` | вырезание `"ask"` без замера — **высокий** на legacy, пока flip не сделан; после flip — средний |
| `COVERAGE_SYS` | **оставить SYS; симметрию — кодом** | в списке; запрет table names в промт не добавлять | правка SYS без замера — средний (coverage-ветка приёмки) |
| `WIKI_PICK_SYS` | **добавить в `OUR_PROMPTS`** (не чистить текст без замера) | живой system вне списка | добавление в список — **нулевой** для ответов (только детект) |
| `WIKI_VERIFY_SYS` | **добавить в `OUR_PROMPTS`** | то же | то же |
| `ARBITRATE` | **не трогать / не возвращать**; при оживлении — константа + `OUR_PROMPTS` | мёртв; сейчас вне списка | н/п |

---

## 3. Итог

### 3.1 Правки-кандидаты

| # | промт / место | строка | действие | риск для живых ответов |
|---|---|---|---|---|
| K1 | `OUR_PROMPTS` (z20 + legacy) | `:755` / `:761` | **добавить** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` | нулевой (только leak-детект); обновить `test_gate`, если появятся якоря |
| K2 | `CLARIFY_SYS` + `clarify_text` | z07:285–311 | **снести** мёртвый контур **или** явно пометить dead и оставить якорь; если снос — убрать из `OUR_PROMPTS` тем же коммитом | нулевой для deliverable |
| K3 | `ANSWER_SYS` поле `"ask"` + абзац middle-road | z18:59–69, 88 | **чистить при one-path flip**: убрать схему `ask` и инструкции про уточнение после ответа (контракт: меню единым построителем ДО SQL, без ask_back) | высокий на legacy до flip; после — средний; нужен замер compose |
| K4 | user-инструкции `compose` (`COMPUTED…`, `VERIFIER…`) | z18:756–869 | **опционально**: либо вынести повторяемые ≥40 в якоря leak (отдельный список), либо не трогать и принять, что user-эхо не ловится | расширение детектора — низкий; правка текста user — средний |
| K5 | `COVERAGE` census `entity` | z20:792–794 | **не** править SYS; при симметрии подписей — человеческие имена **кодом** до модели | средний, нужен замер coverage |
| K6 | `ARBITRATE` inline | z01:607 | не оживлять без именованной константы + записи в `OUR_PROMPTS` | н/п |

### 3.2 Не трогать

| что | почему |
|---|---|
| Текст `INTENT_SYS` | живой вход всего тракта; в `OUR_PROMPTS`; правка без замера intent — прямой регресс |
| Текст `AXIS_PICK_SYS` | узкий JSON; в списке; поведение rank замерено |
| Текст `REFUSE_SYS` | короткий; цифры режет код; в списке |
| Ядро `ANSWER_SYS` (placeholders / NEVER WRITE FIGURE / language) | держит форму ответа; числа уже кодом; чистить только блок `ask` (K3), не всю константу |
| Текст `COVERAGE_SYS` целиком | в списке; цифры + gate; запрет метаданных сюда словами не добавлять |
| Текст `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` | живой каскад; менять формулировки только с замером wiki; сейчас достаточно включить в `OUR_PROMPTS` |
| `prompt_leak` / порог `min_len=40` | устройство верное (код, не промт); менять порог без нужды нельзя — ложные срабатывания на общие фразы |
| Живой `clarify_say` | не промт; возвращать LLM-clarify против приказа one-path |

### 3.3 Одна фраза вердикта линзы

`OUR_PROMPTS` **неполон**: два живых wiki-system вне списка (утечка их строк
клиенту детектором не ловится), плюс мёртвый `CLARIFY_SYS` внутри списка;
симметрия «не светить метаданные» живёт в коде меню, а не в промтах —
слабое место coverage/census, не `CLARIFY_SYS`.
)
