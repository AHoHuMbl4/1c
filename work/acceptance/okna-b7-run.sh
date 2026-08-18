#!/bin/bash
# B7 приёмка okna: golden-вопросы через /ask боевого :8091 (ssh на юнит).
# Сохраняет сырые ответы и сводку JSONL для docs/ACCEPTANCE_OKNA_2026-08-18.md.
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
RUNS=/srv/1c/work/acceptance/runs
TAG=2026-08-18-okna-b7
mkdir -p "$RUNS"

questions=(
  "B7-01|на какую сумму мы продали|1572493.22 79752611.64 79925955.81|${TAG}-01-prodazha-sum.json"
  "B7-02|сколько контрагентов|349|${TAG}-02-kontragenty.json"
  "B7-03|Сколько банков в Казани?|37|${TAG}-03-banki-kazan.json"
  "B7-04|сколько мы продали|8223 3826 1310413.93|${TAG}-04-prodazha-count.json"
  "B7-05|книга продаж сумма|74705|${TAG}-05-kniga-prodazh.json"
  "B7-06|реализация тмц сколько документов|77179|${TAG}-06-realizaciya-tmc.json"
)

ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" 'cat > /tmp/okna_ask_one.py' <<'PY'
import json, os, sys, urllib.request
t = open("/etc/1c-serene-ask.env").read().split("ASK_TOKEN=")[1].split()[0].strip()
q = sys.argv[1]
body = json.dumps({"question": q}).encode()
req = urllib.request.Request("http://127.0.0.1:8091/ask", data=body, method="POST",
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + t})
print(urllib.request.urlopen(req, timeout=180).read().decode())
PY

health=$(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  'curl -sS -m 10 http://127.0.0.1:8091/health')
echo "$health" > "$RUNS/${TAG}-health.json"

summary="$RUNS/${TAG}-summary.jsonl"
: > "$summary"
passed=0
total=${#questions[@]}

score_one() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, re, sys
path, expect_s = sys.argv[1], sys.argv[2]
case_id = sys.argv[3]
with open(path, encoding="utf-8") as fh:
    d = json.load(fh)
expect = [float(x.replace(",", ".")) for x in expect_s.split()]
NUM_RE = re.compile(r"\d{1,3}(?:[\s\u00a0\u202f\u2009\u2060\u2007\u2008\u200a\u200b\u200c\u200d\u200e\u200f\u2028\u2029\u205f\u3000]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")

def numify(s):
    s = re.sub(r"[\s\u00a0\u202f\u2009\u2060\u2007\u2008\u200a\u200b\u200c\u200d\u200e\u200f\u2028\u2029\u205f\u3000]", "", str(s)).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def walk(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("exact_value", "sum", "count", "display_value"):
                n = numify(v)
                if n is not None:
                    found.append(n)
            walk(v, found)
    elif isinstance(obj, list):
        for x in obj:
            walk(x, found)
    elif isinstance(obj, str):
        for m in NUM_RE.findall(obj):
            n = numify(m)
            if n is not None:
                found.append(n)

def close(a, b):
    return round(a, 2) == round(b, 2) or round(a) == round(b)

found = []
walk(d.get("text"), found)
walk(d.get("options"), found)
walk(d.get("totals"), found)
walk(d.get("diag"), found)
uniq = []
seen = set()
for n in found:
    k = round(n, 2)
    if k not in seen:
        seen.add(k)
        uniq.append(n)
matched, missing = [], []
for e in expect:
    hit = [u for u in uniq if close(u, e)]
    if hit:
        matched.append({"expected": e, "got": hit[0]})
    else:
        missing.append(e)
kind = d.get("kind")
ok = (not missing) and kind not in ("no_data", "unavailable", None)
out = {"id": case_id, "question": d.get("_question"), "kind": kind,
       "fork_outcome": (d.get("diag") or {}).get("fork_outcome"),
       "ok": ok, "matched": matched, "missing": missing,
       "nums_in_response": uniq[:30], "text_head": (d.get("text") or "")[:240]}
print(json.dumps(out, ensure_ascii=False))
sys.exit(0 if ok else 1)
PY
}

for item in "${questions[@]}"; do
  IFS='|' read -r cid q expect f <<< "$item"
  echo "=== $cid: $q ==="
  ok=0
  for attempt in 1 2 3; do
    if ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
      "/opt/openclaw-mcp/venv/bin/python3 /tmp/okna_ask_one.py $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$q")" \
      > "$RUNS/$f" 2>/dev/null; then
      ok=1
      break
    fi
    echo "  retry $attempt" >&2
    sleep 15
  done
  if [ "$ok" != 1 ]; then
    echo "{\"id\":\"$cid\",\"question\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$q"),\"ok\":false,\"error\":\"ssh/ask failed\"}" >> "$summary"
    continue
  fi
  python3 -c "import json; d=json.load(open('$RUNS/$f')); d['_question']='$q'; json.dump(d, open('$RUNS/$f','w'), ensure_ascii=False)" 2>/dev/null || true
  line=$(score_one "$RUNS/$f" "$expect" "$cid" || true)
  echo "$line" >> "$summary"
  if python3 -c "import json,sys; print(json.loads(sys.argv[1])['ok'])" "$line" 2>/dev/null | grep -q True; then
    passed=$((passed + 1))
  fi
  echo "$line" | python3 -m json.tool 2>/dev/null | head -20
done

python3 - <<PY
import json
health = json.load(open("$RUNS/${TAG}-health.json"))
print(json.dumps({"tag": "$TAG", "passed": $passed, "total": $total,
                  "health": health}, ensure_ascii=False, indent=2))
with open("$RUNS/${TAG}-run.json", "w", encoding="utf-8") as fh:
    rows = []
    with open("$summary", encoding="utf-8") as sf:
        for line in sf:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    json.dump({"tag": "$TAG", "passed": $passed, "total": $total,
               "health": health, "rows": rows}, fh, ensure_ascii=False, indent=2)
PY

echo "B7 итог: $passed/$total"
