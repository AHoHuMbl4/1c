#!/usr/bin/env bash
# Карта окружения: юнит → порт → md5 развёрнутого serene_ask.py → HEAD? → search_meta.
# Запускает оркестратор (окна без SSH). Вывод — в stdout для вставки в RUNBOOK_DEPLOY.
set -euo pipefail

REPO="${REPO_ROOT:-/srv/1c}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/id_ed25519_deploy}"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" -o ConnectTimeout=20)
HEAD_MD5="$(md5sum "$REPO/ubuntu/serenedb/serene_ask.py" | awk '{print $1}')"
HEAD_SHORT="${HEAD_MD5:0:8}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "# env-map snapshot $STAMP"
echo
echo "HEAD serene_ask.py md5=$HEAD_MD5 ($HEAD_SHORT)"
echo
echo "| host | unit | port | deployed_md5 | matches_HEAD | balance_registers | serene_ro meta |"
echo "|---|---|---:|---|---|---|---|"

probe_host() {
  local label="$1" target="$2" hop="${3:-}"
  local remote
  if [[ -n "$hop" ]]; then
    remote="${SSH[@]} $target $hop"
  else
    remote="${SSH[@]} $target"
  fi

  $remote bash -s <<REMOTE || true
set -euo pipefail
HEAD='$HEAD_MD5'
HOST='$label'
echo_row() {
  printf '| %s | %s | %s | %s | %s | %s | %s |\n' "\$@"
}
load_env() {
  for p in /etc/1c-mcp-reports.env /etc/1c-serene-ask-postgres.env; do
    [ -r "\$p" ] || continue
    while IFS= read -r line || [ -n "\$line" ]; do
      line="\${line%%#*}"; [[ "\$line" != *=* ]] && continue
      export "\${line%%=*}=\${line#*=}"
    done < "\$p"
  done
}
load_env
unset PGUSER PGPASSWORD PGDATABASE
export PGPASSWORD="\${PGPASSWORD:-}"

for unit in \$(systemctl list-units '1c-serene-ask@*.service' --no-legend 2>/dev/null | awk '{print \$1}'); do
  base="\${unit#1c-serene-ask@}"
  base="\${base%.service}"
  envf="/etc/1c-serene-ask-\${base}.env"
  port="?"
  if [ -r "\$envf" ]; then
    port=\$(grep -E '^ASK_LISTEN_PORT=' "\$envf" | head -1 | cut -d= -f2- | tr -d '"'"'\"'"'"' || echo "?")
  fi
  deployed="missing"
  for f in /opt/1c-mcp-reports/serene_ask.py /srv/1c/ubuntu/serenedb/serene_ask.py; do
    if [ -r "\$f" ]; then
      deployed=\$(md5sum "\$f" | awk '{print \$1}')
      break
    fi
  done
  match="no"
  [ "\$deployed" = "\$HEAD" ] && match="yes"
  bal="—"
  ro_meta="—"
  if [ -n "\${SERENEDB_DSN_RO:-}" ]; then
    bal=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT left(coalesce(v,''),48) FROM search_meta WHERE k='balance_registers' LIMIT 1" 2>/dev/null | tr -d '\n' || echo err)
    ro_meta=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT has_table_privilege('serene_ro','search_meta','SELECT')" 2>/dev/null | tr -d '\n' || echo err)
  fi
  echo_row "\$HOST" "\$unit" "\$port" "\$deployed" "\$match" "\$bal" "\$ro_meta"
done

# okna: боевой postgres часто без @unit в имени — дополнительная строка :8091
if [ "\$HOST" = "okna" ] && [ -r /opt/1c-mcp-reports/serene_ask.py ]; then
  deployed=\$(md5sum /opt/1c-mcp-reports/serene_ask.py | awk '{print \$1}')
  match="no"; [ "\$deployed" = "\$HEAD" ] && match="yes"
  bal="—"; ro_meta="—"
  if [ -n "\${SERENEDB_DSN_RO:-}" ]; then
    bal=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT left(coalesce(v,''),48) FROM search_meta WHERE k='balance_registers' LIMIT 1" 2>/dev/null | tr -d '\n' || echo err)
    ro_meta=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT has_table_privilege('serene_ro','search_meta','SELECT')" 2>/dev/null | tr -d '\n' || echo err)
  fi
  echo_row "okna" "1c-serene-ask@postgres.service (:8091)" "8091" "\$deployed" "\$match" "\$bal" "\$ro_meta"
fi
REMOTE
}

# okna
probe_host "okna" "root@167.233.249.110"

# klient-1 через релей
probe_host "klient-1" "root@89.23.101.22" \
  '"ssh -o StrictHostKeyChecking=no root@10.1.1.7 bash -s"'

# dev (локальный LXC, если serenedb жив)
if systemctl is-active serenedb &>/dev/null; then
  bash -s <<LOCAL || true
set -euo pipefail
HEAD='$HEAD_MD5'
echo_row() { printf '| %s | %s | %s | %s | %s | %s | %s |\n' "\$@"; }
for unit in \$(systemctl list-units '1c-serene-ask@*.service' --no-legend 2>/dev/null | awk '{print \$1}'); do
  base="\${unit#1c-serene-ask@}"; base="\${base%.service}"
  envf="/etc/1c-serene-ask-\${base}.env"
  port=\$(grep -E '^ASK_LISTEN_PORT=' "\$envf" 2>/dev/null | head -1 | cut -d= -f2- || echo "?")
  deployed=\$(md5sum /opt/1c-mcp-reports/serene_ask.py 2>/dev/null | awk '{print \$1}' || echo missing)
  match="no"; [ "\$deployed" = "\$HEAD" ] && match="yes"
  bal="—"; ro_meta="—"
  if [ -r /etc/1c-mcp-reports.env ]; then
    set -a; . /etc/1c-mcp-reports.env; set +a
    bal=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT left(coalesce(v,''),48) FROM search_meta WHERE k='balance_registers' LIMIT 1" 2>/dev/null || echo err)
    ro_meta=\$(psql "\$SERENEDB_DSN_RO" -tA -c "SELECT has_table_privilege('serene_ro','search_meta','SELECT')" 2>/dev/null || echo err)
  fi
  echo_row "dev" "\$unit" "\$port" "\$deployed" "\$match" "\$bal" "\$ro_meta"
done
LOCAL
fi

echo
echo "_Снимок: \`bash work/acceptance/env-map.sh\` — оркестратор; HEAD md5 \`$HEAD_SHORT\`._"
