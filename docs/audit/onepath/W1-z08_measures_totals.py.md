# W1: карта живости `ask/z08_measures_totals.py`

Срез: 12.09. Только чтение кода. Код/git/БД не трогались. Чужие
отчёты `onepath/` не читались.

Источник: `ubuntu/serenedb/ask/z08_measures_totals.py` (278 строк файла;
136 строк в определениях верхнего уровня). Загрузка: `_bootstrap.py`
ставит файл в `_ZONE_FILES` → `register_zone('ask.z08_measures_totals', …)`.
Имена живут в общем namespace (`_wire.apply_bindings`); импортов зон нет.
Поиск: `ask/*.py` + оба z20 + `test_*.py`; учтены прямые вызовы и
транзитивные цепочки до корня z20.

---

## Итог зоны

| Вердикт | Символов | Строк определений |
|---|---:|---:|
| **ЖИВА НОВОМУ** | 25 | **124** |
| **ЖИВА ТОЛЬКО LEGACY** | 5 | **5** |
| **МЁРТВА** | 7 | **7** |
| Файл всего | — | 278 (вкл. комментарии/пустоты/`register_zone`) |

**Вердикт зоны: нужна одному пути.** Ядро мер (`measures_of` /
`measure_aliases_of` / `totals_of`) зовётся новым z20 прямо; резолверные
и RRF-константы + `_shares_chars` + `MEANING_TOP` — транзитивно через
`probe` → `resolve_values` и через `kind_axis_hits` /
`live_axis_col_for_count` → `meaning_candidates`. После flip и сноса
legacy останутся мёртвыми только 5 строк fork/skip-флагов и 7 строк
неиспользуемых констант — зона целиком не выкидывается.

---

## Таблица символов

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_shares_chars` | 18 | **новый:** транзитивно `z20_ask_main_http.py` → `probe` → `resolve_values` → `z07_rrf_vectors.py:540`. **legacy:** тот же путь + комментарии `z20_…_legacy.py:1932`, `z16:261` (не вызов). **тесты:** `test_k4_clarify_vs_nodata.py` | **ЖИВА НОВОМУ** |
| `ALIAS_TOP` | 1 | никто (только определение) | **МЁРТВА** |
| `ALIAS_INDEX` | 1 | `z06_entity_search.py:436-437` (`alias_hits`); `z07_rrf_vectors.py:59` (`_rrf_entity_branches`). Цепочка до **нового** z20: см. `MEANING_TOP` / `meaning_candidates` | **ЖИВА НОВОМУ** |
| `CARD_INDEX` | 1 | `z06:477-478`; `z07:64` — то же | **ЖИВА НОВОМУ** |
| `CARD_FIELDS` | 1 | `z06:472`; `z07:65` — то же | **ЖИВА НОВОМУ** |
| `RRF_K` | 1 | `z07:96`, `z07:112` (`_fused_*_rrf`) ← `meaning_candidates` | **ЖИВА НОВОМУ** |
| `ASK_SQL_RRF` | 1 | `z07:147` ← `_fused_candidates` ← `meaning_candidates` | **ЖИВА НОВОМУ** |
| `CORPUS_IVF_IDX` | 1 | `z07:19`, `z07:89` ← `_corpus_ivf_ready` / corpus-ветвь RRF | **ЖИВА НОВОМУ** |
| `_CORPUS_IVF_CACHE` | 1 | `z07:11`, `z07:22` | **ЖИВА НОВОМУ** |
| `ASK_RESOLVER_IVF` | 1 | `z07:514` (`resolve_values`) ← `probe` ← **новый** z20 | **ЖИВА НОВОМУ** |
| `RESOLVER_IVF_IDX` | 1 | `z07:41`, `z07:518` | **ЖИВА НОВОМУ** |
| `_RESOLVER_IVF_CACHE` | 1 | `z07:33`, `z07:44` | **ЖИВА НОВОМУ** |
| `ALIAS_VETO` | 1 | только тело `alias_supported` (`z16:86`); `alias_supported` **не** зовётся ни новым, ни legacy z20 — только `test_step4_guards.py` | **МЁРТВА** (рантайм трактов) |
| `PROBE` | 1 | никто в ask (тест-имена «PROBE …» — про `AB_PROBE`, не этот символ) | **МЁРТВА** |
| `SKIP_SERVICE_RIVALS` | 1 | только `z20_ask_main_http_legacy.py:2686,2824,2842` | **ЖИВА ТОЛЬКО LEGACY** |
| `ALIAS_BY_CONCEPTS` | 1 | никто | **МЁРТВА** |
| `VETO_NEEDS_RANK` | 1 | `z16:108` ← `alias_supported` ← только тесты | **МЁРТВА** |
| `VETO_HEAD_WINS` | 1 | `z16:91` ← то же; тесты `test_step4_guards.py` | **МЁРТВА** |
| `MEANING_TOP` | 2 | `z05:332,369`; `z17:463` (`kind_axis_hits`); `z20_…_legacy.py:2004,2034`. **Новый:** `z20_ask_main_http.py:1593` → `kind_axis_hits`; `:2169` → `live_axis_col_for_count` → … → `meaning_candidates(..., MEANING_TOP)` | **ЖИВА НОВОМУ** |
| `measures_of` | 31 | **новый прямо:** `z20_ask_main_http.py:1508` (`_settle_measure`). **новый транзитивно:** `:2159` → `aggregate_stock_net_distinct` → `_stock_qty_measure_name` (`z12:947`); `:1828` → `_unit_for_measure` (`z18:357`); `measure_label_of` (`z18`←z20). **legacy:** множество мест `:3284…3669`. **зоны:** `z12:947,1192`; `z16:610` (`pick_measure`, только legacy); `z18:357`. **тесты:** `test_k4_guess_vs_clarify`, `test_stock_balance_path`, `test_compose`, `test_measure_menu_not_silent` (grep) | **ЖИВА НОВОМУ** |
| `measure_aliases_of` | 10 | **новый прямо:** `z20:1488,1509`. **новый транзитивно:** `_unit_for_measure` / `measure_label_of` / stock qty. **legacy:** `:3311…3705`. **зоны:** `z12:953`; `z16:516,612`; `z18:360,459`; `z09:872` (только fork-путь legacy). **тесты:** те же + `test_measure_empty` | **ЖИВА НОВОМУ** |
| `totals_of` | 44 | **новый прямо:** `z20_ask_main_http.py:2104` (одна мера). **legacy:** `:3332…3693`. Комментарии в z06/z09/z16/z17 — не вызовы. **тесты:** `test_one_path.py` (имя в списке), `test_measure_menu_not_silent`, `test_compose` | **ЖИВА НОВОМУ** |
| `FORK_DETECT` | 1 | только `z20_…_legacy.py:2360,2900`. **тесты:** `test_stock_balance_path` (глушит) | **ЖИВА ТОЛЬКО LEGACY** |
| `FORK_OUTCOMES` | 1 | только `z20_…_legacy.py:2693,2751,2900`. **тесты:** `test_fork_outcomes.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `ASK_JOURNAL` | 1 | **новый:** `z20:2457` (`_ask_journal_write`); **legacy:** `:4605`. **тесты:** `test_ask_journal`, `test_journal_fields`, `test_trace_rid` | **ЖИВА НОВОМУ** |
| `_JOURNAL_LOST` | 1 | **новый:** `z20:2456,2531,2566-2567`; **legacy:** зеркало `:4604…` | **ЖИВА НОВОМУ** |
| `ASK_CHOICE_MEMORY` | 1 | `z14_clarify_memory.py:580` (`attach_memory_shadow`) ← **новый** `z20:2870,2885` и legacy `:5021,5036`. **тесты:** `test_ask_choice_memory` | **ЖИВА НОВОМУ** |
| `ASK_MEMORY_APPLY` | 1 | символ в ask никто не читает (в `ask_choice_mem.py` — только текст в docstring; env не через этот binding) | **МЁРТВА** |
| `_MEMORY_LOST` | 1 | `z14:575-583` ← `attach_memory_shadow` ← оба z20 | **ЖИВА НОВОМУ** |
| `_JOURNAL_KEEP` | 1 | **новый** `z20:2261-2273`; **legacy** `:4409-4421` | **ЖИВА НОВОМУ** |
| `_JOURNAL_CODE_MD5` | 1 | **новый** `z20:2277-2283`; **legacy** `:4425-4431` | **ЖИВА НОВОМУ** |
| `_JOURNAL_ALIAS_VER` | 1 | **новый** `z20:2301-2313`; **legacy** `:4449-4461` | **ЖИВА НОВОМУ** |
| `_JOURNAL_BUILD_TS` | 1 | **новый** `z20:2287-2297`; **legacy** `:4435-4445` | **ЖИВА НОВОМУ** |
| `_JOURNAL_BUILD_TS_AT` | 1 | **новый** `z20:2287,2289,2296`; **legacy** зеркало | **ЖИВА НОВОМУ** |
| `_FORK_MEAS_TTL` | 1 | `z09:113` (`_measures_by_src`) ← только legacy `z20_…_legacy.py:2375,2919` | **ЖИВА ТОЛЬКО LEGACY** |
| `_fork_meas_cache` | 1 | `z09:112-125` ← то же | **ЖИВА ТОЛЬКО LEGACY** |

---

## `_bootstrap` / `_imports` / `_wire`

| Файл | Связь с зоной |
|---|---|
| `_bootstrap.py:31` | имя файла в `_ZONE_FILES` — зона грузится всегда (и при ASK_ONEPATH=1) |
| `_imports.py` | символов z08 нет; общий `from ask._imports import *` внутри зоны |
| `_wire.py` | `register_zone` / `apply_bindings` — инфраструктура, не знает имён z08 |

getattr / f-строки / словари с именами символов z08 как вызываемых — **не найдены**.

---

## Транзитивные цепочки (до корня z20)

### Живы новому

1. `measures_of` ← `_settle_measure` ← `answer` ← **новый z20**
2. `measure_aliases_of` ← `_settle_measure` / `_measure_menu_opts` ← **новый z20**
3. `totals_of` ← SQL-ступень `answer` ← **новый z20**
4. `measures_of` / `measure_aliases_of` ← `_unit_for_measure` / `measure_label_of` ← compose-хвост ← **новый z20**
5. `measures_of` / `measure_aliases_of` ← `_stock_qty_measure_name` ← `stock_net_register_pair` ← `aggregate_stock_net_distinct` ← **новый z20**
6. `_shares_chars`, `ASK_RESOLVER_IVF`, `RESOLVER_IVF_IDX`, `_RESOLVER_IVF_CACHE` ← `resolve_values` ← `probe` ← **новый z20**
7. `MEANING_TOP`, `ALIAS_INDEX`, `CARD_INDEX`, `CARD_FIELDS`, `RRF_K`, `ASK_SQL_RRF`, `CORPUS_IVF_IDX`, `_CORPUS_IVF_CACHE` ← `meaning_candidates` / `_fused_candidates` / `alias_hits`/`card_hits` ← `kind_axis_hits` **и/или** `entity_form_catalogs_for_kind` ← `_pick_kind_axis_col` ← `live_axis_col_for_count` / `count_defer_measure_clarify` ← **новый z20** (также прямой `kind_axis_hits` в `_settle_axis`)
8. `ASK_JOURNAL`, `_JOURNAL_*` ← `_ask_journal_write` / `_journal_*` ← **новый z20**
9. `ASK_CHOICE_MEMORY`, `_MEMORY_LOST` ← `attach_memory_shadow` ← **новый z20**

### Только legacy

1. `FORK_DETECT` / `FORK_OUTCOMES` ← ветки арбитра/детектора ← **legacy z20**
2. `SKIP_SERVICE_RIVALS` ← отсев служебных соперников ← **legacy z20**
3. `_FORK_MEAS_TTL` / `_fork_meas_cache` ← `_measures_by_src` ← `fork_detector_scan` ← **legacy z20**
4. `measure_aliases_of` (доп. путь) ← `_fork_headline_measure` ← fork-классы ← **legacy only** (новый fork_detector_scan не зовёт)

### Мёртвые для обоих трактов

`ALIAS_TOP`, `PROBE`, `ALIAS_BY_CONCEPTS`, `ASK_MEMORY_APPLY`, `ALIAS_VETO`, `VETO_NEEDS_RANK`, `VETO_HEAD_WINS` (последние три — только оффлайн `alias_supported` в тестах).

---

## Скрытые выбиратели, доступные новому тракту

Сами `measures_of` / `measure_aliases_of` / `totals_of` — **не выбиратели**: читают величины/алиасы/итоги из данных по уже выбранному `src` (или считают SQL по переданному списку мер).

**Да, зона тащит в новый тракт инфраструктуру скрытого выбора сущности/оси:**

| Механизм | Как попадает в новый z20 | Что выбирает |
|---|---|---|
| `MEANING_TOP` + `ALIAS_INDEX` / `CARD_*` / `RRF_K` / `ASK_SQL_RRF` / `CORPUS_IVF_*` | `kind_axis_hits` / `live_axis_col_for_count` → `meaning_candidates` → RRF/alias/card | кандидатов `catalog_*` / сущностей для оси (смысловой мост), без вопроса человеку |
| `_shares_chars` + `ASK_RESOLVER_IVF` / `RESOLVER_IVF_*` | `probe` → `resolve_values` | не ось/меру/период, а **значения** слова вопроса (гарда от мусора); отбор кандидатов резолвера |

Не тащат в новый (только legacy / мёртвые): `FORK_DETECT`/`FORK_OUTCOMES`/`SKIP_SERVICE_RIVALS`/`_fork_meas_*`, `ALIAS_VETO`/`VETO_*`, `ALIAS_TOP`/`PROBE`/`ALIAS_BY_CONCEPTS`/`ASK_MEMORY_APPLY`.

Выбор меры в новом тракте идёт через `_settle_measure` + `measure_choice`/`resolve_measure` (z14) на списке из `measures_of` — это уже не «скрытый выбиратель источника кодом» зоны z08, а меню/билет; при >1 мере новый путь отдаёт options, а не silent pick.

---

## Тесты (замки), задевающие символы зоны

| Тест | Символы / роль |
|---|---|
| `test_one_path.py` | имя `totals_of` в контракте |
| `test_measure_menu_not_silent.py` | grep `totals_of`/`measures_of` на legacy-пути |
| `test_compose.py` | stubs `measures_of` / `measure_aliases_of` / `totals_of` |
| `test_k4_guess_vs_clarify.py` | stubs мер |
| `test_k4_clarify_vs_nodata.py` | `_shares_chars` |
| `test_stock_balance_path.py` | stubs мер; глушит `FORK_DETECT` |
| `test_measure_empty.py` | stub `measure_aliases_of` |
| `test_step4_guards.py` | `VETO_*` через `alias_supported` |
| `test_fork_outcomes.py` | `FORK_OUTCOMES` |
| `test_ask_journal.py` / `test_journal_fields.py` / `test_trace_rid.py` | `ASK_JOURNAL` |
| `test_ask_choice_memory.py` | `ASK_CHOICE_MEMORY` |
| `test_resolver_ivf.py` | `ASK_RESOLVER_IVF` / `RESOLVER_IVF_IDX` / `_shares_chars` |
| `test_sql_rrf.py` | `ASK_SQL_RRF` |
| `test_f6_rollout_measure.py` | env-имя `ASK_RESOLVER_IVF` |

---

## Метод

- AST верхнего уровня z08 → 36 символов, суммы строк.
- ripgrep `\bимя\b` по `ask/*.py` и `test_*.py`.
- Для транзитива: BFS вызовов от точек нового z20 (`probe`, `kind_axis_hits`, `live_axis_col_for_count`, `aggregate_stock_net_distinct`, `attach_memory_shadow`, `_ask_journal_write`, `_settle_measure`, …) до символов зоны.
- Комментарии и docstring с именем — не считались вызовом.
)
