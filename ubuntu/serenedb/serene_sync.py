#!/usr/bin/env python3
"""
Штатный синк витрины SereneDB: выбранные сущности 1С (OData) -> таблицы SereneDB + пересборка
семантического индекса резолвера (resolver_index). Под RW (postgres). Конфиг-нейтрально —
список сущностей из /etc/1c-etl-selected.txt (те же галочки, что и ETL braine).

Сейчас — ПОЛНАЯ идемпотентная перезагрузка каждой таблицы (просто и надёжно). Инкремент по дате —
оптимизация позже (для больших документов). Запуск — systemd-таймер (ночью, после 1c-etl).

Env: SERENEDB_DSN (rw=postgres), ETL_ODATA_BASE, CSV_DIR, ALIBABA_* (для резолвера) — см. serene_report.
"""
import os
import sys

import build_resolver_index as R
import poc_load_entity as L

SELECTED = os.environ.get("SELECTED_FILE", "/etc/1c-etl-selected.txt")


def main():
    if not os.path.exists(SELECTED):
        sys.exit(f"нет файла выбора сущностей: {SELECTED}")
    ents = [ln.strip() for ln in open(SELECTED, encoding="utf-8") if ln.strip() and not ln.lstrip().startswith("#")]
    ok = empty = err = 0
    for es in ents:
        try:
            r = L.load_entity(es)
            if r["rows"] == 0:
                empty += 1
                print(f"  {es}: пусто")
            else:
                ok += 1
                print(f"  {es}: {r['rows']} строк -> {r['table']} ({r['sec']}s)")
        except Exception as e:  # noqa: BLE001 — одна сущность не должна валить весь синк
            err += 1
            print(f"  {es}: ОШИБКА {e}")
    print(f"витрина: загружено {ok}, пусто {empty}, ошибок {err} из {len(ents)}")

    # пересборка семантического индекса резолвера (Qwen text-embedding-v4 @ 1536)
    try:
        R.main()
    except SystemExit as e:
        print(f"resolver_index: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"resolver_index: ошибка пересборки {e}")


if __name__ == "__main__":
    main()
