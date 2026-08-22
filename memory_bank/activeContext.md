# Active Context

_Обновлено: **2026-08-21.** Здесь — только живое: текущее состояние и «С ЧЕГО НАЧАТЬ».
История по дням — в [`progress.md`](progress.md); стадии по контракту — в
[`docs/TARGET_STATUS.md`](../docs/TARGET_STATUS.md)._

---

# ⏭ С ЧЕГО НАЧАТЬ СЛЕДУЮЩУЮ СЕССИЮ

🔴 **Режим оркестрации (владелец, 22.08)**: задачи исполнителям — через свежие
вызовы `cursor-agent -p --force --model auto` (1 задача = 1 процесс = чистый
контекст), параллель — swarm обёрток. Регламент: `docs/ORCHESTRATION_CURSOR.md`.
Субагенты Kimi — на дешёвой модели: `[secondary_model]` в каноне конфига, ставит
владелец + env-флаг (§6–7 документа).

🔴 **PROBE rid_norm verify — код в git, okna жив `[22.08]`**: verify/shell ищут
rid_norm (16 alnum) как serene_ask; lib-probe без esc_rid/sys NameError. Замок
**16/16**. okna «петли» `:8091` — journal ok, no_data, code_md5=c560aebe.
md5: probe_protocol 4cde0a31, lib-probe 5c7a356a.

🔴 **PROBE + journal verify — код в git `[22.08]`**: протокол `probe_protocol.py`/`lib-probe.sh`; dump/save/ab_scorer пишут строку PROBE и сверяют q_len в ask_journal. env-map.sh → RUNBOOK §9.1.

🔴 **проба okna 5/8 — fix в дереве, повтор — оркестратор `[22.08]`**:
кандидат `1ab7d928`: воскресенье no_data (→ `sales_period_empty`); петли clarify
каталог (→ named terms + balance-only/no_data); неделя figures (→ rank без re-gate).
Именованность — только `intent.terms`, без словаря вопросительных слов. md5 **`dc0fc4e3`**.
Замки **25+62+56**. Коммит+проба `:8092` 0err/8 — оркестратор.

🔴 **универсальный путь остатков — staged, коммит ждёт пробу okna `[22.08]`**:
okna «Какие остатки…» → ложный no_data (md5 c560aebe): «какие»=товар +
ранний stock_balance_no_data. Fix: карта `search_balance_map`, мост→clarify,
structural filter, prior без user, missing-table→пустая карта. Замок **24/24**;
md5 ask **1ab7d928**. Следующее: живая проба `:8092` **0err/8** → коммит;
выкат corpus_init+build, ab_scorer okna ≥14/25, сальdo счёта, wiki-alias.



🔴 **ai_embed 404 = устаревший SECRET base_url, не UA `[21.08]`**: klient-1
curl EMBED_HOST 200; ai_embed 404 HTML — секреты на старом хосте при новом env.
Fix: recreate SECRET + `embed_secrets_base_url_check`. ai_embed **0,42с**/1024.
Замок **5/5**. Выкат box_tune/embed_check/build/embed_all — оркестратор.

🔴 **возврат 12 — clarify vs прод, проба 8/8 с /opt `[21.08]`**: после lock
канона ALIAS_VETO/`ask_back` давали clarify при верном числе; qty-канон для
ранга. Кандидат только из `/opt/1c-mcp-reports`. Live `:8092` **8/8**.
md5 ask `c560aebe`. Выкат `:8091` — оркестратор.

🔴 **check-golden = probe+HEAD, не smoke ut_test `[21.08]`**: владелец снял
smoke как блокер выката (§3.90). Выкат: `.probe-okna-last-run` (`okna probe`
+ `0err/N`) **и** md5 SRC_DIRS = HEAD. Канон `check-golden.sh.new`; установка
`bash work/hooks/install-gates.sh`. REGRESSION_BASE1 обновлён.

🔴 **гейт живой пробы okna — код в git, установка за владельцем `[21.08]`**:
`AB_PROBE=okna` + `check-live-probe.sh` блокирует коммит `serene_ask.py` без
свежей отметки `0err/N`. Самопроверка против боя `:8091` — **4/8**, отметка
не писалась (красные: прошлый месяц / воскресенье clarify / почему ноль
clarify). Установка: `bash work/hooks/install-gates.sh`. Процедура —
`REGRESSION_BASE1` §живая проба. Deploy не делали.

🔴 **возврат 11 — sticky focus/stop2, код в git `[21.08]`**: live 1/4 на 96c184a:
июль 0 на передаче ТМЦ (sticky); воскресенье clarify после lock (stop2).
Fix: `sales_refuse_sticky_focus`, stop2 не при lock, memory noncanon refuse.
Замок **57/57** на кандидатах okna. md5 в коммите. Выкат+повтор 1–3 —
оркестратор.

🔴 **left() embed_missing — OOM count по emb, код в git `[21.08]`**: klient-1
fail-loop шага 5 («не удалось прочитать search_corpus») — `left()` сканировал
`emb` в CTE. Fix: подзапрос только лёгких колонок + stderr. Замок
`test_embed_left_count.py` **12/12**, ut_test left **2,9 с**. Выкат
`embed_missing.sh` на klient-1 — оркестратор; приёмка: шаг 5 жив, растёт
`count(emb)` корпуса. На деве после разбора нужен рестарт `serenedb`
(сломан temp_directory → PrivateTmp).

🔴 **возврат 8 — канон «продали» в git, выкат ждёт оркестратора `[21.08]`**:
PLAN §6bis: регистр по `written_by`, документ люк; intraday не fork. Код
`prefer_entity_for_sales` + stock named→no_data. Замок **15/15**. md5 ask
в коммите. Rank/прайс/покупают (#5–6) — следующий заход. Smoke ut_test
отметка — только выкат владельца (HOW_NOT_TO §3.90).

🔴 **контур: тени `_RecordType` + пересчёт после class `[21.08]`**: код в git
(`packet_config` shadow + `build.sh` 2-тер/`PACKET_BASE_ID`; `serene_sync`).
Дев: ut **782→695**, RT-витрина postgres/ut_test очищена; bases.json — поставить
из `work/packet/bases-contour-recalc-20260821.json` (root). okna/klient-1 —
оркестратор (md5 в CHANGELOG). Service в витрине не удаляли — объём в §10.7,
ждёт слова владельца.

🔴 **петля clarify OWUI — мост резолвит текст кодом `[21.08]`**:
`mcp_ask_pending` + проводка в `mcp_ask.py`. Текст/focus без `decision_id` →
билет; повтор вопроса → те же опции; N одинаковых → эскалация → отказ.
`test_mcp_ask` **39/39**, pending **16/16**, `test_decision_id` **31/31**.
md5 `mcp_ask.py` / `mcp_ask_pending.py` — в отчёте коммита. Выкат
`/opt/openclaw-mcp/` + `1c-mcp-ask@postgres` — оркестратор. serene_ask не
трогали.

🔴 **GPU-эмбеддер снова в норме, рестарт не делали `[21.08]`**: утром
таймауты `:8000/v1/embeddings` (08:44/09:25) + VRAM health 16,52 ГБ + batch3
1,4–2,2 с. Сейчас без рестарта: health **15,16 ГБ**, batch16 dev **~0,09–0,13 с**
(цель ~0,2), sustained short-text **~87 стр/с**. klient-1: corpus **15,15 млн**,
emb **7,85 млн**, null ≈**7,3 млн**, resolver null **16**; pipeline activating
на `embed_missing` — окна «0 стр/с» = COUNT/CREATE todo/UPDATE part, не мёртвый
GPU. SSH на `178.63.211.188` (nvidia-smi) из сессии не пустил floor. Прогноз
хвоста: ~8–23 ч @ 260…87 стр/с, на workers=3 дольше. CHANGELOG 21.08.

🔴 **таймаут ai_embed = `http_timeout` `[21.08]`**: доки + живой дев 26.07.3 —
ошибка `Timeout was reached … HTTP POST …/v1/embeddings` от GLOBAL
`http_timeout` (default 30, у нас 60). Ручка: `SET GLOBAL http_timeout = N`.
Секрет openai timeout не принимает. Штатного batch/async в доках нет.
Разведка в CHANGELOG / techContext ловушка 53; код не меняли.

🔴 **возврат 2: чистка service emb klient-1 + контроль такта `[21.08]`**:
после `c160c49` corpus/resolver service emb **5 663 216/605 784→0**;
после такта service emb **0**, resolver service rows **0**, business
corpus emb **2 185 215** цел; `resolver_values=1 631 785`. Выкат без
`+x` на `build.sh` → 126, починено `chmod`. DATA_SCOPE §9.12.

🔴 **okna sync-лаг закрыт `[21.08]`**: корень — merge-сторож не узнавал
`guid#N` у `document_установкаценноменклатуры` (321 757→439) → fail-loop с
20:01 20.08. Фикс в git+`/opt`; ручной merge: корпус 1 229 060, rows_missing
15; неделя на `:8091` снова `answer` (1 341 782.36). Timer возвращён —
`build_ts`/векторы 439 price-doc догонит такт.

🔴 **klient-1 ключ gpu-27b заменён, class полный `[21.08]`**:
[`docs/DATA_SCOPE_2026-08-21.md`](../docs/DATA_SCOPE_2026-08-21.md) §9.11.
`DEEPSEEK_API_KEY` → fp `5e489a22…`; в `1c-mcp-reports.env` добавлен
`DEEPSEEK_MODEL=Qwen3.8-27B` (иначе pipeline-classify → 404).
`search_entity_class` **1457/1457**, business/service **428/1029**; addr4 →
`service`. `/ask` HTTP 200 (не 401). Объём под чистку (не удаляли): corpus
service с emb **5 663 216** + resolver service emb **605 784**. Pipeline
был activating с «0 стр/с» — см. блок GPU выше (сервис ожил). Выкат classify
на `/opt` klient-1 — оркестратор.

🔴 **кнопка «в дашборд» — фронт готов, ждёт одно поле от бэкенда `[19.08]`**:
Action OWUI → `POST /dash/add` → `panel_from_scope.py` собирает панель из
спецификации счёта (`src`/`where`/`measure`/`axis`) и кладёт в личный дашборд
`ask-<sha1(id)>`; закрепляет **только после проверки запроса** через
`/api/ds/query`. Оффлайн **11/11**; живьём: панель по дням **900 строк**,
разрез **1 строка**, битая ось — отказ с перечнем годных колонок от SereneDB,
самопроверочный дашборд удалён; ручка: без сессии **401**, чужой путь **404**.
Ловушки **13** (тип datasource — `grafana-postgresql-datasource`) и **14**
(битый запрос = HTTP 400, ошибка в теле). **Дальше, два хвоста:** (1) бэкенд
— положить `ask_scope` (это `diag.счёт`) в метаданные сообщения OWUI, контракт
в `DASHBOARD_GRAFANA §2.1`: `diag` до чата не доходит, а `:8091` с фронта
закрыт ufw; (2) установить функцию в OWUI — нужен админ чата (Admin →
Functions). Caddy-маршрут `/dash/add` в git есть, на фронте не применён
(кнопка ходит по loopback, ей он не нужен).


🔴 **Полноту данных ведёт оркестратор** — [`docs/PLAN_ORCHESTRATOR.md`](../docs/PLAN_ORCHESTRATOR.md).
