# План: гейты проекта в Cursor — как у Claude Code и Kimi Code

Заведён 13.08. Третий движок тех же правил. Claude Code и Kimi Code не трогаем:
их `settings.json` и `kimi-config.toml` не меняются. Cursor получает свою проводку,
как Kimi получил свою 06.08.

Мерило: запрет держится кодом, а не промтом. Промт модель игнорирует
(`[замер 03.08]`, `HOW_NOT_TO §1.51`, указание владельца «это супер важно»).

---

## 0. Перепроверка (до внедрения)

Снято в этой же сессии Cursor 13.08 06:03–06:10, не по доке.

| Что проверили | Факт |
|---|---|
| Текст `CLAUDE.md` / `AGENTS.md` | оба вброшены в контекст как правила воркспейса |
| Жёсткая ссылка `AGENTS.md` → `CLAUDE.md` | **сломана**: разные иноды, `AGENTS.md` отстал с 06.08 |
| Хуки из `.claude/settings.json` | `SessionStart` **звался** (`hooks.log` 06:03:58) |
| Вброс «С ЧЕГО НАЧАТЬ» в контекст | хук отработал, в стартовый контекст **не попал** (как у Kimi) |
| `PreToolUse` matcher `Bash` на команды Cursor | **не звался**: после десятков `Shell` в этой сессии в журнале только session-start |
| MCP `serenedb-docs` и `memory` | **нет** — Cursor не читает корневой `.mcp.json` |
| Агенты `.claude/agents/` | видны в Task |
| Гейт git | `core.hooksPath=.githooks`, рассчитан на Cursor, жив |
| Аккаунт сессии | **root**, каталог `.claude/hooks/` записываемый — защита правами не действует |
| Сторож `hook_guard_armed` | знает Claude и Kimi, про Cursor молчит |
| Совместимость «Claude hooks в Cursor» | дока обещает маппинг `Bash`→`Shell`; **живой замер это опроверг** |

Вывод перепроверки: опираться на third-party загрузку `.claude/settings.json` нельзя.
Нужна своя проводка `.cursor/hooks.json`, как у Kimi — `kimi-config.toml`.
Гейт git остаётся последним рубежом и уже работает.

---

## 1. Устройство (решение разработки)

Тот же приём, что для Kimi. Скрипты гейтов одни, в защищённом `.claude/hooks/`.
У каждого движка — своя тонкая проводка, которую сторож сверяет по содержимому.

```
Claude  → .claude/settings.json          (не трогаем)
Kimi    → ~/.kimi-code/config.toml       (не трогаем)
Cursor  → .cursor/hooks.json             (новое)
           + .cursor/mcp.json            (новое)
           + cursor-wrap.sh              (адаптер входа/выхода)
git     → .githooks → git-gate.sh        (уже ловит Cursor)
```

`cursor-wrap.sh` — единственное новое место, где Cursor отличается. Он:

1. нормализует вход к форме Claude (`tool_input.command`, `file_path`);
2. зовёт тот же `<гейт>.sh`;
3. переводит выход в форму Cursor (`permission: deny` + `additional_context`);
4. на падении блокирующего гейта закрывается (`deny` + код 2), а не пропускает.

Скрипты гейтов, `lib-hooks.sh` (кроме сторожа), `settings.json` и `kimi-config.toml`
не меняют поведение Claude/Kimi.

Почему не «починить матчер Bash в settings.json». Даже если маппинг починят,
`type: agent` снайпера, вброс stdout и поле `StrReplace` останутся чужими.
Вторая проводка дешевле, чем набор оговорок в общем файле. Урок Kimi.

---

## 2. Что именно подключаем

События — нативные имена Cursor. Матчеры — его инструменты, не Claude.

| Событие Cursor | Матчер | Гейт | failClosed |
|---|---|---|---|
| `sessionStart` | — | `session-start` (вброс через `additional_context`) | нет (вброс) |
| `preToolUse` | `Write\|StrReplace` | `check-prompt-rules` | да |
| `preToolUse` | `Shell` | `prepare-diff`, `check-gates`, `check-sql-docs`, `check-prompt-rules`, `check-diff`, `check-docs`, `check-active-size`, `check-graph-fresh`, `check-golden`, `sniper-kimi` | да |
| `postToolUse` | `Write\|StrReplace` | `count-edits`, `check-write`, `check-deps` | нет (вброс) |
| `postToolUse` | `Shell` | `check-deps` | нет |

Снайпер — существующий `sniper-kimi.sh` (свой дифф, параллельный запуск безопасен).
У Cursor нет `type: agent`; свой CLI модели не пишем. Бинарь `kimi` у `claudedev` уже есть.

`beforeSubmitPrompt` для вброса **не годится**: схема события — только `continue` /
`user_message`, `session_id` во входе нет. Вброс — `sessionStart` + JSON
`additional_context` (поле из доки Cursor).

MCP: `.cursor/mcp.json` — те же `serenedb-docs` и `memory`, что в `.mcp.json`.
Cursor корневой `.mcp.json` не читает (как Kimi 0.33 — живой замер 06.08).

---

## 3. Чтобы из сессии под `claudedev` нельзя было обойти

Как сейчас у Claude/Kimi, правами и сторожем, не промтом.

1. Сессия Cursor запускается **под `claudedev`**, не под root
   (`su - claudedev -c 'cd /srv/1c && …'`). Эта сессия — root, это дефект запуска,
   не проводки.
2. `.cursor/hooks.json` и `.cursor/mcp.json` — файлы правил: `root:root` 644,
   в списке `setup-work-user.sh` рядом с `settings.json`.
3. Логика — в `.claude/hooks/` (уже закрыт). Обёртка без логики, как `.githooks/pre-commit`.
4. `hook_guard_armed` сверяет **содержимое** `.cursor/hooks.json`: каждый гейт
   подключён к `cursor-wrap.sh <гейт>` в защищённом каталоге, на правильном событии,
   блокирующие — с `failClosed: true`. Снятие, пересадка, чужой путь — стоп коммита.
5. Люк по-прежнему только `.claude/hooks/override.txt` (владелец). Пока не пуст —
   git-гейт коммит не пропускает.
6. `AGENTS.md` снова жёсткая ссылка на `CLAUDE.md` (`install-gates.sh` пересоздаёт,
   если иноды разъехались).

Осознанный обход один: `git commit --no-verify`. Он виден в истории. Тихого обхода нет.

---

## 4. Что остаётся за владельцем (эту сессию под root это не закрывает)

- Запускать Cursor от `claudedev`, когда проводка встанет.
- При необходимости перенести бинарь Cursor в дом рабочего аккаунта
  (как Claude Code в `setup-work-user.sh` шаг 4-тер).
- Workspace должен быть trusted — иначе проектные хуки Cursor не зовутся
  (дока Cursor). Проверка: строка в `.claude/hooks.log` после команды в сессии.

---

## 5. Проба (без этого шаг не закончен)

Оффлайн, в `test-hooks.sh`, без сервера и модели:

- адаптер: вход Cursor (`command` сверху, `StrReplace`/`file_path` сверху, `edits`)
  даёт тот же `deny`, что Claude-форма;
- вброс `session-start` через адаптер — JSON с `additional_context`, не голый текст;
- сторож: нет файла / гейт убран / пересажен / чужой путь / нет `failClosed` —
  нарушение поимённо;
- прежние пробы Claude и Kimi зелёные (не сломали).

Живой замер в сессии Cursor: команда или правка → строка гейта в `.claude/hooks.log`.
Хук, которого нет в журнале, не существует (`HOW_NOT_TO §1.42`).

---

## 6. Документы и граф

Тем же заходом: `CHANGELOG`, `CLAUDE.md` (секция третьего движка, как у Kimi),
`MAP.md`, `HOW_NOT_TO` (урок «совместимость без строки в журнале»),
`activeContext.md`, сущности графа `.cursor/hooks.json`, `cursor-wrap.sh`,
`.cursor/mcp.json`.

---

## 7. Внедрено (13.08)

Сделано в том же заходе, что и план. Claude `settings.json` и Kimi `kimi-config.toml`
не менялись.

| Что | Где |
|---|---|
| адаптер | `work/hooks/cursor-wrap.sh` → `.claude/hooks/cursor-wrap.sh` |
| проводка | `.cursor/hooks.json` (root:root 644) |
| MCP | `.cursor/mcp.json` (те же serenedb-docs и memory) |
| сторож | `hook_guard_armed` в `lib-hooks.sh` |
| проба | `test-hooks.sh` — адаптер + сторож; прежние Claude/Kimi зелёные |
| права | `install-gates.sh` шаг 3-кват; `setup-work-user.sh` (владелец) |
| жёсткая ссылка | `ln -f CLAUDE.md AGENTS.md` (иноды снова одни) |

`[замер]` оффлайн: `bash work/hooks/test-hooks.sh` код 0, включая все новые случаи Cursor.
`[замер]` живо: после появления hooks.json команда Shell дала `prepare-diff` и
`check-gates` в `.claude/hooks.log` (06:24:01); до этого на Shell их не было.

Осталось владельцу: `bash work/hooks/setup-work-user.sh` и запуск Cursor от `claudedev`.

