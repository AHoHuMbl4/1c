# ETA досчёта векторов на klient1 (25.08)

Вопрос владельца: сколько ещё займёт досчёт `search_corpus` на klient1
(`embed_all.sh 64`, старт корпуса **24.08 19:51 UTC**). Движок под полной
нагрузкой — полные `count(*)` по корпусу и любые тяжёлые агрегаты не гонялись.

## Штатное средство

| Что | Раздел доков | На живой 26.07.3 |
|---|---|---|
| Оценка/число строк без полного скана | [`compatibility/system-table-compatibility#system-tables`](https://docs.serenedb.com/compatibility/system-table-compatibility#system-tables) — `pg_class` 🟢 | `reltuples` отвечает за секунды; слот соединения бывает ждать 20–60 с |
| Рабочие таблицы раунда | [`sql/functions/duckdb_table_functions#duckdb_tables`](https://docs.serenedb.com/sql/functions/duckdb_table_functions#duckdb_tables) | перечень `emb_postgres_search_corpus_part_*` ок |
| `query_table(подзапрос)` | [`sql/functions/utility#query_tabletbl_names-by_name`](https://docs.serenedb.com/sql/functions/utility#query_tabletbl_names-by-name) | **нет**: `Table function cannot contain subqueries` (как в `embed_progress.sh`: список — литералом) |
| Полный `left()` / `count` по `emb` корпуса | [`data_import_and_export/parquet/overview#partial-reading`](https://docs.serenedb.com/data_import_and_export/parquet/overview#partial-reading) | под нагрузкой не снимался (известный таймаут, `docs/EMBED_BULK_HOWTO.md` §8) |

Метрика прогресса раунда (устройство `ubuntu/serenedb/embed_missing.sh`):

- `emb_postgres_search_corpus_todo` — снимок очереди раунда (размер фиксирован до `transfer`);
- `emb_postgres_search_corpus_part_*` — уже посчитанные векторы, ещё не перенесённые в корпус;
- **остаток раунда** ≈ `todo.reltuples − Σ part.reltuples`;
- в корпус `emb` ляжет только после `transfer` в конце раунда — `search_corpus.reltuples` за время замера не менялся.

Калибровка `reltuples` vs точный `count(*)` на одной part-таблице (дёшево):
`part_10` → **35184 = 35184** (движок `2026-08-25 05:14:26Z`). Для todo полный
`count(*)` не снимался (8,4 млн строк) — оценка помечена как оценка, но у растущих
part совпадение точное.

Туннель: `psql "host=127.0.0.1 port=17891 user=postgres dbname=postgres"`.
Часы движка отстают от wall-clock этой машины примерно на **4 мин**; ниже — метки
**движка** (`now()`), где не сказано иное.

## Снимки

| # | now() движка (UTC) | wall OK (UTC) | part-таблиц | Σ parts (reltuples) | todo (reltuples) | corpus (reltuples) |
|---|---|---|---|---|---|---|
| 1 | 05:00:57 | ~05:05 | 30 | 510 318 | — | 16 537 095 |
| 2 | 05:04:38 | ~05:09 | 30 | 513 163 | — | 16 537 095 |
| A | 05:06:24 | 05:10:37 | 30 | 514 489 | 8 375 917 | 16 537 095 |
| B | 05:10:30 | 05:14:42 | 30 | 517 751 | 8 375 917 | 16 537 095 |
| cal | 05:14:26 | 05:18:40 | — | part_10: 35184=exact | 8 375 917 | — |

## Оценка

На снимке **B** (движок 05:10:30 UTC):

| величина | значение | погрешность |
|---|---|---|
| объём раунда (`todo`) | **8 375 917** строк | оценка `reltuples`; таблица не растёт в раунде |
| уже в part (посчитано в раунде) | **517 751** | `reltuples`; на part_10 совпал с exact |
| осталось в раунде | **≈ 7 858 166** | todo − parts |
| с вектором в корпусе (оценка) | **≈ 8 678 929** | `corpus − (todo − parts)`; transfer ещё не было |
| без вектора в корпусе (оценка) | **≈ 7 858 166** | те же, пока part не перенесены |

Скорость по приросту Σ parts:

| окно | Δ строк | Δt | скорость |
|---|---|---|---|
| 05:00:57 → 05:04:38 | +2 845 | 221 с | **12,85** стр/с |
| A→B 05:06:24 → 05:10:30 | +3 262 | 246 с | **13,26** стр/с |
| с старта корпуса 24.08 19:51 → B | 517 751 | 33 570 с | **15,42** стр/с (средняя) |

Текущая скорость ниже средней с начала раунда (~14 %): лёгкая просадка, не обвал.

### ETA (остаток 7 858 166)

| сценарий | скорость | ETA | до (UTC, от B) |
|---|---|---|---|
| при текущей | 13,3 стр/с | **≈ 6 сут 21 ч** | ~01.09 ~02:00 |
| при средней с старта | 15,4 стр/с | **≈ 5 сут 22 ч** | ~31.08 ~03:00 |
| при просадке ×0,75 | 10,0 стр/с | **≈ 9 сут 4 ч** | ~03.09 ~09:00 |
| при просадке ×0,5 | 6,6 стр/с | **≈ 13 сут 17 ч** | ~08.09 ~03:00 |

**Диапазон для ответа владельцу: примерно 6–14 суток; центральная оценка ~7 суток
при текущих ~13 стр/с.**

Погрешность ETA: ± порядок 20–30 % от колебаний скорости и от того, что `todo.reltuples`
не сверен exact-count; после `transfer` начнётся следующий раунд только если `left()` > 0.

## Две карты и баланс

HTTP к `10.3.1.11:8000` / `10.3.1.12:8002` из этой сессии недоступен (runtime floor) —
живой `/metrics` карт не снят.

По `pg_class` на снимке 1: из 30 part-таблиц ненулевой `reltuples` у **16**; у активных
среднее **31 621**, CV **0,10** (разброс 28 098–35 624) — между пишущими воркерами
нагрузка ровная. Нулевые part — воркеры без накопленных строк на момент снимка (очередь
за `threads` движка, см. шапку `embed_missing.sh`), не признак перекоса карт.

Деградация с начала: средняя 15,4 → окно A–B 13,3 стр/с (−14 %).

## Повторить замер (однострочник)

Ждёт свободный слот (до ~10 попыток), печатает `todo`, `parts`, `остаток`:

```bash
DSN='host=127.0.0.1 port=17891 user=postgres dbname=postgres connect_timeout=20'; for i in $(seq 1 12); do timeout 45 psql "$DSN" -tAc "SELECT now() AS ts, t.reltuples::bigint AS todo, coalesce((SELECT sum(c.reltuples::bigint) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'emb\_%\_search\_corpus\_part\_%' ESCAPE '\\' AND c.reltuples>=0),0) AS parts, t.reltuples::bigint - coalesce((SELECT sum(c.reltuples::bigint) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND c.relname LIKE 'emb\_%\_search\_corpus\_part\_%' ESCAPE '\\' AND c.reltuples>=0),0) AS remaining FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND t.relname='emb_postgres_search_corpus_todo';" && break; echo "wait $i"; sleep 5; done
```

Скорость: снять два раза с паузой 3–5 мин, разделить прирост `parts` на Δt.
Альтернатива с интервалом: `SERENEDB_DSN="$DSN" EMBED_SCOPE_TOTAL=8375917 EMBED_LEFT_TIMEOUT=5 bash ubuntu/serenedb/embed_progress.sh search_corpus 180`
(полный left по корпусу при живом досчёте обычно не успевает — опирается на part + scope).

## Прогон остановлен → перевод на bulk (25.08)

Тактовый `embed_all`/`embed_missing` на остатке ≈ **7 858 166** давал **13,3**
стр/с → ETA ~7 суток. Это инструмент дельты такта; разовая сборка — bulk
(`docs/EMBED_BULK_HOWTO.md` §3, §9): своя ATTACH-база на поток, установившийся
режим **168** стр/с.

Прогон тактом остановлен оркестратором; посчитанное в `emb_*_part_*` не
потеряно (постоянная метка). Дальше — `ubuntu/serenedb/embed_bulk.sh` (запуск
за владельцем, одна карта `10.3.1.11:8000`).

| величина | значение |
|---|---|
| остаток | ≈ 7 858 166 |
| ожидаемая скорость (одна карта, HOWTO §3) | **168** стр/с |
| ETA bulk | 7 858 166 / 168 ≈ **46 780 с ≈ 13,0 ч** |

Защита от повтора ошибки: `embed_tick_guard.sh` (порог
`EMBED_TICK_MAX_REMAINING=100000`) останавливает такт на большом остатке и
называет bulk.
