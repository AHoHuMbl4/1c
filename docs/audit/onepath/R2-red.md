# R2 — красная атака сходимости: 12 линз аудита промптов

**Дата:** 12.09.2026  
**Метод:** чтение L1–L12 → таблица сходимости → сверка спорного с `ubuntu/serenedb/ask/*.py` (файл:строка) → поиск пропущенного всеми → вердикт по каждой правке-кандидату.  
**Ограничения:** код не менялся; чужие R-отчёты не читались; psql не трогался.

**Краткий вердикт красной:** сходимость по мёртвым CLARIFY/ARBITRATE, дыре OUR_PROMPTS без WIKI_*, мёртвому `ask` в ANSWER_SYS и декоративному `why` — высокая и подтверждена кодом. Главные ошибки линз: L2 неверно описала рычаг `separable`; «WIKI_PICK полумёртв» (L1) верно только при успешном verify; `period2` в схеме INTENT почти не влияет на живые compare-ответы (его пишет код). User-утечки техимён (wiki axes/col, coverage entity) — факт кода, не преувеличение L5/L9.

---

## 1. Таблица сходимости

Легенда «независимо?»: **да** = ≥2 линз из разных аспектов/полных повторов; **слабо** = 1 линза или только полные L9–L12 друг с другом без аспектных; **нет** = одна линза.

| # | Вывод | Линзы | Независимо? | Вердикт по коду |
|---|---|---|---|---|
| C1 | `CLARIFY_SYS` / `clarify_text` — мёртв целиком (0 callers); живое меню — `clarify_say` | L1–L12 | **да** | **ПОДТВЕРЖДЕНО.** Определение `z07:285–311`; вызовов `clarify_text(` в ask/ нет (grep). |
| C2 | `arbitrate` + inline sys_msg — мёртв (0 callers); тест сторожит 0 в z20 | L1–L12 | **да** | **ПОДТВЕРЖДЕНО.** `z01:602–628`; callers только определение. |
| C3 | `OUR_PROMPTS` без `WIKI_PICK_SYS` / `WIKI_VERIFY_SYS`; CLARIFY в списке есть | L1–L12 | **да** | **ПОДТВЕРЖДЕНО.** `z20:755`, legacy `:761`. |
| C4 | `ANSWER_SYS` учит поле `"ask"`; код всегда гасит ask_back (`bare_clarify_forbidden`) | L1–L12 | **да** | **ПОДТВЕРЖДЕНО.** Промт `z18:55+`; drop `z20_legacy:4325–4327` (после `canon_locked`). |
| C5 | На answer-пути `claims` не сверяются; на coverage — `check_claims` жив | L1,L2,L4,L8,L9,L10,L11 | **да** | **ПОДТВЕРЖДЕНО.** Комментарий `legacy:4157–4160`; coverage `z20:802` / legacy `:808`. |
| C6 | `WIKI_VERIFY.why` парсится, на исход не влияет | L1,L2,L3,L4,L8,L9,L11,L12 | **да** | **ПОДТВЕРЖДЕНО.** Запись `z21:587–588`; `wiki_outcome_from_verify` (`:671–720`) смотрит только `fit`/`index`. Других чтений `why` в ask/ нет. |
| C7 | Новый z20: INTENT+wiki+coverage+refuse; ANSWER/AXIS compose — stub B4 / legacy-only | L1–L12 | **да** | **ПОДТВЕРЖДЕНО** (скелет + bootstrap legacy). |
| C8 | Дубль `COVERAGE_SYS` в new+legacy z20 | L2–L5,L9–L12 | **да** | **ПОДТВЕРЖДЕНО.** `:736` / `:742`. |
| C9 | REFUSE / ядро INTENT / WIKI fit+choice / COVERAGE поведение — не трогать без замера | почти все | **да** | **СОГЛАСНО** (риск регрессии L67/intent/wiki). |
| C10 | User MUST в compose (`You MUST warn…`) — правила в user, не SYS | L2,L3,L7,L9 | **да** | **ПОДТВЕРЖДЕНО.** `z18:839–868`. |
| C11 | User wiki несёт `platform` / `axes` / `measures`; axis — `(col)`; coverage — сырой `entity` | L5,L6,L9,L11,L12 (+частично L3) | **да** (ядро L5) | **ПОДТВЕРЖДЕНО** — см. §2.3. |
| C12 | INTENT schema без `"="` в `amount.op`, код принимает `"="` | L4,L9–L12 | **да** | **ПОДТВЕРЖДЕНО.** Промт `z01:805`; `_AMOUNT_OPS` `z01:881` + комментарий замера 04.08. |
| C13 | `period2` в `_INTENT_FIELDS` / нормализаторе, в схеме промта нет | L1,L4,L7,L10–L12 | **да** | **ПОДТВЕРЖДЕНО.** Схема без поля (`z01:800–828`); поля в `_INTENT_FIELDS` `:883`; нормализация `z02:527–543`. |
| C14 | WIKI_PICK «полумёртв» — verify перезаписывает исход | **L1** (остальные: «жив») | **нет** | **ЧАСТИЧНО** — см. §2.1. Вызов жив; исход обычно overwrite. |
| C15 | `separable`: модель только ужесточает (AND с kNN) | L1,L4,L8,L12 | **да** | **ПОДТВЕРЖДЕНО** `z21:814–815`. **L2 ошиблась** — см. §2.1. |
| C16 | Снос separable / pick-only-on-degrade — кандидат среднего/высокого риска | L1,L2,L4 | слабо | Код подтверждает рычаг; чистка без wiki-замера **опасна**. |
| C17 | AXIS «several numbers» согласован с меню при ≥2 | L3,L8 | слабо | **ПОДТВЕРЖДЕНО по смыслу** rank→меню; формулировка спорная, не блокер. |
| C18 | INTENT Rules перегружены / ALWAYS vs null | L4,L7,L9,L10 | **да** | Текст есть (`z01:811–813`, Rules `:831+`); чистка без bench — высокий риск. |
| C19 | Порядок `refuse_text or NO_DATA_TEXT` vs наоборот | **L1** | **нет** | **ПОДТВЕРЖДЕНО** локально `z21:911`; остальные call-sites чаще `NO_DATA or refuse`. |
| C20 | `check_claims` comment в coverage путает ANSWER | **L9** | **нет** | Комментарий `legacy:4157` про ANSWER; в coverage claims живы — замечание L9 уместно. |

---

## 2. Разбор спорных мест (файл:строка)

### 2.1 «WIKI_PICK полумёртв — verify перезаписывает исход» (L1)

**Код** (`z21_wiki_choice.py`):

```918:933:ubuntu/serenedb/ask/z21_wiki_choice.py
    if len(cards) == 1:
        verify = wiki_verify_candidates(...)
        pick = verify
    else:
        pick = wiki_pick_from_cards(...)
        ...
        verify = wiki_verify_candidates(...)
        if verify.get("outcome") == "degraded":
            pass
        elif verify.get("outcome") in ("leader", "clarify", "none"):
            pick = verify
```

| Утверждение | Вердикт |
|---|---|
| При ≥2 карточках pick **всегда** зовётся | **да** (`:923`) |
| При успешном verify ∈ {leader,clarify,none} исход pick **затирается** | **да** (`:932–933`) |
| Pick полностью мёртв / не влияет никогда | **нет** — при `verify==degraded` остаётся pick (`:930–931`); ранний return на degrade pick (`:925–927`) |
| Токены на pick тратятся впустую при здоровом verify | **да**, это цена текущего каскада |

**Вердикт красной:** формулировка L1 «полумёртв» **точнее**, чем «жив» у большинства, *если* речь об исходе ответа. Для реестра вызовов правильнее: **жив как вызов, обычно перекрыт verify**. Кандидат «не звать pick» — смена политики каскада, не косметика (риск clarify/leader высокий).

### 2.2 «INTENT: код знает `amount.op="="` и `period2`, в схеме нет» (L10–L12)

**`=`:**

- Схема промта: `z01:805` — `">"|"<"|">="|"<="|"between"|null` — **без `"="`**.
- Код: `_AMOUNT_OPS = ("=", …)` `z01:881`; комментарий `[замер 04.08]` явно: модель уже шлёт `op:"="` на нулевую сумму; без приёма в коде условие пропадало молча.

**Влияние на живые ответы:** сейчас **низкое негативное** — код уже принимает `=`, модель его изобретает вопреки схеме. Риск: если модель станет строже следовать схеме и перестанет слать `=`, снова тихий провал порога «=0». Добавление `"="` в схему — **выравнивание с уже рабочей практикой**, не новая семантика.

**`period2`:**

- В промте поля нет (`z01:800–828`).
- Нормализатор ждёт (`z02:527–543`); `_INTENT_FIELDS` включает (`z01:883`).
- Живой compare: **код** пишет окна — `intent["period2"] = _p2` в `z20_legacy:3738` после `sales_compare_windows`.

**Влияние на живые ответы:** для compare-продаж **почти нулевое** (окна даёт код, не модель). Добавление `period2` в схему модели **может** начать заполнять поле ошибочно → средний риск без intent-bench. **Не** считать дыру схемы причиной текущих L67-провалов compare.

### 2.3 «User-части утекают техимена» (L5, L9)

| Место | Код | Утечка |
|---|---|---|
| Wiki cards | `wiki_format_card_lines` `z21:365–376` — `axes`/`measures` как есть | Источник осей в SQL: `wiki_card_build.sql:24` — `r.col \|\| ' -> ' \|\| r.target_src` |
| Wiki passports | `wiki_format_passport_lines` `z21:536–561` | То же + `distinct` из сырых col (`wiki_passport_distinct` `:471–488`, парсер `_wiki_parse_axes_set` берёт левую часть `col ->`) |
| Хвост пула | `:559–560` | `name or src_table` — прямой `src_table` при пустом name |
| Axis listing | `rank_axis_label_rows` `z10:170–171` | `lab = "%s (%s)" % (lab, col)` когда есть target и lab≠col |
| Coverage census | `z20:792–794` | `entity` из `search_coverage` без `human_table_label` |

**Вердикт:** L5/L9 **правы**. Это не «полная схема БД», но систематические OData-имена колонок/`target_src`/`src_table`/`entity` в user к модели — напряжение с п.19. Меню человеку (`wiki_menu_captions`) строится иначе (name/wiki body) — линзы, сказавшие «для меню ок», правы про клиентские подписи, но **не** отменяют утечку во вход модели.

### 2.4 «why в WIKI_VERIFY парсится и не влияет» (L2, L4)

- Парсинг: `_wiki_row_to_verdict` кладёт `why` в dict (`z21:587–588`).
- Исход: `wiki_outcome_from_verify` — только `fit`/`index` (`:671–720`).
- Grep по ask/: чтений `why` вне записи/докстроки парсера **нет**.
- `verdicts` (с why) остаются на объекте verify; в ветвление clarify/leader/none не входят.

**Вердикт:** **точно не влияет на исход.** Влияние на токены/truncation при `WIKI_VERIFY_MAX_TOKENS` — гипотеза L4 правдоподобна, незамерена. Убрать `why` из инструкции — низкий риск поведения; проверить salvage/parse тесты wiki.

### 2.5 Судьбы CLARIFY_SYS / arbitrate / ask-блока (все 12)

| Судьба | Сходимость 12 | Код |
|---|---|---|
| CLARIFY_SYS — снести (мёртвый) | **12/12** | 0 callers |
| arbitrate — снести (мёртвый) | **12/12** | 0 callers |
| ANSWER ask — чистить под one-path / B4 | **12/12** | drop всегда; промт всё ещё учит |
| Не воскрешать LLM-clarify вместо `clarify_say` | **12/12** | контракт меню кодом |

Расхождения только в **сроке/волне** (сейчас vs B4) и в оценке риска чистки ask (низкий vs средний) — не в диагнозе.

### 2.6 Ошибка L2 по `separable` (атака на сходимость)

Код: `separable = bool(j.get("separable")) and k_sep` (`z21:814–815`).

| Утверждение | Кто | Код |
|---|---|---|
| Модель **может** форсировать clarify при большом gap (`k_sep=True`, model `false`) | L1, L4, L8 | **верно** |
| «Модель не может форсировать clarify против большого kNN gap» | **L2** | **ЛОЖЬ** |
| При близком gap (`k_sep=False`) модель не может сделать leader | все согласные | **верно** |

Кандидат L2 «убрать separable, clarify только по kNN» **снимает** рычаг модели ужесточать — это не «мёртвое поле», а односторонний veto. Без wiki-замера — **не делать**.

---

## 3. Пропущенное всеми 12 линзами

Ни одна линза явно не проверила / не зафиксировала:

1. **Thinking/reasoning switches в `ds_chat`** (`z01:549–560`: `DS_THINKING`, `ASK_THINKING_OFF_BODY`, `DS_REASONING_OFF`) — влияют на *все* system-промпты одинаково; ни L4 (исполняемость), ни L8 (история) не разобрали, меняет ли thinking разбор JSON intent/wiki.
2. **Недостижимый хвост ask_back** после безусловного drop: `legacy:4328–4332` (`if ask_back: return kind=clarify`) — мёртвая ветка ответа; линзы описали drop, но не «мертвый return clarify».
3. **`wiki_validate_leader_axes`** (`z21:770–783`) — тихий veto лидера после модели (только префикс типа src); ни одна линза не включила в контракт «какие поля ответа реально решают» рядом с pick/verify.
4. **Инъекция `intent.kind` в user wiki** (`z21:734–736`, `:795–797`: `ask_text = "%s (%s)"`) — отдельный канал смещения pick/verify; упоминали формат user, не как скрытый выбиратель.
5. **Экспозиция `diag` в HTTP JSON** (`Handler._send` отдаёт весь `out`, включая `diag`) — `why`/verdicts сами по себе в клиентский *текст* не кладутся, но diag уходит в JSON ответа; никто не проверил, не сериализуются ли `verdicts` в diag на каком-то пути.
6. **Temperature**: все `ds_chat` с default `temperature=0`; overrides не искали (мелочь, но для «исполняемости» L4 — пробел).
7. **Синергия COVERAGE_SYS «Name the kinds…» + сырой `entity` в census** — L5/L6 видели entity, но не дословно связали инструкцию SYS с эхом техимён в клиентский text (гейт чисел это не ловит).

Не считалось «пропуском»: OpenClaw-персона / tool-description вне `ask/` (вне scope задачи); эмбеддер/rerank без chat-SYS (линзы верно исключили).

---

## 4. Правки-кандидаты: отбить / подтвердить

| ID | Кандидат (из линз) | Вердикт R2 | Волна | Замер | Риск L67 |
|---|---|---|---|---|---|
| P1 | Снести `CLARIFY_SYS` + `clarify_text`; убрать из `OUR_PROMPTS` | **делать** | B4 hygiene (можно раньше B5) | grep 0 callers + `test_gate`/leak | **нулевой** на ответы |
| P2 | Снести `arbitrate` + inline sys_msg | **делать** | B4 hygiene | grep 0 + `test_no_pre_wiki_reorders` | **нулевой** |
| P3 | `OUR_PROMPTS` += `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` | **делать** | B4 | `prompt_leak` unit / `test_gate` якоря ≥40 | **нулевой** на смысл; ловит эхо wiki-SYS |
| P4 | Вырезать `"ask"` + middle-road из `ANSWER_SYS` (`z18:58–69`, schema) | **делать** | **B4 вместе с compose**, не отдельным выкатом на прод-legacy без плана | compose 92/0 + **L67** после | **средний** на формулировки `text`; поведение ask_back уже drop |
| P5 | Убрать/`null` claims из ANSWER schema | **делать осторожно** | B4 после P4 или вместе | `_split_answer` + compose; **не** трогать COVERAGE claims | **низкий** на answer-пути |
| P6 | Убрать `why` из `WIKI_VERIFY_SYS` | **делать** (низкий приоритет) | B5 или hygiene | wiki verify parse/salvage + hybrid lock | **низкий**; исход не меняется |
| P7 | Не звать WIKI_PICK / не overwrite | **не делать** сейчас | — | потребовал бы полный wiki-каскад A/B | **высокий** на entity/clarify |
| P8 | Убрать `separable` из pick (только kNN) | **не делать** | — | см. §2.6 — снимает veto модели | **средний** на clarify vs leader |
| P9 | Добавить `"="` в INTENT `amount.op` | **делать** | B5 (точечно) | intent_parse_bench + кейс «нулевая сумма» | **низкий**; выравнивает с кодом |
| P10 | Добавить `period2` в схему INTENT | **не делать** без продуктовой нужды | — | compare уже кодом (`legacy:3738`) | **средний** (ложные period2 от модели) |
| P11 | Сжать INTENT Rules / убрать ALWAYS | **не делать** в B4 | позже | только с intent_parse_bench | **высокий** |
| P12 | Wiki user: убрать сырые `col -> target_src` / distinct col / хвост `src_table` | **делать** | **B5** (п.19) | wiki-каскад lock + L-match entity | **высокий** без замера; с замером — главный выигрыш п.19 |
| P13 | Axis labels без `(col)` | **делать** | B5 | rank/axis clarify | **низкий/средний** (коллизии меток) |
| P14 | Coverage census → `human_table_label(entity)` | **делать** | B5 | coverage-вопросы приёмки | **низкий** на числах; средний на формулировках |
| P15 | Слить дубль `COVERAGE_SYS` в один модуль | **делать** | B4/flip | bit-identical md5 | **нулевой** |
| P16 | Убрать MUST из compose user; оговорки кодом | **делать** | B4 | coverage/folders в тексте ответа + L67 | **средний/высокий** если код не дописывает |
| P17 | Смягчить NEVER WRITE / 🔴 в ANSWER | **не делать** первым | после step6 | `[замер 04.08]` рукопись цифр | **высокий** |
| P18 | Унифицировать COVERAGE digits → placeholders | **не делать** в B4 | отдельный эпизод | coverage gate | **средний** |
| P19 | Переформулировать AXIS «several numbers» | **не делать** до решения rank-in-onepath | B5+ | rank L67 | **средний** |
| P20 | Расширить `OUR_PROMPTS` user-литералами compose | **не делать** сейчас | опционально | false-positive leak | низкий/шум |

---

## 5. Финальный перечень правок (приоритет)

### P0 — контракт one-path / гигиена без риска ответов

| Приоритет | Правка | Дословные якоря | Волна | Замер | Риск L67 |
|---|---|---|---|---|---|
| 1 | Добавить wiki в leak-список | `OUR_PROMPTS = […, WIKI_PICK_SYS, WIKI_VERIFY_SYS]` в `z20:755` и legacy `:761` | B4 | unit `prompt_leak` / test_gate | 0 |
| 2 | Снести мёртвый CLARIFY | удалить константу+`clarify_text` (`z07:285–311`); вычеркнуть из OUR_PROMPTS | B4 | callers=0 | 0 |
| 3 | Снести мёртвый ARBITRATE | удалить `arbitrate`+sys_msg (`z01:602–628`) | B4 | `test_no_pre_wiki_reorders` | 0 |
| 4 | Вырезать ask из ANSWER | убрать из JSON `"ask": "one clarifying question, or null"` и абзац `"ask" is the middle road…` (`z18` schema ~58–69); синхронно упростить `_ask_back` ветку | **B4+compose** | L67 + compose lock | средний на текст |
| 5 | Один `COVERAGE_SYS` | общая константа, оба z20 импортируют | B4/flip | md5 identical | 0 |

### P1 — выравнивание схемы / п.19 (только с замером)

| Приоритет | Правка | Дословные якоря | Волна | Замер | Риск L67 |
|---|---|---|---|---|---|
| 6 | INTENT `amount.op` += `"="` | строка schema: сейчас `">"|"<"|">="|"<="|"between"|null` → вставить `"="` (`z01:805`) | B5 | intent bench + «нулевая сумма» | низкий |
| 7 | Убрать `why` из verify-инструкции | `"why": <one line>` из `WIKI_VERIFY_SYS` (`z21:55–56`) | B5 | wiki parse/salvage | низкий |
| 8 | Wiki user без сырых осей | не слать `col -> target_src` в `wiki_format_*`; хвост без `src_table`; `distinct` без raw col | B5 | wiki hybrid + entity L-match | **высокий** без / **средний** с замером |
| 9 | Axis listing без `(col)` | убрать `lab = "%s (%s)" % (lab, col)` (`z10:170–171`) | B5 | rank/axis | низкий–средний |
| 10 | Coverage entity → human label | вместо `r[0]` сырьём в census (`z20:792–794`) — `human_table_label` | B5 | coverage приёмка | низкий–средний |
| 11 | Compose user: убрать MUST | заменить `You MUST warn…` / `You MUST say…` (`z18:842–860`) описанием слотов; оговорки — код | B4 | L67 + folders/missing в ответе | средний |

### Явно не делать (отбито)

- Не добавлять `period2` в INTENT schema «за компанию» (P10).
- Не убирать `separable` и не отключать pick без политики+замера (P7–P8).
- Не резать INTENT Rules / NEVER WRITE / COVERAGE digits в первой волне (P11, P17, P18).
- Не возвращать `CLARIFY_SYS` для подписей меню.

### Не трогать (сходимость + код)

INTENT ядро (terms/kind/want/about/action_*/search_form); WIKI fit/index/choice; REFUSE; COVERAGE claims+gate; ANSWER placeholders + язык; живой `clarify_say` / `wiki_menu_captions` / `readings_menu`; порог verify «ровно один yes + остальные no» в коде.

---

## 6. Итог красной атаки

**Сходимость высокая** по мёртвым контурам, ask_back-долгу, OUR_PROMPTS-дыре и декоративному `why`.  
**Атака нашла:** (1) ошибку L2 о `separable`; (2) уточнение L1 — pick не мёртв, а обычно перекрыт; (3) `period2` в схеме — не рычаг живых compare; (4) пробелы всех 12 — thinking-switches, мёртвый return clarify, `wiki_validate_leader_axes`, kind-инъекция в wiki user.  
**План волн:** B4 = leak+снос мёртвого+ask-чистка с compose+MUST; B5 = `=` + why + user п.19 (wiki/axis/coverage) строго под замками. Без этих замеров чистка user-wiki — главный риск откатить L67 по сущности.

---

*Конец R2-red. Независимость: отчёты R-серии не читались.*
