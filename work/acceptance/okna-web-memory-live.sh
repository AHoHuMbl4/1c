#!/bin/bash
# Живые вопросы web-гейтвею + проверка журнала на memory-error
set -euo pipefail
TOKEN=$(cat /home/undebot/.openclaw-web/.gateway-token)
PORT=18801
ask() {
  local q="$1"
  echo "=== Q: $q ==="
  curl -sf "http://127.0.0.1:${PORT}/v1/chat/completions" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json; print(json.dumps({'model':'openclaw','messages':[{'role':'user','content':'''$q'''}],'max_tokens':120}))")" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); c=d['choices'][0]['message'].get('content','')[:200]; print(c)"
  sleep 2
}
ask "Сколько у нас контрагентов?"
ask "На какую сумму мы продали?"
ask "Что такое реализация товаров?"

echo "=== memory errors last 10 min ==="
journalctl _SYSTEMD_USER_UNIT=openclaw-gateway-web -M undebot@ --since "10 min ago" --no-pager 2>/dev/null \
  | grep -iE 'Memory index failed|memory embeddings|No API key|openai-compatible embeddings failed|401' \
  || echo "(none)"

runuser -u undebot -- env HOME=/home/undebot openclaw --profile web memory status --agent main 2>&1 | grep -iE 'Indexed|Embeddings|Semantic|ready|Issues' || true
