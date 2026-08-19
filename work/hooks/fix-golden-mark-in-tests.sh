#!/usr/bin/env bash
# fix-golden-mark-in-tests.sh — одноразовая правка test-hooks.sh под новый
# двухуровневый check-golden (smoke-отметка с текстом, а не пустой touch).
# Идемпотентен, с бэкапом и проверкой. Запуск: sudo bash work/hooks/fix-golden-mark-in-tests.sh
set -euo pipefail

cd "$(dirname "$0")/.."
F="work/hooks/test-hooks.sh"
OLD="touch .claude/.golden-last-run"
NEW="echo 'smoke ut_test live 0err/8' > .claude/.golden-last-run"

old_n=$(grep -c "^${OLD}$" "$F" || true)
new_n=$(grep -cF "$NEW" "$F" || true)

if [ "$old_n" = "0" ] && [ "$new_n" = "2" ]; then
  echo "уже сделано: обе отметки в формате smoke, ничего не менял"
  exit 0
fi
if [ "$old_n" != "2" ]; then
  echo "СТОП: ожидал ровно 2 строки '$OLD', нашёл $old_n — файл изменился, правь руками" >&2
  exit 1
fi

cp "$F" "$F.bak-golden-mark-$(date -u +%Y%m%d-%H%M%S)"
python3 - "$F" "$OLD" "$NEW" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path, encoding="utf-8").read()
n = src.count(old + "\n")
assert n == 2, f"ожидал 2 вхождения, есть {n}"
open(path, "w", encoding="utf-8").write(src.replace(old + "\n", new + "\n"))
print(f"заменено строк: {n}")
PY

grep -cF "$NEW" "$F" | grep -q "^2$" && echo "проверка: 2 отметки в формате smoke — ок"
echo "проверка прогоном: sudo bash work/hooks/test-hooks.sh 2>&1 | tail -5"
