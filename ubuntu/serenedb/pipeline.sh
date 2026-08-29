#!/bin/bash
# ОДИН ТАКТ КОНВЕЙЕРА: витрина (дельта из 1С) → поисковый слой.
#
# Понятия «ночной» нет. Такт запускается ПО ГОТОВНОСТИ — следующий стартует, когда
# закончился предыдущий (таймер `OnUnitInactiveSec`), а не по расписанию. Значит свежесть
# = длительность такта: на маленькой базе это секунды, на большой — минуты, и система
# подстраивается сама, без зашитого интервала (указание владельца 28.07).
#
# Порядок значим и атомарен:
#   1. синк тянет из 1С ТОЛЬКО изменения (дельта по DataVersion) в витрину;
#   2. сборка делает из витрины корпус/индекс/резолвер, эмбеддинг — только изменённым.
# Оба шага работают только внутри движка и 1С; наружу уходит лишь вызов модели (п. 20).
set -u
cd /opt/1c-mcp-reports || exit 1
# shellcheck disable=SC1091
. ./tick_status.sh

# 🔴 ФОРМА EMBED_HOST ДО СИНКА. Синк на большой базе идёт часами; голый хост
# (замер 17.08, код 000) не должен сжигать это время. Живая дверь — в build.sh.
if [ -x ./box_tune.sh ]; then
  # shellcheck disable=SC1091
  . ./box_tune.sh
  embed_hosts_form_check || {
    echo "конвейер остановлен: EMBED_HOST без схемы+порта" >&2
    tick_status_fail "pipeline" "preflight"
    exit 1
  }
fi

# Раскладка кода из репозитория — ТОЛЬКО на стенде разработки, где переменная задана.
# В продукте установщик кладёт файлы один раз и `SERENE_SRC_DIR` пуста, так что конвейер
# не зависит от наличия репозитория. Нужно потому, что [замер 28.07] забытое копирование
# гоняло чужую базу по старым файлам, а выглядело это как дефект кода.
if [ -n "${SERENE_SRC_DIR:-}" ] && [ -x "$SERENE_SRC_DIR/deploy.sh" ]; then
  echo "== раскладка кода из $SERENE_SRC_DIR"
  "$SERENE_SRC_DIR/deploy.sh" /opt/1c-mcp-reports || echo "раскладка не удалась, идём на том, что лежит" >&2
fi

echo "== синк витрины (дельта из 1С)"
# Частичные ошибки одной сущности не должны рушить весь такт: витрина обновляется тем,
# что удалось, а сборка идёт по имеющемуся. Код возврата синка не прерывает конвейер.
#
# Packet: ETL_ODATA_BASE — каталог снимка. Синк отвечает changed=0 и делает
# DELETE FROM search_changed_sources. Apply кладёт отметки дописыванием; снимок
# до синка возвращает их сборке. Иначе merge видит пустой список и пересобирает 0
# при живом расхождении (okna 18.08 18:41/18:51: «изменились таблицы витрины: 0»
# → «пересобирали 0 из 351»). Доки: sql/statements/insert, sql/statements/delete.
KEEP_MARKS=0
if [ -d "${ETL_ODATA_BASE:-}" ]; then
  KEEP_MARKS=1
  psql "$SERENEDB_DSN" -q -v ON_ERROR_STOP=1 -c \
    "CREATE OR REPLACE TABLE tmp_changed_keep AS SELECT src_table FROM search_changed_sources;" \
    || KEEP_MARKS=0
fi
/opt/openclaw-mcp/venv/bin/python serene_sync.py || echo "синк: частичные ошибки, см. выше"
if [ "$KEEP_MARKS" = 1 ]; then
  n=$(psql "$SERENEDB_DSN" -tA -c \
    "INSERT INTO search_changed_sources SELECT src_table FROM tmp_changed_keep WHERE src_table NOT IN (SELECT src_table FROM search_changed_sources); SELECT count(*) FROM search_changed_sources; DROP TABLE tmp_changed_keep;")
  echo "packet: отметки search_changed_sources возвращены сборке, строк $n"
fi

echo "== сборка поискового слоя"
./build.sh
exit $?
