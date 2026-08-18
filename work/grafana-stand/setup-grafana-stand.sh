#!/bin/bash
# Пробный стенд Grafana для дашбордов проекта (docs/DASHBOARD_GRAFANA.md).
#
# Что делает: качает Grafana OSS, поднимает её в юзерспейсе (без systemd,
# без прав root) на 127.0.0.1:3001, заводит datasource на SereneDB под
# read-only ролью serene_ro и создаёт демо-дашборд через HTTP API.
#
# Запуск: bash work/grafana-stand/setup-grafana-stand.sh
# Демо-дашборд (необязательно): STAND_DEMO_TABLE=<витрина> \
#   STAND_DEMO_DATE_COL=<дата-колонка> STAND_DEMO_SUM_COL=<сумма-колонка> \
#   bash work/grafana-stand/setup-grafana-stand.sh
# Стоп:   kill $(cat /dev/shm/grafana-stand/grafana.pid)
#
# Почему /dev/shm: на /srv/1c действует дисковая квота (~700 МБ свободно
# [замер 18.08]), распакованная Grafana занимает 1,3 ГБ. Побочка: стенд
# не переживает перезагрузку — для пробы это и требуется.
# Пароль read-only роли скрипт читает из /etc/1c-mcp-reports.env
# (PGPASSWORD), сам пароль нигде не печатается и в git не попадает.

set -euo pipefail

VERSION="${GRAFANA_VERSION:-13.2.0}"
BUILD="${GRAFANA_BUILD:-32077357341}"
STAND_DIR="${GRAFANA_STAND_DIR:-/dev/shm/grafana-stand}"
PORT="${GRAFANA_PORT:-3001}"
ADMIN_PW="${GRAFANA_ADMIN_PASSWORD:-stand123}"   # только локальный стенд, loopback
DS_ENV="${DS_ENV:-/etc/1c-mcp-reports.env}"

cd "$STAND_DIR"

# --- 1. бинарь -------------------------------------------------------------
if [ ! -x grafana/bin/grafana ]; then
    [ -f grafana.tar.gz ] || curl -sL -o grafana.tar.gz \
        "https://dl.grafana.com/grafana/release/${VERSION}/grafana_${VERSION}_${BUILD}_linux_amd64.tar.gz"
    tar xzf grafana.tar.gz
    rm grafana.tar.gz
    mv "grafana-${VERSION}" grafana
fi

# --- 2. конфиг -------------------------------------------------------------
mkdir -p data logs plugins
# Ключи сквозной авторизации (auth.jwt): адаптер подписывает короткоживущий
# JWT приватным ключом, Grafana проверяет публичным и логинит без формы.
# На стенде ключи в /dev/shm (эфемерно); в проде — /etc с правами 640.
if [ ! -f jwt-private.pem ]; then
    openssl genrsa -out jwt-private.pem 2048 2>/dev/null
    openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem 2>/dev/null
    chmod 600 jwt-private.pem
fi
# allow_embedding=true — панели встраиваются iframe'ом (по умолчанию Grafana
# шлёт X-Frame-Options: deny [замер 18.08]).
cat > custom.ini <<EOF
[paths]
data = $STAND_DIR/data
logs = $STAND_DIR/logs
plugins = $STAND_DIR/plugins
[server]
http_port = $PORT
domain = localhost
[security]
admin_user = admin
admin_password = $ADMIN_PW
allow_embedding = true
[analytics]
reporting_enabled = false
check_for_updates = false
[users]
allow_sign_up = false
[auth.jwt]
# Сквозной вход из чата: ссылка вида /d/<uid>?auth_token=<JWT> логинит
# без формы (url_login). Проверка — публичным ключом; подписывает адаптер.
enabled = true
url_login = true
header_name = X-JWT-Assertion
key_file = $STAND_DIR/jwt-public.pem
username_claim = sub
email_claim = email
auto_sign_up = true
EOF

# --- 3. запуск -------------------------------------------------------------
if [ -f grafana.pid ] && kill -0 "$(cat grafana.pid)" 2>/dev/null; then
    kill "$(cat grafana.pid)"; sleep 3
fi
nohup ./grafana/bin/grafana server --homepath="$STAND_DIR/grafana" \
    --config="$STAND_DIR/custom.ini" >> logs/console.log 2>&1 &
echo $! > grafana.pid
for i in $(seq 1 30); do
    curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
    sleep 1
done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "grafana не поднялась, см. $STAND_DIR/logs/console.log"; exit 1; }
echo "grafana $VERSION на http://127.0.0.1:$PORT (admin / \$GRAFANA_ADMIN_PASSWORD)"

# --- 4. datasource + демо-дашборд ------------------------------------------
set -a; . "$DS_ENV"; set +a
export GRAFANA_PORT="$PORT" GRAFANA_ADMIN_PASSWORD="$ADMIN_PW"
python3 - <<'PYEOF'
import json, os, base64, urllib.request

port = os.environ["GRAFANA_PORT"]
auth = "Basic " + base64.b64encode(
    ("admin:" + os.environ["GRAFANA_ADMIN_PASSWORD"]).encode()).decode()

def call(method, path, body=None, allow=()):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": auth})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e:
        if e.code in allow:
            return None
        raise

# SereneDB по postgres-протоколу. 🔴 Все колонки приезжают как VARCHAR —
# в SQL панелей обязательны явные касты (::timestamp, ::DECIMAL),
# иначе «No function matches … date_trunc(STRING_LITERAL, VARCHAR)»
# [замер 18.08]. Доки: sql/functions/timestamp#date_trunc,
# sql/data_types/typecasting.
ds_body = {
    "name": "serenedb-ro", "type": "postgres", "access": "proxy",
    "url": "127.0.0.1:7890", "user": "serene_ro", "database": "postgres",
    "jsonData": {"sslmode": "disable", "postgresVersion": 1500},
    "secureJsonData": {"password": os.environ["PGPASSWORD"]},
    "readOnly": True}
import time
# /api/health отвечает раньше, чем apiserver монтирует остальные маршруты:
# сразу после старта GET /api/datasources отдаёт 404 [замер 18.08] — ждём.
all_ds = None
for _ in range(20):
    try:
        all_ds = call("GET", "/api/datasources")
        break
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        time.sleep(1)
if all_ds is None:
    raise SystemExit("grafana API не поднялся за 20 с")
old = next((d for d in all_ds if d["name"] == "serenedb-ro"), None)
if old:
    # в Grafana 12+ мутации — по uid; PUT /api/datasources/<id> отдаёт 404 [замер 18.08]
    call("PUT", f"/api/datasources/uid/{old['uid']}", {**ds_body, "id": old["id"]})
    uid = old["uid"]
else:
    uid = call("POST", "/api/datasources", ds_body)["datasource"]["uid"]
print("datasource serenedb-ro uid:", uid)

# Демо-дашборд — только при явно заданной витрине (без хардкода базы:
# имя таблицы и колонок приезжают параметрами окружения, умолчания нет).
DEMO_TABLE = os.environ.get("STAND_DEMO_TABLE")
DEMO_DATE_COL = os.environ.get("STAND_DEMO_DATE_COL")
DEMO_SUM_COL = os.environ.get("STAND_DEMO_SUM_COL")
if not (DEMO_TABLE and DEMO_DATE_COL and DEMO_SUM_COL):
    print("демо-дашборд пропущен: задайте STAND_DEMO_TABLE / STAND_DEMO_DATE_COL / STAND_DEMO_SUM_COL")
    raise SystemExit(0)
dref = {"type": "grafana-postgresql-datasource", "uid": uid}
SQL_TS = (f'SELECT date_trunc(\'day\', "{DEMO_DATE_COL}"::timestamp) AS time, '
          f'sum("{DEMO_SUM_COL}"::DECIMAL) AS value '
          f'FROM {DEMO_TABLE} GROUP BY 1 ORDER BY 1')
SQL_STAT = f'SELECT count(*) AS "Строк" FROM {DEMO_TABLE}'
dash = {"dashboard": {
    "title": "1C: из чата (стенд)", "uid": "stand-from-chat",
    "refresh": "5m", "time": {"from": "now-180d", "to": "now"},
    "tags": ["from-chat"],
    "panels": [
        {"id": 1, "type": "timeseries", "title": f"{DEMO_TABLE}: сумма по дням",
         "gridPos": {"h": 9, "w": 12, "x": 0, "y": 0}, "datasource": dref,
         "targets": [{"refId": "A", "rawSql": SQL_TS, "format": "time_series", "datasource": dref}],
         "fieldConfig": {"defaults": {"unit": "currencyRUB"}, "overrides": []}},
        {"id": 2, "type": "stat", "title": "Всего строк в витрине",
         "gridPos": {"h": 9, "w": 6, "x": 12, "y": 0}, "datasource": dref,
         "targets": [{"refId": "A", "rawSql": SQL_STAT, "format": "table", "datasource": dref}]},
    ]}, "overwrite": True}
res = call("POST", "/api/dashboards/db", dash)
print("dashboard:", res.get("status"), res.get("url"))
PYEOF
echo "готово: http://127.0.0.1:$PORT (демо-дашборд: /d/stand-from-chat, если задан STAND_DEMO_TABLE)"
