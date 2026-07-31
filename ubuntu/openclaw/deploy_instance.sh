#!/bin/bash
# ВЫКАТКА ПЕРСОНЫ И ОКРУЖЕНИЯ БОТА.
#
# 🔴 ЗАЧЕМ ОТДЕЛЬНЫЙ ШАГ. [замер 31.07] персона правилась в репозитории, а бот отвечал по
# копии в своей рабочей папке от 30.07: копирование было записано в руководстве как ручной
# шаг, и его никто не делал. То есть правки промта не влияли НИ НА ОДИН ответ, и это не
# было видно ниоткуда. Ручной шаг при установке — дефект по п. 14; здесь он ещё и делал
# бессмысленной всю работу над промтом.
#
# 🔴 ЧУЖИЕ СТАРТОВЫЕ ЗАГОТОВКИ УДАЛЯЮТСЯ, А НЕ УГОВАРИВАЮТСЯ. Движок кладёт в новую
# рабочую папку свои шаблоны (`BOOTSTRAP.md`, `SOUL.md`, `IDENTITY.md`, `TOOLS.md`,
# `USER.md`) и вставляет их в системный промт КАЖДЫЙ ХОД — 6 124 символа. Часть прямо
# противоречит контракту: `SOUL.md` велит «come back with answers, not questions», тогда
# как указание владельца 30.07 — «лучше 1, 2, 3 раза уточнить, чем дать не то»; `TOOLS.md`
# описывает камеры и домашние серверы, которых нет. А `BOOTSTRAP.md` без отметки
# `setupCompletedAt` заставляет движок требовать «сначала выполни знакомство», и половина
# наших «главных правил» была написана как оборона от него.
# Правило проекта: запреты держатся КОДОМ, а не промтом. Удаление файла — код; просьба
# модели его не слушаться — промт, то есть не работает.
set -u
cd "$(dirname "$0")" || exit 1

BOTUSER="${OPENCLAW_USER:-undebot}"
WS="${OPENCLAW_WORKSPACE:-/home/$BOTUSER/.openclaw/workspace}"
[ -d "$WS" ] || { echo "выкатка: рабочей папки $WS нет — шаг пропущен"; exit 0; }

BAK="$WS/.replaced-by-deploy"
sudo -u "$BOTUSER" -H mkdir -p "$BAK"

# Персона — из репозитория, всегда.
sudo -u "$BOTUSER" -H cp instance/AGENTS.md "$WS/AGENTS.md"
echo "выкатка: AGENTS.md ($(wc -c < instance/AGENTS.md) символов)"

# 🔴 УДАЛЕНИЕ НЕ РАБОТАЕТ — ДВИЖОК КЛАДЁТ ФАЙЛ ОБРАТНО. [замер 31.07] `TOOLS.md` убрали в
# 04:17:03, движок положил идентичную копию в 04:17:21 — через 18 секунд. Удаление файла,
# который создаёт чужой код, это не запрет кодом, а гонка, и я её проиграл.
# Поэтому заготовки не стираются, а ПЕРЕЗАПИСЫВАЮТСЯ пустышкой: существующий файл движок
# не трогает, значит содержимое остаётся нашим. Оригинал сохраняется рядом.
for f in BOOTSTRAP.md SOUL.md IDENTITY.md TOOLS.md USER.md; do
  [ -f "$WS/$f" ] || continue
  if [ ! -f "$BAK/$f" ]; then
    sudo -u "$BOTUSER" -H cp "$WS/$f" "$BAK/$f"
  fi
  # Пустой файл движок считает заполненным и заново не заводит; в промт уходит одна строка
  # вместо 6 124 символов чужих указаний.
  printf '%s\n' "(не используется — см. instance/AGENTS.md)" \
    | sudo -u "$BOTUSER" -H tee "$WS/$f" >/dev/null
  echo "выкатка: заготовка $f опустошена"
done

# Мост MCP — туда же, куда и персона: он тоже читается чужим процессом.
# [замер 31.07] в /opt лежала копия от 30.07, и правки моста не влияли ни на один ответ.
MCPDIR="${OPENCLAW_MCP_DIR:-/opt/openclaw-mcp}"
if [ -d "$MCPDIR" ]; then
  cp mcp_ask.py "$MCPDIR/mcp_ask.py"
  echo "выкатка: mcp_ask.py -> $MCPDIR"
  systemctl restart 1c-mcp-ask 2>/dev/null && echo "выкатка: 1c-mcp-ask перезапущен"
fi

# Плагин-гейт: маркеры в нём обязаны совпадать с теми, что шлёт мост.
# Путь ИЩЕТСЯ, а не задаётся: движок ставит плагин в каталог со сгенерированным именем
# (`.../npm/projects/openclaw-braine-verify__…__g-<хеш>/node_modules/openclaw-braine-verify`),
# и хеш меняется при переустановке. Записать его в скрипт значило бы поставить догадку.
PLUGDIR=$(sudo -u "$BOTUSER" -H find "/home/$BOTUSER/.openclaw" -name verify-core.js \
          -printf '%h\n' 2>/dev/null | head -1)
if [ -n "$PLUGDIR" ]; then
  sudo -u "$BOTUSER" -H cp verify-plugin/verify-core.js verify-plugin/index.js "$PLUGDIR/" 2>/dev/null \
    && echo "выкатка: verify-plugin -> $PLUGDIR"
else
  echo "🔴 выкатка: плагин-гейт не найден — маркеры моста и гейта могут разойтись"
fi

# Отметка «настройка завершена»: без неё движок считает рабочую папку незаполненной и
# добавляет в промт раздел «Bootstrap Pending», требующий исполнить BOOTSTRAP.md.
# Время берётся из окружения, если задано, иначе текущее — своих меток мы не выдумываем.
STATE="$WS/openclaw-workspace-state.json"
if [ -f "$STATE" ] && ! grep -q setupCompletedAt "$STATE"; then
  TS="${DEPLOY_TS:-$(date -u +%Y-%m-%dT%H:%M:%S.000Z)}"
  sudo -u "$BOTUSER" -H python3 - "$STATE" "$TS" <<'PY'
import json, sys
p, ts = sys.argv[1], sys.argv[2]
d = json.load(open(p, encoding="utf-8"))
d["setupCompletedAt"] = ts
json.dump(d, open(p, "w", encoding="utf-8"))
PY
  echo "выкатка: проставлена отметка setupCompletedAt"
fi
