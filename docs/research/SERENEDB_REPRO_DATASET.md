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
| `export/` | `EXPORT DATABASE (FORMAT parquet, COMPRESSION zstd)` — полный слепок базы: `schema.sql`, `load.sql`, `t_*.parquet` |
| `repro_build.sql` | обёртка: `SET enable_profiling='json'` (profiling_output, coverage ALL) + сама нагрузка |
| `corpus_build.sql` | нагрузка: последовательность INSERT…SELECT по большим таблицам |
| `probe_finalize.sql` | `EXPLAIN ANALYZE` финализы зависающего statement-а из параллельной сессии |
| `reloptions.txt` | дамп `pg_class.reloptions` |
| `serened.conf` | конфиг движка |

## 4. Воспроизведение

1. Поднять SereneDB 26.08.1.
2. Развернуть слепок: `IMPORT DATABASE 'export';` (или вручную: `schema.sql`, затем `load.sql`).
3. Запустить нагрузку: `psql "host=127.0.0.1 port=<ваш_порт> user=postgres dbname=postgres" -f repro_build.sql`.
4. Первый час statement-ы завершаются (psql пишет `INSERT 0 N`, `Time: … ms`); монолитный шаг идёт долго — это норма.
5. Проблемное окно (~60–70 мин от старта нагрузки): из второй сессии — `pg_stat_activity`, `pg_cancel_backend`, параллельно CPU-дельту `/proc/PID/stat`. Ожидание: каталог голодает, cancel не работает, CPU активен, statement не завершается.
6. Для разбора плана финализы — `probe_finalize.sql` из второй сессии.

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
