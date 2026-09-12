# E1-impl — исполнение S2-b / S2-c / S2-d-(а)

Дата: 12.09.2026. Код изменён; git-мутаций нет; psql/полигон/прод не трогались.
Опора: `docs/audit/onepath/S2-b.md`, `S2-c.md`, `S2-d.md` (пункт (а) builder).

---

## 1. S2-b — одноимённые → меню (`z21`)

| Что | Где |
|---|---|
| `_homonym_norm` / `_homonym_keys` | `ask/z21_wiki_choice.py:819+` |
| `wiki_homonym_kind_peers` | `ask/z21_wiki_choice.py:847+` |
| Guard перед `outcome=leader` | `ask/z21_wiki_choice.py:871–914` |

Поведение: после «ровно один yes + остальные no» и успешного `wiki_validate_leader_axes` —
если в том же пуле verify есть peer с тем же `norm(name)` **или** OData-stem и
**другим** kind → `clarify` + `candidates=peers`, diag `wiki_homonym_tie` /
`wiki_homonym_blocked_leader`. Вердикт `no` соседа **не** вычёркивает.
Различимые имена / один kind / пул из одного — лидер как раньше.

Замок: `test_wiki_homonym_menu.py` (10/0).

---

## 2. S2-d-(а) — wiki-clarify через построитель

| Что | Где |
|---|---|
| `try_wiki_hybrid_entity_pick` clarify | `ask/z21_wiki_choice.py:1175` — `return readings_menu(question, "entity", opts, …)` |

Было: bare `Dict{kind:clarify,…}`. Стало: тот же путь подписей
(`mk_opts` → `disambiguate_labels` / kind-хвост → `wiki_menu_captions`), обёртка
только через `readings_menu` → `clarify_opts_response`.

Моки оффлайн-замков (`test_wiki_candidate_verify`, `test_wiki_card_hybrid`)
дополнены `readings_menu` / `human_table_label`.

---

## 3. S2-c — три silent-выбирателя

### 3.1 `measure_choice` (`z14`)

- Ветки silent `how=base` (alias и substring) **сняты**: при `len(covered|same)>1`
  всегда `(None, alts, 'ask')` (`z14:60–67`).
- `_settle_measure` / `readings_menu("measure")` без изменений по контракту.
- `_stock_qty_measure_name`: без `names[0]` и без `base`; sole через
  `_stock_qty_measure_candidates` (`z12`).

Ожидания: `test_gate.py` (base→ask), `test_measure_menu_not_silent.py`.

### 3.2 `_pick_kind_axis_col` (`z05`)

- `_kind_axis_col_candidates` — список cols без `kind_axis_rerank` / `[0]`
  (`z05:663+`).
- `_pick_kind_axis_col` — sole → col; иначе `None`.
- `live_axis_col_candidates` + `live_axis_col_for_count` (sole only)
  (`z05:706+`, `735+`).
- `count_defer_measure_clarify` опирается на `bool(candidates)`, не на победителя.
- В `answer` до SQL: при count и `len(kax)>1` → `axis_clarify_options` по
  подмножеству → `readings_menu("axis")`; sole → `grain_dec.col`
  (`z20:~2055–2075`).
- `axis_clarify_options`: одноимённые labels → `split_ident(col)` (`z18:27+`).

### 3.3 `stock_net_register_pair` (`z12`)

- `stock_net_pair_candidates` — уникальные пары + ambiguous regs; noise/cost/corpus
  как **отсев**, не `sorted_s[0]` / `max(others)` (`z12:1000+`).
- `stock_net_register_pair` — ровно одна пара → взять; иначе `None` (`z12:1122+`).
- `stock_net_register_menu_opts` — подписи из вики/`human_table_label` + роль
  приход/расход (`z12:1062+`).
- В `answer` до SQL: при stock-count без subject и `len(opts)>1` →
  `readings_menu("entity", …)` (`z20:~2080–2090`).

---

## 4. Прогоны замков

| Замок | Итог |
|---|---|
| `test_one_path.py` | **41/0** (полный (а–д) — не этот шаг; E2) |
| `test_zone_names_resolvable.py` | 96/0 |
| `test_wiki_captions_builder.py` | 24/0 |
| `test_k4_meta_names.py` | 15/0 |
| `test_wiki_leader_not_overridden.py` | 10/0 |
| `test_measure_menu_not_silent.py` | 12/0 |
| `test_axis_count_plain.py` | 13/0 |
| `test_wiki_card_hybrid.py` | 65/0 |
| `test_compose.py` | 93/0 |
| `test_gate.py` | 56/0 |
| `test_intent.py` | 162/0 |
| `test_stock_balance_path.py` | 36/0 |
| `test_action_class.py` | 8/0 |
| `test_wiki_candidate_verify.py` | 64/0 |
| `test_verify_threshold_menu.py` | 4/0 |
| `test_wiki_homonym_menu.py` (новый) | **10/0** |

### Окруженческие (помечены, не дефект кода E1)

| Замок | Причина |
|---|---|
| `test_ask_embed_native.py` | `RuntimeError: эмбеддер недоступен: KeyError` (нет живого embed-секрета в среде) |
| `test_focus_loop.py` | `ModuleNotFoundError: No module named 'mcp'` (нет пакета mcp в окружении) |

Живой smoke / L67 / полигон — **не** делались (по заданию).

---

## 5. Вне скоупа (как в проектах)

- Снос мёртвых символов ~2.2k — **E2**.
- Расширение `test_one_path` до полного (а)(б)(в)(г-silent)(д) — **E2** / S2-d целиком.
- Заплатки «предпочесть регистр» — запрещены; одноимённые лечатся меню.

---

## 6. Файлы диффа

Код: `z21_wiki_choice.py`, `z14_clarify_memory.py`, `z05_entity_form.py`,
`z12_stock_balance.py`, `z20_ask_main_http.py`, `z18_compose.py`.

Замки/ожидания: `test_gate.py`, `test_measure_menu_not_silent.py`,
`test_wiki_candidate_verify.py`, `test_wiki_card_hybrid.py`,
`test_wiki_homonym_menu.py` (новый).

Граф: наблюдения на зоны ask + сущность `test_wiki_homonym_menu.py`
(коммит `mcp-memory.json` — вне этого шага: git-мутаций нет).
