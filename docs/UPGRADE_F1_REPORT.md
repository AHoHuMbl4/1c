# Ф1: SereneDB 26.08.1 на песочнице — отчёт замеров

Дата: 2026-08-22. Исполнитель: cursor-agent (dev, `claudedev`). Бой `:7890` **не тронут**.

Песочница: `work/sandbox-26081`, порт **7895**, бинарь **26.08.1**, копия `store.db` dev.

---

## Окружение

| Параметр | Значение |
|---|---|
| Бой dev | SereneDB **26.07.3**, `:7890` — не изменялся |
| Песочница | SereneDB **26.08.1**, `:7895`, `--memory_limit=40 GiB` |
| Корпус замеров | `search_corpus.emb` **66 823** × `FLOAT[1024]`, norm≈1.0001 (sample) |
| Синтетика okna | `f1_okna` **1 230 000** × `FLOAT[1024]` |
| Эмбеддер (живой `/etc/1c-embed.env`) | **Qwen3-Embedding-8B**, dim=1024 |

---

## §3 Совместимость (26.07.3 → 26.08.1)

Источник: `results/compat.tsv`.

| Метрика | Sandbox :7895 | Prod :7890 | Совпало |
|---|---|---|---|
| search_corpus | 103 808 | 103 808 | yes |
| search_tables | 231 | 231 | yes |
| resolver_index | 115 151 | 115 151 | yes |
| search_entity_alias | 178 | 178 | yes |
| text «продажи» | 1 940 | 1 940 | yes |
| emb NOT NULL | 66 823 | 66 823 | check |

**Вердикт:** **GO** — снимок читается, BM25 совпал.

---

## §4 IVF — ворота 1

### 4.1 Порог 5 000 → 6 000 (`results/ivf-threshold.tsv`)

| Строк | dim | metric | wall_sec | peak_rss_kb |
|---|---|---|---|---|
| 5 000 | 1024 | ip | **3** | 2 300 208 (~2,2 ГБ) |
| 6 000 | 1024 | ip | **8** | 2 235 044 (~2,1 ГБ) |

На 26.07.3 6k не завершалось (+ГБ RAM). **Вердикт:** **GO** — порог ушёл.

### 4.2 Отменяемость (`results/ivf-cancel.tsv`)

| Проверка | 26.08.1 |
|---|---|
| `pg_cancel_backend(pid)` после ≥60 с | **f** |
| `active_builds` через 15/30/60 с | **1 / 1 / 1** |
| RSS kb (стабилен) | ~4 032 808 |

**Доки:** `search_docs` по `pg_cancel_backend` / async index build — **штатного способа отмены фоновой сборки inverted/IVF не описано**. Блог [State of Serene, July 2026 — CREATE INDEX stopped blocking your writes](https://blog.serenedb.com/state-of-serene-2026-07#create-index-stopped-blocking-your-writes): сборка идёт параллельно записям, клиент может отключиться — согласуется с `client_alive=no`, а `pg_stat_activity` всё ещё показывает активный `CREATE INDEX`.

**Вердикт:** **NO-GO** — отменяемость не восстановлена; вход в процедуру **Ф5**: сборки IVF только при запасе памяти, без опоры на cancel.

### 4.3 WAL + рестарт (`results/ivf-wal.tsv`)

| Проверка | 26.08.1 |
|---|---|
| `store.db.wal` bytes | 419 972 |
| Рестарт `--keep-wal` | **OK**, startup_sec=**0** |
| `count(search_corpus)` после | 103 808 |

**Вердикт:** **GO** — OOM-петли нет.

### 4.4 Объём okna 1,23M (`results/ivf-okna-scale.tsv`)

| Метрика | Значение |
|---|---|
| wall_sec | **74** |
| peak_rss_kb | **13 606 708** (~13,0 ГБ) |

---

## §5 Квантизация и recall

Данные: `f1_corpus_vec` = реальные `search_corpus.emb`. Сборка (`results/quant-build.tsv`): ip 10 с, sq8 6 с, rabitq 7 с.

**Exact baseline:** таблица `f1_corpus_exact` **без inverted-индекса**, полный перебор `row_number() OVER (ORDER BY emb <#> q)` — штатной session-setting «force exact scan» в доках (`maintenance#session-settings`, `vector-search`) **нет**; запрос к базовой таблице при наличии IVF-индекса маршрутизируется в ANN.

### Recall@10 (`results/quant-recall.tsv`, nprobe=8 default)

| metric | recall@10 | queries |
|---|---|---|
| ip_none | **1.0** | 50 |
| sq8 | **1.0** | 50 |
| rabitq | **1.0** | 50 |

### Сетка sdb_nprobe × латентность (`results/quant-grid.tsv`)

Медиана ms, 5 прогонов, один query-k; recall@10=**1.0** на всех точках.

| index | nprobe | median_ms |
|---|---|---|
| ip | 4 | 216 |
| ip | 16 | 203 |
| ip | 32 | 209 |
| sq8 | 4 / 16 / 32 | 219 / 219 / 214 |
| rabitq | 4 / 16 / 32 | 209 / 207 / 212 |

---

## §6 Фичи (`results/features.tsv`, доп. `export-import.tsv`)

| Фича | Результат |
|---|---|
| solr_synonyms короткий | OK |
| solr_synonyms 260 строк | OK |
| RRF / `rank() OVER` | OK |
| REFRESH (duckdb) | `es_refresh` |
| EXPORT DATABASE | **OK** — 340 файлов, `schema.sql` + `load.sql` в `results/export-test2/` |
| IMPORT DATABASE | **FAIL** — `ERROR: syntax error at or near ")"` (в `schema.sql` inverted-индексы экспортируются как `USING inverted ();`) |
| IMPORT одной таблицы (COPY) | **OK** — `search_entity_alias` 178=178 |

---

## Новые замеры (22.08)

### Массовая векторная запись (`results/bulk-embed.tsv`)

| Тест | Результат |
|---|---|
| CTAS `FLOAT[1024]` 64 / 10 000 / **100 000** строк | **OK** (на 26.07.3 падало `Vector::SetSize out of range` уже при >16–32 строк) |
| `ai_embed` batch **64** | **185,6** строк/с |
| `ai_embed` batch **256** | **308,6** строк/с |

TEMPORARY SECRET с уникальным именем (`f1_emb_*`); модель по `/etc/1c-embed.env` — **Qwen3-Embedding-8B**.

**Вывод:** на 26.08.1 массовый пересчёт **существенно быстрее** — исчез лимит CTAS, `ai_embed` принимает batch 256 (против потолка 16 на 26.07.3).

### Точный kNN vs IVF на 1,23M (`results/okna-knn.tsv`)

Вектор-запрос: реальный `search_corpus.emb` (norm≈1). Медиана ms, 3 прогона.

| mode | nprobe | median_ms |
|---|---|---|
| **exact** (без индекса) | 0 | **1740** |
| ivf ip | 4 | 2605 |
| ivf ip | 16 | 1936 |
| ivf ip | 32 | 2098 |

Точный скан — **~1,7 с** (секунды, не миллисекунды). На этом объёме IVF при nprobe 4–32 **не быстрее** exact; **IVF для okna-масштаба не обязателен** по латентности, если 1–2 с допустимы.

---

## Ворота 1 — GO/NO-GO

| # | Критерий | Вердикт | Доказательство |
|---|---|---|---|
| 1 | Порог 5→6k ушёл | **GO** | `ivf-threshold.tsv`: 6k за 8 с, ~2,1 ГБ |
| 2 | Сборка отменяется | **NO-GO** | `ivf-cancel.tsv`: cancel **f**, build active 60+ с |
| 3 | Рестарт после прерванной сборки | **GO** | `ivf-wal.tsv`: OK, smoke count |
| 4 | Совместимость store.db | **GO** | `compat.tsv` |

**Итог векторной части:** **условный GO** — порог и масштаб okna починены, recall/quant OK, но **cancel NO-GO** → Ф5: только с запасом RAM; полный IMPORT DATABASE блокирован багом export inverted DDL.

**Ответы на новые вопросы:**

1. **Массовый пересчёт:** да, 26.08.1 быстрее — CTAS до 100k OK, ai_embed **309 строк/с** при batch 256.
2. **IVF на okna:** exact **1,74 с** на 1,23M; IVF не даёт выигрыша по latency в замере — можно жить на exact до большего масштаба.

---

## Артефакты

| Путь | Содержание |
|---|---|
| `work/sandbox-26081/f1-run-all.sh` | полный прогон (DROP по одному объекту) |
| `work/sandbox-26081/f1-finish.sh` | дозамеры recall/export/bulk/okna |
| `work/sandbox-26081/results/*.tsv` | все таблицы замеров |
| `work/sandbox-26081/results/export-test2/` | EXPORT DATABASE (340 файлов) |

Повтор:

```bash
bash work/sandbox-26081/f1-finish.sh   # песочница :7895 должна быть up
```
