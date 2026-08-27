#!/bin/bash
# Выкат serene_ask + словарных скриптов на okna (запуск с дева, ключ deploy).
# okna = LXC 10.10.10.12, снаружи ssh -p 2202 root@gpu-erw.timpul.pro (RU-замер 26.08).
# Использование: bash work/acceptance/deploy-okna-serene-ask.sh
set -euo pipefail
HOST=port-2202.root@gpu-erw.timpul.pro
KEY=~/.ssh/id_ed25519_deploy
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
SRC=/srv/1c/ubuntu/serenedb
REMOTE=/opt/1c-mcp-reports
BAK_SUFFIX=".bak-$(date +%Y%m%d-%H%M%S)"

# Что выкатываем: сервис ответа + словарные развилки (старые на okna зовут
# снятый 'openclaw agent --agent main') + шлюз vLLM для OpenClaw.
FILES=(serene_ask.py branch_alias.sh branch_alias_parse.py)

for f in "${FILES[@]}"; do
  scp "${SSH_OPTS[@]}" "$SRC/$f" "$HOST:/tmp/$f.new"
done
scp "${SSH_OPTS[@]}" ubuntu/openclaw/ensure_vllm_gateway.sh "$HOST:/tmp/ensure_vllm_gateway.sh.new"
scp "${SSH_OPTS[@]}" ubuntu/openclaw/patch_vllm_provider.py "$HOST:/tmp/patch_vllm_provider.py.new"

ssh "${SSH_OPTS[@]}" "$HOST" bash -s <<REMOTE
set -e
for f in "${FILES[@]}"; do
  cp -a "$REMOTE/$f" "$REMOTE/$f$BAK_SUFFIX"
  echo "BEFORE $f \$(md5sum $REMOTE/$f | cut -d' ' -f1)"
  cp "/tmp/$f.new" "$REMOTE/$f"
  chmod 755 "$REMOTE/$f"
  echo "AFTER  $f \$(md5sum $REMOTE/$f | cut -d' ' -f1)"
done
mkdir -p /opt/openclaw
for f in ensure_vllm_gateway.sh patch_vllm_provider.py; do
  [ -f "/opt/openclaw/$f" ] && cp -a "/opt/openclaw/$f" "/opt/openclaw/$f$BAK_SUFFIX" || true
  cp "/tmp/$f.new" "/opt/openclaw/$f"
  chmod 755 "/opt/openclaw/$f"
  echo "AFTER  /opt/openclaw/$f \$(md5sum /opt/openclaw/$f | cut -d' ' -f1)"
done
systemctl restart 1c-serene-ask@postgres
sleep 5
curl -sS -m 20 http://127.0.0.1:8091/health
REMOTE
