# O5: замки и план миграции «одного пути» — судьба каждого test_*

Срез: 12.09. Только чтение. Источники: `O1-map.md`, `O2-project.md`,
`docs/audit/snos15-ONEPATH_PLAN.md`, диск `ubuntu/serenedb/ask/z20_ask_main_http.py`,
`ask/_bootstrap.py`, замки `ubuntu/serenedb/test_*.py`. Код и тесты не менялись.

Мера — контракт владельца:

```
вопрос → wiki-каскад → SQL → меню при >1 прочтении → выбор → ответ
```

Отбор реестра: `test_*.py`, которые (а) читают `z20_ask_main_http.py` /
`_patch_z20_wiki_primary` / `_bootstrap`, или (б) зовут символы, живущие в z20
или ветки `answer()`, помеченные в O1 как ступень/нарушитель тракта ask.
Корпус/embed/takt-замки вне тракта **не** входят.

Судьбы:

| Метка | Смысл |
|---|---|
| **ПЕРЕЖИВАЕТ** | зелёный без смены контракта (возможен лишь путь импорта) |
| **ПЕРЕПИСАТЬ** | ожидания/якоря меняются под один путь (что именно — в ячейке) |
| **УДАЛИТЬ** | проверяемое поведение сносится; файл не нужен или сводится к негативу в другом замке |

Имя `test_hatch_luk_negativ` в плане = файл **`test_measure_hatch_luk.py`**.

---

## 1. Реестр замков

### 1.1. Читают диск z20 / bootstrap (статические)

| Имя | Что проверяет | Судьба A (вычистка) | Судьба B (перепись) | O1-нарушитель / строки теста |
|---|---|---|---|---|
| `test_no_pre_wiki_reorders` | Негатив В2–В4: до-вики prefer/K6/rerank/expand/parent, арбитр, `measure_hatch` сняты; мерное меню без entity-lock-исключений | **ПЕРЕЖИВАЕТ** / усилить в A-W6 (ещё символы A13) | **ПЕРЕЖИВАЕТ** / усилить на новый файл | уже негатив сноса; усиливает A13 |
| `test_measure_hatch_luk` | Негатив люка мер: нет `measure_hatch*`; >1 мера → clarify; `code_ambiguous` не растит picked при wiki_hybrid | **ПЕРЕПИСАТЬ**: блок `code_ambiguous` (стр. ~82–90) → «символа/ветки нет» после A-W3 | **ПЕРЕПИСАТЬ** то же; якорь файла → новый z20 | O1 A5 `code_ambiguous` 2513–2538; тест ~82–90 |
| `test_measure_menu_not_silent` | >1 живая мера → `kind=clarify` + `measure_captions`; нет silent winner / hatch | **ПЕРЕПИСАТЬ** A-W5: два блока меню → один API; диск-якоря `_live`/`measure_ambiguous` | **ПЕРЕПИСАТЬ** → `readings_menu(measure)` | O1 A11 3471–3566; тест ~30+ |
| `test_axis_count_plain` | Plain count без breakdown не зовёт axis-clarify; rank — зовёт | **ПЕРЕЖИВАЕТ** смысл; диск-якоря `_plain_ax` / `count_question_skips_axis` точечно | **ПЕРЕПИСАТЬ** якоря строк нового `answer` | ступень count-гашения (O2 A-W5) |
| `test_wiki_leader_not_overridden` | Wiki-лидер не перебит fork-меню; tie → меню ⊆ wiki_pool; диск+bootstrap гейты early-clarify | **ПЕРЕПИСАТЬ** A-W3: убрать ожидание `early_clarify`/`fork_deferred_*` как отдельных механизмов → «меню только builder по wiki_pool» | **ПЕРЕПИСАТЬ**: fork-gate символы могут исчезнуть; суть leader/tie сохранить через z21 | O1 A6/A8/A9; тест 45–59 (диск/патч) |
| `test_wiki_card_hybrid` | Гибрид-пул z21 + каскад; bootstrap inject cascade; **net-distinct в патче**; нет late canon | **ПЕРЕПИСАТЬ** A-W7: «patch identity»; net-distinct assert → нет или только пост-wiki SQL на диске | **ПЕРЕПИСАТЬ** B6: patch empty; импорт нового z20 | O1 патч net-distinct; тест ~266–291 |
| `test_zone_names_resolvable` | Имена зон резолвятся через `_imports`; z20 грузится с патчем | **ПЕРЕПИСАТЬ** A-W7: патч no-op, диск=runtime | **ПЕРЕПИСАТЬ** B1/B6: legacy/new load path | bootstrap; тест ~57–58 |
| `test_enough` | Негатив: enough-слой вне `_answer_checked_core` | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** (перенос core bit-identical) | инфра |
| `test_final_stock_route_filters_absent` | В окне `answer` до «кандидаты собраны» нет stock-route фильтров | **ПЕРЕЖИВАЕТ** / при ужатии A13 — якорь окна | **ПЕРЕПИСАТЬ** границы секций нового `answer` | негатив маршрута |
| `test_early_clarify_atom_fps_hashable` | Early entity-clarify кладёт hashable fingerprint в set (`_ec_atom_fps`) | **УДАЛИТЬ** или **ПЕРЕПИСАТЬ→негатив** «`_ec_atom_fps`/early_clarify_path нет» после A-W3 | **УДАЛИТЬ** (ветки нет в B) | O1 A9 ~3047–3112; тест якорь `_ec_atom_fps` |
| `test_sales_canon_prefer` | Негатив: prefer/force/lock продаж снесены; z20 без call-site | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** | уже негатив В2 |
| `test_rank_leader_path` | Rank vs compare; axis menu; кусок читает z20 | **ПЕРЕПИСАТЬ** частично (rank_fold третье measure-меню — A11) | **ПЕРЕПИСАТЬ** якоря | O1 rank_fold ~3684–3707 |

### 1.2. Положительные на нарушителях (переписать в негатив или снести)

| Имя | Что проверяет | Судьба A | Судьба B | O1 / строки |
|---|---|---|---|---|
| `test_entity_form` | Положительный контракт `ASK_ENTITY_FORM` / `try_entity_form_answer` / collapse | **УДАЛИТЬ** смысловой контракт → **ПЕРЕПИСАТЬ в негатив** «0 call-site `try_entity_form*` / `entity_form_gate_open` в z20» (A-W2) | то же на новом файле (B3–B6) | O1 A7 2851–2872 + ef_gate |
| `test_k4_guess_vs_clarify` | `period_assumed_needs_clarify` → pre-wiki period clarify (P1–P4) | **ПЕРЕПИСАТЬ** A-W1: либо период-меню **после** wiki как прочтение, либо негатив «до `wiki_primary` return clarify нет» | то же | O1 A2 1861–1888; датчик 1610–1638; тест ~73–84 |
| `test_k4_axis_and_names` | Axis + `period_assumed` + `warehouse_clarify` + stock markers | **ПЕРЕПИСАТЬ**: assumed/warehouse-кейсы → post-wiki readings / негатив def | то же | O1 A2; warehouse 1641 |
| `test_action_class` | action_class/axis + куски ecp / assumed / entity_form / distinct | **ПЕРЕПИСАТЬ** срезы ecp/assumed/entity_form (A-W1/W2); оставить action_class как слот intent | то же | O1 A2/A7/A10 |
| `test_axis_focus` | `axis_focus_plan` + `live_src_counts`: focus=ось → holder/clarify | **УДАЛИТЬ** положительный план → **ПЕРЕПИСАТЬ**: меню оси единым builder после wiki; негатив `axis_focus_plan` | то же | O1 A4 1489–1572, 2443–2478 |
| `test_fork_outcomes` | Исходы A/B/C детектора (в т.ч. меню C) | **ПЕРЕПИСАТЬ** A-W4: авто A/B уже негатив; C-меню → только wiki_pool builder | **ПЕРЕПИСАТЬ**: без fork-судьи; меню = readings | O1 A8 2874–3045 |
| `test_fork_detector` | Чистые функции детектора классов | **УДАЛИТЬ** из тракта ask, если `_fork_early` снесён; иначе оставить как библиотечный shadow вне `answer` | **УДАЛИТЬ** из пути B (z09 не звать) | O1 fork_early 2339–2415 |
| `test_fork_label_daybasis` | Day-basis подписи → исход B/C | **ПЕРЕПИСАТЬ** → readings/подписи без fork-B авто | то же | связан с A8 / calendar |
| `test_fork_atom_aggregate` | `_fork_atom_of` == `aggregate` | **УДАЛИТЬ** при сносе fork_scan из тракта | **УДАЛИТЬ** | A8 |
| `test_leader_hatch` | Негатив fork-авто A/B; C unsigned figures + `FORK_OTHER_READING` | **ПЕРЕПИСАТЬ**: C unsigned с «вторым числом/фразой» **против** контракта one-path → убрать/запретить в A-W4 | **ПЕРЕПИСАТЬ** / усилить негатив «нет FORK_OTHER_READING / вторых чисел» | O1 A8; конфликт с п.(б) плана |
| `test_warehouse_axis_autonomy` | Ось склада без хардкода имён; трогает `warehouse_clarify` | **ПЕРЕПИСАТЬ**: автономия оси жива; вызов `warehouse_clarify` из z20 — негатив | то же | O1 warehouse |
| `test_warehouse_aggregate_breakdown` | Structural warehouse/balance path | **ПЕРЕЖИВАЕТ** смысл SQL-ступени; убрать опору на pre-wiki clarify | **ПЕРЕПИСАТЬ** якоря | смесь |
| `test_stock_balance_path` | Путь остатков intent→ответ; net pair / warehouse / axis_focus | **ПЕРЕПИСАТЬ** A-W7: net-distinct не выбиратель; убрать опору на assumed/axis_focus | **ПЕРЕПИСАТЬ** B4–B6 | O1 A14 патч net; A4 |
| `test_compare_sales` | Compare-окна sales; отдельный терминал ответа | **ПЕРЕПИСАТЬ**: окна как readings; ответ только через compose+gate (снести sales_compare terminal) | то же | O1 3720–3756 |
| `test_atom_terminal` | Computed-атом терминален; compare≠rank | **ПЕРЕЖИВАЕТ** (атом/compose) | **ПЕРЕЖИВАЕТ** | ступень хвоста |
| `test_calendar_axis` | Флаг/readings calendar day-basis | **ПЕРЕЖИВАЕТ** как источник **прочтений**; запрет silent `prefer_window_leader` до wiki (дыра O3 №1/8) | **ПЕРЕПИСАТЬ** порядок: меню окна до SQL при >1 | readings, не меню-нарушитель |
| `test_currency_axis` | Amount-basis readings | как calendar | как calendar | readings |
| `test_fork_window_readings` | `period_readings` MTD/full_month | **ПЕРЕЖИВАЕТ** как readings-библиотека | **ПЕРЕЖИВАЕТ** | ступень окон |

### 1.3. Wiki-каскад / меню / verify (ядро формулы)

| Имя | Что проверяет | Судьба A | Судьба B | Заметка |
|---|---|---|---|---|
| `test_wiki_candidate_verify` | Паспорт + исходы verify (leader/clarify/none) | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** (z21) | ступень |
| `test_wiki_captions_builder` | `wiki_menu_captions` N→N, без выбора | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ**; станет ядром `readings_menu` | единый построитель |
| `test_named_type_filter` | Тип из вопроса режет wiki-пул до verify | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** | z21 |
| `test_verify_threshold_menu` | Порог verify: 1 yes→leader; tie/unsure→меню | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** | O2 A-W5 только если порог трогают |
| `test_k4_meta_names` | Clarify без OData-префиксов в label/text | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** | построитель подписей |
| `test_focus_loop` | Канал выбора сущности / resolve_focus / mk_opts | **ПЕРЕЖИВАЕТ**; усилить: focus только из decision_id этого builder | то же (дыра O3 №4) | ступень билета |
| `test_decision_id` | Сырой focus не гасит защиты; trusted снимает одну неоднозначность | **ПЕРЕЖИВАЕТ** / усилить | **ПЕРЕЖИВАЕТ** | инфра+ступень |

### 1.4. Инфра / compose / gate / journal (сохранить)

| Имя | Что проверяет | Судьба A | Судьба B |
|---|---|---|---|
| `test_gate` | Гейт чисел ответа | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** (B2) |
| `test_compose` | Compose / split / figures; упоминает `_ask_back` | **ПЕРЕЖИВАЕТ**; кусок ask_back → негатив «bare clarify forbidden уже в z20» согласован с A-W7 | **ПЕРЕПИСАТЬ** мелочь ask_back (A12 мёртв → не переносить) |
| `test_ask_journal` | Запись журнала на каждый kind | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** B2 |
| `test_journal_fields` | Clarify-поля журнала | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_ask_choice_memory` | Память явного выбора / shadow | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_period_empty` | Пост-SQL «0 за окно» (не pre-wiki assumed!) | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** B2/§5 | O2 ошибочно вязал к A-W1 (O3 №16) — **не** краснеет от сноса assumed |
| `test_health_gap` / `test_health_native_freshness` / `test_health_tick_status` | `/health` | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** B2 (*coverage-ответ мимо wiki — отдельный долг O3 №9, не эти замки*) |
| `test_intent` | Разбор вопроса z02 | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_step2` | probe/match/tables_of | **ПЕРЕПИСАТЬ** частично: unmatched→no_data **до** wiki (A3) уйдёт | то же | O1 1910–1927 |
| `test_step4_guards` | Защиты шага 4 (когда ответ vs вопрос) | **ПЕРЕПИСАТЬ** A-W6 под ужатый до-вики отбор | **ПЕРЕПИСАТЬ** |
| `test_answer_atom` | AnswerAtom / renderer | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_b9_routing` | Count пропускает axis-clarify | **ПЕРЕЖИВАЕТ** смысл | **ПЕРЕПИСАТЬ** если символы переедут |
| `test_rank_axis_anchor` | Rank axis ticket / stock no_data | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_sales_rank_canon` | Негатив sales rank-prefer | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_trace_rid` / `test_terminal_round` | rid / terminal вокруг answer_checked | **ПЕРЕЖИВАЕТ** | **ПЕРЕЖИВАЕТ** |
| `test_caveat` | `measure_caveat` вне z20 | вне тракта one-path; **не трогать** | — |
| `test_k4_clarify_vs_nodata` | Clarify vs no_data границы | **ПЕРЕПИСАТЬ** если опирался на pre-wiki no_data | то же |

### 1.5. Новый замок

| Имя | Что проверяет | Судьба A | Судьба B |
|---|---|---|---|
| **`test_one_path.py`** (новый) | Статический инвариант формулы (а–г), см. §2 | появляется нарастающе A-W1…**полный A-W8** | скелет с B3; **полный B7** |

### 1.6. Сводка числами

| Класс | ~файлов |
|---|---:|
| ПЕРЕЖИВАЕТ без смены контракта | ~18–22 |
| ПЕРЕПИСАТЬ | ~18–22 |
| УДАЛИТЬ / свести к негативу | ~6–8 (`entity_form`+, early_clarify fps, fork_detector/atom_aggregate, положительный axis_focus, …) |
| Новый | 1 (`test_one_path`) |
| **Итого в реестре тракта** | **~45** (не все 250 `test_*.py`) |

Согласуется с оценкой O2 §2.5 (~12–18 переписать, ~10–15 оставить, +1 канон).

---

## 2. Каркас `test_one_path.py`

Стиль как у `test_no_pre_wiki_reorders` / `test_measure_hatch_luk` / `test_enough`:
`Path.read_text` → `t(name, cond)` → счётчик; плюс **AST** (`ast.parse`), как уже
делает `test_enough` / `test_entity_form` на литералах. Не pytest; не живой SQL;
не вопросы конкретной базы.

Цель: на **исходнике** runtime-z20 (диск; после A-W7/B6 — без патча) доказать
инварианты плана. Объект разбора: модуль z20 целиком + выделение `def answer`
(и при B — тонкий pipeline-файл).

### 2.1. Общие примитивы

```
ALLOWED_CLARIFY_BUILDERS = {
  "clarify_opts_response", "readings_menu",   # B: единый API
  # captions — только как аргументы builder, не как return clarify сами:
  # "wiki_menu_captions", "measure_captions", "axis_clarify_options"
}
FORBIDDEN_SELECTORS = {
  "try_entity_form_answer", "try_event_count_period_clarify",
  "period_assumed_needs_clarify", "axis_focus_plan", "warehouse_clarify",
  "arbitrate", "_fork_early", "fork_outcome_b", "fork_outcome_a",
}
FORBIDDEN_REASON_LIT = {
  "assumed-period", "measure_hatch", "early_clarify",
  "склад не назван",  # мёртвый warehouse_clarify
}
SQL_CALLS = {
  "aggregate", "aggregate_groups", "rows_of", "totals_of",
  "aggregate_stock_net_distinct", "live_src_counts",
}
WIKI_DECISION = "wiki_primary_entity_cascade"
```

Вспомогательно: `func_node(tree, "answer")`; линейный порядок операторов;
`call_names(node)`; игнор комментариев/`ast.Expr` со Str (как `_real_calls` в
`test_no_pre_wiki_reorders`).

Исключения **инфры** (не считаются нарушением one-path в `answer`):
ранние return по `about=coverage` / calendar unavailable / health — **только если**
владелец явно оставит их вне формулы; по контракту 12.09 и O3 №9 coverage-SQL
мимо wiki — тоже нарушение → по умолчанию **запрещены** в `answer` (вынести
в Handler или пометить `diag.one_path_exempt` нельзя промтом — только отдельный
не-`answer` вход). В первой версии замка: **fail**, если в `answer` есть
Call `_coverage_answer` или SQL до wiki.

Trusted/`decision_id` focus: допускается skip повторного каскада **только если**
в том же блоке есть проверка `trusted`/`resolved` из seal (имя символа
`consume_decision` / `hold_settled_entity` / `diag.get("trusted")`) — иначе
нарушение (O3 №4).

### 2.2. Проверка (а) — все clarify только построителем меню

| | |
|---|---|
| **Как** | В `answer`: найти все `Return`, чей value — `Dict`/`Call`, где фигурирует `kind: "clarify"` (константа в keywords/`ast.Constant` или `"kind": "clarify"` в dict keys). Для каждого: либо Return есть `Call(func=Name in ALLOWED_CLARIFY_BUILDERS)`, либо Dict собран **только** внутри тела этих функций (не в `answer`). Дополнительно: прямой `return {..., "kind": "clarify", ...}` в `answer` без предшествующего присваивания из builder → fail. Grep-усиление: `"kind\": \"clarify\""` в `answer` встречается только рядом с `clarify_opts_response` / `readings_menu` (окно ±N строк или общий parent `Assign`). |
| **Нарушение** | YoY bare clarify (O1 ~1762); assumed через helper но с отдельным reason-путём ок **только** если helper = builder; axis_focus/early/fork/measure dict-return мимо builder; `ask_back` → clarify. |
| **Зелёный на легитимном** | Единственный `readings_menu` / `clarify_opts_response(...)` для entity/measure/window/axis; captions подаются аргументом. |

### 2.3. Проверка (б) — ни одного ответа с «вторыми числами»

| | |
|---|---|
| **Как** | (1) В z20 нет имён `measure_hatch`, `measure_hatch_B/C`, `_fork_headline_measure` call-site, `FORK_OTHER_READING` в return-пути `answer`. (2) AST: нет `Return` с `kind in {"figures","answer"}` и одновременно сборкой второго списка чисел/альтернатив (эвристика: в том же `Return`/`Assign` к payload есть и `agg`/`atom`, и вторичный `alts`/`other_reading`/`secondary` без ухода в clarify). (3) Негатив как в hatch-замке: `"_entity_locked"` не ослабляет меню. |
| **Нарушение** | Люк мер; fork C unsigned figures с числом+`FORK_OTHER_READING` без меню; compose с вторым числом в тексте без gate-пары. |
| **Зелёный** | Один atom/одно число; при >1 прочтении — **clarify**, не figures. `test_leader_hatch` C-unsigned после миграции должен стать красным → его переписывают (§1.2), а one_path остаётся жёстким. |

### 2.4. Проверка (в) — SQL только после wiki-решения

| | |
|---|---|
| **Как** | В теле `answer` найти **первый** `Call` `wiki_primary_entity_cascade` (или явный early-return trusted-focus с проверкой билета). Во всех операторах **строго до** этой точки: запрещены Call из `SQL_CALLS` и любые `Name` load тех же id. После точки — SQL разрешён. Дополнительно: до wiki нет `return` с `kind in {answer, figures}` (кроме явного unavailable инфры, если разрешено). |
| **Нарушение** | `live_src_counts` в `axis_focus_plan` до каскада; coverage SQL; unmatched no_data до wiki допустим как **не-SQL**, но early SQL в candidate-filter через live counts — fail; net-distinct до src-из-wiki — fail. |
| **Зелёный** | Линейный B-pipeline: intent → wiki → SQL; probe `rows_of` только после leader/src. |

### 2.5. Проверка (г) — нет `reason=`-меню/люков и запретных выбирателей

| | |
|---|---|
| **Как** | (1) Call `FORBIDDEN_SELECTORS` в z20 = 0 (call-site, не комментарий). (2) В `clarify_opts_response`/`readings_menu` вызовах из `answer`: keyword `reason=` значение ∈ `FORBIDDEN_REASON_LIT` → fail; белый список reason после миграции — только нейтральные вроде `"уточните меру"` / `"уточните ось"` / entity-tie **без** имён люков, либо reason убрать вовсе. (3) `_bootstrap._patch_z20_wiki_primary`: AST тела = `Return` одного аргумента `text` (identity); нет inject net-distinct/ef_gate. (4) Нет присваиваний `diag["early_clarify_path"]`, `diag["measure_hatch"]`, `diag["code_ambiguous"] = extra` с последующим expand picked. |
| **Нарушение** | Любой оставшийся A1–A15/A14 патч. |
| **Зелёный** | Пустой патч; меню без люк-reason; выбиратели отсутствуют как символы. |

### 2.6. Наращивание (чтобы не краснеть на легитимной миграции)

| Фаза | Что включено в one_path |
|---|---|
| Скелет | (г) forbidden symbols + hatch-имена; (б) measure_hatch строка |
| После сноса pre-wiki clarify | (в) SQL-до-wiki; (а) bare clarify dict |
| После сноса F/fork/early | полный (а)(г) call-site |
| Финал | полный (а)(б)(в)(г) + patch identity |

Так замок **появляется раньше финала**, но полный набор — только когда код обязан ему соответствовать (A-W8 / B7).

---

## 3. Порядок миграции замков по волнам

### 3.1. Вариант A (вычистка) — волны O2 §1.3

| Волна | Содержание кода | Замки обновить / новый | Временно краснеет? |
|---|---|---|---|
| **A-W0** | Baseline L67 + список зелёных | ничего не менять; зафиксировать список §1 | нет |
| **A-W1** | Снос A1–A3 (YoY / assumed / unmatched pre-wiki) | `test_k4_guess_vs_clarify`, срезы `test_action_class`, `test_k4_axis_and_names` (assumed); **не** `test_period_empty` | Да: положительные P1–P4 assumed — **допустимо**, если в том же коммите переписаны в негатив/post-wiki. Недопустимо красный L67 без обновления замков. |
| **A-W2** | Снос F/ecp + ef_gate | `test_entity_form` → негатив; срезы action_class ecp; куски `test_wiki_card_hybrid` (ef) | Да на entity_form — **только** пока файл не переписан; в одном пат-спеке с негативом |
| **A-W3** | code_ambiguous / arb_pool / early menu | `test_measure_hatch_luk` (code_ambiguous); `test_wiki_leader_not_overridden`; **УДАЛИТЬ/негатив** `test_early_clarify_atom_fps_hashable`; fork C→builder | **Высокий** L67 («движения в регистре») — допустим только со shadow; замки тракта в том же коммите |
| **A-W4** | fork-scan как отдельный исход | `test_fork_outcomes`, `test_leader_hatch` (убрать C-unsigned вторые числа), `test_fork_*` авто | Да fork-положительные — допустимо при переписи; **недопустимо** оставлять зелёный `test_leader_hatch` C-figures против (б) |
| **A-W5** | Унификация measure/axis меню + count | `test_measure_menu_not_silent`, `test_axis_count_plain`, при необходимости `test_verify_threshold_menu`, `test_b9_routing` | Средний; диск-якоря двух блоков меню покраснеют — переписать на один API |
| **A-W6** | Ужать до-вики отбор A13 | усилить `test_no_pre_wiki_reorders`; `test_step4_guards`; `test_final_stock_route_*` якорь окна | Средний |
| **A-W7** | ask_back; net-distinct; patch→identity | `test_wiki_card_hybrid`, `test_stock_balance_path`, `test_zone_names_resolvable`; `test_compose` ask_back | Средний; bootstrap≠диск исчезает |
| **A-W8** | Полный `test_one_path` + L67 | добавить/включить полный §2; выкат | Красный one_path **недопустим**; L67 wrong≤4, silent 0 |

Параллелить волны нельзя (общий файл). На каждой волне: сначала правка
замков под новый контракт (или негатив), потом код — иначе красный замок
маскирует регресс.

### 3.2. Вариант B (перепись, рекомендация O2)

| Шаг | Содержание | Замки | Красное |
|---|---|---|---|
| **B0** | Baseline L67 + md5 | снимок зелёных §1 | нет |
| **B1** | legacy копия; новый файл не в пути | `test_zone_names_resolvable` / load: «legacy = runtime» | нет на прод-пути |
| **B2** | Перенос health/journal/Handler/gate/clarify helpers/period_empty | `test_ask_journal`, `test_journal_fields`, `test_gate`, `test_health_*`, `test_period_empty`, `test_ask_choice_memory` | **Недопустимо** красным — bit-identical |
| **B3** | Skeleton answer: intent→wiki→return | `test_wiki_*` (verify/captions/named_type/threshold/leader смысл) против нового модуля; скелет `test_one_path` (г)(часть а) | Wiki-замки на **legacy** остаются зелёными; новые — на флаге |
| **B4** | SQL+compose+gate; `readings_menu` | `test_measure_menu_*`, `test_axis_count_*`, `test_compose`, `test_gate`, `test_b9_routing`, `test_stock_balance_path` (SQL) | Допустимо красные старые положительные F/fork/assumed — их уже переводят в негатив **до** flip |
| **B5** | `ASK_ONEPATH=1` shadow L67 | сравнивать меню ⊆ wiki; silent 0 | Shadow-wrong ожидаемы на pre-wiki кейсах; **недопустим** silent choice |
| **B6** | Flip; patch identity | `test_wiki_card_hybrid` / zone / leader: «patch empty»; импорт = новый z20 | Кратко красные якоря патча — чинятся в том же коммите flip |
| **B7** | Полный `test_one_path`; удалить legacy | все негативы сноса живы на новом файле; L67 | one_path красный = стоп выката |

Параллель: B2 (инфра) ∥ подготовка негативов (`entity_form`, `k4_guess`, `axis_focus`, `fork_*`); B3–B5 строго последовательно.

### 3.3. Правило «временно красный»

| Допустимо | Недопустимо |
|---|---|
| Замок, чей **положительный** контракт снесён, красный **до конца того же пат-спек коммита**, где его переписали в негатив | Замок формулы (wiki verify, captions, gate, journal) красный «потом починим» |
| Shadow L67 на полигоне с ожидаемым diff (нет pre-wiki меню) | Прод-выкат при silent>0 или one_path fail |
| Старый файл ещё зелёный, пока bootstrap → legacy (B1–B5) | Flip (B6) при красном one_path скелете (г) |

---

## 4. Источники

- `docs/audit/onepath/O1-map.md`, `O2-project.md`, `O3-red.md` (дыры имён волн / period_empty)
- `docs/audit/snos15-ONEPATH_PLAN.md` § этап-2 (а–г)
- Образцы: `test_no_pre_wiki_reorders.py`, `test_measure_hatch_luk.py`, `test_enough.py`
- Диск: `ubuntu/serenedb/ask/z20_ask_main_http.py`, `ask/_bootstrap.py`

*Конец O5. Исполнение волн — только после слова владельца (выбор A/B).*
