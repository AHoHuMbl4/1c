#!/bin/bash
# Статус такта в search_quality — одна строка k=tick_status (PLAN_WIKI_CHOICE §7).
#
# Схема search_quality (corpus_init.sql): k VARCHAR, v BIGINT, note VARCHAR.
# Три отдельных ключа (tick_last_ok / tick_last_fail / tick_fail_reason) дублировали
# бы паттерн build_* и размазали чтение; одна строка: v = epoch последнего УСПЕХА,
# note = машинный хвост «fail=<epoch>|reason=<step>:<category>» без текстов базы.
# После ok reason очищается, fail= сохраняет последний провал для истории.
# Доки: SQL › Statements › INSERT; SQL › Statements › DELETE.

tick_status_dsn() {
  printf '%s' "${SERENEDB_DSN:-${DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}}"
}

_tick_status_esc() {
  printf '%s' "${1:-}" | sed "s/'/''/g"
}

_tick_status_parse_note() {
  _TS_FAIL=0
  _TS_REASON=
  case "${1:-}" in
    *fail=*|*reason=*)
      _TS_FAIL=$(printf '%s' "$1" | sed -n 's/.*fail=\([0-9][0-9]*\).*/\1/p')
      _TS_REASON=$(printf '%s' "$1" | sed -n 's/.*reason=\([^|]*\).*/\1/p')
      ;;
  esac
  [ -n "$_TS_FAIL" ] || _TS_FAIL=0
}

_tick_status_read() {
  _TS_OK=0
  _TS_NOTE=
  _TS_ROW=$(psql "$(tick_status_dsn)" -tA -c \
    "SELECT coalesce(v,0)::TEXT || '|' || coalesce(note,'') FROM search_quality WHERE k='tick_status'" \
    2>/dev/null | head -1) || _TS_ROW=
  if [ -n "$_TS_ROW" ]; then
    _TS_OK="${_TS_ROW%%|*}"
    _TS_NOTE="${_TS_ROW#*|}"
  fi
  _tick_status_parse_note "$_TS_NOTE"
}

_tick_status_write() {
  local ok="$1" note="$2"
  local en
  en=$(_tick_status_esc "$note")
  psql "$(tick_status_dsn)" -q -v ON_ERROR_STOP=1 -c \
    "DELETE FROM search_quality WHERE k = 'tick_status';
     INSERT INTO search_quality VALUES ('tick_status', ${ok}::BIGINT, '${en}');" \
    >/dev/null 2>&1
}

tick_status_ok() {
  _tick_status_read
  local note="fail=${_TS_FAIL}|reason="
  _tick_status_write "$(date +%s)" "$note"
}

tick_status_fail() {
  local step="${1:-pipeline}" cat="${2:-stop}"
  local reason="${step}:${cat}"
  _tick_status_read
  local ts fail_note
  ts=$(date +%s)
  fail_note="fail=${ts}|reason=${reason}"
  _tick_status_write "${_TS_OK:-0}" "$fail_note"
}
