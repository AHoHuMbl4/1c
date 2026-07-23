# Что ставим на Ubuntu (LXC lxc-claude-1c): разбор braine

> Разбор стека braine (мозг горячего контура). Развёрнут на LXC; интеграция с 1С —
> через OData-канал и ETL (`../ubuntu/1c-etl/`), а не через execute_query, как
> предполагалось в исходном разборе. Общая картина — [`ARCHITECTURE.md`](ARCHITECTURE.md).

_Изучение репо https://github.com/AHoHuMbl4/braine (main, v2.1.1) — 2026-07-22, 5 агентов (4 читателя по зонам + критик полноты). Репо read-only, «только как пример» — правило владельца._

## 1. Что это

**smart-bot** — Telegram-бот + HTTP API с «нулевой галлюцинацией»: отвечает строго по одному git-репозиторию документации («KB-репо»). Точность гарантируют не промты, а детерминированные гейты в коде: пороги retrieval → построчная сверка каждого числа/даты/IP с фрагментами корпуса → обязательные цитаты; лестница деградации «ответ → уточни → цитаты → нет данных». Есть SQL-скилл (md-таблицы репо → Postgres, агрегаты считает SELECT'ом код) и «машина времени» (ответы о прошлом по git-истории). Клонируемый шаблон: перенос = свой `.env` + свой golden set.

**Синергия с нашим планом «второго мозга» (docs/PLAN.md):** идеальная. Наш холодный контур выгружает данные 1С в git-репо как md-файлы и md-таблицы → braine их индексирует, отвечает с цитатами, агрегаты считает SQL'ем. Braine = готовый «горячий контур» + бот-интерфейс; нам остаётся ETL 1С → KB-репо.

## 2. Стек на Ubuntu 24.04 (наш LXC подходит: 6 CPU / 62 GB / 238 GB, референс braine — точно такой же непривилегированный LXC)

Всё **нативно через systemd, БЕЗ Docker** (решение D-005: в непривилегированном LXC Docker падает на keyring-квоте — у нас будет то же самое). GPU не нужен.

| Устанавливается | Как | Сервис (порт) |
|---|---|---|
| PostgreSQL 16 + pgvector | apt: `postgresql-16`, `postgresql-16-pgvector`; роль `smartbot`, БД `openwebui`+`mem0`, `CREATE EXTENSION vector` | `postgresql` (127.0.0.1:5432) |
| Эмбеддер | **Qwen `text-embedding-v4` (DashScope intl, engine `openai`), размерность `1536`** — ставится `bootstrap.sh` через API OWUI (D-006). Реально в проде именно он (проверено: `document_chunk.vector = vector(1536)`). Локальных эмбеддеров НЕТ. ⚠️ В `.env` есть неиспользуемые дефолты OWUI `RAG_EMBEDDING_ENGINE=ollama`/`RAG_EMBEDDING_MODEL=bge-m3` — **bootstrap их ПЕРЕКРЫВАЕТ** (в рантайме OWUI берёт свою БД-конфигурацию = text-embedding-v4), на работу не влияют. Каветат: fallback-эмбеддера нет — при недоступности DashScope индексация/поиск стоят | — |
| Open WebUI | pip venv `/opt/owui-venv` + вручную `psycopg2-binary`, `pgvector` (иначе не стартует) | `open-webui` (0.0.0.0:3000) |
| oikb (синк git→KB) | pip venv `/opt/oikb-venv` + sed-патч таймаута 120→600с | `oikb` (8081) |
| rerank-shim | stdlib-скрипт из репо (адаптер OWUI↔DashScope qwen3-rerank) | `rerank-shim` (127.0.0.1:8082) |
| Мост (бот+API) | pip venv `/opt/bridge-venv` (aiogram 3, FastAPI, asyncpg, pymorphy3…) | `tg-bridge` (без порта, long polling), `api` (0.0.0.0:8090) |
| Поллер свежести | скрипт из репо, SHA коммита KB-репо каждые 30с | `kb-poll` |
| Таймеры | ночной golden-регресс 03:40 с телеграм-алертом; синк Google-таблиц раз в 5 мин | `nightly-eval.timer`, `gsheets-sync.timer` |

Код кладётся в `/opt/smart-bot` (путь зашит в юниты). Установка turnkey: заполнить `.env` → `export POSTGRES_PASSWORD=…` → `bash deploy/install.sh` → `bash deploy/bootstrap.sh`.

**Внешние API (egress с LXC):** `api.deepseek.com` (генерация; ключ есть), `dashscope-intl.aliyuncs.com` (эмбеддинги text-embedding-v4 + реранк qwen3-rerank; ключ Alibaba есть — проверить, что он именно DashScope **intl**), `api.telegram.org`, GitLab владельца, разово PyPI. Входящие порты не нужны (Telegram — long polling, свежесть — исходящий поллер).

## 3. Грабли, найденные изучением (сверх документации braine)

1. **Пины версий: docs заявляют «Open WebUI v0.10.2 (pinned), oikb 0.3.6», а `install.sh` ставит `pip install open-webui` БЕЗ пина** — latest. Вся калибровка гейтов (`SCORE_MODE=similarity`, пороги 0.25/0.15) замерена на 0.10.2, retrieval-API при апгрейде может сломаться (D-002 хранит fallback на этот случай). **Решение: при установке пиновать `open-webui==0.10.2` и `oikb==0.3.6`.**
2. **Реального `.env` в репо НЕТ** (в `.gitignore`), несмотря на нарратив «коммитим сознательно». Все ~13 проектных значений собираем с владельцем заранее (см. §4).
3. Ветка KB-репо «main» захардкожена в 5 местах — наш KB-репо должен жить на `main`.
4. `.env`-дефолты кода — docker-эры (`http://open-webui:8080`) — обязательно переопределять на `127.0.0.1` (шаблонный `.env.example` это делает).
5. Юниты работают под root (User= нет нигде) — для первой итерации оставляем как в оригинале, ужесточим после.
6. Бэкапов по расписанию в braine НЕТ (только ручной `pg_dumpall` в `/root/backups`) — **добавим свой таймер** (наше правило: бэкапы всегда).
7. `gsheets.yaml` пуст — таймер будет молотить вхолостую; замаскируем, пока таблицы не нужны.
8. БД `mem0` создаётся install.sh, но кодом не используется (задел) — создаём, безвредно.
9. Секрет-политика v2.1.1 в коде реально закрывает и quotes-путь (страхи OPERATIONS.md устарели) — но наш KB с данными 1С всё равно считаем чувствительным: доступ только allowlist.
10. Golden set/probe/router-тесты захардкожены под KB владельца — под 1С-базу пишем свои (иначе nightly-eval будет слать FAIL-алерты с первой ночи).
11. Open WebUI :3000 и API :8090 слушают 0.0.0.0 — закрыть файрволом до VPN/локалки (у braine это тоже правило: «токен не заменяет сетевую защиту»).

## 4. Что нужно от владельца до развёртывания

**Секреты/значения `.env`:** GITLAB_URL + read-token KB-репо + project id; TELEGRAM_BOT_TOKEN (новый бот или существующий?) + telegram-id владельца; DEEPSEEK_API_KEY (есть), ALIBABA_API_KEY (есть — проверим, что DashScope intl); остальное (POSTGRES_PASSWORD, WEBUI_SECRET_KEY, OIKB_API_KEY, API_TOKEN, админ OWUI) сгенерим при установке.

**Решения:**
1. **Какой KB-репо индексировать?** Для 1С-мозга логично завести отдельный репо под выгрузки (например `1c-kb`), куда наш ETL будет писать md/таблицы. ⚠ oikb работает с **GitLab** — наш проект живёт на GitHub. Варианты: (а) KB-репо на GitLab владельца (gitlab-real.unde.life — уже есть, braine с ним работает), (б) проверить GitHub-поддержку oikb. Рекомендую (а) — проверенный путь.
2. Egress с LXC: DeepSeek + DashScope + Telegram + GitLab — ок? (данные 1С поедут в облачные LLM — это решение §6 плана).
3. Пиновать 0.10.2/0.3.6 — предлагаю да (иначе перекалибровка).

## 5. Порядок развёртывания (когда владелец даст добро)

1. Владелец: ответы на §4 + KB-репо создан.
2. Клон braine на LXC в `/opt/smart-bot` (read-only использование шаблона; наши правки — только `.env`, golden set, `EXPAND_PROMPT`-пример, exclude в `.oikb.yaml` — по PORTING.md).
3. `.env` по карте PORTING.md (с пинами из §3.1), `install.sh` + `bootstrap.sh`.
4. Наши дополнения: бэкап-таймер pg_dumpall, маскировка gsheets-sync, firewall на :3000/:8090.
5. Канарейка свежести (маркер-файл в KB → вопрос боту → удалить → «нет данных»).
6. Golden set под 1С-домен, `nightly-eval` зелёный.
7. Стыковка с 1С-контуром: ETL из фазы 4 плана пишет в KB-репо.

## Ссылки

- Репо: https://github.com/AHoHuMbl4/braine (main) — README, docs/PORTING.md (карта .env, грабли 1-14), docs/ARCHITECTURE.md, deploy/install.sh + bootstrap.sh, memory_bank/decisions/D-001…D-006.
- Наш план: `docs/PLAN.md` (§2 контуры, §6 LLM-приватность).
