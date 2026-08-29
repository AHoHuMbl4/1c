#!/bin/bash
# Выкат ask-кода из HEAD репо в /opt/1c-mcp-reports на окне (только изменившееся, atomic mv).
set -euo pipefail
SSH="ssh -i /home/claudedev/.ssh/id_ed25519_deploy -p 2202 root@gpu-erw.timpul.pro"
SCP="scp -i /home/claudedev/.ssh/id_ed25519_deploy -P 2202"
SRC=/srv/1c/ubuntu/serenedb
DST=/opt/1c-mcp-reports

cd "$SRC"
md5sum serene_ask.py ask/*.py | sort -k2 > /tmp/ask-md5-local.txt
$SSH "cd $DST && md5sum serene_ask.py ask/*.py 2>/dev/null | sort -k2 > /tmp/ask-md5-remote.txt || true"
$SCP -q /tmp/ask-md5-local.txt root@gpu-erw.timpul.pro:/tmp/ask-md5-new.txt

CHANGED=$($SSH "join -j2 /tmp/ask-md5-remote.txt /tmp/ask-md5-new.txt 2>/dev/null | awk '\$2!=\$3{print \$1}' ; comm -13 <(awk '{print \$2}' /tmp/ask-md5-remote.txt|sort) <(awk '{print \$2}' /tmp/ask-md5-new.txt|sort)")
echo "CHANGED:"; echo "$CHANGED"
[ -z "$CHANGED" ] && { echo "изменений нет"; exit 0; }

mkdir -p /tmp/ask-dep && rm -rf /tmp/ask-dep && mkdir -p /tmp/ask-dep
for f in $CHANGED; do install -D -m 644 "$SRC/$f" "/tmp/ask-dep/$f"; done
tar -C /tmp/ask-dep -czf /tmp/ask-dep.tgz .
$SCP -q /tmp/ask-dep.tgz root@gpu-erw.timpul.pro:/tmp/ask-dep.tgz
$SSH 'set -e; mkdir -p /tmp/ask-stage && tar -C /tmp/ask-stage -xzf /tmp/ask-dep.tgz
cd /tmp/ask-stage
find . -type f | while read f; do
  rel=${f#./}
  install -m 644 "$rel" "/opt/1c-mcp-reports/$rel.new"
  mv "/opt/1c-mcp-reports/$rel.new" "/opt/1c-mcp-reports/$rel"
done
echo "deployed:"; find . -type f | sed "s|^\./||"
md5sum /opt/1c-mcp-reports/serene_ask.py | cut -c1-8'
