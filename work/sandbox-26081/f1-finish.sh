#!/usr/bin/env bash
# Дозавершение Ф1: recall, nprobe, bulk embed, okna kNN, export/import.
# Бой :7890 не трогаем. Песочница уже поднята или стартуется здесь.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RES="$ROOT/results"
DSN="host=127.0.0.1 port=7895 user=postgres dbname=postgres"
mkdir -p "$RES"

if ! psql "$DSN" -At -c "SELECT 1;" >/dev/null 2>&1; then
  "$ROOT/start-sandbox.sh"
fi

echo "=== Ф1 finish $(date -Is) ==="

chmod +x "$ROOT"/{recall-measure,quant-grid-measure,bulk-embed-measure,okna-knn-measure,export-import-measure}.sh

echo "--- recall ---"
"$ROOT/recall-measure.sh" "$DSN" "$RES/quant-recall.tsv"

echo "--- nprobe grid ---"
"$ROOT/quant-grid-measure.sh" "$DSN" "$RES/quant-grid.tsv"

echo "--- bulk embed ---"
"$ROOT/bulk-embed-measure.sh" "$RES/bulk-embed.tsv"

echo "--- okna kNN exact vs ivf ---"
"$ROOT/okna-knn-measure.sh" "$DSN" "$RES/okna-knn.tsv"

echo "--- export/import ---"
"$ROOT/export-import-measure.sh"

echo "=== Ф1 finish done $(date -Is) ==="
