# R1 — красная атака сходимости 12 линз аудита промптов

**Дата:** 12.09.2026  
**Метод:** чтение L1–L12 независимо друг от друга (уже готовы) → таблица сходимости →
сверка спорного по `ubuntu/serenedb/ask/*.py` (+ `wiki_card_build.sql` для происхождения
axes) → поиск пропущенного всеми своим чтением кода. Чужие R-отчёты не читались.
Код не менялся; модель/psql не звались.

**Тракты на срезе:** legacy = `z20_ask_main_http_legacy.py` (прод до flip);
новый = `z20_ask_main_http.py` (B3 скелет; compose/SQL — stub B4).

---

## 0. Вердикт красной в одном абзаце

Двенадцать линз **сходятся** по ядру: мёртвые `CLARIFY_SYS`/`arbitrate`, живой конфликт
`ANSWER_SYS.ask` vs безусловный drop, дыра `OUR_PROMPTS` без `WIKI_*`, мёртвый `why` в
verify, claims в ANSWER мёртвы / в COVERAGE живы. Спорное разрешается кодом в пользу
**L1** (WIKI_PICK полумёртв — verify overwrite), **L1+L4** (separable только ужесточает;
L2 формулировку перевернул), **L5/L9** (утечка техимён в user — доказана), **L1**
(`period2` в живых ответах пишет код compare, не модель). Главный долг волны B4 —
вырезать `ask` из ANSWER до подключения compose; безопасная гигиена B5 — снос
CLARIFY/arbitrate + WIKI в leak-список + `"="` в INTENT. Не делать без замера: ужим
wiki axes/measures, снос pick, снос NEVER WRITE, добавление `period2` в промт модели.

---

## 1. Таблица сходимости

| # | Вывод | Линзы | Независимо? | Вердикт по коду |
|---|---|---|---|---|
| C1 | `CLARIFY_SYS` / `clarify_text` мёртвы (0 callers); меню = `clarify_say` | **все 12** | да (8 аспектных + 4 полных) | **ПОДТВЕРЖДЕНО.** Определение `z07:285–311`; callers только def; живое меню `z20:281+` |
| C2 | `arbitrate` + inline sys_msg мёртвы (0 callers); замок `test_no_pre_wiki_reorders` | **все 12** | да | **ПОДТВЕРЖДЕНО.** `z01:602–628`; внешних вызовов нет |
| C3 | `ANSWER_SYS` учит `"ask"` / middle-road; код всегда дропает ask_back | **все 12** | да | **ПОДТВЕРЖДЕНО.** Промт `z18:59–69`; drop `z20_legacy:4325–4327` (`bare_clarify_forbidden`). L11 «почти всегда» — мягче факта: после gate любой непустой ask_back гасится |
| C4 | `OUR_PROMPTS` без `WIKI_PICK`/`WIKI_VERIFY`; с мёртвым CLARIFY | **все 12** | да | **ПОДТВЕРЖДЕНО.** `z20:755` / legacy `:761` |
| C5 | `WIKI_VERIFY.why` парсится, на исход не влияет | **все 12** (явность разная) | да | **ПОДТВЕРЖДЕНО.** Парс `z21:587`; `wiki_outcome_from_verify` (`:671–720`) смотрит только `fit`/`index`. `why` нигде больше не читается |
| C6 | ANSWER `claims` на answer-пути игнорируются; COVERAGE claims живы | **все 12** | да | **ПОДТВЕРЖДЕНО.** ANSWER: промт «ignored» + compose без `check_claims`; COVERAGE: `check_claims` + `gate` (`z20:802–818`) |
| C7 | INTENT / REFUSE / wiki SYS-ядро / COVERAGE SYS — не трогать без замера | **все 12** (с нюансами) | да | **ПОДТВЕРЖДЕНО** как политика риска |
| C8 | Кандидат: снести CLARIFY + arbitrate | **все 12** | да | **делать** (B5 гигиена), риск ответов = 0 |
| C9 | Кандидат: вычистить `ask` из ANSWER | **все 12** | да | **делать в B4** до compose; риск средний на legacy L67 |
| C10 | Кандидат: добавить WIKI_* в `OUR_PROMPTS` | **все 12** | да | **делать** (B5), риск = 0 на ответы |
| C11 | Кандидат: убрать `why` из VERIFY | большинство (L1–L9, L11; L10/L12 слабее) | частично | **делать опционально B5**; исход не меняется; риск низкий на parse/salvage |
| C12 | Дубль `COVERAGE_SYS` new/legacy | 11 (нет явного у L8) | почти | **ПОДТВЕРЖДЕНО** identical; слить при flip — низкий риск |
| C13 | User MUST в compose (`You MUST warn/say`) | L2,L3,L4,L7,L9,L11 | 6/12 | **ПОДТВЕРЖДЕНО** `z18:842–860`. Чистить в B4 осторожно |
| C14 | Утечка техимён в user (axes/col/census) | L5,L9 ядро; L3,L6,L11,L12 частично | **независимые L5+L9** + эхо | **ПОДТВЕРЖДЕНО** (см. §2.3) |
| C15 | INTENT: в схеме нет `"="`, код принимает | L4,L9,L10,L11,L12 | 5/12 (в т.ч. 3 полных) | **ПОДТВЕРЖДЕНО** `z01:805` vs `_AMOUNT_OPS` `:881` + замер 04.08 в комментарии |
| C16 | INTENT: `period2` в полях/нормализаторе, в промте нет | L1,L2,L3,L4,L5,L7,L10,L11,L12 | 9/12 | **ПОДТВЕРЖДЕНО** схема. **Влияние на ответы:** низкое — compare пишет `period2` кодом (`z20_legacy:3738`) |
| C17 | WIKI_PICK полумёртв: verify overwrite | **L1** явно; L4/L8 намекают | **одна линза** (критично) | **ПОДТВЕРЖДЕНО** `z21:922–933` — см. §2.1 |
| C18 | `separable`: модель только ужесточает | L1,L4 верно; **L2 врёт формулировкой** | спор | **L1/L4 правы** — см. §2.4 |
| C19 | Кандидат: убрать `separable` / не звать pick | L1,L2,L4 | 3 | **не делать** без wiki-замера (высокий риск clarify/leader) |
| C20 | Кандидат: `"="` в INTENT schema | L4,L9–L12 | 5 | **делать B5** с intent-bench; риск низкий/средний |
| C21 | Кандидат: добавить `period2` в INTENT промт | L4,L7,L10–12 за; **L1 против** | спор | **не делать** (L1 прав) — см. §2.2 |
| C22 | Кандидат: ужать wiki axes/measures в user | L5,L9 (P1); другие слабее | 2 сильных | **отложить** — только с wiki/L-match; риск высокий |
| C23 | Кандидат: убрать `(col)` из axis labels | L5,L9,L11,L12 | 4 | **делать B5** с rank-замером; риск средний |
| C24 | Кандидат: human label в coverage census | L5,L6,L9,L11 | 4 | **делать B5** с coverage-прогоном; риск низкий/средний |
| C25 | Кандидат: смягчить NEVER WRITE / убрать 🔴 | L4,L7,L9,L10 | 4 | **не делать** без step6/L67 — высокий риск цифр |
| C26 | AXIS_PICK «several» / роль в onepath | L3,L7,L8,L10 | 4 | **не трогать** до решения B4 (ось = reading vs LLM) |

Легенда «независимо?»: аспектные L1–L8 + полные повторы L9–L12 считаются независимыми
исполнителями задачи; сходимость ≥3 аспектов + ≥2 полных = сильная.

---

## 2. Спорные места — разбор по коду

### 2.1 «WIKI_PICK полумёртв — verify перезаписывает исход» (L1) — **правда**

`try_wiki_hybrid_entity_pick` (`z21:889+`):

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

Следствия:

- при ≥2 карточках pick **всегда** зовётся (токены/латентность живы);
- при успешном verify ∈ {leader, clarify, none} исход pick **затирается**;
- pick остаётся видимым клиенту только если verify `degraded` (тогда `pass`) или
  pick сам `degraded` раньше (`:925–927` → fallback).

Большинство линз назвали WIKI_PICK просто «жив» — формально верно как вызов, но
**L1 точнее** про жизнь *исхода*. Кандидат «не звать pick» без замера — высокий риск
(меняется ветка при degraded verify и ранняя диагностика).

### 2.2 «INTENT: код знает `amount.op="="` и `period2`, в схеме нет» (L10–L12) — **правда; влияние разное**

**`=` — правда и влияет на живые ответы опосредованно:**

- промт: `"op": ">"|"<"|">="|"<="|"between"|null` (`z01:805`);
- код: `_AMOUNT_OPS = ("=", ">", …)` (`z01:881`) с явным `[замер 04.08]` —
  без `"="` условие нулевой суммы пропадало молча.

Модель уже шлёт `=`; код принимает. Расхождение схемы не ломает текущие ответы
**только потому что** код шире промта. Добавление `"="` в схему — выравнивание,
не новая семантика.

**`period2` — правда как дыра схемы; на живой compare почти не влияет:**

- `_INTENT_FIELDS` включает `period2` (`z01:883`);
- `_normalize_intent` читает (`z02:527–543`);
- в `INTENT_SYS` поля **нет**;
- legacy compare: `intent["period2"] = _p2` из `sales_compare_windows` (`z20_legacy:3738`),
  **не из модели**.

Учить модель `period2` = риск выдуманного второго окна (п.12). L1 («не добавлять без
нужды») сильнее L4/L7/L10–12. Вердикт красной: **`"="` — да; `period2` в промт — нет**.

### 2.3 «user-части утекают техимена» (L5, L9) — **доказано**

| Место | Код | Что уходит в модель |
|---|---|---|
| Wiki cards | `wiki_format_card_lines` `z21:365–375` | `axes`, `measures` как есть |
| Происхождение axes | `wiki_card_build.sql:24` | `string_agg(r.col \|\| ' -> ' \|\| r.target_src, …)` — **OData col + target_src** |
| Wiki passports | `wiki_format_passport_lines` `z21:536–561` | те же axes/measures + `distinct` из сырых col (`wiki_passport_distinct` `:471–488`) |
| Хвост пула | `z21:559–561` | `name or src_table` — при пустом name → **src_table** |
| Axis pick | `rank_axis_label_rows` `z10:170–171` | `lab = "%s (%s)" % (lab, col)` когда label ≠ col |
| Coverage census | `_coverage_answer` `z20:792–794` | `"%s: …" % r[0]` — `entity` из `search_coverage` (часто тех. имя) |

Рост с **числом таблиц базы** в chat-user закрыт лимитами (`WIKI_PICK_N=8`,
`COVERAGE_TOP`, `ROWS_*`). Дефект L5 — не «линейный рост», а **схема в модель** при
уже урезанном N. Меню человеку (`wiki_menu_captions`) осей не печатает — утечка
именно в LLM-user, не в клиентский clarify.

### 2.4 `why` в VERIFY — **парсится и не влияет на исход** (L2, L4 и все)

- запись: `_wiki_row_to_verdict` → `why[:200]` (`z21:587`);
- ветвление: только `fit`/`index` в `wiki_outcome_from_verify`;
- grep по ask/: чтение `why` только в парсере.

Точно: **не влияет на leader/clarify/none**. Может лежать в `verdicts` diag
(внутренняя диагностика). Клиентский `text` из why не строится.

### 2.5 Судьбы CLARIFY / arbitrate / ask-блока — **все 12 сошлись; код подтверждает**

| Объект | Судьба | Код |
|---|---|---|
| `CLARIFY_SYS` | мёртв; снос безопасен | 0 callers `clarify_text(` |
| `arbitrate` | мёртв; снос безопасен | 0 callers; тест сторожит |
| блок `ask` в ANSWER | жив в промте, мёртв в deliverable | безусловный drop после gate |

Нюанс: между `_ask_back` и drop ask ещё гоняется числовой gate (`ask_back_rejected`) —
лишняя работа; на клиента не влияет.

### 2.6 Ошибка L2 по `separable` (атака на сходимость)

L2 (`§2.7`): «модель **не может** форсировать clarify против большого kNN gap».

Код (`z21:814–815`, `:835`):

```python
separable = bool(j.get("separable")) and k_sep
if not separable and len(cards) >= 2:
    # → clarify
```

При большом gap (`k_sep=True`) модель `separable=false` → `False` → **clarify**.
Модель **может** форсировать clarify против большого gap; не может ослабить малый
gap (`k_sep=False` + model true → всё равно False). Верны L1/L4 («только ужесточить»).

---

## 3. Пропущенное всеми 12 линзами

Ни одна линза не разобрала следующие живые механизмы рядом с промптами:

| # | Пропуск | Где | Почему важно для «жизни промпта» |
|---|---|---|---|
| M1 | **`wiki_leader_post_verify`** после модельного leader | `z21:971`, `:1046–1076` | Модель сказала fit=yes → код может **обнулить** лидера (`measure_not_carried` / `axis_not_carried`) → no_data. Исход verify ≠ исход каскада |
| M2 | **`wiki_validate_leader_axes`** внутри outcome | `z21:699–701`, `:770–783` | Leader с «чужим» префиксом src → `axis_reject` / none — снова код поверх fit |
| M3 | **`filter_pool_by_named_type` до LLM** | `z21:197–215`, зов `:903` | Пул, который видит pick/verify, уже урезан кодом по типу из вопроса. L11 лишь упомянул имя; никто не проверил влияние на user-listing |
| M4 | **`wiki_platform_kind` fallback** | `z21:86–91` | При пустом `kind_word` → `src_table.split("_")[0]` — в user уходит английский OData-префикс (`document`, `catalog`, …) |
| M5 | **Асимметрия `refuse_text` vs `NO_DATA_TEXT`** | большинство call-sites: `NO_DATA or refuse`; `z21:911`: **`refuse or NO_DATA`** | Только L1 заметил. При непустом env на empty_pool модель **всё же зовётся** |
| M6 | **`WIKI_SEP_GAP` (env, default 0.04)** | `z21:24` | Порог, от которого зависит смысл поля `separable`; никто не назвал число |
| M7 | **Post-pick reason `wiki_separability` vs verify-clarify** | `z21:949–968` | Два разных clarify-источника; при overwrite verify pick-separability часто не доезжает — усиливает тезис L1 о полумёртвости |
| M8 | **INTENT×SAMPLES стоимость** | `INTENT_SAMPLES` умолч. 5 × ~3.2k SYS | Реестры длин считали один литерал; суммарный расход system на шаг 1 ≈ 5× — не у всех |
| M9 | **User-фразы compose вне `OUR_PROMPTS`** | `COMPUTED…`, `YOUR PREVIOUS ANSWER WAS REJECTED…` | Только L6 поднял как дыру leak; остальные фокусировались на SYS |
| M10 | **Ложный комментарий coverage** | `z20:804–807` («промт велит оставлять claims пустыми») | Описывает ANSWER, не COVERAGE. L9 поймал; остальные нет — риск будущей «чистки claims» по ложному следу |

Не пропуски, а граница scope (ок, что не в реестре SYS): `rerank`, `embed_one`,
`entity_form` без LLM, `clarify_say`.

---

## 4. Правки-кандидаты — вердикты красной

| # | Кандидат (из линз) | Вердикт | Волна | Замер | Риск L67 |
|---|---|---|---|---|---|
| P1 | Вырезать из `ANSWER_SYS` поле `"ask"` и абзац middle-road (`z18:59–69`, `:88` «ask too») | **делать** | **B4** (до подключения compose к новому тракту; на legacy — тем же диффом с прогоном) | L67 + compose/gate (step6) до/после | **средний** на формулировки `text`; deliverable ask_back уже мёртв |
| P2 | Снести `CLARIFY_SYS` + `clarify_text`; убрать из `OUR_PROMPTS` | **делать** | **B5** гигиена | grep=0 callers + `test_gate` / leak-тесты | **нулевой** |
| P3 | Снести `arbitrate` + inline sys_msg | **делать** | **B5** | grep=0 + `test_no_pre_wiki_reorders` | **нулевой** |
| P4 | Добавить `WIKI_PICK_SYS`, `WIKI_VERIFY_SYS` в `OUR_PROMPTS` (оба z20) | **делать** | **B5** | `test_gate` на новые якоря ≥40 | **нулевой** на ответы |
| P5 | Добавить `"="` в `INTENT_SYS` schema `amount.op` | **делать** | **B5** | `intent_parse_bench` / замок intent (хотя бы кейс нулевой суммы) | **низкий** (код уже принимает) |
| P6 | Убрать `"why"` из `WIKI_VERIFY_SYS` (+ опц. парсер) | **делать опционально** | **B5** | wiki verify parse/salvage замки | **низкий** |
| P7 | Слить дубль `COVERAGE_SYS` в один модуль | **делать** | flip / B4 хвост | bit-identical md5 + 1 coverage-вопрос | **низкий** |
| P8 | Убрать `(col)` из `rank_axis_label_rows` user | **делать** | **B5** | rank/axis clarify прогон | **средний** при одинаковых label |
| P9 | Census coverage: `human_table_label(entity)` вместо сырого `r[0]` | **делать** | **B5** | coverage-вопросы приёмки | **низкий/средний** на формулировки |
| P10 | Убрать MUST из compose user; оставить слоты `{missing}`/`{folders}` | **делать осторожно** | **B4** | L67 + проверка что passport/folders дописывает код | **средний** — часть оговорок может пропасть |
| P11 | Убрать `claims` из ANSWER schema | **отложить** | после P1 | compose parse + coverage не трогать | средний без нужды; COVERAGE claims живы |
| P12 | Не звать WIKI_PICK при ≥2 / не overwrite | **не делать** | — | — | **высокий** без полного wiki-каскада |
| P13 | Убрать `separable` из WIKI_PICK | **не делать** сейчас | — | — | **средний** на частоту clarify; сначала понять M7 |
| P14 | Ужать/убрать axes/measures (`col -> target_src`) из wiki user | **не делать** без отдельного эпизода | после B4 | wiki hybrid + L-match / gold entity | **высокий** |
| P15 | Добавить `period2` в INTENT промт | **не делать** | — | — | средний: модель начнёт выдумывать второе окно; код compare сам пишет |
| P16 | Сжать INTENT Rules / убрать ALWAYS | **не делать** | — | intent bench 162/0 | **высокий** |
| P17 | Смягчить/убрать NEVER WRITE FIGURE / 🔴 | **не делать** | — | step6 `[замер 04.08]` 1/8 рукопись | **высокий** |
| P18 | Унифицировать COVERAGE на placeholders как ANSWER | **не делать** в первой волне | позже | coverage gate F128-класс | **средний** |
| P19 | Переформулировать AXIS «several numbers» | **не делать** до решения onepath-осей | B4 продукт | rank L67 | средний |
| P20 | Расширить `OUR_PROMPTS` user-литералами compose | **отложить** | отдельное решение | false-positive leak | низкий на ответы; API списка = system |

### Порядок волн (рекомендация красной)

```
B4 (рядом с compose «одного пути»):
  P1 ask-блок → P10 MUST (если passport уже дописывает) → P7 дубль COVERAGE

B5 (гигиена, можно до/после B4, низкий риск ответов):
  P2 CLARIFY → P3 arbitrate → P4 WIKI в OUR_PROMPTS → P5 "=" → P6 why?
  → P8 (col) → P9 census labels

НЕ в промпт-волнах без отдельного замера:
  P12–P17, P14 (п.19 wiki payload — отдельный эпизод)
```

### Дословные строки к P1 (вырезать)

```text
"ask": "one clarifying question, or null",
…
"ask" is the middle road between answering and giving up. Fill it ONLY when the rows do
not answer exactly what was asked, …
…
- Reply in the SAME language the question was asked in — "ask" too.
```

### Дословные строки к P5 (добавить в schema)

Было: `"op": ">"|"<"|">="|"<="|"between"|null`  
Стать: `"op": "="|">"|"<"|">="|"<="|"between"|null`

### Дословные якоря мёртвого (P2/P3) — для grep после сноса

CLARIFY: `Ask the person ONE short question… Never show table names…`  
ARBITRATE: `Choose the ONE answer that actually answers the question… Reply with a single digit…`

---

## 5. Что не трогать (свод красной = пересечение линз + код)

| Что | Почему |
|---|---|
| Ядро `INTENT_SYS` (terms/kind/want/about/action_*/search_form) | Вход всего тракта; search_form с замером `708e6a7` |
| `WIKI_PICK`/`VERIFY` system-текст fit/choice/index | Каскад one-path; порог лидера — в коде, не в промте |
| `REFUSE_SYS` | Короткая роль; цифры режет код |
| `COVERAGE_SYS` поведение DIGITS+claims+gate | Единственный живой claims-путь |
| ANSWER placeholders / язык / no invent | `[замер 04.08]` + compose 92/0; L67 на legacy |
| `AXIS_PICK_SYS` индексная schema | Пока legacy rank жив |
| Живой `clarify_say` / `wiki_menu_captions` / `readings_menu` | Единый построитель меню — не возвращать LLM-clarify |
| `gate` / `_fill_figures` / `prompt_leak` порог 40 | Защита кодом, не промтом |

---

## 6. Карта «кто ошибался / кто был точнее»

| Тема | Точнее | Слабее / ошибка |
|---|---|---|
| WIKI_PICK жизнь исхода | **L1** (полумёртв + overwrite) | L2–L12: «жив» без overwrite |
| separable рычаг | **L1, L4** | **L2**: перевёрнута формулировка про clarify vs gap |
| period2 влияние | **L1** (код compare) | L4/L7/L10–12: «добавить в промт» без учёта sales_compare |
| ask_back unconditional | L1–L4, L8–L10, L12 | L11: «почти всегда» |
| user техимена | **L5** (аспект) + **L9** (полный) | аспектные без L5 недооценили P1 |
| leak user-compose | **L6** | остальные |
| история/замки «не трогать» | **L8** | полезно оркестратору для порядка |
| дыры B3/B4 «новых промптов не нужно» | **L7** | согласуется с кодом меню |

---

## 7. Итог для этапа-2

Красная **не опровергает** сходимость ядра (мёртвое + ask + leak + why).  
Красная **уточняет** три опасных упрощения большинства:

1. WIKI_PICK не «просто жив» — исход при штатном verify затирается (L1).  
2. `period2` в промт модели тащить не надо — compare пишет код.  
3. Чистка wiki user-payload (axes/col) — реальный п.19-дефект (L5), но **не** первая
   правка рядом с B4: сначала контракт ответа (`ask`), потом гигиена, потом payload.

Финальный минимальный пакет с приемлемым риском для L67:

1. **B4:** P1 (`ask`) ± P10 (MUST) — замер L67.  
2. **B5:** P2+P3+P4+P5 (±P6) — замер intent + gate; ответы не должны сдвинуться.  
3. **Отдельно:** P8+P9+P14 — только с целевыми прогонами rank/coverage/wiki.

---

*Конец R1-red. Независимость: отчёты R2+ не читались.*
