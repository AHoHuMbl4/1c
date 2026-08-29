#!/bin/bash
# Выкат embed_secrets_install + юнита на okna (запуск с дева, ключ deploy).
set -euo pipefail
HOST=root@gpu-erw.timpul.pro
PORT=2202
KEY=~/.ssh/id_ed25519_deploy
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY")
SRC=/srv/1c/ubuntu/serenedb
REPO=/srv/1c

scp -P "$PORT" "${SSH_OPTS[@]}" \
  "$SRC/embed_secrets_install.sh" \
  "$SRC/embed_secrets_install.sql" \
  "$HOST:/tmp/"

scp -P "$PORT" "${SSH_OPTS[@]}" \
  "$REPO/ubuntu/systemd/1c-serene-embed-secrets.service" \
  "$REPO/ubuntu/systemd/serenedb.service.d/embed-secrets.conf" \
  "$HOST:/tmp/"

ssh -p "$PORT" "${SSH_OPTS[@]}" "$HOST" bash -s <<'REMOTE'
set -euo pipefail
install -m 755 /tmp/embed_secrets_install.sh /opt/1c-mcp-reports/embed_secrets_install.sh
install -m 644 /tmp/embed_secrets_install.sql /opt/1c-mcp-reports/embed_secrets_install.sql
install -m 644 /tmp/1c-serene-embed-secrets.service /etc/systemd/system/1c-serene-embed-secrets.service
mkdir -p /etc/systemd/system/serenedb.service.d
install -m 644 /tmp/embed-secrets.conf /etc/systemd/system/serenedb.service.d/embed-secrets.conf
systemctl daemon-reload
systemctl enable 1c-serene-embed-secrets.service
echo "=== run 1 ==="
systemctl start 1c-serene-embed-secrets.service
c1=$(psql "host=127.0.0.1 port=7890 user=postgres dbname=postgres" -tAc "SELECT count(*) FROM duckdb_secrets()")
echo "secrets_count_1=$c1"
echo "=== run 2 (idempotent) ==="
systemctl start 1c-serene-embed-secrets.service
c2=$(psql "host=127.0.0.1 port=7890 user=postgres dbname=postgres" -tAc "SELECT count(*) FROM duckdb_secrets()")
echo "secrets_count_2=$c2"
journalctl -u 1c-serene-embed-secrets.service -n 20 --no-pager
diff -q /etc/systemd/system/1c-serene-embed-secrets.service /tmp/1c-serene-embed-secrets.service
diff -q /etc/systemd/system/serenedb.service.d/embed-secrets.conf /tmp/embed-secrets.conf
REMOTE
