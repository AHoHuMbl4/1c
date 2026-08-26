# 25. systemd-env

## Зачем участок нужен
Каталог `ubuntu/systemd` (6 файлов) — шаблоны systemd для такта свежести витрины/поиска и для побазового OData-шлюза. Таймеры будят oneshot-сервисы; сервисы подставляют `EnvironmentFile` и запускают `pipeline.sh` / `build.sh` / `odata_gateway.py`. Ответ боту на вопрос здесь не строится.

## Входы
| Источник | Что |
|---|---|
| `1c-serene-pipeline.timer` / `@.timer` | `OnBootSec=3min`, `OnUnitInactiveSec=1min`, `Persistent=true`, `AccuracySec=15s` (`pipeline.timer:8-12`, `@.timer:14-17`) |
| `1c-serene-pipeline.service` | env: `-/etc/1c-mcp-reports.env`, `/etc/1c-serene-sync.env`, `/etc/1c-embed.env` (`:17-25`); `ExecStart=/opt/1c-mcp-reports/pipeline.sh` (`:28`) |
| `1c-serene-pipeline@.service` | env: `-/etc/1c-mcp-reports.env`, `/etc/1c-embed.env`, `/etc/1c-serene-pipeline-%i.env` (`:34-36`); тот же `pipeline.sh` (`:37`); `%i` = имя экземпляра |
| `1c-serene-index.service` | те же три файла, что у одиночного pipeline (`:29-37`); `ExecStart=…/build.sh` (`:38`) |
| `1c-odata-gateway@.service` | `/etc/1c-odata-gateway-%i.env` (`:19`); `ExecStart=python3 /opt/1c-odata-gateway/odata_gateway.py` (`:20`) |
| Процессы (код репо → `/opt`) | переменные из env-файлов; аргументов CLI у юнитов нет |

## Порядок работы
1. Таймер (после boot 3 мин, далее через 1 мин после inactive своего сервиса) стартует одноимённый `*.service` (`pipeline.timer:8-10`, `@.timer:14-15`).
2. **Pipeline oneshot:** `WorkingDirectory=/opt/1c-mcp-reports`; systemd подставляет EnvironmentFile по порядку (последний перекрывает) — `pipeline.service:14-25`, `@.service:28-36`.
3. `pipeline.sh`: при наличии `box_tune.sh` — `embed_hosts_form_check` (`pipeline.sh:18-21`); при `SERENE_SRC_DIR`+`deploy.sh` — раскладка (`:28-30`); если `ETL_ODATA_BASE` — каталог, снимок `search_changed_sources` (`:43-47`); `serene_sync.py` (код ≠0 не стопит) (`:49`); при snapshot — возврат отметок (`:50-53`); `exec ./build.sh` (`:57`).
4. **Index oneshot:** только `build.sh` с теми же env, что одиночный pipeline (`index.service:29-38`).
5. **OData `@`:** long-running; `Restart=always` (`odata-gateway@.service:21-22`); в `main()` без `ODG_GATEWAY_TOKEN` → exit 2 (`odata_gateway.py:140-145`); иначе `ThreadingHTTPServer` на `ODG_LISTEN_*` (`:148-150`).
6. Лимиты: pipeline одиночный `TimeoutStartSec=3600`, `Restart=on-failure`/`3min`, `StartLimitBurst=5`/1h (`pipeline.service:11-12,26-27,6-7`); шаблон — `TimeoutStartSec=infinity`, те же Restart/StartLimit (`@.service:19-26`); index — `TimeoutStartSec=3600`, без Restart (`index.service:20`).
7. Зависимости: pipeline одиночный `After=… serenedb.service 1c-odata-gateway.service`, `Wants=serenedb` (`pipeline.service:5-6`); шаблон — `After=network.target serenedb`, без odata-gateway (`@.service:15-16`); gateway — `After/Wants=network-online` (`odata-gateway@.service:13-14`).

## Выходы
| Юнит | Результат | Кто потребляет (по коду запуска) |
|---|---|---|
| pipeline / pipeline@ | витрина (sync) + слой поиска (build) в SereneDB по `SERENEDB_DSN` | код такта пишет в БД; HTTP-ответ боту — не здесь |
| index | только сборка слоя (`build.sh`) | то же |
| odata-gateway@ | HTTP GET→upstream; `/health`; 405 на запись; 401/403 | клиенты с Bearer `ODG_GATEWAY_TOKEN` (sync/build через `ETL_ODATA_BASE`+токен) |
| timer | повторный start сервиса | systemd |

## Обращения наружу
| Место | Что | Назначение |
|---|---|---|
| `pipeline.sh:45-52` | `psql` `$SERENEDB_DSN` | packet: keep/restore `search_changed_sources` |
| `pipeline.sh:49` → `serene_sync.py` / `poc_load_entity.py` / `odata_census.py` | HTTP к `ETL_ODATA_BASE` + Bearer `ODG_GATEWAY_TOKEN`; SQL в DSN | дельта витрины / перепись |
| `build.sh` (секреты `:163-173`, корпус/merge/embed/…) | `psql`; HTTP OData через секрет SCOPE=`ETL_ODATA_BASE`; `ai_embed` через секреты EMBED_* | сборка корпуса, векторов, индекса |
| `build.sh:421` | `wiki_alias.sh` | разметка алиасов (модель — внутри скрипта) |
| `odata_gateway.py:122-132` | HTTP GET `ODG_UPSTREAM`+path, Basic `ODG_USER`/`ODG_PASS` | прокси к 1С OData |

## Переключатели
Чтение в коде процессов, которые юниты запускают (значения с диска `/etc` здесь не снимались).

| Имя | Где читается | Умолчание в коде |
|---|---|---|
| `SERENEDB_DSN` | `build.sh:30`, `serene_sync.py:103+`, `poc_load_entity.py:33`, `odata_census.py:36` | `host=127.0.0.1 port=7890 user=postgres` (+`dbname=postgres` где указано) |
| `ETL_ODATA_BASE` | `pipeline.sh:43`, `build.sh:32`, `poc_load_entity.py:32`, `odata_census.py:33` | URL `http://127.0.0.1:6011`; каталог → packet-ветка |
| `ODG_GATEWAY_TOKEN` | `build.sh:163`, `poc_load_entity.py:26`, `odata_census.py:49`, `odata_gateway.py:52` | `""`; у шлюза пустой → не старт |
| `ODG_LISTEN_HOST`/`PORT` | `odata_gateway.py:46-47` | `127.0.0.1` / `6011` |
| `ODG_UPSTREAM` | `:49` | `http://192.168.56.1:6003/1c/odata/standard.odata` |
| `ODG_USER`/`ODG_PASS`/`ODG_TIMEOUT` | `:50-53` | `""`/`""`/`120` |
| `EMBED_MODEL` | `build.sh:43-44` | пусто → exit 1 |
| `EMBED_HOST`/`EMBED_HOSTS`/`EMBED_BASE_URL` | `pipeline.sh`→`box_tune.sh:161-169`, `build.sh:108-109` | пусто → стоп формы / нет пар ключ×хост |
| `EMBED_API_KEY(S)` / `ALIBABA_API_KEY(S)` | `build.sh:101` | пусто → «не задан ни один ключ» |
| `EMBED_PATH` | `build.sh:168` | нет подстановки в `build.sh` (берётся из env как есть) |
| `EMBED_DIM`/`EMBED_MAXLEN` | `build.sh:45,54` | `1024` / `20000` |
| `BUILD_EMBED_WORKERS`/`BUILD_THREAD_MIN` | `build.sh:33,37` | `8` / `WORKERS+8` |
| `FORCE_REBUILD`/`EMBED_SERVICE` | `build.sh:247,394` | `0` |
| `WIKI_ALIAS_PER_TACT` | `build.sh:421` | `100` |
| `SERENE_SRC_DIR` | `pipeline.sh:28` | пусто → без deploy |
| `SELECTED_FILE`/`SYNC_SKIP_SERVICE`/`CENSUS_MAX_AGE`/`SYNC_MAX_ENTITIES` | `serene_sync.py:28-29,178,262,316` | рядом `serene-entities.txt` / `"1"` / `3600` / `0` |
| `CSV_DIR`/`ETL_PAGE`/`ETL_HTTP_TIMEOUT` | `poc_load_entity.py:34,49,60` | `/var/lib/serenedb` / `10000` / `600` |
| `PACKET_BASE_ID`/`PACKET_BASES` | `build.sh:305,318` | шаг только если ID задан; bases `/etc/1c-packet-bases.json` |

Порядок EnvironmentFile в юнитах задаёт, какой файл победит при одинаковых именах (`pipeline.service:14-16`, `@.service:28-33`, `index.service:22-28`).

## Развилки
- Одиночный vs `@`: разные наборы env-файлов и `TimeoutStartSec` (`pipeline.service` vs `@.service`).
- `ETL_ODATA_BASE` — каталог vs URL: keep-marks в pipeline (`pipeline.sh:43-54`); packet vs HTTP в load/census.
- `embed_hosts_form_check` fail → pipeline exit 1 до синка (`pipeline.sh:21`).
- `FORCE_REBUILD≠1` и `SKIP_BUILD=1` → корпус не пересобирается (`build.sh:247`).
- `EMBED_SERVICE=1` → доп. проход векторов сервиса (`build.sh:394-396`).
- Gateway: не-GET → 405 (`odata_gateway.py:102-110`); нет Bearer → 401 (`:115-116`); `..` в path → 403 (`:117-119`); `/health` без токена (`:113-114`).
- `flock` занят → `build.sh` exit 0 «такт уже идёт» (`build.sh:76`).
- Код синка ≠0 → предупреждение, build всё равно (`pipeline.sh:49`).

## Чего здесь нет
- Юнитов ask/mcp/monitor/wiki-alias/packet/serenedb/config-ui/etl — их unit-файлы лежат в других каталогах (`ubuntu/serenedb/systemd`, `ubuntu/openclaw/systemd`, …), не в `ubuntu/systemd`.
- Портов ask/MCP в этих шести файлах нет.
- `User=` в юнитах участка нет (systemd default).
- У `pipeline*.service` / `index.service` секции `[Install]` нет; у gateway@ и обоих timer — `WantedBy=…` есть.
- Чтения содержимого `/etc/1c-*.env` с диска в этом отчёте нет — только имена переменных из кода.
