#!/bin/bash
# Выкат только corpus_build.sql на okna + замер строк корпуса до/после такта.
# Не трогает :8091 (ask). Использование: bash work/acceptance/deploy-corpus-build-okna.sh
set -euo pipefail
HOST=root@gpu-erw.timpul.pro
PORT=2202
KEY=~/.ssh/id_ed25519_deploy
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
SRC=/srv/1c/ubuntu/serenedb/corpus_build.sql
REMOTE=/opt/1c-mcp-reports/corpus_build.sql

scp -P "$PORT" "${SSH_OPTS[@]}" "$SRC" "$HOST:/tmp/corpus_build.sql.new"
scp -P "$PORT" "${SSH_OPTS[@]}" "/srv/1c/ubuntu/serenedb/corpus_init.sql" "$HOST:/tmp/corpus_init.sql.new"
ssh -p "$PORT" "${SSH_OPTS[@]}" "$HOST" bash -s <<'REMOTE'
set -euo pipefail
load_env() {
  for p in /etc/1c-mcp-reports.env /etc/1c-serene-pipeline-postgres.env; do
    [ -r "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"; [[ "$line" != *=* ]] && continue
      export "${line%%=*}=${line#*=}"
    done < "$p"
  done
}
load_env
export PGPASSWORD="${SERENEDB_PASSWORD:-}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
REMOTE_FILE=/opt/1c-mcp-reports/corpus_build.sql
INIT_FILE=/opt/1c-mcp-reports/corpus_init.sql
[ -f "$REMOTE_FILE" ] && cp -a "$REMOTE_FILE" "${REMOTE_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
[ -f "$INIT_FILE" ] && cp -a "$INIT_FILE" "${INIT_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
install -m 644 /tmp/corpus_build.sql.new "$REMOTE_FILE"
[ -f /tmp/corpus_init.sql.new ] && install -m 644 /tmp/corpus_init.sql.new "$INIT_FILE"
rm -f /tmp/corpus_build.sql.new
echo "DEPLOYED md5=$(md5sum "$REMOTE_FILE" | awk '{print $1}')"
echo "build.sh mode=$(stat -c '%a' /opt/1c-mcp-reports/build.sh)"
BEFORE=$(psql "$DSN" -tAc "SELECT count(*) FROM search_corpus" 2>/dev/null || echo "?")
echo "CORPUS_BEFORE=$BEFORE"
T0=$(date +%s)
systemctl start 1c-serene-pipeline@postgres
echo "TACTIC_STARTED t0=$T0"
REMOTE
