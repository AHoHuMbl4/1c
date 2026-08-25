#!/bin/bash
# Заморозка локального dev-контура SereneDB (:7890) на этой машине.
# Только stop + disable автозапуска. Файлы и каталоги данных не удаляет.
# Решение владельца 25.08: «dev тормозим, замораживаем»; бой — okna и klient1.
#
# Запуск от root:
#   ./05-dev-freeze.sh
# Предпросмотр без изменений:
#   DEV_FREEZE_DRY_RUN=1 ./05-dev-freeze.sh
set -euo pipefail

DRY="${DEV_FREEZE_DRY_RUN:-0}"

die() { echo "ERROR: $*" >&2; exit 1; }
ok()  { echo "OK: $*"; }
info(){ echo "INFO: $*"; }

if [[ "$DRY" != "1" ]]; then
  [[ $(id -u) -eq 0 ]] || die "запускать от root (или DEV_FREEZE_DRY_RUN=1 для предпросмотра)"
fi

# Только эта машина: loopback :7890 и /var/lib/serenedb на локальном rootfs LXC.
# okna / klient1 — отдельные хосты со своими /var/lib/serenedb; сюда не входят.
HOST_FQDN="$(hostname -f 2>/dev/null || hostname)"
info "хост=${HOST_FQDN} dry_run=${DRY}"

# Поимённо, без масок. Порядок: таймеры → клиенты → движок.
TIMERS=(
  1c-bot-monitor.timer
  1c-packet-apply.timer
  1c-serene-pipeline@ut_test.timer
  1c-serene-pipeline@postgres.timer
  1c-serene-pipeline.timer
  1c-serene-sync.timer
  1c-serene-index.timer
)

SERVICES=(
  1c-bot-monitor.service
  1c-serene-ask@postgres.service
  1c-serene-ask@ut_test.service
  1c-mcp-ask@postgres.service
  1c-mcp-ask@ut_test.service
  1c-mcp-reports.service
  1c-wiki-alias.service
  1c-branch-alias.service
  1c-serene-pipeline@postgres.service
  1c-serene-pipeline@ut_test.service
  1c-serene-sync.service
  1c-serene-index.service
  1c-packet-apply.service
  serenedb.service
)

# Юниты вне заморозки (остаются как есть): packet-server, odata-gateway*,
# config-ui, gate-tunnel*, openclaw-gateway-restart, etl (KB, не SereneDB).

act_stop() {
  local u="$1"
  if [[ "$DRY" == "1" ]]; then
    echo "  [dry] systemctl stop ${u}"
    return 0
  fi
  if systemctl stop "$u" 2>/dev/null; then
    ok "stop ${u}"
  else
    info "stop ${u}: уже не running или нет юнита"
  fi
}

act_disable() {
  local u="$1"
  if [[ "$DRY" == "1" ]]; then
    echo "  [dry] systemctl disable ${u}"
    return 0
  fi
  local en
  en="$(systemctl is-enabled "$u" 2>/dev/null || true)"
  case "$en" in
    enabled|enabled-runtime|linked|linked-runtime|alias)
      if systemctl disable "$u" 2>/dev/null; then
        ok "disable ${u} (было ${en})"
      else
        info "disable ${u}: не удалось (state=${en})"
      fi
      ;;
    static)
      info "disable ${u}: static — автозапуск через timer/Wants, stop достаточно"
      ;;
    disabled|masked|indirect|not-found|"")
      info "disable ${u}: уже ${en:-absent}"
      ;;
    *)
      info "disable ${u}: state=${en} — пропуск"
      ;;
  esac
}

echo "=== предпроверка путей (пересечение с okna/klient1) ==="
if findmnt -T /var/lib/serenedb -no FSTYPE,SOURCE 2>/dev/null | grep -qiE 'nfs|cifs|fuse|sshfs'; then
  die "STOP: /var/lib/serenedb на сетевой ФС — чистка/заморозка может задеть чужой хост"
fi
ok "/var/lib/serenedb на локальной ФС: $(findmnt -T /var/lib/serenedb -no FSTYPE,SOURCE 2>/dev/null || echo '?')"

if grep -RIlE 'okna|klient|167\.233\.249\.110|10\.1\.1\.7|10\.10\.10\.12' /etc/1c-*.env 2>/dev/null | head -1 | grep -q .; then
  die "STOP: в /etc/1c-*.env есть ссылка на okna/klient — разбор вручную"
fi
ok "в /etc/1c-*.env нет хостов okna/klient1"

echo ""
echo "=== 1/3 stop+disable таймеров ==="
for u in "${TIMERS[@]}"; do
  act_stop "$u"
  act_disable "$u"
done

echo ""
echo "=== 2/3 stop+disable сервисов (клиенты, затем движок) ==="
for u in "${SERVICES[@]}"; do
  act_stop "$u"
  act_disable "$u"
done

echo ""
echo "=== 3/3 итог ==="
printf '%-45s %-12s %s\n' "UNIT" "ACTIVE" "ENABLED"
for u in "${TIMERS[@]}" "${SERVICES[@]}"; do
  # is-enabled даёт ненулевой код для disabled/static — это не «нет юнита»
  a="$(systemctl is-active "$u" 2>/dev/null || true)"
  e="$(systemctl is-enabled "$u" 2>/dev/null || true)"
  [[ -n "$a" ]] || a=n/a
  [[ -n "$e" ]] || e=n/a
  printf '%-45s %-12s %s\n' "$u" "$a" "$e"
done

echo ""
echo "=== что ещё живо из 1c-*/serenedb (для сверки) ==="
systemctl list-units '1c-*' 'serenedb*' --type=service,timer --state=running,waiting --no-pager 2>/dev/null || true

if [[ "$DRY" == "1" ]]; then
  echo ""
  info "DRY_RUN=1: ничего не останавливалось. Боевой прогон: убрать DEV_FREEZE_DRY_RUN и запустить от root."
else
  echo ""
  ok "заморозка выполнена: юниты остановлены, автозапуск где возможно отключён; данные на диске не трогались"
  info "чистка CSV — отдельно: ./06-dev-disk-cleanup.sh (сначала без CONFIRM, потом с подтверждением)"
fi
