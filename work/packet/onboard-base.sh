#!/bin/bash
# Онбординг НОВОЙ базы на пакетный транспорт (частый процесс «новый бизнес»,
# решение владельца 08.08). Одна база = один комплект = один слот приёмника.
#
# Использование из рабочей сессии:
#     bash work/packet/onboard-base.sh <base_id>
# base_id — короткая метка слота ([a-z0-9_-]), называть так, чтобы КЛИЕНТ узнал
# свою базу (не «ut», а «ромашка-ут»): установщик показывает её человеку.
#
# Что делает (всё, кроме одноразовой установки юнита — см. ниже):
#   1. комплект: ubuntu/packet/packet_kit.py <base> (токен, age identity,
#      клиентский сертификат mTLS, packet-setup.json) → work/packet/kit/<base>/;
#      повторный прогон = ротация токена/сертификата, identity сохраняется (§3);
#   2. слот на приёмнике: systemctl start 1c-packet-onboard@<base> (root-часть
#      через polkit — identity в /etc, merge в файл баз, каталог снимка $metadata);
#   3. проверка: mTLS /health релея сертификатом НОВОЙ базы;
#   4. дистрибутив установщика: work/packet/dist/<base>/ (1c-ai.exe — тот же
#      бинарь, что в dist/ut + packet-setup.json + client.pfx + ПРОЧТИМЕНЯ.txt),
#      zip;
#   5. выкладка на S3: installers/<base>/1c-ai-<base>.zip (+ 1c-ai.exe), public-read.
#
# Одноразовая подготовка (владелец): установить юнит —
#   sudo install -m 644 /srv/1c/ubuntu/packet/systemd/1c-packet-onboard@.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#
# После выдачи комплекта клиенту дальше работают другие контуры (не этот скрипт):
# первый пакет kind=meta кладёт снимок $metadata, затем строятся витрина
# (work/pipeline/build.sh с ETL_ODATA_BASE=/var/lib/serenedb/packet-meta/<base>)
# и контур агента (packet_config <base>). См. docs/PACKET_ONBOARDING.md.
set -euo pipefail

REPO=/srv/1c
BASE="${1:-}"
case "$BASE" in
  ""|*[!a-z0-9_-]*) echo "использование: bash work/packet/onboard-base.sh <base_id>  ([a-z0-9_-])" >&2; exit 2 ;;
esac

KIT="$REPO/work/packet/kit/$BASE"
DIST="$REPO/work/packet/dist/$BASE"
SRC_DIST="$REPO/work/packet/dist/ut"   # эталонный бинарь установщика (тот же для всех баз)

cd "$REPO"

echo "== 1/5 комплект $BASE (packet_kit.py)"
PACKET_AGE_BIN=/opt/1c-packet/bin/age PACKET_AGE_KEYGEN_BIN=/opt/1c-packet/bin/age-keygen \
  python3 ubuntu/packet/packet_kit.py "$BASE"

echo "== 2/5 слот на приёмнике (root-часть через юнит)"
if ! systemctl start "1c-packet-onboard@$BASE"; then
  echo "ОТКАЗ polkit/юнита. Владельцу — один раз установить юнит:" >&2
  echo "  sudo install -m 644 $REPO/ubuntu/packet/systemd/1c-packet-onboard@.service /etc/systemd/system/" >&2
  echo "  sudo systemctl daemon-reload" >&2
  echo "  и повторить: systemctl start 1c-packet-onboard@$BASE" >&2
  exit 1
fi
# проверка факта: запись базы появилась в файле приёмника (читаем через группу 1c-secrets)
python3 - "$BASE" << 'EOF'
import json, sys
base = sys.argv[1]
doc = json.load(open("/etc/1c-packet-bases.json", encoding="utf-8"))
assert base in doc, f"базы {base} нет в /etc/1c-packet-bases.json после root-части"
assert doc[base].get("identity", "").endswith(f"-{base}.key"), "identity не та"
print(f"слот активен: баз в приёмнике {len(doc)} ({', '.join(sorted(doc))})")
EOF

echo "== 3/5 проверка mTLS сертификатом $BASE (сквозная: релей → приёмник)"
# Сертификат выдан секунды назад: при отставании часов релея он «ещё не
# действителен» (bad certificate). Повторяем до минуты, прежде чем падать
# (замер 09.08: проверка через ~1 мин после выпуска проходит).
ok=""
for i in 1 2 3; do
  out=$(curl -s --max-time 20 --cert "$KIT/client.crt" --key "$KIT/client-key.pem" \
        https://1c-gate.timpul.ru/health) && { ok=1; break; }
  echo "mTLS попытка $i не прошла — пауза 20с (сертификат мог не наступить по notBefore)"
  sleep 20
done
[ -n "$ok" ] || { echo "mTLS не прошёл после 3 попыток — стоп" >&2; exit 1; }
echo "$out"
echo

echo "== 4/5 дистрибутив $DIST"
[ -f "$SRC_DIST/1c-ai.exe" ] || { echo "нет эталонного $SRC_DIST/1c-ai.exe" >&2; exit 1; }
mkdir -p "$DIST"
cp "$SRC_DIST/1c-ai.exe" "$DIST/1c-ai.exe"
cp "$KIT/packet-setup.json" "$DIST/packet-setup.json"
cp "$KIT/client.pfx" "$DIST/client.pfx"
[ -f "$SRC_DIST/ПРОЧТИМЕНЯ.txt" ] && cp "$SRC_DIST/ПРОЧТИМЕНЯ.txt" "$DIST/ПРОЧТИМЕНЯ.txt"
python3 - "$DIST" "$BASE" << 'EOF'
import os, sys, zipfile
dist, base = sys.argv[1], sys.argv[2]
zp = os.path.join(dist, f"1c-ai-{base}.zip")
files = ["1c-ai.exe", "packet-setup.json", "client.pfx", "ПРОЧТИМЕНЯ.txt"]
with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        p = os.path.join(dist, f)
        if os.path.exists(p):
            z.write(p, f)
print("zip:", zp, os.path.getsize(zp), "байт")
EOF

echo "== 5/5 выкладка на S3 (installers/$BASE/)"
set -a; source "${S3_ENV:-$HOME/.s3-1c/env}"; set +a
~/.venvs/s3/bin/python - "$DIST" "$BASE" << 'EOF'
import boto3, os, sys
dist, base = sys.argv[1], sys.argv[2]
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                  aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                  region_name=os.environ.get("S3_REGION", "fsn1"))
b = os.environ["S3_BUCKET"]
for fn, key in [(f"1c-ai-{base}.zip", f"installers/{base}/1c-ai-{base}.zip"),
                ("1c-ai.exe", f"installers/{base}/1c-ai.exe")]:
    s3.upload_file(os.path.join(dist, fn), b, key)
    s3.put_object_acl(Bucket=b, Key=key, ACL="public-read")
    print("s3 ok:", key)
endpoint = os.environ["S3_ENDPOINT"].rstrip("/")  # path-style (замер 07.08)
print(f"ССЫЛКА ДЛЯ КЛИЕНТА: {endpoint}/{b}/installers/{base}/1c-ai-{base}.zip")
EOF

echo "== готово: база $BASE на канале. Дальше — выдать ссылку клиенту; контур и витрина строятся после первого meta (docs/PACKET_ONBOARDING.md)."
