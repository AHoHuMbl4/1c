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
# Периодическое доучивание (С5-пайплайн): 0 = выкл (боевые базы не меняются молча).
REASK_EVERY="${WIKI_ALIAS_REASK_EVERY:-0}"
case "$REASK_EVERY" in ''|*[!0-9]*) REASK_EVERY=0;; esac
REASK_STALE_DAYS="${WIKI_ALIAS_REASK_STALE_DAYS:-30}"
case "$REASK_STALE_DAYS" in ''|*[!0-9]*) REASK_STALE_DAYS=30;; esac
WIKI_ALIAS_TICK="${WIKI_ALIAS_TICK:-0}"
case "$WIKI_ALIAS_TICK" in ''|*[!0-9]*) WIKI_ALIAS_TICK=0;; esac
REASK_CAP="${WIKI_ALIAS_REASK_CAP:-$BATCH}"
case "$REASK_CAP" in ''|*[!0-9]*) REASK_CAP="$BATCH";; esac
CAP="${1:-0}"
# Модель/thinking — infer model run через alias_infer_gateway.py.
# 🔴 Транспорт: умолчание --local (cli/infer.md). [замер 24.08] --gateway =
# RPC-потолок 120 с → GatewayTransportError; loc 1034 с / пачка 20 — exit 0.
# Умолчание модели — своя vLLM Qwen3.8-27B (0 $); DeepSeek — через WIKI_ALIAS_MODEL.
WIKI_ALIAS_MODEL="${WIKI_ALIAS_MODEL:-vllm/Qwen3.8-27B}"
WIKI_ALIAS_THINKING="${WIKI_ALIAS_THINKING:-off}"
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"

# Общие psql-параметры: таблицы и retry — один -f вместо веера -c (п. 20, Э1а).
psql_wa() {
  psql "$DSN" -q -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v retry_h="$RETRY_H" \
    "$@"
}
psql_wa_tA() {
  psql "$DSN" -tA -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v retry_h="$RETRY_H" \
    "$@"
}
DB_TAG=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DB_TAG" ] || DB_TAG="db"
REASK_TABLE="${WIKI_ALIAS_REASK_TABLE:-alias_${DB_TAG}_reask}"
CONFIRM_TABLE="${WIKI_ALIAS_CONFIRM_TABLE:-alias_${DB_TAG}_reask_confirm}"
JOURNAL_TABLE="${WIKI_ALIAS_JOURNAL_TABLE:-alias_${DB_TAG}_reask_journal}"

bash "$(cd "$(dirname "$0")/.." && pwd)/openclaw/ensure_vllm_gateway.sh" || echo "алиасы: ensure_vllm — предупреждение" >&2

command -v openclaw >/dev/null 2>&1 || { echo "алиасы: openclaw не установлен — шаг пропущен"; exit 0; }
# DDL alias/measure/probe — один процесс psql (wiki_alias_init.sql).
psql_wa -f "$HERE/wiki_alias_init.sql" >/dev/null 2>&1

# 🔴 ОБМЕН ФАЙЛАМИ — ТОЛЬКО ЧЕРЕЗ КАТАЛОГ, ЧИТАЕМЫЙ ДВИЖКОМ. [замер 30.07] `read_json` из
# `/tmp/...` даёт «No files found»: процесс `serened` этот путь не видит. Тот же каталог, что у
# загрузчика (`CSV_DIR`, по умолчанию `/var/lib/serenedb`).
EXCH="${CSV_DIR:-/var/lib/serenedb}"
TMP=$(mktemp -d "$EXCH/wiki-alias-XXXXXX") || { echo "алиасы: нет доступа к $EXCH" >&2; exit 0; }
chmod 755 "$TMP"; trap 'rm -rf "$TMP"' EXIT
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
  psql_wa_tA -v batch="$BATCH" \
    -f "$HERE/wiki_alias_select_entity_batch.sql" > "$TMP/pay" 2>/dev/null
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
    # 🔴 ОБИХОДНЫЕ СЛОВА, А НЕ ПЕРЕФРАЗИРОВКИ TITLE (25.08). Задание «SHORT NAMES …
    # including its own title» давало морфологию метаданных («Контрагенты, контрагент»)
    # и имена реквизитов в aliases; ts_lexize('…','клиент') оставался без связи
    # (живой замер okna 25.08). Просим слова из вопросов людей + title; имена величин
    # — только в quantities. Отсев мусора — `wiki_alias_parse.filter_entity_aliases`.
    # 🔴 СЛОВА РОЛИ В ПОТОКЕ (28.08, вечер). Полный C5-прогон okna дал для
    # контрагентов «клиентов и поставщиков», но не «покупателей»: на вопрос
    # «сколько покупателей было за этот месяц» ф9-связь kind→catalog не собралась
    # (в алиасах нет стема «покупател»), ответ остался 76 по кассе. Роль — вещь
    # потока, не сущности: тот же каталог в продаже называют покупателями, в закупке
    # поставщиками. Задание теперь явно просит слова роли для каждого потока, где
    # запись участвует; пример в задании — общебизнесовой, не про конкретную базу.
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. For each, in the SAME language as its title: (1) aliases — everyday words a person uses when asking about this kind of record (the words that appear in their question), and also the record title itself; people also call the same records by the ROLE they play in a specific flow — one and the same catalog is named differently depending on the flow it is asked about (for example, one counterparty catalog is called buyers in sales questions and suppliers in purchase questions), so include those role words for every flow this kind of record takes part in — the input lists those flows for each record (types that hold it as a reference), and the role words come from them; quantity and field names go only under quantities; (2) quantities — for EVERY name from the input quantities list, copy that name exactly and give the short names a person uses for that value (a noun or a noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling types from this list that a person could mean instead and what each of them answers. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
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
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
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
  psql_wa -v rows_path="$TMP/rows.json" -v measures_path="$TMP/measures.json" \
    -f "$HERE/wiki_alias_merge_entity.sql" 2>&1 | grep -i error

  have=$(psql_wa_tA -c "SELECT count(*) FROM $ALIAS_TABLE" 2>/dev/null)
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
  psql_wa_tA -v batch="$BATCH" \
    -f "$HERE/wiki_alias_select_measure_batch.sql" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac
  {
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. For each, in the SAME language as its title: (1) aliases — everyday words a person uses when asking about this kind of record (the words that appear in their question), and also the record title itself; people also call the same records by the ROLE they play in a specific flow — one and the same catalog is named differently depending on the flow it is asked about (for example, one counterparty catalog is called buyers in sales questions and suppliers in purchase questions), so include those role words for every flow this kind of record takes part in — the input lists those flows for each record (types that hold it as a reference), and the role words come from them; quantity and field names go only under quantities; (2) quantities — for EVERY name from the input quantities list, copy that name exactly and give the short names a person uses for that value (a noun or a noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling types from this list that a person could mean instead and what each of them answers. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --ans "$TMP/ans" --err "$TMP/err" || {
      skipped=$((skipped + 1))
      echo "величины: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
      continue
    }
  python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json"
  python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
  chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
  # Только величины. rows.json с алиасами сущности здесь намеренно не пишется в
  # ALIAS_TABLE: добор не имеет права перезаписать уже собранные описания записей.
  psql_wa -v measures_path="$TMP/measures.json" \
    -f "$HERE/wiki_alias_merge_measures.sql" 2>&1 | grep -i error
  have_m=$(psql_wa_tA -c "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''" 2>/dev/null)
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
  # search_alias_probe создаётся в wiki_alias_init.sql (CREATE IF NOT EXISTS).
  rounds=0 asked=0 stopped=""
  # Предел кругов остаётся вторым ограничителем — на случай `WIKI_ALIAS_MAX_SEC=0`.
  while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]; do
    over_budget && { stopped=" (бюджет $BUDGET с исчерпан)"; break; }
    rounds=$((rounds + 1))
    # Выбор слова + отметка probe + JSON пачки — один psql (wiki_alias_collision_round.sql).
    # `md5(string_agg(...))` — штатные функции движка (Aggregate; Utility md5).
    ROUND=$(psql_wa_tA -v batch="$BATCH" -v target_word="$TARGET_WORD" \
      -f "$HERE/wiki_alias_collision_round.sql" 2>/dev/null) || ROUND=""
    [ -z "$ROUND" ] && break
    WORD=${ROUND%%$'\t'*}
    rest=${ROUND#*$'\t'}
    FP=${rest%%$'\t'*}
    PAY=${rest#*$'\t'}
    asked=$((asked + 1))
    printf '%s' "$PAY" > "$TMP/pay"
    chmod 644 "$TMP/pay" 2>/dev/null
    case "$PAY" in ''|'[]'|'null') continue;; esac
    {
      # 🔴 Общие обиходные слова оставляем в aliases: иначе ts_lexize теряет связь
      # («клиент» → пусто, замер okna 25.08). Различие соседей — в notEnoughFor.
      printf '%s' "JSON only, no prose, no code fences. The record types below are ALL CALLED BY THE SAME WORD in this database — a person using that word could mean any of them. For each, in the SAME language as its title: (1) aliases — everyday asking-words and the title for THIS type; everyday words that also fit siblings stay in aliases, and the sibling distinction goes in notEnoughFor; (2) bestUsedFor — what only this one answers; (3) notEnoughFor — the other types from this list and what each answers instead. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
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
    psql_wa -v rows_path="$TMP/rows.json" -f "$HERE/wiki_alias_collision_merge.sql" >/dev/null 2>&1
  done
  # Молчания тут быть не должно: видно и сколько спросили, и сколько ОСТАЛОСЬ на следующий
  # такт (упёрлись в предел кругов), и сколько столкновений модель разобрать не смогла —
  # они лежат в `search_alias_probe` и сами собой больше не переспрашиваются.
  left=$(psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql" 2>/dev/null)
  echo "разведение столкновений: кругов $rounds$stopped, спрошено слов $asked, осталось неспрошенных ${left:-?}"
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
      psql "$DSN" -tA -v ON_ERROR_STOP=1 \
        -v alias_table="$ALIAS_TABLE" \
        -v batch="$BATCH" \
        -v reask_stale_days="$REASK_STALE_DAYS" \
        -v pool_path="$POOL_JSON" \
        -f "$HERE/wiki_alias_reask_select_entity_batch.sql" > "$TMP/reask_pay" 2>/dev/null
      chmod 644 "$TMP/reask_pay" 2>/dev/null
      PAY=$(cat "$TMP/reask_pay")
      case "$PAY" in ''|'[]'|'null') break;; esac
      {
        printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. For each, in the SAME language as its title: (1) aliases — everyday words a person uses when asking about this kind of record (the words that appear in their question), and also the record title itself; people also call the same records by the ROLE they play in a specific flow — one and the same catalog is named differently depending on the flow it is asked about (for example, one counterparty catalog is called buyers in sales questions and suppliers in purchase questions), so include those role words for every flow this kind of record takes part in — the input lists those flows for each record (types that hold it as a reference), and the role words come from them; quantity and field names go only under quantities; (2) quantities — for EVERY name from the input quantities list, copy that name exactly and give the short names a person uses for that value (a noun or a noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling types from this list that a person could mean instead and what each of them answers. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
        cat "$TMP/reask_pay"
      } > "$TMP/reask_msg"
      chmod 644 "$TMP/reask_msg"
      "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/reask_msg" \
        --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
        --ans "$TMP/reask_ans" --err "$TMP/reask_err" || {
          echo "reask: пачка пропущена ($(head -c 100 "$TMP/reask_err" | tr -d '\n'))" >&2
          continue
        }
      python3 ./wiki_alias_parse.py "$TMP/reask_ans" "$TMP/reask_pay" \
        "$TMP/reask_rows.json" "$TMP/reask_meas.json"
      chmod 644 "$TMP/reask_rows.json" "$TMP/reask_meas.json" 2>/dev/null
      # Боковая таблица: полный ответ модели (не основной словарь).
      psql "$DSN" -q -v ON_ERROR_STOP=1 \
        -v alias_table="$REASK_TABLE" \
        -v measure_table="$MEASURE_TABLE" \
        -v rows_path="$TMP/reask_rows.json" \
        -v measures_path="$TMP/reask_meas.json" \
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
      REASK_DONE=$((REASK_DONE + BATCH))
    done
    echo "reask: обработано пачек до $REASK_DONE сущностей" >&2
  fi
fi

# Итог «алиасов в базе» — wiki_alias_publish.sql (stats + REFRESH, не в tx с INSERT).
# Внутри publish: VACUUM (REFRESH_TABLE) $ALIAS_TABLE.
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
  BRANCH_ALIAS_MAX_SEC="${BRANCH_ALIAS_MAX_SEC:-60}" ./branch_alias.sh "${BRANCH_ALIAS_CAP:-10}" \
    || echo "развилки src: шаг не прошёл, такт продолжается" >&2
fi

# ── Ф6.3: Solr-словарь синонимов из таблиц (не списки в коде) ─────────────────
# SELECT → карта → DROP+CREATE файлом (argv ломается на длинной карте, фактура §5.3).
# Пустые источники — словарь не трогаем. Лимит сверх фактуры — честная ошибка.
SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-${SOLR_SYN_DICT:-search_dict_syn}}"
SOLR_OUT="${CSV_DIR:-/var/lib/serenedb}/solr_synonyms_${SOLR_SYN_DICT}.sql"
python3 ./solr_synonyms_build.py compile \
  --dsn "$DSN" --dict "$SOLR_SYN_DICT" --alias-table "$ALIAS_TABLE" \
  --out "$SOLR_OUT" --apply \
  || echo "solr synonyms: шаг не прошёл, такт/юнит продолжается" >&2
