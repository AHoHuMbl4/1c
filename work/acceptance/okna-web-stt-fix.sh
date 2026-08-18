#!/bin/bash
# okna frontend: STT URL в webui.db (перекрывает env)
set -euo pipefail
DB=/home/webui/open-webui-data/webui.db
TS=$(date +%Y%m%d-%H%M%S)
cp -a "$DB" "${DB}.bak-${TS}"
echo "backup: ${DB}.bak-${TS}"

# URL из env-файла владельца или умолчание gpu-erw whisper
STT_ENV=/etc/1c-open-webui-stt.env
if [ -f "$STT_ENV" ] && grep -q '^AUDIO_STT_OPENAI_API_BASE_URL=' "$STT_ENV"; then
  # shellcheck disable=SC1091
  source "$STT_ENV"
fi
NEW_URL="${AUDIO_STT_OPENAI_API_BASE_URL:-http://gpu-erw.timpul.pro:8006/v1}"

python3 - "$DB" "$NEW_URL" <<'PY'
import sqlite3, sys
db, new_url = sys.argv[1:3]
con = sqlite3.connect(db)
cur = con.cursor()
old = cur.execute("SELECT value FROM config WHERE key='audio.stt.openai.api_base_url'").fetchone()
print("old:", old[0] if old else None)
cur.execute(
    "UPDATE config SET value=? WHERE key='audio.stt.openai.api_base_url'",
    (f'"{new_url}"',),
)
con.commit()
new = cur.execute("SELECT value FROM config WHERE key='audio.stt.openai.api_base_url'").fetchone()
print("new:", new[0])
con.close()
PY

for f in /etc/1c-open-webui-stt.env /home/webui/.open-webui.env; do
  [ -f "$f" ] || continue
  if grep -q '^AUDIO_STT_OPENAI_API_BASE_URL=' "$f"; then
    sed -i "s|^AUDIO_STT_OPENAI_API_BASE_URL=.*|AUDIO_STT_OPENAI_API_BASE_URL=${NEW_URL}|" "$f"
  else
    echo "AUDIO_STT_OPENAI_API_BASE_URL=${NEW_URL}" >>"$f"
  fi
  echo "env synced: $f"
done

UID_WEB=$(id -u webui)
runuser -u webui -- env XDG_RUNTIME_DIR="/run/user/$UID_WEB" systemctl --user restart open-webui
sleep 5
curl -sf -o /dev/null -w "webui_health=%{http_code}\n" http://127.0.0.1:8080/health || true

python3 - <<'PY'
import json, sqlite3, struct, wave, io, urllib.request

db = "/home/webui/open-webui-data/webui.db"
con = sqlite3.connect(db)
db_url = con.execute(
    "SELECT value FROM config WHERE key='audio.stt.openai.api_base_url'"
).fetchone()[0].strip('"')
con.close()
print("db_url_host:", db_url.split("://", 1)[-1].split("/")[0])

key = ""
for path in ("/etc/1c-open-webui-stt.env", "/home/webui/.open-webui.env"):
    try:
        for line in open(path):
            if line.startswith("AUDIO_STT_OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
                break
    except OSError:
        pass
    if key:
        break

buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"\x00\x00" * 8000)
wav = buf.getvalue()

base = db_url.rstrip("/")
url = f"{base}/audio/transcriptions"
boundary = b"----bound"
body = (
    b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-large-v3\r\n"
    b"--" + boundary + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.wav\"\r\n"
    b"Content-Type: audio/wav\r\n\r\n" + wav + b"\r\n--" + boundary + b"--\r\n"
)
req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary.decode())
if key:
    req.add_header("Authorization", "Bearer " + key)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("whisper_http", r.status, r.read()[:120])
except Exception as e:
    print("whisper_err", type(e).__name__, str(e)[:160])

try:
    with urllib.request.urlopen("http://127.0.0.1:8080/api/config", timeout=10) as r:
        d = json.load(r)
    stt = d.get("audio", {}).get("stt", {})
    print("owui_engine", stt.get("engine"))
    print("owui_base", (stt.get("openai") or {}).get("api_base_url"))
except Exception as e:
    print("owui_config_err", e)
PY
