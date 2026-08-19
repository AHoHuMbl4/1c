#!/bin/bash
# Пересборка золотого набора okna ИЗ ДАННЫХ базы: генератор едет на okna, читает корпус,
# отдаёт ab-gold-okna.tsv обратно в репозиторий.
set -euo pipefail
KEY=~/.ssh/id_ed25519_deploy
HOST=root@167.233.249.110
SRC=/srv/1c/ubuntu/serenedb
scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$SRC/ab_gold_build.py" "$HOST:/tmp/"
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST" \
  'python3 /tmp/ab_gold_build.py /tmp/ab-gold-okna.tsv /tmp/ab-gold-okna-answers.md'
scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" "$HOST:/tmp/ab-gold-okna.tsv" \
  "$SRC/ab-gold-okna.tsv"
scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$KEY" \
  "$HOST:/tmp/ab-gold-okna-answers.md" /srv/1c/docs/AB_GOLD_OKNA.md
echo "=== $SRC/ab-gold-okna.tsv ==="
cat "$SRC/ab-gold-okna.tsv"
echo "=== docs/AB_GOLD_OKNA.md ==="
cat /srv/1c/docs/AB_GOLD_OKNA.md
