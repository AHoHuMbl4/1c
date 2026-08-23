#!/bin/bash
# Ф3: apt purge postgresql-16* на dev. SereneDB (:7890, /usr/local/bin/serened) не трогаем.
set -euo pipefail

SERENED_BIN=/usr/local/bin/serened
SERENED_PORT=7890

die() { echo "ERROR: $*" >&2; exit 1; }
ok()  { echo "OK: $*"; }

[[ $(id -u) -eq 0 ]] || die "запускать от root"

echo "=== предварительные проверки ==="

# SereneDB должна жить до и после
[[ -x "$SERENED_BIN" ]] || die "SereneDB бинарь ${SERENED_BIN} не найден — STOP"
ok "SereneDB бинарь: ${SERENED_BIN}"

if systemctl is-active --quiet serenedb.service 2>/dev/null; then
  ok "serenedb.service active"
else
  echo "WARN: serenedb.service не active — purge postgres всё равно безопасен для SereneDB"
fi

if ss -ltn 2>/dev/null | grep -q ":${SERENED_PORT} "; then
  ok "SereneDB слушает 127.0.0.1:${SERENED_PORT}"
else
  echo "WARN: порт ${SERENED_PORT} не слушает"
fi

# :5432 — стоп если ещё слушает (кластер не остановлен)
if ss -ltn 2>/dev/null | grep -q ':5432 '; then
  die "порт 5432 всё ещё слушает — сначала: systemctl stop postgresql@16-main postgresql && ss -ltn | grep 5432"
fi
ok "5432 не слушает"

if ss -tnp 2>/dev/null | grep -q ':5432'; then
  die "есть активные соединения к :5432 — дождаться или остановить клиентов"
fi
ok "активных соединений к :5432 нет"

# Список пакетов до purge
echo ""
echo "=== установленные postgres-пакеты (до) ==="
mapfile -t PKGS_BEFORE < <(dpkg -l 2>/dev/null | awk '/^ii/ && /postgres/ {print $2}' || true)
if ((${#PKGS_BEFORE[@]} == 0)); then
  echo "postgres-пакетов нет — нечего удалять"
  exit 0
fi
printf '  %s\n' "${PKGS_BEFORE[@]}"

# Purge целевых пакетов если установлены
PURGE_LIST=()
for pat in 'postgresql-16' 'postgresql-client-16' 'postgresql-16-pgvector'; do
  while IFS= read -r pkg; do
    [[ -n "$pkg" ]] && PURGE_LIST+=("$pkg")
  done < <(dpkg -l 2>/dev/null | awk -v p="$pat" '$1=="ii" && $2 ~ "^"p {print $2}')
done

if ((${#PURGE_LIST[@]} == 0)); then
  echo "Целевые postgresql-16* не установлены — autoremove и выход"
  apt-get autoremove -y
  exit 0
fi

echo ""
echo "=== apt purge ==="
DEBIAN_FRONTEND=noninteractive apt-get purge -y "${PURGE_LIST[@]}"
DEBIAN_FRONTEND=noninteractive apt-get autoremove -y

echo ""
echo "=== после purge ==="
mapfile -t PKGS_AFTER < <(dpkg -l 2>/dev/null | awk '/^ii/ && /postgres/ {print $2}' || true)
if ((${#PKGS_AFTER[@]} == 0)); then
  ok "postgres-пакетов не осталось"
else
  echo "Остались postgres-пакеты:"
  printf '  %s\n' "${PKGS_AFTER[@]}"
fi

if [[ -d /usr/lib/postgresql ]]; then
  echo "WARN: /usr/lib/postgresql ещё существует (возможны другие версии PG)"
  ls -la /usr/lib/postgresql 2>/dev/null || true
else
  ok "/usr/lib/postgresql удалён"
fi

# SereneDB цела
[[ -x "$SERENED_BIN" ]] || die "ПОСЛЕ purge пропал ${SERENED_BIN} — ОТКАТ через apt"
ok "SereneDB бинарь на месте после purge"

if ss -ltn 2>/dev/null | grep -q ":${SERENED_PORT} "; then
  ok "SereneDB :${SERENED_PORT} слушает после purge"
else
  echo "WARN: :${SERENED_PORT} не слушает — проверить systemctl status serenedb.service"
fi

echo ""
echo "Готово. Удалено пакетов: ${#PURGE_LIST[@]}"
