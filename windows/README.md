# Windows-сторона: 1С + IIS + OData (канал чтения)

Машина, где живёт 1С и откуда «второй мозг» читает данные. Отдаёт данные **только на чтение** через
штатный OData 1С на IIS; всё, что дальше (шлюз, ETL, витрина, бот) — на Ubuntu LXC.

> **Как это настраивается пошагово (установка платформы → база → пользователи → IIS → публикация OData →
> read-only) — `docs/RUNBOOK_DEPLOY.md §1-6`.** Как работает в общей картине — `docs/ARCHITECTURE.md §2-3`.
> Готчи автоматизации Windows по SSH (BOM/EncodedCommand/COM) — `RUNBOOK §2` и `memory_bank/techContext.md`.

## Что здесь настроено и работает (проверено live 2026-07-24)
- **Платформа 1С 8.3.27.1786** (x86), файловые базы в `C:\1c\bases\` (`buh_test`, `bld`).
- **IIS (служба W3SVC) = Running / Automatic** — публикует базу; авто-старт, переживает ребут.
- **Опубликована `buh_test`** → `C:\inetpub\1c\default.vrd`: `standardOdata enable="true"`
  (`/1c/odata/standard.odata/`, poolSize 10, reuseSessions autouse). AppPool `enable32BitAppOnWin64=True`
  (под x86-платформу). *(В vrd также `analytics enable="true"` — штатный эндпоинт 1С, нашим стеком НЕ
  используется; читаем только `standardOdata`.)*
- **Read-only — слой 1:** пользователь **`ai_reader`** (профиль «Только просмотр»); OData ходит под ним
  (Basic auth). Читает 200, пишет → отказ прав. Слой 2 (GET-only шлюз) — на LXC (`RUNBOOK §6`).
- **Проверено сквозь канал (через шлюз :6011 на LXC):** реальные `$count` идут (Валюты/Организации/
  Контрагенты), запись (POST) режется 405 до 1С. Данных мало — база тестовая, пустая по документам.

## Раскладка на машине
```
C:\1c\
  repo\      — клон этого репозитория (git pull для обновления скриптов)
  bases\     — файловые базы 1С (buh_test — опубликована в OData; bld)
  backups\   — zip-бэкапы баз (ротация, последние 14)
  distr\     — дистрибутивы (платформа 1С и т.п.)
  logs\      — логи скриптов
C:\inetpub\1c\default.vrd — публикация IIS (какая база + OData enable)
```

## Доступ и адреса
- **SSH Claude:** `ssh unde@10.8.0.58` (ключ `claude-1c` в `administrators_authorized_keys`; из среды на VPN).
  Длинные команды — `powershell -EncodedCommand` (base64 UTF-16LE, вывод в UTF-8), иначе кириллица бьётся.
- **Адреса машины:** `10.8.0.58` (wg0/VPN — SSH) + `192.168.122.141` (LAN — где слушает IIS:80).
- **LXC → 1С:** LXC не видит Windows напрямую; ходит через проброс на роутере
  `192.168.56.1:6003 → 192.168.122.141:80` (это `ODG_UPSTREAM` шлюза). Прямой путь только read-only GET.

## Правила
- 🔴 **1С только читаем.** Состояние Windows/базы меняем ТОЛЬКО по явной инструкции владельца
  (читать/инвентаризировать — можно).
- **Перед любым изменением базы/конфигурации — бэкап:**
  `powershell -NoProfile -File C:\1c\repo\windows\scripts\backup-1c.ps1 -BasePath C:\1c\bases\<база>`.
- Скрипты живут в репозитории (`windows/scripts/`), на машину попадают через `git pull` в `C:\1c\repo`.
- `windows/fork/` — dev-форк MCP-тулкита (НЕ для прода, `RUNBOOK` Приложение); канал прода = OData/IIS.
