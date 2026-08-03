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
path = ti.get("file_path") or ""
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
