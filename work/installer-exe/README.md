# Рабочая папка: Windows-установщик (exe)

Отдельный контур от параллельных агентов. **Исходники продукта не правим отсюда
без явного слова** — сначала обсуждение и план.

Опора на документы проекта (не дублировать здесь как истину):

| Документ | Зачем |
|---|---|
| `TARGET.md` п. 14 | контракт: ручных шагов два (читатель 1С + при необходимости пользователь Windows) |
| `docs/PLAN_AUTONOMY.md` Фаза 1 | что обязан закрыть Windows-установщик |
| `windows/odata-setup/` | уже существующий `setup-1c-odata.exe` |
| `docs/RUNBOOK_DEPLOY.md` §5 | ручной путь = то, что exe автоматизирует |
| `docs/TEST_SECOND_BASE.md` | грабля `standardOdata enable="false"` после `webinst` |
| `docs/HOW_NOT_TO.md` | уроки, не повторять |
| `docs/PLAN_MVP_PACKET_TRANSPORT.md` | MVP без VPN: шифрованные пакеты Windows→Ubuntu (план 06.08) |

Базовый код продукта: `windows/odata-setup/` (src + `dist/setup-1c-odata.exe`).
Черновики и эксперименты — только в этой папке.

**План работ exe (канал OData):** [`PLAN.md`](PLAN.md).  
**План транспорта данных MVP:** [`docs/PLAN_MVP_PACKET_TRANSPORT.md`](../../docs/PLAN_MVP_PACKET_TRANSPORT.md).
