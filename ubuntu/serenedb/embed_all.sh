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
# Очерёдность та же, что в такте: сначала НЕ служебные сущности, потом остальные
# (`corpus_build.sql` → `search_entity_class`). Это не отбор: второй проход идёт без
# сужения и покрывает всё (п. 13).
#
# Ключи берутся из `ALIBABA_API_KEYS` (через запятую) либо из одиночного
# `ALIBABA_API_KEY`. На каждый создаётся свой временный секрет, потоки раскладываются по
# ключам по кругу. Секреты именуются по базе — они у движка ОБЩИЕ НА ИНСТАНС, и одно имя
# на все базы гасило бы эмбеддер соседней сборки (`techContext` ловушка 26).
#
# Использование: embed_all.sh [потоков]
# Окружение:     SERENEDB_DSN, ALIBABA_API_KEYS|ALIBABA_API_KEY, EMBED_ROUNDS
set -u
N="${1:-${BUILD_EMBED_WORKERS:-32}}"
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
export SERENEDB_DSN="$DSN"
cd "$(dirname "$0")" || exit 1

DB=$(psql "$DSN" -tAc 'SELECT current_database()' 2>/dev/null | tr -cd 'A-Za-z0-9_')
[ -n "$DB" ] || { echo "движок не отвечает, имя базы не получено" >&2; exit 1; }

IFS=',' read -r -a KEYS <<< "${ALIBABA_API_KEYS:-${ALIBABA_API_KEY:-}}"
umask 077
SEC=$(mktemp); LIST=""
for i in "${!KEYS[@]}"; do
  k="$(printf '%s' "${KEYS[$i]}" | tr -d ' ')"
  [ -z "$k" ] && continue
  # Одинарные кавычки в ключе удваиваются — иначе оператор сломается, и обрывок ключа
  # уйдёт в текст ошибки. Файл, а не аргумент: в командной строке ключ виден любому `ps`.
  printf "CREATE OR REPLACE TEMPORARY SECRET emb_%s_%s (TYPE openai, api_key '%s', base_url '%s', embeddings_path '%s');\n" \
    "$DB" "$i" "$(printf '%s' "$k" | sed "s/'/''/g")" \
    "${EMBED_HOST:-https://dashscope-intl.aliyuncs.com}" \
    "${EMBED_PATH:-/compatible-mode/v1/embeddings}" >> "$SEC"
  LIST="$LIST emb_${DB}_${i}"
done
[ -n "$LIST" ] || { echo "не задан ни один ключ эмбеддера" >&2; rm -f "$SEC"; exit 1; }
# Вывод гасится целиком: при ошибке psql печатает ОПЕРАТОР, а в нём ключ.
psql "$DSN" -q -f "$SEC" >/dev/null 2>&1 || { echo "секреты не созданы" >&2; rm -f "$SEC"; exit 1; }
rm -f "$SEC"
export EMBED_SECRETS="${LIST# }"

cleanup() {
  local d=""
  for s in $EMBED_SECRETS; do d="$d DROP SECRET IF EXISTS $s;"; done
  psql "$DSN" -q -c "$d" >/dev/null 2>&1
}
trap cleanup EXIT INT TERM HUP

echo "== досчёт: сначала НЕ служебные сущности  $(date -u +%H:%M:%S), потоков $N, ключей ${#KEYS[@]}"
ROWS_WHERE="NOT EXISTS (SELECT 1 FROM search_entity_class e
                        WHERE e.src_table = search_corpus.src_table AND e.cls = 'service')" \
  ./embed_missing.sh search_corpus doc "$N" "src_table,row_key" || echo "первый проход завершился с ошибкой" >&2

echo "== досчёт: остальные строки  $(date -u +%H:%M:%S)"
./embed_missing.sh search_corpus doc "$N" "src_table,row_key" || echo "второй проход завершился с ошибкой" >&2

# 🔴 Индекс публикуется ЗАНОВО: досчёт правит `emb` уже после последней публикации, и без
# этого шага индекс отдавал бы строки со старым вектором.
echo "== публикация индекса  $(date -u +%H:%M:%S)"
psql "$DSN" -q -c "VACUUM (REFRESH_INDEX) search_corpus;" >/dev/null 2>&1

psql "$DSN" -tA -F' | ' -c "SELECT 'с вектором', count(emb), 'без вектора', count(*) - count(emb) FROM search_corpus"
