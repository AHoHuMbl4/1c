#!/bin/bash
# Фаза B: стейджинг :8092 с кодом из /tmp (не /opt). Запуск С okna.
set -euo pipefail
SRC_LOCAL="${1:-/srv/1c/ubuntu/serenedb/serene_ask.py}"
KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_deploy}"
HOST=root@gpu-erw.timpul.pro
PORT=2202

scp -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" -P "$PORT" \
  "$SRC_LOCAL" "$HOST:/tmp/serene_ask_wb.py"

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" -p "$PORT" "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
if [ -f /tmp/serene_ask_wb_8092.pid ]; then kill "$(cat /tmp/serene_ask_wb_8092.pid)" 2>/dev/null || true; fi
if [ -f /tmp/serene_ask_f61_8092.pid ]; then kill "$(cat /tmp/serene_ask_f61_8092.pid)" 2>/dev/null || true; fi
fuser -k 8092/tcp 2>/dev/null || true
sleep 2
load_env() {
  for p in "$@"; do
    [ -f "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"; line="${line%"${line##*[![:space:]]}"}"; line="${line#"${line%%[![:space:]]*}"}"
      [ -z "$line" ] && continue; [[ "$line" != *=* ]] && continue
      key="${line%%=*}"; val="${line#*=}"
      val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
      if [ "${#val}" -ge 2 ] && [ "${val:0:1}" = "${val: -1}" ]; then
        case "${val:0:1}" in \"|\') val="${val:1:-1}";; esac
      fi
      export "$key=$val"
    done < "$p"
  done
}
load_env /etc/1c-mcp-reports.env /etc/1c-embed.env /etc/1c-serene-ask.env /etc/1c-serene-ask-postgres.env
export ASK_LISTEN_PORT=8092 ASK_SQL_RRF=1 PYTHONPATH=/opt/1c-mcp-reports
echo "ASK_SQL_RRF=1" > /tmp/serene_ask_f61_8092.env
echo "ASK_LISTEN_PORT=8092" >> /tmp/serene_ask_f61_8092.env
echo "CODE=/tmp/serene_ask_wb.py md5=$(md5sum /tmp/serene_ask_wb.py | awk '{print $1}')" >> /tmp/serene_ask_f61_8092.env
PY=/opt/openclaw-mcp/venv/bin/python
setsid nohup env ASK_LISTEN_PORT=8092 ASK_SQL_RRF=1 PYTHONPATH=/opt/1c-mcp-reports \
  $PY /tmp/serene_ask_wb.py >/tmp/serene_ask_wb_8092.log 2>&1 &
echo $! >/tmp/serene_ask_wb_8092.pid
ready=0
for i in $(seq 1 90); do
  if ss -ltn | grep -q ':8092'; then
    code=$(curl -s -m 120 -o /tmp/wb_ask_probe.json -w '%{http_code}' \
      -H "Authorization: Bearer $ASK_TOKEN" -H "Content-Type: application/json" \
      -d '{"question":"сколько продали вчера?","user":"wb-phase-b"}' \
      http://127.0.0.1:8092/ask || echo 000)
    kind=$(python3 -c "import json;print(json.load(open(\"/tmp/wb_ask_probe.json\")).get(\"kind\",\"?\"))" 2>/dev/null || echo '?')
    echo "try=$i http=$code kind=$kind"
    if [ "$code" = "200" ] && [ "$kind" != "unavailable" ] && [ "$kind" != "?" ]; then ready=1; break; fi
  fi
  sleep 2
done
[ "$ready" = 1 ] || { tail -50 /tmp/serene_ask_wb_8092.log; exit 4; }
python3 -c "import json;d=json.load(open('/tmp/wb_ask_probe.json'));print('OK kind',d.get('kind'),'leader',(d.get('diag') or {}).get('period_leader'),'readings',(d.get('diag') or {}).get('period_readings'))"
echo STAGING_READY
REMOTE
