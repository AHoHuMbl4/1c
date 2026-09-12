# B3: скелет линейного answer() в новом z20

Срез: 12.09. Источник справки: `z20_ask_main_http_legacy.py` (только чтение).
Новый файл: `ubuntu/serenedb/ask/z20_ask_main_http.py` (не в `_bootstrap` до B6).
Замок: `ubuntu/serenedb/test_one_path.py` (фаза «скелет» O5 §2.6).
Git/база не трогались. Legacy / прочие зоны / прочие test_* не правились.

## Что сделано

1. Линейный `answer()` вместо заглушки B2: intent → readings (без лидера) →
   wiki → coverage-после-wiki → меню окон построителем → SQL-заглушка B4.
2. Helpers: `readings_menu`, `_reading_human_label`, `_readings_to_opts`,
   `_apply_sole_reading`.
3. Скелет замка `test_one_path.py`: (г) + hatch-имена + часть (а).

Билеты `consume_decision` / `seal_clarify` / reissue — уже в перенесённых
`answer_checked` / Handler (B2); в `answer` — `entity_choice_locked` +
`hold_settled_entity` (сырой focus каскад не обходит).

## Карта ступеней скелета

| Ступень | Строки (новый z20) | Дыра O3 / контракт |
|---|---|---|
| Helpers меню прочтений | 1392–1470 | единый построитель; O5 ALLOWED |
| 1. Подготовка: token, шаг, intent, prior/proven period, deadline | 1484–1511 | O3 №13 (точки deadline) |
| 2. Readings z03/z04/z04b → список, без записи лидера в period | 1513–1552 | **№8** (нет silent window leader) |
| calendar_axis_unavailable (инфра) | 1539–1544 | честный unavailable оси |
| 3–5. Wiki / билет; coverage только после | 1554–1613 | **№4**, **№9**, **№14**; wiki = единственный выбор сущности |
| 6. >1 reading → `readings_menu`; ровно 1 → sole | 1615–1635 | **№12** (единственность без ранжира); меню до SQL |
| 7. SQL-заглушка unavailable B4 | 1637–1652 | место SQL/compose (волна B4) |
| 8. Journal | `answer_checked` (без изменений B2) | side-effect как legacy |

Дополнительно закрыто структурой (не отдельной ступенью): нет arb_pool /
early-clarify / code_ambiguous / FORBIDDEN_SELECTORS в новом файле (**№2**-класс
нарушителей не переносится).

## Итоговые числа

| Метрика | Значение |
|---|---|
| Строк нового файла | 2352 (было ~2104 после B2; +~248) |
| `def answer` | 1473–1652 |
| Замок `test_one_path` | 26 проверок |

## Проверки (обязательные)

| # | Проверка | Результат |
|---|---|---|
| 1 | `python3 -m py_compile` z20 + test_one_path | **OK** |
| 2 | `timeout 120 python3 test_one_path.py` | **26/0 зелёные** |
| 3 | Grep-негатив запрещённых имён | **OK** (0 совпадений) |

Запрещённые имена (отсутствуют целиком): `apply_period_leader`,
`prefer_window_leader`, `arb_pool`, `_ec_atom_fps`, `axis_focus_plan`,
`try_entity_form`, `try_event_count_period_clarify`.

FORBIDDEN_SELECTORS (0 call-site): `try_entity_form_answer`,
`try_event_count_period_clarify`, `period_assumed_needs_clarify`,
`axis_focus_plan`, `warehouse_clarify`, `arbitrate`, `_fork_early`,
`fork_outcome_a`, `fork_outcome_b`.

Hatch-имена (0): `measure_hatch`, `_fork_headline`, `_fork_headline_measure`.

Часть (а): в `answer` нет bare `return {..., "kind": "clarify"}`; меню окон —
через `readings_menu` → `clarify_opts_response`.

Существующие замки тракта на legacy **не** гонялись против нового файла.

## Намеренно не сделано (B4+)

- SQL aggregate/rows/compose/gate
- Полное меню мер/осей по живым totals сущности
- Перенос `count_defer_measure_clarify` (O3 №10) — символ из z05; B4
- Flip bootstrap (B6); полный `test_one_path` (а)(б)(в)(г) — B7

## Дальше

Волна **B4**: SQL-ступень + compose/gate; меню мер при >1 (не count);
проводка z11/z12/z15 по whitelist O3 №11.
