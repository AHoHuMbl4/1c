# Датасет для воспроизведения деградации SereneDB 26.08.1 (okna)

## 1. Конфигурация

- Версия: `PostgreSQL 18.3 (SereneDB 26.08.1)`, бинарь `/usr/local/bin/serened`, systemd-юнит `serenedb`.
- Железо: LXD-контейнер, ~40 ядер, RAM 128 ГБ, NVMe. Конфиг — `serened.conf` в датасете.
- `row_group_size` нигде не менялся — дефолт 122 880 (DDL без WITH, `pg_class.reloptions` дефолтные; дамп приложен).

## 2. Что воспроизводим

Под длительной тяжёлой нагрузкой (массовый INSERT…SELECT по большой таблице):

1. **Незавершаемость statement-а** после ~60–70 мин непрерывной нагрузки: CPU активен (12–40 ядер по дельте `/proc/PID/stat`), statement не завершается. Живые случаи: 65+ мин при ~20 ядрах, 22+ мин при 32 ядрах.
2. **Голодание каталога**: `pg_stat_activity` из новой сессии не отвечает 600+ с; `SELECT … FROM pg_class` висит >35 с.
3. **`pg_cancel_backend` / `pg_terminate_backend` не работают.** Лечит только рестарт сервиса.

Не симптом: длинный statement сам по себе — здоровый монолитный шаг идёт 4ч19м и завершается. Проблема — когда после часа нагрузки statement-ы перестают завершаться вовсе.

Отдельно: ошибка `dict_fsst` (текст отправлен ранее дословно; у нас транзиентная — изолированные повторы проходили).

## 3. Состав датасета

Путь в бакете: `serenedb-repro-20260903/`

| Файл | Что это |
|---|---|
| `export/` | `EXPORT DATABASE (FORMAT parquet, COMPRESSION zstd)` — полный слепок базы (schema.sql, load.sql, t_*.parquet) |
| `repro_build.sql` | обёртка: `SET enable_profiling='json'` (profiling_output, coverage ALL) + corpus_build.sql |
| `corpus_build.sql` | тяжёлая нагрузка: многоstatement-овый INSERT…SELECT |
| `probe_finalize.sql` | EXPLAIN ANALYZE финализы из параллельной сессии |
| `reloptions.txt` | дамп `pg_class.reloptions` |
| `serened.conf` | конфиг движка |

## 4. Шаги воспроизведения

1. Поднять SereneDB 26.08.1.
2. `IMPORT DATABASE 'export';`
3. `psql … -f repro_build.sql`
4. Первый час statement-ы завершаются (лог psql пишет `INSERT 0 N`), монолитный шаг идёт долго — норма.
5. Проблемное окно (~60–70 мин): `pg_stat_activity` из второй сессии, `pg_cancel_backend`, CPU-дельта. У нас: каталог голодает, cancel не работает, CPU активен, statement не завершается.
6. `probe_finalize.sql` — план финализы параллельно.

## 5. Что пробовали

Рестарт serenedb — единственное лечение. CHECKPOINT в чистом состоянии проходит; dict_fsst изолированно не воспроизводится.

## 6. Доступ к бакету (ключи временные)

```
Endpoint: fsn1.your-objectstorage.com
Region:   fsn1
Bucket:   1c-data
Path:     serenedb-repro-20260903/
Key:      S2HHLGIPZOGA8DR27TVA
Secret:   Feb6glLjNKRcfDcNZclBuiPJXWCKtdyGCC6Mz2Yl
```
