#!/bin/bash
# Замер psql за один такт build.sh — без правки такта.
#
# Принцип: обёртка psql в PATH; каждый запуск пишет строку в счётчик.
# build.sh и цепочка (*.sh, *.py) зовут psql как раньше — меняется только
# исполняемый файл в начале PATH.
#
# Использование (запускать владельцу/оркестратору, не из офлайн-аудита):
#   bash work/pipeline/count_psql_per_tick.sh [аргументы build.sh…]
#
# Переменные:
#   PSQL_COUNT_DIR   — каталог замера (умолч. work/acceptance/runs/psql-count-<ts>)
#   PSQL_COUNT_BUILD — путь к build.sh (умолч. ubuntu/serenedb/build.sh)
#   SERENEDB_DSN и прочее окружение такта — как у обычного build.sh
#
# Выход: JSON в $PSQL_COUNT_DIR/summary.json и таблица в stdout.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="${PSQL_COUNT_BUILD:-$ROOT/ubuntu/serenedb/build.sh}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="${PSQL_COUNT_DIR:-$ROOT/work/acceptance/runs/psql-count-$TS}"
WRAP="$OUT/bin"
LOG="$OUT/events.tsv"
COUNTER="$OUT/count"
BYTES="$OUT/bytes_out"

mkdir -p "$WRAP"
: > "$LOG"
printf '0\n' > "$COUNTER"
printf '0\n' > "$BYTES"

# Реальный psql — первый в PATH без нашей обёртки.
REAL_PSQL="$(command -v psql)"
while [ -L "$REAL_PSQL" ]; do REAL_PSQL="$(readlink -f "$REAL_PSQL")"; done
if [ ! -x "$REAL_PSQL" ]; then
  echo "count_psql_per_tick: psql не найден в PATH" >&2
  exit 1
fi

cat > "$WRAP/psql" <<WRAP
#!/bin/bash
set -u
OUT="$OUT"
REAL="$REAL_PSQL"
COUNTER="$COUNTER"
BYTES="$BYTES"
LOG="$LOG"
# Атомарный инкремент (flock на каталоге замера).
exec 8>"\$OUT/.lock"
flock 8
n=\$(cat "\$COUNTER")
printf '%s\n' \$((n + 1)) > "\$COUNTER"
# Объём stdout+stderr этого вызова (приближение «что уехало наружу»).
tmp=\$(mktemp)
"\$REAL" "\$@" >"\$tmp.out" 2>"\$tmp.err"
rc=\$?
out_b=\$(wc -c <"\$tmp.out" | tr -d ' ')
err_b=\$(wc -c <"\$tmp.err" | tr -d ' ')
b=\$((out_b + err_b))
tb=\$(cat "\$BYTES")
printf '%s\n' \$((tb + b)) > "\$BYTES"
printf '%s\t%s\t%s\t%s\t%s\n' "\$(date -Iseconds)" "\$((n + 1))" "\$out_b" "\$err_b" "\$*" >> "\$LOG"
cat "\$tmp.out"
cat "\$tmp.err" >&2
rm -f "\$tmp.out" "\$tmp.err"
exit \$rc
WRAP
chmod +x "$WRAP/psql"

export PATH="$WRAP:$PATH"
export PSQL_COUNT_RUN_ID="$TS"
export PSQL_COUNT_DIR="$OUT"

t0=$(date +%s)
(
  cd "$(dirname "$BUILD")" || exit 1
  exec bash "./$(basename "$BUILD")" "$@"
)
build_rc=$?
t1=$(date +%s)

total=$(cat "$COUNTER")
total_bytes=$(cat "$BYTES")

python3 - "$OUT" "$total" "$total_bytes" "$build_rc" "$((t1 - t0))" <<'PY'
import json, os, sys
out, total, total_bytes, rc, secs = sys.argv[1:6]
events = []
log = os.path.join(out, "events.tsv")
if os.path.isfile(log):
    with open(log, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 4)
            if len(parts) >= 5:
                events.append({
                    "ts": parts[0],
                    "n": int(parts[1]),
                    "stdout_b": int(parts[2]),
                    "stderr_b": int(parts[3]),
                    "argv_tail": parts[4][:500],
                })
big = sorted(events, key=lambda e: e["stdout_b"] + e["stderr_b"], reverse=True)[:15]
summary = {
    "run_id": os.path.basename(out),
    "psql_invocations": int(total),
    "output_bytes_total": int(total_bytes),
    "build_exit_code": int(rc),
    "duration_sec": int(secs),
    "events_log": log,
    "top_by_output_bytes": big,
}
with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

exit "$build_rc"
