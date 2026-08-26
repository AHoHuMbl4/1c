# 16. veto-pick-entity

Участок: `ubuntu/serenedb/serene_ask.py:7743–8360` (тело `aggregate` с `:8360` — вне участка).

## Зачем участок нужен

Набор чистых проверок выбора сущности/величины и двух функций с I/O: `pick_measure` (имена величин + опционально `rerank`) и `pick_entity` (SQL + `ds_chat`). `alias_supported` решает, подтверждает ли словарь синонимов выбор. `measure_ambiguous` / `unresolved_quantity` / `pick_measure` — какую величину считать или спросить. Вспомогательные (`not_for_excludes`, `veto_top_without`, `figures_numbers`, `same_number`, mute/rival, empty-pivot) обслуживают арбитраж и пустые итоги.

## Входы

| Функция | Аргументы |
|---|---|
| `alias_supported:7743–7744` | `known`, `hit`, `cand_family`, `leader_family`, `veto=None`, `rank_cand`, `rank_leader`, `undisputed=False` |
| `not_for_excludes:7814` | `kind_stems` (множество основ), `items` — пары `(основы, есть_указатель)` |
| `pair_unanswered:7852` | `writer`, `answered` |
| `single_is_rival:7865` | `picked_first`, `sole` |
| `veto_top_without:7876` | `top` — пары `(t,s)`, `excluded` |
| `figures_numbers:7887` | `out` dict (`figures`, `diag.measure_totals`) |
| `same_number:7907` | `ours`, `theirs` (список) |
| `unresolved_quantity:7933` | `measure`, `alts`, `want`, `compute`, `names`, `totals_by` |
| `mute_measure_blocks:7956` | `sole`, `mute`, `cand_src` |
| `filter_dead_measure_alts:7989` | `alts`, `totals` (строки totals_of) |
| `measure_asked_explicitly:8000` | `word`, `measure`, `how`, `measure_pick` |
| `build_measure_empty_pivot:8032–8033` | `question`, `dead`, `src`, `alive_totals`, `cut`, `diag`, `t0`, `intent`, `how`, `measure_pick` |
| `measure_ambiguous:8088` | `fits` (имена), `totals` (dict имя→число) |
| `pick_measure:8107` | `src_table`, `question`, `word` (`question` в теле не используется) |
| `pick_entity:8155` | `question`, `kind`, `cands`, `counts`, `match`, `diag` |
| `_vec/_num/_numN:8332–8356` | `text` / `x` |

Env внутри `7743–8360` не читаются; используются модульные флаги (см. Переключатели).

## Порядок работы

1. **`alias_supported:7772–7811`**: `known` ложь → `True`. `veto is None` → `ALIAS_VETO`. `not veto` или пустой `leader_family` → `bool(hit)`. `VETO_HEAD_WINS ∧ undisputed ∧ rank_cand==0` → `True`. При `VETO_NEEDS_RANK` и `rank_leader is not None`: `rank_leader<0` или `0≤rank_cand<rank_leader` → `True`; иначе `cand_family == leader_family`.
2. **`not_for_excludes:7848–7849`**: `kind_stems` непусто и ∃ запись: `kind_stems ⊆ st` и `not ptr`.
3. **`pair_unanswered` / `single_is_rival` / `veto_top_without`**: булевы/фильтр списка (`7862`, `7873`, `7884`).
4. **`figures_numbers:7895–7904`**: из `figures.sum` или `.count`, плюс значения `diag.measure_totals`.
5. **`same_number:7914–7931`**: `_intent_number` + `round(...,2)`; совпадение с любым из `theirs`.
6. **`unresolved_quantity:7941–7953`**: есть `measure`/`alts` → как есть; иначе нужен `want=="sum"` или `compute∈{sum,max,min,avg}`; 0 имён → `(None,[])`; 1 → `(name,[])`; `measure_ambiguous` → `(None,names)`; иначе `(names[0],[])`.
7. **`mute_measure_blocks:7961–7971`**: по `mute` с `measure_ambiguous` и другими числами → `src` блокирующего; иначе `None`.
8. **`measure_row_all_zero` / `alive_measure_names` / `filter_dead_measure_alts:7974–7997`**: нулевые итоги; опции только из «живых»; пустой `totals` → `alts` без среза.
9. **`measure_asked_explicitly:8002–8008`**: `measure_pick∧measure` → True; иначе `how∈{exact,substring,alias,base,single}` и непустой `word`.
10. **`format_`/`build_measure_empty_pivot:8011–8085`**: текст RU/EN, passport, `kind=answer`, `diag.measure_empty_pivot`.
11. **`measure_ambiguous:8096–8104`**: `<2` fits → False; иначе `len({float(totals[m])})>1`.
12. **`pick_measure:8131–8152`**: `measures_of` → `measure_choice`; если `how!='rerank'` — возврат; иначе `rerank` + правило base-prefix → `(base,[],'base')` или `(top,[],'rerank')`.
13. **`pick_entity:8168–8329`**: `<2` cands → `(cands[:1],{},{})`; SQL labels/parent; `<2` names → короткий возврат; SQL `map_keys(nums)` для top; `signal_terms` при `match`; бюджет `PICK_BUDGET`; `ds_chat(PICK_SYS)`; разбор JSON/`\d+`; проверка `quantity` через `measures_of`; `(picked|[], marks, plan)`.
14. **`_vec`/`_num`/`_numN:8332–8356`**: литерал вектора / float / float-or-None.

## Выходы

| Функция | Возврат | Потребитель (вне участка) |
|---|---|---|
| `alias_supported` | bool | `answer` `:13017` |
| `not_for_excludes` | bool | фильтр `:12267` |
| `veto_top_without` | список пар | `:12964` |
| `pair_unanswered` / `single_is_rival` / `mute_measure_blocks` | bool / bool / src\|None | арбитраж `:13564`, `:13669–13670` |
| `figures_numbers` / `same_number` | list / bool | `:13550–13551`; внутри mute |
| `pick_entity` | `(list src, marks, plan)` | `:12754` |
| `pick_measure` | `(got, alts, how)` | `:13934` |
| `unresolved_quantity` | `(measure, alts)` | `:13979` |
| `measure_ambiguous` | bool | `:13927`; внутри unresolved |
| `filter_dead_measure_alts` / `measure_asked_explicitly` / `build_measure_empty_pivot` | list / bool / dict ответа | `:14066–14080` |
| `_vec`/`_num`/`_numN` | SQL-литерал / float / float\|None | вызывающие вне участка |

## Обращения наружу

| Что | Место | Назначение |
|---|---|---|
| SQL `SELECT src_table, label, parent FROM search_tables WHERE src_table IN (...)` | `pick_entity:8174–8175` | подписи и parent |
| SQL `string_agg(DISTINCT map_keys(nums)…)` по `search_corpus` | `pick_entity:8212–8215` | имена величин верхних кандидатов |
| `ds_chat([PICK_SYS, user])`, `max_tokens=120` | `pick_entity:8277–8279` | выбор типов + plan |
| `rerank(word, names)` | `pick_measure:8137` | запасной выбор величины |
| `measures_of` / `measure_aliases_of` / `measure_choice` | `8131–8134`, `8327` | данные/правило величины |
| `signal_terms` / `disambiguate_labels` | `8239`, `8191` | типичные термы; подписи |
| `measure_captions` / `build_answer_passport` / `atom_from_agg` / `_diag_pack` | `build_measure_empty_pivot:8037–8085` | ответ-пивот |
| `embed_one` | `_vec:8333` | вектор для SQL |
| HTTP | нет в участке | — |
| SQL/LLM в `alias_supported`…`measure_ambiguous` (кроме pick_*) | нет | чистые функции |

## Переключатели

Чтение env — вне участка; использование здесь:

- `ASK_ALIAS_VETO` → `ALIAS_VETO` (`:3782`, умолч. `'1'`→True); в `alias_supported:7774–7777` если `veto is None`.
- `ASK_VETO_HEAD_WINS` → `VETO_HEAD_WINS` (`:3830`, умолч. `'1'`); `:7780`.
- `ASK_VETO_NEEDS_RANK` → `VETO_NEEDS_RANK` (`:3820`, умолч. `'0'`→False); `:7797`.
- `ASK_PICK_BUDGET_CHARS` → `PICK_BUDGET` (`:92`, умолч. `8000`); обрезка списка `:8259`.
- `ASK_TERMS_FOR` → `TERMS_FOR` (`:103`, умолч. `3`); окно meas `TERMS_FOR*4` `:8210`, marks `:8238`.
- `ASK_TERMS_TOP` → `TERMS_TOP` (`:112`, умолч. `6`); `signal_terms(..., TERMS_TOP)` `:8239`.

Иных env в `7743–8360` нет. Константы `TABLES`/`CORPUS` (`:77`), `PICK_SYS` (`:3376`).

## Развилки

- `known=0` → alias всегда True (`7772–7773`).
- Мягкое вето (`veto=False`) / нет `leader_family` → только `bool(hit)` (`7776–7779`).
- Head-wins: undisputed + `rank_cand==0` → True без сравнения семей (`7780–7796`).
- Rank-гейт: лидер вне круга (`rank_leader<0`) или cand выше лидера → True (`7807–7810`); иначе равенство семей (`7811`).
- `pick_entity`: 0–1 cand / SQL fail / `<2` labels / модель недоступна → короткий кортеж или `RuntimeError("entity-pick-unavailable")` (`8168–8177`, `8193–8194`, `8280–8285`).
- Несколько `types` в ответе модели → список `picked` длиной >1 (`8324–8329`).
- `quantity` не из `measures_of(picked[0])` → в `plan` уходит `quantity_rejected` (`8325–8328`).
- `pick_measure`: не-rerank путь vs rerank+base (`8135–8152`).
- `measure_ambiguous`: разные float-итоги → True (`8096–8104`).
- Empty-pivot: кириллица в `question`/`dead_label` → RU-текст, иначе EN (`8020–8029`).

## Чего здесь нет

- Вызова `alias_supported`/`pick_*` из HTTP-хендлера — только определения; оркестрация в `answer`.
- Записи в БД, OData, сборки `intent`/`cands`/`match`.
- Тела `aggregate` (сигнатура `:8359`, реализация после `:8360`).
- Чтения env внутри строк `7743–8360`.
- Использования аргумента `question` внутри `pick_measure` (есть в сигнатуре, в теле нет).
- Векторного выбора сущности в `pick_entity` (только `ds_chat`).
