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
# Развести конкретное слово, а не самое спорное: путь «сначала прогон, потом точечная правка».
TARGET_WORD="${WIKI_ALIAS_WORD:-}"
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
skipped=0
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
    printf '%s' "Return JSON only, no prose, no code fences. IMPORTANT about aliases: they name the RECORD TYPE ITSELF — how a person refers to this kind of record — never a bare column name. BUT a record type must be findable by WHAT IT HOLDS: if its quantities include one, the aliases must contain the natural way people ask for that value here. [замер 30.07] the line items of a purchase document hold the VAT amount, yet their aliases said only «what we bought», so a question about VAT paid to suppliers landed on a register about paying VAT to the budget and answered 2 719 573,23 instead of 11 036 086,09. The record types below are CLOSE IN MEANING to each other — that is why they are shown together. For each one, in the SAME language as its title: (1) aliases — the words and phrases a business user of this database would use when asking about it; (2) bestUsedFor — the questions it answers; (3) notEnoughFor — what it does NOT answer, and this field MUST name the SIBLING record types from this same list that a person could confuse it with, and say which of them answers that instead. Be concrete: name them. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  sudo -u "$BOTUSER" -H openclaw agent --agent main --session-key wiki-alias --json \
    --message-file "$TMP/msg" \
    > "$TMP/ans" 2>"$TMP/err" || {
      # 🔴 ОДНА ОСЕЧКА НЕ ОСТАНАВЛИВАЕТ ВСЁ. [замер 30.07] на 143-й сущности из 686 модель
      # не ответила в срок (`LLM request timed out`), и прежний код обрывал цикл целиком —
      # остальные 543 остались без описания из-за одной пачки. Теперь пачка пропускается,
      # а её сущности помечаются, чтобы следующий проход не спотыкался о них снова и не
      # ходил по кругу. Сколько пропущено — печатается в конце, молчания тут быть не должно.
      skipped=$((skipped + 1))
      echo "алиасы: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql "$DSN" -q -c "INSERT INTO search_entity_alias
        SELECT entity, '', '', '', now() FROM read_json('$TMP/pay',
          columns := {entity:'VARCHAR', title:'VARCHAR', quantities:'VARCHAR'})
        WHERE entity NOT IN (SELECT src_table FROM search_entity_alias)" >/dev/null 2>&1
      continue
    }

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
  rounds=0
  while [ "$rounds" -lt "${WIKI_ALIAS_COLLISION_ROUNDS:-40}" ]; do
    rounds=$((rounds + 1))
    psql "$DSN" -tA -c "
      WITH al AS (SELECT src_table, trim(lower(x.a)) AS alias
                    FROM search_entity_alias, unnest(str_split(aliases, ',')) AS x(a)
                   WHERE trim(x.a) <> ''),
           dup AS (SELECT alias FROM al GROUP BY 1 HAVING count(DISTINCT src_table) > 1),
           -- Обычно берём САМОЕ спорное слово: у него больше всего сущностей.
           -- 🔴 Но можно назвать слово прямо, переменной WIKI_ALIAS_WORD, — быстрый путь,
           -- когда
           -- прогон приёмки уже показал, ГДЕ система спуталась: разводим ровно тех, кто
           -- ошибся, а не ждём, пока очередь дойдёт. Цель владельца 30.07 — «сто процентов
           -- верных ответов, даже если для этого надо 2-3 раза переспросить»; значит
           -- чинить надо по факту ошибки, а не подряд.
           top AS (SELECT a.alias FROM al a JOIN dup d ON d.alias = a.alias
                    WHERE ('$TARGET_WORD' = '' OR a.alias = lower('$TARGET_WORD'))
                      AND NOT EXISTS (SELECT 1 FROM search_entity_alias s
                                       WHERE s.src_table = a.src_table
                                         AND s.not_enough_for ILIKE '%' || a.alias || '%')
                    GROUP BY 1 ORDER BY count(DISTINCT a.src_table) DESC, 1 LIMIT 1)
      SELECT to_json(list(struct_pack(entity := f.src_table, title := f.label,
                                      quantities := coalesce(f.measures,''))))
      FROM (SELECT f.* FROM wiki_entity_facts f
             WHERE f.src_table IN (SELECT src_table FROM al WHERE alias = (SELECT alias FROM top))
             -- 🔴 ПРЕДЕЛ ОБЯЗАТЕЛЕН: число сущностей на одно спорное слово растёт с размером
             -- базы (у нас со словом «НДС» их 18), а весь список уходит в модель — это п. 19,
             -- объём в модель не должен зависеть от размера базы. Не влезшие в пачку
             -- разведутся следующим кругом: слово останется спорным, пока их не разведут.
             ORDER BY f.src_table LIMIT $BATCH) f" \
      > "$TMP/pay" 2>/dev/null
    PAY=$(cat "$TMP/pay")
    case "$PAY" in ''|'[]'|'null') break;; esac
    {
      printf '%s' "Return JSON only, no prose, no code fences. The record types below are ALL CALLED BY THE SAME WORD in this database, which is exactly the problem: a person using that word could mean any of them. For each one, in the SAME language as its title: (1) aliases — how a person refers to THIS record type, and remove any word that fits the others equally well unless it is genuinely its own name; never use a quantity or column name; (2) bestUsedFor — what only this one answers; (3) notEnoughFor — MUST name the OTHER record types from this very list and say what each of them answers instead. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
      cat "$TMP/pay"
    } > "$TMP/msg"
    chmod 644 "$TMP/msg"
    sudo -u "$BOTUSER" -H openclaw agent --agent main --session-key wiki-alias --json \
      --message-file "$TMP/msg" > "$TMP/ans" 2>"$TMP/err" || {
        echo "разведение: пачка пропущена ($(head -c 100 "$TMP/err" | tr -d '\n'))" >&2; continue; }
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
    psql "$DSN" -q -c "
      UPDATE search_entity_alias a SET aliases = n.aliases, best_used_for = n.best_used_for,
             not_enough_for = n.not_enough_for, seen_at = now()
      FROM read_json('$TMP/rows.json', columns := {src_table:'VARCHAR', aliases:'VARCHAR',
             best_used_for:'VARCHAR', not_enough_for:'VARCHAR'}) n
      WHERE a.src_table = n.src_table" >/dev/null 2>&1
  done
  echo "разведение столкновений: кругов $rounds"
fi

[ "$skipped" -gt 0 ] && echo "алиасы: пачек пропущено из-за отказа модели: $skipped" >&2
psql "$DSN" -tA -F' | ' -c "
  SELECT 'алиасов в базе', count(*) FROM search_entity_alias
  UNION ALL SELECT 'из них ПУСТЫХ (модель не ответила)', count(*) FROM search_entity_alias
    WHERE coalesce(aliases,'') = ''"
