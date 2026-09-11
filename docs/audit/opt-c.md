# OPT-C: молекула Z7→«кандидаты собраны» (25,3 с)

Режим: только чтение кода. Дата: 11.09.2026.  
Роль C. Код: `z20_ask_main_http.py`, `z06_entity_search.py`, `z12_stock_balance.py`,
`z13_fork_outcomes.py`, `entity_rank_v2.py`.  
Факты зонда: rid `b11dac07`, полигон; Z6→Z7 K6-apply **1,3 с**; Z7→«кандидаты собраны»
**25,3 с**; corp-агрегат IN(…) = **40 мс** (EXPLAIN). Контекст: `MOL_PLAN` §0–§3,
`mol-k6-m1` молекула 2.

---

## Вердикт

**Атрибуция «entity_pick_counts_for_model = 25,3 с» неверна** (тот же класс ошибки, что
M1 про K6). `entity_pick_counts_for_model` — чистый Python по уже готовым `by` и
`diag["answer_fit_v2_full"]`, **без SQL**, O(|by|) словарных чтений (миллисекунды).

Реальные **~25 с** окна — блок **stock#2** (`z20:2270–2286`): повторный
`stock_question_engaged` + (при ложном «складской») повтор фильтров / `stock_goods_pool`
/ `filter_balance_structural`. Ожидание **−20…−24 с** закрывается кэшем детектора и
снятием дубля фильтров, а не батчем «counts по 77».

---

## 1. Карта окна (код)

Порядок в `z20` (актуальные строки):

| Строки | Что | SQL? | Оценка wall |
|---|---|---|---|
| `2267–2268` | `entity_pick_counts_for_model(by, diag, intent, question)` | нет | ≪10 мс |
| `2269` | `шаг("K6 v2")` | маркер | — |
| `2270` | `if stock_question_engaged(...)` | **да, внутри детектора** | основная доля 25,3 с |
| `2271` | `balance_capable_or_registers()` | meta/map (кэш 300 с) | ≪0,1 с если карта теплая |
| `2272` | `filter_stock_balance_sales_noise` | снова `engaged` | +детектор |
| `2273` | `filter_stock_goods_registers` | снова `engaged` + `stock_goods_pool` → `registers_for_kind_axes` (**EXISTS по корпусу**) | секунды…десятки с при engaged |
| `2275–2286` | named / `filter_balance_structural` | 1× `GROUP BY` IN(cands) | умеренно, если вошли |
| `2287` | `шаг("кандидаты собраны")` | маркер | накопл. +25,3 с от Z7 |

Важно: вызов `entity_pick_counts_for_model` стоит **до** маркера `K6 v2`, не в интервале
Z7→«собраны». Подпись зонда «entity_pick + до шага» смешивает имя функции с соседним
кодом. Интервал роли C по смыслу задания — **всё до «кандидаты собраны» после K6**, т.е.
`z20:2270+`.

Симметрия с stock#1 (`z20:2232–2239`, факт зонда **50,6 с**): тот же детект + те же
фильтры уже отработали до K6. stock#2 — **второй проход того же класса работ**.

---

## 2. `entity_pick_counts_for_model` — разбор

Источник: `z06_entity_search.py:548–577`.

```548:577:ubuntu/serenedb/ask/z06_entity_search.py
def entity_pick_counts_for_model(by, diag, intent=None, question=""):
    ...
    by = dict(by or {})
    feats = (diag or {}).get("answer_fit_v2_full") or {}
    if not by or not feats:
        return by
    want = ((intent or {}).get("want") or "").strip().lower()
    if want not in ("count", "") and not rank_intent_from(intent, question=question):
        return by
    out = dict(by)
    for src, raw in by.items():
        f = feats.get(src) or {}
        ...
        n_ov = int(f.get("q_row_overlap") or 0)
        ...
```

### Что это делает

1. Берёт literal-счётчики `by` (уже посчитаны шагом буквального отбора — один SQL
   GROUP BY раньше по тракту).
2. Берёт `answer_fit_v2_full` из diag — **уже положено K6** в
   `entity_rank_v2.apply_to_candidates` (`:861`, срез `reordered[:24]`).
3. Для источников с `q_meta_overlap` подменяет число на `q_row_overlap` / оценку из
   `n_rows×q_row_ratio` — без похода в БД.

### Чего нет

- Нет цикла «по одному кандидату → psql».
- Нет counts «по словам» здесь: word-overlap уже сделан внутри K6 функцией
  `_question_overlap_batch` (`entity_rank_v2.py:281–348`) — **один** meta-SQL
  `IN (все cands)` + при необходимости **один** doc-SQL только по `small_meta`
  (n_rows≤1000). Это часть K6-apply (факт зонда **1,3 с**), не окна 25,3 с.
- Corp-агрегат `features_table` (`:368–379`) — тоже один `IN` GROUP BY; EXPLAIN 40 мс
  подтверждает: база быстрая, «counts×77 по одному» в K6 нет.

### Потребитель

`counts_for_model` уходит в `wiki_primary_entity_cascade` (`z20:2835–2837` →
`z21:659–660`). В теле каскада параметр **не читается** (вики-пул из карточек, не из
counts). Эффект на боевом wiki-пути — мёртвый (раньше зафиксировано p1-B9 / map2-B).
Оптимизация counts ради выбора сущности **не даст −20 с** и почти не даст качества.

### Переиспользование by/feats

Уже сделано: feats из K6, by из literal. Дополнительный SQL для «пересчёта counts»
был бы регрессом. Батч-IN для entity_pick — пустая работа (нечего батчить).

---

## 3. Откуда тогда 25,3 с

Согласуется с `mol-k6-m1` §«Молекула 2» (~21,5 с тогда; сейчас 25,3 с — тот же контур).

### 3.1. Детектор (даже на False)

`stock_question_engaged` (`z12:416–437`) всегда:

- `_kind_is_stock_scoped` → `_catalogs_for_axis_word(kind)` →
  `entity_form_catalogs_for_kind` (stem SQL; при периоде — meaning/embed);
- `question_mentions_warehouse_axis` → цикл по словам вопроса × catalogs.

На «сколько продали вчера и чего продали. полный отчет»: period есть →
`allow_meaning=True`; kind/ось «чего» может резолвиться в product-catalog →
`stock_kind=True` → **ложное «складской» на sales+отчёт**.

Внутри stock#2 `engaged` зовётся ещё раз из:

- `filter_stock_balance_sales_noise` (`z13:23`);
- `filter_stock_goods_registers` (`z12:869`).

Итого на одном входе в `if` — до **×3** полных прогонов детектора (плюс stock#1 до K6).

### 3.2. Тело if (если engaged=True)

| Вызов | Где | SQL |
|---|---|---|
| `balance_capable_or_registers` | `z12:724` | `search_balance_map` / meta (TTL 300 с) |
| `filter_stock_goods_registers` → `stock_goods_pool` → `registers_for_kind_axes` | `z12:847–865`, `:440–469` | refcols + **коррелят `EXISTS (… search_corpus … nums)`** |
| `filter_balance_structural` | `z12:1268–1307` | один `IN` + HAVING по корпусу |
| `stock_asks_named_product` / сужение пула | `z20:2275–2278` | + ещё `stock_goods_pool` |

`registers_for_kind_axes` — главный тяжёлый SQL фильтрового тела (не «counts по словам»).
Он уже «батч» по списку регистров, но зонд корпуса дорогой и **повторяется**, если
pool/capable не кэшированы в запросе.

### 3.3. Чего окно не содержит

- Повторного `features_table` / `_question_overlap_batch`.
- Цикла counts×77 в Python с SQL.
- Арбитра / fork / wiki (они после «кандидаты собраны»).

---

## 4. План правок (файл:строка) → −20…−24 с

Только оптимизация существующего контура. Складской путь для истинных складских
вопросов не ломать (гейт Role S/R). Батч «counts×77» для entity_pick **не делать**.

### C0. Субмаркер (обязателен до/вместе с правкой)

| Что | Где |
|---|---|
| `шаг("stock#2 enter")` сразу после `2269` | `z20:2270` |
| `шаг("stock#2 engaged", v=bool)` после первого `engaged` | `z20:2270` |
| `шаг("stock#2 filters done")` перед `2287` | `z20:2286` |

Снять на том же вопросе: доля детект vs фильтры. Без этого легко снова спутать с counts.

### C1. Кэш `stock_question_engaged` на запрос (главный −сек здесь)

| Правка | Файл:строка |
|---|---|
| Ключ `(id(intent), id(plan), hash(question))` или запись в `diag["_stock_engaged_cache"]` | `z12:416` вход функции |
| Первый расчёт пишет bool; повторные вызовы (`z20:2270`, `z13:23`, `z12:869`, `stock_canon_src:1066`) читают кэш | `z12:416–437` |

Ожидание на этом окне: если после Role S детект станет **False за ≪1 мс** — весь stock#2
= early-exit → **−24…−25 с**. Если детект остаётся True (редкий истинный склад) —
кэш всё равно снимает ×3 повторных word-loop/catalog внутри #2 (−несколько с).

Совместимо и зависимо от плана S (быстрый intent-гейт без SQL-проб). C1 без S всё равно
режет повтор внутри #2 и дубль с #1.

### C2. Не гонять фильтры второй раз

| Правка | Файл:строка |
|---|---|
| После успешного stock#1 (`z20:2232–2237`) ставить `diag["stock_pool_filtered"]=1` (+ снимок capable при необходимости) | `z20:2232–2237` |
| В stock#2: если флаг и `engaged` (из кэша) — **не** повторять `balance_capable` / noise / goods; оставить только уникальное: named + `filter_balance_structural` (или structural только если #1 его не делал) | `z20:2270–2286` |

Ожидание при ложном engaged=True (пока S не закрыт): снять второй
`registers_for_kind_axes`+EXISTS → типично **−15…−22 с** из 25,3 (остаток — один детект
до кэша C1 / structural).

### C3. Кэш `stock_goods_pool` / `registers_for_kind_axes` в запросе

| Правка | Файл:строка |
|---|---|
| Memo на `(intent axes, question)` → frozenset | `z12:440`, `z12:847` |

Запасной слой, если C2 ещё не влит, а #1 и #2/`prefer` оба зовут pool. Не новый индекс —
переиспользование результата существующего SQL.

### C4. `entity_pick_counts_for_model` — без таймингового плана

| Действие | Файл:строка | Зачем |
|---|---|---|
| Оставить как есть (уже reuse by/feats) | `z06:548–577`, вызов `z20:2267–2268` | 0 с выигрыша, контракт K6c для legacy pick |
| Опционально: не звать, если `not diag.get("answer_fit_v2_full")` — уже early-return внутри | — | шум |
| Не писать батч-SQL «пересчитать overlap ещё раз» | — | дубль K6, запрет п.20 по духу |
| Не ThreadPool по `by.items()` | — | нет I/O |

Word-counts уже батчем: `_question_overlap_batch` (`entity_rank_v2.py:281–348`). Трогать
только если новый зонд покажет регресс K6>бюджет — это пакет K6/`MOL_PLAN` §3, не C.

### C5. Параллель пачек — для этого окна не нужна

Элементы stock#2 **зависимы по порядку** (engaged → capable → filter → structural) и
пишут в один `diag`/`cands`. Параллелить «по кандидату» фильтры = гонки порядка +
N×EXISTS вместо одного batch. Владельческое «последовательный перебор → параллель»
здесь не применимо: перебора counts×77 нет; есть повтор одного тяжёлого пути.

Параллель — зона Role P (intent-сэмплы, arbiter×N), не молекула C.

---

## 5. Бюджет −20…−24 с

| Шаг | Условие | Δ на окне Z7→собраны |
|---|---|---|
| C1 + быстрый False (план S) | sales/полный отчёт перестаёт быть stock | **−24…−25 с** (весь блок) |
| C1 only (engaged всё ещё True) | сняты ×3 детект внутри #2 | −3…−8 с |
| C2 (+ C3) | снят второй goods/EXISTS | **−15…−22 с** |
| C4 entity_pick | — | **~0 с** |

Целевой коридор роли (−20…−24) достигается **C1∩S** или **C2** на текущем ложном
engaged; в сумме с S (50,6 с stock#1) — основной кусок 88 с.

Анти-двойной счёт с Role S: секунды stock#1 не плюсовать сюда. Здесь только хвост после
K6. Общий выигрыш stock = #1+#2 при одном кэше детектора.

---

## 6. Приёмка (для исполнителей C / стык S)

1. Тот же вопрос rid-класса `b11dac07`: Z7→«кандидаты собраны» ≤ **2 с** (лучше ≤0,2 с
   при engaged=False).
2. Субмаркеры C0: `engaged=0` на sales+полный отчёт; на истинном складском — `engaged=1`
   и фильтры один раз (нет второго EXISTS того же pool).
3. Замки stock + L67: порядок/выбор сущности на полном пути не хуже baseline.
4. `counts_for_model`: снимок до/после на count/rank — равенство где feats те же
   (функция не меняет семантику при C4 no-op).
5. Wiki-каскад не трогать; не вводить питон-пулы поверх корпуса в этом окне.

---

## 7. Итог одной строкой

**25,3 с — это stock#2, не counts.** `entity_pick_counts_for_model` уже переиспользует
`by`/`feats` без SQL; батчить нечего. План: кэш `engaged` + не дублировать фильтры
после stock#1 (`z20:2270–2286`, `z12:416/440/847`) → −20…−24 с на этом окне.
