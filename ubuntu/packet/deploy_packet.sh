#!/bin/bash
# Раскладка контура пакетного транспорта (ubuntu/packet/) в рабочий каталог /opt/1c-packet.
#
# Как deploy.sh у конвейера: каждый файл кладётся в $DST/.<имя>.new и подменяется mv —
# атомарно на файл, внутри существующего каталога (родительский /opt рабочему аккаунту
# не пишется — проверено 06.08: подмена каталога целиком требует root).
#
# 🔴 Как и deploy.sh, НИКОГО не перезапускает: юниты продолжают исполнять версию,
# загруженную при старте. После раскладки перезапустить вручную:
#   systemctl restart 1c-packet-server 1c-packet-apply
# Тесты (test_*.py) и __pycache__ в рабочий каталог не кладутся.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${PACKET_DEPLOY_DIR:-/opt/1c-packet}"
FILES="packet_server.py packet_apply.py packet_config.py packet_crypto.py packet_kit.py"
# Исполняемые (755): авто-онбординг слота на юните (1c-serene-onboard@.service).
EXEC_FILES="onboard_unit.sh"

[ -d "$DST" ] || { echo "нет рабочего каталога $DST — сначала work/packet/setup-receiver.sh" >&2; exit 2; }

changed=0
for f in $FILES; do
  if [ -f "$DST/$f" ] && cmp -s "$SRC/$f" "$DST/$f"; then
    continue
  fi
  install -m 644 "$SRC/$f" "$DST/.$f.new"
  mv -f "$DST/.$f.new" "$DST/$f"
  echo "обновлён: $f"
  changed=1
done

for f in $EXEC_FILES; do
  if [ -f "$DST/$f" ] && cmp -s "$SRC/$f" "$DST/$f"; then
    continue
  fi
  install -m 755 "$SRC/$f" "$DST/.$f.new"
  mv -f "$DST/.$f.new" "$DST/$f"
  echo "обновлён (755): $f"
  changed=1
done

if [ "$changed" = 0 ]; then
  echo "без изменений — рабочий каталог не тронут"
  exit 0
fi
echo "разложено в $DST. Напоминание: юниты сами не перезапустятся —"
echo "  systemctl restart 1c-packet-server 1c-packet-apply"
