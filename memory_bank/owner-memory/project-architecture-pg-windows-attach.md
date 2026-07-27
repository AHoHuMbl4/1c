---
name: project-architecture-pg-windows-attach
description: РЕШЕНИЕ ВЛАДЕЛЬЦА 26.07.2026 — сырые данные 1С живут в PostgreSQL на Windows; SereneDB на Ubuntu держит только корпус+индекс через postgres_attach + VIEW
metadata: 
  node_type: memory
  type: project
  originSessionId: 256f2cba-c821-4a35-a845-ef328eb373e1
  modified: 2026-07-26T15:39:02.557Z
---

Решение владельца 2026-07-26 (выбор из трёх вариантов, явный): **PG на Windows + attach**.

Целевая схема:
- PostgreSQL на Windows-машине рядом с 1С (эксперимент 25.07: +8% к задержке 1С, 128 МБ);
- загрузчик остаётся на Ubuntu, пишет из OData в PG-на-Windows по сети;
- SereneDB: `ATTACH (TYPE postgres, READ_ONLY)` → `CREATE VIEW` (NUMERIC→DOUBLE) →
  корпус и индекс строятся с VIEW; сырых таблиц-копий в SereneDB быть не должно;
- индекс на VIEW обязателен (на attach-таблицу транслируется в btree — docs/SERENEDB.md);
- правда ab_scorer считается по attach-таблицам.

Открытый вопрос коробки: автоматическая установка PG на Windows (две попытки без RDP
неудачны — docs/INSTALL_LOG.md); владелец знает про конфликт с правилом двух ручных
действий и выбрал сознательно.

Связано: [[feedback-data-placement-is-owner-decision]].
