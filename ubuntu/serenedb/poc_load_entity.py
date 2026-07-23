#!/usr/bin/env python3
"""
POC-загрузчик: любая сущность 1С (OData) -> CSV -> SereneDB -> проба агрегации.

Конфиг-нейтрально: имя сущности — аргумент, колонки берём АВТОМАТИЧЕСКИ (union полей),
ничего не хардкодим. Это доказательство конвейера и заготовка под Этап 2 (штатный
инкрементальный ETL->SereneDB). Прод-загрузчик заменит этот POC.

Запуск:  python3 poc_load_entity.py Catalog_КлассификаторБанков
Env:     ETL_ODATA_BASE (default http://127.0.0.1:6011)
         SERENEDB_DSN   (default 'host=127.0.0.1 port=7890 user=postgres')
         CSV_DIR        (default /var/lib/serenedb  — читаемо процессом serened)
"""
import csv, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

ODATA = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
CSV_DIR = os.environ.get("CSV_DIR", "/var/lib/serenedb")
PAGE = 1000


def fetch_all(entity_set):
    rows, skip = [], 0
    while True:
        url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(
            {"$format": "json", "$top": str(PAGE), "$skip": str(skip)}
        )
        v = json.load(urllib.request.urlopen(url, timeout=120)).get("value", [])
        if not v:
            break
        rows.extend(v)
        skip += len(v)
        if len(v) < PAGE:
            break
    return rows


def safe_col(name):
    # кириллица/спецсимволы -> безопасное имя колонки (без хардкода конкретных полей)
    s = re.sub(r"[^0-9A-Za-zА-Яа-яёЁ_]", "_", str(name)).strip("_")
    return s or "col"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: poc_load_entity.py <EntitySet>  (напр. Catalog_КлассификаторБанков)")
    es = sys.argv[1]
    table = safe_col(es).lower()
    csv_path = os.path.join(CSV_DIR, f"{table}.csv")

    t0 = time.time()
    rows = fetch_all(es)
    t_fetch = time.time() - t0
    if not rows:
        sys.exit(f"{es}: пусто")

    cols = list(dict.fromkeys(k for r in rows for k in r.keys()))  # union, порядок стабильный
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([safe_col(c) for c in cols])
        for r in rows:
            w.writerow([r.get(c) for c in cols])
    try:
        subprocess.run(["chown", "serenedb:serenedb", csv_path], check=False)
    except Exception:
        pass

    # загрузка + проба агрегации (read_csv авто-выводит схему)
    sql = (
        f"\\timing on\n"
        f'DROP TABLE IF EXISTS "{table}";\n'
        f"CREATE TABLE \"{table}\" AS SELECT * FROM read_csv('{csv_path}');\n"
        f'SELECT count(*) AS rows FROM "{table}";\n'
    )
    print(f"{es}: {len(rows)} строк за {t_fetch:.2f}s  ->  {csv_path}  ({len(cols)} колонок)")
    print(f"Таблица SereneDB: {table}")
    subprocess.run(["psql", DSN], input=sql, text=True)


if __name__ == "__main__":
    main()
