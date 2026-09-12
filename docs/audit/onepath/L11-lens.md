# L11 — независимая линза: полный аудит промптов тракта ask

**Дата:** 12.09.2026  
**Метод:** свой grep-реестр по `ubuntu/serenedb/ask/*.py` → чтение каждого system/user вызова целиком → оценка качества / лишнего / опасного / мёртвого. Чужие отчёты `docs/audit/onepath/*` не читались.  
**Ограничение:** только чтение исходников + этот файл; код/БД/модель/git-мутации не трогались.

**Инфраструктура вызова:** единственный чат-шлюз — `ds_chat` / `ds_chat_post` в `z01_infra_trace_llm.py` (DeepSeek `DS_MODEL`, по умолчанию `deepseek-v4-pro`). Эмбеддер и `rerank` — не промпты чата; в реестр не входят.

**Тракты:**
- **legacy** — `z20_ask_main_http_legacy.py` (полный `answer` до flip);
- **новый (onepath)** — `z20_ask_main_http.py` (`answer` = intent → readings → wiki → меню; SQL — заглушка B4).

---

## 1. Реестр промптов (независимый)

| Имя | Файл:строка | Длина (симв.) | Кто вызывает | Тракт | Жив/мёртв | Поля ответа, которые читает код |
|---|---|---:|---|---|---|---|
| `INTENT_SYS` | `z01_infra_trace_llm.py:800` | 3239 | `parse_intent` → `_one_intent` (`z02_intent.py:566–582, 666–672`); retry user `"Return the JSON object."` | оба (новый и legacy зовут `parse_intent`) | **жив** | JSON: `terms`, `amount`/`op`/`value`/`value2`, `period`/`from`/`to`, `want`, `measure`, `kind`, `about`, `action_class`, `action_axis`, `search_form`; код ещё ждёт `period2` (в schema промта **нет**). Нормализация `_normalize_intent` |
| `WIKI_PICK_SYS` | `z21_wiki_choice.py:45` | 247 | `wiki_pick_from_cards` (`:785–802`) из каскада `try_wiki_hybrid_entity_pick` | оба | **жив** | `choice` (int), `separable` (bool; AND с kNN gap кодом) |
| `WIKI_VERIFY_SYS` | `z21_wiki_choice.py:50` | 443 | `wiki_verify_candidates` (`:723–742`) | оба | **жив** | `verdicts[].index`, `fit` (`yes`/`no`/`unsure` + RU-алиасы), `why` (обрезка 200; на исход почти не влияет — решает `fit`) |
| `AXIS_PICK_SYS` | `z10_rank.py:136` | 598 | `rank_axis_pick` ← `rank_axis_resolve` (`:190–265`); из legacy `z20_…_legacy.py:3609` | **только legacy** (новый `answer` до SQL не доходит) | **жив в legacy** | JSON `axes` (1-based индексы) или salvage `\d+`; код берёт ≤3 col |
| `ANSWER_SYS` | `z18_compose.py:55` | 2456 | `compose` (`:655–877`); legacy `answer` `:4109`, retry `:4186` | **только legacy** | **жив в legacy** | `_split_answer` → `text`; `_ask_back` → `ask` (далее почти всегда сбрасывается); `claims` парсятся, но промт велит null / «ignored» |
| `COVERAGE_SYS` | `z20_ask_main_http.py:736` **и** дубль `z20_…_legacy.py:742` | 891 (md5 одинаков) | `_coverage_answer` | оба (новый — **после** wiki) | **жив** | `_split_answer` → `text` + `claims`; гейт чисел + `prompt_leak` |
| `REFUSE_SYS` | `z07_rrf_vectors.py:317` | 282 | `refuse_text` (`:323–345`); много веток no_data / calendar / wiki | оба | **жив** | весь текст; цифры вырезаются `_norm_numbers` → пусто |
| `CLARIFY_SYS` | `z07_rrf_vectors.py:285` | 439 | только внутри `clarify_text` (`:295–311`) | — | **мёртв** (`clarify_text(` в дереве ask — 0 вызовов; меню = `clarify_say` / `wiki_menu_captions` / `readings_menu`) | был бы сырой текст уточнения |
| `ARBITRATE_SYS` (inline `sys_msg`) | `z01_infra_trace_llm.py:607–613` | 391 | `arbitrate` (`:602–628`) | — | **мёртв** (вызовов `arbitrate(` в `ask/` нет; живой выбор сущности — wiki) | цифры из ответа → индекс 0-based или `None` |

**Вспомогательные user-фрагменты (не `*_SYS`, но часть контракта с моделью):**

| Место | Содержание | Читает код |
|---|---|---|
| `z02`: user `today=…\nQuestion:…` | дата + вопрос | через INTENT JSON |
| `z02`: retry `"Return the JSON object."` | жёсткий повтор формата | то же |
| `z21`: `Cards:` / `Passports:` | name, description/wiki, **platform**, axes, measures, distinct, doesNotAnswer; хвост «Other pool names» | choice / verdicts |
| `z10`: `Axes:` нумерованный список меток | метка ± `(col)` | индексы → col |
| `z18` `compose` body | QUESTION + ROWS/GROUPS + COMPUTED-плейсхолдеры + MUST-оговорки coverage/folders/measure/corrections | text/ask/claims |
| `z20` coverage user | Census: агрегаты + строки `entity: in_1c, in_search — reason` | text/claims |
| `z01` arbitrate user | Question + Answers listing + optional context[-2000:] | digit |

**`OUR_PROMPTS` (leak-детектор `prompt_leak`, порог строки ≥40):**  
`INTENT_SYS, AXIS_PICK_SYS, CLARIFY_SYS, REFUSE_SYS, ANSWER_SYS, COVERAGE_SYS`  
— **нет** `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS`, inline arbitrate. Дублируется в новом и legacy z20.

---

## 2. Анализ по аспекту (целиком, с дословными строками)

Метод оценки: (а) соответствие роли модели (смысл, не счёт/поиск); (б) формат vs запреты в промте; (в) согласованность с кодом и «одним путём»; (г) риск регрессии при правке.

### 2.1 `INTENT_SYS` — оставить основу; точечная чистка схемы

**Сильное:** язык-нейтральный JSON-контракт; `kind`/`terms`/`about`/`action_*` хорошо разводят смысл; «Never invent concepts…» совпадает с п.12 и уже подкреплено нормализацией/assumed в коде.

**Лишнее / опасное:**
- Блок `Rules:` длинный; часть — формат (нужно), часть — поведенческие запреты, которые код и так чинит (`terms` vs `kind`). Правило 03.08: новые запреты в промт не добавлять; существующие «NEVER put KIND…» работают как описание слота — трогать без замера нельзя (intent — самый чувствительный вход).
- Schema `amount.op` дословно: `">"|"<"|">="|"<="|"between"|null` — **нет `"="`**, тогда как `_AMOUNT_OPS` в том же файле включает `"="` (замер нулевой суммы в комментарии `:876–880`). Расхождение schema↔код: модель может не выдать `=` или выдать вне списка.
- `period2` есть в `_INTENT_FIELDS` и нормализаторе, **в промте поля нет** — мёртвый/скрытый слот.
- `want` не включает rank/max/min (rank выводится кодом из вопроса) — ок по устройству, но в промте это не сказано; путаница при чтении, не баг.

**Вердикт:** оставить; кандидат правки — добавить `"="` в schema `op` (и при желании `period2` одной строкой). Риск: средний (меняет разбор порогов) → только с прогоном intent-bench / приёмкой.

### 2.2 `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS` — оставить; leak и user-payload

**Сильное:** короткие, ровно под код; выбор — индекс, не проза; verify даёт `fit`, `why` почти декоративен. Согласуется с «вики → меню → SQL».

Дословно pick:
> `Map the user's question to one numbered entity card, or 0.`  
> `{"choice": <1-based card index or 0>, "separable": <true|false>}`

Дословно verify:
> `Assess each numbered entity passport against the user question.`  
> `{"verdicts": [{"index": …, "fit": <"yes"|"no"|"unsure">, "why": <one line>}]}`

**Риски:**
1. User-часть несёт `platform:` / `axes:` / `measures:` (и хвост имён пула). Это не схема БД, но метаданные платформы 1С уходят в модель — для сопоставления со слоями вики оправдано; для меню человеку уже режется `wiki_menu_captions` без LLM. Не чистить в промте «не показывай platform» — сломает выбор; держать кодом (уже `filter_pool_by_named_type`).
2. `WIKI_*` **вне** `OUR_PROMPTS` → утечка длинной строки verify/pick в клиентский текст не ловится `prompt_leak`.
3. Бюджет verify: `WIKI_VERIFY_MAX_TOKENS=2048`, body до `1500×N` — не растёт с размером базы линейно, но тяжёлый; п.19 в духе «маленький контекст» здесь напряжённее остальных шагов.

**Вердикт:** оставить тексты; кандидаты — добавить в `OUR_PROMPTS`; не ужимать passport без замера wiki.

### 2.3 `AXIS_PICK_SYS` — оставить в legacy; в onepath пока вне пути

Дословно: `You map a user's question to a grouping axis.` / `{"axes": [numbers]}`.

**Хорошо:** только индексы; «inventing axis names is outside this step».  
**Слабое в user-сборке (код, не SYS):** `rank_axis_label_rows` может дать `"%s (%s)" % (lab, col)` — колонка уходит в модель. Это риск п.19/подписей, чинится в formatter’е осей, не в SYS.

**Вердикт:** SYS не трогать. При волне B (меню осей до SQL) — решить, остаётся ли LLM-ось или только `readings_menu`; до замера не сносить.

### 2.4 `ANSWER_SYS` — чистить под «один путь» (высокий приоритет после B4)

Дословно конфликт с приказом 12.09:
> `"ask": "one clarifying question, or null"`  
> `"ask" is the middle road between answering and giving up…`

В legacy `_ask_back` читает `ask`, затем `ask_back` сбрасывается (`bare_clarify_forbidden` / `canon_locked`). Промт **просит** то, что код **убивает** → лишние токены, двусмысленность роли, риск регрессии если кто-то снимет дроп.

Дословно сильная часть (согласуется с п.19):
> `NEVER WRITE A COMPUTED FIGURE YOURSELF… The system substitutes the placeholders…`

Но рядом: `claims` «leave every role null… ignored» — мёртвый контракт в JSON; COVERAGE наоборот требует цифры в claims (см. ниже).

User-body `compose` добавляет MUST-оговорки (`DATA COMPLETENESS WARNING… You MUST warn…`, folders, quantity name). Это поведенческие правила в user, не в SYS; живут на замерах — править только с gate/compose прогоном.

**Вердикт:** при подключении compose к onepath — убрать/`null`-only контракт `ask` из SYS (и мёртвый `claims`, если гейт coverage/answer согласуют). Риск **высокий** для живых legacy-ответов → только вместе с замком и приёмкой; до flip — не трогать прод-текст без замера.

### 2.5 `COVERAGE_SYS` — оставить поведение; согласовать с ANSWER и дублем

Дословно:
> `State figures in DIGITS, copied from the census — never recompute…`  
> `Put the number of missing rows in "claims.total"…`

Противоположная стратегия чисел, чем у `ANSWER_SYS` (плейсхолдеры). Защита — `gate` + allowed census (в коде явно после F128). Работает, но два стиля в одном продукте.

User census включает `entity` из `search_coverage` — возможны имена сущностей/метаданные в ответе модели (подписи «простыми словами» не гарантированы промтом).

Дубль константы в z20 + legacy — риск рассинхрона при правке одной копии.

**Вердикт:** текст оставить до замера; кандидат — единый модуль константы; в onepath позже — плейсхолдеры как в answer (большая правка).

### 2.6 `REFUSE_SYS` — не трогать

Дословно: `Write ONE short sentence… State no facts, no figures…` + код режет цифры. Коротки, правильная роль. Живой на обоих трактах.

### 2.7 `CLARIFY_SYS` — снести из живого контура (нулевой риск ответов)

Дословно: `Ask the person ONE short question… Never show table names…`  
Вызовов нет; меню строит код (`clarify_say`). В `OUR_PROMPTS` остаётся как якорь leak для мёртвого текста.

**Вердикт:** кандидат удаления константы + `clarify_text` + запись в `OUR_PROMPTS` (или оставить якорь осознанно). На ответы не влияет.

### 2.8 `ARBITRATE` inline — мёртвый; снос безопасен для ответов

Дословно: `Choose the ONE answer… Reply with a single digit…`. Код и так принимает только номер. Нет вызовов. Wiki заменил арбитраж готовых фраз.

**Вердикт:** снести функцию+промт в волне уборки; не раньше, чем убедиться, что тесты/дока не ссылаются как на живой путь.

### 2.9 Сквозные проблемы (не один промт)

| # | Тяжесть | Суть |
|---|---------|------|
| T1 | высокая (контракт onepath) | `ANSWER_SYS.ask` / ask_back vs «меню единым построителем ДО SQL, без ask_back» |
| T2 | средняя (п.19/утечки) | `WIKI_*` и arbitrate вне `OUR_PROMPTS` |
| T3 | средняя (корректность) | `amount.op` без `"="` при живом коде на `=` |
| T4 | средняя (сопровождение) | два файла `COVERAGE_SYS`; мёртвые CLARIFY/ARBITRATE засоряют карту |
| T5 | низкая–средняя | axis labels с `(col)`; coverage entity names — не SYS, а user-сборка |
| T6 | низкая | `claims` в ANSWER мёртв / в COVERAGE жив — разнобой контракта JSON |

---

## 3. Вердикт по каждому промту (сводка)

| Промт | Вердикт | Риск правки для живых ответов |
|---|---|---|
| `INTENT_SYS` | оставить; чистить schema (`=` / опц. `period2`) | средний → нужен intent-замер |
| `WIKI_PICK_SYS` | оставить как есть | высокий при смысловой правке; низкий при добавлении в `OUR_PROMPTS` |
| `WIKI_VERIFY_SYS` | оставить как есть | высокий при урезании; низкий — leak-список |
| `AXIS_PICK_SYS` | оставить; user-метки — отдельно | средний (только legacy rank) |
| `ANSWER_SYS` | чистить (`ask`, согласовать `claims`) **после/вместе с onepath compose** | **высокий** на legacy |
| `COVERAGE_SYS` | оставить; потом унификация с answer | средний |
| `REFUSE_SYS` | **не трогать** | — |
| `CLARIFY_SYS` | снести (мёртвый) | нулевой на ответы |
| `ARBITRATE` inline | снести (мёртвый) | нулевой на ответы |

---

## 4. Итог: правки-кандидаты и «не трогать»

### 4.1 Кандидаты (промт | где | действие | риск)

| # | Промт / место | Действие | Риск |
|---|---|---|---|
| C1 | `ANSWER_SYS` `:57–69` (`"ask"` / middle road) | Убрать поле `ask` из контракта JSON и абзац про clarifying; меню — только код | высокий на legacy до замера compose/gate; обязателен для onepath |
| C2 | `INTENT_SYS` schema `amount.op` `:805` | Добавить `"="` в перечень (как в `_AMOUNT_OPS`) | средний; закрывает известный кейс нулевой суммы |
| C3 | `OUR_PROMPTS` z20 + legacy | Добавить `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` | низкий (только leak) |
| C4 | `CLARIFY_SYS` + `clarify_text` | Удалить или явно пометить dead; убрать из `OUR_PROMPTS` при полном сносе | нулевой на ответы |
| C5 | `arbitrate` + inline sys_msg | Удалить мёртвый путь | нулевой на ответы |
| C6 | `COVERAGE_SYS` дубль | Одна константа (общий модуль) | низкий при идентичном тексте |
| C7 | `ANSWER_SYS` `claims` / `COVERAGE_SYS` claims | Согласовать один числовой контракт (плейсхолдеры vs digits) | высокий; только с гейт-замером |
| C8 | `INTENT_SYS` | Опционально описать `period2` или убрать из `_INTENT_FIELDS` | низкий–средний |
| C9 | `rank_axis_label_rows` (не SYS) | Не клеить сырой `col` в метку для модели | средний на rank-оси |

### 4.2 Не трогать (сейчас)

- **`REFUSE_SYS`** — короткий, код добивает цифры; живой fallback.
- **Тела `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS`** — без wiki-прогона не ужимать и не «улучшать» формулировками запретов.
- **`AXIS_PICK_SYS` текст** — пока legacy rank зелёный; не сносить «на будущее».
- **Крупные MUST в user-body `compose`** (coverage/folders/measure) — держатся замерами гейта; вынос в код = отдельный эпизод.
- **Многократный `INTENT_SAMPLES` / memo** — не промт, но не ломать «для упрощения».
- **Любая правка живых SYS без замера** — явно запрещена задачей и историей приёмки.

### 4.3 Карта «что реально зовёт модель» на срезе 12.09

```
новый answer:     INTENT → (WIKI_PICK и/или WIKI_VERIFY) → REFUSE? → COVERAGE?
                  (+ меню без LLM)
legacy answer:    INTENT → WIKI_* → AXIS_PICK? → ANSWER(compose±retry) → REFUSE?/COVERAGE?
мёртвое:          CLARIFY_SYS, ARBITRATE
```

---

## 5. Заключение линзы

Реестр замкнут: **9 system-текстов** (8 констант + 1 inline), из них **2 мёртвых** (clarify, arbitrate), **1 legacy-only тяжёлый** (ANSWER), **wiki+intent+refuse+coverage** — общий каркас обоих трактов.

Главный структурный дефект промпт-слоя относительно приказа «один путь» — не wiki и не refuse, а **`ANSWER_SYS`, который всё ещё учит модель задавать `ask`**, при том что меню уже строится кодом, а ask_back в legacy гасится. Вторая по полезности правка с низким риском ответов — **leak-список + мёртвый clarify/arbitrate + `"="` в intent schema**.

Правки в прод-промты — только с замером; этот файл — статический аудит, не патч.
