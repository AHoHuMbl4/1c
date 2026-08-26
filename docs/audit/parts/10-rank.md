# 10. rank

## Зачем участок нужен

Участок `ubuntu/serenedb/serene_ask.py:4755–5238` решает три задачи ранга: (1) отменить axis-clarify для count/итога без разреза; (2) выбрать колонку GROUP BY по вопросу/осям источника; (3) собрать ответ топ-1 (или sales-топ-N) кодом без выбора модели. Потребитель — основной путь `ask` (~14202–14774): сброс `grain_dec`, автоось при `clarify=axis`, ранний `rank_deterministic_answer`, fallback после провала гейта.

## Входы

| Функция | Аргументы (как в сигнатуре) |
|---|---|
| `count_question_skips_axis` | `intent`, `measure`, `grain_dec` |
| `question_wants_breakdown` | `intent`, `plan=None` |
| `total_question_skips_axis` | `intent`, `measure`, `grain_dec`, `plan`, `question`, `trusted`, `resolved` |
| `rank_question_text` / `rank_intent_from` | `question` / `intent`, `plan`, `question` |
| `rank_leader_answer_text` | `agg`, `measure_label`, `unit` |
| `rank_axis_label_rows` / `rank_axes_rerank` / `rank_axis_pick` | `axes` / `query, axes` / `question, kind, axes` |
| `rank_axis_resolve` / `rank_product_axis_col` | `src, axes, intent, question, plan` |
| `rank_leader_atom` | `agg, measure, money, src, intent, diag, axes, grain_dec, cov, folders` |
| `rank_deterministic_answer` | `question, agg, src, match, preds, measure, money, intent, plan, diag, axes, cut, t0, _pass_frag, say_measure, grain_dec, cov, hatch_alts` |
| `rank_gate_fallback_answer` | те же + `serene_axis=None` (в тело не передаётся) |
| `prefer_entity_for_rank` | `cands, intent, question, plan` |

Поля `intent`: `want`, `amount` (`op`/`value`), `kind`, `period`. Поля `plan`: `compute`. Поля `agg`: `grain`, `groups[]` (`name`/`value`), `col`, `measure`, `folders`. Элементы `axes`: `col`, `target_src`. В этом диапазоне `os.environ` / `getenv` нет.

## Порядок работы

1. **Пропуски clarify:** `count_question_skips_axis` — True, если `grain_dec.clarify=="axis"`, `want∈{count,list}`, нет `amount.op`/`value`, нет `measure` (4755–4772). `total_question_skips_axis` — False при `rank_intent_from` или `question_wants_breakdown`; иначе True при маркерах «всего/итого…», `want/compute==sum`, или `measure_already_proven` (4790–4808).
2. **Сигнал ранга:** `rank_intent_from` = `want==list` ∨ (`amount.value` без `op`) ∨ `compute∈{max,min}` ∨ `rank_question_text` (маркеры вроде «больше всего», «топ », «рейтинг») (4813–4847).
3. **Метки осей:** `rank_axis_label_rows` — SQL по `target_src` → `(col, label)` (4890–4913).
4. **Выбор оси `rank_axis_resolve` (4979–5041):** пустой `axes` → `refcols_of(src)`; 1 col → `(col,[])`; иначе по порядку: `rank_axis_pick` (модель) → `kind_axis_hits(axes,q)` → `rank_axes_rerank` (2 оси — оба col; иначе топ-1) → при `kind` без `q`: hits/rerank по kind → при `kind`+`q`: топ rerank + один kind-hit. Итог: 1 → `(col,[])`; 2+ → `(первый, остальные)`; пусто → `(None, все cols)`.
5. **`rank_deterministic_answer` (5084–5162):** нет `rank_intent_from` → `None`. Если у `agg` нет group/имени — `rank_axis_resolve`; без `_col`/`src`/`measure` → `None`. При `sales_rank_engaged`: `_k=_sales_rank_top_n`, `_compute=sum`; иначе `_k` из `serene_axis.rank_k(..., ROWS_TO_MODEL)` или 1, `_compute=plan.compute|"sum"`. Пересчёт `aggregate_groups`. Текст: sales → `rank_groups_answer_text`; иначе `rank_leader_answer_text`. Паспорт/`ensure_count_named`, атом `rank_leader_atom`, `options` из `hatch_alts`.
6. **`prefer_entity_for_rank` (5174–5237):** при rank+productish и ≥2 кандидатах — SQL parent/written_by; поднимает `accumulationregister_*` по документам; документные ТЧ сдвигает назад.

## Выходы

- Пропуски: `True`/`False` → вызывающий обнуляет `grain_dec.clarify` (`:14202–14218`).
- `rank_axis_resolve` → `(col, alts)` → `grain_dec` form=rank / `diag.rank_axis_*` (`:14171–14229`).
- `rank_deterministic_answer` / fallback → dict `{kind:"answer", text, sources, atom, atoms, diag, partial, options?}` или `None` (`:14584–14598`, `:14769–14774`); `diag.rank_deterministic=True`, при люке `diag.rank_axis_hatch`.
- `prefer_entity_for_rank` → переупорядоченный `cands` (`:12153`, `:12583`).
- `rank_product_axis_col` → только `col` (обёртка, `:5044–5047`).

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| `4899–4900` | SQL `SELECT src_table, label FROM search_tables WHERE src_table IN (...)` через `psql` | метки осей |
| `4941–4955` | HTTP LLM `ds_chat` (system=`AXIS_PICK_SYS`, max_tokens=80) | индексы осей JSON `{"axes":[…]}` |
| `4924` | HTTP `rerank(query, docs)` | порядок колонок по меткам |
| `4993` | `refcols_of(src)` → SQL `search_refcols` (вне участка) | оси, если `axes` пуст |
| `5007–5023` | `kind_axis_hits` / `kind_axis_rerank` (вне участка) | запасной сигнал оси |
| `5118–5119` | `aggregate_groups(...)` → SQL GROUP BY по корпусу | пересчёт топа |
| `5187–5208` | SQL `search_tables`: `parent`/`written_by`; `accumulationregister_%` по `written_by` | перестановка кандидатов |

## Переключатели

В диапазоне **нет** чтения env. Используются модульные: `TABLES="search_tables"` (`:77`); `ROWS_TO_MODEL=int(ASK_ROWS_TO_MODEL|"25")` (`:118`) — потолок `serene_axis.rank_k` (`:5112–5114`); `serene_axis` — импорт или `None` (`:59–61`): при `None` `_k=1`. Параметр `serene_axis` у `rank_gate_fallback_answer` в вызов не передаётся (`:5169–5171`).

## Развилки

- Нет rank-intent → deterministic/`prefer_entity` не меняют поведение (`None` / исходные `cands`).
- 0 / 1 / 2+ осей → `(None,pool)` / одна без люка / лидер+alts.
- Сбой/`Exception` у `ds_chat` → `[]`, дальше hits/rerank (`:4956–4958`).
- `_need` пересчёта vs уже готовый group-agg с именем.
- `sales_rank_engaged` → топ-N + `sum` vs иначе `_k` из `rank_k` или `1`.
- Пустые groups/имя/текст → `None`.
- `hatch_alts` непустой → `out["options"]`.
- productish + ≥2 cands → SQL-перестановка; иначе вход как есть.

## Чего здесь нет

- Нет чтения env-флагов (`ASK_SALES_RANK_*`, calendar/IVF/solr) в этом диапазоне.
- Нет записи в БД, HTTP кроме `ds_chat`/`rerank` через хелперы.
- Нет реализации `rank_groups_answer_text`, `sales_rank_*`, `aggregate_groups`, `kind_axis_*` (только вызовы).
- Нет выбора меры, периода, match/preds, арбитра готовых ответов.
- `rank_gate_fallback_answer` не использует свой аргумент `serene_axis`.
- Нет calendar-axis / entity-form axis (другие участки файла).
