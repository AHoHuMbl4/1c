# W1 — карта живости: `ask/z04_calendar_axis.py`

Дата съёмки: 12.09.2026. Код не менялся. Источник: `ubuntu/serenedb/ask/z04_calendar_axis.py` (297 строк файла; 19 символов верхнего уровня, сумма тел = 253 строки).

Метод: AST верхнего уровня + `rg` по голым именам в `ask/*.py`, обоих z20, `test_*.py`, `_bootstrap.py` / `_imports.py` / `_wire.py`. Учтены вызовы `(`, getattr/строки (отдельных getattr/f-строк на символы z04 нет). Импортов зон нет — только общий namespace после `_bootstrap` + `wire_all`.

---

## Итог зоны

| Вердикт | Строк символов | Доля от 253 |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 217 | 85.8% |
| **ЖИВА ТОЛЬКО LEGACY** | 22 | 8.7% |
| **МЁРТВА** | 14 | 5.5% |

**Вердикт зоны: нужна одному пути.** Новый z20 прямо зовёт `expand_readings_calendar_axis` и `calendar_axis_unavailable_block`; через `_predicates` → `period_preds` тянет `_working_day_doc_preds`. После flip legacy останется мёртвым только `calendar_day_basis_prefer` (+ уже мёртвый `prefer_day_basis_leader` и затёртый `_sql_ident`).

Прямые входы нового z20 (`z20_ask_main_http.py`):
- `1887` — `expand_readings_calendar_axis(readings, prefer=None)`
- `1907` — `calendar_axis_unavailable_block(...)`

Прямые входы legacy (`z20_ask_main_http_legacy.py`):
- `1779` — `calendar_day_basis_prefer`
- `1781` — `expand_readings_calendar_axis(..., prefer=_day_prefer)`
- `1785` — `calendar_axis_open()`
- `1817` — `calendar_axis_unavailable_block`

Инфраструктура: `_bootstrap.py:26` грузит зону в список; `_imports.py` / `_wire.py` имён z04 не содержат (только общий `register_zone` / `apply_bindings`).

---

## Таблица символов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_sql_ident` | 3 (9–11) | только `_working_day_doc_preds` (z04:287–289). После bootstrap имя в namespace затирает `z04b_currency_axis._sql_ident` (порядок `_bootstrap`: z04 → z04b; `wire_all` — последний побеждает). Тело z04 не исполняется. | **МЁРТВА** (затёрта z04b) |
| `calendar_registers` | 14 (14–27) | z04: `calendar_axis_map_ready` 85, `calendar_axis_open` 182; тесты monkeypatch `test_calendar_axis.py` 75/83/92/314, `test_ab_calendar_axis_set.py` 103. Meta-строка `'calendar_registers'` в SQL/тестах meta_build — не вызов функции. | **ЖИВА НОВОМУ** (через map_ready / open) |
| `calendar_working_day_keys` | 15 (30–44) | z04: map_ready 85, open 182, `_working_day_doc_preds` 273; тесты как registers. | **ЖИВА НОВОМУ** |
| `calendar_map_rows` | 29 (47–75) | z04: map_ready 86, open 183, `_working_day_doc_preds` 274; тесты как registers. | **ЖИВА НОВОМУ** |
| `_DAY_BASIS_HOLIDAY` | 1 (78) | только конструктор `_DAY_BASIS_NEED_MAP` (z04:79). | **ЖИВА НОВОМУ** (через NEED_MAP) |
| `_DAY_BASIS_NEED_MAP` | 1 (79) | z04: `day_basis_from_question` 128, `calendar_day_basis_needed` 141/148/152; `z13_fork_outcomes.py:191` (`_fork_class_axis_unavailable`). | **ЖИВА НОВОМУ** |
| `_CALENDAR_DAY_BASIS_PHRASES` | 1 (80) | только `calendar_day_basis_phrases` (кэш at/map). | **ЖИВА НОВОМУ** |
| `calendar_axis_map_ready` | 4 (83–86) | z04: `calendar_axis_unavailable_block` 163; `z13_fork_outcomes.py:192`; тесты `test_calendar_axis.py` 289/316, `test_fork_outcomes.py` 359–360/407 (monkeypatch). | **ЖИВА НОВОМУ** (прямо через unavailable_block ← new z20) |
| `calendar_day_basis_phrases` | 30 (89–118) | z04: `day_basis_from_question` 126; тесты monkeypatch `test_calendar_axis.py` 277/287/307/316, `test_ab_calendar_axis_set.py` 101. | **ЖИВА НОВОМУ** |
| `day_basis_from_question` | 14 (121–134) | z04: `calendar_day_basis_needed` 143, `calendar_day_basis_prefer` 204; тесты inspect `test_calendar_axis.py` 317. | **ЖИВА НОВОМУ** (через needed ← unavailable_block) |
| `calendar_day_basis_needed` | 18 (137–154) | z04: `calendar_axis_unavailable_block` 160; тесты inspect 317. | **ЖИВА НОВОМУ** |
| `calendar_axis_unavailable_block` | 19 (157–175) | **new** `z20_ask_main_http.py:1907`; **legacy** `z20_ask_main_http_legacy.py:1817`; `z13_fork_outcomes.py:652` (`fork_outcome_c`); тесты `test_calendar_axis.py` 290–304/318/353, `test_ab_calendar_axis_set.py` 106. | **ЖИВА НОВОМУ** |
| `calendar_axis_open` | 6 (178–183) | z04: `calendar_axis_readings` 225, `expand_readings_calendar_axis` 240; **legacy** `z20_ask_main_http_legacy.py:1785` (прямо); тесты 118/122/124/312. | **ЖИВА НОВОМУ** (через expand ← new z20) |
| `calendar_day_basis_prefer` | 22 (186–207) | **legacy** `z20_ask_main_http_legacy.py:1779`; `z09_fork_detector.py:412` (`fork_detector_scan` — в new z20 вызовов нет); тест `test_calendar_axis.py` 257–259. New z20 передаёт `prefer=None` в expand и prefer не зовёт. | **ЖИВА ТОЛЬКО LEGACY** |
| `_day_basis_reading` | 7 (210–216) | z04: `calendar_axis_readings` 234; тесты inspect 314. | **ЖИВА НОВОМУ** |
| `calendar_axis_readings` | 16 (219–234) | z04: `expand_readings_calendar_axis` 244; тесты 102/119/131/144/260/312. | **ЖИВА НОВОМУ** |
| `expand_readings_calendar_axis` | 13 (237–249) | **new** `z20_ask_main_http.py:1887`; **legacy** `…_legacy.py:1781`; `z09_fork_detector.py:413`; тесты 105–107/140/312. | **ЖИВА НОВОМУ** |
| `prefer_day_basis_leader` | 11 (252–262) | прод-вызовов нет; только def + inspect-список `test_calendar_axis.py:313` (без вызова `(`). | **МЁРТВА** |
| `_working_day_doc_preds` | 29 (265–293) | `z03_period_windows.py:45` внутри `period_preds`; тесты 313/338/344. Цепочка new: `_predicates` (z06:17) → `period_preds` → здесь; new z20 зовёт `_predicates` на 1190/1891/1994/2006/2205. | **ЖИВА НОВОМУ** |

Константы `_DAY_BASIS_WORKING` / `_DAY_BASIS_CALENDAR` / `_DAY_BASIS_IDS` / `_DAY_BASIS_LEADER_DEFAULT` / кэши `_CALENDAR_REGS|_CALENDAR_WORK_KEYS|_CALENDAR_MAP` / флаг `ASK_CALENDAR_AXIS` живут в **z03**, не в z04 — в таблицу зоны не входят.

---

## Транзитивные цепочки

### До нового z20 (`z20_ask_main_http.py`)

```
expand_readings_calendar_axis ← z20:1887
  ← calendar_axis_open ← calendar_registers + calendar_working_day_keys + calendar_map_rows
  ← calendar_axis_readings ← _day_basis_reading
      ← calendar_axis_open (ещё раз)

calendar_axis_unavailable_block ← z20:1907
  ← calendar_day_basis_needed
      ← day_basis_from_question ← calendar_day_basis_phrases ← _CALENDAR_DAY_BASIS_PHRASES
          ← _DAY_BASIS_NEED_MAP ← _DAY_BASIS_HOLIDAY
  ← calendar_axis_map_ready ← calendar_registers + calendar_working_day_keys + calendar_map_rows

_working_day_doc_preds ← period_preds (z03:45)
  ← _predicates (z06:17)
  ← z20:_predicates на 1190 / 1891 / 1994 / 2006 / 2205
  ← (после меню/sole) day_basis=working_days на intent.period через _apply_sole_reading (z20:1458+)
  ← calendar_working_day_keys + calendar_map_rows
  ← runtime-_sql_ident (слот имени = z04b после wire)
```

Параллельные пути из зон, **не** достигающие new z20:
- `z09_fork_detector.fork_detector_scan` → prefer + expand — вызывается только из **legacy** z20 (`2380`, `2924`).
- `z13_fork_outcomes.fork_outcome_c` / `_fork_class_axis_unavailable` → unavailable_block / map_ready — `fork_outcome_*` только из **legacy** z20 (`3001+`, `3023`). Для самих символов это доп. legacy-рёбра; живость новому уже обеспечена прямыми вызовами.

### До legacy z20

```
calendar_day_basis_prefer ← legacy:1779
  ← day_basis_from_question (общий с new)

expand_readings_calendar_axis ← legacy:1781 (prefer=_day_prefer)
calendar_axis_open ← legacy:1785 (прямо, плюс через expand)
calendar_axis_unavailable_block ← legacy:1817

calendar_day_basis_prefer ← z09:412 ← fork_detector_scan ← legacy:2380/2924
expand_readings_calendar_axis ← z09:413 ← то же
calendar_axis_unavailable_block ← z13:652 ← fork_outcome_c ← legacy
calendar_axis_map_ready ← z13:192 ← _fork_class_axis_unavailable ← fork_outcome_* ← legacy
```

### Никуда (мёртвые)

```
prefer_day_basis_leader  — нет prod-вызовов
_sql_ident (тело z04)    — затёрта одноимённой функцией z04b при загрузке
```

---

## Замки (тесты)

| Файл | Что трогает из z04 |
|---|---|
| `ubuntu/serenedb/test_calendar_axis.py` | основной замок зоны: open/readings/expand/prefer/unavailable/map_ready/phrases/`_working_day_doc_preds`; inspect-список публичных имён |
| `ubuntu/serenedb/test_ab_calendar_axis_set.py` | `calendar_axis_unavailable_block` + stubs registers/keys/map/phrases |
| `ubuntu/serenedb/test_fork_outcomes.py` | monkeypatch `calendar_axis_map_ready` |
| `ubuntu/serenedb/test_calendar_meta_build.py` | **не** функции z04 — ключи meta `calendar_registers` / `calendar_working_day_keys` (сборка витрины) |

`test_period_bounds.py` зовёт `period_preds` (z03), тем самым косвенно `_working_day_doc_preds`, без прямого имени z04.

---

## Скрытые выбиратели, доступные новому тракту

Критерий: функция зоны, которая **кодом** выбирает day_basis / порядок прочтений / фильтр дат, и достижима из new z20.

| Что | Доступно new? | Роль |
|---|---|---|
| `day_basis_from_question` / `calendar_day_basis_needed` | **да** (через unavailable_block) | Скрытый разбор фраз/ticket/intent → id day_basis для гейта «карта пуста → no_data». Не выбирает SQL-лидера, но выбирает *какой* basis «нужен». |
| `calendar_axis_readings` / `expand_readings_calendar_axis` при `prefer=None` | **да** (z20:1887) | При открытой оси **размножает** оба прочтения (`calendar_days` + `working_days`), порядок по умолчанию calendar-first. New затем при `len>1` строит меню (`readings_menu`, O3 №8) — молчаливого лидера нет. Это не S-выбиратель «взять одно», а авто-раскрытие оси. |
| `_working_day_doc_preds` | **да** (через `_predicates`) | Не выбирает ось/меру: при уже выставленном `day_basis=working_days` добавляет SQL-фильтр рабочих дат из meta-карты. |
| `calendar_day_basis_prefer` | **нет** в new (только legacy + z09) | Классический скрытый лидер day_basis (ticket → intent → фразы → default calendar). В new не проводён (`prefer=None`). |
| `prefer_day_basis_leader` | **нет** (мёртва) | Выбирала бы reading-лидера по day_basis; prod не зовёт. |

**Вывод по выбирателям:** зона **не тащит в новый тракт** legacy-лидер `calendar_day_basis_prefer` / `prefer_day_basis_leader`. В new остаются: (1) фразовый детект для unavailable-гейта, (2) авто-раскрытие двух day-basis readings с меню при множественности, (3) рабочий SQL-фильтр после выбора/sole reading.

---

## Краткий ответ на «нужна ли одному пути»

**Да.** Без z04 новый тракт теряет и раскрытие calendar/working readings, и честный `no_data` при пустой карте, и предикат рабочих дней в `period_preds`. Снос после flip безопасен только для `calendar_day_basis_prefer` (22 строки) и уже мёртвых `prefer_day_basis_leader` + тела `_sql_ident` (14 строк) — не для зоны целиком.
