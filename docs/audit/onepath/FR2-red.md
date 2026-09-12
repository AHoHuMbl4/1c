# FR2-red — атака финального диффа S2 (E1+E2)

Дата: 12.09.2026. Режим: **read-only** + локальные прогоны замков.
Код / git / psql / полигон / прод не менялись. Чужие `FR*.md` не читались.

Опора: `S2-a.md` §1–2, `S2-b`/`S2-c`/`S2-d`, `E1-impl.md`, `E2-final.md`;
дифф `ubuntu/serenedb/ask` + замки на диске.

---

## Вердикт одной строкой

**Дифф готов к коммиту/выкату.** Продуктовых регрессий в коде не найдено;
замки-жертвы зелёные. Есть **мягкие щели в `test_one_path` (а–е)** — замок
не ловит часть мысленных поломок в одиночку, но они закрыты соседними замками
(`test_wiki_homonym_menu`, `test_measure_menu_not_silent`) и живым кодом.
Список обязательных правок перед коммитом: **пуст**.

---

## 1. Снос-чистота

### 1.1 KEEP («НЕ ТРОГАТЬ», S2-a §2) — живы

| Символ / класс | Статус |
|---|---|
| Щели S1: `question_expects_accounting_data`, `_NON_DATA_MARKERS`, `pair_slots_only`, `atom_terminal_gate_text`, `stock_balance_is_sales_noise`, fork-labels, `_fork_sum_headline_pool` / `_fork_headline_doc_measures` | top-level на месте |
| `_measures_by_src`, `_FORK_MEAS_TTL`, `_fork_meas_cache` (z08) | на месте |
| `_sql_ident` | **только** `z04b:20`; копия в z04 снята (зовы z04 идут через bindings) |
| Silent-тройка: `measure_choice`, `_pick_kind_axis_col`, `stock_net_register_pair` | живы + переписаны E1 |
| Соседи: `entity_form_catalogs_for_kind`, `live_axis_col_for_count`, `aggregate_compare_sales`, `kind_axis_hits` / `term_axis_hits` / `rank_axis_resolve` | живы |
| Выборка X1-образцов (`answer`, wiki-cascade, `readings_menu`, …) | 0 missing |

### 1.2 DEL 119 — мёртвы

- 118 имён из §1.2–1.3 + снос `def _sql_ident` в z04 → **119**.
- Top-level определений DEL в `ask/z*.py`: **0**.
- `getattr` / `globals().get` / `__dict__['…']` на DEL: **0**.
- Живые code-refs на DEL в ask/ (вне `#`): **нет**.
  - `z20:266` — слово `clarify_text` **в комментарии** docstring `_opt_values`.
  - `z11:4` — имя `sales_rank_engaged` **в комментарии** шапки модуля.
- Тестовые упоминания DEL — GONE/absence-asserts или docstring; прогоны зелёные.

**Атака «зовёт ли кто снесённое»:** нет callers / dynamic load. Замки, что
раньше звали тела, сужены до GONE (E2-final совпадает с фактом прогона).

---

## 2. Одноимённые (guard z21)

Код: `wiki_homonym_kind_peers` + вызов в `wiki_outcome_from_verify` **после**
`len(yes)==1 ∧ rest no ∧ axes ok`, **до** `outcome=leader`
(`z21_wiki_choice.py:896–914`).

| Кейс | Ожидание | Факт (оффлайн-проба логики) |
|---|---|---|
| Пул=1, один yes | leader | leader |
| Разные name/stem, разные kind, yes/no | leader | leader |
| Одинаковое name, doc vs reg, yes/no | clarify (peers) | clarify |
| Пустые name, общий OData-stem, разные kind | clarify | clarify |
| Один kind, одинаковое name, yes/no | leader (контракт S2-b: только **другой** kind) | leader |
| Уникальный лидер среди пула с чужими именами | leader | leader |

Порог verify (один yes / yes+unsure / два yes) не сломан:
`test_verify_threshold_menu` **4/0** (фикстуры с различимыми именами → leader).
Поведенческий якорь guard: `test_wiki_homonym_menu` **10/0**.

**Ложная тревога (не регресс, контракт):** пересечение по **stem** при разных
человеческих `name` → clarify. Так задумано в S2-b (name **или** stem). Лишние
меню возможны у пар `document_X` / `accumulationregister_X` с разными подписями —
это не silent leader и не поломка одиночных различимых лидеров.

**Меню уверенного лидера:** guard не смотрит на score/threshold отдельно — он
только на одноимённость kind-peers. Уверенный единственный yes без peer → leader
как раньше.

---

## 3. Silent-тройка

| Символ | >1 | 1 | Silent `[0]` / `sorted_s[0]` / `max(others` |
|---|---|---|---|
| `measure_choice` (z14:30+) | `(None, alts, 'ask')`; ветки `base` сняты | `single` / единственный exact\|alias\|substring | `[0]` только после фильтра длины 1 |
| `_pick_kind_axis_col` / `live_axis_col_*` (z05) | `None`; кандидаты в `_*_candidates` | `cands[0]` при `len==1` | `kind_axis_rerank` / `matched[0]` / `hits[0]` нет |
| `stock_net_register_pair` + `stock_net_pair_candidates` (z12) | `None` / ambiguous → `stock_net_register_menu_opts` | единственная пара | `sorted_s[0]` / `max(others` нет; `[0]` только при `len(receipts\|expenses)==1` |

До SQL в `answer` (`z20:2024–2088`):

- мера → `readings_menu("measure")`;
- kind-axis count → `live_axis_col_candidates` → при >1 `readings_menu("axis")`;
- stock-net → `stock_net_register_menu_opts` → `readings_menu("entity")`.

SQL `aggregate_stock_net_distinct` при неоднозначной паре возвращает `None`
(нет молчаливого числа). Замок `test_measure_menu_not_silent` **12/0**
(в т.ч. «без how=base при >1»).

Краевой (не блокер): `exact = […]; return exact[0]` без явного `len(exact)==1` —
при двух полях с одинаковым `lower()` теоретический silent; на практике имена
величин в одной сущности уникальны без учёта регистра.

---

## 4. Замок `test_one_path` 77/0 — мысленный разлом (а–е)

Прогон этой сессии: **77/0**.

| Пункт | Что ломаем | Покраснеет? | Оценка |
|---|---|---|---|
| **(а)** bare `Dict kind=clarify` в `answer` / hybrid | вернуть bare Dict | **да** | крепко |
| **(а)** убрать `readings_menu` из hybrid | | **да** | крепко |
| **(б)** hatch / `render_atom_pair` / SECOND_KEYS | | **да** | крепко |
| **(в)** SQL_CALLS lineno < wiki | | **да** (один call-site wiki → walk=min) | OK на текущем дереве |
| **(г)** FORBIDDEN call-site в z20 | вернуть `prefer_window_leader(` | **да** | крепко для **списка** |
| **(г)** вернуть снесённый `try_rank_period_clarify` / `wiki_leader_alive` / … в z20 | | **нет** — имён нет в FORBIDDEN | **щель замка** |
| **(г-silent)** вернуть `how='base'` в `measure_choice`, оставив `'ask'` рядом | | **нет** (one_path); **да** в `test_measure_menu_not_silent` | слабо в one_path |
| **(г-silent)** silent winner в `stock_net_pair_candidates`, тонкий `stock_net_register_pair` чист | | **нет** (смотрите только тело pair) | **щель** |
| **(г-silent)** `_pick_kind_axis_col`: `return cands[0]` без `len==1`, плюс любой `return None` | | **нет** (маркер `return None` / отсутствие `matched[0]`) | **щель** |
| **(д)** оставить строку `wiki_homonym_kind_peers`, игнорировать `peers` | | **нет** в one_path; **да** в `test_wiki_homonym_menu` | слабо в one_path |
| **(е)** identity `_patch_z20_wiki_primary` | сломать патч | **да** | крепко |

Чёрный список: старый FORBIDDEN + контракт тройки + маркеры homonym + (е)
identity — **на месте как в S2-d**. Полнота «все 119 DEL запрещены как call-site
в z20» — **нет** (и не требовалась буквально S2-d; зона покрыта сносом + zone/GONE).

Итог по замку: **77/0 честный на текущем диффе**, но **не самодостаточный**
сторож silent/homonym — опирается на соседние 10/0 и 12/0.

---

## 5. Замки-жертвы (оркестратор не гонял / доп. срез)

Все доступные из списка — **зелёные**. Регрессий нет; «жертв правды» (устаревшие
ожидания) в красных прогонах нет — красных нет.

| Замок | Итог |
|---|---|
| `test_b9_routing` | 7/0 |
| `test_k4_guess_vs_clarify` | 13/0 (+2 pending) |
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
| `test_ask_journal` | 11/0 (live skip — контур) |
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
| `test_health_*` (имена из ТЗ) | **файлов нет**; ближайшие: `test_health_gap` 23/0, `test_health_native_freshness` 32/0, `test_health_tick_status` 14/0 |

Контроль S2 рядом: `test_one_path` 77/0, `test_zone_names_resolvable` 96/0,
`test_wiki_homonym_menu` 10/0, `test_measure_menu_not_silent` 12/0,
`test_ab_ambiguous_set` 19/0, `test_ab_calendar_axis_set` 24/0.

Окруженческие (не дефект диффа): как в E2 — embed-секрет / пакет `mcp` вне этого
прогона.

---

## 6. Вердикт и список правок

### Готов к коммиту/выкату: **да**

Обязательных правок `файл:строка`: **нет**.

### Не блокеры (усиление замка — по желанию оркестратора, не условие выката)

1. `test_one_path.py` (г-silent): сканировать тело `stock_net_pair_candidates`, не
   только `stock_net_register_pair`; для `_pick_kind_axis_col` требовать
   `len(cands) == 1` перед `[0]`.
2. `test_one_path.py` (г-silent): запрет `'base'` / `how == "base"` в
   `measure_choice` (дубль `test_measure_menu_not_silent`).
3. `test_one_path.py` (д): AST-проверка `if peers: return clarify`, не только
   наличие имени `wiki_homonym_kind_peers`.
4. `test_one_path.py` (г): опционально добавить call-site запрет ключевых DEL
   (`try_rank_period_clarify`, `wiki_leader_alive`, …) — сейчас ловят GONE-замки
   зон.

### Вне скоупа (как в E1/E2)

Лотерея «реализациятмц» doc-vs-reg без одноимённости в пуле verify — качество
модели; при попадании обоих в пул guard уже → меню. Заплатки «предпочесть
регистр» запрещены.

---

## 7. Метод

- AST presence KEEP/DEL + grep Name / `getattr` / `globals().get` по `ask/` +
  `test_*.py`.
- Чтение guard / тройки / `answer` pre-SQL меню.
- Оффлайн-проба `wiki_outcome_from_verify` на табличных кейсах.
- Локальные `python3 test_*.py` (без psql-полигона / без git).

**Числа:** DEL 119/119 gone; KEEP sample 0 missing; one_path 77/0; жертвы — все
зелёные; обязательных правок 0.
