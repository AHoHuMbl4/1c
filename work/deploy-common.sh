# Общие SSH/SCP параметры выката на окно. Источник — deploy-ask.sh / deploy-sql.sh.
# shellcheck shell=bash
DEPLOY_SSH_IDENTITY="${DEPLOY_SSH_IDENTITY:-/home/claudedev/.ssh/id_ed25519_deploy}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-2202}"
DEPLOY_SSH_HOST="${DEPLOY_SSH_HOST:-root@gpu-erw.timpul.pro}"
DEPLOY_DST="${DEPLOY_DST:-/opt/1c-mcp-reports}"

deploy_ssh() {
  ssh -i "$DEPLOY_SSH_IDENTITY" -p "$DEPLOY_SSH_PORT" "$DEPLOY_SSH_HOST" "$@"
}

deploy_scp() {
  scp -i "$DEPLOY_SSH_IDENTITY" -P "$DEPLOY_SSH_PORT" "$@"
}
