# 20. ask-main-http

Участок: `ubuntu/serenedb/serene_ask.py:10122–15748`. Источник — только этот диапазон (константы/env, объявленные выше и здесь только читаемые, помечены).

## Зачем участок нужен

Гейт чисел/дат ответа (`gate`/`gate_out`), уточнения без прозы модели (`clarify_say`), проверка полноты корпуса (`_coverage_of`/`_health_gap`), главный конвейер вопроса (`answer`), обёртка достаточности и журнала (`answer_checked`), HTTP `ThreadingHTTPServer` с `/ask` и `/health` (`Handler`/`main`).

## Входы

| Точка | Поля / аргументы |
|---|---|
| `POST /ask` JSON (`:15649–15674`) | `question`, `memory`, `focus`, `measure`, `context` (≤4000), `prior`, `decision_id`, `user`, `channel` (умолч. `"http"`), `rid` |
| Заголовок | `Authorization: Bearer ` + `ASK_TOKEN`; `Content-Length` |
| `answer(...)` (`:11810`) | `question`, `focus`, `measure_pick`, `context`, `no_arbiter`, `prior`, `trusted`, `resolved` |
| `answer_checked(...)` (`:15411`) | то же + `decision_id`, `user`, `channel`, `mem_action`, `rid` |
| `GET /health` | путь; тела нет |
| `main()` | env `ASK_TOKEN`, `ASK_LISTEN_HOST`, `ASK_LISTEN_PORT` (чтение вне участка `:72–74`) |

## Порядок работы

1. **`main`** (`:15735–15743`): без `ASK_TOKEN` → код 2; иначе `ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()`.
2. **`GET /health`** (`:15591–15638`): `count(*)` по `CORPUS` → при ошибке 503; `_health_gap()` → `_classify_health_gap`; опционально `_measure_native_index_freshness` при флаге; ответ 503/200 (см. Развилки).
3. **`POST /ask`** (`:15641–15732`): путь ≠ `/ask` → 404; Bearer ≠ токен → 401; битый JSON / пустой вопрос без mem → 400; `ACM.split_memory_action`; либо только shadow-память, либо `answer_checked` → при `options` — `seal_clarify` → `attach_memory_shadow` → возраст `search_quality.build_ts` → `stale_note` → `_persist_ask_scope` → 200; исключение → 503 `kind=unavailable`.
4. **`answer_checked`** (`:15411–15492`): `_rid_enter`; без `user` — `prior=None`; `peek_resolved` / `consume_decision` / reissue; `_answer_checked_core`; `_try_memory_apply`; `finally` — `_ask_journal_write`.
5. **`_answer_checked_core`** (`:15337–15379`): если `ENOUGH_ON` и `serene_enough` и не `guards_skip_for_choice` — `verdict_before` → возможно `_need_clarify`; иначе/`после` — `answer(...)`; при `kind∈{answer,figures}` и `facts_wanted` — `question_facts` + `verdict_after` → возможно уточнение.
6. **`answer` слои** (`:11810–14914`):
   1. `parse_intent` → `apply_prior_period` / `apply_period_leader` / `expand_readings_calendar_axis` → `_predicates`.
   2. `about==coverage` → `_coverage_answer` (или отказ в `period_zero_why`).
   3. ранний stock named без balance → `stock_balance_named_no_data`.
   4. `probe` → `match_expr` → `tables_of` + `partial_tables` + `meaning_candidates` + `children_by_parent`; запасной kNN по `CORPUS.emb`; пусто → `no_data`.
   5. сбор `cands` + prefer_*/stock filters + `not_for` + отсев без `nums` при `want==sum`.
   6. порядок: `ORDER_BY_MEANING` + card/tables emb + `rerank`; parent-before-child при числовом want.
   7. `FORK_DETECT` → `fork_detector_scan`; `ASK_ENTITY_FORM` pre_entity; sales period_empty до выбора.
   8. `focus` / `pick_entity` / арбитр / fork outcomes A/B/C/unique → ранние return.
   9. выбор меры, `aggregate*` / `rows_of`, `compose`, `gate`/`gate_out`, retry; итог `kind` answer|figures|clarify|no_data|unavailable.
7. **Гейт/уточнение** (`:10122–10430`): `rows_seen` → whitelist `gate` → `gate_out` (+`prompt_leak`); `clarify_say` строит нумерованные опции и гоняет через `gate_out`.

## Выходы

| Источник | Форма | Потребитель в участке |
|---|---|---|
| `Handler._send` | JSON HTTP | клиент `/ask`/`/health` |
| `answer` / `answer_checked` | dict: `kind`, `text`, `sources`, `partial`, `diag`, опц. `options`/`figures`/`atom`/`completeness`/`ask_scope` | Handler; под-вызовы `answer(..., no_arbiter=True)` |
| `_persist_ask_scope` | поля `ask_scope`, `ask_scope_sha256` + INSERT в `ask_scope` | ответ JSON; таблица через `_resolver_psql` |
| `_ask_journal_write` | строки `ask_journal` / `ask_journal_text` | нет в участке (только запись) |

`kind` значения из return-ов участка: `answer`, `figures`, `clarify`, `no_data`, `unavailable`, `choice_error` (через чужие хелперы при ошибке билета).

## Обращения наружу

| Место | Что | Назначение |
|---|---|---|
| множество `psql(...)` в `answer`/`_coverage_*`/`_health_*`/`gate`-соседях | SQL к SereneDB (корпус, индекс, coverage, quality, sdb_metrics, journal…) | отбор, счёт, health, журнал |
| `_resolver_psql` `:15555–15572` | INSERT/DDL `ask_scope` | дашборд-scope |
| `ds_chat` в `_coverage_answer` `:10836`, `question_facts`/`need_say` (через `serene_enough`) | LLM | текст coverage / facts / need-clarify |
| `rerank(...)` `:12459` | HTTP-реранкер (реализация вне участка) | порядок кандидатов |
| `embed_one`/`_vec` / `embed_model_live` (вызовы из `answer`) | эмбеддер | смысл/порядок |
| HTTP наружу кроме сервера | нет в `Handler` | — |

## Переключатели

| Имя | Чтение | Умолч. | Где меняет поведение в участке |
|---|---|---|---|
| `ASK_HEALTH_GAP_TTL` | `:10562` | `"300"` | TTL кэша `_health_gap` |
| `ASK_HEALTH_NATIVE_FRESHNESS` | `:10569` | `"0"` | поля `freshness` из `sdb_metrics` в `/health` |
| `ASK_HEALTH_SEARCH_IDX` | `:10571` | `"search_idx"` | имя индекса в native SQL |
| `ASK_ENOUGH` → `ENOUGH_ON` | `:14929` | вкл. (`"1"`) | шаг достаточности вокруг `answer` |
| `ASK_SLOT_COVER` → `SLOT_COVER` | `:14931` | `"0"` | объявлен; влияние на тело — через `serene_enough` вне явного if в участке |
| `ASK_JOURNAL_KEEP` | `:15028` | иначе формула от `search_tables` | ротация журнала |
| `ASK_TOKEN` / `ASK_LISTEN_*` | вне `:72–74` | host `127.0.0.1`, port `8091`, token `""` | `main`/`Handler` |
| `ASK_STALE_WARN_SEC` / `ASK_STALE_TEXT` | вне `:111–112,:321` | 3600; шаблон текста | `stale_note` после `/ask` |
| `ASK_JOURNAL` / `ASK_CHOICE_MEMORY` / `ASK_MEMORY_APPLY` | вне `:3952–3959` | journal/memory вкл.; apply выкл. | журнал; `_try_memory_apply` |
| `ASK_FORK_DETECT` / `ASK_FORK_OUTCOMES` | вне `:3948–3949` | оба вкл. | детектор/исходы в `answer` |
| `ASK_ENTITY_FORM` / `ASK_ATOM_TERMINAL` / `ASK_CALENDAR_AXIS` / `ASK_SALES_RANK_CANON` | вне `:1424–1431` | `"0"` | ветки form/calendar/canon/atom в `answer` |
| `ASK_NOT_FOR` → `NOT_FOR` | вне `:10901` | `"1"` | отсев `not_enough_for` |
| `ASK_ARBITER_MAX` | вне `:10893` | `3` | размер круга арбитра |
| `ORDER_BY_MEANING` / `RERANK_TOP` / бюджеты rows | вне участка | — | порядок кандидатов / `rows_seen` |

## Развилки

- `/health`: ошибка корпуса/gap → 503; `kind==systemic` → 503; `freshness_lag` → 200 + freshness; иначе 200 `serene-ask-ok` (`:15615–15638`).
- `/ask`: 401/400/404; mem-only без data_q → пустой answer + shadow; исключение → классификация текста ошибки в 3 сообщения (`:15725–15732`).
- `answer`: `no_data` (нет термов/кандидатов/пустой agg); `clarify` (focus-ось, fork C, measure, ask_back, enough); fork A/B/unique/unavailable; gейт fail → `figures` или `no_data` или rank fallback; успех → `answer` (`:14767–14914`).
- `answer_checked`: ошибка `decision_id` → reissue clarify или fallback core с `ticket_reissued` (`:15434–15454`).

## Чего здесь нет

- Вызовов OData / записи в 1С — нет.
- Старта DDL `ask_scope` из `main` — функция `_ensure_ask_scope_table` есть (`:15563`), из `main` не вызывается.
- Других HTTP-путей кроме `/ask` и `/health` — нет (`:15639`, `:15642`).
- Разбора intent / probe / aggregate / pick_entity / fork_scan — тела вне участка; здесь только вызовы.
- Push/WebSocket — нет; только `ThreadingHTTPServer`.
- Авторизации кроме Bearer `ASK_TOKEN` — нет.
