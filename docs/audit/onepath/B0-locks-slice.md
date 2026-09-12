# B0: redirect grep-замков на legacy + срез зелёных/красных

Срез: 12.09 (после коммита 98cf63c: `z20_ask_main_http.py` →
`z20_ask_main_http_legacy.py`). Код зон / новый `z20_ask_main_http.py` не
трогались. Git не вызывался. База не трогалась.

## Что сделано

Grep по `ubuntu/serenedb/**/*.py` на строку `z20_ask_main_http.py` (не
`_legacy`). Найдено **13** замков + комментарий в самом legacy (не трогали).

В каждом замке путь заменён на `z20_ask_main_http_legacy.py` (только строка
пути / `path.name`). Остальное в тестах не менялось.

| Файл | Было → стало |
|---|---|
| `test_measure_menu_not_silent.py` | `ASK / "…http.py"` → `…_legacy.py` |
| `test_no_pre_wiki_reorders.py` | то же |
| `test_measure_hatch_luk.py` | то же |
| `test_sales_canon_prefer.py` | то же |
| `test_axis_count_plain.py` | `ROOT / "ask" / "…http.py"` → legacy |
| `test_wiki_leader_not_overridden.py` | то же |
| `test_wiki_card_hybrid.py` | то же |
| `test_enough.py` | `Z20 = …http.py` → legacy |
| `test_final_stock_route_filters_absent.py` | то же |
| `test_early_clarify_atom_fps_hashable.py` | то же |
| `test_rank_leader_path.py` | `"ask/…http.py"` → legacy |
| `test_ask_choice_memory.py` | `join(…, "…http.py")` → legacy |
| `test_zone_names_resolvable.py` | `path.name == "…http.py"` → `…_legacy.py` (как в `_bootstrap.py`) |

Повторный grep: в `test_*.py` старого имени нет. Единственное оставшееся
упоминание — комментарий в `ask/z20_ask_main_http_legacy.py` («новый тракт
пишется в z20_ask_main_http.py») — корректно, не правили.

## Таблица среза

Прогон: `cd ubuntu/serenedb && timeout 120 python3 test_<имя>.py`.
«До» числом не снимали в этой сессии (после rename без redirect замки с
чтением диска упали бы на `FileNotFoundError`). Ориентир «ожидались
зелёными» — список задачи B0 / O5 §1.

| Замок | До (если знал) | После redirect | Зелёных/красных | Вывод |
|---|---|---|---|---|
| `test_zone_names_resolvable` | ожид. зелёный; путь обновлён | EXIT=0 | **99/0** | зелёный |
| `test_enough` | ожид. зелёный; путь обновлён | EXIT=0 | **10/0** | зелёный |
| `test_ask_choice_memory` | ожид. зелёный; путь обновлён | EXIT=0 | **45/0** | зелёный |
| `test_sales_canon_prefer` | ожид. зелёный; путь обновлён | EXIT=0 | **29/0** | зелёный |
| `test_rank_leader_path` | ожид. зелёный; путь обновлён | EXIT=0 | **30/0** | зелёный |
| `test_wiki_card_hybrid` | ожид. зелёный; путь обновлён | EXIT=0 | **65/0** | зелёный |
| `test_early_clarify_atom_fps_hashable` | ожид. зелёный; путь обновлён | EXIT=0 | **9/0** | зелёный |
| `test_final_stock_route_filters_absent` | путь обновлён; z20 читается | EXIT=1 | **13/1** | красный **не из-за rename** (см. ниже) |
| `test_no_pre_wiki_reorders` | ожид. зелёный; путь обновлён | EXIT=0 | **39/0** | зелёный |
| `test_measure_menu_not_silent` | ожид. зелёный; путь обновлён | EXIT=0 | **14/0** | зелёный |
| `test_wiki_leader_not_overridden` | ожид. зелёный; путь обновлён | EXIT=0 | **24/0** | зелёный |
| `test_axis_count_plain` | ожид. зелёный; путь обновлён | EXIT=0 | **13/0** | зелёный |
| `test_measure_hatch_luk` | ожид. зелёный; путь обновлён | EXIT=0 | **15/0** | зелёный |
| `test_measure_menu` | — | **файла нет** | — | пропуск (нет `test_measure_menu.py`) |
| `test_verify_threshold_menu` | ожид. зелёный; z20-путь не читал | EXIT=0 | **4/0** | зелёный |
| `test_named_type_filter` | ожид. зелёный; z20-путь не читал | EXIT=0 | **16/0** | зелёный |
| `test_compose` | ожид. зелёный; z20-путь не читал | EXIT=0 | **92/0** | зелёный |
| `test_ask_journal` | ожид. зелёный; z20-путь не читал | EXIT=0 | **11/0** | зелёный (live skip: движок не отвечает) |
| `test_ask_embed_native` | живой эмбеддер | EXIT=1 | crash до счётчика | красный **был до** (эмбеддер); не rename |
| `test_fork_outcomes` | ожид. зелёный; z20-путь не читал | EXIT=0 | **53/0** | зелёный |

**Итого прогнанных:** 19 файлов (1 отсутствует).
**Зелёных EXIT=0:** 17. **Красных:** 2 (оба не из-за redirect).

## Упавшие (хвост вывода ≤15 строк)

### `test_final_stock_route_filters_absent` — был красный до (не rename)

Redirect сработал: есть `ok - z20 readable` и окна route без stock-фильтров.
Единственный FAIL — логический якорь `plan={} kept before K6`, не путь файла.
Не чинили.

```
ok  - answer window non-empty
ok  - no stock_bypass_empty_by in z20
ok  - route window: no filter_stock_balance_sales_noise
ok  - route window: no filter_stock_goods_registers
ok  - route window: no prefer_entity_for_stock
ok  - route window: no stock_question_engaged
ok  - post-cands route: no filter_stock_balance_sales_noise
ok  - post-cands route: no filter_stock_goods_registers
ok  - post-cands route: no prefer_entity_for_stock
FAIL- plan={} kept before K6 
ok  - orphan filter_stock_balance_sales_noise lives in tree
ok  - orphan filter_stock_goods_registers lives in tree
ok  - orphan prefer_entity_for_stock lives in tree
PASS 13 FAIL 1
EXIT=1
```

### `test_ask_embed_native` — был красный до (живой эмбеддер)

Падает на `embed_one` до итогового счётчика. К пути z20 не относится.
Не чинили.

```
ok  - ASK_EMBED_NATIVE exists
ok  - default ASK_EMBED_NATIVE off
Traceback (most recent call last):
  File "/srv/1c/ubuntu/serenedb/test_ask_embed_native.py", line 101, in <module>
    vec = A.embed_one("тестовый вопрос")
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/srv/1c/ubuntu/serenedb/ask/z01_infra_trace_llm.py", line 789, in embed_one
    raise RuntimeError("эмбеддер недоступен: %s" % type(last).__name__)
RuntimeError: эмбеддер недоступен: KeyError
EXIT=1
```

## Вывод B0

1. Все grep-якоря на старое имя файла переведены на
   `z20_ask_main_http_legacy.py` (13 файлов).
2. Замки, которые читают диск z20, после redirect снова зелёные (кроме
   `test_final_stock_route_filters_absent` — 1 логический FAIL, не путь).
3. Сырой журнал прогонов: `.claude/state/b0-locks/*.out`.
4. Дальше (оркестратор): приёмка / коммит пат-спеком — вне этой задачи.
)