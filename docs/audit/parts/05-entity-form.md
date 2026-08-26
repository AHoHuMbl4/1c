# 05. entity-form

## Зачем участок нужен

Участок `ubuntu/serenedb/serene_ask.py:1995–2594` реализует форму ответа F: счёт по оси ссылки (`distinct_axis`) и дополнение к каталогу (`complement`), плюс гейты, отделяющие rank/top-N от compare двух окон продаж. `try_entity_form_answer` собирает готовый ответ-атом; `aggregate_compare_sales` считает разность двух сумм продаж (`form=compare`). Всё включается флагом `ASK_ENTITY_FORM`.

## Входы

- `intent`: `want`, `kind`, `period`/`period2` (`from`/`to`), `amount.value` — `entity_form_rank_single_window:2003–2014`, `entity_form_count_target_is_movement:2207–2220`, `entity_form_applicable:2283–2305`, `entity_form_structs:2445–2454`.
- `question` (строка): `sales_compare_intent:2037–2057`, `entity_form_rank_single_window` через `rank_question_text` / `_sales_rank_top_n:2008–2019`.
- `pool` / `raw`: список `src_table` (`catalog_*`, `document_*`, `accumulationregister_*`) — `entity_form_expand_pool:2239`, `entity_form_applicable:2287–2299`, `try_entity_form_answer:2542`.
- `today`, `match`, `diag`, `cut`, `t0`, `when`, `early_classes` — `try_entity_form_answer:2536–2548`, `sales_compare_windows:2066`.
- `form`/`meta` (`catalog_src`, `sales_src`, `axis`, `period`) — `entity_form_compute:2509–2532`.
- `aggregate_compare_sales`: `src`, `match`, `period1`, `period2`, `measure` — `2570–2575`.
- Глобал `ASK_ENTITY_FORM` (см. Переключатели). Константы вне участка, читаемые здесь: `ROWS_TO_MODEL`, `STEM_DICT`, `TABLES`, `CORPUS`, `MEANING_TOP`, `_ORIGIN_ASSUMED`.

## Порядок работы

1. **Гейт B / compare-окно** (`entity_form_rank_single_window:2001–2022`): при `ASK_ENTITY_FORM` — True, если нет `period2`, и есть rank-текст / `amount`∈[1..ROWS_TO_MODEL] / `_sales_rank_top_n>1`.
2. **`sales_compare_intent:2036–2057`**: нужен `sales_sum_intent`; суперлативы → False; при `ASK_ENTITY_FORM` гейт B без «vs/чем» → False; иначе маркеры «лучше/хуже/больше чем…».
3. **`sales_compare_windows:2066–2121`**: по `today` и `period.from` строит пару WTD/MTD↔prior (`form_id` `wtd`/`mtd`/`explicit`); при `ASK_ENTITY_FORM` + гейт B без `period2` пару не разворачивает.
4. **Резолв kind** (`entity_form_catalogs_for_kind:2135–2156`, `entity_form_movements_for_kind:2170–2196`): stem/label SQL по `TABLES`+`search_entity_alias`; пусто и `allow_meaning` → `meaning_candidates`.
5. **Гейт A** (`entity_form_count_target_is_movement:2204–2234`): `want`∈{count,""} и kind→движение → True (F закрыта).
6. **`entity_form_expand_pool:2237–2257`**: +каталоги kind + sales-holders осей (`holders_of_target`).
7. **`entity_form_applicable:2281–2305`**: F открыта при count + catalog + sales; без периода — только если в сыром пуле уже есть движение; гейт A → False.
8. **`entity_form_structs:2441–2493`**: пары `(complement|distinct_axis, meta)`; без окна — только kind→catalog, не product-catalog; product+окно → complement; иначе distinct (±`entity_form_rolling_year:2260–2270`).
9. **`entity_form_pick:2503–2506`**: первый элемент `structs`.
10. **`entity_form_compute:2518–2532`**: `aggregate_distinct_axis` и/или `aggregate` каталога → атом.
11. **`try_entity_form_answer:2540–2567`**: при `when=="pre_entity"` — `entity_form_pre_entity_ok` (один early-класс, `form_n==1`); иначе первый struct → ответ dict.
12. **`aggregate_compare_sales:2572–2594`**: две `aggregate` → `sum = s1−s2`, `form=compare`.
13. Вспомогательные: `entity_form_collapse_guard:2308–2321`, `entity_form_pre_entity_ok:2324–2338`, атомы `2341–2370`, ось `entity_form_axis_on_sales:2403–2432`.

## Выходы

- `try_entity_form_answer` → `None` или `{"kind":"answer","text",…,"atom","atoms","diag",…}` (`2564–2567`). Потребители вне участка: `answer` при `when="pre_entity"` (`12644–12651`) и без when (`13315–13320`) — ранний `return`.
- `entity_form_pick` → `(form, meta)` или `(None, {})` (`2504–2506`).
- `entity_form_structs` → список пар; `entity_form_compute` → атом или `None`.
- `entity_form_collapse_guard` → `action` `none`|`resolve_early`|`skip` (+`fork_outcome_skipped`); потребитель `13347–13355`.
- `sales_compare_intent` / `sales_compare_windows` → bool / `(period, period2, form_id)`; вместе с `aggregate_compare_sales` — путь compare в `answer` (`14316–14348`).
- `aggregate_compare_sales` → dict с `sum`=diff, `form=compare`, `compare_base`/`compare_other` или `None`.

## Обращения наружу

| Что | Место | Назначение |
|---|---|---|
| SQL `SELECT t.src_table … catalog_%` + `ts_lexize`/`list_has_any` | `entity_form_catalogs_for_kind:2136–2144` | kind→каталоги |
| SQL то же для `document_%`/`accumulationregister_%` | `entity_form_movements_for_kind:2170–2180` | kind→движения (гейт A) |
| SQL `count(DISTINCT map_extract_value(refs_map,…)) FILTER (≠IsFolder)` | `aggregate_distinct_axis:2387–2390` | distinct по оси |
| `aggregate(...)` (SQL внутри функции вне участка) | `entity_form_compute:2525`; `aggregate_compare_sales:2574–2575` | \|catalog\|; две суммы для diff |
| `meaning_candidates` | `2153`, `2190` | запасной резолв src при пустом stem SQL |
| `holders_of_target` / `refcols_of` / `_measures_by_src` | `2248–2256`, `2414–2430` | оси и канон sales-регистра |
| HTTP | нет | — |
| Вызов языковой модели | нет | — |

## Переключатели

- `ASK_ENTITY_FORM`: `os.environ.get("ASK_ENTITY_FORM","0")=="1"` (определение `1431`; чтение в участке `2001`, `2048`, `2095`, `2204`, `2281`, `2540`). Умолч. выкл. (`"0"`). Без флага: rank/compare идут веткой `elif rank_intent_from` (`2052–2053`); F-функции сразу False/`None`/`[]`.
- Иных env, читаемых внутри `1995–2594`, нет. `ROWS_TO_MODEL` / `STEM_DICT` / `MEANING_TOP` задаются вне участка и используются здесь.

## Развилки

- `ASK_ENTITY_FORM` off → весь F и гейт B не работают; compare-intent без суперлатива режется только `rank_intent_from`.
- Гейт B + одно окно → не compare (`2050–2051`), `sales_compare_windows` не строит пару (`2097–2101`).
- Гейт A (kind→движение) → `entity_form_applicable` False (`2289–2290`).
- Нет catalog+sales после expand → F закрыта (`2300–2301`).
- Нет явного period и нет movement в сыром пуле → F закрыта (`2303–2305`).
- Без окна: нет kind→catalog / все product-catalog → `structs=[]` (`2459–2467`); product+окно → `complement`, иначе `distinct_axis` (+rolling year) (`2478–2492`).
- `when=="pre_entity"` и (`early_classes>1` или `form_n≠1`) → `None` (`2546–2549`).
- Пустой atom / `exact_value is None` / пустой text → `None` (`2552–2556`).
- `aggregate_compare_sales`: нет src/measure, нет обеих агрегатов или sum → `None` (`2572–2580`).
- `entity_form_collapse_guard`: early_classes>1 и arb_pool_len≤1 → `resolve_early` если form_applicable, иначе `skip` (`2317–2321`).

## Чего здесь нет

- HTTP, LLM, OData, запись в БД.
- Rank/top-N ответа (только гейт, отделяющий от compare).
- Выбора между несколькими формами (берётся `structs[0]`; clarify при len>1 — только отказ на `pre_entity`).
- Сборки `intent`/`pool`/`match` (приходят снаружи).
- Рендера графиков, памяти выбора (`memory_eligible: False` жёстко, `2566`).
- Самого вызова из HTTP-хендлера — только функции; оркестрация в `answer` вне участка.
