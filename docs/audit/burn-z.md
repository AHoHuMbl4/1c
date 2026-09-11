# BURN-Z: красная атака дожига word-детектора складского пути

Дата: 11.09.2026. Режим: **только чтение**. Коммитов нет.  
Роль **Z**. Вход: постановка владельца (К9-ф3 / п.0), зонд OPT-S
(`docs/audit/opt-s.md`, rid `b11dac07`), красная OPT-R (`opt-r.md`), код
`z12` / `z11` / `z10` / `z20` / `z21`, замки `test_stock_balance_path.py`,
`test_no_domain_wordlists.py` (+ baseline z10×13 / z11×24), gold
`client-gold-okna.tsv`, `docs/PLAN_TO_TARGET.md` §0, activeContext
(инертные stock-helpers).

---

## Вердикт одной строкой

**Изымать сейчас** — word-loop’ы и ложный engage в **складской маршрутизации**
(`stock_question_engaged` и его ворота), но **не** подменой OPT-S
(`sales_sum_intent` early-exit): это паллиатив и снова слова вопроса.
Настоящий дожиг обязан **сузить** `_stock_intent_signal` / `balance_routing_core`:
сейчас `want=list` + любой `kind` уже даёт «складской» сигнал — дыра зонда
живёт **внутри «intent»-детектора**, не только в word-loop.  
**Отдельным пакетом** — О6-выжигание z11/z10 («всего»/sales-лексика), удаление
инертных helpers, полный отказ от question→ось в `resolved_*` **после** замера,
что разбор стабильно кладёт `action_axis` / `action_class=object` на gold
остатков. Скоуп «всего» — **только складской маршрут**; трогать
`total_question_skips_axis` / sales-маркеры сейчас = расползание.

---

## 0. Что атакуем (карта, без дубля роли X)

Цепочка ложного engage на sales+«полный отчет» (OPT-S, код сверен):

| Узел | Файл:строка | Роль в дыре |
|---|---|---|
| `question_wants_breakdown` | `z10:29–41` | `want=list` ← «полный отчет» / list-ось разбора |
| `intent_axis_words` | `z12:284–302` | **всегда** тянет `kind` (+ `action_axis` / resolved) |
| `balance_routing_core` | `z12:353–368` | breakdown ∧ `intent_axis_words` → True; `sales_kind_in_intent` **не** ловит «продали» при kind=товар |
| `_kind_is_stock_scoped` | `z12:113–126` | kind→product-catalog («чего»/товар) → True |
| `stock_question_engaged` | `z12:416–437` | идёт в `balance_routing_core`, **не** в `balance_path_engaged` (там есть `sales_sum_intent`) |
| word-loop | `z12:161–200`, `:395–401`; `z11:716–721` | платит секунды даже при False; на rid **не обязателен** для True |

Контраст уже в коде:

```383:392:ubuntu/serenedb/ask/z12_stock_balance.py
def balance_path_engaged(intent, plan=None, question=""):
    """Balance-path: routing по intent; sales-sum исключается."""
    if sales_sum_intent(intent or {}, question):
        return False
    return balance_routing_core(intent, plan, question)


def question_asks_stock_balance(question, intent=None, plan=None):
    """Вопрос про остаток — триггер balance-path (intent, не слова вопроса)."""
    return balance_path_engaged(intent, plan, question)
```

Docstring `:391` («intent, не слова») **врёт относительно engage**: боевой гейт
— `stock_question_engaged`, не `question_asks_stock_balance`.

---

## 1. Атака: intent молчит, вопрос про остатки (разброс разбора)

### 1.1 Разбор не кладёт ось / класс

Живой замок прямо кодирует сценарий «ось только в тексте»:

```86:105:ubuntu/serenedb/test_stock_balance_path.py
INTENT_LIVE = {"want": "count", "kind": "позиции", "action_class": "object",
               "terms": [], "action_axis": ""}
Q_LIVE = "сколько на складе позиций всего"
...
t("live intent: dict axis from question",
  A.resolved_warehouse_axis_word(Q_LIVE, INTENT_LIVE).startswith("склад"))
t("live intent: warehouse axis mentioned",
  A.question_mentions_warehouse_axis(Q_LIVE, INTENT_LIVE))
```

`resolved_warehouse_axis_word` (`z12:190–200`): сначала `action_axis`, иначе
цикл `_question_dictionary_axis_candidates` по **словам вопроса и terms**.
Это и есть word-механика оси места.

**Если изъять цикл без компенсации** (только `action_axis` ↔ `search_refcols`):

| Разбор | Сегодня | После голого burn |
|---|---|---|
| `action_axis="склад"`, `action_class=object` | engage OK | OK (целевой путь) |
| `action_axis=""`, слово «склад» только в q | ось из словаря q | **нет оси** → engage↓ |
| `action_class`≠`object`, нет breakdown | часто False | False |
| kind пустой / «позиции» без product-catalog | держится на wh-оси из q | **теряем** |

Gold-остатки в `client-gold-okna.tsv` почти все содержат «склад/остат*» в
тексте (стр. 5–20, 25–26, 60–63, 68…). Многие эталоны сейчас `no_data`/`match`
через витрину — **путь** всё равно должен остаться складским (фильтры,
fork place, skip clarify), иначе уйдут в catalog-count / wiki-карточку
склада как сущности.

### 1.2 Честный no → wrong?

Два разных регресса:

1. **match / честный stock-no_data → чужой путь с числом** = **wrong**
   (п.10 хуже отказа). Пример: «сколько на складе позиций» → count по
   `catalog_*` без остатков; или sales-путь на смешанной формулировке.
2. **match → honest_no** = регресс п.21 (данные есть, путь отрезан). На gold
   с `no_data` эталоном вердикт может **не сдвинуться**, а механика уже
   сломана — L67 по вердиктам **слеп**, нужны diag-маркеры
   (`stock_question_engaged`, `stock_canon_*`, fork `place`).

Разброс INTENT_SAMPLES (уже в activeContext / speed-аудит): один и тот же
складской вопрос то с `action_axis`, то без — **word-fallback сейчас маскирует
дырявый разбор**. Дожиг без ужесточения контракта разбора (или без
метаданных-only резолва terms→ось **через словарь базы**, не через
маршрутизационный any-in-q) поднимает дисперсию match↔honest_no.

**Контратака Z:** изъятие word-loop допустимо только вместе с правилом:
ось места = `action_axis` **или** terms/группы разбора, прогнанные через
**тот же** `_catalogs_for_warehouse_axis_word` / `search_refcols` — без
`re.finditer` по сырому `question`. Сырой вопрос в маршрутизации = дефект
п.0; terms из разбора = поле intent (К9).

### 1.3 Саботаж «intent-детектора»

```371:380:ubuntu/serenedb/ask/z12_stock_balance.py
def _stock_intent_signal(intent, plan=None, question=""):
    """Сигнал остатка из разбора модели — без подтверждения метаданными."""
    ...
    if question_wants_breakdown(intent, plan) and intent_axis_words(intent, question):
        return True
```

`intent_axis_words` включает **kind**. Значит `_stock_intent_signal` ≡
«есть list/breakdown и любой kind» (минус event/sales_kind). На зонде этого
достаточно для ложного склада **даже после удаления word-loop**.

**Вердикт по (1):** нельзя «просто вырезать mentions_*». Обязательно сузить
сигнал: склад = `state_path` (`action_class=object`) **и/или** подтверждённая
ось места из метаданных; `want=list`+product-kind **без** place-оси — **не**
склад. Иначе burn не лечит 50,6 с и рискует wrong на границах.

---

## 2. Атака: replacements снова словесные (грань no_domain_wordlists)

### 2.1 OPT-S S1 = запрещённый паллиатив для этой волны

Владелец (постановка BURN): early-exit из word-детектора / OPT-S — **не**
цель. `sales_sum_intent` (`z11:21+`) — классический `any(w in q …)` по
«продали/оборот/…». Повторный зов из `stock_question_engaged`:

- не новый литерал в baseline (OPT-R At2 это уже сказал);
- но **закрепляет** word-слой как гейт склада → противоречит К9-ф3 и
  `PLAN_TO_TARGET.md` §0 («предметные слова в маршрутизации — дефект»).

Допустимый **не-словесный** анти-sales: уже живой `sales_kind_in_intent`
(поля `kind`/`measure` разбора) + `event_path_active`. Дыра зонда как раз в
том, что при «продали» разбор часто ставит **product-kind**, а не sales-kind —
лечить надо **позитивным** складом (object + place↔refcols), а не
расширением sale_q.

### 2.2 «Полный отчет»

Запрещено (OPT-R At1, повтор Z): любой deny/allow list «полный отчет /
отчёт» в routing. Разрез уже в `want=list` / `question_wants_breakdown`
(`z10:29–41`) — форма вопроса, не домен. **В диффе burn — ноль новых
DOMAIN_LITERAL и ноль новых any-in-q.**

### 2.3 Замок не ловит главный word-loop

`test_no_domain_baseline.json`: **z12 отсутствует** (0 hits). Word-механика
склада — не литералы «склад/остат», а цикл слов q → catalogs (`z12:185–199`).
Трещотка no_domain **не остановит** ни сохранение loop, ни «умный» SQL по
каждому токену вопроса. Нужен отдельный grep-замок роли Y:
`re.finditer` / `_question_dictionary_axis_candidates` **не** участвуют в
`stock_question_engaged` / `balance_routing_core` / `catalog_kind_total_question`.

### 2.4 Серая зона уже в «intent»

`sales_kind_in_intent` держит подстроки «продаж/торг/…» в kind/measure —
базлайн z11, не question-router. Для burn склада **не расширять**; выжигать
— пакет О6, не эта волна.

---

## 3. Атака: инертные stock-helpers

activeContext (02.09): `warehouse_clarify`, `balance_bridge_clarify`,
`stock_subject_needs_clarify` — **только тесты**, «отдельным решением».

Факт кода 11.09:

| Символ | Определение | Боевой зов |
|---|---|---|
| `warehouse_clarify` | `z20:1746` | вызовов `warehouse_clarify(` в ask/ **нет** (только тесты) |
| `balance_bridge_clarify` | `z12:1310` | тесты; ранние return из answer сняты (трек RM2) |
| `stock_subject_needs_clarify` | `z12:622` | тесты; не в hot path engage |
| `stock_skips_warehouse_clarify` | `z12:574` | **жив** — `z13:854` (fork place → breakdown) |

**Вердикт Z:** в пакет BURN **не включать** удаление инертных helpers.
Смешение с маршрутизацией раздует дифф, ломает замки
`test_warehouse_axis_autonomy` / куски `test_stock_balance_path`, не даёт
−сек на зонде. `stock_skips_warehouse_clarify` — **не** инертный: при burn
engage его поведение надо пересчитать от нового сигнала (иначе fork place
разъедется с wiki).

---

## 4. Атака: совместимость с wiki-каскадом

Порядок в `z20`: stock-фильтры (`:2232+`, `:2270+`) **до**
`wiki_primary_entity_cascade` (`:2835+`). Ложный engage на sales+list
засоряет пул до вики — burn **помогает** wiki на классе зонда.

Риски:

1. **`wiki_leader_post_verify`** (`z21:1067+`) для оси берёт
   `intent.action_axis`, иначе `resolved_unaccounted_slice_axis_word`
   (тоже словарь по словам q, `z12:250–281`). Складской burn, трогающий
   только `stock_question_engaged`, вики **не чинит и не ломает** — пока
   не вычищают `resolved_*` общим ножом.
2. Если burn **сужает** engage так, что складские q перестают
   `stock_question_engaged`, fork (`z13:615–617`) может не поставить
   `place`, а `stock_skips_warehouse_clarify` перестанет срабатывать →
   лишний clarify / другой исход при живой wiki-карточке. Приёмка: gold
   «какие есть склады» / «места хранения» vs «остатки по складам» —
   разные пути (catalog vs stock).
3. Canon-lock после wiki (`prefer_entity_for_stock` / `stock_canon_*`) —
   не разжимать в этом пакете (уже разобрано в TD1/TP): burn engage ≠
   трогать post-wiki prefer.

**Вердикт Z:** burn совместим с wiki, если (а) не трогает z21 verify-ось
в том же диффе без замера; (б) L67 + diag на stock **и** wiki-locked
sales/catalog вопросах.

---

## 5. Атака: скоуп «всего» (z11/z10 vs склад)

Baseline трещотки (факт): **z10×13**, **z11×24**, z12=0. В z10 —

- `total_question_skips_axis` (`z10:44–62`): `any(w in q … «всего/итого»)`) —
  **clarify-skip для итогов**, в т.ч. продаж/ранга, не складской engage.
- rank-маркеры «больше всего» и т.п.

В z11 — sales/прайс/суперлативы («лучше всего», «продаж», …) +
`catalog_count_question` режет `остат/склад` в **тексте** (`z11:754–755`).

**Вердикт Z по скоупу:**

| Трогать в BURN сейчас | Не трогать |
|---|---|
| `stock_question_engaged` и вызовы word-axis **как ворот склада** | `total_question_skips_axis` / «всего» в z10 |
| `catalog_kind_total_question` → убрать платный `question_mentions_warehouse_axis` word-loop; заменить проверкой оси из intent↔meta | sales any-in-q, прайс-лексика z11 |
| сужение `_stock_intent_signal` / `balance_routing_core` (list+kind ≠ stock) | О6-массовое выжигание baseline z10/z11 |
| опционально: выровнять engage с `question_asks_stock_balance`, но **без** опоры на `sales_sum_intent` как главный гейт | инертные helpers |

Слово «всего» в gold («сколько на складе позиций **всего**») сегодня
попадает в aggregate через **intent** (`aggregate_count_intent` /
`question_has_aggregate_total_marker` → `balance_routing_core` + count), не
через маркер «всего» в z12 (функция `:404–408` маркеров вопроса **не
читает** — docstring честен). Путать с z10-«всего» нельзя.

---

## 6. Сводка атак → требования к плану внедрения

| # | Атака | Требование к burn |
|---|---|---|
| Z1 | list+kind = ложный `_stock_intent_signal` | Сузить: place-ось из meta **или** `action_class=object` + оси; list+product без place ≠ stock |
| Z2 | вырез word-loop без terms/action_axis | Ось: только поля разбора → `search_refcols`; сырой q — вне routing |
| Z3 | OPT-S / `sales_sum_intent` early-exit | **Отклонить** как целевой гейт склада (паллиатив + слова) |
| Z4 | «полный отчет»-списки | Запрет; только `want`/`plan.compute` |
| Z5 | no_domain не видит loop | Отдельный grep-замок на candidates/finditer в stock-route |
| Z6 | инертные helpers | Вне пакета |
| Z7 | wiki | Не смешивать с z21 unaccounted; L67+diag stock/wiki |
| Z8 | «всего» z10/z11 | Скоуп только складской маршрут; О6 — позже |

Кэш pred + снятие дубля stock#2 (OPT-C) — **второй слой**, ортогонален
дожигу; Z не возражает (уже принято постановкой).

---

## 7. Вердикт: что изымать сейчас / что отдельным пакетом

### Сейчас (пакет BURN-склад)

1. **Сузить** `_stock_intent_signal` и ветку breakdown в `balance_routing_core`
   так, чтобы sales+«полный отчет»+product-kind **не** включали склад
   (позитивный критерий К9, не sale_q).
2. Убрать из ворот `stock_question_engaged` / `catalog_kind_total_question`
   оплату и семантику **question-word → warehouse axis** (loop
   `_question_dictionary_axis_candidates` / `question_mentions_warehouse_axis`
   как router). Замена: `action_axis` (+ terms разбора) ↔
   `_catalogs_for_warehouse_axis_word` / place catalogs из `search_refcols`.
3. Переписать замки, которые **требуют** ось из сырого q (`INTENT_LIVE` +
   Q_LIVE без `action_axis`) — либо заполнять `action_axis` в фикстуре, либо
   резолв через terms, иначе тесты закрепят дефект.
4. Приёмка: stock-замки + L67 (вердикты **и** diag engage) на классах
   stock / sales+list / catalog-count; субмаркеры «stock-detect ≤ N мс»
   (роль Y); no_domain счётчик **не↑**.

### Отдельным пакетом

1. **О6** — выжигание baseline z11×24 / z10×13 (включая «всего» в
   `total_question_skips_axis`, sales/прайс any-in-q).
2. Удаление инертных `warehouse_clarify` / `balance_bridge_clarify` /
   `stock_subject_needs_clarify` (+ чистка тестов).
3. Полный отказ от question-scan в `resolved_unaccounted_slice_axis_word`
   и вики-fallback оси — после замера разброса action_axis на gold.
4. Любой «временный» `sales_sum_intent` в `stock_question_engaged` как
   костыль к п.1 — **не** делать; если когда-либо понадобится симметрия с
   `balance_path_engaged`, это отдельное решение владельца против п.0.

### Не изымать «на всякий случай»

- Живой `stock_skips_warehouse_clarify` / fork place (`z13`) — перенастроить
  под новый сигнал, не выкидывать вслепую.
- OPT-C кэш / дедуп stock#1/#2 — оставить как слой скорости.
- Post-wiki canon/prefer — вне скоупа BURN.

---

## 8. Источники (код / доки)

- `ubuntu/serenedb/ask/z12_stock_balance.py` `:113–437`, `:574–633`
- `ubuntu/serenedb/ask/z11_sales.py` `:10–71`, `:716–756`
- `ubuntu/serenedb/ask/z10_rank.py` `:29–62`
- `ubuntu/serenedb/ask/z20_ask_main_http.py` `:2232+`, `:2270+`, `:1746`
- `ubuntu/serenedb/ask/z21_wiki_choice.py` `:1033–1097`
- `ubuntu/serenedb/test_stock_balance_path.py` `:45–111`
- `ubuntu/serenedb/test_no_domain_wordlists.py` + `test_no_domain_baseline.json`
- `ubuntu/serenedb/client-gold-okna.tsv` (остатки/склады)
- `docs/audit/opt-s.md`, `docs/audit/opt-r.md`
- `docs/PLAN_TO_TARGET.md` §0; `memory_bank/activeContext.md` (инертные helpers)

**Числа:** baseline no_domain z10=13, z11=24, z12=0; зонд OPT-S stock#1=50,6 с,
catalog word-loop≈9,5 с, stock#2=25,3 с — атрибуция OPT-S/R, Z по коду
подтверждает механизм ложного engage (list+kind), не переснимал зонд.
