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

# Заготовки движка убираются в сторону, а не стираются: они не наши, и разбирать их
# содержимое может понадобиться при обновлении OpenClaw.
for f in BOOTSTRAP.md SOUL.md IDENTITY.md TOOLS.md USER.md; do
  if [ -f "$WS/$f" ]; then
    sudo -u "$BOTUSER" -H mv "$WS/$f" "$BAK/$f"
    echo "выкатка: убрана заготовка $f"
  fi
done

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
