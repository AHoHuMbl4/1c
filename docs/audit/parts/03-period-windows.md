# 03. period-windows

Источник: `ubuntu/serenedb/serene_ask.py:1374–1808`.

## Зачем участок нужен

Строит SQL-предикаты по `doc_date` из словаря периода (`period_preds`). Раскрывает одно окно дат в конечный список прочтений W по форме границ относительно `today` (`period_readings` / `_period_form_id`). Выбирает лидера среди прочтений и записывает его в `intent["period"]` (`prefer_window_leader` / `apply_period_leader`). Склеивает машинный отпечаток окна `from|to|origin[|day_basis]` (`window_fp_of`).

Рядом в том же диапазоне: `_num_pred` — предикаты по числу из `intent["amount"]` к `map_extract(nums, measure)`, не к дате (`:1374–1392`).

## Входы

| Что | Где читается |
|---|---|
| `period`: `from`, `to`, опц. `origin`, `day_basis`, `interpretation_id` | `period_preds`, `window_fp_of`, `_window_reading`, `period_readings` |
| `intent["period"]`, `intent["parse"]["assumed"]` | `_period_origin`, `period_readings`, `apply_period_leader` |
| `period_from_prior: bool` | `_period_origin`, `period_readings`, `apply_period_leader` |
| `today: str` ISO (умолч. `time.strftime("%Y-%m-%d")`) | `period_readings:1601–1602`, `apply_period_leader` |
| `question: str` | `apply_period_leader` → `period_form_from_question` |
| `prefer_form` | `prefer_window_leader` |
| `intent["amount"]` + `measure` | `_num_pred` |
| env: `ASK_CALENDAR_AXIS`, `ASK_SALES_RANK_CANON`, `ASK_ATOM_TERMINAL`, `ASK_ENTITY_FORM` | `:1424–1431` |
| `search_meta.k='period_relative_forms'` или файл `period_relative_forms.json` рядом с модулем | `period_relative_forms:1735–1754` |

## Порядок работы

1. **`period_preds(period)`** (`:1395–1411`): если есть `from` → `doc_date >= lit(from)`; если есть `to` → `doc_date < (lit(to)::date + INTERVAL 1 day)`; затем `out.extend(_working_day_doc_preds(p))` (тело вне участка, `:1964+`).
2. **`_period_origin(intent, period_from_prior)`** (`:1512–1523`): `prior` → `prior`; иначе любой `assumed` с префиксом `period.` → `assumed`; иначе есть `from`/`to` → `explicit`; иначе `none`.
3. **`_period_form_id(period, today)`** (`:1540–1564`): сравнение `from`/`to` с границами месяца/недели от `today` → `mtd` / `full_month` / `wtd` / `full_week`; при `ASK_SALES_RANK_CANON` ещё `prev_week`; иначе `explicit` или `none`.
4. **`period_readings(...)`** (`:1592–1680`):
   - нет валидного `today` → одно reading `none`;
   - нет `from` и `to` → `none`; при origin `assumed` добавляет `drop_assumed`;
   - битые даты → одно `explicit`;
   - origin `assumed` + скользящие 7 дней (конец сегодня/вчера, не календарная неделя) → подмена границ на пн–вс текущей недели, исходное окно в `sliding_hatch`;
   - по `fid`: разворачивает пару mtd/full_month или wtd/full_week (если `to` уже конец месяца/недели — только full); `prev_week`; иначе одно `explicit`;
   - если был hatch — добавляет исходное окно как `explicit`;
   - при `ASK_SALES_RANK_CANON` и наличии wtd/full_week без prev_week — добавляет `prev_week`;
   - дедуп по `window_fp` (`_add`).
5. **`apply_period_leader(...)`** (`:1772–1808`): при `ASK_SALES_RANK_CANON` может выставить `prefer_form` из словаря/`interpretation_id==prev_week` и переписать `intent["period"]` на prev_week; зовёт `period_readings`; `prefer_window_leader`; пишет лидера в `intent["period"]` (если есть from/to или id ∈ {`none`,`drop_assumed`}); возвращает список readings.
6. **`prefer_window_leader`**: сначала `prefer_form` по `interpretation_id`, иначе первый из (`mtd`,`wtd`), иначе `readings[0]`.
7. **`render_window_label`**: подпись из `_period_day_label` + id формы + origin (`assumed`/`prior`).

## Выходы

| Функция | Что отдаёт | Кто зовёт (в этом файле) |
|---|---|---|
| `period_preds` | `list[str]` SQL-фрагментов WHERE | `_predicates:2605`, `entity_form_compute:2514`, `aggregate_compare_sales:2574–2575`, `fork_scan_readings:4203`, `fork_detector_scan:4273`, др. |
| `window_fp_of` | строка отпечатка | `_window_reading:1584`, `fork_scan_readings:4215`, др. |
| `period_readings` | `list[dict]`: `period`, `origin`, `window_fp`, `interpretation_id`, опц. `day_basis` | `apply_period_leader:1796`, `fork_detector_scan:4265` |
| `prefer_window_leader` | один reading или `None` | `apply_period_leader:1797`, основной путь `:11884` |
| `apply_period_leader` | список readings; мутирует `intent["period"]` | основной ask-путь `:11859–11860` → дальше `expand_readings_calendar_axis`, `_predicates` |
| `render_window_label` | `str` или `None` | вне участка (потребители по имени) |
| `_num_pred` | `list[str]` предикатов по nums | вне участка |

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| `period_relative_forms:1735` | `psql("SELECT v FROM search_meta WHERE k = 'period_relative_forms' LIMIT 1")` | словарь form_id → фразы |
| `period_relative_forms:1746–1752` | чтение `ubuntu/serenedb/period_relative_forms.json` | запас, если meta пуста/ошибка |
| такт `build.sh` шаг **1-period** + `period_relative_forms_load.sql` | `read_text` JSON → `INSERT search_meta` (вне SKIP корпуса) | наполнение ключа каждый такт |
| `/health` → `_health_period_relative_forms` | `{loaded, forms}`; пустой → 503 degraded | нехватка словаря видна, не молчит |
| `period_preds` | SQL **не исполняет**; только строки предикатов | исполнение у вызывающих через `psql`/aggregate/fork_scan |
| HTTP | `/health` (см. выше); ask-путь периода — нет | — |
| вызов ЯМ | нет | — |

Кэш словаря: `_PERIOD_RELATIVE_FORMS`, TTL **300** с (`:1729–1732`, `:1755`).

`period_preds` дописывает результат `_working_day_doc_preds` (вне участка); там при `ASK_CALENDAR_AXIS` и `day_basis=working_days` строится `IN (UNION query_table…)` — исполнение тоже у вызывающего.

## Переключатели

| Имя | Чтение | Умолч. | Эффект в участке |
|---|---|---|---|
| `ASK_SALES_RANK_CANON` | `:1426` (`=="1"`) | `"0"` | `_period_form_id` → `prev_week`; `period_readings` добавляет prev_week к неделе; `apply_period_leader` — словарь/перепись period на prev_week |
| `ASK_CALENDAR_AXIS` | `:1424` | `"0"` | в этом диапазоне только объявление; влияет через `_working_day_doc_preds` из `period_preds` |
| `ASK_ATOM_TERMINAL` | `:1428` | `"0"` | объявление; в функциях участка не читается |
| `ASK_ENTITY_FORM` | `:1431` | `"0"` | объявление; в функциях участка не читается |

## Развилки

- Нет `from`/`to` → reading `none`; +`drop_assumed` только при origin `assumed` (`:1611–1615`).
- `assumed` + 7 дней скользящих ≠ календарная неделя → лидер календарная неделя + люк explicit (`:1628–1633`, `:1669–1670`).
- `mtd`/`wtd` при `to ==` конец месяца/недели → только `full_*` (`:1649–1650`, `:1657–1658`).
- `prefer_form` (словарь/prev_week) побеждает дефолт mtd/wtd (`:1716–1719`).
- `apply_period_leader`: лидер `None` → readings без записи в intent (`:1798–1799`); иначе запись period при from/to или id `none`/`drop_assumed` (`:1805–1807`).
- `_num_pred`: пустой список, если нет `op`/`value`/`measure`; `between` требует `value2`; неизвестный `op` → `[]` (`:1383–1392`).

## Чего здесь нет

- Разбора русской лексики периода в `period_readings` / `_period_form_id` (только границы и словарь relative в `period_form_from_question`).
- Исполнения SQL агрегатов/поиска, HTTP, вызова модели.
- Раскрытия `period2` / compare двух окон.
- Раскрытия day-basis calendar/working в readings (только поле в fp/`_window_reading`; expand — вне участка).
- Использования `ASK_ATOM_TERMINAL` / `ASK_ENTITY_FORM` внутри функций этого диапазона строк.
- Записи в БД; только чтение `search_meta` / JSON для relative forms.
