#!/usr/bin/env bash
# Генерация metadata-okna.xml на машине с витриной okna (127.0.0.1:7890).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
load_env() {
  for p in /etc/1c-mcp-reports.env /etc/1c-serene-ask-postgres.env; do
    [ -r "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"
      [[ "$line" != *=* ]] && continue
      export "${line%%=*}=${line#*=}"
    done < "$p"
  done
}
load_env
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=serene_ro dbname=postgres}"
ENT="${ROOT}/docs/completeness-okna/contour.txt"
OUT="${ROOT}/work/manifest-diff/metadata-okna.xml"
python3 work/manifest-diff/gen_metadata_vitrine.py \
  --dsn "$DSN" \
  --entities-file "$ENT" \
  --out "$OUT"
python3 work/manifest-diff/test_gen_metadata_vitrine.py
