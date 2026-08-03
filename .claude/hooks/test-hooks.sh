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
asks() { printf '%s' "$1" | grep -q '"permissionDecision": *"ask"'; }

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
cp "$REPO"/.claude/hooks/{lib-hooks.sh,check-docs.sh,check-graph-fresh.sh,check-active-size.sh} "$G/.claude/hooks/"
cp "$REPO"/.githooks/pre-commit "$G/.githooks/"
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

echo
if [ "$FAILED" != 0 ]; then echo "🔴 ПРОВАЛОВ: $FAILED"; exit 1; fi
echo 'Хуки прошли пробу полностью.'
