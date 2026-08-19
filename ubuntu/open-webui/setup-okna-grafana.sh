#!/bin/bash
# Grafana + сквозной вход на фронте okna (веб-сервер с Open WebUI).
# Решение владельца 18.08: Grafana живёт на веб-сервере okna.
#
# Что делает (идемпотентно):
#   1. пользователи grafana / dashenter, каталоги /opt/1c-grafana, /var/lib/1c-grafana
#   2. Grafana OSS из tarball (без пакетов), 127.0.0.1:3001, подпуть /dash/
#   3. RSA-пара для auth.jwt: приватный /etc/1c-grafana-jwt-private.pem (640 root:dashenter),
#      публичный рядом с конфигом Grafana
#   4. юниты 1c-grafana.service и 1c-dash-enter.service (адаптер, 127.0.0.1:3002)
#   5. Caddyfile из Caddyfile.okna → /etc/caddy/Caddyfile (caddy validate + reload)
#   6. datasource SereneDB через релей бэкенда (BACKEND_IP:7890, serene_ro)
#
# Запуск (root на фронте):
#   SERENE_RO_PW=<пароль serene_ro с бэкенда> bash /opt/1c-open-webui/setup-okna-grafana.sh
# Пароль попадает в /etc/1c-grafana.env (640 root:root) — нужен для пересоздания
# datasource при повторных прогонах; в git и в вывод не попадает.

set -euo pipefail

DOMAIN="${DOMAIN:-baulogistic.timpul.pro}"
BACKEND_IP="${BACKEND_IP:-10.3.0.4}"
VERSION="${GRAFANA_VERSION:-13.2.0}"
BUILD="${GRAFANA_BUILD:-32077357341}"
BASE=/opt/1c-grafana
# Семена дашбордов контура (пусто = не ставить; для okna: grafana/contours/okna).
DASHBOARD_SEEDS_DIR="${DASHBOARD_SEEDS_DIR:-}"
DATA=/var/lib/1c-grafana
ENVF=/etc/1c-grafana.env
KEY_PRIV=/etc/1c-grafana-jwt-private.pem
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV=$BASE/venv

[ "$(id -u)" = 0 ] || { echo "нужен root"; exit 1; }

# --- 1. пользователи и каталоги ---------------------------------------------
for u in grafana dashenter; do
    id "$u" &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin "$u"
done
mkdir -p "$BASE" "$DATA"
chown grafana:grafana "$DATA"

# --- 1б. venv адаптера --------------------------------------------------------
# 🔴 НЕ venv OWUI (/home/webui/...): /home/webui недоступен пользователю
# dashenter — status=203/EXEC Permission denied [замер 18.08]. Свой venv.
if [ ! -x "$VENV/bin/python3" ]; then
    python3 -m venv "$VENV"
fi
# 🔴 нужен именно pyjwt[crypto]: голый pyjwt RS256 не умеет
# (KeyError 'RS256' на первом же /dash/enter) [замер 18.08].
"$VENV/bin/pip" -q install --no-input --upgrade "pyjwt[crypto]"

# --- 2. бинарь Grafana --------------------------------------------------------
if [ ! -x "$BASE/grafana/bin/grafana" ]; then
    cd "$BASE"
    [ -f grafana.tar.gz ] || curl -sL -o grafana.tar.gz \
        "https://dl.grafana.com/grafana/release/${VERSION}/grafana_${VERSION}_${BUILD}_linux_amd64.tar.gz"
    tar xzf grafana.tar.gz && rm grafana.tar.gz
    mv "grafana-${VERSION}" grafana
fi

# --- 3. ключи auth.jwt и секреты ----------------------------------------------
if [ ! -f "$KEY_PRIV" ]; then
    openssl genrsa -out "$KEY_PRIV" 2048 2>/dev/null
    openssl rsa -in "$KEY_PRIV" -pubout -out "$BASE/jwt-public.pem" 2>/dev/null
    chmod 640 "$KEY_PRIV"; chown root:dashenter "$KEY_PRIV"
fi
chmod 644 "$BASE/jwt-public.pem"
if [ ! -f "$ENVF" ]; then
    install -m 640 -o root -g root /dev/null "$ENVF"
    printf 'GRAFANA_ADMIN_PASSWORD=%s\n' "$(openssl rand -base64 18)" >> "$ENVF"
fi
# Пароль serene_ro: из вызова или из прошлого прогона.
if [ -n "${SERENE_RO_PW:-}" ]; then
    grep -q '^SERENE_RO_PW=' "$ENVF" && sed -i '/^SERENE_RO_PW=/d' "$ENVF"
    printf 'SERENE_RO_PW=%s\n' "$SERENE_RO_PW" >> "$ENVF"
fi
set -a; . "$ENVF"; set +a
: "${SERENE_RO_PW:?нужен SERENE_RO_PW (env или $ENVF) — пароль serene_ro с бэкенда}"

# --- 4. конфиг Grafana ---------------------------------------------------------
# Подпуть /dash/: Caddy проксирует БЕЗ срезания префикса (handle, не
# handle_path — ловушка 8), Grafana ждёт подпуть в запросе
# (serve_from_sub_path). auth.jwt: вход по заголовку от
# Caddy (cookie gf_jwt → X-JWT-Assertion); header_name обязателен явно,
# url_login первым запросом сессии не даёт [замер 18.08, docs/DASHBOARD_GRAFANA.md].
cat > "$BASE/custom.ini" <<EOF
[paths]
data = $DATA
logs = $DATA/logs
plugins = $DATA/plugins
[server]
http_addr = 127.0.0.1
http_port = 3001
domain = $DOMAIN
root_url = https://$DOMAIN/dash/
serve_from_sub_path = true
[security]
admin_user = admin
admin_password = $GRAFANA_ADMIN_PASSWORD
allow_embedding = true
cookie_secure = true
[analytics]
reporting_enabled = false
check_for_updates = false
[users]
allow_sign_up = false
[auth.anonymous]
enabled = false
[auth.jwt]
enabled = true
header_name = X-JWT-Assertion
key_file = $BASE/jwt-public.pem
username_claim = sub
email_claim = email
auto_sign_up = true
EOF
chown -R grafana:grafana "$BASE" && chmod 755 "$BASE"
mkdir -p "$DATA/logs" "$DATA/plugins" && chown -R grafana:grafana "$DATA"

# --- 5. юниты ------------------------------------------------------------------
cat > /etc/systemd/system/1c-grafana.service <<EOF
[Unit]
Description=Grafana (дашборды okna, подпуть /dash/)
After=network-online.target

[Service]
User=grafana
ExecStart=$BASE/grafana/bin/grafana server --homepath=$BASE/grafana --config=$BASE/custom.ini
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/1c-dash-enter.service <<EOF
[Unit]
Description=Сквозной вход OWUI → Grafana (dash/enter)
After=network-online.target

[Service]
User=dashenter
EnvironmentFile=$ENVF
Environment=OWUI_URL=http://127.0.0.1:8080
Environment=JWT_PRIVATE_KEY_FILE=$KEY_PRIV
Environment=LISTEN=127.0.0.1:3002
ExecStart=$VENV/bin/python3 $SCRIPT_DIR/dash_adapter.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now 1c-grafana 1c-dash-enter >/dev/null
systemctl restart 1c-grafana 1c-dash-enter
for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:3001/api/health >/dev/null && curl -sf http://127.0.0.1:3002/dash/healthz >/dev/null && break
    sleep 1
done
curl -sf http://127.0.0.1:3001/api/health >/dev/null || { echo "grafana не поднялась: journalctl -u 1c-grafana -n 40"; exit 1; }
curl -sf http://127.0.0.1:3002/dash/healthz >/dev/null || { echo "адаптер не поднялся: journalctl -u 1c-dash-enter -n 40"; exit 1; }
echo "✅ grafana :3001 и dash-enter :3002 подняты"

# --- 6. Caddy -------------------------------------------------------------------
# Шаблон Caddyfile.okna уже содержит блоки /dash/* (handle enter → :3002,
# handle /dash/* → :3001 с подстановкой cookie в заголовок, префикс не срезаем).
sed "s/__DOMAIN__/$DOMAIN/g" "$SCRIPT_DIR/Caddyfile.okna" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile >/dev/null
systemctl reload caddy
echo "✅ caddy перечитал Caddyfile (блоки /dash/* активны)"

# --- 7. datasource SereneDB (через релей бэкенда) --------------------------------
export GRAFANA_ADMIN_PASSWORD BACKEND_IP SCRIPT_DIR DASHBOARD_SEEDS_DIR
python3 - <<'PYEOF'
import json, os, base64, time, urllib.request, urllib.error

auth = "Basic " + base64.b64encode(
    ("admin:" + os.environ["GRAFANA_ADMIN_PASSWORD"]).encode()).decode()

def call(method, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:3001{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": auth})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

# API монтируется позже /api/health [замер 18.08] — ждём ретраем.
all_ds = None
for _ in range(20):
    try:
        all_ds = call("GET", "/api/datasources"); break
    except urllib.error.HTTPError as e:
        if e.code != 404: raise
        time.sleep(1)
if all_ds is None:
    raise SystemExit("grafana API не поднялся за 20 с")

ds_body = {
    "name": "serenedb-ro", "type": "postgres", "access": "proxy",
    "url": f"{os.environ['BACKEND_IP']}:7890", "user": "serene_ro",
    "database": "postgres",
    # 🔴 имя базы обязано лежать в jsonData: Grafana 13 у postgres читает его
    # оттуда, а не из поля верхнего уровня. С одним верхним полем панели дают
    # «You do not currently have a default database configured for this data
    # source» и No data [замер 19.08, живой okna].
    "jsonData": {"sslmode": "disable", "postgresVersion": 1500,
                 "database": "postgres"},
    "secureJsonData": {"password": os.environ["SERENE_RO_PW"]},
    "readOnly": True}
old = next((d for d in all_ds if d["name"] == "serenedb-ro"), None)
if old:
    call("PUT", f"/api/datasources/uid/{old['uid']}", {**ds_body, "id": old["id"]})
    uid = old["uid"]
else:
    uid = call("POST", "/api/datasources", ds_body)["datasource"]["uid"]
print("datasource serenedb-ro uid:", uid)

# Проверка живым запросом: версия движка через datasource.
probe = {"queries": [{"refId": "A", "datasource": {"type": "postgres", "uid": uid},
    "rawSql": "select version() as v", "format": "table"}]}
res = call("POST", "/api/ds/query", probe)
frames = res["results"]["A"].get("frames", [])
if not frames:
    raise SystemExit(f"probe не вернул данных: {res}")
print("✅ probe select version():", frames[0]["data"]["values"][0][0][:60])

# --- 8. семена дашбордов контура ------------------------------------------------
# Дашборд, созданный руками в UI, живёт только в grafana.db — переустановка
# теряет его молча [19.08]. Семя — снимок дашборда КОНТУРА: в его панелях стоят
# имена таблиц конкретной базы 1С, поэтому в установку по умолчанию оно НЕ
# входит (иначе коробка на чужой базе получила бы панели с чужими именами).
# Каталог задаётся снаружи: DASHBOARD_SEEDS_DIR=grafana/contours/okna.
# uid datasource в семени — плейсхолдер ${DS_SERENEDB} (на другой машине другой).
# Существующий дашборд НЕ перетирается: его правит пользователь (и будущая
# кнопка «добавить в дашборд» дописывает панели через API).
import glob, pathlib

seeds_dir = os.environ.get("DASHBOARD_SEEDS_DIR", "").strip()
seeds = []
if seeds_dir:
    if not os.path.isabs(seeds_dir):
        seeds_dir = os.path.join(os.environ["SCRIPT_DIR"], seeds_dir)
    seeds = sorted(glob.glob(os.path.join(seeds_dir, "*.json")))
    if not seeds:
        raise SystemExit(f"DASHBOARD_SEEDS_DIR={seeds_dir}: семян не найдено")
else:
    print("семена дашбордов не заданы (DASHBOARD_SEEDS_DIR пуст) — пропускаем")
for path in seeds:
    raw = pathlib.Path(path).read_text(encoding="utf-8").replace("${DS_SERENEDB}", uid)
    model = json.loads(raw)
    try:
        call("GET", f"/api/dashboards/uid/{model['uid']}")
        print(f"дашборд {model['uid']}: уже есть, не трогаем")
        continue
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    call("POST", "/api/dashboards/db",
         {"dashboard": model, "overwrite": False,
          "message": "seed из репозитория (setup-okna-grafana.sh)"})
    print(f"✅ дашборд {model['uid']} восстановлен из семени")

# --- 9. приёмка: панели отдают данные -------------------------------------------
# probe select version() ходит НЕ тем путём, что панель: с datasource без
# jsonData.database probe проходил, а панели давали No data [замер 19.08,
# ловушка 11]. Поэтому приёмка гоняет rawSql каждой панели каждого дашборда
# через /api/ds/query — то же, что делает открытая страница.
bad = []
for item in call("GET", "/api/search?type=dash-db"):
    dash = call("GET", f"/api/dashboards/uid/{item['uid']}")["dashboard"]
    for panel in dash.get("panels", []):
        for target in panel.get("targets", []):
            sql = target.get("rawSql")
            if not sql:
                continue
            # Окно — из самого дашборда (и panel.timeFrom, если панель его
            # переопределяет), как у открытой страницы. Зашивать своё нельзя:
            # на базе с другой историей исправная панель дала бы 0 строк.
            win = dash.get("time") or {}
            q = {"queries": [{"refId": "A", "datasource": panel["datasource"],
                              "rawSql": sql, "format": target.get("format", "table")}],
                 "from": panel.get("timeFrom") or win.get("from", "now-6h"),
                 "to": win.get("to", "now")}
            res = call("POST", "/api/ds/query", q)["results"]["A"]
            if res.get("error"):
                bad.append(f"{dash['title']} / {panel.get('title')}: {res['error']}")
                continue
            rows = 0
            for frame in res.get("frames", []):
                values = frame.get("data", {}).get("values") or []
                rows = max(rows, len(values[0]) if values else 0)
            mark = "✅" if rows else "⚠️ пусто"
            print(f"{mark} панель «{panel.get('title')}» ({dash['title']}): строк {rows}")
            if not rows:
                bad.append(f"{dash['title']} / {panel.get('title')}: 0 строк")
if bad:
    raise SystemExit("панели не отдают данные:\n  " + "\n  ".join(bad))
PYEOF

echo "Готово: https://$DOMAIN/dash/enter — вход из чата без второго логина."
