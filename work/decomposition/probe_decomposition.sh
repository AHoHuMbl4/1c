#!/usr/bin/env bash
# ДЕК1 — прогон точечных подвопросов к ядру /ask.
# Оркестратор запускает на контуре; сессия подготовки стенд не трогает.
#
# Обязательное окружение:
#   ASK_URL   — полный URL эндпоинта, например http://127.0.0.1:18092/ask
#   ASK_TOKEN — Bearer-токен сервиса ответов
# Необязательное:
#   OUT       — файл ответов (по умолчанию work/decomposition/out/probe-$$.jsonl)
#   ASK_TIMEOUT_SEC — таймаут одного запроса (по умолчанию 120)
#   ANCHOR_DATE — якорь «сегодня» для подписей (по умолчанию 2026-08-26, день лога scorer-k2)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${OUT:-$ROOT/work/decomposition/out/probe-$(date -u +%Y%m%dT%H%M%SZ).jsonl}"
ASK_TIMEOUT_SEC="${ASK_TIMEOUT_SEC:-120}"
ANCHOR_DATE="${ANCHOR_DATE:-2026-08-26}"

if [ -z "${ASK_URL:-}" ]; then
  echo "FATAL: задайте ASK_URL (полный URL /ask)" >&2
  exit 2
fi
if [ -z "${ASK_TOKEN:-}" ]; then
  echo "FATAL: задайте ASK_TOKEN" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUT")"
: > "$OUT"

# id|parent_id|role|question
# parent_id — исходный вопрос из /tmp/scorer-k2.log; role — контроль / атом разложения
QUESTIONS=$(cat <<'EOF'
C1|сколько продали вчера?|control|Сколько сумма продаж в деньгах за календарный день 2026-08-25 по всем клиентам и всем товарам?
C2|сколько продали в прошлом месяце?|control|Сколько сумма продаж в деньгах с 2026-07-01 по 2026-07-31 включительно по всем клиентам и всем товарам?
F1a|сколько позиций совсем не продаётся в этом месяце?|atom|Сколько позиций номенклатуры (не папок) всего в каталоге?
F1b|сколько позиций совсем не продаётся в этом месяце?|atom|Сколько различных товаров имели хотя бы одну продажу с 2026-08-01 по 2026-08-26 включительно?
F1c|сколько позиций совсем не продаётся в этом месяце?|atom|Сколько позиций номенклатуры (не папок) не имели ни одной продажи с 2026-08-01 по 2026-08-26 включительно?
F2a|эта неделя лучше прошлой или хуже?|atom|Сколько сумма продаж в деньгах с 2026-08-24 по 2026-08-26 включительно по всем клиентам и всем товарам?
F2b|эта неделя лучше прошлой или хуже?|atom|Сколько сумма продаж в деньгах с 2026-08-17 по 2026-08-23 включительно по всем клиентам и всем товарам?
F3a|в этом месяце продали больше, чем в прошлом?|atom|Сколько сумма продаж в деньгах с 2026-08-01 по 2026-08-26 включительно по всем клиентам и всем товарам?
F3b|в этом месяце продали больше, чем в прошлом?|atom|Сколько сумма продаж в деньгах с 2026-07-01 по 2026-07-31 включительно по всем клиентам и всем товарам?
F4a|сколько клиентов реально покупают?|atom|Сколько различных клиентов имели хотя бы одну продажу с 2025-08-26 по 2026-08-26 включительно?
EOF
)

echo "# DEK1 probe  anchor_date=$ANCHOR_DATE  ask_url=$ASK_URL  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
echo "# OUT=$OUT" >&2

n=0
while IFS='|' read -r id parent role question; do
  [ -n "${id:-}" ] || continue
  n=$((n + 1))
  rid="dek1-${id}-$(date -u +%Y%m%dT%H%M%SZ)"
  tmp="$(mktemp)"
  http=0
  t0=$(date +%s%3N)
  set +e
  http=$(curl -sS -m "$ASK_TIMEOUT_SEC" -o "$tmp" -w "%{http_code}" \
    -X POST "$ASK_URL" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $ASK_TOKEN" \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"question":sys.argv[1],"rid":sys.argv[2]},ensure_ascii=False))' "$question" "$rid")")
  curl_rc=$?
  set -e
  t1=$(date +%s%3N)
  elapsed_ms=$((t1 - t0))

  python3 - "$OUT" "$id" "$parent" "$role" "$question" "$rid" "$http" "$curl_rc" "$elapsed_ms" "$tmp" <<'PY'
import json, sys
out_path, id_, parent, role, question, rid, http, curl_rc, elapsed_ms, tmp = sys.argv[1:11]
rec = {
    "id": id_,
    "parent": parent,
    "role": role,
    "question": question,
    "rid": rid,
    "http": int(http) if str(http).isdigit() else http,
    "curl_rc": int(curl_rc),
    "elapsed_ms": int(elapsed_ms),
}
try:
    body = json.load(open(tmp, encoding="utf-8"))
except Exception as e:
    rec["parse_error"] = str(e)
    body = None
if isinstance(body, dict):
    rec["kind"] = body.get("kind")
    rec["text"] = body.get("text")
    rec["partial"] = body.get("partial")
    rec["figures"] = body.get("figures")
    # компактный diag без огромных кандидатов
    diag = body.get("diag") or {}
    if isinstance(diag, dict):
        rec["diag_keys"] = sorted(diag.keys())
        for k in ("fork_outcome", "kind", "preds", "parse"):
            if k in diag:
                rec["diag_%s" % k] = diag[k]
with open(out_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("%s http=%s kind=%s ms=%s" % (
    id_, http, (rec.get("kind") or "?"), elapsed_ms), flush=True)
PY
  rm -f "$tmp"
done <<< "$QUESTIONS"

echo "# done n=$n out=$OUT" >&2
echo "$OUT"
