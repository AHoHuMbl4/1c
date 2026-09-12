# W1 — карта живости `ask/z06_entity_search.py`

Дата: 2026-09-12. Только чтение кода. Чужие отчёты onepath не читались.

Зона: поиск сущностей (entity-search). Имена экспортируются **голыми** в общий
namespace (`register_zone` + `exec` через `_bootstrap.py`). Переопределений тех же
имён в других `z*.py` нет. `_imports.py` / `_wire.py` символы зоны не вызывают;
`_bootstrap.py` только грузит файл в `_ZONE_FILES` (строка 29).

Файл: 604 строки; top-level определений: 18 `def` (констант/классов нет).

---

## Итог зоны

| Вердикт | Символов | Строк (тело def) |
|---|---:|---:|
| **ЖИВА НОВОМУ** (прямо или транзитивно) | 12 | **348** |
| **ЖИВА ТОЛЬКО LEGACY** | 3 | **146** |
| **МЁРТВА** | 3 | **65** |
| **Всего по символам** | 18 | **559** |

Зона **нужна одному пути**: ядро row-filter / match (`probe` → `match_expr` →
`tables_of`, `_predicates`, `matched_group_count`) зовётся из нового `answer()`.
Часть пула кандидатов сущности (`meaning_candidates` и поверхности) жива новому
транзитивно через ось/`mk_opts`, не как прямой выбор `src` в onepath.
После flip и сноса legacy можно снести ~146 строк
(`children_by_parent` / `partial_tables` / `date_only_kind_filter`) и три мёртвых
символа (~65 строк), если замки тестов перепишут/уберут.

---

## Таблица символов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_predicates` | 9–17 (9) | **new** `z20_ask_main_http.py`: `dates_outside_period_filter:1190`, `answer:1891,1994,2006,2205`; **legacy** `z20_…_legacy.py`: `dates_outside_period_filter:1216`, `drop_period_preds:1341`, `answer:1790,3915` (3914 — комментарий); тест `test_intent.py:563` | **ЖИВА НОВОМУ** |
| `_fetch` | 20–32 (13) | никто (только комментарий в `z07_rrf_vectors.py:271`) | **МЁРТВА** |
| `_like_pattern` | 35–55 (21) | внутри зоны: `probe:91`; тесты `test_step2.py:84–92` | **ЖИВА НОВОМУ** (← `probe` ← new `answer`) |
| `probe` | 58–160 (103) | **new** `answer:2070`; **legacy** `answer:1911` (+комменты); внутри: `question_exprs:499`; тесты `test_step2.py`, `test_b9_routing.py:69`, моки `test_compose.py` / `test_stock_balance_path.py` | **ЖИВА НОВОМУ** |
| `matched_group_count` | 163–173 (11) | **new** `answer:2075`; **legacy** `answer:1925`; тесты `test_k4_clarify_vs_nodata.py:34,36`, `test_step2.py` | **ЖИВА НОВОМУ** |
| `with_refs` | 176–184 (9) | внутри: `match_expr:197,217`, `partial_tables:324,348` | **ЖИВА НОВОМУ** (← `match_expr` ← new); также ← legacy `partial_tables` |
| `match_expr` | 187–217 (31) | **new** `answer:2083`; **legacy** `answer:1938`; тесты `test_step2.py`, моки compose/stock | **ЖИВА НОВОМУ** |
| `children_by_parent` | 220–270 (51) | **только legacy** `answer:2053`; тесты `test_step2.py:240,248`, моки | **ЖИВА ТОЛЬКО LEGACY** |
| `partial_tables` | 273–350 (78) | **только legacy** `answer:1951` (+коммент 1946); моки `test_stock_balance_path.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `tables_of` | 353–369 (17) | **new** `answer:2087`; **legacy** `answer:1941,2080`; тесты `test_step2.py`, моки | **ЖИВА НОВОМУ** |
| `date_only_kind_filter` | 372–388 (17) | **только legacy** `answer:2006`; тесты `test_measure_empty.py:126,132` | **ЖИВА ТОЛЬКО LEGACY** |
| `keep_empty_period_opts` | 391–406 (16) | **new** `mk_opts:1075`; **legacy** `mk_opts:1099`; тесты `test_measure_empty.py`, `test_terminal_round.py:137` | **ЖИВА НОВОМУ** (← `mk_opts` ← wiki/fork ← new `answer`) |
| `alias_hits` | 409–440 (32) | внутри: `meaning_candidates:538`; legacy — только комментарии `answer:1968,1989` | **ЖИВА НОВОМУ** (← `meaning_candidates`) |
| `card_hits` | 443–481 (39) | внутри: `meaning_candidates:539`; упоминание в комменте `z08_measures_totals.py:37` | **ЖИВА НОВОМУ** (← `meaning_candidates`) |
| `question_exprs` | 484–502 (19) | внутри: `meaning_candidates:532`; **legacy** `answer:1999` | **ЖИВА НОВОМУ** (← `meaning_candidates`); плюс прямой legacy |
| `meaning_candidates` | 505–545 (41) | **legacy** `answer:2004`; `z05_entity_form.py` `entity_form_catalogs_for_kind:332`, `entity_form_movements_for_kind:369`; `z17_aggregate_groups.py` `kind_axis_hits:463`; тесты/моки compose, entity_form, stock | **ЖИВА НОВОМУ** (транзитивно; прямо в new — нет) |
| `entity_pick_counts_for_model` | 548–577 (30) | только `test_k6_rank_v2.py:82` | **МЁРТВА** (прод/зоны не зовут) |
| `entity_matching_records_suffix` | 580–601 (22) | только `test_k6_rank_v2.py:79` | **МЁРТВА** (прод/зоны не зовут) |

Ловушка namespace: локальная переменная `probe` в `z04b_currency_axis.py:398+` и
строки «probe» в тестах ab-/gold — **не** зов зоны. AST `Call` по голым именам
совпадает с таблицей выше; `getattr`/`f-string` с именами символов z06 не найдены
(кроме `globals().get("entity_form_catalogs_for_kind")` в z21 — это не символ z06,
но тянет `meaning_candidates`).

---

## Транзитивные цепочки

### Живы новому `z20_ask_main_http.py`

```
_predicates
  ← dates_outside_period_filter ← build_period_empty_answer ← answer
  ← answer (прямые preds / _date_preds)

_like_pattern ← probe ← answer:2070
                 ↳ question_exprs ← meaning_candidates ← … (ниже)

probe ← answer:2070

matched_group_count ← answer:2075

with_refs ← match_expr ← answer:2083

match_expr ← answer:2083

tables_of ← answer:2087

keep_empty_period_opts ← mk_opts:1075
  ← wiki_primary_entity_cascade (z21:958) ← answer:1951
  ← fork_outcomes (z13:637,839) ← … ← answer (clarify-ветки)

meaning_candidates
  ← kind_axis_hits (z17:463) ← _settle_axis:1593 ← answer:2043
  ← entity_form_catalogs_for_kind (z05:332)
       ← wiki_leader_carries_axis (z21:1027 getattr) ← wiki cascade ← answer
       ← (и др. зоны z02/z10/z11/z12 — при достижимости из answer)
  ← entity_form_movements_for_kind (z05:369) ← … (legacy F-путь сильнее; new
       без прямого try_entity_form_answer в диске z20)

alias_hits ← meaning_candidates ← …
card_hits  ← meaning_candidates ← …
question_exprs ← meaning_candidates ← …
             ↳ probe ← question_exprs
```

### Только legacy `z20_ask_main_http_legacy.py`

```
children_by_parent ← answer:2053
partial_tables     ← answer:1951
date_only_kind_filter ← answer:2006
  (вход kind_ok ← meaning_candidates ← answer:2004;
   question_exprs ← answer:1999 — сами meaning/question_exprs живут и новому)
```

### Мёртвые (нет корня ни в new, ни в legacy answer)

```
_fetch
entity_pick_counts_for_model   ← только test_k6_rank_v2
entity_matching_records_suffix ← только test_k6_rank_v2
```

---

## Bootstrap / imports / wire

| Файл | Роль для z06 |
|---|---|
| `_bootstrap.py` | грузит `z06_entity_search.py` в `_ZONE_FILES`; символы не вызывает |
| `_imports.py` | упоминаний символов z06 нет |
| `_wire.py` | `register_zone` / `apply_bindings` — механизм, не зов символов |

---

## Замки (тесты)

| Символ | Замки |
|---|---|
| `_predicates` | `test_intent.py` |
| `_like_pattern`, `probe`, `matched_group_count`, `match_expr`, `tables_of`, `children_by_parent` | `test_step2.py` (+ routing/k4) |
| `probe` / `match_expr` / `tables_of` / `children_by_parent` / `partial_tables` / `meaning_candidates` | моки в `test_compose.py`, `test_stock_balance_path.py` |
| `date_only_kind_filter`, `keep_empty_period_opts` | `test_measure_empty.py`; keep — ещё `test_terminal_round.py` |
| `meaning_candidates` | `test_entity_form.py` (подмена) |
| `entity_pick_*` / `entity_matching_*` | `test_k6_rank_v2.py` |

Отдельного `test_one_path` / замка на зону в этом заходе не искали за пределами
`ubuntu/serenedb/test_*.py` (по заданию).

---

## Скрытые выбиратели, доступные НОВОМУ тракту

Критерий: функция зоны, которая кодом отбирает/сужает **источник / меру / период / ось**,
и достижима из нового `answer`.

| Символ | Что выбирает | Как попадает в new |
|---|---|---|
| **`meaning_candidates`** (+ `alias_hits`, `card_hits`, `question_exprs`) | список `src_table`-кандидатов по alias/card/near (не wiki) | через `kind_axis_hits` → `_settle_axis` (ось: `target_src ∈ found`); через `entity_form_catalogs_for_kind(..., allow_meaning=…)` в wiki post-verify оси |
| **`keep_empty_period_opts`** | какие источники оставить в меню clarify при пустом/непустом окне даты | через `mk_opts` ← wiki clarify / fork |
| `match_expr` | порог `k` (min_should_match), не src/мера/период/ось | прямо из `answer` — **не** скрытый выбиратель сущности; механика match |
| `probe` | вариант матча слова (exact/slop/fuzzy/part/resolved) | row-filter после wiki — не выбор src |

**Не тащатся в new** (только legacy): `partial_tables` (сущности с частичным k),
`children_by_parent` (расширение пула табличными частями), `date_only_kind_filter`
(фильтр пула при пустом match по kind).

**Вывод по выбирателям:** зона тащит в один путь два кодовых отбора, связанных с
кандидатами/меню (`meaning_candidates` для оси/форм, `keep_empty_period_opts` для
меню источников). Прямого выбора `src` ответа в новом `answer` зона не делает
(src — из wiki-каскада; `probe`/`tables_of` — row-filter и счёт по уже выбранному src).

---

## Метод

- AST top-level `def` в `z06_entity_search.py` + число строк `end_lineno−lineno+1`.
- Упоминания: word-boundary по всем `ask/*.py` и `ubuntu/serenedb/test_*.py`.
- Живость: AST `Call` + достижимость из `answer` / `answer_checked` при общем namespace
  (new и legacy z20 по отдельности; другой z20 из графа исключён).
- Переопределений имён z06 в других зонах: 0.
