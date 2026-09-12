# W1: карта живости `ask/z16_veto_pick_entity.py`

Срез: 12.09.2026. Код не менялся. Поиск по фактическим именам в общем
namespace (`ask/*.py`, новый/legacy z20, `test_*.py`, `_bootstrap`/`_imports`/`_wire`);
учтены вызовы, getattr/строковые имена и f-строки.

Файл зоны: 625 строк; верхнеуровневых символов: 28 (сумма тел **559** строк;
остальное — модульный docstring, импорты, `apply_bindings`, `register_zone`, пустые строки).

Загрузка: `_bootstrap.py` → `_ZONE_FILES` включает `z16_veto_pick_entity.py`
(после z15, до z17). z20 выбирается флагом `ASK_ONEPATH` (`z20_ask_main_http.py`
vs `z20_ask_main_http_legacy.py`). `_imports.py` / `_wire.py` символов зоны не
упоминают — только общий `register_zone` / `apply_bindings`.

⚠️ Перекрытие имён: z02 тоже определяет `_NON_DATA_MARKERS` и
`question_expects_accounting_data`. z16 грузится **позже** и **перезаписывает**
оба имени в общем пространстве. Живой runtime-символ — версия z16 (маркеры
байт-в-байт те же; тело `question_expects_*` у z02 богаче и после загрузки z16
по имени недоступно).

---

## Таблица символов

| символ | строки | кто зовёт (файл:строка) | вердикт |
|---|---|---|---|
| `pair_slots_only` | 9–11 (3) | **зоны:** `z18_compose.py:646` (`compose`). **новый z20:** транзитивно ← `compose` ← `z20_ask_main_http.py:1699,1745`. **legacy:** тот же `compose` ← legacy `:4109,4186`. тесты — нет | **ЖИВА НОВОМУ** |
| `atom_whitelist_labels` | 14–23 (10) | прод/зоны/z20 — нет. **тесты:** `test_answer_atom.py:148` | **МЁРТВА** |
| `atom_whitelist_numbers` | 26–42 (17) | прод/зоны/z20 — нет. **тесты:** `test_answer_atom.py:150` | **МЁРТВА** |
| `arbiter_figures` | 45–51 (7) | прод/зоны/z20 — нет. **тесты:** `test_step4_guards.py:170,202,204`; `test_gate.py:306` | **МЁРТВА** |
| `alias_supported` | 54–122 (69) | прод/зоны/z20 — нет (в `z08_measures_totals.py:114` только комментарий). **тесты:** `test_step4_guards.py` (много) | **МЁРТВА** |
| `not_for_excludes` | 125–160 (36) | **legacy:** `z20_ask_main_http_legacy.py:2203` (коммент `:864`). новый z20 — нет. **тесты:** `test_step4_guards.py:301+` | **ЖИВА ТОЛЬКО LEGACY** |
| `pair_unanswered` | 163–173 (11) | прод/зоны/z20 — нет. **тесты:** `test_step4_guards.py:322+` | **МЁРТВА** |
| `single_is_rival` | 176–184 (9) | прод/зоны/z20 — нет. **тесты:** `test_step4_guards.py:294,332+` | **МЁРТВА** |
| `veto_top_without` | 187–195 (9) | прод/зоны/z20 — нет. **тесты:** `test_step4_guards.py:342+` | **МЁРТВА** |
| `figures_numbers` | 198–215 (18) | только внутри зоны ← `mute_measure_blocks:442,448`. внешних зовов нет. **тесты:** `test_step4_guards.py:47+` | **МЁРТВА** |
| `same_number` | 218–242 (25) | только внутри ← `mute_measure_blocks:448`. **тесты:** `test_step4_guards.py:66+` | **МЁРТВА** |
| `src_supports_question` | 246–306 (61) | **legacy:** `:3488`. внутри ← `any_live_src_supports_question`. новый — нет. **тесты:** `test_k4_clarify_vs_nodata.py:40+` | **ЖИВА ТОЛЬКО LEGACY** |
| `any_live_src_supports_question` | 309–320 (12) | никто снаружи (обёртка не подключена) | **МЁРТВА** |
| `_NON_DATA_MARKERS` | 323–326 (4) | внутри ← `question_expects_accounting_data:336`; также runtime-lookup у z02 `_creative_non_data_question` после перекрытия. новый тракт тянет через `question_expects_*` | **ЖИВА НОВОМУ** |
| `question_expects_accounting_data` | 329–356 (28) | **зоны:** `z21_wiki_choice.py:907` (`try_wiki_hybrid_entity_pick`). **новый z20:** транзитивно ← `wiki_primary_entity_cascade:855` ← `z20_ask_main_http.py:1951`. **legacy:** прямо `:1868` + тот же wiki-каскад `:2513`. внутри ← `src_supports_question:299`. **тесты:** stubs в wiki/stock tests; `test_intent.py`, `test_k4_clarify_vs_nodata.py` | **ЖИВА НОВОМУ** |
| `canon_claims_question` | 359–375 (17) | **legacy:** `:1628`, `:1866`. новый — нет. **тесты:** `test_k4_clarify_vs_nodata.py:136+`; stub `test_stock_balance_path.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `kind_has_corpus_support` | 378–395 (18) | **legacy:** `:1865`. внутри ← `src_supports_question:297`. новый — нет. **тесты:** stub `test_stock_balance_path.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `measure_class_alts` | 398–410 (13) | **legacy:** `:3390`, `:3499`. новый — нет. **тесты:** `test_k4_guess_vs_clarify.py`, `test_k4_clarify_vs_nodata.py`, `test_k4_axis_and_names.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `unresolved_quantity` | 413–432 (20) | **legacy:** `:3370`. коммент в `z09:188`. новый — нет. **тесты:** `test_measure_menu_not_silent.py`, `test_measure_hatch_luk.py`, `test_step4_guards.py`, `test_k4_guess_vs_clarify.py` | **ЖИВА ТОЛЬКО LEGACY** |
| `mute_measure_blocks` | 435–450 (16) | прод/зоны/z20 — нет. **тесты:** `test_step4_guards.py:285+` | **МЁРТВА** |
| `measure_row_all_zero` | 453–460 (8) | **legacy:** `:3442`, `:3445`. внутри ← `alive_measure_names:465` | **ЖИВА ТОЛЬКО LEGACY** |
| `alive_measure_names` | 463–465 (3) | только внутри ← `filter_dead_measure_alts:475` (тот — legacy) | **ЖИВА ТОЛЬКО LEGACY** |
| `filter_dead_measure_alts` | 468–476 (9) | **legacy:** `:3436` | **ЖИВА ТОЛЬКО LEGACY** |
| `measure_asked_explicitly` | 479–487 (9) | **legacy:** `:3447` | **ЖИВА ТОЛЬКО LEGACY** |
| `format_measure_empty_pivot` | 490–508 (19) | только внутри ← `build_measure_empty_pivot:520` | **ЖИВА ТОЛЬКО LEGACY** |
| `build_measure_empty_pivot` | 511–564 (54) | **legacy:** `:3450` | **ЖИВА ТОЛЬКО LEGACY** |
| `measure_ambiguous` | 567–583 (17) | **legacy:** `:3333`, `:3511` (+ присвоения ключа diag `"measure_ambiguous"`). **зоны:** `z09_fork_detector.py:850` (`_fork_headline_measure` ← `_fork_atom_of` ← `fork_detector_scan` / `ordered_fork_classes`); эти корни зовутся из **legacy** (`:2380,:2924`), из нового z20 — **нет**. **тесты:** step4 / measure_menu / hatch / gate | **ЖИВА ТОЛЬКО LEGACY** |
| `pick_measure` | 586–622 (37) | **legacy:** `:3337` (комменты `:2215,:2304,:3272,:3321`). новый — нет; в `test_one_path.py` имя в `B4_FORBIDDEN`. **тесты:** `test_measure_menu_not_silent.py`, `test_k4_guess_vs_clarify.py`, `test_compose.py` (stub) | **ЖИВА ТОЛЬКО LEGACY** |

---

## Итог зоны

| вердикт | символов | строк тел |
|---|---|---|
| **ЖИВА НОВОМУ** | 3 (`pair_slots_only`, `_NON_DATA_MARKERS`, `question_expects_accounting_data`) | **35** |
| **ЖИВА ТОЛЬКО LEGACY** | 14 | **321** |
| **МЁРТВА** | 11 | **203** |
| **всего символов** | 28 | **559** |

Вердикт по зоне: **почти вся зона — legacy/мёртвая армия вето-арбитра и выбора меры.**
Одному пути нужны **~6%** строк зоны (35/559): слот-гард compose и страж
«вопрос про учёт» на пустом wiki-пуле. После flip и сноса legacy остаётся
жить только эта тонкая полоска (+ замки тестов на мёртвые символы, если их
не снимут).

---

## Транзитивные цепочки

### До нового z20 (`z20_ask_main_http.py`)

1. `pair_slots_only` ← `compose` (`z18:646`) ← `answer` compose-хвост (`:1699`, `:1745`)
2. `question_expects_accounting_data` ← `try_wiki_hybrid_entity_pick` (`z21:907`) ← `wiki_primary_entity_cascade` (`z21:855`) ← `answer` (`:1951`)
3. `_NON_DATA_MARKERS` ← `question_expects_accounting_data` ← (цепочка 2)

Прямых вызовов имён z16 из нового z20: **0**.

### До legacy z20

1. `not_for_excludes` ← legacy `:2203`
2. `question_expects_accounting_data` ← legacy `:1868` (+ wiki-каскад как у нового)
3. `canon_claims_question` ← `:1628`, `:1866`
4. `kind_has_corpus_support` ← `:1865`
5. `pick_measure` ← `:3337`
6. `measure_ambiguous` ← `:3333`, `:3511`
7. `unresolved_quantity` ← `:3370`
8. `measure_class_alts` ← `:3390`, `:3499`
9. `filter_dead_measure_alts` ← `:3436`
10. `measure_row_all_zero` ← `:3442`, `:3445`
11. `measure_asked_explicitly` ← `:3447`
12. `build_measure_empty_pivot` ← `:3450` ← `format_measure_empty_pivot`
13. `src_supports_question` ← `:3488` ← (`kind_has_corpus_support`, `question_expects_*` внутри)
14. `measure_ambiguous` ← `_fork_headline_measure` (`z09:850`) ← `_fork_atom_of` ← `fork_detector_scan` ← legacy `:2380`, `:2924`  
    (и ← `ordered_fork_classes` в z13 — без корня в новом z20)

### Никуда (только тесты / внутренние мёртвые)

`atom_whitelist_*`, `arbiter_figures`, `alias_supported`, `pair_unanswered`,
`single_is_rival`, `veto_top_without`, `figures_numbers`, `same_number`,
`mute_measure_blocks`, `any_live_src_supports_question`.

---

## Скрытые выбиратели и новый тракт

Критерий: функция, **кодом** выбирающая источник / меру / период / ось.

| кандидат в зоне | выбирает | доступен новому? |
|---|---|---|
| `pick_measure` | меру (через `measure_choice` / ask-меню) | **нет** (только legacy; в B4_FORBIDDEN) |
| `unresolved_quantity` | меру при одной имени / меню при >1 | **нет** |
| `measure_class_alts` | коллапс nums → money\|qty | **нет** |
| `measure_ambiguous` + `_fork_headline_measure` | при равных итогах — `sorted(pool)[0]` (молчаливая мера) | **нет** (fork-корень только legacy) |
| `alias_supported` / `not_for_excludes` / `veto_top_without` | вето сущности | **нет** (мёртвы или только legacy) |
| `pair_slots_only` | нет (режим слотов compose) | да, но **не выбиратель** |
| `question_expects_accounting_data` | нет (классификатор учёт/не-учёт) | да, но **не выбиратель** |

**Итог:** скрытых выбирателей источника/меры/периода/оси зона **в новый тракт не тащит**.
Всё, что в зоне действительно выбирает меру или режет сущность, висит на legacy
(и/или мёртво). Новый путь для меры уже зовёт `measure_choice` напрямую
(`z20_ask_main_http.py:1534+`), минуя `pick_measure`.

---

## Замки (тесты), затрагивающие зону

| тест | символы |
|---|---|
| `test_step4_guards.py` | `figures_numbers`, `same_number`, `alias_supported`, `arbiter_figures`, `unresolved_quantity`, `mute_measure_blocks`, `single_is_rival`, `not_for_excludes`, `pair_unanswered`, `veto_top_without` |
| `test_answer_atom.py` | `atom_whitelist_labels`, `atom_whitelist_numbers` |
| `test_gate.py` | `measure_ambiguous`, `arbiter_figures` |
| `test_measure_menu_not_silent.py` | `pick_measure`, `unresolved_quantity` (+ текст зоны) |
| `test_measure_hatch_luk.py` | `unresolved_quantity`, `measure_ambiguous` |
| `test_k4_clarify_vs_nodata.py` | `src_supports_question`, `question_expects_*`, `canon_claims_question`, `measure_class_alts` |
| `test_k4_guess_vs_clarify.py` / `test_k4_axis_and_names.py` | `measure_class_alts`, `pick_measure`, `unresolved_quantity` |
| `test_intent.py` | `question_expects_accounting_data` |
| `test_one_path.py` | запрет `pick_measure` в B4 |
| wiki/stock stubs | подмена `question_expects_*` / `kind_has_corpus_*` / `canon_claims_*` |

---

## `_bootstrap` / `_imports` / `_wire`

- `_bootstrap.py:39` — имя файла в `_ZONE_FILES`; символов зоны нет.
- `_imports.py`, `_wire.py` — упоминаний символов z16 нет.
