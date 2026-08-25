#!/bin/bash
# Чистка места в /var/lib/serenedb на локальном dev: только восстановимые выгрузки.
# Каталог данных движка (engine_duckdb / engine_search) скрипт не удаляет.
#
# По умолчанию — холостой прогон (печать плана). Удаление только при:
#   CONFIRM_DEV_DISK_CLEANUP=YES
# и после заморозки (serenedb.service не active) — иначе отказ в режиме удаления.
#
# Запуск:
#   ./06-dev-disk-cleanup.sh
#   CONFIRM_DEV_DISK_CLEANUP=YES ./06-dev-disk-cleanup.sh
set -euo pipefail

ROOT=/var/lib/serenedb
CONFIRM="${CONFIRM_DEV_DISK_CLEANUP:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
ok()  { echo "OK: $*"; }
info(){ echo "INFO: $*"; }

bytes_human() {
  local b="$1"
  awk -v b="$b" 'BEGIN{
    if (b<1024){printf "%d B", b; exit}
    split("KiB MiB GiB TiB", u, " ");
    x=b; i=0;
    while (x>=1024 && i<4){x/=1024; i++}
    printf "%.2f %s", x, u[i]
  }'
}

# Цели удаления: только промежуточные выгрузки / EXPORT-снимок Ф1.
# Не входят: engine_duckdb, engine_search, packet-meta, LOCK, conf.
declare -a TARGETS=()

add_dir_if_present() {
  local p="$1"
  if [[ -d "$p" ]]; then
    TARGETS+=("$p")
  fi
}

echo "=== предпроверки ==="
[[ -d "$ROOT" ]] || die "нет каталога ${ROOT}"

if findmnt -T "$ROOT" -no FSTYPE,SOURCE 2>/dev/null | grep -qiE 'nfs|cifs|fuse|sshfs'; then
  die "STOP: ${ROOT} на сетевой ФС — отказ (риск задеть okna/klient1)"
fi
ok "ФС локальная: $(findmnt -T "$ROOT" -no FSTYPE,SOURCE 2>/dev/null || echo '?')"

# Абсолютные цели строго под ROOT
add_dir_if_present "${ROOT}/f1-export-prod"
add_dir_if_present "${ROOT}/csv-ut_test"
add_dir_if_present "${ROOT}/ut"

# Корневые *.csv (выгрузки синка/такта), не каталоги движка
mapfile -t ROOT_CSV < <(find "$ROOT" -maxdepth 1 -type f -name '*.csv' 2>/dev/null | sort || true)

echo ""
echo "=== план удаления ==="
TOTAL=0
printf '%-55s %12s\n' "PATH" "SIZE"
for d in "${TARGETS[@]}"; do
  case "$d" in
    "${ROOT}"/*) ;;
    *) die "внутренняя ошибка: путь вне ${ROOT}: ${d}" ;;
  esac
  sz="$(du -sb "$d" 2>/dev/null | awk '{print $1}')"
  TOTAL=$((TOTAL + sz))
  printf '%-55s %12s\n' "$d" "$(bytes_human "$sz")"
done

CSV_BYTES=0
CSV_COUNT=${#ROOT_CSV[@]}
if (( CSV_COUNT > 0 )); then
  for f in "${ROOT_CSV[@]}"; do
    case "$f" in
      "${ROOT}"/*.csv) ;;
      *) die "внутренняя ошибка: csv вне корня: ${f}" ;;
    esac
    b="$(stat -c '%s' "$f" 2>/dev/null || echo 0)"
    CSV_BYTES=$((CSV_BYTES + b))
  done
  TOTAL=$((TOTAL + CSV_BYTES))
  printf '%-55s %12s\n' "${ROOT}/*.csv (${CSV_COUNT} файлов)" "$(bytes_human "$CSV_BYTES")"
fi

echo ""
echo "Итого к удалению: $(bytes_human "$TOTAL") (${TOTAL} байт)"
echo ""
echo "НЕ удаляется этим скриптом:"
echo "  ${ROOT}/engine_duckdb   — store.db + wal (данные движка)"
echo "  ${ROOT}/engine_search   — поисковый слой движка"
echo "  ${ROOT}/packet-meta     — метаданные пакетного контура"
echo "  Ручной снос базы — см. work/root-tasks/00-README-dev-freeze.md"

AVAIL_BEFORE="$(df -B1 --output=avail "$ROOT" | tail -1 | tr -d ' ')"

if [[ "$CONFIRM" != "YES" ]]; then
  echo ""
  info "холостой режим: ничего не удалено"
  info "для удаления: CONFIRM_DEV_DISK_CLEANUP=YES $0"
  exit 0
fi

[[ $(id -u) -eq 0 ]] || die "удаление — только от root"

if systemctl is-active --quiet serenedb.service 2>/dev/null; then
  die "serenedb.service ещё active — сначала ./05-dev-freeze.sh"
fi
ok "serenedb.service не active"

echo ""
echo "=== удаление ==="
for d in "${TARGETS[@]}"; do
  echo "rm -rf -- ${d}"
  rm -rf -- "$d"
done
if (( CSV_COUNT > 0 )); then
  echo "rm -f -- ${ROOT}/*.csv  (${CSV_COUNT} файлов)"
  # только файлы из собранного списка, не glob сюрпризов
  for f in "${ROOT_CSV[@]}"; do
    rm -f -- "$f"
  done
fi

AVAIL_AFTER="$(df -B1 --output=avail "$ROOT" | tail -1 | tr -d ' ')"
FREED=$((AVAIL_AFTER - AVAIL_BEFORE))
if (( FREED < 0 )); then FREED=0; fi

echo ""
echo "=== после чистки ==="
du -sh "$ROOT" 2>/dev/null || true
df -h "$ROOT" | tail -1
ok "освобождено по df avail: $(bytes_human "$FREED") (план был $(bytes_human "$TOTAL"))"
