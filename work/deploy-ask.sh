#!/bin/bash
# Выкат ask-кода из HEAD репо в /opt/1c-mcp-reports на окне (только изменившееся, atomic mv).
set -euo pipefail
cd "$(dirname "$0")" || exit 1
# shellcheck disable=SC1091
. ./deploy-common.sh

SRC=/srv/1c/ubuntu/serenedb
DST="$DEPLOY_DST"

cd "$SRC"
md5sum serene_ask.py ask/*.py wiki_card*.sql wiki_passport.sql 2>/dev/null | sort -k2 > /tmp/ask-md5-local.txt
deploy_ssh "cd $DST && md5sum serene_ask.py ask/*.py wiki_card*.sql wiki_passport.sql 2>/dev/null | sort -k2 > /tmp/ask-md5-remote.txt || true"
deploy_scp -q /tmp/ask-md5-local.txt "${DEPLOY_SSH_HOST}:/tmp/ask-md5-new.txt"

CHANGED=$(deploy_ssh "join -j2 /tmp/ask-md5-remote.txt /tmp/ask-md5-new.txt 2>/dev/null | awk '\$2!=\$3{print \$1}' ; comm -13 <(awk '{print \$2}' /tmp/ask-md5-remote.txt|sort) <(awk '{print \$2}' /tmp/ask-md5-new.txt|sort)")
echo "CHANGED:"; echo "$CHANGED"
[ -z "$CHANGED" ] && { echo "изменений нет"; exit 0; }

mkdir -p /tmp/ask-dep && rm -rf /tmp/ask-dep && mkdir -p /tmp/ask-dep
for f in $CHANGED; do install -D -m 644 "$SRC/$f" "/tmp/ask-dep/$f"; done
tar -C /tmp/ask-dep -czf /tmp/ask-dep.tgz .
deploy_scp -q /tmp/ask-dep.tgz "${DEPLOY_SSH_HOST}:/tmp/ask-dep.tgz"
deploy_ssh 'set -e; mkdir -p /tmp/ask-stage && tar -C /tmp/ask-stage -xzf /tmp/ask-dep.tgz
cd /tmp/ask-stage
find . -type f | while read f; do
  rel=${f#./}
  install -m 644 "$rel" "/opt/1c-mcp-reports/$rel.new"
  mv "/opt/1c-mcp-reports/$rel.new" "/opt/1c-mcp-reports/$rel"
done
echo "deployed:"; find . -type f | sed "s|^\./||"
md5sum /opt/1c-mcp-reports/serene_ask.py | cut -c1-8'
