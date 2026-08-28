# Ось развилки «валюта документа vs валюта учёта» (okna, §7bis)

**Статус:** шаг 2 ask-кода выполнен 28.08 (зона `z04b_currency_axis`, флаг
`ASK_CURRENCY_AXIS` умолч. 0). Шаг 1 корпуса (`search_currency_map`) — вне этого
захода; ось на стейджинге открывается только при непустой карте meta.  
**Дата:** 2026-08-27 (сводка замера C1 25.08)  
**Опора:** замер C1 / перепроверка okna `:17890`
([`.claude/state/prompt-currency-impl.md`](../.claude/state/prompt-currency-impl.md),
§0–§7 прежней версии этого файла, коммит `ecfbf83`),  
[`work/calendar-axis-design.md`](calendar-axis-design.md) (образец 6 разделов),  
[`docs/PLAN_ANSWER_CONTRACT.md`](../docs/PLAN_ANSWER_CONTRACT.md) §2 / §7 / §7bis,  
точка вставки в `ubuntu/serenedb/corpus_build.sql` (образец `balance_registers` /
блок «1-кватер. ОСЬ ДАТ ГРАФИКА»),  
W-трек в `ubuntu/serenedb/serene_ask.py` (`period_readings`, fork, ticket /
`ask_choice_memory`),  
[`docs/GOLD_SETS.md`](../docs/GOLD_SETS.md) (рабочий vs приёмочный набор).

Иерархия источников (§7bis): база 1С → сами данные → развилка+память нажатия →  
внешний справочник последним. Списков ISO-кодов / «MDL» / «EUR» / Ref_Key в  
Python нет. Имена EntitySet человеку не показываются.

---

## 0. Зачем ось (числа замера, не гипотеза)

Живая витрина okna 25.08 (`serene_ro`, read-only; зерно = шапка
`DISTINCT ON (Ref_Key)`, проведённые + неудалённые):

| Метрика | Число |
|---|---:|
| шапок `Document_РеализацияТМЦ` | **8 237** |
| из них курс ≠ 1 (FX) | **40** (все — август 2026) |
| Σ «Всего» (валюта документа) | **78 758 010,00** |
| Σ «Всего × Курс» (валюта учёта) | **79 133 447,03** |
| Δ doc vs acct | **375 437,03** |
| доля Δ в окне августа | **10,3 %** от doc_raw; на одном доке до **19,23×** |

Справочники / якоря (тот же замер + инвентарь):

| Сущность (витрина) | Строк | Роль |
|---|---:|---|
| `Catalog_Валюты` | **6** | рабочие валюты |
| `InformationRegister_КурсыВалют` | **3 824** | Period + курс (+ кратность в структуре регистра) |
| `Constant_ВалютаБухгалтерскогоУчета` | **1** | якорь валюты учёта (= MDL на okna) |
| документных EntitySet с `Валюта_Key` + `Курс` | **36** | факты для карты amount |

**Бой `:8091` сейчас:** «сколько продали в евро» → число регистра **3 817 442,31**,
`unit` пуст — молдавские леи без пометки. Это п. **10** (чужое число) и п. **13**
(молчаливая подмена размерности). Умножения на курс в пути ответа нет;
подпись денег — env-константа, не валюта строки.

**Исход по разбору — B:** обе суммы законны; нужна ось amount-basis, не всегдашнее
умножение. C3 (document vs register) курсом не объясняется (разрыв
register−doc_raw **293 719**) — отдельная развилка, в этот проект не входит.

---

## 1. Данные

### 1.1. Где живут курсы на okna (только из замера)

| Сущность | Поля из замера | Роль |
|---|---|---|
| `InformationRegister_КурсыВалют` | `Period`, ссылка на валюту, число курса (и кратность, если есть в prop) | курс на дату |
| `Catalog_Валюты` | `Ref_Key`, `Code`, `Description` (платформенные) | словарь валют для карты / подписей агента §7 |
| `Constant_ВалютаБухгалтерскогоУчета` | значение → Ref валюты | якорь accounting-ветки |
| факты документов (напр. `Document_РеализацияТМЦ`) | `Валюта_Key`, `Курс`, сумма (`Всего` / measure из `$metadata`), дата документа | зерно счёта; `Курс` на шапке — замерённый prop |

Имена таблиц/полей выше — **только** из замера C1 / инвентаря / витрины.
Выдуманных колонок нет; пробелы — §1.5.

### 1.2. Как размечается «документ» vs «учёт»

- **Валюта учёта** — Ref из константы БУ (`search_meta.accounting_currency_constant`).
- **Валюта документа** — currency-ref prop факта (имя prop — из карты
  `currency_amount_map`, не литерал `Валюта_Key` в ask-коде).
- **Курс для пересчёта** — join регистра курсов на **дату документа** и валюту
  строки (один SQL, §1.3). Prop `Курс` на шапке — контрольный источник замера;
  при расхождении с регистром статус ячейки обязан быть виден (риск 3).

Рабочий класс FX: валюта факта ≠ якорю **или** курс ≠ 1. Множество — в
`search_meta` / данных выборки, не `frozenset` в Python.

### 1.3. Один SQL: обе ветки (join шапок с курсом на дату)

Счёт — внутри SereneDB (п. 20 TARGET). Эскиз приёмки: имена `:src` / колонок —
из `currency_amount_map` + `currency_rate_registers` после шага корпуса;
ниже — имена замера okna только как иллюстрация приёмки, не хардкод будущего кода.

```sql
-- Эскиз: один запрос, без Python-цикла.
-- :acct_key — Ref валюты учёта из search_meta.
-- :rate_reg / :rate_period / :rate_curr / :rate_val — из карты курса.
-- Зерно = шапка (DISTINCT ON), иначе плоская витрина раздует Σ (п. 13).
WITH hdr AS (
  SELECT DISTINCT ON (d.ref_key)
    d.ref_key,
    d.doc_date,
    d.curr_key,
    try_cast(d.amount AS DOUBLE) AS amount
  FROM /* :src */ d
  WHERE /* posted / not deleted / match+preds окна — как fork_scan */
  ORDER BY d.ref_key
),
rated AS (
  SELECT
    h.ref_key,
    h.curr_key,
    h.amount,
    (
      SELECT try_cast(r.rate_val AS DOUBLE)
      FROM /* :rate_reg */ r
      WHERE r.rate_curr = h.curr_key
        AND r.rate_period <= h.doc_date
      ORDER BY r.rate_period DESC
      LIMIT 1
    ) AS rate_on_date
  FROM hdr h
)
SELECT
  round(sum(amount), 2) AS doc_amount,
  round(sum(
    CASE
      WHEN curr_key = :acct_key
        OR rate_on_date IS NULL
        OR rate_on_date = 1
      THEN amount
      ELSE amount * rate_on_date
    END
  ), 2) AS accounting_amount,
  count(*) AS n_headers,
  count(*) FILTER (
    WHERE curr_key IS DISTINCT FROM :acct_key
      AND rate_on_date IS NOT NULL
      AND rate_on_date <> 1
  ) AS n_fx
FROM rated;
```

Синтаксис subquery / `DISTINCT ON` / aggregates — штатный SereneDB (при кодировании:
`serenedb-docs` → строка `Доки:` в коммите). Кратность курса, если в регистре есть
отдельный numeric prop — множитель в том же CASE из карты; иначе белое пятно §1.5.

### 1.4. Точка вставки в корпус (как calendar / balance_registers)

Образец — `corpus_build.sql` блок `balance_registers` (~стр. 90–101) и
«1-кватер. ОСЬ ДАТ ГРАФИКА» (~167+): отбор из `tmp3_ent` / `tmp3_prop` по
**структуре** `$metadata`, запись в `search_meta`; пустая карта = ось честно
выключена.

| Ключ `search_meta` | Содержимое | Как находят EntitySet |
|---|---|---|
| `currency_catalogs` | csv справочников валют | catalog: Code+Description; на него ссылаются currency-props фактов |
| `currency_rate_registers` | csv регистров курсов | informationregister: Period + currency Guid*_Key + numeric rate |
| `accounting_currency_constant` | имя константы / value Ref | constant → ref в currency catalog |
| `currency_amount_map` | src, curr_col, amount_col, date_col, grain, опц. rate_col | document/register с currency ref + numeric amount |
| опц. `currency_working_keys` | Ref валют, встречающихся в фактах | join витрины после сборки; пусто → ось выключена |

Сейчас `search_meta` currency_* на okna = **0** (замер §7.2) — до шага 1 корпус
ось не открывает.

Приёмка корпуса: `accounting_currency_constant` непуст; `currency_amount_map` ≥ 1;
SQL §1.3 на полном срезе реализации даёт `n_fx = 40` и
`doc_amount ≠ accounting_amount` (ожидание Δ порядка **375 437**).

### 1.5. Белые пятна (честно: в замере / corpus_build нет)

| Вопрос | Статус |
|---|---|
| Точные имена prop регистра курсов (`Курс` / `Кратность` / имя currency-key) на живой окне join | в замере есть сущность и роль Period+курс; **имена колонок регистра для join не зафиксированы отдельным SELECT** — снять на шаге 1 корпуса из `tmp3_prop` / `duckdb_columns` |
| Как сопоставить «человек сказал евро» с Ref валюты без списка слов | словарь / wiki-alias / `search_fork_label` по **данным** `Catalog_Валюты` (Code/Description); холодный старт без словаря = always-on по разному счёту + C |
| Зерно header vs line для всех 36 EntitySet | замер зерна — на реализации; универсальное правило `grain` пишется картой из `$metadata`, не проверено на каждом из 36 |
| Курсы ЦБ vs банковские EUR в `Catalog_Валюты` (6 строк: MDL/USD/EUR + банковские) | какая строка «евро» для вопроса — **не решено замером**; развилка внутри каталога = данные + словарь §7, не хардкод |
| `currency_*` уже в `corpus_build.sql` | **нет** (только calendar / balance) — блок ещё писать |
| Связь C1 с ответом регистра (сейчас лидер продаж — register) | ось amount-basis внутри document; канон register vs document — C3 / sales_canon, не этот проект |

---

## 2. Детектор

### 2.1. Нужда в оси

Ось нужна, когда одновременно:

1. в `search_meta` непусты `accounting_currency_constant` + `currency_amount_map`
   (+ регистр курсов для join); иначе ось не открыта — честно по данным;
2. выбранный источник факта есть в карте;
3. в отобранных строках есть FX (`curr ≠ acct` или `rate_on_date ≠ 1`)
   **или** словарь/ticket назвал валютную ось / валюту из каталога.

Режим как у calendar / W: **always-on при карте** — два amount-reading:
`doc_amount` и `accounting_amount`. Совпали → A; разошлись → B/C.

Узнать, что «сумма в MDL, а спросили в EUR»: не списком слов, а
(а) валюта фактов из карты/строк, (б) якорь учёта из meta, (в) hit словаря
phrase→currency Ref / `currency_basis` из данных каталога. Нет hit и нет FX →
ось молчит. Hit «евро» при фактах только в учёте без конвертации в EUR-число —
не подменять молча: либо ветка с подписью и курсом на дату (§3.2), либо C/clarify.

### 2.2. Где в пайплайне

Рядом с W / calendar, не отдельный конвейер:

```
parse_intent
  → apply_period_leader / period_readings
  → calendar_axis_readings          # уже в дереве, свой флаг
  → [NEW] currency_axis_readings(intent, match, search_meta)
        # 0..2 amount-basis: doc_amount | accounting_amount
  → fork_scan / fork_scan_readings
  → fork_classes* / resolve_fork_outcome
  → fork_outcome_a | fork_outcome_b | fork_outcome_c
  → ask_journal (ticket_variant только при нажатии; ask_choice_memory)
```

Отпечаток — координата amount-basis в `fork_key_of` / measure-fp (иначе B
сольёт ветки). Не ломать window_fp / day-basis.

### 2.3. Без списка слов / Ref_Key в Python

Триггеры «в евро», «в леях», «в валюте учёта» — **не** литералы ask-кода.

1. Словарь в данных (`search_fork_label` / wiki-alias / meta): phrase →
   `currency_basis=doc|accounting` или Ref валюты из каталога.
2. Форма данных: ось раскрыта при разных числах; лексика только сдвигает
   лидера (§2.4).

Запрещено: ISO-коды, «MDL»/«EUR», списки Ref_Key, промт «всегда спрашивай валюту».

### 2.4. Лидер amount-basis

| Условие | Лидер | Люк |
|---|---|---|
| ось не названа | **status quo** = `doc_amount` (сумма поля **без** умножения на курс — то, что путь ответа делает сегодня; на okna почти всегда MDL с курсом 1) | `accounting_amount` |
| словарь / ticket → учёт | `accounting_amount` | `doc_amount` |
| словарь / ticket → документ | `doc_amount` | `accounting_amount` |

Молчание человека ≠ выбор (§2 контракта). Sticky только через `decision_id` /
память нажатия люка. Смена лидера по умолчанию на accounting сдвинула бы ровно
40 FX-шапок — без слова владельца не делать (прежние ответы не едут).

---

## 3. Развилка

### 3.1. Класс

**Сумма в валюте документа vs сумма в валюте учёта** (amount-basis × то же
E×M×W). Тот же класс механики, что MTD vs месяц / calendar vs working (§7bis):
лидер + люк, нажатие в память.

### 3.2. Пары «число + подпись» (B / C)

Подписи — из словаря §7 (`search_fork_label`), не из имён таблиц. Примеры
смысла для агента (не литералы кода):

| Ветка | Подпись-кандидат |
|---|---|
| `doc_amount` | «в валюте документа» |
| `accounting_amount` | «в валюте учёта» / «по курсу на дату документа» |

Для вопроса с явной валютой из каталога агент §7 может дать подпись вида
«в евро по курсу на дату…» — текст из данных/агента, не из env. Нет подписей →
исход **C**: число лидера + константа «есть другое прочтение», `options` пуст,
ветки не называть. Имена метаданных человеку не показывать.

### 3.3. Память — только нажатие

`ask_journal` / `ask_choice_memory` / ticket W-трека:

- пишется **только** факт нажатия (`ticket_used` / `ticket_variant`);
- молчание не обновляет память;
- без trusted click `ticket_variant` пуст.

### 3.4. Исход A

Атом совпал на обеих ветках (курс 1 / нет FX / нет курса → ветки равны) → **A**,
люк не открываем.

Разные числа + подписи → **B**. Разные без подписей → **C**.

---

## 4. Ответ лидера

1. Победитель шага 4 — `fork_leader_class(picked_src, classes)`.  
2. Среди окон — `mtd`/`wtd` (`prefer_window_leader`).  
3. Среди day-basis — правило календарной оси.  
4. Среди amount-basis — §2.4 (`doc_amount` = status quo).

Не делать отдельную лестницу валют; не подменять `fork_leader_class`; не звать
`arbitrate` при `ASK_FORK_OUTCOMES=1`.

Флаг: **`ASK_CURRENCY_AXIS`**, умолчание **`0`**. Бой не включать до решения
владельца; проба на стейджинге.

Ответ: пара лидера; при B — люк с подписанной второй веткой; при C — число
лидера + «есть другое прочтение». Смешение валют в одном atom без подписи —
не собирать (п. 13).

---

## 5. Тесты

### 5.1. Оффлайн-замки

Модуль `test_currency_axis` (на шаге внедрения; до создания в дереве нет) —
без LLM, без сети, мок `psql` / фикстуры `search_meta`.

| Замок | Что фиксирует |
|---|---|
| флаг `ASK_CURRENCY_AXIS` умолч. `0` | код за env, бой не включён |
| флаг off → `currency_axis_readings` пуст / no-op | **бит-в-бит** прежнее поведение W/calendar |
| флаг on + пустая карта meta → ось не открыта | нет карты = нет ветки |
| курс 1 / нет FX → числа равны → outcome ∈ {A, unique} | люк не открыт |
| числа разные + подписи → B, `atoms[0]` = лидер status quo (`doc_amount`) | §2.4 / §2 |
| числа разные без подписей → C, options пуст | §2 / §7 |
| `ticket_variant` только при trusted click | молчание ≠ выбор |
| нет ISO/«MDL»/«EUR»/списков Ref_Key в diff ask | снайпер / grep замка |

Соседние: `test_calendar_axis`, `test_fork_outcomes`, `test_fork_window_readings`
— не ломать; currency = расширение readings.

### 5.2. Наборы (GOLD_SETS — замки не подгоняются)

По [`docs/GOLD_SETS.md`](../docs/GOLD_SETS.md):

- **правки / регрессия оси** — отдельный `ab-currency-axis-okna.tsv` +
  `AB_CURRENCY_AXIS` (как `ab-calendar-axis-okna.tsv`), умолч. off; в
  `ab-gold-okna.tsv` / probe / приёмку **не** смешивать;
- **приёмка** (`ACCEPTANCE_UT`, `ACCEPTANCE_OKNA_LIVE`, ambiguous) — эталоны
  не подгонять под ось; провал → чинят код или заводят вопрос в **рабочий**
  набор оси;
- эталон чисел — `truth()` живым SQL §1.3 при прогоне, не выдуманные цифры в tsv.

Кандидаты вопросов (рабочий набор оси):

1. «Сумма реализации за период» (ось не названа; FX в окне → лидер doc, люк acct).
2. «Продажи в валюте учёта…» / «в валюте документа…».
3. Окно только курс=1 → A.
4. Окно с 40 FX-шапками августа → B или C.
5. «Сколько продали в евро…» — не MDL-число без unit (п. 10/13).
6. Follow-up: B → нажатие → ticket сдвигает лидера; повтор без ticket не sticky.

---

## 6. Порядок внедрения

### Шаг 1 — `corpus_build.sql` (+ при нужде `corpus_init.sql`)

- Блок `search_meta` §1.4 структурным отбором (как 1-кватер календаря /
  `balance_registers`). Новый загрузчик / Python-обход — запрещены.
- **Приёмка:** на okna ключи currency_* непусты; SQL §1.3 → `n_fx > 0` и
  `doc_amount ≠ accounting_amount` (порядок Δ **375 437** на полном срезе).

### Шаг 2 — ask-код за `ASK_CURRENCY_AXIS` (умолч. 0)

- Чтение meta как `balance_registers()` / calendar; readings рядом с
  period/calendar; исходы через `resolve_fork_outcome` / `fork_outcome_*`;
  лидер §2.4; пересчёт — SQL §1.3 в базе.
- Бой `:8091` не включать; проба `:8092`.
- **Приёмка:** флаг 0 — поведение = до правки (md5 / base1 / okna AB);
  флаг 1 — FX-окно даёт B или C, окно без FX — A; `ticket_variant` пуст без клика;
  «в евро» не отдаёт чужую валюту молча.

**[исполнено 28.08]** зона `ubuntu/serenedb/ask/z04b_currency_axis.py`, интеграция
W/fork/outcomes, оффлайн `test_currency_axis.py` **18/0**, соседние fork/calendar
**зелёные** при флаге 0. Стейджинг `:8092` — см. замер в `REGRESSION_BASE1.md`.
Детектор FX: `currency_fx_probe` — один SQL §1.3 (`query_table` + join регистра
курсов на дату, `DISTINCT ON` при `grain=header`). Подписи веток:
`search_fork_label` по id `doc_amount` / `accounting_amount`. Δ эталон **375 437,03**
на полном срезе (40 FX-шапок августа 2026).

### Шаг 3 — оффлайн-замки + словарь подписей + рабочий AB-набор

- `test_currency_axis` (≥ кейсов §5.1, все green).
- Очередь класса → агент §7 пишет подписи веток.
- `ab-currency-axis-okna.tsv` + `AB_CURRENCY_AXIS` (GOLD_SETS: полка «правки»).
- **Приёмка:** замки offline; проба 0err на наборе §5.2; выкат на бой —
  решение владельца.

---

## Риски (три главных)

1. **Плоская витрина шапка+строки** — суммирование повторённого `Всего` без
   `grain=header` / `DISTINCT ON` раздувает ветки (п. 13); замок на fixture с
   двумя строками одного Ref обязателен на шаге 3.
2. **Смешение размерностей в `doc_amount`** — несколько валют документа в одном
   окне: «сумма в валюте документа» складывает несоизмеримое; без подписи B/C
   ответ не собирать, иначе люк хуже молчания.
3. **Курс на документе vs регистр на дату** — расхождение даст третью ветку или
   тихий сдвиг; правило проекта: join регистра на дату (§1.3); prop шапки —
   контроль замера; расхождение видно в статусе ячейки, не глотается.
