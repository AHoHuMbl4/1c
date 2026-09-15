# Бот-слой OpenClaw — код инстанции

Диалоговая оболочка тона над двумя «мозгами» (braine + SereneDB): принимает Telegram, зовёт MCP-инструменты
`ask_1c`/`report_1c`, отвечает живо. Данные 1С сам не трогает.

> Здесь — только **код и эталоны** бот-слоя. Пошаговое развёртывание (движок, юзер `undebot`, конфиг,
> verify-плагин, gateway) — **`docs/RUNBOOK_DEPLOY.md` §11**. Как всё устроено — **`docs/OPENCLAW_BOT.md`**.

## Раскладка
| Путь | Что |
|---|---|
| `mcp_braine.py` + `systemd/1c-mcp-braine.service` | MCP-сервер инструмента `ask_1c` над braine `/ask` (streamable-http, `127.0.0.1:6014`) |
| `instance/openclaw.json` | эталон конфига инстанции (совпадает с деплоем `~undebot/.openclaw/openclaw.json` 1:1, кроме генер-токена) |
| `instance/AGENTS.md` | эталон персоны (**только тон** — не слой гарантий) |
| `verify-plugin/` | гейт `braine-verify` (анти-галлюцинации КОДОМ): `verify-core.js` логика, `index.js` хуки, `test-verify.mjs` 36 юнитов, `README.md` |
| `qa/qa-probes.sh` | QA-батарея через CLI (без Telegram): приветствие, мета, инъекции, отчёт-чисто, нет-данных, не-слил-SQL |
| `requirements.txt` | зависимости `mcp_braine.py` |


## Мост `mcp_ask` (активный контур)

Сервис MCP `ask_1c` → serene_ask. Webchat-конверт движка (HISTORY/CURRENT + `User:`)
снимается с `question` в мосту до сведения pending (`strip_webchat_question_envelope`).

Замки (тот же venv, что у моста):
- `test_mcp_ask.py` — формат ответа моста
- `test_mcp_ask_pending.py` — pending clarify / текстовый выбор
- `test_mcp_ask_envelope.py` — чистка webchat-конверта

## Правила слоя (🔴 приоритетнее прочего — см. `docs/OPENCLAW_BOT.md`)
- **Только нативное OpenClaw.** Кастом — с явного согласия владельца (гейт `braine-verify` одобрен).
- **Документацию движка смотреть в склонированных репо** `/opt/openclaw`, `/opt/openclaw-engine` (read-only),
  не «по памяти».
- **Гарантии — КОДОМ, не промтом:** числа/анти-слив/read-only держат гейт+роли; персона (`AGENTS.md`) — тон.

*(Инструмент `report_1c` и его сервис `1c-mcp-reports` :6015 — в `ubuntu/serenedb/` / `docs/SERENEDB.md`.)*
