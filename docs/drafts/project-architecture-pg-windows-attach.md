---
name: project-architecture-pg-windows-attach
description: ЧЕРНОВИК для owner-memory — заменяет memory_bank/owner-memory/project-architecture-pg-windows-attach.md (каталог закрыт на запись claudedev). Применить владельцу.
metadata:
  draft_for: memory_bank/owner-memory/project-architecture-pg-windows-attach.md
  superseded_by_decision: 2026-08-22 (PLAN_UPGRADE_NATIVE.md §0)
---

# ОТМЕНЕНО 22.08.2026 — решение 26.07 больше не действует

**Было (26.07):** сырые данные 1С — в PostgreSQL на Windows; SereneDB на Ubuntu держит
только корпус и индекс через `postgres_attach` + `VIEW`.

**Стало (22.08, решение владельца):** «сырое хранилище на Windows — неактуально, база
хранится у нас». Продукт целиком на SereneDB: витрина, корпус и индекс — **родные таблицы**
на нашей стороне (`serene_sync.py` → `127.0.0.1:7890`). Схема `ATTACH (TYPE postgres,
READ_ONLY)` **не** целевая и **не** используется в пайплайне.

## Что остаётся из старого решения (история, не цель)

- Эксперимент 25.07: PostgreSQL 17.6 headless на Windows рядом с 1С — см. `docs/INSTALL_LOG.md`.
- `/etc/1c-pg-windows.env` — реквизиты того контура; **сирота** (ни код, ни юниты не читают).
- **[действие владельца, в работе]:** остановить/удалить PG на Windows; снести env на Ubuntu;
  обновить `TARGET.md` п.4/16 только если владелец меняет контракт.

## PG-протокол ≠ PostgreSQL как компонент

SereneDB отвечает по wire-протоколу PostgreSQL для клиентов (`psql`, Grafana datasource,
OWUI SQL). Это интерфейс движка, не отдельная СУБД в продукте (`data_directory` пуст,
`pg_extension` пуст, хранилище `store.db` — [замер 22.08]).

Связано: [[feedback-data-placement-is-owner-decision]] — размещение данных по-прежнему
решение владельца; с 22.08 актуальное размещение — SereneDB у нас, не PG на Windows.
