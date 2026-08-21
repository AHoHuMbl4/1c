# Active Context

_Обновлено: **2026-08-21.** Здесь — только живое: текущее состояние и «С ЧЕГО НАЧАТЬ».
История по дням — в [`progress.md`](progress.md); стадии по контракту — в
[`docs/TARGET_STATUS.md`](../docs/TARGET_STATUS.md)._

---

# ⏭ С ЧЕГО НАЧАТЬ СЛЕДУЮЩУЮ СЕССИЮ


🔴 **GPU-эмбеддер снова в норме, рестарт не делали `[21.08]`**: утром
таймауты `:8000/v1/embeddings` (08:44/09:25) + VRAM health 16,52 ГБ + batch3
1,4–2,2 с. Сейчас без рестарта: health **15,16 ГБ**, batch16 dev **~0,09–0,13 с**
(цель ~0,2), sustained short-text **~87 стр/с**. klient-1: corpus **15,15 млн**,
emb **7,85 млн**, null ≈**7,3 млн**, resolver null **16**; pipeline activating
на `embed_missing` — окна «0 стр/с» = COUNT/CREATE todo/UPDATE part, не мёртвый
GPU. SSH на `178.63.211.188` (nvidia-smi) из сессии не пустил floor. Прогноз
хвоста: ~8–23 ч @ 260…87 стр/с, на workers=3 дольше. CHANGELOG 21.08.

🔴 **возврат 2: fail-closed разметка + service без emb — код в git `[21.08]`**:
classify exit 2 → стоп такта; resolver/labels/card не берут service.
`test_classify_fail_closed` 11/11. md5 build `3234fcdf`, classify `5db1cbce`,
resolver `d8c5ea64`. Чистка emb klient-1 (5,66M + 0,61M) — после выката
оркестратором. DATA_SCOPE §9.12.

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

🔴 **дашборды okna — вход жив, `No data` починен и принят `[19.08]`**: владелец
открыл `/dash/enter` из браузера — дашборд открылся **без второго логина**
(последний хоп цепочки закрыт). Панели при этом `No data`: datasource
создавался без `jsonData.database`, а Grafana 13 у postgres читает имя базы
оттуда (ловушка 11; probe установщика при этом проходит и ничего не
доказывает). Отсечено чтением: юниты active, TCP до релея OK, стартовый
хендшейк postgres отвечает SASL, uid datasource совпадает, падает и
`count(*)`. Код в git: `jsonData.database` в `setup-okna-grafana.sh`, шаг 8
восстанавливает дашборды из семян, контурное семя `grafana/contours/okna/okna-sales.json` (ставится только по `DASHBOARD_SEEDS_DIR`)
(дашборд жил только в `grafana.db` — переустановка теряла его молча),
выгрузка `grafana/export-dashboards.py`. **Выкат сделан и принят**: на фронте
`json_data` = `{"database":"postgres","postgresVersion":1500,"sslmode":"disable"}`,
приёмка `grafana/check-panels.py` — «сумма по дням» **900 строк**, «Строк в
витрине» **1**, `без данных 0`. Приёмка живёт кодом (шаг 9 установщика зовёт
тот же инструмент; окно берётся из дашборда, не зашито). **Дальше:** кнопка
«добавить в дашборд» (OWUI Action → API панелей). 🔑 Пароли `GRAFANA_ADMIN_PASSWORD`
и `SERENE_RO_PW` засветились в переписке 19.08 — сменить (после смены
`SERENE_RO_PW` на бэкенде прогнать установщик фронта с новым значением).

🔴 **rank 217.10 + регистр из табчастей — код в git `[19.08]`**: (в) `{total}`≠лидер
→ gate 217.10; fix compose/fill + детерминированный топ-1 (rid `7a1362c8`). (б)
prefer снимает tabparts, fork_pool через prefer. **36/36** + F-замки. md5 **`79d2dca3`**.
Выкат `:8091` — оркестратор.

🔴 **веб-чат okna — утечка протокола/RAG — код в git `[19.08]`**: baulogistic
утекали EN-рассуждения про decision_id/tickets (путь `/v1` без
`message_sending`); кручение stale билета; fallback в OWUI knowledge-tools.
Fix: verify-plugin **1.1.8** (`hasProtocolLeak` на finalize, EN strip,
stale-id refresh, block wiki/RAG side tools), `configure-branding.py`
`builtinTools.*=false`, docstring `mcp_ask.py`. Оффлайн **126/126** +
**35/35**. md5 core **`7d3c1fc0`**, index **`f215bc47`**, mcp **`798caaad`**,
branding **`9cf2f1eb`**. Выкат web-гейт + branding на фронте — оркестратор;
живой «какой самый продаваемый товар вчера?» — после выката.

🔴 **золотой okna + smoke-гейт — код в git `[19.08]`**: `ab-gold-okna.tsv`
(10 вопросов), `ab_scorer.py` (`AB_CONTOUR=okna`, `AB_GOLD_MODE=smoke`),
`check-golden.sh` (smoke `0err/N` до выката). Smoke ut_test **0err/8** ✓.
Okna `:8091` **3/10**, 2 сбоя, склад no_data ✓; `/opt` ask **`d442630f`** ≠
git cd1789b (`372b529e`) — **повтор приёмки после выката rank-hotfix**.
md5 tsv **`6db327ad`**, scorer **`e3368d07`**, гейт **`9d63b8a5`**.

🔴 **возврат 7: B-форма + fork без match + scorer 0 [21.08]**: живой B «вчера»
принят; «неделя» — регистр выпадал из-за повторного match в `fork_scan` (п.13) —
match снят, `fork.excluded` в diag; scorer воскресенье coalesce/0 + kind answer|no_data.
Оффлайн 43/26/19. md5 ask **`3c022b6e`**. Выкат `:8091` — оркестратор.

🔴 **fork «продали»→headline — код в git, выкат `:8091` `[21.08]`**:
живой TRACE: `величина=продали`, `rel=[]` → NA/empty при SQL Всего; fix
`_fork_relevant`/`_fork_headline_measure` — want=sum + неразрешённое слово →
headline; NA только для явной меры без поля. Оффлайн **41/41** + **24/24**;
живой A + **49155.96** — оркестратор.

🔴 **fork NA want=sum без measure — код в git, выкат `:8091` `[19.08]`**:
«сколько продали вчера?» → `fork.classes=1`, было `outcome=empty` (NA при
посчитанном `Всего`); fix `_fork_relevant`/`_fork_headline_measure` + rel по
`want=sum`; `diag.fork.outcome_reason`/`na_classes`. Оффлайн **34/34** +
outcomes **24/24**; md5 ask **`ef318b60`**. Живой A + **49155.96** — оркестратор.

🔴 **rank gate числа из имён групп — код в git `[19.08]`**:
Заход-5: `_norm_numbers(g["name"])` в whitelist — числа внутри подписей
(«0,5 mm», «12 G») заземлены. Плюс полная числовая поверхность agg полей.
`_rank_wants_quantity` для товарного рейтинга без Количества.
Оффлайн **45/132/92/24/18/30/26**. md5 ask **`7f3e9d57`**. Выкат — оркестратор.

🔴 **money unit «шт/количество» и хвост rank без голых чисел — код в git `[19.08]`**: в `ubuntu/serenedb/serene_ask.py` включена `postprocess_money_answer_text()` для money=True и хвост word-anchored через `· всего позиций/записей`. Оффлайн-замки: `49 ok / 0 fail`. Дальше: оркестратор проверит живую цепочку после выката.

🔴 **klient-1 первая сборка — СЛИЯНИЕ ЗАКРЫТО `[18.08]`**: `search_corpus`
**15 148 327** / 1457 сущностей; `/health` ok; store.db **60G** (155G диск,
67G своб). Пачки **17/17**, exit 0 (21:08 UTC). Догон: ENOSPC на 96G →
апгрейд диска; checkpoint-invalidated → **рестарт serenedb** (WAL 115K,
без OOM-петли); правка 48h-окна для частичного merge в git. Pipeline timer
**active**, такт идёт (resolver embed). **Дальше:** векторы gpu-erw (~15,1M,
отдельное окно); `box_tune_restore` — владельцу (memory_limit 12.4GiB,
build-swap 12G активны). `corpus_build.sql` **3c2abbce** на `/opt` — не
трогать.

🔴 **догон корпуса okna ЗАКРЫТ `[18.08]`**: регистр 77527=витрина, дни 17.08
176 / 693 688,38; 18.08 81; 19.08 247 — призраков нет. `/health` freshness_lag.
Журнал 20:03: «список не затирался» → 30 из 351. Замок: `changed_sources_sql` +
`tmp3_lag`. Оффлайн **17/17**. Таймер возвращён. Отчёт CORPUS_VITRINE §5–6.

🔴 **класс F ось→ПКО — код в git `[18.08]`**: после снятых entity+measure
цепочка не меняет сущность (rid `83ca8b22`: регистр 331 → не физлицо 0 / не
ПКО 4). Ось `ДокументОснование` не пересаживает settled-документ на ПКО.
Оффлайн: terminal_round **24/24**, axis_focus **18/18**; прежние замки зелёные
(period_empty 30, measure_empty 26, gate 132, compose 92, period_bounds 3,
health_gap 14, fork_outcomes 24, decision_id 31). md5 ask **`4ad9a272`**.
Выкат `:8091` — оркестратор. Живое: «сколько продали вчера всего?» → регистр
→ «итого» → число. Частоты шага 0 — `docs/CLARIFY_JOURNAL_OKNA_2026-08-18.md`.

🔴 **дашборды — Grafana, стенд зелёный `[18.08]`**: решение владельца — Grafana.
Стенд 13.2.0 в `/dev/shm` на `:3001` (квота /srv ~700МБ): datasource SereneDB
`serene_ro`, демо-дашборд `/d/stand-from-chat` по живой витрине okna; кнопка
«добавить в дашборд» = GET→append→POST панели (доказано). Ловушки: колонки
VARCHAR → касты обязательны; API по uid; `allow_embedding=true`; refresh —
на уровне дашборда. Код `work/grafana-stand/setup-grafana-stand.sh`, дизайн —
`docs/DASHBOARD_GRAFANA.md`. Выката нет. Следующий шаг: адаптер
«ответ ask → панель» + OWUI Action.

🔴 **дашборды — сквозная авторизация замерена `[18.08]`**: решение владельца
«та же, что в чате, без второго логина». `[auth.jwt]` RS256: вход по заголовку
`X-JWT-Assertion` на каждый запрос (cookie→header на Caddy); `url_login`
логинит только первый запрос (сессии нет), `header_name` обязателен явно —
обе ловушки замером. Минтер ссылки `work/grafana-stand/mint-jwt.py` (зародыш
адаптера). Caddy-снипет в §2 документа на живом фронте не замерян.
Открыто: размещение Grafana в продукте (§3.1), адаптер `/dash/enter`.

🔴 **дашборды — ВЫКАТ на okna `[18.08]`**: решение владельца — Grafana на
веб-сервере okna. Фронт: `1c-grafana` (:3001, подпуть `/dash/`), `1c-dash-enter`
(:3002, `ubuntu/open-webui/dash_adapter.py`, свой venv — `/home/webui` закрыт);
бэкенд: `1c-serene-lan-relay` (socket-proxyd 10.3.0.4:7890→127.0.0.1, ufw с
10.3.0.2, движок не тронут). Живое: probe `PostgreSQL 18.3 (SereneDB 26.07.3)`;
дашборд `/d/okna-sales` «Продажи okna» — 900 точек по `…реализациятмц_recordtype`;
cookie `gf_jwt` → 200/логин из токена, гость → 302/401. Ловушки: pyjwt[crypto]
(голый не умеет RS256); Caddy `handle`, НЕ `handle_path` (Grafana 13 ждёт
подпуть в запросе — иначе 301-петля). **Клик владельца для финального хопа:**
https://baulogistic.timpul.pro/dash/enter. Дальше: кнопка «добавить в
дашборд» (OWUI Action → API панелей).

🔴 **«позавчера» 503 / ложь all-time — код в git `[18.08]`**: d273e9d на бою
снимал окно → 8246 / 79 752 611,64 за всё время → TypeError после TOKENS →
503 (rid `2c934d58`). Окно держим (`period_window_empty`); ответ
`period_empty` (0 за 16.08), без общего итога. Оффлайн **30/30**
`test_period_empty`, measure_empty **26/26**, terminal **13/13**, gate **132**.
Выкат `:8091` — оркестратор; живой прогон — владелец.

🔴 **пустышка «Сумма» + compose `{count}` — код в git `[18.08]`**: опции меры
без всюду-0 (один `totals_of`); явный билет/слово → пивот, не refuse; compose
sum=0.0 на sum/rank не кладёт `{count}`. Оффлайн **26/26** `test_measure_empty.py`.
Числа в замках **по корпусу** (Всего 766 578,68 / 331). Выкат okna — оркестратор.

🔴 **«позавчера» не кратность/курс — код в git `[18.08]`**: пустой match больше
не кормит отбор случайными dated; пустая вилка не режется (cf6872f). После
выбора пустой день — hotfix выше, не recount. `period_preds` не меняли.

🔴 **корпус okna ≠ 1С по дням `[18.08]`**: витрина=RecordType=1С 77421,
17.08 **176 / 693 688,38**; корпус 331 / 766 578,68 — Period уехал на 19.08.
Такт 8+ ч на векторах (flock). Код: LineNumber в ключ регистра, /health дни.
Выкат + догон после flock — оркестратор. Отчёт `docs/CORPUS_VITRINE_OKNA_2026-08-18.md`.
md5 ask `3f14a685`. **Не писать search_corpus, пока pid 2823380 жив.**

🔴 **граница периода (п.13) — ЗАКРЫТ в git + okna `[18.08]`**: `period_preds`
~1230 — `doc_date < (to::date + INTERVAL 1 day)`, не `<=`; `outside_period` через
`NOT(period_preds)`. **8/8** `test_period_bounds.py`; okna `:8091` «вчера» → регистр
**331** / **766 578,68**; outside **77 050**; 16.08 — **0** строк. md5
**89671dc6…**. `/opt` okna выкатан 18.08.

🔴 **пустой период (в т.ч. «вчера»/assumed) — код в git `[18.08]`**: okna
`:8091` после 9cc11b02 всё ещё `figures`/refuse — `period_empty_outcome`
смотрел только `empty_period`, а «вчера» → `drop_assumed`. Починка:
count=0 + outside_period + окно не снято; diag `empty_after_period_action`.
**16/16** `test_period_empty.py`. Живой okna — повторный выкат md5 из коммита.

🔴 **терминальный второй круг (measure↔axis) — код в git `[18.08]`**: осцилляция
entity→measure→axis→measure закрыта (`_RESOLVED_CHOICES`, skip axis,
`measure_already_proven`); **13/13** `test_terminal_round.py`; md5 **9cc11b02…**
(общий с period_empty).

🔴 **stop1 sum / figures fallback — ЗАКРЫТ в git `[18.08]`**: `{count}` в sum-форме
11:54 UTC — после выбора источника сервис посчитал сумму 766 510,44, но compose
написал `{count}` в sum-форме; `_fill_figures`/гейт отвергли ответ и поток ушёл
в stalled. Причина найдена: `ANSWER_SYS` открывал глобальный каталог мест,
хотя `answer_slot_mode="sum"` его уже закрыл в `compose` и `compose_slot_values`.
Правка в git: системный промт разрешает только placeholders текущего блока
`COMPUTED`/`GROUPS`/`PAIRS`; оффлайн-замок `test_compose.py` проверяет и это,
и fallback `answer() -> kind=figures` при незаполнимом месте. Дыра 5ca1b66
(sum=0.0 → `{count}` в COMPUTED) закрыта в том же `compose`; замок —
`test_measure_empty.py`.

🔴 **уточнение → чипы WebUI — код ЗАКРЫТ `[18.08]`**: каждый вариант —
`N. {вопрос}: {подпись}? — {hint}` (`clarify_say`; OPTIONS моста — тот же
вопрос, `focus`=подпись). Выбор: номер / подпись / начало / строка-вопрос
(`resolve_focus`, `matchClarifyOption`). Плагин при `kind=clarify` без всех
OPTIONS → replace эталоном. Follow-up OWUI: Admin Tasks / `GET|POST
/api/v1/tasks/config[/update]` (`configure-branding.py`, тот же signin).
Генератор чипов — отдельный вызов модели, детерминизма нет; статические
suggestions не подходят. `/opt` и живой фронт не трогали — выкат + POST
брендинга оркестратору. Живой: «сколько продали вчера всего?» → оба пункта
и 79 752 611,64 / 79 925 955,81 — после выката.

Hotfix: выбор «1» в okna больше не отпускал замок; rewrite берёт выбор из inbound.text (message_received), поэтому decision_id уходит в params `ask_1c`.

🔴 **E4 онбординг коробки — код ЗАКРЫТ `[18.08]`**: `box_tune.sh` железо→conf
(формулы из ночи: small ≤16 GiB → threads=4, limit 1.5×RAM, swap ceil(RAM);
large → пул эмбеддера ≤96); Restart= 5/час у firstbuild/pipeline; форма
`EMBED_HOST` до такта; красный такт >15 мин → `1c-bot-monitor`/`tact_watch`.
Синтетика **60/60**. `/opt` и юниты okna/klient-1 не трогали. Живая повторная
установка — при следующем стенде.


🔴 **Полноту данных ведёт оркестратор** — [`docs/PLAN_ORCHESTRATOR.md`](../docs/PLAN_ORCHESTRATOR.md).
