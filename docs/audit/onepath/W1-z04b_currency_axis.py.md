# W1 — карта живости `ask/z04b_currency_axis.py`

Дата: 12.09.2026. Только чтение кода; чужие отчёты onepath не читались.
Файл зоны: 567 строк; определений верхнего уровня: 34 символа / **506** строк тела.
Загрузка: `_bootstrap.py:27` → `z04b_currency_axis.py` (после `z04_calendar_axis.py`);
в конце `register_zone('ask.z04b_currency_axis', …)`. В `_imports.py` / `_wire.py`
имён зоны нет (только `apply_bindings` + `register_zone` внутри самой зоны).
Вызовы — голые имена в общем namespace после exec.

Метод: AST top-level defs → `rg` по `ask/*.py` + `test_*.py` + getattr/строки.
Корень «новому» = `z20_ask_main_http.py`; «legacy» = `z20_ask_main_http_legacy.py`.

---

## Итог зоны

| Вердикт | Символов | Строк определений |
|---|---:|---:|
| **ЖИВА НОВОМУ** (прямо/транзитивно) | 29 | **433** |
| **ЖИВА ТОЛЬКО LEGACY** | 4 | **62** |
| **МЁРТВА** | 1 | **11** |
| **Всего** | 34 | **506** |

**Вердикт по зоне:** зона **нужна одному пути** (85% строк определений живы
новому). Прямые точки входа нового тракта: `expand_readings_currency_axis`,
`currency_mismatch_blocks_answer`, `currency_unit_for_reading`. После сноса
legacy останутся мёртвыми 62 строки (prefer / patch_scan / sum_for_basis /
`_class_amount_basis`) плюс уже мёртвый `prefer_amount_basis_leader` (11).

Замечание рантайма (не меняет живость вызова): новый `answer()` зовёт
`expand_readings_currency_axis(..., prefer=None, intent=…, trusted=…)` **без**
`rel_by_src`/`preds` → в `currency_axis_applies` `mapped=[]` → ось часто
no-op; цепочка символов в графе вызовов при этом остаётся живой.

---

## Таблица символов

| Символ | Стр. | Кто зовёт (файл:строка) | Вердикт |
|---|---:|---|---|
| `_AMOUNT_BASIS_DOC` | 1 | зона внутри; `z09:396-397`; `z13:498`; new/`mismatch`; tests | **ЖИВА НОВОМУ** |
| `_AMOUNT_BASIS_ACCOUNTING` | 1 | зона внутри; new/`mismatch`; tests | **ЖИВА НОВОМУ** |
| `_AMOUNT_BASIS_IDS` | 1 | зона; `z09:565,582,994`; `z13:115,194,463,494`; **`z14:385` `issue_decision` ← `seal_clarify` ← new z20:2884**; tests | **ЖИВА НОВОМУ** |
| `_AMOUNT_BASIS_LEADER_DEFAULT` | 1 | зона (`readings`/`unit_for_reading`/prefer); `z13:116` | **ЖИВА НОВОМУ** |
| `_CURRENCY_REGS` | 1 | только зона + `test_currency_axis:51` (сброс кэша) | **ЖИВА НОВОМУ** (кэш `currency_rate_registers`) |
| `_CURRENCY_ACCT` | 1 | зона + test:52 | **ЖИВА НОВОМУ** |
| `_CURRENCY_MAP` | 1 | зона + test:53 | **ЖИВА НОВОМУ** |
| `_CURRENCY_RATE_MAP` | 1 | зона + test:54 | **ЖИВА НОВОМУ** |
| `_CURRENCY_CATALOGS` | 1 | зона + test:55 | **ЖИВА НОВОМУ** |
| `_sql_ident` | 2 | зона (FX/unit); после bootstrap перекрывает одноимённую из `z04` — `z04:287-289` `_working_day_doc_preds` бьёт в binding зоны | **ЖИВА НОВОМУ** |
| `currency_catalogs` | 14 | зона ← `unit_for_ref` / `ref_requested`; mock в tests; meta-строки в `test_currency_meta_build` (не вызов) | **ЖИВА НОВОМУ** |
| `currency_rate_registers` | 14 | зона ← `_currency_rate_subquery`; tests | **ЖИВА НОВОМУ** |
| `accounting_currency_key` | 14 | зона ← open / fx / unit / mismatch; tests | **ЖИВА НОВОМУ** |
| `currency_map_rows` | 36 | зона ← open / map_for_src; tests | **ЖИВА НОВОМУ** |
| `currency_rate_map_rows` | 31 | зона ← open / fx; tests | **ЖИВА НОВОМУ** |
| `currency_map_for_src` | 5 | зона ← applies / fx / patch / unit / mismatch | **ЖИВА НОВОМУ** |
| `currency_axis_open` | 6 | зона; **legacy z20:1811**; `z13:196` `_fork_class_axis_unavailable`; expand/mismatch; tests | **ЖИВА НОВОМУ** (также legacy) |
| `currency_amount_basis_prefer` | 26 | **legacy z20:1780**; `z09:416` `fork_detector_scan` ← **только legacy**; tests | **ЖИВА ТОЛЬКО LEGACY** |
| `currency_basis_from_labels` | 19 | зона ← prefer + `currency_axis_applies` (в теле applies → new через expand) | **ЖИВА НОВОМУ** |
| `_amount_basis_reading` | 8 | зона ← `currency_axis_readings` | **ЖИВА НОВОМУ** |
| `currency_axis_applies` | 24 | зона ← readings; stub в tests | **ЖИВА НОВОМУ** |
| `currency_axis_readings` | 10 | зона ← expand; tests | **ЖИВА НОВОМУ** |
| `expand_readings_currency_axis` | 16 | **new z20:1888 `answer`**; **legacy z20:1782**; `z09:417` `fork_detector_scan` (legacy); tests | **ЖИВА НОВОМУ** |
| `prefer_amount_basis_leader` | 11 | **нигде** (только определение) | **МЁРТВА** |
| `_currency_period_where` | 9 | зона ← `currency_fx_probe` | **ЖИВА НОВОМУ** |
| `_currency_rate_subquery` | 25 | зона ← `currency_fx_probe` | **ЖИВА НОВОМУ** |
| `currency_fx_probe` | 70 | зона ← applies / sum_for_basis; stub tests | **ЖИВА НОВОМУ** (через applies←expand) |
| `currency_sum_for_basis` | 8 | зона ← `currency_patch_fork_scan` ← `z09:353` `fork_scan_readings` ← `fork_detector_scan` ← **только legacy** | **ЖИВА ТОЛЬКО LEGACY** |
| `currency_patch_fork_scan` | 20 | `z09:353` `fork_scan_readings` ← legacy; tests | **ЖИВА ТОЛЬКО LEGACY** |
| `currency_unit_for_ref` | 20 | зона ← unit_for_reading / mismatch; tests | **ЖИВА НОВОМУ** |
| `currency_unit_for_reading` | 27 | **new z20:1831** `_onepath_compose_gate`; **legacy z20:4385**; tests | **ЖИВА НОВОМУ** |
| `currency_ref_requested` | 41 | зона ← mismatch; stub tests | **ЖИВА НОВОМУ** |
| `currency_mismatch_blocks_answer` | 33 | **new z20:1821** `_onepath_compose_gate` ← answer:2240; **legacy z20:4377**; tests | **ЖИВА НОВОМУ** |
| `_class_amount_basis` | 8 | только `z13` (`fork_leader_class` / `_fork_class_axis_unavailable` / `_fork_clarify_axis_kind` / `_fork_human_measure_label` / `_fork_clarify_opts`) ← `fork_outcome_c` / resolve ← **только legacy**; tests | **ЖИВА ТОЛЬКО LEGACY** |

### Bootstrap / imports / wire

| Место | Роль |
|---|---|
| `_bootstrap.py:27` | файл зоны в `_ZONE_FILES` (всегда грузится) |
| `_bootstrap.py:14-15` | выбор new/legacy z20 по `ASK_ONEPATH` — на состав зоны не влияет |
| `_imports.py` | имён зоны нет |
| `_wire.py` | имён зоны нет; `register_zone` в конце файла зоны |

### Тесты (замки)

| Файл | Что трогает |
|---|---|
| `ubuntu/serenedb/test_currency_axis.py` | прямой замок зоны: open/readings/expand/prefer/fx/sum/patch/unit/ref/mismatch/`_class_amount_basis`/константы/кэши |
| `ubuntu/serenedb/test_currency_meta_build.py` | **не** зовёт символы ask; проверяет SQL/meta-ключи `currency_catalogs` / `currency_rate_registers` / шаг `currency_axis` |

getattr / f-строки с именами символов зоны снаружи — **не найдены**.

---

## Транзитивные цепочки

### К новому z20 (`z20_ask_main_http.py`)

1. **expand (меню amount-basis до SQL)**  
   `expand_readings_currency_axis` ← `answer:1888`  
   ← `currency_axis_open` ← (`currency_map_rows` ∧ `accounting_currency_key` ∧ `currency_rate_map_rows`)  
   ← `currency_axis_readings` ← `currency_axis_applies`  
   ← (`currency_map_for_src`, `currency_basis_from_labels`, `currency_fx_probe`  
   ← `_currency_period_where` / `_currency_rate_subquery` ← `currency_rate_registers` / `_sql_ident`)  
   ← `_amount_basis_reading`  
   ← константы `_AMOUNT_BASIS_*`

2. **mismatch → clarify**  
   `currency_mismatch_blocks_answer` ← `_onepath_compose_gate:1821` ← `answer:2240`  
   ← `currency_axis_open`, `currency_ref_requested` ← `currency_catalogs`,  
   `accounting_currency_key`, `currency_map_for_src`, `currency_unit_for_ref`,  
   `_AMOUNT_BASIS_DOC` / `_AMOUNT_BASIS_ACCOUNTING`

3. **единица ответа**  
   `currency_unit_for_reading` ← `_onepath_compose_gate:1831`  
   ← `accounting_currency_key`, `currency_unit_for_ref` ← `currency_catalogs`,  
   `currency_map_for_src`, `_sql_ident`, `_AMOUNT_BASIS_*`

4. **билет clarify (константа)**  
   `_AMOUNT_BASIS_IDS` ← `issue_decision:385` ← `seal_clarify:435` ← new `answer:2884`

### Только к legacy z20

5. **лидер amount-basis (скрытый prefer)**  
   `currency_amount_basis_prefer` ← legacy `answer:1780`  
   и ← `z09.fork_detector_scan:416` ← legacy `answer:2380,2924`  
   ← `currency_basis_from_labels` (также жива новому через applies)

6. **подмена сумм в fork_scan**  
   `currency_patch_fork_scan` ← `z09.fork_scan_readings:353`  
   ← `fork_detector_scan` ← legacy  
   ← `currency_sum_for_basis` ← `currency_fx_probe` (fx также жив новому через applies)

7. **классы развилки**  
   `_class_amount_basis` (+ константы) ← `z13.fork_leader_class` /  
   `_fork_class_axis_unavailable` (`currency_axis_open`) /  
   `_fork_clarify_axis_kind` / `_fork_human_measure_label` / `_fork_clarify_opts`  
   ← `fork_outcome_c` / `resolve_fork_outcome` ← legacy `answer:2970,3023`  
   (в new z20 этих имён **нет**)

8. **diag leader**  
   `currency_axis_open` ← legacy `answer:1811` (дубль; open и так жив новому)

### Мёртвая

9. `prefer_amount_basis_leader` — определена, вызовов нет.

---

## Скрытые выбиратели и новый тракт

Критерий: функция, которая **кодом** выбирает источник / меру / период / ось
молча (без меню человеку).

| Кандидат | Роль | Доступен новому? |
|---|---|---|
| `currency_amount_basis_prefer` | лидер amount-basis из ticket/intent/словаря | **Нет** (только legacy + `fork_detector_scan`) |
| `prefer_amount_basis_leader` | молча взять один reading | **Нет** (мертва) |
| `currency_axis_readings` / `expand_readings_currency_axis` | развернуть 0..2 readings (doc/accounting); порядок при `prefer=None` → doc первым | **Да**, но это **расширение меню**, не выбор одного ответа; new явно `prefer=None` (без лидера) |
| `currency_axis_applies` + `currency_fx_probe` | решить, нужна ли ось (FX / словарь) | **Да** — гейт «показывать ли ось», не выбор ветки ответа |
| `currency_basis_from_labels` | hit словаря → applies/prefer | **Да** (через applies); не выбирает ответ |
| `currency_ref_requested` | угадать Ref валюты из подписей в вопросе | **Да** (через mismatch) — вход в clarify, не число |
| `currency_mismatch_blocks_answer` | при чужой валюте → clarify с options | **Да** — **не** скрытый: отдаёт выбор человеку |
| `currency_patch_fork_scan` / `currency_sum_for_basis` | подмена sums под выбранный basis в fork | **Нет** (только legacy fork) |
| `_class_amount_basis` + `fork_leader_class` | лидер класса по amount-basis | **Нет** (только legacy fork outcomes) |

**Вывод:** в новый тракт зона **не тащит** молчаливого выбирателя одной
ветки amount-basis (`prefer` / `prefer_amount_basis_leader` / fork-leader).
Тянет: expand readings (меню), FX-гейт «ось нужна?», mismatch→clarify,
подстановку единицы валюты в текст ответа.

---

## Сводка для этапа-2

- Зону **оставлять** в контуре одного пути: 433/506 строк живы новому.
- Кандидаты на снос **после flip + удаления legacy**:  
  `currency_amount_basis_prefer`, `currency_patch_fork_scan`,
  `currency_sum_for_basis`, `_class_amount_basis`, `prefer_amount_basis_leader`
  (и вызовы из z09/z13, если те зоны тоже чистят).
- Замок: `test_currency_axis.py` (не отпускать при правках expand/mismatch/unit).
