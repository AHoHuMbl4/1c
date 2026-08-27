# L4: сверка `docs/HOW_IT_REALLY_WORKS.md` по коду

Дата: 2026-08-25. Правки только в `HOW_IT_REALLY_WORKS.md` и этом журнале.
Код не менялся. Сеть / БД / сервисы / git commit — не трогались.

Вердикты: **верно** | **исправлено** | **не подтверждается**.

| # | Утверждение | Вердикт | Источник |
|---|---|---|---|
| 1 | Бот зовёт MCP `ask_1c` (`mcp_ask.py`) | верно | `ubuntu/openclaw/mcp_ask.py:484-487` |
| 2 | Мост шлёт `POST {ASK_URL}/ask` | верно | `mcp_ask.py:113-120` |
| 3 | `serene_ask` читает SereneDB RO, intent→поиск→SQL→compose→fill→gate | верно | `serene_ask.py:63`, `answer` `:11810+`, compose/fill/gate |
| 4 | Числа считает база; модель — разбор/выбор/текст вокруг слотов | верно | `ANSWER_SYS` / compose `:9549+` («values are not shown») |
| 5 | Схема: ветка A packet `:6021` → apply → витрина | верно | `packet_server.py:41`; `packet_apply.py` |
| 6 | Схема: ветка B gateway `:6011` → `serene_sync` | верно | `odata_gateway.py:46-47`; `pipeline.sh:49` |
| 7 | Таймер `1c-serene-pipeline` → `pipeline.sh` → `build.sh` | верно | `1c-serene-pipeline.timer:8-10`; `pipeline.service:28`; `pipeline.sh:57` |
| 8 | ask: intent → период → поиск → src/мера → SQL → compose → fill → gate | верно | `answer` `:11810+` |
| 9 | mcp форматирует строку боту | верно | `mcp_ask.py:549-650` |
| 10 | Шаг 1: `windows/odata-setup` вне такта ask | верно | каталог `windows/odata-setup` (вне ask-пути) |
| 11 | Пакет: цикл агента `Tact.Run` | исправлено | было «`Tact.Run`»; факт: `new Tact(…).Run()` `PacketAgent.cs:3167-3180` |
| 12 | `PACKET_LISTEN` умолч. `127.0.0.1:6021` (`:41`) | верно | `packet_server.py:41` |
| 13 | Apply timer `OnBootSec=2min`, `OnUnitActiveSec=2min` | верно | `ubuntu/packet/systemd/1c-packet-apply.timer:6-7` |
| 14 | Gateway `ODG_LISTEN` умолч. `:6011` | верно | `odata_gateway.py:46-47` |
| 15 | Pipeline timer `OnBootSec=3min`, `OnUnitInactiveSec=1min` | верно | `1c-serene-pipeline.timer:8-10` |
| 16 | Exec `/opt/1c-mcp-reports/pipeline.sh` | верно | `1c-serene-pipeline.service:28` |
| 17 | `pipeline.sh`: keep marks при каталоге `ETL_ODATA_BASE`; sync код≠0 не стопит; `exec build.sh` (`:42-57`) | верно | `pipeline.sh:42-57` |
| 18 | Preflight embed form `:18-21` | верно | `pipeline.sh:18-21` |
| 19 | Корпус: init → build → merge (`build.sh:147-279`) | верно | `build.sh:147-148`, `:255-279` (в диапазоне также секреты) |
| 20 | Classify fail-closed; `PACKET_BASE_ID` → `packet_config` (`:296-320`) | верно | `build.sh:296-320` |
| 21 | Embed: labels → resolver → corpus; service только при `EMBED_SERVICE=1` (`:336-399`) | верно | `build.sh:336-399` |
| 22 | VACUUM search_idx → coverage → wiki → solr_synonyms fail-closed → cards → postcheck (`:403-452`) | верно | `build.sh:403-452` |
| 23 | `oc_etl.py` → KB, таймер `03:00`, не пишет `search_*` | верно | `ubuntu/1c-etl/oc_etl.py`; `1c-etl.timer` (аудит 26) |
| 24 | `ETL_ODATA_BASE` каталог = packet; URL = HTTP | верно | `pipeline.sh:43-48`; `build.sh:32` `GATE=…` |
| 25 | Боевой сборщик — `build.sh`, не `serene_search_build.py` (`build.sh:4`) | верно | `build.sh:4-5`; `ubuntu/systemd/1c-serene-index.service:38` |
| 26 | Второй `build.sh` при flock → exit 0 (`:76`) | верно | `build.sh:76` |
| 27 | Ask читает `SERENEDB_DSN_RO` (`:63`), не ходит в 1С/gateway | верно | `serene_ask.py:63` |
| 28 | Env-файлы такта/ask/mcp/packet/gateway | верно | юниты `ubuntu/systemd/`, `ubuntu/serenedb/systemd/`, `ubuntu/openclaw/systemd/`, `ubuntu/packet/systemd/` |
| 29 | `PACKET_ROOT` `/var/lib/1c-packet` | верно | `packet_server.py:40`; `packet_apply.py:33` |
| 30 | `PACKET_META_DIR` `/var/lib/serenedb/packet-meta` | верно | `packet_apply.py:593`; `packet_config.py:55` |
| 31 | `CSV_DIR` `/var/lib/serenedb` | верно | `poc_load_entity.py:34`; `build.sh` `${CSV_DIR:-/var/lib/serenedb}` |
| 32 | Путь вопроса #1: `ask_1c` `:485-512` | верно | `mcp_ask.py:485-512` (сигнатура+docstring) |
| 33 | Pending refuse/short_circuit `:519-533` | верно | `mcp_ask.py:519-533` |
| 34 | POST + Bearer; handler `:15641-15692` | верно | `mcp_ask.py:113-118`; `serene_ask.py:15641-15692` |
| 35 | `answer_checked` → `_answer_checked_core` `:15411+`, `:15337+` | верно | defs на этих строках |
| 36 | `ASK_ENOUGH`: intent → verdict_before → clarify (`:15345-15379`, `:14929`) | верно | `_answer_checked_core`; `ENOUGH_ON` `:14929` |
| 37 | `parse_intent` / `_one_intent` / `_normalize_intent` `:1289`, `:1228-1244` | верно | defs/вызовы |
| 38 | Период: `apply_period_leader` `:1772`, `period_preds` `:1395`, флаг calendar `:1424` | верно | defs; в `answer` calendar через `expand_readings_calendar_axis` |
| 39 | coverage / early stock named `:11905-11925` | верно | `serene_ask.py:11905-11925` |
| 40 | probe/match_expr/tables_of/meaning_candidates `:2646`, `:2775`, `:2941`, `:3093` | верно | defs |
| 41 | aggregate / aggregate_groups `:8359`, `:8727` | верно | defs |
| 42 | compose_slot_values / compose `:7410`, `:9448`, `:9669` | верно | defs; ds_chat в compose `:9669` |
| 43 | `_fill_figures` / `fill_atom_pairs` `:8994`, `:7666` | верно | defs |
| 44 | formulation_flaws / gate / retry compose `:9310+`, `:10149`, `:14674-14763` | верно | использование `:14677+`, retry `:14707+` |
| 45 | seal_clarify / stale / JSON 200 `:15693-15714`, seal `:7027` | верно | handler + def |
| 46 | Мост по kind `:549-650` | верно | `mcp_ask.py:549-650` |
| 47 | Таблица chat-вызовов (intent/pick/axis/clarify/refuse/compose/arbitrate/coverage/facts/need) | верно | `ds_chat` на указанных строках (grep) |
| 48 | Emped `embed_one`/`ai_embed` `:744`, `:297`; rerank HTTP; в mcp LLM нет | верно | defs; `mcp_ask` без ds_chat |
| 49 | kinds: answer/figures/clarify/no_data/unavailable/choice_error | верно | возвраты в `serene_ask.py` |
| 50 | HTTP: 401/400/404/503; `/health` 503/200 | исправлено | было `:15615-15630` (неполно); факт `do_GET` `:15591-15638`, `do_POST` ошибки `:15647-15732` |
| 51 | Ранний stock no_data `:11920-11925`, `:12565-12570` | верно | код |
| 52 | prefer_entity_* `:12153-12155`; stock filters `:12156-12181` | верно | код |
| 53 | fork_detector_scan `:4261`, оркестрация `:12571-12629`; fork_scan `:4107+` | верно | defs/зовы |
| 54 | entity form pre_entity `:2536`, `:12637-12651`; после arb `:13315-13320`; forms distinct/complement/structs[0] | верно | `entity_form_pick` `:2503-2506`; `entity_form_compute` |
| 55 | sticky/hold `:12671+` | верно | `sales_refuse_sticky_focus`, `hold_settled_entity` |
| 56 | Fork A/B/C: флаги `:3948-3949` | исправлено | умолч. на `:3949-3950` (коммент был на 3948) |
| 57 | `resolve_fork_outcome` A/B/C/unique/uncounted/scan_error `:6285-6334` | верно | код |
| 58 | Мера: measure_pick→resolve; иначе sales; иначе measure_choice | исправлено | факт порядок: plan/`measure_choice`/`pick_measure` → unresolved → measure_pick → sales-canon (`:13901-14024`) |
| 59 | rank_axis_resolve LLM→stem→rerank `:4979-5041`; deterministic `:5084`, `:14584+` | верно | код |
| 60 | seal/issue/consume; memory shadow/apply | верно | после правки apply → `_try_memory_apply` `:15384+` |
| 61 | Продажи lift по written_by, канон «первого scored» `:5336+` | исправлено | lift в `prefer_entity_for_sales` `:5428+`; канон `sales_canon_src` `:5534`; `:5336` = `sales_rank_engaged` |
| 62 | Остатки no_data `:6042-6049`; bridge clarify `:6103-6136` | верно | defs |
| 63 | focus/trusted гасят fork/entity-form | верно | условия `:12571+`, `:12637` |
| 64 | Юнит pipeline → `pipeline.sh` | верно | `ubuntu/systemd/` |
| 65 | `1c-serene-index.service` → только `build.sh` (`ubuntu/systemd/`) | верно | `ubuntu/systemd/1c-serene-index.service:38` (мёртвый двойник в `serenedb/systemd` удалён Э5) |
| 66 | ask@ env порядок mcp-reports→embed→ask→ask-%i | верно | `1c-serene-ask@.service:29-32` |
| 67 | mcp-ask одиночный `ASK_URL=:8099`, `MCP_PORT=6016` (`:15-17`) | верно | `1c-mcp-ask.service:15-17` |
| 68 | ask без `ASK_TOKEN` → exit 2 (`:15735+`) | верно | `main` `:15735-15739` |
| 69 | MCP без `MCP_TOKEN` → SystemExit(2) (`:76-79`) | верно | `mcp_ask.py:76-79` |
| 70 | Порт SereneDB `:7890` (env/юниты) | верно | `build.sh:30` default DSN `port=7890`; в ask — из env |
| 71 | Порты gateway/packet/ask/mcp defaults | верно | см. строки выше |
| 72 | Все env-переключатели таблицы (умолч. + строки) | верно | сверка каждой строки `serene_ask.py` (после правки FORK `:3949-3950`) |
| 73 | `/health` corpus/gap/freshness | верно | `:15591-15638` |
| 74 | ab_scorer TSV→psql→POST, до 6 clarify, modes | верно | `ask_with_clarify_follow(…, max_steps=6)` `:352`; modes в scorer |
| 75 | Выбор TSV AB_PROBE/CONTOUR/CALENDAR `:51-69` | верно | `resolve_gold_file` |
| 76 | Отметки `.probe-okna-last-run` / golden (`:571-614`) | верно | `write_mark` |
| 77 | Гейты коммита + deploy:golden в `git-gate.sh:72+` | исправлено | `git-gate.sh:68-73` = docs/graph/active/prompt/live-probe + sql-docs/diff; `check-golden` — PreToolUse (settings/hooks.json), не git-gate |
| 78 | Люк `override.txt` не потребляется | верно | `git-gate.sh:48-56` |
| 79 | Scorer не зовёт LLM для оценки | верно | `docs/audit/parts/28-scorer-tests.md` + код scorer |
| 80 | Якоря раздела «Где что лежит» (функции/файлы) | верно | defs совпадают (после правок sales/fork/memory) |
| 81 | Белое пятно: канал/персона бота вне mcp/ask | не подтверждается | вне разобранного кода; оставлено в белых пятнах |
| 82 | Белое пятно: полная логика `mcp_ask_pending` | не подтверждается | в L4 смотрели только точки вызова в `mcp_ask.py` |
| 83 | Белое пятно: живые `/etc/*.env` и порты хоста | не подтверждается | намеренно не снимались |
| 84 | Белое пятно: packet vs HTTP на конкретной базе | не подтверждается | зависит от env хоста |
| 85 | Белое пятно: тело ACM / таблица памяти | исправлено (уточнение) | зов shadow `:7212+` и `_try_memory_apply` `:15384+` есть; тело ACM/`ask_choice_mem` и схема таблицы — не разбирались |
| 86 | Белое пятно: кто пишет `search_fork_label` | не подтверждается | ask только SELECT (`fork_labels_of` `:4503`) |
| 87 | Белое пятно: SQL SUM остатка по баланс-регистру | не подтверждается | в разобранных stock-участках — отбор/no_data/clarify |
| 88 | Белое пятно: полный круг арбитра после `:13476` | не подтверждается | стык есть; внутренности не вычитывались целиком в L4 |
| 89 | Белое пятно: промпты `serene_enough.*` / JSON need_say | не подтверждается | модуль `serene_enough` не разбирался |
| 90 | Белое пятно: verify-плагин OpenClaw | не подтверждается | docstring моста; код плагина не смотрели |
| 91 | Белое пятно: запускается ли `serenedb/systemd/…index` со старым build | не подтверждается | в дереве два шаблона; live unit-files не снимались |
| 92 | Белое пятно: потребители `oc_etl` в search-слое | не подтверждается | вызовов в ask/build нет |

## Счёт

| | |
|---|---|
| Проверено (строк таблицы) | **92** |
| Верно | **78** |
| Исправлено | **7** |
| Не подтверждается | **7** |

Исправления в `HOW_IT_REALLY_WORKS.md`:

1. Порядок выбора меры (#7) — по коду `:13901-14024`.
2. `check-golden` вынесен из «гейтов коммита / git-gate» в отдельную строку PreToolUse.
3. Продажи: якорь lift/канона с `:5336+` на `prefer_entity_for_sales` / `sales_canon_src`.
4. Флаги fork `:3948-3949` → `:3949-3950`.
5. `/health` диапазон строк → `:15591-15638` (вкл. freshness_lag→200).
6. Пакет-агент: `new Tact(…).Run()` + путь `PacketAgent.cs:3167-3180`.
7. Белое пятно #5 уточнено (путь `_try_memory_apply` есть в `serene_ask`).
