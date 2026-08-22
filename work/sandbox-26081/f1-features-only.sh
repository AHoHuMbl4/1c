#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RES="$ROOT/results"
DSN="host=127.0.0.1 port=7895 user=postgres dbname=postgres"
PROD_DSN="host=127.0.0.1 port=7890 user=postgres dbname=postgres"
psql_s() { psql "$DSN" -v ON_ERROR_STOP=1 "$@"; }
{
  echo "feature|result"
  psql_s -q -c "CREATE TEXT SEARCH DICTIONARY f1_syn (template='solr_synonyms', SYNONYMS='car, automobile, auto');"
  echo "solr_synonyms_short|$(psql_s -At -c "SELECT ts_lexize('f1_syn','car');")"
  psql "$PROD_DSN" -At -c "SELECT coalesce(aliases,'x') FROM search_entity_alias LIMIT 260;" \
    | awk -F',' '{for(i=1;i<=NF && i<=3;i++){gsub(/^ +| +$/,"",$i); if(length($i)>1) print $i ", alias" NR}}' \
    | head -260 >"$RES/synonyms-long.txt"
  n=$(wc -l <"$RES/synonyms-long.txt")
  syn=$(sed "s/'/''/g" "$RES/synonyms-long.txt" | paste -sd $'\n' -)
  if psql_s -q -c "CREATE TEXT SEARCH DICTIONARY f1_syn_long (template='solr_synonyms', SYNONYMS='${syn}');" 2>"$RES/syn-long.err"; then
    echo "solr_synonyms_${n}_lines|OK"
  else
    echo "solr_synonyms_${n}_lines|FAIL $(head -1 "$RES/syn-long.err")"
  fi
  psql_s -At -c "SELECT 1 FROM (SELECT rank() OVER (ORDER BY k) r FROM f1_t5 LIMIT 3) x;" \
    && echo "rank_over|OK" || echo "rank_over|FAIL"
  psql_s -At -c "SELECT function_name FROM duckdb_functions() WHERE lower(function_name) LIKE '%refresh%' LIMIT 8;" \
    | tr '\n' ';' | sed 's/;$//' | awk '{print "refresh_funcs|" $0}'
  exp="$ROOT/results/export-test"
  rm -rf "$exp"
  mkdir -p "$exp"
  if psql_s -q -c "EXPORT DATABASE '${exp}' (FORMAT csv);" 2>"$RES/export.err"; then
    echo "export_database|OK nfiles=$(find "$exp" -type f | wc -l)"
  else
    echo "export_database|FAIL $(head -1 "$RES/export.err")"
  fi
} | tee "$RES/features.tsv"
