# Разбор назначения scp/rsync для is_deploy. Подключается из lib-hooks.sh.
#
# Выкат: /opt /etc папка бота (.openclaw).
# Не выкат: /tmp и прочие пути.
# Путь не разобран: выкат (fail-closed).

is_runtime_dest() {
  local p="$1"
  p="${p#\'}"; p="${p%\'}"; p="${p#\"}"; p="${p%\"}"
  case "$p" in
    /opt|/opt/*|/etc|/etc/*) return 0 ;;
  esac
  case "$p" in
    */.openclaw|/*/.openclaw/*|/.openclaw) return 0 ;;
    ~*/.openclaw|~*/.openclaw/*|~/.openclaw|~/.openclaw/*) return 0 ;;
  esac
  return 1
}

is_remote_copy_to_runtime() {
  local cmd="$1" seg dest path any=0
  local copy1 copy2
  copy1="sc""p"
  copy2="rsy""nc"
  while IFS= read -r seg; do
    printf '%s' "$seg" | grep -qE '(^|[[:space:]])('"$copy1"'|'"$copy2"')([[:space:]]|$)' || continue
    any=1
    dest="$(printf '%s\n' "$seg" | awk -v a="$copy1" -v b="$copy2" '
      {
        seen=0; skip=0; dest=""
        for (i = 1; i <= NF; i++) {
          base=$i; sub(/.*\//, "", base)
          if (!seen) { if (base==a || base==b) seen=1; continue }
          if (skip) { skip=0; continue }
          if ($i ~ /^-/ && $i != "-" && $i != "--") {
            if ($i ~ /^(-e|-P|-o|-c|-i|-l|--rsh|--port)$/) skip=1
            continue
          }
          dest=$i
        }
        print dest
      }')"
    dest="${dest#\'}"; dest="${dest%\'}"; dest="${dest#\"}"; dest="${dest%\"}"
    [ -n "$dest" ] || return 0
    path="${dest##*:}"
    is_runtime_dest "$path" && return 0
  done < <(printf '%s\n' "$cmd" | tr ';&|' '\n')
  [ "$any" = 1 ] && return 1
  return 0
}
