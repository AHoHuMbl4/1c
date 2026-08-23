---
name: project-architecture-pg-windows-attach
description: РЕШЕНИЕ ВЛАДЕЛЬЦА 22.08.2026 — PG-слой выведен; сырые данные 1С на Windows рядом с 1С (OData); корпус и индекс — родные таблицы SereneDB на Ubuntu
metadata:
  node_type: memory
  type: project
  originSessionId: 256f2cba-c821-4a35-a845-ef328eb373e1
  modified: 2026-08-23T00:00:00.000Z
---

## Статус: решение 26.07 **отменено** решением 22.08

**Было (26.07):** PostgreSQL на Windows + `postgres_attach` → VIEW → корпус/индекс в SereneDB.

**Стало (22.08, владелец):** «сырое хранилище на Windows — неактуально, **база хранится у нас**».
Отдельного PostgreSQL в целевой схеме **нет** — ни на Windows, ни как слой продукта.

Источники: CHANGELOG 22.08 «сырое хранилище на Windows отменено»;
`docs/ARCHITECTURE.md` §0; `docs/PLAN_UPGRADE_NATIVE.md` §0.

---

## Целевая схема (актуальная)

| Слой | Где | Что делает |
|---|---|---|
| **1С** | Windows, рядом с данными клиента | Штатная СУБД 1С; **только читаем** через OData (IIS, :6011 и т.п.) |
| **OData-шлюз** | Ubuntu | GET-only прокси к 1С; запись в 1С запрещена |
| **SereneDB** | Ubuntu (`127.0.0.1:7890`, `store.db`, `--server_directory`) | **Единственная БД продукта:** сырые витрины, корпус, индекс, векторы, ответы. PG-протокол — только интерфейс клиентов (`psql`, Grafana), не отдельный PostgreSQL |
| **PostgreSQL** | — | **Не используется.** На dev `:5432` — наследие braine (снос Ф3). На Windows `:5432` — не в работе. `/etc/1c-pg-windows.env` — сирота |

Пайплайн: OData → `serene_sync` / packet → **родные таблицы SereneDB** → `corpus_build` / IVF / `serene_ask`.
`ATTACH (TYPE postgres, READ_ONLY)` и VIEW поверх чужого PG **не** применяются.

---

## Что осталось от старой схемы (наследие, не цель)

- Файл `/etc/1c-pg-windows.env` — ни один юнит репозитория не читает (grep 22.08).
- Имена инстансов `@postgres` в systemd — **dbname SereneDB**, не СУБД PostgreSQL.
- Зачёркнутые формулировки в `docs/ARCHITECTURE.md` — история, не инструкция к развёртыванию.

---

## Открытые хвосты (не этот файл)

- Снос пакетов `postgresql-16*` на dev — root-скрипт `work/root-tasks/02-purge-pg.sh`.
- Перевод эмбеддера на Qwen3-Embedding-4B на всех хостах — Ф4.
- Полный пересчёт векторов после смены модели — `EMBED_RESET=1`, отдельный заход.

Связано: [[feedback-data-placement-is-owner-decision]].
