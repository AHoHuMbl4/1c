#!/bin/bash
# B8: стабильность /ask okna — 6 golden × N прогонов на текущей модели (Qwen).
# Ничего на юните не меняет; артефакты → work/acceptance/runs/2026-08-18-okna-b8-*.
set -euo pipefail
HOST=root@167.233.249.110
RUNS=/srv/1c/work/acceptance/runs
TAG=2026-08-18-okna-b8
REPEATS="${1:-5}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15)
if [ -n "${SSH_AUTH_SOCK:-}" ]; then
  :
elif [ -S /tmp/ssh-1c-eu.sock ]; then
  export SSH_AUTH_SOCK=/tmp/ssh-1c-eu.sock
else
  SSH+=(-o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_deploy)
fi
mkdir -p "$RUNS"

# --- SQL-снимок эталонов на день прогона ---
"${SSH[@]}" "$HOST" bash -s <<'REMOTE' > "$RUNS/${TAG}-sql-truth.tsv"
load_env() {
  for p in /etc/1c-mcp-reports.env /etc/1c-serene-ask-postgres.env; do
    [ -r "$p" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%%#*}"; [[ "$line" != *=* ]] && continue
      export "${line%%=*}=${line#*=}"
    done < "$p"
  done
}
load_env
export PGPASSWORD
psql "$SERENEDB_DSN_RO" -tA <<'SQL'
SELECT 'B8-02 catalog_контрагенты count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='catalog_контрагенты'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-03 catalog_классификаторбанков Казань count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='catalog_классификаторбанков'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false)
  AND coalesce(body, '') ILIKE '%КАЗАН%';
SELECT 'B8-04 document_реализациятмц count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='document_реализациятмц'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-04 document_выручкаотреализациитмцфизлицо_номенклатура count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='document_выручкаотреализациитмцфизлицо_номенклатура'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-04 document_выручка sum СуммаБезНДС' || E'\t' || round(sum(try_cast(map_extract_value(nums, 'СуммаБезНДС') as double))::numeric, 2)::text
FROM search_corpus WHERE src_table='document_выручкаотреализациитмцфизлицо_номенклатура'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-05 accumulationregister_книгапродаж count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='accumulationregister_книгапродаж'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-06 accumulationregister_реализациятмц count' || E'\t' || count(*)::text
FROM search_corpus WHERE src_table='accumulationregister_реализациятмц'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-01 document_выручка sum Всего' || E'\t' || round(sum(try_cast(map_extract_value(nums, 'Всего') as double))::numeric, 2)::text
FROM search_corpus WHERE src_table='document_выручкаотреализациитмцфизлицо_номенклатура'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-01 document_реализациятмц sum Всего' || E'\t' || round(sum(try_cast(map_extract_value(nums, 'Всего') as double))::numeric, 2)::text
FROM search_corpus WHERE src_table='document_реализациятмц'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SELECT 'B8-01 accumulationregister_реализациятмц sum Всего' || E'\t' || round(sum(try_cast(map_extract_value(nums, 'Всего') as double))::numeric, 2)::text
FROM search_corpus WHERE src_table='accumulationregister_реализациятмц'
  AND NOT coalesce(map_extract_value(flags, 'IsFolder'), false);
SQL
REMOTE

# --- метаданные юнита (без секретов) ---
"${SSH[@]}" "$HOST" bash -s <<'REMOTE' > "$RUNS/${TAG}-meta.json"
python3 - <<'PY'
import hashlib, json, subprocess, urllib.request
meta = {}
meta["health"] = json.loads(urllib.request.urlopen("http://127.0.0.1:8091/health", timeout=10).read())
with open("/opt/1c-mcp-reports/serene_ask.py", "rb") as fh:
    meta["serene_ask_md5"] = hashlib.md5(fh.read()).hexdigest()
for p in ("/etc/1c-serene-ask.env", "/etc/1c-serene-ask-postgres.env"):
    try:
        for line in open(p):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in ("DEEPSEEK_MODEL", "ASK_MEMORY_APPLY", "ASK_MEMORY_MODE"):
                meta[k] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
print(json.dumps(meta, ensure_ascii=False, indent=2))
PY
REMOTE

# --- deploy ask helper once ---
"${SSH[@]}" "$HOST" 'cat > /tmp/okna_ask_one.py' <<'PY'
import json, sys, urllib.request
t = open("/etc/1c-serene-ask.env").read().split("ASK_TOKEN=")[1].split()[0].strip()
q = sys.argv[1]
body = json.dumps({"question": q}).encode()
req = urllib.request.Request("http://127.0.0.1:8091/ask", data=body, method="POST",
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + t})
print(urllib.request.urlopen(req, timeout=180).read().decode())
PY

questions=(
  "B8-01|на какую сумму мы продали"
  "B8-02|сколько контрагентов"
  "B8-03|Сколько банков в Казани?"
  "B8-04|сколько мы продали"
  "B8-05|книга продаж сумма"
  "B8-06|реализация тмц сколько документов"
)

summary="$RUNS/${TAG}-summary.jsonl"
: > "$summary"

for item in "${questions[@]}"; do
  IFS='|' read -r cid q <<< "$item"
  for run in $(seq 1 "$REPEATS"); do
    slug=$(echo "$cid" | tr '[:upper:]' '[:lower:]' | sed 's/^b8-//')
    f="${TAG}-${slug}-run${run}.json"
    echo "=== $cid run $run/$REPEATS: $q ==="
    ok=0
    for attempt in 1 2 3; do
      if "${SSH[@]}" "$HOST" \
        "/opt/openclaw-mcp/venv/bin/python3 /tmp/okna_ask_one.py $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$q")" \
        > "$RUNS/$f" 2>/dev/null; then
        ok=1
        break
      fi
      echo "  retry $attempt" >&2
      sleep 10
    done
    if [ "$ok" != 1 ]; then
      echo "{\"id\":\"$cid\",\"run\":$run,\"question\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$q"),\"ok\":false,\"error\":\"ssh/ask failed\"}" >> "$summary"
      continue
    fi
    python3 - "$RUNS/$f" "$cid" "$run" "$q" <<'PY' >> "$summary"
import json, re, sys
path, case_id, run_s, question = sys.argv[1:5]
run = int(run_s)
with open(path, encoding="utf-8") as fh:
    d = json.load(fh)
d["_question"] = question
d["_run"] = run
with open(path, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False)

NUM_RE = re.compile(r"\d{1,3}(?:[\s\u00a0\u202f\u2009\u2060\u2007\u2008\u200a\u200b\u200c\u200d\u200e\u200f\u2028\u2029\u205f\u3000]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")

def numify(s):
    s = re.sub(r"[\s\u00a0\u202f\u2009\u2060\u2007\u2008\u200a\u200b\u200c\u200d\u200e\u200f\u2028\u2029\u205f\u3000]", "", str(s)).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

def walk_visible(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("exact_value", "sum", "count", "display_value", "found"):
                n = numify(v)
                if n is not None:
                    found.append(n)
            walk_visible(v, found)
    elif isinstance(obj, list):
        for x in obj:
            walk_visible(x, found)
    elif isinstance(obj, str):
        for m in NUM_RE.findall(obj):
            n = numify(m)
            if n is not None:
                found.append(n)

def fork_sig(diag):
    fork = (diag or {}).get("fork") or {}
    atoms = fork.get("atoms") or []
    sig = []
    for a in atoms:
        srcs = tuple(sorted(a.get("srcs") or []))
        atom = a.get("atom") or {}
        ev = atom.get("exact_value")
        op = atom.get("operation")
        sig.append((srcs, op, ev))
    return tuple(sorted(sig))

visible = []
walk_visible(d.get("text"), visible)
walk_visible(d.get("options"), visible)
walk_visible(d.get("totals"), visible)
walk_visible(d.get("atoms"), visible)
uniq = []
seen = set()
for n in visible:
    k = round(n, 2)
    if k not in seen:
        seen.add(k)
        uniq.append(n)

diag = d.get("diag") or {}
kind = d.get("kind")
out = {
    "id": case_id,
    "run": run,
    "question": question,
    "kind": kind,
    "fork_outcome": diag.get("fork_outcome"),
    "fork_classes": diag.get("fork", {}).get("classes"),
    "fork_srcs": diag.get("fork", {}).get("srcs"),
    "fork_pool": diag.get("fork", {}).get("pool"),
    "fork_sig_hash": hash(fork_sig(diag)) & 0xFFFFFFFF,
    "memory_mode": (diag.get("memory") or {}).get("mode"),
    "memory_applied": (diag.get("memory") or {}).get("applied"),
    "sec": diag.get("sec"),
    "nums_visible": uniq[:20],
    "text_head": (d.get("text") or "")[:200],
    "options_n": len(d.get("options") or []),
}
print(json.dumps(out, ensure_ascii=False))
PY
  done
done

python3 - "$RUNS/${TAG}-sql-truth.tsv" "$summary" "$RUNS/${TAG}-meta.json" "$REPEATS" "$TAG" <<'PY'
import json, re, sys
from collections import defaultdict

truth_path, summary_path, meta_path, repeats_s, tag = sys.argv[1:6]
repeats = int(repeats_s)

# parse SQL truth
truth = {}
for line in open(truth_path, encoding="utf-8"):
    line = line.strip()
    if not line or "\t" not in line:
        continue
    k, v = line.split("\t", 1)
    truth[k] = float(v.replace(",", "."))

expect = {
    "B8-01": [
        truth.get("B8-01 document_выручка sum Всего"),
        truth.get("B8-01 document_реализациятмц sum Всего"),
        truth.get("B8-01 accumulationregister_реализациятмц sum Всего"),
    ],
    "B8-02": [truth.get("B8-02 catalog_контрагенты count")],
    "B8-03": [truth.get("B8-03 catalog_классификаторбанков Казань count")],
    "B8-04": [
        truth.get("B8-04 document_реализациятмц count"),
        truth.get("B8-04 document_выручкаотреализациитмцфизлицо_номенклатура count"),
        truth.get("B8-04 document_выручка sum СуммаБезНДС"),
    ],
    "B8-05": [truth.get("B8-05 accumulationregister_книгапродаж count")],
    "B8-06": [truth.get("B8-06 accumulationregister_реализациятмц count")],
}
expect = {k: [x for x in v if x is not None] for k, v in expect.items()}

def close(a, b):
    return round(a, 2) == round(b, 2) or round(a) == round(b)

rows = []
for line in open(summary_path, encoding="utf-8"):
    line = line.strip()
    if line:
        rows.append(json.loads(line))

by_case = defaultdict(list)
for r in rows:
    exp = expect.get(r["id"], [])
    nums = r.get("nums_visible") or []
    matched, missing = [], []
    for e in exp:
        hit = [u for u in nums if close(u, e)]
        if hit:
            matched.append({"expected": e, "got": hit[0]})
        else:
            missing.append(e)
    kind = r.get("kind")
    ok = (not missing) and kind in ("answer", "figures") and exp
    r["expect"] = exp
    r["matched"] = matched
    r["missing"] = missing
    r["ok"] = ok
    by_case[r["id"]].append(r)

per_case = {}
total_ok = 0
total_runs = 0
for cid, runs in sorted(by_case.items()):
    kinds = [r["kind"] for r in runs]
    ok_runs = sum(1 for r in runs if r["ok"])
    total_ok += ok_runs
    total_runs += len(runs)
    sigs = [r.get("fork_sig_hash") for r in runs]
    per_case[cid] = {
        "expect": expect.get(cid, []),
        "ok_runs": ok_runs,
        "runs": len(runs),
        "kind_stable": len(set(kinds)) == 1,
        "kinds": kinds,
        "fork_sig_stable": len(set(sigs)) == 1,
        "fork_sig_variants": len(set(sigs)),
        "fork_outcomes": [r.get("fork_outcome") for r in runs],
        "memory_modes": list({r.get("memory_mode") for r in runs}),
    }

meta = json.load(open(meta_path, encoding="utf-8"))
out = {
    "tag": tag,
    "repeats": repeats,
    "model": meta.get("DEEPSEEK_MODEL"),
    "serene_ask_md5": meta.get("serene_ask_md5"),
    "ASK_MEMORY_APPLY": meta.get("ASK_MEMORY_APPLY"),
    "health": meta.get("health"),
    "sql_truth": truth,
    "expect": expect,
    "total_ok_runs": total_ok,
    "total_runs": total_runs,
    "full_pass_rate": f"{total_ok}/{total_runs}",
    "per_case": per_case,
    "rows": rows,
}
out_path = summary_path.replace("-summary.jsonl", "-aggregate.json")
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(json.dumps({"aggregate": out_path, "full_pass_rate": out["full_pass_rate"], "per_case": per_case}, ensure_ascii=False, indent=2))
PY

echo "B8 stability done → $RUNS/${TAG}-aggregate.json"
