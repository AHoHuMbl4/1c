#!/bin/bash
# ЖЕЛЕЗО → КОНФИГ движка для первой сборки и онбординга (E4 / TARGET п. 9, 14).
#
# Формулы — из замеров 17–18.08 и штатного умолчания движка (80 % RAM), не из имён баз:
#   * 8 vCPU / 11.7 GiB: cpu_threads=160 → shutdown; threads=4 живы; pin-block при
#     memory_limit=9.3 GiB (80 %); SEGV при 16GB; сборка источников при 18GB + swap 12–20G
#     (CHANGELOG 17.08). Пик RSS p_doc 11.09 GiB при 4 потоках.
#   * ≤8 GiB / 4 vCPU: cpu_threads=4, memory_limit 6500MB, swap 4G (okna, RUNBOOK §10.1).
#   * Доки: Configuration › Pragmas › Memory Limit / Threads;
#     Cookbook › Performance › Out-of-Memory Issues (default 80 %, threads↓,
#     preserve_insertion_order=false; операции в обход buffer manager).
#
# Логика НЕ читает /proc: только box_tune_plan <ram_kb> <vcpu>.
# Чтение железа — отдельные функции (подмена в тестах через BOX_TUNE_RAM_KB / BOX_TUNE_VCPU).
#
# Использование:
#   . box_tune.sh
#   box_tune_plan "$ram_kb" "$vcpu"          # печатает key=value
#   embed_host_form_check "$EMBED_HOST"      # 0 — схема+хост+порт
#   box_tune_apply_first_build               # conf + swap + env + SET (идемпотентно)
#   box_tune_restore                         # memory_limit и swap после первой сборки
set -u

# Порог «малая коробка»: пик p_doc 11.09 GiB; ниже 16 GiB первая сборка упирается в RAM,
# а не в сеть эмбеддера. Это порог железа, не таблицы «под нашу базу».
BOX_TUNE_SMALL_RAM_KIB="${BOX_TUNE_SMALL_RAM_KIB:-$((16 * 1024 * 1024))}"
BOX_TUNE_EMBED_WORKERS="${BUILD_EMBED_WORKERS:-8}"

# --- чтение железа (инъекция: BOX_TUNE_RAM_KB / BOX_TUNE_VCPU) -----------------

box_tune_read_ram_kb() {
  if [ -n "${BOX_TUNE_RAM_KB:-}" ]; then
    printf '%s\n' "$BOX_TUNE_RAM_KB"
    return 0
  fi
  awk '/^MemTotal:/ { print $2; exit }' /proc/meminfo
}

box_tune_read_vcpu() {
  if [ -n "${BOX_TUNE_VCPU:-}" ]; then
    printf '%s\n' "$BOX_TUNE_VCPU"
    return 0
  fi
  nproc
}

# --- чистая формула ------------------------------------------------------------

box_tune_plan() {
  local ram_kb="${1:-}" vcpu="${2:-}"
  local swap_gib cpu_threads io_threads thread_min
  local limit_first limit_steady phase workers
  case "$ram_kb" in
    ''|*[!0-9]*) echo "box_tune_plan: ram_kb должен быть целым КиБ, получено «$ram_kb»" >&2; return 2 ;;
  esac
  case "$vcpu" in
    ''|*[!0-9]*) echo "box_tune_plan: vcpu должен быть целым, получено «$vcpu»" >&2; return 2 ;;
  esac
  [ "$ram_kb" -ge 100000 ] || { echo "box_tune_plan: ram_kb=$ram_kb слишком мало" >&2; return 2; }
  [ "$vcpu" -ge 1 ] || { echo "box_tune_plan: vcpu=$vcpu" >&2; return 2; }

  workers="${BOX_TUNE_EMBED_WORKERS:-8}"
  case "$workers" in *[!0-9]*) workers=8 ;; esac

  if [ "$ram_kb" -le "$BOX_TUNE_SMALL_RAM_KIB" ]; then
    # Малая коробка: p_doc держит ~2.5–2.8 ГиБ на поток (11.09 ГиБ / 4).
    # Потолок 4 — оба замера ночи (4 vCPU и 8 vCPU) собрались на четырёх.
    # 160 потоков на 11.7 GiB убили движок (CHANGELOG 17.08).
    phase=small
    cpu_threads=$vcpu
    [ "$cpu_threads" -gt 4 ] && cpu_threads=4
    [ "$cpu_threads" -lt 1 ] && cpu_threads=1
    io_threads=$cpu_threads
    thread_min=$cpu_threads
    # Swap ≥4 ГиБ и не меньше ceil(RAM) — klient-1 начал с 12G на 11.7 GiB;
    # 4G на ~7.6 GiB у okna заняты на 1.8G. ceil(7.6)=8 — запас, не таблица баз.
    swap_gib=$(( (ram_kb + 1024*1024 - 1) / (1024*1024) ))
    [ "$swap_gib" -lt 4 ] && swap_gib=4
    # memory_limit первой сборки: 1.5×RAM (18GB / 11.7 GiB ≈ 1.54), целое ГиБ вверх.
    # Верх — RAM+swap (лимит не может опереться на несуществующую виртуальность).
    limit_first=$(( (ram_kb * 3 + 2*1024*1024 - 1) / (2 * 1024 * 1024) ))
    [ "$limit_first" -lt 1 ] && limit_first=1
    if [ "$limit_first" -gt $(( ram_kb/(1024*1024) + swap_gib )) ]; then
      limit_first=$(( ram_kb/(1024*1024) + swap_gib ))
    fi
    limit_first="${limit_first}GB"
  else
    # Много RAM: пул под сеть эмбеддера (PLAN_AUTONOMY, замер 29.07: 96 на ~62 ГиБ).
    # cpu_threads ≈ 1.5×RAM_GiB, зажат в [max(vcpu, workers+8), 96] — не 160.
    phase=large
    cpu_threads=$(( (ram_kb * 3 + 2*1024*1024 - 1) / (2 * 1024 * 1024) ))
    [ "$cpu_threads" -lt 16 ] && cpu_threads=16
    [ "$cpu_threads" -gt 96 ] && cpu_threads=96
    [ "$cpu_threads" -lt "$vcpu" ] && cpu_threads=$vcpu
    thread_min=$((workers + 8))
    [ "$cpu_threads" -lt "$thread_min" ] && cpu_threads=$thread_min
    io_threads=8
    [ "$io_threads" -gt "$cpu_threads" ] && io_threads=$cpu_threads
    swap_gib=0
    limit_first=""
  fi

  # Штатное умолчание движка — 80 % RAM (Cookbook › OOM; SHOW 9.3 GiB на 11.7).
  # Возврат после первой сборки: PLAN_KEY_DEDUP_RECOVERY §0.
  limit_steady=$(( ram_kb * 8 / 10 / 1024 ))
  limit_steady="${limit_steady}MB"
  [ -n "$limit_first" ] || limit_first="$limit_steady"

  printf 'ram_kb=%s\n' "$ram_kb"
  printf 'vcpu=%s\n' "$vcpu"
  printf 'phase_class=%s\n' "$phase"
  printf 'cpu_threads=%s\n' "$cpu_threads"
  printf 'io_threads=%s\n' "$io_threads"
  printf 'thread_min=%s\n' "$thread_min"
  printf 'swap_gib=%s\n' "$swap_gib"
  printf 'memory_limit_first=%s\n' "$limit_first"
  printf 'memory_limit_steady=%s\n' "$limit_steady"
  printf 'preserve_insertion_order=false\n'
}

box_tune_plan_field() {
  local k="$1"
  box_tune_plan "$2" "$3" | awk -F= -v k="$k" '$1==k { print substr($0, index($0, "=")+1); exit }'
}

# --- форма EMBED_HOST (замер 17.08: голый хост → curl код 000) -----------------

embed_host_form_check() {
  local h="${1:-}" stripped port
  if [ -z "$h" ]; then
    echo "EMBED_HOST пуст: нужна схема http(s)://, хост и порт (замер 17.08: голый хост → код 000)." >&2
    return 1
  fi
  stripped="${h%/}"
  case "$stripped" in
    http://*|https://*) ;;
    *)
      echo "EMBED_HOST «$h»: нет схемы http:// или https:// (замер 17.08, дверь движка код 000)." >&2
      return 1 ;;
  esac
  if [[ ! "$stripped" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]{1,5})(/.*)?$ ]]; then
    echo "EMBED_HOST «$h»: нужны хост и явный порт (пример http://embed.example:8000)." >&2
    return 1
  fi
  port="${stripped#http://}"
  port="${port#https://}"
  port="${port#*:}"
  port="${port%%/*}"
  case "$port" in
    ''|*[!0-9]*) echo "EMBED_HOST «$h»: порт не разобран." >&2; return 1 ;;
  esac
  if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
    echo "EMBED_HOST «$h»: порт $port вне 1–65535." >&2
    return 1
  fi
  return 0
}

embed_hosts_form_check() {
  local raw="${EMBED_HOSTS:-${EMBED_HOST:-}}" one host
  if [ -z "$raw" ]; then
    if [ -n "${EMBED_BASE_URL:-}" ]; then
      embed_host_form_check "${EMBED_BASE_URL%/}" || return 1
      return 0
    fi
    echo "не задан EMBED_HOST / EMBED_HOSTS" >&2
    return 1
  fi
  IFS=',' read -r -a _eh <<< "$raw"
  for one in "${_eh[@]}"; do
    one="$(printf '%s' "$one" | tr -d ' ')"
    [ -z "$one" ] && continue
    host="${one%%|*}"
    embed_host_form_check "$host" || return 1
  done
  return 0
}

# --- запись conf / env / swap / pragma ----------------------------------------

box_tune_upsert_flag() {
  # $1 file, $2 flag name without dashes (cpu_threads), $3 value
  local f="$1" name="$2" val="$3" tmp
  [ -f "$f" ] || { echo "box_tune: нет файла conf $f" >&2; return 1; }
  tmp="${f}.box-tune.new"
  awk -v name="$name" -v val="$val" '
    BEGIN { done=0 }
    $0 ~ ("^--" name "=") { print "--" name "=" val; done=1; next }
    { print }
    END { if (!done) print "--" name "=" val }
  ' "$f" > "$tmp" || return 1
  mv -f "$tmp" "$f"
}

box_tune_upsert_env() {
  local f="$1" name="$2" val="$3" tmp
  if [ ! -f "$f" ]; then
    printf '%s=%s\n' "$name" "$val" > "$f"
    return 0
  fi
  tmp="${f}.box-tune.new"
  awk -v name="$name" -v val="$val" '
    BEGIN { done=0 }
    $0 ~ ("^" name "=") { print name "=" val; done=1; next }
    { print }
    END { if (!done) print name "=" val }
  ' "$f" > "$tmp" || return 1
  mv -f "$tmp" "$f"
}

box_tune_ensure_swap() {
  # $1 GiB, $2 path. В тестах BOX_TUNE_SWAP_APPLY=0 — только учесть в плане.
  local gib="$1" path="$2"
  [ "$gib" -gt 0 ] || return 0
  if [ "${BOX_TUNE_SWAP_APPLY:-}" = 0 ]; then
    echo "box_tune: swap ${gib}G $path (без swapon — SWAP_APPLY=0)"
    return 0
  fi
  if [ "$(id -u)" != 0 ]; then
    echo "box_tune: swap ${gib}G требует root, пропускаю $path" >&2
    return 0
  fi
  if [ ! -f "$path" ]; then
    fallocate -l "${gib}G" "$path" 2>/dev/null || dd if=/dev/zero of="$path" bs=1M count=$((gib * 1024)) status=none
    chmod 600 "$path"
    mkswap "$path" >/dev/null
  fi
  swapon "$path" 2>/dev/null || true
  echo "box_tune: swap ${gib}G на $path"
}

box_tune_drop_swap() {
  local path="$1"
  if [ "${BOX_TUNE_SWAP_APPLY:-}" = 0 ]; then
    echo "box_tune: снять swap $path (без swapoff — SWAP_APPLY=0)"
    rm -f "$path"
    return 0
  fi
  if [ "$(id -u)" != 0 ]; then
    echo "box_tune: снять swap требует root, пропускаю $path" >&2
    return 0
  fi
  swapoff "$path" 2>/dev/null || true
  rm -f "$path"
  echo "box_tune: swap $path снят"
}

box_tune_restart_engine() {
  if [ "${BOX_TUNE_RESTART:-}" = 0 ]; then
    echo "box_tune: рестарт serenedb пропущен (RESTART=0)"
    return 0
  fi
  if [ "$(id -u)" != 0 ]; then
    echo "box_tune: рестарт serenedb требует root — conf записан, движок подхватит при следующем старте" >&2
    return 0
  fi
  systemctl restart serenedb.service
}

box_tune_sql() {
  local dsn="$1" sql="$2"
  if [ -z "$dsn" ]; then
    echo "box_tune: DSN пуст — SET $sql пропущен"
    return 0
  fi
  if [ "${BOX_TUNE_SQL:-}" = 0 ]; then
    echo "box_tune: SQL пропущен (SQL=0): $sql"
    return 0
  fi
  psql "$dsn" -q -c "$sql"
}

box_tune_state_dir() {
  printf '%s\n' "${BOX_TUNE_STATE:-/var/lib/serenedb/box-tune.state}"
}

box_tune_apply_first_build() {
  local ram_kb vcpu plan conf envf swapf state dsn
  local cpu_threads io_threads thread_min swap_gib limit_first limit_steady
  ram_kb="$(box_tune_read_ram_kb)"
  vcpu="$(box_tune_read_vcpu)"
  plan="$(box_tune_plan "$ram_kb" "$vcpu")" || return $?
  cpu_threads="$(printf '%s\n' "$plan" | awk -F= '$1=="cpu_threads"{print $2}')"
  io_threads="$(printf '%s\n' "$plan" | awk -F= '$1=="io_threads"{print $2}')"
  thread_min="$(printf '%s\n' "$plan" | awk -F= '$1=="thread_min"{print $2}')"
  swap_gib="$(printf '%s\n' "$plan" | awk -F= '$1=="swap_gib"{print $2}')"
  limit_first="$(printf '%s\n' "$plan" | awk -F= '$1=="memory_limit_first"{print $2}')"
  limit_steady="$(printf '%s\n' "$plan" | awk -F= '$1=="memory_limit_steady"{print $2}')"

  conf="${BOX_TUNE_CONF:-/etc/serenedb/serened.conf}"
  envf="${BOX_TUNE_PIPELINE_ENV:-}"
  swapf="${BOX_TUNE_SWAPFILE:-/swapfile-1c-build}"
  state="$(box_tune_state_dir)"
  dsn="${BOX_TUNE_DSN:-${SERENEDB_DSN:-}}"

  if [ -f "$conf" ]; then
    box_tune_upsert_flag "$conf" cpu_threads "$cpu_threads"
    box_tune_upsert_flag "$conf" io_threads "$io_threads"
  else
    echo "box_tune: нет $conf — флаги не записаны (движок ещё не ставили?)" >&2
  fi

  if [ -n "$envf" ]; then
    box_tune_upsert_env "$envf" BUILD_THREAD_MIN "$thread_min"
  fi

  box_tune_ensure_swap "$swap_gib" "$swapf"

  mkdir -p "$(dirname "$state")"
  {
    printf '%s\n' "$plan"
    printf 'phase=first-build\n'
    printf 'swapfile=%s\n' "$swapf"
    printf 'conf=%s\n' "$conf"
  } > "$state"

  box_tune_sql "$dsn" "SET memory_limit = '${limit_first}';"
  box_tune_sql "$dsn" "SET preserve_insertion_order = false;"

  if [ "${BOX_TUNE_SKIP_RESTART:-}" != 1 ]; then
    box_tune_restart_engine
  fi
  echo "box_tune: первая сборка cpu_threads=$cpu_threads io_threads=$io_threads memory_limit=$limit_first swap=${swap_gib}G thread_min=$thread_min (возврат $limit_steady)"
}

box_tune_restore() {
  # После успешной первой сборки: memory_limit → 80 % RAM, swap снять.
  # cpu_threads НЕ возвращаем к 160 — на малой коробке 4 потока и есть рабочий режим.
  local state ram_kb vcpu plan limit_steady swapf dsn
  state="$(box_tune_state_dir)"
  [ -f "$state" ] || { echo "box_tune: нет штампа $state — восстанавливать нечего"; return 0; }
  ram_kb="$(awk -F= '$1=="ram_kb"{print $2}' "$state")"
  vcpu="$(awk -F= '$1=="vcpu"{print $2}' "$state")"
  [ -n "$ram_kb" ] || ram_kb="$(box_tune_read_ram_kb)"
  [ -n "$vcpu" ] || vcpu="$(box_tune_read_vcpu)"
  plan="$(box_tune_plan "$ram_kb" "$vcpu")" || return $?
  limit_steady="$(printf '%s\n' "$plan" | awk -F= '$1=="memory_limit_steady"{print $2}')"
  swapf="$(awk -F= '$1=="swapfile"{print $2}' "$state")"
  [ -n "$swapf" ] || swapf="${BOX_TUNE_SWAPFILE:-/swapfile-1c-build}"
  dsn="${BOX_TUNE_DSN:-${SERENEDB_DSN:-}}"

  box_tune_sql "$dsn" "SET memory_limit = '${limit_steady}';"
  box_tune_drop_swap "$swapf"
  {
    printf '%s\n' "$plan"
    printf 'phase=restored\n'
  } > "$state"
  echo "box_tune: возврат после первой сборки memory_limit=$limit_steady swap снят"
}

# Точка входа, когда файл зовут как команду (не source).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  cmd="${1:-plan}"
  shift || true
  case "$cmd" in
    plan)
      box_tune_plan "$(box_tune_read_ram_kb)" "$(box_tune_read_vcpu)"
      ;;
    apply|first-build)
      box_tune_apply_first_build
      ;;
    restore)
      box_tune_restore
      ;;
    embed-form)
      embed_hosts_form_check
      ;;
    *)
      echo "использование: box_tune.sh plan|apply|restore|embed-form" >&2
      exit 2
      ;;
  esac
fi
