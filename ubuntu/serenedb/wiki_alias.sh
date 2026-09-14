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
# Память «слово уже разводили» (collision). Песочница задаёт свою — иначе пометки
# уйдут в боевую probe и следующий боевой круг молча пропустит эти слова (п.13).
PROBE_TABLE="${PROBE_TABLE:-search_alias_probe}"
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
# Модель/thinking — вызов через alias_infer_gateway.py (рантайм agent/infer).
# 🔴 Транспорт: умолчание --local (cli/infer.md). [замер 24.08] --gateway =
# RPC-потолок 120 с → GatewayTransportError; loc 1034 с / пачка 20 — exit 0.
# Умолчание модели — OpenRouter qwen/qwen3.8-27b (провайдер vllm в конфиге HOME
# смотрит на openrouter.ai); своя GPU vLLM — через WIKI_ALIAS_MODEL.
WIKI_ALIAS_MODEL="${WIKI_ALIAS_MODEL:-vllm/qwen/qwen3.8-27b}"
WIKI_ALIAS_THINKING="${WIKI_ALIAS_THINKING:-off}"
# Force-перегенерация непустых aliases (песочница; штатный путь без флага = 0).
WIKI_ALIAS_FORCE="${WIKI_ALIAS_FORCE:-0}"
case "$WIKI_ALIAS_FORCE" in 1) WIKI_ALIAS_FORCE=1;; *) WIKI_ALIAS_FORCE=0;; esac
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"

# Общие psql-параметры: таблицы и retry — один -f вместо веера -c (п. 20, Э1а).
psql_wa() {
  psql "$DSN" -q -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v probe_table="$PROBE_TABLE" \
    -v retry_h="$RETRY_H" \
    -v force="$WIKI_ALIAS_FORCE" \
    "$@"
}
psql_wa_tA() {
  psql "$DSN" -tA -v ON_ERROR_STOP=1 \
    -v alias_table="$ALIAS_TABLE" \
    -v measure_table="$MEASURE_TABLE" \
    -v probe_table="$PROBE_TABLE" \
    -v retry_h="$RETRY_H" \
    -v force="$WIKI_ALIAS_FORCE" \
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
BUDGET="${WIKI_ALIAS_MAX_SEC:-120}"  # 0 = без потолка (over_budget)
t_start=$(date +%s)
over_budget() { [ "$BUDGET" != "0" ] && [ $(( $(date +%s) - t_start )) -ge "$BUDGET" ]; }

# ── Промты «1 задача = 1 вызов» (dictfix-final-prompt.md, дословно) ──
_WA_INIT_A=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language when the title is in another language). TASK: for EACH record produce ONLY the aliases field — everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). RULES: (1) Include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. (2) WHEN the input for this record lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): at least ONE alias MUST be a spoken action/event form people use when asking about such events (same language as the title, 1-2 words). Keep that event alias even if a sibling could use a similar word — the sibling distinction belongs to the notEnoughFor field (a separate call), not to dropping the event alias. If you must drop something to fit the limit, drop a redundant noun synonym, never the event alias. For records without flows/quantities, event aliases are optional — include only when natural. (3) Limits: 3 to 10 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). (4) Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Do not put quantity names or field names into aliases (quantities are filled by a separate call). (5) BANS (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; NOUN words that equally fit a sibling in THIS batch (leave those out — the distinction goes to notEnoughFor; this ban is about nouns — spoken action/event forms stay, see rule 2); jargon opaque to a non-developer. (6) "If unsure — omit" applies to meta-labels and jargon; for action/event forms on records where Input lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): prefer one everyday event form over a near-duplicate noun synonym. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","aliases":["buyers","suppliers","customers"]}]} Never copy the English example strings into the output when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","aliases":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_INIT_B=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY). TASK: for EACH record produce ONLY the bestUsedFor field — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks, not full sentences). RULES: (1) No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). (2) No office jargon gerunds. Prefer spoken wording over metadata wording. (3) Hard format rule for EVERY string: no PARENTHESES WITH A COMMA INSIDE the string (parentheses without a comma, and commas outside parentheses, are fine). Rewrite enumerations with a dash or a word instead. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","bestUsedFor":["how many customers","who bought this month"]}]} Never copy the English example strings when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","bestUsedFor":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_INIT_C=$(cat <<'EOF_WA_PROMPT'
JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string = the language of that record's title (the English example below is STRUCTURE ONLY). TASK: for EACH record produce ONLY the notEnoughFor field — short strings telling what this record does NOT answer. TWO KINDS, both required when applicable: (a) THEMATIC "not me" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. When a sibling shares this record's action/event asking-words, name that shared topic here (what THAT sibling's events are). FORMAT RULES: no commas and no parentheses inside any string (downstream stores arrays as comma-CSV). Use a dash or the word "not"/"see" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it. Do not invent sibling names that are not in the input. Structure example (English skeleton only): {"items":[{"entity":"catalog_counterparties","notEnoughFor":["not stock balances","not price list","Organizations - our own companies not trading partners"]}]} Never copy the English example strings when the title language is different. Every Input entity appears once; entity values copy Input exactly. Schema: {"items":[{"entity":"<exact copy of Input entity string>","notEnoughFor":["..."]}]}. Input:
EOF_WA_PROMPT
)
_WA_COLL_A=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. Answer language = the language of each title. TASK: for EACH type produce ONLY the aliases field. RULES: (1) Keep "<SHARED_WORD>" in the list — people use it. Also keep the title if it is already an everyday asking-word; each alias is a distinct word — no grammatical variants of the same stem. (2) ADD 1-2 DISTINCTIVE everyday words or short phrases (1-3 words each) that a person would use when they mean THIS type and not the siblings. WHEN the input for this type lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): at least ONE of the added words MUST be a spoken action/event form people use when asking about such events (same language as the title). Keep that event word even if a sibling could use a similar one — the sibling distinction belongs to the notEnoughFor field (a separate call), not to dropping the event word. If only 1 confident — add just 1; quality over quantity. (3) Ground aliases only in this type title, its listed flows, and quantities from Input (and in its current aliases if Input lists them); take roles/event cues from listed flows and quantities only — do not invent flows or quantities. (4) Distinctive phrases may stay unique to this type, or overlap a sibling only when both truly share that role; empty contrast (only the shared word and bare title for every sibling) leaves siblings indistinguishable — give contrast with whole asking-words, not truncated title fragments. (5) Aliases are only concrete everyday words a person would type for THIS type. Match the title language exactly. When unsure a word is everyday for THIS type — omit it (this "unsure — omit" applies to noun words; for action/event forms on types where Input lists flows, OR lists quantities that are movement / money-total / event totals (not a bare headcount/Count alone): prefer one everyday event form over a near-duplicate noun synonym). Few-shot (English scaffold only; YOUR output language = language of each title). Shared word "party": {"items":[{"entity":"ent_partners","aliases":["party","partners","buyers"]},{"entity":"ent_counterparties","aliases":["party","counterparties","legal entities"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","aliases":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)
_WA_COLL_B=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database ("<SHARED_WORD>"). Answer language = the language of each title. TASK: for EACH type produce ONLY the bestUsedFor field — 2 to 4 short topic templates this type alone answers among the siblings (short phrases, not full sentences; topics belong to this type, not to a sibling). RULES: (1) No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a type that does not answer them). (2) No office jargon gerunds. Prefer spoken wording over metadata wording. (3) FORMAT RULE: no PARENTHESES WITH A COMMA INSIDE any string (parentheses without a comma, and commas outside parentheses, are fine). Rewrite enumerations with a dash or a word instead. Few-shot (English scaffold only): {"items":[{"entity":"ent_partners","bestUsedFor":["who we sell to","partner headcount"]},{"entity":"ent_counterparties","bestUsedFor":["taxpayer id","contract party"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","bestUsedFor":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)
_WA_COLL_C=$(cat <<'EOF_WA_PROMPT'
You are a database disambiguation engine. JSON only, no prose, no code fences. The record types in Input are ALL CALLED BY THE SAME WORD in this database. That shared word is "<SHARED_WORD>": a person who types only that word could mean any type below. Answer language = the language of each title. TASK: for EACH type produce ONLY the notEnoughFor field — when a person says "<SHARED_WORD>" but means a COMPETITOR TOPIC that another type in this list answers better, name that TOPIC (what they are looking for), then optionally the sibling title from Input. RULES: (1) Prefer themes over bare sibling names. Example shape: "stock on hand / warehouse balances — see <sibling title>"; "current price list — see <sibling title>". (2) Siblings come only from Input. (3) Each type includes the shared word "<SHARED_WORD>" in at least one notEnoughFor entry so later passes see the collision was addressed. (4) When a sibling shares this type's action/event asking-words, name that shared topic here (what THAT sibling's events are). (5) FORMAT RULE: no commas and no parentheses inside any string (downstream stores arrays as comma-CSV). Use a dash or the word "not"/"see" instead. (6) When unsure — omit that line. Few-shot (English scaffold only; YOUR output language = language of each title). Shared word "party": {"items":[{"entity":"ent_partners","notEnoughFor":["party as legal taxpayer / contract party — see Legal counterparties"]},{"entity":"ent_counterparties","notEnoughFor":["party as sales partner list — see Business partners"]}]}. Schema: {"items":[{"entity":"<exact copy of Input entity string>","notEnoughFor":["..."]}]}. Every Input entity appears once; entity values copy Input exactly. Input:
EOF_WA_PROMPT
)

# Вызов одного поля с ретраем до сборки (dictfix §2). Падение — в stderr (п.13).
# $1=prompt $2=pay $3=ans $4=err $5=msg $6=field $7=site(init|collision) $8=log_tag
wa_infer_field() {
  local prompt="$1" pay="$2" ans="$3" err="$4" msg="$5" field="$6" site="$7" tag="$8"
  local attempt
  for attempt in 0 1 2; do
    {
      printf '%s' "$prompt"
      cat "$pay"
    } > "$msg"
    chmod 644 "$msg"
    # stdout шлюза глотаем: вызывающий ловит только строку сборки в parse_out=$(…).
    if ! "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$msg" \
      --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
      --retry-items-json 2 \
      --ans "$ans" --err "$err" >/dev/null; then
      echo "$tag: поле $field попытка $attempt шлюз ($(head -c 100 "$err" 2>/dev/null | tr -d '\n'))" >&2
      continue
    fi
    if python3 ./wiki_alias_parse.py --check-field "$field" --site "$site" \
         "$ans" "$pay"; then
      return 0
    fi
    echo "$tag: поле $field попытка $attempt не прошло валидацию" >&2
  done
  echo "$tag: поле $field ПАДЕНИЕ после ретраев" >&2
  return 1
}

# Три поля A/B/C → rows.json (+ пустой measures при meas_out непустом).
# $1=site $2=pay $3=pref(tmp prefix) $4=rows_out $5=meas_out|"" $6=tag
# $7,$8,$9 = prompts A B C (уже с подставленным SHARED_WORD для collision)
# stdout — только итог assemble («алиасов разобрано: N…»).
wa_infer_three_fields() {
  local site="$1" pay="$2" pref="$3" rows_out="$4" meas_out="$5" tag="$6"
  local pA="$7" pB="$8" pC="$9"
  wa_infer_field "$pA" "$pay" "${pref}.ans_a" "${pref}.err_a" "${pref}.msg_a" \
    aliases "$site" "$tag" || return 1
  wa_infer_field "$pB" "$pay" "${pref}.ans_b" "${pref}.err_b" "${pref}.msg_b" \
    bestUsedFor "$site" "$tag" || return 1
  wa_infer_field "$pC" "$pay" "${pref}.ans_c" "${pref}.err_c" "${pref}.msg_c" \
    notEnoughFor "$site" "$tag" || return 1
  python3 ./alias_usage_log.py --contour wiki --ans "${pref}.ans_a" \
    --model "$WIKI_ALIAS_MODEL" >/dev/null 2>&1 || true
  if [ -n "$meas_out" ]; then
    python3 ./wiki_alias_parse.py --assemble --site "$site" \
      "${pref}.ans_a" "${pref}.ans_b" "${pref}.ans_c" \
      "$pay" "$rows_out" "$meas_out"
  else
    python3 ./wiki_alias_parse.py --assemble --site "$site" \
      "${pref}.ans_a" "${pref}.ans_b" "${pref}.ans_c" \
      "$pay" "$rows_out"
  fi
}

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
  # 🔴 СБОЙ СЕЛЕКТА ≠ «БАЗА КОНЧИЛАСЬ» (28.08, ночь). Сломанный SQL давал
  # пустой PAY, stderr глотался, цикл молча выходил как «нет непокрытых» —
  # холостой прогон по живой базе. Ошибка базы обязана останавливать прогон
  # с текстом в журнале юнита, а не приравниваться к пустому результату.
  # 🔴 OFFSET ТОЛЬКО ПРИ force=1. При force=0 пул сжимается сам (заполнение
  # aliases / mark_skip выводит строку из NOT EXISTS) — OFFSET сдвинул бы
  # mark_skip-хвост в голову и крутил бы одни и те же «пропущенные». При force=1
  # пул = весь корпус всегда → :skip_rows (= done_total) — единственный курсор.
  if ! psql_wa_tA -v batch="$BATCH" -v skip_rows="$done_total" \
      -f "$HERE/wiki_alias_select_entity_batch.sql" > "$TMP/pay"; then
    echo "алиасы: СБОЙ селекта пачки (ошибка выше) — прогон остановлен, пачка не потеряна" >&2
    exit 1
  fi
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac

  # 🔴 ЗАДАНИЕ ПЕРЕДАЁТСЯ ФАЙЛОМ, А НЕ АРГУМЕНТОМ. [замер 30.07] с `-m "$PAY"` на пачке из 25
  # сущностей команда отвечала «Missing message»: длинный JSON в аргументе командной строки не
  # доходит. У `openclaw agent` для этого есть штатный `--message-file`. Тот же класс дефекта, что
  # «стена argv» в разборе `HOW_NOT_TO §0`: данные аргументом командной строки не передаются.
  # «1 задача = 1 вызов»: init-A/B/C → сборка → один MERGE (dictfix §2).
  if ! parse_out=$(wa_infer_three_fields init "$TMP/pay" "$TMP/ent" \
        "$TMP/rows.json" "$TMP/measures.json" "алиасы" \
        "$_WA_INIT_A" "$_WA_INIT_B" "$_WA_INIT_C"); then
      skipped=$((skipped + 1))
      echo "алиасы: пачка пропущена (падение поля A/B/C)" >&2
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
      done_total=$((done_total + BATCH))
      [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
      continue
  fi

  # Разбор ответа модели — своим кодом это разрешено (п. 20: проверка ответа модели).
  # Выдуманное имя величины отбрасывается: во входном списке его не было.
  # 🔴 rc0 шлюза + 0 разобранных = попытка, не успех (R4). items=[] проходит
  # валидацию шлюза, MERGE был no-op, mark_skip не звался — пачка терялась молча.
  echo "$parse_out"
  ents_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*алиасов разобрано: \([0-9][0-9]*\).*/\1/p' | tail -n1)
  case "$ents_n" in ''|*[!0-9]*) ents_n=0;; esac
  if [ "$ents_n" -eq 0 ]; then
    skipped=$((skipped + 1))
    echo "алиасы: пачка пропущена (rc0, разобрано 0)" >&2
    psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
    done_total=$((done_total + BATCH))
    [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
    continue
  fi
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
# 🔴 OFFSET МЕР — СВОЙ СЧЁТЧИК. done_total к этому моменту уже = число сущностей
# первого прохода; подставлять его в skip_rows мер при force=1 сдвинуло бы пул
# мер на весь entity-объём. done_measures стартует с 0 и растёт на BATCH пачки;
# при force=0 OFFSET в SQL = 0 (счётчик не используется). CAP по-прежнему
# смотрит на done_total (общий потолок прогона).
done_measures=0
while :; do
  over_budget && { echo "величины: бюджет $BUDGET с исчерпан — добор возьмёт следующий такт"; break; }
  [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
  # OFFSET только при force=1 (см. комментарий у entity-select выше).
  psql_wa_tA -v batch="$BATCH" -v skip_rows="$done_measures" \
    -f "$HERE/wiki_alias_select_measure_batch.sql" > "$TMP/pay" 2>/dev/null
  chmod 644 "$TMP/pay" 2>/dev/null
  PAY=$(cat "$TMP/pay")
  case "$PAY" in ''|'[]'|'null') break;; esac
  {
    printf '%s' "JSON only, no prose, no code fences. Below are record types of one database, shown together because they are CLOSE IN MEANING — that is what makes them easy to confuse. Answer language for every string field = the language of that record's title (the English example below is STRUCTURE ONLY — never copy its language into the output when the title is in another language). For EACH record: (1) aliases — ONLY everyday words a person actually puts in a question when they mean THIS kind of record (their spoken asking-words). ALSO include ROLE words for every flow listed in the input for this record: the same catalog is named differently by role depending on the flow (structure example: a counterparty catalog → buyers in sales flows, suppliers in purchase flows); take roles ONLY from the listed flows — do not invent flows. ALSO include 1-2 spoken action/event forms people use when asking about events THIS kind of record captures, when such forms are natural for the type (same language as the title; same quality limits as other aliases; distinctive for THIS type among siblings in THIS batch — forms that equally fit a sibling go under notEnoughFor). Limits: 3 to 8 aliases; each alias is 1 to 3 words; no sentences; no question words alone (how/how many/what/who as standalone tokens). Do NOT add the title (or a morphological variant of the title) as an alias — the title is already known from input. Quantity names and field names go ONLY under quantities, never under aliases. BANS for aliases (skip the token if unsure): platform meta-labels and their equivalents in the title language (list, catalog, directory, types, kinds, register, journal, document, classifier, form, report as a meta-word); case/number/inflection variants of the SAME stem (pick one citation form); Latin-script words when the title is not Latin; words that equally fit a sibling in THIS batch (leave those out of aliases — put the distinction in notEnoughFor); jargon opaque to a non-developer. (2) quantities — for EVERY name from the input quantities list, copy that name EXACTLY and give 1-5 short names a person uses for that value (a noun, or a noun with the action/event word they say — e.g. spoken event forms for money totals), 1-3 words each, no sentences. Same bans as aliases. If a listed quantity has no clear everyday name, return it with an empty aliases array. (3) bestUsedFor — 2 to 4 short question TEMPLATES this record truly answers (the shape of what a person asks). No foreign topics (do not advertise price-list / stock-balance / customer-count questions for a record that does not answer them). No office jargon gerunds. Prefer spoken wording over metadata wording. (4) notEnoughFor — two kinds of short strings, both required when applicable: (a) THEMATIC \"not me\" — topic labels a person might confuse with this record but that this record does NOT answer (stock balances, price list, customer list/count, cash, payroll, … — only topics that are plausible confusions for THIS title); (b) SIBLING redirect — for each easy-to-confuse sibling from THIS input list, one short string: sibling title then what THAT sibling answers instead. Hard format rule for EVERY notEnoughFor string: no commas and no parentheses inside the string (downstream stores arrays as comma-CSV). Use a dash or the word \"not\"/\"see\" instead. Prefer 3-8 strings total. If unsure whether a topic is a real confusion — omit it. Global: if you are not sure a token or claim is correct — do not write it (omit; never guess). Do not invent quantities, flows, or sibling names that are not in the input. One structure example (English skeleton only; rewrite all strings into the title language of each real item): {\"entity\":\"catalog_counterparties\",\"aliases\":[\"buyers\",\"suppliers\",\"customers\"],\"quantities\":[{\"name\":\"Count\",\"aliases\":[\"headcount\",\"how many partners\"]}],\"bestUsedFor\":[\"how many customers\",\"who bought this month\"],\"notEnoughFor\":[\"not stock balances\",\"not price list\",\"Organizations - our own companies not trading partners\"]} Never copy the English example strings into the output when the title language is different — rewrite every string in the title language. Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
    cat "$TMP/pay"
  } > "$TMP/msg"
  chmod 644 "$TMP/msg"
  "${RUNAS_BOT[@]}" python3 ./alias_infer_gateway.py --message-file "$TMP/msg" \
    --model "$WIKI_ALIAS_MODEL" --thinking "$WIKI_ALIAS_THINKING" \
    --retry-items-json 2 \
    --ans "$TMP/ans" --err "$TMP/err" || {
      # При force=1 mark_skip пул не сжимает → OFFSET двигаем и на осечке.
      skipped=$((skipped + 1))
      echo "величины: пачка пропущена ($(head -c 120 "$TMP/err" | tr -d '\n'))" >&2
      psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
      done_measures=$((done_measures + BATCH))
      done_total=$((done_total + BATCH))
      [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
      continue
    }
  # rc0 + 0 величин = попытка (R4), зеркало entity-ветки выше.
  parse_out=$(python3 ./wiki_alias_parse.py "$TMP/ans" "$TMP/pay" "$TMP/rows.json" "$TMP/measures.json")
  echo "$parse_out"
  meas_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*величин: \([0-9][0-9]*\).*/\1/p' | tail -n1)
  case "$meas_n" in ''|*[!0-9]*) meas_n=0;; esac
  if [ "$meas_n" -eq 0 ]; then
    skipped=$((skipped + 1))
    echo "величины: пачка пропущена (rc0, разобрано 0)" >&2
    psql_wa -v pay_path="$TMP/pay" -f "$HERE/wiki_alias_mark_measure_skip.sql" >/dev/null 2>&1
    done_measures=$((done_measures + BATCH))
    done_total=$((done_total + BATCH))
    [ "$CAP" != "0" ] && [ "$done_total" -ge "$CAP" ] && break
    continue
  fi
  python3 ./alias_usage_log.py --contour wiki --ans "$TMP/ans" --model "$WIKI_ALIAS_MODEL" 2>/dev/null || true
  chmod 644 "$TMP/rows.json" "$TMP/measures.json" 2>/dev/null
  # Только величины. rows.json с алиасами сущности здесь намеренно не пишется в
  # ALIAS_TABLE: добор не имеет права перезаписать уже собранные описания записей.
  psql_wa -v measures_path="$TMP/measures.json" \
    -f "$HERE/wiki_alias_merge_measures.sql" 2>&1 | grep -i error
  have_m=$(psql_wa_tA -c "SELECT count(*) FROM $MEASURE_TABLE WHERE coalesce(aliases,'') <> ''" 2>/dev/null)
  echo "величины: непустых в базе $have_m"
  done_measures=$((done_measures + BATCH))
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
  # :probe_table (PROBE_TABLE, умолч. search_alias_probe) — wiki_alias_init.sql (CREATE IF NOT EXISTS).
  # Песочница задаёт свою PROBE_TABLE, чтобы не марать боевую память столкновений.
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
    # «1 задача = 1 вызов»: collision-A/B/C → сборка → collision_merge.
    _CA="${_WA_COLL_A//<SHARED_WORD>/$WORD}"
    _CB="${_WA_COLL_B//<SHARED_WORD>/$WORD}"
    _CC="${_WA_COLL_C//<SHARED_WORD>/$WORD}"
    if ! parse_out=$(wa_infer_three_fields collision "$TMP/pay" "$TMP/coll" \
          "$TMP/rows.json" "" "разведение" \
          "$_CA" "$_CB" "$_CC"); then
      echo "разведение: пачка пропущена (падение поля A/B/C)" >&2
      continue
    fi
    echo "$parse_out"
    chmod 644 "$TMP/rows.json" 2>/dev/null   # тот же случай, что в первом проходе
    psql_wa -v rows_path="$TMP/rows.json" -f "$HERE/wiki_alias_collision_merge.sql" >/dev/null 2>&1
  done
  # Молчания тут быть не должно: видно и сколько спросили, и сколько ОСТАЛОСЬ на следующий
  # такт (упёрлись в предел кругов), и сколько столкновений модель разобрать не смогла —
  # они лежат в `$PROBE_TABLE` (умолч. search_alias_probe) и сами собой больше не переспрашиваются.
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
      # «1 задача = 1 вызов»: init-A/B/C (тот же канон, что entity-init).
      if ! parse_out=$(wa_infer_three_fields init "$TMP/reask_pay" "$TMP/reask" \
            "$TMP/reask_rows.json" "$TMP/reask_meas.json" "reask" \
            "$_WA_INIT_A" "$_WA_INIT_B" "$_WA_INIT_C"); then
        echo "reask: пачка пропущена (падение поля A/B/C)" >&2
        continue
      fi
      echo "$parse_out"
      ents_n=$(printf '%s\n' "$parse_out" | sed -n 's/.*алиасов разобрано: \([0-9][0-9]*\).*/\1/p' | tail -n1)
      case "$ents_n" in ''|*[!0-9]*) ents_n=0;; esac
      if [ "$ents_n" -eq 0 ]; then
        skipped=$((skipped + 1))
        echo "reask: пачка пропущена (rc0, разобрано 0)" >&2
        psql_wa -v pay_path="$TMP/reask_pay" -f "$HERE/wiki_alias_mark_skip.sql" >/dev/null 2>&1
        REASK_DONE=$((REASK_DONE + BATCH))
        continue
      fi
      chmod 644 "$TMP/reask_rows.json" "$TMP/reask_meas.json" 2>/dev/null
      # Боковая таблица: полный ответ модели (не основной словарь).
      psql "$DSN" -q -v ON_ERROR_STOP=1 \
        -v alias_table="$REASK_TABLE" \
        -v measure_table="$MEASURE_TABLE" \
        -v rows_path="$TMP/reask_rows.json" \
        -v measures_path="$TMP/reask_meas.json" \
        -v force="${WIKI_ALIAS_FORCE:-0}" \
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
# 🔴 ИСТОЧНИК — ВСЕГДА БОЕВАЯ ТАБЛИЦА, ДАЖЕ В ПОБОЧНОМ ПРОГОНЕ. [замер 29.08]
# Прогон юнита с ALIAS_TABLE=alias_okna_c5 (28.08 20:58) пересобрал ЖИВОЙ
# search_dict_syn правилами побочной таблицы — ранжирование в бою деградировало
# («сколько клиентов реально покупали…» → 2 · Валюты вместо 141 · Контрагенты).
# Побочная таблица — черновик генератора; живой словарь имеет право меняться
# только вслед за боевой (MERGE «только пустые строки» → пересборка из боевой).
SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-${SOLR_SYN_DICT:-search_dict_syn}}"
DICT_LOCALE="${SEARCH_DICT_LOCALE:-ru_RU.utf8}"
# Тот же путь, что build.sh:511-517 — без Python-посредника. Fail-closed: юнит и ручной
# прогон не маскируют битый словарь. alias_table жёстко search_entity_alias (см. выше).
psql "$DSN" -q \
  -v dict_locale="$DICT_LOCALE" \
  -v solr_syn_dict="$SOLR_SYN_DICT" \
  -v alias_table="search_entity_alias" \
  -f "$HERE/solr_synonyms_compile.sql" \
  || { echo "solr synonyms: компиляция не прошла ($SOLR_SYN_DICT)" >&2; exit 1; }
