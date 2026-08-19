# Active Context

_Обновлено: **2026-08-18.** Здесь — только живое: текущее состояние и «С ЧЕГО НАЧАТЬ».
История по дням — в [`progress.md`](progress.md); стадии по контракту — в
[`docs/TARGET_STATUS.md`](../docs/TARGET_STATUS.md)._

---

# ⏭ С ЧЕГО НАЧАТЬ СЛЕДУЮЩУЮ СЕССИЮ

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

🔴 **rank gate bad float + регистр из табчастей — код в git `[19.08]`**:
(в) живой 503 после cd1789b — `gate()` возвращал float в `bad_nums`, шаг()
резал `bad[0][:60]` → TypeError; fix + rank whitelist leader/count. (б)
`prefer_entity_for_rank` поднимает регистр по `written_by` (rid `7337254b`).
Оффлайн **29/29** + F-замки. md5 ask **`ea718df0`**. Выкат `:8091` — оркестратор.

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
