# Как система работает

## Одним абзацем

Человек пишет вопрос боту OpenClaw; бот зовёт MCP-инструмент `ask_1c`
(`ubuntu/openclaw/mcp_ask.py`). Мост шлёт `POST {ASK_URL}/ask` на сервис
`serene_ask.py`, который читает поисковый слой SereneDB (корпус, индекс, алиасы),
разбирает вопрос моделью в JSON-intent, ищет сущности, выбирает таблицу и меру
(при сомнении — уточнение с билетом), считает итоги SQL-агрегатами внутри базы,
формулирует прозу моделью по **именам** слотов без значений, подставляет числа
кодом и проверяет гейтом. Данные в витрину попадают из 1С либо пакетным агентом
Windows→Ubuntu, либо HTTP через OData-шлюз; таймер `1c-serene-pipeline` гоняет
`pipeline.sh` → `serene_sync.py` → `build.sh`, который собирает `search_corpus` /
`search_idx` / векторы / словари. Числа считает только база; модель пишет разбор,
выбор и текст вокруг уже посчитанных слотов.

## Схема целиком

```
1С (OData / packet-agent)
        │
        ├─ ветка A: CSV zstd → packet_server :6021 → packet_apply → таблицы витрины
        └─ ветка B: odata_gateway :6011 → serene_sync.py → таблицы витрины
        │
        ▼
1c-serene-pipeline.timer → pipeline.sh → build.sh
        │  corpus_build → search_corpus; ai_embed → emb;
        │  VACUUM search_idx; wiki_alias; solr_synonyms; entity_card
        ▼
SereneDB (витрина + search_* + resolver_index)
        │
человек → OpenClaw-бот → MCP ask_1c (:6016) → POST /ask (:8091/:8099…)
        │
        ▼
serene_ask: intent → период → поиск → выбор src/меры → SQL aggregate
        → compose(слоты) → fill figures → gate → JSON {kind,text,…}
        │
        ▼
mcp_ask форматирует строку → бот отдаёт человеку
```

## Путь данных

| # | Шаг | Что запускает | Где код |
|---|---|---|---|
| 1 | Публикация OData / установка агента | владелец / `windows/odata-setup` | `windows/odata-setup` (вне такта ask) |
| 2a | Пакет: чтение OData → чанки → HTTPS PUT | Windows packet-agent, цикл `new Tact(…).Run()` | агент C# `windows/packet-agent/src/PacketAgent.cs:3167-3180`; приём `ubuntu/packet/packet_server.py` (`PACKET_LISTEN` умолч. `127.0.0.1:6021`, `:41`) |
| 3a | Apply verified→таблицы + `search_changed_sources` + `$metadata` | `1c-packet-apply.timer` (`OnBootSec=2min`, `OnUnitActiveSec=2min`) | `ubuntu/packet/packet_apply.py`; юнит `ubuntu/packet/systemd/` |
| 2b | HTTP: GET через шлюз → load entity | `pipeline.sh` зовёт `serene_sync.py` | `ubuntu/systemd/1c-odata-gateway@.service` → `odata_gateway.py` (`ODG_LISTEN` умолч. `:6011`); sync `ubuntu/serenedb/serene_sync.py` |
| 4 | Такт конвейера | `1c-serene-pipeline.timer`: `OnBootSec=3min`, `OnUnitInactiveSec=1min` | `ubuntu/systemd/1c-serene-pipeline.timer:8-10` → `pipeline.service` → `/opt/1c-mcp-reports/pipeline.sh` |
| 5 | В `pipeline.sh` | при каталоге `ETL_ODATA_BASE` — keep `search_changed_sources`; sync (код≠0 не стопит); `exec build.sh` | `ubuntu/serenedb/pipeline.sh:42-57`; preflight embed form `:18-21` |
| 6 | Корпус | `corpus_init.sql` → при необходимости `corpus_build.sql` (`:gate` = URL или каталог meta) → `corpus_merge.sql` → `search_corpus` | `ubuntu/serenedb/build.sh:147-279` |
| 7 | Разметка / контур | `classify_entities.py` fail-closed; при `PACKET_BASE_ID` — `packet_config.py` | `build.sh:296-320` |
| 8 | Векторы | `embed_missing.sh` + `ai_embed`: labels → `resolver_index` → `search_corpus.doc` (service только при `EMBED_SERVICE=1`) | `build.sh:336-399` |
| 9 | Индекс и словари | `VACUUM (REFRESH_INDEX) search_idx` → coverage → `wiki_alias.sh` / publish → `solr_synonyms_build.py compile --apply` (шаг 7-solr, fail-closed) → entity cards → postcheck | `build.sh:403-452` |
| 10 | Вне тракта витрины | `oc_etl.py` → markdown/git KB, таймер `03:00` | не пишет в `search_*` |

Взаимоисключение веток: `ETL_ODATA_BASE` как **каталог** → packet-режим (keep-marks, meta с диска); как **URL** → HTTP load. Боевой сборщик корпуса в такте — `build.sh` (`build.sh:4`, «вместо serene_search_build.py»), не питоновский `serene_search_build.py`. Второй `build.sh` при занятом `flock` выходит 0 (`build.sh:76`).

Готовый слой, который читает ask: таблицы витрины (= имена EntitySet), `search_corpus`, `search_idx`, `search_tables`, `resolver_index`, `search_changed_sources`, `search_meta` / `search_*_map` / `search_quality`, `search_entity_alias` / `search_measure_alias`, solr-dict, `search_fork_*`, карточки. Ask к 1С и к gateway **не** ходит: только SereneDB RO (`SERENEDB_DSN_RO`, `:63`) и внешние chat/embed/rerank.

### Env такта (файлы)

| Файл | Кто читает |
|---|---|
| `/etc/1c-mcp-reports.env` | pipeline, ask, scorer |
| `/etc/1c-serene-sync.env` | pipeline |
| `/etc/1c-embed.env` | pipeline, ask |
| `/etc/1c-serene-pipeline-%i.env` | pipeline@ |
| `/etc/1c-odata-gateway-%i.env` | gateway@ |
| `/etc/1c-packet.env`, `1c-packet-bases.json` | packet |
| `/etc/1c-serene-ask.env`, `1c-serene-ask-%i.env` | ask@ |
| `/etc/1c-mcp-ask.env` / `-%i.env` | mcp-ask |

Диск: `PACKET_ROOT` `/var/lib/1c-packet`; `PACKET_META_DIR` `/var/lib/serenedb/packet-meta`; `CSV_DIR` `/var/lib/serenedb`.

## Путь вопроса

| # | Шаг | Модель? | Число? | Код |
|---|---|---|---|---|
| 1 | Бот зовёт `ask_1c(question, focus?, measure?, …)` | нет в мосте | нет | `mcp_ask.py:485-512` |
| 2 | Pending: `refuse` / `short_circuit` / идти дальше | нет | нет | `mcp_ask.py:519-533` |
| 3 | `POST {ASK_URL}/ask`, Bearer `ASK_TOKEN` | нет | нет | `mcp_ask.py:94-120`, `:535-538`; handler `serene_ask.py:15641-15692` |
| 4 | `answer_checked` → билет `decision_id` → `_answer_checked_core` | опц. enough | нет ещё | `:15411+`, `:15337+` |
| 5 | При `ASK_ENOUGH`: `parse_intent` → `verdict_before` → возможно clarify без поиска | LLM intent / need | нет | `:15345-15379`, `:14929` |
| 6 | `parse_intent`: `ds_chat(INTENT_SYS)` → JSON → `_normalize_intent` | **да** | нет | `:1289`, `:1228-1244` |
| 7 | Период: `apply_period_leader` → readings; опц. calendar axis; `period_preds` | нет | нет | `:1772`, `:1395`, флаг `:1424` |
| 8 | `about==coverage` → `_coverage_answer`; early stock named → `no_data` | coverage: LLM | нет | `:11905-11925` |
| 9 | Поиск: `probe` → `match_expr` → `tables_of` / `meaning_candidates` (RRF/alias/kNN) | embed/rerank HTTP, не chat | нет | `:2646`, `:2775`, `:2941`, `:3093` |
| 10 | Выбор сущности/меры, fork, entity-form, arbiter — см. след. раздел | pick/axis: LLM; fork: нет | SQL в fork-scan | `answer` `:11810+` |
| 11 | **Счёт:** `aggregate` / `aggregate_groups` (sum/count по `nums`/`refs_map`) | нет | **да, здесь** | `:8359`, `:8727` |
| 12 | Слоты `compose_slot_values`; `compose` → модель видит имена слотов, не значения | **да** | нет (имена) | `:7410`, `:9448`, `:9669` |
| 13 | `_fill_figures` + `fill_atom_pairs` подставляют числа кодом | нет | подстановка | `:8994`, `:7666` |
| 14 | `formulation_flaws` / `copied_figures` / `asked_figure_missing` / `prompt_leak` / `gate`; fail → один retry compose | retry: LLM | нет новых | `:9310+`, `:10149`, `:14674-14763` |
| 15 | `seal_clarify` при options; `stale_note`; JSON 200 | нет | нет | `:15693-15714`, `seal_clarify` `:7027` |
| 16 | Мост по `kind` → строка боту (`clarify`/`figures`/`no_data`/text + маркеры) | нет | нет | `mcp_ask.py:549-650` |

### Вызовы chat-модели в ask

| Функция | Строки | Вход |
|---|---|---|
| `parse_intent` / `_one_intent` | `:1230`, `:1238` | `INTENT_SYS` + today + вопрос |
| `pick_entity` | `:8155` / зов `ds_chat` ~`:8277` | `PICK_SYS` + метки/термы |
| `rank_axis_pick` | `:4951` | `AXIS_PICK_SYS` + список осей |
| `clarify_text` / `refuse_text` | `:3467`, `:3500` | `CLARIFY_SYS` / `REFUSE_SYS` |
| `compose` | `:9669` (+ retry) | `ANSWER_SYS` + ROWS/COMPUTED **без значений итогов** |
| `arbitrate` | `:631` | готовые тексты ответов; max_tokens=8 |
| `_coverage_answer` | ~`:10836` | `COVERAGE_SYS` |
| `question_facts` / `need_say` | `:14952`, `:15015` | enough / facts |

Эмбеддинг вопроса: `embed_one` / native `ai_embed` (`:744`, `:297`) — не chat. Реранк: HTTP `RERANK_URL`. В `mcp_ask` LLM нет.

Исходы `kind` (сервис → мост): `answer`, `figures`, `clarify`, `no_data`, `unavailable`, `choice_error`, …

Поля JSON ответа `/ask` (потребители — мост и scorer): `kind`, `text`, `figures`/`totals`, `atoms`/`atom`, `options` (с `decision_id`, `focus`, `measure`, …), `partial`, `diag`, опц. presentation. После options сервис пломбирует билеты (`seal_clarify`); мост при `clarify`/`figures`+options кладёт pending для следующего реплика человека.

HTTP-ошибки сервиса: нет/неверный Bearer → 401; пустой вопрос → 400; не `/ask` → 404; исключение в handler → 503 `kind=unavailable` (`:15715-15732`). `/health`: ошибка корпуса или systemic gap → 503; freshness_lag и норма → 200 (+ freshness при флаге) (`:15591-15638`).

## Как выбирается, что считать

Порядок внутри `answer` после появления кандидатов `src_table` (`serene_ask.py`):

1. **Ранний отказ остатка с именем товара** без capable/goods → `kind=no_data` (`:11920-11925`, `:12565-12570`).
2. **Перестановка кандидатов:** `prefer_entity_for_rank` → `prefer_entity_for_sales` → `prefer_entity_for_catalog_count` (`:12153-12155`); для остатков — noise/structural/bridge-clarify (`:12156-12181`).
3. **Ранний скан развилки** при `ASK_FORK_DETECT` и `len(cands)>1`: `fork_detector_scan` (`:4261`, оркестрация `:12571-12629`) — SQL count/sums по `search_corpus`, классы по отпечатку атома (`fork_scan` `:4107+`).
4. **Форма F** при `ASK_ENTITY_FORM` (`:1431`): `try_entity_form_answer` pre_entity (`:2536`, зов `:12637-12651`) — один early-класс и одна форма → атом; иначе `None`. Позже снова после arb_pool (`:13315-13320`): `distinct_axis` / `complement` / pick `structs[0]`.
5. **Sticky / билет:** `sales_refuse_sticky_focus`; `hold_settled_entity` (`:12671+`).
6. **Исходы A/B/C** при `ASK_FORK_OUTCOMES ∧ ASK_FORK_DETECT` (`:3949-3950`, `:13356+`): `resolve_fork_outcome` (`:6285-6334`) —
   - 1 класс / 1 src → unique; много src одного класса → A;
   - ≥2 класса с label → B (`figures`+options); без label → C;
   - uncounted cell → C; scan_error → unavailable.
7. **Мера на одиночном src** (`:13901-14024`): `plan.quantity` / `measure_choice`-гейт / `pick_measure` → `unresolved_quantity` → при `measure_pick` — `resolve_measure` → при продажах — sales-canon / `sales_force_money_measure` / qty (`measure_choice` `:6638`).
8. **Ранг:** `rank_axis_resolve` — LLM pick → stem hits → rerank (`:4979-5041`); при успехе `rank_deterministic_answer` может вернуть ответ без `compose` (`:5084`, `:14584+`).
9. **Уточнение:** ответ с `options` → `seal_clarify` → `issue_decision` (процессный `_DECISIONS`, `:7027-7079`); повтор с `decision_id` → `consume_decision` → focus/measure/`trusted` (`:7082`, `:15434-15463`). Shadow памяти: `ASK_CHOICE_MEMORY` (`:3957`); применение в ответ — только `ASK_MEMORY_APPLY` (`:3959`, `_try_memory_apply` `:15384+`).

Продажи: lift `accumulationregister_*` по `written_by` в `prefer_entity_for_sales` (`:5428+`); канон — первый после score/порядка (`sales_canon_src` `:5534`); `ASK_SALES_RANK_CANON` — топ-N + роль qty/money (`:1426`, `:5362+`).

Остатки (фильтры до счёта): маркеры остатка + именованный товар без capable/goods → `no_data` (`:6042-6049`); остатки без имени, capable есть, hit/пул пуст → bridge `clarify` (`:6103-6136`). Сам SUM по баланс-регистру в разобранных участках аудита не зафиксирован (см. белые пятна).

Фокус снаружи: параметр `focus` / билет / `no_arbiter` гасят fork и entity-form перехваты на пути (`:12571+`, доверие только `trusted` или `ASK_RAW_FOCUS_TRUST`).

## Службы, порты, переключатели

### Службы (шаблоны в репо)

| Юнит | Роль | Exec / вход |
|---|---|---|
| `1c-serene-pipeline[.timer\|@.…]` | такт sync+build | `ubuntu/systemd/`; `pipeline.sh` |
| `1c-serene-index.service` | только `build.sh` | `ubuntu/systemd/` |
| `1c-odata-gateway@.service` | read-only GET к OData | `odata_gateway.py`, env `%i` |
| `1c-packet-server` / `1c-packet-apply.timer` | приём/apply пакетов | `ubuntu/packet/systemd/` |
| `1c-serene-ask@.service` | HTTP `/ask`, `/health` | `ubuntu/serenedb/systemd/`; `serene_ask.py`; env: mcp-reports → embed → `1c-serene-ask.env` → **`1c-serene-ask-%i.env`** (последний сильнее) |
| `1c-mcp-ask@.service` | MCP `ask_1c` | `ubuntu/openclaw/systemd/`; env `%i` |
| `1c-mcp-ask.service` (одиночный) | то же | зашито `ASK_URL=:8099`, `MCP_PORT=6016` (`1c-mcp-ask.service:15-17`) |

Старт ask без `ASK_TOKEN` → exit 2 (`serene_ask.py:15735+`). MCP без `MCP_TOKEN` → `SystemExit(2)` (`mcp_ask.py:76-79`).

### Порты (умолчания в коде, не live-снимок)

| Компонент | Умолчание | Источник |
|---|---|---|
| SereneDB | `:7890` | `SERENEDB_DSN*` в env/юнитах |
| OData-шлюз | `127.0.0.1:6011` | `odata_gateway` / L1-25 |
| packet_server | `127.0.0.1:6021` | `packet_server.py:41` |
| serene-ask listen | `:8091` | `serene_ask.py:72-73` |
| mcp_ask → ASK_URL | `:8099` | `mcp_ask.py:46` |
| MCP listen | `:6016` | `mcp_ask.py:48-49` |

Стык `:8091` (listen) и `:8099` (default URL моста) — только явным env выката; оба дефолта верны для своих модулей.

### Переключатели ответа (чтение в `serene_ask.py`)

| Env | Умолч. | Строка | Эффект |
|---|---|---|---|
| `ASK_SQL_RRF` | `0` | `:3762` | RRF в поиске корпуса |
| `ASK_RESOLVER_IVF` | `0` | `:3768` | ANN резолвера |
| `ASK_SOLR_SYNONYMS` | `0` | `:906` | query-side solr dict |
| `ASK_CALENDAR_AXIS` | `0` | `:1424` | day-basis readings |
| `ASK_ENTITY_FORM` | `0` | `:1431` | форма F |
| `ASK_ATOM_TERMINAL` | `0` | `:1428` | ранний return unique |
| `ASK_SALES_RANK_CANON` | `0` | `:1426` | канон продаж для rank |
| `ASK_FORK_DETECT` / `OUTCOMES` | `1`/`1` | `:3949-3950` | скан / A·B·C |
| `ASK_ENOUGH` | `1` | `:14929` | гейт достаточности |
| `ASK_CHOICE_MEMORY` / `ASK_MEMORY_APPLY` | `1`/`0` | `:3957-3959` | shadow / apply |
| `ASK_JOURNAL` | `1` | `:3952` | журнал исходов |
| `ASK_NOT_FOR` | `1` | `:10901` | veto not_for |
| `ASK_ORDER_BY_MEANING` | `1` | `:202` | порядок кандидатов |
| `ASK_RERANK_TOP` | `60` | `:228` | лимит реранка |
| `ASK_ROWS_TO_MODEL` | `25` | `:118` | строк в compose |
| `ASK_SCORER` | `bm25` | `:183` | текстовый скорер |
| `ASK_STALE_WARN_SEC` | `3600` | `:111` | stale_note |
| `ASK_HEALTH_NATIVE_FRESHNESS` | `0` | `:10569` | freshness в `/health` |
| `ASK_EMBED_NATIVE` | `0` | `:297` | embed через `ai_embed` |
| `ASK_DECISION_TTL_SEC` | `3600` | `:6872` | TTL билета |
| `ASK_RAW_FOCUS_TRUST` | `0` | `:6871` | аварийное доверие focus |
| `ASK_MONEY_UNIT` | `""` | `:75` | единица денег |
| `ASK_LISTEN_*` / `ASK_TOKEN` | `:8091` / `""` | `:72-74` | HTTP |

Такт/embed: `SERENEDB_DSN`, `ETL_ODATA_BASE`, `EMBED_*`, `FORCE_REBUILD`, `EMBED_SERVICE`, `WIKI_ALIAS_PER_TACT`, `PACKET_BASE_ID` — `build.sh` / `pipeline.sh`.

## Чем проверяется качество

| Прибор | Что делает | Код / артефакт |
|---|---|---|
| `GET /health` | `count(*)` корпуса; gap; опц. native freshness → 200/`serene-ask-ok` или 503 | `serene_ask.py:15591-15638` |
| `ab_scorer.py` | TSV → эталон `psql` → POST `/ask` (до 6 clarify) → modes `digits`/`kind`/`clarify`/`name` | `ubuntu/serenedb/ab_scorer.py:617-765` |
| Наборы TSV | gold / probe okna / calendar axis | `ab-gold-okna.tsv`, `ab-probe-okna.tsv`, `ab-calendar-axis-okna.tsv`; выбор через `AB_PROBE`/`AB_CONTOUR`/`AB_CALENDAR_AXIS` (`:51-69`) |
| Отметки при 0 сбоев | вход гейтов | `.claude/.probe-okna-last-run`, `.golden-okna-last-run`, `.golden-last-run` (`ab_scorer.py:571-614`) |
| Оффлайн `test_*.py` | замки функций без `/ask` | каталог `ubuntu/serenedb/` |
| Гейты коммита | docs / graph / activeContext / prompt-rules / live-probe; commit-msg: sql-docs / diff | `.claude/hooks/git-gate.sh:68-73`; `check-live-probe.sh` |
| Гейт выката | `check-golden` на PreToolUse/Shell (не в `git-gate.sh`) | `.claude/hooks/check-golden.sh`; проводка `.claude/settings.json` / `.cursor/hooks.json` |
| Люк | строка в `override.txt` снимает именной гейт (не потребляется) | `.claude/hooks/override.txt` |

Scorer не зовёт LLM для оценки (`docs/audit/parts/28-scorer-tests.md`).

## Где что лежит

| Тема | Файл | Якоря |
|---|---|---|
| MCP-мост, `ask_1c` | `ubuntu/openclaw/mcp_ask.py` | `:46-50`, `:485-650` |
| HTTP ask/health/main | `ubuntu/serenedb/serene_ask.py` | `:72-74`, `:15591-15743` |
| Intent / период / calendar | то же | `:1289`, `:1395`, `:1424`, `:1772`, `:1880` |
| Поиск сущностей | то же | `probe` `:2646`, `tables_of` `:2941`, `meaning_candidates` `:3093` |
| Fork / outcomes | то же | `fork_scan` `:4107`, `fork_detector_scan` `:4261`, `resolve_fork_outcome` `:6285` |
| Sales / stock prefer | то же | `:5336+`, `:6042+`, `:12153+` |
| Entity form F | то же | `try_entity_form_answer` `:2536`, флаг `:1431` |
| Мера / pick entity | то же | `measure_choice` `:6638`, `pick_measure` `:8107`, `pick_entity` `:8155` |
| Aggregate | то же | `:8359`, `:8727` |
| Compose / fill / gate | то же | `:9448`, `:8994`, `:10149` |
| Enough / facts | то же | `:14929+` |
| Билеты clarify | то же | `issue_decision` `:6988`, `seal_clarify` `:7027`, `consume_decision` `:7082` |
| Оркестрация `answer` | то же | `:11810+` |
| Pipeline такт | `ubuntu/serenedb/pipeline.sh` | `:18-57` |
| Сборка слоя | `ubuntu/serenedb/build.sh` | `:147-452` |
| Корпус SQL | `ubuntu/serenedb/corpus_build.sql`, `corpus_merge.sql`, `corpus_init.sql` | зов из `build.sh` |
| Sync витрины | `ubuntu/serenedb/serene_sync.py` | зов `pipeline.sh:49` |
| Packet | `ubuntu/packet/packet_server.py`, `packet_apply.py` | listen `:41` |
| OData-шлюз | `ubuntu/1c-gateway/odata_gateway.py` (выкат) / репо gateway | L1-24/25 |
| Scorer | `ubuntu/serenedb/ab_scorer.py` | `:51-123`, `:617-765` |
| Юниты pipeline/odata | `ubuntu/systemd/` | timer/service |
| Юниты ask | `ubuntu/serenedb/systemd/` | `1c-serene-ask@.service` |
| Юниты MCP | `ubuntu/openclaw/systemd/` | `1c-mcp-ask*.service` |
| Гейты | `.claude/hooks/`, `.githooks/` | `git-gate.sh` |
| Аудит-сырьё | `docs/audit/level2/S1…S4`, `docs/audit/parts/*.md` | этот документ собран из них + сверка строк |

## Белые пятна

По коду отчётов аудита и точечной сверке **не установлено**:

1. Приём канала (Telegram / Open WebUI), персона бота, перефраз до `ask_1c` и финальная проза клиенту после строки инструмента — вне `mcp_ask` / `serene_ask`.
2. Полная логика `mcp_ask_pending` (в L1 только точки вызова).
3. Живые значения `/etc/1c-*.env` и фактические слушающие порты инстансов на хосте (в аудите не снимались).
4. Какой контур (packet vs HTTP) включён на конкретной базе в бою.
5. Тело `ACM.attach_choice_memory` и схема постоянной таблицы выбора — в модуле `ask_choice_mem` (зов shadow из `serene_ask.attach_memory_shadow` `:7212+`; путь применения `_try_memory_apply` в `serene_ask.py:15384+` есть, внутренности ACM по этому документу не разбирались).
6. Кто заполняет `search_fork_label` (детектор читает; писатель вне разобранных участков).
7. Точная SQL-формула **числа остатка** по баланс-регистру (участок stock в аудите — отбор/`no_data`/`clarify`, не SUM).
8. Полный круг арбитра готовых ответов после empty/unique (`answer` после `:13476`) — стык отмечен, внутренности не входили в сырьё S3.
9. Содержимое промптов `serene_enough.*` и точный JSON для `need_say`/`parse_facts`.
10. Verify-плагин OpenClaw после ответа инструмента — упомянут в docstring моста, в L1 не разобран.
11. ~~Запускается ли где-либо шаблон index со старым `serene_search_build.py`~~ — **закрыто Э5**: мёртвый двойник удалён; канон — `ubuntu/systemd` → `build.sh`.
12. Потребители ETL-KB (`oc_etl.py`) внутри `/srv/1c` поискового слоя — вызовов в участках 21–26 нет.
