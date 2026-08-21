#!/bin/bash
# ТОЛЬКО ДОСЧЁТ ВЕКТОРОВ — без пересборки корпуса.
#
# 🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ ВХОД. Вопрос владельца 29.07: «а зачем мы постоянно делаем сборку?
# теряем время». Чтобы продолжить векторизацию, полный такт не нужен: корпус уже собран,
# менять в нём нечего. [замер 29.07] за день такт перезапускался пять раз ради настроек
# эмбеддинга, и каждый раз корпус собирался заново — по 8-18 минут холостой работы.
#
# Отличие от `build.sh`: тот делает ТАКТ (синк → корпус → слияние → разметка → векторы →
# индекс → проверки). Этот делает ровно один шаг — досчёт векторов тем строкам, у которых
# их нет. Применять, когда данные не менялись, а векторы не досчитаны: после обрыва,
# после смены числа потоков или ключей, при первой заливке крупной базы.
#
# Кому считается вектор: НЕ служебным сущностям (разметка в `search_entity_class`).
# Служебным — не считается вовсе, решение владельца 29.07 «да, не нужны они в векторе».
# Они целиком в корпусе и в ТЕКСТОВОМ индексе, то есть находятся по словам; не находятся
# только «по смыслу», а по смыслу замеры времени и объекты «Удалить…» никто не ищет.
# Отсутствие вектора у них НАЗВАНО причиной в переписи (`cov_noemb_service`) отдельно от
# «ещё в очереди» (`cov_noemb_pending`) — это разные вещи (п. 13).
# Вернуть прежнее поведение: `EMBED_SERVICE=1`.
#
# Ключи берутся из `EMBED_API_KEYS` (через запятую) либо из одиночного `EMBED_API_KEY`
# (прежние `ALIBABA_*` читаются как запасные). На каждый создаётся свой временный секрет,
# потоки раскладываются по ключам по кругу. 🔴 Механизм задумывался против квоты облака
# на аккаунт; на своих картах несколько ключей смысла не имеют — там ограничитель другой
# (`threads` движка и память клиента, см. `docs/EMBED_BULK_HOWTO.md`). Секреты именуются по базе — они у движка
# ОБЩИЕ НА ИНСТАНС, и одно имя на все базы гасило бы эмбеддер соседней сборки
# (`techContext` ловушка 26).
#
# 🔴 ЧТО СЧИТАТЬ — ЗАДАЁТСЯ, А НЕ ЗАШИТО. `EMBED_TARGETS` перечисляет цели в порядке
# важности: `labels` (метки сущностей — по ним идёт ВЫБОР СУЩНОСТИ, их всего полторы
# тысячи), `resolver` (слово человека → значение базы), `corpus` (самый дорогой и нужен
# реже всех — только когда буквальный отбор дал ноль).
# Зачем разделение: [замер 02.08] на своём эмбеддере 4,6 строки/с, то есть боевая база
# целиком — около 34 часов, а метки — пять минут. Система работоспособна после КАЖДОЙ
# цели, и заставлять её ждать сутки ради корпуса, который нужен реже всего, — неверно.
#
# Использование: embed_all.sh [потоков]
# Окружение:     SERENEDB_DSN, EMBED_API_KEYS|EMBED_API_KEY, EMBED_HOST, EMBED_PATH,
#                EMBED_MODEL, EMBED_TARGETS, EMBED_ROUNDS
set -u
N="${1:-${BUILD_EMBED_WORKERS:-32}}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
export SERENEDB_DSN="$DSN"
cd "$(dirname "$0")" || exit 1

DB=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DB" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }

IFS=',' read -r -a KEYS <<< "${EMBED_API_KEYS:-${EMBED_API_KEY:-${ALIBABA_API_KEYS:-${ALIBABA_API_KEY:-}}}}"
# 🔴 НЕСКОЛЬКО АДРЕСОВ — ПО ОДНОМУ НА КАРТУ. `EMBED_HOSTS` (через запятую) заводит по
# секрету на адрес, и потоки досчёта раскладываются по ним по кругу — тем же механизмом,
# что был сделан под несколько ключей облака.
# Зачем: [замер 02.08] балансировщик перед несколькими копиями эмбеддера отдавал
# скорость ОДНОЙ из них при любом числе потоков, а прямое обращение к каждой —
# кратно больше. Один «удобный» адрес стоил половины мощности.
# 🔴 ЭТО ВЕРНО НЕ ПРО ЛЮБОЙ БАЛАНСИР. [замер 19.08, klient-1] балансир с раскладкой
# least-inflight дал 71,3 строк/с против 74,5 у четырёх прямых адресов — то есть
# наравне, а при добавлении карт он ещё и не требует правки настроек. Плохим был
# конкретный балансир 02.08, а не сам приём; прежняя формулировка обобщала лишнее.
# Проверять надо замером на своём балансире, а не отвергать заранее.
# 🔴 И ГЛАВНОЕ: число адресов не поднимает одновременность само по себе — наружу уходит
# ровно `threads` запросов (доки how_to_tune_workloads#querying-remote-files, [замер
# 20.08]: 42 потока → ровно 18 запросов при threads=18). Адреса делят нагрузку между
# картами, а не увеличивают её. Разбор — `docs/EMBED_BULK_HOWTO.md`.
IFS=',' read -r -a HOSTS <<< "${EMBED_HOSTS:-${EMBED_HOST:-}}"
[ ${#HOSTS[@]} -gt 0 ] || HOSTS=("${EMBED_HOST:-}")
# Адрес и модель эмбеддера задаются явно: умолчание с именем поставщика однажды уже
# означало бы, что забытая переменная тихо уводит вектор в чужое облако другой моделью,
# а разные модели дают НЕСРАВНИМЫЕ векторы без единой ошибки.
[ -n "${EMBED_HOST:-}" ] && [ -n "${EMBED_PATH:-}" ] \
  || { echo "не заданы EMBED_HOST/EMBED_PATH (адрес эмбеддера)" >&2; exit 1; }
[ -n "${EMBED_MODEL:-}" ] || { echo "не задан EMBED_MODEL (модель эмбеддера)" >&2; exit 1; }
umask 077
SEC=$(mktemp); LIST=""
# 🔴 У КАЖДОГО АДРЕСА МОЖЕТ БЫТЬ СВОЙ КЛЮЧ. Запись `EMBED_HOSTS` — «адрес» или
# «адрес|ключ»: копии эмбеддера бывают на разных машинах, и общий ключ там не работает.
# Без своего ключа берётся общий (`EMBED_API_KEYS`), и тогда получается прежнее поведение
# «все адреса × все ключи».
PAIRS=()
for h in "${HOSTS[@]}"; do
  h="$(printf '%s' "$h" | tr -d ' ')"
  [ -z "$h" ] && continue
  case "$h" in
    *"|"*) PAIRS+=("${h%%|*}|${h#*|}") ;;
    *)     for k0 in "${KEYS[@]}"; do PAIRS+=("$h|$(printf '%s' "$k0" | tr -d ' ')"); done ;;
  esac
done
for i in "${!PAIRS[@]}"; do
  h="${PAIRS[$i]%%|*}"; k="${PAIRS[$i]#*|}"
  [ -z "$k" ] || [ -z "$h" ] && continue
  # Одинарные кавычки в ключе удваиваются — иначе оператор сломается, и обрывок ключа
  # уйдёт в текст ошибки. Файл, а не аргумент: в командной строке ключ виден любому `ps`.
  printf "CREATE OR REPLACE TEMPORARY SECRET emb_%s_%s (TYPE openai, api_key '%s', base_url '%s', embeddings_path '%s');\n" \
    "$DB" "$i" "$(printf '%s' "$k" | sed "s/'/''/g")" \
    "$h" "$EMBED_PATH" >> "$SEC"
  LIST="$LIST emb_${DB}_${i}"
done
[ -n "$LIST" ] || { echo "не задан ни один ключ эмбеддера" >&2; rm -f "$SEC"; exit 1; }
# Вывод гасится целиком: при ошибке psql печатает ОПЕРАТОР, а в нём ключ.
psql "$DSN" -q -f "$SEC" >/dev/null 2>&1 || { echo "секреты не созданы" >&2; rm -f "$SEC"; exit 1; }
rm -f "$SEC"
if [ -f "$(dirname "$0")/box_tune.sh" ]; then
  # shellcheck disable=SC1091
  . "$(dirname "$0")/box_tune.sh"
  embed_secrets_base_url_check || { echo "base_url секретов openai не совпал с EMBED_HOST" >&2; exit 1; }
fi
export EMBED_SECRETS="${LIST# }"

cleanup() {
  local d=""
  for s in $EMBED_SECRETS; do d="$d DROP SECRET IF EXISTS $s;"; done
  psql "$DSN" -q -c "$d" >/dev/null 2>&1
}
trap cleanup EXIT INT TERM HUP

MAXLEN=${EMBED_MAXLEN:-3000}
TARGETS="${EMBED_TARGETS:-labels resolver corpus}"

# 🔴 ПЕРЕВЕКТОРИЗАЦИЯ ПРИ СМЕНЕ МОДЕЛИ — И ОТМЕТКА О НЕЙ.
# Векторы разных моделей несравнимы, но сравниваются БЕЗ ОШИБКИ: система не падает, она
# тихо выбирает не то. Поэтому при смене модели старые векторы обнуляются (`EMBED_RESET=1`),
# а в перепись кладётся отметка, КАКОЙ моделью посчитана таблица. Сервис ответов
# (`serene_ask.emb_ready`) включает поиск по смыслу только там, где отметка совпала с его
# моделью, — то есть смешать пространства нельзя даже по забывчивости.
reset_target() {
  local t="$1"
  psql "$DSN" -q -c "UPDATE $t SET emb = NULL WHERE emb IS NOT NULL;" || return 1
  mark_target "$t"
}
mark_target() {
  local t="$1"
  psql "$DSN" -q -c "DELETE FROM search_quality WHERE k = 'emb_model_$t';
       INSERT INTO search_quality SELECT 'emb_model_$t', epoch(now())::BIGINT,
              '$(printf '%s' "$EMBED_MODEL" | sed "s/'/''/g")';"
}

# 🔴 ДО ПЕРВОГО ВЕКТОРА: та ли модель. Эндпоинт при неизвестном имени молча подставляет
# свою ([замер 02.08]), а несравнимые векторы не дают ни одной ошибки — см. embed_check.sh.
./embed_check.sh || { echo "досчёт не начат: эмбеддер отдаёт не ту модель" >&2; exit 1; }

echo "== досчёт  $(date -u +%H:%M:%S), потоков $N, адресов ${#HOSTS[@]}, ключей ${#KEYS[@]}, цели: $TARGETS"
[ "${EMBED_RESET:-0}" = "1" ] && echo "== 🔴 РЕЖИМ ПЕРЕВЕКТОРИЗАЦИИ: старые векторы целей обнуляются"

for tgt in $TARGETS; do
  case "$tgt" in labels) _t=search_tables;; resolver) _t=resolver_index;; corpus) _t=search_corpus;;
                 card) _t=search_entity_card;; *) _t="";; esac
  if [ "${EMBED_RESET:-0}" = "1" ] && [ -n "$_t" ]; then
    echo "== обнуление векторов $_t (смена модели на $EMBED_MODEL)  $(date -u +%H:%M:%S)"
    reset_target "$_t" || { echo "не удалось обнулить $_t" >&2; exit 1; }
  fi
  case "$tgt" in
    labels)
      # Метки сущностей — по ним идёт выбор сущности. Их полторы тысячи, считаются минуты.
      # Service не эмбеддим: отбор кандидатов их отсекает по class (возврат 2).
      echo "== метки сущностей  $(date -u +%H:%M:%S)"
      ROWS_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e
                              WHERE e.src_table = search_tables.src_table AND e.cls = 'service')" \
        ./embed_missing.sh search_tables label "$N" "src_table" || echo "метки: проход с ошибкой" >&2
      ;;
    resolver)
      # Вход обрезается ЗДЕСЬ, а не в таблице: `resolver_index.value` идёт в предикат
      # `WHERE`, и обрезанное значение перестало бы совпадать с данными.
      # Service в resolver_build уже не попадает; фильтр — второй рубеж.
      echo "== резолвер  $(date -u +%H:%M:%S)"
      ROWS_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e
                              WHERE lower(e.src_table) = lower(resolver_index.table_name)
                                AND e.cls = 'service')" \
        ./embed_missing.sh resolver_index "substr(value,1,$MAXLEN)" "$N" "table_name,column_name,value" \
        || echo "резолвер: проход с ошибкой" >&2
      ;;
    corpus)
      echo "== корпус, НЕ служебные сущности  $(date -u +%H:%M:%S)"
      ROWS_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e
                              WHERE e.src_table = search_corpus.src_table AND e.cls = 'service')" \
        ./embed_missing.sh search_corpus "substr(doc,1,$MAXLEN)" "$N" "src_table,row_key" \
          || echo "корпус (бизнес): проход с ошибкой" >&2
      # Служебным вектор не считается — решение владельца 29.07. Они целиком в корпусе и в
      # текстовом индексе (находятся по словам), а отсутствие вектора названо в переписи
      # причиной (`cov_noemb_service`). Вернуть прежнее: `EMBED_SERVICE=1`.
      if [ "${EMBED_SERVICE:-0}" = "1" ]; then
        echo "== корпус, остальные строки, включая служебные  $(date -u +%H:%M:%S)"
        ./embed_missing.sh search_corpus "substr(doc,1,$MAXLEN)" "$N" "src_table,row_key" \
          || echo "корпус (служебные): проход с ошибкой" >&2
      else
        echo "== служебным вектор не считается (решение владельца)"
      fi
      ;;
    card)
      # Карточка сущности — поверхность отбора кандидатов (`entity_card_build.sql`).
      # Считается вектор ВСЕЙ карточки, а не одной метки: метка как поисковый сигнал у нас
      # замерена и признана слабой ([замер 27.07] у «продажи» ближайшая метка — «Склады»,
      # верный документ не входит даже в тройку). Проверить, лучше ли карточка метки, —
      # и есть смысл Ф2 плана `work/entity-choice/PLAN_ENTITY_SURFACE.md`.
      # 🔴 В такт НЕ включено: цель по умолчанию не входит в `TARGETS`, зовётся только явно
      # (`EMBED_TARGETS=card`). Включать в конвейер — после решения по числу (Ф5).
      echo "== карточки сущностей  $(date -u +%H:%M:%S)"
      # Service в entity_card_build уже отфильтрован; ROWS_WHERE — второй рубеж.
      ROWS_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e
                              WHERE e.src_table = search_entity_card.src_table AND e.cls = 'service')" \
        ./embed_missing.sh search_entity_card "substr(card,1,$MAXLEN)" "$N" "src_table" \
        || echo "карточки: проход с ошибкой" >&2
      # 🔴 Отметка модели ставится ВСЕГДА, а не только при перевекторизации: без неё
      # `serene_ask.emb_ready(CARD)` отвечает «не готово», и сервис молча работает по
      # метке — то есть посчитанные векторы не участвовали бы ни в одном ответе.
      mark_target search_entity_card
      # Индекс карточки публикуется заново по той же причине, что и корпусный ниже.
      psql "$DSN" -q -c "VACUUM (REFRESH_INDEX) search_entity_card;" >/dev/null 2>&1
      psql "$DSN" -tA -F' | ' -c "SELECT 'карточки: с вектором', count(emb),
             'без вектора', count(*) - count(emb) FROM search_entity_card"
      ;;
    *) echo "неизвестная цель досчёта: $tgt (знаю labels, resolver, corpus, card)" >&2 ;;
  esac
done

# 🔴 Индекс публикуется ЗАНОВО: досчёт правит `emb` уже после последней публикации, и без
# этого шага индекс отдавал бы строки со старым вектором.
echo "== публикация индекса  $(date -u +%H:%M:%S)"
psql "$DSN" -q -c "VACUUM (REFRESH_INDEX) search_corpus;" >/dev/null 2>&1

psql "$DSN" -tA -F' | ' -c "
  SELECT 'метки: с вектором', count(emb), 'без вектора', count(*) - count(emb) FROM search_tables
  UNION ALL SELECT 'резолвер: с вектором', count(emb), 'без вектора', count(*) - count(emb) FROM resolver_index
  UNION ALL SELECT 'корпус: с вектором', count(emb), 'без вектора', count(*) - count(emb) FROM search_corpus"
