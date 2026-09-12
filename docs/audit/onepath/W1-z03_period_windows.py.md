# W1 — карта живости `ask/z03_period_windows.py`

Дата: 12.09.2026. Метод: AST top-level символы зоны + grep/AST Load по
`ask/*.py`, `z20_ask_main_http.py`, `z20_ask_main_http_legacy.py`,
`ubuntu/serenedb/test_*.py`. Импорт-структуры нет — только фактические имена
в общем namespace. getattr/f-строки с именами z03 в z20 не найдены.

Файл зоны: 615 строк. Сумма строк top-level символов: **539** (остальное —
импорты/`apply_bindings`, пустые строки, комментарии между символами).

## Итог зоны

| вердикт | символов | строк |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 42 | **471** |
| **ЖИВА ТОЛЬКО LEGACY** | 4 | **68** |
| **МЁРТВА** | 0 | 0 |
| всего символов | 46 | 539 |

**Вердикт зоны:** зона **нужна одному пути**. Прямые входы нового z20:
`repair_period_from_question`, `period_readings`, `_num_pred`,
`ASK_CURRENCY_AXIS`, `period_relative_forms` (+ health). После flip/сноса
legacy отмирают только лидер окна и подпись: `apply_period_leader`,
`prefer_window_leader`, `_WINDOW_LEADER_FORMS`, `render_window_label`
(68 строк).

Прямые z03 из **нового** z20: `ASK_CURRENCY_AXIS`, `_num_pred`,
`period_readings`, `period_relative_forms`, `repair_period_from_question`.

Прямые z03 из **legacy** z20: те же по смыслу плюс `apply_period_leader`,
`prefer_window_leader`, `period_form_from_question`, `render_window_label`,
`period_preds`, `ASK_ENTITY_FORM`, `ASK_SALES_RANK_CANON`, `_DAY_BASIS_WORKING`.

`_imports.py` / `_wire.py`: упоминаний символов z03 нет.
`_bootstrap.py`: только строки с `ASK_ENTITY_FORM` (патч F-гейта, не зов функции).

---

## Таблица символов

Пути сокращены: `ask/` = `ubuntu/serenedb/ask/`, тесты = `ubuntu/serenedb/test_*.py`.
«только self» = нет внешних упоминаний; живость тогда только через вызов
из другого символа той же зоны (см. цепочки).

| символ | вид | стр. | span | кто зовёт (файл:строка) | вердикт |
|---|---|---:|---|---|---|
| `_num_pred` | def | 19 | 9–27 | **new** `z20_ask_main_http.py:2099`; **legacy** `:3578,:3725`; зоны: комментарии `z01:836`, `z02:521`; тесты `test_intent.py:234,:333,:564` | ЖИВА НОВОМУ |
| `period_preds` | def | 17 | 30–46 | **legacy** `:3804,:3806`; **зоны** `z04b:235`, `z05:1150,:1215,:1216`, `z06_entity_search.py:17` (`_predicates`), `z09:340,:423`; тесты `test_period_bounds.py` | ЖИВА НОВОМУ (транз. new←`_predicates`) |
| `_ORIGIN_ASSUMED` | const | 1 | 50 | зоны `z05:531`; иначе self | ЖИВА НОВОМУ |
| `_ORIGIN_PRIOR` | const | 1 | 51 | только self | ЖИВА НОВОМУ |
| `_ORIGIN_EXPLICIT` | const | 1 | 52 | зоны `z05:828,:832,:835` | ЖИВА НОВОМУ |
| `_ORIGIN_NONE` | const | 1 | 53 | зоны `z04:214`, `z04b:210`, `z05:823,:836`, `z09:466` | ЖИВА НОВОМУ |
| `_WINDOW_FORM_IDS` | const | 4 | 54–57 | только self | ЖИВА НОВОМУ |
| `ASK_CALENDAR_AXIS` | const | 1 | 59 | зоны `z04_calendar_axis.py` (несколько); тесты `test_calendar_axis`, `test_fork_label_daybasis` | ЖИВА НОВОМУ |
| `ASK_CURRENCY_AXIS` | const | 1 | 60 | **new** `:1820,:1829`; **legacy** `:1811,:4376,:4384`; зоны `z04b`, `z09:352`; тесты `test_currency_axis` | ЖИВА НОВОМУ |
| `ASK_SALES_RANK_CANON` | const | 1 | 62 | **legacy** `:1800`; зоны `z11_sales.py:154`; тесты `test_sales_rank_canon.py:15` | ЖИВА НОВОМУ (внутри `period_readings`) |
| `ASK_ATOM_TERMINAL` | const | 1 | 64 | зоны `z13:413`, `z15:93`; тесты `test_atom_terminal` | ЖИВА НОВОМУ |
| `ASK_ENTITY_FORM` | const | 1 | 67 | **legacy** `:2860,:2862,:3744`; зоны `z05`, `z09`; **boot** `_bootstrap.py:111–153` (строки); тесты `test_entity_form`, `test_compare_sales`, … | ЖИВА НОВОМУ (←`sales_compare_windows`) |
| `_PERIOD_RELATIVE_FORMS` | const | 1 | 68 | тесты `test_period_relative_forms_ready.py:147,:161` | ЖИВА НОВОМУ |
| `_DAY_BASIS_CALENDAR` | const | 1 | 69 | зоны `z04`, `z09`; тест `test_calendar_axis.py:332` | ЖИВА НОВОМУ |
| `_DAY_BASIS_WORKING` | const | 1 | 70 | **legacy** `:1785,:1789`; зоны `z04`; тест `:333` | ЖИВА НОВОМУ |
| `_DAY_BASIS_IDS` | const | 1 | 71 | зоны `z04`, `z09`, `z13`, `z14:382` | ЖИВА НОВОМУ |
| `_DAY_BASIS_LEADER_DEFAULT` | const | 1 | 72 | зоны `z04`, `z13:109` | ЖИВА НОВОМУ |
| `_CALENDAR_REGS` | const | 1 | 73 | зоны `z04:17–26`; тест `test_calendar_axis.py:64` | ЖИВА НОВОМУ |
| `_CALENDAR_WORK_KEYS` | const | 1 | 74 | зоны `z04:33–43`; тест `:65` | ЖИВА НОВОМУ |
| `_CALENDAR_MAP` | const | 1 | 75 | зоны `z04:53–74`; тест `:66` | ЖИВА НОВОМУ |
| `_calendar_date` | def | 6 | 78–83 | зоны `z05` (много) | ЖИВА НОВОМУ |
| `_month_range` | def | 8 | 86–93 | зоны `z05:130,:229,:236,:281,:825` | ЖИВА НОВОМУ |
| `_quarter_range` | def | 10 | 96–105 | зоны `z05:829` | ЖИВА НОВОМУ |
| `_week_range_monday` | def | 5 | 108–112 | зоны `z05:230` | ЖИВА НОВОМУ |
| `_prev_week_range` | def | 9 | 115–123 | зоны `z05:231` | ЖИВА НОВОМУ |
| `_is_seven_day_span` | def | 5 | 126–130 | только self | ЖИВА НОВОМУ |
| `_is_current_calendar_week` | def | 8 | 133–140 | только self | ЖИВА НОВОМУ |
| `_assumed_sliding_week_not_calendar` | def | 11 | 143–153 | только self | ЖИВА НОВОМУ |
| `_iso_date` | def | 2 | 156–157 | зоны `z05` (много) | ЖИВА НОВОМУ |
| `_period_origin` | def | 12 | 160–171 | только self | ЖИВА НОВОМУ |
| `window_fp_of` | def | 18 | 174–191 | зоны `z09:354,:555,:568`; тесты calendar/currency/fork_* | ЖИВА НОВОМУ (←`_window_reading`) |
| `_period_form_id` | def | 25 | 194–218 | только self | ЖИВА НОВОМУ |
| `_window_reading` | def | 32 | 221–252 | зоны `z04:216`, `z04b:213`, `z05:823–836`; тесты calendar/currency | ЖИВА НОВОМУ |
| `period_readings` | def | 95 | 255–349 | **new** `:1885,:1898`; **legacy** diag `:1798`; зоны `z04:238` (док), `z09:409`; тесты `test_fork_window_readings` | ЖИВА НОВОМУ |
| `render_window_label` | def | 19 | 352–370 | **legacy** `:1887`; зоны `z05:850`, `z09:1002`, `z10:454`, `z13:205,:584` — **эти зоны недостижимы из new z20**; тесты `test_fork_window_readings` | ЖИВА ТОЛЬКО LEGACY |
| `_WINDOW_LEADER_FORMS` | const | 1 | 374 | зоны `z13:106` (функция недостижима из new) | ЖИВА ТОЛЬКО LEGACY |
| `prefer_window_leader` | def | 17 | 377–393 | **legacy** `:1805`; тесты `test_fork_window_readings`, запрет-имя в `test_one_path.py:217` | ЖИВА ТОЛЬКО LEGACY |
| `period_relative_forms` | def | 29 | 396–424 | **new** `:731` + health keys; **legacy** аналогично; тесты `test_period_relative_forms_ready`, `test_etalon_1c`, … | ЖИВА НОВОМУ |
| `period_form_from_question` | def | 11 | 427–437 | **legacy** `:1801`; зоны `z10:436` (не из new); тесты `test_period_relative_forms_ready.py:170` | ЖИВА НОВОМУ (←`repair_period_from_question`) |
| `_MONTH_DAY_RANGE_RE` | const | 2 | 441–442 | только self | ЖИВА НОВОМУ |
| `month_day_range_from_question` | def | 28 | 445–472 | тесты `test_period_bounds.py:41`, `test_ab_calendar_axis_set.py:98` | ЖИВА НОВОМУ |
| `_apply_period_form_window` | def | 36 | 475–510 | только self | ЖИВА НОВОМУ |
| `_strip_period_assumed` | def | 11 | 513–523 | только self | ЖИВА НОВОМУ |
| `_clear_month_day_parse_noise` | def | 23 | 526–548 | только self | ЖИВА НОВОМУ |
| `repair_period_from_question` | def | 28 | 551–578 | **new** `:1883`; тесты `test_period_bounds.py:54` | ЖИВА НОВОМУ |
| `apply_period_leader` | def | 31 | 581–611 | **legacy** `:1777`; тесты `test_fork_window_readings`; запрет-имя `test_one_path.py:217` | ЖИВА ТОЛЬКО LEGACY |

---

## Транзитивные цепочки (до корня z20)

Формат: `символ ← … ← z20` (или прямой `z20 →`).

### Новый z20 (`z20_ask_main_http.py`)

**Прямые**

- `_num_pred` ← z20:2099
- `ASK_CURRENCY_AXIS` ← z20:1820,1829
- `period_readings` ← z20:1885 (diag:1898)
- `repair_period_from_question` ← z20:1883
- `period_relative_forms` ← z20:731 (`_health_period_relative_forms`) + ключи /health

**Через repair / readings (ядро периода)**

- `month_day_range_from_question` ← `repair_period_from_question` ← z20
- `_MONTH_DAY_RANGE_RE` ← `month_day_range_from_question` ← …
- `period_form_from_question` ← `repair_period_from_question` ← z20
- `_apply_period_form_window` ← `repair_period_from_question` ← z20
- `_strip_period_assumed` ← `repair_period_from_question` ← z20
- `_clear_month_day_parse_noise` ← `repair_period_from_question` ← z20
- `_calendar_date` ← `repair_period_from_question` / `period_readings` ← z20
- `_quarter_range` ← `_apply_period_form_window` ← …
- `_window_reading` ← `period_readings` ← z20
- `window_fp_of` ← `_window_reading` ← …
- `_period_form_id` ← `period_readings` ← z20
- `_period_origin` ← `period_readings` ← z20
- `_ORIGIN_*`, `_WINDOW_FORM_IDS` ← `period_readings` / `_period_origin` ← z20
- `_assumed_sliding_week_not_calendar` ← `period_readings` ← z20
- `_is_seven_day_span`, `_is_current_calendar_week` ← `_assumed_sliding_week_not_calendar` ← …
- `_month_range`, `_week_range_monday`, `_prev_week_range`, `_iso_date` ← `period_readings` (и также ← `sales_compare_windows`) ← z20
- `ASK_SALES_RANK_CANON` ← `period_readings` ← z20
- `_PERIOD_RELATIVE_FORMS` ← `period_relative_forms` ← z20

**Через другие зоны, которые зовёт new**

- `period_preds` ← `_predicates` (`z06`) ← z20
- `ASK_CALENDAR_AXIS`, `_DAY_BASIS_*`, `_CALENDAR_*` ← `expand_readings_calendar_axis` / `calendar_axis_*` (`z04`) ← z20:1887
- `ASK_ATOM_TERMINAL` ← `answer_slot_mode` (`z15`) ← z20
- `ASK_ENTITY_FORM` ← `sales_compare_windows` (`z05`) ← z20
- хелперы дат `_calendar_date` / `_iso_date` / `_month_range` / `_week_range_monday` / `_prev_week_range` также ← `sales_compare_windows` ← z20
- `_window_reading` также ← `_day_basis_reading` / `_amount_basis_reading` при expand calendar/currency ← z20

### Только legacy z20

- `apply_period_leader` ← legacy:1777
- `prefer_window_leader` ← legacy:1805 (и внутри `apply_period_leader`)
- `_WINDOW_LEADER_FORMS` ← `prefer_window_leader` ← legacy
- `render_window_label` ← legacy:1887  
  (внешние зоны `z05/z09/z10/z13` зовут её, но **цепочки до new z20 нет**)

---

## Скрытые выбиратели, доступные новому тракту

Критерий: функция зоны, которая **кодом** выбирает период/форму окна
(не человек, не вики-меню) и при этом достижима из new z20.

| символ | что делает | в new? | оценка |
|---|---|---|---|
| `repair_period_from_question` | до меню пишет `intent["period"]` из разбора вопроса | да, прямо | **скрытый выбиратель периода** (оркестратор) |
| `period_form_from_question` | первое совпадение фразы → `form_id` из словаря | да, через repair | **скрытый выбиратель формы периода** |
| `_apply_period_form_window` | по `form_id` подставляет конкретное окно | да, через repair | исполнитель выбора |
| `month_day_range_from_question` | парсит «с N по M» → одно окно | да, через repair | скорее парсер, чем выбор из альтернатив |
| `period_readings` | раскрывает MTD/full / WTD/full (+ люк sliding, + prev_week при флаге) | да, прямо | **не** молчаливый лидер: список для меню; но при assumed sliding **молча сдвигает** локальное окно на календарную неделю до раскрытия |
| `prefer_window_leader` / `apply_period_leader` | выбирают одно окно-лидер и пишут в intent | **нет** (только legacy) | в new не тащатся — совпадает с O3 №8 |
| `ASK_*` флаги | включают оси/каноны | да (транз./прямо) | гейты фич, не выбор прочтения |

**Итог по выбирателям:** в новый тракт из z03 **протаскивается** связка
`repair_period_from_question` → `period_form_from_question` +
`_apply_period_form_window` (молчаливая подстановка периода из словаря
фраз **до** меню). Лидер `prefer_window_leader` / `apply_period_leader`
новому **не** доступен. `period_readings` отдаёт список прочтений (нужен
меню), с оговоркой про silent rewrite assumed sliding→calendar week.

---

## Замки (тесты), задевающие зону

| тест | что трогает из z03 |
|---|---|
| `test_intent.py` | `_num_pred` |
| `test_period_bounds.py` | `period_preds`, `month_day_range_from_question`, `repair_period_from_question` |
| `test_fork_window_readings.py` | `period_readings`, `window_fp_of`, `render_window_label`, `prefer_window_leader`, `apply_period_leader`, `period_relative_forms` |
| `test_period_relative_forms_ready.py` | `period_relative_forms`, `_PERIOD_RELATIVE_FORMS`, `period_form_from_question` (поиск в src) |
| `test_calendar_axis.py` / `test_fork_label_daybasis.py` | `ASK_CALENDAR_AXIS`, `_CALENDAR_*`, `_DAY_BASIS_*`, `_window_reading`, `window_fp_of` |
| `test_currency_axis.py` | `ASK_CURRENCY_AXIS`, `_window_reading`, `window_fp_of` |
| `test_atom_terminal.py` | `ASK_ATOM_TERMINAL` |
| `test_entity_form.py` / `test_compare_sales.py` / `test_fork_detector.py` | `ASK_ENTITY_FORM` |
| `test_sales_rank_canon.py` | `ASK_SALES_RANK_CANON` |
| `test_one_path.py:217` | имена `apply_period_leader`, `prefer_window_leader` как запрещённые для onepath |
| `test_etalon_1c.py` | `period_relative_forms` |
| `test_ab_calendar_axis_set.py` | `month_day_range_from_question` |

---

## Метод / границы

- Живость «НОВОМУ» = AST `Load` имени из new z20 **или** достижимость по
  графу вызовов top-level def зон (Name Load в теле).
- Упоминание в зоне, чья функция **не** достижима из new, не делает символ
  живым новому (`render_window_label` и др.).
- Комментарии (`z01`/`z02` про `_num_pred`) учтены как упоминания, не как зов.
- Код не менялся; чужие отчёты onepath не читались.
