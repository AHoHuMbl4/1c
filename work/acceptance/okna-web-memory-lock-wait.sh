#!/bin/bash
# 35 мин: журнал web-гейтвея без memory-error (poll каждые 60 с)
set -euo pipefail
OUT=/tmp/okna-memory-lock-$(date +%Y%m%d-%H%M%S).log
echo "start $(date -Is)" | tee "$OUT"
ERR=0
for i in $(seq 1 35); do
  n=$(journalctl _SYSTEMD_USER_UNIT=openclaw-gateway-web -M undebot@ --since "2 min ago" --no-pager 2>/dev/null \
    | grep -ciE 'Memory index failed|memory embeddings unavailable|No API key resolved|openai-compatible embeddings failed' || true)
  echo "$(date -Is) poll=$i memory_errors=$n" | tee -a "$OUT"
  if [ "$n" -gt 0 ]; then ERR=$n; fi
  sleep 60
done
if [ "$ERR" -eq 0 ]; then
  echo "LOCK_OK $(date -Is)" | tee -a "$OUT"
else
  echo "LOCK_FAIL last_err=$ERR $(date -Is)" | tee -a "$OUT"
fi
