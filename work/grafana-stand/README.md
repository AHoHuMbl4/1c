# Пробный стенд Grafana (дашборды)

Один скрипт: `setup-grafana-stand.sh` — поднимает Grafana OSS в юзерспейсе,
подключает к SereneDB (роль `serene_ro`) и создаёт демо-дашборд через API.

Зачем и что проверено — в [`docs/DASHBOARD_GRAFANA.md`](../../docs/DASHBOARD_GRAFANA.md).

```bash
bash work/grafana-stand/setup-grafana-stand.sh   # поднять/пересоздать
kill $(cat /dev/shm/grafana-stand/grafana.pid)   # остановить
```

Сквозной вход (без формы логина): `[auth.jwt]` включён в конфиге стенда,
RSA-ключи генерятся при первом запуске. Ссылка-вход:

```bash
python3 work/grafana-stand/mint-jwt.py --email ivan.petrov@example.org --name "Иван"
# → http://127.0.0.1:3001/d/stand-from-chat?auth_token=…  (логинит первый запрос;
#   постоянный вход — через cookie→header на прокси, см. docs/DASHBOARD_GRAFANA.md §2)
```

Демо-дашборд создаётся только при явно заданной витрине (хардкода базы нет):

```bash
STAND_DEMO_TABLE=accumulationregister_реализацияуслуг_recordtype \
STAND_DEMO_DATE_COL=Period STAND_DEMO_SUM_COL=Сумма \
bash work/grafana-stand/setup-grafana-stand.sh
```

Стенд живёт в `/dev/shm` (квота /srv/1c ~700 МБ против 1,3 ГБ Grafana) и не
переживает перезагрузку — это проба, а не прод. Пароль БД не хранится:
скрипт читает `PGPASSWORD` из `/etc/1c-mcp-reports.env` в момент запуска.
