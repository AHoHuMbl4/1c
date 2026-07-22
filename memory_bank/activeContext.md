# Active Context

_Обновлено: 2026-07-22 (вечер) — «второй мозг» РАБОТАЕТ end-to-end_

## Статус: ✅ ГОТОВО end-to-end
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

## Тюнинг прода (НЕ хвосты MVP — работает; улучшать на реальной ERP)
- OData отдаёт guid'ы в ссылочных полях → `$expand`/маппинг в наименования.
- Инкремент документов по дате (сейчас полная перевыгрузка; идемпотентно).
- Состав OData сузить с «все 1128» до нужных разделов.
- Каветат ИТС/легальность Бухгалтерии Проф — на реальной базе с подпиской неактуально.
- Данных в чистой тестовой базе мало — на клиентской ERP наполнится.

## Ключевые доступы (пароли НЕ в git)
KB-репо money/1c-test (GitLab id 95); бот @test1c_mcp_bot (`credentials/telegram-1c-bot.env`); admin/ai_reader базы (пароли у владельца; ai_reader в `/etc/1c-odata-gateway.env` на LXC); ключи DeepSeek/Alibaba/GitLab в `credentials/`.
