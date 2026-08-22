#!/usr/bin/env bash
# Распаковка tarball 26.08.1 в каталог песочницы (.deb не ставим).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
TARBALL="$ROOT/serenedb-26.08.1-linux-amd64.tar.gz"
BIN="$ROOT/serened"

if [[ -x "$BIN" ]]; then
  echo "OK: $BIN уже есть"
  "$BIN" --version 2>&1 | head -1 || true
  exit 0
fi

if [[ ! -f "$TARBALL" ]]; then
  echo "BLOCKER: нет $TARBALL" >&2
  echo "Скачать (38 МБ):" >&2
  echo "  curl -fsSL -o '$TARBALL' \\" >&2
  echo "    'https://github.com/serenedb/serenedb/releases/download/v26.08.1/serenedb-26.08.1-linux-amd64.tar.gz'" >&2
  exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -xzf "$TARBALL" -C "$tmp"
found=$(find "$tmp" -name serened -type f | head -1)
if [[ -z "$found" ]]; then
  echo "ERROR: serened не найден в tarball" >&2
  exit 1
fi
cp "$found" "$BIN"
chmod +x "$BIN"
echo "OK: распакован $BIN"
"$BIN" --version 2>&1 | head -1 || true
