#!/bin/bash
# Выкат serene_ask + словарных скриптов на okna (запуск с дева, ключ deploy).
# okna = LXC 10.10.10.12, снаружи ssh -p 2202 root@gpu-erw.timpul.pro (RU-замер 26.08).
# Использование: bash work/acceptance/deploy-okna-serene-ask.sh
set -euo pipefail
HOST=root@gpu-erw.timpul.pro
PORT=2202
KEY=~/.ssh/id_ed25519_deploy
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
SRC=/srv/1c/ubuntu/serenedb
REMOTE=/opt/1c-mcp-reports
BAK_SUFFIX=".bak-$(date +%Y%m%d-%H%M%S)"

# Что выкатываем: сервис ответа + жёсткие локальные модули ask + словарные
# скрипты (развилки / Solr-синонимы) + шлюз vLLM для OpenClaw.
# На okna SERENE_SRC_DIR пуст → pipeline не зовёт deploy.sh; без этого списка
# новый *.py на /opt/1c-mcp-reports не доезжает (падение на import / can't open file).
# FILES и FILES_R обязаны совпадать: scp → /tmp → backup+cp в REMOTE, chmod 755.
FILES=(
  serene_ask.py
  ask_choice_mem.py
  partial_visible.py
  branch_alias.sh
  branch_alias_parse.py
  solr_synonyms_build.py
)

for f in "${FILES[@]}"; do
  scp -P "$PORT" "${SSH_OPTS[@]}" "$SRC/$f" "$HOST:/tmp/$f.new"
done
scp -P "$PORT" "${SSH_OPTS[@]}" ubuntu/openclaw/ensure_vllm_gateway.sh "$HOST:/tmp/ensure_vllm_gateway.sh.new"
scp -P "$PORT" "${SSH_OPTS[@]}" ubuntu/openclaw/patch_vllm_provider.py "$HOST:/tmp/patch_vllm_provider.py.new"

ssh -p "$PORT" "${SSH_OPTS[@]}" "$HOST" REMOTE_DIR="$REMOTE" BAK_SFX="$BAK_SUFFIX" bash -s <<'REMOTE'
set -e
FILES_R="serene_ask.py ask_choice_mem.py partial_visible.py branch_alias.sh branch_alias_parse.py solr_synonyms_build.py"
for f in $FILES_R; do
  # Нового файла ещё нет — бэкап не обязателен (первый выкат модуля).
  if [ -e "$REMOTE_DIR/$f" ]; then
    cp -a "$REMOTE_DIR/$f" "$REMOTE_DIR/$f$BAK_SFX"
    echo "BEFORE $f \$(md5sum $REMOTE_DIR/$f | cut -d' ' -f1)"
  else
    echo "BEFORE $f (отсутствовал)"
  fi
  cp "/tmp/$f.new" "$REMOTE_DIR/$f"
  chmod 755 "$REMOTE_DIR/$f"
  echo "AFTER  $f \$(md5sum $REMOTE_DIR/$f | cut -d' ' -f1)"
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
