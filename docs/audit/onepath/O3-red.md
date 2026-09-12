# O3: красная команда — атака проектов «одного пути»

Срез: 12.09. Только чтение `O1-map.md`, `O2-project.md`, диска
`ubuntu/serenedb/ask/z20_ask_main_http.py` (5094), `_bootstrap.py`, соседних
`z01`–`z22`, замков `ubuntu/serenedb/test_*.py`. Код не менялся.

Мера — контракт владельца 12.09 (`docs/audit/snos15-ONEPATH_PLAN.md`):

```
вопрос → wiki-каскад → SQL → меню при >1 прочтении любого рода → выбор → ответ
```

Люков нет. Вторых чисел нет. Обходов вики нет. Count — мера не спрашивается.
Критерий: мимо вики физически некуда; clarify — только единым построителем.

Цель отчёта — **дыры**, не подтверждение O1/O2.

---

## 1. Дыры (список)

| № | В чём (O1/O2) | Файл:строка | Почему дыра против контракта |
|---|---|---|---|
| 1 | **O1** полнота | `z20:1768–1774` (`apply_period_leader`, `expand_readings_calendar_axis`, `expand_readings_currency_axis`, prefer day/currency) | В таблице §2.2 свалено в «parse_intent + prior + preds» как **СТУПЕНЬ**. На диске `prefer_window_leader` **молча пишет** `intent["period"]` (`z03:600–610`) до вики. Окно — прочтение; молчаливый лидер окна = выбиратель **до** каскада. В §5 `def`/`class` этих вызовов нет (они из z03/z04). |
| 2 | **O1** вердикт | `z20:1929–2109` (+ хвост до ~2419: not_for / sum-filter / fork_early) | Помечено **СТУПЕНЬ*** («кормит z21»). O2 и сам z21 (`wiki_hybrid_pool`, каскад 843–884): `cands` на выбор сущности **не влияет**. Этот блок кормит arb_pool/early/fork — то есть **нарушителей**, не ступень формулы. Завышение «ступеней» ~480 строк. |
| 3 | **O1** полнота карты блоков | незакрытые диапазоны внутри `answer`, суммарно ~341 строк; крупные: `2539–2566`, `2617–2663`, `2686–2732`, `3138–3184`, `4037–4063`, `1831–1845` | Таблица §2 объявлена полной (74 блока = 5094). Между помеченными блоками живёт логика: сбор `служебные`/`writer` (2567+), `signals_disagree` уже частично покрыт, но **схлопывание** `len(opts)==1 → picked=[opts[0]]` (`3138–3139`) — вне блока «меню 3117–3137»; `extra_vals`/`_cmp_form_locked` перед compose (`4037–4063`) не размечены. Карта **дырява по полноте покрытия**, не только по ярлыкам. |
| 4 | **O1** вердикт / «мимо» | `z20:2479–2503` + §4 п.8 | Focus-путь верно назван обходом каскада. Но §6 O1 предлагает оставить trusted/focus без повторного каскада как «выбор человека» — **без условия**, что `focus` пришёл из **этого** построителя/`decision_id`. Сырой `focus` в HTTP (`Handler` ~4992+) по комментарию сам по себе защиту не даёт, но ветка `if focus:` всё равно **пропускает** `wiki_primary_entity_cascade`. Дыра: «билет ОК» и «любой focus» смешаны. |
| 5 | **O1** вердикт | `z20:3299–3388` + `3502–3505` | «Смесь» / auto `_live[0]` отмечены, но **не** вынесены в сводку §0 как отдельный класс скрытого выбора меры (наравне с net/ef). При одном «живом» totals код сам берёт меру — без вики-прочтения меры. Для контракта это либо ступень «одно прочтение», либо нарушение — нужна явная норма; сейчас O1 оставляет двусмысленность. |
| 6 | **O1** vs факт «8 выходов» | `z20:1761…2459` | Ввод задачи / план ждали «≥8 early». На диске **7** явных `return` до вызова каскада (YoY, calendar unavailable, coverage, assumed-period, unmatched, empty pool, axis_focus) + **1** skip каскада по `focus`. Итого 8 путей — счётно верно, но O1 §4 раздувает до 21 пункта, смешивая **пост-каскадные** меню мер/осей (п.16–17) с «мимо вики». Меряет разное: «мимо каскада сущностей» ≠ «мимо формулы». Путает O2 при сносе «смысла меню». |
| 7 | **O1** мёртвый держатель | `z20:1641` `warehouse_clarify` | Вердикт «не зовётся в answer» **верен** (единственное определение в z20; вызовов нет). Но склад-clarify ещё фигурирует в `z13`/`z12` (`stock_skips_warehouse_clarify`). Карта z20-only **не показывает**, что обход может жить вне файла — для «одного пути» мало снести def в z20. |
| 8 | **O2** B эскиз порядка | O2 §2.2 шаги 2 и 6; факт `z20:1768–1774`, `z03:581–611` | Шаг 2: «calendar/currency readings → список (ещё НЕ меню)» **до** wiki. Шаг 6: меню окна/оси **внутри/после** SQL. Контракт: при >1 окне — меню **до** SQL (иначе SQL уже с чужим лидером). Эскиз либо сохраняет молчаливый `apply_period_leader` (выбиратель), либо считает SQL без выбранного окна (ложные числа). **Порядок ступеней в B сломан.** |
| 9 | **O2** B / A сохранение | O2 §2.1 §3 + §2.3: перенос `_coverage_answer` «без изменений»; O1 `z20:754–838`, `1815–1830` | O1 верно: coverage — **отдельный SQL+LLM путь мимо z21**. O2 тащит его bit-identical в B как «инфра п.13». П.13 — про объявление неполноты, не про второй тракт ответа. В B остаётся легальный обход вики. |
| 10 | **O2** B запрет зон | O2 §7: «z05/z09/z13 — не звать»; count-гашение | `count_defer_measure_clarify` живёт в **`z05_entity_form.py:740`**, зовётся из z20 (`3473`, `3534`). Запрет z05 целиком **убивает** контрактное «count — мера не спрашивается», если функцию не перенести. В эскизе B4 «count без measure-меню» написано, источника символа — нет. |
| 11 | **O2** B упущение ступеней/библиотек | — | В «не переписывать» (§7) есть z21/z14/z18/z17/z06–08/z01. **Нет явного контракта** на: `z03`/`z04`/`z04b` (окна/оси как прочтения), `z11` (`sales_compare_*`, терминал `z20:3720–3756`), `z12` (stock SQL; в шаге 6 упомянут вскользь), `z15` (`atom_from_agg` / distinct-terminal `3980–4036`), слой мер `pick_measure`/`measure_choice`/`measure_captions` (captions в **z14:86**, pick — не z14), `z19.stale_note` (Handler `5044`), `seal_clarify`/`consume_decision` (z14; Handler `5026`, `answer_checked` `4732+`). Без них B либо молча потеряет форматы L67, либо заново напишет выбиратели. |
| 12 | **O2** B новый скрытый выбиратель | §2.2 шаг 5–6; перенос `mk_opts`/`pick_measure` не запрещён явно в «Не переносить» | «Одно прочтение → сразу ответ» без правила *кто* фиксирует единственную меру/ось: текущий `pick_measure` / `kind_axis_rerank` (`z20:3607–3609`) / net-distinct «как явная SQL-ступень» (O2 §3) — всё ещё **код выбирает форму счёта**. Эскиз не требует, чтобы единственная мера/ось/агрегат были **исходом wiki- или ticket-решения**, а не эвристики. |
| 13 | **O2** B инфра отказов | Handler `z20:5047–5076` | Таймаут `AskDeadline` → 503 unavailable; Exception → «БД недоступна» / «модель не отвечает». В линейном `answer()` B (§2.2) этих исходов нет; в рисках (§2.6) дедлайн упомянут, **отказы 1С/LLM — нет**. `deadline_hit` сейчас вшит в fork-блоки (`2363`, `2900`), которые B сносит — **точки дедлайна исчезают**, если не поставить новые. |
| 14 | **O2** B билеты | §2.2 шаг 5 vs `answer_checked`/`seal_clarify` | Память выбора (z14) в §7 «не трогать», но в pipeline нет: seal после clarify, consume до answer, reissue при err, `hold_settled_entity`. Риск: новый `answer()` примет сырой focus и снова обойдёт вики (дыра №4), либо потеряет decision_id → L67 «меню-вопросы» станут no_data/wrong. |
| 15 | **O2** замки — имена | O2 A-W3 `test_early_clarify_*`; B2 `test_health_*`; B §2.5 `test_named_type_*`, `test_wiki_leader_*`, `test_verify_threshold_*`, `test_no_pre_wiki_*` | Файлы: ровно **один** `test_early_clarify_atom_fps_hashable.py` (не семейство early-clarify на поведение меню); `test_named_type_filter.py`; `test_wiki_leader_not_overridden.py`; `test_verify_threshold_menu.py`; `test_no_pre_wiki_reorders.py`. Wildcard **создаёт ложное ощущение покрытия**. Лишних несуществующих имён (кроме будущего `test_one_path`) нет; завышен объём «зелёных семейств». |
| 16 | **O2** A-W1 привязка замка | O2: assumed-period → «частично `test_period_empty`» | `test_period_empty` — про **пост-SQL** «0 за окно», не про pre-wiki assumed clarify (`period_assumed_needs_clarify` / `test_k4_guess_vs_clarify`). Неверная карта регрессии волны. |
| 17 | **O1+O2** diag/L67 | O2 §2.6 «чеклист diag.*»; O1 не даёт списка полей | Прогонщик/L67 смотрит не только kind/text. Снос doubt/fork/arb_pool/`wiki_verify`/`measure_ambiguous`/`early_clarify_path` без таблицы полей → ложные **honest_no/wrong** при том же смысле ответа. Чеклиста в проектах нет — только намерение. |
| 18 | **O2** рекомендация B без стоп-условий | O2 §5 | Рекомендация B как будто эскиз уже удовлетворяет приказу. Дыры №8–14 делают **исполнение B в текущем виде** нарушением того же контракта, который B якобы чинит. |

---

## 2. Вердикт по вариантам

### A — вычистка z20

**Вердикт: жизнеспособен как миграция, дыряв как доказательство «одного пути».**

Плюсы (по факту диска, не по вкусу): сохраняет SQL-хвост (period_empty, stock, compare, atoms, gate), Handler-отказы, journal, билеты; поволновый откат; O2-список A1–A15 в целом бьётся с нарушителями O1.

Минусы против контракта:

- После 8 волн файл ~3500–4000 строк — места для нового люка остаются (сам O2 это признаёт).
- Карта O1, по которой чистят, **недосчитала** silent window-leader (дыра №1) и **переоценила** до-вики match/rank как ступень (№2) — волны A-W1/W6 могут снести не то / оставить не то.
- `test_one_path` в конце (A-W8) — поздно: люк можно внести в W3–W5.

**До исполнения A доделать:** (1) переклассифицировать `apply_period_leader`/expand_readings: либо меню окон до SQL, либо запрет лидера при len(readings)>1; (2) не считать до-вики candidate-pipeline ступенью; (3) ввести каркас `test_one_path` **с W0/W1**, наращивать; (4) сырой focus ≠ ticket; (5) вынести/сохранить `count_defer` явно.

### B — переписать z20

**Вердикт: дыряв в эскизе; жизнеспособен только после закрытия дыр №8–14.**

Плюсы: единственный реалистичный путь к доказуемому инварианту «мимо вики некуда» (линейный файл + AST-замок); shadow+legacy до flip; патч bootstrap умирает естественно; цель ≤1500 строк достижима только так.

Минусы текущего O2-эскиза (блокеры):

1. Порядок окон/осей vs SQL (№8).
2. Coverage-тракт как второй путь (№9).
3. Запрет z05 без переноса count-гашения (№10).
4. Нет явной проводки z03/04/11/12/15/14-seal/z19/deadline (№11, №13, №14).
5. Не запрещён скрытый выбор единственной меры/оси/агрегата (№12).

**До исполнения B доделать (минимум в план, не в код):** переписать §2.2 так, чтобы при >1 любом прочтении меню было **до** SQL; coverage только через тот же pipeline или честный no_data после wiki; whitelist внешних символов (включая count_defer, seal/consume, stale_note, stock/compare/atom); правило «единственная мера/ось = ticket | единственный кандидат из данных без эвристики-ранжира | wiki»; точки `deadline_hit` вне fork; `test_one_path` с B1.

---

## 3. Финальная рекомендация

**B — после обязательной правки эскиза (стоп-точка владельцу: не «B как в O2», а «B + закрытие дыр 8–14»).**

Почему не A: приказ — «физически некуда мимо вики». Вычистка 4k-строчного `answer` с ~40 return этого не доказывает; O1 уже показал ≥7 pre-wiki return + focus-skip, и дыра №1 в «ступенях» показывает, что даже карта сноса слепа к выбирателю окна. A оставляет тот же класс дефекта («verify-лотерея» / второй механизм), только реже.

Почему не «B сразу»: эскиз O2 сам вводит/сохраняет обходы (coverage, silent readings, возможный снос count через z05, потеря deadline/ticket). Исполнять B в текущем виде — нарушить контракт новым файлом.

Расхождение с O2: **направление то же (B), допуск к этапу-2 — нет**, пока эскиз не переписан. A — только если владелец запретит parallel/legacy; тогда A с усиленным `test_one_path` с волны 0, не «как написано W8 в конце».

---

## 4. Замки: сверка имён O2 ↔ `test_*.py`

| Упоминание O2 | Факт на диске |
|---|---|
| `test_one_path` | **нет** (планируется) — ок |
| `test_ask_journal`, `test_gate`, `test_compose`, `test_entity_form`, `test_action_class`, `test_k4_guess_vs_clarify`, `test_period_empty`, `test_measure_hatch_luk`, `test_fork_outcomes`, `test_atom_terminal`, `test_measure_menu_not_silent`, `test_axis_count_plain`, `test_verify_threshold_menu`, `test_no_pre_wiki_reorders`, `test_step4_guards`, `test_wiki_card_hybrid`, `test_wiki_leader_not_overridden`, `test_zone_names_resolvable`, `test_stock_balance_path`, `test_leader_hatch`, `test_ask_choice_memory`, `test_journal_fields`, `test_focus_loop`, `test_wiki_captions_builder`, `test_wiki_candidate_verify`, `test_k4_axis_and_names` | **есть** |
| `test_health_*` | 3 файла: `test_health_gap`, `test_health_native_freshness`, `test_health_tick_status` |
| `test_fork_*` | 5 файлов (detector/outcomes/atom/window/label) — не все про «авто A/B» |
| `test_early_clarify_*` | **только** `test_early_clarify_atom_fps_hashable.py` |
| `test_wiki_leader_*` / `test_named_type_*` / `test_verify_threshold_*` / `test_no_pre_wiki_*` | по одному файлу каждый (см. дыру №15) |
| `test_warehouse_*` (O1) | `test_warehouse_axis_autonomy`, `test_warehouse_aggregate_breakdown` — не `test_warehouse_clarify` |
| Лишние несуществующие имена | не найдены (кроме `test_one_path`) |

O2 не перечисляет ряд живых z20-замков, которые B заденет поведением: `test_axis_focus`, `test_compare_sales`, `test_decision_id`, `test_k4_clarify_vs_nodata`, `test_measure_empty`, `test_post_gate_none_src`, `test_rank_leader_path`, `test_sales_*`, `test_terminal_round`. Не «лишние имена», а **дыра покрытия плана замков**.

---

## 5. Риски L67 при B (классы эталона)

Якорь среза (из activeContext): **22 match / 41 honest_no / 4 wrong / 0 молчаливых**.

| Класс эталона | Что может упасть при B | Механизм |
|---|---|---|
| **Count / «сколько записей»** | match→wrong или clarify вместо числа | Потеря `count_defer_measure_clarify` (z05) → мерное меню; или net-distinct/stock SQL не перенесены → другое число |
| **Меню-вопросы (entity/measure/axis/window)** | match↔honest_no | Смена источника меню (early/fork → только wiki_pool); другие подписи; потеря `seal_clarify`/`decision_id` → нельзя выбрать → повтор без билета |
| **Assumed / длинное окно** | honest_no→wrong или reverse | Снос pre-wiki assumed-clarify без меню окон **до** SQL: либо молчаливый период (молчаливый выбор — хуже якоря 0), либо ответ по другому окну |
| **Формат ответа (atom / compare / distinct_axis)** | wrong при «том же» смысле | Неперенос `sales_compare` terminal, `atom_from_agg`/`render_atom_pair`, distinct-axis terminal → другой text/figures при том же agg |
| **Диагностика doubt / fork / wiki_verify** | ложный wrong/honest_no | Прогонщик классифицирует по diag/kind; чеклиста полей в O2 нет (дыра №17) |
| **Coverage / about=полнота** | отдельная корзина | Bit-identical `_coverage_answer` сохранит поведение, но **нарушит** one-path замок; вырезание без замены → no_data/unavailable |
| **Таймаут / широкие вопросы** | unavailable↔wrong | Исчезновение `deadline_hit` вместе с fork → либо зависание/другой 503, либо «дожать» SQL и выдать сомнительный ответ |
| **«Движений в регистре X» (verify-лотерея)** | нестабильный match/меню | Как раз цель B; на shadow возможен временный рост wrong, пока меню каскада не единственный исход tie — критерий B5: silent=0 важнее удержать match |

---

## 6. Что должно войти в `test_one_path` (формулировки, не код)

Статический (AST/текст загружаемого z20 + `_patch_z20_wiki_primary`):

1. **Единый построитель clarify:** любой `kind=="clarify"` (или return с `options`) в `answer`/`answer_checked` строится только через канонический API меню (`clarify_opts_response` / `readings_menu` / эквивалент); нет вызовов `try_entity_form*`, `try_event_count_period_clarify`, `warehouse_clarify`, `axis_focus_plan` как return-пути; нет `reason=`-люков из чёрного списка (assumed-period, early_clarify_path, fork_outcome, yoy_need_sales_context, …).
2. **SQL только после wiki-решения:** в `answer` нет вызовов `aggregate`/`rows_of`/`totals_of`/`aggregate_groups`/`aggregate_stock*`/`psql` отбора строк **до** вызова `wiki_primary_entity_cascade`, за исключением путей, помеченных как ticket-replay (`trusted`/`resolved` из consume_decision) или чистого health/coverage-отказа без чисел данных (если coverage оставят — отдельный негатив: coverage не вызывает wiki → **падение**, пока не влит в pipeline).
3. **Нет вторых чисел:** в ветках `kind in (answer, figures)` нет сборки второго числового контура «для человека» (нет headline/второго atom в тексте; gate белый список — одно множество figures); запрет паттернов «снятие допущения» / dual-sum в ответе.
4. **Патч bootstrap — identity:** `_patch_z20_wiki_primary` возвращает текст без net-distinct/ef_gate/ecp-reorder вставок.
5. **Сырой focus не обходит вики:** ветка пропуска каскада допустима только при доказанном ticket (`trusted`/`resolved` после `consume_decision`); иначе каскад обязателен.
6. **Окно/ось/мера при >1:** нет присваивания `intent["period"]` лидером/`prefer_*` при `len(readings)>1` без предшествующего clarify-меню; нет `pick_measure`/`kind_axis_rerank`→одиночный выбор при `len(alts)>1`; count-путь не вызывает measure-меню (`count_defer` или эквивалент присутствует и зовётся).
7. **Меню-подписи:** clarify-options обогащаются wiki/captions API (нет обязательных имён `src_table`/`catalog_` в `label` уходящих options) — стык с `test_k4_meta_names` / `test_wiki_captions_builder`.
8. **Чёрный список символов-выбирателей** в загружаемом модуле: `arb_pool` меню, `code_ambiguous` expand picked, `period_assumed_needs_clarify`, fork-outcome авто A/B, `ask_back` return-path (имена уточнить по финальному API).

Динамический (минимум на полигоне, можно тем же файлом или соседним):

9. На фиксированном наборе: каждый clarify-ответ имеет `options` из построителя; ни один answer не содержит двух независимых величин в figures; вопросы count не получают measure-options.
10. Shadow-критерий к L67-якорю: wrong ≤ 4, молчаливых выборов 0, меню ⊆ wiki-подписи — как в плане; плюс **нет** pre-wiki `kind=clarify` с reason из чёрного списка.

---

## 7. Краткая сводка атаки

| Вопрос задачи | Ответ красной |
|---|---|
| Полнота O1 | **Нет** — пропущен silent window-leader; ~341 строк вне таблицы; post-menu collapse; внешние склад-пути |
| Верность вердиктов O1 | **Частично** — до-вики match/rank ошибочно «ступень»; focus/ticket смешаны; мера auto-_live недоформализована; warehouse_clarify в z20 мёртв (верно) |
| Полнота B (O2) | **Нет** — порядок window/SQL; coverage; z05/count; z11/12/15/14-seal/z19/deadline; русские captions названы, отказы LLM/1С — нет |
| Новый выбиратель в B | **Да** — readings+leader до wiki; net-distinct «как SQL»; неспецифицированный pick единственной меры/оси |
| Замки | Имена в основном реальны; wildcards завышают покрытие; `test_one_path` ещё нет; ряд живых замков не в плане B |
| L67 | Риск на count, меню+билеты, формат atom/compare, diag, assumed-window, deadline |

*Конец O3. Сходимость с владельцем: выбирать не «A/B из O2», а «B после закрытия дыр 8–14» или «A с усиленным замком с W0».*
