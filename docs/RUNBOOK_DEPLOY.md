# RUNBOOK: развёртывание «второго мозга» на 1С с нуля

Пошаговая воспроизводимая инструкция для раскатки на новом проекте — **сквозной стек от 1С на Windows до всей системы на Ubuntu**. Проверено end-to-end на стенде 2026-07-22..24 (Windows 11, платформа 8.3.27.1786 x86, Бухгалтерия 3.0.190.11 → OData/IIS → Ubuntu LXC: braine RAG + SereneDB-аналитика → OpenClaw-бот отвечает по данным 1С фактами и отчётами). Эталон для клонирования — держать актуальным.

**Порядок разделов = порядок раскатки:** §1-6 Windows/1С/OData/read-only → §7-8 braine (факты) → §9 zero-touch/карта сервисов → §10 SereneDB (аналитика/отчёты) → §11 OpenClaw (бот-слой + гейт). Каждый слой ставится ПОВЕРХ предыдущего.

Связанные: `docs/ARCHITECTURE.md` (устройство целиком) · `docs/UBUNTU_SETUP.md` (стек braine) · `docs/SERENEDB.md` (аналитика) · `docs/OPENCLAW_BOT.md` (бот-слой) · `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md` (почему НЕ встроенный тулкит) · `ubuntu/1c-gateway/` (OData-шлюз) · `ubuntu/1c-etl/` (ETL).

---

## 0. Архитектура (прод — соединение по IP, канал = OData на IIS)

```
Windows (1С):  файловая база ─► IIS (служба) ─► штатный OData 1С (read-only user ai_reader)
                                   ▲ авто-старт, многопоточно, без idle-обработчика/модалок
Роутер 192.168.56.1:  проброс :6003 ─► Windows-IIS:80
Ubuntu LXC (наш, всё loopback):
  OData-шлюз :6011 (только GET) ─┬─► ETL(ночь) ─► KB-репо(GitLab) ─► oikb/OWUI ─► braine /ask :8090   [факты, RAG]
                                 └─► serene_sync(ночь) ─► витрина SereneDB :7890                        [аналитика, OLAP+вектор]
  OpenClaw-бот :18800 (юзер undebot) ─┬─ ask_1c    (MCP :6014) ─► braine /ask
     Telegram ◄─── тон, DeepSeek      └─ report_1c (MCP :6015) ─► SereneDB (ro-роль + резолвер + график)
     → verify-плагин (ГЕЙТ КОДОМ: числа сверяет, внутреннее режет) → ответ клиенту
```

**Полная карта сервисов LXC `.42` (всё loopback; ground-truth, `enabled` = переживает ребут):**

| Порт | Unit / таймер | Процесс | Юзер | Слой |
|---|---|---|---|---|
| — | `1c-odata-gateway` :6011 | `odata_gateway.py` | root | канал: только GET к 1С-OData (upstream `192.168.56.1:6003`) |
| `0.0.0.0:6012` | `1c-config-ui` | `oc_config_ui.py` | root | веб-галочки «что тянуть» (ETL) |
| — | `1c-etl.timer` 03:00 | `oc_etl.py` | root | ночь: 1С → md-таблицы → KB-репо (braine) |
| `127.0.0.1:5432` | `postgresql` | postgres | postgres | pgvector braine (OWUI) |
| `0.0.0.0:3000` | `open-webui` | — | root | индекс/retrieval braine |
| `0.0.0.0:8081` | `oikb` | — | root | синк KB-репо → OWUI |
| `127.0.0.1:8082` | `rerank-shim` | — | root | реранкер qwen3 |
| `0.0.0.0:8090` | `api` (braine) | — | root | `POST /ask` (RAG-ответ с цитатами) |
| `127.0.0.1:7890` | `serenedb` | `serened` | **serenedb** | витрина аналитики (Postgres-протокол) |
| `127.0.0.1:6015` | `1c-mcp-reports` | `mcp_reports.py` | root | MCP `report_1c` (NL→SQL + график) |
| — | `1c-serene-sync.timer` 03:40 | `serene_sync.py` | root | ночь: витрина + резолвер (после ETL) |
| `127.0.0.1:6014` | `1c-mcp-braine` | `mcp_braine.py` | root | MCP `ask_1c` над braine |
| `127.0.0.1:18800` | `openclaw-gateway` (**user**-юнит) | `node …/openclaw` | **undebot** | бот: Telegram + DeepSeek-тон + verify-гейт |
| — | `1c-bot-monitor.timer` +2min | `bot_health_check.sh` | root | алерт владельцу в Telegram при падении |

- **Инвариант:** в 1С только читаем. Гарантия read-only — двумя слоями (§6): пользователь `ai_reader` (нет прав записи) + шлюз (режет не-GET). Не на настройках приложения.
- **Почему OData, а не встроенный сервер MCP-тулкита:** тулкит обслуживает HTTP через клиентский idle-обработчик 1С — ~1 req/s и встаёт на любом модальном окне сессии (`docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`). OData обслуживает IIS (служба Windows): многопоточно, авто-старт, переживает ребут, модалок в веб-сессии нет. Тулкит остаётся как **dev-опция** (§Приложение).
- Два контура: холодный (ночная выгрузка ETL/синк → KB+витрина) + горячий (бот отвечает по индексу/витрине). `docs/ARCHITECTURE.md §3`.

---

## 1. Предусловия (собрать заранее)

| Что | Где | Куда |
|---|---|---|
| Дистрибутив платформы 1С 8.3.25+ (Windows) | releases.1c.ru / developer.1c.ru | `C:\1c\distr\` |
| Комьюнити-лицензия разработчика (бесплатно) | developer.1c.ru → «Комьюнити-лицензии» | активация в GUI при 1-м запуске |
| Тестовая/клиентская база (.dt или .cf) | клиент / демо | `C:\1c\distr\` |
| KB-репо на GitLab + read/write-токен | self-host GitLab | project id + token |
| Telegram-бот + свой telegram-id | @BotFather | `credentials/` |
| Ключи DeepSeek + Alibaba DashScope intl | platform.deepseek.com / Model Studio | `credentials/` |

---

## 2. Windows-стенд: раскладка и доступ

```powershell
New-Item -ItemType Directory -Force -Path C:\1c\bases,C:\1c\backups,C:\1c\distr,C:\1c\logs,C:\1c\repo
git config --global user.name "<имя>"; git config --global user.email "<mail>"
git clone <repo> C:\1c\repo
```
SSH-ключ Claude — в `C:\ProgramData\ssh\administrators_authorized_keys` (для admin-пользователя), НЕ в `%USERPROFILE%`.

### ⚠ Готчи автоматизации по SSH (сэкономят часы)
- Длинные PowerShell по SSH — только `powershell -EncodedCommand` (base64 UTF-16LE) ИЛИ `scp` файла + `-File`. Экранирование bash→cmd ломает `$`/кавычки/кириллицу; лимит cmd ~8191 символов.
- `.ps1` с кириллицей — UTF-8 **с BOM** (PS 5.1 без BOM = ANSI → синтакс-ошибки).
- COM-коннектор: `regsvr32 comcntr.dll` запускать **из каталога bin** платформы; класс `V83.COMConnector`; вызывать из **32-битного** PowerShell (`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`) под x86-платформу.
- COM-квирк: свойства (`Metadata`) через PowerShell отдаются только рефлексией (`InvokeMember GetProperty`); **методы коллекций метаданных не резолвятся** (`Найти`/`Count`) — но **`foreach` по коллекции (COM-энумератор) работает** (см. §5 состав OData). Прямые вызовы методов объектов (`$ib.NewObject`, `$arr.Добавить`) — работают.

---

## 3. Установка платформы (тихо, headless)

```powershell
Start-Process "<distr>\vc_redist.x86.exe" -Args '/install','/quiet','/norestart' -Wait
Start-Process msiexec.exe -Wait -Args @(
  '/i','"<distr>\1CEnterprise 8.msi"','/qn','/norestart','TRANSFORMS=1049.mst',
  'DESIGNERALLCLIENTS=1','THICKCLIENT=1','THINCLIENT=1','THINCLIENTFILE=1',
  'WEBSERVEREXT=1',                 # веб-модуль wsisapi.dll — ОБЯЗАТЕЛЬНО для OData/IIS
  'LANGUAGES=RU','/l*v','C:\1c\logs\install_1c.log')
```
⚠ **Лицензия нужна даже тестовой сборке** (`CREATEINFOBASE` работает без, конфигуратор/предприятие — нет). Активировать комьюнити-лицензию в GUI при первом запуске.

---

## 4. Развёртывание базы

```powershell
$exe='C:\Program Files (x86)\1cv8\<версия>\bin\1cv8.exe'
Start-Process $exe -Wait -Args 'CREATEINFOBASE File="C:\1c\bases\<база>" /DisableStartupDialogs'
Start-Process $exe -Wait -Args 'DESIGNER /F"C:\1c\bases\<база>" /RestoreIB "<distr>\<база>.dt" /Out C:\1c\logs\restore.log /DisableStartupDialogs'
```
Первый интерактивный вход: «база восстановлена из копии» → **«Это копия информационной базы»** (внешние операции остаются заблокированы). Помощник → вид организации «Юридическое лицо».

**Пользователи (BSP, порядок ВАЖЕН):** Администрирование → Настройки пользователей и прав → Пользователи.
1. Сначала **admin** (полные права) — иначе после создания первого юзера потеряешь админ-доступ.
2. Затем **ai_reader** — профиль **«Только просмотр»** (read-only ко всем данным). Запомнить пароли.

**Бэкап (правило проекта, перед любым изменением базы):** `powershell -File C:\1c\repo\windows\scripts\backup-1c.ps1 -BasePath C:\1c\bases\<база>` → zip в `C:\1c\backups` (ротация 14).

---

## 5. Прод-канал: OData на IIS (headless)

### 5.1 Включить IIS (нужен один ребут)
```powershell
Enable-WindowsOptionalFeature -Online -All -NoRestart -FeatureName `
  IIS-WebServerRole,IIS-WebServer,IIS-CommonHttpFeatures,IIS-StaticContent,IIS-DefaultDocument,`
  IIS-HttpErrors,IIS-RequestFiltering,IIS-Security,IIS-ISAPIExtensions,IIS-ISAPIFilter,IIS-CGI,`
  IIS-ManagementConsole,IIS-BasicAuthentication
# фичи встают в EnablePending → ПЕРЕЗАГРУЗИТЬ Windows (разовый шаг настройки).
# После ребута: служба W3SVC = Running / Automatic (авто-старт).
```

### 5.2 Опубликовать базу и включить OData
```powershell
$webinst='C:\Program Files (x86)\1cv8\<версия>\bin\webinst.exe'
& $webinst -publish -iis -wsdir 1c -dir C:\inetpub\1c -connstr "File='C:\1c\bases\<база>';"
# в C:\inetpub\1c\default.vrd переключить <standardOdata enable="false"  →  enable="true"
# права пула IIS на файловую базу (нужна запись для сессий/блокировок):
icacls 'C:\1c\bases\<база>' /grant 'IIS APPPOOL\DefaultAppPool:(OI)(CI)M' /T
icacls 'C:\1c\bases\<база>' /grant 'IUSR:(OI)(CI)M' /T
# для x86-платформы — 32-битный пул:
Import-Module WebAdministration; Set-ItemProperty 'IIS:\AppPools\DefaultAppPool' enable32BitAppOnWin64 $true
iisreset /restart
```
Эндпоинт: `http://<host>/1c/odata/standard.odata/` (первый запрос прогревается; дальше мгновенно). Без auth → 401.

### 5.3 Задать состав OData (какие объекты отдавать) — COM под админом
Через COM (32-бит PowerShell), **перебором коллекций** (методы `Найти`/`Count` не резолвятся, а `foreach` — да):
```powershell
$GP=[Reflection.BindingFlags]::GetProperty
function P($o,$n){ [__ComObject].InvokeMember($n,$GP,$null,$o,$null) }
$ib=(New-Object -ComObject 'V83.COMConnector').Connect('File="C:\1c\bases\<база>";Usr="admin";Pwd="<admin-pass>";')
$md=P $ib 'Metadata'; $arr=$ib.NewObject('Array')
foreach($coll in @('Справочники','Документы')){ foreach($o in (P $md $coll)){ $arr.Добавить($o) } }
$ib.УстановитьСоставСтандартногоИнтерфейсаOData($arr)   # выставит все справочники+документы
```
(На проде состав можно сузить до нужных разделов ERP.)

---

## 6. 🔒 Read-only — два слоя (проверено)

**Слой 1 — пользователь `ai_reader`** (OData Basic auth под ним): читает (200), пишет → отказ прав. Основная гарантия.
**Слой 2 — наш OData-шлюз** (`ubuntu/1c-gateway/odata_gateway.py`, :6011): пропускает только GET; POST/PATCH/PUT/DELETE → **405, до 1С не доходят**.

### Роутер `.1`: проброс на IIS
На роутере/шлюзе сети LXC пробросить порт на **Windows-IIS:80** (напр. `192.168.56.1:6003 → <win-ip>:80`). Тогда LXC ходит `192.168.56.1:<порт>/1c/odata/standard.odata/…`.

### Развернуть OData-шлюз (LXC)
```bash
install -D odata_gateway.py /opt/1c-odata-gateway/odata_gateway.py
cat > /etc/1c-odata-gateway.env <<EOF
ODG_USER=ai_reader
ODG_PASS=<пароль ai_reader>
ODG_UPSTREAM=http://192.168.56.1:6003/1c/odata/standard.odata
EOF
chmod 600 /etc/1c-odata-gateway.env
cp systemd/1c-odata-gateway.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now 1c-odata-gateway
```

### Проверки безопасности (ворота, проверено на стенде с LXC)
1. `GET Catalog_Валюты/$count` через шлюз → данные ✅.
2. `POST/PATCH/PUT/DELETE` через шлюз → **405** (не доходят до 1С) ✅.
3. Прямая запись под `ai_reader` (мимо шлюза) → отказ прав (HTTP 500) ✅.
4. Итоговое правило клиента: ходить только через шлюз, только GET.

---

## 7. Стек braine (LXC) — `docs/UBUNTU_SETUP.md`
Клон braine в `/opt/smart-bot`; `.env` из `credentials/` (KB-репо, бот, ключи, сгенерированные секреты); `install.sh` пропатчить (пины `open-webui==0.10.2`/`oikb==0.3.6`); `bootstrap.sh` (админ OWUI, KB, **эмбеддер Qwen `text-embedding-v4` @ 1536 через DashScope**, реранкер qwen3-rerank-шим). Сервисы: postgresql, open-webui(:3000), oikb(:8081), rerank-shim(:8082), tg-bridge, api(:8090), kb-poll. Пустой `gsheets-sync.timer` — замаскировать, если Google Sheets не нужны.

---

## 8. Холодный контур: ETL 1С → KB — `ubuntu/1c-etl/`
Читает через OData-шлюз (:6011, GET), пишет md-таблицы в KB-репо (GitLab), пушит → oikb/kb-poll индексируют.
```bash
install -D oc_etl.py /opt/1c-etl/oc_etl.py
cat > /etc/1c-etl.env <<EOF
ETL_ODATA_BASE=http://127.0.0.1:6011
ETL_KB_REPO=http://root:<glpat>@<gitlab>/<group>/<kb-repo>.git
ETL_KB_DIR=/opt/1c-etl/kb
ETL_KB_SUBDIR=1c
EOF
chmod 600 /etc/1c-etl.env
cp systemd/1c-etl.{service,timer} /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now 1c-etl.timer   # ночь 03:00
systemctl start 1c-etl.service                                   # первый прогон
```
Список сущностей — `oc_etl.py: ENTITIES` (на проде расширить). Пишет `1c/catalogs/*.md`, `1c/documents/*.md`, `1c/_index.md`.

---

## 9. Zero-touch: что переживает ребут
Полная карта портов/юзеров — в §0. Всё `enabled`; после ребута любой машины стек поднимается сам.
- **Windows:** IIS (W3SVC) = Automatic; публикация/состав OData/пользователи — персистентны. После ребута OData сам доступен.
- **LXC — system-сервисы (`enabled`):** postgresql, open-webui, oikb, rerank-shim, api, kb-poll,
  **1c-odata-gateway**, **1c-config-ui**, **serenedb**, **1c-mcp-braine**, **1c-mcp-reports**;
  таймеры nightly-eval, **1c-etl** (03:00), **1c-serene-sync** (03:40), **1c-bot-monitor** (+2 мин).
- **LXC — OpenClaw gateway:** systemd **user**-юнит юзера `undebot` с **`linger=yes`** → стартует на буте
  **без логина** (проверено). Telegram — long polling, токен в `tokenFile`.
- `tg-bridge` (braine-фронт Telegram) — **disabled**: Telegram держит OpenClaw `@test1c_mcp_bot`.
- Итог: перезагрузка любой из машин → всё восстанавливается без ручных действий; мониторинг алертит, если что-то не встало.

---

## 10. SereneDB-аналитика: развёртывание + подключение НОВОЙ 1С-базы

Слой «вопрос на естественном языке → точный отчёт/график». **Общий, без хардкода — переносится на любую
1С-базу.** Описание — `docs/SERENEDB.md`. Ставится ПОВЕРХ §1-6 (нужен читающий OData-шлюз :6011). Весь код —
в `ubuntu/serenedb/`.

### 10.1 Движок SereneDB
Установить бинарём + systemd — `ubuntu/serenedb/README.md` (loopback :7890, под юзером `serened`, enabled).

### 10.2 Код аналитики + окружение
```bash
install -d /opt/1c-mcp-reports
cp ubuntu/serenedb/*.py ubuntu/serenedb/*.sh ubuntu/serenedb/serene-entities.txt /opt/1c-mcp-reports/
chmod +x /opt/1c-mcp-reports/*.sh
cat > /etc/1c-mcp-reports.env <<EOF        # секреты не в git, chmod 600
ETL_ODATA_BASE=http://127.0.0.1:6011         # читающий OData-шлюз из §6
CSV_DIR=/var/lib/serenedb                    # каталог данных SereneDB (загрузчик пишет CSV сюда)
DEEPSEEK_API_KEY=<ключ>                        # NL→SQL + grounding-критик
DEEPSEEK_BASE=https://api.deepseek.com
ALIBABA_API_KEY=<ключ>                         # эмбеддер резолвера (Qwen text-embedding-v4)
ALIBABA_EMBED_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
EMBED_MODEL=text-embedding-v4
EMBED_DIM=1536
CHART_DIR=/home/<botuser>/.openclaw/workspace/charts   # PNG-графики: только из песочницы бота
MCP_HOST=127.0.0.1
MCP_PORT=6015
EOF
chmod 600 /etc/1c-mcp-reports.env
```

### 10.3 Роли + секреты (идемпотентно, генерируемые пароли)
```bash
cd /opt/1c-mcp-reports && bash setup.sh /etc/1c-mcp-reports.env
```
Создаёт `serene_ro` (read-only) + `serene_resolver` (доступ к `resolver_index`; у `serene_ro` отозван) и
дописывает в env `PGPASSWORD`/`RESOLVER_PW`/`RESOLVER_DSN`/`SERENEDB_DSN`. Пароли рутуются при каждом прогоне
→ после setup перезапусти `1c-mcp-reports`.

### 10.4 Подключение НОВОЙ базы: выбор сущностей ИЗ ЖИВОГО OData
```bash
cd /opt/1c-mcp-reports
export $(grep -E '^ETL_ODATA_BASE=' /etc/1c-mcp-reports.env | xargs -d '\n')
python3 serene_select.py --review          # → serene-entities.txt.review (кандидаты по убыванию строк)
# раскомментируй нужные БИЗНЕС-сущности, сохрани как serene-entities.txt
```
Имена всегда из реальности. Авто-дискавери включает и платформенные справочники (метаданные/классификаторы)
— бизнес-сущности отбираешь сам; преполёт синка сверяет список каждый прогон.

### 10.5 Первый синк (загрузка витрины + резолвер)
```bash
export $(grep -E '^(ALIBABA_|ETL_ODATA_BASE|CSV_DIR|EMBED_)' /etc/1c-mcp-reports.env | xargs -d '\n')
export SERENEDB_DSN='host=127.0.0.1 port=7890 user=postgres'   # загрузка под rw
python3 serene_sync.py
```

### 10.6 Сервисы (reboot-safe)
```bash
cp ubuntu/serenedb/systemd/1c-mcp-reports.service /etc/systemd/system/     # EnvironmentFile=/etc/1c-mcp-reports.env
cp ubuntu/serenedb/systemd/1c-serene-sync.{service,timer} /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-mcp-reports.service     # инструмент report_1c (:6015)
systemctl enable --now 1c-serene-sync.timer       # ночная пересборка витрины (после ETL)
```

### 10.7 Бот (инструмент `report_1c`) → `docs/OPENCLAW_BOT.md`
Подключить MCP-инструмент `report_1c` к OpenClaw-боту (маршрутизация: аналитика → `report_1c`, факт/текст →
`ask_1c`; гейт `verify-plugin` сверяет числа обоих).

### 10.8 Проверка
```bash
cd /opt/1c-mcp-reports
export $(grep -E '^(ALIBABA_|EMBED_|PGPASSWORD|RESOLVER_PW)=' /etc/1c-mcp-reports.env | xargs -d '\n')
export SERENEDB_DSN='host=127.0.0.1 port=7890 user=serene_ro dbname=postgres'
export RESOLVER_DSN='host=127.0.0.1 port=7890 user=serene_resolver dbname=postgres'
for t in test_validate test_integrity test_caveat test_ro_role; do python3 $t.py; done   # все PASS
./probe.sh "<вопрос по вашим данным>"       # реальный отчёт через весь путь NL→SQL→exec
```
⚠ Реальная аналитика (обороты/суммы/периоды) требует РЕАЛЬНЫХ данных в 1С + публикации нужных
`AccumulationRegister` в OData (сторона 1С) — иначе готовых оборотов через OData нет. См. `PRODUCTION_PLAN.md` §7.

---

## 11. OpenClaw: бот-слой (Telegram + гейт анти-галлюцинаций)

Диалоговая оболочка тона над двумя мозгами: Telegram → OpenClaw (DeepSeek) → `ask_1c` (braine) / `report_1c`
(SereneDB) → **verify-плагин** сверяет числа кодом. Ставится ПОВЕРХ §7-8 (braine) и §10 (SereneDB).
Устройство — `docs/OPENCLAW_BOT.md`. Код — `ubuntu/openclaw/`. 🔴 Только нативное OpenClaw; гарантии — кодом,
не промтом (персона держит только тон).

### 11.1 MCP-сервер `ask_1c` над braine (:6014)
```bash
install -d /opt/openclaw-mcp && python3 -m venv /opt/openclaw-mcp/venv
/opt/openclaw-mcp/venv/bin/pip install -r ubuntu/openclaw/requirements.txt   # FastMCP (офиц. MCP SDK)
install -D ubuntu/openclaw/mcp_braine.py /opt/openclaw-mcp/mcp_braine.py
cat > /etc/1c-mcp-braine.env <<EOF        # chmod 600
BRAINE_TOKEN=<API_TOKEN braine из /opt/smart-bot/.env>
EOF
chmod 600 /etc/1c-mcp-braine.env
cp ubuntu/openclaw/systemd/1c-mcp-braine.service /etc/systemd/system/   # BRAINE_URL=127.0.0.1:8090, MCP_PORT=6014
systemctl daemon-reload && systemctl enable --now 1c-mcp-braine
```
*(Инструмент `report_1c` :6015 уже поднят в §10.6 — оба MCP-сервера нужны боту.)*

### 11.2 Движок OpenClaw + инстанция под юзером `undebot`
```bash
npm install -g openclaw@2026.7.1-2          # движок глобально; CLI /usr/bin/openclaw
useradd --create-home --shell /bin/bash undebot
loginctl enable-linger undebot              # user-сервисы стартуют на буте БЕЗ логина (reboot-safe)
install -d -o undebot -g undebot -m700 /home/undebot/.openclaw /home/undebot/.openclaw/workspace
```

### 11.3 Конфиг + секреты (эталон — `ubuntu/openclaw/instance/openclaw.json`)
Конфиг класть **файлом** (headless `onboard` сломан). Эталон совпадает с прод-деплоем 1:1; подставить свои
пути/ID. Ключевое (детали — `docs/OPENCLAW_BOT.md`): `tools.allow:["message","bundle-mcp"]` (узкий набор
кодом), `dmPolicy:allowlist`+`allowFrom:[<свой tg-id>]` (только владелец!), `commands.native:false`,
`mcp.servers` = `second-brain`(:6014→`ask_1c`) + `second-brain-reports`(:6015→`report_1c`).
```bash
sudo -u undebot cp ubuntu/openclaw/instance/openclaw.json /home/undebot/.openclaw/openclaw.json
sudo -u undebot cp ubuntu/openclaw/instance/AGENTS.md     /home/undebot/.openclaw/workspace/AGENTS.md
printf '%s' '<TELEGRAM_BOT_TOKEN>' | sudo -u undebot tee /home/undebot/.openclaw/telegram-token >/dev/null
sudo -u undebot chmod 600 /home/undebot/.openclaw/telegram-token
printf 'DEEPSEEK_API_KEY=%s\n' '<ключ>' | sudo -u undebot tee /home/undebot/.openclaw/.env >/dev/null
sudo -u undebot chmod 600 /home/undebot/.openclaw/.env
# ключ провайдера — ТАКЖЕ в auth-store (иначе «No API key found» при явном plugins.allow):
sudo -u undebot openclaw models auth paste-api-key --provider deepseek --profile-id deepseek:default
```

### 11.4 verify-плагин (гейт анти-галлюцинаций, КОДОМ)
```bash
cd ubuntu/openclaw/verify-plugin && node test-verify.mjs      # 36 оффлайн-юнитов — все PASS
npm pack --pack-destination /tmp
sudo -u undebot openclaw plugins install npm-pack:/tmp/openclaw-braine-verify-1.0.0.tgz --force
# в openclaw.json уже: plugins.allow += "braine-verify"; entries.braine-verify.enabled=true +
#   hooks.allowConversationAccess=true (иначе хуки к переписке молча не срабатывают)
```

### 11.5 Gateway (systemd user-юнит, reboot-safe)
```bash
sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) openclaw gateway install --port 18800
sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) systemctl --user enable --now openclaw-gateway
```

### 11.6 Проверка
```bash
UD="sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot)"
$UD systemctl --user is-active openclaw-gateway          # active
$UD openclaw channels status --probe                     # telegram: works
$UD openclaw mcp probe second-brain; $UD openclaw mcp probe second-brain-reports   # по 1 tool
bash ubuntu/openclaw/qa/qa-probes.sh                     # приветствие/мета/инъекции/нет-данных/не-слил-SQL — PASS
# живой гейт: написать боту в Telegram вопрос → факт с числом из данных проходит;
#   выдуманное число без эталона → заменяется/режется (см. braine-verify-debug.log при config.debug)
```
⚠ **Ротация bot-токена** перед реальным продом — действие владельца (@BotFather `/revoke` → новый токен в
`telegram-token` → `systemctl --user restart openclaw-gateway`). Мониторинг `1c-bot-monitor` читает тот же файл.

---

## Приложение: MCP Toolkit — dev-only (НЕ для прода)
Встроенный сервер тулкита удобен для интерактивной отладки/произвольных `execute_query`, но НЕ годится для сервиса: обслуживает всё через один клиентский idle-обработчик 1С (~1 req/s, встаёт на модальном окне — `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`). Также подтверждено: UI-тумблеры инструментов **не блокируют вызов** (отключённый `execute_code` исполнял код). Артефакты для dev: `ubuntu/1c-gateway/gateway.py` (whitelist-прокси MCP), `windows/fork/` (форк с вырезанным execute_code — x86-ребилд падал на нативном компоненте). Для прода — OData (§5-6).

---

## Журнал проверенного end-to-end (2026-07-22..24)
- Платформа 8.3.27.1786 x86 + community-лицензия; база Бухгалтерия 3.0.190.11; бэкап 760 MB — ✅.
- IIS включён (ребут), W3SVC Automatic; база опубликована; OData enable=true; состав — 1128 объектов (COM foreach) — ✅.
- OData читает как служба: `Организации`→«Наша организация», `Валюты`=1; **зависаний/модалок нет** — ✅.
- Read-only 2 слоя: `ai_reader` пишет→500; шлюз POST/PATCH/PUT/DELETE→405 (проверено с LXC) — ✅.
- braine развёрнут (7 сервисов active, пины 0.10.2/0.3.6, эмбеддер Qwen `text-embedding-v4` @ 1536); бот @test1c_mcp_bot в Telegram — ✅.
- **ETL прогнан:** 19 сущностей / 44 записи через OData-шлюз → push в KB-репо → oikb «Synced: 20 added» → индексация — ✅.
- **Бот отвечает по данным 1С:** «Каких контрагентов знаешь?» → «МИ ФНС России по управлению долгом (ИНН 7727406020), Казначейство России» с цитатами — ✅.
- **SereneDB-аналитика (§10):** витрина загружена (стабильная пагинация + дедуп + исключение папок); NL→SQL под `serene_ro`; валидатор allow-list + резолвер Qwen; тесты `validate/integrity/caveat/ro_role` — ✅. Гейт продакшена — реальные обороты/регистры (`PRODUCTION_PLAN.md §7`).
- **OpenClaw бот-слой (§11):** движок 2026.7.1-2 под `undebot` (linger); оба MCP (`ask_1c`:6014, `report_1c`:6015, `mcp probe` = 1 tool); verify-плагин (36 юнитов) `enabled`, гейт на РЕАЛЬНОЙ Telegram-доставке: обоснованное число → прошло, выдуманное → заменено/срезано — ✅.
- Zero-touch: все system-сервисы enabled; OpenClaw user-юнит + linger; IIS Automatic — ✅.
