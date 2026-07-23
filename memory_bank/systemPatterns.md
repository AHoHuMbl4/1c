# System Patterns

## Архитектура (кратко; полностью — `docs/ARCHITECTURE.md`)
Два контура:
- **Холодный** (наполнение): 1С OData (read-only) → GET-only шлюз → ETL выгружает
  выбранные сущности в md → push в KB-репо (GitLab) → oikb/kb-poll → OpenWebUI/pgvector индекс.
- **Горячий** (ответ): вопрос → braine (retrieval + гейты точности + DeepSeek) → ответ с цитатами.

Ключевые решения:
- Канал чтения — **штатный OData на IIS** (служба Windows), НЕ встроенный MCP-тулкит
  (тот на idle-обработчике 1С — зависает; `docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md`).
- Read-only — два слоя: пользователь `ai_reader` + шлюз (только GET).
- Мозг — **braine** (клонируемый RAG-шаблон, Open WebUI + pgvector), не своя схема.
- **Конфиг-нейтральность:** код универсален; «что тянуть» — конфиг под бизнес (галочки
  config-ui → `/etc/1c-etl-selected.txt`), не хардкод. Резолв ссылок guid→имя — универсален.

## Структура репозитория
- `docs/` — документация (ARCHITECTURE, RUNBOOK — главные).
- `ubuntu/` — код на LXC: `1c-gateway/` (OData-шлюз + dev MCP-прокси), `1c-etl/` (ETL+таймер),
  `1c-config-ui/` (галочки+discovery). У каждого — README + systemd/.
- `windows/` — скрипты стенда (`scripts/backup-1c.ps1`), `fork/` (dev-форк тулкита).
- `memory_bank/` — контекст. `credentials/` — секреты (в `.gitignore`).

## Соглашения
- Коммиты: `тип(область): описание` (feat/docs/fix/chore).
- Каждое изменение → коммит + push в `origin/main`. Значимое → обновлять
  `memory_bank/activeContext.md` и `progress.md`.
- Сервисы на LXC — systemd, `enabled` (zero-touch, переживают ребут).

## Правила (владелец)
- 🔴 1С только читаем; перед любым изменением базы 1С — бэкап (`.dt`/копия).
- На серверах (LXC/Windows) состояние меняем только по явной инструкции владельца.
- Секреты — вне git (`credentials/`, `/etc/*.env` chmod 600).
- Windows-автоматизация — с учётом готчей (BOM, EncodedCommand, COM) из `techContext.md`.
