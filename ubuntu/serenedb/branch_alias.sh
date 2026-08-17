#!/bin/bash
# ЧЕЛОВЕЧЕСКИЕ ПОДПИСИ ВЕТОК РАЗВИЛОК — ШТАТНЫМ АГЕНТОМ OPENCLAW.
#
# 🔴 ЗАЧЕМ. План `docs/PLAN_ANSWER_CONTRACT.md` §7, аудит §12: ручная разметка
# отвергнута (третье ручное действие не существует на холодном старте). Подпись вида
# «Реализация ТМЦ (документ)» не говорит человеку «это отгрузки, а не оплаты».
# Класс развилки (множество источников, по которым один вопрос даёт РАЗНЫЕ числа)
# фиксирует детектор ответного контура в `search_fork_class`; этот скрипт один раз
# спрашивает у агента смысл каждой ветки и кладёт подписи в `search_fork_label`.
# Рендер веток читает словарь кодом; класса в словаре нет — честный C, не догадка.
#
# 🔴 ПОЧЕМУ АГЕНТОМ. Та же причина, что у `wiki_alias.sh`: `openclaw agent` — штатный
# неинтерактивный прогон через шлюз; модель, ключ и учёт берутся из его конфигурации.
#
# 🔴 УНИВЕРСАЛЬНОСТЬ. В скрипте нет ни одного имени сущности и ни одного слова
# конкретной базы. Модели уходят ТОЛЬКО имена: метки источников (search_tables),
# описания «на что отвечает» (search_entity_alias) и имя величины развилки — никаких
# значений данных, ни сумм, ни счётов (п. 19). Отвечать её просят «на том же языке,
# что названия» — на английской базе выйдут английские подписи без правки кода.
#
# Идемпотентно: спрашиваются только классы, у которых НЕ все ветки имеют непустую
# подпись. Пустая запись — это ПОПЫТКА, а не ответ (та же семантика, что в
# `wiki_alias.sh`): переспрашивается, но не чаще RETRY_H часов, чтобы модель не
# жглась на классе, который она и правда не может описать.
# Использование: branch_alias.sh [классов за прогон]   (0 или пусто = все оставшиеся)
set -u
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
BOTUSER="${OPENCLAW_USER:-undebot}"
# 🔴 КАК ЗАПУСКАТЬ ОТ ИМЕНИ БОТА — РЕШАЕТСЯ ПО ОКРУЖЕНИЮ (как в `wiki_alias.sh`), но с
# одним добавлением: OPENCLAW_RUNAS, заданная ПУСТОЙ, означает прямой вызов. На деве
# CLI достаёт шлюз и без профиля бота [замер 15.08: `openclaw agent` из-под claudedev
# ответил, модель deepseek-v4-pro], а `sudo` рабочей сессии закрыт средой — без этого
# выбора прогон на деве упирался бы в пароль.
if [ "${OPENCLAW_RUNAS+x}" = "x" ]; then
  read -r -a RUNAS_BOT <<< "$OPENCLAW_RUNAS"
elif [ "$(id -un)" = "$BOTUSER" ]; then
  RUNAS_BOT=()
elif [ "$(id -u)" = 0 ] && command -v runuser >/dev/null 2>&1; then
  RUNAS_BOT=(runuser -u "$BOTUSER" --)
else
  RUNAS_BOT=(sudo -u "$BOTUSER" -H)
fi
# Сколько классов за одно обращение к модели. Класс несёт свои ветки (обычно 2-4
# источника), поэтому десяток классов — это десятки подписей за вызов.
BATCH="${BRANCH_ALIAS_BATCH:-10}"
SRC_CHUNK="${BRANCH_ALIAS_SRC_CHUNK:-40}"
case "$SRC_CHUNK" in ''|*[!0-9]*) SRC_CHUNK=40;; esac
RETRY_H="${BRANCH_ALIAS_RETRY_H:-6}"
case "$RETRY_H" in ''|*[!0-9]*) RETRY_H=6;; esac
# 🔴 КУДА ПИСАТЬ. Умолчание — боевые таблицы; своё имя нужно, чтобы пробу словаря
# вести РЯДОМ, не трогая тот словарь, по которому отвечает бот (та же ручка, что
# ALIAS_TABLE у `wiki_alias.sh`).
FORK_CLASS_TABLE="${FORK_CLASS_TABLE:-search_fork_class}"
FORK_LABEL_TABLE="${FORK_LABEL_TABLE:-search_fork_label}"
CAP="${1:-0}"
cd "$(dirname "$0")" || exit 1

# 🔴 vLLM для словарей [17.08]: патч allowlist шлюза undebot (идемпотентно, бэкап).
# Ключ/URL — из EnvironmentFile embed; без sudo, от undebot через runuser.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/../openclaw/ensure_vllm_gateway.sh" || echo "развилки: ensure_vllm — предупреждение (см. stderr)" >&2

command -v openclaw >/dev/null 2>&1 || { echo "развилки: openclaw не установлен — шаг пропущен"; exit 0; }
# 🔴 DDL ДЕРЖИТСЯ И ЗДЕСЬ, а не только в `corpus_init.sql`: на базе без свежего init
# контур иначе молча мёртв. GRANT — сразу: без него рендер ловит permission denied и
# считает «развилок нет» при живом словаре (та же грабля, что у алиасов, HOW_NOT_TO §2.9).
# Схема `search_fork_class` — ровно та, что пишет детектор (`serene_ask.py`, `_fork_log`):
# колонка `measure_ctx` и UNIQUE на fork_key (его INSERT … ON CONFLICT без уникальной
# цели конфликта отвергается движком — замер 16.08). INSERT/UPDATE для serene_ro —
# единственное исключение из read-only: журнал пишет тот же DSN, что читает (подробнее —
# `corpus_init.sql`).
psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS $FORK_CLASS_TABLE (fork_key VARCHAR UNIQUE, src_set VARCHAR, measure_ctx VARCHAR, seen_at TIMESTAMP, seen_count INTEGER)" >/dev/null 2>&1
psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS $FORK_LABEL_TABLE (fork_key VARCHAR, src VARCHAR, label VARCHAR, seen_at TIMESTAMP)" >/dev/null 2>&1
psql "$DSN" -q -c "GRANT SELECT, INSERT, UPDATE ON $FORK_CLASS_TABLE TO serene_ro" >/dev/null 2>&1
psql "$DSN" -q -c "GRANT SELECT ON $FORK_LABEL_TABLE TO serene_ro" >/dev/null 2>&1

# 🔴 ОБМЕН ФАЙЛАМИ — ТОЛЬКО ЧЕРЕЗ КАТАЛОГ, ЧИТАЕМЫЙ ДВИЖКОМ (как в `wiki_alias.sh`):
# `read_json` из /tmp процесс serened не видит.
EXCH="${CSV_DIR:-/var/lib/serenedb}"
TMP=$(mktemp -d "$EXCH/branch-alias-XXXXXX") || { echo "развилки: нет доступа к $EXCH" >&2; exit 0; }
chmod 755 "$TMP"; trap 'rm -rf "$TMP"' EXIT
done_total=0
skipped=0
aborted_infra=0

# 🔴 БЮДЖЕТ ВРЕМЕНИ, А НЕ ЧИСЛО КРУГОВ (та же причина, что в `wiki_alias.sh`): шаг
# обязан укладываться в такт свежести (п. 17 TARGET.md), а цена круга — это цена
# ответа модели сегодня. Не успевшее за бюджет возьмёт следующий такт.
BUDGET="${BRANCH_ALIAS_MAX_SEC:-120}"
t_start=$(date +%s)
over_budget() { [ "$BUDGET" != "0" ] && [ $(( $(date +%s) - t_start )) -ge "$BUDGET" ]; }

# 🔴 Свежий transcript на каждый прогон: битая сессия `branch-alias` от
# биллингового прогона 16.08 ловила TranscriptNotContinuableError [17.08].
BRANCH_ALIAS_SESSION="${BRANCH_ALIAS_SESSION_KEY:-branch-alias-$(date +%Y%m%d-%H%M%S)}"
# Модель и thinking — через infer model run (замер 17.08). Умолчание транспорта
# — --gateway; BRANCH_ALIAS_INFER=local обходит потолок RPC шлюза 120 с
# (cli/infer.md; замер 17.08 okna). Модель — vLLM Qwen3.8-27B (0 $);
# DeepSeek pro — через BRANCH_ALIAS_MODEL.
BRANCH_ALIAS_MODEL="${BRANCH_ALIAS_MODEL:-vllm/Qwen3.8-27B}"
BRANCH_ALIAS_THINKING="${BRANCH_ALIAS_THINKING:-off}"
ZERO_STREAK_MAX="${BRANCH_ALIAS_ZERO_STREAK_MAX:-3}"
zero_streak=0

# Отбор: класс с неподписанными ветками; за один вызов модели — не больше
# SRC_CHUNK веток (на ut_test класс может нести сотни источников [17.08]).
NEED_SQL="
  WITH need AS (
    SELECT c.fork_key, c.src_set, c.measure_ctx
    FROM $FORK_CLASS_TABLE c
    WHERE EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE NOT EXISTS (
        SELECT 1 FROM $FORK_LABEL_TABLE l
        WHERE l.fork_key = c.fork_key AND l.src = trim(x.s, '{} ')
          AND (coalesce(l.label, '') <> ''
               OR l.seen_at > now() - INTERVAL $RETRY_H HOUR)))
    ORDER BY c.fork_key
    LIMIT $BATCH),
  raw_srcs AS (
    SELECT n.fork_key, n.measure_ctx, trim(x.s, '{} ') AS src
    FROM need n, unnest(str_split(n.src_set, ',')) AS x(s)
    WHERE NOT EXISTS (
      SELECT 1 FROM $FORK_LABEL_TABLE l
      WHERE l.fork_key = n.fork_key AND l.src = trim(x.s, '{} ')
        AND (coalesce(l.label, '') <> ''
             OR l.seen_at > now() - INTERVAL $RETRY_H HOUR))),
  srcs AS (
    SELECT fork_key, measure_ctx, src
    FROM (
      SELECT fork_key, measure_ctx, src,
             row_number() OVER (PARTITION BY fork_key ORDER BY src) AS rn
      FROM raw_srcs) z
    WHERE rn <= $SRC_CHUNK)"

# 🔴 ОТМЕТКА ПОПЫТКИ — MERGE, А НЕ «INSERT ГДЕ НЕТ». [замер 15.08, дым на ut_test]
# INSERT с NOT EXISTS пропускал ветку, у которой пустышка УЖЕ лежит, но протухла:
# отметка не обновлялась, отбор на следующем круге брал тот же класс снова — цикл
# жёг вызовы агента, пока не кончился бюджет (377 вызовов-заглушек за 120 с; спас
# только бюджет времени). MERGE обновляет seen_at существующей пустышки и не трогает
# живую подпись (условный WHEN MATCHED — доки SereneDB, Sql › Statements › MERGE INTO).
mark_attempt() {
  psql "$DSN" -q -c "
    MERGE INTO $FORK_LABEL_TABLE t
    USING (SELECT fork_key, src, '' AS label, now() AS seen_at
           FROM read_json('$TMP/payflat', columns := {fork_key:'VARCHAR', src:'VARCHAR'})) p
    ON (t.fork_key = p.fork_key AND t.src = p.src)
    WHEN MATCHED AND coalesce(t.label, '') = '' THEN UPDATE SET seen_at = p.seen_at
    WHEN NOT MATCHED THEN INSERT" >/dev/null 2>&1
}

while :; do
  over_budget && { echo "развилки: бюджет $BUDGET с исчерпан — остальные классы возьмёт следующий такт"; break; }
  # Пачка классов с ветками: метка источника и его «на что отвечает» — это всё,
  # что видит модель. Значений данных здесь нет и быть не должно (п. 19).
  psql "$DSN" -tA -c "$NEED_SQL
    SELECT to_json(list(struct_pack(fork_key := fork_key, measure := measure,
                                    sources := items)))
    FROM (SELECT s.fork_key, max(s.measure_ctx) AS measure,
                 list(struct_pack(src := s.src,
                                  title := coalesce(t.label, s.src),
                                  bestUsedFor := coalesce(a.best_used_for, ''))
                      ORDER BY s.src) AS items
          FROM srcs s
          LEFT JOIN search_tables t ON t.src_table = s.src
          LEFT JOIN search_entity_alias a ON a.src_table = s.src
          GROUP BY s.fork_key
          ORDER BY s.fork_key) z" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac
  # Плоский список пар (fork_key, src) той же пачки — для отметки попытки: и при
  # осечке модели, и для веток, которые модель обошла молча. Без второго случая
  # цикл крутился бы на одном классе, пока не кончится бюджет.
  psql "$DSN" -tA -c "$NEED_SQL
    SELECT to_json(list(struct_pack(fork_key := fork_key, src := src))) FROM srcs" \
    > "$TMP/payflat" 2>/dev/null
  chmod 644 "$TMP/payflat" 2>/dev/null

  # 🔴 ЗАДАНИЕ ПЕРЕДАЁТСЯ ФАЙЛОМ, А НЕ АРГУМЕНТОМ (как в `wiki_alias.sh`): длинный
  # JSON в argv не доходит, у `openclaw agent` есть штатный `--message-file`.
  {
    printf '%s' "JSON only, no prose, no code fences. Below are FORK CLASSES of one database. Each class lists record types (sources) whose data OVERLAP: the same business fact can be read from any of them, and totals by the shown measure DIFFER between them, so a person asking about that measure must choose a branch. For EVERY source of EVERY class write a short label that says what these records MEAN for the business — what kind of fact it is, and how it differs from the other sources of the same class; the person already sees the type name, so the label must add the meaning, not repeat the name. Use the SAME language as the titles. Keys in labels are the technical source identifiers (the \"src\" field); each source also carries a human title, which is shown to the person separately and is not a key. Schema: {\"forks\":[{\"fork_key\":\"<copy exactly>\",\"labels\":{\"<technical source id exactly>\":\"<label>\"}}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  t_agent=$(date +%s)
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$BRANCH_ALIAS_MODEL" --thinking "$BRANCH_ALIAS_THINKING" \
    --ans "$TMP/ans" --err "$TMP/err" || {
      # 🔴 Биллинг, lock шлюза, summarization — не ответ модели: попытку не
      # списываем, пустышек не пишем, прогон прерываем (замер 17.08: 75 732
      # пустых label после billing error).
      if python3 ./branch_alias_parse.py --infra-check "$TMP/err" "$TMP/ans" 2>/dev/null; then
        aborted_infra=1
        echo "развилки: прогон прерван — инфра/биллинг ($(head -c 160 "$TMP/err" | tr -d '\n'))" >&2
        break
      fi
      # Иная осечка (таймаут без признаков инфры и т.п.) — попытка, RETRY_H.
      skipped=$((skipped + 1))
      echo "развилки: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      mark_attempt
      continue
    }

  # Ответ с кодом 0, но текст — служебная ошибка шлюза/провайдера.
  wall_ms=$(( ($(date +%s) - t_agent) * 1000 ))
  if python3 ./branch_alias_parse.py --infra-check "$TMP/err" "$TMP/ans" 2>/dev/null; then
    aborted_infra=1
    echo "развилки: прогон прерван — инфра/биллинг в ответе агента" >&2
    break
  fi

  # Разбор ответа модели — своим кодом это разрешено (п. 20: проверка ответа модели).
  # В словарь попадают только пары (fork_key, src) из входной пачки с непустой
  # подписью; чужой класс и выдуманная ветка отбрасываются разбором.
  parsed_n=$(python3 ./branch_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" | awk '{print $NF}')
  case "$parsed_n" in ''|*[!0-9]*) parsed_n=0;; esac
  python3 ./alias_usage_log.py --contour branch --ans "$TMP/ans" \
    --model "$BRANCH_ALIAS_MODEL" --wall-ms "$wall_ms" --parsed "$parsed_n" 2>/dev/null || true
  if [ "$parsed_n" -eq 0 ]; then
    zero_streak=$((zero_streak + 1))
    if [ "$zero_streak" -ge "$ZERO_STREAK_MAX" ]; then
      echo "развилки: $zero_streak пачек подряд без разбора — стоп (окно B)" >&2
      break
    fi
  else
    zero_streak=0
  fi
  # 🔴 ФАЙЛ ЧИТАЕТ ДВИЖОК, А НЕ МЫ: права — рядом с записью (живой случай okna 13.08
  # у словаря сущностей: файл 600 root → «Permission denied» при исправной модели).
  chmod 644 "$TMP/rows.json" 2>/dev/null
  # Запись — ОДНИМ MERGE из файла, без цикла по строкам (п. 20; доки SereneDB, Sql ›
  # Statements › MERGE INTO — первичного ключа у таблицы нет, ключ пары в ON).
  # MERGE, а не DELETE+INSERT: класс может быть подписан ЧАСТИЧНО (модель назвала не
  # все ветки), и перезапись подписанной ветки новой редакцией того же ответа —
  # штатный случай, а не конфликт.
  psql "$DSN" -q -c "
    MERGE INTO $FORK_LABEL_TABLE t
    USING (SELECT fork_key, src, label, now() AS seen_at
           FROM read_json('$TMP/rows.json',
             columns := {fork_key:'VARCHAR', src:'VARCHAR', label:'VARCHAR'})) n
    ON (t.fork_key = n.fork_key AND t.src = n.src)
    WHEN MATCHED THEN UPDATE SET label = n.label, seen_at = n.seen_at
    WHEN NOT MATCHED THEN INSERT" 2>&1 | { grep -i error || true; }
  # Ветки, которые модель обошла или подписала пустым, помечаются попыткой — иначе
  # следующий круг этого же прогона спросит их снова, и так до конца бюджета.
  mark_attempt

  done_total=$((done_total + BATCH))
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
done

[ "$skipped" -gt 0 ] && echo "развилки: пачек пропущено из-за отказа модели: $skipped" >&2
[ "$aborted_infra" -gt 0 ] && echo "развилки: прогон прерван по инфра/биллингу — попытки не списаны" >&2
# Молчания быть не должно: видно и покрытие, и пустышки-attempt'ы.
psql "$DSN" -tA -F' | ' -c "
  SELECT 'классов развилок в базе', count(*) FROM $FORK_CLASS_TABLE
  UNION ALL SELECT 'классов, покрытых подписями ЦЕЛИКОМ', count(*) FROM (
    SELECT c.fork_key FROM $FORK_CLASS_TABLE c
    WHERE NOT EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE NOT EXISTS (SELECT 1 FROM $FORK_LABEL_TABLE l
                        WHERE l.fork_key = c.fork_key AND l.src = trim(x.s, '{} ')
                          AND coalesce(l.label, '') <> ''))
    GROUP BY c.fork_key) q
  UNION ALL SELECT 'непустых подписей веток', count(*) FROM $FORK_LABEL_TABLE
    WHERE coalesce(label, '') <> ''
  UNION ALL SELECT 'пустышек (модель не ответила)', count(*) FROM $FORK_LABEL_TABLE
    WHERE coalesce(label, '') = ''"

[ "$aborted_infra" -gt 0 ] && exit 2
exit 0
