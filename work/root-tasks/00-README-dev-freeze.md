# Заморозка и чистка локального dev SereneDB (25.08)

Решение владельца 25.08: локальный dev тормозим и замораживаем; работа идёт на
okna и klient1. Скрипты ниже — **только для этой машины** (`/srv/1c` в LXC),
запуск **от root**. Подготовка сессией claudedev; исполнение — владелец.

Связанный разбор зависания: `docs/DEV_ENGINE_HANG_2026-08-25.md`.
Свод замков: `docs/LOCKS_SWEEP_2026-08-25.md`.

---

## Стоп-сигнал пересечения путей

**Нет.** На замере 25.08:

- `/var/lib/serenedb` — локальный btrfs rootfs контейнера (`/dev/loop3[…/lxc-claude-1c]`), не NFS/CIFS;
- все `SERENEDB_DSN` / `CSV_DIR` в `/etc/1c-*.env` указывают на `127.0.0.1:7890` и локальные
  `CSV_DIR=/var/lib/serenedb` или `…/csv-ut_test`;
- строк с хостами okna / klient1 в `/etc/1c-*.env` нет.

Имя пути `/var/lib/serenedb` на okna и klient1 **совпадает по строке**, но это
**другие машины** со своими дисками. Чистка на этом хосте их не трогает.
Скрипты при сетевой ФС или при появлении okna/klient в env — выходят с ошибкой STOP.

---

## Группы в `/var/lib/serenedb` (замер 25.08, `du`)

Всего каталог ≈ **23.9 ГиБ** (округлённо 24 ГБ).

| Группа | Размер | Что это | Если удалить | Восстановимо? |
|---|---:|---|---|---|
| `f1-export-prod/` | **11.3 ГиБ** | снимок `EXPORT DATABASE` (Ф1, 22.08) | пропадает готовый import-набор для песочницы/миграции | да: заново `EXPORT DATABASE` с живого движка |
| `engine_duckdb/` (`store.db`+wal) | **10.1 ГиБ** | данные движка | витрина/корпус/индексы SQL пропадут | нет «быстро»: только ре-синк из 1С + пересборка слоя (часы) или restore бэкапа |
| корневые `*.csv` | **0.80 ГиБ** | промежуточные выгрузки синка (1767 файлов с ~30.07) | такт/синк пишет заново при следующем прогоне | да, тактом/`serene_sync` |
| `ut/` | **0.76 ГиБ** | старый каталог CSV второй базы | то же | да |
| `csv-ut_test/` | **0.70 ГиБ** | `CSV_DIR` для `ut_test` | то же | да |
| `engine_search/` | **0.15 ГиБ** | файлы поискового движка | поиск сломается до пересборки индекса | частично: `1c-serene-index` / build, нужен живой store |
| `packet-meta/` | **0.02 ГиБ** | мета пакетного контура | onboard/apply локальных баз | из inbox/пакетов, не «CSV такта» |
| прочее (bench, wiki-alias-*) | ≈0 | временное | без эффекта на бой | да |

**Безопасно освободить скриптом 06** (только восстановимое):  
`f1-export-prod` + корневые csv + `ut/` + `csv-ut_test/` ≈ **13.6 ГиБ**.

Движок (`engine_duckdb`, `engine_search`) скрипт **не** удаляет.

---

## Кто пишет / читает этот каталог (dev)

| Источник | Роль |
|---|---|
| `serenedb.service` (`--server_directory=/var/lib/serenedb`) | читает/пишет `engine_duckdb`, `engine_search` |
| `/etc/1c-serene-sync.env` `CSV_DIR=/var/lib/serenedb` | синк → корневые csv |
| `/etc/1c-serene-pipeline-postgres.env` `CSV_DIR=/var/lib/serenedb` | такт первой базы |
| `/etc/1c-serene-pipeline-ut_test.env` `CSV_DIR=…/csv-ut_test` | такт ut_test |
| `ubuntu/serenedb/{poc_load_entity,build,wiki_alias,branch_alias,solr_synonyms_*}.sh|py` | читают `CSV_DIR` (умолчание `/var/lib/serenedb`) |
| ask/mcp (`1c-serene-ask@*`, `1c-mcp-ask@*`, `1c-mcp-reports`) | SQL к `:7890`, не пишут csv на диск |
| `1c-packet-apply` | SQL в витрину через DSN на `:7890` |

---

## Порядок запуска

```bash
cd /srv/1c/work/root-tasks
chmod +x 05-dev-freeze.sh 06-dev-disk-cleanup.sh
```

### 1. Предпросмотр заморозки (без изменений)

```bash
DEV_FREEZE_DRY_RUN=1 ./05-dev-freeze.sh
```

### 2. Заморозка (stop + disable, без удаления файлов)

```bash
./05-dev-freeze.sh
```

Останавливает и где возможно отключает автозапуск **поимённо**:

- таймеры: `1c-bot-monitor.timer`, `1c-packet-apply.timer`,
  `1c-serene-pipeline@ut_test.timer`, `1c-serene-pipeline@postgres.timer`,
  `1c-serene-pipeline.timer`, `1c-serene-sync.timer`, `1c-serene-index.timer`
- сервисы: `1c-bot-monitor.service`, `1c-serene-ask@postgres.service`,
  `1c-serene-ask@ut_test.service`, `1c-mcp-ask@postgres.service`,
  `1c-mcp-ask@ut_test.service`, `1c-mcp-reports.service`,
  `1c-wiki-alias.service`, `1c-branch-alias.service`,
  `1c-serene-pipeline@postgres.service`, `1c-serene-pipeline@ut_test.service`,
  `1c-serene-sync.service`, `1c-serene-index.service`,
  `1c-packet-apply.service`, `serenedb.service`

Не трогает: `1c-packet-server`, `1c-odata-gateway*`, `1c-config-ui`,
`1c-gate-tunnel*`, `1c-openclaw-gateway-restart`, `1c-etl*`.

### 3. Холостая чистка (печать плана)

```bash
./06-dev-disk-cleanup.sh
```

### 4. Реальная чистка (~13.6 ГиБ)

```bash
CONFIRM_DEV_DISK_CLEANUP=YES ./06-dev-disk-cleanup.sh
```

---

## Ручной снос данных движка (не скрипт)

Только осознанно, **после** `05-dev-freeze.sh`, если база на dev больше не нужна:

```bash
# точные пути на этом хосте:
rm -rf -- /var/lib/serenedb/engine_duckdb /var/lib/serenedb/engine_search
# полный снос всего каталога (включая packet-meta) — ещё жёстче:
# rm -rf -- /var/lib/serenedb/*
```

Восстановление после полного сноса — ре-синк/пакетный контур + пересборка индекса,
либо restore из бэкапа (`ubuntu/serenedb/serenedb_backup.sh`). Без бэкапа данные
движка **безвозвратны** относительно текущего `store.db`.

---

## Как вернуть dev

```bash
systemctl enable --now serenedb.service
# дождаться SELECT 1 на :7890, затем:
systemctl enable --now 1c-serene-ask@postgres.service
systemctl enable --now 1c-serene-ask@ut_test.service
systemctl enable --now 1c-mcp-ask@postgres.service
systemctl enable --now 1c-mcp-ask@ut_test.service
systemctl enable --now 1c-mcp-reports.service
systemctl enable --now 1c-packet-apply.timer
systemctl enable --now 1c-bot-monitor.timer
# такт по готовности (не по часам), при необходимости:
systemctl enable --now 1c-serene-pipeline@ut_test.timer
```

Wiki/branch-alias и sync/index — по нужде (`systemctl start …`), они были disabled/static.

---

## Предупреждение про замки

После заморозки **9 live-замков** из `docs/LOCKS_SWEEP_2026-08-25.md` остаются
без живого контура на этом хосте (и так не были зачтены 25.08 из‑за timeout
`SELECT 1` на `:7890`). Оффлайн **2150/0** от заморозки не зависят. Живые пробы
и приёмка — на okna / klient1.
