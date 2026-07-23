# RUNBOOK: развёртывание «второго мозга» на 1С с нуля

Пошаговая воспроизводимая инструкция для раскатки на новом проекте. Проверено end-to-end на стенде 2026-07-22 (Windows 11, платформа 8.3.27.1786 x86, Бухгалтерия 3.0.190.11 → OData/IIS → braine на Ubuntu LXC → бот отвечает по данным 1С). Эталон для клонирования — держать актуальным.

Связанные: `docs/PLAN.md` (архитектура/решения) · `docs/UBUNTU_SETUP.md` (стек braine) · `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md` (почему НЕ встроенный тулкит) · `ubuntu/1c-gateway/` (OData-шлюз) · `ubuntu/1c-etl/` (ETL).

---

## 0. Архитектура (прод — соединение по IP, канал = OData на IIS)

```
Windows (1С):  файловая база ─► IIS (служба) ─► штатный OData 1С (read-only user ai_reader)
                                   ▲ авто-старт, многопоточно, без idle-обработчика/модалок
Роутер 192.168.56.1:  проброс <порт> ─► Windows-IIS:80
Ubuntu LXC (наш):  OData-шлюз :6011 (только GET) ─► ETL ─► KB-репо (GitLab) ─► oikb/OWUI индексация ─► бот
```
- **Инвариант:** в 1С только читаем. Гарантия read-only — двумя слоями (§6): пользователь `ai_reader` (нет прав записи) + шлюз (режет не-GET). Не на настройках приложения.
- **Почему OData, а не встроенный сервер MCP-тулкита:** тулкит обслуживает HTTP через клиентский idle-обработчик 1С — ~1 req/s и встаёт на любом модальном окне сессии (`docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`). OData обслуживает IIS (служба Windows): многопоточно, авто-старт, переживает ребут, модалок в веб-сессии нет. Тулкит остаётся как **dev-опция** (§Приложение).
- Два контура: холодный (ночная выгрузка ETL → KB) + горячий (бот отвечает по индексу). `docs/PLAN.md §2`.

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
- **Windows:** IIS (W3SVC) = Automatic; публикация/состав OData/пользователи — персистентны. После ребута OData сам доступен.
- **LXC (все enabled):** postgresql, open-webui, oikb, rerank-shim, tg-bridge, api, kb-poll, **1c-odata-gateway**; таймеры nightly-eval, **1c-etl**. Ребут LXC → всё поднимается само.
- Итог: после перезагрузки любой из машин канал восстанавливается без ручных действий.

---

## Приложение: MCP Toolkit — dev-only (НЕ для прода)
Встроенный сервер тулкита удобен для интерактивной отладки/произвольных `execute_query`, но НЕ годится для сервиса: обслуживает всё через один клиентский idle-обработчик 1С (~1 req/s, встаёт на модальном окне — `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`). Также подтверждено: UI-тумблеры инструментов **не блокируют вызов** (отключённый `execute_code` исполнял код). Артефакты для dev: `ubuntu/1c-gateway/gateway.py` (whitelist-прокси MCP), `windows/fork/` (форк с вырезанным execute_code — x86-ребилд падал на нативном компоненте). Для прода — OData (§5-6).

---

## Журнал проверенного end-to-end (2026-07-22)
- Платформа 8.3.27.1786 x86 + community-лицензия; база Бухгалтерия 3.0.190.11; бэкап 760 MB — ✅.
- IIS включён (ребут), W3SVC Automatic; база опубликована; OData enable=true; состав — 1128 объектов (COM foreach) — ✅.
- OData читает как служба: `Организации`→«Наша организация», `Валюты`=1; **зависаний/модалок нет** — ✅.
- Read-only 2 слоя: `ai_reader` пишет→500; шлюз POST/PATCH/PUT/DELETE→405 (проверено с LXC) — ✅.
- braine развёрнут (7 сервисов active, пины 0.10.2/0.3.6, эмбеддер Qwen `text-embedding-v4` @ 1536); бот @test1c_mcp_bot в Telegram — ✅.
- **ETL прогнан:** 19 сущностей / 44 записи через OData-шлюз → push в KB-репо → oikb «Synced: 20 added» → индексация — ✅.
- **Бот отвечает по данным 1С:** «Каких контрагентов знаешь?» → «МИ ФНС России по управлению долгом (ИНН 7727406020), Казначейство России» с цитатами — ✅.
- Zero-touch: все сервисы enabled; IIS Automatic — ✅.
