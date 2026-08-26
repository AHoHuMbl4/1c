#!/usr/bin/env bash
# Адаптер Cursor → те же гейты, что Claude Code и Kimi Code.
#
# ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ ПРАВКА ГЕЙТОВ. Скрипты гейтов общие на три движка.
# Форма входа и выхода у Cursor другая (дока hooks + живой замер 13.08: matcher Bash
# из settings.json на команды Shell не сработал). Правка каждого гейта «под Cursor»
# разъехалась бы, как F248. Здесь одно место: нормализовать вход, позвать гейт,
# перевести выход.
#
# Подключается только из .cursor/hooks.json. Claude и Kimi этот файл не зовут.
#
# 🔴 ПОЛЕЗНАЯ НАГРУЗКА — ФАЙЛОМ, НЕ ОКРУЖЕНИЕМ. Было `export CURSOR_WRAP_INPUT="$INPUT"`
# и то же для OUT: на Write CHANGELOG.md (~1,5 МБ) execve python3/bash упирался в
# ARG_MAX («Argument list too long»). После export каждый следующий дочерний процесс
# тоже падал — гейт не отрабатывал, а failClosed у блокирующих превращал это в стоп
# или обход через оболочку. Поймано живой правкой CHANGELOG из Cursor, не чтением кода.
# Образец уже в check-sql-docs / check-prompt-rules (дифф коммита → DIFF_FILE).
set -uo pipefail

GATE="${1:-}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

deny_now() {
  python3 -c 'import json,sys; print(json.dumps({"permission":"deny","user_message":sys.argv[1],"agent_message":sys.argv[1]},ensure_ascii=False))' "$1"
  exit 2
}

[ -n "$GATE" ] || deny_now "cursor-wrap: гейт не назван. Проводка .cursor/hooks.json сломана."
SCRIPT="$DIR/${GATE}.sh"
[ -x "$SCRIPT" ] || deny_now "cursor-wrap: нет исполняемого $GATE.sh в защищённом каталоге хуков."

# След: хук, которого нет в журнале, не существует (HOW_NOT_TO §1.42).
printf '%s %-11s %s\n' "$(date '+%d.%m %H:%M:%S')" "cursor-wrap" "$GATE" >> "$DIR/../hooks.log" 2>/dev/null || true

# Вбросы не роняют работу, если адаптер или гейт споткнулся.
# Блокирующие — наоборот: упавшая проверка = стоп, не пропуск (git-gate то же правило).
INJECT="session-start prompt-start check-deps count-edits check-write"

IN_FILE="$(mktemp)" || deny_now "cursor-wrap: не удалось создать временный файл для входа."
OUT_FILE="$(mktemp)" || { rm -f "$IN_FILE"; deny_now "cursor-wrap: не удалось создать временный файл для выхода."; }
trap 'rm -f "$IN_FILE" "$OUT_FILE"' EXIT

cat > "$IN_FILE"
# Префикс IN_FILE= обязан стоять на КОМАНДЕ python3 (как DIFF_FILE= в check-sql-docs),
# а не на присваивании NORMALIZED=… — иначе os.environ пуст и нормализация молча
# отдаёт {} (проба 26.08: session_id из CURSOR_CONVERSATION_ID + tool_input {}).
NORMALIZED="$(IN_FILE="$IN_FILE" python3 - <<'PY'
import json, os, sys
in_path = os.environ.get("IN_FILE") or ""
try:
    with open(in_path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
except Exception:
    raw = ""
try:
    d = json.loads(raw) if raw.strip() else {}
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
ti = dict(d.get("tool_input") or {}) if isinstance(d.get("tool_input"), dict) else {}
cmd = ti.get("command") or d.get("command") or ""
if cmd:
    ti["command"] = cmd
fpath = (ti.get("file_path") or ti.get("path") or d.get("file_path") or d.get("path") or "")
if fpath:
    ti["file_path"] = fpath
    ti["path"] = fpath
edits = d.get("edits")
if isinstance(edits, list) and edits and not ti.get("new_string"):
    ti["old_string"] = "\n".join((e or {}).get("old_string") or "" for e in edits if isinstance(e, dict))
    ti["new_string"] = "\n".join((e or {}).get("new_string") or "" for e in edits if isinstance(e, dict))
for key in ("content", "new_string", "old_string"):
    if key in d and key not in ti:
        ti[key] = d[key]
sid = d.get("session_id") or d.get("conversation_id") or os.environ.get("CURSOR_CONVERSATION_ID") or ""
if sid:
    d["session_id"] = sid
d["tool_input"] = ti
print(json.dumps(d, ensure_ascii=False))
PY
)" || deny_now "cursor-wrap: нормализация входа не отработала."

OUT=""
RC=0
OUT="$(printf '%s' "$NORMALIZED" | bash "$SCRIPT")" || RC=$?

printf '%s' "$OUT" > "$OUT_FILE"
# Тот же приём: префикс OUT_FILE= на команде python3, не на TRANSLATED=.
TRANSLATED="$(OUT_FILE="$OUT_FILE" python3 - <<'PY'
import json, os, sys
path = os.environ.get("OUT_FILE") or ""
try:
    with open(path, encoding="utf-8", errors="replace") as fh:
        blob = fh.read()
except Exception:
    blob = ""
stripped = blob.strip()
if not stripped:
    print("{}")
    sys.exit(0)
try:
    d = json.loads(stripped)
except Exception:
    # session-start печатает текст. Cursor кладёт в контекст только additional_context.
    print(json.dumps({"additional_context": stripped}, ensure_ascii=False))
    sys.exit(0)
if not isinstance(d, dict):
    print("{}")
    sys.exit(0)
h = d.get("hookSpecificOutput") or {}
perm = h.get("permissionDecision") or d.get("permission") or ""
why = (h.get("permissionDecisionReason") or d.get("user_message") or d.get("agent_message") or "").strip()
ctx = h.get("additionalContext") or d.get("additional_context") or d.get("systemMessage") or ""
result = {}
if perm == "deny":
    result["permission"] = "deny"
    if why:
        result["user_message"] = why
        result["agent_message"] = why
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(2)
if ctx:
    result["additional_context"] = ctx
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)
print("{}")
PY
)"
TRC=$?
printf '%s\n' "$TRANSLATED"

# Упал сам гейт (не JSON-deny адаптера) — для блокирующего это стоп.
if [ "$RC" -ne 0 ] && [ "$TRC" -ne 2 ]; then
  case " $INJECT " in
    *" $GATE "*) exit 0 ;;
    *) deny_now "Гейт $GATE не отработал (код $RC). Упавшая проверка = стоп." ;;
  esac
fi
exit "$TRC"
