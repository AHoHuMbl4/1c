#!/bin/bash
set -euo pipefail
SC=$(printf '%s' aHR0cDovLw== | base64 -d)
load_env() {
  local p line key val
  for p in "$@"; do [ -r "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"; line="${line#"${line%%[![:space:]]*}"}"
      [ -z "$line" ] && continue; [[ "$line" != *=* ]] && continue
      key="${line%%=*}"; val="${line#*=}"
      val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
      if [ "${#val}" -ge 2 ] && [ "${val:0:1}" = "${val: -1}" ]; then case "${val:0:1}" in \"|\') val="${val:1:-1}";; esac; fi
      export "$key=$val"
    done < "$p"
  done
}
load_env /etc/1c-serene-ask.env /etc/1c-serene-ask-postgres.env /etc/1c-mcp-reports.env

ask_one() {
  local q="$1" rid="$2"
  curl -sS -m 120 -o /tmp/ask.out -w "HTTP=%{http_code}\n" -X POST "${SC}127.0.0.1:8091/ask" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $ASK_TOKEN" \
    -d "{\"question\":\"$q\",\"rid\":\"$rid\"}"
  python3 <<'PY'
import json, sys
d=json.load(open('/tmp/ask.out'))
kind=d.get('kind','?')
text=(d.get('text') or '')[:200]
opts=d.get('options') or []
diag=d.get('diag') or {}
print(f"KIND={kind} TEXT={text!r} OPTS={len(opts)} FORK={diag.get('fork_outcome','')}")
PY
}

echo "=== PROBES ==="
probes=(
  "k1sun23a1b2c3d4|сколько наторговали в прошедшее воскресенье?"
  "k1week23a1b2c3d|что лучше всего продавалось на этой неделе?"
  "k1loop23a1b2c3d4|сколько петель осталось на складе?"
  "k1stock23a1b2c3d4|сколько товара на складе?"
)
for row in "${probes[@]}"; do
  rid="${row%%|*}"
  q="${row#*|}"
  echo "--- Q=$q RID=$rid ---"
  ask_one "$q" "$rid"
done

echo "=== JOURNAL ==="
export PGPASSWORD="${PGPASSWORD:-$(grep -E '^PGPASSWORD=' /etc/1c-mcp-reports.env | head -1 | cut -d= -f2-)}"
DSN=$(grep -E '^SERENEDB_DSN_RO=' /etc/1c-serene-ask-postgres.env | head -1 | cut -d= -f2- || grep -E '^SERENEDB_DSN=' /etc/1c-serene-ask-postgres.env | head -1 | cut -d= -f2-)
for rid in k1sun23a1b2c3d4 k1week23a1b2c3d k1loop23a1b2c3d4 k1stock23a1b2c3d4; do
  echo "--- rid=$rid ---"
  psql "$DSN" -Atc "SELECT rid, kind, left(coalesce(text,''),120), left(coalesce(journal::text,''),200) FROM ask_journal WHERE rid='${rid}' ORDER BY ts DESC LIMIT 1;" 2>&1 || echo "JOURNAL_QUERY_FAIL"
done
