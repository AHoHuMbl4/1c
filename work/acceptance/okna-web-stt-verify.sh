#!/bin/bash
# Проверка STT: DB + OWUI API + прямой whisper
set -euo pipefail
python3 - <<'PY'
import json, sqlite3, urllib.request
db="/home/webui/open-webui-data/webui.db"
con=sqlite3.connect(db)
url=con.execute("SELECT value FROM config WHERE key='audio.stt.openai.api_base_url'").fetchone()[0]
engine=con.execute("SELECT value FROM config WHERE key='audio.stt.engine'").fetchone()[0]
model=con.execute("SELECT value FROM config WHERE key='audio.stt.model'").fetchone()[0]
con.close()
print("db_engine", engine)
print("db_model", model)
print("db_url", url)
PY
curl -sf -o /dev/null -w "webui=%{http_code}\n" http://127.0.0.1:8080/health
