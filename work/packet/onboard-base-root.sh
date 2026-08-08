#!/bin/sh
# Root-часть онбординга базы пакетного транспорта (контракт docs/PACKET_CONTRACT.md).
#
# Зовётся двумя способами:
#   systemctl start 1c-packet-onboard@<base_id>   — из рабочей сессии (polkit 1c-*)
#   sudo sh /srv/1c/work/packet/onboard-base-root.sh <base_id>   — владельцем напрямую
#
# Делает ровно три вещи, которые сессии по правам недоступны:
#   1. age identity комплекта → /etc/1c-packet-age-<base>.key (640 root:1c-secrets);
#   2. MERGE записи базы в /etc/1c-packet-bases.json (НЕ overwrite — иначе соседние
#      базы потеряют токены; приёмник перечитывает файл сам по mtime, рестарт не нужен);
#   3. каталог снимка $metadata /var/lib/serenedb/packet-meta/<base> (serenedb:serenedb).
#
# Идемпотентно: повторный прогон просто перезаписывает те же значения.
set -eu

REPO=/srv/1c
BASE="${1:-}"

case "$BASE" in
  ""|*[!a-z0-9_-]*) echo "onboard-base-root: недопустимый base_id «$BASE» ([a-z0-9_-])" >&2; exit 2 ;;
esac

KIT="$REPO/work/packet/kit/$BASE"
[ -f "$KIT/age.key" ] || { echo "onboard-base-root: нет комплекта $KIT — сначала packet_kit.py (onboard-base.sh $BASE)" >&2; exit 1; }
[ -f "$KIT/bases-entry.json" ] || { echo "onboard-base-root: нет $KIT/bases-entry.json" >&2; exit 1; }

echo "== identity age"
install -m 640 -o root -g 1c-secrets "$KIT/age.key" "/etc/1c-packet-age-$BASE.key"

echo "== merge в /etc/1c-packet-bases.json"
python3 - "$KIT/bases-entry.json" "$BASE" << 'EOF'
import json, os, sys

entry_path, base = sys.argv[1], sys.argv[2]
bases_path = "/etc/1c-packet-bases.json"
entry = json.load(open(entry_path, encoding="utf-8"))
if base not in entry:
    sys.exit(f"onboard-base-root: в {entry_path} нет записи «{base}»")
doc = {}
if os.path.exists(bases_path):
    doc = json.load(open(bases_path, encoding="utf-8"))
rec = entry[base]
rec["identity"] = f"/etc/1c-packet-age-{base}.key"
doc[base] = rec
tmp = bases_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
os.replace(tmp, bases_path)
print(f"баз в файле: {len(doc)} ({', '.join(sorted(doc))})")
EOF
chown root:1c-secrets /etc/1c-packet-bases.json
chmod 640 /etc/1c-packet-bases.json

echo "== каталог снимка \$metadata"
install -d -m 755 -o serenedb -g serenedb "/var/lib/serenedb/packet-meta/$BASE"

echo "== готово: слот $BASE на приёмнике активен (перечитывание по mtime, рестарт не нужен)"
