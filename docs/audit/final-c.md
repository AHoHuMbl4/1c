# FINAL-C: атака изъятия stock-фильтров из маршрутизации (роль C, красная)

Дата: 11.09. Режим: **только чтение кода**. Коммитов нет.
Постановка: изъять блок `z20:2227–2238` + stock#2 `z20:2270–2286`
(`filter_stock_*` / `prefer_entity_for_stock` в сборке пула до
`wiki_primary_entity_cascade`). Граница: счётные слои (z16/z17,
`balance_capable_or_registers` при подсчёте выбранной сущности) не трогать.

Опоры: живой код `z20`/`z21`/`z12`/`z13`/`z11`; зонд-факты OPT-S/C/P
(50,6 с / 25,3 с / ~77 cands); `SPEED_ASK_PLAN` A/B; `corpus_merge.sql`
(гвард 10% — отдельный контур).

---

## Вердикт одной строкой

**Условно допустимо, не «безопасно само по себе».** Изъятие закрывает ~75 с
ложного engage и **не** краснит прод через гвард 10% «снесло бы» (ложная
связь контуров). Главная дыра качества: вики-пул **уже не чистится**
stock-фильтрами `cands` (пулы ортогональны); паспорт **не** отвергает
«продажи вместо остатков» структурно — при холодной/дырявой вики возможен
`confident_wrong`. Закрытие — L67 на складском gold (`confident_wrong=0`)
+ покрытие карточек баланс-регистров + честный `no_data`/`clarify`, а не
надежда на паспорт как на сторожа склада.

---

## 1. Холодная вики: арбитр → продажи → wrong?

### 1.1 Факт по коду: фильтры `cands` ≠ пул вики

Порядок в `z20`:

1. Сборка `cands` + stock-фильтры (`:2227–2238`, `:2270–2286`).
2. Позже `wiki_primary_entity_cascade` (`:2835`) →
   `try_wiki_hybrid_entity_pick` → `wiki_hybrid_pool(question, intent)`.

`wiki_hybrid_pool` (`z21:199–238`) читает **свой** SQL
(`wiki_card_hybrid.sql`: kNN ∪ struct по `search_wiki_entity_card`),
аргумент `cands` в каскад **не подмешивается**. Stock-чистка `cands`
засоряет/чистит голову для K6, fork (`prefer_entity_for_stock` на
`cands[:ARBITER_MAX*4]`, `:2685–2692`) и arb_pool (`:3302`) — но **не**
карточки вики.

Следствие атаки: «убрать фильтры → пул вики грязнее» — **ложно**. Пул
вики и сегодня не чистится `filter_stock_*`. Изъятие меняет риск на
**fallback/arbiter/fork**, не на primary wiki-путь.

### 1.2 Сценарий: нет карточки у баланс-регистра

`struct_register` / kNN в hybrid SQL берут только строки
`search_wiki_entity_card`. Нет карточки у `accumulationregister_*`
остатков → регистр **не входит** в wiki-пул. В пуле остаются соседи по
kNN (часто документы/регистры оборота с живыми карточками).

Цепочка по коду (`z21:913–995`, `:492–536`, `:1067–1097`):

| Исход | Что делает код | Wrong? |
|---|---|---|
| Пустой пул + `question_expects_accounting_data` | `wiki_empty_pool` → cascade `kind=no_data` (`:695–704`) | Нет — honest_no |
| Пустой пул + не accounting | `wiki_none_empty` → no_data | Нет |
| Карточки есть, verify все `fit=no` | `outcome=none` → no_data | Нет |
| Несколько `yes`/`unsure` | `clarify` / collapse | Нет (п.12) |
| Один `fit=yes` на **продажи** | `leader` → `wiki_leader_post_verify` | **Да, если post_verify True** |

### 1.3 Закроет ли паспорт-верификация?

**Нет как сторож «остатки ≠ продажи».**

- `WIKI_VERIFY_SYS` (`z21:50–57`) — модель `yes|no|unsure` по паспорту;
  структурного правила «sales-noise имя → no» нет.
- `wiki_validate_leader_axes` (`:586–598`) — только префикс формы
  (`catalog|document|accumulationregister|…`); `accumulationregister_реализац*`
  проходит.
- `wiki_leader_post_verify` (`:1067–1097`) — named measure + `action_axis`
  (refcols). Отвергнет продажи **только если** в intent есть
  `action_axis` (склад) и у лидера нет ref на place-каталог →
  `axis_not_carried` → `None` → honest_no. Без оси места (вопрос
  «сколько остатков товара») post_verify **пропускает** sales-лидера.

Арбитр после wiki (`z20:3302` `prefer_entity_for_stock` на arb_pool):
если prefer **тоже** изымается из маршрутизации (трещотка роли B),
соперники не вытесняют продажи из головы `cands`. Если prefer
оставить на arb_pool — смягчает fallback, но это уже не «полный
вынос» и противоречит grep-замку B.

**Итог атаки 1:** паспорт ≠ stock-фильтр. Закрытие:

1. Приоритет — **карточки** баланс-регистров в `search_wiki_entity_card`
   (struct/kNN видят остатки).
2. Допустимый исход без карточки — `no_data`/`clarify`, не число продаж
   (`confident_wrong=0` на L67).
3. Не чинить изъятие новым сторожем-словарём в маршруте (решения №1/№10);
   чинить начало (вики/паспортное знание), не возвращать `filter_stock_*`.

---

## 2. Пул растёт: 77 → сколько? K6 / арбитр

### 2.1 Что фильтры реально делают с размером

Факт зонда: «~77 кандидатов» — размер **до/вокруг** K6, не результат
чистки до 3. По коду (`opt-p` P5, `opt-s` §3):

- `filter_stock_balance_sales_noise` — Python-отсев имён
  (`реализац` / `книгапродаж` / сверка): обычно **единицы** src.
- `filter_stock_goods_registers` — убирает `accumulationregister_*`
  вне `stock_goods_pool`; при пустом `out` — **подмена** `list(pool)`
  (`z12:882`). Тяжёлое — SQL EXISTS в `registers_for_kind_axes`
  (`z12:457–466`), не цикл ×77.
- `prefer_entity_for_stock` (else-ветка / fork / arb) — **сужает** к
  goods-pool + canon в голове, не расширяет.

Оценка после изъятия маршрутных фильтров:

| Узел | Было (порядок) | Станет | Время |
|---|---|---|---|
| Вход K6 (`cands`) | ~70–80 (после редкой чистки) | **~те же 70–90** (шум sales/non-goods остаётся) | K6-apply зонда **1,3 с** — рост маргинален (фичи по списку, не EXISTS×N) |
| `stock_goods_pool` EXISTS | 1–2× на stock#1+#2 | **0** в маршруте | **−50,6 − ~15…25 с** (цель изъятия) |
| Арбитр | `ARBITER_MAX=3` (`z20:849`) | **всё ещё ≤3** | wall = sum/max sub-answer, **не** ×\|cands\| |
| Fork-голова | `cands[:12…16]` + prefer_stock | без prefer — грязнее голова, размер бюджета тот же | риск качества fork A/B/C, не линейный рост wall |

**Ответ на «77→сколько?»:** для K6/арбитра по wall — **≈77→≈77…90**
кандидатов на ранжирование, арбитр **остаётся 3**. Страх «арбитр ×77»
кодом не подтверждён. Выигрыш изъятия — исчезновение EXISTS/word-loop
детектора, не сжатие 77→3.

### 2.2 Где рост пула бьёт по качеству, не по секундам

Без `prefer_entity_for_stock` / noise-drop голова `cands` и fork-пул
могут держать sales рядом с остатками → чаще clarify (хорошо для п.12)
или, при сломанной вики, wrong (плохо). Это аргумент L67, не ETA.

---

## 3. STOP-гвард 10% «снесло бы» — встанет ли прод?

**Нет. Связь отсутствует.**

- Гвард «удаление снесло бы >10%» — `corpus_merge.sql` (~`:688–709`),
  числитель = unmatched ∪ объяснения shrink/repost/… по **корпусу**.
- `filter_stock_*` / `prefer_entity_for_stock` / `stock_question_engaged`
  живут в **ask** (`ubuntu/serenedb/ask/`). Grep по `corpus_merge.sql`:
  совпадений с stock-фильтрами ask — **0**.
- «Складская убыль объяснена» в merge — свидетели витрины/маркеров
  строк (`tmp3_merge_shrink`, deleted_delta, …), не маршрутизация
  выбора сущности в `/ask`.

Атака «без фильтров ask первая складская дельта в 1С покраснит merge»
— **категориальная ошибка**. Изъятие ask-маршрута merge-STOP не
двигает. (Отдельный риск Full-B / partial unmatched — вне скоупа FINAL.)

---

## 4. Catalog-гейт без word-loop: «сколько всего товаров»

### 4.1 Куда идёт вопрос сегодня

`catalog_kind_total_question` (`z11:716–740`):

1. Сейчас первым зовёт `question_mentions_warehouse_axis` (word-loop /
   ось) — при True → **False** (не catalog-kind-total).
2. `want` ∈ {count,""}, без периода, `kind` → catalogs.
3. Если любой catalog — **product** (`_is_product_catalog`) → **False**.

«Сколько всего товаров» при `kind≈товар/номенклатура` резолвится в
product-catalog → функция **False** независимо от word-loop склада.
Дальше:

- `catalog_count_question` (`:743–756`): True только через kind-total
  **или** прайс-лексику (`прайс`/`номенклатур`/…) с deny
  `остат|склад|прода|куп`. Одно «товаров» без прайс-маркера → **False**.
- `stock_question_engaged`: `_kind_is_stock_scoped` True на product-kind
  (`z12:113–126`) → при balance/stock-signal — **складской/вики путь**,
  не `kind=catalog_count`.

Итого: целевой kind ответа — **не** `catalog_count`, а stock/wiki
(остатки / net-distinct / clarify), как и задумано для «товаров» как
ТМЦ.

### 4.2 Что меняет изъятие word-loop (burn-X14) vs изъятие фильтров

- Убрать ранний wh-вызов из `catalog_kind_total` (9,5 с на зонде) для
  **этого** Q почти no-op: product-kind и так False после catalogs.
- Убрать stock-фильтры `cands`: на true-stock Q перестаёт EXISTS-чистка;
  выбор — вики. **Не** перекидывает Q в catalog_count.
- Риск сломать: вопросы вида «сколько организаций всего» (non-product
  kind) — они как раз живут catalog_kind_total; wh-guard должен остаться
  **intent/meta**, не word-loop (burn-x), иначе ложный False на «склад»
  в тексте без stock-intent.

**Вердикт по п.4:** «сколько всего товаров» изъятием маршрутных
stock-фильтров **не** уезжает в `catalog_count`. Регресс — только если
параллельно сломать product-гейт в `catalog_kind_total` или
`_kind_is_stock_scoped`.

---

## 5. Совместимость с A-блоком (ранний clarify) и B-дедлайном

Контур: `SPEED_ASK_PLAN_2026-09-11` — A = early entity-clarify до
arbiter×N (`z20:3623+`); B = `ASK_DEADLINE_SEC=88` < `ASK_TIMEOUT=90`.

| Ось | Эффект изъятия |
|---|---|
| Ложный stock на sales+list (зонд) | −50,6/−25,3 с **до** A/B → меньше `deadline_aborts`, A чаще успевает |
| True-stock, вики-лидер verified | `wiki_arbiter_locked` / `_ec_wiki` гасит early-clarify (`:3653–3657`) — как сейчас; фильтры cands не участвовали |
| True-stock, вики tie / fallback, грязный arb_pool | Чаще `len(arb_pool)>1` → **A срабатывает чаще** (меню побеждает deadline) — совместимо с A, полезно для B |
| Оставить `prefer_entity_for_stock` только на `:3302` | Сужает arb_pool → реже A; противоречит полному выносу |
| Поднять `ASK_DEADLINE_SEC` | **Не нужно** и запрещено планом (инвариант моста) |

Конфликта A↔B изымание **не создаёт**: экономит префикс; на неоднозначности
толкает в уже принятый early-clarify. Риск — качество меню (sales в
options), ловится L67 clarify≠wrong.

---

## 6. Сводка атак → условия внедрения

| # | Атака | Вердикт | Условие / закрытие |
|---|---|---|---|
| C1 | Cold wiki → sales wrong | **Реальна** на verify-yes без оси места | Карточки баланс-регистров; L67 `confident_wrong=0`; honest_no/clarify ок; не ждать structural reject от паспорта |
| C2 | 77→N, арбитр тормозит | **Слаба** | N≈77…90; ARBITER_MAX=3; wall выигрывает от −EXISTS |
| C3 | Гвард 10% merge | **Ложная** | Не блокирует изъятие; контуры разведены |
| C4 | «всего товаров» → catalog_count | **Не ломается** фильтром | Не трогать product-гейт kind-total; wh в catalog — intent, не word |
| C5 | A/B | **Совместимо / помогает** | Не поднимать deadline; L67 на clarify-меню |

### Вердикт роли C

**Изъятие маршрутных stock-фильтров — ДОПУСТИМО при условиях:**

1. Дифф только маршрутизация выбора (`z20:2227–2238`, `:2270–2286` и
   согласованные вызовы prefer/filter в сборке пула/fork/arb **если**
   трещотка B требует чистоты z20); счётные `stock_question_engaged` /
   `balance_capable_*` / net-aggregate **не** вырезать.
2. Обязательный L67 до/после на складском срезе gold (роль B: 18+3+5):
   `confident_wrong=0`, match не хуже.
3. Замер 3 классов wall (sales-list / stock-остатки / catalog-count) —
   ожидание: sales-list ≪ зонд; stock не хуже wall существенно; catalog
   без регресса.
4. Приёмка cold-wiki: пустой/чужой пул → `no_data`|`clarify`, не число
   с sales-src (diag `wiki_empty_pool` / `wiki_none` / `axis_not_carried`).
5. Grep-замок B против возврата фильтров в маршрут.
6. Не путать с burn word-loop и с Full-B / merge-гвардами.

**Без п.2–4 — НЕ выкатывать:** философия «один судья = паспорт» при
дырявой вики даёт wrong, который старые фильтры `cands` **и так не
лечили на primary wiki-пути**, но лечили fallback/fork голову; полный
вынос убирает этот мягкий слой — качество держит только вики+L67.

---

## Ссылки на код

- `ubuntu/serenedb/ask/z20_ask_main_http.py:2227–2287`, `:2685–2692`,
  `:2835–2842`, `:3302`, `:3623–3657`
- `ubuntu/serenedb/ask/z21_wiki_choice.py:199–238`, `:492–536`,
  `:586–598`, `:913–995`, `:1067–1097`
- `ubuntu/serenedb/ask/z12_stock_balance.py:416–437`, `:847–882`,
  `:1065–1094`
- `ubuntu/serenedb/ask/z13_fork_outcomes.py:9–28`
- `ubuntu/serenedb/ask/z11_sales.py:716–756`
- `ubuntu/serenedb/wiki_card_hybrid.sql` (knn / struct_register)
- `docs/audit/opt-s.md`, `opt-c.md`, `opt-p.md`, `SPEED_ASK_PLAN_2026-09-11.md`
