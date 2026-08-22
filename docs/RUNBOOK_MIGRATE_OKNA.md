# RUNBOOK: перенос okna на новую коробку

Пошаговая инструкция переноса боевого контура **okna** со старого хоста Hetzner на LXD-контейнер
на `gpu-erw.timpul.pro`. Klient-1 переезжает **позже** — отдельным прогоном по §10.

Связанные: [`docs/PLAN_UPGRADE_NATIVE.md`](PLAN_UPGRADE_NATIVE.md) (решения владельца, фазы) ·
[`docs/UPGRADE_F1_REPORT.md`](UPGRADE_F1_REPORT.md) (ворота совместимости 26.07.3→26.08.1) ·
[`docs/RUNBOOK_DEPLOY.md`](RUNBOOK_DEPLOY.md) (раскладка с нуля) ·
[`docs/REGRESSION_BASE1.md`](REGRESSION_BASE1.md) (приёмка, проба okna).

---

## 0. Статус и дата

**Документ:** 2026-08-22. **Исполнитель ранбука:** оркестратор + владелец (переключение, сеть).

| Что | Статус |
|---|---|
| Доступ к новой коробке (SSH `:2202`, LXD `10.10.10.12`) | 🟢 **[замер 22.08]** |
| Одноразовый ключ миграции `/root/.ssh/id_ed25519_migrate` (old→new) | 🟢 добавлен в `authorized_keys` новой |
| Пользователи `serenedb`, `undebot`, группа `1c-secrets`, каталоги | 🟢 подготовлены на цели |
| Тарболл SereneDB **26.08.1** на цели (`/root/stage/serenedb-26.08.1-linux-amd64.tar.gz`, md5 `527e5ed2de1fe4fe098062bac503591d`) | 🟢 |
| **Проход 1** rsync `store.db` old→new (живьём, **110,8 МБ/с**, 27 206 889 472 байт за 3:54) | 🟢 **[замер 22.08]** |
| Tar-поток конфигов/юнитов/`/opt`/`/home/undebot` (без venv, транзиента) | 🟢 **[замер 22.08]** |
| Установка бинаря **26.08.1**, `serened.conf`, EXPORT/IMPORT store.db, `serenedb.service` `:7890` | 🟢 **[замер 22.08]** — см. §3.4 |
| vSwitch **4003** (Hetzner, эмбеддеры `10.3.1.11:8000` / `10.3.1.12:8002`) | 🟢 **[замер 22.08]** — см. §12 |
| Пересчёт эмбеддингов 4B на новой коробке | ⏳ **идёт** [замер 22.08]: labels 254 строки ~1 с |
| Приёмка (§7) и переключение (§8) | ⏳ **не выполнялись** — шаги ниже |
| Откат на старой коробке | 🟢 старая okna **не тронута**, работает до конца приёмки **[решение 22.08]** |

---

## 1. Инвентарь источника (167.233.249.110, Hetzner)

| Компонент | Факт на источнике | Куда на цели |
|---|---|---|
| **Железо** | 7 ГБ RAM, 4 vCPU, диск 150 ГБ | LXD: 125 ГБ RAM, 40 vCPU, ~400 ГБ свободно |
| **ОС / сеть** | eth0 `167.233.249.110/32`; enp7s0 `10.3.0.4/32` (частная сеть клиента) | `10.10.10.12/24`; шлюз эмбеддера `10.10.10.1:8000` |
| **SereneDB** | **26.07.3**, `/usr/local/bin/serened`, конфиг `/etc/serenedb/serened.conf`, данные `/var/lib/serenedb/engine_duckdb/store.db` **27 206 889 472** байт + `store.db.wal`, loopback `:7890`, юнит `serenedb.service` | **26.08.1** [решение 22.08]; тот же путь данных; `memory_limit` поднять (§2) |
| **Корпус** | `search_corpus` ~**1,23M** строк, dim **1024**, модель **Qwen3-Embedding-8B** | Пересчёт **4B** на цели (§5); IVF **не строить** [решение 22.08, F1: exact kNN 1740 ms ≈ IVF] |
| **`1c-serene-ask@postgres`** | бой `:8091` | тот же шаблон и порт |
| **`1c-mcp-ask@postgres`** | MCP-мост → ask | тот же |
| **`1c-packet-server`** | приёмник пакетов | тот же |
| **`1c-packet-apply.timer`** | apply каждые 2 мин | тот же |
| **`1c-serene-pipeline@postgres.timer`** | такт синк→сборка | тот же (остановить на время финального rsync) |
| **`1c-serene-lan-relay`** | socket+service: `:7890` → `10.3.0.4` (enp7s0) | ⚠ **открытый вопрос** — нужен ли relay на новой (§11) |
| **`1c-bot-monitor`** | service+timer | тот же |
| **`1c-serene-firstbuild@`**, **`1c-serene-onboard@`** | path-юниты | тот же |
| **OData-шлюз** | `python3` на `0.0.0.0:6090` | перенести; **как достаёт 1С клиента — белое пятно**, зафиксировать при переносе (§8) |
| **Бот** | пользователь `undebot`, `/home/undebot/.openclaw` (agents, identity, memory, `gateway.systemd.env`); транзиент: cache, logs, media, npm — **не копировать** | перенос конфигов; gateway `:18800` (loopback), `:18801` (0.0.0.0) |
| **`/opt/1c-mcp-reports`** | код ask, сборки | tar-поток + venv пересборка |
| **`/opt/1c-packet`** | пакетный транспорт | tar-поток |
| **`/opt/1c-bot-monitor`** | сторож | tar-поток |
| **`/opt/1c-open-webui`** | ~116 КБ | tar-поток |
| **`/opt/openclaw-mcp`** | ~222 МБ + venv | tar-поток без venv → пересборка |
| **`/opt/serenedb-dist`** | 26.07.3 | заменить на 26.08.1 |
| **`/etc/1c-*.env`** | восемь файлов + `1c-wiki-alias-postgres.env` | копировать как есть (секреты у владельца) |
| **`/etc/serenedb/serened.conf`** | под ~7 ГБ RAM | переписать под 125 ГБ (§2) |

---

## 2. Подготовка цели (10.10.10.12)

### 2.1 Уже сделано [замер 22.08]

- LXD-контейнер на `gpu-erw.timpul.pro` (`178.63.211.188`), Ubuntu 26.04 LTS, x86_64.
- Пользователи `serenedb`, `undebot`; группа `1c-secrets`; каталоги данных и `/opt`.
- SSH с dev: `ssh -p 2202 root@gpu-erw.timpul.pro` (klient-1 — `:2201`).
- Ключ миграции с источника: `/root/.ssh/id_ed25519_migrate` → `authorized_keys` цели.
- Сосед klient-1 `10.10.10.11` пингуется; эмбеддер хоста `10.10.10.1:8000` жив (GET → 405).

### 2.2 Установка SereneDB 26.08.1

**[решение 22.08]** Цель сразу на **26.08.1**. На **dev-копии** store.db прямое открытие доказано Ф1
(`docs/UPGRADE_F1_REPORT.md` §3); на **okna** rsync-копия **не открывается** 26.08.1 напрямую — см. §3.4
(канонический путь: EXPORT/IMPORT).

```bash
# на цели (root)
cd /root/stage
# md5 527e5ed2de1fe4fe098062bac503591d
tar xzf serenedb-26.08.1-linux-amd64.tar.gz
install -m 755 serenedb-26.08.1-linux-amd64/serened /usr/local/bin/serened
/usr/local/bin/serened --version   # ожидание: 26.08.1
```

Дубль тарболла: S3 `klient1-migration/engine/` (для klient-1 позже).

### 2.3 `serened.conf` и память

На источнике движок жил под **~7 ГБ RAM** (`memory_limit` ≈ 6,5 ГБ — `RUNBOOK_DEPLOY` §10.1).
На цели **125 ГБ RAM, 40 vCPU**.

🔴 **Параметр для подтверждения оркестратором:** `memory_limit = 40 GiB` (как песочница Ф1).
Допустимый диапазон по решению владельца: **32–48 ГБ**. После подтверждения — записать
фактическое значение в этот раздел и в `/etc/serenedb/serened.conf`.

```conf
# /etc/serenedb/serened.conf — okna NEW, черновик (подтвердить оркестратором)
--cpu_threads=96
--io_threads=8
--memory_limit=40GiB
```

После первого старта на импортированной базе:

```bash
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres -c "SHOW memory_limit; SELECT version();"
```

Права: каталог `/var/lib/serenedb` — `serenedb:serenedb`; конфиг — root, читаем `serenedb`.

### 2.4 Файрвол и доступ

| Откуда | Куда | Статус |
|---|---|---|
| dev `201.34.142.160` | `:2202` gpu-erw | 🟢 |
| старая okna `167.233.249.110` | `:2202` gpu-erw | 🟢 |
| klient-1 публичная `89.23.101.22` | `:2201`/`:2202` | ⏳ **не открыт** — вопрос владельцу (§11) |

---

## 3. Перенос store.db

**[решение 22.08]** S3 (`s3.twcstorage.ru`) для store.db **не подошло**: квота ~1 ГБ, 403 после ~0,6 ГБ.
Большие файлы — **напрямую rsync** old→new.

### 3.1 Проход 1 (живьём, без останова)

**[замер 22.08]** Скорость **110,8 МБ/с** (27 206 889 472 байт за 3:54). Выполнен с источника или с dev через ключ миграции.

```bash
# пример: с источника (root), ключ уже на цели
RSYNC_RSH="ssh -i /root/.ssh/id_ed25519_migrate -o StrictHostKeyChecking=accept-new"
rsync -avh --progress --partial \
  /var/lib/serenedb/engine_duckdb/store.db \
  /var/lib/serenedb/engine_duckdb/store.db.wal \
  root@10.10.10.12:/var/lib/serenedb/engine_duckdb/
chown -R serenedb:serenedb /var/lib/serenedb
```

### 3.2 Финальный дельта-прогон (окно останова)

⏳ **Не выполнялся.** Порядок:

1. На **источнике**: `systemctl stop serenedb.service` (и таймеры pipeline/apply — по согласованию).
2. Финальный rsync тех же файлов (секунды–минуты при ~27 ГБ и малом дельта).
3. На **цели**: `systemctl start serenedb.service`.
4. Источник **не включать** до решения об откате/переключении (§9).

### 3.3 Стена формата (прямое открытие rsync-копии)

**[замер 22.08]** После rsync **26.08.1 НЕ открыл** okna `store.db`:

```
FATAL: serialized data has 5 element(s), expected 4
```

Копия **цела**: **26.07.3** открывает её за **5 с** (`search_corpus` **1 230 156**).
На dev-файле (Ф1) формат чище — там **26.08.1** открыл напрямую (`docs/UPGRADE_F1_REPORT.md` §3).

🔴 **Вывод:** rsync переносит байты, но **не гарантирует** открытие на новой версии движка.
Канонический путь переноса store.db (okna, klient-1 и далее) — **EXPORT/IMPORT DATABASE** (§3.4).

### 3.4 EXPORT/IMPORT DATABASE — канонический путь

**Доки:** `sql/statements/export_and_import_database`.

На **источнике** (26.07.3, база открыта) или на **цели** после открытия копии 26.07.3:

```bash
# EXPORT (на машине, где store.db открывается)
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres \
  -c "EXPORT DATABASE '/tmp/okna-export' (FORMAT parquet, COMPRESSION zstd);"
# [замер 22.08 okna]: 27 ГБ → 2,4 ГБ, ~20 с
```

На **цели** (26.08.1, пустой или после DROP):

```bash
# ловушка 2 — schema public уже есть
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres \
  -c "DROP SCHEMA public CASCADE;"

# ловушка 1 — правка schema.sql ПЕРЕД import (см. ниже)

psql -h 127.0.0.1 -p 7890 -U postgres -d postgres \
  -c "IMPORT DATABASE '/tmp/okna-export';"
```

#### Ловушка 1: `syntax error at or near ")"` при IMPORT

**[замер 22.08]** Причина **НЕ в движке**: `schema.sql` экспорта содержит строки вида
`CREATE INDEX ... USING inverted ()` — **пустые скобки**. Так отдаёт `duckdb_indexes().sql`
(см. комментарий `ubuntu/serenedb/serene_search_build.py:55`).

**Лечение:** удалить **3 такие строки** из копии экспорта; индексы пересоздать нашими файлами
(`corpus_init.sql`, `entity_card_build.sql`).

Разбор опровергает вывод Ф1 «IMPORT сломан» — `docs/UPGRADE_F1_REPORT.md` §6 (дополнение 22.08).

#### Ловушка 2: `schema public already exists`

Перед `IMPORT DATABASE` выполнить `DROP SCHEMA public CASCADE;`.

#### Ловушка 3: IMPORT **не переносит** (доделать вручную)

| Что | Действие |
|---|---|
| **Роли** | `CREATE ROLE` заново; пароли — из мигрированных `/etc/1c-*.env` |
| **Текстовые словари** | `corpus_init.sql` с `-v dict_locale=ru_RU.utf8` (`build.sh:46,143`) |
| **Представления** `wiki_pages`, `wiki_entity_facts` | перенести `view_definition` с источника; **`wiki_pages` зависит от `wiki_entity_facts`** — порядок важен |
| **Пустые backing-таблицы индексов** | `DROP TABLE search_idx, alias_idx, entity_card_idx` перед `CREATE INDEX` |

#### Проверка после IMPORT + пересборки индексов

**[замер 22.08]** Итог проверен:

| Метрика | Значение |
|---|---|
| Таблицы | count'ы всех **418** таблиц **1-в-1** с источником |
| `search_idx` | **1 230 156** строк после `VACUUM (REFRESH_TABLE)` |
| `alias_idx` | **254** |
| `entity_card_idx` | **254** |
| wiki views | **254** / **351** |
| Движок | **26.08.1**, `serenedb.service`, `:7890` отвечает |

```bash
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres -c "SELECT version();"
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres -c "SELECT count(*) FROM search_corpus;"
```

Сверка с источником (до останова):

```bash
# на источнике
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres -c "SELECT count(*) FROM search_corpus;"
```

---

## 4. Конфиги, юниты, `/opt`; пересборка venv

### 4.1 Tar-поток old→new

**[замер 22.08]** Исключения: `venv/`, `__pycache__/`, `node_modules/`, `.git/`, транзиент
`.openclaw/{cache,logs,media,npm}`.

```bash
# на источнике → цель (пример одного потока)
ssh -i /root/.ssh/id_ed25519_migrate root@10.10.10.12 'mkdir -p /root/restore'
tar -C / --exclude='venv' --exclude='__pycache__' --exclude='node_modules' \
    --exclude='.git' \
    --exclude='home/undebot/.openclaw/cache' \
    --exclude='home/undebot/.openclaw/logs' \
    --exclude='home/undebot/.openclaw/media' \
    --exclude='home/undebot/.openclaw/npm' \
    -cf - etc/systemd/system/1c-*.service etc/systemd/system/1c-*.timer \
           etc/systemd/system/1c-*.socket etc/systemd/system/1c-*.path \
           etc/1c-*.env etc/serenedb/serened.conf \
           opt/1c-mcp-reports opt/1c-packet opt/1c-bot-monitor \
           opt/1c-open-webui opt/openclaw-mcp \
           home/undebot/.openclaw \
    | ssh -i /root/.ssh/id_ed25519_migrate root@10.10.10.12 'tar -C / -xf -'
```

После распаковки:

```bash
systemctl daemon-reload
# venv — пересборка (Ubuntu 26.04, python новее; старый venv ABI-несовместим)
cd /opt/openclaw-mcp && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# при необходимости — venv в /opt/1c-mcp-reports, если использовался
chown -R undebot:undebot /home/undebot/.openclaw
chmod 640 /etc/1c-*.env
chgrp 1c-secrets /etc/1c-*.env
```

### 4.2 Эмбеддер в env

**[решение 22.08]** Обновить `/etc/1c-embed.env` (и связанные) на **Qwen3-Embedding-4B**, dim=1024:

| Контекст | URL |
|---|---|
| снаружи | `http://178.63.211.188:8000/v1/embeddings`, резерв `http://49.13.97.101:8002/v1/embeddings` |
| из контейнеров okna/klient1 (LXD) | `http://10.10.10.1:8000/v1/embeddings` |
| **vSwitch 4003** (внутренняя облачная сеть, **[замер 22.08]**) | `http://10.3.1.11:8000`, резерв `http://10.3.1.12:8002` — `EMBED_HOSTS` на новой okna переключён |

Проверка формы (без секретов в командной строке — env-файл):

```bash
source /etc/1c-embed.env   # или load_env построчно, см. REGRESSION_BASE1
curl -sS "${EMBED_HOST%/}/health" | head
```

### 4.3 Юниты — порядок включения (после store.db + conf)

1. `serenedb.service`
2. `1c-serene-ask@postgres.service`, `1c-mcp-ask@postgres.service`
3. `1c-packet-server.service`, `1c-packet-apply.timer`
4. `1c-serene-pipeline@postgres.timer` — **после** пересчёта 4B или с остановленным embed-шагом
5. user-юнит `openclaw-gateway` (undebot)
6. `1c-bot-monitor.timer`

Таймеры pipeline/apply на время §3.2 и §5 — **stop/disable**, чтобы не писать в полуденную базу.

---

## 5. Пересчёт эмбеддингов 4B

**[решение 22.08]** Все векторы 8B/1024 на okna **заменяются** на 4B **на новой коробке**
(не на источнике). IVF для корпуса **не строить** (F1: exact 1740 ms на 1,23M).

### 5.1 Контрольные count до

```bash
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres <<'SQL'
SELECT count(*) AS corpus_rows FROM search_corpus;
SELECT count(*) AS emb_not_null FROM search_corpus WHERE emb IS NOT NULL;
SELECT count(*) FROM resolver_index WHERE emb IS NOT NULL;
SQL
```

Записать числа в журнал переноса (ожидание emb_not_null ≈ 1,23M — старые 8B).

### 5.2 Запуск пересчёта

```bash
cd /opt/1c-mcp-reports
# EMBED_RESET=1 обнуляет старые векторы целей перед записью
EMBED_RESET=1 EMBED_TARGETS="labels resolver card corpus" ./embed_all.sh 32
```

**[замер 22.08]** Пересчёт 4B на новой okna **идёт**; метки (**254** строки) — ~**1 с** по внутренней сети vSwitch.

Оценка времени **[замер F1, 22.08]**: на 26.08.1 `ai_embed` batch 256 ≈ **309 строк/с**.
При 1,23M строк корпуса + labels/resolver/card: **~1–2 ч** на одном эндпоинте; два эндпоинта
суммарно ~**220 строк/с** — **проверить замером** на цели (`journalctl`, счётчики скрипта).

### 5.3 Контрольные count после

```bash
psql -h 127.0.0.1 -p 7890 -U postgres -d postgres <<'SQL'
SELECT count(*) AS emb_not_null FROM search_corpus WHERE emb IS NOT NULL;
-- должно совпасть с corpus_rows; отметка модели на таблице — 4B (через embed_check / health ask)
SQL
```

`/health` ask-сервиса: `emb_ready=true`, модель = 4B (см. `docs/REGRESSION_BASE1.md`).

---

## 6. Контур бота (undebot + openclaw gateway)

| Параметр | Значение |
|---|---|
| Пользователь | `undebot` |
| Конфиг | `/home/undebot/.openclaw/` (agents, identity, memory, `gateway.systemd.env`) |
| Gateway | `127.0.0.1:18800`, `0.0.0.0:18801` (user systemd) |
| MCP | `openclaw-mcp` → `1c-mcp-ask@postgres` |

### 6.1 Перенос

- Tar-поток §4.1 (без cache/logs/media/npm).
- Venv `/opt/openclaw-mcp` — пересборка §4.1.
- Секреты Telegram/DeepSeek — в env-файлах у владельца (`gateway.systemd.env`, `/etc/…`).

### 6.2 Проверка (на цели, до переключения prod)

```bash
# gateway
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18800/health || true
ss -ltnp | grep -E '18800|18801'

# цепочка до ask
curl -sS -H "Authorization: Bearer $(grep ASK_TOKEN /etc/1c-serene-ask.env | cut -d= -f2)" \
  http://127.0.0.1:8091/health | head
```

⏳ Доставка в Telegram на новой коробке — только после §8 (куда смотрит webhook/polling).

---

## 7. Приёмка — ворота (go/no-go)

Все пункты — **на цели**, после §3–§5. Старая okna параллельно **остаётся эталоном отката**.

| # | Критерий | Команда / ожидание |
|---|---|---|
| 1 | Движок **26.08.1** | `SELECT version();` → содержит `26.08.1` |
| 2 | Корпус на месте | `SELECT count(*) FROM search_corpus;` = count на источнике до останова |
| 3 | Ask health | `curl :8091/health` → **200**, `emb_ready=true` после §5 |
| 4 | Воскресенье → число | live `/ask`: «почему в воскресенье продаж ноль…» → **answer**, sum=0 |
| 5 | Петли → no_data | «сколько петель осталось на складе?» → **no_data** |
| 6 | Склад → clarify | «сколько товара на складе?» → **clarify** с вариантами |
| 7 | Неделя → answer с именем | rank-вопрос про неделю → **answer** с именем лидера |
| 8 | Scorer ≥14/25 | после пересчёта 4B (ожидание по `PLAN_UPGRADE_NATIVE` Ф4) |

### 7.1 Scorer (эталон 25 вопросов)

```bash
# на цели; env — см. REGRESSION_BASE1 §«Золотой набор»
AB_CONTOUR=okna python3 /opt/1c-mcp-reports/ab_scorer.py \
  /opt/1c-mcp-reports/ab-gold-okna.tsv
# критерий: ≥14/25, 0 сбоев обращения — зафиксировать в журнале
```

### 7.2 Живая проба (8 вопросов, кандидат)

До выката на «бой» — `ab-probe-okna.tsv`, **0err/8** (`docs/REGRESSION_BASE1.md` §«Живая проба okna»):

```bash
AB_PROBE=okna AB_BASE=postgres ASK_LISTEN_PORT=8091 \
  python3 /opt/1c-mcp-reports/ab_scorer.py /opt/1c-mcp-reports/ab-probe-okna.tsv
```

---

## 8. Переключение (prod)

⏳ **Не выполнялось.** Каждый подпункт — действие владельца или замер.

| # | Вопрос | Действие |
|---|---|---|
| 1 | **Куда смотрит бот** | Обновить `ASK_URL` / MCP / конфиг openclaw: с old `:8091` на new `10.10.10.12:8091` (или localhost после переноса бота). Замер: один вопрос в Telegram. |
| 2 | **Telegram: webhook vs polling** | Выяснить текущий режим на старой okna (`gateway.systemd.env`, @BotFather). На `:18801` inbound webhook или long polling — **зафиксировать и повторить на цели**. |
| 3 | **Шлюз OData :6090 → 1С** | Белое пятно [замер 22.08]. При переносе: трассировать маршрут (WireGuard? reverse SSH? packet-only?). Записать схему в этот раздел. |
| 4 | **Частная сеть `10.3.0.4`** | На старой — `1c-serene-lan-relay` на enp7s0. На новой enp7s0 **нет** — нужен ли relay, VPN или только packet-transport? **Владелец** (§11). |
| 5 | **DNS / IP клиента** | Если клиент ходит на `167.233.249.110` — переключить A-запись или маршрут на новый публичный IP **после** §7. |
| 6 | **Packet mTLS** | Клиентские сертификаты и `1c-gate.timpul.ru` — убедиться, что apply на новой okna принимает пакеты (health packet-server). |

После переключения: повтор §7.1–7.2 на **prod-порту**, мониторинг `1c-bot-monitor`.

---

## 9. Откат

**[решение 22.08]** Старая коробка **167.233.249.110** не выключается и не перезаписывается до
конца приёмки на новой.

| Ситуация | Действие |
|---|---|
| Приёмка §7 не прошла | Оставить prod на старой; новую остановить (`serenedb`, ask, gateway); разбор без давления. |
| Переключили, но регресс | Вернуть DNS/бот на старую `:8091`; новую — stop. Финальный rsync **не** откатывает старую (она не менялась после останова). |
| Частичный перенос | Старая продолжает работать; новую можно уничтожить и начать §10 заново. |

---

## 10. Чек-лист «новое подключение с нуля» (универсальность, п.12 TARGET.md)

Подстановка только env/имён; порядок тот же для **klient-1** и следующих бизнесов.

| Шаг | Действие | Переменные |
|---|---|---|
| 1 | LXD/VM, пользователи `serenedb`, `undebot`, `1c-secrets` | `<HOST>`, `<SSH_PORT>` |
| 2 | SereneDB **26.08.1** из stage/S3 | md5 тарболла в журнале |
| 3 | `serened.conf`: `memory_limit`, `cpu_threads` по RAM/vCPU | `box_tune.sh` или таблица §2.3 |
| 4 | rsync `store.db` (+ wal) → **EXPORT/IMPORT** на цели (§3.4) **или** firstbuild с нуля | `<SRC_HOST>`, `<MIGRATE_KEY>` |
| 5 | tar-поток `/etc/1c-*`, юниты, `/opt`, `.openclaw` (без venv/транзиента) | `<BUSINESS>` |
| 6 | Пересборка venv, `daemon-reload` | — |
| 7 | `/etc/1c-embed.env` → 4B, `10.10.10.1:8000` из контейнера | `EMBED_HOST` |
| 8 | `EMBED_RESET=1 EMBED_TARGETS="labels resolver card corpus" ./embed_all.sh` | `<DBNAME>` |
| 9 | Старт `serenedb` → `1c-serene-ask@<DB>` → `1c-mcp-ask@<DB>` → packet → pipeline timer | порты из env |
| 10 | Приёмка: version, count, `/health`, probe 8, scorer ≥ порога | `AB_CONTOUR`, `ab-gold-*.tsv` |
| 11 | Переключение бота + сеть + OData/packet | владелец |
| 12 | Удалить одноразовый ключ миграции **с обеих** сторон | §11 п.4 |

**Klient-1 отличия (запланировано):** store.db ~60 ГБ, корпус ~15M строк; файрвол для
`89.23.101.22`; SSH `:2201`; IP `10.10.10.11`; время embed — часы, не минуты.

---

## 11. Открытые вопросы (ответ — владелец)

| # | Вопрос | Зачем |
|---|---|---|
| 1 | Файрвол gpu-erw для **89.23.101.22 → :2201/:2202** | миграция klient-1, доступ с его публичной точки |
| 2 | **10.3.0.4 / lan-relay** на новой okna | нужен ли клиентский private LAN или достаточно packet+mTLS |
| 3 | **Webhook Telegram** на `:18801` vs polling | переключение без простоя бота |
| 4 | **Окно останова** для финального delta-rsync | согласовать с клиентом (минуты serened down на источнике) |
| 5 | **`memory_limit` финальное** (32 / 40 / 48 GiB) | подтвердить оркестратором после первых тактов |
| 6 | **OData :6090** — как достаёт 1С | закрыть белое пятно при переносе |
| 7 | Удаление **`id_ed25519_migrate`** после успеха | безопасность; чек-лист §10 п.12 |

---

## Приложение: адреса и ключи (без секретов)

| Роль | Адрес |
|---|---|
| Старая okna (источник) | `167.233.249.110`, SSH root + deploy-ключ с dev |
| Новая okna (цель) | `10.10.10.12`, снаружи `ssh -p 2202 root@gpu-erw.timpul.pro` |
| Хост эмбеддера | `178.63.211.188`, внутри LXD `10.10.10.1:8000` |
| Сосед klient-1 | `10.10.10.11`, SSH `:2201` |
| S3 (мелкие артефакты) | `s3.twcstorage.ru`, bucket `klient1-migration` (~365 МБ); **store.db непригоден** — квота ~1 ГБ, 403 QuotaExceeded |
| vSwitch шлюз | `10.3.1.1` (ICMP не отвечает — норма) |
| Эмбеддеры vSwitch | `10.3.1.11:8000` (gpu-1c), `10.3.1.12:8002` (gpu-qwen27b) |

Секреты — только в `/etc/1c-*.env`, `/home/undebot/.openclaw/gateway.systemd.env`; у владельца.
Одноразовый ключ миграции `/root/.ssh/id_ed25519_migrate` — **удалить после всех миграций** (§10 п.12).

---

## 12. vSwitch 4003 (Hetzner) — внутренняя сеть к эмбеддерам

**[замер 22.08]** Контейнеры LXD (`10.10.10.0/24`) видят облачную сеть **без доп. NAT**
(контейнер okna → `10.3.0.4`, **3,3 мс**).

### 12.1 Robot / Hetzner Cloud

1. vSwitch **4003**: подсеть **`10.3.1.0/24`** в network-1 с галочкой **«dedicated server vSwitch connection»**.
2. Членство серверов — **Robot → vSwitch → Add servers** (без этого кадры уходят в никуда: ARP без ответа, **RX=0**).

### 12.2 На хостах (gpu-1c `178.63.211.188`, gpu-qwen27b)

```bash
ip link add link eno1 name eno1.4003 type vlan id 4003
ip link set eno1.4003 mtu 1400 up
# gpu-1c:
ip addr add 10.3.1.11/24 dev eno1.4003
# gpu-qwen27b:
ip addr add 10.3.1.12/24 dev eno1.4003
ip route add 10.3.0.0/16 via 10.3.1.1
```

Персист: `/etc/netplan/02-vswitch.yaml` (`vlans:`).

Шлюз **`10.3.1.1`** на ICMP **не отвечает** — это норма, трафик через него идёт.

### 12.3 Эмбеддеры

| Хост | Внутренний URL |
|---|---|
| gpu-1c (RTX 6000 Ada, 125 ГБ RAM / 40 vCPU) | `http://10.3.1.11:8000` |
| gpu-qwen27b | `http://10.3.1.12:8002` |

SSH к хостам: `ssh -p 2202 root@gpu-erw.timpul.pro` (контейнер okna `10.10.10.12`).

### 12.4 Туннели владельца (RU ↔ EU, справочно)

**[замер 22.08]** `89.23.101.22` ↔ `2.28.54.129` (pro-router): WireGuard UDP **51820** ~**44 мс**,
~**192/240 Mbps** (рекомендован); ssh-tun — запасной.
