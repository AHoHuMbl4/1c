#!/usr/bin/env python3
"""Пересборка справочной витрины `banks` — проекция Catalog_КлассификаторБанков (БИК-классификатор
банков РФ) на удобную англ. схему. Идемпотентно.

Почему отдельный скрипт, а не generic-загрузчик: `banks` — витрина-ПРОЕКЦИЯ (значимые поля,
англ. имена), а `poc_load_entity` кладёт сырьё под именем сущности с кириллическими полями.
Логику выгрузки НЕ дублируем — берём общий `fetch_all` (он уже тянет со стабильной пагинацией
`$orderby=Ref_Key`, поэтому страницы OData не перекрываются: нет ни дублей, ни потерь строк).
Плюс дедуп-сеть по ref_key на укладке — тот же grain-инвариант «одна строка на объект 1С».

История: прежняя `banks` пришла кривой пагинацией — 2779 строк, но 2058 distinct ref_key
(721 банк потерян, заменён дублями). Этот скрипт восстанавливает полный справочник (2779 distinct).

Запуск:  python3 rebuild_banks.py
Env:     как у poc_load_entity (ETL_ODATA_BASE, SERENEDB_DSN, CSV_DIR).
"""
import csv, os, subprocess
from poc_load_entity import fetch_all, CSV_DIR, DSN

ENTITY = "Catalog_КлассификаторБанков"
RO_ROLE = "serene_ro"
# поле OData -> колонка витрины (проекция значимых полей; порядок = порядок колонок)
MAPPING = [
    ("Ref_Key", "ref_key"), ("Code", "code"), ("Description", "description"),
    ("IsFolder", "is_folder"), ("Parent_Key", "parent_key"), ("Город", "city"),
    ("КоррСчет", "corr_account"), ("СВИФТБИК", "swift"), ("ИНН", "inn"),
]


def main():
    rows = fetch_all(ENTITY)  # стабильная пагинация (общий фикс) → полный справочник без перекрытий
    csv_path = os.path.join(CSV_DIR, "banks.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([col for _, col in MAPPING])
        for r in rows:
            w.writerow([r.get(src) for src, _ in MAPPING])
    subprocess.run(["chown", "serenedb:serenedb", csv_path], check=False)
    sql = (
        "DROP TABLE IF EXISTS banks;\n"
        f"CREATE TABLE banks AS SELECT * FROM read_csv('{csv_path}') "
        "QUALIFY row_number() OVER (PARTITION BY ref_key ORDER BY ref_key) = 1;\n"
        f"GRANT SELECT ON banks TO {RO_ROLE};\n"
    )
    r = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1"], input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"load error: {r.stderr.strip()[:300]}")
    chk = subprocess.run(
        ["psql", DSN, "-tAc", "SELECT count(*), count(DISTINCT ref_key) FROM banks;"],
        text=True, capture_output=True,
    )
    print(f"banks пересобрана: pulled={len(rows)}  table(rows|distinct ref_key)={chk.stdout.strip()}")


if __name__ == "__main__":
    main()
