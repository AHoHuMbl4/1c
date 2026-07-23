#!/usr/bin/env bash
# Оффлайн-снапшот витрины SereneDB (проверено round-trip: снапшот → потеря → restore → данные на месте).
# Кратко останавливает serenedb для консистентности. Ротация: держим последние KEEP.
#
# ⚠ ПЕРВИЧНОЕ восстановление витрины — РЕ-СИНК из 1С (`serene_sync`, витрина производная — не система
#   оф-рекорд). Снапшот — БЫСТРЫЙ restore без повторного пула OData и ре-эмбеддинга резолвера.
#
# Запуск: bash serenedb_backup.sh   (или systemd-таймер, если нужен регулярный).
set -euo pipefail
DIR=${BACKUP_DIR:-/root/backups/serenedb}
KEEP=${KEEP:-7}
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DIR"

systemctl stop serenedb
tar czf "$DIR/serenedb-$TS.tar.gz" -C /var/lib/serenedb .
systemctl start serenedb

# ротация
ls -1t "$DIR"/serenedb-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "backup: $DIR/serenedb-$TS.tar.gz ($(du -h "$DIR/serenedb-$TS.tar.gz" | cut -f1))"

# RESTORE (вручную):
#   systemctl stop serenedb
#   rm -rf /var/lib/serenedb/*
#   tar xzf <backup.tar.gz> -C /var/lib/serenedb
#   chown -R serenedb:serenedb /var/lib/serenedb
#   systemctl start serenedb
