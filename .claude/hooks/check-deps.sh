#!/usr/bin/env bash
# PostToolUse на Edit|Write: правится файл — вбросить его зависимости из графа.
#
# Зачем: главная беда проекта — «починил одно, сломал другое». Граф зависимостей
# (memory_bank/mcp-memory.json, 53 сущности) знает, что от чего зависит, но правило
# «спроси граф перед правкой» текстом не держится — держится этим хуком: зависимости
# всплывают сами, в момент правки, без дисциплины.
#
# Граф читается напрямую из JSONL-файла (MCP тут не нужен и недоступен хуку).
set -uo pipefail

INPUT=$(cat)
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-.}")" || { echo '{}'; exit 0; }

GRAPH="memory_bank/mcp-memory.json"
[ -f "$GRAPH" ] || { echo '{}'; exit 0; }

HOOK_INPUT="$INPUT" python3 - "$GRAPH" <<'PY'
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

fp = (data.get("tool_input") or {}).get("file_path") or ""
if not fp:
    print("{}"); sys.exit(0)

root = os.getcwd()
rel = os.path.relpath(fp, root) if os.path.isabs(fp) else fp
base = os.path.basename(rel)

# Служебное не проверяем: сам граф, скретч, скрытые каталоги харнесса
if rel.startswith((".claude/", "..")) or rel == "memory_bank/mcp-memory.json":
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

# Сущности, относящиеся к правящемуся файлу. Сверяем не только полное имя, но и
# основу: имя без расширений и без шаблонной части после «@» — иначе новый
# 1c-serene-ask@.service не находит сущность «1c-serene-ask» (промах 03.08).
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

def matches(e):
    hay = e["name"] + " " + " ".join(e.get("observations", []))
    return any(c in hay for c in cands)

hit = [name for name, e in entities.items() if matches(e)]
if not hit:
    log(f"тихо  {rel} (в графе не найден)")
    print("{}"); sys.exit(0)

lines = []
for name in hit[:4]:
    ins  = [r for r in relations if r.get("to") == name]
    outs = [r for r in relations if r.get("from") == name]
    if not ins and not outs:
        continue
    part = [f"«{name}»:"]
    for r in outs[:6]:
        part.append(f"  {name} —{r.get('relationType','?')}→ {r.get('to','?')}")
    for r in ins[:6]:
        part.append(f"  {r.get('from','?')} —{r.get('relationType','?')}→ {name}")
    lines.append("\n".join(part))

if not lines:
    log(f"тихо  {rel} (сущности без связей: {', '.join(hit[:3])})")
    print("{}"); sys.exit(0)

log(f"ВБРОС {rel} → {', '.join(hit[:4])}")

ctx = (f"Граф зависимостей: правка {rel} задевает —\n" + "\n".join(lines) +
       "\nПроверь задетое; изменил зависимость — обнови граф тем же заходом "
       "(create_relations/add_observations) и закоммить mcp-memory.json (CLAUDE.md).")
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": ctx}}, ensure_ascii=False))
PY
