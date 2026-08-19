#!/bin/bash
# Пробный заход в живой ask okna: вопросы приходят на stdin (по одному в строке),
# печатается kind/focus/claims/text — для разбора провалов золотого набора.
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT=${ASK_PORT:-8091}
QS=$(cat)
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "PORT=$PORT bash -s" <<EOF
set -euo pipefail
ASK_TOKEN=\$(grep -E '^ASK_TOKEN=' /etc/1c-serene-ask.env | cut -d= -f2- | tr -d '"'"'"'"')
md5sum /opt/1c-mcp-reports/serene_ask.py
while IFS= read -r q; do
  [ -z "\$q" ] && continue
  python3 - "\$q" "\$ASK_TOKEN" "\$PORT" <<'PY'
import json, sys, urllib.request, time
q, tok, port = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request("http://127.0.0.1:%s/ask" % port,
    data=json.dumps({"question": q}).encode(), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Bearer " + tok)
t = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
except Exception as e:
    print("Q= %s\n  ERROR %s" % (q, e)); raise SystemExit(0)
dg = d.get("diag") or {}
print("Q= %s  (%.1fs)" % (q, time.time() - t))
print("  kind=%s focus=%s rid=%s" % (d.get("kind"), dg.get("focus"), dg.get("rid")))
print("  claims=%s" % json.dumps(dg.get("claims"), ensure_ascii=False)[:300])
print("  options=%s" % json.dumps([o.get("label") if isinstance(o, dict) else o
                                   for o in (d.get("options") or [])], ensure_ascii=False)[:400])
print("  text=%s" % (d.get("text") or "").replace("\n", " | ")[:600])
PY
done <<'QEOF'
$QS
QEOF
EOF
