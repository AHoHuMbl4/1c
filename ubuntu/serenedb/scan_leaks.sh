#!/bin/bash
# Найти файлы под /tmp, где лежат ЗНАЧЕНИЯ живых секретов (а не просто имена переменных).
# Значения не печатаются: в вывод идут только пути и имя переменной.
set -u
declare -A S
S[PGPASSWORD]=$(sudo grep -h '^PGPASSWORD=' /etc/1c-mcp-reports.env 2>/dev/null | head -1 | cut -d= -f2-)
S[ASK_TOKEN]=$(sudo grep -h '^ASK_TOKEN=' /etc/1c-serene-ask.env 2>/dev/null | head -1 | cut -d= -f2-)
S[MCP_TOKEN]=$(sudo grep -h '^MCP_TOKEN=' /etc/1c-mcp-ask.env 2>/dev/null | head -1 | cut -d= -f2-)
S[RESOLVER_PW]=$(sudo grep -h '^RESOLVER_PW=' /etc/1c-serene-ask-ut_test.env /etc/1c-mcp-reports.env 2>/dev/null | head -1 | cut -d= -f2-)
S[DEEPSEEK_API_KEY]=$(sudo -u undebot grep -h '^DEEPSEEK_API_KEY=' /home/undebot/.openclaw/gateway.systemd.env 2>/dev/null | cut -d= -f2-)
S[ODG_GATEWAY_TOKEN]=$(sudo grep -h '^ODG_GATEWAY_TOKEN=' /etc/1c-serene-sync.env 2>/dev/null | head -1 | cut -d= -f2-)

found=0
for k in "${!S[@]}"; do
  v="${S[$k]}"
  [ -n "$v" ] && [ ${#v} -ge 12 ] || continue
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\t%s\t%s\n' "$k" "$(stat -c '%a %U' "$f")" "$f"
    found=$((found+1))
  done < <(grep -rl -F -- "$v" /tmp 2>/dev/null)
done
[ "$found" = 0 ] && echo "значений живых секретов под /tmp не найдено"
