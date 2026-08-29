#!/usr/bin/env bash
# Установка скилла compound-ask в контур OpenClaw (штатный каталог workspace/skills).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
NAME="compound-ask"

usage() {
  echo "Usage: $0 [--workspace DIR] [--dry-run]"
  echo "  Копирует work/skill-decomp → <workspace>/skills/compound-ask/"
  echo "  По умолчанию workspace = ~/.openclaw/workspace (или OPENCLAW_WORKSPACE)"
  exit 1
}

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1"; usage ;;
  esac
done

DEST="$WORKSPACE/skills/$NAME"
echo "source: $SRC"
echo "dest:   $DEST"

if [[ $DRY -eq 1 ]]; then
  echo "(dry-run, no copy)"
  exit 0
fi

mkdir -p "$DEST"
rsync -a --delete \
  --exclude 'test_*.py' \
  --exclude '__pycache__' \
  --exclude 'fixtures/' \
  "$SRC/" "$DEST/"

echo "installed → $DEST"
echo "verify:   openclaw skills list | grep -i compound"
echo "reload:   /new в чате или openclaw gateway restart"
