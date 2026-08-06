#!/usr/bin/env bash
# PostToolUse: файл ИЗМЕНИЛСЯ — вбросить его зависимости из графа.
#
# 🔴 ЭТО ПОДГОТОВЛЕННАЯ ВЕРСИЯ. Записывать прямо в `.claude/hooks/` рубеж среды не даёт
# (точка входа хука), поэтому файл лежит здесь, а владелец ставит его одной командой:
#     install -m 755 work/hooks/check-deps.sh .claude/hooks/check-deps.sh
#
# Зачем хук: главная беда проекта — «починил одно, сломал другое». Граф зависимостей
# (memory_bank/mcp-memory.json) знает, что от чего зависит, но правило «спроси граф перед
# правкой» текстом не держится — держится этим хуком: зависимости всплывают сами, в момент
# правки, без дисциплины.
#
# 🔴 ПОЧЕМУ СМОТРИМ НА ФАКТ ИЗМЕНЕНИЯ, А НЕ НА ИМЯ ИНСТРУМЕНТА (расширено 03.08).
# До этого хук висел только на `Write|Edit` и читал `tool_input.file_path`. Запись файла из
# оболочки — `python3 - <<PY`, `sed -i`, `tee` — он не видел ПО УСТРОЙСТВУ. За сессию 03.08
# `serene_ask.py` дважды правился скриптом из Bash, хук не отозвался ни разу, граф остался
# нетронутым, и наблюдение, которое в графе уже лежало, выводилось заново полдня
# (`HOW_NOT_TO §1.49`). Тишина хука читалась как «всё чисто», а означала «прошёл мимо».
#
# Теперь два пути, и второй не зависит от того, чем правили:
#   1. есть `tool_input.file_path` (Write/Edit) — берём его сразу;
#   2. иначе — сравниваем СНИМОК изменённых файлов с прошлым запуском и берём то, что
#      появилось или поменялось. Снимок обновляется при КАЖДОМ запуске, поэтому один и тот
#      же файл не вбрасывается дважды подряд.
#
# Снимок — `path \t mtime \t size` по файлам, отличающимся от HEAD, плюс неотслеживаемые.
# Их единицы, поэтому цена запуска не растёт с размером репозитория (п. 19: ничто в контуре
# не должно расти с размером данных).
#
# Граф читается напрямую из JSONL-файла (MCP тут не нужен и недоступен хуку).
set -uo pipefail

INPUT=$(cat)
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-.}")" || { echo '{}'; exit 0; }

GRAPH="memory_bank/mcp-memory.json"
[ -f "$GRAPH" ] || { echo '{}'; exit 0; }

SNAP=".claude/state/deps-snapshot.tsv"
mkdir -p "$(dirname "$SNAP")" 2>/dev/null

# Текущий снимок «грязных» файлов. `-uall` — чтобы новый файл в новом каталоге считался
# по отдельности, а не одной строкой каталога.
# Служебное отсеивается ДО `stat`: хук зовётся на каждой команде, и трогать сотню файлов
# харнесса и выводов приборов на каждый `ls` незачем.
CUR=$(git status --porcelain -uall 2>/dev/null \
      | sed -e 's/^...//' -e 's/^"//' -e 's/"$//' \
      | grep -v -e '^\.claude/' -e '^out/' -e '/runs/' \
      | while IFS= read -r f; do
          [ -n "$f" ] && [ -f "$f" ] || continue
          s=$(stat -c '%Y %s' "$f" 2>/dev/null) || continue
          printf '%s\t%s\n' "$f" "$s"
        done)

HOOK_INPUT="$INPUT" SNAP_FILE="$SNAP" CUR_SNAP="$CUR" python3 - "$GRAPH" <<'PY'
import json, os, sys, time

def log(msg):
    try:
        with open(".claude/hooks.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m %H:%M:%S") + " check-deps  " + msg + "\n")
    except Exception:
        pass

try:
    data = json.loads(os.environ["HOOK_INPUT"])
except Exception:
    print("{}"); sys.exit(0)

root = os.getcwd()
snap_file = os.environ.get("SNAP_FILE") or ".claude/state/deps-snapshot.tsv"
cur = {}
for l in (os.environ.get("CUR_SNAP") or "").splitlines():
    p, _, st = l.rstrip("\n").partition("\t")
    if p.strip():
        cur[p] = st

prev, first_run = {}, not os.path.exists(snap_file)
if not first_run:
    try:
        with open(snap_file, encoding="utf-8") as f:
            for l in f:
                p, _, st = l.rstrip("\n").partition("\t")
                if p:
                    prev[p] = st
    except Exception:
        first_run = True

# Снимок обновляется ВСЕГДА и ДО решения о вбросе: иначе выход ниже по коду оставил бы
# старый снимок, и следующий запуск вбросил бы то же самое ещё раз.
try:
    with open(snap_file, "w", encoding="utf-8") as f:
        for p in sorted(cur):
            f.write("%s\t%s\n" % (p, cur[p]))
except Exception:
    pass

targets = []
# У Claude поле пути — file_path, у Kimi — path (замер 06.08): принимаем оба.
_ti = data.get("tool_input") or {}
fp = _ti.get("file_path") or _ti.get("path") or ""
if fp:
    targets = [os.path.relpath(fp, root) if os.path.isabs(fp) else fp]
elif not first_run:
    # Что появилось или изменилось со времени прошлого запуска — независимо от того,
    # каким инструментом. Первый запуск молчит намеренно: снимка не было, и «изменилось»
    # означало бы «всё, что лежит незакоммиченным», то есть шум вместо сигнала.
    targets = [p for p, st in cur.items() if prev.get(p) != st]


def skip(rel):
    """Служебное не проверяем: сам граф, каталоги харнесса, журналы прогонов."""
    return (not rel or rel.startswith((".claude/", "..", "out/"))
            or rel == "memory_bank/mcp-memory.json"
            or "/runs/" in rel)


targets = [t for t in targets if not skip(t)]
if not targets:
    print("{}"); sys.exit(0)

entities, relations = {}, []
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") == "entity":
        entities[d["name"]] = d
    elif d.get("type") == "relation":
        relations.append(d)


def candidates_for(rel):
    """Имена, под которыми файл может быть известен графу.

    Сверяем не только полное имя, но и основу: имя без расширений и без шаблонной части
    после «@» — иначе новый `1c-serene-ask@.service` не находит сущность `1c-serene-ask`
    (промах 03.08).
    """
    base = os.path.basename(rel)
    cands = {rel, base}
    stem = base
    while "." in stem:
        stem = stem.rsplit(".", 1)[0]
        cands.add(stem)
    for c in list(cands):
        if "@" in c:
            cands.add(c.split("@")[0])
    cands = {c for c in cands if len(c) >= 7}
    cands.add(rel)
    return cands


blocks, hit_all = [], []
# Разом правят помногу (скрипт, переименование): вбрасываем зависимости первых трёх
# задетых файлов, иначе вброс сам станет шумом и его перестанут читать.
for rel in sorted(targets)[:3]:
    cands = candidates_for(rel)

    def matches(e, cands=cands):
        hay = e["name"] + " " + " ".join(e.get("observations", []))
        return any(c in hay for c in cands)

    hit = [name for name, e in entities.items() if matches(e)]
    if not hit:
        continue
    lines = []
    for name in hit[:4]:
        ins = [r for r in relations if r.get("to") == name]
        outs = [r for r in relations if r.get("from") == name]
        if not ins and not outs:
            continue
        part = ["«%s»:" % name]
        for r in outs[:6]:
            part.append("  %s —%s→ %s" % (name, r.get("relationType", "?"), r.get("to", "?")))
        for r in ins[:6]:
            part.append("  %s —%s→ %s" % (r.get("from", "?"), r.get("relationType", "?"), name))
        lines.append("\n".join(part))
    if lines:
        hit_all.extend(hit[:4])
        blocks.append("правка %s задевает —\n%s" % (rel, "\n".join(lines)))

if not blocks:
    log("тихо  %s (в графе не найдены)" % ", ".join(sorted(targets)[:3]))
    print("{}"); sys.exit(0)

how = "по file_path" if fp else "по факту изменения файлов"
log("ВБРОС (%s) %s → %s" % (how, ", ".join(sorted(targets)[:3]), ", ".join(hit_all[:4])))

ctx = ("Граф зависимостей (%s): " % how + "\n\n".join(blocks) +
       "\nПроверь задетое; изменил зависимость — обнови граф тем же заходом "
       "(create_relations/add_observations) и закоммить mcp-memory.json (CLAUDE.md).")
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": ctx}}, ensure_ascii=False))
PY
