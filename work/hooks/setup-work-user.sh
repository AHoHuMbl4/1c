#!/usr/bin/env bash
# Рабочий аккаунт для сессий: всё в проекте — его, кроме ПРАВИЛ.
#
# 🔴 ЗАЧЕМ. До 03.08 сессия шла под root: гейты держались тем, что среда Claude Code
# закрывает `.claude/hooks/`. Это защита одного инструмента, а не системы — из-под root
# любая другая оболочка (`python3`, `sed -i`, чужой скрипт) переписала бы гейт и не
# заметила бы запрета. Права — механизм ниже уровнем: они действуют независимо от того,
# кто и чем правит.
#
# Что остаётся владельцу (root), то есть недоступно рабочему аккаунту на запись:
#   .claude/hooks/         — гейты, библиотека, git-gate.sh, файл люка override.txt
#   .githooks/             — обёртка гейта коммита
#   .claude/settings.json  — подключение гейтов к сессии
#   CLAUDE.md, TARGET.md   — правила и контракт
#   memory_bank/owner-memory/ — решения владельца, пересмотру не подлежат
# Всё прочее — код, документы, память проекта, work/, .git — рабочему аккаунту:
# документы правятся в тех же сессиях, что и код (иначе документ отстаёт от кода, а это
# главная поломка проекта).
#
# 🔴 Каталоги-родители правил принадлежат владельцу, а не рабочему аккаунту. Право на
# КАТАЛОГ позволяет удалить или переименовать файл, которым не владеешь: `CLAUDE.md` нельзя
# было бы изменить, но можно было бы снести и положить свой. Sticky-бит здесь НЕ помогает —
# он не ограничивает владельца каталога, и проба это показала, снеся правила. Immutable
# (`chattr +i`) в этом окружении недоступен. Остаётся владение.
#
# Запуск (от root):  bash work/hooks/setup-work-user.sh [имя-аккаунта]
# Повторный запуск безопасен.
set -uo pipefail
USER_NAME="${1:-claudedev}"
cd "$(git rev-parse --show-toplevel)" || exit 1
ROOT="$(pwd)"

[ "$(id -u)" = 0 ] || { echo "Нужны права root: скрипт меняет владельцев файлов."; exit 1; }

echo "== 1. аккаунт $USER_NAME =="
if id "$USER_NAME" >/dev/null 2>&1; then
  echo "  уже есть"
else
  useradd -m -s /bin/bash "$USER_NAME" && echo "  создан"
  # Пароля нет и вход по паролю невозможен: заходить `su - <имя>` от root или по ключу.
  # Пустой пароль (`passwd -d`) не ставим намеренно — он разрешает вход кому угодно.
  passwd -l "$USER_NAME" >/dev/null 2>&1 && echo "  пароль заблокирован (вход: su - $USER_NAME или по ключу)"
fi

echo "== 2. проект — рабочему аккаунту =="
chown -R "$USER_NAME":"$USER_NAME" "$ROOT"
echo "  chown -R $USER_NAME $ROOT"

echo "== 3. правила — обратно владельцу =="
PROTECTED_DIRS=".claude/hooks .githooks memory_bank/owner-memory"
PROTECTED_FILES=".claude/settings.json CLAUDE.md TARGET.md"
for d in $PROTECTED_DIRS; do
  [ -d "$d" ] || { echo "  ⚠ нет каталога $d"; continue; }
  chown -R root:root "$d"
  chmod 755 "$d"
  find "$d" -type f -name '*.sh' -exec chmod 755 {} +
  find "$d" -type f ! -name '*.sh' -exec chmod 644 {} +
  # 🔴 pre-commit без расширения — тоже исполняемый файл, иначе git молча не зовёт гейт.
  [ -f "$d/pre-commit" ] && chmod 755 "$d/pre-commit"
  echo "  root:root $d (каталог 755 — рабочий не создаёт и не удаляет здесь ничего)"
done
for f in $PROTECTED_FILES; do
  [ -f "$f" ] || { echo "  ⚠ нет файла $f"; continue; }
  chown root:root "$f"; chmod 644 "$f"
  echo "  root:root $f"
done

echo "== 4. родители правил — владельцу =="
# 🔴 STICKY НЕ ПОМОГАЕТ, И ЭТО ПРОВЕРЕНО ПРОБОЙ, А НЕ ВЫЧИТАНО. Первая редакция ставила
# `chmod +t` на корень и оставляла его рабочему аккаунту. Проба тут же снесла `CLAUDE.md`:
# sticky запрещает удалять чужие файлы всем, КРОМЕ владельца каталога, — а владельцем и был
# рабочий аккаунт. Значит каталог, где лежат правила, обязан принадлежать владельцу.
# Атрибут immutable закрыл бы вопрос без этого, но в нашем окружении он недоступен
# (проверено: `chattr +i` отбит, «Operation not permitted»).
#
# Цена известна и принята: рабочий аккаунт НЕ создаёт новые файлы в корне и в `.claude/`,
# и git не может переписать файл КОРНЯ (`git checkout -- CHANGELOG.md`, `git pull` с
# изменением корневых файлов) — такие шаги делает владелец. Правка существующих файлов,
# коммит и push работают полностью: это проверено пробами ниже.
for p in "$ROOT" "$ROOT/.claude"; do
  chown root:root "$p"; chmod 755 "$p"
  echo "  root:root $p"
done
# 🔴 memory_bank тоже владельцу — и это тоже показала проба, а не рассуждение. Пока
# каталог принадлежал рабочему аккаунту, `mv memory_bank/owner-memory memory_bank/_x`
# проходил: sticky не запрещает владельцу каталога трогать чужое, а решения владельца,
# которые можно «спрятать» одним переименованием, защищены ровно никак.
# Цена: новые файлы памяти проекта заводит владелец. Правка существующих — свободна.
chown root:root "$ROOT/memory_bank"; chmod 755 "$ROOT/memory_bank"
echo "  root:root memory_bank (owner-memory внутри теперь не переименовать)"

echo "== 4-бис. git для рабочего аккаунта =="
# Корень принадлежит root, а работает другой пользователь — git считает это «dubious
# ownership» и отказывается работать вовсе, пока каталог не назван доверенным.
su -s /bin/bash "$USER_NAME" -c "git config --global --add safe.directory '$ROOT'" 2>/dev/null \
  && echo "  safe.directory прописан"

echo "== 4-тер. окружение Claude Code для рабочего аккаунта =="
# 🔴 Сам Claude Code, плагины и глобальные настройки лежат в доме того, кто их ставил
# (`/root/.local/share/claude`, `/root/.claude/plugins`), а дом root закрыт (700). Рабочий
# аккаунт без переноса не увидит ни harness, ни настроек — то есть «правила настроены»
# оказалось бы верно только для прежнего пользователя.
SRC_HOME="${SUDO_HOME:-/root}"
DST_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
copy_env() { # copy_env <откуда> <куда> <что это>
  [ -e "$1" ] || { echo "  · нет $3 ($1) — пропуск"; return 0; }
  [ -e "$2" ] && { echo "  · $3 уже на месте"; return 0; }
  mkdir -p "$(dirname "$2")"
  cp -a "$1" "$2" && echo "  перенесено: $3"
}
copy_env "$SRC_HOME/.local/share/claude"  "$DST_HOME/.local/share/claude"  "Claude Code"
copy_env "$SRC_HOME/.claude/plugins"      "$DST_HOME/.claude/plugins"      "плагины (harness)"
copy_env "$SRC_HOME/.claude/settings.json" "$DST_HOME/.claude/settings.json" "глобальные настройки"
copy_env "$SRC_HOME/.claude/projects"     "$DST_HOME/.claude/projects"     "память Claude по проекту"
# Кэш npx: без него MCP-сервер графа пришлось бы качать из сети при каждом старте.
copy_env "$SRC_HOME/.npm"                 "$DST_HOME/.npm"                 "кэш npm (MCP memory)"
ver="$(ls "$DST_HOME/.local/share/claude/versions" 2>/dev/null | tail -1)"
if [ -n "$ver" ]; then
  mkdir -p "$DST_HOME/.local/bin"
  ln -sfn "$DST_HOME/.local/share/claude/versions/$ver" "$DST_HOME/.local/bin/claude"
  echo "  claude → $ver"
fi
chown -R "$USER_NAME":"$USER_NAME" "$DST_HOME/.local" "$DST_HOME/.claude" "$DST_HOME/.npm" 2>/dev/null
# 🔴 Учётные данные (`.credentials.json`) НЕ переносим: это секрет, и его судьба — решение
# владельца. Либо он копирует файл сам, либо входит заново из-под рабочего аккаунта.
echo "  · .credentials.json намеренно не тронут — вход выполняет владелец"

echo "== 5. журнал хуков — только дозапись =="
# Обход обязан оставлять след, а след не должен стираться тем, кого он изобличает.
LOG="$ROOT/.claude/hooks.log"
[ -f "$LOG" ] || : > "$LOG"
chown "$USER_NAME":"$USER_NAME" "$LOG"; chmod 644 "$LOG"
if chattr +a "$LOG" 2>/dev/null; then
  echo "  chattr +a (только дозапись, стереть нельзя даже владельцу файла)"
else
  echo "  ⚠ chattr +a не поддержан на этой ФС — журнал можно стереть, это остаточный риск"
fi

echo
echo "== 6. проверка от имени $USER_NAME =="
# 🔴 Проба, которая ломает то, что проверяет, — сама себе дефект: первая редакция
# действительно СНЕСЛА `CLAUDE.md` строкой «rm -f CLAUDE.md», и обнаружилось это лишь тем,
# что следующая проверка не нашла файл. Восстанавливать из git нельзя: половина
# защищённого состояния (установленные гейты, правка settings.json) в HEAD не совпадает с
# тем, что стоит сейчас, и «починка» затёрла бы рабочее. Поэтому снимок делается ДО проб и
# возвращается после каждой.
SNAP="$(mktemp -d)" || { echo "Не создан временный каталог — пробы не запускаю: без снимка они разрушительны."; exit 1; }
PROTECTED_PATHS=".claude/hooks .githooks .claude/settings.json CLAUDE.md TARGET.md memory_bank/owner-memory"
for p in $PROTECTED_PATHS; do
  [ -e "$ROOT/$p" ] || continue
  mkdir -p "$SNAP/$(dirname "$p")"
  cp -a "$ROOT/$p" "$SNAP/$p" || { echo "Снимок $p не снялся — пробы не запускаю."; exit 1; }
done
# 🔴 Порядок «сначала положить, потом убрать» — не придирка: обрыв (Ctrl-C, SIGTERM) между
# `rm -rf` и `cp -a` оставил бы правила стёртыми, а снимок — единственной копией. Поэтому
# новое кладётся рядом и въезжает одним `mv`, а прежнее сносится уже после.
restore_protected() {
  local p tmp
  for p in $PROTECTED_PATHS; do
    [ -e "$SNAP/$p" ] || continue
    # Промежуточная копия готовится в снимке, а не рядом с целью: наполовину
    # восстановленное правило не должно ни секунды лежать там, где его видит и может
    # подхватить работающая сессия.
    tmp="$SNAP/.restoring"
    rm -rf "$tmp"
    if cp -a "$SNAP/$p" "$tmp"; then
      rm -rf "${ROOT:?}/$p" && mv "$tmp" "$ROOT/$p" || echo "  🔴 не удалось вернуть $p — снимок в $SNAP"
    else
      echo "  🔴 не удалось снять копию для возврата $p — снимок в $SNAP"
      rm -rf "$tmp"
    fi
  done
  # Хвост от пробы «спрятать память владельца»: если переименование ВСЁ ЖЕ прошло, копия
  # осталась бы лежать рядом. Убираем только наш собственный след, ничего чужого.
  [ -d "$ROOT/memory_bank/_x" ] && rm -rf "$ROOT/memory_bank/_x"
  return 0
}
# Возврат вешается на любой выход, включая обрыв: недоделанная проба не должна оставить
# проект без правил.
trap 'restore_protected; rm -rf "$SNAP"' EXIT INT TERM

probe() { # probe <ожидание: deny|allow> <описание> <команда>
  local want="$1" name="$2" cmd="$3" out rc
  out=$(su -s /bin/bash "$USER_NAME" -c "cd '$ROOT' && $cmd" 2>&1); rc=$?
  restore_protected
  if [ "$want" = deny ]; then
    [ "$rc" -ne 0 ] && echo "  OK   нельзя: $name" || { echo "  🔴 МОЖНО (а не должно): $name"; FAIL=1; }
  else
    [ "$rc" -eq 0 ] && echo "  OK   можно: $name" || { echo "  🔴 НЕЛЬЗЯ (а должно): $name — $out"; FAIL=1; }
  fi
}
FAIL=0
probe deny  'править библиотеку хуков'      'printf x >> .claude/hooks/lib-hooks.sh'
probe deny  'удалить гейт'                  'rm -f .claude/hooks/check-docs.sh'
probe deny  'подложить свой хук'            'printf x > .claude/hooks/evil.sh'
probe deny  'открыть себе люк'              'printf "check-docs сам себе" > .claude/hooks/override.txt'
probe deny  'править обёртку гейта коммита' 'printf x >> .githooks/pre-commit'
probe deny  'править настройки сессии'      'printf x >> .claude/settings.json'
probe deny  'править правила'               'printf x >> CLAUDE.md'
probe deny  'править контракт'              'printf x >> TARGET.md'
probe deny  'снести правила и подложить свои' 'rm -f CLAUDE.md'
probe deny  'править память владельца'      'printf x >> memory_bank/owner-memory/project-serenedb-ivf-blocked.md'
probe deny  'снести каталог гейтов'          'rm -rf .claude/hooks'
probe deny  'спрятать память владельца'      'mv memory_bank/owner-memory memory_bank/_x'
probe allow 'править код'                   'printf "" >> ubuntu/serenedb/serene_ask.py'
probe allow 'править документы'             'printf "" >> CHANGELOG.md'
probe allow 'править состояние работ'       'printf "" >> memory_bank/activeContext.md'
probe allow 'создать файл в work/'          'touch work/.probe && rm -f work/.probe'
probe allow 'читать правила'                'head -1 CLAUDE.md >/dev/null'
probe allow 'читать хуки'                   'head -1 .claude/hooks/lib-hooks.sh >/dev/null'
probe allow 'работать с git'                'git status --porcelain >/dev/null'
probe allow 'дозаписать журнал хуков'       'printf "" >> .claude/hooks.log'
probe allow 'писать в .claude/state'        'touch .claude/state/.probe && rm -f .claude/state/.probe'

echo
echo "  известные ограничения (так и задумано, не дефект):"
su -s /bin/bash "$USER_NAME" -c "cd '$ROOT' && touch _probe" 2>/dev/null \
  && { echo "  🔴 новый файл в КОРНЕ создаётся — значит корень не защищён"; rm -f "$ROOT/_probe"; FAIL=1; } \
  || echo "  · новый файл в корне репозитория — только через владельца"
echo "  · git checkout/pull, переписывающий файл КОРНЯ, — только через владельца"
echo "  · новый файл в memory_bank/ — только через владельца (правка существующих свободна)"

echo
if [ "$FAIL" = 0 ]; then
  echo "Права разложены и проверены. Дальше сессии запускать от $USER_NAME:"
  echo "  su - $USER_NAME -c 'cd $ROOT && claude'"
else
  echo "🔴 Проверка нашла расхождение — разбирать до конца, иначе защита неполная."
fi
exit "$FAIL"
