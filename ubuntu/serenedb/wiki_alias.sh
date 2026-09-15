#!/bin/bash
# ЧЕЛОВЕЧЕСКИЕ СЛОВА К СУЩНОСТИ — ШТАТНЫМ АГЕНТОМ OPENCLAW.
#
# 🔴 ПОЧЕМУ АГЕНТОМ, А НЕ СВОИМ ВЫЗОВОМ МОДЕЛИ. Указание владельца 30.07: «используй механизмы
# openclaw». `openclaw agent` — штатный неинтерактивный прогон через шлюз: модель, ключ, профиль
# аутентификации и учёт берутся из его конфигурации, а не задаются мной второй раз.
#
# 🔴 ЗАЧЕМ ЭТО НУЖНО. [замер 30.07] из 11 провалов приёмки 8-10 — выбрана НЕ ТА сущность. Модель
# посильнее (`v4 pro`) не помогла: плохих исходов 11 против 11. Дело не в силе рассуждения — из
# названия неоткуда узнать, что «Отчёт о розничных продажах» это розница, а не опт. Спрошенное
# один раз кладётся в базу и служит основой (вики) на каждом вопросе.
#
# 🔴 УНИВЕРСАЛЬНОСТЬ. В скрипте нет ни одного имени сущности и ни одного слова конкретной базы.
# Модели уходят ТОЛЬКО названия и имена величин из данных, а отвечать её просят «на том же языке,
# что название» — поэтому на английской базе выйдут английские слова без всякой правки кода.
# Значений данных не уходит: ни сумм, ни счётов (п. 19).
#
# Идемпотентно: спрашиваются только сущности, которых ещё нет в словаре.
# Использование: wiki_alias.sh [сущностей за прогон]   (0 или пусто = все оставшиеся)
set -u
# Одноразовый замер infer (work/acceptance/measure_wiki_alias_infer.sh): WIKI_ALIAS_MEASURE=1
if [ "${WIKI_ALIAS_MEASURE:-0}" = "1" ]; then
  exec bash "$(cd "$(dirname "$0")/../.." && pwd)/work/acceptance/measure_wiki_alias_infer.sh"
fi
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
BOTUSER="${OPENCLAW_USER:-undebot}"
# 🔴 КАК ЗАПУСКАТЬ ОТ ИМЕНИ БОТА — РЕШАЕТСЯ ПО ОКРУЖЕНИЮ, А НЕ ЗАШИТО В `sudo`. Профиль,
# ключ модели и токен шлюза лежат у пользователя бота (0600), поэтому `openclaw agent`
# запускается от него. Но `sudo` доступен не везде: рабочей сессии его закрывает среда, и
# прогон упирался в просьбу к владельцу «наберите, пожалуйста». Способ выбирается сам:
# уже бот — зовём напрямую, есть права администратора — `runuser`, иначе прежний `sudo`.
if [ -n "${OPENCLAW_RUNAS:-}" ]; then
  read -r -a RUNAS_BOT <<< "$OPENCLAW_RUNAS"
elif [ "$(id -un)" = "$BOTUSER" ]; then
  RUNAS_BOT=()
elif [ "$(id -u)" = 0 ] && command -v runuser >/dev/null 2>&1; then
  RUNAS_BOT=(runuser -u "$BOTUSER" --)
else
  RUNAS_BOT=(sudo -u "$BOTUSER" -H)
fi
# [замер 14.09] BATCH=1: на пачках >1 модель роняет event-квоту (глаголы выжигаются
# баном «подходит соседу»), на длинных пайлоадах иногда отдаёт пустой ответ; при 1
# размер пайлоада привязан только к самой записи — устойчиво на любой базе (п.0).
BATCH="${WIKI_ALIAS_BATCH:-1}"
# 🔴 ПУСТАЯ ЗАПИСЬ — ЭТО ПОПЫТКА, А НЕ ОТВЕТ. Осечка пачки помечает её сущности пустыми
# строками, чтобы проход не ходил по кругу; но отбор пропускал их по одному факту наличия
# записи, и сущность выбывала из словаря НАВСЕГДА. Живой случай okna 13.08: 140 записей из
# 254 пустые (следствие дефекта прав на файле обмена), среди них обе «Реализация ТМЦ», —
# то есть ровно те, чьё описание разводит одноимённые источники. Теперь пустая запись
# переспрашивается, но не чаще этого срока: модель не жжётся на сущностях, которые она
# и правда не может описать.
RETRY_H="${WIKI_ALIAS_RETRY_H:-6}"
case "$RETRY_H" in ''|*[!0-9]*) RETRY_H=6;; esac
# Развести конкретное слово, а не самое спорное: путь «сначала прогон, потом точечная правка».
# Одинарные кавычки удваиваются сразу: слово приходит извне (переменная окружения), и в
# запрос оно подставляется текстом — без этого апостроф в слове ломал бы запрос.
TARGET_WORD="${WIKI_ALIAS_WORD:-}"; TARGET_WORD=${TARGET_WORD//\'/\'\'}
# 🔴 КУДА ПИСАТЬ СЛОВАРЬ. Умолчание — боевая таблица, как было. Своё имя (`ALIAS_TABLE`)
# нужно затем, чтобы новую редакцию словаря можно было собрать РЯДОМ и сравнить прибором
# `work/entity-choice/alias_rank_bench.py`, не трогая тот словарь, по которому сейчас
# отвечает бот. Иначе всякая проба словаря — это правка боевого поведения вслепую.
ALIAS_TABLE="${ALIAS_TABLE:-search_entity_alias}"
# Словарь величин — отдельная таблица: связь поле → слова. Имя настраивается той же
# ручкой, что и у сущностей, чтобы прогон рядом не трогал боевой словарь.
MEASURE_TABLE="${MEASURE_TABLE:-search_measure_alias}"
# Память «слово уже разводили» (collision). Песочница задаёт свою — иначе пометки
# уйдут в боевую probe и следующий боевой круг молча пропустит эти слова (п.13).
PROBE_TABLE="${PROBE_TABLE:-search_alias_probe}"
# Периодическое доучивание (С5-пайплайн): 0 = выкл (боевые базы не меняются молча).
REASK_EVERY="${WIKI_ALIAS_REASK_EVERY:-0}"
case "$REASK_EVERY" in ''|*[!0-9]*) REASK_EVERY=0;; esac
REASK_STALE_DAYS="${WIKI_ALIAS_REASK_STALE_DAYS:-30}"
case "$REASK_STALE_DAYS" in ''|*[!0-9]*) REASK_STALE_DAYS=30;; esac
WIKI_ALIAS_TICK="${WIKI_ALIAS_TICK:-0}"
case "$WIKI_ALIAS_TICK" in ''|*[!0-9]*) WIKI_ALIAS_TICK=0;; esac
# tick = обычный такт (умолч.); cycle = разовый полный пересбор (plan-cycle-mode.md).
# Cycle не пишется в постоянный env юнита — только явный запуск (red9b-1).
WIKI_ALIAS_MODE="${WIKI_ALIAS_MODE:-tick}"
case "$WIKI_ALIAS_MODE" in tick|cycle) ;; *)
  echo "алиасы: WIKI_ALIAS_MODE=$WIKI_ALIAS_MODE — ожидается tick|cycle" >&2
  exit 1
  ;;
esac
# Прогресс-репорт и стоп-при-тишине (plan-progress-stall.md). 0 = выкл.
# STALL умолч. 8100 = 1.5 × (retry+1) × ALIAS_AGENT_TIMEOUT_SEC
# (retry шлюза = 2 → до 3 subprocess × 1800 = 5400; ×1.5 = 8100).
# Иначе ложный TERM на внутренних ретраях шлюза и на длинных одиночных
# psql (VACUUM / promote), где .progress_* не обновляется минутами.
WIKI_ALIAS_REPORT_EVERY_SEC="${WIKI_ALIAS_REPORT_EVERY_SEC:-300}"
WIKI_ALIAS_STALL_SEC="${WIKI_ALIAS_STALL_SEC:-8100}"
WIKI_ALIAS_POLL_SEC="${WIKI_ALIAS_POLL_SEC:-10}"
# Пауза между TERM и KILL -9 группе/дереву главного при стоп-при-тишине.
WIKI_ALIAS_KILL_GRACE_SEC="${WIKI_ALIAS_KILL_GRACE_SEC:-15}"
case "$WIKI_ALIAS_REPORT_EVERY_SEC" in ''|*[!0-9]*) WIKI_ALIAS_REPORT_EVERY_SEC=300;; esac
case "$WIKI_ALIAS_STALL_SEC" in ''|*[!0-9]*) WIKI_ALIAS_STALL_SEC=8100;; esac
case "$WIKI_ALIAS_POLL_SEC" in ''|*[!0-9]*) WIKI_ALIAS_POLL_SEC=10;; esac
case "$WIKI_ALIAS_KILL_GRACE_SEC" in ''|*[!0-9]*) WIKI_ALIAS_KILL_GRACE_SEC=15;; esac
# POLL=0 при живом REPORT/STALL → 10 (иначе цикл проверки не крутится).
if [ "$WIKI_ALIAS_POLL_SEC" -eq 0 ] \
   && { [ "$WIKI_ALIAS_REPORT_EVERY_SEC" -gt 0 ] || [ "$WIKI_ALIAS_STALL_SEC" -gt 0 ]; }; then
  WIKI_ALIAS_POLL_SEC=10
fi
# 🔴 [замер 14.09] COLL_BATCH — размер пачки collision/reask. Эти пачки — ГРУППЫ
# записей (общее слово / перевопрос уточнений), к «1 задача = 1 вызов» первого
# прохода отношения не имеют: при BATCH=1 группа из одной записи ломает разведение
# (модель не видит сестёр) и перевопрос. Свой размер, исторический дефолт 8.
COLL_BATCH="${WIKI_ALIAS_COLLISION_BATCH:-8}"
case "$COLL_BATCH" in ''|*[!0-9]*) COLL_BATCH=8;; esac
[ "$COLL_BATCH" -lt 1 ] && COLL_BATCH=1
REASK_CAP="${WIKI_ALIAS_REASK_CAP:-$COLL_BATCH}"
case "$REASK_CAP" in ''|*[!0-9]*) REASK_CAP="$COLL_BATCH";; esac
CAP="${1:-0}"
# Модель/thinking — вызов через alias_infer_gateway.py (рантайм agent/infer).
# 🔴 Транспорт: умолчание --local (cli/infer.md). [замер 24.08] --gateway =
# RPC-потолок 120 с → GatewayTransportError; loc 1034 с / пачка 20 — exit 0.
# Умолчание модели — OpenRouter qwen/qwen3.8-27b (провайдер vllm в конфиге HOME
# смотрит на openrouter.ai); своя GPU vLLM — через WIKI_ALIAS_MODEL.
WIKI_ALIAS_MODEL="${WIKI_ALIAS_MODEL:-vllm/qwen/qwen3.8-27b}"
WIKI_ALIAS_THINKING="${WIKI_ALIAS_THINKING:-off}"
# Force-перегенерация непустых aliases (песочница; штатный путь без флага = 0).
WIKI_ALIAS_FORCE="${WIKI_ALIAS_FORCE:-0}"
case "$WIKI_ALIAS_FORCE" in 1) WIKI_ALIAS_FORCE=1;; *) WIKI_ALIAS_FORCE=0;; esac
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"

# ── версия генератора для самоочистки probe (plan-probe-result.md) ──
# md5(скрипт + модель + thinking): смена кода/промтов/модели = новая версия.
# Пустой/битый md5 → ABORT (fail-closed: без версии чистку не делаем).
GEN_VER=$(
  { cat "$HERE/wiki_alias.sh"; printf '%s%s' "$WIKI_ALIAS_MODEL" "$WIKI_ALIAS_THINKING"; } \
    | md5sum 2>/dev/null | awk '{print $1}'
)
case "$GEN_VER" in
  ''|*[!0-9a-fA-F]*)
    echo "алиасы: GEN_VER пуст/битый — ABORT (fail-closed)" >&2
    exit 1
    ;;
esac

# Общие psql-параметры: таблицы и retry — один -f вместо веера -c (п. 20, Э1а).
psql_wa() {
  psql "$DSN" -q -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v probe_table="$PROBE_TABLE" \
    -v retry_h="$RETRY_H" \
    -v force="$WIKI_ALIAS_FORCE" \
    "$@"
}
psql_wa_tA() {
  psql "$DSN" -tA -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v probe_table="$PROBE_TABLE" \
    -v retry_h="$RETRY_H" \
    -v force="$WIKI_ALIAS_FORCE" \
    "$@"
}
DB_TAG=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DB_TAG" ] || DB_TAG="db"
REASK_TABLE="${WIKI_ALIAS_REASK_TABLE:-alias_${DB_TAG}_reask}"
CONFIRM_TABLE="${WIKI_ALIAS_CONFIRM_TABLE:-alias_${DB_TAG}_reask_confirm}"
JOURNAL_TABLE="${WIKI_ALIAS_JOURNAL_TABLE:-alias_${DB_TAG}_reask_journal}"

bash "$(cd "$(dirname "$0")/.." && pwd)/openclaw/ensure_vllm_gateway.sh" || echo "алиасы: ensure_vllm — предупреждение" >&2

command -v openclaw >/dev/null 2>&1 || { echo "алиасы: openclaw не установлен — шаг пропущен"; exit 0; }
# 🔴 ОБМЕН ФАЙЛАМИ — ТОЛЬКО ЧЕРЕЗ КАТАЛОГ, ЧИТАЕМЫЙ ДВИЖКОМ. [замер 30.07] `read_json` из
# `/tmp/...` даёт «No files found»: процесс `serened` этот путь не видит. Тот же каталог, что у
# загрузчика (`CSV_DIR`, по умолчанию `/var/lib/serenedb`).
EXCH="${CSV_DIR:-/var/lib/serenedb}"
TMP=$(mktemp -d "$EXCH/wiki-alias-XXXXXX") || { echo "алиасы: нет доступа к $EXCH" >&2; exit 0; }
chmod 755 "$TMP"
# 🔴 КАТАЛОГ ПИШЕТ БОТ, А СОЗДАЁТСЯ ОТ ROOT. [okna 27.08] alias_infer_gateway идёт
# под undebot (RUNAS_BOT), а mktemp рождает каталог root:root 755 — бот не может
# записать ans/err, каждая пачка падает PermissionError и помечает сущности пустыми.
# Владелец меняется при запуске от root; запуск от самого бота не трогается.
[ "$(id -u)" = 0 ] && chown "$BOTUSER" "$TMP" 2>/dev/null || true
done_total=0
skipped=0

# 🔴 БЮДЖЕТ ВРЕМЕНИ, А НЕ ЧИСЛО КРУГОВ. Шаг идёт в такте свежести, а такт обязан
# укладываться в 20 минут (п. 17 TARGET.md). Число кругов этого не держит: круг — это вызов
# модели, и его цена зависит от того, как модель отвечает сегодня. [замер 05.08] 40 кругов
# на боевой базе — час, то есть предел «40» молча означал «час», и п. 17 не выполнялся.
# Бюджет измеряет то, что и ограничено контрактом, — ВРЕМЯ. Не успевшее за бюджет никуда
# не девается: работа идёт следующим тактом с того же места (оба прохода идемпотентны).
BUDGET="${WIKI_ALIAS_MAX_SEC:-120}"  # 0 = без потолка (over_budget)
t_start=$(date +%s)

# ── прогресс / стоп-при-тишине (plan-progress-stall.md) ──
# Одна строка unixts<TAB>счётчик<TAB>метка; атомарно >tmp && mv. Дешёво, не в цикле psql.
wa_progress_write() {
  local f="$1" c="${2:-0}" lab="${3:-.}" now
  [ -n "${f:-}" ] || return 0
  now=$(date +%s)
  printf '%s\t%s\t%s\n' "$now" "$c" "$lab" > "${f}.tmp" && mv -f "${f}.tmp" "$f"
}
wa_progress_scan() {
  # выставляет _pg_max_ts / _pg_last_lab / _pg_files (seed = t_start).
  local f ts _c lab
  _pg_max_ts=$t_start
  _pg_last_lab="(seed)"
  _pg_files=""
  for f in "$TMP"/.progress_*; do
    [ -f "$f" ] || continue
    case "$f" in *.tmp) continue;; esac
    IFS=$'\t' read -r ts _c lab < "$f" || continue
    case "$ts" in ''|*[!0-9]*) continue;; esac
    _pg_files="${_pg_files:+$_pg_files,}${f##*/}"
    if [ "$ts" -ge "$_pg_max_ts" ]; then
      _pg_max_ts=$ts
      _pg_last_lab="${lab:-?}"
    fi
  done
}
wa_progress_report() {
  local kind="${1:-}" now elapsed left age cleft
  now=$(date +%s)
  elapsed=$((now - t_start))
  if [ "$BUDGET" = "0" ]; then
    left=inf
  else
    left=$((BUDGET - elapsed))
    [ "$left" -lt 0 ] && left=0
  fi
  wa_progress_scan
  age=$((now - _pg_max_ts))
  cleft=$(cat "$TMP/.collision_left_echo" 2>/dev/null || true)
  echo "прогресс${kind:+ ($kind)}: elapsed=${elapsed}s budget_left=${left}s last=${_pg_last_lab} age=${age}s files=${_pg_files:-none}${cleft:+ collision_left=$cleft}" >&2
}
_PROGRESS_OBS_PID=""
_wiki_alias_on_exit() {
  if [ -n "${_PROGRESS_OBS_PID:-}" ]; then
    kill "$_PROGRESS_OBS_PID" 2>/dev/null || true
    wait "$_PROGRESS_OBS_PID" 2>/dev/null || true
    _PROGRESS_OBS_PID=""
  fi
  if [ "${WIKI_ALIAS_REPORT_EVERY_SEC:-0}" -gt 0 ]; then
    # Без 2>/dev/null: wa_progress_report пишет в stderr — подавление глотало бы финал.
    wa_progress_report "финал" || true
  fi
  rm -rf "$TMP"
}
# Наблюдатель — tick и cycle; seed max_ts=t_start (нет файлов ≠ эпоха 0).
if [ "$WIKI_ALIAS_REPORT_EVERY_SEC" -gt 0 ] || [ "$WIKI_ALIAS_STALL_SEC" -gt 0 ]; then
  (
    last_rep=0
    if [ "$WIKI_ALIAS_REPORT_EVERY_SEC" -gt 0 ]; then
      wa_progress_report "старт"
      last_rep=$(date +%s)
    fi
    while :; do
      sleep "$WIKI_ALIAS_POLL_SEC"
      now=$(date +%s)
      wa_progress_scan
      max_ts=$_pg_max_ts
      [ "$max_ts" -lt "$t_start" ] && max_ts=$t_start
      if [ "$WIKI_ALIAS_STALL_SEC" -gt 0 ]; then
        silent=$((now - max_ts))
        if [ "$silent" -gt "$WIKI_ALIAS_STALL_SEC" ]; then
          # bash откладывает TERM главному, пока оно в wait форграунд-psql
          # ([замер] одиночный TERM → стоп только после возврата ребёнка).
          # Путь: setsid-киллер (свой session → не гибнет от группового TERM).
          # Главное = $$ (не $PPID): в bash-( ) субшелле $$ = PID главного
          # скрипта, а PPID = родитель главного (systemd/shell) — убивать его
          # нельзя и бессмысленно.
          # [замер] setsid/systemd: PGID==PID главного (лидер группы) →
          #   kill -TERM/-KILL -$PGID бьёт всё дерево, включая зависший psql.
          # Чужая группа (ручной запуск в чужой session, PGID≠PID): групповой
          # kill убил бы соседей — тогда TERM/KILL только главному и прямым
          # детям из /proc/$$/task/*/children (без pkill -P).
          _stall_main=$$
          _stall_pgid=$(ps -o pgid= -p "$_stall_main" 2>/dev/null | tr -d '[:space:]')
          case "$_stall_pgid" in ''|*[!0-9]*) _stall_pgid=$_stall_main;; esac
          echo "стоп-при-тишине: ${silent} сек без прогресса (последний: ${_pg_last_lab} возрастом ${silent} с) (TERM группе ${_stall_pgid})" >&2
          setsid bash -c '
            main="$1"; pgid="$2"; grace="$3"
            wa_kill_tree() {
              local sig="$1" c f
              kill -s "$sig" "$main" 2>/dev/null || true
              for f in /proc/"$main"/task/*/children; do
                [ -r "$f" ] || continue
                for c in $(cat "$f"); do
                  case "$c" in ""|*[!0-9]*) continue;; esac
                  kill -s "$sig" "$c" 2>/dev/null || true
                done
              done
            }
            if [ "$pgid" = "$main" ]; then
              kill -TERM -- -"$pgid" 2>/dev/null || true
            else
              wa_kill_tree TERM
            fi
            sleep "$grace"
            if kill -0 "$main" 2>/dev/null; then
              echo "стоп-при-тишине: эскалация (KILL группе ${pgid})" >&2
              if [ "$pgid" = "$main" ]; then
                kill -KILL -- -"$pgid" 2>/dev/null || true
              else
                wa_kill_tree KILL
              fi
            fi
          ' bash "$_stall_main" "$_stall_pgid" "$WIKI_ALIAS_KILL_GRACE_SEC" </dev/null >/dev/null &
          exit 0
        fi
      fi
      if [ "$WIKI_ALIAS_REPORT_EVERY_SEC" -gt 0 ] \
         && [ $((now - last_rep)) -ge "$WIKI_ALIAS_REPORT_EVERY_SEC" ]; then
        wa_progress_report
        last_rep=$now
      fi
    done
  ) &
  _PROGRESS_OBS_PID=$!
fi
trap '_wiki_alias_on_exit' EXIT

# DDL tick — ПОСЛЕ наблюдателя (живая проба: висящий init-DDL ловится stall).
# 🔴 cycle пропускает (red12b-3): DDL в фазе «а» по черновым именам + своя probe.
[ "$WIKI_ALIAS_MODE" != "cycle" ] && wa_progress_write "$TMP/.progress_main" 0 "ddl"
[ "$WIKI_ALIAS_MODE" != "cycle" ] && psql_wa -f "$HERE/wiki_alias_init.sql" >/dev/null 2>&1

over_budget() { [ "$BUDGET" != "0" ] && [ $(( $(date +%s) - t_start )) -ge "$BUDGET" ]; }

# Самоочистка probe: оставить ok-любой и failed-текущей GEN_VER; убрать остальное.
# 🔴 Только по выбранной PROBE_TABLE прогона (tick — env уже финален; cycle — после фазы а).
wa_probe_purge() {
  local out deleted failed_left
  wa_progress_write "$TMP/.progress_main" 0 "probe"
  out=$(psql_wa_tA -v gen_ver="$GEN_VER" -f "$HERE/wiki_alias_probe_purge.sql" 2>/dev/null) || out=""
  deleted=${out%%$'\t'*}
  failed_left=${out#*$'\t'}
  case "$deleted" in ''|*[!0-9]*) deleted="?";; esac
  case "$failed_left" in ''|*[!0-9]*) failed_left="?";; esac
  echo "probe-чистка: удалено $deleted осталось failed $failed_left (gen_ver=$GEN_VER)" >&2
}

# Отчёт качества init (plan-quality-report v2): heartbeat → SQL → одна stderr-строка.
# 🔴 fail-closed: ошибка/пустой вывод — ABORT (init без отчёта неуспешен, п.13).
wa_quality_report() {
  local out err
  wa_progress_write "$TMP/.progress_main" 0 "quality"
  out=$(psql_wa_tA -f "$HERE/wiki_alias_quality_report.sql" 2>"$TMP/.quality_err") || out=""
  out=$(printf '%s' "$out" | tr -d '\r' | head -n 1)
  if [ -z "$out" ]; then
    err=$(head -c 120 "$TMP/.quality_err" | tr -d '\n')
    echo "отчёт качества init: ABORT (сбой SQL: $err)" >&2
    return 1
  fi
  echo "отчёт качества init: $out" >&2
  return 0
}

# Пометка ok/failed после merge (UPDATE по alias+entities_fp).
wa_probe_mark() {
  local word="$1" fp="$2" result="$3"
  wa_progress_write "$TMP/.progress_main" 0 "probe"
  [ -n "${WA_PROGRESS_FILE:-}" ] && wa_progress_write "$WA_PROGRESS_FILE" 0 "probe"
  psql_wa -v word="$word" -v fp="$fp" -v result="$result" -v gen_ver="$GEN_VER" \
    -f "$HERE/wiki_alias_probe_mark.sql" >/dev/null 2>&1 || \
    echo "разведение: пометка probe не записалась ($word)" >&2
  echo "разведение: слово ${word} → ${result}" >&2
}

# ok = (≥1 объект модели И MERGE затронул ≥1) ИЛИ word+fp исчез из cand (still=0).
# Иначе failed (падение поля, rc0-пустышка, merge no-op без разрешения).
wa_probe_result_for() {
  local wtmp="$1" word fp objs merge_n still result
  word=$(cat "$wtmp/word" 2>/dev/null || true)
  fp=$(cat "$wtmp/fp" 2>/dev/null || true)
  result=failed
  objs=0
  merge_n=0
  if [ -s "$wtmp/rows.json" ]; then
    objs=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' \
      "$wtmp/rows.json" 2>/dev/null) || objs=0
    case "$objs" in ''|*[!0-9]*) objs=0;; esac
    if [ "$objs" -ge 1 ]; then
      merge_n=$(psql_wa_tA -v rows_path="$wtmp/rows.json" \
        -f "$HERE/wiki_alias_collision_merge.sql" 2>/dev/null | grep -c . || true)
      case "$merge_n" in ''|*[!0-9]*) merge_n=0;; esac
    fi
  fi
  if [ "$objs" -ge 1 ] && [ "$merge_n" -ge 1 ]; then
    result=ok
  elif [ -n "$word" ] && [ -n "$fp" ]; then
    still=$(psql_wa_tA -v word="$word" -v fp="$fp" \
      -f "$HERE/wiki_alias_probe_still.sql" 2>/dev/null) || still="?"
    case "$still" in 0) result=ok;; esac
  fi
  printf '%s' "$result"
}

# [замер 14.09] ПАРАЛЛЕЛЬНЫЕ ВОРКЕРЫ ПЕРВОГО ПРОХОДА (только force=1). vLLM батчит
# одновременные вызовы почти бесплатно: 3 параллельных — 74/168/188 с на вызов против
# ~420 с на те же три последовательно (живой замер шлюзом генератора). Решётка:
# воркер i берёт пачки i, i+WORKERS, … — при force=1 пул = весь корпус, OFFSET-курсор
# детерминирован, решётки не пересекаются, MERGE-строки пачек не пересекаются тоже.
# При force=0 пул сжимается сам (OFFSET=0) — воркеры столкнулись бы на голове пула:
# параллель принудительно выключается.
WORKERS="${WIKI_ALIAS_WORKERS:-1}"
case "$WORKERS" in ''|*[!0-9]*) WORKERS=1;; esac
[ "$WORKERS" -lt 1 ] && WORKERS=1
[ "$WIKI_ALIAS_FORCE" != "1" ] && WORKERS=1

# ── Промты «1 задача = 1 вызов» (dictfix-final-prompt.md, дословно) ──
_WA_INIT_A=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language when the title is in another language). TASK: for EACH record produce ONLY the aliases field — everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). RULES: (1) Include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. (2) WHEN the input for this record lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): at least ONE alias MUST be a spoken action/event form people use when asking about such events (same language as the title, 1-2 words). Keep that event alias even if a sibling could use a similar word — the sibling distinction belongs to the notEnoughFor field (a separate call), not to dropping the event alias. If you must drop something to fit the limit, drop a redundant noun synonym, never the event alias. For records without flows/quantities, event aliases are optional — include only when natural. (3) Limits: 3 to 10 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). (4) Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Do not put quantity names or field names into aliases (quantities are filled by a separate call). (5) BANS (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; NOUN words that equally fit a sibling in THIS batch (leave those out — the distinction goes to notEnoughFor; this ban is about nouns — spoken action/event forms stay, see rule 2); jargon opaque to a non-developer. (6) "If unsure — omit" applies to meta-labels and jargon; for action/event forms on records where Input lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): prefer one everyday event form over a near-duplicate noun synonym. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","aliases":["buyers","suppliers","customers"]}]} Never copy the English example strings into the output when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","aliases":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_INIT_B=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY). TASK: for EACH record produce ONLY the bestUsedFor field — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks, not full sentences). RULES: (1) No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). (2) No office jargon gerunds. Prefer spoken wording over metadata wording. (3) Hard format rule for EVERY string: no PARENTHESES WITH A COMMA INSIDE the string (parentheses without a comma, and commas outside parentheses, are fine). Rewrite enumerations with a dash or a word instead. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","bestUsedFor":["how many customers","who bought this month"]}]} Never copy the English example strings when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","bestUsedFor":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_INIT_C=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY). TASK: for EACH record produce ONLY the notEnoughFor field — short strings telling what this record does NOT answer. TWO KINDS, both required when applicable: (a) THEMATIC "not me" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. When a sibling shares this record's action/event asking-words, name that shared topic here (what THAT sibling's events are). FORMAT RULES: no commas and no parentheses inside any string (downstream stores arrays as comma-CSV). Use a dash or the word "not"/"see" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it. Do not invent sibling names that are not in the input. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","notEnoughFor":["not stock balances","not price list","Organizations - our own companies not trading partners"]}]} Never copy the English example strings when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","notEnoughFor":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_COLL_A=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. Answer language = the language of each title. TASK: for EACH type produce ONLY the aliases field. RULES: (1) Keep "<SHARED_WORD>" in the list — people use it. Also keep the title if it is already an everyday asking-word; each alias is a distinct word — no grammatical variants of the same stem. (2) ADD 1-2 DISTINCTIVE everyday words or short phrases (1-3 words each) that a person would use when they mean THIS type and not the siblings. WHEN the input for this type lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): at least ONE of the added words MUST be a spoken action/event form people use when asking about such events (same language as the title). Keep that event word even if a sibling could use a similar one — the sibling distinction belongs to the notEnoughFor field (a separate call), not to dropping the event word. If only 1 confident — add just 1; quality over quantity. (3) Ground aliases only in this type title, its listed flows, and quantities from Input (and in its current aliases if Input lists them); take roles/event cues from listed flows and quantities only — do not invent flows or quantities. (4) Distinctive phrases may stay unique to this type, or overlap a sibling only when both truly share that role; empty contrast (only the shared word and bare title for every sibling) leaves siblings indistinguishable — give contrast with whole asking-words, not truncated title fragments. (5) Aliases are only concrete everyday words a person would type for THIS type. Match the title language exactly. When unsure a word is everyday for THIS type — omit it (this "unsure — omit" applies to noun words; for action/event forms on types where Input lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): prefer one everyday event form over a near-duplicate noun synonym). Few-shot (English scaffold only; YOUR output language = language of each title). Shared word "party": {"items":[{"entity":"ent_partners","aliases":["party","partners","buyers"]},{"entity":"ent_counterparties","aliases":["party","counterparties","legal entities"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","aliases":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)
_WA_COLL_B=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database ("<SHARED_WORD>"). Answer language = the language of each title. TASK: for EACH type produce ONLY the bestUsedFor field — 2 to 4 short topic templates this type alone answers among the siblings (short phrases, not full sentences; topics belong to this type, not to a sibling). RULES: (1) No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a type that does not answer them). (2) No office jargon gerunds. Prefer spoken wording over metadata wording. (3) FORMAT RULE: no PARENTHESES WITH A COMMA INSIDE any string (parentheses without a comma, and commas outside parentheses, are fine). Rewrite enumerations with a dash or a word instead. Few-shot (English scaffold only): {"items":[{"entity":"ent_partners","bestUsedFor":["who we sell to","partner headcount"]},{"entity":"ent_counterparties","bestUsedFor":["taxpayer id","contract party"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","bestUsedFor":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)
_WA_COLL_C=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. Answer language = the language of each title. TASK: for EACH type produce ONLY the notEnoughFor field — when a person says "<SHARED_WORD>" but means a COMPETITOR TOPIC that another type in this list answers better, name that TOPIC (what they are looking for), then optionally the sibling title from Input. RULES: (1) Prefer themes over bare sibling names. Example shape: "stock on hand / warehouse balances — see <sibling title>"; "current price list — see <sibling title>". (2) Siblings come only from Input. (3) Each type includes the shared word "<SHARED_WORD>" in at least one notEnoughFor entry so later passes see the collision was addressed. (4) When a sibling shares this type's action/event asking-words, name that shared topic here (what THAT sibling's events are). (5) FORMAT RULE: no commas and no parentheses inside any string (downstream stores arrays as comma-CSV). Use a dash or the word "not"/"see" instead. (6) When unsure — omit that line. Few-shot (English scaffold only; YOUR output language = language of each title). Shared word "party": {"items":[{"entity":"ent_partners","notEnoughFor":["party as legal taxpayer / contract party — see Legal counterparties"]},{"entity":"ent_counterparties","notEnoughFor":["party as sales partner list — see Business partners"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","notEnoughFor":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)

# Вызов одного поля с ретраем до сборки (dictfix §2). Падение — в stderr (п.13).
# $1=prompt $2=pay $3=ans $4=err $5=msg $6=field $7=site(init|collision) $8=log_tag
wa_infer_field() {
  local prompt="$1" pay="$2" ans="$3" err="$4" msg="$5" field="$6" site="$7" tag="$8"
  local attempt
  for attempt in 0 1 2; do
    # Heartbeat до КАЖДОЙ попытки: штатная тишина ≤ один вызов шлюза (plan-progress-stall).
    [ -n "${WA_PROGRESS_FILE:-}" ] \
      && wa_progress_write "$WA_PROGRESS_FILE" "$attempt" "infer:$field"
    {
      printf '%s' "$prompt"
      cat "$pay"
    } > "$msg"
    chmod 644 "$msg"
    # stdout шлюза глотаем: вызывающий ловит только строку сборки в parse_out=$(…).
    if ! "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$msg" \
      --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
      --retry-items-json 2 \
      --ans "$ans" --err "$err" >/dev/null; then
      echo "$tag: поле $field попытка $attempt шлюз ($(head -c 100 "$err" 2>/dev/null | tr -d '\n'))" >&2
      continue
    fi
    if python3 ./wiki_alias_parse.py --check-field "$field" --site "$site" \
         "$ans" "$pay"; then
      return 0
    fi
    echo "$tag: поле $field попытка $attempt не прошло валидацию" >&2
  done
  echo "$tag: поле $field ПАДЕНИЕ после ретраев" >&2
  return 1
}

# Три поля A/B/C → rows.json (+ пустой measures при meas_out непустом).
# $1=site $2=pay $3=pref(tmp prefix) $4=rows_out $5=meas_out|"" $6=tag
# $7,$8,$9 = prompts A B C (уже с подставленным SHARED_WORD для collision)
# stdout — только итог assemble («алиасов разобрано: N…»).
wa_infer_three_fields() {
  local site="$1" pay="$2" pref="$3" rows_out="$4" meas_out="$5" tag="$6"
  local pA="$7" pB="$8" pC="$9"
  wa_infer_field "$pA" "$pay" "${pref}.ans_a" "${pref}.err_a" "${pref}.msg_a" \
    aliases "$site" "$tag" || return 1
  wa_infer_field "$pB" "$pay" "${pref}.ans_b" "${pref}.err_b" "${pref}.msg_b" \
    bestUsedFor "$site" "$tag" || return 1
  wa_infer_field "$pC" "$pay" "${pref}.ans_c" "${pref}.err_c" "${pref}.msg_c" \
    notEnoughFor "$site" "$tag" || return 1
  python3 ./alias_usage_log.py --contour wiki --ans "${pref}.ans_a" \
    --model "$WIKI_ALIAS_MODEL" >/dev/null 2>&1 || true
  if [ -n "$meas_out" ]; then
    python3 ./wiki_alias_parse.py --assemble --site "$site" \
      "${pref}.ans_a" "${pref}.ans_b" "${pref}.ans_c" \
      "$pay" "$rows_out" "$meas_out"
  else
    python3 ./wiki_alias_parse.py --assemble --site "$site" \
      "${pref}.ans_a" "${pref}.ans_b" "${pref}.ans_c" \
      "$pay" "$rows_out"
  fi
}

# Первый проход сущностей — воркер на решётке курсора (WORKERS×параллельно при
# force=1, иначе один). Все временные файлы воркера — в своём $WTMP, счётчики —
# в своих файлах; пачки воркеров не пересекаются (решётка), MERGE-строки тоже.
wiki_alias_entities_worker() {
  local w="$1" WTMP done_total wskipped STEP
  local WA_PROGRESS_FILE="$TMP/.progress_ent_$w"
  WTMP="$TMP/w$w"; mkdir -p "$WTMP"
  [ "$(id -u)" = 0 ] && chown "$BOTUSER" "$WTMP" 2>/dev/null || true
  done_total=$(( w * BATCH ))
  wskipped=0
  STEP=$(( BATCH * WORKERS ))
while :; do
  # 🔴 ПАЧКА — ЭТО ГРУППА ПОХОЖИХ, А НЕ СЛУЧАЙНЫЕ СУЩНОСТИ ПОДРЯД.
  # [замер 30.07] описанные поодиночке страницы не различают соседей: у «Подтверждения
  # оплаты НДС в бюджет» в «не годится» стояло «налоговая декларация, конкретный платёж» —
  # верно, но не отделяет ни от «НДС записи книги покупок», ни от строк приобретений. А
  # сущностей со словом «НДС» в базе ВОСЕМНАДЦАТЬ, и бот отвечал не из той: 8 654 378,11
  # вместо 11 036 086,09.
  #
  # Поэтому пачка набирается ПО БЛИЗОСТИ СМЫСЛА к первой невзятой сущности — тем же
  # вектором названия, что уже лежит в `search_tables.emb`. Ни списка тем, ни слов о
  # конкретной базе: соседей определяет сама база. Тогда модель видит их рядом и может
  # сказать, чем они отличаются ДРУГ ОТ ДРУГА.
  # 🔴 СБОЙ СЕЛЕКТА ≠ «БАЗА КОНЧИЛАСЬ» (28.08, ночь). Сломанный SQL давал
  # пустой PAY, stderr глотался, цикл молча выходил как «нет непокрытых» —
  # холостой прогон по живой базе. Ошибка базы обязана останавливать прогон
  # с текстом в журнале юнита, а не приравниваться к пустому результату.
  # 🔴 OFFSET ТОЛЬКО ПРИ force=1. При force=0 пул сжимается сам (заполнение
  # aliases / mark_skip выводит строку из NOT EXISTS) — OFFSET сдвинул бы
  # mark_skip-хвост в голову и крутил бы одни и те же «пропущенные». При force=1
  # пул = весь корпус всегда → :skip_rows (= done_total) — единственный курсор.
  wa_progress_write "$WA_PROGRESS_FILE" "$done_total" "sel"
  if ! psql_wa_tA -v batch="$BATCH" -v skip_rows="$done_total" \
      -f "$HERE/wiki_alias_select_entity_batch.sql" > "$WTMP/pay"; then
    echo "алиасы: СБОЙ селекта пачки (ошибка выше) — прогон остановлен, пачка не потеряна" >&2
    echo 1 > "$WTMP/.fail"
    return 1
  fi
  chmod 644 "$WTMP/pay" 2>/dev/null
  PAY=$(cat "$WTMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac

  # 🔴 ЗАДАНИЕ ПЕРЕДАЁТСЯ ФАЙЛОМ, А НЕ АРГУМЕНТОМ. [замер 30.07] с `-m "$PAY"` на пачке из 25
  # сущностей команда отвечала «Missing message»: длинный JSON в аргументе командной строки не
  # доходит. У `openclaw agent` для этого есть штатный `--message-file`. Тот же класс дефекта, что
  # «стена argv» в разборе `HOW_NOT_TO §0`: данные аргументом командной строки не передаются.
  # «1 задача = 1 вызов»: init-A/B/C → сборка → один MERGE (dictfix §2).
  if ! parse_out=$(wa_infer_three_fields init "$WTMP/pay" "$WTMP/ent" \
        "$WTMP/rows.json" "$WTMP/measures.json" "алиасы" \
        "$_WA_INIT_A" "$_WA_INIT_B" "$_WA_INIT_C"); then
      wskipped=$((wskipped + 1))
      echo "алиасы: пачка пропущена (падение поля A/B/C)" >&2
      psql_wa -v pay_path="$WTMP/pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
      done_total=$((done_total + STEP))
      wa_progress_write "$WA_PROGRESS_FILE" "$done_total" "ent"
      [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
      continue
  fi

  # Разбор ответа модели — своим кодом это разрешено (п. 20: проверка ответа модели).
  # Выдуманное имя величины отбрасывается: во входном списке его не было.
  # 🔴 rc0 шлюза + 0 разобранных = попытка, не успех (R4). items=[] проходит
  # валидацию шлюза, MERGE был no-op, mark_skip не звался — пачка терялась молча.
  echo "$parse_out"
  ents_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*алиасов разобрано: \([0-9][0-9]*\).*/\1/p' | tail -n1)
  case "$ents_n" in ''|*[!0-9]*) ents_n=0;; esac
  if [ "$ents_n" -eq 0 ]; then
    wskipped=$((wskipped + 1))
    echo "алиасы: пачка пропущена (rc0, разобрано 0)" >&2
    psql_wa -v pay_path="$WTMP/pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
    done_total=$((done_total + STEP))
    wa_progress_write "$WA_PROGRESS_FILE" "$done_total" "ent"
    [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
    continue
  fi
  # 🔴 ФАЙЛ ЧИТАЕТ ДВИЖОК, А НЕ МЫ. Каталогу права выставлены при создании, но
  # сам файл рождается с маской процесса: такт идёт из `build.sh`, где стоит
  # `umask 077` (секреты), и `rows.json` выходил 600 root — движок (`serenedb`)
  # получал «Permission denied», модель при этом отвечала исправно. Живой случай
  # okna-1 13.08: словарь встал на 140 из 351 при «алиасов разобрано: 20» каждую
  # пачку — то есть деньги за модель тратились, а словарь не рос. Права ставятся
  # рядом с записью, как у `msg` выше.
  chmod 644 "$WTMP/rows.json" "$WTMP/measures.json" 2>/dev/null
  # Запись — ОДНИМ запросом из файла, без цикла по строкам (п. 20). Пустая заготовка,
  # оставшаяся от прежней осечки, сначала снимается: иначе ответ модели молча падал бы
  # мимо словаря (`NOT IN` считает такую строку уже отвеченной), и переспрос был бы
  # бесполезен — деньги за модель тратились бы вечно.
  psql_wa -v rows_path="$WTMP/rows.json" -v measures_path="$WTMP/measures.json" \
    -f "$HERE/wiki_alias_merge_entity.sql" 2>&1 | grep -i error

  have=$(psql_wa_tA -c "SELECT count(*) FROM $ALIAS_TABLE" 2>/dev/null)
  echo "алиасы: всего в базе $have"
  done_total=$((done_total + STEP))
  wa_progress_write "$WA_PROGRESS_FILE" "$done_total" "ent"
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
  over_budget && { echo "алиасы: бюджет $BUDGET с исчерпан — остальные сущности возьмёт следующий такт"; break; }
done
  echo "$wskipped" > "$WTMP/.skipped"
  echo "$done_total" > "$WTMP/.done"
}

# ── WIKI_ALIAS_MODE=cycle: полный пересбор одним прогоном (plan-cycle-mode.md v2) ──
# Tick-путь НИЖЕ этого if не меняется. Cycle — ранний выход после фаз а…ж.
# Журнал юнита — единственное место наблюдения (п.13): каждая фаза START|END|ABORT.

_cycle_phase_stamp() {
  local now
  now=$(date +%s)
  _CYCLE_ELAPSED=$((now - t_start))
  if [ "$BUDGET" = "0" ]; then
    _CYCLE_BUDGET_LEFT=inf
  else
    _CYCLE_BUDGET_LEFT=$((BUDGET - (now - t_start)))
    [ "$_CYCLE_BUDGET_LEFT" -lt 0 ] && _CYCLE_BUDGET_LEFT=0
  fi
}

# $1=буква фазы $2=START|END|ABORT $3=счётчики/текст
_cycle_phase() {
  _cycle_phase_stamp
  echo "фаза $1 $2 elapsed=${_CYCLE_ELAPSED}s budget_left=${_CYCLE_BUDGET_LEFT}s${3:+ $3}"
}

# Init+добор величин при текущих FORCE/WORKERS/CAP (общие с tick SQL).
# Retry-флаг через переменную, чтобы prompts_v2 по-прежнему видел ровно
# два литерала в tick (wa_infer_field + measure-сайт).
_CYCLE_RETRY_ITEMS=2
_cycle_run_init_pass() {
  done_total=0
  skipped=0
  pids=""
  for w in $(seq 0 $((WORKERS - 1))); do
    if [ "$WORKERS" -gt 1 ]; then
      wiki_alias_entities_worker "$w" &
      pids="$pids $!"
    else
      wiki_alias_entities_worker "$w"
    fi
  done
  # ждём только порождённых: голый wait ловит вечного наблюдателя (живая проба 15.09, стоп-при-тишине 129 с)
  [ "$WORKERS" -gt 1 ] && wait $pids
  for w in $(seq 0 $((WORKERS - 1))); do
    [ -f "$TMP/w$w/.fail" ] && {
      echo "алиасы: воркер $w упал по сбою селекта — прогон остановлен" >&2
      return 1
    }
  done
  for w in $(seq 0 $((WORKERS - 1))); do
    s=$(cat "$TMP/w$w/.skipped" 2>/dev/null); case "$s" in ''|*[!0-9]*) s=0;; esac
    skipped=$((skipped + s))
    d=$(cat "$TMP/w$w/.done" 2>/dev/null); case "$d" in ''|*[!0-9]*) d=0;; esac
    [ "$d" -gt "$done_total" ] && done_total="$d"
  done
  done_measures=0
  while :; do
    over_budget && {
      echo "величины: бюджет $BUDGET с исчерпан — прогон остановлен по бюджету"
      break
    }
    [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
    wa_progress_write "$TMP/.progress_meas" "$done_measures" "sel"
    psql_wa_tA -v batch="$BATCH" -v skip_rows="$done_measures" \
      -f "$HERE/wiki_alias_select_measure_batch.sql" > "$TMP/pay" 2>/dev/null
    chmod 644 "$TMP/pay" 2>/dev/null
    PAY=$(cat "$TMP/pay")
    case "$PAY" in ''|'[]'|'null') break;; esac
    {
      printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string field = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language into the output when the title is in another language). For EACH record: (1) aliases — ONLY everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). ALSO include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. ALSO include 1-2 spoken action/event forms people use when asking about events THIS kind of record captures, when such forms are natural for the type (same language as the title; same quality limits as other aliases; distinctive for THIS type among siblings in THIS batch — forms that equally fit a sibling go under notEnoughFor). Limits: 3 to 8 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Quantity names and field names go ONLY under quantities, never under aliases. BANS for aliases (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; words that equally fit a sibling in THIS batch (leave those out of aliases — put the distinction in notEnoughFor); jargon opaque to a non-developer. (2) quantities — for EVERY name from the input quantities list, copy that name EXACTLY and give 1-5 short names a person uses for that value (a noun, or a noun with the action/event word they say — e.g. spoken event forms for money totals), 1-3 words each, no sentences. Same bans as aliases. If a listed quantity has no clear everyday name, return it with an empty aliases array. (3) bestUsedFor — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks). No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). No office jargon gerunds. Prefer spoken wording over metadata wording. (4) notEnoughFor — two kinds of short strings, both required when applicable: (a) THEMATIC \"not me\" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. Hard format rule for EVERY notEnoughFor string: no commas and no parentheses inside the string (downstream stores arrays as comma-CSV). Use a dash or the word \"not\"/\"see\" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it. Global: if you are not sure a token or claim is correct — do not write it (omit; never guess). Do not invent quantities, flows, or sibling names that are not in the input. One structure example (English skeleton only; rewrite all strings into the title language of each real item): {\"entity\":\"catalog_counterparties\",\"aliases\":[\"buyers\",\"suppliers\",\"customers\"],\"quantities\":[{\"name\":\"Count\",\"aliases\":[\"headcount\",\"how many partners\"]}],\"bestUsedFor\":[\"how many customers\",\"who bought this month\"],\"notEnoughFor\":[\"not stock balances\",\"not price list\",\"Organizations - our own companies not trading partners\"]} Never copy the English example strings into the output when the title language is different — rewrite every string in the title language. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
      cat "$TMP/pay"
    } > "$TMP/msg"
    chmod 644 "$TMP/msg"
    wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
    "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
      --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
      --retry-items-json "$_CYCLE_RETRY_ITEMS" \
      --ans "$TMP/ans" --err "$TMP/err" || {
        skipped=$((skipped + 1))
        echo "величины: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
        psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
        done_measures=$((done_measures + BATCH))
        done_total=$((done_total + BATCH))
        wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
        [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
        continue
      }
    parse_out=$(python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json")
    echo "$parse_out"
    meas_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*величин: \([0-9][0-9]*\).*/\1/p' | tail -n1)
    case "$meas_n" in ''|*[!0-9]*) meas_n=0;; esac
    if [ "$meas_n" -eq 0 ]; then
      skipped=$((skipped + 1))
      echo "величины: пачка пропущена (rc0, разобрано 0)" >&2
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
      done_measures=$((done_measures + BATCH))
      done_total=$((done_total + BATCH))
      wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
      [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
      continue
    fi
    python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
    chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
    psql_wa -v measures_path="$TMP/measures.json" \
      -f "$HERE/wiki_alias_merge_measures.sql" 2>&1 | grep -i error
    have_m=$(psql_wa_tA -c "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''" 2>/dev/null)
    echo "величины: непустых в базе $have_m"
    done_measures=$((done_measures + BATCH))
    done_total=$((done_total + BATCH))
    wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
  done
  return 0
}

# Collision до нуля с лифтом CEILING (ОБЕ проверки потолка читают CEILING; rounds не сбрасывается).
_cycle_run_collision() {
  local COLL_WORKERS rounds asked stopped left left_at_window window_asked
  local CEILING ROUNDS_STEP ROUNDS_MAX
  rounds=0
  asked=0
  stopped=""
  left=""
  left_at_window=""
  CEILING="${WIKI_ALIAS_COLLISION_ROUNDS:-40}"
  case "$CEILING" in ''|*[!0-9]*) CEILING=40;; esac
  ROUNDS_STEP="${WIKI_ALIAS_ROUNDS_STEP:-40}"
  case "$ROUNDS_STEP" in ''|*[!0-9]*) ROUNDS_STEP=40;; esac
  ROUNDS_MAX="${WIKI_ALIAS_ROUNDS_MAX:-400}"
  case "$ROUNDS_MAX" in ''|*[!0-9]*) ROUNDS_MAX=400;; esac
  [ "$CEILING" -gt "$ROUNDS_MAX" ] && CEILING=$ROUNDS_MAX
  # CAP>0: точечная проба не жжёт модель — потолок collision = min(CEILING, CAP).
  case "$CAP" in ''|*[!0-9]*) ;; *)
    if [ "$CAP" -gt 0 ] && [ "$CEILING" -gt "$CAP" ]; then
      CEILING=$CAP
    fi
    ;;
  esac
  echo "collision CEILING=$CEILING (CAP=$CAP)"
  COLL_WORKERS="${WIKI_ALIAS_COLLISION_WORKERS:-3}"
  case "$COLL_WORKERS" in ''|*[!0-9]*) COLL_WORKERS=3;; esac
  [ "$COLL_WORKERS" -lt 1 ] && COLL_WORKERS=1
  # WIKI_ALIAS_WORD → ровно одно слово без лифта (plan §2 в).
  [ -n "$TARGET_WORD" ] && COLL_WORKERS=1

  while :; do
    left_at_window=$(psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql" 2>/dev/null)
    # 🔴 fail-closed (red12b-1): нечитаемый счётчик ≠ 0 — лифт и гейты останавливаются.
    case "$left_at_window" in ''|*[!0-9]*)
      echo "разведение: collision_left не читается — прогон остановлен" >&2
      stopped="left_read_error"
      break
      ;;
    esac
    window_asked=0
    while [ "$rounds" -lt "$CEILING" ]; do
      over_budget && { stopped="budget"; break; }
      QWORDS="" Q=0
      for iq in $(seq 1 "$COLL_WORKERS"); do
        # red5: предел кругов — CEILING (одна переменная с внешним while).
        [ "$rounds" -lt "$CEILING" ] || break
        ROUND=$(psql_wa_tA -v batch="$COLL_BATCH" -v target_word="$TARGET_WORD" \
          -f "$HERE/wiki_alias_collision_round.sql" 2>/dev/null) || ROUND=""
        [ -z "$ROUND" ] && break
        WORD=${ROUND%%$'\t'*}
        rest=${ROUND#*$'\t'}
        FP=${rest%%$'\t'*}
        PAY=${rest#*$'\t'}
        WTMP="$TMP/cw$iq"; mkdir -p "$WTMP"
        [ "$(id -u)" = 0 ] && chown "$BOTUSER" "$WTMP" 2>/dev/null || true
        rm -f "$WTMP/rows.json"
        printf '%s' "$PAY" > "$WTMP/pay"
        printf '%s' "$WORD" > "$WTMP/word"
        printf '%s' "$FP" > "$WTMP/fp"
        chmod 644 "$WTMP/pay" "$WTMP/word" "$WTMP/fp" 2>/dev/null
        QWORDS="$QWORDS $iq"
        Q=$((Q + 1))
        rounds=$((rounds + 1))
        [ -n "$TARGET_WORD" ] && break
      done
      [ "$Q" -eq 0 ] && break
      asked=$((asked + Q))
      window_asked=$((window_asked + Q))
      _pg=""
      for iq in $QWORDS; do
        (
          WTMP="$TMP/cw$iq"
          WA_PROGRESS_FILE="$TMP/.progress_col_$iq"
          PAY=$(cat "$WTMP/pay" 2>/dev/null)
          case "$PAY" in ''|'[]'|'null') exit 0;; esac
          WORD=$(cat "$WTMP/word" 2>/dev/null)
          _CA="${_WA_COLL_A//<SHARED_WORD>/$WORD}"
          _CB="${_WA_COLL_B//<SHARED_WORD>/$WORD}"
          _CC="${_WA_COLL_C//<SHARED_WORD>/$WORD}"
          if ! parse_out=$(wa_infer_three_fields collision "$WTMP/pay" "$WTMP/coll" \
                "$WTMP/rows.json" "" "разведение" \
                "$_CA" "$_CB" "$_CC"); then
            echo "разведение: пачка пропущена (падение поля A/B/C)" >&2
            wa_progress_write "$WA_PROGRESS_FILE" 0 "col"
            exit 0
          fi
          echo "$parse_out"
          chmod 644 "$WTMP/rows.json" 2>/dev/null
          wa_progress_write "$WA_PROGRESS_FILE" 1 "col"
        ) &
        _pg="$_pg $!"
      done
      # ждём только порождённых: голый wait ловит вечного наблюдателя (живая проба 15.09, стоп-при-тишине 129 с)
      [ -n "$_pg" ] && wait $_pg
      for iq in $QWORDS; do
        # merge внутри wa_probe_result_for (RETURNING → count); пометка всегда.
        _pr=$(wa_probe_result_for "$TMP/cw$iq")
        WORD=$(cat "$TMP/cw$iq/word" 2>/dev/null || true)
        FP=$(cat "$TMP/cw$iq/fp" 2>/dev/null || true)
        wa_probe_mark "$WORD" "$FP" "$_pr"
      done
      [ -n "$TARGET_WORD" ] && break
    done
    left=$(psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql" 2>/dev/null)
    # 🔴 fail-closed (red12b-1): нечитаемый финальный счётчик ≠ «разведено всё».
    case "$left" in ''|*[!0-9]*)
      echo "разведение: финальный collision_left не читается — прогон остановлен" >&2
      stopped="left_read_error"
      break
      ;;
    esac
    echo "разведение столкновений: кругов $rounds CEILING=$CEILING, спрошено слов $asked, осталось $left${stopped:+ ($stopped)}"
    printf '%s\n' "$left" > "$TMP/.collision_left_echo"

    [ "$left" -eq 0 ] && break
    [ -n "$TARGET_WORD" ] && break
    [ "$stopped" = "budget" ] && break
    # СТОП лифта: нет прогресса (left не уменьшился / Q=0 при left>0).
    if [ "$window_asked" -eq 0 ]; then
      echo "лифт CEILING стоп: Q=0 при left=$left"
      break
    fi
    if [ "$left" -ge "$left_at_window" ]; then
      echo "лифт CEILING стоп: нет прогресса left=$left (было $left_at_window)"
      break
    fi
    # потолок не исчерпан — лифт не поднимаем (-ge, чтобы rounds<CEILING осталось ровно 2: while+red5)
    [ "$rounds" -ge "$CEILING" ] || break
    # CAP>0: точечная проба не жжёт модель — лифт CEILING отключён (F1).
    case "$CAP" in ''|*[!0-9]*) ;; *)
      if [ "$CAP" -gt 0 ]; then
        echo "лифт CEILING отключён (CAP=$CAP — точечная проба)"
        break
      fi
      ;;
    esac
    if [ "$CEILING" -ge "$ROUNDS_MAX" ]; then
      echo "лифт CEILING стоп: достигнут MAX=$ROUNDS_MAX left=$left"
      break
    fi
    CEILING=$((CEILING + ROUNDS_STEP))
    [ "$CEILING" -gt "$ROUNDS_MAX" ] && CEILING=$ROUNDS_MAX
    echo "лифт CEILING → $CEILING (left=$left, rounds=$rounds)"
  done
  _CYCLE_COLL_ROUNDS=$rounds
  _CYCLE_COLL_ASKED=$asked
  _CYCLE_COLL_LEFT=$left
  _CYCLE_COLL_CEILING=$CEILING
  _CYCLE_COLL_STOPPED=$stopped
  return 0
}

wiki_alias_run_cycle() {
  local _base_a _base_m CYCLE_SUFFIX exists uncovered allow_left
  local BATTLE_E BATTLE_M promote_rc migrate_rc solr_rc a3_rc a3_out
  local draft_n have have_m a3_kasha a3_ok a3_prob
  local _v_ceiling _v_rmax

  # ── а) датированные черновики + СВОЯ PROBE (боевую search_alias_probe не трогаем) ──
  _cycle_phase а START
  CYCLE_SUFFIX=$(date +%Y%m%d)
  _base_a="$ALIAS_TABLE"
  _base_m="$MEASURE_TABLE"
  ALIAS_TABLE="${_base_a}_cycle_${CYCLE_SUFFIX}"
  MEASURE_TABLE="${_base_m}_cycle_${CYCLE_SUFFIX}"
  # Изоляция: память столкновений только у черновика (red9a-5/red9b-3).
  PROBE_TABLE="${ALIAS_TABLE}_probe"
  for exists in "$ALIAS_TABLE" "$MEASURE_TABLE" "$PROBE_TABLE"; do
    # fail-closed: stderr не глушим; любой ответ кроме 0/1 — ABORT (red10a-2/red10b-1).
    # existence-чек штатным каталогом: to_regclass в SereneDB НЕТ (живая проба 15.09:
    # «Scalar Function ... does not exist» → честный ABORT, ничего не перезаписано —
    # fail-closed сработал до этой правки). Доки: Sql › Information Schema › tables.
    draft_n=$(psql "$DSN" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_name = '$exists'" | tr -d '[:space:]')
    case "$draft_n" in
      1)
        _cycle_phase а ABORT "таблица $exists уже есть — не overwrite; полный cycle не resume — хвост после упавшего solr/A3 добивается вручную (имена снапшотов уже в журнале promote)"
        return 1
        ;;
      0) ;;
      *)
        _cycle_phase а ABORT "не удалось проверить $exists"
        return 1
        ;;
    esac
  done
  wa_progress_write "$TMP/.progress_main" 0 "ddl"
  psql_wa -f "$HERE/wiki_alias_init.sql" >/dev/null 2>&1 || {
    _cycle_phase а ABORT "DDL черновика не прошёл"
    return 1
  }
  _cycle_phase а END "suffix=$CYCLE_SUFFIX alias=$ALIAS_TABLE measure=$MEASURE_TABLE probe=$PROBE_TABLE"

  # ── б) init (+добор величин): FORCE=1 только здесь; потом FORCE=0 WORKERS=1; reask выкл ──
  _cycle_phase б START "FORCE=1"
  # Reask в cycle выключен явно (не зависит от env юнита).
  REASK_EVERY=0
  WIKI_ALIAS_FORCE=1
  WORKERS="${WIKI_ALIAS_WORKERS:-1}"
  case "$WORKERS" in ''|*[!0-9]*) WORKERS=1;; esac
  [ "$WORKERS" -lt 1 ] && WORKERS=1
  if ! _cycle_run_init_pass; then
    _cycle_phase б ABORT "init/воркер"
    return 1
  fi
  # FORCE только на init (red9a-4): до collision сброс + один воркер.
  WIKI_ALIAS_FORCE=0
  WORKERS=1
  # Бюджет не рвёт готовый черновик (red10a-1): полноту гейтит фаза г (uncovered/CAP).
  if over_budget; then
    echo "бюджет модельных фаз исчерпан; полноту черновика проверит фаза г"
  fi
  # F2: stderr psql не глушим; нечисло → «?» (журнал не врёт нулём).
  have=$(psql_wa_tA -c "SELECT count(*) FROM $ALIAS_TABLE")
  case "$have" in ''|*[!0-9]*) have='?';; esac
  have_m=$(psql_wa_tA -c "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''")
  case "$have_m" in ''|*[!0-9]*) have_m='?';; esac
  _cycle_phase б END "done=$done_total skipped=$skipped have=$have have_m=$have_m FORCE=0 WORKERS=1 reask=0"

  # Отчёт качества init — после фазы б, до collision (фаза в).
  if ! wa_quality_report; then
    return 1
  fi

  # ── в) collision до нуля с лифтом CEILING ──
  # F3: клещи min(CEILING,CAP)/MAX до START — журнал печатает фактический потолок.
  _v_ceiling="${WIKI_ALIAS_COLLISION_ROUNDS:-40}"
  case "$_v_ceiling" in ''|*[!0-9]*) _v_ceiling=40;; esac
  _v_rmax="${WIKI_ALIAS_ROUNDS_MAX:-400}"
  case "$_v_rmax" in ''|*[!0-9]*) _v_rmax=400;; esac
  [ "$_v_ceiling" -gt "$_v_rmax" ] && _v_ceiling=$_v_rmax
  case "$CAP" in ''|*[!0-9]*) ;; *)
    if [ "$CAP" -gt 0 ] && [ "$_v_ceiling" -gt "$CAP" ]; then
      _v_ceiling=$CAP
    fi
    ;;
  esac
  case "$CAP" in ''|*[!0-9]*|0) _cycle_phase в START "CEILING=$_v_ceiling" ;;
    *) _cycle_phase в START "CEILING=$_v_ceiling (точечная проба CAP=$CAP)" ;;
  esac
  # Самоочистка probe черновика — после фазы а (PROBE_TABLE уже свой), до collision.
  wa_probe_purge
  if [ "${WIKI_ALIAS_COLLISIONS:-1}" = "1" ]; then
    _cycle_run_collision
  else
    _CYCLE_COLL_ROUNDS=0
    _CYCLE_COLL_ASKED=0
    _CYCLE_COLL_LEFT=$(psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql" 2>/dev/null)
    _CYCLE_COLL_CEILING=0
    _CYCLE_COLL_STOPPED=skipped
  fi
  # 🔴 fail-closed: нечитаемый collision_left НЕ считается «разведено 0» (red12b-1):
  # promote при слепом гейте невозможен.
  case "${_CYCLE_COLL_LEFT:-}" in ''|*[!0-9]*)
    _cycle_phase в ABORT "collision_left не читается (сбой psql) — promote не выполняем"
    return 1
    ;;
  esac
  # ABORT по budget только если хвост collision не доведён (left>0); left=0 — END (red10a-1).
  if [ "${_CYCLE_COLL_STOPPED:-}" = "budget" ] && [ "${_CYCLE_COLL_LEFT}" -gt 0 ]; then
    _cycle_phase в ABORT "модельный бюджет rounds=${_CYCLE_COLL_ROUNDS:-0} left=${_CYCLE_COLL_LEFT} — promote не выполняем"
    return 1
  fi
  _cycle_phase в END "rounds=${_CYCLE_COLL_ROUNDS:-0} asked=${_CYCLE_COLL_ASKED:-0} left=${_CYCLE_COLL_LEFT:-?} CEILING=${_CYCLE_COLL_CEILING:-?}${_CYCLE_COLL_STOPPED:+ stopped=$_CYCLE_COLL_STOPPED}"

  # ── г) гейты перед promote (fail-closed) ──
  _cycle_phase г START
  uncovered=$(psql_wa_tA -c \
    "SELECT count(*) FROM wiki_entity_facts f WHERE NOT EXISTS (SELECT 1 FROM $ALIAS_TABLE a WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')" \
    2>/dev/null)
  case "$uncovered" in ''|*[!0-9]*) uncovered=999999;; esac
  # init покрыт: нет непокрытых ИЛИ достигнут CAP пробы.
  if [ "$uncovered" -gt 0 ]; then
    if [ "$CAP" = "0" ] || [ "$done_total" -lt "$CAP" ]; then
      _cycle_phase г ABORT "init не покрыт: uncovered=$uncovered done=$done_total CAP=$CAP"
      return 1
    fi
  fi
  allow_left="${WIKI_ALIAS_CYCLE_ALLOW_LEFT:-0}"
  case "${_CYCLE_COLL_LEFT:-0}" in ''|*[!0-9]*) _CYCLE_COLL_LEFT=0;; esac
  if [ "${_CYCLE_COLL_LEFT:-0}" -ne 0 ] && [ "$allow_left" != "1" ]; then
    _cycle_phase г ABORT "collision left=${_CYCLE_COLL_LEFT} (нужен 0 или WIKI_ALIAS_CYCLE_ALLOW_LEFT=1)"
    return 1
  fi
  if [ "${_CYCLE_COLL_LEFT:-0}" -ne 0 ] && [ "$allow_left" = "1" ]; then
    echo "promote с неразведёнными ${_CYCLE_COLL_LEFT} словами"
  fi
  _cycle_phase г END "uncovered=$uncovered left=${_CYCLE_COLL_LEFT} allow_left=$allow_left"

  # ── д) promote: цель только BATTLE_TABLE | PROMOTE_BATTLE=1 (иначе стоп) ──
  _cycle_phase д START
  if [ -n "${WIKI_ALIAS_BATTLE_TABLE:-}" ]; then
    # Пара (+_MEASURE): без меры случайный бой мер невозможен (fail-closed).
    if [ -z "${WIKI_ALIAS_BATTLE_MEASURE:-}" ]; then
      _cycle_phase д ABORT "promote не выполнен: задай BATTLE_MEASURE вместе с BATTLE_TABLE"
      return 1
    fi
    BATTLE_E="$WIKI_ALIAS_BATTLE_TABLE"
    BATTLE_M="$WIKI_ALIAS_BATTLE_MEASURE"
    # Бой через BATTLE_TABLE без флага запрещён (red10b-2); песочница — без флага.
    if [ "$BATTLE_E" = "search_entity_alias" ] || [ "$BATTLE_M" = "search_measure_alias" ]; then
      if [ "${WIKI_ALIAS_PROMOTE_BATTLE:-0}" != "1" ]; then
        _cycle_phase д ABORT "BATTLE_TABLE указывает на бой — нужен PROMOTE_BATTLE=1"
        return 1
      fi
    fi
  elif [ "${WIKI_ALIAS_PROMOTE_BATTLE:-0}" = "1" ]; then
    BATTLE_E=search_entity_alias
    BATTLE_M=search_measure_alias
  else
    _cycle_phase д ABORT "promote не выполнен: задай BATTLE_TABLE или PROMOTE_BATTLE=1"
    return 1
  fi
  wa_progress_write "$TMP/.progress_main" 0 "promote"
  psql "$DSN" -v ON_ERROR_STOP=1 \
    -v draft_table="$ALIAS_TABLE" \
    -v battle_table="$BATTLE_E" \
    -v draft_measure="$MEASURE_TABLE" \
    -v battle_measure="$BATTLE_M" \
    -v snap_suffix="$CYCLE_SUFFIX" \
    -f "$HERE/wiki_alias_promote.sql"
  promote_rc=$?
  if [ "$promote_rc" -ne 0 ]; then
    _cycle_phase д ABORT "wiki_alias_promote.sql rc=$promote_rc battle=$BATTLE_E"
    return 1
  fi
  _cycle_phase д END "battle=$BATTLE_E measure=$BATTLE_M snap_suffix=$CYCLE_SUFFIX"

  # ── е) migrate_sep + solr (бой: compile; песочница: skip — red10c-1) ──
  # Хвост без модели — выполняется всегда после успешных гейтов (plan §3).
  _cycle_phase е START
  wa_progress_write "$TMP/.progress_main" 0 "migrate"
  psql "$DSN" -v ON_ERROR_STOP=1 \
    -v battle_table="$BATTLE_E" \
    -v battle_measure="$BATTLE_M" \
    -v snap_suffix="$CYCLE_SUFFIX" \
    -f "$HERE/wiki_alias_migrate_sep.sql"
  migrate_rc=$?
  if [ "$migrate_rc" -ne 0 ]; then
    _cycle_phase е ABORT "migrate_sep rc=$migrate_rc"
    return 1
  fi
  SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-${SOLR_SYN_DICT:-search_dict_syn}}"
  DICT_LOCALE="${SEARCH_DICT_LOCALE:-ru_RU.utf8}"
  if [ "$BATTLE_E" = "search_entity_alias" ]; then
    wa_progress_write "$TMP/.progress_main" 0 "solr"
    psql "$DSN" -q \
      -v dict_locale="$DICT_LOCALE" \
      -v solr_syn_dict="$SOLR_SYN_DICT" \
      -v alias_table="search_entity_alias" \
      -f "$HERE/solr_synonyms_compile.sql"
    solr_rc=$?
    if [ "$solr_rc" -ne 0 ]; then
      _cycle_phase е ABORT "solr synonyms rc=$solr_rc — словарь боя и Solr разошлись"
      return 1
    fi
    _cycle_phase е END "migrate=ok solr=$SOLR_SYN_DICT"
  else
    echo "solr: пропуск (цель — песочница)"
    _cycle_phase е END "migrate=ok solr=skip"
  fi

  # ── ж) A3: корзины КАША/ОК/ПРОБЕЛ в журнал ──
  _cycle_phase ж START "dict_table=$BATTLE_E"
  wa_progress_write "$TMP/.progress_main" 0 "a3"
  a3_out=$(psql "$DSN" -v ON_ERROR_STOP=1 -v dict_table="$BATTLE_E" \
    -f "$HERE/wiki_alias_metric_a3.sql" 2>&1)
  a3_rc=$?
  printf '%s\n' "$a3_out"
  if [ "$a3_rc" -ne 0 ]; then
    _cycle_phase ж ABORT "A3 rc=$a3_rc — словарь боя и Solr разошлись"
    return 1
  fi
  a3_kasha=$(printf '%s\n' "$a3_out" | sed -n 's/^[[:space:]]*КАША[[:space:]]*|[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
  a3_ok=$(printf '%s\n' "$a3_out" | sed -n 's/^[[:space:]]*ОК[[:space:]]*|[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
  a3_prob=$(printf '%s\n' "$a3_out" | sed -n 's/^[[:space:]]*ПРОБЕЛ[[:space:]]*|[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n1)
  # «?» вместо лжи нулём при сбое разбора (red12b-2, п.13).
  case "$a3_kasha" in ''|*[!0-9]*) a3_kasha="?";; esac
  case "$a3_ok" in ''|*[!0-9]*) a3_ok="?";; esac
  case "$a3_prob" in ''|*[!0-9]*) a3_prob="?";; esac
  _cycle_phase ж END "A3 ok КАША=$a3_kasha ОК=$a3_ok ПРОБЕЛ=$a3_prob"
  [ "$skipped" -gt 0 ] && echo "алиасы: пачек пропущено из-за отказа модели: $skipped" >&2
  return 0
}

if [ "$WIKI_ALIAS_MODE" = "cycle" ]; then
  wiki_alias_run_cycle
  exit $?
fi

# ── tick (умолч.): существующий поток ниже — без изменений поведения ──

pids=""
for w in $(seq 0 $((WORKERS - 1))); do
  if [ "$WORKERS" -gt 1 ]; then
    wiki_alias_entities_worker "$w" &
    pids="$pids $!"
  else
    wiki_alias_entities_worker "$w"
  fi
done
# ждём только порождённых: голый wait ловит вечного наблюдателя (живая проба 15.09, стоп-при-тишине 129 с)
[ "$WORKERS" -gt 1 ] && wait $pids
# 🔴 СБОЙ СЕЛЕКТА ≠ «БАЗА КОНЧИЛАСЬ» и в параллельном воркере: exit субшелла
# погасил бы стоп, прогон продолжился бы молча. Воркер ставит .fail — главный
# скрипт останавливает юнит целиком.
for w in $(seq 0 $((WORKERS - 1))); do
  [ -f "$TMP/w$w/.fail" ] && { echo "алиасы: воркер $w упал по сбою селекта — прогон остановлен" >&2; exit 1; }
done
for w in $(seq 0 $((WORKERS - 1))); do
  s=$(cat "$TMP/w$w/.skipped" 2>/dev/null); case "$s" in ''|*[!0-9]*) s=0;; esac
  skipped=$((skipped + s))
  d=$(cat "$TMP/w$w/.done" 2>/dev/null); case "$d" in ''|*[!0-9]*) d=0;; esac
  [ "$d" -gt "$done_total" ] && done_total="$d"
done
# ── ДОБОР ВЕЛИЧИН: сущность описана, поля — нет ────────────────────────────────
# Первый проход берёт тех, кого ещё нет в словаре сущностей. Уже описанные
# (живой случай okna: сотни страниц без мер) в него не попадут, и словарь
# величин остался бы пустым навсегда. Здесь пачка — сущности с непустым
# алиасом записи, с величинами в данных и без единого непустого алиаса поля
# (пустышка старше retry переспрашивается). Алиасы сущности НЕ перезаписываются.
# 🔴 OFFSET МЕР — СВОЙ СЧЁТЧИК. done_total к этому моменту уже = число сущностей
# первого прохода; подставлять его в skip_rows мер при force=1 сдвинуло бы пул
# мер на весь entity-объём. done_measures стартует с 0 и растёт на BATCH пачки;
# при force=0 OFFSET в SQL = 0 (счётчик не используется). CAP по-прежнему
# смотрит на done_total (общий потолок прогона).
done_measures=0
while :; do
  over_budget && { echo "величины: бюджет $BUDGET с исчерпан — добор возьмёт следующий такт"; break; }
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
  # OFFSET только при force=1 (см. комментарий у entity-select выше).
  wa_progress_write "$TMP/.progress_meas" "$done_measures" "sel"
  psql_wa_tA -v batch="$BATCH" -v skip_rows="$done_measures" \
    -f "$HERE/wiki_alias_select_measure_batch.sql" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac
  {
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string field = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language into the output when the title is in another language). For EACH record: (1) aliases — ONLY everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). ALSO include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. ALSO include 1-2 spoken action/event forms people use when asking about events THIS kind of record captures, when such forms are natural for the type (same language as the title; same quality limits as other aliases; distinctive for THIS type among siblings in THIS batch — forms that equally fit a sibling go under notEnoughFor). Limits: 3 to 8 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Quantity names and field names go ONLY under quantities, never under aliases. BANS for aliases (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; words that equally fit a sibling in THIS batch (leave those out of aliases — put the distinction in notEnoughFor); jargon opaque to a non-developer. (2) quantities — for EVERY name from the input quantities list, copy that name EXACTLY and give 1-5 short names a person uses for that value (a noun, or a noun with the action/event word they say — e.g. spoken event forms for money totals), 1-3 words each, no sentences. Same bans as aliases. If a listed quantity has no clear everyday name, return it with an empty aliases array. (3) bestUsedFor — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks). No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). No office jargon gerunds. Prefer spoken wording over metadata wording. (4) notEnoughFor — two kinds of short strings, both required when applicable: (a) THEMATIC \"not me\" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. Hard format rule for EVERY notEnoughFor string: no commas and no parentheses inside the string (downstream stores arrays as comma-CSV). Use a dash or the word \"not\"/\"see\" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it. Global: if you are not sure a token or claim is correct — do not write it (omit; never guess). Do not invent quantities, flows, or sibling names that are not in the input. One structure example (English skeleton only; rewrite all strings into the title language of each real item): {\"entity\":\"catalog_counterparties\",\"aliases\":[\"buyers\",\"suppliers\",\"customers\"],\"quantities\":[{\"name\":\"Count\",\"aliases\":[\"headcount\",\"how many partners\"]}],\"bestUsedFor\":[\"how many customers\",\"who bought this month\"],\"notEnoughFor\":[\"not stock balances\",\"not price list\",\"Organizations - our own companies not trading partners\"]} Never copy the English example strings into the output when the title language is different — rewrite every string in the title language. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --retry-items-json 2 \
    --ans "$TMP/ans" --err "$TMP/err" || {
      # При force=1 mark_skip пул не сжимает → OFFSET двигаем и на осечке.
      skipped=$((skipped + 1))
      echo "величины: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
      done_measures=$((done_measures + BATCH))
      done_total=$((done_total + BATCH))
      wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
      [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
      continue
    }
  # rc0 + 0 величин = попытка (R4), зеркало entity-ветки выше.
  parse_out=$(python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json")
  echo "$parse_out"
  meas_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*величин: \([0-9][0-9]*\).*/\1/p' | tail -n1)
  case "$meas_n" in ''|*[!0-9]*) meas_n=0;; esac
  if [ "$meas_n" -eq 0 ]; then
    skipped=$((skipped + 1))
    echo "величины: пачка пропущена (rc0, разобрано 0)" >&2
    psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
    done_measures=$((done_measures + BATCH))
    done_total=$((done_total + BATCH))
    wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
    [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
    continue
  fi
  python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
  chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
  # Только величины. rows.json с алиасами сущности здесь намеренно не пишется в
  # ALIAS_TABLE: добор не имеет права перезаписать уже собранные описания записей.
  psql_wa -v measures_path="$TMP/measures.json" \
    -f "$HERE/wiki_alias_merge_measures.sql" 2>&1 | grep -i error
  have_m=$(psql_wa_tA -c "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''" 2>/dev/null)
  echo "величины: непустых в базе $have_m"
  done_measures=$((done_measures + BATCH))
  done_total=$((done_total + BATCH))
  wa_progress_write "$TMP/.progress_meas" "$done_measures" "meas"
done
# Отчёт качества init — после measure-добора, до purge/collision (plan-quality-report).
if ! wa_quality_report; then
  exit 1
fi
# ── ВТОРОЙ ПРОХОД: РАЗВЕСТИ ТЕХ, КОГО НАЗЫВАЮТ ОДИНАКОВО ────────────────────────────
# 🔴 Указание владельца 30.07: «если и там и там есть одно и то же описание, значит надо
# уточнить или правильно разложить через ллм, что это такое».
#
# Зачем. Первый проход набирает пачку по близости вектора названия, и пара, которую путают
# чаще всего, может в неё не попасть: [замер 30.07] `Партнеры` и `Контрагенты` описывались
# в РАЗНЫХ пачках, у обоих в алиасах оказались и «партнёр», и «контрагент», и «клиент», и
# друг о друге они молчали. Вопрос «сколько у нас партнёров» получил ответ про контрагентов
# (155 вместо 164) — притом что до этой правки отвечал верно.
#
# Здесь пачка набирается НЕ по близости, а по ФАКТУ СТОЛКНОВЕНИЯ: одно и то же слово ведёт
# в несколько сущностей. Это признак из данных, а не порог и не список слов.
# Пересчитывается на каждом круге: разведённые пары из списка уходят сами.
# :probe_table (PROBE_TABLE, умолч. search_alias_probe) — wiki_alias_init.sql (CREATE IF NOT EXISTS).
# Песочница задаёт свою PROBE_TABLE, чтобы не марать боевую память столкновений.
# Самоочистка probe — до if COLLISIONS (зеркало cycle): при COLLISIONS=0 чистка всё равно идёт.
wa_probe_purge
if [ "${WIKI_ALIAS_COLLISIONS:-1}" = "1" ]; then
  # 🔴 ПАМЯТЬ О ЗАДАННЫХ ВОПРОСАХ — ИНАЧЕ ПРОХОД НЕ СХОДИТСЯ. [замер 05.08, боевая база]
  # проход выбирал слово, спрашивал модель и обновлял `not_enough_for`. Но если модель не
  # ответила разбираемым JSON («разведено сущностей: 0») или ответила, не назвав само слово
  # в `not_enough_for`, слово оставалось спорным — и на следующем круге выбиралось СНОВА.
  # Круги упирались в предел (40 из 40) КАЖДЫЙ такт, а число алиасов стояло на 697 семь
  # тактов подряд: час вызовов модели за такт, ноль изменений. Это же и есть причина, по
  # которой не выполнялся п. 17 — час из двух с четвертью уходил сюда.
  #
  # Отметка ставится ДО вызова модели (как у пропущенной пачки первого прохода): осечка
  # модели тоже расходует попытку, иначе цикл снова закрутится на том же слове.
  # Ключ отметки — слово И ОТПЕЧАТОК НАБОРА сущностей, которые им называются. Появилась
  # новая сущность с тем же словом — отпечаток другой, вопрос задаётся заново. То есть это
  # не «спросили один раз и забыли», а «спросили про ЭТО столкновение».
  rounds=0 asked=0 stopped=""
  # [замер 14.09] ПАРАЛЛЕЛЬНЫЕ СЛОВА: одна пачка слова идёт ~10 мин (группа до
  # COLL_BATCH записей × 3 поля); хвост 230 слов последовательно — двое суток.
  # Очередь из COLL_WORKERS слов собирается быстрыми pick-ами (probe отмечает
  # каждое ДО вызова модели), генерация — параллельными субшеллами в
  # изолированных $TMP/cw$iq, а MERGE — строго последовательно после wait:
  # разные слова пересекаются по строкам сущностей, конкурентный MERGE терял
  # бы правки (read-modify-write одного поля).
  COLL_WORKERS="${WIKI_ALIAS_COLLISION_WORKERS:-3}"
  case "$COLL_WORKERS" in ''|*[!0-9]*) COLL_WORKERS=3;; esac
  [ "$COLL_WORKERS" -lt 1 ] && COLL_WORKERS=1
  # Предел кругов остаётся вторым ограничителем — на случай `WIKI_ALIAS_MAX_SEC=0`.
  while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]; do
    over_budget && { stopped=" (бюджет $BUDGET с исчерпан)"; break; }
    # ── сбор очереди: до COLL_WORKERS слов; pick последовательный (по одному
    # слову за psql), отметка probe в момент выбора — дублей слов в очереди нет.
    QWORDS="" Q=0
    for iq in $(seq 1 "$COLL_WORKERS"); do
      # красная red5: предел кругов не может быть перешагнут сбором очереди;
      # явное TARGET_WORD — ровно один слот (probe-фильтр в SQL при этом
      # выключен, дубль слова ушёл бы в параллель ×N).
      [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ] || break
      ROUND=$(psql_wa_tA -v batch="$COLL_BATCH" -v target_word="$TARGET_WORD" \
        -f "$HERE/wiki_alias_collision_round.sql" 2>/dev/null) || ROUND=""
      [ -z "$ROUND" ] && break
      WORD=${ROUND%%$'\t'*}
      rest=${ROUND#*$'\t'}
      FP=${rest%%$'\t'*}
      PAY=${rest#*$'\t'}
      WTMP="$TMP/cw$iq"; mkdir -p "$WTMP"
      [ "$(id -u)" = 0 ] && chown "$BOTUSER" "$WTMP" 2>/dev/null || true
      rm -f "$WTMP/rows.json"   # красная red5b: stale rows.json упавшего слова не должен попасть в merge
      printf '%s' "$PAY" > "$WTMP/pay"
      printf '%s' "$WORD" > "$WTMP/word"
      printf '%s' "$FP" > "$WTMP/fp"
      chmod 644 "$WTMP/pay" "$WTMP/word" "$WTMP/fp" 2>/dev/null
      QWORDS="$QWORDS $iq"
      Q=$((Q + 1))
      rounds=$((rounds + 1))
      [ -n "$TARGET_WORD" ] && break
    done
    [ "$Q" -eq 0 ] && break
    asked=$((asked + Q))
    # ── параллельная генерация слов очереди (изолированные $WTMP)
    _pg=""
    for iq in $QWORDS; do
      (
        WTMP="$TMP/cw$iq"
        WA_PROGRESS_FILE="$TMP/.progress_col_$iq"
        PAY=$(cat "$WTMP/pay" 2>/dev/null)
        case "$PAY" in ''|'[]'|'null') exit 0;; esac
        WORD=$(cat "$WTMP/word" 2>/dev/null)
        # «1 задача = 1 вызов»: collision-A/B/C → сборка (merge после wait).
        _CA="${_WA_COLL_A//<SHARED_WORD>/$WORD}"
        _CB="${_WA_COLL_B//<SHARED_WORD>/$WORD}"
        _CC="${_WA_COLL_C//<SHARED_WORD>/$WORD}"
        if ! parse_out=$(wa_infer_three_fields collision "$WTMP/pay" "$WTMP/coll" \
              "$WTMP/rows.json" "" "разведение" \
              "$_CA" "$_CB" "$_CC"); then
          echo "разведение: пачка пропущена (падение поля A/B/C)" >&2
          wa_progress_write "$WA_PROGRESS_FILE" 0 "col"
          exit 0
        fi
        echo "$parse_out"
        chmod 644 "$WTMP/rows.json" 2>/dev/null   # тот же случай, что в первом проходе
        wa_progress_write "$WA_PROGRESS_FILE" 1 "col"
      ) &
      _pg="$_pg $!"
    done
    # ждём только порождённых: голый wait ловит вечного наблюдателя (живая проба 15.09, стоп-при-тишине 129 с)
    [ -n "$_pg" ] && wait $_pg
    # ── MERGE+пометка строго последовательно: слова пересекаются по строкам сущностей.
    for iq in $QWORDS; do
      _pr=$(wa_probe_result_for "$TMP/cw$iq")
      WORD=$(cat "$TMP/cw$iq/word" 2>/dev/null || true)
      FP=$(cat "$TMP/cw$iq/fp" 2>/dev/null || true)
      wa_probe_mark "$WORD" "$FP" "$_pr"
    done
  done
  # Молчания тут быть не должно: видно и сколько спросили, и сколько ОСТАЛОСЬ на следующий
  # такт (упёрлись в предел кругов), и сколько столкновений модель разобрать не смогла —
  # они лежат в `$PROBE_TABLE` (умолч. search_alias_probe) и сами собой больше не переспрашиваются.
  left=$(psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql" 2>/dev/null)
  echo "разведение столкновений: кругов $rounds$stopped, спрошено слов $asked, осталось неспрошенных ${left:-?}"
  printf '%s\n' "${left:-}" > "$TMP/.collision_left_echo"
fi

[ "$skipped" -gt 0 ] && echo "алиасы: пачек пропущено из-за отказа модели: $skipped" >&2

# ── С5: периодическое доучивание (боковая таблица → сверка → MERGE подтверждённых) ─
# WIKI_ALIAS_REASK_EVERY=0 по умолчанию: живые базы не трогаются без явного env.
if [ "$REASK_EVERY" -gt 0 ] && [ "$WIKI_ALIAS_TICK" -gt 0 ] \
   && [ $(( WIKI_ALIAS_TICK % REASK_EVERY )) -eq 0 ]; then
  echo "reask: такт $WIKI_ALIAS_TICK, период $REASK_EVERY, таблица $REASK_TABLE" >&2
  psql "$DSN" -q -v ON_ERROR_STOP=1 \
    -v reask_table="$REASK_TABLE" \
    -v confirm_table="$CONFIRM_TABLE" \
    -v journal_table="$JOURNAL_TABLE" \
    -f "$HERE/wiki_alias_reask_init.sql" >/dev/null 2>&1
  POOL_JSON="$TMP/reask_pool.json"
  python3 "$(cd "$HERE/../.." && pwd)/work/pipeline/alias_reask_pool.py" \
    --out "$POOL_JSON" --dsn "$DSN" --alias-table "$ALIAS_TABLE" \
    --stale-days "$REASK_STALE_DAYS" \
    || echo "reask: пул кандидатов не собран — шаг пропущен" >&2
  if [ -s "$POOL_JSON" ]; then
    chmod 644 "$POOL_JSON" 2>/dev/null
    REASK_DONE=0
    while [ "$REASK_DONE" -lt "$REASK_CAP" ]; do
      over_budget && { echo "reask: бюджет $BUDGET с исчерпан" >&2; break; }
      wa_progress_write "$TMP/.progress_main" "$REASK_DONE" "sel"
      psql "$DSN" -tA -v ON_ERROR_STOP=1 \
        -v alias_table="$ALIAS_TABLE" \
        -v batch="$COLL_BATCH" \
        -v reask_stale_days="$REASK_STALE_DAYS" \
        -v pool_path="$POOL_JSON" \
        -f "$HERE/wiki_alias_reask_select_entity_batch.sql" > "$TMP/reask_pay" 2>/dev/null
      chmod 644 "$TMP/reask_pay" 2>/dev/null
      PAY=$(cat "$TMP/reask_pay")
      case "$PAY" in ''|'[]'|'null') break;; esac
      # «1 задача = 1 вызов»: init-A/B/C (тот же канон, что entity-init).
      WA_PROGRESS_FILE="$TMP/.progress_main"
      if ! parse_out=$(wa_infer_three_fields init "$TMP/reask_pay" "$TMP/reask" \
            "$TMP/reask_rows.json" "$TMP/reask_meas.json" "reask" \
            "$_WA_INIT_A" "$_WA_INIT_B" "$_WA_INIT_C"); then
        echo "reask: пачка пропущена (падение поля A/B/C)" >&2
        continue
      fi
      echo "$parse_out"
      ents_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*алиасов разобрано: \([0-9][0-9]*\).*/\1/p' | tail -n1)
      case "$ents_n" in ''|*[!0-9]*) ents_n=0;; esac
      if [ "$ents_n" -eq 0 ]; then
        skipped=$((skipped + 1))
        echo "reask: пачка пропущена (rc0, разобрано 0)" >&2
        psql_wa -v pay_path="$TMP/reask_pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
        REASK_DONE=$((REASK_DONE + COLL_BATCH))
        continue
      fi
      chmod 644 "$TMP/reask_rows.json" "$TMP/reask_meas.json" 2>/dev/null
      # Боковая таблица: полный ответ модели (не основной словарь).
      psql "$DSN" -q -v ON_ERROR_STOP=1 \
        -v alias_table="$REASK_TABLE" \
        -v measure_table="$MEASURE_TABLE" \
        -v rows_path="$TMP/reask_rows.json" \
        -v measures_path="$TMP/reask_meas.json" \
        -v force="${WIKI_ALIAS_FORCE:-0}" \
        -f "$HERE/wiki_alias_merge_entity.sql" 2>&1 | grep -i error || true
      # Сверка: только подтверждённые связи дописываются в основной словарь.
      python3 "$(cd "$HERE/../.." && pwd)/work/pipeline/alias_reask_confirm.py" \
        --rows-path "$TMP/reask_rows.json" \
        --confirmed-out "$TMP/reask_confirmed.json" \
        --journal-out "$TMP/reask_rejected.json" \
        --dsn "$DSN" --alias-table "$ALIAS_TABLE" \
        --confirm-table "$CONFIRM_TABLE" --apply \
        || echo "reask: сверка не прошла" >&2
      if [ -s "$TMP/reask_confirmed.json" ]; then
        psql "$DSN" -q -v ON_ERROR_STOP=1 \
          -v alias_table="$ALIAS_TABLE" \
          -v rows_path="$TMP/reask_confirmed.json" \
          -f "$HERE/wiki_alias_reask_merge_confirmed.sql" 2>&1 | grep -i error || true
      fi
      if [ -s "$TMP/reask_rejected.json" ]; then
        psql "$DSN" -q -v ON_ERROR_STOP=1 \
          -v journal_table="$JOURNAL_TABLE" \
          -v journal_path="$TMP/reask_rejected.json" \
          -f "$HERE/wiki_alias_reask_journal.sql" 2>&1 | grep -i error || true
      fi
      REASK_DONE=$((REASK_DONE + COLL_BATCH))
    done
    echo "reask: обработано пачек до $REASK_DONE сущностей" >&2
  fi
fi

# Итог «алиасов в базе» — wiki_alias_publish.sql (stats + REFRESH, не в tx с INSERT).
# Внутри publish: VACUUM (REFRESH_TABLE) $ALIAS_TABLE.
wa_progress_write "$TMP/.progress_main" 0 "pub"
psql_wa -f "$HERE/wiki_alias_publish.sql" \
  || echo "алиасы: VACUUM (REFRESH_TABLE) $ALIAS_TABLE не прошёл" >&2

# ── §7 / §7bis: подписи веток развилок (day-basis + src) ───────────────────────
# Классы day-basis пишет детектор в search_fork_class с src_set=calendar_days,working_days
# (id веток, не таблицы данных). Тот же контур, что branch_alias.sh: агент OpenClaw,
# branch_alias_parse, MERGE в search_fork_label. Русских подписей в коде нет.
FORK_CLASS_TABLE="${FORK_CLASS_TABLE:-search_fork_class}"
FORK_LABEL_TABLE="${FORK_LABEL_TABLE:-search_fork_label}"
DAY_BASIS_FORK_BATCH="${DAY_BASIS_FORK_BATCH:-10}"
DAY_BASIS_FORK_RETRY_H="${DAY_BASIS_FORK_RETRY_H:-$RETRY_H}"
DAY_BASIS_FORK_MAX_SEC="${DAY_BASIS_FORK_MAX_SEC:-60}"
DAY_BASIS_IDS="'calendar_days','working_days'"
t_fork_start=$(date +%s)
fork_over_budget() {
  [ "$DAY_BASIS_FORK_MAX_SEC" != "0" ] \
    && [ $(( $(date +%s) - t_fork_start )) -ge "$DAY_BASIS_FORK_MAX_SEC" ]
}
psql_wa -v fork_class_table="$FORK_CLASS_TABLE" -v fork_label_table="$FORK_LABEL_TABLE" \
  -f "$HERE/wiki_alias_fork_init.sql" >/dev/null 2>&1
mark_day_fork_attempt() {
  psql_wa -v fork_label_table="$FORK_LABEL_TABLE" -v flat_path="$TMP/dayforkflat" \
    -f "$HERE/wiki_alias_dayfork_mark.sql" >/dev/null 2>&1
}
day_fork_done=0
while :; do
  fork_over_budget && break
  wa_progress_write "$TMP/.progress_main" "$day_fork_done" "dayfork"
  BUNDLE=$(psql_wa_tA \
    -v fork_class_table="$FORK_CLASS_TABLE" \
    -v fork_label_table="$FORK_LABEL_TABLE" \
    -v fork_batch="$DAY_BASIS_FORK_BATCH" \
    -v fork_retry_h="$DAY_BASIS_FORK_RETRY_H" \
    -v day_basis_ids="$DAY_BASIS_IDS" \
    -f "$HERE/wiki_alias_dayfork_batch.sql" 2>/dev/null) || BUNDLE=""
  [ -z "$BUNDLE" ] && break
  DF_PAY=${BUNDLE%%$'\t'*}
  DF_FLAT=${BUNDLE#*$'\t'}
  printf '%s' "$DF_PAY" > "$TMP/dayforkpay"
  printf '%s' "$DF_FLAT" > "$TMP/dayforkflat"
  chmod 644 "$TMP/dayforkpay" "$TMP/dayforkflat" 2>/dev/null
  case "$DF_PAY" in ''|'[]'|'null') break;; esac
  {
    printf '%s' "JSON only, no prose, no code fences. Below are FORK CLASSES with day-basis branches of one database. Each class is one period window and one measure context; branches are machine ids calendar_days (all calendar dates in the window) and working_days (only working dates per the calendar register in data). For EVERY branch id of EVERY class write a short label that tells a person HOW the number was counted for that branch — not repeating the id. Use the SAME language as the measure field. Keys in labels are the branch ids exactly (the src field). Schema: {\"forks\":[{\"fork_key\":\"<copy exactly>\",\"labels\":{\"<branch id exactly>\":\"<label>\"}}]}. Input: "
    cat "$TMP/dayforkpay"
  } > "$TMP/dayforkmsg"
  chmod 644 "$TMP/dayforkmsg"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/dayforkmsg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --ans "$TMP/dayforkans" --err "$TMP/dayforkerr" || {
      if python3 ./branch_alias_parse.py --infra-check "$TMP/dayforkerr" "$TMP/dayforkans" 2>/dev/null; then
        echo "day-basis развилки: прогон прерван — инфра/биллинг" >&2
        break
      fi
      echo "day-basis развилки: пачка пропущена ($(head -c 120 "$TMP/dayforkerr" | tr -d '\n'))" >&2
      mark_day_fork_attempt
      continue
    }
  if python3 ./branch_alias_parse.py --infra-check "$TMP/dayforkerr" "$TMP/dayforkans" 2>/dev/null; then
    echo "day-basis развилки: прогон прерван — инфра в ответе" >&2
    break
  fi
  python3 ./branch_alias_parse.py "$TMP/dayforkans" "$TMP/dayforkpay" "$TMP/dayforkrows.json" >/dev/null 2>&1 || true
  chmod 644 "$TMP/dayforkrows.json" 2>/dev/null
  psql_wa -v fork_label_table="$FORK_LABEL_TABLE" -v rows_path="$TMP/dayforkrows.json" \
    -f "$HERE/wiki_alias_dayfork_merge.sql" 2>&1 | { grep -i error || true; }
  mark_day_fork_attempt
  day_fork_done=$((day_fork_done + 1))
done
# Обычные src/окно классы — тот же штатный генератор (рядом, не вместо systemd-юнита).
if [ -x ./branch_alias.sh ]; then
  wa_progress_write "$TMP/.progress_main" 0 "branch"
  BRANCH_ALIAS_MAX_SEC="${BRANCH_ALIAS_MAX_SEC:-60}" ./branch_alias.sh "${BRANCH_ALIAS_CAP:-10}" \
    || echo "развилки src: шаг не прошёл, такт продолжается" >&2
fi

# ── Ф6.3: Solr-словарь синонимов из таблиц (не списки в коде) ─────────────────
# SELECT → карта → DROP+CREATE файлом (argv ломается на длинной карте, фактура §5.3).
# Пустые источники — словарь не трогаем. Лимит сверх фактуры — честная ошибка.
# 🔴 ИСТОЧНИК — ВСЕГДА БОЕВАЯ ТАБЛИЦА, ДАЖЕ В ПОБОЧНОМ ПРОГОНЕ. [замер 29.08]
# Прогон юнита с ALIAS_TABLE=alias_okna_c5 (28.08 20:58) пересобрал ЖИВОЙ
# search_dict_syn правилами побочной таблицы — ранжирование в бою деградировало
# («сколько клиентов реально покупали…» → 2 · Валюты вместо 141 · Контрагенты).
# Побочная таблица — черновик генератора; живой словарь имеет право меняться
# только вслед за боевой (MERGE «только пустые строки» → пересборка из боевой).
SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-${SOLR_SYN_DICT:-search_dict_syn}}"
DICT_LOCALE="${SEARCH_DICT_LOCALE:-ru_RU.utf8}"
# Тот же путь, что build.sh:511-517 — без Python-посредника. Fail-closed: юнит и ручной
# прогон не маскируют битый словарь. alias_table жёстко search_entity_alias (см. выше).
wa_progress_write "$TMP/.progress_main" 0 "solr"
psql "$DSN" -q \
  -v dict_locale="$DICT_LOCALE" \
  -v solr_syn_dict="$SOLR_SYN_DICT" \
  -v alias_table="search_entity_alias" \
  -f "$HERE/solr_synonyms_compile.sql" \
  || { echo "solr synonyms: компиляция не прошла ($SOLR_SYN_DICT)" >&2; exit 1; }
