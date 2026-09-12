# S1b: доводка замков после сноса S1 (12.09)

После S1 (−7799 строк legacy-z20 + z09/z13/z16) четыре замка падали.
Правки только в замках; z20 не трогали (п.4 — смена ожидания, не возврат ветки).
Git-мутаций / psql / полигон / прод — нет.

## 1. `test_compose.py` — `resolve_focus`

**Было.** Блок figures-fallback брал `A.resolve_focus` / `A.pick_measure` в
снимок моков → `AttributeError` на импорте атрибута (символы снесены с
legacy-z20).

**Сделал.** Переписал fallback на живой onepath: сущность/мера через билет
`resolved={src, measure}` (+ `measure_pick`), вики/меню обходятся; SQL и
compose — моками (`period_readings=[]`, `aggregate`/`rows_of`/`totals_of`,
`ds_chat` с незаполнимым `{count}`). `resolve_focus` / `pick_measure` /
`meaning_candidates` / `children_by_parent` из блока убраны.

**Прогон.** `93` проверок, 0 FAIL.

## 2. `test_b9_routing.py` — `fork_outcome_b`

**Было.** Замок звал снесённый `fork_outcome_b` как утилиту теста →
`AttributeError`.

**Сделал.** Убрал вызов. Суть B8-02 уже закрыта блоком
`count_question_skips_axis` выше; добавлена негативная проверка
`fork_outcome_b GONE (S1)`.

**Прогон.** `7` проверок, 0 FAIL.

## 3. `test_k4_guess_vs_clarify.py` — `pick_measure`

**Было.** M3/M4 звали `pick_measure` / `unresolved_quantity` (снесённые
выбиратели) → `AttributeError`.

**Сделал.** M3/M4 на `_settle_measure`: при `want=sum` и >1 имени меры —
`(None, alts)` (меню), не silent winner / не `names[0]`. Негатив
`pick_measure GONE`. Убраны неиспользуемые фикстуры `_q_top` / `_intent_top`
/ `_AX_PROD`.

**Прогон.** `12` ok, `0` FAIL, `3` pending (как и раньше: period_assumed /
measure_class_alts / stock marker №12).

## 4. `test_period_empty.py` — «пустышка меры не пивотит пустое окно»

**Было.** Ожидание строки
`if _мертва and not diag.get("period_window_empty")` в `ask_source()`.
Ветка жила только в legacy-z20 (~3440–3455) + `build_measure_empty_pivot`
(z16); оба снесены S1 (W1: **ЖИВА ТОЛЬКО LEGACY**). Флаг
`period_window_empty` в новом z20 жив (~2091–2099).

**Сделал.** z20 не возвращал: пивот пустышки — legacy-механика, на onepath
пустое окно закрывает `period_empty`, пивота all-time больше нет. Ожидание
замка: флаг `period_window_empty` есть + `build_measure_empty_pivot` /
`_мертва` отсутствуют (инвариант «нет пивота без учёта пустого окна»).

**Прогон.** `30` проверок, 0 FAIL.

## Итоговый прогон

| Замок | Итог |
|---|---|
| `test_compose.py` | 93/0 |
| `test_b9_routing.py` | 7/0 |
| `test_k4_guess_vs_clarify.py` | 12/0 (+3 pending) |
| `test_period_empty.py` | 30/0 |
| `test_one_path.py` | 41/0 |
| `test_wiki_card_hybrid.py` | 65/0 |

Файлы: `ubuntu/serenedb/test_compose.py`, `test_b9_routing.py`,
`test_k4_guess_vs_clarify.py`, `test_period_empty.py`, этот отчёт.
