# S1. Путь вопроса: от сообщения человека до текста ответа

Источники L1: 24, 20, 02, 03, 04, 06, 07, 08, 16, 17, 18, 19, 15, 01. Сверка кода: `ubuntu/openclaw/mcp_ask.py`, `ubuntu/serenedb/serene_ask.py`.

## Коротко

Сообщение человека принимает OpenClaw-бот (вне `mcp_ask`); бот зовёт MCP-инструмент `ask_1c`. Мост шлёт HTTP POST на `ASK_URL/ask` с полями вопроса. Сервис `serene_ask` разбирает вопрос моделью в `intent`, строит окно дат и предикаты, ищет сущности в индексе/корпусе SereneDB, выбирает источник и меру, считает итоги SQL-агрегатами, формулирует текст моделью по именам слотов (без значений), подставляет числа кодом и проверяет гейтом. Исход `kind` (`answer`/`figures`/`clarify`/`no_data`/…) мост превращает в строку для бота; бот дальше формулирует ответ клиенту (вне этого контура). Числа считает только база; модель пишет разбор, выбор и прозу вокруг уже посчитанных слотов.

## Схема пути

1. **Вход человека → инструмент** — OpenClaw зовёт `ask_1c(question, focus?, measure?, context?, prior?, decision_id?, user?, memory?, channel?, rid?)` (`mcp_ask.py:485-512`). Приём Telegram/WebUI в `mcp_ask` отсутствует (24).
2. **Pending до /ask** — `apply_pending_before_ask`; `refuse` → отказ петли; `short_circuit` → clarify без HTTP (`:519-533`).
3. **HTTP POST /ask** — JSON тех же полей; Bearer `ASK_TOKEN` (`:94-112`, `:535-538`). Handler: 401/400; иначе `answer_checked` (`serene_ask.py:15641-15692`).
4. **Обёртка** — `_rid_enter`; билет `decision_id` → `trusted`/`resolved` или `choice_error`; `_answer_checked_core`; журнал (`:15411+`). При `ASK_ENOUGH`: `parse_intent` → `verdict_before` → возможно `_need_clarify` (LLM `need_say`); иначе/`после` — `answer`; при `kind∈{answer,figures}` и `facts_wanted` — `question_facts` + `verdict_after` → снова clarify (`:15337-15379`, `:14937+`, `:15015`).
5. **Разбор** — `parse_intent`: `ds_chat(INTENT_SYS + today+вопрос)` → JSON → `_normalize_intent` (`:11854`, `:1289-1348`, `:1230`). Опц. `prior` → второй `parse_intent` + `apply_prior_period` (`:11856-11857`).
6. **Период** — `apply_period_leader` → readings MTD/WTD/…; `expand_readings_calendar_axis` при открытой оси; `preds = period_preds` (+ working-days IN при флаге) (`:11859-11869`, 03/04).
7. **Ветки до поиска** — `about==coverage` → `_coverage_answer` (LLM); иначе early stock named → `no_data` (`:11905-11925`).
8. **Поиск** — `probe(terms)` → `match_expr` → `tables_of` / `partial_tables` / `meaning_candidates` (RRF/alias/card/kNN) → кандидаты `src_table`; пусто → `no_data` (06/07, `:11951+` по 20).
9. **Выбор сущности/меры** — фильтры prefer/not_for/stock; при сомнении `pick_entity` → `ds_chat(PICK_SYS)` (`:12754`, `:8277`); `pick_measure` / `unresolved_quantity` / clarify меры (16); опц. `fork_detector_scan` / исходы A/B/C; опц. `arbitrate` по готовым текстам (`:13646`, 01).
10. **Счёт** — `aggregate` / `aggregate_groups` (SQL sum/count/… по `nums`/`refs_map`); `totals_of`/`measures_of` для контекста меры (17/08, `:14403+`). Число рождается здесь.
11. **Формулировка** — слоты `compose_slot_values` / атом `atom_from_agg` (15); `compose` → `ds_chat(ANSWER_SYS + QUESTION/ROWS/COMPUTED со именами слотов)` (`:9669-9670`, `:14632`); `_split_answer` → `_fill_figures` + `fill_atom_pairs` + паспорт (18/15). Rank без модели: `rank_deterministic_answer` может вернуть раньше (`:14584-14598`).
12. **Проверка** — `formulation_flaws` / `copied_figures` / `asked_figure_missing` / `prompt_leak` / `gate` по `rows_seen`+`agg`+whitelist (`:14674-14696`, 19/20). Fail + есть `agg` → один retry `compose(corrections=…)` и тот же гейт (`:14707-14763`); иначе `kind=figures` со структурой чисел или rank-fallback (`:14767-14809`).
13. **Хвост HTTP** — `seal_clarify` при options; `stale_note` по `search_quality.build_ts`; `_persist_ask_scope`; JSON 200 (`:15693-15714`).
14. **Мост → бот** — по `kind`: clarify/figures/no_data/text + маркеры/`ATOM_JSON`/`PRESENTATION_JSON` (`mcp_ask.py:549-650`). Дальше клиентский текст пишет бот (вне L1 этого набора).

### Точки вызова языковой модели (chat) и что ей передаётся

| Место | Передаётся |
|---|---|
| `parse_intent` `:1230/:1238` | system=`INTENT_SYS`; user=`today=…\n\nQuestion: …`; повтор с «Return the JSON object.» |
| `pick_entity` `:8277` | system=`PICK_SYS`; user=вопрос + список меток/термов/мер (бюджет `PICK_BUDGET`) |
| `rank_axis_pick` `:4951` | system=`AXIS_PICK_SYS`; user=вопрос(+kind) + нумерованный список осей (код; L1-10 вне сырья) |
| `clarify_text` / `refuse_text` `:3467/:3500` | `CLARIFY_SYS`+вопрос+опции / `REFUSE_SYS`+вопрос |
| `compose` `:9669` (+retry `:14709`) | `ANSWER_SYS` + тело: вопрос, строки/группы **без значений итогов**, имена слотов `{sum}`/`{pair:pN}`… |
| `arbitrate` `:631` | system+вопрос+пронумерованные готовые ответы (+`context`); max_tokens=8 |
| `_coverage_answer` `:10836` | `COVERAGE_SYS` + вопрос |
| `question_facts` `:14952` | `serene_enough.FACTS_SYS` + вопрос |
| `_need_clarify` → `need_say` `:15015` | через `ds_chat` + слоты недостаточности; гейт `_gate_need` |

Эмбеддинг вопроса: `embed_one` HTTP или `ai_embed` (01) — не chat. Реранк: HTTP `RERANK_URL` (07), не `ds_chat`. В `mcp_ask` LLM нет (24).

## Точки принятия решений

- Pending: refuse / short_circuit / идти в `/ask` (`mcp_ask.py:525-533`).
- HTTP: 401/400; mem-only без data_q — пустой answer+shadow (`:15679-15683`).
- Enough: `verdict_before` → clarify без поиска; `verdict_after` → clarify после счёта (`:15345-15379`).
- `about=coverage` vs data; `period_zero_why` сбрасывает coverage (`:11905-11915`).
- Нет термов/кандидатов → `no_data`; ambiguous entity/measure/axis/fork C → `clarify`+options.
- `focus`/`trusted`/`decision_id` / `no_arbiter` гасят fork/арбитр/entity-form перехваты (20, код `:12571+`).
- `calendar_axis_open` false → readings/preds без day-basis (04).
- Rank-детерминизм успех → return без `compose`; иначе compose→gate; gate fail → retry → figures/fallback.
- `kind` в мосте → разные строки боту (24 п.5).

## Что участвует снаружи

- **Сервисы/порты:** OpenClaw → MCP `ask_1c` (`MCP_HOST`/`MCP_PORT`, умолч. `127.0.0.1:6016`); `ASK_URL/ask` (умолч. URL `:8099`); listen ask (умолч. `:8091`); chat `{DEEPSEEK_BASE}/v1/chat/completions`; embed `EMBED_*`; rerank `RERANK_*`.
- **Env:** `/etc` через юниты выката; ключи `ASK_TOKEN`/`MCP_TOKEN`/`DEEPSEEK_*`/`SERENEDB_DSN_RO`/`RESOLVER_DSN`; флаги `ASK_ENOUGH`, `ASK_FORK_*`, `ASK_CALENDAR_AXIS`, `ASK_ENTITY_FORM`, `ASK_SQL_RRF`, `ASK_EMBED_NATIVE`, …
- **БД (чтение):** `search_idx`/`search_corpus`/`search_tables`, alias/card индексы, `search_measure_alias`, `search_refcols`/`search_refmap`, `search_meta`/`search_calendar_map`/`search_quality`, опц. `resolver_index`; запись: `ask_journal*`, `ask_scope` (20).
- **Не на этом пути:** `1c-gateway` / `odata_gateway` (вызовов из `mcp_ask` нет, 24).

## Расхождения между отчётами уровня 1

- **Умолчание порта ask:** `ASK_URL` → `:8099` (`mcp_ask.py:46`, 24) vs `ASK_LISTEN_PORT` → `:8091` (20, модуль `:72–74`). Оба верны как дефолты своих модулей; стык только явным env выката.
- **`PICK_SYS`:** 07 («в срезе только объявлен», `:3376`) и 16 (`ds_chat` в `pick_entity:8277`) — оба верны: разные диапазоны строк.
- Иных противоречий по фактам пути между перечисленными L1 нет.

## Белые пятна

- Приём канала (Telegram/WebUI), персона бота, перефраз до `ask_1c` и финальная проза клиенту после строки инструмента — вне `mcp_ask` (24 «Чего здесь нет»).
- Полная логика `mcp_ask_pending` (только точки вызова в 24).
- Тела fork-outcomes / sales / stock / entity-form / rank (L1 09–13, 05, 10, 11, 12) — зовутся из `answer`, но не входили в сырьё; на пути отмечены как ветки без разбора внутренностей.
- Содержимое промптов `serene_enough.*` и точный JSON, который ждёт `need_say`/`parse_facts`, кроме факта вызова `ds_chat`.
- Verify-плагин OpenClaw после ответа инструмента — в docstring моста есть, в L1-24 не разобран.
