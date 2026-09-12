# FR1-red — атака финального диффа S2 (E1+E2)

Дата: 12.09.2026. Режим: **read-only** + локальные прогоны замков.
Код / git / psql / полигон / прод не менялись. Чужие FR-*.md не читались.

Опора: `S2-a.md` §1–2, `E1-impl.md`, `E2-final.md`, `S2-d.md`;
диск `ubuntu/serenedb/ask/*` + перечисленные замки.

---

## Вердикт одной строкой

**Дифф готов к коммиту/выкату.** Поведенческих регрессий по коду E1+E2 и по
прогону «замков-жертв» не найдено. Находки ниже — мягкость `test_one_path` и
остаточные silent вне тройки S2-c; **правок кода волны не требуют**, если не
ставить отдельную задачу на ужесточение замка / хвосты KEEP.

---

## 0. Что атаковалось

| # | цель | метод |
|---|---|---|
| 1 | Снос-чистота S2-a | AST top-level DEL/KEEP; grep Name; getattr/globals |
| 2 | Homonym-guard z21 | чтение условия + кейсы; `test_wiki_homonym_menu` |
| 3 | Silent-тройка | ветки z14/z05/z12 + меню в `answer` до SQL |
| 4 | Сила `test_one_path` 77/0 | мысленный слом (а)–(е) |
| 5 | Замки-жертвы | локальный прогон списка ТЗ |

Дифф ask/: **+343 / −2496** (17 файлов) — согласуется с заявленным.

---

## 1. Снос-чистота

### 1.1 DEL (119) — тела сняты

AST top-level `def`/`Assign` по `ask/*.py`: **0** символов из S2-a §1 ещё
определены. `getattr(..., 'DEL')` / `globals().get('DEL')` в ask/: **0**.

Упоминания DEL в `test_*.py` — assert'ы GONE / чёрные списки (ожидаемо после
S5). В ask/ остались **только комментарии** (`sales_rank_engaged` в шапке z11,
`RERANK_TOP`/`_slot_fp`/`answers_diverge` в комментариях, `CLARIFY_SYS` в
комментарии z07) — не Call/Load.

### 1.2 KEEP §2 — всё живо

| KEEP | где def |
|---|---|
| щели S1 (`question_expects_accounting_data`, `_NON_DATA_MARKERS`, `pair_slots_only`, fork_labels_*, atom/stock noise, `_fork_figures_of`, sales headline щели, `_measures_by_src` + `_FORK_MEAS_*`) | z02/z11/z15/z21/z08 |
| `_sql_ident` | **только z04b** (def); z04 зовёт через `apply_bindings` — копия z04:9–11 снята |
| silent-тройка + `live_axis_col_for_count` / `entity_form_catalogs_for_kind` / `aggregate_compare_sales` / `aggregate_stock_net_distinct` / `kind_axis_hits` / `term_axis_hits` / `rank_axis_resolve` / `ASK_JOURNAL` | на месте |

Пересечения сноса с живыми соседями z05/z12 (каталоги/compare/stock settle) —
не задеты: функции на диске, `py_compile`/`test_one_path`/`zone` зелёные.

### 1.3 Атака «зовётся ли снесённое»

Нет live-caller из ask/. Замки зовут имена только как «GONE» / blacklist.
**Дыры нет:** снос не оставил висячий Call на удалённое тело.

---

## 2. Одноимённые (guard z21)

Код: `wiki_homonym_kind_peers` → в sole-yes ветке `wiki_outcome_from_verify`
(`z21:896–914`).

| кейс | ожидание | факт по коду |
|---|---|---|
| пул=1 | лидер | `len(pool)<2` → `[]` → leader |
| разные имена/stem, один yes + остальные no | лидер | нет пересечения keys |
| один kind, даже same name | лидер | kind== → skip peer |
| same name/stem, **разный** kind, yes+no | clarify + peers | guard; verify=no соседа не вычёркивает |
| ≥2 yes / yes+unsure | clarify (старый tie) | guard не входит (другая ветка) |
| axis_reject | none | до peers |

**Одиночные различимые лидеры не ломаются.** Порог verify (ровно 1 yes + все
прочие no) не ослаблен — guard только *добавляет* clarify поверх уже
законного sole-yes.

Ложный меню-риск (атака): stem после первого `_` совпал у разных kind при
разных человеческих именах → clarify. Это **намеренно** (кейс FooBar в
`test_wiki_homonym_menu`); одиночный лидер с уникальным stem/именем — нет.

**Остаток вне S2-b (не регресс волны):** same name + **same kind** ×2 → всё ещё
silent leader (замок явно фиксирует). Лотерея Catalog×Catalog не закрыта.

Прогон: `test_wiki_homonym_menu.py` **10/0**; `test_verify_threshold_menu.py` **4/0**.

Clarify-путь hybrid: `readings_menu` (`z21:1173+`) — builder-only.

---

## 3. Silent-тройка

### 3.1 `measure_choice` (z14)

- `len(names)==1` → sole; `len(covered|same)>1` → `(None, …, 'ask')`; silent
  `how=base` снят.
- `_settle_measure`: при `ask` → `None, alts`; в `answer` →
  `readings_menu("measure")` **до SQL** (`z20:2028–2035`).
- Краевой (не silent among equals): `exact[0]` при нескольких именах с одним
  `.lower()` — экзотика 1С-имён; не путь «>1 разных мер».

### 3.2 `_pick_kind_axis_col` / axis count (z05 + z20)

- Кандидаты без `matched[0]`/`kind_axis_rerank`; pick = sole or None.
- `answer`: `live_axis_col_candidates` → `len>1` → `axis_clarify_options` →
  `readings_menu("axis")`; sole → `grain_dec.col` (`z20:2054–2077`).
- Теоретическая щель: `len(_kax)>1` и `len(_k_opts)≤1` (оси не покрыли cols) →
  нет меню и нет sole. На одном `refcols_of` маловероятно; **не воспроизведено**.

### 3.3 `stock_net_register_pair` (z12 + z20)

- Пары/ambiguous без `sorted_s[0]`/`max(others)`; cost/corpus — **отсев**, не
  выбор среди равных.
- `len(pairs)!=1` или ambig → `None`; меню `stock_net_register_menu_opts` →
  `readings_menu("entity")` до SQL (`z20:2078–2088`).
- Меню только при `stock_count_aggregate_without_subject` — контракт пути
  stock-count, не общий entity-picker.

### 3.4 Residual silent **вне** тройки (атака на «всё silent умерло»)

| место | что | вердикт |
|---|---|---|
| `sales_money_measure` → `_fork_sum_headline_pool` → `pool[0]` | KEEP/SR1 щель | не E1/E2; не трогать в этой волне |
| z11/`entity_rank_v2` ещё принимают `how in (…,'base')` | мёртвый acceptor | E1 снял producer; риск только при возврате `base` |
| `kind_axis_rerank` (z17) всегда `[cols[order[0]]]`; зов из `rank_axis_resolve` (z10) | silent sole по rerank | **не в тройке S2-c**; FORBIDDEN только call в z20/z05 |

Это **не блокеры коммита S2**, но честный красный хвост: контракт «silent→меню»
закрыт для тройки, не для всего ранжирования осей.

---

## 4. Полный замок `test_one_path` 77/0 — сила

Прогон этой сессии: **77/0**.

| проверка | слом → краснеет? | мягкость |
|---|---|---|
| **(а)** bare `Dict{kind:clarify}` в answer/hybrid / вне builder\|journal | да | сильная на AST return/Dict |
| **(б)** hatch-имена / `render_atom_pair` / second-number keys | да на известные ключи | обход новым ключом payload |
| **(в)** SQL_CALLS lineno &lt; wiki + ticket-guards | да | список SQL конечен |
| **(г)** FORBIDDEN call-sites в **z20** | да для списка | **нет** запрета def/call в z10/z17; DEL-имена вроде `wiki_leader_alive` / `sales_rank_engaged` **не** в FORBIDDEN |
| **(г-silent)** | частично | `_pick_kind_axis_col` / `stock_net_register_pair` — только тонкое тело: winner можно вернуть в `_kind_axis_col_candidates` / `stock_net_pair_candidates` и замок останется зелёным; `measure_choice` — наличие строк `'ask'` / `len(names)==1`, не полнота всех `>1→ask` веток |
| **(д)** homonym | слабо в one_path | достаточно *вызвать* `wiki_homonym_kind_peers` (тело `return []` → 77/0 зелёный). Поведение держит **`test_wiki_homonym_menu`**, не one_path |
| **(е)** identity `_patch_z20_wiki_primary` | да | сильная |

Чёрный список: старый FORBIDDEN + упоминания silent-контракта + call
`wiki_homonym_kind_peers` + identity — **как в S2-d, на месте**. Не «полон» в
смысле всех 119 DEL — и не обязан: часть покрыта GONE-замками зон.

**Итог по замку:** 77/0 — хороший сторож регресса *текущего* диффа, но **не
доказательство** «peers нельзя выхолостить» / «silent нельзя вернуть в
хелпер». Красная оценка силы: **средняя**; опора на suite рядом
(homonym_menu, measure_menu_not_silent, zone).

---

## 5. Замки-жертвы (оркестратор не гонял / список ТЗ)

Все прогнаны локально в этой сессии. **Красных нет.**

| замок | итог |
|---|---|
| `test_b9_routing` | 7/0 |
| `test_k4_guess_vs_clarify` | 13 ok, 0 FAIL, 2 pending |
| `test_k4_clarify_vs_nodata` | 7/0 |
| `test_fork_label_daybasis` | 27/0 |
| `test_rank_leader_path` | 27/0 |
| `test_sales_canon_prefer` | 29/0 |
| `test_early_clarify_atom_fps_hashable` | 4/0 |
| `test_final_stock_route_filters_absent` | 11/0 |
| `test_verify_threshold_menu` | 4/0 |
| `test_named_type_filter` | 16/0 |
| `test_wiki_candidate_verify` | 64/0 |
| `test_atom_terminal` | 5/0 |
| `test_answer_atom` | 5/0 |
| `test_caveat` | PASS |
| `test_decision_id` | 24/0 |
| `test_ask_choice_memory` | 45/0 |
| `test_ask_journal` | 11/0 (live skip — окружение) |
| `test_journal_fields` | 22/0 |
| `test_measure_hatch_luk` | 16/0 |
| `test_no_pre_wiki_reorders` | 41/0 |
| `test_enough` | 9/0 |
| `test_measure_empty` | 7/0 |
| `test_wiki_card_hybrid` | 67/0 |
| `test_rank_axis_anchor` | 60/0 |
| `test_sales_rank_canon` | 16/0 |
| `test_trace_rid` | 10/0 |
| `test_terminal_round` | 24/0 |
| `test_health_gap` / `_native_freshness` / `_tick_status` | 23/0, 32/0, 14/0 |

Дополнительно (не в списке жертв, для опоры §2–4): `test_one_path` 77/0,
`test_zone_names_resolvable` 96/0, `test_wiki_homonym_menu` 10/0,
`test_measure_menu_not_silent` 12/0.

Окруженческие (как у E1/E2, не регресс диффа): embed-секрет / пакет `mcp` —
сюда не входили.

---

## 6. Список правок (если ужесточать — не блокер волны)

Блокирующих `файл:строка` для коммита **нет**.

Опциональный hardening (отдельный шаг, не S2-обязательство):

1. `ubuntu/serenedb/test_one_path.py` — расширить (г-silent) на тела
   `_kind_axis_col_candidates` / `stock_net_pair_candidates`; (д) — assert что
   при same-name/diff-kind peers непустой (или оставить опору на
   `test_wiki_homonym_menu` явно в комментарии замка).
2. `FORBIDDEN_SELECTORS` — добавить часто возвращаемые DEL
   (`wiki_leader_alive`, `sales_rank_engaged`, …) если нужен сторож
   re-introduce в z20.
3. Вне скоупа S2: `ask/z17_aggregate_groups.py:377` (`kind_axis_rerank` →
   всегда один col) + потребитель `z10_rank.py:255` — silent вне тройки;
   `ask/z11_sales.py:145` (`pool[0]`) — KEEP.

---

## 7. Итог

| вопрос ТЗ | ответ |
|---|---|
| Снос чист, KEEP живы? | **да** |
| Homonym ломает одиночных лидеров / ложный меню при законном лидере? | **нет** (same-kind same-name — остаток вне S2-b) |
| Silent-тройка >1→меню, 1→sole, меню через readings_menu до SQL? | **да** |
| 77/0 слаб? | **частично** (д)/(г-silent) — см. §4; suite рядом закрывает |
| Жертвы красные? | **нет** (все зелёные) |
| Коммит/выкат? | **да** |

Числа прогона FR1: one_path 77/0; zone 96/0; жертвы списка ТЗ — 0 FAIL;
homonym 10/0; DEL defs ask 0; KEEP defs missing 0.
