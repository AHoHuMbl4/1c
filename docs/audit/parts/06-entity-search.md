# 06. entity-search

Участок: `ubuntu/serenedb/serene_ask.py:2597-3135`.

## Зачем участок нужен
Строит поисковые выражения по понятиям вопроса (`probe`), выбирает порог «сколько понятий совпало» (`match_expr`), раскладывает совпадения по `src_table` (`tables_of`), дополняет частичными и табличными частями (`partial_tables`, `children_by_parent`), даёт кандидатов не из буквального корпуса (`alias_hits`, `card_hits`, `meaning_candidates`). Вспомогательно: предикаты периода, выборка строк, фильтр «только дата».

## Входы
| Функция | Аргументы |
|---|---|
| `_predicates` | `intent` — берёт `intent["period"]` → `period_preds` |
| `_fetch` | `match_sql`, `preds`, `order`, `limit` |
| `probe` | `groups` — список групп альтернатив (слов/фраз) |
| `matched_group_count` | `kinds` — diag от `probe` |
| `with_refs` / `match_expr` | `expr` / `exprs`, `preds` |
| `children_by_parent` | `by`, `match`, `preds` (`preds` в теле не используется) |
| `partial_tables` | `exprs`, `preds`, `best` |
| `tables_of` | `match`, `preds` |
| `date_only_kind_filter` | `by`, `match`, `kind_ok` |
| `keep_empty_period_opts` | `srcs`, `counted`, `preds` |
| `alias_hits` / `card_hits` | `exprs`, `limit` |
| `question_exprs` | `exprs`, `kind_text` |
| `meaning_candidates` | `exprs`, `kind_text`, `question`, `limit`, `exclude=()`, `diag=None` |

Чтений `os.environ` в участке нет. Используются константы модуля (чтение вне участка): `INDEX`/`CORPUS`/`TABLES` (`:77`), `REFS_BOOST` (`ASK_REFS_BOOST`, умолч. `"8.0"`, `:195`), `SCORER`/`SCORERS` (`ASK_SCORER`, умолч. `"bm25"`, `:175-183`), `ALIAS_INDEX` (`ASK_ALIAS_INDEX`, умолч. `'alias_idx'`, `:3749`), `CARD_INDEX` (`ASK_CARD_INDEX`, умолч. `'entity_card_idx'`, `:3754`), `CARD_FIELDS` = `("label","aliases","about","quantities","attrs")` (`:3755`).

## Порядок работы
1. `_predicates(intent)` → `period_preds(intent.get("period"))` (`:2606`).
2. `probe(groups)` (`:2646-2748`):
   - для каждой альтернативы каждой группы строит варианты: `ts_phrase` (exact); при >1 слове — `ts_phrase` со slop (`:2665-2672`); `ts_levenshtein` с `min(2, len//4)` (`:2677-2678`); при непустом `_like_pattern` — `ts_like` (`:2679-2681`);
   - один `UNION ALL` `count(*)` по `INDEX` (`:2683-2689`);
   - на группу берёт наименьший rank среди видов с `n>0` (`exact=0…part=3`) (`:2695-2703`);
   - группы без совпадений: `resolve_values` → иначе `_resolve_values_literal` → иначе `_resolve_values_corpus`; exprs = `ts_phrase` или `ts_like` для corpus_literal (`:2710-2730`);
   - выход: список exprs + `diag` (вид по gi; `_resolved` → значения).
3. `matched_group_count(kinds)` — число ключей-`int` в diag (`:2761`).
4. `match_expr(exprs, preds)` (`:2775-2805`): пусто → `("",0)`; одно → `with_refs(expr), 1`; иначе `UNION ALL` count по `ts_compound(..., k)` для k=n…1, `best` = max k с count>0 (иначе 1); возврат `with_refs(ts_compound(..., best)), best`.
5. `tables_of(match, preds)` — `GROUP BY src_table` по `INDEX` если match иначе `CORPUS` (`:2949-2957`).
6. `partial_tables` — только если `len(exprs)>=2` и `best>1` (`:2892-2894`); уровни k=best…1 через `with_refs(ts_compound)`; в out только `1<=lvl<best` со своим pred (`:2932-2938`).
7. `children_by_parent` — parents из `by`; SQL parent→child в `TABLES`; count по `CORPUS` с pred `split_part(row_key…)` (`:2825-2858`); при `RuntimeError` → `{},{}`.
8. `meaning_candidates` (`:3093-3133`): `question_exprs` (+ `probe([[kind_text]])` при непустом kind); `_fused_candidates(...)`; если `None` — последовательный union: `alias_hits`, `card_hits`, `near_tables(question)`, `near_tables(kind_text)`; фильтр `t not in exclude`.
9. `alias_hits`/`card_hits`: expr = первое или `ts_compound(...,1)`; SELECT `src_table` + scorer, ORDER BY s DESC, src_table, LIMIT; при `RuntimeError` → `[]`.

Вызовы снаружи участка (потребители): основной путь `answer` ~`:11951-12092` (`probe`→`match_expr`→`tables_of`→`partial_tables`→`meaning_candidates`→`date_only_kind_filter`→`children_by_parent`); также `meaning_candidates` `:2153,:2190,:8573`; `alias_hits` `:12943`; `keep_empty_period_opts` `:11094`; `_predicates` `:11313,:11436,:11869,:14468`.

## Выходы
| Функция | Возврат |
|---|---|
| `_predicates` | список SQL-предикатов периода |
| `_fetch` | строки `psql` (row_key, src_table, 0, date, s, doc) |
| `probe` | `(list[expr], diag)` |
| `matched_group_count` | `int` |
| `with_refs` | SQL: `(doc @@ E OR refs @@ (E ^ REFS_BOOST))` |
| `match_expr` | `(match_sql, best_k)` |
| `tables_of` | `{src_table: count}` |
| `partial_tables` | `({t: lvl}, {t: pred_sql})` |
| `children_by_parent` | `({child: n}, {child: pred_sql})` |
| `date_only_kind_filter` | `(kept_by, dropped_srcs)` |
| `keep_empty_period_opts` | `list` src |
| `alias_hits`/`card_hits` | `list[src_table]` |
| `question_exprs` | `list[expr]` |
| `meaning_candidates` | `list[src_table]` без `exclude` |

## Обращения наружу
**HTTP / LLM в участке:** нет.

**SQL через `psql`:**
- `probe`: count по `INDEX` + `doc @@ expr` (`:2683-2689`).
- `match_expr`: count `ts_compound` по `INDEX` (`:2792-2797`).
- `children_by_parent`: `SELECT src_table, parent FROM TABLES…` (`:2831-2832`); count по `CORPUS` (`:2845-2850`).
- `partial_tables`: `src_table,k` по `INDEX` (`:2910-2920`).
- `tables_of` / `_fetch`: SELECT по `INDEX`/`CORPUS` (`:2952`, `:2617-2620`).
- `alias_hits`: `aliases @@` по `ALIAS_INDEX` (`:3022-3025`).
- `card_hits`: OR по `CARD_FIELDS` на `CARD_INDEX` (`:3060-3066`).

**Вызовы вне участка (не SQL в этом файле-диапазоне):** `period_preds`, `resolve_values`, `_resolve_values_literal`, `_resolve_values_corpus`, `_fused_candidates`, `near_tables`, `lit`, `psql`.

## Переключатели
В участке env не читаются. На поведение влияют (определены вне `:2597-3135`):
- `ASK_SCORER` → `SCORER` (умолч. `bm25`) — score в `alias_hits`/`card_hits` (`:3024`, `:3065`).
- `ASK_REFS_BOOST` → `REFS_BOOST` (умолч. `"8.0"`) — `with_refs` (`:2772`).
- `ASK_ALIAS_INDEX` / `ASK_CARD_INDEX` — имена индексов.
- `CARD_FIELDS` — фиксированный кортеж полей карточки.

## Развилки
- `probe`: нет probes → `[], {}` (`:2686-2687`); группа с hit / без → resolver cascade; `corpus_literal` → `ts_like`, иначе `ts_phrase` (`:2725-2728`).
- `match_expr`: 0 / 1 / N exprs (`:2782-2805`); `best` из counts или 1.
- `partial_tables`: `n<2` или `best<=1` → `{},{}`; сущности с `lvl>=best` отбрасываются (`:2933-2934`); `RuntimeError` → `{},{}`.
- `children_by_parent`: пустой `by`/`match`/parents/`pred_by` или ошибка → `{},{}`.
- `date_only_kind_filter`: если `match` или пустой `by` или пустой `kind_ok` — без фильтра (`:2969-2972`).
- `keep_empty_period_opts`: `counted is None` → без реза; есть live → только live; иначе при pred с `doc_date` → все `srcs`, иначе `live` (`:2986-2994`).
- `alias_hits`/`card_hits`: пустые exprs или `RuntimeError` → `[]`.
- `meaning_candidates`: `_fused_candidates is None` → fallback по четырём спискам (`:3122-3132`); итог минус `exclude`.

## Чего здесь нет
- Разбора вопроса / intent (terms, kind) — только потребление готовых групп.
- Выбора сущности моделью, агрегатов, ответа пользователю.
- Векторного отбора корпуса (кроме вызова `near_tables` / `_fused_candidates` снаружи).
- HTTP и вызова языковой модели.
- Чтения env внутри строк 2597–3135.
- Использования аргумента `preds` в теле `children_by_parent`.
- Записи в БД — только SELECT/count.
