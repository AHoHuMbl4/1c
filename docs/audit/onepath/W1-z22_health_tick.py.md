# W1 — карта живости: `ask/z22_health_tick.py`

Дата: 12.09.2026. Только чтение кода. Метод: AST верхнего уровня зоны +
`rg` по `ubuntu/serenedb/ask/*.py`, оба z20, `_bootstrap`/`_imports`/`_wire`,
`ubuntu/serenedb/test_*.py` (в т.ч. f-строки / getattr / строковые имена).

Файл зоны: 58 строк. Определений верхнего уровня: **3**.

---

## 1. Определения верхнего уровня

| Символ | Вид | Строки файла | Число строк |
|---|---|---|---|
| `_TICK_STATUS_NOTE_RE` | константа (`re.compile`) | 9–9 | 1 |
| `_parse_tick_status_note` | `def` | 12–19 | 8 |
| `_measure_tick_status` | `def` | 22–55 | 34 |
| **сумма символов** | | | **43** |

Остаток файла (15 строк): модульный docstring, импорты/`apply_bindings`,
пустые строки, `register_zone()` — не символы зоны.

Назначение зоны: поле `tick` в ответе `GET /health` (статус последнего такта
из `search_quality.k=tick_status`). К wiki-каскаду ask / выбору прочтения
не относится — это дверь HTTP того же модуля Handler.

---

## 2. Кто зовёт (по символам)

### `_measure_tick_status` (34 строки)

| Источник | Вызовы | Примечание |
|---|---|---|
| **новый** `z20_ask_main_http.py` | `2783` (`Handler.do_GET`, ветка `/health`) | прямой вызов |
| **legacy** `z20_ask_main_http_legacy.py` | `4934` (`Handler.do_GET`, ветка `/health`) | прямой вызов, зеркало |
| другие `z*.py` | — | упоминаний нет |
| `_bootstrap.py` | файл зоны в `_ZONE_FILES` (`:44`) | загрузка зоны в namespace, не вызов символа |
| `_imports.py` / `_wire.py` | — | нет |
| тесты | `test_health_tick_status.py:45,51` (прямой); `:93` — строка в `ask_source()` | замок `/health` + tick |

getattr / словарь / f-строка с именем — **не найдены**.

### `_parse_tick_status_note` (8 строк)

| Источник | Вызовы |
|---|---|
| внутри зоны | `_measure_tick_status` → `z22_health_tick.py:32` |
| новый / legacy z20 | нет прямого |
| другие зоны | нет |
| bootstrap / imports / wire | нет |
| тесты | `test_health_tick_status.py:26,27,28` |

### `_TICK_STATUS_NOTE_RE` (1 строка)

| Источник | Вызовы |
|---|---|
| внутри зоны | `_parse_tick_status_note` → `z22_health_tick.py:16` |
| снаружи зоны | нет (ни z20, ни тесты, ни другие зоны) |

---

## 3. Таблица вердиктов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---|---|---|
| `_TICK_STATUS_NOTE_RE` | 1 | только `z22_health_tick.py:16` ← `_parse_tick_status_note` | **ЖИВА НОВОМУ** (транзитивно) |
| `_parse_tick_status_note` | 8 | `z22_health_tick.py:32` ← `_measure_tick_status`; тесты `test_health_tick_status.py:26–28` | **ЖИВА НОВОМУ** (транзитивно) |
| `_measure_tick_status` | 34 | **новый** `z20_ask_main_http.py:2783`; legacy `z20_ask_main_http_legacy.py:4934`; тесты `test_health_tick_status.py:45,51` | **ЖИВА НОВОМУ** (прямо) |

Нет символов «только legacy» и нет мёртвых.

---

## 4. Итог зоны

| Вердикт | Строк символов | Доля от 43 |
|---|---|---|
| **ЖИВА НОВОМУ** | **43** | 100% |
| ЖИВА ТОЛЬКО LEGACY | 0 | 0% |
| МЁРТВА | 0 | 0% |
| Файл всего (с обвязкой) | 58 | — |

**Вердикт зоны:** зона **ЖИВА НОВОМУ**. Нужна одному пути как часть HTTP-поверхности
нового z20 (`GET /health` → поле `tick`), не как шаг тракта
«вопрос → вики → SQL → меню». После сноса legacy зона **остаётся** — тот же
прямой зов есть в новом z20.

`_bootstrap.py` грузит `z22_health_tick.py` **всегда** (до выбора z20), в общий
namespace; `_imports.py` / `_wire.py` имён зоны не держат.

Писатель `tick_status` в БД — shell `ubuntu/serenedb/tick_status.sh` (build/pipeline),
не эта зона; замок `test_pipeline_tick_status.py` зону Python не трогает.

---

## 5. Транзитивные цепочки

```
_TICK_STATUS_NOTE_RE
  ← _parse_tick_status_note
    ← _measure_tick_status
      ← Handler.do_GET (/health)
        ← новый z20_ask_main_http.py:2783
        ← legacy z20_ask_main_http_legacy.py:4934
```

Корень для «новому»: **новый z20**, прямой. Legacy — параллельный корень
(тот же `/health` до flip). Других зон в цепочке нет.

Тестовая цепочка (не прод-корень):

```
_parse_tick_status_note / _measure_tick_status
  ← test_health_tick_status.py
  (+ косвенно Handler.do_GET через FakeHandler в том же тесте)
```

---

## 6. Скрытые выбиратели, доступные новому тракту

**Нет.**

Зона только:

1. читает одну строку `search_quality` (`k='tick_status'`);
2. разбирает `note` regex’ом `fail=…|reason=…`;
3. считает возраст ok/fail и строку `summary`.

Нет выбора источника / меры / периода / оси / типа записи. В ask-каскад
нового z20 (`answer` / wiki) символы зоны не входят — только в `do_GET /health`.
В новый тракт «вопрос→ответ» скрытых выбирателей зона не тащит.

---

## 7. Краткий ответ на вопрос задачи

**Нужна ли зона одному пути?** Да — для двери `/health` нового z20 (поле
`tick`). Для самого ask-onepath (wiki→SQL→меню) — нет роли. Сносить после
flip нельзя: новый z20 её зовёт напрямую.
