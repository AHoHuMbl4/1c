# W1 — карта живости: `ask/z14_clarify_memory.py`

Дата: 12.09.2026. Только чтение кода. Зона 680 строк файла; верхний уровень — 41 символ, 587 строк тел (остальное — шапка модуля, комментарии, `register_zone`, пустые строки).

Метод: AST границ символов + `\bимя\b` по `ubuntu/serenedb/ask/*.py` и `ubuntu/serenedb/test_*.py`; учтены getattr/строковые имена (находок нет). Импорты зон не учитывались — только фактические упоминания в общем namespace.

Вердикты:
- **ЖИВА НОВОМУ** — прямо или транзитивно нужна `z20_ask_main_http.py` (onepath);
- **ТОЛЬКО LEGACY** — нужна `z20_ask_main_http_legacy.py`, после flip+сноса legacy мертва;
- **МЁРТВА** — нет живого зова из нового/legacy (только self/тесты/комментарии).

Тесты сами по себе вердикт тракта не поднимают.

---

## Таблица символов

| символ | строки | кто зовёт (файл:строка) | вердикт |
|---|---:|---|---|
| `_alias_parts` | 5 (9–13) | self: `measure_choice`/:57, `measure_captions`/:91, `resolve_measure`/:129 | **ЖИВА НОВОМУ** (через measure_*) |
| `_word_hits_text` | 5 (16–20) | self: `measure_choice`/:57 | **ЖИВА НОВОМУ** |
| `split_ident` | 5 (23–27) | **new** `z20:900,902` (`human_table_label`); **legacy** `legacy:924,926`; зоны `z18:460` (`measure_label_of`), `z09:928,939`; self: `measure_captions` | **ЖИВА НОВОМУ** |
| `measure_choice` | 54 (30–83) | **new** `z20:1534,1539` (`_settle_measure`); **legacy** `legacy:1502,3329`; зоны `z09` (`_fork_relevant`/:211, `_fork_headline_measure`/:846), `z11:285` (`sales_money_measure`), `z12` (`rank_measure_hint`/:671, `_stock_qty`/:956, `_breakdown_fallback`/:1197), `z16:611` (`pick_measure`); self: `slot_measure_uncovered`; тесты `test_gate`, `test_stock_balance_path` (mock) | **ЖИВА НОВОМУ** ⚠ скрытый выбиратель меры |
| `measure_captions` | 19 (86–104) | **new** `z20:1488` (`_measure_menu_opts`); **legacy** `legacy:3525,3567,3705`; зоны `z18:459` (`measure_label_of`), `z16:516` (`build_measure_empty_pivot`); self: `resolve_measure`; тесты `test_gate` | **ЖИВА НОВОМУ** |
| `resolve_measure` | 33 (107–139) | **new** `z20:1516,1524`; **legacy** `legacy:3375`; тесты `test_gate`, `test_focus_loop` | **ЖИВА НОВОМУ** |
| `slot_measure_uncovered` | 9 (142–150) | **legacy** `legacy:3458`; тесты `test_gate:264,266` | **ТОЛЬКО LEGACY** |
| `_FP_SKIP` | 1 (163) | self: `_slot_fp`/:173 | **МЁРТВА** |
| `_FP_STR` | 1 (164) | self: `_slot_fp`/:178 | **МЁРТВА** |
| `_slot_fp` | 19 (167–185) | self: `answers_diverge`/:217; комментарий `z08:245`; тесты `test_a3_passport` | **МЁРТВА** |
| `answers_diverge` | 34 (188–221) | self: `answers_src_conflict`/:236; docstring `z16:221` (не вызов); тесты `test_a3_passport`, `test_step4_guards`, `test_gate`, `test_compose` | **МЁРТВА** |
| `answers_src_conflict` | 16 (223–238) | только тесты `test_a3_passport`, `test_step4_guards` | **МЁРТВА** |
| `RAW_FOCUS_TRUST` | 1 (244) | self: `guards_skip_for_choice`/:674 | **МЁРТВА** (единственный потребитель мёртв для трактов) |
| `DECISION_TTL_SEC` | 1 (245) | self: `accumulate_resolution`, `issue_decision`, `seal_clarify` | **ЖИВА НОВОМУ** |
| `_DECISION_LOCK` | 1 (246) | self: все API билетов | **ЖИВА НОВОМУ** |
| `_DECISIONS` | 1 (247) | self: issue/consume/peek/purge/reset | **ЖИВА НОВОМУ** |
| `_CLARIFY_BATCHES` | 1 (248) | self: seal/lookup/purge/reset | **ЖИВА НОВОМУ** |
| `_RESOLVED_CHOICES` | 1 (250) | self: peek/accumulate/purge/reset | **ЖИВА НОВОМУ** |
| `question_fingerprint` | 4 (253–256) | self: `_resolved_key`, `issue_decision`, `seal_clarify`, `consume_decision`, `lookup_clarify_batch` | **ЖИВА НОВОМУ** |
| `db_fingerprint` | 15 (259–273) | self: `issue_decision`, `consume_decision`, `peek_decision` | **ЖИВА НОВОМУ** |
| `options_version` | 14 (276–289) | self: `seal_clarify`/:422 (и поле билета) | **ЖИВА НОВОМУ** |
| `ambiguity_of_options` | 12 (292–303) | self: `seal_clarify`/:421 | **ЖИВА НОВОМУ** |
| `_new_decision_id` | 3 (306–308) | self: `issue_decision`/:369 | **ЖИВА НОВОМУ** |
| `_purge_decisions` | 16 (311–326) | self: peek/accumulate/issue/consume/lookup/reset | **ЖИВА НОВОМУ** |
| `_resolved_key` | 3 (329–331) | self: `peek_resolved`, `accumulate_resolution` | **ЖИВА НОВОМУ** |
| `peek_resolved` | 7 (334–340) | **new** `z20:2591,2624`; **legacy** `legacy:4740,4773`; тесты `test_terminal_round` | **ЖИВА НОВОМУ** |
| `accumulate_resolution` | 20 (343–362) | **new** `z20:2623`; **legacy** `legacy:4772`; тесты `test_terminal_round` | **ЖИВА НОВОМУ** |
| `issue_decision` | 42 (365–406) | self: `seal_clarify`/:435 | **ЖИВА НОВОМУ** |
| `seal_clarify` | 53 (409–461) | **new** `z20:2884`; **legacy** `legacy:5035`; тесты `test_decision_id`, `test_terminal_round`, `test_ask_choice_memory` | **ЖИВА НОВОМУ** |
| `consume_decision` | 28 (464–491) | **new** `z20:2593`; **legacy** `legacy:4742`; тесты `test_decision_id`, `test_terminal_round`, `test_ask_choice_memory` | **ЖИВА НОВОМУ** |
| `peek_decision` | 21 (494–514) | self: передаётся в `attach_memory_shadow` → ACM; тесты `test_ask_choice_memory` | **ЖИВА НОВОМУ** |
| `lookup_clarify_batch` | 25 (517–541) | **new** `z20:2595`; **legacy** `legacy:4744` | **ЖИВА НОВОМУ** |
| `reissue_clarify` | 19 (544–562) | **new** `z20:2596`; **legacy** `legacy:4745` | **ЖИВА НОВОМУ** |
| `reset_decisions_for_tests` | 6 (565–570) | только тесты: `test_decision_id`, `test_terminal_round`, `test_ask_choice_memory`, `test_ask_journal` | **МЁРТВА** (оффлайн-хелпер) |
| `attach_memory_shadow` | 12 (573–584) | **new** `z20:2870,2885`; **legacy** `legacy:5021,5036`; тесты `test_ask_choice_memory` | **ЖИВА НОВОМУ** |
| `choice_proven` | 7 (587–593) | **new** `z20:1565` (`_settle_axis`); **legacy** `legacy:3640`; зона `z11:323` (`sales_ticket_hatch` — сам мёртв); self: `guards_skip_for_choice`; тесты `test_decision_id` | **ЖИВА НОВОМУ** |
| `choice_levels_proven` | 17 (596–612) | self: `measure_already_proven`, `entity_choice_locked`; тесты `test_terminal_round` | **ЖИВА НОВОМУ** |
| `measure_already_proven` | 5 (615–619) | **new** `z20:1510`; **legacy** `legacy:3480,3485,3553,3665`; зона `z10:66` (`total_question_skips_axis` ← **new** `z20:1579`); self: `hold_settled_entity`; тесты `test_terminal_round` | **ЖИВА НОВОМУ** |
| `entity_choice_locked` | 3 (622–624) | **new** `z20:1933`; **legacy** `legacy:1523,2435,2437,2481`; self: `hold_settled_entity`; тесты `test_terminal_round`, mock в `test_stock_balance_path` | **ЖИВА НОВОМУ** |
| `hold_settled_entity` | 35 (627–661) | **new** `z20:1934,2600,2630`; **legacy** `legacy:2438,4749,4779`; тесты `test_terminal_round`, mock `test_stock_balance_path` | **ЖИВА НОВОМУ** ⚠ выбиратель src |
| `guards_skip_for_choice` | 13 (664–676) | зона `z15:17` (`stop2_active` — **ни new, ни legacy не зовут**; только тесты); тесты `test_decision_id` | **МЁРТВА** |

---

## Итог зоны

| | строк символов | доля от 587 |
|---|---:|---:|
| **всего тел символов** | **587** | 100% |
| **ЖИВА НОВОМУ** | **487** | 83% |
| **ТОЛЬКО LEGACY** | **9** | 2% |
| **МЁРТВА** | **91** | 15% |
| файл целиком | 680 | — |

**Вердикт зоны для одного пути: НУЖНА.** Ядро decision_id / seal / consume / resolved / memory / measure menus / hold_settled — прямо в новом z20. После flip можно снести только `slot_measure_uncovered` (9 строк) и мёртвый блок A3/stop2 (`answers_*`, `_slot_fp`, `guards_skip_for_choice`, `RAW_FOCUS_TRUST`, test-reset) — ~91+9 строк, не всю зону.

### Bootstrap / imports / wire

| файл | роль |
|---|---|
| `_bootstrap.py:37` | зона всегда в `_ZONE_FILES` (грузится и при onepath, и при legacy) |
| `_imports.py` | имён зоны нет |
| `_wire.py` | имён зоны нет; `register_zone('ask.z14_clarify_memory', …)` в конце файла |

---

## Транзитивные цепочки (до нового / legacy z20)

### До нового z20

```
split_ident ← human_table_label ← new z20
measure_captions ← _measure_menu_opts ← new z20
measure_captions / split_ident ← measure_label_of(z18) ← new z20:1213,1294,1687
_alias_parts / _word_hits_text ← measure_choice ← _settle_measure ← new z20
measure_choice ← sales_money_measure(z11) ← _measure_dimension ← _unit_for_measure ← new z20:1828
resolve_measure / measure_already_proven / measure_choice ← _settle_measure ← new z20
choice_proven ← _settle_axis ← new z20
measure_already_proven ← total_question_skips_axis(z10) ← new z20:1579
entity_choice_locked / hold_settled_entity ← new z20 (Handler)
peek_resolved / consume_decision / lookup_clarify_batch / reissue_clarify
  / accumulate_resolution / hold_settled_entity ← new z20 (decision path ~2591–2630)
seal_clarify / attach_memory_shadow ← new z20 (~2870–2885)
  └ issue_decision / ambiguity_of_options / options_version / question_fingerprint /
    db_fingerprint / _new_decision_id / _purge_* / _DECISIONS / _CLARIFY_BATCHES
peek_decision ← attach_memory_shadow ← new z20
choice_levels_proven ← measure_already_proven | entity_choice_locked ← new z20
```

### Только legacy (нет в новом)

```
slot_measure_uncovered ← legacy:3458
measure_choice ← pick_measure(z16) ← legacy:3337
measure_choice ← rank_measure_hint(z12) ← legacy (коммент/бывший путь; зов legacy:3313 область)
measure_choice ← _fork_relevant / _fork_atom_of(z09) ← legacy:2377,2393,2921,2940
measure_captions ← build_measure_empty_pivot(z16) ← legacy:3450
```

(символы из этих цепочек, которые новый уже зовёт иначе — остаются **ЖИВА НОВОМУ**, не «только legacy».)

### Никуда из трактов (мёртвые цепочки)

```
answers_src_conflict ← только тесты
answers_diverge ← answers_src_conflict | тесты
_slot_fp / _FP_* ← answers_diverge
guards_skip_for_choice ← stop2_active(z15) ← только тесты (new/legacy не зовут)
RAW_FOCUS_TRUST ← guards_skip_for_choice
reset_decisions_for_tests ← только тесты
sales_ticket_hatch(z11) ← choice_proven  — hatch сам ниоткуда не зовётся
```

---

## Скрытые выбиратели, доступные новому тракту

| # | символ / цепочка | что выбирает кодом | риск для «одного пути» |
|---|---|---|---|
| S-z14-1 | **`measure_choice`** ← `_settle_measure` (new:1534,1539) | меру по слову вопроса (`exact`/`alias`/`base`/`substring`/`single`) без меню; меню только при `how=='ask'` | **Да** — молчаливый выбор величины. В onepath частично смягчён (при `ask` → alts), но silent-ветки живы |
| S-z14-2 | **`measure_choice`** ← `sales_money_measure` ← `_unit_for_measure` (new:1828) | какое поле считать «деньгами» для единицы | Слабый: не src/ось/период ответа, только валютная подпись |
| S-z14-3 | **`hold_settled_entity`** (new:1934,2600,2630) | src: settled vs focus по билету/found_by/holder | **Да** — выбирает сущность кодом после билета (задумано как память выбора, не меню) |
| S-z14-4 | **`resolve_measure`** | текст человека → имя поля | Нет (разбор ответа меню, не скрытый выбор) |
| S-z14-5 | **`ambiguity_of_options`** | тип clarify (entity/measure/axis/period) | Нет (классификация меню) |

Legacy-only выбиратели через z14 (`pick_measure`, fork `_fork_headline_measure`, `rank_measure_hint`, `slot_measure_uncovered`) в новый тракт **не** протянуты прямым зовом z20; косвенно `measure_choice`/`measure_captions` уже живы своим путём.

---

## Тесты (замки), трогающие зону

| замок | символы z14 |
|---|---|
| `test_gate.py` | `measure_choice`, `measure_captions`, `resolve_measure`, `slot_measure_uncovered`, `answers_diverge` |
| `test_decision_id.py` | `seal_clarify`, `consume_decision`, `guards_skip_for_choice`, `choice_proven`, `reset_decisions_for_tests` (+ `stop2_active` снаружи) |
| `test_terminal_round.py` | seal/consume/accumulate/peek_resolved/hold/`measure_already_proven`/`entity_choice_locked`/`choice_levels_proven`/reset |
| `test_ask_choice_memory.py` | seal/consume/`attach_memory_shadow`/`peek_decision`/reset |
| `test_a3_passport.py` | `answers_diverge`, `answers_src_conflict` |
| `test_step4_guards.py` | `answers_diverge`, `answers_src_conflict` (+ `stop2_active`) |
| `test_compose.py` | `answers_diverge` |
| `test_focus_loop.py` | `resolve_measure` |
| `test_ask_journal.py` | `reset_decisions_for_tests` |
| `test_stock_balance_path.py` | mock `measure_choice`, `entity_choice_locked`, `hold_settled_entity` |
| `test_measure_*` / `test_no_pre_wiki_reorders.py` | строковая проверка `measure_captions(` в исходнике z20 |

---

## Краткий вывод

Зона **жива одному пути** (~83% строк символов): билеты clarify, меню мер с подписями, settle меры/оси, память выбора, shadow-memory. После сноса legacy останется снести крошку (`slot_measure_uncovered`) и уже мёртвый A3/stop2-блок. В новый тракт зона тащит два заметных кодовых выбора: **молчаливый `measure_choice`** и **`hold_settled_entity`**.
