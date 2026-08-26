# S4. Контур эксплуатации и контроля качества

Сырьё L1: `25-systemd-env`, `20-ask-main-http`, `27-gates`, `28-scorer-tests`. Доп. сверка юнитов ask/MCP (их нет в шести файлах `ubuntu/systemd`).

## Коротко

Таймеры systemd будят oneshot-такт: sync витрины через OData-шлюз и `build.sh` слоя поиска в SereneDB. Отдельный long-running `1c-serene-ask[@база]` слушает HTTP `/ask` и `/health`, читает корпус/индекс и отдаёт JSON с `kind`/числом/уточнением. Мост `1c-mcp-ask[@база]` зовёт этот `/ask` для бота. Поведение ответа и health режут переменные из `/etc/1c-*.env` (порядок EnvironmentFile: последний слой сильнее). Живость ответа — `GET /health` (корпус + coverage_gap ± native freshness). Качество — `ab_scorer.py`: эталон SQL в psql, POST `/ask`, OK/FAIL по modes; при 0 сбоев пишет отметку в `.claude/`. Гейты в `.claude/hooks/` (через git-gate и хуки движков) останавливают коммит/выкат/правки без документов, графа, живой пробы okna и т.д.

## Схема пути

1. **Таймер такта** — `OnBootSec=3min`, затем `OnUnitInactiveSec=1min` → старт `1c-serene-pipeline[.service|@.service]` (`ubuntu/systemd/1c-serene-pipeline.timer:8-12`, `@.timer`). Дальше — сервис.
2. **Pipeline oneshot** — env из `/etc/1c-mcp-reports.env` + sync/embed (+ `@` → `/etc/1c-serene-pipeline-%i.env`); `pipeline.sh` → (опц.) packet-keep → `serene_sync.py` → `exec build.sh` (`25`, `pipeline.service:17-28`, `pipeline.sh:43-57`). Пишет витрину/корпус в SereneDB по `SERENEDB_DSN`.
3. **Index oneshot (опц.)** — тот же env, только `build.sh` (`1c-serene-index.service`).
4. **OData-шлюз** — `1c-odata-gateway@.service`: `odata_gateway.py` на `ODG_LISTEN_*`, GET→`ODG_UPSTREAM`, `/health` без токена; sync/build ходят с Bearer (`25`, `odata-gateway@.service:19-22`).
5. **Ask-сервис** — `1c-serene-ask@.service`: python `serene_ask.py`; env mcp-reports → embed → optional `1c-serene-ask.env` → **`1c-serene-ask-%i.env`** (`1c-serene-ask@.service:29-33`). `main`: без `ASK_TOKEN` → exit 2; иначе `ThreadingHTTPServer` (`serene_ask.py:15735-15743`).
6. **`GET /health`** — `count(*)` корпуса; `_health_gap`/`_classify_health_gap`; при `ASK_HEALTH_NATIVE_FRESHNESS=1` — `sdb_metrics`; 503 systemic/ошибка, 200 `serene-ask-ok` (+ freshness_lag) (`:15591-15638`).
7. **`POST /ask`** — Bearer; JSON → `answer_checked` → (options→`seal_clarify`) → `stale_note` по `search_quality.build_ts` → 200 JSON (`:15641-15714`). Исключение → 503 `kind=unavailable` (`:15715-15732`).
8. **MCP-мост** — `1c-mcp-ask@.service` / одиночный с `ASK_URL`/`MCP_PORT` в env (`1c-mcp-ask@.service:22-24`, `1c-mcp-ask.service:15-17`). Бот → MCP → ask.
9. **Измерение качества** — `ab_scorer.py`: TSV → `truth(sql)` psql → POST `/ask` (до 6 шагов clarify) → score → stdout + при полном попадании отметка (`.probe-okna-last-run` / `.golden-*`) (`28`, `:617-765`, `:571-614`).
10. **Гейты** — правка/commit/deploy: хуки движка + `.githooks/*` → `git-gate.sh`. Pre-commit: guard, люк, docs/graph/active/prompt/live-probe; commit-msg: sql-docs/diff; deploy: + golden (`27`, `git-gate.sh:68-73`). Отметка probe — вход `check-live-probe` / `check-golden`.

## Точки принятия решений

| Условие | Сворот |
|---|---|
| `ETL_ODATA_BASE` каталог vs URL | packet keep-marks vs HTTP load (`pipeline.sh:43-54`) |
| `embed_hosts_form_check` fail | pipeline exit 1 до sync (`pipeline.sh:21`) |
| sync код ≠0 | предупреждение, build всё равно (`pipeline.sh:49`) |
| `flock` занят | `build.sh` exit 0 «такт уже идёт» (`build.sh:76`) |
| OData: не-GET / нет Bearer / `..` | 405 / 401 / 403; `/health` открыт (`25`) |
| Ask: нет токена / пустой вопрос / не `/ask` | exit 2 при старте; 401/400/404 |
| `/health` gap `systemic` / ошибка корпуса | 503; `freshness_lag` → 200+freshness (`:15615-15630`) |
| `ASK_ENOUGH` / fork / entity_form / calendar / SQL_RRF / solr / scorer… | ветки внутри `answer`/`answer_checked` (`20`, флаги `:1424-1431`, `:3762`, `:3948-3959`, `:14929`) |
| `AB_PROBE`/`AB_CONTOUR`/`AB_GOLD_MODE`/`AB_CALENDAR_AXIS` | выбор TSV, live vs A/B restart scorers, имя отметки (`28`, `:51-119`, `:571-602`) |
| mode digits/kind/clarify/name | разный score; probe-digits требует `kind∈{answer,figures}` (`:698-713`) |
| гейт: люк `override.txt` с именем | `{}` вместо deny (`lib-hooks.sh`) |
| коммит: `Доки:` / `Числа:`\|`Бюджет:` | закрывает sql-docs / check-diff |
| индекс только `serene_ask.py` без свежей `okna probe … 0err/N` | deny live-probe (`check-live-probe.sh:15-38`) |
| deploy без той же отметки или md5≠HEAD по SRC_DIRS | deny golden (`check-golden.sh:62-78`) |

## Что участвует снаружи

**Юниты (шаблоны в репо):** `1c-serene-pipeline[.timer|@.timer|.service|@.service]`, `1c-serene-index.service`, `1c-odata-gateway@.service` (`ubuntu/systemd`); `1c-serene-ask[.service|@.service]` (`ubuntu/serenedb/systemd`); `1c-mcp-ask[.service|@.service]` (`ubuntu/openclaw/systemd`). Зависимости ask/pipeline: `serenedb.service` (юнит вне четырёх L1).

**Порты (умолчания в коде/примерах, не live-снимок):** SereneDB `7890` (`SERENEDB_DSN*` умолч./пример); OData-шлюз `ODG_LISTEN` умолч. `127.0.0.1:6011` (`25`); ask `ASK_LISTEN` умолч. `:8091` (`serene_ask.py:72-73`, пример env); одиночный mcp-ask зашивает `ASK_URL=:8099`, `MCP_PORT=6016` (`1c-mcp-ask.service:15-17`); шаблон mcp — порты только из `/etc/1c-mcp-ask-%i.env`.

**Env-файлы:** `/etc/1c-mcp-reports.env`, `/etc/1c-embed.env`, `/etc/1c-serene-sync.env`, `/etc/1c-serene-pipeline-%i.env`, `/etc/1c-odata-gateway-%i.env`, `/etc/1c-serene-ask.env`, `/etc/1c-serene-ask-%i.env`, `/etc/1c-mcp-ask[.env|-%i.env]`.

**Переключатели ответа (сводка):** `ASK_SCORER`, `ASK_SQL_RRF`, `ASK_RESOLVER_IVF`, `ASK_SOLR_SYNONYMS`(+dict), `ASK_CALENDAR_AXIS`, `ASK_ENTITY_FORM`, `ASK_ATOM_TERMINAL`, `ASK_SALES_RANK_CANON`, `ASK_FORK_*`, `ASK_ENOUGH`, `ASK_NOT_FOR`, `ASK_ORDER_BY_MEANING`, `ASK_RERANK_TOP`, `ASK_JOURNAL`/`ASK_CHOICE_MEMORY`/`ASK_MEMORY_APPLY`, `ASK_STALE_WARN_SEC`, `ASK_HEALTH_*`, `ASK_MONEY_UNIT`, `ASK_TOKEN`/`ASK_LISTEN_*` (`20` + чтения в `serene_ask.py`). Такт/embed: `SERENEDB_DSN`, `ETL_ODATA_BASE`, `ODG_*`, `EMBED_*`, `FORCE_REBUILD`, `WIKI_ALIAS_PER_TACT` (`25`).

**БД/таблицы (по L1):** `search_corpus`/`search_idx`/`search_tables`/`search_quality`; журнал `ask_journal*`; опц. `ask_scope`; эталоны scorer — SQL по `search_corpus` в TSV.

**LLM:** в ask — coverage/facts/enough/intent/compose (вызовы из конвейера, `20`); в scorer оценки ответа — нет (`28`); в гейтах — `sniper-kimi` на дифф (`27`).

**Файлы качества/гейтов:** TSV `ab-gold*.tsv` / `ab-probe-okna.tsv` / `ab-calendar-axis-okna.tsv`; отметки `.claude/.probe-okna-last-run`, `.golden-okna-last-run`, `.golden-last-run`; `override.txt`; `mcp-memory.json`; `activeContext.md`.

## Расхождения между отчётами уровня 1

нет (разный scope: `25` явно без ask/MCP-портов; `20`/`28`/`27` стыкуются по `:8091`, формату `okna probe … 0err/N`, Bearer).

## Белые пятна

- Содержимое `/etc/1c-*.env` и фактические слушающие порты инстансов в этой сессии не снимались.
- Юнит `serenedb.service`, монитор, вызывающий `/health`, wiki-alias/packet/open-webui — вне четырёх L1; здесь только имена зависимостей/комментарии в коде.
- Полный перечень `ASK_*` длиннее таблицы в `20` (много чтений выше диапазона HTTP-участка); влияние каждого флага на ветку ответа в S4 не развёрнуто.
- Кто именно в бою выставляет `ASK_URL` стейджинга `:8092` — только текст помощи в `check-live-probe.sh`/`check-golden.sh`, не контракт юнита.
