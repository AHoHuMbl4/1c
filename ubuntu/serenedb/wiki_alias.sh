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
BATCH="${WIKI_ALIAS_BATCH:-20}"
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
CAP="${1:-0}"
# Модель/thinking — infer model run --gateway (замер 17.08).
# Умолчание — своя vLLM Qwen3.8-27B (0 $); DeepSeek — через WIKI_ALIAS_MODEL.
WIKI_ALIAS_MODEL="${WIKI_ALIAS_MODEL:-vllm/Qwen3.8-27B}"
WIKI_ALIAS_THINKING="${WIKI_ALIAS_THINKING:-off}"
cd "$(dirname "$0")" || exit 1

bash "$(cd "$(dirname "$0")/.." && pwd)/openclaw/ensure_vllm_gateway.sh" || echo "алиасы: ensure_vllm — предупреждение" >&2

command -v openclaw >/dev/null 2>&1 || { echo "алиасы: openclaw не установлен — шаг пропущен"; exit 0; }
psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS $ALIAS_TABLE (src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR, not_enough_for VARCHAR, seen_at TIMESTAMP)" >/dev/null 2>&1
psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS $MEASURE_TABLE (src_table VARCHAR, measure VARCHAR, aliases VARCHAR, seen_at TIMESTAMP)" >/dev/null 2>&1
# Без GRANT сервис молча считает «словаря нет» (RuntimeError → пустой alias_by).
psql "$DSN" -q -c "GRANT SELECT ON $MEASURE_TABLE TO serene_ro" >/dev/null 2>&1

# 🔴 ОБМЕН ФАЙЛАМИ — ТОЛЬКО ЧЕРЕЗ КАТАЛОГ, ЧИТАЕМЫЙ ДВИЖКОМ. [замер 30.07] `read_json` из
# `/tmp/...` даёт «No files found»: процесс `serened` этот путь не видит. Тот же каталог, что у
# загрузчика (`CSV_DIR`, по умолчанию `/var/lib/serenedb`).
EXCH="${CSV_DIR:-/var/lib/serenedb}"
TMP=$(mktemp -d "$EXCH/wiki-alias-XXXXXX") || { echo "алиасы: нет доступа к $EXCH" >&2; exit 0; }
chmod 755 "$TMP"; trap 'rm -rf "$TMP"' EXIT
done_total=0
skipped=0

# 🔴 БЮДЖЕТ ВРЕМЕНИ, А НЕ ЧИСЛО КРУГОВ. Шаг идёт в такте свежести, а такт обязан
# укладываться в 20 минут (п. 17 TARGET.md). Число кругов этого не держит: круг — это вызов
# модели, и его цена зависит от того, как модель отвечает сегодня. [замер 05.08] 40 кругов
# на боевой базе — час, то есть предел «40» молча означал «час», и п. 17 не выполнялся.
# Бюджет измеряет то, что и ограничено контрактом, — ВРЕМЯ. Не успевшее за бюджет никуда
# не девается: работа идёт следующим тактом с того же места (оба прохода идемпотентны).
BUDGET="${WIKI_ALIAS_MAX_SEC:-120}"
t_start=$(date +%s)
over_budget() { [ "$BUDGET" != "0" ] && [ $(( $(date +%s) - t_start )) -ge "$BUDGET" ]; }
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
  psql "$DSN" -tA -c "
    WITH seed AS (
      SELECT f.src_table, t.emb FROM wiki_entity_facts f
      JOIN search_tables t ON t.src_table = f.src_table
      WHERE f.cls <> 'service'
        AND NOT EXISTS (SELECT 1 FROM $ALIAS_TABLE a WHERE a.src_table = f.src_table
                        AND (coalesce(a.aliases,'') <> ''
                             OR a.seen_at > now() - INTERVAL $RETRY_H HOUR))
      ORDER BY f.src_table LIMIT 1)
    SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                    quantities := coalesce(measures,''))))
    FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
            FROM wiki_entity_facts f
            JOIN search_tables t ON t.src_table = f.src_table
           WHERE f.cls <> 'service'
             AND NOT EXISTS (SELECT 1 FROM $ALIAS_TABLE a WHERE a.src_table = f.src_table
                        AND (coalesce(a.aliases,'') <> ''
                             OR a.seen_at > now() - INTERVAL $RETRY_H HOUR))
           ORDER BY d, f.src_table LIMIT $BATCH)" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac

  # 🔴 ЗАДАНИЕ ПЕРЕДАЁТСЯ ФАЙЛОМ, А НЕ АРГУМЕНТОМ. [замер 30.07] с `-m "$PAY"` на пачке из 25
  # сущностей команда отвечала «Missing message»: длинный JSON в аргументе командной строки не
  # доходит. У `openclaw agent` для этого есть штатный `--message-file`. Тот же класс дефекта, что
  # «стена argv» в разборе `HOW_NOT_TO §0`: данные аргументом командной строки не передаются.
  {
    # 🔴 СЛОВАРЬ — ЭТО СЛОВА, А НЕ ВОПРОСЫ (05.08, вечер). Прежнее задание просило «the
    # natural way someone would ask for that value», и модель честно клала в словарь вопросы
    # целиком: у регистра тары там оказалось «сколько тары у нас». Поиск считает совпадение
    # по всем словам вопроса, включая «сколько», «у», «нас», — и этот регистр стал лидером
    # ЛЮБОГО вопроса «сколько у нас …» с одной и той же оценкой 12,49 на трёх разных
    # вопросах приёмки (партнёры, склады, организации). Верные ответы 164, 17 и 5 из-за
    # этого отвергались проверкой выбора. Разбор — `work/entity-choice/ANSWER_RATE_P21.md`.
    #
    # Просим теперь ИМЕНА: как называют сам вид записи и как называют каждую его величину,
    # включая то слово-действие, которым о ней говорят («отгрузка», «продажа»). Запретов в
    # задании нет намеренно — правило держится не текстом для модели, а формой ответа
    # (короткие именующие обороты) и прибором `work/entity-choice/alias_rank_bench.py`,
    # который меряет словарь числом: на каком месте эталонная сущность вопроса.
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. For each, in the SAME language as its title: (1) aliases — the SHORT NAMES a person here uses for this kind of record, including its own title; names of its quantities do not belong here; (2) quantities — for EVERY name from the input quantities list, copy that name exactly and give the short names a person uses for that value (a noun or a noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling types from this list that a person could mean instead and what each of them answers. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --ans "$TMP/ans" --err "$TMP/err" || {
      # 🔴 ОДНА ОСЕЧКА НЕ ОСТАНАВЛИВАЕТ ВСЁ. [замер 30.07] на 143-й сущности из 686 модель
      # не ответила в срок (`LLM request timed out`), и прежний код обрывал цикл целиком —
      # остальные 543 остались без описания из-за одной пачки. Теперь пачка пропускается,
      # а её сущности помечаются, чтобы следующий проход не спотыкался о них снова и не
      # ходил по кругу. Сколько пропущено — печатается в конце, молчания тут быть не должно.
      skipped=$((skipped + 1))
      echo "алиасы: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql "$DSN" -q -c "INSERT INTO $ALIAS_TABLE
        SELECT entity, '', '', '', now() FROM read_json('$TMP/pay',
          columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'})
        WHERE entity NOT IN (SELECT src_table FROM $ALIAS_TABLE)" >/dev/null 2>&1
      # Пустышка величины — та же семантика: попытка, не ответ. Без неё осечка
      # пачки на доборе величин крутилась бы вечно; с непустым ответом её снимает
      # DELETE перед INSERT ниже.
      psql "$DSN" -q -c "INSERT INTO $MEASURE_TABLE
        SELECT entity, trim(q), '', now()
        FROM read_json('$TMP/pay',
          columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'}),
             unnest(str_split(quantities, ',')) AS x(q)
        WHERE trim(q) <> ''
          AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE a
                          WHERE a.src_table = entity AND a.measure = trim(q))" >/dev/null 2>&1
      continue
    }

  # Разбор ответа модели — своим кодом это разрешено (п. 20: проверка ответа модели).
  # Выдуманное имя величины отбрасывается: во входном списке его не было.
  python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json"
  python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
  # 🔴 ФАЙЛ ЧИТАЕТ ДВИЖОК, А НЕ МЫ. Каталогу права выставлены при создании, но
  # сам файл рождается с маской процесса: такт идёт из `build.sh`, где стоит
  # `umask 077` (секреты), и `rows.json` выходил 600 root — движок (`serenedb`)
  # получал «Permission denied», модель при этом отвечала исправно. Живой случай
  # okna-1 13.08: словарь встал на 140 из 351 при «алиасов разобрано: 20» каждую
  # пачку — то есть деньги за модель тратились, а словарь не рос. Права ставятся
  # рядом с записью, как у `msg` выше.
  chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
  # Запись — ОДНИМ запросом из файла, без цикла по строкам (п. 20). Пустая заготовка,
  # оставшаяся от прежней осечки, сначала снимается: иначе ответ модели молча падал бы
  # мимо словаря (`NOT IN` считает такую строку уже отвеченной), и переспрос был бы
  # бесполезен — деньги за модель тратились бы вечно.
  psql "$DSN" -q -c "
    DELETE FROM $ALIAS_TABLE WHERE coalesce(aliases,'') = '' AND src_table IN
      (SELECT src_table FROM read_json('$TMP/rows.json',
         columns := {src_table:'VARCHAR', aliases:'VARCHAR',
                     best_used_for:'VARCHAR', not_enough_for:'VARCHAR'})
       WHERE coalesce(aliases,'') <> '');
    INSERT INTO $ALIAS_TABLE
    SELECT src_table, aliases, best_used_for, not_enough_for, now()
    FROM read_json('$TMP/rows.json', columns := {src_table:'VARCHAR', aliases:'VARCHAR',
                                                best_used_for:'VARCHAR', not_enough_for:'VARCHAR'})
    WHERE src_table NOT IN (SELECT src_table FROM $ALIAS_TABLE);
    DELETE FROM $MEASURE_TABLE WHERE coalesce(aliases,'') = '' AND src_table IN
      (SELECT DISTINCT src_table FROM read_json('$TMP/measures.json',
         columns := {src_table:'VARCHAR', measure:'VARCHAR', aliases:'VARCHAR'})
       WHERE coalesce(aliases,'') <> '');
    INSERT INTO $MEASURE_TABLE
    SELECT src_table, measure, aliases, now()
    FROM read_json('$TMP/measures.json',
         columns := {src_table:'VARCHAR', measure:'VARCHAR', aliases:'VARCHAR'}) n
    WHERE coalesce(n.aliases,'') <> ''
      AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE a
                      WHERE a.src_table = n.src_table AND a.measure = n.measure
                        AND coalesce(a.aliases,'') <> '')" 2>&1 | grep -i error

  have=$(psql "$DSN" -tAc "SELECT count(*) FROM $ALIAS_TABLE" 2>/dev/null)
  echo "алиасы: всего в базе $have"
  done_total=$((done_total + BATCH))
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
  over_budget && { echo "алиасы: бюджет $BUDGET с исчерпан — остальные сущности возьмёт следующий такт"; break; }
done
# ── ДОБОР ВЕЛИЧИН: сущность описана, поля — нет ────────────────────────────────
# Первый проход берёт тех, кого ещё нет в словаре сущностей. Уже описанные
# (живой случай okna: сотни страниц без мер) в него не попадут, и словарь
# величин остался бы пустым навсегда. Здесь пачка — сущности с непустым
# алиасом записи, с величинами в данных и без единого непустого алиаса поля
# (пустышка старше retry переспрашивается). Алиасы сущности НЕ перезаписываются.
while :; do
  over_budget && { echo "величины: бюджет $BUDGET с исчерпан — добор возьмёт следующий такт"; break; }
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
  psql "$DSN" -tA -c "
    WITH seed AS (
      SELECT f.src_table, t.emb FROM wiki_entity_facts f
      JOIN search_tables t ON t.src_table = f.src_table
      WHERE f.cls <> 'service'
        AND coalesce(f.measures,'') <> ''
        AND EXISTS (SELECT 1 FROM $ALIAS_TABLE a
                    WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
        AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE m
                        WHERE m.src_table = f.src_table AND coalesce(m.aliases,'') <> '')
        AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE m
                        WHERE m.src_table = f.src_table
                          AND coalesce(m.aliases,'') = ''
                          AND m.seen_at > now() - INTERVAL $RETRY_H HOUR)
      ORDER BY f.src_table LIMIT 1)
    SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                    quantities := coalesce(measures,''))))
    FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
            FROM wiki_entity_facts f
            JOIN search_tables t ON t.src_table = f.src_table
           WHERE f.cls <> 'service'
             AND coalesce(f.measures,'') <> ''
             AND EXISTS (SELECT 1 FROM $ALIAS_TABLE a
                         WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
             AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE m
                             WHERE m.src_table = f.src_table AND coalesce(m.aliases,'') <> '')
             AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE m
                             WHERE m.src_table = f.src_table
                               AND coalesce(m.aliases,'') = ''
                               AND m.seen_at > now() - INTERVAL $RETRY_H HOUR)
           ORDER BY d, f.src_table LIMIT $BATCH)" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac
  {
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. For each, in the SAME language as its title: (1) aliases — the SHORT NAMES a person here uses for this kind of record, including its own title; names of its quantities do not belong here; (2) quantities — for EVERY name from the input quantities list, copy that name exactly and give the short names a person uses for that value (a noun or a noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling types from this list that a person could mean instead and what each of them answers. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --ans "$TMP/ans" --err "$TMP/err" || {
      skipped=$((skipped + 1))
      echo "величины: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql "$DSN" -q -c "INSERT INTO $MEASURE_TABLE
        SELECT entity, trim(q), '', now()
        FROM read_json('$TMP/pay',
          columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'}),
             unnest(str_split(quantities, ',')) AS x(q)
        WHERE trim(q) <> ''
          AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE a
                          WHERE a.src_table = entity AND a.measure = trim(q))" >/dev/null 2>&1
      continue
    }
  python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json"
  python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
  chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
  # Только величины. rows.json с алиасами сущности здесь намеренно не пишется в
  # ALIAS_TABLE: добор не имеет права перезаписать уже собранные описания записей.
  psql "$DSN" -q -c "
    DELETE FROM $MEASURE_TABLE WHERE coalesce(aliases,'') = '' AND src_table IN
      (SELECT DISTINCT src_table FROM read_json('$TMP/measures.json',
         columns := {src_table:'VARCHAR', measure:'VARCHAR', aliases:'VARCHAR'})
       WHERE coalesce(aliases,'') <> '');
    INSERT INTO $MEASURE_TABLE
    SELECT src_table, measure, aliases, now()
    FROM read_json('$TMP/measures.json',
         columns := {src_table:'VARCHAR', measure:'VARCHAR', aliases:'VARCHAR'}) n
    WHERE coalesce(n.aliases,'') <> ''
      AND NOT EXISTS (SELECT 1 FROM $MEASURE_TABLE a
                      WHERE a.src_table = n.src_table AND a.measure = n.measure
                        AND coalesce(a.aliases,'') <> '')" 2>&1 | grep -i error
  have_m=$(psql "$DSN" -tAc "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''" 2>/dev/null)
  echo "величины: непустых в базе $have_m"
  done_total=$((done_total + BATCH))
done
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
  psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS search_alias_probe (alias VARCHAR, entities_fp VARCHAR, asked_at TIMESTAMP)" >/dev/null 2>&1
  rounds=0 asked=0 stopped=""
  # Предел кругов остаётся вторым ограничителем — на случай `WIKI_ALIAS_MAX_SEC=0`.
  while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]; do
    over_budget && { stopped=" (бюджет $BUDGET с исчерпан)"; break; }
    rounds=$((rounds + 1))
    # Слово выбирается ОТДЕЛЬНЫМ запросом: его отпечаток нужен, чтобы отметить попытку.
    # `md5(string_agg(...))` — штатные функции движка (доки: Sql › Functions › Utility
    # Functions; Sql › Functions › Aggregate Functions).
    PICK=$(psql "$DSN" -tA -F$'\t' -c "
      WITH al AS (SELECT src_table, trim(lower(x.a)) AS alias
                    FROM $ALIAS_TABLE, unnest(str_split(aliases, ',')) AS x(a)
                   WHERE trim(x.a) <> ''),
           dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
           -- Обычно берём САМОЕ спорное слово: у него больше всего сущностей.
           -- 🔴 Но можно назвать слово прямо, переменной WIKI_ALIAS_WORD, — быстрый путь,
           -- когда
           -- прогон приёмки уже показал, ГДЕ система спуталась: разводим ровно тех, кто
           -- ошибся, а не ждём, пока очередь дойдёт. Цель владельца 30.07 — «сто процентов
           -- верных ответов, даже если для этого надо 2-3 раза переспросить»; значит
           -- чинить надо по факту ошибки, а не подряд. Названное слово память не блокирует:
           -- владелец спрашивает повторно осознанно.
           cand AS (SELECT a.alias,
                           md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp,
                           count(DISTINCT a.src_table) AS n
                      FROM al a JOIN dup d ON d.alias = a.alias
                     WHERE ('$TARGET_WORD' = '' OR a.alias = lower('$TARGET_WORD'))
                       AND NOT EXISTS (SELECT 1 FROM $ALIAS_TABLE s
                                        WHERE s.src_table = a.src_table
                                          AND s.not_enough_for ILIKE '%' || a.alias || '%')
                     GROUP BY 1)
      SELECT c.alias, c.fp FROM cand c
       WHERE '$TARGET_WORD' <> ''
          OR NOT EXISTS (SELECT 1 FROM search_alias_probe p
                          WHERE p.alias = c.alias AND p.entities_fp = c.fp)
       ORDER BY c.n DESC, c.alias LIMIT 1" 2>/dev/null)
    [ -z "$PICK" ] && break
    WORD=${PICK%%$'\t'*}; FP=${PICK##*$'\t'}
    # Одинарные кавычки удваиваются: слово приходит из данных, а не от нас.
    WORD_SQL=${WORD//\'/\'\'}
    psql "$DSN" -q -c "INSERT INTO search_alias_probe VALUES ('$WORD_SQL', '$FP', now())" >/dev/null 2>&1
    asked=$((asked + 1))
    psql "$DSN" -tA -c "
      WITH al AS (SELECT src_table, trim(lower(x.a)) AS alias
                    FROM $ALIAS_TABLE, unnest(str_split(aliases, ',')) AS x(a)
                   WHERE trim(x.a) <> '')
      SELECT to_json(list(struct_pack(entity := f.src_table, title := f.label,
                                      quantities := coalesce(f.measures,''))))
      FROM (SELECT f.* FROM wiki_entity_facts f
             WHERE f.src_table IN (SELECT src_table FROM al WHERE alias = '$WORD_SQL')
             -- 🔴 ПРЕДЕЛ ОБЯЗАТЕЛЕН: число сущностей на одно спорное слово растёт с размером
             -- базы (у нас со словом «НДС» их 18), а весь список уходит в модель — это п. 19,
             -- объём в модель не должен зависеть от размера базы. Не влезшие в пачку
             -- разведутся следующим кругом: слово останется спорным, пока их не разведут.
             ORDER BY f.src_table LIMIT $BATCH) f" \
      > "$TMP/pay" 2>/dev/null
    chmod 644 "$TMP/pay" 2>/dev/null
    PAY=$(cat "$TMP/pay")
    case "$PAY" in ''|'[]'|'null') continue;; esac
    {
      printf '%s' "JSON only, no prose, no code fences. The record types below are ALL CALLED BY THE SAME WORD in this database — a person using that word could mean any of them. For each, in the SAME language as its title: (1) aliases — how a person refers to THIS one, keeping its own title and dropping words that fit the others equally well; (2) bestUsedFor — what only this one answers; (3) notEnoughFor — the other types from this list and what each answers instead. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
      cat "$TMP/pay"
    } > "$TMP/msg"
    chmod 644 "$TMP/msg"
    "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
      --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
      --ans "$TMP/ans" --err "$TMP/err" || {
        echo "разведение: пачка пропущена ($(head -c 100 "$TMP/err" | tr -d '\n'))" >&2; continue; }
    python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
    python3 - "$TMP/ans" "$TMP/rows.json" <<'PY2'
import json, re, sys
raw = open(sys.argv[1], encoding='utf-8', errors='replace').read()
text = ''
try:
    env = json.loads(raw)
    def dig(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('text', 'content') and isinstance(v, str) and '{' in v:
                    yield v
                yield from dig(v)
        elif isinstance(o, list):
            for v in o:
                yield from dig(v)
    c = list(dig(env)); text = max(c, key=len) if c else ''
except ValueError:
    text = raw
m = re.search(r'\{.*\}', text, re.S)
rows = []
if m:
    try:
        for it in (json.loads(m.group(0)).get('items') or []):
            e = (it.get('entity') or '').strip()
            if not e: continue
            j = lambda x: ', '.join(str(i).strip() for i in (x or []) if str(i).strip())[:900]
            rows.append({"src_table": e, "aliases": j(it.get('aliases')),
                         "best_used_for": j(it.get('bestUsedFor')),
                         "not_enough_for": j(it.get('notEnoughFor'))})
    except ValueError:
        pass
open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False))
print("разведено сущностей: %d" % len(rows))
PY2
    chmod 644 "$TMP/rows.json" 2>/dev/null   # тот же случай, что в первом проходе
    psql "$DSN" -q -c "
      UPDATE $ALIAS_TABLE a SET aliases = n.aliases, best_used_for = n.best_used_for,
             not_enough_for = n.not_enough_for, seen_at = now()
      FROM read_json('$TMP/rows.json', columns := {src_table:'VARCHAR', aliases:'VARCHAR',
             best_used_for:'VARCHAR', not_enough_for:'VARCHAR'}) n
      WHERE a.src_table = n.src_table" >/dev/null 2>&1
  done
  # Молчания тут быть не должно: видно и сколько спросили, и сколько ОСТАЛОСЬ на следующий
  # такт (упёрлись в предел кругов), и сколько столкновений модель разобрать не смогла —
  # они лежат в `search_alias_probe` и сами собой больше не переспрашиваются.
  left=$(psql "$DSN" -tAc "
    WITH al AS (SELECT src_table, trim(lower(x.a)) AS alias
                  FROM $ALIAS_TABLE, unnest(str_split(aliases, ',')) AS x(a)
                 WHERE trim(x.a) <> ''),
         dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
         cand AS (SELECT a.alias,
                         md5(string_agg(DISTINCT a.src_table, ',' ORDER BY a.src_table)) AS fp
                    FROM al a JOIN dup d ON d.alias = a.alias
                   WHERE NOT EXISTS (SELECT 1 FROM $ALIAS_TABLE s
                                      WHERE s.src_table = a.src_table
                                        AND s.not_enough_for ILIKE '%' || a.alias || '%')
                   GROUP BY 1)
    SELECT count(*) FROM cand c
     WHERE NOT EXISTS (SELECT 1 FROM search_alias_probe p
                        WHERE p.alias = c.alias AND p.entities_fp = c.fp)" 2>/dev/null)
  echo "разведение столкновений: кругов $rounds$stopped, спрошено слов $asked, осталось неспрошенных ${left:-?}"
fi

[ "$skipped" -gt 0 ] && echo "алиасы: пачек пропущено из-за отказа модели: $skipped" >&2
psql "$DSN" -tA -F' | ' -c "
  SELECT 'алиасов в базе', count(*) FROM $ALIAS_TABLE
  UNION ALL SELECT 'из них ПУСТЫХ (модель не ответила)', count(*) FROM $ALIAS_TABLE
    WHERE coalesce(aliases,'') = ''
  UNION ALL SELECT 'величин в словаре', count(*) FROM $MEASURE_TABLE
    WHERE coalesce(aliases,'') <> ''
  UNION ALL SELECT 'пустышек величин (модель не ответила)', count(*) FROM $MEASURE_TABLE
    WHERE coalesce(aliases,'') = ''"
