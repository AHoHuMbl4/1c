# Класс «rank-путь»: одна починка координат ответа (okna, K1+K2+K3)

**Статус:** исполнен 25.08 (`ASK_SALES_RANK_CANON`, стейджинг `:8092`; скорер 15→19/24, класс 4/4; бой выкл.).  
**Дата:** 2026-08-25  
**Опора:** [`docs/SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md)
(классы K1–K3, 4 вопроса), [`docs/PLAN_ANSWER_CONTRACT.md`](../docs/PLAN_ANSWER_CONTRACT.md)
§2 / §3 / §6bis / §7, образец структуры [`work/calendar-axis-design.md`](calendar-axis-design.md),
контур `ubuntu/serenedb/serene_ask.py` (канон продаж + rank + W-readings + A/B/C).

Иерархия источников (§7bis): база 1С → сами данные → развилка+память нажатия →  
словарь подписей / алиасов. Новых списков русских слов в Python нет: расширение  
лексики — только данные (`search_measure_alias` / словарь периода), не литералы ask.

---

## 0. Проблема (живая диагностика 25.08, стейджинг `:18092`)

Полный скорер okna: бой и стейджинг **15/24**, diff вердиктов **0**. Кластер  
rank-пути = **K1+K2+K3 = 4** вопроса из 9 FAIL  
([`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) §4).

Повтор `/ask` на стейджинге (Bearer из `/tmp/okna-probe.env`, `user=gold-v2`;  
бой не трогали):

| # | Вопрос | kind | Цитата ответа / diag (не пересказ) |
|---|---|---|---|
| K1a | какого товара больше всего продали за всё время? | answer | text: `«Balama Rollenband…»: 3 271 771.26 лей · … · Всего · Номенклатура · rank`; `sales_canon_locked=accumulationregister_реализациятмц`; `sales_measure_canon={"было":"Количество","стало":"Всего","how":"sales_canon"}` |
| K1b | какой клиент больше всех купил в этом месяце? | answer | text: `«DYNAMIC SELLING… ap. 89»: 1 543 357.32 лей · … · Реализация ТМЦ (документ) · Всего · Контрагенты · rank`; `focus=document_реализациятмц`; `sales_canon_locked` отсутствует; fork `pool_srcs=["document_реализациятмц"]` |
| K2 | дай топ-3 клиента по деньгам за этот месяц | clarify | text: `…: итого? / курс? / НДС? / оплата карточкой? / долг клиента?`; `ambiguity=measure`; `measure_ambiguous=["Всего","Курс","СуммаНДС",…]`; `measure_guess_refused=rerank`; `compute=sum`; `focus=document_реализациятмц` |
| K3 | кто из клиентов молодец за прошлую неделю, три лучших | answer | text: `«VEFASISTEM-COMPANIE…»: 136 906.08 лей · … · 2026-08-24..2026-08-25 assumed · … (документ) · Всего · rank`; `period_leader=wtd`; `intent_assumed=period.from=2026-08-24, period.to=2026-08-25`; fork readings только wtd/full_week текущей недели |

Эталон корпуса (`ab-gold-okna.tsv`): во всех четырёх —  
`accumulationregister_реализациятмц`; товар — мера **Количество**; клиентские —  
мера **Всего**; «прошлая неделя» — полное предыдущее календарное окно  
(`date_trunc('week')−7d … date_trunc('week')`), top-3.

### Общая причина (слой: детектор)

**Канон координат rank×sales (E = регистр по `written_by`, M = роль меры по  
форме rank + алиасы, W = именованное окно) не включается единым контуром:  
src / мера / «отвечать vs clarify» / окно схлопываются разрозненными  
лексическими гейтами (`sales_sum_intent`, `sales_force_money_measure`) до  
счёта классов §3.**

Как бьёт по четырём (один механизм, разные координаты):

| Вопрос | Какая координата сломалась | След гейта |
|---|---|---|
| K1a | M (Количество → Всего) | `sales_sum_intent` да → lock регистра ок; `sales_force_money_measure` всё ещё true на «какого…продали» (в списке только «какой/какая/какие», не род. падеж) → `how=sales_canon` перебивает уже найденное Количество |
| K1b | E (документ вместо регистра) | «купил» не входит в `sales_sum_intent` → `prefer_entity_for_sales` / lock не зовутся → в пуле один документ |
| K2 | M+форма (measure-clarify вместо top-N) | нет sales-canon; `compute=sum` + `measure_guess_refused=rerank` → clarify по полям меры документа, ось Контрагент не собирается |
| K3 | E + W | тот же промах E (документ); период assumed = текущий WTD (24–25.08), readings без предыдущей календарной недели → лидер за чужое окно |

Отдельные «баги на вопрос» здесь — симптомы одной ранней развилки: **rank по  
фактам продаж не проходит §6bis как класс формы**, а как набор подстрок.

---

## 1. Данные

### 1.1. Уже есть (не плодить загрузчик)

| Источник | Роль для rank-пути |
|---|---|
| `search_tables.written_by` / `parent` | подъём документ → `accumulationregister_*` (уже в `prefer_entity_for_sales`) |
| `measures_of` / `search_measure_alias` | роль меры: Количество vs Всего / «деньги» |
| `search_refcols` | оси GROUP BY (ТМЦ, Контрагент) — уже `rank_axis_resolve` |
| `period_readings` / формы mtd\|wtd\|full_* | ось W; лидер `prefer_window_leader` |

### 1.2. Что донастроить данными (не кодом под okna)

1. **Алиасы меры** — фразы роли «деньги / сумма / выручка» → канон денежной  
   меры источника (`Всего` / `*Документа` через существующий  
   `sales_money_measure` + alias_by). Наполнение — штатный контур словаря  
   (как §7 / wiki_alias), без `frozenset` в ask.
2. **Относительные окна периода** (для K3) — phrase → форма  
   `prev_week` / `wtd` / … в meta или рядом со словарём развилок (тот же  
   приём, что day_basis в [`calendar-axis-design.md`](calendar-axis-design.md)
   §2.3). Холодный старт без словаря: always-on конкурирующие week-readings  
   (см. §2.3) + исход B/C, не молчаливый WTD.

Новых EntitySet / SQL-загрузчиков нет. Счёт top-N остаётся штатным  
`GROUP BY` + `sum` по корпусу (как эталон в `ab-gold-okna.tsv`; синтаксис  
интервалов — SereneDB `date_trunc` / `INTERVAL`, см. доки при кодировании).

### 1.3. Слой «прибор»

Дефект прибора как первичная причина класса — **нет**  
([`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) §4  
«Не провалы»). Эталон SQL на той же базе; чинить скорер/эталоны под класс  
запрещено. После починки детектора — только замок «4 зелёные, 20 не  
краснеют» на том же наборе.

---

## 2. Детектор

### 2.1. Один контур вместо четырёх заплаток

Включить **sales-rank canon** когда одновременно:

1. `rank_intent_from(intent, plan, question)` — форма рейтинга/top-N (уже есть);
2. среди кандидатов есть документ/регистр, с которого структурно поднимается  
   sales-register по `written_by` (тот же SQL, что в `prefer_entity_for_sales`,  
   **без** обязательного `sales_sum_intent` на подстроках «продали»).

Тогда одним проходом:

| Координата | Правило лидера | Люк / иначе |
|---|---|---|
| **E** | `prefer_entity_for_sales` → lock `accumulationregister_*` | документ остаётся опцией B/focus по §6bis |
| **M** | rank + нет money-роли из алиасов → `sales_qty_measure`; rank + money-роль из данных → `sales_money_measure`; **не** звать денежный force на любой sales_sum при rank | measure-clarify только если роль меры в данных неоднозначна после алиасов |
| **ось** | уже `rank_axis_resolve` (ТМЦ / Контрагент) | hatch по alts |
| **W** | именованное / словарное окно; иначе readings §2.3 | B/C при разных числах |
| **исход** | top-N / rank_deterministic, не measure-clarify | — |

Почему не четыре патча: K1a/K1b/K2/K3 чинятся одним включением канона на  
**форму rank × структурный sales-src**; морфология «какого/купил/деньгам»  
больше не условие входа.

### 2.2. Где в пайплайне

```
parse_intent
  → apply_period_leader / period_readings          # W, + prev_week см. §2.3
  → candidates / RRF
  → [NEW gate] sales_rank_engaged = rank_intent ∧ lift_possible(cands)
        → prefer_entity_for_sales / sales_canon_force_pool   # E
        → measure: qty | money по роли из alias, не force_money(rank)  # M
  → rank_axis_resolve / rank_deterministic         # ось + ответ
  → fork_scan / resolve_fork_outcome               # A/B/C без новой лестницы
```

Точки правки (имена уже в дереве): `sales_sum_intent` /  
`prefer_entity_for_sales` / `sales_force_money_measure` / блок  
`sales_measure_canon` (~12826) / ветка `measure_ambiguous` clarify /  
`period_readings` (+ форма prev_week). Новый выбирающий арбитр не вводить.

### 2.3. Ось W: предыдущая календарная неделя

Сейчас при assumed WTD readings = текущие `wtd` + `full_week` (диагностика  
K3: `period_leader=wtd`, окно `2026-08-24..2026-08-25`). Предыдущей недели  
в пространстве нет → детектор не видит развилку.

Проект:

1. Форма `prev_week`:  
   `[date_trunc(week, today) − 7d, date_trunc(week, today))` — та же форма,  
   что эталон gold (не скользящие 7 дней).
2. Когда в readings есть текущая неделя (wtd/full_week) **или** словарь  
   периода указал prev — добавить reading `prev_week` в перечень W  
   (always-on по форме, как MTD/full_month).
3. Лидер: словарь/ticket `prev_week` → лидер prev; иначе status quo  
   (`mtd`/`wtd` из `_WINDOW_LEADER_FORMS`). Молчание ≠ выбор (§2 контракта).
4. Без словаря на «прошлую неделю» misparsed как current WTD: числа  
   prev≠wtd → B/C с люком, не уверенный чужой лидер (п. 13/21 лучше, чем  
   молчаливый FAIL). После словаря периода — авто-лидер prev, скорер зелёный.

### 2.4. `sales_force_money_measure` при rank

Правило проекта (универсальное, без расширения списков падежей):

- если `rank_intent_from` → денежный force **выкл.**;
- денежная мера на rank только когда роль меры разрешена из  
  `intent.measure` / `search_measure_alias` / явного money-слова через  
  существующий `measure_choice` (данные), затем `sales_money_measure`.

Это закрывает K1a (Количество больше не перебивается) и K2 (Всего  
фиксируется ролью «деньги», не clarify по Курс/НДС), без хардкода «какого».

### 2.5. Слои: лечится ли класс здесь

| Слой | Лечит класс? | Что меняется |
|---|---|---|
| **Данные** | частично | алиасы меры «деньги»→Всего; словарь relative period → `prev_week`; карта written_by уже есть |
| **Детектор** | **да, ядро** | один gate sales-rank → E+M+анти-clarify; W + `prev_week` reading |
| **Словарь** | подписи/роль | подписи веток W (текущая vs прошлая неделя); не правила «всегда» |
| **Прибор** | нет как причина | после фикса — регрессия 24 вопросов; эталоны не трогать |

---

## 3. Исходы A/B/C

Без новой лестницы. Меняется только **какой атом лидера** и что в пуле:

| Ситуация | Исход |
|---|---|
| регистр+мера+окно единственны | unique / A |
| документ vs регистр, атомы разные | B (лидер = регистр) или C без подписей |
| qty vs money роли разные и обе посчитаны | B/C по мере (подписи из §7) |
| wtd vs prev_week числа разные | B/C по W |
| measure-clarify при однозначной money/qty роли после канона | **запрещён** этим проектом (это и есть K2) |

`fork_leader_class` / `fork_outcome_*` не подменять; `ASK_FORK_OUTCOMES`  
как сейчас.

---

## 4. Флаг / умолчание

| Env | Умолч. | Смысл |
|---|---|---|
| `ASK_SALES_RANK_CANON` | `0` | выкл. на бою; 1 = gate §2.1 + M-правило §2.4 + W `prev_week` |

Бой `:8091` не включать этим заходом. Стейджинг `:8092` — проба после  
кода. Имя флага — рабочее; при реализации можно слить с существующим  
контуром sales_canon, если замер покажет нулевую регрессию sum-пути.

---

## 5. Замки

### 5.1. Оффлайн (расширение существующих; новый файл — на шаге кода)

Уже в дереве: `test_sales_canon_prefer.py`, `test_rank_leader_path.py`,  
`test_fork_window_readings.py`, `test_fork_outcomes.py`,  
`test_calendar_axis.py`, `test_rank_axis_anchor.py`.

| Замок | Что фиксирует |
|---|---|
| rank + document в cands → lock регистра **без** подстроки «продали» | E для K1b/K2/K3 |
| «какого товара…продали» + rank → мера Количество, не Всего | M для K1a |
| rank + money-роль из alias → Всего, **нет** measure_ambiguous clarify | K2 |
| `sales_force_money_measure` false при любом `rank_intent_from` | анти-регресс K1a |
| period_readings: при wtd есть reading `prev_week` с границами gold | W форма |
| словарь/ticket prev → лидер prev_week | K3 авто |
| sum-путь «сколько продали вчера» по-прежнему money+register | регресс §6bis |
| `test_fork_*` + `test_calendar_axis` зелёные | A/B/C и calendar не сломаны |

### 5.2. Живой замок класса (приёмка проекта)

На стейджинге, тот же `ab-gold-okna.tsv` / скорер okna **24** вопроса:

1. **Четыре вопроса класса — OK** (K1a, K1b, K2, K3).
2. **Остальные 20 не краснеют** (вердикты OK остаются OK; новые FAIL = брак).
3. **A/B/C не ломаются:** оффлайн `test_fork_outcomes`,  
   `test_fork_window_readings`, `test_fork_detector`,  
   `test_calendar_axis` — все green.

Доказательство починки класса — этот тройной замок, не ручная правка  
одного эталона.

---

## 6. Вопросы в скорер

Новый набор не заводить: класс уже размечен в  
[`SCORER_CLASSES_2026-08-25.md`](../docs/SCORER_CLASSES_2026-08-25.md) и  
сидит в `ab-gold-okna.tsv` (строки про товар / клиента / топ-3 / прошлую  
неделю). После кода — тот же прибор `ab_scorer.py`, `AB_CONTOUR=okna`.

Критерий: kind=answer (K2 больше не clarify по мере); имена/числа = SQL  
эталона; период K3 = prev_week gold.

---

## 7. Порядок внедрения

### Шаг 1 — оффлайн-замки под проект (без выката)

Кейсы §5.1 красные на текущем коде (ожидаемо) → фиксируют контракт.

### Шаг 2 — детектор за `ASK_SALES_RANK_CANON` (умолч. 0)

Gate §2.1–2.4 в `serene_ask.py`; бой не включать. Проба `:18092`.

**Приёмка:** флаг 0 — md5/поведение sum-пути как до правки; флаг 1 —  
диагностика четырёх вопросов: register lock, меры qty/money, нет  
measure-clarify на K2, readings содержат prev_week.

### Шаг 3 — данные словаря (мера + period), затем скорер

Алиасы / period phrases агентом §7. Живой скорер 24: **4 OK класса, 20 не  
краснеют**. Выкат флага на бой — отдельное слово владельца.

### Шаг 4 — граф + документы статуса

Наблюдение в `mcp-memory.json`; CHANGELOG / activeContext — заходом  
реализации (этот проект их не трогает).

---

## 8. Универсальность

| Проверка девиза | Как проходит |
|---|---|
| Чужая база без правки кода | lift по `written_by` + мерам из `$metadata`/корпуса; имена конфигурации не вшиты |
| Без ручного разбора вопроса | вход — `rank_intent_from` + структура кандидатов, не список «купил/какого» |
| База-специфика | только в alias/meta/словаре, наполняемых агентом |
| Если нет sales-register | канон не lock'ается; clarify/no_data по данным, не догадка |

Если реализация снова полезет в расширение русских подстрок в  
`sales_sum_intent` / `sales_force_money_measure` — это **брак проекта**,  
вернуться к §2.

---

## 9. Риски (кратко)

1. **Ложный lift** на rank не про продажи (рейтинг справочника) — смягчение:  
   lift только если в cands уже есть document/register с `written_by` sales,  
   не cold-lift всего каталога.
2. **prev_week always-on** рядом с «эта неделя» — лишний B; терпимо по §2,  
   пока словарь не сдвинет лидера.
3. **top-K > 1** («три лучших») — отдельный хвост `rank_k`; этот проект  
   чинит src/меру/окно/clarify; если после канона top-1≠top-3 имя эталона  
   всё ещё мимо — добить `rank_k` тем же флагом, не отдельным классом.
