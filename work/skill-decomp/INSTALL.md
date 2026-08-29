# Установка скилла compound-ask (К8)

Скилл живёт в репозитории: `work/skill-decomp/`. В бой — штатным механизмом
OpenClaw: каталог `<workspace>/skills/compound-ask/` с `SKILL.md` в корне.

Документация: `/usr/lib/node_modules/openclaw/docs/tools/creating-skills.md`
(поля frontmatter, `{baseDir}`), `/usr/lib/node_modules/openclaw/docs/tools/skills.md`
(порядок загрузки, `openclaw skills install`).

## Вариант A — скрипт из репозитория

```bash
bash /srv/1c/work/skill-decomp/scripts/install.sh \
  --workspace /home/undebot/.openclaw/workspace
```

Скрипт копирует SKILL.md, references/, examples/, table.py (без test/fixtures).
Тесты в бой не нужны.

## Вариант B — rsync вручную

```bash
rsync -a --delete \
  --exclude 'test_*.py' --exclude 'fixtures/' --exclude '__pycache__' \
  /srv/1c/work/skill-decomp/ \
  /home/undebot/.openclaw/workspace/skills/compound-ask/
```

## Вариант C — openclaw skills install (локальный путь)

Из workspace агента, если CLI видит репозиторий:

```bash
cd /home/undebot/.openclaw/workspace
openclaw skills install /srv/1c/work/skill-decomp --as compound-ask
```

## Проверка

```bash
openclaw skills list | grep compound-ask
```

Новая сессия агента: `/new` в чате или `openclaw gateway restart`.

## Gating

Скилл не требует отдельных env: зависит только от MCP `ask_1c`, уже
подключённого в контуре бота. `metadata.openclaw.requires` не задан —
скилл виден, когда лежит в `skills/` и не отфильтрован allowlist.

## Отличие от ubuntu/openclaw/skills/ask-decomposer/

| | `compound-ask` (этот каталог) | `ask-decomposer` (эталон с арифметикой) |
|---|---|---|
| Сводка | prose из таблицы ответов, вердикт без diff | `decomposer.py` печатает разность |
| Вызов ask | MCP `ask_1c` (инструкция агенту) | HTTP + CLI |
| Статус | К8, ставится в бота | эталон в репо, не в бою |

В бой для К8 ставится **compound-ask**, не ask-decomposer.
