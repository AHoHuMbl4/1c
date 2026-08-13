#!/usr/bin/env bash
# refresh-dist.sh <новый generic exe>
# Обновляет дистрибутивы ВСЕХ слотов новым бинарём установщика, повторяя шаги
# 4 и 4б onboard-base.sh (комплекты и ссылки не меняются — меняется только exe).
# Заведён 13.08: до него обновление дистов делалось повторным прогоном
# onboard-base.sh, который заодно ПЕРЕВЫПУСКАЛ токен и сертификат слота, —
# на живой базе это разрывает канал у уже установленного клиента.
set -euo pipefail

NEW="${1:?использование: refresh-dist.sh <путь к новому 1c-ai.exe>}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_ROOT="$REPO/work/packet/dist"
KIT_ROOT="$REPO/work/packet/kit"
WEBEXT="$REPO/work/packet/webext-store"

[ -f "$NEW" ] || { echo "нет файла $NEW" >&2; exit 1; }
echo "новый бинарь: $(stat -c%s "$NEW") байт, sha256 $(sha256sum "$NEW" | cut -c1-16)…"
echo

# Эталон (из него onboard-base.sh берёт exe для новых баз).
install -m 600 "$NEW" "$DIST_ROOT/ut/1c-ai.exe"
echo "эталон work/packet/dist/ut/1c-ai.exe обновлён"

for D in "$DIST_ROOT"/*/; do
  BASE="$(basename "$D")"
  KIT="$KIT_ROOT/$BASE"
  if [ ! -d "$KIT" ]; then
    echo "  $BASE: комплекта нет — пропуск"
    continue
  fi
  install -m 600 "$NEW" "$D/1c-ai.exe"
  python3 - "$D" "$BASE" <<'PY'
import os, sys, zipfile
dist, base = sys.argv[1], sys.argv[2]
zp = os.path.join(dist, "1c-ai-%s.zip" % base)
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
    for f in ["1c-ai.exe", "packet-setup.json", "client.pfx", "ПРОЧТИМЕНЯ.txt"]:
        p = os.path.join(dist, f)
        if os.path.exists(p):
            z.write(p, f)
print("  %s: zip %d байт" % (base, os.path.getsize(zp)), end="")
PY
  python3 "$REPO/work/packet/pack-onefile.py" "$NEW" "$KIT" "$WEBEXT" \
          "$D/1c-ai-$BASE.exe" >/dev/null
  echo ", onefile $(stat -c%s "$D/1c-ai-$BASE.exe") байт"
done
echo
echo "готово. Выкладка на S3 — отдельным шагом (upload-dist.sh), комплекты не тронуты."
