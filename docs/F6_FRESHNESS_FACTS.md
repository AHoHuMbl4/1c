# Ф6.4 — фактура: свежесть индекса для `/health` на SereneDB 26.08.1

Снято 24.08 на **локальном sandbox** (`psql :7895`,
`/srv/1c/work/sandbox-26081`, SereneDB **26.08.1**). Код `serene_ask.py` не
менялся. База: только `SELECT` / `EXPLAIN` (без `VACUUM`/`DDL`). Боевой
локальный `:7890` в момент пробы **не отвечал** (см. §3) — факты версии и
метрик сняты на sandbox той же сборки 26.08.1.

Соседний образец формата: `docs/F6_HYBRID_FACTS.md`.

## 1. Что сейчас делает `/health` (код, не движок)

Путь в `ubuntu/serenedb/serene_ask.py`:

| Функция | Роль |
|---|---|
| `_measure_health_gap` | один `SELECT` из `search_coverage` → разрыв витрина↔корпус |
| `_classify_health_gap` | если `mart_changed_ts > build_ts` в `search_quality` → `kind=freshness_lag`, `merge_pending_sec = mart_ts - build_ts` |
| `do_GET /health` | `freshness_lag` → **HTTP 200** + поле `freshness.merge_pending_sec`; `systemic` → **503** |

Это эвристика **пайплайна сборки** (витрина новее последнего такта merge), а не
возраст инвертированного индекса и не «сколько строк ещё не опубликовано
читателям `@@`».

Отдельно в ответе `/ask`: `data_age_sec = now() - build_ts` (возраст такта),
не индексный буфер.

## 2. Что говорят доки (штатные средства)

| Раздел | URL | Суть |
|---|---|---|
| VACUUM › REFRESH_* | https://docs.serenedb.com/sql/statements/vacuum#refreshing--refresh_ | `VACUUM (REFRESH_INDEX\|REFRESH_TABLE\|…)` публикует pending-записи индекса читателям |
| Maintenance › visibility | https://docs.serenedb.com/sql/indexes/inverted/maintenance#visibility-and-the-refresh-model | фон `refresh_interval` (умолч. 1000 мс) + явный REFRESH |
| Maintenance › sdb_metrics | https://docs.serenedb.com/sql/indexes/inverted/maintenance#sdb-metrics | per-index: `num_buffered_docs`, `num_live_docs`, `num_failed_commits`, …; process: `refresh_pending` / `refresh_active` |
| Maintenance › introspection | https://docs.serenedb.com/sql/indexes/inverted/maintenance#introspection | каталог: `duckdb_indexes()`, `pg_indexes` |
| Metadata › duckdb_indexes | https://docs.serenedb.com/sql/functions/duckdb_table_functions#duckdb_indexes | список индексов; **колонок возраста / last_refresh нет** |

Отдельного «возраста индекса в секундах» / `last_refresh_ts` в доках **нет**.
Ближайший штатный сигнал «ещё не searchable» — `num_buffered_docs`
(документы в writer, не закоммичены в сегменты).

## 3. Живые пробы 24.08

### 3.1 Отказ боевого локального `:7890`

```text
$ PGCONNECT_TIMEOUT=2 psql "host=127.0.0.1 port=7890 user=postgres dbname=postgres connect_timeout=2" -c "SELECT version();"
psql: error: connection to server at "127.0.0.1", port 7890 failed: timeout expired
```

Порт слушает, но accept/handshake не укладывается в 2 с (на инстансе висели
длинные чужие `psql`). **Непроверено на этом процессе** в этот заход.

### 3.2 Успех sandbox `:7895` (SereneDB 26.08.1)

```text
version → PostgreSQL 18.3 (SereneDB 26.08.1)
```

| Проба | Результат |
|---|---|
| `duckdb_indexes()` | 6 индексов, в т.ч. `search_idx` → `search_corpus`; `sql` = `USING inverted ()` (пустые скобки — известная ловушка каталога) |
| `SELECT … FROM sdb_metrics` | отвечает; колонки `metric, value, description, relation_id` |
| `sdb_index_stats` | ❌ `Table with name sdb_index_stats does not exist! Did you mean "sdb_settings"?` |
| `JOIN sdb_metrics` × `pg_class` по `search_idx` | `num_buffered_docs=0`, `num_live_docs=103808`, `num_failed_commits=0` |
| process gauges | `refresh_pending=0`, `refresh_active=0` |
| `search_quality` | `build_ts` / `mart_changed_ts` есть; `mart − build = 137` с при `buffered=0` |
| `EXPLAIN VACUUM (REFRESH_INDEX) search_idx` | план `PRAGMA` (синтаксис принят; **не исполняли**) |
| `EXPLAIN VACUUM (REFRESH_TABLE) search_corpus` | то же |

**Ключевой разъезд слоёв** на той же базе: эвристика пайплайна дала бы
`merge_pending_sec=137`, а штатный буфер индекса — **0**. Это разные понятия;
подменять одно другим без замера на бое нельзя.

Повтор `:17890` (тот же хост): тоже `SereneDB 26.08.1`, `SELECT 1` ок — запасной
listen; метрики свежести снимались на `:7895`.

## 4. Сводка «средство → доки → 26.08.1 → `/health`»

| Средство | В доках | На 26.08.1 (sandbox) | Применимо к `/health` |
|---|---|---|---|
| `sdb_metrics.num_buffered_docs` (per index) | ✅ | ✅ `SELECT` + join `pg_class` | **да** — прямой сигнал «ещё не searchable» |
| `sdb_metrics.refresh_pending` / `refresh_active` | ✅ | ✅ | да, как process-gauge очереди refresh |
| `sdb_metrics.num_failed_commits` | ✅ | ✅ | да, как degraded при >0 |
| `duckdb_indexes()` | ✅ | ✅ список/sql | каталог есть; **возраста нет** |
| timestamp / age последнего refresh | ❌ в доках | ❌ в метриках | нет штатного поля |
| `VACUUM (REFRESH_INDEX)` | ✅ | синтаксис `EXPLAIN` ок; исполнение **не** гоняли | **не** звать из GET `/health` (побочный эффект) |
| `VACUUM (REFRESH_TABLE)` | ✅ | синтаксис ок | **запрещён** на корпусе с вектором — см. §5 |
| `search_quality.build_ts` / `mart_changed_ts` | наш слой | ✅ | текущая эвристика; второй рубеж до A/B |

## 5. Ловушки

1. **`REFRESH_TABLE` на большой таблице / корпусе** — публикация одним куском,
   не «уборка». Уже роняло движок (34 ГБ): `HOW_NOT_TO` §2.4;
   `CHECKLIST_SEARCH_FIX` / `SERVER_HANDOFF`: только `REFRESH_INDEX`, и то не
   из двери health.
2. **Два слоя «свежести»** — лаг merge пайплайна (`mart`/`build`) ≠ буфер
   inverted (`num_buffered_docs`). На sandbox они разошлись (137 с vs 0).
3. **`duckdb_indexes().sql`** — `USING inverted ()`, состав колонок каталог не
   хранит (старая ловушка).
4. **Фон `refresh_interval=1000`** обычно сам публикует; явный REFRESH нужен
   после bulk load перед чтением, не как polling `/health`.
5. Боевой okna / klient-1 в этом заходе **не мерялись** (без ssh); перенос
   вывода — после той же `SELECT` на их `:7890`.

## 6. Минимальный следующий кодовый шаг

**Реализовано за флагом (24.08):** `ASK_HEALTH_NATIVE_FRESHNESS=0` (умолч.), имя индекса `ASK_HEALTH_SEARCH_IDX` (умолч. `search_idx`); при `=1` — поля `freshness.index_buffered_docs` / `index_failed_commits` / `refresh_pending` / `refresh_active` рядом с `merge_pending_sec`; эвристика `_classify_health_gap` не снята; `VACUUM (REFRESH_*)` из `/health` не зовётся. Бой не включён.

Предложение (флаг, старое рядом до замера):

1. Env, напр. `ASK_HEALTH_NATIVE_FRESHNESS=1`.
2. При флаге читать штатно (один SQL):

```sql
SELECT c.relname,
       MAX(CASE WHEN m.metric = 'num_buffered_docs' THEN m.value END) AS buffered,
       MAX(CASE WHEN m.metric = 'num_failed_commits' THEN m.value END) AS failed
FROM sdb_metrics m
JOIN pg_class c ON c.oid = m.relation_id
WHERE c.relname = 'search_idx'   -- имя из конфига корпуса, не хардкод базы
GROUP BY 1;
```

   плюс process `refresh_pending` из `sdb_metrics WHERE relation_id IS NULL`.
3. В JSON `/health`: поле вроде `freshness.index_buffered_docs` /
   `refresh_pending` вместо (или рядом с) `merge_pending_sec`.
4. Пока флаг выключен или замер не сравнил поведение с `1c-bot-monitor` —
   оставить `_classify_health_gap` / `mart_changed_ts` вторым рубежом
   (как в плане Ф6.4).
5. **Не** вызывать `VACUUM (REFRESH_*)` из `/health`.

Критерий снятия эвристики: на бою A/B «дверь зелёная/жёлтая» совпадает с
ожиданием оператора не хуже текущего `merge_pending`, и ложных 503 нет.
