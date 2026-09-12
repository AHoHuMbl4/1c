# O2: проект «одного пути» — вычистка z20 vs переписывание z20

Срез исходников: 12.09 (диск). База плана: `docs/audit/snos15-ONEPATH_PLAN.md`.
Код не менялся; только чтение `z20` / `_bootstrap` / замков `test_*.py`.

Контракт (приказ владельца 12.09):

```
вопрос → wiki-каскад → SQL → меню при >1 прочтении любого рода → выбор → ответ
```

Люков нет. Вторых чисел нет. Обходов вики нет. Count — мера не спрашивается.

---

## 0. Факт о текущем z20 (замер чтения)

| Слой | Строки | Заметка |
|---|---|---|
| Файл целиком | 5094 | `z20_ask_main_http.py` |
| `answer()` | 1703–4397 (~2695) | из них ~895 комментариев, ~1763 кода |
| HTTP + журнал + scope | ~650 | `Handler`, `_ask_journal_*`, `answer_checked` |
| Health / coverage | ~370 | `/health`, `_coverage_answer` |
| Clarify/gate helpers | ~340 | `gate`, `clarify_*`, `mk_opts` |
| Period/assumed/focus helpers | ~500 | в т.ч. кандидаты на снос |
| `_bootstrap._patch_z20_wiki_primary` | ~120 | net-distinct + `ef_gate` (+ reorder ecp/F) |

Wiki-каскад **уже** строит пул сам (`z21.wiki_hybrid_pool` → verify → leader/меню).
Параметр `cands` в `wiki_primary_entity_cascade` на выбор сущности не влияет:
при отсутствии лидера — честный `no_data`, без manual-fallback (z21:843–884).
Длинный до-вики отбор в `answer` (≈1939–2419, ~480 строк) кормит в основном
остатки `arb_pool` / early-clarify / fork-scan — не ступень формулы.

Точка вики в `answer`: 2504–2511. Всё, что `return` clarify/no_data/answer
**раньше** этой точки (кроме ticket-`focus` и infra/coverage/health) — обход порядка.

---

## 1. Вариант A — ВЫЧИСТКА z20

### 1.1. Блоки-нарушители (удалить или свернуть в единое меню каскада)

Составлено по чтению `answer()` + helpers. Диапазоны — диск-версия; патч
bootstrap указан отдельно.

| # | Блок | Строки (диск) | Почему не ступень формулы | Что при удалении |
|---|---|---|---|---|
| A1 | YoY bare-clarify | 1754–1766 | clarify до вики, пустые options | вопросы YoY без окна пойдут в каскад |
| A2 | assumed-period clarify | 1861–1888 + helper 1610–1638 | окно-меню **до** вики | период-меню только после wiki-решения (как прочтение) |
| A3 | unmatched→no_data | 1916–1927 | отказ до вики | unmatched — после выбора сущности, на SQL-ступени |
| A4 | `axis_focus_plan` clarify | 2443–2478 + 1504–1572 | отдельный выбиратель держателя оси | focus-ticket → сразу holder/SQL или меню каскада |
| A5 | `code_ambiguous` expand picked | 2513–2538 | дописывает src мимо verify | замок `test_measure_hatch_luk` (негатив) → удалить/свести к diag-only |
| A6 | doubt / `arb_pool` сборка | 2540–2840 (~300) | круг «соперников» — скрытый выбиратель | убрать; >1 src только из wiki_pool / post-wiki меню |
| A7 | ecp1 + entity_form F | 2851–2872 | ответ/clarify мимо каскада | снос вызовов; `z05` не трогать в A-волне 1 (мертвый импорт позже) |
| A8 | fork outcomes A/B/C scan | 2874–3035 | второй механизм меню/исходов | при >1 окне/классе — **тот же** построитель меню, не fork-авто |
| A9 | early entity-clarify ×2 | 3060–3134 | два источника меню (`arb_pool` ∪ `picked`) | один вызов построителя по `wiki_pool`/tie |
| A10 | ecp2 | 3465–3469 | период-clarify после src, всё ещё отдельный люк | период — прочтение → меню построителем |
| A11 | dual measure-menu | 3471–3570 | два блока меню мер | **не сносить смысл**: свернуть в один вызов; count-гашение оставить |
| A12 | ask_back clarify | 4282–4321 | модель-уточнение после compose | запрещён контрактом (меню только построителем) |
| A13 | до-вики candidate/rank/not_for/fork_early | 1939–2419 (~480) | не нужен для wiki_pool; кормит A6–A9 | оставить минимум: `match`/`preds`/`by` для SQL |
| A14 | bootstrap net-distinct | `_bootstrap` 55–101 | скрытый выбор агрегата | либо влить в SQL-ступень явно после wiki, либо снести |
| A15 | bootstrap `ef_gate` | `_bootstrap` 105–164 | расширяет F | убрать вместе с A7; патч → no-op/пустой |

**Оценка строк, уходящих из файла:** ~1100–1600 (код нарушителей + ставшие
мёртвыми helpers + часть комментариев у снесённых блоков).  
**Ожидаемый размер z20 после A:** ~3500–4000 строк (не 800–1500): исторический
нарратив и SQL/compose-хвост остаются. Довести до «тонкого» только повторными
волнами комментарий-долга — это уже почти B внутри A.

### 1.2. Сохраняемые функции (A)

**Инфра (без обсуждения):**  
`Handler`, `main`, весь `_journal_*`, `_ask_journal_write`, `answer_checked`,
`_answer_checked_core`, `_build/_persist/_ensure_ask_scope*`, health-пакет
(`_health_*`, `_coverage_*`, `_measure_*_freshness`, `_classify_health_gap`),
`шаг`/`diag.шаги` внутри `answer`, вызовы дедлайна z01.

**Ступени формулы (оставить, возможно ужать):**  
- слоты: вызов `parse_intent` / `apply_proven_period` / `apply_prior_period` /
  `apply_period_leader` / preds;  
- `wiki_primary_entity_cascade` (единственный выбор сущности);  
- SQL: `aggregate` / `aggregate_groups` / `rows_of` / `totals_of` /
  stock-net **только как SQL-форма после wiki**, не как выбиратель;  
- меню: `clarify_opts_response` + `wiki_menu_captions` + `measure_captions` +
  `axis_clarify_options` — **свести к одному внешнему API** «прочтения»;  
- `compose` + `gate` / `gate_out`;  
- ticket-путь: `resolve_focus` при `trusted`/`resolved` (выбор человека уже был).

**Не сохранять как поведение (код можно удалить):**  
`period_assumed_needs_clarify`, `warehouse_clarify`, `try_entity_form_answer`
(вызовы), `try_event_count_period_clarify` (вызовы), сборка `arb_pool`,
early-clarify A, YoY-заглушка, ask_back.

### 1.3. Волны A (правка → замки → полигон → L67)

Каждая волна: пат-спек коммит своих файлов; новый статический замок
наращивать постепенно; полный L67 в конце волны (критерий плана: wrong ≤ 4,
молчаливых выборов 0, меню только из вики).

| Волна | Содержание | Замки переписать/снять | Риск L67 |
|---|---|---|---|
| A-W0 | Зафиксировать baseline L67 + зелёные ~19 z20-замков на текущем HEAD | — | низкий |
| A-W1 | Снос A1–A3 (до-вики clarify/no_data) | `test_k4_guess_vs_clarify`, `test_action_class` (assumed/ecp), частично `test_period_empty` | средний: длинные окна станут либо ответом после wiki, либо меню окна |
| A-W2 | Снос A7+A10+A15 (F/ecp + ef_gate) | `test_entity_form` → удалить/перевести в негатив «вызовов нет»; `test_wiki_card_hybrid` (ef/net якоря) | средний |
| A-W3 | Снос A5–A6–A9 (code_ambiguous, arb_pool, dual early menu) | `test_measure_hatch_luk`, `test_wiki_leader_not_overridden`, `test_early_clarify_*`, `test_fork_outcomes` (C-меню → wiki_pool only) | **высокий**: «движений в регистре» / verify-лотерея |
| A-W4 | Снос A8 (fork-scan как отдельный исход) → меню окон/классов построителем | `test_fork_outcomes`, `test_atom_terminal`, `test_fork_*` | высокий |
| A-W5 | Унификация A11 measure/axis меню + count-гашение | `test_measure_menu_not_silent`, `test_axis_count_plain`, `test_verify_threshold_menu` | средний |
| A-W6 | Ужать A13 (до-вики отбор → минимум match/by) | `test_no_pre_wiki_reorders` (усилить), `test_step4_guards` | средний |
| A-W7 | A12 ask_back; A14 net-distinct; `_patch_z20_wiki_primary` → пустой | `test_wiki_card_hybrid`, `test_stock_balance_path`, `test_zone_names_resolvable` | средний |
| A-W8 | Новый `test_one_path.py` (а–г из плана) + полный L67 + выкат | — | стоп-критерий |

**Число волн:** 8 (+ W0). Реалистично 2–4 недели календарно при одном
полигоне/L67 на волну; параллелить волны нельзя (общий файл).

### 1.4. Риски A и снятие

| Риск | Как снять |
|---|---|
| Остаточный люк в 3500+ строках (пропуск при чтении) | `test_one_path.py` + grep-гейт на `reason=`/early return до `wiki_primary` |
| Регрессия L67 на каждой волне | shadow: тот же корпус вопросов до/после; откат = revert волны |
| Замки, утверждающие *наличие* снесённого кода | заранее перевести в негативы «символа нет» (как В2/В3/В4) |
| Патч bootstrap расходится с диском | W7: патч пустой; замки читают диск = runtime |
| Потеря тонких SQL-веток (net-distinct, period_empty) | period_empty — ступень ответа после SQL, **сохранить**; net-distinct — только после wiki+src |

**Откатываемость A:** высокая поволново (маленькие диффы), низкая в сумме
(после W3–W4 файл уже другой зверь; полный откат = revert цепочки).

---

## 2. Вариант B — ПЕРЕПИСАТЬ z20 (~800–1500 строк)

### 2.1. Эскиз секций нового файла

Имя рабочего: `z20_ask_main_http.py` (старый уходит в
`z20_ask_main_http.legacy.py` на время миграции; bootstrap грузит новый).

| § | Секция | ~строк | Содержание |
|---|---|---|---|
| 1 | Импорты / константы зоны | 40–60 | как сейчас через `_bootstrap` exec |
| 2 | Gate + единый построитель меню | 120–180 | перенос `gate`/`gate_out`/`clarify_*`; один `readings_menu(kind, items)` → `wiki_menu_captions` |
| 3 | Health / coverage | 200–280 | перенос `_health_*`, `_coverage_answer` **без изменений** |
| 4 | Labels / mk_opts (тонкий) | 80–120 | `human_table_label`, `mk_opts`, без live-arbiter |
| 5 | Period empty (пост-SQL) | 80–120 | `build_period_empty_answer` и друзья — ответ «ноль за окно», не до-вики clarify |
| 6 | `answer()` линейный pipeline | 250–400 | см. §2.2 |
| 7 | Journal + `answer_checked` | 200–250 | перенос как есть |
| 8 | `Handler` + `main` | 180–220 | перенос как есть |
| | **Итого** | **~1150–1630** | цель держать ≤1500 кода; комментарии — коротко |

### 2.2. Линейный `answer()` (B)

```
1. token/deadline/шаги/intent (z02) + prior/trusted period
2. calendar/currency readings → список прочтений окна/оси (ещё НЕ меню)
3. coverage/health early — только about=coverage / axis_unavailable (инфра п.13)
4. wiki_primary_entity_cascade  — единственный выбор сущности
   · clarify → return (уже через wiki_menu_captions)
   · no_data  → return
   · leader   → src
5. ticket focus/trusted — если уже выбран человеком, wiki не переигрываем
6. SQL (z17/z06/z07/z08/z12): aggregate/rows
   · если >1 мера (и не plain count) → readings_menu(measure)
   · если >1 окно/ось из readings → readings_menu(window|axis)
7. compose (z18) + gate → один ответ, одно число
8. journal side-effect в answer_checked / Handler
```

Никаких: assumed-period pre-wiki, entity_form, ecp, arb_pool, fork-outcome
авто, ask_back, code_ambiguous expand, YoY-заглушки.

### 2.3. Что переносится из старого z20 без изменений (конкретные символы)

| Символ | Строки (сейчас) | Зачем |
|---|---|---|
| `gate`, `gate_out` | 73–256 | контракт чисел |
| `clarify_choice_*`, `format_clarify_options`, `clarify_say`, `clarify_opts_response` | 277–375 | оболочка меню |
| `_health_*` / `_coverage_*` / `_measure_native_index_freshness` / `_attach_native_freshness` | 388–730, 754–838 | `/health`, п.13 |
| `looks_like_src_table` … `mk_opts` | 897–1102 | подписи без мета-имён |
| `empty_after_period_action` … `build_period_empty_answer` | 1140–1327 | честный ноль окна |
| `apply_prior_period`, `period_slot_for_inherit` | 1658–1700 | диалог |
| `_journal_*`, `_ask_journal_write` | 4398–4706 | журнал |
| `answer_checked`, scope helpers | 4710–4878 | decision_id / память |
| `Handler`, `main` | 4881–5088 | HTTP |

**Не переносить:** `period_assumed_needs_clarify`, `warehouse_clarify`,
`axis_focus_plan` (логику влить в readings_menu), тело `answer` 1754–4321
нарушителей, любой код, чьё имя содержит выбор мимо wiki.

### 2.4. Порядок миграции B

| Шаг | Действие | Доказательство |
|---|---|---|
| B0 | Baseline L67 + md5 прод-ask | якорь wrong/меню |
| B1 | Новый файл рядом; bootstrap временно грузит **legacy**; новый не в пути | замок «legacy = runtime» |
| B2 | Перенос §3/§7/§8 (HTTP/health/journal) bit-identical | `test_ask_journal`, `test_health_*`, ручной `/health` |
| B3 | Skeleton `answer`: intent → wiki → no_data/clarify/leader-заглушка | `test_wiki_*` против нового модуля |
| B4 | SQL + compose + gate; measure/axis/window меню одним API | `test_measure_menu_*`, `test_axis_count_*`, `test_compose`, `test_gate` |
| B5 | Flag `ASK_ONEPATH=1` на полигоне; shadow L67 new vs legacy | diff только ожидаемые (нет pre-wiki меню) |
| B6 | Flip default; legacy off; `_patch_z20_wiki_primary` → `return text` (пустой) | `test_wiki_card_hybrid` якоря патча → «patch empty» |
| B7 | `test_one_path.py` полный; удалить legacy; выкат | L67: wrong ≤ 4, silent 0 |

**Число волн:** 7 содержательных (+ B0). Параллель: B2 (инфра) ∥ подготовка
замков; B3–B5 строго последовательны.

### 2.5. Замки при B

| Класс | Что делать |
|---|---|
| Негативы сноса В2–В4 / люка (`test_no_pre_wiki_*`, `test_measure_hatch_luk`, `test_leader_hatch`) | **оставить/усилить** — новый файл обязан не содержать символов |
| Положительные на F/ecp/assumed-pre-wiki (`test_entity_form`, куски `test_action_class`, `test_k4_guess_vs_clarify`) | **переписать в негатив** «вызова нет / до wiki return нет» или удалить |
| Wiki-каскад (`test_wiki_card_hybrid`, `test_wiki_candidate_verify`, `test_wiki_leader_*`, `test_named_type_*`, `test_verify_threshold_*`) | перенацелить импорт на новый z20; суть та же |
| Fork-авто (`test_fork_outcomes` авто A/B) | уже негативы В4 — сохранить; C-меню → только wiki_pool builder |
| HTTP/journal/gate/compose/memory | без переписи логики — зелёные как есть |
| Новый | `test_one_path.py` (статический разбор AST: все clarify через builder; нет SQL до wiki; нет вторых чисел; нет reason-люков) |

Оценка: **переписать/снять ~12–18 файлов**; **оставить зелёными ~10–15**;
**добавить 1** канонический. Не «все 140 test_*.py».

### 2.6. Риски B и снятие

| Риск | Как снять |
|---|---|
| Потеря diag-полей, на которые смотрит L67/прогонщик | чеклист ключей `diag.*` из baseline-журнала; shadow-сравнение |
| Потеря таймингов/`шаг` | перенести `шаг()` 1-в-1 в новый `answer` |
| Health/journal регресс | B2 bit-identical + замки до смены pipeline |
| Дедлайн/AskDeadline дыры | те же вызовы z01 в тех же точках (после intent, до тяжёлого SQL) |
| L67 провал на flip | B5 shadow до критерия; flip только при wrong≤якорь и silent=0; rollback = вернуть bootstrap на legacy |
| «Дописали выбиратель в новом файле» | `test_one_path.py` + запрет патча bootstrap |

**Откатываемость B:** на B1–B5 — мгновенная (флаг/legacy). После B6–B7 —
revert коммита flip + выкат legacy. Выше, чем у A после середины цепочки.

---

## 3. `_bootstrap` / `_patch_z20_wiki_primary` (оба варианта)

Сейчас патч (живой):

1. **net-distinct** в ветке `no_axis_member` и в общем `agg is None` —
   расширяет условие stock-агрегата (скрытый выбор формы счёта);
2. **ef_gate** — `ASK_ENTITY_FORM or entity_form_gate_open(...)`;
3. **ecp↔F reorder** — если в тексте есть маркер swap.

План после финала (A-W7 или B6): функция остаётся для идемпотентности
загрузчика, тело:

```python
def _patch_z20_wiki_primary(text: str) -> str:
    return text
```

| Вариант | Когда патч пустеет | Куда девается логика |
|---|---|---|
| A | последняя волна, после сноса F/ecp и явного SQL net-distinct (или отказа от него как выбирателя) | диск = runtime |
| B | вместе с flip на новый файл | net-distinct только как явная SQL-ступень **после** wiki+src, если ещё нужен по данным; иначе не переносить |

Замки, читающие патч (`test_wiki_card_hybrid`, `test_wiki_leader_not_overridden`,
`test_zone_names_resolvable`): сменить ожидание на «patch is identity».

---

## 4. Сравнение A / B

| Критерий | A — вычистка | B — перепись |
|---|---|---|
| Строки результата | ~3500–4000 (после 8 волн; ≤1500 только ценой почти-B) | **~1100–1500** целевые |
| Волны до «один путь» | 8 (+baseline) | 7 (+baseline) |
| Замки | ~10 переписать + много точечных правок на каждой волне | ~12–18 разово; 1 новый канон |
| Риск L67 | высокий **на каждой** средней волне (общий файл) | высокий один раз на shadow/flip; до flip — изолирован |
| Доказуемость «мимо вики некуда» | сложная (остаточный граф ветвлений) | **простая** (линейный файл + AST-замок) |
| Откат | поволново лёгкий; суммарно тяжёлый | до flip — мгновенный (legacy); после — один revert |
| Потеря diag/health/journal | низкая (код жив) | низкая при B2 bit-identical; контролируется чеклистом |
| Соответствие приказу «убери лишнее / или перепиши» | формально да, но долг комментариев/веток остаётся | **прямое** исполнение второй ветки приказа |
| Риск нового выбирателя | высокий (привычные ветки рядом) | средний (пустой файл легче сторожить замком) |

---

## 5. Рекомендация

**Вариант B — переписать z20.**

Обоснование (по фактам среза, не по вкусу):

1. **Физический инвариант** («некуда мимо вики») на 2695-строчном `answer` с
   ~40 early-return не удерживается вычисткой без того же объёма работы, что
   перепись; после A файл всё ещё ~4k строк с местами для нового люка.
2. **Wiki-каскад уже автономен** (`wiki_hybrid_pool`): до-вики отбор (~480 строк)
   и `arb_pool` (~300) — мёртвый груз относительно формулы; в B их просто нет.
3. **Откат и L67:** shadow+legacy в B дают критерий до выката; A ломает прод-путь
   каждым коммитом в том же файле (как уже видно по «verify-лотерее» —
   лечится только одним путём, не заплаткой).
4. **Патч bootstrap** в B естественно умирает на flip; в A он мешает до W7 и
   провоцирует «диск ≠ runtime» (уже болели на V4c/E–H).
5. Цель «~800–1500» **достижима только в B**; A туда не приводит без
   переписывания `answer` целиком — то есть без того же B под другим именем.

A остаётся запасным, если владелец запретит параллельный файл/флаг; тогда
исполнять A-W1…W8 строго, без попыток «чуть подкрутить» оставшиеся ветки.

---

## 6. План миграции для рекомендованного (B) — шаги

Готов к исполнению **только после слова владельца** (стоп-точка этапа-1).

1. **B0.** Снять L67-якорь и список зелёных z20-замков; записать в
   `docs/audit/onepath/` (отдельный файл замера, не этот).
2. **B1.** `z20_ask_main_http.legacy.py` ← копия текущего; bootstrap по
   умолчанию грузит legacy; заготовка `z20_onepath_body.py` (или сразу новый
   z20 под флагом) не в прод-пути.
3. **B2.** Перенести без правки поведения: health, journal, Handler, gate,
   clarify helpers, period_empty builders. Прогон: journal/health/gate замки.
4. **B3.** Собрать линейный `answer`: z02 → z21 → return. Полигон: entity
   clarify/leader/no_data совпадают с legacy на wiki-кейсах.
5. **B4.** Подключить SQL z17/z06/z07/z08 (+ stock SQL при необходимости) и
   z18; единый `readings_menu` для measure/window/axis; count без measure-меню.
6. **B5.** `ASK_ONEPATH=1` на полигоне; полный L67 shadow; чинить только
   новый файл; молчаливых выборов 0; меню ⊆ wiki-подписи.
7. **B6.** Flip: bootstrap → новый z20; `_patch_z20_wiki_primary = identity`;
   выкат md5; мониторинг `/health` + журнал.
8. **B7.** Включить `test_one_path.py`; удалить legacy; добить wordlists
   (хвост плана В7) отдельной волной вне z20.

Критерий готово: замок one-path зелёный + L67 (wrong ≤ 4, silent 0) + патч
пустой + в коде нет вызовов entity_form/ecp/assumed-pre-wiki/arb_pool-меню.

---

## 7. Общий список сохраняемых внешних модулей (A и B)

Не переписывать (план §3): **z21, z14, z18 compose/gate, z17/z06/z07/z08, z01**.
Использовать как библиотеки. z05/z09/z13 — не звать из нового тракта
(выбиратели/fork-авто); при необходимости только чистые SQL/подписи, уже
разрешённые контрактом.

---

*Конец O2. Сходимость с O1/O3 — на стоп-точке владельца (выбор A или B).*
