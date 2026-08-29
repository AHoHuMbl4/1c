#!/bin/bash
# Журнал такта okna после corpus_build fix.
set -euo pipefail
HOST=root@gpu-erw.timpul.pro
PORT=2202
KEY=~/.ssh/id_ed25519_deploy
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
ssh -p "$PORT" "${SSH_OPTS[@]}" "$HOST" bash -s <<'REMOTE'
set -uo pipefail
load_env() {
  for p in /etc/1c-mcp-reports.env; do
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
echo "===== STATUS ====="
systemctl status 1c-serene-pipeline@postgres --no-pager -l 2>&1 | tail -20
echo "===== JOURNAL corpus ====="
journalctl -u 1c-serene-pipeline@postgres --no-pager -n 80 2>&1 | grep -E 'corpus_build|СБОРКА|ERROR|syntax|GetComparison|шаг|build_state|failed' || journalctl -u 1c-serene-pipeline@postgres --no-pager -n 40
echo "===== CORPUS COUNT ====="
psql "$DSN" -tAc "SELECT count(*) FROM search_corpus" 2>/dev/null || true
psql "$DSN" -tAc "SELECT k,v FROM build_state ORDER BY k LIMIT 10" 2>/dev/null || true
REMOTE
