# Active Context

_Обновлено: 2026-07-23 — «второй мозг» работает; текущий фокус — OpenClaw-обёртка (диалог)_

## 🔴 ТЕКУЩИЙ ФОКУС: OpenClaw поверх braine (см. `docs/OPENCLAW_BOT.md` — читать ПЕРВЫМ)
У владельца УЖЕ работает бот-менеджер на OpenClaw (репо `money/opwnclaw-bot`, склонирован `/opt/openclaw`); отвечает «сухо». Надо, чтобы он **черпал факты из нашего braine**. OpenClaw = надстройка тона, НЕ замена: человек→OpenClaw→наш braine→OpenClaw оживил→клиент.

🔴🔴 **ПРАВИЛА (первые при работе над бот-слоем):** (1) только НАТИВНЫЙ OpenClaw, кастом запрещён без явного согласия владельца; (2) документацию смотреть в склонированных на LXC репо (`/opt/openclaw` + движок `/opt/openclaw-engine` из github.com/openclaw/openclaw), НЕ угадывать.

**Нативный путь (docs движка):** OpenClaw — нативный MCP-клиент (`openclaw mcp add`, streamable-http). Anti-hallucination: владелец одобрил **Вариант А — плагин-verify** (хук `message_sending` сверяет факты ответа с выводом braine, режет несверенное — кодом, не промтом; промтом ЗАПРЕЩЕНО).

**Сборка (артефакты `ubuntu/openclaw/`):**
- ✅ Компонент 1 — MCP-сервер `ask_1c` над braine (mcp_braine.py, FastMCP streamable-http). Сервис **1c-mcp-braine** :6014 (enabled). Проверено: вернул контрагентов с ИНН+цитатой.
- ✅ Компонент 2 — движок OpenClaw (npm 2026.7.1-2). Инстанс под юзером `undebot` (`~/.openclaw/`, DeepSeek provider-плагин), gateway = systemd user-юнит (enabled --now, «gateway ready»). Турн через gateway проверен (DeepSeek ответил).
- ⏳ Компонент 4 — осталось: `openclaw mcp add second-brain` (:6014) + персона AGENTS.md + tools.allow. 3 — verify-плагин (after_tool_call+message_sending). 5 — тест на галлюцинации.
Топология: собираем/демо на нашем `.42` (рядом с braine), НЕ трогая их прод-бот на `.15`.
🔒 Эталон `money/opwnclaw-bot` (`/opt/openclaw`) + движок (`/opt/openclaw-engine`) — READ-ONLY, только читаю; к проду `.15` не подключался. Проверено 2026-07-23 (git clean, HEAD==origin).

---

## Статус: ✅ ГОТОВО end-to-end (второй мозг)
Спросил бота в Telegram (`@test1c_mcp_bot`) → он отвечает по реальным данным 1С с цитатами. Вся цепочка сцеплена и переживает ребут без ручных действий.

```
1С (Windows, файловая база buh_test)
  └─ IIS (служба, авто-старт) → штатный OData (read-only ai_reader)
      └─ роутер 192.168.56.1 проброс → IIS:80
          └─ LXC: OData-шлюз :6011 (только GET, писать нельзя)
              └─ ETL (ubuntu/1c-etl) → md-таблицы → KB-репо money/1c-test (GitLab)
                  └─ oikb/kb-poll → OWUI/pgvector (эмбеддинги DashScope)
                      └─ tg-bridge (бот) + api :8090 → ответы с цитатами (DeepSeek, гейты)
```

Эталон раскатки на новом проекте: **`docs/RUNBOOK_DEPLOY.md`** (переписан под OData).

## Прод-канал = OData на IIS (НЕ встроенный тулкит)
Тулкит отвергнут для прода: обслуживает всё через 1 клиентский idle-обработчик 1С (~1 req/s, встаёт на модалке — `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`); тумблеры не блокируют execute_code. OData обслуживает IIS-служба: многопоточно, авто-старт, без модалок. Тулкит остался dev-опцией (`ubuntu/1c-gateway/gateway.py`, `windows/fork/`).

## Read-only — два слоя (проверено с LXC)
1. `ai_reader` (пароль qwaszx) — читает 200, пишет 500 (нет прав).
2. OData-шлюз `odata_gateway.py` — GET проходит, POST/PATCH/PUT/DELETE → 405 до 1С.

## Проверено end-to-end (2026-07-22)
- OData читает как служба (Организации→«Наша организация»), зависаний нет.
- ETL: 19 сущностей/44 записи через шлюз → push в KB → oikb «Synced 20 added» → индексация.
- Бот: «Каких контрагентов знаешь?» → «МИ ФНС России по управлению долгом (ИНН 7727406020), Казначейство России» с цитатами.
- Zero-touch: W3SVC Automatic; все LXC-сервисы enabled (postgresql/open-webui/oikb/rerank-shim/tg-bridge/api/kb-poll/1c-odata-gateway + таймеры nightly-eval, 1c-etl). gsheets-sync замаскирован. Старый MCP 1c-gateway disabled.

## Перепроверка (2026-07-23) ✅
Сверено git↔LXC↔живое: все 9 сервисов + 2 таймера enabled/active; порты 6011/6012/3000/8081/8082/8090/5432 слушают; OData-шлюз чтение=1/запись=405; config-ui 116 чекбоксов; Windows IIS Automatic/Running; бот отвечает; ссылки в доках все рабочие. **Найден и починен рассинхрон:** `oc_etl.py` на LXC был старее git (без чтения галочек, в авто-режиме → ночью тянул бы мусор) — передеплоен (md5=git). Поставлен дефолт-выбор `/etc/1c-etl-selected.txt` (23 бизнес-сущности Бухгалтерии) — ночной ETL теперь тянет только их; владелец может переотметить через config-ui `:6012`.

## Конфиг-нейтральность (сделано 2026-07-23) — копипаст на любой бизнес
- **ETL без хардкод-списка:** что тянуть — из `ETL_INCLUDE` → выбора UI (`/etc/1c-etl-selected.txt`) → авто из OData. Резолв ссылок guid→наименование + чистка полей/дат/пустых колонок — универсальны.
- **config-ui `:6012`** (`1c-config-ui`, enabled): веб-галочки «что тянуть» — список всех непустых сущностей 1С (116 на стенде) с числом записей, человек отмечает бизнес-разделы. discovery параллельный (`oc_discover.py`). Кэш `/var/lib/1c-config-ui/entities.json`.
- Модель: код универсален, «что важно» — 5-мин конфиг под бизнес (галочки).
- **Документация приведена в порядок (2026-07-23):** `README.md` (точка входа) + `docs/ARCHITECTURE.md` (полная картина) новые; PLAN/PHASE2 помечены как история; memory_bank актуализирован под OData.

## Тюнинг прода (НЕ хвосты MVP — работает; улучшать на реальной ERP)
- Регистры (остатки/обороты) в состав OData + `TOP_PREFIXES` ETL.
- Инкремент документов по дате (сейчас полная перевыгрузка; идемпотентно).
- Состав OData сузить с «все 1128» до нужных разделов.
- Каветат ИТС/легальность Бухгалтерии Проф — на реальной базе с подпиской неактуально.
- Данных в чистой тестовой базе мало — на клиентской ERP наполнится.

## Ключевые доступы (пароли НЕ в git)
KB-репо money/1c-test (GitLab id 95); бот @test1c_mcp_bot (`credentials/telegram-1c-bot.env`); admin/ai_reader базы (пароли у владельца; ai_reader в `/etc/1c-odata-gateway.env` на LXC); ключи DeepSeek/Alibaba/GitLab в `credentials/`.
