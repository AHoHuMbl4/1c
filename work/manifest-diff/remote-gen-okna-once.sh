#!/usr/bin/env bash
# Одноразовый прогон metadata-okna на okna через /tmp/genrepo (оркестратор).
set -euo pipefail
KEY="${KEY:-/home/claudedev/.ssh/id_ed25519_deploy}"
HOST="${HOST:-root@gpu-erw.timpul.pro}"
PORT="${PORT:-2202}"
LOCAL_GEN="/srv/1c/work/manifest-diff/gen_metadata_vitrine.py"
REMOTE_GEN="/tmp/genrepo/work/manifest-diff/gen_metadata_vitrine.py"
REMOTE_OUT="/tmp/genrepo/work/manifest-diff/metadata-okna.xml"
LOCAL_OUT="/srv/1c/work/manifest-diff/metadata-okna.xml"

scp -i "$KEY" -P "$PORT" -q "$LOCAL_GEN" "$HOST:$REMOTE_GEN"
ssh -i "$KEY" -p "$PORT" -o BatchMode=yes "$HOST" 'cd /tmp/genrepo && bash work/manifest-diff/run-metadata-okna.sh'
scp -i "$KEY" -P "$PORT" -q "$HOST:$REMOTE_OUT" "$LOCAL_OUT"
python3 /srv/1c/work/manifest-diff/test_gen_metadata_vitrine.py
