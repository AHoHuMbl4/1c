#!/bin/bash
# B9 live: 6 golden okna × N на удалённом dev :8097 (/tmp/serene_ask_b9.py).
# Бой :8091 и /opt не трогаем.
set -euo pipefail
REPEATS="${1:-3}"
HOST=root@167.233.249.110
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_deploy)
TAG=2026-08-18-okna-b9-remote
RUNS=/srv/1c/work/acceptance/runs
mkdir -p "$RUNS"

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

"${SSH[@]}" "$HOST" 'cat > /tmp/okna_ask_8097.py' <<'PY'
import json, sys, urllib.request
t = open("/etc/1c-serene-ask.env").read().split("ASK_TOKEN=")[1].split()[0].strip()
q = sys.argv[1]
body = json.dumps({"question": q}).encode()
req = urllib.request.Request("http://127.0.0.1:8097/ask", data=body, method="POST",
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
md5sum /srv/1c/ubuntu/serenedb/serene_ask.py | awk '{print $1}' > "$RUNS/${TAG}-md5.txt"

for item in "${questions[@]}"; do
  IFS='|' read -r cid q <<< "$item"
  for run in $(seq 1 "$REPEATS"); do
    slug=$(echo "$cid" | tr '[:upper:]' '[:lower:]' | sed 's/^b8-//')
    f="${TAG}-${slug}-run${run}.json"
    echo "=== $cid run $run/$REPEATS ==="
    "${SSH[@]}" "$HOST" \
      "/opt/openclaw-mcp/venv/bin/python3 /tmp/okna_ask_8097.py $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$q")" \
      > "$RUNS/$f"
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
print(json.dumps({
    "id": case_id, "run": run, "question": question,
    "kind": d.get("kind"),
    "fork_outcome": diag.get("fork_outcome"),
    "axis_clarify_skipped": diag.get("axis_clarify_skipped"),
    "aligned_to_terms": diag.get("aligned_to_terms"),
    "nums_visible": uniq[:20],
    "text_head": (d.get("text") or "")[:160],
    "reason": diag.get("reason"),
}, ensure_ascii=False))
PY
  done
done

python3 - "$RUNS/${TAG}-sql-truth.tsv" "$summary" "$REPEATS" "$TAG" <<'PY'
import json, sys
from collections import defaultdict

truth_path, summary_path, repeats_s, tag = sys.argv[1:5]
repeats = int(repeats_s)
truth = {}
for line in open(truth_path, encoding="utf-8"):
    line = line.strip()
    if line and "\t" in line:
        k, v = line.split("\t", 1)
        truth[k] = float(v.replace(",", "."))

expect = {
    "B8-01": [truth.get("B8-01 document_выручка sum Всего"),
              truth.get("B8-01 document_реализациятмц sum Вsего") or truth.get("B8-01 document_реализациятмц sum Всего"),
              truth.get("B8-01 accumulationregister_реализациятмц sum Всего")],
    "B8-02": [truth.get("B8-02 catalog_контрагенты count")],
    "B8-03": [truth.get("B8-03 catalog_классификаторбанков Казань count")],
    "B8-04": [truth.get("B8-04 document_реализациятмц count"),
              truth.get("B8-04 document_выручкаотреализациитмцфизлицо_номенклатура count"),
              truth.get("B8-04 document_выручка sum СуммаБезНДС")],
    "B8-05": [truth.get("B8-05 accumulationregister_книгапродаж count")],
    "B8-06": [truth.get("B8-06 accumulationregister_реализациятмц count")],
}
expect = {k: [x for x in v if x is not None] for k, v in expect.items()}

def close(a, b):
    return round(a, 2) == round(b, 2) or round(a) == round(b)

rows = [json.loads(l) for l in open(summary_path) if l.strip()]
by_case = defaultdict(list)
for r in rows:
    exp = expect.get(r["id"], [])
    nums = r.get("nums_visible") or []
    missing = [e for e in exp if not any(close(u, e) for u in nums)]
    r["expect"] = exp
    r["missing"] = missing
    r["ok"] = (not missing) and r.get("kind") in ("answer", "figures") and bool(exp)
    by_case[r["id"]].append(r)

per_case = {}
total_ok = total_runs = 0
for cid, runs in sorted(by_case.items()):
    ok_runs = sum(1 for r in runs if r["ok"])
    total_ok += ok_runs
    total_runs += len(runs)
    per_case[cid] = {"expect": expect[cid], "ok_runs": ok_runs, "runs": len(runs),
                     "kinds": [r["kind"] for r in runs],
                     "nums_sample": [r.get("nums_visible") for r in runs]}

out = {"tag": tag, "repeats": repeats, "total_ok": total_ok, "total_runs": total_runs,
       "full_pass_rate": f"{total_ok}/{total_runs}", "per_case": per_case, "expect": expect}
out_path = summary_path.replace("-summary.jsonl", "-aggregate.json")
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
PY

echo "B9 remote → $RUNS/${TAG}-aggregate.json"
