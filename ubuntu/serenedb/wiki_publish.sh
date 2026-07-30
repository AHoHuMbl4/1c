#!/bin/bash
# ПУБЛИКАЦИЯ ВИКИ OPENCLAW — штатный шаг такта, не ручная операция.
#
# 🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ ШАГ В КОНВЕЙЕРЕ. Замечание владельца 30.07: «дословно как в базе — это ТЫ
# делаешь, а должна система при любой базе вообще». Первую вики я собрал своим скриптом из
# /tmp для одной базы — на чужой базе её бы не появилось, а по п. 14 любой ручной шаг при
# установке считается дефектом. Поэтому шаг живёт в репозитории, раскладывается `deploy.sh` и
# вызывается тактом.
#
# Разделение труда: текст страниц собирает БАЗА (`wiki_build.sql`, представление `wiki_pages`),
# здесь только запись файлов и штатная компиляция — того, чего движок не умеет (п. 20).
#
# Если OpenClaw на машине нет или вики не включена — шаг МОЛЧА пропускается и такт не падает:
# вики улучшает выбор сущности, но ответы без неё работают.
set -u
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
BOTUSER="${OPENCLAW_USER:-undebot}"
cd "$(dirname "$0")" || exit 1

command -v openclaw >/dev/null 2>&1 || { echo "вики: openclaw не установлен — шаг пропущен"; exit 0; }
VAULT=$(sudo -u "$BOTUSER" -H openclaw wiki status 2>/dev/null | sed -n 's/^Vault: ready (\(.*\))$/\1/p')
[ -n "$VAULT" ] || { echo "вики: хранилище не готово (плагин memory-wiki выключен?) — шаг пропущен"; exit 0; }

psql "$DSN" -q -v ON_ERROR_STOP=1 -f wiki_build.sql >/dev/null || { echo "вики: wiki_build.sql не прошёл" >&2; exit 1; }

# Страницы выгружаются ОДНИМ запросом. Разделитель — символ, которого в тексте страницы быть
# не может (записи разделены \x1e, поля \x1f): подстроки и переводы строк внутри тела не мешают.
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
psql "$DSN" -tA -R $'\x1e' -F $'\x1f' -c "SELECT page_id, body FROM wiki_pages" > "$TMP/dump" || {
  echo "вики: выгрузка страниц не удалась" >&2; exit 1; }

python3 - "$TMP/dump" "$VAULT/entities" <<'PY'
import os, sys
dump, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
data = open(dump, encoding='utf-8').read()
n = 0
for rec in data.split('\x1e'):
    if '\x1f' not in rec:
        continue
    page_id, body = rec.split('\x1f', 1)
    page_id = page_id.strip()
    if not page_id:
        continue
    # Имя файла — идентификатор сущности от платформы; посторонних символов в нём нет,
    # но проверяем, чтобы страница не могла уйти за пределы каталога.
    if '/' in page_id or page_id.startswith('.'):
        continue
    open(os.path.join(out, page_id + '.md'), 'w', encoding='utf-8').write(body.rstrip('\n') + '\n')
    n += 1
print('вики: записано страниц %d' % n)
PY

chown -R "$BOTUSER":"$BOTUSER" "$VAULT/entities" 2>/dev/null
sudo -u "$BOTUSER" -H openclaw wiki compile 2>&1 | tail -2
