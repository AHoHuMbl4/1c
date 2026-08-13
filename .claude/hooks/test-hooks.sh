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
# 🔴 «Кладёт в /opt» ещё не значит «выкатывает наш код»: 03.08 гейт замера остановил перенос
# самого Claude Code в /opt. Ложная тревога такого рода приучает обходить гейт, поэтому
# выкатом считается попадание туда файла ИЗ ДЕРЕВА ПРОЕКТА.
for c in 'cp -a /root/.local/share/claude/. /opt/claude-code/' \
         'install -m 644 /etc/hosts /opt/backup/hosts'; do
  is_deploy "$c"; [ $? = 1 ]; say $? "не выкат (чужой источник): $c"
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
# 🔴 ОБЁРТКИ БЕРУТСЯ ИЗ УСТАНОВЛЕННОГО `.githooks`, а не из подготовительного каталога.
# Проба, запущенная копией из `.claude/hooks/`, не находила там `commit-msg.thin` (туда
# ставятся только `*.sh`) — и падала на «защита цела», хотя защита была цела: в реальном
# репозитории обёртка стоит. Проба обязана смотреть на то же, что работает.
cp "$REPO"/.githooks/pre-commit "$G/.githooks/" 2>/dev/null
if [ -f "$REPO/.githooks/commit-msg" ]; then
  cp "$REPO"/.githooks/commit-msg "$G/.githooks/"
else
  install -m 755 "$HOOKS/commit-msg.thin" "$G/.githooks/commit-msg" 2>/dev/null
fi
chmod +x "$G"/.githooks/* 2>/dev/null
# Гейты сверяются с настройками сессии — в песочнице нужен свой settings.json с их именами.
python3 - "$G" <<'PY'
import json, sys
gates = ["check-docs", "check-graph-fresh", "check-active-size", "check-sql-docs",
         "check-diff", "check-prompt-rules", "check-golden", "check-gates", "prepare-diff"]
hooks = [{"type": "command", "command": ".claude/hooks/%s.sh" % g} for g in gates]
json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": hooks}]}},
          open(sys.argv[1] + "/.claude/settings.json", "w"), ensure_ascii=False)
PY
printf '{"entities":[],"relations":[]}\n' > "$G/memory_bank/mcp-memory.json"
printf '# Active Context\n' > "$G/memory_bank/activeContext.md"
# Правила проекта — часть проверяемого состояния: с 03.08 hook_guard_armed сверяет, что они
# на месте и принадлежат владельцу (подмена сносом и подкладыванием своего иначе не видна).
mkdir -p "$G/memory_bank/owner-memory"
printf '# правила\n' > "$G/CLAUDE.md"
printf '# контракт\n' > "$G/TARGET.md"
printf '# решение владельца\n' > "$G/memory_bank/owner-memory/probe.md"
# AGENTS.md — второе имя правил для Kimi (жёсткая ссылка в настоящем репозитории);
# сторож сверяет его наличие и владельца наравне с CLAUDE.md.
printf '# агенты\n' > "$G/AGENTS.md"
# Stub подключения Kimi — ИЗ КАНОНИЧЕСКОГО ШАБЛОНА с подменой пути под песочницу:
# проба проверяет ту же проводку, что ставится вживую, а не второй список, который
# обязан совпадать с настоящим и не совпадает (тот же урок, что с выборкой хуков 03.08).
# Сторож разбирает TOML и сверяет пары (событие, команда), поэтому stub обязан быть
# настоящим TOML, а не набором строк для грепа.
sed "s|/srv/1c/.claude/hooks|$G/.claude/hooks|g" "$REPO/work/hooks/kimi-config.toml" > "$G/kimi-config.toml"
export KIMI_CONFIG_TOML="$G/kimi-config.toml"
mkdir -p "$G/.cursor"
cp "$REPO/.cursor/hooks.json" "$G/.cursor/hooks.json"
cp "$REPO/.cursor/mcp.json" "$G/.cursor/mcp.json"
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

# 🔴 Пометка в сообщении проверяется НАСТОЯЩИМ коммитом: в pre-commit сообщения ещё нет
# (man githooks: «before obtaining the proposed commit log message»), и первая редакция
# читала .git/COMMIT_EDITMSG — то есть текст ПРОШЛОГО коммита. Нашла рабочая сессия.
printf 'q = "SELECT src_table FROM search_idx"\n' > ubuntu/serenedb/gsql.py
printf '\nстрока про gsql\n' >> README.md
printf '{"type":"entity","name":"gsql.py","entityType":"компонент","observations":["проба"]}\n' \
  >> memory_bank/mcp-memory.json
git add ubuntu/serenedb/gsql.py README.md memory_bank/mcp-memory.json
gate block 'SQL без пометки — коммит остановлен со стороны git'

git add ubuntu/serenedb/gsql.py README.md memory_bank/mcp-memory.json
git commit -qm 'правка. Доки: sql/functions/search/full-text' >/dev/null 2>&1
say $? 'SQL с пометкой «Доки:» в сообщении — коммит проходит'
git reset -q

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

# --- SQL: раздел доков и чужие файлы в общем индексе ------------------------------
echo
echo '== гейт SQL: раздел доков в коммите, чужое в индексе =='
cd "$G" || exit 1
git reset -q
mkdir -p ubuntu/serenedb
printf 'q = "SELECT src_table FROM search_idx"\n' > ubuntu/serenedb/sqlcode.py
printf 'x = 1\n' > ubuntu/serenedb/plain.py
git add ubuntu/serenedb/sqlcode.py ubuntu/serenedb/plain.py

OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-sql-docs.sh 2>/dev/null)
asks "$OUT"; say $? 'SQL без названного раздела — останавливает'

# 🔴 Раздел называет тот, кто коммитит, — строкой «Доки:» в сообщении. Прежде выходом был
# только аварийный люк, то есть на каждый SQL-коммит дёргали владельца, хотя проверку
# делал исполнитель. Названный раздел вдобавок уезжает в историю вместе с кодом.
OUT=$(printf '{"tool_input":{"command":"git commit -m \x27правка. Доки: sql/functions/search/full-text\x27"}}' | bash .claude/hooks/check-sql-docs.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'раздел назван в сообщении — пропускает'

# 🔴 Индекс общий на все сессии, коммит идёт пат-спеком. Гейт обязан смотреть только то,
# что уедет в историю: чужой staged-файл с SQL не должен останавливать наш коммит.
OUT=$(printf '{"tool_input":{"command":"git commit -m x -- ubuntu/serenedb/plain.py"}}' | bash .claude/hooks/check-sql-docs.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'чужой файл с SQL вне пат-спека — не мешает коммиту'

OUT=$(printf '{"tool_input":{"command":"git commit -m x -- ubuntu/serenedb/sqlcode.py"}}' | bash .claude/hooks/check-sql-docs.sh 2>/dev/null)
asks "$OUT"; say $? 'свой файл с SQL в пат-спеке — останавливает'
git reset -q; rm -f ubuntu/serenedb/sqlcode.py ubuntu/serenedb/plain.py
cd "$TMP" || exit 1

# --- числа: объяснение в коммите ---------------------------------------------------
echo
echo '== гейт подгонки: числа объясняются в коммите =='
cd "$G" || exit 1
git reset -q
printf 'LIMIT = 37\nTHRESHOLD = 0.83\n' > ubuntu/serenedb/nums.py
git add ubuntu/serenedb/nums.py
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/check-diff.sh 2>/dev/null)
asks "$OUT"; say $? 'новые числа без объяснения — останавливает'
OUT=$(printf '{"tool_input":{"command":"git commit -m \x27правка. Числа: бюджеты имитации, не отсечки правильности\x27"}}' | bash .claude/hooks/check-diff.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'числа объяснены в сообщении — пропускает'
git reset -q; rm -f ubuntu/serenedb/nums.py
cd "$TMP" || exit 1

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

# --- подача диффа снайперу --------------------------------------------------------
echo
echo '== дифф для снайпера =='
cd "$G" || exit 1
git reset -q
OUT=$(printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/prepare-diff.sh 2>/dev/null)
# 🔴 Пустой индекс на коммите — не «нечего проверять», а невыполненная проверка: хук движка
# срабатывает ДО команды, поэтому на `git add … && git commit …` индекс ещё пуст. Так живой
# коммит 0d75629 прошёл мимо снайпера: он получил «пусто» и ответил OK.
grep -q 'ДИФФ НЕ СНЯТ' .claude/state/staged.diff
say $? 'пустой индекс на коммите — снайперу подана пометка «дифф не снят», а не пустота'

printf 'print(9)\n' > ubuntu/serenedb/sniper.py; git add ubuntu/serenedb/sniper.py
printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/prepare-diff.sh >/dev/null 2>&1
grep -q 'sniper.py' .claude/state/staged.diff
say $? 'непустой индекс — снайпер получает настоящий дифф'
git reset -q; rm -f ubuntu/serenedb/sniper.py
OUT=$(printf '{"tool_input":{"command":"ls"}}' | bash .claude/hooks/prepare-diff.sh 2>/dev/null)
[ "$OUT" = '{}' ]; say $? 'на посторонней команде молчит'

# 🔴 Граф исключён из ревью (11.08): он раздувал дифф снайпера до ~200 КБ, и модель не
# укладывалась в таймаут (код 124 на пяти коммитах подряд). Коммит из одного графа —
# не код, снайперу подаётся пометка, а не дифф.
printf '{"type":"entity","name":"probe-g2","entityType":"x","observations":[]}\n' >> memory_bank/mcp-memory.json
git add memory_bank/mcp-memory.json
printf '{"tool_input":{"command":"git commit -m x"}}' | bash .claude/hooks/prepare-diff.sh >/dev/null 2>&1
head -1 .claude/state/staged.diff | grep -q 'НЕ КОД'; say $? 'в коммите только граф — снайперу пометка «НЕ КОД»'
git reset -q; git checkout -q -- memory_bank/mcp-memory.json
cd "$TMP" || exit 1

# --- аварийный люк ----------------------------------------------------------------
echo
echo '== аварийный люк (одноразовый, со следом) =='
L="$TMP/hatch"; mkdir -p "$L/.claude/state" "$L/.claude/hooks" "$L/.git"
cd "$L" || exit 1; git init -q .
cp "$HOOKS"/lib-hooks.sh "$L/.claude/hooks/"
( . "$L/.claude/hooks/lib-hooks.sh"
  cd "$L"
  # 🔴 Люк живёт в каталоге гейтов, а не в .claude/state/. Там, где сессия пишет сама, он
  # был бы не люком, а выключателем: исполнитель открывал бы себе дверь одной строкой.
  # Отсюда и то, что строка НЕ потребляется — снимает её владелец, а дверь удерживает
  # остановка коммита, пока файл не пуст.
  HATCH=".claude/hooks/override.txt"
  printf 'check-docs проба люка\n' > "$HATCH"
  hook_override_take check-docs || exit 11
  grep -q 'ОБХОД ЛЮКОМ' .claude/hooks.log || exit 12    # след обязателен
  hook_override_take check-doc && exit 13               # имя сверяется точно, не образцом
  hook_override_take check-active-size && exit 14       # чужой гейт люком не открыт
  [ -s "$HATCH" ] || exit 15                            # строку снимает владелец, не хук
  exit 0 )
say $? 'люк: открывает названный гейт, точное имя, след, строку снимает владелец'

# --- воронка ответа (fail-open) ---------------------------------------------------
echo '== воронка ответа: упавшая проверка = остановка =='
( . "$HOOKS/lib-hooks.sh"
  cd "$L"
  rm -f .claude/hooks/override.txt
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

# 🔴 С 03.08 правила защищены ПРАВАМИ, а не только средой: сессия работает под рабочим
# аккаунтом, каталоги правил принадлежат владельцу. Единственный оставшийся способ обойти
# это — снести файл и положить свой, но тогда владелец файла меняется. Отсюда две пробы.
mv CLAUDE.md "$TMP/rules.bak"
[ -n "$(armed)" ]; say $? 'правило снесено — нарушение видно'
mv "$TMP/rules.bak" CLAUDE.md

# Владельца в песочнице не подменить (тест идёт не от root), поэтому проверяем саму
# способность отличать: подставляем несуществующий путь через тот же список.
OUT=$( . "$G/.claude/hooks/lib-hooks.sh"; cd "$G"; rm -f TARGET.md; hook_guard_armed )
printf '%s' "$OUT" | grep -q 'TARGET.md'; say $? 'пропажу контракта гейт называет поимённо'
printf '# контракт\n' > TARGET.md

[ -z "$(armed)" ]; say $? 'всё возвращено — нарушений снова нет'

echo '== check-gates: повышение прав вместо прямого вызова =='
# 🔴 Сессии повышение прав закрыто её средой, а юниты проекта разрешены polkit напрямую.
# Без этой подсказки попытка упирается намертво и превращается в просьбу к владельцу —
# 04.08 такая просьба пришла дважды уже после того, как прямой путь был сделан.
OUT=$(printf '{"tool_input":{"command":"sudo systemctl restart 1c-serene-ask@ut_test"}}' | bash .claude/hooks/check-gates.sh 2>/dev/null)
asks "$OUT"; say $? 'повышение прав + systemctl — останавливает и называет прямую команду'
OUT=$(printf '{"tool_input":{"command":"systemctl restart 1c-serene-ask@ut_test"}}' | bash .claude/hooks/check-gates.sh 2>/dev/null)
asks "$OUT"; [ $? = 1 ]; say $? 'та же команда напрямую — молчит'

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

# --- вброс состояния в Kimi (prompt-start.sh, UserPromptSubmit) --------------------
echo
echo '== prompt-start: вброс «С ЧЕГО НАЧАТЬ» один раз на сессию =='
cd "$G" || exit 1
printf '# С ЧЕГО НАЧАТЬ\nсвежая строка состояния\n' > memory_bank/activeContext.md
OUT=$(printf '{"session_id":"probe-1","prompt":"x"}' | bash .claude/hooks/prompt-start.sh 2>/dev/null)
printf '%s' "$OUT" | grep -q 'свежая строка состояния'; say $? 'первое сообщение сессии — вброс есть'
OUT=$(printf '{"session_id":"probe-1","prompt":"y"}' | bash .claude/hooks/prompt-start.sh 2>/dev/null)
[ -z "$OUT" ]; say $? 'второе сообщение той же сессии — молчит (метка)'
OUT=$(printf '{"session_id":"probe-2","prompt":"x"}' | bash .claude/hooks/prompt-start.sh 2>/dev/null)
printf '%s' "$OUT" | grep -q 'свежая строка состояния'; say $? 'другая сессия — вброс снова есть'
rm -f .claude/state/prompt-start-probe-*

# --- снайпер Kimi (sniper-kimi.sh) --------------------------------------------------
# 🔴 Модель в пробе подменяется stub'ом через шов SNIPER_KIMI_CMD: проба обязана идти
# без сервера и модели, а форма вызова и разбор вердикта — оставаться настоящими.
echo
echo '== снайпер Kimi: вердикт по маяку, упавшая проверка = остановка =='
cd "$G" || exit 1
git reset -q
stub() { printf '#!/usr/bin/env bash\n%s\n' "$1" > "$TMP/sniper-stub.sh"; chmod +x "$TMP/sniper-stub.sh"; }
sn_call() { printf '%s' "$1" | SNIPER_KIMI_CMD="$TMP/sniper-stub.sh" bash .claude/hooks/sniper-kimi.sh 2>/dev/null; }

stub 'echo "VERDICT: OK"'
OUT=$(sn_call '{"tool_input":{"command":"ls"}}')
[ "$OUT" = '{}' ]; say $? 'на посторонней команде молчит'

OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
asks "$OUT"; say $? 'пустой индекс — вердикта нет, останавливает (0d75629)'

printf 'print(9)\n' > ubuntu/serenedb/sn.py; git add ubuntu/serenedb/sn.py
# 🔴 Маяк со служебной разметкой — настоящий формат `kimi -p` (живые прогоны 06.08:
# «  VERDICT: OK», «• VERDICT: OK»): разбор, требующий начала строки, останавливал
# чистый коммит. Берётся последний маяк в выводе.
stub 'echo "• болтовня с упоминанием VERDICT: OK в рассуждении"; echo "• VERDICT: OK"'
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
[ "$OUT" = '{}' ]; say $? 'VERDICT: OK (с разметкой kimi -p, последний маяк) — пропускает'

stub 'echo "• ход рассуждения"; echo "FINDING: sn.py:1 — свой цикл вместо ts_compound — убрать"; echo "VERDICT: FINDINGS"'
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
asks "$OUT" && printf '%s' "$OUT" | grep -q 'FINDING: sn.py:1'
say $? 'VERDICT: FINDINGS — останавливает, и в причине сама находка, а не шум вывода'

stub 'echo "болтовня без маяка"'
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
asks "$OUT"; say $? 'ответ без маяка — вердикт не разобран, останавливает'

stub 'exit 1'
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
asks "$OUT"; say $? 'модель упала — упавшая проверка = остановка'

# 🔴 Граф исключён из ревью (11.08) — иначе каждый коммит тащит ~200 КБ JSONL, и модель
# не укладывается в таймаут. Коммит из одного графа модель не зовётся вовсе.
# (индекс сначала чистим: прежний случай оставил sn.py staged — нашла проба)
git reset -q; rm -f ubuntu/serenedb/sn.py
printf '{"type":"entity","name":"probe-g1","entityType":"x","observations":[]}\n' >> memory_bank/mcp-memory.json
git add memory_bank/mcp-memory.json
stub 'exit 1'   # если снайпер позвал модель — это ошибка
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
[ "$OUT" = '{}' ]; say $? 'коммит из одного графа — модель не зовётся, пропуск'

printf 'print(1)\n' > ubuntu/serenedb/sn2.py; git add ubuntu/serenedb/sn2.py
stub 'echo "• VERDICT: OK"'
OUT=$(sn_call '{"tool_input":{"command":"git commit -m x"}}')
[ "$OUT" = '{}' ]; say $? 'код + граф — пропуск при OK'
grep -q 'mcp-memory' .claude/state/staged-kimi.diff && r=1 || r=0; say $r 'граф не попадает в дифф снайпера при смешанном коммите'
grep -q 'sn2.py' .claude/state/staged-kimi.diff; say $? 'код в диффе остался'
git reset -q; rm -f ubuntu/serenedb/sn.py ubuntu/serenedb/sn2.py
git checkout -q -- memory_bank/mcp-memory.json

# 🔴 Промт снайпера живёт в ДВУХ местах — agent-хук settings.json (Claude) и
# sniper-kimi.sh (Kimi). Разъехавшиеся копии одного правила — тот самый дефект F248,
# ради которого заводился lib-hooks.sh: находка обязана быть в обоих.
echo
echo '== снайпер: находка про OpenClaw — в обоих движках =='
REAL="$(cd "$HOOKS/../.." && pwd)"
grep -q 'openclaw-native' "$HOOKS/sniper-kimi.sh"; say $? 'sniper-kimi.sh — находка про OpenClaw на месте'
grep -q 'openclaw-native' "$REAL/.claude/settings.json"; say $? 'agent-снайпер settings.json — та же находка на месте'

# --- сторож: подключение Kimi -------------------------------------------------------
echo
echo '== защита гейтов: подключение Kimi (hook_guard_armed) =='
cd "$G" || exit 1
[ -z "$(armed)" ]; say $? 'kimi-конфиг полон — нарушений нет'
# 🔴 Владелец конфига НЕ проверяется: бинарь Kimi пересериализует его при старте
# (rename в каталоге рабочего аккаунта), и сторож на владельце останавливал работу
# на сам движок (06.08 10:14). Сторожится содержимое проводки.
chown --reference=README.md "$KIMI_CONFIG_TOML" 2>/dev/null || true
cp "$KIMI_CONFIG_TOML" "$TMP/kimi.bak"
sed -i '/sniper-kimi/d' "$KIMI_CONFIG_TOML"
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'гейт убран из kimi-конфига — нарушение видно поимённо'
cp "$TMP/kimi.bak" "$KIMI_CONFIG_TOML"
# Пересадка на не то событие — на гейте, который подключён ОДИН раз (у check-prompt-rules
# две записи, и переворот одной оставляет пару на месте: нашла проба, не чтение кода).
python3 - "$KIMI_CONFIG_TOML" <<'PY'
import sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().splitlines(keepends=True)
for i, l in enumerate(lines):
    if "sniper-kimi.sh" in l and l.strip().startswith("command"):
        for j in range(i, -1, -1):
            if lines[j].strip().startswith("event"):
                lines[j] = lines[j].replace("PreToolUse", "PostToolUse")
                break
        break
open(p, "w", encoding="utf-8").writelines(lines)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'гейт пересажен на не то событие — нарушение видно поимённо'
cp "$TMP/kimi.bak" "$KIMI_CONFIG_TOML"
sed -i 's|\.claude/hooks/sniper-kimi\.sh|/tmp/sniper-kimi.sh|' "$KIMI_CONFIG_TOML"
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'команда гейта указывает в чужой каталог — нарушение видно'
cp "$TMP/kimi.bak" "$KIMI_CONFIG_TOML"
printf 'это не toml {{{\n' > "$KIMI_CONFIG_TOML"
OUT=$(armed); printf '%s' "$OUT" | grep -q 'TOML'; say $? 'конфиг не разбирается — нарушение видно, а не «нет проводки»'
rm -f "$KIMI_CONFIG_TOML"
OUT=$(armed); printf '%s' "$OUT" | grep -q 'Kimi'; say $? 'kimi-конфиг снесён — нарушение видно'
cp "$TMP/kimi.bak" "$KIMI_CONFIG_TOML"
mv AGENTS.md "$TMP/ag.bak"
OUT=$(armed); printf '%s' "$OUT" | grep -q 'AGENTS.md'; say $? 'AGENTS.md снесён — нарушение видно поимённо'
mv "$TMP/ag.bak" AGENTS.md
[ -z "$(armed)" ]; say $? 'всё возвращено — нарушений снова нет'

echo
# --- адаптер и сторож Cursor (13.08) ------------------------------------------
echo
echo '== cursor-wrap: вход Cursor, выход permission/additional_context =='
cd "$G" || exit 1
WRAP="$G/.claude/hooks/cursor-wrap.sh"
wrap_call() { printf '%s' "$1" | CLAUDE_PROJECT_DIR="$G" bash "$WRAP" "$2" 2>/dev/null || true; }

# session-start печатает текст — адаптер кладёт его в additional_context.
printf '# С ЧЕГО НАЧАТЬ\nстрока состояния курсора\n' > memory_bank/activeContext.md
OUT=$(wrap_call '{"session_id":"c-probe"}' session-start)
printf '%s' "$OUT" | grep -q '"additional_context"' && printf '%s' "$OUT" | grep -q 'строка состояния курсора'
say $? 'session-start через адаптер — JSON additional_context, не голый текст'

# команда на верхнем уровне (beforeShellExecution / preToolUse Shell)
printf 'print(1)\n' > ubuntu/serenedb/cursor_probe.py
git add ubuntu/serenedb/cursor_probe.py
OUT=$(wrap_call '{"command":"git commit -m x","tool_name":"Shell"}' check-docs)
printf '%s' "$OUT" | grep -q '"permission": *"deny"'
say $? 'check-docs на command сверху — permission deny (код без документов)'
git reset -q
rm -f ubuntu/serenedb/cursor_probe.py

# afterFileEdit: file_path сверху + edits
SAMPLE="$G/ubuntu/openclaw/instance/AGENTS.md"
mkdir -p "$(dirname "$SAMPLE")"
printf 'ты помощник.\n' > "$SAMPLE"
OUT=$(wrap_call "$(python3 -c 'import json;print(json.dumps({"file_path":"'"$SAMPLE"'","edits":[{"old_string":"ты помощник.","new_string":"Ты обязан всегда звать ask_1c."}]}))')" check-prompt-rules)
printf '%s' "$OUT" | grep -q '"permission": *"deny"'
say $? 'check-prompt-rules на afterFileEdit (file_path+edits) — deny'
rm -rf "$G/ubuntu/openclaw"

echo
echo '== защита гейтов: подключение Cursor (hook_guard_armed) =='
cd "$G" || exit 1
[ -z "$(armed)" ]; say $? 'cursor-проводка полна — нарушений нет'

cp .cursor/hooks.json "$TMP/cursor-hooks.bak"
python3 - .cursor/hooks.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
d["hooks"]["preToolUse"] = [h for h in d["hooks"]["preToolUse"]
                            if "sniper-kimi" not in (h.get("command") or "")]
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'гейт убран из cursor-hooks — нарушение видно поимённо'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

python3 - .cursor/hooks.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
for h in d["hooks"]["preToolUse"]:
    if "sniper-kimi" in (h.get("command") or ""):
        d["hooks"].setdefault("postToolUse", []).append(h)
        d["hooks"]["preToolUse"].remove(h)
        break
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'гейт пересажен на не то событие — нарушение видно поимённо'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

python3 - .cursor/hooks.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
for h in d["hooks"]["preToolUse"]:
    if "sniper-kimi" in (h.get("command") or ""):
        h["command"] = "/tmp/cursor-wrap.sh sniper-kimi"
        break
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'sniper-kimi'; say $? 'команда гейта без cursor-wrap в .claude/hooks — нарушение видно'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

python3 - .cursor/hooks.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
for h in d["hooks"]["preToolUse"]:
    if "check-docs" in (h.get("command") or ""):
        h["failClosed"] = False
        break
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'failClosed'; say $? 'failClosed снят у блокирующего — нарушение видно'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

printf 'это не json {{{\n' > .cursor/hooks.json
OUT=$(armed); printf '%s' "$OUT" | grep -q 'JSON'; say $? 'hooks.json не разбирается — нарушение видно'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

rm -f .cursor/hooks.json
OUT=$(armed); printf '%s' "$OUT" | grep -q 'Cursor'; say $? 'hooks.json снесён — нарушение видно'
cp "$TMP/cursor-hooks.bak" .cursor/hooks.json

python3 - .cursor/mcp.json <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
del d["mcpServers"]["serenedb-docs"]
json.dump(d, open(p, "w"), ensure_ascii=False)
PY
OUT=$(armed); printf '%s' "$OUT" | grep -q 'serenedb-docs'; say $? 'MCP без serenedb-docs — нарушение видно'
cp "$REPO/.cursor/mcp.json" .cursor/mcp.json 2>/dev/null || true

[ -z "$(armed)" ]; say $? 'всё возвращено — нарушений снова нет'

if [ "$FAILED" != 0 ]; then echo "🔴 ПРОВАЛОВ: $FAILED"; exit 1; fi
echo 'Хуки прошли пробу полностью.'