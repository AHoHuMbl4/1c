#!/bin/bash
# Полный JSON ответа ask okna на один вопрос (для разбора полей options/diag).
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PORT=${ASK_PORT:-8091}
Q=${1:?вопрос первым аргументом}
DID=${2:-}
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" "PORT=$PORT bash -s" <<EOF
set -euo pipefail
ASK_TOKEN=\$(grep -E '^ASK_TOKEN=' /etc/1c-serene-ask.env | cut -d= -f2- | tr -d '"'"'"'"')
python3 - "$Q" "\$ASK_TOKEN" "\$PORT" "$DID" <<'PY'
import json, sys, urllib.request
q, tok, port, did = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
body = {"question": q}
if did:
    body["decision_id"] = did
req = urllib.request.Request("http://127.0.0.1:%s/ask" % port,
    data=json.dumps(body).encode(), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Bearer " + tok)
with urllib.request.urlopen(req, timeout=600) as r:
    print(json.dumps(json.loads(r.read()), ensure_ascii=False, indent=1)[:6000])
PY
EOF
