#!/bin/bash
# Прибор Ф6.5: снимок ДО/ПОСЛЕ по одному флагу и таблица сравнения.
# Флаг в env юнита/процесса ставит оператор снаружи — этот скрипт только меряет.
#
# Env:
#   ASK_URL     — http://host:port/ask (обязателен для before/after)
#   F6_FLAG     — имя флага (метка снимка), напр. ASK_RESOLVER_IVF
#   F6_PHASE    — before | after | compare
#   F6_MARK_DIR — корень снимков (умолч. work/acceptance/runs/f6-rollout)
#   ASK_TOKEN   — если сервис требует Bearer
#   F6_SKIP_GOLDEN=1 / F6_SKIP_PROBE=1 — пропуск части (только для отладки прибора)
#
# Коды: 0 ок; 2 нет URL/флага/фазы; 3 контур недоступен; 4 пустой/битый снимок;
#       5 провал probe/golden; 6 compare: нет пары before/after.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PHASE=${F6_PHASE:-}
FLAG=${F6_FLAG:-}
MARK_ROOT=${F6_MARK_DIR:-$ROOT/work/acceptance/runs/f6-rollout}
ASK_URL=${ASK_URL:-}
GOLDEN_SH=${GOLDEN_SH:-$HERE/golden.sh}
GOLDEN_FILE=${GOLDEN_FILE:-$HERE/golden-questions.txt}
AB_SCORER=${AB_SCORER:-$HERE/ab_scorer.py}
CURL_MAX=${F6_CURL_MAX:-15}
ASK_SMOKE_MAX=${F6_ASK_SMOKE_MAX:-120}

die() { echo "f6_rollout_measure: $*" >&2; exit "${2:-2}"; }

phase_dir() {
  printf '%s/%s/%s' "$MARK_ROOT" "$FLAG" "$1"
}

# --- health base URL from ASK_URL ---
health_url() {
  local u=${1%/ask}
  u=${u%/}
  printf '%s/health' "$u"
}

ready_check() {
  local hu code kind ms t0 t1 hc hb_file he_file ae_file
  hb_file=$(mktemp)
  he_file=$(mktemp)
  ae_file=$(mktemp)
  hu=$(health_url "$ASK_URL")
  t0=$(date +%s%N)
  set +e
  code=$(curl -sS --max-time "$CURL_MAX" -o "$hb_file" -w '%{http_code}' "$hu" 2>"$he_file")
  hc=$?
  set -e
  if [ "$hc" -ne 0 ]; then
    echo "f6_rollout_measure: контур недоступен: /health curl rc=$hc ($(tr '\n' ' ' <"$he_file"))" >&2
    rm -f "$hb_file" "$he_file" "$ae_file"
    exit 3
  fi
  t1=$(date +%s%N)
  ms=$(( (t1 - t0) / 1000000 ))
  if [ "$code" != "200" ]; then
    echo "f6_rollout_measure: контур недоступен: /health HTTP $code (${ms} мс)" >&2
    rm -f "$hb_file" "$he_file" "$ae_file"
    exit 3
  fi
  # живой /ask: без модели/базы замер бракован (план §Ф6)
  local payload out_ask curl_ask
  payload=$(python3 -c 'import json; print(json.dumps({"question":"ping readiness f6"}))')
  t0=$(date +%s%N)
  curl_ask=(curl -sS --max-time "$ASK_SMOKE_MAX" -X POST "$ASK_URL" \
    -H 'Content-Type: application/json')
  if [ -n "${ASK_TOKEN:-}" ]; then
    curl_ask+=(-H "Authorization: Bearer $ASK_TOKEN")
  fi
  curl_ask+=(-d "$payload")
  set +e
  out_ask=$("${curl_ask[@]}" 2>"$ae_file")
  hc=$?
  set -e
  t1=$(date +%s%N)
  if [ "$hc" -ne 0 ] || [ -z "$out_ask" ]; then
    echo "f6_rollout_measure: модель или база недоступны: /ask curl rc=$hc ($(tr '\n' ' ' <"$ae_file"))" >&2
    rm -f "$hb_file" "$he_file" "$ae_file"
    exit 3
  fi
  kind=$(printf '%s' "$out_ask" | python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    print("")
    raise SystemExit(0)
err=(d.get("diag") or {}).get("error")
print("" if err else (d.get("kind") or ""))
' 2>/dev/null || true)
  if [ -z "$kind" ]; then
    echo "f6_rollout_measure: модель или база недоступны: /ask без kind / не JSON" >&2
    rm -f "$hb_file" "$he_file" "$ae_file"
    exit 3
  fi
  ASK_SMOKE_KIND=$kind
  ASK_SMOKE_MS=$(( (t1 - t0) / 1000000 ))
  HEALTH_MS=$ms
  HEALTH_BODY=$(cat "$hb_file")
  rm -f "$hb_file" "$he_file" "$ae_file"
}

run_probe() {
  local outf=$1
  if [ "${F6_SKIP_PROBE:-0}" = "1" ]; then
    echo '{"skipped":true,"hits":null,"total":null,"errs":null,"secs":null}' >"$outf"
    return 0
  fi
  local log rc
  log=$(mktemp)
  set +e
  AB_PROBE=okna ASK_URL="$ASK_URL" \
    python3 "$AB_SCORER" >"$log" 2>&1
  rc=$?
  set -e
  cp "$log" "$(dirname "$outf")/probe.log"
  python3 - "$log" "$outf" "$rc" <<'PY'
import re, json, sys
log, outf, rc = sys.argv[1], sys.argv[2], int(sys.argv[3])
text = open(log, encoding="utf-8", errors="replace").read()
hits = total = secs = errs = None
m = re.search(r"верных\s+(\d+)/(\d+).*?средняя\s+([0-9.]+)\s*с", text, re.S)
if m:
    hits, total, secs = int(m.group(1)), int(m.group(2)), float(m.group(3))
me = re.search(r"СБОЕВ\s+(\d+)", text)
if me:
    errs = int(me.group(1))
else:
    me2 = re.search(r"сбоев\s+(\d+)", text, re.I)
    errs = int(me2.group(1)) if me2 else (0 if hits is not None else None)
json.dump({
    "rc": rc, "hits": hits, "total": total, "errs": errs, "secs": secs,
    "ok_parse": hits is not None and total is not None,
}, open(outf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  # снимок с hits сохраняем даже при rc!=0 (есть FAIL-строки); брак — нет разбора или errs>0
  python3 - "$outf" <<'PY' || exit 5
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
if not d.get("ok_parse"):
    print("f6_rollout_measure: probe: нет разбора «верных N/M» — замер бракован", file=sys.stderr)
    sys.exit(5)
if (d.get("errs") or 0) > 0:
    print("f6_rollout_measure: probe: сбои обращения errs=%s" % d.get("errs"), file=sys.stderr)
    sys.exit(5)
PY
}

run_golden() {
  local outf=$1
  if [ "${F6_SKIP_GOLDEN:-0}" = "1" ]; then
    echo '{"skipped":true,"n":null}' >"$outf"
    return 0
  fi
  if [ ! -f "$GOLDEN_FILE" ]; then
    echo "f6_rollout_measure: нет golden-файла: $GOLDEN_FILE" >&2
    exit 4
  fi
  local n_q
  n_q=$(python3 - "$GOLDEN_FILE" <<'PY'
import sys
n=0
for line in open(sys.argv[1], encoding="utf-8"):
    s=line.strip()
    if not s or s.startswith("#"):
        continue
    n+=1
print(n)
PY
)
  if [ "${n_q:-0}" -le 0 ]; then
    echo "f6_rollout_measure: golden-набор пуст — успехом не считаем" >&2
    exit 4
  fi
  local log
  log=$(mktemp)
  set +e
  ASK_URL="$ASK_URL" GOLDEN_FILE="$GOLDEN_FILE" bash "$GOLDEN_SH" >"$log" 2>&1
  local rc=$?
  set -e
  cp "$log" "$(dirname "$outf")/golden.log"
  python3 - "$log" "$outf" "$rc" "$n_q" <<'PY'
import re, json, sys
log, outf, rc, n_q = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
text = open(log, encoding="utf-8", errors="replace").read()
m = re.search(r"вопросов:\s*(\d+)", text)
n = int(m.group(1)) if m else None
kinds = re.findall(r"^\S.*?\s+(\S+)\s+", text, re.M)
json.dump({
    "rc": rc, "n": n, "expected_n": n_q, "ok_parse": n is not None and n > 0,
}, open(outf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
if n is None or n <= 0:
    sys.exit(4)
PY
}

write_summary() {
  local dest=$1
  python3 - "$dest" "$FLAG" "$PHASE" "$ASK_URL" "$HEALTH_MS" "$ASK_SMOKE_MS" "$ASK_SMOKE_KIND" "$HEALTH_BODY" <<'PY'
import json, sys, os
dest, flag, phase, url, h_ms, a_ms, kind, health_raw = sys.argv[1:9]
d = os.path.dirname(dest)
probe = json.load(open(os.path.join(d, "probe.json"), encoding="utf-8"))
golden = json.load(open(os.path.join(d, "golden.json"), encoding="utf-8"))
try:
    health_obj = json.loads(health_raw)
except Exception:
    health_obj = {"_raw": health_raw[:500]}
fresh = {}
if isinstance(health_obj, dict):
    fr = health_obj.get("freshness") or {}
    if isinstance(fr, dict):
        for k in ("index_buffered_docs", "index_failed_commits",
                  "refresh_pending", "refresh_active", "merge_pending_sec"):
            if k in fr:
                fresh[k] = fr[k]
summary = {
    "flag": flag,
    "phase": phase,
    "ask_url": url,
    "health_ms": int(h_ms),
    "ask_smoke_ms": int(a_ms),
    "ask_smoke_kind": kind,
    "freshness": fresh,
    "probe": probe,
    "golden": golden,
}
json.dump(summary, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
}

do_measure() {
  [ -n "$ASK_URL" ] || die "ASK_URL пуст"
  [ -n "$FLAG" ] || die "F6_FLAG пуст"
  local dir
  dir=$(phase_dir "$PHASE")
  mkdir -p "$dir"
  ready_check
  printf '%s\n' "$HEALTH_BODY" >"$dir/health.json"
  run_probe "$dir/probe.json"
  run_golden "$dir/golden.json"
  write_summary "$dir/summary.json"
  echo "f6_rollout_measure: снимок $FLAG/$PHASE → $dir/summary.json"
}

do_compare() {
  [ -n "$FLAG" ] || die "F6_FLAG пуст"
  local b a
  b=$(phase_dir before)/summary.json
  a=$(phase_dir after)/summary.json
  if [ ! -f "$b" ] || [ ! -f "$a" ]; then
    echo "f6_rollout_measure: нет пары снимков before/after для $FLAG" >&2
    echo "  before: $b" >&2
    echo "  after:  $a" >&2
    exit 6
  fi
  python3 - "$b" "$a" "$FLAG" <<'PY'
import json, sys
b = json.load(open(sys.argv[1], encoding="utf-8"))
a = json.load(open(sys.argv[2], encoding="utf-8"))
flag = sys.argv[3]

def cell(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return "—"
        cur = cur[p]
    if cur is None:
        return "—"
    return cur

rows = [
    ("probe hits", cell(b, "probe", "hits"), cell(a, "probe", "hits")),
    ("probe total", cell(b, "probe", "total"), cell(a, "probe", "total")),
    ("probe errs", cell(b, "probe", "errs"), cell(a, "probe", "errs")),
    ("probe secs", cell(b, "probe", "secs"), cell(a, "probe", "secs")),
    ("golden n", cell(b, "golden", "n"), cell(a, "golden", "n")),
    ("health_ms", cell(b, "health_ms"), cell(a, "health_ms")),
    ("ask_smoke_ms", cell(b, "ask_smoke_ms"), cell(a, "ask_smoke_ms")),
    ("ask_smoke_kind", cell(b, "ask_smoke_kind"), cell(a, "ask_smoke_kind")),
]
print("flag: %s" % flag)
print("| metric | before | after |")
print("|---|---|---|")
for name, bv, av in rows:
    print("| %s | %s | %s |" % (name, bv, av))

# пустой набор в снимке — не успех сравнения
for label, d in (("before", b), ("after", a)):
    p = d.get("probe") or {}
    g = d.get("golden") or {}
    if p.get("skipped") and g.get("skipped"):
        print("f6_rollout_measure: снимок %s пуст (probe+golden skipped)" % label, file=sys.stderr)
        sys.exit(4)
    if not p.get("skipped") and not p.get("ok_parse"):
        print("f6_rollout_measure: снимок %s: probe без разбора" % label, file=sys.stderr)
        sys.exit(4)
PY
}

case "$PHASE" in
  before|after) do_measure ;;
  compare) do_compare ;;
  *) die "F6_PHASE=before|after|compare (сейчас '${PHASE:-∅}')" ;;
esac
