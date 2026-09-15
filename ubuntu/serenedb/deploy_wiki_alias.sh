#!/bin/bash
# Выкат рантайма генератора словаря (wiki_alias) на сервер окна одной командой.
#
# Зачем: ночью 12–13.09 выкат был scp 11–13 файлов вручную + md5 + chmod
# (.claude/state/G7-checklist.md §1 п.1). На новой базе без SERENE_SRC_DIR
# обычный deploy.sh не закрывает удалённый /opt — этот скрипт закрывает.
#
# Не рестартует юниты и не запускает генерацию: только раскладка файлов.
# Запуск — слово владельца / systemctl start 1c-wiki-alias@…
#
# Использование:
#   WIKI_DEPLOY_TARGET=user@host[:port] WIKI_DEPLOY_SSH_KEY=~/.ssh/key \
#     bash ubuntu/serenedb/deploy_wiki_alias.sh
#   bash ubuntu/serenedb/deploy_wiki_alias.sh user@host[:port] [path-to-key]
#
# Назначение: ${WIKI_DEPLOY_DIR:-/opt/1c-mcp-reports}
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-${WIKI_DEPLOY_TARGET:-}}"
SSH_KEY="${2:-${WIKI_DEPLOY_SSH_KEY:-}}"
DEST="${WIKI_DEPLOY_DIR:-/opt/1c-mcp-reports}"

# Фактический набор вызовов wiki_alias.sh: каждый -f "$HERE/…" + локальные
# python3 ./… (плюс сам wiki_alias.sh). migrate_sep — не здесь (только по слову
# владельца). work/pipeline/alias_reask_*.py — дерево репо, не /opt.
FILES=(
  wiki_alias.sh
  wiki_alias_parse.py
  alias_infer_gateway.py
  alias_usage_log.py
  branch_alias.sh
  branch_alias_parse.py
  wiki_alias_init.sql
  wiki_alias_select_entity_batch.sql
  wiki_alias_select_measure_batch.sql
  wiki_alias_merge_entity.sql
  wiki_alias_merge_measures.sql
  wiki_alias_mark_skip.sql
  wiki_alias_mark_measure_skip.sql
  wiki_alias_collision_round.sql
  wiki_alias_collision_merge.sql
  wiki_alias_collision_left.sql
  wiki_alias_probe_mark.sql
  wiki_alias_probe_purge.sql
  wiki_alias_probe_still.sql
  wiki_alias_reask_init.sql
  wiki_alias_reask_select_entity_batch.sql
  wiki_alias_reask_merge_confirmed.sql
  wiki_alias_reask_journal.sql
  wiki_alias_publish.sql
  wiki_alias_fork_init.sql
  wiki_alias_dayfork_mark.sql
  wiki_alias_dayfork_batch.sql
  wiki_alias_dayfork_merge.sql
  wiki_alias_promote.sql
  wiki_alias_migrate_sep.sql
  wiki_alias_metric_a3.sql
  wiki_alias_quality_report.sql
  solr_synonyms_compile.sql
)

if [ -z "$TARGET" ]; then
  echo "нужен WIKI_DEPLOY_TARGET или \$1 (user@host[:port])" >&2
  exit 1
fi

SSH_PORT=22
SSH_HOST="$TARGET"
case "$TARGET" in
  *:*)
    _tail="${TARGET##*:}"
    if [[ "$_tail" =~ ^[0-9]+$ ]]; then
      SSH_PORT="$_tail"
      SSH_HOST="${TARGET%:"$_tail"}"
    fi
    ;;
esac

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -p "$SSH_PORT")
SCP_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -P "$SSH_PORT")
if [ -n "$SSH_KEY" ]; then
  SSH_OPTS+=(-i "$SSH_KEY")
  SCP_OPTS+=(-i "$SSH_KEY")
fi

LOCAL_PATHS=()
for f in "${FILES[@]}"; do
  if [ ! -f "$SRC/$f" ]; then
    echo "нет локального файла: $SRC/$f" >&2
    exit 1
  fi
  LOCAL_PATHS+=("$SRC/$f")
done

TS="$(date +%Y%m%d-%H%M%S)"
BAK="$DEST/.bak-deploy-$TS"

echo "цель=$SSH_HOST порт=$SSH_PORT dest=$DEST bak=$BAK файлов=${#FILES[@]}"

# Бэкап существующих на стороне назначения (только те, что будут заменены).
ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
  "DEST=$(printf '%q' "$DEST") BAK=$(printf '%q' "$BAK") FILES=$(printf '%q' "$(printf '%s ' "${FILES[@]}")") bash -s" <<'EOS'
set -euo pipefail
mkdir -p "$DEST" "$BAK"
for f in $FILES; do
  if [ -e "$DEST/$f" ]; then
    cp -a "$DEST/$f" "$BAK/$f"
  fi
done
echo "backup_ok $BAK"
EOS

scp "${SCP_OPTS[@]}" "${LOCAL_PATHS[@]}" "$SSH_HOST:$DEST/"

ssh "${SSH_OPTS[@]}" "$SSH_HOST" "chmod 755 $(printf '%q' "$DEST/wiki_alias.sh")"

LOCAL_MD5="$(
  cd "$SRC"
  md5sum "${FILES[@]}" | sort -k2
)"
REMOTE_MD5="$(
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
    "cd $(printf '%q' "$DEST") && md5sum $(printf '%q ' "${FILES[@]}") | sort -k2"
)"

MISMATCH=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  hash="${line%% *}"
  name="${line#* }"
  name="${name# }"
  name="${name#\*}"
  rhash="$(printf '%s\n' "$REMOTE_MD5" | awk -v n="$name" '$2==n || $2==("*" n) {print $1; exit}')"
  if [ -z "$rhash" ]; then
    echo "md5: на сервере нет $name" >&2
    MISMATCH=1
  elif [ "$hash" != "$rhash" ]; then
    echo "md5: несовпадение $name local=$hash remote=$rhash" >&2
    MISMATCH=1
  else
    echo "md5 ok  $name $hash"
  fi
done <<< "$LOCAL_MD5"

if [ "$MISMATCH" -ne 0 ]; then
  echo "md5-сверка провалена" >&2
  exit 1
fi

echo "{\"выкат\":\"ok\",\"цель\":\"$SSH_HOST\",\"dest\":\"$DEST\",\"bak\":\"$BAK\",\"файлов\":${#FILES[@]}}"
