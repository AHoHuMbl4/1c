#!/usr/bin/env bash
# Перехват ПЕРЕД правкой: правило, запрет или указание, вписанное в ТЕКСТ ДЛЯ МОДЕЛИ.
#
# 🔴 ЗАЧЕМ. Указание владельца 03.08: «запрещено делать промтами правила, запреты,
# указания. это супер важно». Правило в проекте было и раньше («запреты держатся кодом, а
# не промтом»), но держалось оно… текстом в `CLAUDE.md` — то есть само собой и нарушалось.
#
# Живой случай, стоивший замера. Я расширил описание инструмента `ask_1c` словами «знаешь
# тип записи — передай его первым же вызовом, а не спрашивай человека», выкатил и снял три
# прогона приёмки настоящей доставкой: 5, 5, 4 из 10 — то есть РОВНО ТОТ ЖЕ уровень, и
# «бот ответил, не позвав `ask_1c`» осталось 3-4 случая из десяти. Двадцать сообщений
# владельцу в мессенджер и три прогона ушли на подтверждение того, что и так записано в
# правилах: модель инструкцию читает и не исполняет.
#
# ЧТО СЧИТАЕТСЯ ТЕКСТОМ ДЛЯ МОДЕЛИ (определяется устройством, а не списком наших файлов):
#   * персона бота — `.md` в каталоге `instance/` (так её кладёт движок);
#   * строковые литералы питона — проверяются РАЗБОРОМ (`ast`), а не догадкой по строке:
#     добавленная строка обязана попасть внутрь настоящего литерала;
#   * присваивания полям, чей текст уходит модели: `instruction`, `reason`, `reviseReason`,
#     `*_SYS`, `*_HINT`, `*_PROMPT`.
#
# Хук НЕ запрещает промты как таковые — без них модель не работает. Он останавливает ровно
# один случай: когда в промт добавляется ПРАВИЛО (обязан / запрещено / всегда / никогда /
# must / never / always), то есть то, что обязано держаться кодом.
#
# Не блокирует молча, а выносит решение владельцу — как остальные хуки.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"

# 🔴 СОБЫТИЕ ПЕРЕДАЁТСЯ ПЕРЕМЕННОЙ, А НЕ ЧЕРЕЗ stdin. Первая редакция читала
# `json.load(sys.stdin)` внутри `python3 - <<'PY'` — а heredoc САМ занимает stdin, и питон
# разбирал как событие текст собственной программы. Хук при этом не падал: он молча
# печатал `{}` на любой вход, то есть был fail-open и не поймал бы ничего. Поймано пробой,
# а не чтением кода (`test-hooks.sh`).
EVENT_JSON=$(cat)
export EVENT_JSON

# 🔴 ВТОРОЙ ЗАХОД — НА КОММИТЕ. Хук движка ловит правку, сделанную ЭТОЙ сессией. Мимо него
# проходит всё остальное: другая сессия, редактор владельца, Cursor, `python3 -c`, `sed -i`.
# Правило, которое ловит один способ правки из пяти, правилом не является. Поэтому тот же
# разбор делается по индексу на коммите — и гейт коммита (`.githooks/pre-commit`) зовёт
# этот хук наравне с остальными: git зовётся всегда, кто бы ни коммитил.
# 🔴 Поле пути у движков зовётся по-разному: Claude шлёт `file_path`, Kimi — `path`
# (замер полезной нагрузки 06.08, /tmp-ловушкой). Проверка ветки и разбор обязаны
# принимать оба, иначе под Kimi хук молча уходил бы в ветку коммита и пропускал всё.
if ! printf '%s' "$EVENT_JSON" | grep -qE '"(file_path|path)"'; then
  CMD=$(printf '%s' "$EVENT_JSON" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print((d.get("tool_input") or {}).get("command") or "")' 2>/dev/null)
  is_git_commit "$CMD" || { echo '{}'; exit 0; }
  cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя."; exit 0; }
  # При пат-спеке смотрим только названные пути: чужой staged-файл соседней сессии
  # не должен останавливать наш коммит.
  mapfile -t PS < <(hook_commit_pathspec "$CMD")
  STAGED_DIFF="${DIFF_OVERRIDE:-$(git diff --cached -U0 -- "${PS[@]}" 2>/dev/null)}"
  [ -z "$STAGED_DIFF" ] && { echo '{}'; exit 0; }
  # 🔴 Дифф — ФАЙЛОМ, не окружением: на большом коммите переменная окружения упирается в
  # предел (`/usr/bin/python3: Argument list too long`, код 126), гейт считает проверку
  # непройденной и останавливает коммит целиком. Чем крупнее работа, тем вернее правило
  # переставало работать — поймано настоящим коммитом, а не чтением кода.
  DIFF_FILE="$(mktemp)" || { hook_ask "Хук $(basename "$0") не смог создать временный файл и ничего не проверил."; exit 0; }
  trap 'rm -f "$DIFF_FILE"' EXIT
  printf '%s' "$STAGED_DIFF" > "$DIFF_FILE"
  DIFF_FILE="$DIFF_FILE" python3 <<'PY' | hook_gate_json check-prompt-rules
import json, os, re, sys

MARK = re.compile(
    r"(?i)(обязан\w*|запрещ\w+|нельзя|никогда|всегда|не\s+смей\w*|должен|должна|должно|"
    r"\bmust\b|\bnever\b|\balways\b|\bforbidden\b|\bmandatory\b|\bdo\s+not\b|\bdon't\b|"
    r"\byou\s+should\b|\brequired\s+to\b)")
FLD = re.compile(r"(?i)^\s*(instruction|reason|reviseReason|[A-Z_]*(SYS|HINT|PROMPT))\s*[:=]")

# Хуки, документы и память — не текст для модели: правило про промты к ним не относится.
SKIP = (".claude/", "work/hooks/", "docs/", "memory_bank/")

with open(os.environ["DIFF_FILE"], encoding="utf-8", errors="replace") as fh:
    diff_lines = fh.read().splitlines()

cur, added = None, {}
for line in diff_lines:
    if line.startswith("+++ b/"):
        cur = line[6:].strip()
        continue
    if not line.startswith("+") or line.startswith("+++") or not cur:
        continue
    if cur.startswith(SKIP):
        continue
    added.setdefault(cur, []).append(line[1:])

hits = []
for path, lines in added.items():
    marked = [l.strip() for l in lines if MARK.search(l)]
    if not marked:
        continue
    if path.endswith(".md") and "/instance/" in path:
        hits.append((path, "персона бота", marked)); continue
    if any(FLD.search(l) for l in lines):
        hits.append((path, "поле, чей текст уходит модели", marked)); continue
    if path.endswith(".py"):
        # Внутри ли добавленное строкового литерала — решает РАЗБОР той версии файла,
        # что уходит в коммит (`git show :путь`), а не подсчёт кавычек и не рабочая копия.
        import ast, subprocess
        try:
            src = subprocess.run(["git", "show", ":" + path], capture_output=True, text=True,
                                 timeout=20).stdout
            tree = ast.parse(src)
        except Exception:
            continue
        spans = [(n.lineno, n.end_lineno) for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.lineno and n.end_lineno]
        body = src.splitlines()
        inside = []
        for m in marked:
            for i, l in enumerate(body, 1):
                if m and m in l and any(a <= i <= b for a, b in spans):
                    inside.append(m); break
        if inside:
            hits.append((path, "строковый литерал (проверено разбором)", inside))

if not hits:
    print("{}"); sys.exit(0)

lines = ["  %s — %s: «%s»" % (p, place, "; ".join(h[:90] for h in hh[:2])) for p, place, hh in hits[:6]]
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason":
        "В коммите ПРАВИЛО, вписанное в текст для модели:\n" + "\n".join(lines) +
        "\n\nУказание владельца 03.08: запрещено делать промтами правила, запреты и указания —\n"
        "модель их читает и не исполняет. [замер 03.08] расширение контракта `ask_1c` словами\n"
        "«передай focus первым вызовом» дало 5, 5, 4 из 10 — тот же уровень, что и без него.\n"
        "Скажите, чем это держится КОДОМ (хук движка, проверка в мосте, гейт, роль базы)."}},
    ensure_ascii=False))
PY
  exit 0
fi

REASON=$(python3 - <<'PY' 2>/dev/null
import ast
import json
import os
import re
import sys

try:
    ev = json.loads(os.environ.get("EVENT_JSON") or "{}")
except Exception:
    print("")
    sys.exit(0)

ti = ev.get("tool_input") or {}
# У Claude поле пути — file_path, у Kimi — path (замер 06.08). Принимаем оба.
path = ti.get("file_path") or ti.get("path") or ""
# Edit даёт замену, Write — целое содержимое. Нас интересует только ДОБАВЛЯЕМЫЙ текст.
added = ti.get("new_string")
if added is None:
    added = ti.get("content") or ""
old = ti.get("old_string") or ""

if not path or not added.strip():
    print("")
    sys.exit(0)

# Правило — это долженствование или запрет. Слова обеих сторон: наши промты двуязычны.
MARK = re.compile(
    r"(?i)(обязан\w*|запрещ\w+|нельзя|никогда|всегда|не\s+смей\w*|должен|должна|должно|"
    r"\bmust\b|\bnever\b|\balways\b|\bforbidden\b|\bmandatory\b|\bdo\s+not\b|\bdon't\b|"
    r"\byou\s+should\b|\brequired\s+to\b)")

# Строки, добавленные этой правкой (для Edit — те, которых не было в old_string).
old_lines = set(old.splitlines())
new_lines = [l for l in added.splitlines() if l not in old_lines]
hits = [l.strip() for l in new_lines if MARK.search(l)]
if not hits:
    print("")
    sys.exit(0)


def where():
    """Куда попадает добавленный текст: персона, литерал питона, поле с текстом для модели."""
    # Персона бота: движок кладёт её в каталог `instance/`.
    if path.endswith(".md") and "/instance/" in path:
        return "персона бота (%s)" % path.rsplit("/", 1)[-1]

    # Поля, содержимое которых уходит модели дословно.
    fld = re.compile(r"(?i)^\s*(instruction|reason|reviseReason|[A-Z_]*(SYS|HINT|PROMPT))\s*[:=]")
    if any(fld.search(l) for l in new_lines):
        return "поле, чей текст уходит модели"

    # Питон: считаем текст промтом ТОЛЬКО если он и правда внутри строкового литерала.
    # Проверяем разбором готового файла, а не подсчётом кавычек: подсчёт ошибается.
    if path.endswith(".py"):
        try:
            src = open(path, encoding="utf-8").read()
        except OSError:
            return ""
        merged = src.replace(old, added, 1) if old and old in src else None
        if merged is None:
            return ""
        try:
            tree = ast.parse(merged)
        except SyntaxError:
            return ""
        spans = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.lineno and node.end_lineno:
                    spans.append((node.lineno, node.end_lineno))
        if not spans:
            return ""
        lines = merged.splitlines()
        for h in hits:
            for i, l in enumerate(lines, 1):
                if h and h in l and any(a <= i <= b for a, b in spans):
                    return "строковый литерал в %s (проверено разбором)" % path.rsplit("/", 1)[-1]
    return ""


place = where()
if not place:
    print("")
    sys.exit(0)

sample = "; ".join(h[:90] for h in hits[:2])
print("В %s добавляется ПРАВИЛО: «%s».\n"
      "Указание владельца 03.08: запрещено делать промтами правила, запреты и указания — "
      "модель их читает и не исполняет. [замер 03.08] расширение контракта `ask_1c` словами "
      "«передай focus первым вызовом» дало 5, 5, 4 из 10 — тот же уровень, что и без него.\n"
      "Скажите, чем это держится КОДОМ (хук движка, проверка в мосте, гейт, роль базы). "
      "Если правка всё равно нужна — подтвердите шаг." % (place, sample))
PY
)

if [ -z "$REASON" ]; then
  echo '{}'
else
  hook_ask "$REASON"
fi
