#!/bin/bash
# Произвольный SQL на okna по RO-роли: SQL приходит на stdin.
#   echo "SELECT 1" | bash work/acceptance/okna-sql.sh
# Аргументы после -- уходят в psql (например -tA, -F$'\t').
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
PSQL_ARGS=${PSQL_ARGS:--tA}
SQL=$(cat)
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  "PSQL_ARGS='$PSQL_ARGS' bash -s" <<EOF
set -euo pipefail
DSN=\$(grep -E '^SERENEDB_DSN_RO=' /etc/1c-serene-ask-postgres.env | cut -d= -f2-)
export PGPASSWORD=\$(grep -E '^PGPASSWORD=' /etc/1c-mcp-reports.env | cut -d= -f2-)
psql "\$DSN" -v ON_ERROR_STOP=1 \$PSQL_ARGS <<'SQLEOF'
$SQL
SQLEOF
EOF
