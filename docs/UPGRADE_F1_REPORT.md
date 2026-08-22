# Ф1: SereneDB 26.08.1 на песочнице — отчёт замеров

Дата: 2026-08-22. Исполнитель: окно разработки dev (`claudedev`). Оркестратор
перепроверяет цифры независимо.

---

## Статус сессии

| Шаг | Статус | Как измерено |
|---|---|---|
| 1. Tarball 26.08.1 | **готово** | `stat`: **38 224 045** байт, `work/sandbox-26081/serenedb-26.08.1-linux-amd64.tar.gz` |
| 2. Песочница `:7895` | **готово** | `sandbox.conf`; `start-sandbox.sh [--keep-wal]` |
| 3. Копия `store.db` | **готово** | 10 829 967 360 байт; бой не тронут |
| 4–6. Прогон | **см. results/** | `bash work/sandbox-26081/f1-run-all.sh` |

**Методика (правки 22.08):**

- **Cancel:** `f1_cancel500k` (500 000 × 1024), `pg_cancel_backend` после ≥60 с активной сборки.
- **WAL:** рестарт с `--keep-wal` (не переименовывать `store.db.wal`).
- **Recall:** exact = `f1_corpus_vec ORDER BY emb <#> q` (таблица без inverted-пути); approx = `f1_corpus_*_idx`; векторы — `search_corpus.emb` (66 823 строк). Сетка: `sdb_nprobe` / `sdb_rerank_factor` (доки maintenance#session-settings).

```bash
bash /srv/1c/work/sandbox-26081/f1-run-all.sh
```

---

## Окружение (факты оркестратора — не перемерялись)

| Параметр | Значение |
|---|---|
| Бой dev | SereneDB **26.07.3**, `:7890`, юнит `serenedb`, `store.db` 11 ГБ в `/var/lib/serenedb/engine_duckdb` — **не тронут** |
| okna корпус | **1,23 млн** строк (оркестратор) |
| klient-1 корпус | **18,3 млн** (оркестратор) |
| Эмбеддер | Qwen3-Embedding-4B, **dim=1024**, norm≈1 (оркестратор) |
| dev RAM / диск | 62 ГБ / **180 ГБ** свободно (оркестратор) |

Песочница: `--memory_limit=40.0 GiB` (в `sandbox.conf`), `--cpu_threads=6`, `--io_threads=4`, журнал в `work/sandbox-26081/logs/`.

---

## Базовая линия боя dev (`:7890`) — [замер 22.08]

Источник: `psql host=127.0.0.1 port=7890`, файл `work/sandbox-26081/baseline-prod.tsv`.

| Метрика | Значение | SQL |
|---|---|---|
| version | PostgreSQL 18.3 (SereneDB **26.07.3**) | `SELECT version()` |
| search_corpus | **103 808** | `count(*)` |
| search_tables | 231 | |
| resolver_index | 115 151 | |
| search_entity_alias | 178 | |
| emb NOT NULL | 66 823 | `emb FLOAT[1024]` |
| текстовый поиск «продажи» | **1 940** | `count(*) FROM search_idx WHERE doc @@ 'продажи'` |
| duckdb_tables (не internal) | 1 896 | |

Примечание: dev-контур (ut_test/postgres) **не** содержит 1,23 млн строк okna — масштаб okna в §4 воспроизводится **синтетикой** `range(1230000)` × `FLOAT[1024]` на песочнице, как указано в `PLAN_UPGRADE_NATIVE.md` Ф1.

---

## §3 Совместимость данных (26.07.3 → 26.08.1)

**Ожидаемая проверка** (после запуска 26.08.1 на копии):

1. `SELECT version()` содержит `26.08.1`
2. Count'ы таблиц = baseline-prod (таблица выше)
3. `count(*) FROM search_idx WHERE doc @@ 'продажи'` = **1940**
4. Zstd `.col` layout (изменение в 26.07.5) — неявно: если count'ы и BM25 совпали, снимок читается

| Метрика | Sandbox :7895 | Prod :7890 | Совпало |
|---|---|---|---|
| *(заполнится f1-run-all.sh)* | | | |

---

## §4 IVF — ворота 1

Сценарий: `docs/SERENEDB_IVF_ISSUE_RU.md`, адаптация под **dim=1024**, `metric='ip'`
(нормированные векторы, оркестратор).

### 4.1 Порог 5 000 → 6 000

| Строк | dim | metric | Ожидание 26.07.3 | Результат 26.08.1 |
|---|---|---|---|---|
| 5 000 | 1024 | ip | ~1 с, 0 МБ прироста | wall=… peak_rss_kb=… |
| 6 000 | 1024 | ip | не завершилось, +ГБ RAM | wall=… peak_rss_kb=… |

Измерение: `measure-cmd.sh` — wall_sec + peak RSS всех процессов с `flagfile=…/sandbox.conf`, потолок **40 ГБ** → kill.

### 4.2 Отменяемость

Таблица **500 000** строк (`f1_cancel500k`), сборка `f1_cancel500k_idx`. После обнаружения
backend pid — пауза ≥60 с, затем `pg_cancel_backend`. Лог: `results/ivf-cancel.tsv`.

| Проверка | 26.07.3 | 26.08.1 |
|---|---|---|
| `pg_cancel_backend(pid)` | `t`, работа продолжается | … |
| RSS через 15/30/60 с после cancel | растёт | … |

### 4.3 WAL + рестарт

После cancel-теста: `stop-sandbox.sh`, затем `start-sandbox.sh --keep-wal` (WAL **не**
переименовывается). Лог: `results/ivf-wal.tsv`.

| Проверка | 26.07.3 | 26.08.1 |
|---|---|---|
| `store.db.wal` после прерванной сборки | есть | bytes=… |
| Рестарт песочницы | OOM-петля | OK/FAIL, startup_sec=… |

### 4.4 Объём okna (~1,23 млн × 1024)

| Метрика | Значение | Как |
|---|---|---|
| Строк | 1 230 000 | `CREATE TABLE … FROM range(1230000)` |
| wall_sec | … | measure-cmd, timeout 3600 с |
| peak_rss_kb | … | measure-cmd |
| index size | … | `duckdb_indexes().estimated_size` |

---

## §5 Квантизация (нормированные + ip)

Доки: `sql/indexes/inverted/vector-search#quantization`. Данные: `f1_corpus_vec` =
`search_corpus.emb` (NOT NULL). Exact baseline — запрос к **таблице**, не к `*_idx`.

| quant | Сборка 50k×1024 | recall@10 vs exact | Примечание |
|---|---|---|---|
| none (ip) | … | … | baseline |
| sq8 | … | … | |
| rabitq | … | … | |

Сетка `sdb_nprobe` × `sdb_rerank_factor`: файл `results/quant-grid.tsv` (если прогон завершён).

Запрос ANN: оператор **`<#>`**, не `<=>` (ловушка PLAN_VECTOR_CHECKS §2).

---

## §6 Наличие фич в 26.08.1

| Фича | Доки | Проверка | Результат |
|---|---|---|---|
| `solr_synonyms` короткий | create_text_search_dictionary/solr-synonyms | `CREATE … SYNONYMS='car, automobile, auto'` + `ts_lexize` | … |
| `solr_synonyms` длинный (254+ строк) | тот же | inline SYNONYMS из `search_entity_alias` (260 строк) | … |
| RRF / `RANK()` | cookbook/reciprocal-rank-fusion; PR #992 | `rank() OVER (ORDER BY …)` в SQL | … |
| `REFRESH_*` | vacuum#refreshing | `duckdb_functions()` + `VACUUM (REFRESH_TABLE)` | … |
| `EXPORT DATABASE` | export_and_import_database | export в `results/export-test/` | … |
| `IMPORT DATABASE` | тот же | *(после export — опционально)* | … |

---

## Ворота 1 — GO/NO-GO

| # | Критерий | Вердикт | Доказательство |
|---|---|---|---|
| 1 | Порог 5→6k **ушёл** (6k собирается ≤ разумного времени/памяти) | **TBD** | `results/ivf-threshold.tsv` |
| 2 | Сборка **отменяется** (`pg_cancel_backend` останавливает работу) | **TBD** | `results/ivf-cancel.tsv` |
| 3 | Рестарт после прерванной сборки **не роняет** | **TBD** | `results/ivf-wal.tsv` |
| 4 | Совместимость **store.db** 26.07.3→26.08.1 | **TBD** | `results/compat.tsv` |

**Итог:** **NO-GO (incomplete)** — бинарь 26.08.1 не получен; замеры IVF не запускались.

При финальном NO-GO после прогона — воспроизводимый отчёт вендору по образцу
`docs/SERENEDB_IVF_ISSUE_RU.md` (раздел «Воспроизведение» + таблицы выше).

---

## Артефакты

| Путь | Содержание |
|---|---|
| `work/sandbox-26081/sandbox.conf` | флаги песочницы |
| `work/sandbox-26081/extract.sh` | распаковка tarball |
| `work/sandbox-26081/start-sandbox.sh` / `stop-sandbox.sh` | жизненный цикл |
| `work/sandbox-26081/measure-cmd.sh` | wall + peak RSS |
| `work/sandbox-26081/f1-run-all.sh` | полный прогон |
| `work/sandbox-26081/baseline-prod.tsv` | эталон count'ов боя |
| `work/sandbox-26081/results/` | выход прогона (после бинаря) |

---

## Что не делали (по правилам)

- Боевой `/usr/local/bin/serened`, юнит `serenedb`, `/var/lib/serenedb` — **не изменялись**
- `.deb` не ставили; `/opt`, `/etc` — **не писали**
- okna/klient-1 — **не трогали**
