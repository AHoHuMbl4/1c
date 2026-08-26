#!/usr/bin/env bash
# Установка гейтов. Запускает ВЛАДЕЛЕЦ — из сессии этого сделать нельзя: каталог
# `.claude/hooks/` среда закрывает на запись даже из оболочки, и это не помеха, а опора
# всей конструкции (см. `.claude/hooks/git-gate.sh`).
#
# Запуск:  bash work/hooks/install-gates.sh
#
# Что делает:
#   1. ставит все гейты из work/hooks/ в .claude/hooks/ (755);
#   1-тер. канон lib-hooks/test-hooks/check-golden из *.new + check-live-probe;
#   2. подключает check-gates / prepare-diff / check-live-probe в settings.json;
#   3. включает core.hooksPath=.githooks; Kimi; Cursor (+ check-live-probe);
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

echo "== 1-тер. канон lib-hooks/test-hooks/check-golden + check-live-probe =="
# Файлы root:root в work/hooks сессия не переписывает; актуальный канон — *.new.
for pair in "lib-hooks.sh:644" "test-hooks.sh:755" "check-golden.sh:755"; do
  f="${pair%%:*}"; mode="${pair##*:}"
  if [ -f "$SRC/$f.new" ]; then
    install -m "$mode" -o root -g root "$SRC/$f.new" "$SRC/$f"
    install -m "$mode" -o root -g root "$SRC/$f.new" "$DST/$f"
    echo "  поставлен $f из $f.new"
  fi
done
if [ -f "$SRC/check-live-probe.sh" ]; then
  install -m 755 -o root -g root "$SRC/check-live-probe.sh" "$DST/check-live-probe.sh"
  echo "  поставлен check-live-probe.sh"
fi

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
        ("prepare-diff", 15, "Дифф подан снайперу"),
        ("check-live-probe", 20, "Проверка: живая проба okna до коммита serene_ask"),
        ("check-gold-split", 15, "Проверка: код ответа и приёмочный набор не в одном коммите")]
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
elif [ "$(stat -c %i CLAUDE.md 2>/dev/null)" != "$(stat -c %i AGENTS.md 2>/dev/null)" ]; then
  ln -f CLAUDE.md AGENTS.md && echo "  AGENTS.md — ссылка пересоздана (иноды разъехались)"
else
  echo "  уже есть, один инод"
fi

echo "== 3-тер. конфиг Kimi рабочего аккаунта =="
# 🔴 Канон проводки гейтов — work/hooks/kimi-config.toml. Живой ~/.kimi-code/config.toml
# держит провайдеров, oauth и модели владельца; [замер 26.08] полная перезапись каноном
# снесла Foveance :8800 и свой oauth-слот. Поэтому: конфига нет → полный канон;
# конфиг есть → бэкап + влить только [[hooks]] из канона, остальное не трогать.
# Сторож по-прежнему сверяет пары событие+команда на root-скрипты.
KHOME="$(getent passwd claudedev 2>/dev/null | cut -d: -f6)"
KDIR="${KHOME:-/home/claudedev}/.kimi-code"
mkdir -p "$KDIR"
KCFG="$KDIR/config.toml"
KCANON="$SRC/kimi-config.toml"
if [ ! -f "$KCFG" ]; then
  install -m 644 -o claudedev -g claudedev "$KCANON" "$KCFG" \
    && echo "  $KCFG — полный канон (файла не было)"
else
  bak="$KCFG.bak-$(date +%Y%m%d-%H%M%S)"
  cp -a "$KCFG" "$bak" && echo "  бэкап → $bak"
  python3 - "$KCFG" "$KCANON" <<'PY'
import re, sys
from pathlib import Path

live_path, canon_path = Path(sys.argv[1]), Path(sys.argv[2])
live = live_path.read_text(encoding="utf-8")
canon = canon_path.read_text(encoding="utf-8")

# Блок [[hooks]] — только до следующей секции, начинающейся с "[".
# Иначе при hooks посередине живого файла (бинарь Kimi так кладёт) последний
# блок съедал бы [providers]/[models] до EOF ([замер 26.08] на копии).
hook_re = re.compile(r"(?m)^\[\[hooks\]\]\n(?:(?!\[).*\n)*")
canon_hooks = hook_re.findall(canon)
if not canon_hooks:
    print("  🔴 в каноне нет [[hooks]] — конфиг не трогаю", file=sys.stderr)
    sys.exit(1)

# Вырезать все [[hooks]] из живого; провайдеры/oauth/модели — где бы ни стояли — остаются.
body = hook_re.sub("", live)
# Сжать пустые дыры после вырезания из середины.
body = re.sub(r"\n{3,}", "\n\n", body).rstrip() + "\n\n"
merged = body + "".join(canon_hooks)
if not merged.endswith("\n"):
    merged += "\n"
live_path.write_text(merged, encoding="utf-8")

n = len(canon_hooks)
print(f"  {live_path}: влиты {n} блоков [[hooks]] из канона; преамбула живого сохранена")
PY
  chown claudedev:claudedev "$KCFG" 2>/dev/null || true
  chmod 644 "$KCFG" 2>/dev/null || true
fi
chown claudedev:claudedev "$KDIR" 2>/dev/null || true
# Бинарь ставится разово руками владельца: install -m 755 <источник> /usr/local/bin/kimi
su -s /bin/bash claudedev -c 'command -v kimi' >/dev/null 2>&1 \
  || echo "  ⚠ kimi не найден в PATH у claudedev — поставь бинарь в /usr/local/bin/kimi"

echo "== 3-кват. проводка Cursor =="
# Канон — .cursor/hooks.json и .cursor/mcp.json в git. Здесь только права:
# сессия claudedev не должна переписать собственный запрет.
mkdir -p .cursor
if [ -f .cursor/hooks.json ]; then
  chown root:root .cursor .cursor/hooks.json
  chmod 755 .cursor
  chmod 644 .cursor/hooks.json
  echo "  .cursor/hooks.json — root:root 644"
else
  echo "  ⚠ нет .cursor/hooks.json — положи канон в git, иначе сессии Cursor без гейтов на Shell"
fi
if [ -f .cursor/mcp.json ]; then
  chown root:root .cursor/mcp.json
  chmod 644 .cursor/mcp.json
  echo "  .cursor/mcp.json — root:root 644"
else
  echo "  ⚠ нет .cursor/mcp.json — MCP serenedb-docs/memory в Cursor не подключатся"
fi
# cursor-wrap.sh ставится шагом 1 вместе с прочими *.sh

echo "== 3-квин. Cursor: check-live-probe =="
if [ -f "$SRC/cursor-hooks.json.new" ]; then
  install -m 644 -o root -g root "$SRC/cursor-hooks.json.new" .cursor/hooks.json
  echo "  .cursor/hooks.json — из cursor-hooks.json.new"
else
  echo "  ⚠ нет cursor-hooks.json.new — проводка Cursor не обновлена"
fi

echo "== 4. проба =="
bash "$DST/test-hooks.sh"
rc=$?
echo "== 4-бис. проба check-gold-split (И5) =="
if [ -x "$SRC/test-gold-split.sh" ]; then
  bash "$SRC/test-gold-split.sh" || rc=1
else
  echo "  ⚠ нет work/hooks/test-gold-split.sh"
  rc=1
fi

echo
if [ "$rc" = 0 ]; then
  echo "Гейты установлены и проверены. Дальше проверять их состояние не нужно:"
  echo "check-gates.sh и git-gate.sh сверяют защиту сами, на каждом коммите."
else
  echo "🔴 Проба не прошла — гейты установлены, но что-то из них не работает. Разбирать до конца."
fi
exit "$rc"
