#!/usr/bin/env bash
# Установка гейтов. Запускает ВЛАДЕЛЕЦ — из сессии этого сделать нельзя: каталог
# `.claude/hooks/` среда закрывает на запись даже из оболочки, и это не помеха, а опора
# всей конструкции (см. `.claude/hooks/git-gate.sh`).
#
# Запуск:  bash work/hooks/install-gates.sh
#
# Что делает:
#   1. ставит все гейты из work/hooks/ в .claude/hooks/ (755);
#   2. подключает check-gates.sh в .claude/settings.json, если его там ещё нет;
#   3. включает core.hooksPath=.githooks;
#   4. прогоняет пробу и печатает итог.
# Повторный запуск безопасен: каждый шаг проверяет состояние, а не делает вслепую.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1
SRC="work/hooks"
DST=".claude/hooks"

echo "== 1. гейты =="
for f in "$SRC"/*.sh; do
  b="$(basename "$f")"
  [ "$b" = "install-gates.sh" ] && continue
  install -m 755 "$f" "$DST/$b" && echo "  поставлен $b"
done

echo "== 1-бис. обёртка гейта коммита =="
# 🔴 Обёртка ставится ПОСЛЕ гейтов и только вместе с ними: тонкая обёртка без
# .claude/hooks/git-gate.sh останавливает вообще любой коммит (exec несуществующего файла).
# Порядок здесь — не стиль, а условие того, что репозиторий остаётся рабочим.
if [ -x "$DST/git-gate.sh" ]; then
  install -m 755 "$SRC/pre-commit.thin" .githooks/pre-commit && echo "  .githooks/pre-commit — тонкая обёртка"
  # Второй заход: проверки, закрываемые пометкой в сообщении. В pre-commit сообщения
  # ещё нет (man githooks), поэтому без этой обёртки «Доки:» и «Числа:» не видны.
  install -m 755 "$SRC/commit-msg.thin" .githooks/commit-msg && echo "  .githooks/commit-msg — тонкая обёртка"
else
  echo "  🔴 git-gate.sh не поставился — обёртку не трогаю, прежний гейт остаётся рабочим"
fi

echo "== 2. подключение в settings.json =="
python3 - <<'PY'
import json

p = ".claude/settings.json"
d = json.load(open(p, encoding="utf-8"))
pre = d.setdefault("hooks", {}).setdefault("PreToolUse", [])
bash = next((b for b in pre if b.get("matcher") == "Bash"), None)
if bash is None:
    bash = {"matcher": "Bash", "hooks": []}
    pre.append(bash)

tpl = ('"${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}'
       '/.claude/hooks/%s.sh"')
want = [("check-gates", 15, "Проверка: гейты не разоружены"),
        # 🔴 Подавальщик диффа обязан стоять В ЦЕПОЧКЕ РАНЬШЕ снайпера-агента: тот читает
        # уже готовый файл вместо того, чтобы лезть в оболочку, которой ему могут не дать.
        ("prepare-diff", 15, "Дифф подан снайперу")]
for name, timeout, msg in want:
    if any(name in h.get("command", "") for h in bash["hooks"]):
        print("  уже подключён:", name)
        continue
    bash["hooks"].insert(0, {"type": "command", "command": tpl % name,
                             "timeout": timeout, "statusMessage": msg})
    print("  подключён:", name)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY

echo "== 3. гейт коммита =="
cur="$(git config core.hooksPath 2>/dev/null)"
if [ "$cur" != ".githooks" ]; then
  git config core.hooksPath .githooks && echo "  core.hooksPath = .githooks"
else
  echo "  уже включён"
fi

echo "== 3-бис. AGENTS.md для Kimi =="
# 🔴 Kimi читает в контекст AGENTS.md, а не CLAUDE.md (живой замер 06.08: содержимое
# CLAUDE.md в сессию Kimi не попадает, модель признала это сама). Жёсткая ссылка — один
# инод на два имени: правится CLAUDE.md, читают оба движка, рассинхрон невозможен по
# построению. В git ссылка не едет — на новом клоне её создаёт этот же шаг.
if [ ! -e AGENTS.md ]; then
  ln CLAUDE.md AGENTS.md && echo "  AGENTS.md — жёсткая ссылка на CLAUDE.md"
else
  echo "  уже есть"
fi

echo "== 3-тер. конфиг Kimi рабочего аккаунта =="
# 🔴 Канон проводки гейтов Kimi — work/hooks/kimi-config.toml; ставится сюда с root:root
# 644 как ОПОРНАЯ ТОЧКА. Живой файл бинарь Kimi волен пересериализовать (так он
# персистит модель/каталог — замер 06.08): владелец и комментарии теряются, и это НЕ
# нарушение. Сторож сверяет содержимое проводки (пары событие+команда на root-скрипты),
# поэтому перезапись движка коммитов не останавливает, а отсоединение гейта — останавливает.
KHOME="$(getent passwd claudedev 2>/dev/null | cut -d: -f6)"
KDIR="${KHOME:-/home/claudedev}/.kimi-code"
mkdir -p "$KDIR"
install -m 644 -o root -g root "$SRC/kimi-config.toml" "$KDIR/config.toml" \
  && echo "  $KDIR/config.toml — канон из work/hooks/kimi-config.toml"
chown claudedev:claudedev "$KDIR" 2>/dev/null || true
# Бинарь ставится разово руками владельца: install -m 755 <источник> /usr/local/bin/kimi
su -s /bin/bash claudedev -c 'command -v kimi' >/dev/null 2>&1 \
  || echo "  ⚠ kimi не найден в PATH у claudedev — поставь бинарь в /usr/local/bin/kimi"

echo "== 4. проба =="
bash "$DST/test-hooks.sh"
rc=$?

echo
if [ "$rc" = 0 ]; then
  echo "Гейты установлены и проверены. Дальше проверять их состояние не нужно:"
  echo "check-gates.sh и git-gate.sh сверяют защиту сами, на каждом коммите."
else
  echo "🔴 Проба не прошла — гейты установлены, но что-то из них не работает. Разбирать до конца."
fi
exit "$rc"
