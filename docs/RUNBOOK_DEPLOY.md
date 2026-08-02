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
  OData-шлюз :6011 (только GET) ──► serene_sync ──► витрина SereneDB :7890
                                       └─► serene_search_build ──► корпус + инвертированный индекс
  OpenClaw-бот :18800 (юзер undebot) ── serene_ask :8091 ──► индекс SereneDB (отбор) + база (счёт)
     Telegram ◄─── тон, DeepSeek
     → verify-плагин (ГЕЙТ КОДОМ: числа сверяет, внутреннее режет) → ответ клиенту
```

**Полная карта сервисов LXC `.42` (всё loopback; ground-truth, `enabled` = переживает ребут):**

| Порт | Unit / таймер | Процесс | Юзер | Слой |
|---|---|---|---|---|
| — | `1c-odata-gateway` :6011 | `odata_gateway.py` | root | канал: только GET к 1С-OData (upstream `192.168.56.1:6003`) |
| `127.0.0.1:6012` | `1c-config-ui` | `oc_config_ui.py` | root | веб-галочки «что тянуть» (ETL). Требует `Authorization: Bearer $UI_TOKEN` и на GET, и на POST — из браузера без токена страница не откроется |
| — | `1c-etl.timer` 03:00 | `oc_etl.py` | root | ⚠ кормил braine → **не нужен** после вывода слоя |
| — | *(braine: postgresql/open-webui/oikb/rerank-shim/api :8090)* | — | — | ⚠ **слой выведен из контура** 26.07, освободилось 972 МБ. §7-8 оставлены как история |
| `127.0.0.1:7890` | `serenedb` | `serened` | **serenedb** | витрина аналитики (Postgres-протокол) |
| `127.0.0.1:8091` | **`1c-serene-ask`** | `serene_ask.py` | root | **отвечающий сервис ПЕРВОЙ базы**: ищет индексом, считает базой. ⚠ [замер 02.08] юнит `enabled`, но `inactive`, на `:8091` никто не слушает; боевые ответы идёт с `:8099` — процесса вне systemd (см. таблицу второй базы ниже) |
| — | `1c-serene-sync.timer` 03:40 | `serene_sync.py` | root | ⚠ **остановлен**: синк стал частью конвейера |
| — | **`1c-serene-pipeline.timer`** (по готовности) | `pipeline.sh` | root | 🟢 **боевой такт**: раскладка кода → синк-дельта → сборка. Понятия «ночной» нет (п. 17) |
| — | **`1c-serene-index.timer`** (`OnUnitActiveSec=20min`, `disabled`) | `build.sh` | root | ⚠ **таймер остановлен 28.07.** Сборка переехала в штатные средства движка: `build.sh` (корпус, величины, резолвер, индекс — одним SQL, без питона), и **живой юнит на неё переключён 28.07** (старый `ExecStart` сохранён в `.bak-20260728`). Таймер выключен, потому что такт целиком отдан `1c-serene-pipeline`. 🔴 Опасна не установленная копия, а **репозиторная** `ubuntu/serenedb/systemd/1c-serene-index.service` — она до сих пор зовёт `serene_search_build.py`, который при новом составе корпуса **сносит таблицу и индекс** (авария 28.07, `HOW_NOT_TO §2.9`); см. §10.6 |
| `127.0.0.1:6015` | `1c-mcp-reports` | `mcp_reports.py` | root | ⚠ `report_1c` (NL→SQL) — **выведен из контура**, юнит ещё жив |
| `127.0.0.1:18800` | `openclaw-gateway` (**user**-юнит) | `node …/openclaw` | **undebot** | бот: Telegram + DeepSeek-тон + verify-гейт |
| — | `1c-bot-monitor.timer` (каждые 3 мин) | `bot_health_check.sh` | root | алерт владельцу в Telegram при падении |
| — | `nightly-eval.timer` | `nightly-eval.sh` | root | ⛔ **погашен 29.07**: гонял евал выведенного слоя braine и слал алерт владельцу **с боевого токена бота**. Поднимать не надо |

### Вторая база 1С (стенд, состояние на 02.08)

Баз 1С у клиента бывает несколько. У каждой — **свой шлюз, своя база движка, свой
отвечающий сервис**. Шаблонный юнит: `1c-odata-gateway@<имя>` читает
`/etc/1c-odata-gateway-<имя>.env` (права 600).

| Порт | Что | Состояние на 02.08 |
|---|---|---|
| `127.0.0.1:6021` | шлюз OData второй базы, `1c-odata-gateway@ut` | 🟢 **переведён на штатный юнит 02.08** `[замер]`: после освобождения порта ответ тот же (HTTP 200, 10 238 байт на `Catalog_Организации?$top=1`), 401 без токена, 405 на POST, переживает `restart`, журнал в `journald`. *Было ошибочно: «мало освободить порт — `ODG_PASS` пуст, поэтому штатный путь отдаст 401». **Чем опровергнуто:** файл `/etc/1c-odata-gateway-ut.env` и окружение сироты совпали побайтно по всем шести переменным, включая пустой `ODG_PASS`; сирота с тем же пустым паролем отдавал 200 (пароль у этой учётки 1С пуст, см. `F127`). Юнит падал только из-за занятого порта — `Address already in use`, 740 попыток* |
| `127.0.0.1:8099` | сервис ответов второй базы, `1c-serene-ask@ut_test` | 🟢 **переведён на шаблонный юнит 02.08** `[замер]`: `/health` отдаёт 623 565 строк корпуса `ut_test`, экземпляр в своём cgroup, `enabled`. Боевая конфигурация (DSN, порт, скорер) переехала из памяти процесса в `/etc/1c-serene-ask-ut_test.env` (600). Первая база — `1c-serene-ask@postgres` на :8091, 103 808 строк. Старый одиночный `1c-serene-ask` — `disabled` |
| база движка | `ut_test` | пересоздана с нуля 29.07 (бэкап → `DROP DATABASE` → `CREATE DATABASE` → конвейер) |

🔴 **Оба осиротевших процесса — это и есть «ручной шаг», который ломает автономность.**
[замер 29.07] шлюз второй базы, поднятый руками, не пережил перезапуск: сборка второй базы
упала, а её падение снесло общие секреты движка и оставило без векторов такт **первой**
базы. Один ручной шаг обошёлся в два дефекта.

- **Инвариант:** в 1С только читаем. Гарантия read-only — двумя слоями (§6): пользователь `ai_reader` (нет прав записи) + шлюз (режет не-GET). Не на настройках приложения.
- **Почему OData, а не встроенный сервер MCP-тулкита:** тулкит обслуживает HTTP через клиентский idle-обработчик 1С — ~1 req/s и встаёт на любом модальном окне сессии (`docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`). OData обслуживает IIS (служба Windows): многопоточно, авто-старт, переживает ребут, модалок в веб-сессии нет. Тулкит остаётся как **dev-опция** (§Приложение).
- Два контура: холодный (ночная выгрузка ETL/синк → KB+витрина) + горячий (бот отвечает по индексу/витрине). `docs/ARCHITECTURE.md §3`.
- ⚠ **Права юнитов: все наши `1c-*` ходят под `root`, и решение об этом нигде не записано.**
  [замер 02.08] `systemctl show -p User` пуст у всех двенадцати сервисов `1c-*` и у
  шаблонного `1c-odata-gateway@` — включая обе сетевые двери (`1c-odata-gateway`,
  `1c-config-ui`) и процессы, держащие ключи облачных
  моделей; из ужесточающих директив есть ровно одна — `NoNewPrivileges=true` у
  `1c-mcp-reports`; `ProtectSystem`/`ProtectHome`/`PrivateTmp` не выставлены нигде.
  Единственный юнит с выделенным пользователем — `serenedb` (`User=serenedb`). Таблица §0
  это честно печатает; **вопрос владельцу** — ужесточать или зафиксировать «на стенде
  оставляем root» (`work/doc-audit/QUESTIONS_TO_OWNER.md`).

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

### 🔴 Доступ к Windows с нашего сервера (проверено 28.07.2026)

С Ubuntu-сервера (LXC `192.168.56.42`) на Windows-стенд ходим по SSH **ключом**:

```bash
ssh -i /root/.ssh/id_ed25519_1c -p 2222 unde@192.168.56.1
```

- **`192.168.56.1:2222`** — проброшенный на роутере SSH Windows-машины. Сам `192.168.56.1:22`
  — это SSH **Linux-роутера** (баннер `OpenSSH … Ubuntu`), не Windows; туда мы не логинимся.
- Хост: `DESKTOP-UQG768B`, пользователь **`unde`** (не администратор домена; для COM под
  админом 1С см. §5.3).
- Ключ `id_ed25519_1c` лежит на сервере в `/root/.ssh/`. Другого приватного ключа в системе
  нет — прежняя запись «SSH-ключ в `administrators_authorized_keys`» описывала вход НА
  Windows со стороны владельца, а не с нашего сервера.
- Прямого маршрута к Windows в подсети `192.168.56.0/24` нет: RDP/WinRM/IIS на отдельном
  адресе не видны, единственные каналы — этот SSH (:2222) и проброс OData (:6003 → IIS:80).

**Что где на Windows:** платформа `C:\Program Files (x86)\1cv8\8.3.27.1786`; базы
`C:\1c\bases\` (`bld`, `buh_test`); опубликована в OData файловая **`C:\1c\bases\buh_test`**
(дескриптор `C:\inetpub\1c\default.vrd`, `standardOdata enable="true"`).

```powershell
New-Item -ItemType Directory -Force -Path C:\1c\bases,C:\1c\backups,C:\1c\distr,C:\1c\logs,C:\1c\repo
git config --global user.name "<имя>"; git config --global user.email "<mail>"
git clone <repo> C:\1c\repo
```

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

### 5.0 🚀 АВТОМАТИЧЕСКИ (рекомендуется): `setup-1c-odata.exe`
Один файл делает §5.1-5.3 + §6-слой прав + бэкап + проверку. Руками остаётся **только пользователь-читатель**
(§4). Без зависимостей, повторный запуск безопасен, `--check` ничего не меняет.
```bat
:: посмотреть план, ничего не меняя
windows\odata-setup\dist\setup-1c-odata.exe --check --base "C:\1c\bases\<база>"

:: настроить (пароль администратора 1С спросит скрытно)
windows\odata-setup\dist\setup-1c-odata.exe --base "C:\1c\bases\<база>" --admin-user Администратор ^
        --scope analytics --reader-user ai_reader
```
Печатает готовый блок `ODG_UPSTREAM/ODG_USER/ODG_PASS` для §6 и сохраняет его в
`C:\1c\logs\1c-odata-connection.txt`. Код возврата 10 = «поставлены компоненты IIS, перезагрузите и
запустите снова». Все ключи, сценарии нехватки компонентов и коды возврата — `windows/odata-setup/README.md`.

Ниже — **ручной путь** (что именно делает инструмент; нужен для разбора и нестандартных случаев).

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

### 🔴 Находка 28.07: часть сущностей отдаёт данным 401, а `$count` — 200

**Симптом.** У сущности `$count` возвращает число и HTTP 200, а сама выборка данных —
**401**. То есть по счётчику объект выглядит доступным, а прочитать его нельзя. Перепись
полноты (`search_coverage`, п. 13) насчитала таких **934**.

**Разбор (замер по `base_profile`, `rows = -1`).** Это не спрятанные бизнес-данные, а по
большинству — мусор конфигурации:

| категория | сколько | что это |
|---|---|---|
| `*_RecordType` | 25 | вложенные типы регистров — служебные тени, не данные |
| `Удалить*` (кроме `_RecordType`) | 330 | объекты, **помеченные в конфигурации на удаление** |
| прочее | 579 | служебные таб. части (`ПрисоединённыеФайлы`, `Состав`, `Назначение`), настройки обмена, группы доступа; из них 363 `InformationRegister`, 168 `Catalog`, 46 `Document`, 2 `AccumulationRegister` |

*Было ошибочно: «25 / 352 / 579» — категории пересекались (22 сущности вида
`Удалить…_RecordType` попадали в обе), сумма давала 956 ≠ 934. **Чем опровергнуто:**
`psql`-пересчёт — `_RecordType` 25, `LIKE '%Удалить%'` 352 (из них 22 одновременно
`_RecordType`), прочих 579; непересекающееся разбиение 25 + 330 + 579 = 934.*

**Почему так и почему это правильно.** Профиль `ai_reader` — «Только просмотр» (BSP) —
намеренно не даёт доступа к персональным данным, правам доступа и служебным регистрам.
Инвариант проекта: «в 1С только читаем, гарантия — узкая роль, а не настройки приложения».
Открывать всё веерно **нельзя** — это откроет читателю и персональные данные сотрудников.

**Решение (владелец 28.07).** Оставляем как есть: 934 закрытых — почти всё мусор и
служебное, по нужным данным полнота 99,998 % (не дошло 2 строки из 103 958, и те — 401).
Бот честно отвечает «закрыто правами». Если конкретный раздел понадобится — добавить
`ai_reader` **точечную** роль на него (COM/`setup-1c-odata.exe`, §5.3) и проверить замером,
что 401 сменился на 200. Веерного «дать всё» не делаем.

**Важное различие, которое тут проверено:** эти 934 **есть в `$metadata`** — значит их не
исключили из состава OData, ограничивает именно РОЛЬ. Если бы дело было в составе, их не
было бы и в переписи. Состав и роль — два разных рычага (состав — §5.3, роль — профиль
пользователя).

### Роутер `.1`: проброс на IIS
На роутере/шлюзе сети LXC пробросить порт на **Windows-IIS:80** (напр. `192.168.56.1:6003 → <win-ip>:80`). Тогда LXC ходит `192.168.56.1:<порт>/1c/odata/standard.odata/…`.

### Развернуть OData-шлюз (LXC)

🔴 **Шлюз ставится ПОЭКЗЕМПЛЯРНО: один экземпляр = одна база 1С.** Даже если база пока одна,
разворачивайте шаблонным юнитом `1c-odata-gateway@<имя>` — иначе вторая база потребует
переписать `/etc/1c-odata-gateway.env` первой (потеряются креды `ai_reader` и токен шлюза) и
займёт тот же порт 6011.

Все пути ниже — **от корня репозитория**.

```bash
BASE=ut                                        # короткое имя экземпляра: свой env, свой порт
GW=6021                                        # его порт; понадобится дальше в §10
install -D ubuntu/1c-gateway/odata_gateway.py /opt/1c-odata-gateway/odata_gateway.py
cat > /etc/1c-odata-gateway-$BASE.env <<EOF
ODG_USER=<пользователь-читатель этой базы>
ODG_PASS=<его пароль>                          # 🔴 обязательно: пустой ODG_PASS → 401 на все запросы
ODG_GATEWAY_TOKEN=<сгенерируйте: openssl rand -hex 24>   # 🔴 без него шлюз НЕ СТАРТУЕТ (exit 2)
ODG_LISTEN_PORT=$GW                            # 🔴 свой порт на каждый экземпляр (умолчание 6011)
ODG_UPSTREAM=http://192.168.56.1:6003/$BASE/odata/standard.odata   # путь ПУБЛИКАЦИИ этой базы
EOF
chmod 600 /etc/1c-odata-gateway-$BASE.env
cp ubuntu/systemd/1c-odata-gateway@.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now 1c-odata-gateway@$BASE
```

🔴 **`ODG_GATEWAY_TOKEN` обязателен и здесь, и дальше.** `odata_gateway.py` при пустом токене
выходит с кодом 2 («отказ на старте, а не тихое снятие защиты»), а у шаблонного юнита
`Restart=always` — получится бесконечная петля рестартов. Этот же токен понадобится в §10.2
и в каждом ручном запуске загрузчика (§10.4, §10.5): без него шлюз ответит **401**.

*Было ошибочно: единственная инструкция по шлюзу была однобазовой — писала
`/etc/1c-odata-gateway.env` без `ODG_LISTEN_PORT`, с путём публикации `/1c/`, и включала
непараметризованный `1c-odata-gateway.service`; шаблонный юнит упоминался только в
справочной таблице §0. **Чем опровергнуто:** живая вторая база настроена иначе —
`/etc/1c-odata-gateway-ut.env` с `ODG_LISTEN_PORT=6021` и путём `/ut/odata/standard.odata`;
`odata_gateway.py:47` берёт `ODG_LISTEN_PORT` с умолчанием 6011, то есть по прежней
инструкции второй экземпляр вставал бы на тот же порт.*

### Проверки безопасности (ворота, проверено на стенде с LXC)
1. `GET Catalog_Валюты/$count` через шлюз → данные ✅.
2. `POST/PATCH/PUT/DELETE` через шлюз → **405** (не доходят до 1С) ✅.
3. Прямая запись под `ai_reader` (мимо шлюза) → отказ прав (HTTP 500) ✅.
4. Итоговое правило клиента: ходить только через шлюз, только GET.

---

## 7. Стек braine (LXC) — `docs/UBUNTU_SETUP.md`

> ⚠ **РАЗДЕЛЫ 7 И 8 БОЛЬШЕ НЕ ЧАСТЬ ПРОДУКТА.** Слой braine (RAG на OWUI/pgvector) выведен
> из контура 26.07 — его заменил `serene_ask` (§10.6), который ищет тем же индексом SereneDB.
> Разделы сохранены как история установки; **при развёртывании с нуля их пропускать.**
> Замер, на основании которого выведен: `docs/BENCH_BRAINE_VS_SERENE.md`.
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
- **LXC — system-сервисы (`enabled`), [замер 01.08]:** `postgresql`, `serenedb`,
  **`1c-odata-gateway`**, **`1c-config-ui`**, **`1c-mcp-ask`**, **`1c-mcp-braine`**,
  **`1c-mcp-reports`**, **`1c-serene-ask`**, **`1c-odata-gateway@ut`** (шлюз второй базы);
  таймеры **`1c-serene-pipeline`** (по готовности) и **`1c-bot-monitor`** (каждые 3 мин).

  ⚠ `1c-odata-gateway@ut` `enabled` — то есть после ребута он **стартует**, но с пустым
  `ODG_PASS` (см. таблицу второй базы в §0) будет отвечать 401 на все запросы.

  *Было ошибочно: в перечне стояли `open-webui`, `oikb`, `rerank-shim`, `api`, `kb-poll`
  и таймеры `1c-etl` (03:00), `1c-serene-sync` (03:40). **Чем опровергнуто:**
  `systemctl list-unit-files --state=enabled` — первых пяти в enabled нет вовсе (слой braine
  выведен 26.07, см. §0), `1c-etl.timer` и `1c-serene-sync.timer` существуют, но disabled:
  синк стал шагом конвейера, ETL кормил выведенный braine. Отдельно: `1c-serene-sync` нельзя
  было называть «переживающим ребут» — §0 того же файла объявляет его остановленным.*

  🔴 Список снят со стенда в аварийном состоянии (конвейер стоит с 29.07, сервис ответов
  и шлюз второй базы — процессы вне systemd). `enabled` здесь означает «поднимется после
  ребута», а не «работает сейчас».
- **LXC — OpenClaw gateway:** systemd **user**-юнит юзера `undebot` с **`linger=yes`** → стартует на буте
  **без логина** (проверено). Telegram — long polling, токен в `tokenFile`.
- `tg-bridge` (braine-фронт Telegram) — **disabled**: Telegram держит OpenClaw `@test1c_mcp_bot`.
- Итог: перезагрузка любой из машин → всё восстанавливается без ручных действий; мониторинг алертит, если что-то не встало.

---

## 10. SereneDB-аналитика: развёртывание + подключение НОВОЙ 1С-базы

Слой «вопрос на естественном языке → точный отчёт/график». **Общий, без хардкода — переносится на любую
1С-базу.** Описание — `docs/SERENEDB.md`. Ставится ПОВЕРХ §1-6 (нужен читающий OData-шлюз этой базы).
Весь код — в `ubuntu/serenedb/`.

🔴 **База движка — параметр этого раздела, а не константа.** У каждой базы 1С — своя база
внутри SereneDB. Заведите её и подставляйте во ВСЕ строки подключения ниже:

```bash
export DB=ut_test                              # имя базы движка под эту базу 1С
export GW=6021                                 # порт OData-шлюза этого экземпляра (§6)
psql 'host=127.0.0.1 port=7890 user=postgres dbname=postgres' -c "CREATE DATABASE $DB"
```

🔴 **`DB` и `GW` держите в ОДНОЙ оболочке до конца §10** (потому и `export`). Пустое значение
не даёт ошибки: `psql '…user=postgres dbname='` молча открывает базу `postgres`, то есть
витрину первой базы 1С — ровно тот отказ, который этот раздел и закрывает.

⚠ **Параметром стала строка подключения, но НЕ имена env-файлов, юнитов и портов.** Вторая
база на одном сервере этим разделом пока не разворачивается до конца: `§10.2` пишет в
единственные `/etc/1c-mcp-reports.env` и `/etc/1c-serene-sync.env`, `setup.sh` ротирует
пароли ОБЩИХ ролей `serene_ro`/`serene_resolver`, а `1c-serene-ask` непараметризован и займёт
`:8091` первого экземпляра. Поэкземплярные юниты (`1c-serene-ask@<имя>`) — Фаза 2
`PLAN_AUTONOMY`, см. §0. Пока их нет, второй экземпляр поднимается руками, и это записанный
ручной шаг, а не «как надо».

*Было ошибочно: §10 подавался как «подключение НОВОЙ 1С-базы», но базу движка параметром не
делал — `CREATE DATABASE` не упоминался, в §10.3/§10.5 `dbname` был опущен (libpq подставляет
`postgres`), в §10.8 стояло зашитое `dbname=postgres`, а `ETL_ODATA_BASE` указывал на шлюз
ПЕРВОЙ базы :6011. **Чем опровергнуто:** `psql 'host=… user=postgres' -tAc 'select
current_database()'` → `postgres`; на стенде базы разведены правильно (`postgres` — 103 808
строк корпуса / 231 сущность, `ut_test` — 623 565 / 1502), то есть исполнение прежней
редакции «для новой базы» слило бы её таблицы в витрину первой. Этот же класс уже стоил дня
29.07 (`TEST_SECOND_BASE`, Н-6).*

### 10.1 Движок SereneDB
Установить бинарём + systemd — `ubuntu/serenedb/README.md` (loopback :7890, под юзером `serened`, enabled).

🔴 **Пул исполнителей обязателен, иначе первая загрузка растянется на сутки.** [замер 29.07]
`ai_embed` — сетевой вызов ВНУТРИ запроса, и запрос занимает исполнителя на всё время
ожидания ответа. `--cpu_threads` по умолчанию `0` = число ядер: на шести ядрах наружу
уходит **5-6 запросов**, сколько бы `psql`-потоков ни запускали (12 и 64 дали одинаковые
9,2 строки/с). `--io_threads` по умолчанию `max(1, ядер/4)` = 1 и сериализует соединения.

```conf
# /etc/serenedb/serened.conf
--cpu_threads=96      # НЕ по числу ядер: ограничение сетевое, а не счётное
--io_threads=8
```

Переподписка здесь безопасна: исполнители не считают, а ждут сеть — [замер] под полной
нагрузкой процессор всех процессов в нуле, память 9 ГБ из 62. Значение выбирается по
желаемому числу одновременных обращений к эмбеддеру (`BUILD_EMBED_WORKERS` + запас на
обычные запросы), верхняя граница — квота провайдера: признак, что упёрлись, — `HTTP 429`.

⚠ Пока это ставится **руками**; по плану автономности настройку обязан делать установщик
(`PLAN_AUTONOMY`, ручной шаг №0).

### 10.2 Код аналитики + окружение

🔴 **Раскладка кода — `deploy.sh`, а не `cp` руками.** [замер 28.07] забытое копирование
однажды заставило сборку чужой базы полтакта идти по СТАРЫМ файлам, и выглядело это как
дефект кода, которого в коде уже не было (`HOW_NOT_TO §3.15`). `deploy.sh` копирует только
изменившееся, печатает что именно, и подменяет файлы **атомарно** (`mv`, а не запись
поверх: `bash` дочитывает скрипт по ходу исполнения, и запись в идущий такт порвала бы
его в произвольном месте).

```bash
install -d /opt/1c-mcp-reports
ubuntu/serenedb/deploy.sh /opt/1c-mcp-reports     # вместо cp; идемпотентно
```

**На стенде разработки** раскладка делается сама, первым шагом каждого такта: в
`/etc/1c-serene-sync.env` задана `SERENE_SRC_DIR=/srv/1c/ubuntu/serenedb`, и `pipeline.sh`
зовёт `deploy.sh` перед синком. В продукте переменная не задаётся — установщик кладёт
файлы один раз, и конвейер не зависит от наличия репозитория.

Раскладка вручную (если `deploy.sh` почему-то недоступен):
```bash
install -d /opt/1c-mcp-reports
cp ubuntu/serenedb/*.py ubuntu/serenedb/*.sh ubuntu/serenedb/*.sql ubuntu/serenedb/*.tsv \
   ubuntu/serenedb/serene-entities.txt /opt/1c-mcp-reports/
chmod +x /opt/1c-mcp-reports/*.sh
cat > /etc/1c-mcp-reports.env <<EOF        # секреты не в git, chmod 600
DEEPSEEK_API_KEY=<ключ>                        # NL→SQL + grounding-критик
DEEPSEEK_BASE=https://api.deepseek.com
ALIBABA_API_KEY=<ключ>                         # эмбеддер резолвера (Qwen text-embedding-v4)
ALIBABA_EMBED_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
EMBED_MODEL=text-embedding-v4
EMBED_DIM=1024                                 # столько отдаёт наш эндпоинт; колонка emb FLOAT[1024]
CHART_DIR=/home/<botuser>/.openclaw/workspace/charts   # PNG-графики: только из песочницы бота
MCP_HOST=127.0.0.1
MCP_PORT=6015
SERENEDB_DSN='host=127.0.0.1 port=7890 user=serene_ro dbname=$DB'
RESOLVER_DSN='host=127.0.0.1 port=7890 user=serene_resolver dbname=$DB'
SERENEDB_DSN_RO='host=127.0.0.1 port=7890 user=serene_ro dbname=$DB'
PGPASSWORD=<пароль serene_ro>
RESOLVER_PW=<пароль serene_resolver>
ODG_GATEWAY_TOKEN=<тот же токен, что в /etc/1c-odata-gateway-$BASE.env из §6>
MCP_TOKEN=<токен MCP>
EOF
chmod 600 /etc/1c-mcp-reports.env

cat > /etc/1c-serene-sync.env <<EOF        # окружение конвейера (синк + сборка), chmod 600
ETL_ODATA_BASE=http://127.0.0.1:$GW          # читающий OData-шлюз ЭТОЙ базы 1С (§6)
CSV_DIR=/var/lib/serenedb                    # каталог данных SereneDB (загрузчик пишет CSV сюда)
SERENEDB_DSN='host=127.0.0.1 port=7890 user=postgres dbname=$DB'   # сборке нужен rw
ODG_GATEWAY_TOKEN=<тот же токен шлюза>
EOF
chmod 600 /etc/1c-serene-sync.env
```

🔴 **`SERENEDB_DSN_RO` — отдельная переменная, и без неё сервис ответов читает не ту базу.**
`serene_ask.py` берёт базу из `SERENEDB_DSN_RO` (умолчание в коде — `dbname=postgres`), а не
из `SERENEDB_DSN`. Юнит `1c-serene-ask` подключает `/etc/1c-mcp-reports.env` и
`-/etc/1c-serene-ask.env`; если `SERENEDB_DSN_RO` не задана ни там, ни там, корпус будет
читаться из `postgres`, а резолвер — из `$DB`, и ответы разъедутся молча. На стенде это
именно так и не задано — обе переменные живут только в окружении процесса, поднятого руками.

*Было ошибочно: `ETL_ODATA_BASE`, `CSV_DIR` показаны как часть `/etc/1c-mcp-reports.env`,
`EMBED_DIM=1536`. **Чем опровергнуто:** перепись имён переменных на стенде — в
`/etc/1c-mcp-reports.env` этих двух ключей нет, они в `/etc/1c-serene-sync.env`;
`SELECT len(emb) FROM search_corpus` → 1024, `corpus_init.sql:18` `emb FLOAT[1024]`.*

🔴 **Порядок `EnvironmentFile=` в юнитах сборки значим и менять его нельзя.**
`1c-serene-index.service` и `1c-serene-pipeline.service` подключают сначала
`-/etc/1c-mcp-reports.env` (он нужен ради ключей эмбеддера и DeepSeek), потом
`/etc/1c-serene-sync.env` — и второй перекрывает `SERENEDB_DSN` на `user=postgres`.
Так и задумано: боту нужен `serene_ro`, а сборке — `rw`, иначе `CREATE TABLE` падает на
`permission denied for schema public` (починка 27.07, `SERVER_HANDOFF §6`). `dbname`
записывайте явно: без него libpq берёт имя базы равным имени роли, и переименование роли
молча уводит сборку в другую базу.

### 10.3 Роли + секреты (идемпотентно, генерируемые пароли)
```bash
cd /opt/1c-mcp-reports
SETUP_RW_DSN="host=127.0.0.1 port=7890 user=postgres dbname=$DB" \
SETUP_RO_DSN="host=127.0.0.1 port=7890 user=serene_ro dbname=$DB" \
SETUP_RES_DSN="host=127.0.0.1 port=7890 user=serene_resolver dbname=$DB" \
  bash setup.sh /etc/1c-mcp-reports.env
```
🔴 **Именно эти три переменные, а не `SERENEDB_DSN`.** `setup.sh` читает `SETUP_RW_DSN` /
`SETUP_RO_DSN` / `SETUP_RES_DSN` (строки 15-17) и сам экспортирует `SERENEDB_DSN` поверх
входящего (строка 51) — переданный снаружи `SERENEDB_DSN` будет молча отброшен. Умолчания у
всех трёх — `dbname=postgres`. `CREATE ROLE` в движке кластерный, а `GRANT SELECT ON ALL
TABLES` — **пободазовый**: ошибётесь здесь — роли создадутся, а гранты лягут в витрину первой
базы, и `serene_ro` не увидит в `$DB` ни одной таблицы.

*Было ошибочно (правка 02.08, исправлено в тот же день): здесь стояло
`SERENEDB_DSN="…dbname=$DB" bash setup.sh` и оговорка «без него роли создадутся в
`postgres`». **Чем опровергнуто:** чтением `ubuntu/serenedb/setup.sh` — `SERENEDB_DSN` он не
читает вовсе. Инструкция была написана, не открыв скрипт, о котором она.*
Создаёт `serene_ro` (read-only) + `serene_resolver` (доступ к `resolver_index`; у `serene_ro` отозван) и
дописывает в env `PGPASSWORD`/`RESOLVER_PW`/`RESOLVER_DSN`/`SERENEDB_DSN`. Пароли рутуются при каждом прогоне
→ после setup перезапусти `1c-mcp-reports`.

### 10.4 Подключение НОВОЙ базы: выбор сущностей ИЗ ЖИВОГО OData
```bash
cd /opt/1c-mcp-reports
export $(grep -E '^(ETL_ODATA_BASE|ODG_GATEWAY_TOKEN)=' /etc/1c-serene-sync.env | xargs -d '\n')
python3 serene_select.py --review          # → serene-entities.txt.review (кандидаты по убыванию строк)
# раскомментируй нужные БИЗНЕС-сущности, сохрани как serene-entities.txt
```
Имена всегда из реальности. Авто-дискавери включает и платформенные справочники (метаданные/классификаторы)
— бизнес-сущности отбираешь сам; преполёт синка сверяет список каждый прогон.

### 10.5 Первый синк (загрузка витрины + резолвер)
```bash
export $(grep -E '^(ALIBABA_|EMBED_)' /etc/1c-mcp-reports.env | xargs -d '\n')
export $(grep -E '^(ETL_ODATA_BASE|CSV_DIR|ODG_GATEWAY_TOKEN)=' /etc/1c-serene-sync.env | xargs -d '\n')
export SERENEDB_DSN="host=127.0.0.1 port=7890 user=postgres dbname=$DB"   # загрузка под rw, dbname ЯВНО
python3 serene_sync.py
```

### 10.6 Сервисы (reboot-safe)
```bash
cp ubuntu/systemd/1c-serene-pipeline.{service,timer}       /etc/systemd/system/
cp ubuntu/serenedb/systemd/1c-serene-ask.service           /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-serene-pipeline.timer  # ЕДИНСТВЕННЫЙ такт: раскладка → синк-дельта → сборка
systemctl enable --now 1c-serene-ask.service     # отвечающий сервис
```

🔴 **`1c-serene-sync.timer` и `1c-serene-index.timer` включать НЕЛЬЗЯ.** Синк с 28.07 —
шаг конвейера, а не отдельный таймер. А юнит `1c-serene-index.service` лежит в репозитории
**в двух копиях, и они разные**:

| Копия | `ExecStart` | Что это |
|---|---|---|
| `ubuntu/systemd/1c-serene-index.service` | `/opt/1c-mcp-reports/build.sh` | **боевая**, побайтно равна установленной |
| `ubuntu/serenedb/systemd/1c-serene-index.service` | `…venv/bin/python …/serene_search_build.py` | 🔴 **снятая**: тот самый питоновский сборщик, который **снёс таблицу и индекс** 28.07 (`HOW_NOT_TO §2.9`). Пометки об этом в самом файле нет |

Если проверите `systemctl cat 1c-serene-index.service` и увидите `build.sh` — это не значит,
что предупреждение протухло: на стенде юнит переключён 28.07, опасна именно вторая копия в
репозитории. Боевого таймера (`OnBootSec=5min` / `OnUnitActiveSec=20min`) в git нет вовсе —
единственная его версия в репозитории — снятое ночное расписание `OnCalendar 03:55`.

*Было ошибочно: §10.6 без единой оговорки предписывала `cp` обоих юнитов и
`systemctl enable --now 1c-serene-sync.timer` / `1c-serene-index.timer`. **Чем
опровергнуто:** §0 строки 35-37 объявляют оба таймера остановленными и называют причину;
`systemctl list-timers --all` — `1c-serene-index.timer` в списке отсутствует, живой такт
один, `1c-serene-pipeline`. Раскатка по прежней редакции воспроизводила известную аварию на
чистой машине. Юниты конвейера лежат в `ubuntu/systemd/`, а не в `ubuntu/serenedb/systemd/`.*
`1c-serene-ask` читает `/etc/1c-mcp-reports.env` (ключи Alibaba/DeepSeek, пароли ролей) и
необязательный `/etc/1c-serene-ask.env` (`ASK_TOKEN` — авторизация запросов, `ASK_*_BUDGET_CHARS` —
символьные бюджеты контекста модели).

**Такт.** «Ночного» такта в продукте нет: `1c-serene-pipeline.timer` работает **по
готовности** — следующий заход начинается, когда закончился предыдущий. Этого требует п. 17
`TARGET.md` (свежесть не позднее 20 минут).

*Было ошибочно: «сейчас таймер ночной (03:55), здесь должен стоять `OnUnitActiveSec` —
открытый пункт». **Чем опровергнуто:** `systemctl cat 1c-serene-index.timer` →
`OnUnitActiveSec=20min`, сам таймер `disabled`; такт целиком у `1c-serene-pipeline.timer`
(по готовности). Требуемое прежней редакцией изменение по расписанию сделано.*

🔴 **Но п. 17 этим НЕ закрыт: на стенде свежести нет с 29.07.** [замер 02.08]
`1c-serene-pipeline.service` → `ActiveState=failed`, `Result=signal`, последний запуск
29.07 06:41; таймер `enabled`, но `inactive`, `NEXT` пуст; `1c-serene-sync.service` тоже
`failed`. Механизм такта сделан и замерен — **работает он не сейчас**. Пока конвейер не
поднят, любое утверждение «свежесть обеспечена» в любом документе неверно.

### 10.7 Подключение к боту
Бот ходит в отвечающий сервис через MCP-мост `ask_1c` (`1c-mcp-ask`, :6016), а мост — по
`ASK_URL`. **`ASK_URL` — единственный рычаг выбора того, какой сервис (а значит, какая база
1С) отвечает боту.** Задан он строкой `Environment=ASK_URL=…` в теле юнита
`1c-mcp-ask.service`; штатный способ переопределить — drop-in:

```bash
systemctl edit 1c-mcp-ask        # [Service] Environment=ASK_URL=http://127.0.0.1:<порт>
systemctl restart 1c-mcp-ask
```

Какую **базу движка** читает сам сервис ответов — задаёт `SERENEDB_DSN_RO`/`RESOLVER_DSN`
в его окружении (`/etc/1c-serene-ask.env`).

⚠ Если выносить `ASK_URL` в `/etc/1c-mcp-ask.env`, то `EnvironmentFile=` в юните надо
поставить **ниже** строки `Environment=`, иначе значение из юнита перекроет env-файл.

*Было ошибочно: «бот переключается одной строкой `BRAINE_URL` в `/etc/1c-mcp-braine.env` —
и так же откатывается обратно». **Чем опровергнуто:** в `/etc/1c-mcp-braine.env` есть только
`BRAINE_TOKEN` и `MCP_TOKEN`, `BRAINE_URL` там нет (он `Environment=` в юните
`1c-mcp-braine`, адрес :8091 никто не слушает); в конфиге бота записи `braine` нет вовсе —
мост выведен из контура. Исполнение прежней инструкции не меняло ничего.*

Гейт `verify-plugin` сверяет числа ответа с данными КОДОМ (`docs/OPENCLAW_BOT.md`).

### 10.8 Проверка
```bash
cd /opt/1c-mcp-reports
export $(grep -E '^(ALIBABA_|EMBED_|PGPASSWORD|RESOLVER_PW)=' /etc/1c-mcp-reports.env | xargs -d '\n')
export SERENEDB_DSN="host=127.0.0.1 port=7890 user=serene_ro dbname=$DB"
export RESOLVER_DSN="host=127.0.0.1 port=7890 user=serene_resolver dbname=$DB"
for t in test_validate test_integrity test_caveat test_ro_role; do python3 $t.py; done   # все PASS
./probe.sh "<вопрос по вашим данным>"       # реальный отчёт через весь путь NL→SQL→exec
```

🔴 **`sql.sh`, `probe.sh` и `test_ro_role.py` читают `dbname=postgres`, и строка подключения
у них зашита в код — окружение они не читают.** На однобазовой установке из этого раздела
это та самая база; но если сервис ответов настроен на другую базу движка (на стенде боевая —
`ut_test`), сверка «ответ бота против ground-truth SELECT» пойдёт **по чужим данным**, и
расхождение будет выглядеть беспричинным. Перед сверкой убедитесь, что база в `sql.sh` та же,
что в `SERENEDB_DSN_RO` отвечающего сервиса.
Сквозная проверка отвечающего сервиса (`8091` — умолчание кода; если задавали
`ASK_LISTEN_PORT`, подставьте свой порт — на стенде это `:8099`):
```bash
curl -s -X POST http://127.0.0.1:${ASK_LISTEN_PORT:-8091}/ask -H 'Content-Type: application/json' \
  ${ASK_TOKEN:+-H "Authorization: Bearer $ASK_TOKEN"} \
  -d '{"question":"<вопрос по вашим данным>"}'
```
Виды ответа: `answer` — ответ с числами из базы; `clarify` — уточняющий вопрос, если прочтений
несколько; `figures` — гейт не пропустил цифру. Догадок нет по построению (п. 12 `TARGET.md`).

### 10.9 Снапшот и восстановление витрины

🔴 **Снапшот и восстановление — на весь инстанс движка, а не на базу.** Каталог
`/var/lib/serenedb` общий: в нём лежат ВСЕ базы движка. `serenedb_backup.sh` останавливает
движок и кладёт `tar.gz` всего каталога (ротация `KEEP=7`); процедура `RESTORE` в шапке того
же скрипта делает `rm -rf /var/lib/serenedb/*` и распаковку. Значит **восстановление одной
базы заменяет и все остальные** состоянием из архива.

На стенде это уже заряженная ловушка: снапшот на диске ровно один,
`serenedb-20260729-044937.tar.gz` от 29.07 04:53, снят **перед** `DROP DATABASE ut_test` /
`CREATE DATABASE` (`PLAN_AUTONOMY`). Восстановить по нему «первую базу» — значит откатить
боевую вторую на трое суток и потерять оплаченные векторы. Обещанный запасной путь
(«витрина производная — ре-синк из 1С») для второй базы недоступен: у неё нет ни юнита, ни
таймера, ни env, а `serene_sync.py` без `SERENEDB_DSN` пойдёт в первую.

**У движка ЕСТЬ штатные средства — три наших документа утверждали обратное, не проверив**
([замер 02.08] на нашей сборке 26.07.3):

| Средство | Что делает (по докам движка) | Что доказано замером |
|---|---|---|
| `COPY FROM DATABASE <src> TO <dst>` | копирует содержимое одной прикреплённой базы в другую | `ERROR: Catalog "zzz_nonexistent_src" does not exist!` — **оператор распознан** |
| `EXPORT DATABASE '<каталог>'` | выгружает схему и данные базы в каталог | `ERROR: Failed to create directory …` — **дошло до исполнения** |
| `IMPORT DATABASE '<каталог>'` | заливает обратно из `schema.sql` + `load.sql` | `ERROR: Cannot open file ".../schema.sql"` |

Контрольный опыт: `EXPORTX DATABASE`, `IMPORTX DATABASE`, `BACKUP DATABASE`,
`RESTORE DATABASE`, `COPY FROM DATABASEX` — **все** дают `syntax error`. Так выглядит
неизвестный оператор, значит три средства выше движок действительно знает.

🔴 **Граница доказанного — не переступайте её при планировании.** Замером подтверждено
только то, что операторы **существуют и доходят до исполнения**. НЕ проверено: работают ли
они на наших объёмах, что именно попадает в выгрузку, и восстанавливается ли база обратно —
round-trip в проекте не делался ни разу. Прежде чем переводить на них резерв, это надо
замерить (вопрос владельцу №46).

⚠ Оффлайн-снапшот пока не отменяется: он снимает каталог целиком, то есть **весь инстанс со
всеми базами разом**, и заведомо включает файлы инвертированного индекса. Покрывает ли их
`EXPORT DATABASE` — **не проверено ни замером, ни доками**: там перечислены «schema
information, tables, views and sequences», про индексы не сказано ни в ту, ни в другую
сторону. *В первой редакции этого раздела (02.08) стояло «которого `EXPORT DATABASE` не
выгружает» — утверждение без доказательства, ровно того класса, который абзацем выше
требует проверки.*

---

## 11. OpenClaw: бот-слой (Telegram + гейт анти-галлюцинаций)

Диалоговая оболочка тона над двумя мозгами: Telegram → OpenClaw (DeepSeek) → `ask_1c` (braine) / `report_1c`
(SereneDB) → **verify-плагин** сверяет числа кодом. Ставится ПОВЕРХ §7-8 (braine) и §10 (SereneDB).
Устройство — `docs/OPENCLAW_BOT.md`. Код — `ubuntu/openclaw/`. 🔴 Только нативное OpenClaw; гарантии — кодом,
не промтом (персона держит только тон).

### 11.1 MCP-сервер `ask_1c` над `serene_ask` (:6016) — с 30.07

🔴 **Прежний мост над braine (:6014) выведен.** Он обращался к `BRAINE_URL=:8090`, а слой braine
выведен из продукта и порт не слушает — [замер 30.07] бот на любой вопрос отвечал «сервер 1С не
отвечает». Это второй раз класс `HOW_NOT_TO §2.14`: вывод компонента не закончен, пока не убраны
его связки. Решение владельца 30.07: новый мост, бот отвечает по второй базе.

```bash
install -d /opt/openclaw-mcp && python3 -m venv /opt/openclaw-mcp/venv
/opt/openclaw-mcp/venv/bin/pip install -r ubuntu/openclaw/requirements.txt   # офиц. MCP SDK
/opt/openclaw-mcp/venv/bin/pip install matplotlib                            # ⬅ отрисовка графиков
install -D ubuntu/openclaw/mcp_ask.py /opt/openclaw-mcp/mcp_ask.py
install -m 644 ubuntu/openclaw/systemd/1c-mcp-ask.service /etc/systemd/system/
# /etc/1c-mcp-ask.env (600): ASK_TOKEN=<токен serene_ask>, MCP_TOKEN=<свой, fail-closed>
systemctl daemon-reload && systemctl enable --now 1c-mcp-ask
```

🔴 **`requirements.txt` неполон, и на этом молча теряется график.** В файле одна строка
`mcp>=1.28`, а в боевом `/opt/openclaw-mcp/venv` стоят ещё `matplotlib`, `numpy`, `pillow`,
`contourpy`, `fonttools`, `kiwisolver`, `cycler` — зависимостями `mcp` они не являются, их
ставили руками. Импорт `matplotlib` ленивый (внутри `render_chart`), а вызов обёрнут в
`except Exception: png = None` — на машине, поставленной строго по прежней редакции этого
руководства, **график просто не появляется, без единого сообщения**. Отрисовка изображений —
один из четырёх пунктов, которые `TARGET.md` разрешает делать своим кодом.

Этот же venv указан в `ExecStart` шести юнитов репозитория (`1c-mcp-ask`, `1c-mcp-braine`,
`1c-mcp-reports`, `1c-serene-ask`, `1c-serene-sync`, `1c-serene-index`) и в `pipeline.sh` и
`probe.sh` — поэтому шаг его создания стоит здесь, а не в выведенном §11.1-старое, где он
лежал раньше. Своего файла зависимостей у `ubuntu/serenedb/` нет вовсе.

Подключение к боту — штатным `mcp.servers`: запись `serene-ask` → `http://127.0.0.1:6016/mcp`,
заголовок `Authorization: Bearer $MCP_TOKEN`, `toolFilter.include = ["ask_1c"]`.
Запись `second-brain` (braine) **удалена**; `second-brain-reports` (:6015) не тронут по слову
владельца («пока не трогать»).

**Чем этот мост отличается по сути:** пробрасывает `focus`, `measure` и `context`, поэтому
работает ЦЕПОЧКА — вопрос → уточнение о сущности → уточнение о величине → ответ. Без этих полей
уточнение было односторонним: сервис спрашивал, а вернуть выбор человека было нечем.

Проверка вживую 30.07: «на какую сумму мы закупили товаров и услуг» → **73 181 157,68 по 249
документам, 4 прогона из 4** (совпадает с живой 1С); «сколько мы продали» → бот **переспросил**
«оптовые или розничные», а не выбрал сам.

### 11.1-старое MCP-сервер `ask_1c` над braine (:6014) — выведен
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
# 🔴 ПЕРСОНА — ТОЛЬКО СКРИПТОМ, не копированием руками.
# [замер 31.07] пока здесь стояло `cp`, персона правилась в репозитории, а бот отвечал по
# копии от 30.07: шаг никто не делал, и правки промта не влияли НИ НА ОДИН ответ, причём
# это ниоткуда не было видно. Скрипт вдобавок убирает стартовые заготовки движка
# (`BOOTSTRAP.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`, `USER.md`) — 6 124 символа в
# системном промте каждый ход, часть прямо против контракта. Разбор — `HOW_NOT_TO §1.27`,
# `§1.28`.
ubuntu/openclaw/deploy_instance.sh
printf '%s' '<TELEGRAM_BOT_TOKEN>' | sudo -u undebot tee /home/undebot/.openclaw/telegram-token >/dev/null
sudo -u undebot chmod 600 /home/undebot/.openclaw/telegram-token
printf 'DEEPSEEK_API_KEY=%s\n' '<ключ>' | sudo -u undebot tee /home/undebot/.openclaw/.env >/dev/null
sudo -u undebot chmod 600 /home/undebot/.openclaw/.env
# ключ провайдера — ТАКЖЕ в auth-store (иначе «No API key found» при явном plugins.allow):
sudo -u undebot openclaw models auth paste-api-key --provider deepseek --profile-id deepseek:default
```

### 11.4 verify-плагин (гейт анти-галлюцинаций, КОДОМ)
```bash
cd ubuntu/openclaw/verify-plugin && node test-verify.mjs      # 52 оффлайн-юнита — все PASS
npm pack --pack-destination /tmp
sudo -u undebot openclaw plugins install npm-pack:/tmp/openclaw-braine-verify-1.0.0.tgz --force
# в openclaw.json уже: plugins.allow += "braine-verify"; entries.braine-verify.enabled=true +
#   hooks.allowConversationAccess=true (иначе хуки к переписке молча не срабатывают)
```

### 11.4-бис Смысловой поиск по вики (с 02.08) — на НАШЕМ эмбеддере

Без этого шаг «перефразирование по вики» возвращает пусто почти на каждом живом вопросе
(буквальный поиск не берёт мешок слов). Разбор — [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md),
раздел про вики.

```bash
# 1) ключ эмбеддера — в штатный env-файл шлюза (600, владелец undebot), НЕ в openclaw.json
printf 'EMBED_API_KEY=%s\n' "$KEY" >> /home/undebot/.openclaw/gateway.systemd.env

# 2) в openclaw.json (пути — те, что принимает схема сборки 2026.7.1-2):
#    agents.defaults.memorySearch = {
#      enabled: true, provider: "openai-compatible", model: "<модель эмбеддера>",
#      remote: { baseUrl: "<адрес>/v1", apiKey: "${EMBED_API_KEY}" },
#      extraPaths: ["<хранилище вики>/entities"]          # без него индекс пуст: 0/0 файлов
#    }
#    plugins.entries."memory-wiki".config.search = { backend: "shared", corpus: "all" }

sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) systemctl --user restart openclaw-gateway
EMBED_API_KEY=$KEY sudo -u undebot -H openclaw memory index --force --agent main
```

🔴 **Три места, где легко ошибиться** (каждое проверено замером 02.08):

- путь настройки — **`agents.defaults.memorySearch`**, а не `memory.search.*` из доков
  движка: последний схема отвергает (`config validate` → `memory: Invalid input`).
  Верный путь называет `openclaw doctor`;
- **`corpus: "all"`**, не `"wiki"`: страницы попадают в индекс как источник `memory`, и с
  `"wiki"` поиск смотрит не в тот корпус — выдача остаётся пустой;
- пересборка индекса **обязательна и вручную**: при смене модели движок ставит векторный
  поиск на паузу и сам не пересобирает.

**Проверка** — только через шлюз или `openclaw memory search`; `openclaw wiki search` из
CLI остаётся буквальным независимо от настройки и покажет «ничего не изменилось»:

```bash
EMBED_API_KEY=$KEY sudo -u undebot -H openclaw memory status --deep   # Indexed: N/N, Semantic vectors: ready
EMBED_API_KEY=$KEY sudo -u undebot -H openclaw memory search "мешок слов из живого вопроса"
```

⚠ `memory-lancedb` установлен, но **выключен**: команда пересборки индекса принадлежит
`memory-core` и работает только при его слоте, а у lancedb в этой сборке нет ни `reindex`,
ни `drop-index`. Пакет остался в `~/.openclaw/npm/projects/`, в контуре не участвует.

### 11.5 Gateway (systemd user-юнит, reboot-safe)
```bash
sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) openclaw gateway install --port 18800
sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) systemctl --user enable --now openclaw-gateway
```

### 11.5-бис ВТОРОЙ БОТ НА ДРУГУЮ БАЗУ — ✅ СДЕЛАНО 02.08

🔴 **Это не план, а описание работающего.** `[замер 02.08]` второй бот поднят и отвечает:

| | боевой (вторая база) | второй (первая база) |
|---|---|---|
| бот | `@test1c_mcp_bot` | **`@Test11c_bot`** |
| база движка | `ut_test` | `postgres` |
| сервис ответов | :8099 | :8091 |
| мост MCP | `1c-mcp-ask` :6016 | **`1c-mcp-ask@postgres` :6017** |
| шлюз | `openclaw-gateway` :18800 | **`openclaw-gateway-buh` :18830** |
| каталог состояния | `~/.openclaw` | `~/.openclaw-buh` |
| хранилище вики | `~/.openclaw/wiki/main`, 697 страниц, отметка `ut_test` | `~/.openclaw-buh/wiki/buh`, **178 страниц, отметка `postgres`** |
| гейт `braine-verify` | загружен, 5 хуков | **загружен, 5 хуков** |

**Проверка, ради которой всё делалось:** «Сколько банков в Казани?» второму боту →
**«В Казани 37 банков»**. 37 — эталон **первой** базы из приёмочного набора
(`ab-gold.tsv`), то есть бот ответил по своей базе, а не по чужой. Оговорка о старении
данных пришла вместе с ответом.

Ниже — как это делается, шаг за шагом.

**Зачем.** У каждой базы 1С свой контур целиком: свой шлюз OData, своя база внутри движка,
свой сервис ответов. Бот — последнее звено, и у него та же логика: **свой бот на базу**.
Иначе один бот отвечает по одной базе, а вики (словарь «как это называется здесь»)
получается общей на две — и он перефразирует вопрос именами чужой конфигурации.

**Почему именно отдельный экземпляр, а не второй агент внутри одного.** В сборке
`2026.7.1-2` вики-хранилище **одно на процесс**, разделить его по агентам нечем: у плагина
в коде `strictObject({path, renderMode})`, в схеме у `agents.list[]` стоит
`additionalProperties: false` и ключа для плагинов там нет. Штатный способ — **профиль**:
отдельный экземпляр gateway со своим конфигом, каталогом состояния, портом и ботом
(`multiple-gateways.md:38-46`). Заодно изоляция инструментов выходит **по построению**: у
каждого экземпляра свой `mcp.servers`, то есть бот одной базы физически не видит мост
другой — а не «настроен не видеть».

**Что уже есть.** Боты заведены владельцем 02.08: `@Test11c_bot` — **первой** базе
(`postgres`, Бухгалтерия), `@Test21c_bot` — в запас. Нынешний `@test1c_mcp_bot` работает по
**второй** базе (`ut_test`) и не трогается: второй экземпляр поднимается **рядом**, а не
вместо. Токены — `/etc/1c-telegram-test1.token` и `/etc/1c-telegram-test2.token`, права
600, владелец `undebot`.

#### Шаг 1. Свой мост MCP на эту базу

Сейчас `1c-mcp-ask.service` — **один экземпляр** с зашитыми `ASK_URL=http://127.0.0.1:8099`
и `MCP_PORT=6016`, то есть намертво привязан ко второй базе. Его надо сделать шаблоном —
ровно так же, как это уже сделано для сервиса ответов (`1c-serene-ask@<база>`):

Шаблон заведён: `ubuntu/openclaw/systemd/1c-mcp-ask@.service` (в юните не зашито ничего
про конкретную базу). Побазовый `/etc/1c-mcp-ask-<база>.env`, права 600:

```bash
# ASK_URL=http://127.0.0.1:8091   — сервис ответов ЭТОЙ базы (первая :8091, вторая :8099)
# MCP_PORT=6017                   — порт ЭТОГО моста; свой у каждой базы
# ASK_TOKEN=<Bearer сервиса ответов>   MCP_TOKEN=<свой, генерируется>
install -m 644 ubuntu/openclaw/systemd/1c-mcp-ask@.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now 1c-mcp-ask@postgres
```

#### Шаг 2. Свой экземпляр бота

```bash
UD="sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot)"
$UD openclaw --profile buh gateway install --port 18830   # порт НЕ ближе чем на 20 к 18800
$UD systemctl --user enable --now openclaw-gateway-buh
```

🔴 **Четыре грабли этого шага, каждая поймана на живом стенде** `[замер 02.08]`:

- **плагины ставятся в каталог состояния профиля, а не глобально.** Новому экземпляру
  нужны свои `deepseek` и — обязательно — **гейт `braine-verify`**: без него второй бот
  остался бы без защиты от выдуманных чисел. `openclaw --profile buh plugins install …`;
- 🔴 **npm отдаёт из кэша пакет той же версии.** Плагин сегодня менялся, а версия
  оставалась `1.0.0` — в профиль встал **старый** гейт (7 ключей в манифесте вместо 17), и
  конфиг из-за этого не проходил проверку. Лечится единственно правильно: **поднять версию
  пакета**, раз содержимое изменилось (теперь `1.1.0`). Если кэш всё равно отдаёт старое —
  удалить каталог `~/.openclaw-<профиль>/npm/projects/<пакет>` и поставить заново;
- **установщик юнита переписывает `gateway.systemd.env`** — ключи, положенные туда заранее,
  пропадают. Класть их **после** `gateway install`, а `EnvironmentFile` подключать
  drop-in'ом (`ubuntu/openclaw/systemd/openclaw-gateway-buh.service.d/env.conf`): он
  переживёт переустановку юнита;
- **учётные данные модели — свои у каждого профиля** (`agentDir` не общий). Без
  `DEEPSEEK_API_KEY` в его env бот отвечает `No API key found for provider "deepseek"`.

При неудачных стартах срабатывает предохранитель («restart-loop breaker») — после починки
`systemctl --user reset-failed openclaw-gateway-buh`, иначе служба не поднимется.

Профиль даёт своё: файл конфигурации (`~/.openclaw-buh/openclaw.json`), каталог состояния,
рабочую папку, имя службы, порт и токен бота. Дальше в **его** конфиге:

```json5
{
  channels: { telegram: { enabled: true, tokenFile: "/etc/1c-telegram-test1.token" } },
  mcp: { servers: { "serene-ask": { url: "http://127.0.0.1:<порт моста шага 1>/mcp" } } },
  plugins: { entries: { "memory-wiki": { config: {
    vault: { path: "/home/undebot/.openclaw-buh/wiki/buh" },   // 🔴 ЗАДАТЬ ЯВНО
  } } } },
  agents: { defaults: { memorySearch: {
    enabled: true, provider: "openai-compatible", model: "<модель эмбеддера>",
    remote: { baseUrl: "<адрес>/v1", apiKey: "${EMBED_API_KEY}" },
    extraPaths: ["/home/undebot/.openclaw-buh/wiki/buh/entities"],
  } } },
}
```

🔴 **`vault.path` задать ОБЯЗАТЕЛЬНО.** Путь по умолчанию считается от домашнего каталога,
а **не** от каталога состояния профиля (`dist/config-BRlVcj4J.js:84-86`). Без явного пути
второй бот будет писать в то же `~/.openclaw/wiki/main`, что и первый, — две вики сольются
в одну **молча**, и ни одна диагностика этого не покажет: путь ведь валидный.

Ключ эмбеддера — в `gateway.systemd.env` этого профиля (600), как в §11.4-бис.

#### Шаг 3. Наполнить его вики страницами ЕГО базы

```bash
SERENEDB_DSN="host=127.0.0.1 port=7890 user=postgres dbname=postgres" \
WIKI_VAULT=/home/undebot/.openclaw-buh/wiki/buh \
OPENCLAW_PROFILE_ID=buh \
  ./wiki_publish.sh
```

🔴 **`OPENCLAW_PROFILE_ID` обязателен.** Без него скрипт запишет страницы в **это**
хранилище, а `wiki compile` и переиндексацию выполнит в экземпляре **по умолчанию** — обе
стороны при этом выглядят исправными, а бот ищет по чужому индексу. Поймано на этом самом
развёртывании до того, как навредило.

Скрипт сам поставит отметку `.built-from` с именем базы и на следующих тактах **не пустит**
в это хранилище другую базу. Он же удалит страницы, которых в базе больше нет, и
переиндексирует вики — без этого смысловой поиск ищет по прошлому такту.

#### Шаг 3-бис. Персона и нейтрализация чужих заготовок

🔴 **Без этого шага бот работает с ЧУЖИМИ инструкциями.** Свежий экземпляр получает от
движка свой `AGENTS.md` и полный набор заготовок (`SOUL.md`, `BOOTSTRAP.md`, `TOOLS.md`,
`USER.md`, `IDENTITY.md`) — 6 124 символа в промте каждый ход, и часть из них прямо
против контракта: `SOUL.md` велит «come back with answers, not questions», тогда как
указание владельца — «лучше 1, 2, 3 раза уточнить, чем дать не то» (п. 12).

```bash
OPENCLAW_PROFILE_ID=buh OPENCLAW_ASK_UNIT=1c-mcp-ask@postgres \
  ./deploy_instance.sh          # DRY_RUN=1 — посмотреть, ничего не меняя
```

`deploy_instance.sh` с 02.08 работает с любым экземпляром: `OPENCLAW_PROFILE_ID` задаёт
каталог состояния, из него выводятся рабочая папка и каталог плагина;
`OPENCLAW_ASK_UNIT` — какой мост перезапустить.

⚠ **Новому боту достаётся персона из репозитория** (`instance/AGENTS.md`), а не та, что
лежит в рабочей папке боевого. Это осознанно: боевая персона содержит имена **чужой для
него конфигурации** (развилка `№45`), и на базе другой конфигурации она вредна.

#### Шаг 4. Проверка

```bash
UDB="sudo -u undebot XDG_RUNTIME_DIR=/run/user/$(id -u undebot) openclaw --profile buh"
$UDB gateway status --deep
$UDB openclaw wiki status        # Vault должен быть СВОЙ, не ~/.openclaw/wiki/main
cat /home/undebot/.openclaw-buh/wiki/buh/.built-from     # имя его базы
# и главное — вопрос в его Telegram: ответ должен считаться по ЕГО базе
```

⚠ `openclaw gateway probe` покажет «multiple reachable gateway identities detected» — это
ожидаемо при двух экземплярах (`multiple-gateways.md:137`), а не ошибка.

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
- **OpenClaw бот-слой (§11):** движок 2026.7.1-2 под `undebot` (linger); оба MCP (`ask_1c`:6014, `report_1c`:6015, `mcp probe` = 1 tool); verify-плагин (52 юнита) `enabled`, гейт на РЕАЛЬНОЙ Telegram-доставке: обоснованное число → прошло, выдуманное → заменено/срезано — ✅.
- Zero-touch: все system-сервисы enabled; OpenClaw user-юнит + linger; IIS Automatic — ✅.
- **Повторная проверка Windows-канала (2026-07-24, read-only):** W3SVC Running/Automatic; опубликована
  `buh_test`, `standardOdata enable=true` (poolSize 10); платформа 8.3.27.1786; AppPool 32-bit=True; данные
  идут через шлюз ($count Валюты/Организации/Контрагенты), POST→405 — ✅. (Данных мало — база пуста по документам.)
