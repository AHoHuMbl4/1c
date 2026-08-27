# К4-3: ось уточнения, отказ склада, имена метаданных

**Дата:** 2026-08-27  
**Источник замера:** [`ACCEPTANCE_AMBIGUOUS.md`](ACCEPTANCE_AMBIGUOUS.md) §8 (okna, коммит
`96b51ab`, **5/18**).  
**Контракт:** [`TARGET.md`](../TARGET.md) п. 12 (догадка — ошибка), п. 21 (отказ при
данных — дефект; уточнение словами человека).  
**Код не менялся** (`serene_ask.py` у оркестратора). Здесь — разбор + проект патчей.

Классы этой задачи (5 из 13 провалов §8.4):

| Класс | Шт. | № |
|---|---:|---|
| Уточнение не по той оси | 3 | 3, 7, 16 |
| Отказ вместо уточнения склада | 1 | 11 |
| Имена метаданных на первом экране | 1 | 10 |

---

## 1. Пять случаев из отчёта

| № | Вопрос | Ответ бота (kind / суть) | Что было неоднозначно на самом деле | Каким должен был быть ответ |
|---:|---|---|---|---|
| **3** | Сколько закупили весной? | `clarify`: варианты **итого / НДС** | «весна» **без года** (в корпусе okna несколько лет) | `clarify`: «за какую весну / какой год?» |
| **7** | Сколько мы закупили товаров? | `clarify`: варианты **итого / НДС** | мера не задана: **деньги или количество** | `clarify`: «в рублях или в штуках?» (игла ACCEPTANCE) |
| **16** | Как у нас дела? | `clarify`: валюта дебет/кредит / «189043» | тема вопроса не названа (продажи? остатки? …) | `clarify`: «о чём спросить: продажи, остатки…?» |
| **11** | Сколько осталось на складе? | `no_data` (отказ) | склад не назван; в `catalog_местахранения` **3** склада | `clarify`: «на каком складе?» |
| **10** | Сколько товара на складе? | `clarify`: список источников с `accumulationregister_…` | тот же класс «какой склад»; плюс утечка служебных имён | `clarify` словами человека про склад; без `document_` / `catalog_` / `accumulationregister_` / «регистр…» как имени таблицы на 1-м экране (п. 12 TARGET: служебные имена человеку не показываются) |

Верные 5 из прогона (§8.3): №4, 5, 9, 13, 15 — к этим трём классам не относятся
(честный `no_data` / предметное уточнение / ответ при наличии данных 2022).

---

## 2. Как выбирается ось уточнения

### 2.1. Ответ кодом: **фиксированный порядок пайплайна**, не «мера неоднозначности»

Ось не ранжируется по тому, насколько сильно она меняет число. Срабатывает **первая**
ветка early-return, до которой дошёл `answer` / обёртка `answer_checked`.

Порядок (упрощённо):

1. **`serene_enough.verdict_before`** — до поиска, только если нет ни `kind`, ни `terms`
   ([`serene_enough.py:174–198`](../ubuntu/serenedb/serene_enough.py); вызов
   [`serene_ask.py:15514–15518`](../ubuntu/serenedb/serene_ask.py)). Слоты: subject
   (+ period спутником). №3/7/16 сюда **не** попадают: у них есть род/тема в разборе.
2. **Уточнение сущности** (несколько `src`) — `mk_opts` / fork, раньше выбора меры.
3. **Уточнение величины** — как только есть `measure_alts` и нет выбранной меры
   ([`:14266–14308`](../ubuntu/serenedb/serene_ask.py)): перечень **имён полей** nums
   (через `measure_captions`), не классов «деньги/штуки».
4. **Уточнение оси GROUP BY** — `grain_dec.clarify == "axis"` после
   `serene_axis.decide_grain` ([`:14380+`](../ubuntu/serenedb/serene_ask.py),
   [`serene_axis.py:85–144`](../ubuntu/serenedb/serene_axis.py)).
5. **`serene_enough.verdict_after`** — **после** уже готового `answer`/`figures`
   ([`:15520–15540`](../ubuntu/serenedb/serene_ask.py)): subject (+ period). На путях
   `clarify`/`no_data` **не вызывается**.

Классификатор уже собранных options — тоже фиксированный, не по силе неоднозначности:

```7026:7035:ubuntu/serenedb/serene_ask.py
def ambiguity_of_options(opts):
    """Предмет clarify: сущность / величина / ось."""
    opts = [o for o in (opts or []) if isinstance(o, dict)]
    if not opts:
        return "entity"
    if any("measure" in o for o in opts):
        return "measure"
    if all("found" not in o for o in opts) and any(o.get("distinct_by") for o in opts):
        return "axis"
    return "entity"
```

Период как **самостоятельная** конкурирующая ось на пути «уже есть kind, период
assumed» **не** стоит в очереди: assumed пишется в `diag` / применяется фильтром
([`:12094–12097`](../ubuntu/serenedb/serene_ask.py)), а не превращается в `clarify`
раньше measure-alts. Отсюда №3: вместо «какой год?» — «итого или НДС?».

Набор alts для №7 порождает `unresolved_quantity` / `measure_ambiguous` по **всем**
живым полям с разными итогами ([`:8040–8060`](../ubuntu/serenedb/serene_ask.py),
[`:8195–8211`](../ubuntu/serenedb/serene_ask.py)) — без свёртки в money|qty:

```8040:8060:ubuntu/serenedb/serene_ask.py
def unresolved_quantity(measure, alts, want, compute, names, totals_by=None):
    ...
    if measure_ambiguous(names, totals_by or {}):
        return None, names
    return names[0], []
```

Итог: ось = **порядок веток кода**, не арбитраж «какая неоднозначность важнее».

### 2.2. Почему №3 / №7 / №16 попали не туда

| № | Что сработало первым | Почему не та ось |
|---|---|---|
| 3 | measure-clarify (итого/НДС) | год «весны» assumed/потерян; period-clarify в этой точке нет |
| 7 | тот же measure-clarify по полям | нет оси «класс меры» money\|qty; поля nums конкурируют раньше |
| 16 | entity/measure-clarify по валютным кандидатам | `verdict_before` молчит (есть kind/шум); тема «дела» не становится слотом subject до ответа |

---

## 3. Отказ вместо уточнения склада (№11)

### 3.1. Ветка отказа

Глобальный early-return **до** складского контура:

```12278:12282:ubuntu/serenedb/serene_ask.py
    if not by and not extra:
        by = tables_of("", preds)
    if not by and not extra:
        return {"partial": cut or None, "kind": "no_data", "text": NO_DATA_TEXT or refuse_text(question), "sources": [],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
```

Обработка остатков (`question_asks_stock_balance` → filter / `balance_bridge_clarify`)
начинается только **ниже**, с [`:12316`](../ubuntu/serenedb/serene_ask.py).

Для «Сколько осталось на складе?»:

- маркер остатка срабатывает (`_STOCK_MARKERS`: «остат», «на складе») —
  [`:6063–6068`](../ubuntu/serenedb/serene_ask.py);
- именованного товара нет → `stock_asks_named_product` = false
  (см. замок `test_stock_balance_path.py`);
- буквальный/смысловой/alias-отбор часто **пуст** (род «остаток» плохо бьёт в имена
  регистров) → `by` и `extra` пусты → **`no_data` на `:12281`**;
- до `balance_bridge_clarify` (`:6210`) и до любого «какой склад?» код **не доходит**.

Дополнительно: даже достигнутый `balance_bridge_clarify` спрашивает **источник
остатков**, а не член оси склада (Vitrina / Bubuieci / Depozit). Пути «перечислить
значения `МестоХранения` / `catalog_местахранения`» в `serene_ask.py` **нет**
(поиск по коду: нет ветки clarify по складам-значениям).

### 3.2. Почему уточнение не дошло

| Барьер | Эффект |
|---|---|
| `no_data` при пустом `by`/`extra` **перед** stock-path | складской clarify недостижим |
| Нет оси «склад-значение» | даже bridge ≠ «на каком складе?» |
| `verdict_after` только на answer/figures | после no_data слот «склад» не появится |

---

## 4. Имена метаданных на первом экране (№10)

### 4.1. Путь утечки

Живой исход №10 — `kind=clarify` со списком источников, в тексте/options видны
`accumulationregister_…`. Это ветка **`balance_bridge_clarify`**
([`:6210–6243`](../ubuntu/serenedb/serene_ask.py)): мост не нашёл баланс-кандидат в
отборе → clarify по `capable`.

Самое дешёвое место, где служебное имя **не** подменяется человеческим — fallback на
`src_table`:

```6217:6226:ubuntu/serenedb/serene_ask.py
    lab_by = {}
    missing = [s for s in srcs if s not in labels]
    if missing:
        for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(s) for s in missing))):
            if r and r[0]:
                lab_by[r[0]] = r[1] or r[0]
    lab_by.update(labels)
    opts = [{"src": s, "label": lab_by.get(s, s), "hint": "",
             "distinct_by": "", "found": 0} for s in srcs]
```

Дальше тот же fallback в общем различителе подписей:

```11147:11164:ubuntu/serenedb/serene_ask.py
def disambiguate_labels(pairs, ambiguous=None):
    ...
    for src, lab in pairs:
        many = len(seen.get(norm(lab), [])) > 1 or norm(lab) in ambiguous
        out[src] = label_with_kind(src, lab) if many else ((lab or "").strip() or src)
```

и в `label_with_kind` ([`:11115`](../ubuntu/serenedb/serene_ask.py)):
`lab = (label or "").strip() or str(src_table)`.

Контраст: `_table_label` ([`:9408–9419`](../ubuntu/serenedb/serene_ask.py)) **намеренно**
не подставляет `src` при пустой метке — «Пусто — не подставлять src». Bridge и
`disambiguate_labels` это правило **нарушают**.

Цепочка на экран: `opts[].label` → `clarify_say` / `format_clarify_options`
([`:10546–10579`](../ubuntu/serenedb/serene_ask.py)) → текст первого экрана. Поле `src`
в options остаётся внутренним; утечка — когда **label** = OData-имя.

Дешевле всего чинить: **один** запрет fallback `→ src` в `disambiguate_labels` + в
`balance_bridge_clarify` (и тот же шаблон `r[1] or r[0]` / `lab_by.get(s, s)` в
`mk_opts` на входе в disambiguate). Подстановка: `label_with_kind(src, split_ident(
хвост после первого `_`))` или пропуск варианта без человеческой метки — но не сырой
`src_table`.

---

## 5. Проект патча (без правки в этом коммите)

### 5.1. Ось уточнения (№3, №7, №16)

| Что | Где | Суть |
|---|---|---|
| Период assumed при неоднозначном годе/квартале/сезоне | до measure-alts в `answer`, рядом с `разбор.assumed` / `apply_period_leader` | если period assumed **и** в данных >1 года (или форма season/quarter без года) → `clarify` period **раньше** `measure_alts` |
| Класс меры money\|qty | `unresolved_quantity` / ветка `:14266` | при want=sum и отсутствии слова меры: сначала два класса (деньги/количество) по роли полей (`sales_money_measure` / `sales_qty_measure` уже есть), **не** полный список nums; полный список — только внутри выбранного класса |
| Тема «дела» / пустой смысл | `verdict_before` или ранний слот subject | расширить cheap-half: want=sum/count при kind, который не сводится к одному роду записей → subject-clarify словами человека (без имён таблиц) |

**Почему не ломает верные 5:**

- №4/5 — `no_data` по отсутствию контрагента **до** measure/period-clarify; порядок
  «нет значения → отказ» не трогаем.
- №9 — уже subject-clarify («о каких записях…»); ранний subject совместим.
- №13 — нет номенклатуры → `no_data`; period/measure-ось не включается.
- №15 — период **назван** (2022) → period-clarify по assumed не сработает;
  `period_given` уже отличает assumed от явного.

### 5.2. Склад: отказ → уточнение (№11)

| Что | Где | Суть |
|---|---|---|
| Не резать stock-вопросы глобальным no_data | **перед** `:12281`: если `question_asks_stock_balance` и не named-absent | не return no_data; уйти в stock-path / warehouse-clarify |
| Уточнение склада-значения | новый helper рядом с `balance_bridge_clarify` | при >1 значении оси склада (из refs_map / `catalog_местахранения`) → options с **человеческими** именами складов; 1 склад — отвечать без уточнения; 0 — тогда bridge или no_data |
| Named без balance | оставить `stock_balance_named_no_data` | не смешивать с unnamed «на складе» |

**Почему не ломает верные 5:** они не stock-balance; early stock-bypass не задевает
контрагентов/велосипеды/2022.

### 5.3. Имена метаданных (№10) — самое дешёвое

| Что | Где | Суть |
|---|---|---|
| Запрет fallback на `src` | `disambiguate_labels` `:11163`, `label_with_kind` `:11115`, `balance_bridge_clarify` `:6223–6225` | пустая/служебная метка → `split_ident` + `kind_word` **без** OData-префикса в строке; либо отбросить option |
| Санитар первого экрана | `clarify_say` / `format_clarify_options` (fail-closed) | если в `label`/`hint`/`text` есть запрещённый префикс — не отдавать как есть (замок ниже) |
| Не путать с `kind_word` | `(документ)` / `(справочник)` как различитель одноимённых — **оставить** | запрет именно на `accumulationregister_foo`, не на слово «документ» в скобках у человеческой метки (уже в `test_focus_loop`) |

**Почему не ломает верные 5:** они не entity-clarify с пустыми label; уникальные
человеческие метки (`disambiguate` без many) не меняются, если label уже из
`search_tables`.

---

## 6. Проект замка

Стиль: `ubuntu/serenedb/test_*.py` (оффлайн, без сети/БД где возможно).

### 6.1. Обязательный: имена на первом экране

Новый оффлайн-замок в стиле уже существующего
[`test_stock_balance_path.py`](../ubuntu/serenedb/test_stock_balance_path.py)
(заводить **вместе с патчем** §5.3, не раньше — в этом коммите файла нет).

Запрещённые подстроки в `text` + `options[].label` + `options[].hint` при
`kind=clarify` (первый экран):

```
document_
catalog_
documentjournal_
accumulationregister_
informationregister_
accountingregister_
calculationregister_
chartofaccounts_
businessprocess_
exchangeplan_
```

плюс целый токен, равный `src_table` вида `тип_хвост`.

Кейсы:

1. `balance_bridge_clarify` с mock `psql`, где `label` пуст / NULL → ни один option.label
   не содержит префиксов выше; `src` внутри dict **может** остаться (внутреннее).
2. `disambiguate_labels([("accumulationregister_x", "")])` → подпись без
   `accumulationregister_`.
3. `mk_opts` с `lab_by={src: src}` → после disambiguate наружу не уходит сырой src.
4. Регрессия `test_focus_loop`: «Отгрузка Пробная (документ)» — **допустима**
   (человеческая метка + вид); замок не запрещает `(документ)` без OData-префикса.

### 6.2. Ось (рекомендуемый)

Отдельный оффлайн-замок (имя на усмотрение патча §5.1; файла в дереве пока нет):

- assumed season/year + несколько money-полей → функция-решатель (после выноса)
  выбирает `period`, не `measure`;
- want=sum без меры + есть qty и money → класс money\|qty, не `["Всего","НДС",…]`;
- явный период 2022 + money fields → **не** period-clarify (защита №15).

### 6.3. Склад (рекомендуемый)

Дописать существующий
[`test_stock_balance_path.py`](../ubuntu/serenedb/test_stock_balance_path.py):

- при `question_asks_stock_balance` и пустых by/extra **не** считать финальным
  исходом глобальный no_data-хелпер (после появления early-bypass);
- warehouse-clarify: 3 склада → 3 options с человеческими именами; 1 склад → нет clarify.

---

## 7. Связь с приёмкой

Повторный прогон после патчей: те же 18 вопросов okna
([`ACCEPTANCE_AMBIGUOUS.md`](ACCEPTANCE_AMBIGUOUS.md) §8). Критерий сдвига по классам
К4-3: №3/7/16 — игла оси; №11 — `clarify` склада, не `no_data`; №10 — clarify без
OData-префиксов (и желательно ось склада, не список регистров). Верные 5 не должны
уйти в FAIL.
