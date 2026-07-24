# SereneDB — установка ДВИЖКА (self-host)

SereneDB — search+analytics БД (полнотекст + вектор + колоночный OLAP) с **Postgres-протоколом**,
Apache-2.0 (single-node). У нас — движок витрины/аналитики над данными 1С.

> Здесь — только установка **движка**. Развёртывание слоя аналитики (роли, загрузка витрины, отчёты,
> подключение НОВОЙ 1С-базы) — **`docs/RUNBOOK_DEPLOY.md` §10**. Как всё устроено — `docs/SERENEDB.md`.

## Раскатка (что сделано на .42, версия 26.07.3)
Ставим **бинарём + systemd** (без `curl|sh`, консистентно со стеком; docker на боксе нет).

```bash
# 1) артефакт (linux amd64 tarball) с GitHub releases
curl -fsSL -o /tmp/serenedb.tgz \
  https://github.com/serenedb/serenedb/releases/download/v26.07.3/serenedb-26.07.3-linux-amd64.tar.gz
mkdir -p /opt/serenedb-dist && tar xzf /tmp/serenedb.tgz -C /opt/serenedb-dist
SRC=/opt/serenedb-dist/serenedb-26.07.3-linux-amd64   # раскладка usr/etc/var

# 2) юзер, бинарь, конфиг, данные
useradd --system --no-create-home --shell /usr/sbin/nologin serenedb
install -m0755 $SRC/usr/bin/serened /usr/local/bin/serened
mkdir -p /etc/serenedb /var/lib/serenedb
install -m0644 serened.conf /etc/serenedb/serened.conf   # loopback:7890, data=/var/lib/serenedb
chown -R serenedb:serenedb /var/lib/serenedb

# 3) сервис (enabled = reboot-safe)
install -m0644 serenedb.service /etc/systemd/system/serenedb.service
systemctl daemon-reload && systemctl enable --now serenedb.service
```

## Проверка
```bash
systemctl is-active serenedb        # active
ss -tlnp | grep 7890                # LISTEN 127.0.0.1:7890 (loopback)
psql "host=127.0.0.1 port=7890 user=postgres" -c "select version();"   # PostgreSQL 18.3 (SereneDB 26.07.3)
```

## Заметки
- **Только loopback** (`127.0.0.1:7890`), под юзером `serened` (не root). Наружу НЕ выставлять без
  `--hba_config`/`--auth_*`/`--tls_*` — по умолчанию доступ без пароля на loopback (как локальный PG).
- Данные — `/var/lib/serenedb` (persistent; проверено: переживают рестарт сервиса).
- Логи — `journalctl -u serenedb`. Под капотом DuckDB (OLAP) — `select * from duckdb_logs()`.
- **Бэкап:** оффлайн-снапшот `/var/lib/serenedb` (`serenedb_backup.sh`) + первичное восстановление =
  ре-синк из 1С (витрина производная). Штатный online-backup/PITR — вопрос фаундерам (`docs/SERENEDB.md`).
- Загрузку витрины и всё приложение поднимает **`docs/RUNBOOK_DEPLOY.md` §10** (не вручную SQL).
