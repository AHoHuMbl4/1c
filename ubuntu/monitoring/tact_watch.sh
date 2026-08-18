#!/bin/bash
# Сторож красного такта: firstbuild/pipeline в failed дольше N минут.
# Зовётся из bot_health_check.sh. Зависимости (systemctl, clock) инъектируются —
# тесты не ходят в живой systemd.
#
# Замер-повод: klient-1 firstbuild «Start request repeated too quickly» 14–17.08,
# никому не сказано. Молчаливый простой = дефект (п. 13 духом).
set -u

TACT_FAIL_MAX_MIN="${TACT_FAIL_MAX_MIN:-15}"

# Имена юнитов, чей failed виден владельцу. Шаблон — любая база, не список «наших».
tact_watch_unit_globs() {
  printf '%s\n' '1c-serene-pipeline@*.service' '1c-serene-firstbuild@*.service' \
                '1c-serene-onboard@*.service' '1c-serene-pipeline.service'
}

# Список failed-юнитов (один на строку). Подмена: TACT_WATCH_FAILED_LIST.
tact_watch_list_failed() {
  if [ -n "${TACT_WATCH_FAILED_LIST:-}" ]; then
    printf '%s\n' "$TACT_WATCH_FAILED_LIST"
    return 0
  fi
  local g
  while IFS= read -r g; do
    [ -z "$g" ] && continue
    systemctl list-units --state=failed --no-legend --no-pager "$g" 2>/dev/null \
      | awk '{ print $1 }'
  done <<< "$(tact_watch_unit_globs)"
}

# Epoch входа в failed. Подмена: TACT_WATCH_FAILED_SINCE='unit=epoch unit2=epoch'
tact_watch_failed_since_epoch() {
  local unit="$1" pair name ts
  if [ -n "${TACT_WATCH_FAILED_SINCE:-}" ]; then
    for pair in $TACT_WATCH_FAILED_SINCE; do
      name="${pair%%=*}"
      ts="${pair#*=}"
      if [ "$name" = "$unit" ]; then
        printf '%s\n' "$ts"
        return 0
      fi
    done
  fi
  ts="$(systemctl show -p InactiveEnterTimestamp --value "$unit" 2>/dev/null || true)"
  if [ -z "$ts" ] || [ "$ts" = "n/a" ] || [ "$ts" = "0" ]; then
    printf '%s\n' "$(tact_watch_now_epoch)"
    return 0
  fi
  date -d "$ts" +%s 2>/dev/null || tact_watch_now_epoch
}

tact_watch_now_epoch() {
  if [ -n "${TACT_WATCH_NOW:-}" ]; then
    printf '%s\n' "$TACT_WATCH_NOW"
    return 0
  fi
  date +%s
}

# Печатает токены «такт:имя:Nмин» через пробел, если failed дольше порога.
tact_watch_tokens() {
  local unit since now age max_min tokens=""
  max_min="${TACT_FAIL_MAX_MIN:-15}"
  case "$max_min" in *[!0-9]*) max_min=15 ;; esac
  [ "$max_min" -gt 0 ] || return 0
  now="$(tact_watch_now_epoch)"
  while IFS= read -r unit; do
    [ -z "$unit" ] && continue
    since="$(tact_watch_failed_since_epoch "$unit")"
    age=$(( (now - since) / 60 ))
    [ "$age" -lt 0 ] && age=0
    if [ "$age" -ge "$max_min" ]; then
      tokens="$tokens такт:${unit%.service}:${age}мин"
    fi
  done <<< "$(tact_watch_list_failed | sort -u)"
  printf '%s\n' "${tokens# }"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  tact_watch_tokens
fi
