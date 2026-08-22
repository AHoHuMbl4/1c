#!/usr/bin/env bash
# Ф1: полный прогон замеров на песочнице 26.08.1 :7895
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RES="$ROOT/results"
DSN="host=127.0.0.1 port=7895 user=postgres dbname=postgres"
PROD_DSN="host=127.0.0.1 port=7890 user=postgres dbname=postgres"
mkdir -p "$RES"
exec > >(tee -a "$RES/f1-run.log") 2>&1

echo "=== Ф1 $(date -Is) ==="

"$ROOT/extract.sh"
"$ROOT/start-sandbox.sh"

psql_s() { psql "$DSN" -v ON_ERROR_STOP=1 "$@"; }
psql_prod() { psql "$PROD_DSN" -v ON_ERROR_STOP=1 "$@"; }

peak_rss_kb() {
  local best=0 p rss
  while read -r p; do
    [[ -z "$p" ]] && continue
    rss=$(awk '/VmRSS/{print $2; exit}' "/proc/$p/status" 2>/dev/null || echo 0)
    [[ "$rss" -gt "$best" ]] && best=$rss
  done < <(pgrep -f "flagfile=$ROOT/sandbox.conf" 2>/dev/null || true)
  echo "$best"
}

# §3 Совместимость
echo "--- §3 compat ---"
{
  echo "key|sandbox|prod|match"
  echo "version|$(psql_s -At -c 'SELECT version();')|$(psql_prod -At -c 'SELECT version();')|n/a"
  for tbl in search_corpus search_tables resolver_index search_entity_alias; do
    sb=$(psql_s -At -c "SELECT count(*) FROM $tbl")
    pb=$(psql_prod -At -c "SELECT count(*) FROM $tbl")
    m=$([[ "$sb" == "$pb" ]] && echo yes || echo NO)
    echo "count_${tbl}|${sb}|${pb}|${m}"
  done
  ts=$(psql_s -At -c "SELECT count(*) FROM search_idx WHERE doc @@ 'продажи'")
  tp=$(psql_prod -At -c "SELECT count(*) FROM search_idx WHERE doc @@ 'продажи'")
  echo "text_продажи|${ts}|${tp}|$([[ "$ts" == "$tp" ]] && echo yes || echo NO)"
  echo "emb_not_null|$(psql_s -At -c 'SELECT count(*) FROM search_corpus WHERE emb IS NOT NULL')|$(psql_prod -At -c 'SELECT count(*) FROM search_corpus WHERE emb IS NOT NULL')|check"
} | tee "$RES/compat.tsv"

# §4 порог 5k/6k (завершение vs зависание)
echo "--- §4 threshold 5k/6k ---"
psql_s -q <<'SQL'
DROP TABLE IF EXISTS f1_t5, f1_t6 CASCADE;
CREATE TABLE f1_t5 AS SELECT i::VARCHAR AS k,
  list_transform(range(1024), x -> (random()::FLOAT * 2 - 1))::FLOAT[1024] AS emb
  FROM range(5000) s(i);
CREATE TABLE f1_t6 AS SELECT i::VARCHAR AS k,
  list_transform(range(1024), x -> (random()::FLOAT * 2 - 1))::FLOAT[1024] AS emb
  FROM range(6000) s(i);
SQL
{
  echo "test|metric"
  "$ROOT/measure-cmd.sh" ivf_5k_1024_ip 120 \
    "CREATE INDEX f1_t5_idx ON f1_t5 USING inverted(k, emb ivf (metric = 'ip'));"
  "$ROOT/measure-cmd.sh" ivf_6k_1024_ip 120 \
    "CREATE INDEX f1_t6_idx ON f1_t6 USING inverted(k, emb ivf (metric = 'ip'));" || true
} | tee "$RES/ivf-threshold.tsv"

# §4 cancel — ≥500k строк, сборка минуты; pg_cancel_backend
echo "--- §4 cancel (500k) ---"
psql_s -q <<'SQL'
DROP TABLE IF EXISTS f1_cancel500k CASCADE;
CREATE TABLE f1_cancel500k AS SELECT i::VARCHAR AS k,
  list_transform(range(1024), x -> (random()::FLOAT * 2 - 1))::FLOAT[1024] AS emb
  FROM range(500000) s(i);
SQL
{
  echo "phase|value"
  echo "rows|500000"
  echo "build_start|$(date -Is)"
  psql "$DSN" -v ON_ERROR_STOP=0 \
    -c "CREATE INDEX f1_cancel500k_idx ON f1_cancel500k USING inverted(k, emb ivf (metric = 'ip'));" &
  cpid=$!
  bid=""
  wait_found=0
  for w in $(seq 1 90); do
    bid=$(psql_s -At -c "SELECT pid FROM pg_stat_activity WHERE state = 'active' AND query ILIKE '%CREATE INDEX%f1_cancel500k_idx%' AND pid != pg_backend_pid() LIMIT 1;" 2>/dev/null || true)
    if [[ -n "$bid" ]]; then wait_found=$((w * 2)); break; fi
    sleep 2
  done
  echo "backend_pid_found_after_sec|${wait_found}|pid=${bid:-NONE}"
  # даём сборке поработать ≥60 с до cancel
  sleep 60
  rss_before=$(peak_rss_kb)
  if [[ -n "$bid" ]]; then
    cancel=$(psql_s -At -c "SELECT pg_cancel_backend(${bid});" 2>/dev/null || echo ERR)
    echo "pg_cancel_backend|pid=${bid}|result=${cancel}|rss_kb_before=${rss_before}"
  else
    echo "pg_cancel_backend|SKIPPED|no_backend_pid"
  fi
  for t in 15 30 60; do
    sleep 15
    still=$(psql_s -At -c "SELECT count(*) FROM pg_stat_activity WHERE query ILIKE '%CREATE INDEX%f1_cancel500k_idx%' AND state = 'active';" 2>/dev/null || echo ERR)
    rss=$(peak_rss_kb)
    echo "after_${t}s|active_builds=${still}|rss_kb=${rss}|client_alive=$(kill -0 "$cpid" 2>/dev/null && echo yes || echo no)"
  done
  kill -9 "$cpid" 2>/dev/null || true
} | tee "$RES/ivf-cancel.tsv"

# §4 WAL — рестарт С wal (прерванная сборка должна реплеиться)
echo "--- §4 wal restart (keep-wal) ---"
"$ROOT/stop-sandbox.sh"
wal=$(stat -c%s "$ROOT/data/engine_duckdb/store.db.wal" 2>/dev/null || echo 0)
echo "wal_bytes|${wal}" | tee "$RES/ivf-wal.tsv"
t0=$(date +%s)
if "$ROOT/start-sandbox.sh" --keep-wal; then
  t1=$(date +%s)
  echo "restart|OK|startup_sec=$((t1 - t0))" | tee -a "$RES/ivf-wal.tsv"
  echo "version_after_restart|$(psql_s -At -c 'SELECT version();')" | tee -a "$RES/ivf-wal.tsv"
  echo "select_smoke|$(psql_s -At -c 'SELECT count(*) FROM search_corpus;')" | tee -a "$RES/ivf-wal.tsv"
else
  echo "restart|FAIL|startup_sec=$(( $(date +%s) - t0 ))" | tee -a "$RES/ivf-wal.tsv"
  exit 1
fi

# §4 okna-scale 1.23M
echo "--- §4 okna 1.23M ---"
psql_s -q <<'SQL'
DROP TABLE IF EXISTS f1_okna CASCADE;
CREATE TABLE f1_okna AS SELECT i::VARCHAR AS k,
  list_transform(range(1024), x -> (random()::FLOAT * 2 - 1))::FLOAT[1024] AS emb
  FROM range(1230000) s(i);
SQL
"$ROOT/measure-cmd.sh" ivf_okna_1230000 3600 \
  "CREATE INDEX f1_okna_idx ON f1_okna USING inverted(k, emb ivf (metric = 'ip'));" \
  | tee "$RES/ivf-okna-scale.tsv" || true
idx_sz=$(psql_s -At -c "SELECT coalesce(sum(estimated_size),0) FROM duckdb_indexes() WHERE index_name='f1_okna_idx';" 2>/dev/null || echo ERR)
echo "index_est_bytes|${idx_sz}" | tee -a "$RES/ivf-okna-scale.tsv"

# §5 quantization — реальные векторы search_corpus (без индекса на baseline-таблице)
echo "--- §5 quant (corpus emb) ---"
psql_s -q <<'SQL'
DROP TABLE IF EXISTS f1_corpus_vec CASCADE;
CREATE TABLE f1_corpus_vec AS
  SELECT src_table || '|' || row_key AS k, emb
  FROM search_corpus WHERE emb IS NOT NULL;
SQL
corpus_n=$(psql_s -At -c "SELECT count(*) FROM f1_corpus_vec;")
norm_sample=$(psql_s -At -c "
  SELECT round(avg(sq), 4) FROM (
    SELECT sqrt(list_sum(list_transform(emb, x -> x*x))) AS sq
    FROM f1_corpus_vec USING SAMPLE 1000 ROWS
  ) s;" 2>/dev/null || psql_s -At -c "
  SELECT round(avg(sq), 4) FROM (
    SELECT sqrt(list_sum(list_transform(emb, x -> x*x))) AS sq
    FROM f1_corpus_vec LIMIT 1000
  ) s;")
echo "corpus_rows|${corpus_n}" | tee "$RES/quant-corpus.tsv"
echo "norm_mean_sample|${norm_sample}" | tee -a "$RES/quant-corpus.tsv"

for q in ip sq8 rabitq; do
  psql_s -q -c "DROP INDEX IF EXISTS f1_corpus_${q}_idx;"
  if [[ "$q" == "ip" ]]; then
    sql="CREATE INDEX f1_corpus_ip_idx ON f1_corpus_vec USING inverted(k, emb ivf (metric = 'ip'));"
    tag="quant_build_ip_none"
  else
    sql="CREATE INDEX f1_corpus_${q}_idx ON f1_corpus_vec USING inverted(k, emb ivf (metric = 'ip', quant = '${q}'));"
    tag="quant_build_${q}"
  fi
  "$ROOT/measure-cmd.sh" "$tag" 1800 "$sql" | tee -a "$RES/quant-build.tsv" || true
done

# recall@10 + nprobe grid (отдельные скрипты — один сеанс SQL на recall)
echo "--- §5 recall ---"
chmod +x "$ROOT/recall-measure.sh" "$ROOT/quant-grid-measure.sh"
"$ROOT/recall-measure.sh" "$DSN" "$RES/quant-recall.tsv"

echo "--- §5 nprobe grid ---"
"$ROOT/quant-grid-measure.sh" "$DSN" "$RES/quant-grid.tsv"

# §6 features
echo "--- §6 features ---"
{
  echo "feature|result"
  psql_s -q -c "CREATE TEXT SEARCH DICTIONARY f1_syn (template='solr_synonyms', SYNONYMS='car, automobile, auto');"
  echo "solr_synonyms_short|$(psql_s -At -c "SELECT ts_lexize('f1_syn','car');")"
  psql_prod -At -c "SELECT coalesce(aliases,'x') FROM search_entity_alias LIMIT 260;" \
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
  psql_s -At -c "SELECT name FROM duckdb_functions() WHERE lower(name) LIKE '%refresh%' LIMIT 8;" \
    | tr '\n' ';' | sed 's/;$//' | awk '{print "refresh_funcs|" $0}'
  exp="$ROOT/results/export-test"; rm -rf "$exp"; mkdir -p "$exp"
  if psql_s -q -c "EXPORT DATABASE '${exp}' (FORMAT csv);" 2>"$RES/export.err"; then
    echo "export_database|OK nfiles=$(find "$exp" -type f | wc -l)"
  else
    echo "export_database|FAIL $(head -1 "$RES/export.err")"
  fi
} | tee "$RES/features.tsv"

echo "=== Ф1 done $(date -Is) ==="
"$ROOT/stop-sandbox.sh"
