# И0 — генератор client-gold (packet ↔ vitrine)

Задача [`docs/PLAN_TO_TARGET.md`](../docs/PLAN_TO_TARGET.md) §И0. Базовая
классификация и батч-SQL — [`ubuntu/serenedb/etalon_1c.py`](../../ubuntu/serenedb/etalon_1c.py).

## Назначение

1. **Покрытие сущностей** — `information_schema.tables` (`catalog_*`,
   `accumulationregister_*`, `document*`), не `search_tables` / не `search_corpus`.
2. **Формулировки** — шаблоны классов × сущности + живые вопросы из
   `ask_journal_text` (без подгонки под ответы бота).
3. **Эталон** — двойной счёт **packet** (`base_profile` или сырой регистр) ↔
   **vitrine** (прямой SQL по таблицам витрины). Корпус и словари поиска не
   участвуют.
4. **Выход** — `client-gold.tsv`: вопрос, эталон, источник, лаг свежести (с),
   статус сверки. Расхождения — в отдельный TSV-лог.

Роль набора в реестре gold — [`docs/GOLD_SETS.md`](../docs/GOLD_SETS.md)
(`client-gold-okna.tsv` = **приёмка**).

## Запуск

```bash
cd /srv/1c
export SERENEDB_DSN='host=127.0.0.1 port=7890 user=postgres dbname=postgres'
export PGPASSWORD=…   # из /etc/1c-mcp-reports.env на okna

python3 work/gold/test_client_gold.py

python3 work/gold/client_gold.py --dsn "$SERENEDB_DSN" build \
  --slices work/gold/slices-okna-packet.json \
  --from-journal --limit-journal 40 \
  --limit-templates 30 \
  --out ubuntu/serenedb/client-gold-okna.tsv \
  --discrepancy-log work/acceptance/runs/client-gold-discrepancies.tsv
```

На prod okna (read-only): [`run_okna.sh`](run_okna.sh).

## Оговорка OData / пакеты

На контуре okna OData-шлюза нет; эталон 1С = **живые пакеты** (след в
`base_profile` + прямой SQL по таблицам витрины после apply; для периодов —
тот же регистр, не `search_corpus`). Лаг свежести — `build_state.ts`.
Когда шлюз появится — те же срезы можно дополнить `odata.entity` в
`etalon_1c.py verify`.

Журнал `ask_journal_text` **не включает** формулировки из рабочих наборов
(`ab-gold-okna`, `ab-calendar-axis-okna`, …) — см. `load_working_gold_questions`.

## Замок

`python3 work/gold/test_client_gold.py` — офлайн: детерминированность,
пересечение с `ab-gold-okna.tsv` = 0, packet↔vitrine, формат TSV.
