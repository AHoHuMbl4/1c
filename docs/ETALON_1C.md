# Эталоны из живой 1С (`etalon_1c.py`)

Задача **И0** [`PLAN_TO_TARGET.md`](PLAN_TO_TARGET.md). Инструмент:
`ubuntu/serenedb/etalon_1c.py`. Замок офлайн: `ubuntu/serenedb/test_etalon_1c.py`.

## Что делает

1. По описанию среза (вопрос + как считать) получает число **из 1С** через
   HTTP-шлюз OData (`1c-odata-gateway@…`, только GET) и **из корпуса** одним
   SQL на **все** срезы с `corpus.sql` (скалярные подзапросы через
   `UNION ALL`, один процесс клиента — п. 20). Два счёта независимы.
2. Сравнивает числа и ставит статус сверки. Расхождение по существу попадает в
   очередь `independent_read` отчёта (независимое прочтение вопроса без
   контекста кода). Статус `freshness_lag` — этикетка лага такта на
   относительных периодах, не провал набора.
3. Собирает черновик приёмочного набора `client-gold.tsv`: покрытие сущностей
   из `$metadata` и/или `search_tables`, покрытие формулировок из `ask_journal`
   / файла вопросов.

Источник эталона в `client-gold.tsv` после успешного счёта 1С — `1c`.
Заявленное значение из старого набора, не совпавшее с 1С, получает статус
`declared_wrong` (прецедент 31.07: склады 25 → 17 без групп).

Живой прогон okna (packet): [`I0_ETALON_TOOL.md`](I0_ETALON_TOOL.md) — dual-verify
витрина↔корпус через `fact.sql` (OData на Ubuntu в packet-режиме нет).

## Запуск

Контур задаётся снаружи (URL шлюза, DSN). В коде имён баз нет.

```bash
# сверка срезов (OData и/или fact.sql витрины)
export ETL_ODATA_BASE=http://127.0.0.1:<порт-шлюза>   # если есть odata.entity
export ODG_GATEWAY_TOKEN=…          # Bearer шлюза
export SERENEDB_DSN='host=… port=… user=… dbname=…'

python3 ubuntu/serenedb/etalon_1c.py verify \
  --slices slices.json \
  --out report.json \
  --gold-out client-gold.tsv

# сразу после такта корпуса: relative mismatch считается substantive
python3 ubuntu/serenedb/etalon_1c.py verify --slices slices.json --just-after-tick

# генератор набора (офлайн-снимки или живые источники)
python3 ubuntu/serenedb/etalon_1c.py generate \
  --metadata-xml /path/to/\$metadata \
  --journal-tsv questions.tsv \
  --out client-gold.tsv

python3 ubuntu/serenedb/etalon_1c.py generate \
  --from-gateway --from-journal --out client-gold.tsv

# packet / без $metadata: журнал + search_tables
python3 ubuntu/serenedb/etalon_1c.py generate \
  --from-journal --from-search-tables --out client-gold.tsv
```

Формат среза (`slices.json` — список или `{"slices":[…]}`):

```json
{
  "id": "warehouses",
  "question": "Сколько у нас складов?",
  "period": "stable",
  "declared": 25,
  "odata": {
    "entity": "Catalog_Склады",
    "op": "count",
    "filter": "IsFolder eq false"
  },
  "fact": {
    "sql": "SELECT count(*) FROM catalog_склады WHERE lower(cast(isfolder as varchar))<>'true'"
  },
  "corpus": {
    "sql": "SELECT count(*) FROM catalog_склады WHERE \"IsFolder\"='false'"
  }
}
```

`op`: `count` | `sum` (для `sum` нужно `field`). Если `$filter` на стороне 1С
не срабатывает — `local_filter` / запасной обход страницами.
`fact.sql` — факт 1С из витрины (packet); пишется в `odata_value` / `etalon_source=1c`.
Можно без `odata`, если все срезы на `fact`/`corpus`.

Колонки `client-gold.tsv`: `question`, `etalon`, `etalon_source`, `verify_status`.

## Что считается расхождением

| Статус | Когда | Следствие |
|---|---|---|
| `match` | 1С и корпус совпали (и заявленное, если есть) | ок |
| `declared_wrong` | заявленный эталон ≠ факт 1С | очередь независимого прочтения; эталон в gold берётся из 1С |
| `freshness_lag` | относительный период (фраза из `period_relative_forms.json` или `"period":"relative"`) и 1С≠корпус, сверка не сразу после такта | этикетка «данные уехали за лаг», не FAIL набора |
| `mismatch` / `needs_independent_read` | 1С≠корпус на стабильном срезе (или relative сразу после такта) | очередь независимого прочтения |
| `pending` | посчитана одна сторона | досчитать |
| `error` | транспорт / SQL | ненулевой код `verify` |

Относительный период распознаётся по фразам словаря
`ubuntu/serenedb/period_relative_forms.json` (тот же источник, что у ask /
шага такта) или по полю `"period":"relative"`. Языкового списка слов в коде
нет: пока формы вроде «вчера» нет в словаре — только через hint в срезе.
Фиксированного срока свежести в контракте нет (п. 17 с 26.08) — лаг такта
существует всегда и для relative отражается статусом, а не провалом.

Корпус: `CorpusClient.scalars` собирает один запрос
`SELECT i, CAST((<sql_i>) AS VARCHAR) … UNION ALL …` (доки SereneDB:
Scalar Subquery; UNION ALL bag semantics) и запускает клиент **один раз**
на весь список срезов.

## Замок

```bash
python3 ubuntu/serenedb/test_etalon_1c.py
```

Без сети и без `psql`: фикстуры OData, сравнение, классификация (в т.ч. прецедент
складов), генерация TSV, проверка исходника на литералы контуров, на N срезов —
один запуск клиента корпуса, отсутствие языкового списка периодов в исходнике.

## Живой прогон (оркестратор)

Этот документ и офлайн-замок живой контур не трогают. Осталось:

1. Проверить, что шлюз OData контура отвечает (`/health`, `$metadata`).
2. Собрать `slices.json` по вопросам приёмки / черновику gold.
3. `verify` на стендах с уже поднятым шлюзом (например чужие базы контура).
4. `generate --from-gateway --from-journal` → `client-gold.tsv`, затем сверка
   эталонов и разбор очереди `independent_read`.
