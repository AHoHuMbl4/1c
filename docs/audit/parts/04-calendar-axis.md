# 04. calendar-axis

Источник: `ubuntu/serenedb/serene_ask.py:1811–1994`. Константы/флаг участка объявлены выше: `1424`, `1433–1439`.

## Зачем участок нужен

Участок держит day-basis окна периода: читает метаданные календаря из SereneDB, решает, открыта ли календарная ось, размножает одно period-reading на два (`calendar_days` / `working_days`) и для `working_days` строит SQL-предикат «`doc_date` ∈ рабочих дат из карты». Без оси список readings и предикаты периода не меняются.

## Входы

| Что | Где в участке | Смысл по коду |
|---|---|---|
| `ASK_CALENDAR_AXIS` | `1882`, `1939`, `1970` | bool модуля; env вне участка: `os.environ.get("ASK_CALENDAR_AXIS", "0") == "1"` (`1424`) |
| `base_reading` / `readings` | `1918+`, `1936+`, `1951+` | dict(s) с `period` (`from`/`to`/`origin`/`interpretation_id`/`day_basis`), опц. top-level `origin`, `interpretation_id`, `day_basis` |
| `prefer` | `1918`, `1936`, `1951` | строка day-basis; вне `_DAY_BASIS_IDS` → `"calendar_days"` |
| `intent`, `trusted` | `1888` | dict; `day_basis`; у `trusted` ещё `src`/`label`; у `intent` ещё `period.day_basis` |
| `period` | `1964` | dict: `day_basis`, `from`, `to` |
| кэши `_CALENDAR_*` | `1819–1821`, `1835–1837`, `1855–1857` | TTL 300 с; объявлены `1437–1439` |
| `_DAY_BASIS_*` | по участку | `"calendar_days"`, `"working_days"`; лидер по умолчанию = calendar (`1433–1436`) |

Env внутри `1811–1994` не читаются (только уже вычисленный `ASK_CALENDAR_AXIS`).

## Порядок работы

1. **`_sql_ident(name)`** (`1811–1813`) — `"…"` с экранированием `"`.
2. **`calendar_registers()`** (`1816–1829`) — кэш &lt;300 с → `_CALENDAR_REGS["set"]`; иначе `psql` `search_meta.k='calendar_registers'`, split `,`, `frozenset`; `RuntimeError` → пустой набор; обновляет кэш.
3. **`calendar_working_day_keys()`** (`1832–1846`) — то же для `k='calendar_working_day_keys'`.
4. **`calendar_map_rows()`** (`1849–1877`) — кэш / `SELECT src_table, date_col, day_key_col, hours_col FROM search_calendar_map`; нет таблицы (по тексту ошибки) → `[]`; иной `RuntimeError` — re-raise; строки без `src`/`date`/`day_key` отброшены; пустой `hours_col` → `""`.
5. **`calendar_axis_open()`** (`1880–1885`) — `False` при флаге off или пустых registers **или** keys **или** map; иначе `True`.
6. **`calendar_day_basis_prefer(intent, trusted)`** (`1888–1906`) — первый валидный id: `trusted.day_basis` → `trusted.{day_basis,src,label}` → `intent.day_basis` → `intent.period.day_basis` → `_DAY_BASIS_LEADER_DEFAULT`.
7. **`_day_basis_reading(base_rd, day_basis)`** (`1909–1915`) — `period`/`origin`/`interpretation_id` из base → `_window_reading(..., day_basis=)` (вне участка, `1567`).
8. **`calendar_axis_readings(base_reading, prefer)`** (`1918–1933`) — `[]` если ось закрыта или нет `period.from` и `period.to`; иначе два reading: calendar→working, или working→calendar при `prefer == working_days`.
9. **`expand_readings_calendar_axis(readings, prefer)`** (`1936–1948`) — флаг off / ось закрыта → исходный список; иначе для каждого rd: непустой `calendar_axis_readings` → оба, иначе rd как есть.
10. **`prefer_day_basis_leader(readings, prefer)`** (`1951–1961`) — первое reading с `day_basis`/`period.day_basis == prefer`, иначе `readings[0]`; пусто → `None`.
11. **`_working_day_doc_preds(period)`** (`1964–1992`) — `[]` при флаге off, `day_basis != working_days`, нет keys/map/`from`/`to`; иначе `UNION` DISTINCT дат из `query_table(src)` по ключам и окну → один предикат `try_cast(doc_date AS DATE) IN (<union>)`. `hours_col` в SQL не входит (`_hours`, `1979`).

## Выходы

| Функция | Возврат | Кто зовёт (вне участка) |
|---|---|---|
| `calendar_registers` / `calendar_working_day_keys` / `calendar_map_rows` | `frozenset` / `list` кортежей | внутри оси; map/keys ещё из `_working_day_doc_preds` |
| `calendar_axis_open` | `bool` | `ask` (`11864`), `calendar_axis_readings`, `expand_readings_calendar_axis` |
| `calendar_day_basis_prefer` | `"calendar_days"` \| `"working_days"` | `fork_detector_scan` (`4268`), `ask` (`11861`) |
| `calendar_axis_readings` | `list` 0..2 reading | только `expand_readings_calendar_axis` |
| `expand_readings_calendar_axis` | `list` readings | `fork_detector_scan` (`4269`), `ask` (`11862`) |
| `prefer_day_basis_leader` | reading \| `None` | в `serene_ask.py` вызовов нет; есть в `test_calendar_axis.py` |
| `_working_day_doc_preds` | `list[str]` SQL-фрагментов | `period_preds` (`1410`) |

Содержимое `calendar_registers` в SQL участка не подставляется — только непустота в `calendar_axis_open`.

## Обращения наружу

HTTP и вызовов языковой модели нет.

| Место | Вызов | Назначение |
|---|---|---|
| `1823` | `psql(... search_meta ... 'calendar_registers')` | CSV регистров |
| `1839–1840` | `psql(... 'calendar_working_day_keys')` | CSV Ref_Key рабочих дней |
| `1859–1861` | `psql(... FROM search_calendar_map)` | карта источников |
| `1981–1988` | текст SQL (`query_table`, `try_cast`, `UNION`), не `psql` | даты working-basis для предиката |
| `1915` | `_window_reading(...)` | сборка reading (не I/O) |
| `1978` | `lit(...)` | литералы SQL |

## Переключатели

| Имя | Чтение в участке | По умолчанию |
|---|---|---|
| `ASK_CALENDAR_AXIS` | `1882`, `1939`, `1970` | env `"0"` → False (`1424`, вне участка) |
| TTL кэша 300 с | `1820`, `1836`, `1856` | литерал `300` |
| `_DAY_BASIS_LEADER_DEFAULT` | `1906`, `1929`, `1956` | `"calendar_days"` (`1436`) |

Других env/флагов участок не читает.

## Развилки

- Кэш meta/map свежий → без SQL (`1819–1821`, `1835–1837`, `1855–1857`).
- `psql` meta → `RuntimeError` → пустой набор (`1824–1825`, `1841–1842`).
- Нет `search_calendar_map` (по тексту ошибки) → `[]`; иначе re-raise (`1862–1869`).
- `ASK_CALENDAR_AXIS` False → ось закрыта / expand без изменений / preds без working-фильтра.
- Пустые registers **или** keys **или** map → `calendar_axis_open` False.
- Нет `from`+`to` → `calendar_axis_readings` → `[]`; expand оставляет исходный rd (`1944–1947`).
- `prefer == working_days` → порядок working→calendar (`1931–1932`).
- `_working_day_doc_preds` только при `day_basis == working_days` и полных keys/map/from/to; иначе `[]`.

## Чего здесь нет

- Записи в БД, HTTP, LLM.
- Разбора фраз вопроса (docstring `1889`: «Без phrase-list»).
- Использования `hours_col` в предикатах (читается, в SQL не идёт).
- Подстановки `calendar_registers` в SQL (только bool-непустота).
- Вызова `prefer_day_basis_leader` из прод-кода `serene_ask.py`.
- Расчёта «сегодня» / MTD / WTD — только day-basis поверх готового окна.
