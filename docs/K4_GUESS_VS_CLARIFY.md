# K4-1. Догадка вместо уточнения (прогон Э3 okna 27.08)

Источник замера: [`ACCEPTANCE_AMBIGUOUS.md`](ACCEPTANCE_AMBIGUOUS.md) §8
(коммит отчёта `96b51ab`). Итог **5/18**; класс «догадка вместо уточнения» —
**4** случая (№1, 2, 8, 12).

Контракт: [`TARGET.md`](../TARGET.md) п. **12** (догадка — ошибка) и п. **21**
(ответ → уточняющий вопрос → отказ). Уточнение — словами человека; имена
метаданных на первый экран не выходят.

🔴 `ubuntu/serenedb/serene_ask.py` в этом шаге **не правится** (файл у
оркестратора). Здесь — разбор, место решения, проект патча и замок.
Номера строк — снимок **15931** строк на 27.08; якоря — имена функций.

---

## 1. Четыре случая

| № | Вопрос | Что ответил бот | Почему догадка | Неснятое допущение |
|---:|---|---|---|---|
| 1 | Сколько мы продали за год? | `kind=answer`, сумма за окно **assumed** 2025-08-27…2026-08-27 | В вопросе нет года; в корпусе okna **5** лет (2022…2026). Код выбрал скользящий «год от сегодня» и отдал число | Какой год / какое из прочтений «за год» |
| 2 | Какая выручка за квартал? | `kind=answer`, сумма с 2026-07-01… | Квартал не назван (ни год, ни «этот/прошлый»); молча взят один квартальный срез | Какой квартал (и год) |
| 8 | Топ-5 товаров по продажам | `kind=answer`, топ по «Всего» (деньги) | Мера не названа; равноправны деньги и количество. Э3 ждёт `clarify` («по деньгам или по количеству?») | Ось меры топа |
| 12 | Сколько лежит на всех складах вместе? | `kind=figures` по реализации (count), текст «невозможно» | Товар не назван; «всех складах» снимает только ось склада. Нужен clarify «какой товар», не figures | Предмет остатка (номенклатура) |

Верные 5 из того же прогона (их нельзя сломать патчем):

| № | kind | Почему верно |
|---:|---|---|
| 4 | `no_data` | контрагента «Алмаз» на okna нет |
| 5 | `no_data` | «Сатурн» нет |
| 9 | `clarify` | предмет не назван — уточнил |
| 13 | `no_data` | велосипедов в номенклатуре нет |
| 15 | `answer` | **2022** назван в вопросе — период не assumed; данные есть |

---

## 2. Где в коде принимается решение

Общий дефект: шаг 1 **умеет пометить** догадку (`parse.assumed`), но ответный
путь **молча применяет** её и отдаёт `answer`/`figures`. Пометка уходит в
`diag.intent_assumed`, человеку как уточнение не показывается.

### 2.1. №1 и №2 — assumed-период → ответ

| Что | Где |
|---|---|
| Разметка догадки | `_normalize_intent` — блок «УСЛОВИЕ, КОТОРОГО В ВОПРОСЕ НЕ БЫЛО» (~1213–1225): границы периода, чьи YYYY нет среди цифр вопроса → `parse.assumed = ["period.from", …]` |
| Датчик «система догадалась» | `serene_enough.period_assumed` / `period_given` (`serene_enough.py` ~147–171) |
| Канон-форма «год от today» | `period_is_canon_guess` (~11898–11922): to≈today и длина 364…367 (или Jan1…to того же года) |
| Молчаливый выбор окна | `apply_period_leader` (~1773–1809) + `prefer_window_leader` (~1709–1725): лидер пишется в `intent["period"]`, человек не спрашивается |
| Догадка только в diag | `answer` (~12091–12097): при `разбор.assumed` пишется `diag.intent_assumed`, фильтр **остаётся** |
| Документ закрепляет дефект | `HOW_IT_WORKS.md`: «period, выведенный… применяется, но помечается допущением» — против п. 12 |

Комментарий в коде (~1214–1219) уже знает правильный исход: приёмка ждёт
уточнения («за год» = календарный год / 12 месяцев / любой из лет корпуса).
Механизма clarify на этом признаке **нет**.

`period_assumed` сейчас используется в основном для `drop_assumed` при
пустой выборке (`empty_after_period_action` ~11303–11318) — «не отказать»,
но не «уточнить вместо числа».

### 2.2. №8 — мера топа → деньги

| Что | Где |
|---|---|
| Единая точка меры rank×sales | `sales_rank_resolve_measure` (~5676–5722) |
| Канон qty/money | `sales_rank_canon_measure` (~5725–5756): без названной меры на товарной оси → qty; иначе часто `None` |
| Молчаливый money-fallback | тот же `sales_rank_resolve_measure`: при `not sm and not product_axis` → `sales_money_measure` / `how="sales_rank_money"` (~5705–5721) |
| Call-site | `answer` (~14154–14184): при `_rank_sales` результат канона ставится в `measure`, `measure_alts=[]` — ветка `measure_ambiguous` (~14266–14308) **не** открывается из‑за `sales_measure_canon` / `_rank_sales` |
| `role_ask` уже есть | `measure_choice` → `how=="ask"` → `sales_rank_canon_measure` возвращает `(None, "role_ask")`; call-site обнуляет `_sm` (~14171–14172), но **сам** clarify не строит, если дальше снова выбирают другую меру |

Живой ответ «топ по Всего»: сработал money-fallback (товарная ось /
`ASK_SALES_RANK_CANON` не удержали qty, либо qty не спросили по контракту Э3).
По п. 12 равноправные деньги/количество без слова в вопросе — **уточнение**,
не тихий выбор (ни money, ни qty).

⚠️ Натяжение с `test_sales_rank_canon.py` (топ-N товара → Количество): тот
замок фиксирует **другую** догадку как эталон gold. После K4-1 gold-строки
без названной меры должны либо ждать `clarify`, либо явно звать меру в
вопросе/билете. Верные 5 из Э3 этот конфликт не затрагивают.

### 2.3. №12 — остатки без товара → figures по продажам

| Что | Где |
|---|---|
| Триггер остатков | `question_asks_stock_balance` (~6063–6068) по `_STOCK_MARKERS` (~6002–6005) |
| Именованный товар | `stock_asks_named_product` (~6121–6146) |
| Путь без имени | `answer` (~12316–12341): без named — filter balance / `balance_bridge_clarify` (список **источников**, часто с именами регистров — отдельный дефект №10) |

Фраза «Сколько лежит на всех складах вместе?» **не** содержит маркеров
`остат` / `на складе` (есть «лежит», «складах» — другой падеж). Триггер
остатков молчит → вопрос уходит в обычный отбор → `figures` по реализации.
Даже при сработавшем триггере нет ветки «склад снят словом „всех“, товар
не назван → clarify subject».

---

## 3. Проект починки (без правки в этом коммите)

### 3.0. Принципы

1. Правило — **кодом** (гейт/ветка), не промтом.
2. Уточнение — слоты/options словами человека (`period` / «деньги или количество» /
   «какой товар»), не `accumulationregister_…`.
3. Не трогать верные №4, 5, 9, 13, 15:
   - №15: год в цифрах вопроса → `assumed` пуст → clarify периода **не** зовётся;
   - №4/5/13: `no_data` до меры/периода — ранний clarify периода только когда
     период уже выведен и собираются считать;
   - №9: `verdict_before` / already-clarify — не перекрывать.

### 3.1. Хелпер: длинное assumed-окно → нужно уточнение

Новая чистая функция рядом с `period_is_canon_guess`:

```python
def period_assumed_needs_clarify(intent, today=None):
    """Assumed-окно длиной ≥ ~квартала без года в вопросе → уточнить период.

    День/неделя/месяц (короткие относительные) — False: одно условное прочтение.
    Календарный/скользящий год и кварталоподобное окно — True (п. 12).
    """
    if serene_enough is None or not serene_enough.period_assumed(intent):
        return False
    p = (intent or {}).get("period") or {}
    fr, to = p.get("from"), p.get("to")
    if not fr or not to:
        return False
    if not today:
        today = time.strftime("%Y-%m-%d")
    if period_is_canon_guess(p, today):
        return True
    od_fr, od_to = _day_ord(fr), _day_ord(to)
    if od_fr is None or od_to is None:
        return False
    span = od_to - od_fr
    # квартал ≈ 89..92; год уже покрыт canon_guess; короче месяца — нет
    return span >= 85
```

Почему не ломает верные и обычные относительные:

- «вчера» / «эта неделя» / MTD — span ≪ 85 → False;
- «за 2022 год» — не `period_assumed` → False (№15);
- «за год» / «за квартал» без цифр года — True (№1, №2).

### 3.2. Патч A — ранний clarify периода в `answer`

Сразу после записи `diag.intent_assumed` (~12094), до поиска:

```diff
     if разбор.get("assumed"):
         diag["intent_assumed"] = ", ".join(
             "%s=%s" % (a, (intent.get("period") or {}).get(a.split(".")[-1], ""))
             for a in разбор["assumed"])
+    # K4-1 / п. 12: длинное assumed-окно — уточнение, не число наугад.
+    # Не при period_from_prior и не при доказанном ticket (trusted/resolved period).
+    if (not period_from_prior
+            and not (trusted or {}).get("period")
+            and period_assumed_needs_clarify(intent, today)):
+        diag["period_assumed_clarify"] = True
+        slots = [{"kind": "period", "word": ""}]
+        ask = _need_clarify(
+            question, slots,
+            "период выведен системой, в вопросе не назван",
+            dict(diag, шаг="assumed-period"))
+        if ask:
+            return ask
```

`_need_clarify` уже даёт `kind=clarify`, `options=[]`, текст моделью на языке
человека, без имён таблиц — тот же путь, что у «достаточности» (№9 не ломает:
там нет assumed year/quarter).

### 3.3. Патч B — rank×sales без названной меры → `role_ask` + clarify

В `sales_rank_resolve_measure` (~5676): если у источника есть **и** money, **и**
qty, а в вопросе/intent нет роли ни одной (`_alias_role_in_question` /
`intent.measure` пуст) — не выбирать:

```diff
 def sales_rank_resolve_measure(...):
     ...
     product_axis = sales_rank_product_axis(...)
     sm, how = sales_rank_canon_measure(...)
     if how == "role_ask":
         return None, "role_ask"
+    # K4-1 / Э3 №8: топ без «деньги|штуки» — уточнение, не money/qty-догадка.
+    _money = sales_money_measure(names, alias_by)
+    _qty = sales_qty_measure(names, alias_by)
+    _word = ((intent or {}).get("measure") or "").strip()
+    _named = bool(_word) or (
+        (_money and _alias_role_in_question(question, _money, alias_by))
+        or (_qty and _alias_role_in_question(question, _qty, alias_by)))
+    if not _named and _money and _qty and not measure_pick_sentinel:
+        return None, "role_ask"
     if not sm and not product_axis:
         ...  # прежний fallback — только если одной из мер нет
```

В `answer` (~14171), когда `_how == "role_ask"`: не продолжать канон, а собрать
options как у `measure_ambiguous` — только две живые меры с `measure_captions`
(человеческие подписи из алиасов), `kind=clarify`.

Не задевает: compare/sum с `sales_force_money_measure` (не `_rank_sales`);
вопросы «по деньгам» / «по количеству» (`_named`); №15 и no_data-ветки.

После выката — синхронизировать `test_sales_rank_canon.py`: строки «топ-3
товара → Количество без меры» сменить на ожидание `role_ask` / clarify
(или добавить меру в формулировку gold).

### 3.4. Патч C — №12 остатки без товара

1. Расширить опознание остатков **без** нового списка русских слов в промте —
   в код маркеров (уже есть прецедент `_STOCK_MARKERS`): стемы/корни
   `леж` / `склад` / `warehouse` / `storage`, либо `ts_lexize` по словарным
   маркерам из `search_meta` (предпочтительно данные, не литералы).
   Минимум для закрытия замера: ловить «склад*» и «лежит/леж» рядом с
   существующими маркерами — иначе вопрос №12 снова не войдёт в stock-path.

2. После `question_asks_stock_balance` и `not stock_asks_named_product`:
   если человек **снял** неоднозначность склада («всех» / all) **или** складов
   в данных больше одного, а товар не назван — `clarify` со слотом
   `subject` («какой товар / какая номенклатура?») через `_need_clarify`,
   **не** `balance_bridge_clarify` со списком регистров.

```diff
     if question_asks_stock_balance(question):
         ...
         named = stock_asks_named_product(question, intent)
+        if not named and not (trusted or measure_pick):
+            # K4-1 / Э3 №12: остаток без предмета — уточнение, не figures.
+            diag["stock_subject_clarify"] = True
+            ask = _need_clarify(
+                question, [{"kind": "subject", "word": "товар"}],
+                "остаток без названного товара",
+                dict(diag, шаг="stock-subject"))
+            if ask:
+                return ask
```

Узкий вход: только stock-path. Не трогает №4/5/13 (не stock) и №9 (уже
subject-clarify другим путём). №10/11 после этого могут сначала спросить
товар — если нужно сохранить «какой склад?» при одном безымянном товаре,
уточнить порядок слотов отдельным шагом (не блокер K4-1 №12: там склад
уже «всех»).

### 3.5. Документы после выката патча (оркестратор)

- `HOW_IT_WORKS.md`: строка «assumed применяется, но помечается» → «длинное
  assumed-окно → `clarify`, короткое относительное — как сейчас».
- `ACCEPTANCE_AMBIGUOUS.md`: после повторного прогона — обновить §8.
- `test_sales_rank_canon.py` — см. §3.3.

---

## 4. Проект замка

**Файл:** `ubuntu/serenedb/test_k4_guess_vs_clarify.py`  
Стиль: как `test_enough.py` / `test_period_empty.py` — оффлайн, без базы/сети,
подмена только там, где нужна; `t(name, cond)`.

### 4.1. Случаи (провал = assert не выполняется)

| id | Что проверяет | Провал |
|---|---|---|
| P1 | `period_assumed_needs_clarify` на окне rolling-12m + `parse.assumed` | False / нет clarify |
| P2 | то же для span≈90 дней (квартал) | False |
| P3 | «2022» в period + assumed пуст → False | True (ломает №15) |
| P4 | span=0 «вчера» + assumed → False | True (ломает короткие относительные) |
| M1 | `sales_rank_resolve_measure` на топ без меры, names⊃{Всего,Количество} → `(None, "role_ask")` | вернулся Всего/Количество |
| M2 | то же с `measure`/`question` «по деньгам» → money, не ask | ask или qty |
| S1 | `question_asks_stock_balance("…лежит на всех складах…")` → True | False (как сейчас) |
| S2 | `stock_asks_named_product` на №12 → False | True |
| S3 | хелпер/ветка `stock_subject_needs_clarify` → True при stock∧¬named | False |

### 4.2. Каркас теста (выкатывается вместе с патчем A/B/C)

```python
#!/usr/bin/env python3
"""K4-1: догадка периода/меры/остатка → clarify (Э3 okna №1,2,8,12)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
import serene_ask as A
import serene_enough as E

PASS, FAIL = 0, []
def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1; print("ok  -", name)
    else:
        FAIL.append(name); print("FAIL-", name, detail or "")

today = "2026-08-27"
# P1–P4
intent_year = {
    "want": "sum", "kind": "продажи",
    "period": {"from": "2025-08-27", "to": "2026-08-27"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
t("P1 rolling year assumed → clarify",
  A.period_assumed_needs_clarify(intent_year, today))
t("P3 explicit 2022 → no assumed-clarify",
  not A.period_assumed_needs_clarify({
      "period": {"from": "2022-01-01", "to": "2022-12-31"},
      "parse": {"assumed": []}}, today))
# M1–M2 — sales_rank_resolve_measure + aliases
# S1–S3 — stock markers + subject helper
# ...
print("----\n%d ok, %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
```

Файл уже в дереве: до патча A/B/C кейсы хелперов — `pending` (не FAIL);
после выката кода те же id обязаны стать `ok`.

### 4.3. Живой контроль после выката

Повтор команды из `ACCEPTANCE_AMBIGUOUS.md` §4 на okna: ожидание по классу
K4-1 — №1, 2, 8, 12 дают `kind=clarify` (игла: год/квартал; деньги|количество;
товар). Верные №4, 5, 9, 13, 15 без регресса.

---

## 5. Связь с графом / выкат

| Компонент | Роль |
|---|---|
| `serene_ask.py` | патчи A/B/C (оркестратор, не этот коммит) |
| `serene_enough.py` | датчики `period_assumed` / `period_given` без смены контракта |
| `docs/ACCEPTANCE_AMBIGUOUS.md` | замер 5/18; повтор после патча |
| этот файл | проект K4-1 |

Порядок выката: замок оффлайн зелёный → deploy `serene_ask` → живой §4 на
okna → правка HOW_IT_WORKS + строка в CHANGELOG с числами до/после.
