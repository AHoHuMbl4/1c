# 24. bot-gateway

## Зачем участок нужен
`ubuntu/openclaw/mcp_ask.py` — MCP-сервер с инструментом `ask_1c`: принимает параметры от OpenClaw-бота, шлёт HTTP POST на `ASK_URL/ask`, форматирует JSON-ответ сервиса в строку для модели бота (`:484-650`, `:92-120`).  
`ubuntu/1c-gateway/gateway.py` и `odata_gateway.py` — отдельные read-only HTTP-прокси к MCP Toolkit 1С и к OData IIS; в коде участка вызовов между `mcp_ask` и этими прокси нет.

## Входы
**mcp_ask / `ask_1c`** (`:485-512`): `question`, опц. `focus`, `measure`, `context`, `prior`, `decision_id`, `user`, `memory`, `channel`, `rid` (все `str`, пустые по умолчанию).  
HTTP к `/ask` (`:94-112`): JSON с теми же полями (пустые не кладутся); `memory` только если `"remember"`/`"forget"` (`:516-517`, `:538`).  
Авторизация входящих к MCP: заголовок `Authorization: Bearer <MCP_TOKEN>` (`:81-85`).  
**gateway.py POST `/mcp`** (`:109-120`): тело JSON-RPC; Bearer `GW_GATEWAY_TOKEN` (`:86-91`).  
**odata_gateway.py GET** (`:112-122`): путь + query; Bearer `ODG_GATEWAY_TOKEN` (`:75-80`).

## Порядок работы
1. Старт MCP: без `MCP_TOKEN` — `SystemExit(2)` (`:76-79`); иначе FastMCP streamable HTTP + Auth + uvicorn (`:87-89`, `:653-656`).
2. `ask_1c`: TRACE `ask_start` (`:514`); `memory` → `remember`/`forget`/None (`:516-517`).
3. `_pending.apply_pending_before_ask(...)` (`:519-524`); при `refuse` → `CLARIFY_LOOP_REFUSE` (`:525-528`); при `short_circuit` → `_format_clarify_out` без `/ask` (`:529-533`).
4. Иначе `_ask` → POST `{ASK_URL}/ask` (`:535-538`, `:113-120`); HTTPError/`Exception` → `ERROR_REPLY` (`:539-546`).
5. По `kind` ответа (`:549+`):
   - `unavailable` → clear pending, `ERROR_REPLY` (`:555-557`);
   - `choice_error` → повтор `_ask` без `decision_id` (`:559-564`); если снова `choice_error` — clarify-текст без билета (`:572-577`);
   - `clarify` → `store_pending`, `_format_clarify_out` (`:579-583`);
   - `figures` → `FIGURES_HINT` + роли атомов/`ATOM_JSON`/опции/`PRESENTATION_JSON` (`:589-623`);
   - `no_data` / пустой `text` → `NO_DATA_REPLY` или текст с `[NO DATA]` (`:625-634`);
   - иначе ответный `text` (+ `[measure:…]`, `ATOM_JSON`, флаги) (`:636-650`).
6. **gateway.py**: GET `/health` локально (`:103-106`); POST `/mcp` → auth → `_decision` allowlist (`:122-126`) → под lock POST `{UPSTREAM}/mcp` (`:128-147`).
7. **odata_gateway.py**: GET `/health` (`:113-114`); иначе auth → `_path_ok` (блок `..`) (`:117-119`) → GET `{UPSTREAM}{path}` с Basic (`:120-132`); POST/PUT/PATCH/DELETE/MERGE → 405 (`:102-110`).

## Выходы
| Источник | Что | Кто дальше |
|---|---|---|
| `ask_1c` | `str` (маркеры `[FIGURES]`/`[CLARIFICATION…]`/`[NO DATA]`/`ATOM_JSON`/`PRESENTATION_JSON`) | OpenClaw-бот (MCP tool result) |
| `_ask` | JSON dict сервиса (`kind`, `text`, `atoms`/`atom`, `options`, `partial`, …) | ветки `ask_1c` |
| gateway `/mcp` | тело/статус upstream JSON-RPC | клиент MCP Toolkit |
| odata GET | тело/статус OData | клиент OData |
| оба `/health` | `gateway-ok` / `odata-gateway-ok` | мониторинг |

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| `mcp_ask.py:113-120` | HTTP POST `{ASK_URL}/ask`, Bearer `ASK_TOKEN` | запрос ответа сервиса |
| `mcp_ask.py:562-564` | тот же POST без `decision_id` | повтор после `choice_error` |
| `gateway.py:129-147` | HTTP POST `{GW_UPSTREAM}/mcp`, Bearer `GW_TOOLKIT_TOKEN` | прокси к Toolkit 1С |
| `odata_gateway.py:123-132` | HTTP GET `{ODG_UPSTREAM}{path}`, Basic `ODG_USER`/`ODG_PASS` | прокси к OData |
| SQL | нет | — |
| вызов языковой модели | нет | — |

## Переключатели
| Имя | Чтение | Умолчание |
|---|---|---|
| `ASK_URL` | `mcp_ask.py:46` | `http://127.0.0.1:8099` |
| `ASK_TOKEN` | `:47` | `""` (WARN при старте `:654-655`) |
| `MCP_HOST` / `MCP_PORT` | `:48-49` | `127.0.0.1` / `6016` |
| `ASK_TIMEOUT` | `:50` | `300` |
| `MCP_TOKEN` | `:58` | `""` (старт запрещён) |
| `ASK_TRACE` | `:60` | вкл.; выкл: `0`/`false`/`no` |
| `MCP_NO_DATA_REPLY` / `MCP_ERROR_REPLY` / `MCP_CLARIFY_LABEL` / `MCP_FIGURES_HINT` / `MCP_PARTIAL_HINT` / `MCP_CLARIFY_HINT` | `:130-155` | англ. строки в коде |
| `GW_LISTEN_HOST` / `GW_LISTEN_PORT` | `gateway.py:38-39` | `127.0.0.1` / `6010` |
| `GW_UPSTREAM` | `:40` | `http://192.168.56.1:6003` |
| `GW_TOOLKIT_TOKEN` / `GW_GATEWAY_TOKEN` | `:41-42` | `""` (GATEWAY обязателен `:155-158`) |
| `GW_TIMEOUT` | `:43` | `180` |
| `ODG_LISTEN_HOST` / `ODG_LISTEN_PORT` | `odata_gateway.py:46-47` | `127.0.0.1` / `6011` |
| `ODG_UPSTREAM` | `:49` | `…/1c/odata/standard.odata` |
| `ODG_USER` / `ODG_PASS` / `ODG_GATEWAY_TOKEN` | `:50-52` | `""` (TOKEN обязателен `:140-145`) |
| `ODG_TIMEOUT` | `:53` | `120` |

Юниты: `EnvironmentFile=/etc/1c-gateway.env` → `gateway.py` (`systemd/1c-gateway.service:10-11`); `/etc/1c-odata-gateway.env` → `odata_gateway.py` (`1c-odata-gateway.service:10-11`).

## Развилки
- Нет/неверный Bearer MCP → 401 (`mcp_ask.py:83-84`); то же у gateway/odata (`gateway.py:112-113`, `odata_gateway.py:115-116`).
- `kind` ответа `/ask` → разные строки боту (см. порядок п.5).
- `figures` с `options` → store pending + OPTIONS/кнопки; без options → clear (`:591-594`).
- `partial` с ключами из `PARTIAL_LOSS_KEYS` → дописывается `PARTIAL_HINT`+блок (`:372-378`, `:335-337`); budget/assumption-ключи в текст не идут.
- gateway: method вне `ALLOWED_METHODS`/`tools/call` или tool вне `ALLOWED_TOOLS` → JSON-RPC error 200 (`:45-58`, `:123-126`); `execute_code` в списке нет.
- odata: не-GET → 405; `..`/`%2e%2e` в пути → 403 (`:83-99`, `:117-119`).

## Чего здесь нет
- Связи `mcp_ask` ↔ `1c-gateway` / OData (импортов и URL между ними нет).
- Поиска в SereneDB, SQL, эмбеддинга, вызова LLM — только HTTP к `/ask` и форматирование.
- Приёма сообщения Telegram/WebUI: вход — уже вызов инструмента MCP.
- Плагина verify и персоны бота.
- Логики pending целиком: она в `mcp_ask_pending.py` (здесь только вызовы `:519`, `:527-533`, `:556`, `:582`, `:592-594`, `:626`, `:633`, `:636`).
