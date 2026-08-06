#!/bin/bash
# Раскладка контура пакетного транспорта (ubuntu/packet/) в рабочий каталог /opt/1c-packet.
#
# Атомарной подменой, как deploy.sh у конвейера: рабочий каталог собирается заново в
# соседнем и подменяется одним mv — читающий юнит никогда не видит половину файлов.
#
# 🔴 Как и deploy.sh, НИКОГО не перезапускает: юниты продолжают исполнять версию,
# загруженную при старте. После раскладки перезапустить вручную:
#   systemctl restart 1c-packet-server 1c-packet-apply
# Тесты (test_*.py) и __pycache__ в рабочий каталог не кладутся.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${PACKET_DEPLOY_DIR:-/opt/1c-packet}"
TMP="${DST}.new.$$"
FILES="packet_server.py packet_apply.py packet_config.py packet_crypto.py packet_kit.py"

mkdir -p "$TMP"
changed=0
for f in $FILES; do
  if [ -f "$DST/$f" ] && cmp -s "$SRC/$f" "$DST/$f"; then
    cp "$DST/$f" "$TMP/$f"
  else
    install -m 644 "$SRC/$f" "$TMP/$f"
    echo "обновлён: $f"
    changed=1
  fi
done

if [ "$changed" = 0 ]; then
  rm -rf "$TMP"
  echo "без изменений — рабочий каталог не тронут"
  exit 0
fi

OLD="${DST}.old.$$"
if [ -d "$DST" ]; then mv -T "$DST" "$OLD"; fi
mv -T "$TMP" "$DST"
rm -rf "$OLD"
echo "разложено в $DST ($(echo $FILES | wc -w) файлов). Напоминание: юниты сами не перезапустятся —"
echo "  systemctl restart 1c-packet-server 1c-packet-apply"
