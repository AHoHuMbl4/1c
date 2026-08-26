#!/usr/bin/env bash
# Гейт И5: код ответа + приёмочный набор в одном коммите = стоп.
#
# 🔴 ЭТО ПОДГОТОВЛЕННАЯ ВЕРСИЯ. В `.claude/hooks/` сессия не пишет (root-owned).
#
# УСТАНОВКА (владелец, из корня репозитория):
#   1. bash work/hooks/install-gates.sh
#      — ставит check-gold-split.sh в .claude/hooks/ (755),
#        обновляет git-gate (commit-msg), lib-hooks, kimi-config, .cursor/hooks.json,
#        дописывает гейт в .claude/settings.json, прогоняет пробы.
#   2. Проба отдельно (если нужен только И5): bash work/hooks/test-gold-split.sh
#   3. После установки — дописать в docs/GOLD_SETS.md §5 «Чем держится механически»
#      абзац про гейт (см. отчёт И5); до установки документ не трогать.
#
# ЗАЧЕМ. Прецедент 993ad81: вопрос и эталон правились в одном коммите с
# serene_ask.py + ab_scorer.py, и ничто это не остановило. Правило GOLD_SETS
# «приёмочный набор не открываем при отладке» жило дисциплиной; замер 03.08:
# напоминание без остановки исполнено 0 раз из 94. PLAN_TO_TARGET §И5 + §4 п.2–3.
#
# ЧТО ДЕЛАЕТ.
#   * одновременно затронуты (а) исполняемый код ответа и (б) файлы роли
#     «для приёмки» из docs/GOLD_SETS.md → deny (пометкой не закрывается;
#     аварийный люк — override.txt у владельца);
#   * правка только эталона приёмки без пометки «Факт 1С: …» → deny;
#   * только код / только эталон с пометкой → пропуск.
#
# Реестр ролей читается из docs/GOLD_SETS.md (§3 + пути §1), не зашит здесь.
set -uo pipefail

. "$(dirname "${BASH_SOURCE[0]}")/lib-hooks.sh"
CMD=$(hook_command)
is_git_commit "$CMD" || { echo '{}'; exit 0; }

cd_repo || { hook_ask "Хук $(basename "$0") не смог определить каталог репозитория и ничего не проверил. Пропускать проверку молча нельзя — подтвердите шаг вручную."; exit 0; }

mapfile -t PS < <(hook_commit_pathspec "$CMD")
if [ "${#PS[@]}" -gt 0 ]; then
  STAGED=$(git diff --cached --name-only -- "${PS[@]}" 2>/dev/null)
else
  STAGED=$(git diff --cached --name-only 2>/dev/null)
fi
[ -z "$STAGED" ] && { echo '{}'; exit 0; }

# Пометка закрывает правку ЭТАЛОНА отдельно от кода (не комбо).
HOOK_CMD_FOR_NOTE="$CMD"
NOTE="$(hook_commit_note 'факт[[:space:]]*1[СсCc]|1[СсCc]')"

# Разбор реестра и классификация staged — в python (разбор markdown).
export GOLD_SPLIT_STAGED="$STAGED"
export GOLD_SPLIT_NOTE="$NOTE"
python3 <<'PY' | hook_gate_json check-gold-split
import json, os, re, sys, time

def log(msg):
    try:
        with open(".claude/hooks.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m %H:%M:%S") + " gold-split  " + msg + "\n")
    except Exception:
        pass

# Исполняемый код ответа — то, что формирует/считает ответ (прецедент 993ad81).
ANSWER_CODE = {
    "ubuntu/serenedb/serene_ask.py",
    "ubuntu/serenedb/ab_scorer.py",
}

DOC = "docs/GOLD_SETS.md"
staged = [p.strip() for p in (os.environ.get("GOLD_SPLIT_STAGED") or "").splitlines() if p.strip()]
note = (os.environ.get("GOLD_SPLIT_NOTE") or "").strip()

def deny(reason: str) -> None:
    log("СТОП: " + reason.split("\n", 1)[0][:120])
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)

def ok(msg: str = "тихо") -> None:
    log(msg)
    print("{}")
    sys.exit(0)

if not os.path.isfile(DOC):
    deny(
        "Гейт check-gold-split: нет %s — реестр ролей наборов прочитать нечем.\n"
        "Без реестра правило «код + приёмка = стоп» проверить нельзя; молча пропускать "
        "нельзя (fail-open).\nВерните файл или обойдите люком владельца." % DOC
    )

text = open(DOC, encoding="utf-8").read()

# §1: basename → путь репозитория (из markdown-ссылок таблицы реестра).
basename_to_path = {}
for m in re.finditer(
    r"\|\s*\[`([^`]+)`\]\(([^)]+)\)",
    text,
):
    shown, href = m.group(1).strip(), m.group(2).strip()
    # href вида ../ubuntu/... или ACCEPTANCE_UT.md рядом с docs/
    if href.startswith("../"):
        path = href[3:]
    elif href.startswith("./"):
        path = "docs/" + href[2:]
    elif "/" not in href:
        # относительная ссылка внутри docs/
        path = shown if "/" in shown else ("docs/" + href)
    else:
        path = href.lstrip("/")
    if shown.startswith("docs/") or shown.startswith("ubuntu/") or shown.startswith("work/"):
        path = shown
    basename_to_path[os.path.basename(path)] = path
    basename_to_path[os.path.basename(shown)] = path

# §3 «Разделение»: строки роли с «приёмк» (приёмочный / приёмка).
sec3 = text
idx = text.find("## 3.")
if idx >= 0:
    rest = text[idx + 4:]
    nxt = re.search(r"\n## \d", rest)
    sec3 = rest[: nxt.start()] if nxt else rest

acceptance = set()
parse_hits = 0
for line in sec3.splitlines():
    if "|" not in line or "---" in line or line.strip().startswith("| Роль"):
        continue
    # | **Роль** | `набор` … | …
    m = re.match(
        r"\|\s*\*\*([^*]+)\*\*\s*\|\s*`([^`]+)`",
        line.strip(),
    )
    if not m:
        continue
    role = m.group(1).strip()
    raw = m.group(2).strip()
    # «приёмочный» → приемочный (нет «приемк»); «приёмка» → приемка.
    role_n = role.lower().replace("ё", "е")
    if not re.search(r"прием(к|оч)", role_n):
        continue
    parse_hits += 1
    # путь: полный или basename из §1
    if "/" in raw:
        path = raw
    else:
        path = basename_to_path.get(raw) or basename_to_path.get(os.path.basename(raw))
        if not path:
            # запас: известные каталоги наборов
            for prefix in ("ubuntu/serenedb/", "docs/", "work/acceptance/"):
                cand = prefix + raw
                if os.path.isfile(cand) or cand in staged:
                    path = cand
                    break
            if not path:
                path = "ubuntu/serenedb/" + raw
    acceptance.add(path)

if not acceptance:
    deny(
        "Гейт check-gold-split: в %s §3 не найдено ни одного набора роли «приёмка»/"
        "«приёмочный».\nРеестр обязан объявлять замороженную приёмку — иначе гейт "
        "нечего сторожить и превращается в пустышку.\nПоправьте GOLD_SETS.md "
        "(или люк владельца, если документ ещё не готов)." % DOC
    )

def is_acceptance(path: str) -> bool:
    if path in acceptance:
        return True
    base = os.path.basename(path)
    for a in acceptance:
        if os.path.basename(a) == base and (
            path == a or path.endswith("/" + a) or a.endswith("/" + path)
        ):
            return True
        if os.path.basename(a) == base and path.endswith(base):
            # один и тот же файл под коротким/длинным путём
            return True
    return False

acc_hit = sorted({p for p in staged if is_acceptance(p)})
code_hit = sorted({p for p in staged if p in ANSWER_CODE})

if not acc_hit:
    ok("тихо (приёмочный набор не в коммите)")

if code_hit and acc_hit:
    deny(
        "Гейт check-gold-split (И5): в одном коммите и код ответа, и приёмочный набор.\n\n"
        "Код ответа:\n  " + "\n  ".join(code_hit) + "\n"
        "Приёмка (роль из docs/GOLD_SETS.md §3):\n  " + "\n  ".join(acc_hit) + "\n\n"
        "Прецедент 993ad81: эталон правили вместе с serene_ask/ab_scorer — подгонка.\n"
        "Правило PLAN_TO_TARGET §4 п.2: эталон — только по факту 1С и отдельным "
        "коммитом от кода.\n\n"
        "Разнесите на два коммита. Пометкой «Факт 1С:» комбо не закрывается "
        "(иначе правило снова на дисциплине).\n"
        "Аварийный люк — строка в .claude/hooks/override.txt у владельца."
    )

# Только эталон приёмки: нужна запись факта 1С в сообщении.
if note:
    ok("пропуск: эталон с пометкой — " + note[:80])

deny(
    "Гейт check-gold-split (И5): правка приёмочного набора без ссылки на факт 1С.\n\n"
    "Файлы приёмки:\n  " + "\n  ".join(acc_hit) + "\n\n"
    "Эталон правится только по факту 1С (не по ответу системы), отдельным коммитом "
    "от кода ответа — PLAN_TO_TARGET §4 п.2 / GOLD_SETS.\n\n"
    "Добавьте в сообщение коммита строку вида:\n"
    "  Факт 1С: <откуда взято эталонное значение — OData/отчёт/ссылка>\n"
    "и повторите коммит. Люк владельца — только если гейт ошибается."
)
PY
