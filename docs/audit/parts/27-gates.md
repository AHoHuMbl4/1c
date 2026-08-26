# 27. gates

## Зачем участок нужен
Останавливает `git commit` / выкат и часть правок, если нарушены правила репозитория. Логика в `.claude/hooks/`; `.githooks/pre-commit` и `commit-msg` только `exec` в `git-gate.sh` (`.githooks/pre-commit:21`, `.githooks/commit-msg:11`). Ответ блокирующих гейтов — JSON с `permissionDecision: deny` (`lib-hooks.sh:62-69`); люк — строка в `.claude/hooks/override.txt` (`lib-hooks.sh:92-100`).

## Входы
- stdin: JSON события движка (`tool_input.command`, `file_path`/`path`, `new_string`/`content`/`old_string`, `session_id`); git-gate подставляет fake `{"tool_input":{"command":"git commit"}}` (`git-gate.sh:75`).
- `$1` у git-gate: путь к файлу сообщения коммита из `commit-msg` (`git-gate.sh:68-69` → `HOOK_MSG_FILE`).
- Индекс git: `git diff --cached` / `--name-only` / `--name-status` (пат-спек из команды — `hook_commit_pathspec`, `lib-hooks.sh:477-481`).
- Файлы: `memory_bank/mcp-memory.json`, `memory_bank/activeContext.md`, `.claude/.probe-okna-last-run`, `.claude/hooks/override.txt`, `.claude/settings.json`, `~/.kimi-code/config.toml`, `.cursor/hooks.json`, `.cursor/mcp.json`.

## Порядок работы
1. Движок (Claude/Kimi/Cursor через `cursor-wrap.sh`) зовёт хук на событии; Cursor нормализует поля и переводит `deny`→`permission:deny`+exit 2 (`cursor-wrap.sh:34-118`).
2. `is_git_commit` / `is_deploy` / наличие `file_path` — иначе `{}` и выход.
3. `cd_repo` (`lib-hooks.sh:36-41`); при провале — `hook_ask`/стоп.
4. **git pre-commit** → `git-gate.sh` без `$1`: `hook_guard_armed`; непустой `override.txt`; гейты `check-docs check-graph-fresh check-active-size check-prompt-rules check-live-probe` (`git-gate.sh:68-73`). Любой `permissionDecisionReason` или ненулевой rc → stderr + exit 1 (`git-gate.sh:98-102`). Пропуск: пустой индекс; весь индекс только `windows/odata-setup/` (`git-gate.sh:22-29`).
5. **git commit-msg** → `git-gate.sh "$1"`: те же сторож+люк, затем `check-sql-docs check-diff` (`git-gate.sh:68-70`).
6. Сессионные блокирующие на commit/deploy: `check-gates`, `check-sql-docs`, `check-diff`, `check-docs`, `check-graph-fresh`, `check-active-size`, `check-prompt-rules`, `check-golden` (только deploy), `check-live-probe`, `sniper-kimi` (Kimi); плюс `prepare-diff` пишет `.claude/state/staged.diff`.
7. Правка файла: `check-prompt-rules` (PreToolUse); PostToolUse — `check-deps` (вброс), `count-edits`, `check-write` (не deny).
8. Старт: `session-start.sh` / `prompt-start.sh` → текст «С ЧЕГО НАЧАТЬ».

## Выходы
- `{}` — пропуск; `hookSpecificOutput.permissionDecision=deny` + reason — стоп инструмента/через git-gate — стоп коммита (exit 1).
- Cursor: `{"permission":"deny",...}` или `{"additional_context":...}` (`cursor-wrap.sh:94-105`).
- `systemMessage` / `additionalContext` — предупреждение без deny (`count-edits.sh:33-38`, `check-write.sh:49-52`, `check-deps.sh:197-199`).
- Журнал `.claude/hooks.log`; диффы `.claude/state/staged.diff`, `staged-kimi.diff`; снимок `deps-snapshot.tsv`.
- Потребители: Claude/Kimi/Cursor (хуки), git (pre-commit/commit-msg), человек (stderr git-gate).

## Обращения наружу
- SQL: нет.
- HTTP: `check-golden.sh:94` — `curl -sS -m 5` к `GOLDEN_EMBED_HEALTH` или `EMBED_HEALTH_URL` из `/etc/1c-embed.env` (`check-golden.sh:84-91`); проверка JSON `model`/`workers`.
- LLM: `sniper-kimi.sh:87` — `timeout 570 "$SNIPER" -p "$PROMPT"` (`SNIPER_KIMI_CMD` или `kimi`); читает `.claude/state/staged-kimi.diff`.

## Переключатели
| Имя | Где | По умолчанию |
|---|---|---|
| `CLAUDE_PROJECT_DIR` | `hook_repo_root` | пусто → git / путь хука |
| `HOOK_MSG_FILE` | `hook_commit_note`, git-gate | нет |
| `DIFF_OVERRIDE` / `STAGED_OVERRIDE` | sql-docs, prompt-rules, graph-fresh | живой `git diff` |
| `KIMI_CONFIG_TOML` | `kimi_config_path` | `~claudedev/.kimi-code/config.toml` |
| `CURSOR_HOOKS_JSON` / `CURSOR_MCP_JSON` | cursor_*_path | `.cursor/hooks.json`, `.cursor/mcp.json` |
| `SNIPER_KIMI_CMD` | sniper-kimi | `kimi` |
| `GOLDEN_EMBED_HEALTH` | check-golden | из `/etc/1c-embed.env` или нет (статус 2) |
| `CLAUDE_SESSION_ID` / `session_id` | count-edits, prompt-start | `default` / выход без вброса |

## Развилки
- **deny vs `{}`**: люк `override.txt` с именем гейта → `{}` (`hook_stop`/`hook_gate_json`).
- **Пометка коммита**: `Доки:`/`Docs:` снимает sql-docs; `Числа:`/`Бюджет:`/`Numbers:`/`Budget:` — check-diff (`hook_commit_note`).
- **check-docs**: код без `.md` → deny; только `.md` с путями вне дерева/индекса/HEAD → deny; иначе ok.
- **check-graph-fresh**: A без сущности / D известного / M|R|C известного без графа в индексе → deny; A в `work/` пропуск.
- **check-active-size**: `activeContext.md` > 300 строк → deny.
- **check-prompt-rules**: маркеры обязан/never/… в персоне `instance/`, полях `*SYS`/`*HINT`/`instruction`/…, или в py-литерале (ast) → deny; иначе `{}`.
- **check-live-probe**: в индексе ровно путь `ubuntu/serenedb/serene_ask.py` и нет свежей отметки `okna probe … 0err/N` (или ask новее mark) → deny.
- **check-golden**: не deploy → `{}`; иначе нужна та же отметка + md5 дерева SRC_DIRS = HEAD; эмбеддер мёртв + в HEAD `Золотой: невозможен` → пропуск.
- **check-gates**: `sudo`+`systemctl` → deny с подсказкой; иначе commit/deploy + `hook_guard_armed` непустой → deny.
- **sniper-kimi**: `VERDICT: OK` → `{}`; `FINDINGS` / нет маяка / rc≠0 / дифф не снят → deny.
- **cursor-wrap**: гейты из `INJECT` при падении rc → exit 0; остальные → deny (`cursor-wrap.sh:30,112-116`).

## Чего здесь нет
- Проверки факта вызова MCP `serenedb-docs` (sql-docs только требует пометку в сообщении).
- Снайпера-агента Claude в этом каталоге (есть только `sniper-kimi.sh`; `prepare-diff` пишет файл для внешнего agent-хука).
- `check-golden` / `sniper-kimi` / `prepare-diff` / PostToolUse-хуков в `git-gate.sh` (только перечисленные в шагах 4–5).
- Автопереноса истории из `activeContext.md`.
- Потребления строки люка хуком (строка остаётся, пока владелец не сотрёт).
- Установки гейтов (`install-gates.sh` вне участка); `test-hooks.sh` — пробы, не гейт.
