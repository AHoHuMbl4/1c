# K5: применение трёх проектов K4 к `serene_ask.py`

**Дата:** 2026-08-27  
**База:** okna (живой прогон — за оркестратором)  
**Источники:** [`K4_GUESS_VS_CLARIFY.md`](K4_GUESS_VS_CLARIFY.md),
[`K4_CLARIFY_VS_NODATA.md`](K4_CLARIFY_VS_NODATA.md),
[`K4_AXIS_AND_NAMES.md`](K4_AXIS_AND_NAMES.md); замер ambiguous **5/18**
([`ACCEPTANCE_AMBIGUOUS.md`](ACCEPTANCE_AMBIGUOUS.md), `96b51ab`).

`serene_ask.py` **готов к живой пробе**, в этот коммит **не входит**
(гейт `.claude/.probe-okna-last-run` — оркестратор после `/ask` на okna).

---

## 1. Порядок правок

| # | Класс | Что сделано |
|---|---|---|
| 1 | Имена метаданных (№10) | `human_table_label` / `looks_like_src_table` / `label_has_meta_src`; запрет fallback `label→src` в `label_with_kind`, `disambiguate_labels`, `balance_bridge_clarify`, `mk_opts`; санитар в `format_clarify_options` |
| 2 | no_data vs clarify (№6/14/17/18) | Место A: любой unmatched term-group → `no_data`. Место B: `src_supports_question` перед measure-clarify; `diag.by_period_fill` на запасном `tables_of("", preds)` |
| 3 | Ось + склад (№3/7/11) | `period_assumed_needs_clarify` до поиска; `measure_class_alts` (money\|qty); stock-bypass пустого by; `warehouse_clarify` |
| 4 | Догадка (№1/2/8/12) | assumed-period → `_need_clarify`; rank×sales без меры → `role_ask`; маркер `леж` + `stock_subject_needs_clarify` |

---

## 2. Расхождения проекта с кодом

| Проект | Что | Как поступили |
|---|---|---|
| K4-3 §5.3 / K4-1 §3.4 | Расширить маркеры «склад*» / warehouse / storage | **Не взяли голый `склад`**: ловит «стих про склад» (№18) и уводит в stock-path. Для №12 достаточно `леж` + subject-clarify |
| K4-1 тест P2 | Фикстура `2026-07-01…08-27` (~57 д) при пороге `span≥85` | Поверили **коду** (порог из проекта §3.1); фикстуру замка поправили на квартал `04-01…06-30` |
| Номера строк | Снимок ~15931 → после правок ~16202 | Якоря — имена функций; карта пересобрана `code_map.py` |
| K4-2 место C | Не наполнять period-pool | **Не применено** (проект: «после замка B»). Достаточно A+B + флаг `by_period_fill` |
| K4-3 №16 «дела» | Расширить `verdict_before` | **Не применено** в этом заходе: дешёвых якорей без риска сломать №9 не нашлось; страж B режет мусорный measure-clarify |

---

## 3. Замки до / после

| Замок | До | После |
|---|---|---|
| `test_k4_guess_vs_clarify.py` | 6 ok / 0 FAIL / **4 pending** | **13/0/0** |
| `test_k4_meta_names.py` | не было | **12/0** (перечень запрещённых префиксов) |
| `test_k4_clarify_vs_nodata.py` | не было | **11/0** |
| `test_k4_axis_and_names.py` | не было | **11/0** |
| `test_sales_rank_canon.py` | 49/2 (role_ask vs qty/money) | **51/0** (live → `role_ask` по K4-1 §3.3) |
| `test_stock_balance_path.py` | 27/0 | **27/0** |
| `test_partial_flag_propagation.py` | 20/0 | **20/0** |
| `test_fork_outcomes.py` | 29/0 | **29/0** |
| `test_fork_window_readings.py` | 40/0 | **40/0** |
| `test_calendar_axis.py` | 36/0 | **36/0** |
| `test_code_map.py` | — | **28/0** (после `code_map.py`) |

Живой ambiguous **5/18** в этом шаге **не** переснимался (стейджинг —
оркестратор). Числа замков не подогнаны под приёмку.

---

## 4. Новые / обновлённые файлы (в коммите)

- `ubuntu/serenedb/test_k4_meta_names.py`
- `ubuntu/serenedb/test_k4_clarify_vs_nodata.py`
- `ubuntu/serenedb/test_k4_axis_and_names.py`
- правки `test_k4_guess_vs_clarify.py`, `test_sales_rank_canon.py`
- `docs/CODE_MAP_ASK.md`, `docs/audit/code-map.json`
- этот отчёт

**Вне коммита:** `ubuntu/serenedb/serene_ask.py` — после живой пробы okna
оркестратор ставит отметку и коммитит файл.

---

## 5. Ожидание по классам после пробы (не замер)

| № | Ожидание kind | Механизм |
|---:|---|---|
| 1, 2, 3 | `clarify` period | `period_assumed_needs_clarify` |
| 6, 14, 17, 18 | `no_data` | A unmatched / B `src_supports_question` |
| 7, 8 | `clarify` money\|qty | `measure_class_alts` / `role_ask` |
| 10 | `clarify` без OData-префиксов | `human_table_label` |
| 11 | `clarify` склада (или bridge) | stock-bypass + `warehouse_clarify` |
| 12 | `clarify` subject | `леж` + `stock_subject_needs_clarify` |
| 4, 5, 9, 13, 15 | без регресса | не трогали early no_data по полному match / явный год |

Если живой прогон не улучшит 5/18 — зафиксировать факт в
`ACCEPTANCE_AMBIGUOUS.md` без подгонки.
