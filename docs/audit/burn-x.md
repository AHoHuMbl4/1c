# BURN-X: карта word-механики складской маршрутизации (К9-ф3 доводка)

Дата: 11.09.2026. Режим: **только чтение**. Коммитов нет.
Роль **X**. Вход: постановка владельца (дожиг вместо OPT-S паллиатива);
`PLAN_TO_TARGET.md` §0 / К9-ф3 29.08; `opt-s.md` / `opt-r.md` (зонды);
код `z12` / `z11` / `z10` / `z13` / `z20` / `z21`; замок-базлайн
`test_no_domain_baseline.json` (z10×13, z11×23); `test_stock_balance_path.py`.

---

## Вердикт одной строкой

Складской путь **уже формально** завязан на intent (`_stock_intent_signal`,
`balance_routing_core` / `state_path` + metadata), но **дорогой word-loop**
`_question_dictionary_axis_candidates` → `resolved_warehouse_axis_word` всё ещё
кормит оси из **сырого текста вопроса** и протекает в гейты
`stock_question_engaged` / `catalog_kind_total_question` / breakdown-ветку
routing. Дожиг = **отрезать question-scan оси места**, оставить только
`action_axis`/`kind` из разбора ↔ `search_refcols`; маркеры «всего» в z12
уже intent (`aggregate_count_intent`) — имя легаси. z10/z11 «всего/склад/остат»
в базлайне О6 — **смежный скоуп**, в этот пакет только то, что режет/включает
stock-route.

---

## 0. Целевая схема (контракт К9-ф3)

| Вход | Разрешено | Запрещено |
|---|---|---|
| Сигнал остатка | `_stock_intent_signal` (`z12:371–380`): `action_class=object` / breakdown + оси из intent | сканирование слов вопроса |
| Триггер balance | `question_asks_stock_balance` → `balance_path_engaged` (`:383–392`): routing минус `sales_sum_intent` | доменные списки «остат/склад/всего» |
| Ось места | `action_axis` (разбор) → `_catalogs_for_warehouse_axis_word` → place-каталоги из `search_refcols` (`_stock_place_axis_catalogs`) | `re.finditer` по `question` |
| Kind stock | `_kind_is_stock_scoped`: kind → catalogs (product / place) | word-loop по q |

OPT-S early-exit (`sales_sum_intent` в начале `stock_question_engaged`) и OPT-C
кэш — **второй слой скорости**, не замена дожига word-слоя.

---

## 1. Граф: где слова вопроса решают «склад»

```
question (сырой текст)
    │
    ▼
_question_dictionary_axis_candidates          z12:161–187   ★ WORD-LOOP
    │  terms(intent) + re.finditer(question)
    ▼
resolved_warehouse_axis_word                  z12:190–200
    │  1) action_axis → catalogs (ОК, intent)
    │  2) for w in candidates → catalogs     ★ изъять ветку 2
    ├──────────────────┬─────────────────────┬──────────────────┐
    ▼                  ▼                     ▼                  ▼
question_mentions_   intent_axis_words    secondary_axis_    resolved_unaccounted_
warehouse_axis       (+ kind/action_axis) known              slice_axis_word
z12:395–401          z12:284–302          z12:328–338        z12:250–281
    │                  │                     │
    │                  ▼                     │
    │         balance_routing_core           │
    │         z12:366 breakdown∧axes         │
    │         _stock_intent_signal :376–378  │
    ▼                  ▼                     ▼
catalog_kind_total ←── stock_question_engaged ←── stock_skips / count_agg
z11:719–721            z12:416–437                z12:574–618
                       │
                       ▼
                 z20 if stock#1/#2, fork skip, z13 filters, z16, z02
```

Стоимость на rid «продажи+полный отчет» (opt-s): word-loop в
`catalog_kind_total_question` ≈ **9,5 с**; pred×3 в stock-блоке; ложный
engage через product-kind + breakdown — отдельный дефект гейта (OPT-S S1),
но **питается той же осью-словарём**, если wh/axes тянутся из q.

---

## 2. Карта функций (кто зовёт / что решает / замена / изъятие)

### 2.1 Ядро word-слоя (изымать)

| # | Место | Кто зовёт | Что решает сейчас | Чем заменить | Изъять? | Риск |
|---|---|---|---|---|---|---|
| **X1** | `z12:161–187` `_question_dictionary_axis_candidates` | `resolved_warehouse_axis_word:197`, `resolved_unaccounted_slice_axis_word:266` | Кандидаты оси = **все слова вопроса** (+ terms) минус kind/measure/action_axis | Только поля разбора: `action_axis`, опционально **structured** `terms` (не токены q). Метаданные — через `_catalogs_for_warehouse_axis_word` / `search_refcols` | **Да** (тело или удаление хелпера) | Вопросы, где LLM не заполнил `action_axis`, а «склад» только в тексте → wh=False; нужен clarify/wiki, не silent wrong |
| **X2** | `z12:197–199` ветка `for w in _question_dictionary…` в `resolved_warehouse_axis_word` | `question_mentions_warehouse_axis`, `intent_axis_words:297`, `secondary_axis_known:331`, `warehouse_axis_values:559`, `z21:_wiki_axis_has_carriers:141–142`, clarify `z12:1212` | Фоллбэк «найти склад в тексте» | Оставить **только** `:195–196` (`action_axis` + place catalogs). Пусто → `""` | **Да** | Тот же: INTENT_LIVE в `test_stock_balance_path:86–105` **обязан** перейти на `action_axis="склад"` |
| **X3** | `z12:266–278` word-loop в `resolved_unaccounted_slice_axis_word` | `z21` post-verify (`:1079+`), тесты journal-ghost | Journal-ось по словам q | Кандидаты только из `action_axis` / intent terms; journal-матч по metadata без scan q | **Да** (тем же пакетом — общий хелпер) | Ghost-ось без action_axis перестанет находиться из текста |

### 2.2 Обёртки, которые становятся чистыми после X1–X2

| # | Место | Кто зовёт | Что решает | Замена / правка | Изъять? | Риск |
|---|---|---|---|---|---|---|
| **X4** | `z12:395–401` `question_mentions_warehouse_axis` | `catalog_kind_total:719`, `stock_question_engaged:427`, `stock_skips:577`, `stock_count_agg:607`, `z13:615` | «В вопросе упомянута ось места» | После X2 = «`action_axis` резолвится в place-catalog». Имя можно сузить позже; тело — тонкая обёртка | **Не удалять API** (много call-site); **семантику** — да | Низкий, если X2 сделан |
| **X5** | `z12:284–302` `intent_axis_words` | `balance_routing_core:366`, `_stock_intent_signal:376–378`, `registers_for_kind_axes:445`, `warehouse_axis_values:555`, `_rank_wants_quantity:653`, `z21:118` | Оси = kind + action_axis + **resolved_wh** | Убрать `:297–301` (добавление `resolved_warehouse…` из q). Оставить kind + action_axis. Registers — по этим же словам ↔ refcols | **Да** (хвост resolved) | Breakdown без action_axis/kind не даст True через «слово склада в q» — **желаемый** эффект К9 |
| **X6** | `z12:328–338` `secondary_axis_known` | `stock_skips:583`, `stock_count_agg:605`, `stock_subject:631` | Вторичная ось ≠ kind | Только `intent.action_axis` (убрать `or resolved_warehouse…`) | **Да** (фоллбэк) | Count-agg без action_axis → subject-clarify чаще — честнее, чем угадывать из текста |

### 2.3 Intent-детекторы (оставить; почистить входы)

| # | Место | Кто зовёт | Что решает | Замена | Изъять? | Риск |
|---|---|---|---|---|---|---|
| **X7** | `z12:371–380` `_stock_intent_signal` | `stock_question_engaged:432` | object/breakdown + оси | Уже целевой детектор. После X5 оси = только intent | **Нет** (ядро) | — |
| **X8** | `z12:353–368` `balance_routing_core` | `balance_path_engaged`, `question_has_aggregate_total_marker`, `stock_question_engaged:430`, `sales_sum_intent:67`, `catalog_kind_total:722` | object→metadata confirm; или breakdown∧axes | Не читает q напрямую; после X5 breakdown-ветка без word-leak. `state_path` + `balance_axis_registers_confirmed` — **оставить** | **Нет** тела; **да** косвенный word через axes | — |
| **X9** | `z12:404–408` `question_has_aggregate_total_marker` | `stock_question_engaged:436`, `stock_skips:579`, `z20:2673`, `z20:4400`, bootstrap | Итог без разреза | Тело уже `aggregate_count_intent` (want/amount) + routing — **не word-list**. Легаси-имя; опциональный rename | **Нет** (логика); не путать с z10 «всего» | — |
| **X10** | `z12:310–325` `aggregate_count_intent` | X9, stock_skips, count_agg | want count/sum без rank/breakdown | Уже intent | **Нет** | — |
| **X11** | `z12:383–392` `balance_path_engaged` / `question_asks_stock_balance` | stock_asks_named, count_agg, subject_clarify | Routing − sales_sum | Целевой публичный гейт | **Нет** | — |
| **X12** | `z12:113–126` `_kind_is_stock_scoped` | `stock_question_engaged:426` | kind → product/place catalogs | Intent kind ↔ metadata — **К9-ок** | **Нет** | Ложный product-kind на «чего» (opt-s) — чинить sales-гейтом / kind-семантикой, **не** word-deny |

### 2.4 Оркестратор и каталог-гейт

| # | Место | Кто зовёт | Что решает | Замена | Изъять? | Риск |
|---|---|---|---|---|---|---|
| **X13** | `z12:416–437` `stock_question_engaged` | z20×много, z13 filters, z16, z02, z11 sales_canon, prefer_stock | Вход в stock-фильтры | После X2–X5: `catalog_*` guards + `_kind_is_stock_scoped` + wh(intent) + `_stock_intent_signal` / `balance_routing_core`. Зеркало `sales_sum_intent` (OPT-S S1) — скорость, не word-слой | **Не удалять**; **пересобрать порядок** | Ложный engage sales+list остаётся, пока нет S1 / sales_kind раньше — вне «изъятия word», но в том же выкате желательно |
| **X14** | `z11:716–740` `catalog_kind_total_question` | `stock_question_engaged:423`, `catalog_count:745`, `prefer_catalog:764`, `sales_canon:354` | count + kind→не-product catalog; **сначала** wh-word-loop | 1) Дешёвые поля intent (want/period/kind) **до** оси. 2) Warehouse-guard = `action_axis` place / `_stock_intent_signal` / `balance_routing_core`, **без** scan q. 3) Не звать полный `question_mentions_warehouse_axis`, пока не нужен | **Изъять вызов word-path**; функцию оставить | Catalog «сколько организаций» должен остаться True |
| **X15** | `z11:752–755` deny в `catalog_count_question`: `("прода","куп","остат","склад")` | `catalog_count` → prefer/sales_canon | Прайс-канон режется словами | Для **складского** deny: `stock_question_engaged` / `_stock_intent_signal` / `balance_path_engaged` вместо `"остат","склад"`. `"прода","куп"` — sales О6, **не этот пакет** | **Да** только `остат`/`склад` | Прайс+слово «склад» в тексте без intent — edge; приёмка catalog/price замков |

### 2.5 Легаси z10/z11 базлайна — попадание в stock-route

| # | Базлайн | Место | В stock-route? | Вердикт X |
|---|---|---|---|---|
| **X16** | z11 `any-in-q 'остат'`, `'склад'` | `catalog_count_question:754` | Да (отрицательный гейт прайса ↔ склад) | **В пакет** (X15) |
| **X17** | z11 `for-header 'всего'`, «лучше/больше всего», sales literals | measure/rank sales `z11:81+`, `:401+`, `:464+` | Нет (меры/ранг продаж) | **Вне пакета** — О6 отдельно |
| **X18** | z10 `any-in-q 'всего'/'итого'` | `total_question_skips_axis:54` | Нет (axis-clarify skip, общий) | **Вне** складского дожига; слово «всего» в sales-путях не трогать здесь |
| **X19** | z10 `'товар'/'номенклатур'/'продаж'` + rank markers | `rank_question_text:67–85`, prefer_rank | Нет (rank) | **Вне** |
| **X20** | z11 sales_sum / sales_kind подстроки «продаж…» | `z11:10–35` | Косвенно (режет balance через `balance_path_engaged`) | Не изымать в burn-stock; OPT-S S1 **переиспользует**. О6 — отдельный пакет |

### 2.6 Потребители z20/z13 (не word-источник, но зависят)

| Call-site | Строки | Зависимость | После дожига |
|---|---|---|---|
| `z20` stock bypass empty | `:2187` | `stock_question_engaged` | Чище False на sales |
| `z20` stock#1 pre-K6 | `:2232+` | engaged → фильтры | −ложный if (с S1) |
| `z20` stock#2 post-K6 | `:2270+` | то же | симметрия |
| `z20` `_skip_stock_fork` | `:2670–2674` | engaged + aggregate_total / breakdown | aggregate_total уже intent |
| `z20` measure clarify skip | `:4399–4400` | engaged + aggregate_total | без изменений логики |
| `z13` `filter_stock_balance_sales_noise` | `:23` | engaged | кэш OPT-C |
| `z13` fork place | `:615–617` | engaged **or** mentions_warehouse | mentions → action_axis |
| `z13` warehouse clarify | `:854` | `stock_skips_warehouse_clarify` | X6/X9 |
| `z21` wiki axis carriers | `:141–149` | `resolved_warehouse_axis_word(question…)` | Передавать intent; не сканировать phrase как q-слова без action_axis |

---

## 3. Список изъятий (файл:строка) — рабочий чеклист

| ID | Изъятие | Замена | Риск потери складских Q |
|---|---|---|---|
| **B1** | `z12:185–186` (+ весь фоллбэк scan) в candidates | candidates = `action_axis` (+ опц. intent.terms), не токены q | Средний: разбор без axis → нет wh; mitigation: clarify / wiki / требовать action_axis у модели |
| **B2** | `z12:197–199` loop в `resolved_warehouse_axis_word` | только ветка `action_axis` `:195–196` | Высокий на кейсах «ось только в тексте» (замки INTENT_LIVE) — **переписать тесты** |
| **B3** | `z12:297–301` append resolved_wh в `intent_axis_words` | kind + action_axis only | Низкий для корректного разбора; режет ложный breakdown∧«слово склада» |
| **B4** | `z12:331–332` `or resolved_warehouse…` в `secondary_axis_known` | только `intent.action_axis` | Средний: count-agg без axis |
| **B5** | `z12:266+` loop в unaccounted slice | axis из intent | Низкий (узкий journal-ghost) |
| **B6** | `z11:719–721` ранний `_wh(question…)` до дешёвых проверок | сначала want/period/kind; wh = action_axis→place **или** `balance_routing_core` / `_stock_intent_signal` | Низкий при сохранении семантики False на stock |
| **B7** | `z11:754` литералы `"остат","склад"` | negative через `_stock_intent_signal` / `balance_path_engaged` / engaged | Низкий; базлайн трещотки ↓ |
| **B8** | (не код) тест `Q_LIVE` без `action_axis` | `INTENT_LIVE.action_axis="склад"`; assert resolved из intent | Обязателен, иначе замок держит дефект |

**Не изымать в этом пакете:** тела `filter_stock_*` / `stock_goods_pool` / EXISTS; wiki-каскад; z10 «всего»; sales measure «всего»; `_stock_intent_signal` / `balance_axis_registers_confirmed`; OPT-C кэш.

---

## 4. Что уже не word (не путать с именем)

| Функция | Имя звучит как маркеры | Факт тела |
|---|---|---|
| `question_has_aggregate_total_marker` | «маркер всего» | `aggregate_count_intent` (want/amount) + `balance_routing_core` — **intent** |
| `question_wants_per_axis_breakdown` | — | делегат `question_wants_breakdown` (want=list / max|min) — **intent** |
| `question_asks_stock_balance` | — | `balance_path_engaged` — docstring уже «intent, не слова» |
| `_stock_scaffold_stems` | — | kind + action_axis only (`:1116–1127`) — образец К9 |

Паллиатив OPT-S (early-exit из word-детектора) **не удаляет** B1–B2: loop остаётся на настоящих stock-q и на catalog-гейте. Дожиг — B1–B7.

---

## 5. Можно ли изъять без потери складских вопросов?

| Класс вопроса | До (word) | После (intent+meta) | Вердикт |
|---|---|---|---|
| `action_class=object`, `action_axis`→place catalog, kind product/place | engaged | engaged через X7+X12+X4 | **Сохраняется** |
| Count итог + axis в intent (`want=count`, aggregate) | aggregate_total + skips | то же через X9/X10 | **Сохраняется** |
| Breakdown/list по складу с `action_axis` | routing:366 | axes без q-scan | **Сохраняется** |
| «сколько на складе…» **без** `action_axis` в разборе (только текст) | wh True через X1 | wh False | **Теряем silent path** — по К9 это **дефект разбора**, чинить заполнение axis / clarify, не word-loop |
| Sales + `want=list` + product kind («полный отчет») | ложный engaged (opt-s) | после B3 меньше wh; **S1 sales_sum** всё ещё нужен против product-kind∧breakdown | Word-burn **недостаточен** один; держать S1/OPT-C |

Итог: **да**, изъять word-loop можно без потери **канонических** складских Q с заполненным разбором; цена — отказ от компенсации дыр LLM сканом текста (это и есть решение владельца 29.08).

---

## 6. Порядок внедрения (для оркестратора; не код)

1. **B1–B5** в z12 одним патчем (хелпер оси + callers).
2. **B8** замки `test_stock_balance_path` (+ journal-ghost при необходимости).
3. **B6–B7** z11 catalog-гейт.
4. Параллельно/тем же выкатом: OPT-S **S1+S2** + OPT-C (скорость; не замена B1).
5. Grep-замок (роль Y): нет `re.finditer` по question в stock-axis resolve; нет `"остат"/"склад"` в catalog_count deny.
6. О6 z10×13 / остаток z11×23 (мера/ранг/«всего») — **следующий пакет**, не смешивать.

---

## 7. След для ролей Y / Z

- **Y:** эталоны остатков — вопросы с ожидаемым `action_axis`/object; трещотка на исчезновение X1-loop; субмаркер `stock_detect_ms` вокруг `stock_question_engaged` после B1 (без SQL word-loop должен быть ≪9 с даже на cold catalogs-for-kind×1).
- **Z:** контратака «разбор не дал axis» — главный residual; replacements в §2 не вводят новых DOMAIN_LITERAL; инертные helpers / wiki / скоуп «всего» в sales — §2.5 X17–X19 вне пакета.

---

## Источники (код)

- `ubuntu/serenedb/ask/z12_stock_balance.py:113–437`, `:552–618`, `:1116–1157`
- `ubuntu/serenedb/ask/z11_sales.py:10–72`, `:716–756`
- `ubuntu/serenedb/ask/z10_rank.py:29–54`, `:67–101`
- `ubuntu/serenedb/ask/z13_fork_outcomes.py:23`, `:615–617`, `:854`
- `ubuntu/serenedb/ask/z20_ask_main_http.py:2187`, `:2232`, `:2270`, `:2670–2674`
- `ubuntu/serenedb/ask/z21_wiki_choice.py:141–149`
- `ubuntu/serenedb/test_no_domain_baseline.json`, `test_stock_balance_path.py:86–105`
- `docs/PLAN_TO_TARGET.md` §0; `docs/audit/opt-s.md`, `opt-r.md`
