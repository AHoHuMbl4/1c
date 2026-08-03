#!/usr/bin/env bash
# Проба хуков. Без сервера, без базы, без модели: временный репозиторий в /tmp.
#
# Зачем: хуки — это код, который держит правила проекта, и до 02.08 у него не было ни
# одной проверки. Дефект `F248` (отбор команды по подстроке «git commit», мимо которой
# проходит `git -C … commit`) прожил столько же, сколько сами хуки, и нашёл его аудит, а
# не прогон. Правило, которое держится кодом, обязано иметь пробу — иначе оно держится
# верой в код.
#
# Запуск: bash .claude/hooks/test-hooks.sh   (код возврата 1 при любом провале)
set -uo pipefail

HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HOOKS/lib-hooks.sh"
FAILED=0

say() { # say <ок?> <название>
  if [ "$1" = 0 ]; then printf 'OK   %s\n' "$2"; else printf '🔴   %s\n' "$2"; FAILED=$((FAILED+1)); fi
}

# --- опознаватели команд ---------------------------------------------------------
echo '== опознаватель коммита (F248) =='
for c in 'git commit -m x' 'git -C /srv/1c commit -m x' 'git -c user.name=X commit' \
         'git --git-dir=/srv/1c/.git --work-tree=/srv/1c commit -m x' \
         'cd /tmp && git -C /srv/1c commit -m x'; do
  is_git_commit "$c"; say $? "коммит опознан: $c"
done
for c in 'git log --grep commit' 'git status' 'git log | grep commit' 'echo commit'; do
  is_git_commit "$c"; [ $? = 1 ]; say $? "не коммит: $c"
done

echo '== опознаватель выката (F133, №14) =='
for c in 'scp x root@h:/opt/' 'rsync -a x h:/opt/' 'ubuntu/serenedb/deploy.sh' \
         'bash ubuntu/openclaw/deploy_instance.sh' 'install -m 755 x.py /opt/1c-mcp-reports/' \
         'cp -f x.py /opt/1c-mcp-reports/x.py'; do
  is_deploy "$c"; say $? "выкат опознан: $c"
done
for c in 'ls /opt' 'git commit -m x' 'python3 work/acceptance/test_acceptance.py'; do
  is_deploy "$c"; [ $? = 1 ]; say $? "не выкат: $c"
done

# --- хуки на временном репозитории -----------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$TMP" || exit 1
git init -q .
git config user.email t@t; git config user.name t
mkdir -p ubuntu/serenedb .claude
printf 'print(1)\n' > ubuntu/serenedb/real.py
printf '# doc\n' > README.md
git add -A; git commit -qm init

# Хук зовётся так же, как его зовёт движок: событие JSON на stdin.
call() { printf '{"tool_input":{"command":%s}}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")" | bash "$HOOKS/$2" 2>/dev/null; }
# 🔴 Ждём именно `deny`. Прежде проба ждала `ask` — и была зелёной ровно в тот день, когда
# замер показал, что `ask` в фоновой сессии равен разрешению: правка, которую хук обязан
# остановить, прошла молча. Проба, согласная с дефектом, хуже отсутствующей.
asks() { printf '%s' "$1" | grep -q '"permissionDecision": *"deny"'; }

echo '== check-docs: обратная проверка (№13) =='
printf 'ссылка на ubuntu/serenedb/ghost.py\n' >> README.md
git add README.md
OUT=$(call 'git commit -m x' check-docs.sh)
asks "$OUT"; say $? 'документ про несуществующий файл — спрашивает'

git reset -q; git checkout -q -- README.md
printf 'ссылка на ubuntu/serenedb/real.py\n' >> README.md
git add README.md
OUT=$(call 'git commit -m x' check-docs.sh)
asks "$OUT"; [ $? = 1 ]; say $? 'документ про существующий файл — молчит'

echo '== check-docs: прямая проверка (код без документов) =='
git reset -q; git checkout -q -- README.md
printf 'print(2)\n' > ubuntu/serenedb/new.py
git add ubuntu/serenedb/new.py
OUT=$(call 'git commit -m x' check-docs.sh)
asks "$OUT"; say $? 'код без документов — спрашивает'
OUT=$(call 'git -C . commit -m x' check-docs.sh)
asks "$OUT"; say $? 'та же проверка на форме `git -C … commit` (F248)'
OUT=$(call 'git status' check-docs.sh)
asks "$OUT"; [ $? = 1 ]; say $? 'на посторонней команде молчит'

echo '== check-golden: замер до выката (№14) =='
mkdir -p ubuntu/serenedb
OUT=$(call 'ubuntu/serenedb/deploy.sh' check-golden.sh)
asks "$OUT"; say $? 'выкат deploy.sh без отметки замера — спрашивает'
touch .claude/.golden-last-run
sleep 1; touch ubuntu/serenedb/new.py
OUT=$(call 'ubuntu/serenedb/deploy.sh' check-golden.sh)
asks "$OUT"; say $? 'исходники правились после замера — спрашивает'
touch .claude/.golden-last-run
OUT=$(call 'ubuntu/serenedb/deploy.sh' check-golden.sh)
asks "$OUT"; [ $? = 1 ]; say $? 'замер свежее правок — молчит'
OUT=$(call 'ls /opt' check-golden.sh)
asks "$OUT"; [ $? = 1 ]; say $? 'на посторонней команде молчит'

echo '== каталог запуска: хук не имеет права молчать (fail-open 02.08) =='
# Хук зовут не обязательно из каталога проекта. Прежняя форма
# `cd "$(git rev-parse --show-toplevel || echo .)"` в этом случае оставалась в чужом
# каталоге, `git diff --cached` отдавал пусто, и коммит проходил БЕЗ ПРОВЕРКИ.
printf 'print(3)\n' > "$TMP/ubuntu/serenedb/other.py"
git -C "$TMP" add ubuntu/serenedb/other.py
OUT=$(cd / && CLAUDE_PROJECT_DIR="$TMP" bash -c "printf '%s' '{\"tool_input\":{\"command\":\"git commit -m x\"}}' | bash '$HOOKS/check-docs.sh'" 2>/dev/null)
asks "$OUT"; say $? 'запуск из / с CLAUDE_PROJECT_DIR — проверяет указанный репозиторий'
ROOT=$(cd / && env -u CLAUDE_PROJECT_DIR bash -c ". '$HOOKS/lib-hooks.sh'; hook_repo_root")
[ "$ROOT" = "$(cd "$HOOKS/../.." && pwd)" ]
say $? 'без переменной и вне репозитория — корень берётся от места самого хука'
cd "$TMP" || exit 1

echo '== гейт git (.githooks/pre-commit): последний рубеж =='
# 🔴 Проверяется НАСТОЯЩИМИ коммитами: `git commit --dry-run` хуки не зовёт вовсе, и
# «проверил на сухом прогоне» означало бы, что не проверил.
REPO="$(cd "$HOOKS/../.." && pwd)"
G="$TMP/gate"; mkdir -p "$G/.claude/hooks" "$G/memory_bank" "$G/ubuntu/serenedb" \
                        "$G/windows/odata-setup" "$G/.githooks"
# 🔴 Копируются ВСЕ хуки, а не выборка. 03.08 проба падала на случае «коммит проходит»
# только потому, что в песочницу не попал `check-sql-docs.sh`, добавленный в гейт: гейт
# честно сообщал «проверка не отработала», а выглядело это как поломка гейта. Выборка
# файлов в пробе — это второй список, который обязан совпадать с настоящим и не совпадает.
cp "$REPO"/.claude/hooks/*.sh "$G/.claude/hooks/" 2>/dev/null
cp "$HOOKS"/*.sh "$G/.claude/hooks/" 2>/dev/null   # проверяем ту версию, что правится
cp "$REPO"/.githooks/pre-commit "$G/.githooks/"
# Гейты сверяются с настройками сессии — в песочнице нужен свой settings.json с их именами.
python3 - "$G" <<'PY'
import json, sys
gates = ["check-docs", "check-graph-fresh", "check-active-size", "check-sql-docs",
         "check-diff", "check-prompt-rules", "check-golden", "check-gates"]
hooks = [{"type": "command", "command": ".claude/hooks/%s.sh" % g} for g in gates]
json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": hooks}]}},
          open(sys.argv[1] + "/.claude/settings.json", "w"), ensure_ascii=False)
PY
printf '{"entities":[],"relations":[]}\n' > "$G/memory_bank/mcp-memory.json"
printf '# Active Context\n' > "$G/memory_bank/activeContext.md"
cd "$G" || exit 1
git init -q .; git config user.email t@t; git config user.name t
git config core.hooksPath .githooks
printf '# doc\n' > README.md; printf 'print(0)\n' > ubuntu/serenedb/known.py
git commit -qm init --no-verify -- README.md ubuntu/serenedb/known.py 2>/dev/null || { git add -A; git commit -qm init --no-verify; }

gate() { # gate <ожидание: block|pass> <название>
  local want="$1" name="$2"
  git commit -qm "$name" >/dev/null 2>&1
  local rc=$?
  if [ "$want" = block ]; then [ "$rc" -ne 0 ]; else [ "$rc" -eq 0 ]; fi
  say $? "$name"
  # Каждый случай независим: заблокированный коммит не должен тащить свой индекс
  # в следующий — иначе одна поломка выдаёт себя за несколько.
  git reset -q
}

printf 'print(1)\n' > ubuntu/serenedb/newcode.py; git add ubuntu/serenedb/newcode.py
gate block 'код без документов — коммит остановлен'

printf '\nстрока\n' >> README.md; git add ubuntu/serenedb/newcode.py README.md
gate block 'код с документом, но компонент не в графе — остановлен'

# 🔴 С 03.08 «граф тронут» не пропуск: компонент должен существовать СУЩНОСТЬЮ в той
# версии графа, что идёт в коммит (дыра: имена в наблюдениях чужих сущностей считались
# учётом). Формат — JSONL, по объекту на строку, как пишет сервер MCP memory: агрегат
# {"entities":[…]} гейт видеть не обязан.
printf '{"type":"entity","name":"newcode.py","entityType":"компонент","observations":["проба test-hooks"]}\n' \
  > memory_bank/mcp-memory.json
git add ubuntu/serenedb/newcode.py README.md memory_bank/mcp-memory.json
gate pass 'код + документ + граф с сущностью компонента — коммит проходит'

printf 'x\n' > windows/odata-setup/setup.cs; git add windows/odata-setup/setup.cs
gate pass 'трек владельца (odata-setup) пропускается'

printf 'print(2)\n' > ubuntu/serenedb/nodocs.py; git add ubuntu/serenedb/nodocs.py
git commit -qm 'обход осознанный' --no-verify >/dev/null 2>&1
say $? '--no-verify обходит гейт (аварийный люк на месте)'
git reset -q

# Упавшая проверка не должна означать пройденную.
printf 'print(3)\n' > ubuntu/serenedb/broken.py; git add ubuntu/serenedb/broken.py
cp .claude/hooks/check-docs.sh "$TMP/cd-gate.bak"
printf '#!/usr/bin/env bash\nexit 3\n' > .claude/hooks/check-docs.sh
gate block 'упавшая проверка = не пройденная, а не пропущенная'
cp "$TMP/cd-gate.bak" .claude/hooks/check-docs.sh
cd "$TMP" || exit 1

# --- правило в промте (check-prompt-rules.sh) ------------------------------------
# 🔴 Первая редакция этого хука читала событие из stdin внутри `python3 - <<'PY'`, а
# heredoc сам занимает stdin — питон разбирал как событие текст собственной программы.
# Хук при этом НЕ падал: он молча печатал `{}` на любой вход, то есть был fail-open и не
# поймал бы ничего. Нашла это проба, а не чтение кода — поэтому она здесь.
echo
echo '== правило, вписанное в промт =='
PR="$HOOKS/check-prompt-rules.sh"
SAMPLE="$TMP/prompt-sample.py"
printf '%s\n' '# Комментарий: разделитель обязателен всегда.' \
              'ANSWER_SYS = """You answer questions.' \
              'Use the figures as they are.' \
              '"""' \
              'x = 1' > "$SAMPLE"

pr_case() { # pr_case <ждём ask|pass> <json события> <название>
  local want="$1" ev="$2" name="$3" out
  out=$(printf '%s' "$ev" | bash "$PR" 2>/dev/null)
  case "$out" in
    *'"permissionDecision": "deny"'*) if [ "$want" = ask ]; then say 0 "$name"; else say 1 "$name"; fi ;;
    *) if [ "$want" = pass ]; then say 0 "$name"; else say 1 "$name"; fi ;;
  esac
}

pr_case ask "$(python3 -c 'import json;print(json.dumps({"tool_input":{"file_path":"/x/ubuntu/openclaw/instance/AGENTS.md","new_string":"Ты обязан всегда звать ask_1c перед ответом.","old_string":""}}))')" \
  'правило в персону бота — останавливает'
pr_case ask "$(python3 -c 'import json,sys;print(json.dumps({"tool_input":{"file_path":sys.argv[1],"new_string":"ANSWER_SYS = \"\"\"You answer questions.\nYou must always call the tool.\n\"\"\"","old_string":"ANSWER_SYS = \"\"\"You answer questions.\nUse the figures as they are.\n\"\"\""}}))' "$SAMPLE")" \
  'правило в строковый литерал питона — останавливает (разбор, не догадка)'
pr_case pass "$(python3 -c 'import json,sys;print(json.dumps({"tool_input":{"file_path":sys.argv[1],"new_string":"# Разделитель равенства обязателен всегда.\nx = 1","old_string":"x = 1"}}))' "$SAMPLE")" \
  'то же слово в КОММЕНТАРИИ — пропускает (нет ложных срабатываний)'
pr_case pass "$(python3 -c 'import json,sys;print(json.dumps({"tool_input":{"file_path":sys.argv[1],"new_string":"x = 2","old_string":"x = 1"}}))' "$SAMPLE")" \
  'обычная правка кода — пропускает'
pr_case ask "$(python3 -c 'import json;print(json.dumps({"tool_input":{"file_path":"/x/verify-plugin/index.js","new_string":"      instruction: \"You must call the data tool before answering.\",","old_string":""}}))')" \
  'правило в поле instruction (текст уходит модели) — останавливает'
pr_case pass "$(python3 -c 'import json;print(json.dumps({"tool_input":{"file_path":"/x/docs/HOW_NOT_TO.md","new_string":"Правило: разделитель равенства обязателен всегда.","old_string":""}}))')" \
  'правило в ДОКУМЕНТ — пропускает: документы для людей, а не для модели'

# --- большой дифф -----------------------------------------------------------------
# 🔴 Гейты передавали дифф python-части ЧЕРЕЗ ОКРУЖЕНИЕ, и на крупном коммите это давало
# `/usr/bin/python3: Argument list too long` (код 126). Гейт коммита считает упавшую
# проверку непройденной — значит правило отказывало ровно на больших правках, где нужнее.
# Поймано настоящим коммитом этой самой работы. Порог здесь заведомо выше предела окружения.
echo
echo '== большой дифф не роняет гейты =='
cd "$G" || exit 1
python3 - <<'PY'
with open("bigfile.py", "w", encoding="utf-8") as f:
    for i in range(20000):
        f.write("x%d = 'строка данных номер %d, достаточно длинная чтобы набрать объём'\n" % (i, i))
PY
git add bigfile.py
for h in check-sql-docs check-prompt-rules; do
  OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash ".claude/hooks/$h.sh" 2>/dev/null)
  rc=$?
  [ "$rc" = 0 ] && printf '%s' "$OUT" | grep -qv 'Argument list too long'
  say $? "$h переживает дифф в 20 000 строк (код $rc)"
done
git reset -q; rm -f bigfile.py
cd "$TMP" || exit 1

# --- аварийный люк ----------------------------------------------------------------
echo
echo '== аварийный люк (одноразовый, со следом) =='
L="$TMP/hatch"; mkdir -p "$L/.claude/state" "$L/.claude/hooks" "$L/.git"
cd "$L" || exit 1; git init -q .
cp "$HOOKS"/lib-hooks.sh "$L/.claude/hooks/"
( . "$L/.claude/hooks/lib-hooks.sh"
  cd "$L"
  # 🔴 Файл ИЗ ОДНОЙ СТРОКИ — тот самый случай, на котором первая редакция ломалась:
  # `grep -v … > tmp && mv` при пустом остатке возвращал 1, `mv` не выполнялся, и люк
  # оставался открытым навсегда, притом что в журнал уже ушло «потреблён».
  printf 'check-docs проба одноразовости\n' > .claude/state/override.txt
  hook_override_take check-docs || exit 11
  [ -s .claude/state/override.txt ] && exit 12          # строка обязана исчезнуть
  hook_override_take check-docs && exit 13              # второй раз люка нет
  grep -q 'ОБХОД ЛЮКОМ' .claude/hooks.log || exit 14    # след обязателен
  printf 'check-docs причина\n' > .claude/state/override.txt
  hook_override_take check-doc && exit 15               # имя сверяется точно, не образцом
  exit 0 )
say $? 'люк: одноразовый на файле из одной строки, точное имя, след в журнале'

# --- воронка ответа (fail-open) ---------------------------------------------------
echo '== воронка ответа: упавшая проверка = остановка =='
( . "$HOOKS/lib-hooks.sh"
  cd "$L"
  rm -f .claude/state/override.txt
  printf '' | hook_gate_json check-docs | grep -q '"deny"' || exit 21          # пустой вывод
  printf 'Traceback (most recent call last):' | hook_gate_json check-docs | grep -q '"deny"' || exit 22
  printf '{}' | hook_gate_json check-docs | grep -q 'permissionDecision' && exit 23  # молчание проходит
  printf '{"hookSpecificOutput":{"permissionDecision":"ask","permissionDecisionReason":"x"}}' \
    | hook_gate_json check-docs | grep -q '"deny"' || exit 24                  # ask поднимается до deny
  exit 0 )
say $? 'воронка: пусто и мусор → deny, «{}» → пропуск, ask → deny'

# --- самозащита: гейты сторожат друг друга ----------------------------------------
echo '== защита гейтов (hook_guard_armed) =='
cd "$G" || exit 1
armed() { ( . "$G/.claude/hooks/lib-hooks.sh"; cd "$G"; hook_guard_armed ); }
[ -z "$(armed)" ]; say $? 'целое состояние — нарушений нет'

git config --unset core.hooksPath
[ -n "$(armed)" ]; say $? 'снят core.hooksPath — нарушение видно'
git config core.hooksPath .githooks

cp .githooks/pre-commit "$TMP/wrap.bak"
printf '#!/usr/bin/env bash\nexit 0\n' > .githooks/pre-commit; chmod +x .githooks/pre-commit
[ -n "$(armed)" ]; say $? 'обёртка выпотрошена (гейт не зовётся) — нарушение видно'
cp "$TMP/wrap.bak" .githooks/pre-commit

cp .claude/hooks/check-docs.sh "$TMP/soft.bak"
sed -i 's/"permissionDecision": "deny"/"permissionDecision": "ask"/' .claude/hooks/check-docs.sh
[ -n "$(armed)" ]; say $? 'вердикт понижен до ask — нарушение видно'
cp "$TMP/soft.bak" .claude/hooks/check-docs.sh

cp .claude/settings.json "$TMP/set.bak"
python3 -c "
import json
p='.claude/settings.json'
d=json.load(open(p))
hs=d['hooks']['PreToolUse'][0]['hooks']
d['hooks']['PreToolUse'][0]['hooks']=[h for h in hs if 'check-sql-docs' not in h['command']]
json.dump(d, open(p,'w'), ensure_ascii=False)"
[ -n "$(armed)" ]; say $? 'гейт убран из settings.json — нарушение видно'
cp "$TMP/set.bak" .claude/settings.json
[ -z "$(armed)" ]; say $? 'всё возвращено — нарушений снова нет'

echo '== check-gates: разоружение останавливает коммит =='
cp .githooks/pre-commit "$TMP/wrap2.bak"
printf '#!/usr/bin/env bash\nexit 0\n' > .githooks/pre-commit; chmod +x .githooks/pre-commit
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-gates.sh 2>/dev/null)
asks "$OUT"; say $? 'разоружённый гейт — check-gates останавливает коммит'
OUT=$(printf '{"tool_input":{"command":"ls"}}' | bash .claude/hooks/check-gates.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'на посторонней команде молчит'
cp "$TMP/wrap2.bak" .githooks/pre-commit
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-gates.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'защита цела — молчит'

# --- правило в промте на КОММИТЕ (правка мимо сессии) -----------------------------
echo '== правило в промте: второй заход, по индексу =='
cd "$G" || exit 1
mkdir -p ubuntu/serenedb
printf 'SYS = """You answer questions.\nUse the figures as they are.\n"""\n' > ubuntu/serenedb/prompts.py
git add ubuntu/serenedb/prompts.py; git commit -qm base --no-verify >/dev/null 2>&1
printf 'SYS = """You answer questions.\nYou must always call the tool first.\n"""\n' > ubuntu/serenedb/prompts.py
git add ubuntu/serenedb/prompts.py
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-prompt-rules.sh 2>/dev/null)
asks "$OUT"; say $? 'правило добавлено в литерал МИМО сессии — ловится на коммите'
git reset -q; git checkout -q -- ubuntu/serenedb/prompts.py

printf 'SYS = """You answer questions.\nUse the figures as they are.\n"""\n# Комментарий: разделитель обязателен всегда.\n' > ubuntu/serenedb/prompts.py
git add ubuntu/serenedb/prompts.py
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-prompt-rules.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'то же слово в комментарии — на коммите молчит'
git reset -q
cd "$TMP" || exit 1

echo
if [ "$FAILED" != 0 ]; then echo "🔴 ПРОВАЛОВ: $FAILED"; exit 1; fi
echo 'Хуки прошли пробу полностью.'
