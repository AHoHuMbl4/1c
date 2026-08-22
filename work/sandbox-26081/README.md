# Песочница SereneDB 26.08.1 (Ф1)

Отдельный `--server_directory`, порт **7895**. Бой `:7890` не трогаем.

## Быстрый старт

```bash
# 1. Скачать tarball (38 МБ) — если ещё нет
curl -fsSL -o serenedb-26.08.1-linux-amd64.tar.gz \
  'https://github.com/serenedb/serenedb/releases/download/v26.08.1/serenedb-26.08.1-linux-amd64.tar.gz'

# 2. Полный прогон Ф1
bash f1-run-all.sh
```

## Файлы

| Файл | Назначение |
|---|---|
| `sandbox.conf` | флаги (memory_limit 40 GiB, log file) |
| `extract.sh` | распаковка tarball → `./serened` |
| `start-sandbox.sh` / `stop-sandbox.sh` | жизненный цикл |
| `measure-cmd.sh` | wall time + peak RSS |
| `recall-measure.sh` / `quant-grid-measure.sh` | recall@10 и сетка nprobe |
| `f1-run-all.sh` | все замеры → `results/` |
| `baseline-prod.tsv` | эталон count'ов с `:7890` |
| `data/engine_duckdb/store.db` | копия боя 11 ГБ |

Отчёт: [`docs/UPGRADE_F1_REPORT.md`](../docs/UPGRADE_F1_REPORT.md)
