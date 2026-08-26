# 15. answer-atoms

Участок: `ubuntu/serenedb/serene_ask.py:7369–7740`.

## Зачем участок нужен

Собирает режим числовых слотов ответа и словарь плейсхолдеров из уже посчитанного `agg`. Собирает типизированный `AnswerAtom`, рендерит его в одну строку «подпись + число + единица + оговорки» и подставляет `{pair:pN}` в текст. Даёт белые списки подписей/чисел из атомов и отпечаток `figures` кандидата для арбитра.

## Входы

| Функция | Аргументы (как в сигнатуре) |
|---|---|
| `answer_money` | `want`, `compute`, `measure` — :7369 |
| `answer_slot_mode` | `want`, `compute`, `form=None`, `grain=None` — :7381 |
| `compose_slot_values` | `agg`, `measure=None`, `folders=0`, `money=None`, `slot_mode=None` — :7410 |
| `atom_operation` | `want`, `compute`, `form`, `grain`, `slot_mode` — :7496 |
| `build_answer_atom` | `operation`, `exact_value`, `display_value`, `measure_id`, `measure_label`, `unit_or_currency`, `period`, `filters`, `grain`, `axis`, `form`, `completeness`, `freshness`, `excluded`, `proof_status`, `interpretation_id`, `src` — :7535–7540 |
| `atom_from_agg` | `agg` + те же метки/поля, плюс `money=True`, `period_origin=""`, `folders=0` — :7581–7586 |
| `render_atom_pair` | `atom` (dict) — :7625 |
| `fill_atom_pairs` | `text`, `pairs` (каталог атомов) — :7666 |
| `pair_slots_only` | `n_pairs` — :7698 |
| `atom_whitelist_labels` / `atom_whitelist_numbers` | `atoms` — :7703, :7715 |
| `arbiter_figures` | `sub` с полем `figures` — :7734 |

Переменные окружения участок сам не читает; использует уже загруженные `ASK_ATOM_TERMINAL` (:7400) и `ROWS_TO_MODEL` (:7449).

## Порядок работы

1. `answer_money(want, compute, measure)` → `True`, если `measure` истинен и нет режима счёта (`compute`/`want` == `"count"`) — :7369–7378.
2. `answer_slot_mode(...)` выбирает строку режима: `count` / `compare` / `rank` / `sum` / `list` — :7381–7407 (условия — в «Развилки»).
3. `compose_slot_values(agg, ...)` строит dict слотов для плейсхолдеров compose — :7410–7481: при пустом `agg` — `{}`; иначе по `slot_mode` копирует поля из `agg` (`count`, `sum`, `g0…`, `leader`, даты, `folders`, …).
4. `atom_operation(...)` мапит `slot_mode`/`compute` в одну из `_ATOM_OPS` — :7496–7510.
5. `_atom_exact_value(agg, operation, money)` выбирает одно числовое значение под операцию — :7513–7532.
6. `atom_from_agg` → считает `exact`, дописывает `excluded` (folders/undated/outside_period), собирает `period`, зовёт `build_answer_atom` — :7581–7622.
7. `build_answer_atom` нормализует `operation` (неизв. → `"count"`), ставит `proof_status`, при отсутствии `display_value` зовёт `_fmt(exact_value)`, возвращает dict атома — :7535–7578.
8. `render_atom_pair(atom)` склеивает одну строку пары или `None` — :7625–7663.
9. `fill_atom_pairs(text, pairs)` через `SLOT.sub` заменяет только роль `pair`; индекс `pN` или число; битые места копятся в `bad` — :7666–7695.
10. `pair_slots_only(n)` → `True` при `n > 1` — :7698–7700.
11. `atom_whitelist_labels` / `atom_whitelist_numbers` собирают списки из атомов — :7703–7731.
12. `arbiter_figures(sub)` копирует `sub["figures"]`, выкидывает `in_1c`/`in_search`/`missing`/`_totals` — :7734–7740.

## Выходы

| Выход | Тип | Кто зовёт в том же файле |
|---|---|---|
| `answer_money` → bool | флаг денег | путь ответа ~:14522, :11289 |
| `answer_slot_mode` → str | режим слотов | ~:14525 |
| `compose_slot_values` → dict | плейсхолдеры цифр | ~:11403, :14592, :14790, :14863, :14884 |
| `atom_operation` → str | операция атома | вместе с `atom_from_agg` ~:14618–14621 |
| `build_answer_atom` / `atom_from_agg` → dict | атом | ~:14618, :11410, :8068, :14331, :14795, :14889; также ранние сборщики ~:2347+ |
| `render_atom_pair` → str\|None | готовая пара | ~:2554, :6364, :6387, :6444, :6463, :6492, :6548, :14337 |
| `fill_atom_pairs` → `(text, bad)` | текст + список неподставленных маркеров | ~:14653, :14720 |
| `pair_slots_only` → bool | флаг «только пары» | ~:9461 (`compose`) |
| `atom_whitelist_labels` / `atom_whitelist_numbers` → list | подписи / числа из атомов | вызовов в `serene_ask.py` **нет** |
| `arbiter_figures` → dict | отпечаток кандидата | ~:13582 |

## Обращения наружу

SQL, HTTP, вызов языковой модели в участке **нет**.

Локальные вызовы вне строк 7369–7740 (не I/O):
- `_fmt` (:445) — из `build_answer_atom`, `render_atom_pair`.
- `_group_leader` (:8706) — из `compose_slot_values`, `_atom_exact_value`.
- `_unit_for_measure` (:9162) — из `atom_from_agg` при `unit_or_currency is None`.
- `SLOT` (:8968) — regex подстановки в `fill_atom_pairs`.

## Переключатели

| Имя | Где читается в участке | Загрузка / умолчание |
|---|---|---|
| `ASK_ATOM_TERMINAL` | :7400 — `form=="compare"` → `"compare"` если True, иначе `"rank"` | `os.environ.get("ASK_ATOM_TERMINAL", "0") == "1"` — :1428 |
| `ROWS_TO_MODEL` | :7449 — срез `groups[:ROWS_TO_MODEL]` для слотов `gN` | `int(os.environ.get("ASK_ROWS_TO_MODEL", "25"))` — :118 |
| `money` (арг.) | `compose_slot_values`, `atom_from_agg` | в compose: `None` → `bool(measure)` — :7418–7419; в atom_from_agg: умолч. `True` — :7582 |
| `slot_mode` (арг.) | `compose_slot_values` | `None` → `"rank"` если `agg.grain=="group"`, иначе `"list"` — :7420–7421 |
| `UNIT_UNKNOWN` | константа `"unknown"` — :7489; в render единица с этим значением не дописывается — :7647 |
| `PROOF_*` | `"computed"` / `"not_applicable"` / `"not_computed"` — :7490–7492 |
| `_ATOM_OPS` | допустимые операции; иное → `"count"` — :7493, :7548–7550, :7588–7590 |

## Развилки

**`answer_slot_mode` (:7394–7407):** счёт → `"count"`; `form==compare` → `"compare"` или `"rank"` (см. `ASK_ATOM_TERMINAL`); `form==rank` → `"rank"`; `want==sum` или `compute∈{sum,max,min,avg}` → `"sum"`; `grain==group` → `"rank"`; иначе `"list"`.

**`compose_slot_values`:** пустой `agg` → `{}` (:7423–7424). По `slot_mode`: `count` — только count (+служебные даты/папки ниже); `compare`+money — `sum`; `sum`+money — `count_amount`/`sum`/`max`/`min`/`avg` (на group только `sum`); `rank` — `sum` если money и `n_groups > shown`, плюс `g0…`; иначе (ветка `money`) — агрегаты + `leader` на group (:7452–7463). Общие хвосты: `n_groups`, `date_*`, `folders`, `undated`, `outside_period` (:7464–7480).

**`_atom_exact_value` (:7517–7532):** `count`→count; max/min/avg→поле; sum/rank/compare→leader на group, иначе sum если money, иначе count; list→sum если money иначе count.

**`render_atom_pair`:** не dict / `proof_status==not_computed` / оба value None → `None` (:7631–7636). С подписью: `"label: value"`; без — только value; единица если не пуста и ≠`unknown`; notes из `excluded` и `completeness.missing` (:7642–7663).

**`fill_atom_pairs`:** пустой text → `(text, [])` (:7672–7673); роль ≠`pair` — маркер не трогает (:7679–7680); плохой индекс или `render` None — маркер остаётся, в `bad` (:7687–7692).

**`build_answer_atom`:** `proof_status` не передан → `computed` если `exact_value is not None`, иначе `not_computed` (:7551–7552). `unit_or_currency is None` → `""` (:7553).

## Чего здесь нет

- SQL-агрегации и чтения `agg` из базы (участок только потребляет готовый `agg`).
- Вызова модели / HTTP.
- Гейта проверки ответа (только подготовка whitelist/figures).
- Сборки текста вопроса/промпта (`compose` снаружи).
- API «подпись отдельно + число отдельно» (явно нет — :7627–7629, :7667).
- Записи в БД / файлы / env.
- Разбора `want`/`compute` из сырой прозы пользователя (принимает уже решённые поля).
