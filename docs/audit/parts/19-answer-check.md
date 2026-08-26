# 19. answer-check

Участок: `ubuntu/serenedb/serene_ask.py:9696–10130`. Источник — только этот диапазон (+ константы `NUMTOK`/`SEP`/`DATE3`/`DATE2` на `:9690–9693`, на которые участок ссылается).

## Зачем участок нужен

Набор чистых функций разбора и проверки текста ответа: извлечь числа/даты из строки, сверить заявленные роли (`claims`) с агрегатами базы, убедиться что запрошенная величина написана цифрами, поймать дословную утечку системной инструкции, приписать пометку о старении, собрать разрешённые числа/даты из условий отбора, снять маркеры нумерации списка. Вызовов наружу нет.

## Входы

| Функция | Аргументы |
|---|---|
| `_readings` | `tok` — строка числового токена |
| `_plausible` | `d`, `mo` — день и месяц |
| `_dates` / `_date_spans` / `_tokens` / `_norm_numbers` | `text` |
| `_date2_readings` | `text`, `d`, `mo` |
| `check_claims` | `claims` (dict), `agg` (dict), `totals=None` (итерируемое кортежей) |
| `claims_in_text` | `claims`, `text`, `want=None` (`"sum"`/`"count"`/иное) |
| `prompt_leak` | `text`, `prompts` (итерируемое строк), `min_len=40` |
| `asked_figure_missing` | `text`, `agg`, `want`, `has_measure`, `folders=0` |
| `stale_note` | `out` (dict), `age`, `warn_sec`, `text_fmt` (шаблон `%`) |
| `_threshold_values` / `_filter_values` / `_filter_dates` | `intent` (dict) |
| `without_list_markers` | `text` |
| `rows_seen` | `rows` — в диапазоне только сигнатура и docstring (`:10122–10130`); тело с `:10135` |

Переменных окружения участок не читает. Константа модуля: `ROLE_TOL = 0.01` (`:9852`). Регексы: `NUMTOK`, `SEP`, `DATE3`, `DATE2` (`:9690–9693`); `LIST_MARKER`, `INLINE_MARKER` (`:10097–10102`). Внешние символы, вызываемые отсюда: `_fmt` (`:445`), `_group_leader` (`:8706`).

## Порядок работы

1. **`_readings(tok)`** (`:9696–9736`): вычистить цифры; если группировка валидна (1 группа или первая 1–3 цифры и далее по 3) — добавить `float` целого; иначе последний разделитель трактовать как десятичный (при валидной целой части). Дополнить целыми `float(int(v))` для целых значений.
2. **`_plausible` → `_dates` / `_date_spans`** (`:9739–9808`): даты `DATE3`/`DATE2` только при `1≤d≤31`, `1≤mo≤12`; `DATE2` не пересекающиеся с уже найденными `DATE3`.
3. **`_tokens` → `_norm_numbers`** (`:9811–9849`): затереть span’ы дат пробелами; по `NUMTOK` собрать множества `_readings`; при пустом whole — по группам-перечислениям; объединить во множество.
4. **`check_claims`** (`:9855–9888`): при пустом `agg` или не-dict `claims` → `(True, [])`. Для ролей `total`/`count`/`max`/`min`: пропуск `None`; нечисло → `"role=?"`; для `total`/`max`/`min` при `totals` — совпадение с `t[1]`/`t[2]`/`t[3]` в `ROLE_TOL` снимает роль; иначе сверка с `agg["sum"|"count"|"max"|"min"]`. Возврат `(not bad, bad)`.
5. **`claims_in_text`** (`:9894–9933`): не-dict → `(True, [])`. `need = ASKED_ROLE.get(want)` (`sum→total`, `count→count`, `:9891`). Если `need is None` — каждый role пропускается (`continue`). Иначе проверяется только `role == need`: float из claims должен быть в `_norm_numbers(text)` (или `round(fv,2)`).
6. **`prompt_leak`** (`:9936–9955`): нормализовать пробелы `text`; по строкам каждого `p` из `prompts` — если `len(line)≥min_len` и `line in t` → `line[:60]`; иначе `None`.
7. **`asked_figure_missing`** (`:9958–10032`): без `agg` → `None`. Собрать `needs`: при `want=="count"` — `agg.count`; при `want=="sum"` и `has_measure` — `agg.sum`; при `grain=="group"` и `has_measure` — лидер `_group_leader(agg)` и при отличии — `sum`. Любое `need` не в `_norm_numbers(text)` → строка отказа. Затем при `folders` — число папок в тексте; при `grain=="group"` и `n_groups > len(groups)` — `n_groups` в тексте. Иначе `None`.
8. **`stale_note`** (`:10035–10050`): если не dict / `age is None` / `age≤warn_sec` / `kind` не в `{answer,figures,clarify,no_data}` — вернуть `out` как есть; иначе дописать `text_fmt % (age//60)` к `text`, поставить `stale=True`.
9. **`_threshold_values` / `_filter_values` / `_filter_dates`** (`:10053–10094`): пороги `intent.amount.value|value2`; плюс числа из `intent.terms`; строки `period`/`period2` `from`/`to`.
10. **`without_list_markers`** (`:10105–10119`): `LIST_MARKER` затем `INLINE_MARKER` вырезать из текста.

## Выходы

| Функция | Возврат |
|---|---|
| `_readings` / `_norm_numbers` | `set` float |
| `_tokens` | `list[set]` |
| `_dates` | `list[(d,mo,y\|None)]` |
| `_date_spans` | `list[(start,end)]` |
| `check_claims` / `claims_in_text` | `(ok: bool, bad: list[str])` |
| `prompt_leak` | `str\|None` (до 60 символов) |
| `asked_figure_missing` | `str` причина \| `None` |
| `stale_note` | тот же `out` (возможно мутированный) |
| `_filter_values` / `_threshold_values` | `list` чисел |
| `_filter_dates` | `list[str]` |
| `without_list_markers` | `str` |

В участке нет вызывающего кода; кто потребляет возвраты — в диапазоне `:9696–10130` не видно.

## Обращения наружу

Нет. SQL, HTTP, вызовов языковой модели в участке нет.

## Переключатели

| Имя | Место | По умолчанию |
|---|---|---|
| `ROLE_TOL` | `:9852` | `0.01` |
| `min_len` у `prompt_leak` | `:9936` | `40` |
| `folders` у `asked_figure_missing` | `:9958` | `0` |
| `totals` у `check_claims` | `:9855` | `None` |
| `want` у `claims_in_text` | `:9894` | `None` |

Переменных окружения нет. `ASKED_ROLE = {"sum":"total","count":"count"}` (`:9891`).

## Развилки

- `_readings`: группировка ок → только целое; иначе ещё десятичное прочтение (`:9708–9735`).
- `check_claims`: ранний `(True,[])`; роль через `totals` vs через `agg` (`:9882–9887`).
- `claims_in_text`: при `want` не из `ASKED_ROLE` все роли пропускаются → `(True,[])` (`:9925–9926`).
- `asked_figure_missing`: ветки `want`/`grain`/`has_measure`/`folders`/`n_groups` задают разные `needs` и причины (`:9986–10031`).
- `stale_note`: по `age`, `kind` — приписка или без изменений (`:10044–10047`).
- `prompt_leak`: совпадение длинной строки → обрезка 60 символов; иначе `None`.

## Чего здесь нет

- **`copied_figures`** — нет в диапазоне; определение на `:9340` (вне участка).
- Тела **`rows_seen`** — объявление/docstring до `:10130`, исполняемый код с `:10135`.
- SQL / HTTP / LLM.
- Чтение env.
- Вызовов `gate` / `check_roles` (упоминаются только в docstring `claims_in_text`).
- Списка числительных / языковой морфологии.
- Сборки ответа клиенту, второй попытки модели, структуры `figures` (описаны в docstring, кода нет).
- Самих констант `OUR_PROMPTS`, `STALE_WARN_SEC`, `ROWS_TO_MODEL` (в участке не читаются).
