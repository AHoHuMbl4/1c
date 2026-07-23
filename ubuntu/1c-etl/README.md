# 1C → KB ETL (холодный контур)

Читает данные 1С через read-only OData-шлюз (`:6011`, только GET), пишет md-таблицы
справочников/документов в клон KB-репо (GitLab `money/1c-test`), коммитит и пушит.
Дальше oikb/kb-poll (braine) сами индексируют → бот отвечает по данным 1С.

## Инвариант
1С только читаем. ETL ходит исключительно через OData-шлюз под `ai_reader` — записать
в 1С нечем (шлюз режет не-GET → 405; у пользователя нет прав записи). См.
`ubuntu/1c-gateway/odata_gateway.py`, `docs/RUNBOOK_DEPLOY.md`.

## Развёртывание (LXC)
```bash
install -D oc_etl.py /opt/1c-etl/oc_etl.py
cat > /etc/1c-etl.env <<EOF
ETL_ODATA_BASE=http://127.0.0.1:6011
ETL_KB_REPO=http://root:<glpat из credentials/gitlab-1c-test.env>@gitlab-real.unde.life/money/1c-test.git
ETL_KB_DIR=/opt/1c-etl/kb
ETL_KB_SUBDIR=1c
EOF
chmod 600 /etc/1c-etl.env
cp systemd/1c-etl.service systemd/1c-etl.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now 1c-etl.timer          # ночная выгрузка 03:00
systemctl start 1c-etl.service               # первый прогон сейчас
journalctl -u 1c-etl -n 40 --no-pager        # лог
```

## Что генерит в KB-репо (`1c/`)
```
1c/catalogs/<Имя>.md     # справочники — md-таблицы
1c/documents/<Имя>.md    # документы — md-таблицы
1c/_index.md             # что выгружено, сколько записей, что пропущено
```

## Что тянуть — конфиг-нейтрально (копипаст на любой бизнес)
ETL НЕ содержит захардкоженного списка под конкретную конфигурацию. Что выгружать —
по приоритету:
1. `ETL_INCLUDE` (env) — явный список сущностей;
2. **выбор из веб-UI галочками** → `/etc/1c-etl-selected.txt` (`ubuntu/1c-config-ui/`) —
   основной способ: один раз отметил бизнес-разделы, дальше автомат;
3. авто из OData (все непустые Catalog_/Document_) — фолбэк; на типовой 1С тянет и
   служебные классификаторы (сотни), поэтому для прода — выбор через UI/INCLUDE.

Резолв ссылок guid→наименование, чистка полей и дат — **универсальны** (платформенные
паттерны 1С), работают на любой конфигурации без настройки.

## Читаемость (сделано, универсально)
- Ссылки `*_Key`/составные (guid) → наименования по карте `Ref_Key→Description`.
- Нулевые ссылки, пустые даты, техно-поля (`_Type`, `@navigationLinkUrl`, `DataVersion`)
  и полностью пустые колонки — убираются.

## Тюнинг прода (не хвосты)
- Инкремент документов по дате (сейчас полная перевыгрузка; идемпотентно).
- Регистры (остатки/обороты) — добавить в состав OData + `TOP_PREFIXES`.
- На больших базах карту ссылок строить только из справочников (память).
