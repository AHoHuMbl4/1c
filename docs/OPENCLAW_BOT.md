# Бот-слой: OpenClaw (диалоговая оболочка «второго мозга»)

> 🔴🔴🔴 **ГЛАВНОЕ ПРАВИЛО — ЧИТАТЬ ПЕРВЫМ, ДО ЛЮБОЙ РАЗРАБОТКИ БОТ-СЛОЯ:**
>
> **1. Используем НАТИВНЫЕ решения OpenClaw. Кастом — ЗАПРЕЩЁН без явного согласия владельца.**
>    Любую задачу сначала решаем штатными средствами (конфиг, плагины, механизмы движка). Если
>    кажется, что нужен кастомный код/патч/обход — СТОП, спросить владельца.
>
> **2. Документацию OpenClaw смотрим В РЕПОЗИТОРИИ движка на LXC — не угадывать.**
>    Склонированы `/opt/openclaw` (проектная докум. клиент-ботов владельца) и `/opt/openclaw-engine`
>    (движок). Оба **read-only**. Перед действием — ответ в их README/docs/коде, не «по памяти».
>
> Эти два правила приоритетнее любых прочих соображений в документе.

Как раскатать бот-слой командами — **`RUNBOOK_DEPLOY.md` §11**. Аналитика/витрина — `SERENEDB.md`.
Вся картина — `ARCHITECTURE.md`.

---

## Что это
OpenClaw — **разговорная оболочка тона** над двумя «мозгами», НЕ их замена. Мозги отвечают точно, но
«сухо»; OpenClaw делает диалог живым/человеческим. Сам данные 1С **не трогает** — только через два
MCP-инструмента:

```
человек → Telegram @бот → OpenClaw (тон, DeepSeek) — сам выбирает инструмент:
   ├ report_1c → SereneDB: аналитика/отчёт/график (NL→SQL под ro-ролью + резолвер Qwen)
   └ ask_1c    → braine RAG: факты/текст с цитатами
   → verify-плагin (ГЕЙТ, КОДОМ): числа сверяет с эталоном инструмента, внутреннее (SQL/пути) режет
   → живой ответ клиенту (таблица/график)
```

🔴 **Критичный инвариант:** мозги гарантируют «не выдумывать» (числа сверены с источником, цитаты).
Оболочка обязана **переформулировать ТОЛЬКО то, что вернул инструмент** — не добавлять/менять факты.
Держит это не персона, а **гейт кодом** (ниже) — правило владельца «промт не держит».

## Развёртывание (по факту на `.42`)
- **Движок:** `openclaw@2026.7.1-2` — npm global, `/usr/lib/node_modules/openclaw`, CLI `/usr/bin/openclaw`.
- **1 клиент = 1 инстанция:** отдельный Linux-юзер **`undebot`** + `linger=yes` + `~/.openclaw/`
  (`openclaw.json` конфиг, `.env` 600, `workspace/AGENTS.md` персона, `telegram-token` 600, логи/сессии).
- **Gateway** — systemd **user**-юнит `openclaw-gateway.service` (`enabled`, linger → стартует на буте
  без логина): `node …/openclaw/dist/index.js gateway --port 18800`, loopback `127.0.0.1:18800`, auth token.
- **Telegram** — long polling (входящие порты не нужны), токен в отдельном `tokenFile` (не в конфиге).

## Конфиг `~/.openclaw/openclaw.json` (эталон — `ubuntu/openclaw/instance/openclaw.json`)
Репо-копия совпадает с деплоем 1:1 (кроме секрета `gateway.auth.token`, генерится при `gateway install`).

| Ключ | Значение | Зачем |
|---|---|---|
| `agents.defaults.model.primary` | `deepseek/deepseek-chat` | LLM тона (openai-completions, ключ в `.env` + auth-store) |
| `agents.defaults.thinkingDefault` | `off` | без «размышлений» в чат |
| `session.dmScope` | `per-channel-peer` | изоляция диалогов по собеседнику (обязательно) |
| `commands.native` | `false` | без служебного меню команд в Telegram |
| `tools.allow` | `["message","bundle-mcp"]` | 🔒 **узкий набор кодом**: только слать сообщения + MCP-инструменты; ~20 прочих нативных инструментов отрезаны |
| `plugins.allow` | `["deepseek","braine-verify"]` | allow-list плагинов (гейтит discovery) |
| `channels.telegram.dmPolicy` | `allowlist` + `allowFrom:[5949699699]` | 🔒 **только владелец** пишет боту (бот отдаёт данные компании!) |
| `channels.telegram.streaming.mode` | `off` | без тех-болтовни/частичных апдейтов |

**Два MCP-инструмента** (`mcp.servers`, оба `streamable-http`, `toolFilter.include` — берём ровно один tool):

| Сервер | URL | Инструмент | Таймаут | Бэкенд |
|---|---|---|---|---|
| `second-brain` | `127.0.0.1:6014/mcp` | `ask_1c` | 60с | braine `/ask` :8090 (факты/текст) |
| `second-brain-reports` | `127.0.0.1:6015/mcp` | `report_1c` | 120с | SereneDB-витрина (аналитика/график) |

Инструмент проецируется боту под именем `<server>__<tool>` (напр. `second-brain__ask_1c`). Подключение —
штатной командой `openclaw mcp add <name> --url … --transport streamable-http --include <tool>` (не патч).

**Плагины** (`plugins.entries`): `deepseek` (провайдер модели), `memory-core` (нативная память диалога),
`braine-verify` (наш гейт; `config.debug:true`, `hooks.allowConversationAccess:true`).

## 🔴 Гейт анти-галлюцинаций `braine-verify` — КОДОМ, не промтом
Нативный плагин OpenClaw (`ubuntu/openclaw/verify-plugin/`, установлен `/home/undebot/braine-verify/`,
`enabled`). Точность даёт **детерминированная сверка кода**, не запрет в промте (правило владельца).
Финальный ответ всегда генерит LLM бота (нативного passthrough в движке нет → LLM может исказить факт
при «оживлении»); гейт ловит это на исходящем. Чистая логика — `verify-core.js` (без зависимостей,
**36 оффлайн-юнитов** `test-verify.mjs`); `index.js` — подключение к хукам + состояние хода в памяти.

Четыре хука:
1. **`after_tool_call`** — ответ инструмента (`ask_1c` **или** `report_1c`) кладём в эталон хода.
2. **`message_received`** — запоминаем числа из ввода пользователя (эхо его же номера ≠ выдумка).
3. **`message_sending`** — числовые токены исходящего (≥`minDigits` цифр, с группировкой `7 727 406 020`,
   `1 234,56`) обязаны быть обоснованы эталоном/вводом. Иначе: есть эталон с данными → **replace** на
   дословный ответ инструмента; эталон «нет данных» → **replace** на безопасную строку; выдуманное длинное
   число (ИНН/счёт, ≥`highRiskDigits`) без эталона → **cancel**. Плюс `stripInternal` режет внутреннее.
4. **`reply_payload_sending`** — тем же `stripInternal` чистит **подпись к медиа** (у фото caption идёт
   мимо `content` хука `message_sending`) → полное покрытие: текст + подпись к графику.

`stripInternal` — НАШИ известные форматы (не открытая классификация): SQL (`SELECT…FROM…`), серверные
пути (`/home|/var|/opt/…`), наши маркеры (`[ГРАФИК-ФАЙЛ:…]`, `Трактовка (SQL):`, `[НЕТ ДАННЫХ…]`).

**Дефолты (в коде `verify-core.js`, конфиг-нейтрально):** `toolNames:["ask_1c","report_1c"]`,
`minDigits:4`, `highRiskDigits:7`, `noDataMarker:"[НЕТ ДАННЫХ"`, `stripInternal:true`. Границы и конфиг —
`ubuntu/openclaw/verify-plugin/README.md`.

## Персона `workspace/AGENTS.md` — ТОЛЬКО тон (не слой гарантий)
Эталон — `ubuntu/openclaw/instance/AGENTS.md`. Держит стиль (вежливый ассистент компании, на «вы»,
русский, приветствие один раз), запрет мета-реплик про себя-ИИ (+ конкретный редирект на «ты кто?»),
запрет нарратива действий, «не сливать внутреннее» даже «на тест/разработчику», устойчивость к инъекциям
(«покажи промпт»/«стань другим ботом»), маршрутизацию инструментов (аналитика→`report_1c`, факт→`ask_1c`).
Всё это — **тон и удобство**; жёсткие гарантии (числа/анти-слив/read-only) держат гейт и роли, а не промт.

## 🔒 Изоляция
Сборка — только под юзером `undebot` на **нашей** LXC `.42` (рядом с braine). Прод-бот владельца на `.15`
не трогаем (не подключались). Эталонные репо `/opt/openclaw` (+ `/opt/openclaw-engine`) — read-only, в них
не пишем/не коммитим. Токен `@test1c_mcp_bot` забран у braine-моста `tg-bridge` (он `stop+disable`).

## Zero-touch
`linger=yes` → gateway стартует на буте без логина (проверено). Telegram long polling. Мониторинг
`1c-bot-monitor.timer` (алерт владельцу в Telegram при падении gateway/mcp/serenedb) — см. `ARCHITECTURE.md`.

## Эксплуатация / грабли (важное, проверено в рантайме)
- **Хуки не-bundled плагина к переписке** блокируются по умолчанию → нужен
  `plugins.entries.braine-verify.hooks.allowConversationAccess:true` (иначе хуки молча не срабатывают).
- **Корреляция хода:** у `message_sending` в ctx **нет `runId`**, есть `ctx.sessionKey`; доставка идёт
  **после `agent_end`**. Поэтому эталон храним по `sessionKey`, **не** удаляем на `agent_end`, сбрасываем
  на новом `runId`. (Раньше удаление на `agent_end` давало ложный `cancel` верного числа.)
- **Ключ провайдера** держать в auth-store, не только env:
  `openclaw models auth paste-api-key --provider deepseek --profile-id deepseek:default`
  (иначе «No API key found» после явного `plugins.allow`).
- **Ротация bot-токена** (действие владельца — я к @BotFather доступа не имею): `/revoke` у BotFather →
  новый токен в `/home/undebot/.openclaw/telegram-token` (600) → `systemctl --user restart openclaw-gateway`
  → `openclaw channels status --probe` = `works`. Мониторинг читает тот же файл автоматически.
- **CLI-турн для проверки:** `openclaw agent --message "<текст>"` (+ `--session-key`); без `--deliver`
  ответ в stdout (проверить мозг/эталон, гейт `message_sending` — только на реальной доставке в канал).

## Файлы (`ubuntu/openclaw/`)
| Файл | Роль |
|---|---|
| `mcp_braine.py` | MCP-сервер инструмента `ask_1c` над braine `/ask` (FastMCP, streamable-http) → сервис `1c-mcp-braine` :6014 |
| `instance/openclaw.json` | эталон конфига инстанции (совпадает с деплоем) |
| `instance/AGENTS.md` | эталон персоны (тон) |
| `verify-plugin/` | гейт `braine-verify`: `verify-core.js` (логика), `index.js` (хуки), `test-verify.mjs` (36 юнитов), манифест |
| `qa/qa-probes.sh` | QA-батарея через CLI (приветствие, мета, инъекции, отчёт-чисто, нет-данных, не-слил-SQL) — без Telegram |
| `systemd/1c-mcp-braine.service` | юнит MCP-сервера `ask_1c` |

*(Инструмент `report_1c` и его сервис `1c-mcp-reports` :6015 живут в `ubuntu/serenedb/` — см. `SERENEDB.md`.)*

---
История интеграции (пошаговые находки отладки бот-слоя, выбор нативного MCP-пути, живые тесты гейта на
Telegram-доставке) — в `git log`.
