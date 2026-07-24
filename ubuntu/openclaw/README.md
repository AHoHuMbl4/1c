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

## Правила слоя (🔴 приоритетнее прочего — см. `docs/OPENCLAW_BOT.md`)
- **Только нативное OpenClaw.** Кастом — с явного согласия владельца (гейт `braine-verify` одобрен).
- **Документацию движка смотреть в склонированных репо** `/opt/openclaw`, `/opt/openclaw-engine` (read-only),
  не «по памяти».
- **Гарантии — КОДОМ, не промтом:** числа/анти-слив/read-only держат гейт+роли; персона (`AGENTS.md`) — тон.

*(Инструмент `report_1c` и его сервис `1c-mcp-reports` :6015 — в `ubuntu/serenedb/` / `docs/SERENEDB.md`.)*
