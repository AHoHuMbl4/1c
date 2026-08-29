# K7: ось склада без привязки к конфигурации

**Дата:** 2026-08-27  
**База:** okna (живой SQL-замер)  
**Повод:** снайпер коммита отбил `warehouse_axis_values` — литерал
`МестоХранения` и маска `catalog_%мест%хран%` (находка верная).

`serene_ask.py` правится в этом шаге, **в коммит не входит** (как K5:
оркестратор после живой пробы `/ask`).

---

## 1. Что было не так

| Привязка | Почему дефект |
|---|---|
| `map_extract_value(refs_map, 'МестоХранения')` | имя реквизита русской типовой; на чужой базе / другом языке ось пуста, clarify молча вырождается |
| `lower(src_table) LIKE 'catalog_%мест%хран%'` | догадка по маске имени таблицы (`HOW_NOT_TO §3.9`, `§3.14`) |

Девиз 29.07 / [`PLAN_AUTONOMY.md`](PLAN_AUTONOMY.md): узнать нужное у движка /
словаря / `$metadata`-производных, не разбирать текст конфигурации.

---

## 2. Как уже решают ту же задачу в проекте

Рабочий приём — тот же, что выбор оси rank/entity:

1. **Каталог** — `entity_form_catalogs_for_kind(kind)`: stem вопроса
   (`склад` / `warehouse`) ∩ `label|aliases|best_used_for` в
   `search_entity_alias` + `search_tables`.
2. **Колонка refs_map** — `search_refcols` по `target_src` каталога
   (имя реквизита знает база; в коде его нет). Score: сколько держателей
   `accumulationregister_*`, затем `count(DISTINCT)` значений.
3. **Значения** — `map_extract_value(refs_map, col)` в корпусе
   ([доки](https://docs.serenedb.com/sql/functions/map#map_extract_valuemap-key)).
4. **Запасной** — `search_refmap.name WHERE owner = catalog`
   (те же человеческие строки на okna).

Вызов: `warehouse_clarify` → `warehouse_axis_values()` (единственный
живой caller; тесты передают `warehouses=` явно).

---

## 3. Замер okna (до / после)

Один SSH-проход, DSN `:7890`, пароль из `/etc/1c-mcp-reports.env`.

| путь | список |
|---|---|
| **до** (литерал `МестоХранения`) | Bubuieci / 0000000003 / …; Depozit / 0000000001 / …; Vitrina / 0000000002 / … |
| **после** (alias → refcols → best col) | те же **3** строки, тот же set |
| fallback `search_refmap` | те же **3** |

Меньше не стало. Лучшая колонка на okna: `МестоХранения` (on_accum=1,
n_vals=3) — имя узнано из `search_refcols`, не из кода.

**Доки:** Sql › Functions › Map Functions › `map_extract_value`;
Sql › Statements › SELECT › ORDER BY, LIMIT.

---

## 4. Замки

| замок | результат |
|---|---|
| `test_warehouse_axis_autonomy.py` (новый) | **12/0** |
| `test_warehouse_aggregate_breakdown.py` (29.08) | **17/0** |
| `test_k4_axis_and_names.py` | **11/0** |
| `test_k4_guess_vs_clarify.py` | **13/0** |
| `test_k4_meta_names.py` | **12/0** |
| `test_k4_clarify_vs_nodata.py` | **11/0** |
| `test_sales_rank_canon.py` | **51/0** |
| `test_partial_flag_propagation.py` | **20/0** |
| `test_fork_outcomes.py` | **29/0** |
| `test_calendar_axis.py` | **36/0** |
| `test_code_map.py` (после `code_map.py`) | **28/0** |

Замок падает, если в `warehouse_axis_values` снова появится литерал
реквизита / маска таблицы / `Description`, или пропадёт путь через
`entity_form_catalogs_for_kind` + `search_refcols` + `search_refmap`.

---

## 5. Файлы

| файл | в коммите? |
|---|---|
| `ubuntu/serenedb/serene_ask.py` (`warehouse_axis_values`) | **нет** (оркестратор) |
| `ubuntu/serenedb/test_warehouse_axis_autonomy.py` | да |
| `docs/K7_WAREHOUSE_AXIS.md` | да |
| `docs/CODE_MAP_ASK.md`, `docs/audit/code-map.json` | да (перегенерация) |

---

## 6. Проба оркестратора и коммит `serene_ask.py` (27.08)

Кандидат с правками К5 + К7 поднят на okna отдельным процессом
(`/tmp/serene_ask_k7.py`, md5 `35daa28008373a41b92134e5ab3cdcb0`, порт 8093,
`PYTHONPATH=/opt/1c-mcp-reports`). Боевой `:8091` и стейджинг `:8092` не трогали —
на `:8092` в это время шёл замер набора ambiguous.

| набор | результат |
|---|---|
| `AB_PROBE=okna` (8 вопросов) | **8/8, средняя 21,09 с** |

Прогон поставил отметку `.claude/.probe-okna-last-run` (0err/8), после чего
`ubuntu/serenedb/serene_ask.py` ушёл в git вместе с правками К5.

Почему кандидат жил во временном каталоге, а не в `/opt/1c-mcp-reports`: гейт
`check-golden` не пропускает доставку в рабочие каталоги, пока дерево
`ubuntu/**` не совпадает с HEAD, а в дереве в тот момент лежали незакоммиченные
правки соседней задачи (набор ambiguous). Доставка во временный каталог гейтом
разрешена и ничего не подменяет на боевом контуре.
