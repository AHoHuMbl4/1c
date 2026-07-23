# Tech Context

Полная архитектура — `docs/ARCHITECTURE.md`; раскатка — `docs/RUNBOOK_DEPLOY.md`.
Здесь — окружение, машины, доступы и готчи автоматизации (важно для будущих сессий).

## Машины
- **LXC `lxc-claude-1c` `192.168.56.42`** (Ubuntu 24.04, 6 CPU, 62 GB RAM, ~238 GB своб.,
  Python 3.12) — весь наш код: OData-шлюз, ETL, config-ui, braine. Доступ `root@192.168.56.42` по ключу.
- **Windows-стенд `10.8.0.58`** (Win11, 2 CPU, 8 GB, PowerShell 5.1) — 1С + IIS.
  Доступ `ssh unde@10.8.0.58`. IIS-адрес для проброса — `192.168.122.141:80`.
  ⚠ Диск ~60 GB, тесно (загрузки владельца). Раскладка: `C:\1c\{repo,bases,backups,distr,logs}`,
  `C:\inetpub\1c` (публикация IIS).
- **Роутер `192.168.56.1`** (владельца) — проброс порта на Windows-IIS:80. LXK ходит на
  1С через `192.168.56.1:<порт>`.
- Продакшн у клиента — 1С:ERP «производство»; к ней НЕ подключаемся, пока не отработано на стенде.

## Стенд (готово)
- Платформа 1С **8.3.27.1786 x86** (компоненты: клиенты, конфигуратор, сервер, консоль,
  веб-расширение wsisapi.dll). Комьюнити-лицензия активирована.
- База **Бухгалтерия 3.0.190.11** → `C:\1c\bases\buh_test` (файловая). Первый бэкап есть.
- Опубликована на IIS, OData включён, состав — все справочники+документы; пользователи
  `admin` + `ai_reader` (Только просмотр).

## Доступ по SSH
Ключ Claude (dedicated): `~/.ssh/id_ed25519_1c`. `ssh -i ~/.ssh/id_ed25519_1c <user>@<host>`.
На Windows ключ — в `C:\ProgramData\ssh\administrators_authorized_keys`.

## ⚠ Готчи автоматизации Windows по SSH (сэкономят часы)
- Длинные PowerShell по SSH — только `powershell -EncodedCommand` (base64 UTF-16LE) ИЛИ
  `scp` файла + `-File`. Экранирование bash→cmd ломает `$`/кавычки/кириллицу; лимит cmd ~8191.
- `.ps1` с кириллицей — UTF-8 **с BOM** (PS 5.1 без BOM = ANSI → синтакс-ошибки).
- COM-коннектор: `regsvr32 comcntr.dll` из каталога `bin` платформы; класс `V83.COMConnector`;
  вызывать из **32-битного** PowerShell (`C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`).
- COM-квирк: свойства (`Metadata`) отдаются только рефлексией; методы коллекций метаданных
  (`Найти`/`Count`) НЕ резолвятся, но **`foreach` по коллекции работает** (так задавали состав OData).

## Ключи и секреты (все в `credentials/`, вне git)
- `deepseek.env` (генерация), `alibaba.env` (DashScope — эмбеддинги/реранк),
  `gitlab-1c-test.env` (KB-репо money/1c-test id 95), `telegram-1c-bot.env` (@test1c_mcp_bot + owner id 5949699699),
  `mcp-toolkit.env` (dev). На LXC — `/etc/1c-odata-gateway.env`, `/etc/1c-etl.env`, `/etc/1c-etl-selected.txt` (chmod 600).
- Пароли 1С (`admin`/`ai_reader`) — у владельца; ai_reader — в `/etc/1c-odata-gateway.env`.
- ⚠ Приватность: DeepSeek/DashScope облачные — на проде с реальными данными решить (self-host vs компромисс).

## Инвариант и правила
- 1С только читаем (два слоя: `ai_reader` + GET-only шлюз). Перед изменением базы — бэкап.
- На серверах менять состояние только по явной инструкции владельца.
