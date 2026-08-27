#!/bin/bash
# Досчитать векторы тем строкам, у которых их нет — штатной функцией движка `ai_embed`.
#
# Почему это shell, а не SQL одним запросом: оператор с `ai_embed` нельзя делать большим.
# 🔴 ПРЕДЕЛ — У ДВИЖКА, А НЕ У ПРОВАЙДЕРА. Прежняя версия этого комментария говорила, что
# режем из-за облачного провайдера («не больше 10 за раз и не длиннее 33 000 символов,
# иначе `batch size is invalid`», [замер 27.07]). Это было верно для того облака и неверно
# как объяснение: [замер 20.08, klient-1, своя карта без ограничений на вход] оператор,
# отдающий больше ~16-32 строк с колонкой `FLOAT[1024]`, роняет ЗАПРОС независимо от
# провайдера — `Vector::SetSize out of range - trying to set size to 2097152 for vector
# with capacity 16384` (2 097 152 = 2048 × 1024, то есть полный блок обработки движка).
# Воспроизводится и в `CREATE TABLE AS`, и в `UPDATE ... SET emb = ai_embed(...)`.
# Поэтому пачка в 16 строк — не наследие облака, а рабочий предел сборки 26.07.3, и
# поднимать её нельзя. Разбор целиком — `docs/EMBED_BULK_HOWTO.md`.
# Данные при этом НЕ покидают движок: текст берётся и вектор кладётся внутри базы,
# наружу уходит только вызов модели, что п. 20 разрешает явно.
#
# 🔴 ПАРАЛЛЕЛЬНОСТЬ ОГРАНИЧЕНА `threads`, А НЕ ПРОВАЙДЕРОМ. Прежняя версия писала «12
# потоков — около 30 строк/с, дальше упирается в провайдера» — неверно: доки говорят
# «each SereneDB thread can make at most one HTTP request at a time»
# (`cookbook/performance/how_to_tune_workloads#querying-remote-files`), и [замер 20.08]
# при 42 работающих потоках наружу уходило РОВНО `threads` = 18 запросов, ни одним больше.
# Число воркеров сверх `threads` не даёт ничего — они стоят в очереди. Доки советуют
# `threads` в 2-5 раз больше числа ядер; выше — упирается в память (см. HOWTO §3.5).
#
# 🔴 Э1 (п. 20): ОДНА сессия psql на раунд, без веера внешних клиентов.
# Прежний веер `WORKERS` фоновых `psql` запрещён контрактом поимённо («psql в цикле»).
# Параллельность HTTP — только `SET threads` внутри этой сессии (Sql › SET / Pragmas ›
# threads; AI Functions: каждый ai_embed = network request). Разовая сборка с ATTACH на
# поток — `embed_bulk.sh` / `docs/EMBED_BULK_HOWTO.md`, не этот скрипт.
# Staging `${TAG}_part_0` + transfer в конце — докатка оплаченного при обрыве; прямых
# параллельных UPDATE в целевую таблицу нет ([замер 28.07] SIGSEGV на 26.07.3).
# [замер 27.08 okna 26.08.1] UPDATE … ai_embed::FLOAT[1024] на 8…256 строк в боковой
# таблице — без Vector::SetSize; пачки всё равно режем (бюджет символов / дельта такта).
#
# 🔴 ОЧЕРЁДНОСТЬ, А НЕ ОТБОР. `ROWS_WHERE` сужает ЭТОТ прогон до части строк, чтобы
# вызывающий мог посчитать сначала то, о чём спрашивают, а потом остальное. Это не фильтр
# полноты (п. 13) сам по себе: КОМУ вектор положен, решает вызывающий. С 29.07 служебным
# сущностям он не считается вовсе (решение владельца), и это НЕ молчаливая потеря —
# отсутствие вектора названо причиной в переписи (`cov_noemb_service`), а сами строки
# лежат в корпусе и в текстовом индексе, то есть находятся по словам. Сужение сделано условием, а НЕ пересортировкой: `chunk` монотонен в
# физическом порядке ключа, на этом стоят зонные карты и выборка пачки за миллисекунду
# ([замер] 0,45–1,36 мс на 97 965 строках). Сортировка по приоритету это сломала бы.
#
# Использование: embed_missing.sh <таблица> <выражение-источник> [игнор-воркеров] [ключ,через,запятую]
# 3-й аргумент раньше был числом внешних psql; с Э1 игнорируется (совместимость argv build.sh).
set -u
TBL="$1"; SRC="$2"; N="${3:-1}"; KEY="${4:-}"
ROWS_WHERE="${ROWS_WHERE:-}"
[ -n "$ROWS_WHERE" ] && ROWS_WHERE="AND ($ROWS_WHERE)"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
MODEL="${EMBED_MODEL:-text-embedding-v4}"
# Имя секрета несёт базу: секреты у движка ОБЩИЕ НА ИНСТАНС ([замер 29.07]
# `ai_embed: secret 'qwen' not found` посреди чужого такта). Несколько ключей облака
# крутил прежний веер psql; для такта берём первый секрет, ротация — в embed_bulk.
read -r -a SECRETS <<< "${EMBED_SECRETS:-${EMBED_SECRET:-qwen}}"
NSEC=${#SECRETS[@]}
SEC0="${SECRETS[0]}"
DIM="${EMBED_DIM:-1024}"
if [ "${N:-1}" -gt 1 ] 2>/dev/null; then
  echo "embed_missing: внешние WORKERS=$N игнорируются (Э1: одна сессия psql; параллель = SET threads)" >&2
fi

# 🔴 МЕТКА ПОСТОЯННАЯ, ПО ИМЕНИ ТАБЛИЦЫ, а не `emb_$$`. С меткой по номеру процесса
# следующий запуск имел другой номер и НЕ находил недоделанное предыдущим: посчитанные
# векторы оставались лежать в осиротевших таблицах, а строки считались заново.
# [замер 28.07] в базе нашлось 224 719 таких строк ≈ 0,9 ГБ. С постоянной меткой
# прерванный прогон ДОКАТЫВАЕТСЯ следующим, а не выбрасывается.
#
# 🔴 И ПО ИМЕНИ БАЗЫ. Указание владельца 29.07: «разве так сложно отдельные таблицы
# сделать?» — и это правильнее фильтра. Фильтр по `database_name` надо ПОМНИТЬ в каждом
# запросе; забыл один раз — и `duckdb_tables()` показал рабочие таблицы соседней базы
# (`techContext` ловушка 25). Разные имена делают столкновение невозможным по построению,
# а фильтр остаётся вторым рубежом, а не единственным.
# Имя базы спрашиваем у движка: `dbname=` в строке подключения может быть не указан вовсе
# (`HOW_NOT_TO §3.14`).
DBNAME=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DBNAME" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }
TAG="emb_${DBNAME}_${TBL}"

# Прежняя метка без имени базы. Нужна ровно для одного: докатить уже ПОСЧИТАННЫЕ И
# ОПЛАЧЕННЫЕ векторы, оставшиеся от прогонов до этой правки. [замер 29.07] в `ut_test`
# таких лежало 2 121 в четырёх таблицах — молча их потерять значило бы заплатить дважды.
# Когда старых таблиц не останется, ветка станет холостой и её можно будет снять.
TAG_OLD="emb_${TBL}"

# Предел длины входа. Пачка = не больше 10 строк И не больше $BUDGET символов; значение
# длиннее $MAXLEN в пачку не берётся вовсе. $BUDGET + $MAXLEN < 33 000 — это доказывает,
# что ни одна пачка не может превысить предел провайдера.
# 🔴 РАЗМЕР ПАЧКИ — РУЧКА С ЖЁСТКИМ ПОТОЛКОМ. Прежняя версия говорила «десятка была
# пределом прежнего облачного провайдера, у своего сервиса такого предела нет» — и звала
# подбирать значение замером. Подбирать можно только ВНИЗ: [замер 20.08] выше ~16-32 строк
# оператор падает с `Vector::SetSize out of range` (см. шапку файла) — это предел движка
# 26.07.3 на колонку `FLOAT[1024]`, он не зависит ни от провайдера, ни от длины строк.
# Ниже потолка значение действительно подбирается: [замер 02.08, облако] 10 — 7,0 строк/с,
# 16 — 9,5, 32 — 8,4, 64 — 6,2; [замер 20.08, своя карта] 8 — 26,4 строк/с, 16 — 21,9,
# 32 — 22,3 на карту при трёх потоках, но с учётом накладных расходов на запуск `psql`
# на порцию выгоднее 16. Мельче 8 не имеет смысла: круг запроса начинает съедать больше,
# чем сам счёт.
ROWS_PER_BATCH=${EMBED_BATCH_ROWS:-16}
BUDGET=${EMBED_BATCH_CHARS:-12000}
# Предел берётся из окружения, потому что на него опираются ПРОВЕРКИ в других файлах
# (`corpus_precheck.sql`, `corpus_postcheck.sql`): строки длиннее него вектор получить не
# могут, и счёт «сделано ли то, что должно» обязан их исключать. Скопированная константа
# разошлась бы молча.
MAXLEN=${EMBED_MAXLEN:-20000}

# Ключ строки. По умолчанию — `rowid` движка, но это ЗАПАСНОЙ путь: [замер] rowid
# устойчив внутри одного прогона (удаление дыры не переиспользует, обновление не двигает),
# однако прогон теперь докатывается через рестарт движка, а устойчивость rowid через
# уплотнение никем не проверена. Вектор, легший на чужую строку, — тихая порча смысла.
# Поэтому вызывающий передаёт настоящий ключ; он есть у обеих таблиц.
if [ -n "$KEY" ]; then
  KCOLS="$KEY"
  # Условие соединения склеивается вручную. `paste -sd' AND '` здесь НЕ ГОДИТСЯ: `-d`
  # принимает СПИСОК ОДНОСИМВОЛЬНЫХ разделителей и берёт их по кругу, поэтому вместо
  # `AND` между условиями подставлялся пробел — получался синтаксически битый `UPDATE`,
  # который поток проглатывал молча, и досчёт не двигался ни на строку.
  ON=""
  for c in ${KEY//,/ }; do
    [ -n "$ON" ] && ON="$ON AND "
    ON="${ON}t.$c = p.$c"
  done
  ORD="$KEY"
else
  KCOLS="rowid AS rid"; ON="t.rowid = p.rid"; ORD="rid"
fi

T0=$(date +%s)
psql_q() { psql "$DSN" -q -v ON_ERROR_STOP=1 "$@"; }

# 🔴 left() НЕ ДОЛЖЕН ПРОЕЦИРОВАТЬ колонку emb. Форма
#   SELECT count(*) FROM $TBL WHERE emb IS NULL AND NOT EXISTS (...)
# на сборке 26.07.3 даёт план с `Projections: emb, src_table` в CTE антисоединения
# ([замер 21.08] EXPLAIN на ut_test/синтетике). На klient-1 (15 млн × FLOAT[1024])
# этот count уходил в OOM за ~3 м 15 с при ~6 ГБ свободных — такт падал с
# «не удалось прочитать search_corpus», потому что stderr глушился.
# Штатное средство: проекция только нужных колонок (доки SereneDB —
# `data_import_and_export/parquet/overview#partial-reading`: читать лишь то, что
# нужно запросу; то же для собственного формата). Подзапрос отдаёт лёгкие колонки,
# `emb IS NULL` остаётся Column Filter без проекции вектора; ROWS_WHERE видит
# алиас = имя $TBL и не меняется у вызывающего.
# Колонки для подзапроса — те, на которые ROWS_WHERE ссылается как `$TBL.col`
# (корпус/метки/карточки — src_table; резолвер — table_name).
left() {
  local errf out sql light
  errf=$(mktemp) || return 1
  if [ -z "${ROWS_WHERE}" ]; then
    sql="SELECT count(*) FROM $TBL WHERE emb IS NULL"
  else
    light=$(printf '%s' "$ROWS_WHERE" \
      | grep -oE "${TBL}\\.[A-Za-z_][A-Za-z0-9_]*" \
      | sed "s/^${TBL}\\.//" \
      | sort -u \
      | paste -sd, -)
    [ -n "$light" ] || light="src_table"
    sql="SELECT count(*) FROM (SELECT $light FROM $TBL WHERE emb IS NULL) $TBL WHERE true $ROWS_WHERE"
  fi
  out=$(psql "$DSN" -tA -v ON_ERROR_STOP=1 -c "$sql" 2>"$errf") || {
    echo "не удалось прочитать $TBL: $(tr '\n' ' ' <"$errf" | head -c 400)" >&2
    rm -f "$errf"
    return 1
  }
  rm -f "$errf"
  printf '%s\n' "$out"
}

# 🔴 ВТОРОЙ РУБЕЖ: фильтр по базе. Первый — разные имена (метка несёт имя базы). Фильтр
# оставлен потому, что `duckdb_tables()` показывает таблицы ВСЕХ присоединённых баз, и
# полагаться на одну лишь дисциплину именования в чужом коде нельзя. [замер 29.07] из
# базы `postgres` было видно 5 рабочих таблиц базы `ut_test`; без обеих защит `transfer`
# подставил бы в `UPDATE` чужую таблицу, а `drop_parts` снёс бы чужую оплаченную работу —
# оба вреда молчаливые.
DBQ="AND database_name = current_database()"

# Перенос посчитанного из рабочих таблиц в целевую. Вызывается ДО начала работы (докатка
# прерванного прогона) и после неё. Писатель у движка один, поэтому последовательно.
# Берутся ОБЕ метки: текущая и прежняя — иначе уже оплаченные векторы старых прогонов
# остались бы лежать мёртвым грузом и были бы посчитаны заново.
transfer() {
  psql "$DSN" -tA -c "SELECT 'UPDATE $TBL t SET emb = p.emb FROM ' || table_name ||
         ' p WHERE $ON AND t.emb IS NULL;'
       FROM duckdb_tables()
       WHERE (table_name LIKE '${TAG}\_part\_%' ESCAPE '\'
           OR table_name LIKE '${TAG_OLD}\_part\_%' ESCAPE '\') $DBQ" \
    | psql "$DSN" -q >/dev/null 2>&1
}
# Уборка перечисляет РОВНО те таблицы, которые этот скрипт создаёт, а не «всё по шаблону
# `метка_%`». Со звёздочкой метка `emb_<таблица>` могла бы задеть метку другой цели, если
# база названа префиксом её имени (`emb_` + база `search` + `_corpus` = `emb_search_corpus`,
# то же, что прежняя метка таблицы `search_corpus`). Случай надуманный, но проверять это
# каждый раз глазами — та же ошибка, что полагаться на память о фильтре.
drop_parts() {
  psql "$DSN" -tA -c "SELECT 'DROP TABLE IF EXISTS ' || table_name || ';' FROM duckdb_tables()
       WHERE (table_name LIKE '${TAG}\_part\_%' ESCAPE '\' OR table_name = '${TAG}_todo'
           OR table_name LIKE '${TAG_OLD}\_part\_%' ESCAPE '\' OR table_name = '${TAG_OLD}_todo')
         $DBQ" | psql "$DSN" -q >/dev/null 2>&1
}

# Докатка: если прошлый прогон оборвался, его векторы уже посчитаны и оплачены.
transfer

# 🔴 ЗАЩИТА ОТ ТАКТА НА БОЛЬШОМ ОСТАТКЕ (25.08). Тактовый путь — для дельты;
# разовая сборка миллионов строк на нём даёт ~15 строк/с вместо ~168 (HOWTO §3).
# Оценка — pg_class.reltuples (docs/EMBED_ETA_KLIENT1.md); обход —
# EMBED_ALLOW_LARGE_TICK=1. До начала счёта ai_embed, до полного left().
# shellcheck disable=SC1091
. "$(dirname "$0")/embed_tick_guard.sh"
embed_tick_guard_check "$TBL" "$TAG"
_guard_rc=$?
if [ "$_guard_rc" -eq 2 ]; then
  exit 2
elif [ "$_guard_rc" -ne 0 ]; then
  exit "$_guard_rc"
fi

n=$(left) || exit 1
[ -z "$n" ] && { echo "не удалось прочитать $TBL: пустой ответ" >&2; exit 1; }
if [ "$n" = "0" ]; then
  drop_parts
  echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":0,\"осталось\":0}"
  exit 0
fi

# 🔴 Э1: один проход, без shell-while по раундам (п. 20: psql не в цикле).
# Отказ пачки (429) / остаток — добирает СЛЕДУЮЩИЙ такт (строки с emb IS NULL).
# Явный EMBED_ROUNDS>1 оставлен только для отладки вне такта; умолчание 1.
impossible=0; bad=0
ROUNDS=${EMBED_ROUNDS:-1}
PAUSE=${EMBED_RETRY_PAUSE:-20}
round=0
while : ; do
  round=$((round + 1))
  T0=$(date +%s)
  # Докатка перед DROP: иначе оплаченные векторы сносятся ([замер 29.07]).
  transfer
  before_round=$(left) || exit 1
  if [ "${before_round:-0}" = "0" ]; then after=0; break; fi

drop_parts

# Пачки по строкам И символам; chunk монотонен → зонные карты ([замер] 0,45–1,36 мс).
psql_q -c "CREATE OR REPLACE TABLE ${TAG}_todo AS
  WITH s AS (SELECT $KCOLS, $SRC AS txt FROM $TBL WHERE emb IS NULL $ROWS_WHERE),
       ok AS (SELECT * FROM s WHERE txt IS NOT NULL AND length(txt) BETWEEN 1 AND $MAXLEN),
       w AS (SELECT *, row_number() OVER (ORDER BY $ORD) - 1 AS rn,
                    sum(length(txt)) OVER (ORDER BY $ORD ROWS BETWEEN UNBOUNDED PRECEDING
                                                              AND 1 PRECEDING) AS cum
             FROM ok)
  SELECT * EXCLUDE (rn, cum),
         (rn / $ROWS_PER_BATCH) + (coalesce(cum, 0) / $BUDGET) AS chunk
  FROM w;" || exit 1

psql "$DSN" -tA -c "SELECT 'вектор невозможен, длина ' || length($SRC) || ': ' ||
       substr(replace($SRC, chr(10), ' '), 1, 60)
     FROM $TBL WHERE emb IS NULL AND length($SRC) > $MAXLEN $ROWS_WHERE" >&2
impossible=$(psql "$DSN" -tA -c "SELECT count(*) FROM $TBL
     WHERE emb IS NULL AND (($SRC) IS NULL OR length($SRC) > $MAXLEN OR length($SRC) = 0)")
impossible=${impossible:-0}

# Параллель HTTP — SET threads в ЭТОЙ же сессии (не веер клиентов).
THR_OLD=""
restore_threads() {
  [ -n "$THR_OLD" ] && psql "$DSN" -q -c "SET threads = $THR_OLD" >/dev/null 2>&1
  THR_OLD=""
}

ERRDIR=$(mktemp -d); trap 'rm -rf "$ERRDIR"; restore_threads' EXIT

THR_SQL=""
if [ -n "${EMBED_THREADS:-}" ]; then
  _thr_now=$(psql "$DSN" -tA -c "SHOW threads" 2>/dev/null | tr -cd '0-9')
  if [ -n "$_thr_now" ] && [ "$_thr_now" -lt "$EMBED_THREADS" ]; then
    THR_SQL="SET threads = $EMBED_THREADS;"
    THR_OLD="$_thr_now"
    echo "  потоки движка на время досчёта: $_thr_now -> $EMBED_THREADS" >&2
  fi
fi

# Одна сессия: staging part_0 + \gexec по всем chunk (AI Functions / Quick Start).
psql "$DSN" -q -v ON_ERROR_STOP=0 <<SQL >/dev/null 2>"$ERRDIR/0"
$THR_SQL
CREATE OR REPLACE TABLE ${TAG}_part_0 AS SELECT * FROM ${TAG}_todo WHERE false;
ALTER TABLE ${TAG}_part_0 DROP COLUMN txt;
ALTER TABLE ${TAG}_part_0 DROP COLUMN chunk;
ALTER TABLE ${TAG}_part_0 ADD COLUMN emb FLOAT[$DIM];
SELECT 'INSERT INTO ${TAG}_part_0 SELECT * EXCLUDE (txt, chunk), ai_embed(txt, ''$MODEL'', ''$SEC0'')::FLOAT[$DIM]
        FROM ${TAG}_todo WHERE chunk = ' || chunk || ';'
FROM (SELECT DISTINCT chunk FROM ${TAG}_todo ORDER BY 1)
\gexec
SQL
sess_rc=$?
restore_threads
bad=0
n_err=$(grep -cE '^(ERROR|FATAL|ОШИБКА)' "$ERRDIR/0" 2>/dev/null || true)
n_429=$(grep -c 'HTTP 429' "$ERRDIR/0" 2>/dev/null || true)
if [ "${n_err:-0}" -gt 0 ] || [ "$sess_rc" -ne 0 ]; then
  first_err=$(grep -m1 -E '^(ERROR|FATAL|ОШИБКА)' "$ERRDIR/0" || true)
  echo "досчёт: отказов пачек $n_err (из них по перегрузке $n_429). Первая: ${first_err:0:160}" >&2
  bad=1
fi

secs=$(( $(date +%s) - T0 ))
tot=$(psql "$DSN" -tA -c "SELECT count(*) FROM ${TAG}_part_0" 2>/dev/null | tr -d '[:space:]')
tot=${tot:-0}
echo "  сессия: $tot строк за ${secs}с (секрет $SEC0)" >&2

transfer
after=$(left) || exit 1
drop_parts

  moved=$(( ${before_round:-0} - ${after:-0} ))
  if [ "${after:-0}" = "0" ]; then break; fi
  if [ "$moved" -le 0 ]; then
    echo "  проход $round: не сдвинулось ни строки — повторять нечем" >&2; break
  fi
  if [ "$round" -ge "$ROUNDS" ]; then
    echo "  осталось $after — доберёт следующий такт (EMBED_ROUNDS=$ROUNDS)" >&2; break
  fi
  echo "  проход $round: посчитано $moved, осталось $after; пауза ${PAUSE}с" >&2
  sleep "$PAUSE"
done
n=${n:-0}

echo "{\"таблица\":\"$TBL\",\"было_без_вектора\":$n,\"осталось\":${after:-?},\"вектор_невозможен\":$impossible,\"ошибок_сессии\":$bad}"

# 🔴 НЕНУЛЕВОЙ КОД, ЕСЛИ РАБОТА НЕ СДВИНУЛАСЬ. Прежде скрипт заканчивался успехом, даже
# посчитав ноль строк, — так тихо умирал весь досчёт (`HOW_NOT_TO §2.10`).
# Строки, которым вектор невозможен, из ожидания вычитаются: иначе одно слишком длинное
# значение валило бы такт на каждом прогоне, и настоящий отказ утонул бы в этом шуме.
[ -z "$after" ] && { echo "не удалось прочитать итог по $TBL: пустой ответ" >&2; exit 1; }
[ "$after" -le "$impossible" ] && exit 0
[ "$after" -ge "$n" ] && { echo "досчёт не сдвинулся: было $n, осталось $after" >&2; exit 1; }
exit 0
