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
# Идемпотентно: спрашиваются только сущности, которых ещё нет в `search_entity_alias`.
# Использование: wiki_alias.sh [сущностей за прогон]   (0 или пусто = все оставшиеся)
set -u
DSN="${SERENEDB_DSN:-host=127.0.0.1 port=7890 user=postgres dbname=postgres}"
BOTUSER="${OPENCLAW_USER:-undebot}"
BATCH="${WIKI_ALIAS_BATCH:-20}"
CAP="${1:-0}"
cd "$(dirname "$0")" || exit 1

command -v openclaw >/dev/null 2>&1 || { echo "алиасы: openclaw не установлен — шаг пропущен"; exit 0; }
psql "$DSN" -q -c "CREATE TABLE IF NOT EXISTS search_entity_alias (src_table VARCHAR, aliases VARCHAR, best_used_for VARCHAR, not_enough_for VARCHAR, seen_at TIMESTAMP)" >/dev/null 2>&1

# 🔴 ОБМЕН ФАЙЛАМИ — ТОЛЬКО ЧЕРЕЗ КАТАЛОГ, ЧИТАЕМЫЙ ДВИЖКОМ. [замер 30.07] `read_json` из
# `/tmp/...` даёт «No files found»: процесс `serened` этот путь не видит. Тот же каталог, что у
# загрузчика (`CSV_DIR`, по умолчанию `/var/lib/serenedb`).
EXCH="${CSV_DIR:-/var/lib/serenedb}"
TMP=$(mktemp -d "$EXCH/wiki-alias-XXXXXX") || { echo "алиасы: нет доступа к $EXCH" >&2; exit 0; }
chmod 755 "$TMP"; trap 'rm -rf "$TMP"' EXIT
done_total=0
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
        AND NOT EXISTS (SELECT 1 FROM search_entity_alias a WHERE a.src_table = f.src_table)
      ORDER BY f.src_table LIMIT 1)
    SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                    quantities := coalesce(measures,''))))
    FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
            FROM wiki_entity_facts f
            JOIN search_tables t ON t.src_table = f.src_table
           WHERE f.cls <> 'service'
             AND NOT EXISTS (SELECT 1 FROM search_entity_alias a WHERE a.src_table = f.src_table)
           ORDER BY d, f.src_table LIMIT $BATCH)" > "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac

  # 🔴 ЗАДАНИЕ ПЕРЕДАЁТСЯ ФАЙЛОМ, А НЕ АРГУМЕНТОМ. [замер 30.07] с `-m "$PAY"` на пачке из 25
  # сущностей команда отвечала «Missing message»: длинный JSON в аргументе командной строки не
  # доходит. У `openclaw agent` для этого есть штатный `--message-file`. Тот же класс дефекта, что
  # «стена argv» в разборе `HOW_NOT_TO §0`: данные аргументом командной строки не передаются.
  {
    printf '%s' "Return JSON only, no prose, no code fences. The record types below are CLOSE IN MEANING to each other — that is why they are shown together. For each one, in the SAME language as its title: (1) aliases — the words and phrases a business user of this database would use when asking about it; (2) bestUsedFor — the questions it answers; (3) notEnoughFor — what it does NOT answer, and this field MUST name the SIBLING record types from this same list that a person could confuse it with, and say which of them answers that instead. Be concrete: name them. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  sudo -u "$BOTUSER" -H openclaw agent --agent main --session-key wiki-alias --json \
    --message-file "$TMP/msg" \
    > "$TMP/ans" 2>"$TMP/err" || { echo "алиасы: агент не ответил: $(head -c 200 "$TMP/err")" >&2; break; }

  # Разбор ответа модели — своим кодом это разрешено (п. 20: проверка ответа модели).
  python3 - "$TMP/ans" "$TMP/rows.json" <<'PY'
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
    cands = list(dig(env))
    text = max(cands, key=len) if cands else ''
except ValueError:
    text = raw
m = re.search(r'\{.*\}', text, re.S)
rows = []
if m:
    try:
        for it in (json.loads(m.group(0)).get('items') or []):
            e = (it.get('entity') or '').strip()
            if not e:
                continue
            def j(x):
                return ', '.join(str(i).strip() for i in (x or []) if str(i).strip())[:900]
            rows.append({"src_table": e, "aliases": j(it.get('aliases')),
                         "best_used_for": j(it.get('bestUsedFor')),
                         "not_enough_for": j(it.get('notEnoughFor'))})
    except ValueError:
        pass
open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(rows, ensure_ascii=False))
print("алиасов разобрано: %d" % len(rows))
PY
  # Запись — ОДНИМ запросом из файла, без цикла по строкам (п. 20).
  psql "$DSN" -q -c "
    INSERT INTO search_entity_alias
    SELECT src_table, aliases, best_used_for, not_enough_for, now()
    FROM read_json('$TMP/rows.json', columns := {src_table:'VARCHAR', aliases:'VARCHAR',
                                                best_used_for:'VARCHAR', not_enough_for:'VARCHAR'})
    WHERE src_table NOT IN (SELECT src_table FROM search_entity_alias)" 2>&1 | grep -i error

  have=$(psql "$DSN" -tAc "SELECT count(*) FROM search_entity_alias" 2>/dev/null)
  echo "алиасы: всего в базе $have"
  done_total=$((done_total + BATCH))
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
done
psql "$DSN" -tA -F' | ' -c "SELECT 'алиасов в базе', count(*) FROM search_entity_alias"
