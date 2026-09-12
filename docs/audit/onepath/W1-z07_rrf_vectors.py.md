# W1 — карта живости зоны `ask/z07_rrf_vectors.py`

Дата среза: 12.09.2026. Файл: `ubuntu/serenedb/ask/z07_rrf_vectors.py` (556 строк;
символы верхнего уровня — 497 строк тел; 59 строк — шапка зоны, пустые строки,
комментарии между символами).

Метод: AST верхнего уровня зоны; grep по `ask/*.py` + `ubuntu/serenedb/test_*.py`
(границы слова; учитывались f-строки/getattr/словари имён). Импорт-структуре не
доверяли — зоны грузятся в общий namespace через `_bootstrap.py`. Чужие отчёты
`docs/audit/onepath/` не читались.

Вердикты:
- **ЖИВА НОВОМУ** — прямо или транзитивно зовётся из `z20_ask_main_http.py`;
- **ЖИВА ТОЛЬКО LEGACY** — нужна `z20_ask_main_http_legacy.py`, после flip/сноса legacy — мёртва;
- **МЁРТВА** — нет вызывающих (или только комментарии / мёртвые).

---

## 1. Таблица символов

| Символ | Строки | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_corpus_ivf_ready` | 15 (9–23) | внутр. `_fused_candidates` (`z07:147`); тест `test_sql_rrf.py:57,70,73,76,81,87,92` | **ЖИВА НОВОМУ** (транз. через `_fused_candidates`) |
| `_resolver_ivf_ready` | 20 (26–45) | внутр. `resolve_values` (`z07:514`); тест `test_resolver_ivf.py:47,50,55` | **ЖИВА НОВОМУ** (транз. через `resolve_values` ← `probe`) |
| `_rrf_entity_branches` | 32 (48–79) | внутр. `_fused_candidates` (`z07:144,162`) | **ЖИВА НОВОМУ** (транз.) |
| `_rrf_corpus_branch` | 8 (82–89) | внутр. `_fused_candidates` (`z07:153`) | **ЖИВА НОВОМУ** (транз.) |
| `_fused_sql_rrf` | 6 (92–97) | внутр. `_fused_candidates` (`z07:155,168`) | **ЖИВА НОВОМУ** (транз.) |
| `_fused_python_rrf` | 17 (100–116) | внутр. `_fused_candidates` (`z07:164`) | **ЖИВА НОВОМУ** (транз.) |
| `_fused_candidates` | 52 (119–170) | `z06:533` (`meaning_candidates`); тесты `test_sql_rrf.py:64,71,78,89` | **ЖИВА НОВОМУ** (транз. `kind_axis_hits` → `meaning_candidates`); также legacy прямой `meaning_candidates` |
| `near_tables` | 39 (173–211) | `z06:540,541` (`meaning_candidates`); legacy комментарий `z20_legacy:1969` | **ЖИВА НОВОМУ** (транз. через `meaning_candidates`) |
| `rows_of` | 33 (214–246) | **новый** `z20:2147`; legacy `z20_legacy:3223,3247,3838` (+ коммент. `:3207`); `_bootstrap.py:92` только коммент.; тесты `test_compose.py:467,492`, `test_one_path.py:60` (имя в SQL_CALLS) | **ЖИВА НОВОМУ** (прямо) |
| `signal_terms` | 34 (249–282) | нигде кроме определения | **МЁРТВА** |
| `CLARIFY_SYS` | 1 (287) | **только legacy** `OUR_PROMPTS` (`z20_legacy:761`); новый `OUR_PROMPTS` без неё (`z20:755`); замок `test_one_path.py:292–293` | **ЖИВА ТОЛЬКО LEGACY** |
| `clarify_text` | 3 (290–292) | упоминания только в комментариях (`z20:266`, `z20_legacy:271`); вызовов нет | **МЁРТВА** |
| `REFUSE_SYS` | 4 (298–301) | внутр. `refuse_text` (`z07:322`); **новый** `OUR_PROMPTS` (`z20:755`); legacy `OUR_PROMPTS` (`z20_legacy:761`) | **ЖИВА НОВОМУ** (прямо по имени + через `refuse_text`) |
| `refuse_text` | 23 (304–326) | **новый** `z20:783,787,1813,1965,2080,2136,2152,2185`; legacy много (`:788+`); `z04:173`, `z13:421,777`, `z21:880,911`; тесты `test_atom_terminal.py`, stubs в wiki/named_type | **ЖИВА НОВОМУ** (прямо + транз. z04/z13/z21) |
| `rerank` | 59 (329–387) | внутр. `resolve_values` (`z07:543`); `z10:184` (`rank_axes_rerank`); `z17:489` (`kind_axis_rerank`); прочие — строка `'rerank'` как how / комменты / URL; тесты resolver/stock/gate | **ЖИВА НОВОМУ** (транз. `rank_axis_resolve` → `rank_axes_rerank` и `resolve_values`) |
| `_resolver_psql` | 19 (390–408) | внутр. `_resolver_ivf_ready` / `_resolve_values_literal` / `resolve_values`; **новый** `z20:2717,2730,2734` (ask_scope); legacy `:4868,4881,4885`; тесты `test_b9_routing`, `test_resolver_ivf` | **ЖИВА НОВОМУ** (прямо) |
| `RESOLVE_NEAR` | 1 (411) | внутр. `resolve_values` (`z07:518,529`) | **ЖИВА НОВОМУ** (транз.) |
| `RESOLVE_KEEP` | 1 (412) | внутр. `_resolve_values_literal` / `resolve_values` (`z07:430,455,544`) | **ЖИВА НОВОМУ** (транз.) |
| `_resolve_values_literal` | 45 (415–459) | `z06:129` (`probe`); тесты `test_b9_routing`, `test_step2` | **ЖИВА НОВОМУ** (транз. `probe` ← новый `z20:2070`) |
| `_resolve_values_corpus` | 22 (462–483) | `z06:132` (`probe`); тесты `test_step2` | **ЖИВА НОВОМУ** (транз. `probe`) |
| `resolve_values` | 58 (488–545) | `z06:127` (`probe`); тесты `test_b9_routing`, `test_resolver_ivf`, `test_step2` | **ЖИВА НОВОМУ** (транз. `probe`) |
| `_ngrams` | 5 (548–552) | `z08:26` (`_shares_chars`); `_shares_chars` зовёт `resolve_values` (`z07:540`) | **ЖИВА НОВОМУ** (транз. через резолвер) |

`_imports.py` / `_wire.py`: упоминаний символов зоны нет.  
`_bootstrap.py`: только комментарий про `rows_of` (`:92`) — не вызов.

---

## 2. Итог зоны

| | Строк символов |
|---|---:|
| Всего тел символов | **497** |
| Файл целиком | **556** (ещё 59 — шапка/пробелы/комменты между) |
| **ЖИВА НОВОМУ** | **459** (19 символов) |
| **ЖИВА ТОЛЬКО LEGACY** | **1** (`CLARIFY_SYS`) |
| **МЁРТВА** | **37** (`signal_terms` 34 + `clarify_text` 3) |

**Вердикт по зоне:** зона **нужна одному пути** — ядро (отказ, строки, резолвер
значений, RRF/near как запас оси, rerank осей, `_resolver_psql` для ask_scope)
живо новому тракту. После flip и сноса legacy из зоны уходит по сути только
якорь `CLARIFY_SYS` (+ уже мёртвые `clarify_text` / `signal_terms`).

---

## 3. Транзитивные цепочки (до корня z20)

### Живы новому `z20_ask_main_http.py`

1. `rows_of` ← **новый z20:2147** (прямо)
2. `refuse_text` ← **новый z20** (прямо, несколько точек no_data)
3. `REFUSE_SYS` ← `OUR_PROMPTS` (**новый z20:755**) и ← `refuse_text` ← новый z20
4. `_resolver_psql` ← **новый z20:2717+** (ask_scope DDL/INSERT)
5. `resolve_values` / `_resolve_values_literal` / `_resolve_values_corpus` /
   `_resolver_ivf_ready` / `RESOLVE_*` / внутренний `rerank` / `_ngrams`
   ← `probe` (`z06`) ← **новый z20:2070**
6. `rerank` ← `rank_axes_rerank` ← `rank_axis_resolve` (`z10`) ← **новый z20:1597**
   (также `kind_axis_rerank` ← `rank_axis_resolve` при kind-без-вопроса)
7. `_fused_candidates` + RRF-стек (`_corpus_ivf_ready`, `_rrf_*`, `_fused_*_rrf`)
   + `near_tables`
   ← `meaning_candidates` (`z06`) ← `kind_axis_hits` (`z17`, `meaning_ok=True` по умолчанию)
   ← **новый z20:1593** (запас, когда stem-совпадение осей пусто)
8. `refuse_text` ← `calendar_axis_unavailable_block` (`z04`) ← **новый z20:1907**
9. `refuse_text` ← `atom_terminal_gate_text` (`z13`) ← **новый z20:1807**
10. `refuse_text` ← `wiki_primary_entity_cascade` (`z21`) ← **новый z20:1951**

### Живы только legacy

1. `CLARIFY_SYS` ← `OUR_PROMPTS` (**legacy z20:761**); в новом списке нет
2. Прямой `meaning_candidates(...)` в entity-search — **только legacy z20:2004**
   (символы RRF при этом всё равно живы новому через цепочку 7)
3. Доп. `rows_of` probe (`z20_legacy:3223,3247`) и `fork_outcome_c` → `refuse_text`
   — только legacy; у нового `refuse_text`/`rows_of` есть свои прямые зовы

### Мёртвые

1. `signal_terms` — нет callers
2. `clarify_text` — нет callers (тело `""`; B4)

---

## 4. Скрытые выбиратели, доступные новому тракту

Через транзитивные вызовы зона **тащит в новый путь** механизмы, которые кодом
ранжируют/отбирают кандидатов (не wiki-меню человека):

| Механизм | Цепочка в новый z20 | Что выбирает |
|---|---|---|
| `near_tables` + `_fused_candidates` (SQL/Python RRF, IVF-ветвь корпуса) | `kind_axis_hits` → `meaning_candidates` → … ← `z20:1593` | `src_table` по смыслу/слиянию поверхностей — **запасной отбор target_src для оси**, не wiki-entity, но всё же кодовый выбор источника-кандидата |
| `rerank` | `rank_axis_resolve` → `rank_axes_rerank` ← `z20:1597` | **ось** по меткам (при ≥2 — меню в `rank_axis_resolve`, не silent first; при 1 — берёт одну) |
| `resolve_values` (+ внутренний `rerank`, IVF/exact) | `probe` ← `z20:2070` | **значения фильтра** («Питер»→«Санкт-Петербург») молча, без меню; не ось/мера/период, но кодовый выбиратель значения |

Не выбиратели источника/меры/периода/оси (для полноты): `rows_of` (выборка строк),
`refuse_text`/`REFUSE_SYS` (формулировка отказа), `_resolver_psql` (служебный SQL
роли resolver / ask_scope).

`signal_terms` (отличительные термы для модели при выборе сущности) — **мёртв**,
в новый тракт не входит.

---

## 5. Замки (тесты)

| Тест | Что трогает из z07 |
|---|---|
| `test_sql_rrf.py` | `_fused_candidates`, `_corpus_ivf_ready` |
| `test_resolver_ivf.py` | `resolve_values`, `_resolver_ivf_ready`, `_resolver_psql`, `rerank` |
| `test_b9_routing.py` | `_resolve_values_literal`, `resolve_values`, `_resolver_psql` |
| `test_step2.py` | `resolve_values`, `_resolve_values_literal`, `_resolve_values_corpus` |
| `test_compose.py` | `rows_of` (mock) |
| `test_one_path.py` | `rows_of` в SQL_CALLS; запрет `CLARIFY_SYS` в новом OUR_PROMPTS |
| `test_atom_terminal.py` | `refuse_text` (stub) |
| `test_wiki_*` / `test_named_type_filter.py` | stub `refuse_text` в фейковом ns |
| `test_stock_balance_path.py` | mock `rerank` |
| `test_gate.py` / `test_measure_*` / `test_no_pre_wiki_reorders.py` | строка `'rerank'` как how / отсутствие silent rerank — не зов функции `rerank` |

---

## 6. Краткие выводы

1. Зона **не мёртвая для onepath**: ~92 % строк символов живы новому тракту.
2. После сноса legacy безопасный выкидыш из зоны: `CLARIFY_SYS`, уже пустой
   `clarify_text`, мёртвый `signal_terms` (37+1 строк символов).
3. RRF/`near_tables` **не убраны** из нового пути: они сидят в запасном плече
   `kind_axis_hits` → `meaning_candidates`, хотя прямой entity-search через
   `meaning_candidates` в новом z20 уже нет.
4. Скрытые кодовые отборы, доступные onepath: смысловой RRF источников для осей,
   rerank осей, молчаливый value-resolver в `probe`.
