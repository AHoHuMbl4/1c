#!/bin/bash
# ПУБЛИКАЦИЯ ВИКИ — штатный шаг такта (зов из build.sh не меняется).
#
# Э7 (б1, docs/drafts/e7-wiki-dump-in-engine.md): текст страниц собирает и
# хранит БАЗА (`wiki_build.sql` → VIEW `wiki_pages`). Файловый контур
# SELECT → Python → entities/*.md + purge СНЯТ: штатный COPY TO пишет один
# файл / Hive, а не раскладку memory-wiki (доки SereneDB COPY … TO). Перефраз
# сущностей для бота — `search_entity_alias` (шаг wiki_alias), ask уже читает
# алиасы из движка без disk-vault.
#
# Своим кодом здесь больше ничего не делается: compile/memory index entity-
# страниц из такта не зовём (потребитель .md на диске, если остался, читает
# прежнее дерево; такт его не переписывает).
set -u
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
cd "$(dirname "$0")" || exit 1

# Имя базы спрашиваем У БАЗЫ, а не разбираем DSN (`HOW_NOT_TO §3.9`).
DBNAME=$(psql "$DSN" -tAc "SELECT current_database()" 2>/dev/null | tr -d '[:space:]')
[ -n "$DBNAME" ] || { echo "вики: база не отвечает — шаг пропущен"; exit 0; }

psql "$DSN" -q -v ON_ERROR_STOP=1 -f wiki_build.sql >/dev/null || {
  echo "вики: wiki_build.sql не прошёл" >&2
  exit 1
}

echo "вики: Э7 — страницы в wiki_pages (движок), файловый dump снят (база $DBNAME)"
exit 0
