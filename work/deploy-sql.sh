#!/bin/bash
# Выкат такт-SQL из HEAD репо в /opt/1c-mcp-reports на окне (только изменившееся, atomic mv).
# Список — SQL такта из build.sh / wiki_publish.sh (pipeline.sh → build.sh).
# --dry: сверка md5 без доставки. --offline-dry: только локальный список/наличие (без SSH).
set -euo pipefail
cd "$(dirname "$0")" || exit 1
# shellcheck disable=SC1091
. ./deploy-common.sh

SRC="${DEPLOY_SQL_SRC:-/srv/1c/ubuntu/serenedb}"
DST="$DEPLOY_DST"
TAG=sql-dep

# Фактический список SQL такта (build.sh + wiki_publish.sh).
SQL_FILES=(
  corpus_init.sql
  corpus_precheck.sql
  corpus_build.sql
  corpus_merge.sql
  period_relative_forms_load.sql
  resolver_build.sql
  coverage_build.sql
  solr_synonyms_compile.sql
  entity_card_build.sql
  corpus_postcheck.sql
  wiki_build.sql
  wiki_passport.sql
  wiki_card_build.sql
)

DRY=0
OFFLINE=0
for a in "$@"; do
  case "$a" in
    --dry) DRY=1 ;;
    --offline-dry) OFFLINE=1; DRY=1 ;;
    -h|--help)
      echo "usage: $0 [--dry|--offline-dry]"
      exit 0
      ;;
  esac
done

cd "$SRC"
missing=0
for f in "${SQL_FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "нет файла в репо: $f" >&2
    missing=1
  fi
done
[ "$missing" = 0 ] || exit 1

if [ "$OFFLINE" = 1 ]; then
  echo "offline-dry: SQL такта (${#SQL_FILES[@]} файлов)"
  md5sum "${SQL_FILES[@]}" | sort -k2
  echo "изменений не сверяли (нет SSH)"
  exit 0
fi

md5sum "${SQL_FILES[@]}" 2>/dev/null | sort -k2 > "/tmp/${TAG}-md5-local.txt"
deploy_ssh "cd $DST && md5sum ${SQL_FILES[*]} 2>/dev/null | sort -k2 > /tmp/${TAG}-md5-remote.txt || true"
deploy_scp -q "/tmp/${TAG}-md5-local.txt" "${DEPLOY_SSH_HOST}:/tmp/${TAG}-md5-new.txt"

CHANGED=$(deploy_ssh "join -j2 /tmp/${TAG}-md5-remote.txt /tmp/${TAG}-md5-new.txt 2>/dev/null | awk '\$2!=\$3{print \$1}' ; comm -13 <(awk '{print \$2}' /tmp/${TAG}-md5-remote.txt|sort) <(awk '{print \$2}' /tmp/${TAG}-md5-new.txt|sort)")
echo "CHANGED:"; echo "$CHANGED"
[ -z "$CHANGED" ] && { echo "изменений нет"; exit 0; }

if [ "$DRY" = 1 ]; then
  echo "dry: доставка пропущена"
  exit 0
fi

mkdir -p "/tmp/${TAG}" && rm -rf "/tmp/${TAG}" && mkdir -p "/tmp/${TAG}"
for f in $CHANGED; do install -D -m 644 "$SRC/$f" "/tmp/${TAG}/$f"; done
tar -C "/tmp/${TAG}" -czf "/tmp/${TAG}.tgz" .
deploy_scp -q "/tmp/${TAG}.tgz" "${DEPLOY_SSH_HOST}:/tmp/${TAG}.tgz"
deploy_ssh "set -e; mkdir -p /tmp/${TAG}-stage && tar -C /tmp/${TAG}-stage -xzf /tmp/${TAG}.tgz
cd /tmp/${TAG}-stage
find . -type f | while read f; do
  rel=\${f#./}
  install -m 644 \"\$rel\" \"${DST}/\$rel.new\"
  mv \"${DST}/\$rel.new\" \"${DST}/\$rel\"
done
echo \"deployed:\"; find . -type f | sed 's|^\\./||'"
