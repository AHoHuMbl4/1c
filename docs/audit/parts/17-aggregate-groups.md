# 17. aggregate-groups

## Зачем участок нужен

Участок `ubuntu/serenedb/serene_ask.py:8359–8878` считает итоги по всему множеству строк (`aggregate`) и разрезы GROUP BY по оси ссылки (`aggregate_groups`), плюс вспомогательные функции осей (`refcols_of`, `kind_axis_*`, `term_axis_*`, `axis_clarify_options`, `resolve_member_names`). Числа берутся SQL-агрегатами в базе, без LIMIT на цифру (LIMIT только на число групп в ответе). Со строки `8881` начинается другая секция (`ANSWER_SYS` / формулировка) — не логика агрегатов.

## Входы

- `aggregate(src_table, match, preds, measure=None)` — `8359`: SQL-фрагменты `match`/`preds`, имя меры в `nums`.
- `aggregate_groups(src_table, match, preds, measure, col, k, compute=None, members=None)` — `8727–8728`: ось `col`, лимит групп `k`, режим свёртки `compute`, опционально список имён членов `members`.
- `refcols_of(src_table)` / `holders_of_target(target_src)` / `src_is_child(src_table)` — `8478–8524`.
- `measures_of_many(srcs)` — `8527`: список `src_table`.
- `kind_axis_hits(axes, kind_text)` / `kind_axis_rerank(axes, kind_text)` — `8545–8602`: оси `{col, target_src}` и текст рода.
- `term_ref_owners(groups)` / `term_axis_hits(src_table, axes, groups)` — `8605–8673`: группы альтернатив terms.
- `resolve_member_names(src_table, col, groups, gis, target_src="")` — `8676`: индексы групп `gis`; `target_src` в теле не читается.
- `merge_period2_groups(agg, agg2)` / `axis_clarify_options(src, axes)` / `_group_leader(agg)` / `_group_fold(compute, measure)` — `8706–8878`.
- Константы вне участка, читаемые здесь: `CORPUS`/`INDEX`/`TABLES` (`77`), `ROWS_TO_MODEL` (`118`), `STEM_DICT` (`903`), `MEANING_TOP` (`3856–3857`). Env в самом `8359–8878` не читаются.

## Порядок работы

1. **`aggregate:8359–8474`**: нет `src_table` → `None`. WHERE = `match`+`preds`+`src_table`; источник `INDEX` если `match` иначе `CORPUS` (`8369–8370`). Мера → `map_extract(nums,…)` → `TRY_CAST(… AS DECIMAL(38,10))` (`8375`, `8424`). Фильтр папок `NOT IsFolder` (`8395`). Один `SELECT` count/sum/min/max/avg/дат/`count_amount`/folders/`out_of_range` (`8434–8446`). Пустой ответ → `None`; иначе dict (`8453–8474`).
2. **`src_is_child:8478–8487`**: `SELECT parent FROM TABLES` → bool.
3. **`refcols_of:8490–8504`**: оси из `search_refcols` → `[{col, target_src}]`.
4. **`holders_of_target:8507–8524`**: обратный lookup `search_refcols` (без self) → уникальные `{src, col}`.
5. **`measures_of_many:8527–8542`**: ключи `nums` по списку src → `{src: [k,…]}`.
6. **`kind_axis_hits:8545–8576`**: stem-пересечение kind с label/alias/`col` осей; пусто → `meaning_candidates` ∩ `target_src`.
7. **`kind_axis_rerank:8579–8602`**: метки `target_src` из `TABLES` → `rerank` → один `col` или `[]`.
8. **`term_ref_owners:8605–8631`**: terms → владельцы `search_refmap` (равно/LIKE/stem).
9. **`term_axis_hits:8634–8673`**: terms × оси: hit в `search_refmap` по `target_src` или равенство значения `refs_map[col]` в `CORPUS`.
10. **`resolve_member_names:8676–8703`**: собрать alt из `groups[gis]` → матч к значениям `refs_map[col]` в `CORPUS`; нет SQL-находок → исходные имена; `RuntimeError` → исходные имена.
11. **`_group_fold:8718–8724`**: `count`/`avg`/`sum` по `compute` и наличию `measure`.
12. **`aggregate_groups:8727–8833`**: нет `src_table`/`col` → `None`. `k` → int, clamp `[1, ROWS_TO_MODEL]` (`8737–8741`). При `members` — `match` из WHERE убирается (`8744–8746`); источник всегда `CORPUS` (`8748`). CTE `base`→`stats`→`folded` GROUP BY `refs_map[col]`, фильтр `members` по stem, ORDER по fold ASC|DESC, `LIMIT k` (`8774–8795`). Сборка `groups[]`, `leader`, `sum`=fold_sum всего base (не первой группы) (`8818–8833`).
13. **`merge_period2_groups:8836–8851`**: к группам первого среза дописывает `value2`/`count2`/`missing2`, флаги `period2`.
14. **`axis_clarify_options:8854–8878`**: label из `TABLES` по `target_src` (fallback `col`) → уникальные `{src, label, distinct_by, entity_label}`.

## Выходы

- `aggregate` → `None` или `{count,sum,min,max,avg,date_min,date_max,count_amount,src,measure,out_of_range,scope,folders}` (`8453–8474`).
- `aggregate_groups` → `None` или `{count,n_groups,groups[{name,value,count,sum,avg}],sum,leader,min/max/avg=None,count_amount,src,measure,out_of_range,grain="group",col,k,scope,folders=0}` (`8825–8833`).
- `axis_clarify_options` → список опций clarify (`8869–8877`).
- `resolve_member_names` → `list[str]` (`8702–8703`).
- Потребители вне участка (вызовы): `aggregate` — `2525`, `2574–2575`, `14403`, `14425`; `aggregate_groups`/`merge_period2_groups` — `14373–14393`, также `5118`; оси — `14159–14186`, `14237`, `14605–14608` и др. **`resolve_member_names` в репозитории не вызывается** (только определение `8676`).

## Обращения наружу

| Что | Место | Назначение |
|---|---|---|
| SQL count/sum/min/max/avg/дат + IsFolder + out_of_range | `aggregate:8434–8446` | итог множества |
| SQL `parent` из `TABLES` | `src_is_child:8483–8484` | tabular part? |
| SQL `search_refcols` | `refcols_of:8495–8497`, `holders_of_target:8512–8516` | оси / держатели |
| SQL `unnest(map_keys(nums))` CORPUS | `measures_of_many:8532–8535` | меры источников |
| SQL stem kind×оси + `meaning_candidates` | `kind_axis_hits:8554–8573` | выбор оси по роду |
| SQL labels + `rerank(...)` | `kind_axis_rerank:8589–8599` | запасной выбор оси |
| SQL `search_refmap` | `term_ref_owners:8616–8624` | owners по terms |
| SQL refmap ∪ refs_map | `term_axis_hits:8650–8667` | term→ось |
| SQL vals `refs_map[col]` | `resolve_member_names:8688–8699` | канон имён членов |
| SQL GROUP BY refs_map + LIMIT | `aggregate_groups:8774–8797` | группы / лидер / fold_sum |
| SQL labels TABLES | `axis_clarify_options:8863–8864` | подписи clarify |
| HTTP | нет | — |
| Вызов языковой модели | нет (строка `ANSWER_SYS:8882` — только константа промпта) | — |

## Переключатели

- В `8359–8878` чтений `os.environ` нет.
- `ROWS_TO_MODEL` (= `ASK_ROWS_TO_MODEL`, умолч. `"25"`, вне участка `118`): верх/fallback `k` в `aggregate_groups:8739–8741`.
- `STEM_DICT` (= `ASK_STEM_DICT`, умолч. `"search_dict_stem"`, `903`): все `ts_lexize` в участке.
- `MEANING_TOP` (= `ASK_MEANING_TOP` или derived, `3856–3857`): аргумент `meaning_candidates` в `kind_axis_hits:8573`.
- `INDEX`/`CORPUS`/`TABLES` — литералы `"search_idx"`/`"search_corpus"`/`"search_tables"` (`77`).

## Развилки

- `aggregate`: нет `src_table` / пустой `psql` → `None` (`8367–8368`, `8447–8448`); `match` пуст → чтение `CORPUS`, иначе `INDEX` (`8370`); нет `measure` → мера NULL, avg/sum/min/max по NULL (`8375`, `8424`).
- `aggregate_groups`: нет src/col → `None` (`8735–8736`); `members` задан → без `match` в WHERE + фильтр stem по `g` (`8744–8765`); `compute=="min"` → ORDER ASC, иначе DESC (`8773`); fold `count`/`avg`/`sum` задаёт и `value` группы, и `ord_expr` (`8767–8772`, `8811–8814`); `sum` ответа = `fold_sum` всего base при fold sum, avg всего base при fold avg, иначе `None` (`8819–8824`); `psql` exception → `None` (`8798–8799`).
- `kind_axis_hits`: stem-hit → список col; иначе candidates по смыслу (`8568–8576`).
- `kind_axis_rerank` / SQL-хелперы: `RuntimeError` → `[]`/`{}`/`False` по функции.
- `resolve_member_names`: пустые имена → `[]`; SQL fail или пустой found → исходные `names` (`8700–8703`).
- `merge_period2_groups`: нет `agg` → как есть; нет пары во втором срезе → `missing2=True`, `value2`/`count2`=None (`8838–8847`).
- `_group_leader`: только при `grain=="group"`; иначе `None` (`8708–8709`).

## Чего здесь нет

- HTTP, OData, запись в БД, вызов LLM.
- Оркестрации `answer` / разбора intent / сборки `match`/`preds` (только чистые функции).
- Вызовов `resolve_member_names` (функция мёртвая относительно остального файла).
- Использования аргумента `target_src` внутри `resolve_member_names`.
- Отбора папок в `aggregate_groups.folders` (всегда `0`, `8833`; в `aggregate` folders считаются).
- Рендера текста ответа человеку (начинается с `ANSWER_SYS:8882`, вне агрегатной логики).
