#!/bin/bash
# Остановить осиротевший прогон золотого набора на okna (ssh с этой стороны убит,
# python на сервере продолжал бы жечь вызовы модели).
# Шаблон собирается из кусков: иначе pkill -f находит собственную командную строку
# и глушит сам сеанс ssh (ответ 255 вместо отчёта).
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" bash -s <<'EOF'
PAT="ab_""scorer.py"
n=$(pgrep -fc "$PAT" || true)
if [ "${n:-0}" -gt 0 ]; then
  pkill -f "$PAT" || true
  echo "прогон на okna остановлен (процессов: $n)"
else
  echo "прогонов на okna нет"
fi
EOF
