#!/usr/bin/env bash
# Подготовка данных 26.08.1: store.db 26.07.3 напрямую не открывается
# (FATAL serialized data has 5 element(s), expected 4) — миграция EXPORT→IMPORT.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DSN="host=127.0.0.1 port=7895 user=postgres dbname=postgres"
PROD_DSN="host=127.0.0.1 port=7890 user=postgres dbname=postgres"
EXPORT_DIR="${F1_EXPORT_DIR:-/var/lib/serenedb/f1-export-prod}"
MARK="$ROOT/data/.bootstrap-imported"

psql_s() { psql "$DSN" -v ON_ERROR_STOP=1 "$@"; }

need_import=0
if [[ ! -f "$MARK" ]]; then
  n=$(psql "$DSN" -At -c "SELECT count(*) FROM search_corpus;" 2>/dev/null || echo 0)
  [[ "$n" -lt 1000 ]] && need_import=1
fi

if [[ "$need_import" -eq 1 ]]; then
  echo "bootstrap: import from $EXPORT_DIR"
  if [[ ! -f "$EXPORT_DIR/schema.sql" ]]; then
    echo "bootstrap: export отсутствует — делаем EXPORT с боя :7890" >&2
    psql "$PROD_DSN" -v ON_ERROR_STOP=1 \
      -c "EXPORT DATABASE '${EXPORT_DIR}' (FORMAT csv);"
  fi
  sed -e '/CREATE SCHEMA public/d' -e '/USING inverted ();;/d' -e 's/;;$;/;/' \
    "$EXPORT_DIR/schema.sql" >"$ROOT/results/schema-fixed.sql"
  psql_s -f "$ROOT/results/schema-fixed.sql"
  psql_s -f "$EXPORT_DIR/load.sql"
  # load.sql мог оборваться до resolver_index — добираем при нуле
  ri=$(psql_s -At -c "SELECT count(*) FROM resolver_index;")
  if [[ "$ri" == "0" ]] && [[ -f "$EXPORT_DIR/public_resolver_index.csv" ]]; then
    psql_s -c "COPY public.resolver_index FROM '${EXPORT_DIR}/public_resolver_index.csv' (FORMAT 'csv', delimiter ',', header 1, quote '\"');"
  fi
  date -Is >"$MARK"
fi

# search_idx: export создаёт таблицу search_idx; на бою это inverted-индекс на search_corpus
has_inv=$(psql_s -At -c "SELECT count(*) FROM duckdb_indexes() WHERE index_name='search_idx';")
if [[ "$has_inv" == "0" ]]; then
  echo "bootstrap: DROP TABLE search_idx (если из export) + CREATE inverted index"
  psql_s -q <<'SQL'
DROP TABLE IF EXISTS search_idx;
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict (
  template = 'text', locale = 'en_US.UTF-8', case = 'lower',
  stemming = false, accent = false, frequency = true, position = true, norm = true);
CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS search_dict_stem (
  template = 'copy_from', from = 'search_dict', stemming = true);
CREATE INDEX search_idx ON search_corpus
  USING inverted(doc search_dict, refs search_dict, src_table)
  INCLUDE (src_table, row_key, doc_date);
SQL
fi

echo "bootstrap: corpus=$(psql_s -At -c 'SELECT count(*) FROM search_corpus;') emb=$(psql_s -At -c 'SELECT count(*) FROM search_corpus WHERE emb IS NOT NULL;') resolver=$(psql_s -At -c 'SELECT count(*) FROM resolver_index;')"
