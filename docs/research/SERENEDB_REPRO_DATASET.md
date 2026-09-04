# SereneDB 26.08.1: датасет для воспроизведения деградации под длительной нагрузкой

## 1. Окружение

- `SELECT version();` → `PostgreSQL 18.3 (SereneDB 26.08.1)`.
- ~40 ядер CPU, RAM 128 ГБ, NVMe. Конфиг движка — `serened.conf` (в датасете).
- `row_group_size` нигде не менялся: дефолт 122 880 (в DDL нет WITH-опций; дамп `pg_class.reloptions` — `reloptions.txt` в датасете).

## 2. Симптомы

Под длительной тяжёлой нагрузкой (массовый INSERT…SELECT по большой таблице; statement-ы того же класса в начале прогона идут минутами и завершаются):

1. **Statement перестаёт завершаться** после ~60–70 мин непрерывной нагрузки. CPU при этом активен — 12–40 ядер (замер дельтой utime+stime из `/proc/PID/stat`). Случаи: 65+ мин при ~20 ядрах; 22+ мин при 32 ядрах.
2. **Каталог голодает**: `pg_stat_activity` из новой сессии не отвечает 600+ с; `SELECT … FROM pg_class` висит >35 с.
3. **`pg_cancel_backend` / `pg_terminate_backend` не прерывают** зависший statement. Возвращает в рабочее состояние только рестарт процесса serened.

Не симптом: длительность statement-а сама по себе — здоровый монолитный шаг того же прогона идёт 4ч19м и завершается. Проблема — после часа нагрузки statement-ы перестают завершаться вовсе.

Попутно, в том же окне нагрузки ловилась ошибка `dict_fsst` — несоответствие размера словаря `263799 > 262136` (order-INSERT, строка `corpus_build.sql:1532`, после ~275 МБ записанных доков). Транзиентная: изолированный повтор того же оператора проходил, `CHECKPOINT` в чистом состоянии чист.

## 3. Состав датасета

Путь в бакете: `serenedb-repro-20260903/`

| Файл | Что это |
|---|---|
| `export/schema.sql` | DDL всех 306 таблиц |
| `export/load.sql` | COPY FROM для загрузки (запускать из каталога `export/`) |
| `export/manifest.txt` | слаг файла → имя таблицы (латинский слаг ↔ исходное имя) |
| `export/<префикс>_<NNN>.parquet` | данные 306 таблиц: 277 витрин (`document_*`, `accumulationregister_*`, `catalog_*`, `chartofaccounts_*`, `informationregister_*`) + 29 `search_*`; пофайловый `COPY … TO parquet (COMPRESSION zstd)` |
| `$metadata` | XML-снимок метаданных 1С (OData edmx, 819 EntityType, 890 387 Б, md5 `3f396ff1…`) — единственная внешняя зависимость нагрузки: `read_text(:'gate' \|\| '/$metadata')` (corpus_build.sql:35). У нас такт берёт его локальным файлом из packet-meta, снимок пишет packet_apply |
| `export-extra/` | довесок 04.09: 74 таблицы витрины, не вошедшие в первый слепок — `constant_*` (32), `documentjournal_*` (14), `chartofcharacteristictypes_*` (10), `chartofcalculationtypes_*` (8), `exchangeplan_*` (8), регистры бухгалтерии/расчёта (2); `schema_extra.sql` + `load_extra.sql` + `manifest_extra.txt` + parquet, слаги 307–380. Первый слепок нёс 277 из 351 источника `search_sources`, и замок `corpus_build.sql:978` («источники исчезли из витрины») останавливал прогон. Все 74 файла сверены: строк в parquet = строк в таблице-источнике |
| `repro_build.sql` | обёртка: `SET enable_profiling='json'` (profiling_output, coverage ALL) + сама нагрузка |
| `corpus_build.sql` | нагрузка: последовательность INSERT…SELECT по большим таблицам |
| `probe_finalize.sql` | `EXPLAIN ANALYZE` финализы из параллельной сессии |
| `reloptions.txt` | дамп `pg_class.reloptions` |
| `serened.conf` | конфиг движка |

Слепок снят пофайлово, а не `EXPORT DATABASE`: на 26.08.1 `EXPORT DATABASE` падает целиком с `ERROR: Could not find node in column segment tree! Attempting to find row number "5267610" in 42 nodes` (после 523 файлов, на таблице `backup_corpus_emb`, ~5.27M строк). Ещё один кандидат к вашему фиксу. Вектора, бэкапы и tmp-таблицы в датасет не входят — для репро деградации не нужны, `corpus_build` строит корпус из витрин. Индексы не включены — `corpus_build` создаёт свои объекты сам.

Обход от разработчика SereneDB (03.09): `SET force_dict_fsst_mode = 'AUTO_NATIVE'` — применяется на нашей стороне до фикса.

## 4. Воспроизведение

1. Поднять SereneDB 26.08.1.
2. Развернуть слепок: из каталога `export/` — `psql … -f schema.sql`, затем `psql … -f load.sql`.
3. Развернуть довесок из `export-extra/` тем же способом (`psql … -f schema_extra.sql`, затем `psql … -f load_extra.sql` из этого каталога) — без него прогон останавливается замком `corpus_build.sql:978` «источники исчезли из витрины».
4. Положить `$metadata` в отдельный каталог (имя файла — ровно `$metadata`); каталог пойдёт в `gate` при запуске (слэш в конце не нужен — скрипт сам дописывает `/$metadata`).
5. Исключить инкрементальный путь: `psql … -c "UPDATE search_quality SET v=0 WHERE k='changed_sources_ok';"` — иначе снятые `search_quality`/`search_refmap`/`search_corpus` могут направить скрипт в лёгкий инкремент вместо полного прохода (полный проход и есть нагрузка для репро).
6. Запустить нагрузку: `psql "host=127.0.0.1 port=<ваш_порт> user=postgres dbname=postgres" -v gate=<каталог> -f repro_build.sql` (переменная psql доезжает и внутрь `\i corpus_build.sql`; других внешних зависимостей у нагрузки нет, `ai_embed` в `corpus_build.sql` не используется).
7. Первый час statement-ы завершаются (psql пишет `INSERT 0 N`, `Time: … ms`); монолитный шаг идёт долго — это норма.
8. Проблемное окно (~60–70 мин от старта нагрузки): из второй сессии — `pg_stat_activity`, `pg_cancel_backend`, параллельно CPU-дельту `/proc/PID/stat`. Ожидание: каталог голодает, cancel не работает, CPU активен, statement не завершается.
9. Для разбора плана финализы — `probe_finalize.sql` из второй сессии.

## 5. Что уже пробовали

Рестарт serened — единственное лечение. `CHECKPOINT` в чистом состоянии проходит; ошибка `dict_fsst` изолированным повтором не воспроизводится.

## 6. Доступ к бакету (ключи временные)

```
Endpoint: fsn1.your-objectstorage.com
Region:   fsn1
Bucket:   1c-data
Path:     serenedb-repro-20260903/
Key:      S2HHLGIPZOGA8DR27TVA
Secret:   Feb6glLjNKRcfDcNZclBuiPJXWCKtdyGCC6Mz2Yl
```

Пример скачивания:

```
mc alias set h https://S2HHLGIPZOGA8DR27TVA:<SECRET>@fsn1.your-objectstorage.com
mc cp --recursive h/1c-data/serenedb-repro-20260903/ .
```
