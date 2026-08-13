#!/usr/bin/env bash
# upload-dist.sh [база …]   — без аргументов: все слоты work/packet/dist/*
# Кладёт готовые файлы слота на S3 (installers/<base>/), public-read — шаг 5
# onboard-base.sh, вынесенный отдельно: обновление exe у существующих баз НЕ
# должно перевыпускать токен и сертификат (это разорвало бы канал живого клиента).
# Провайдеры берутся из ~/.s3-1c/env* — каждый файл задаёт свой endpoint/bucket.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_ROOT="$REPO/work/packet/dist"
BASES=("$@")
if [ ${#BASES[@]} -eq 0 ]; then
  for D in "$DIST_ROOT"/*/; do BASES+=("$(basename "$D")"); done
fi

shopt -s nullglob
ENVS=("$HOME"/.s3-1c/env "$HOME"/.s3-1c/env-*)
[ ${#ENVS[@]} -gt 0 ] || { echo "нет файлов окружения ~/.s3-1c/env*" >&2; exit 1; }

for ENVF in "${ENVS[@]}"; do
  echo "== провайдер $(basename "$ENVF")"
  set -a; source "$ENVF"; set +a
  for BASE in "${BASES[@]}"; do
    "$HOME/.venvs/s3/bin/python" - "$DIST_ROOT/$BASE" "$BASE" <<'PY'
import boto3, os, sys
dist, base = sys.argv[1], sys.argv[2]
if not os.path.isdir(dist):
    print("  %s: слота нет — пропуск" % base); raise SystemExit(0)
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"],
                  aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                  region_name=os.environ.get("S3_REGION", "fsn1"))
b = os.environ["S3_BUCKET"]
for fn, key in [("1c-ai-%s.zip" % base, "installers/%s/1c-ai-%s.zip" % (base, base)),
                ("1c-ai-%s.exe" % base, "installers/%s/1c-ai-%s.exe" % (base, base)),
                ("1c-ai.exe",           "installers/%s/1c-ai.exe" % base)]:
    p = os.path.join(dist, fn)
    if not os.path.exists(p):
        print("  %s: нет %s — пропуск" % (base, fn)); continue
    s3.upload_file(p, b, key)
    s3.put_object_acl(Bucket=b, Key=key, ACL="public-read")
    print("  ok %s (%d байт)" % (key, os.path.getsize(p)))
PY
  done
done
echo "готово."
