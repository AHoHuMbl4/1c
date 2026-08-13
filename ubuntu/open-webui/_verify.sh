#!/bin/bash
set -euo pipefail
D=okna.timpul.pro
curl -sI --resolve "${D}:443:127.0.0.1" "https://${D}/" | head -12
echo ---
ss -tlnp | grep -E ':443|:8080|:80 '
echo ---
runuser -u webui -- env XDG_RUNTIME_DIR=/run/user/"$(id -u webui)" systemctl --user is-active open-webui
systemctl is-active caddy
