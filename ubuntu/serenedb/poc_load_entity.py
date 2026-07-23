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


def load_entity(es, ro_role="serene_ro"):
    """Сущность 1С (OData) -> CSV -> таблица SereneDB (полная идемпотентная перезагрузка) +
    GRANT SELECT ro-роли (default privileges на SereneDB не всегда покрывают новые таблицы).
    Возвращает dict со статистикой. Переиспользуется штатным синком (serene_sync.py)."""
    table = safe_col(es).lower()
    csv_path = os.path.join(CSV_DIR, f"{table}.csv")
    t0 = time.time()
    rows = fetch_all(es)
    dt = round(time.time() - t0, 2)
    if not rows:
        return {"entity": es, "table": table, "rows": 0, "sec": dt}
    cols = list(dict.fromkeys(k for r in rows for k in r.keys()))  # union полей, порядок стабильный
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([safe_col(c) for c in cols])
        for r in rows:
            w.writerow([r.get(c) for c in cols])
    subprocess.run(["chown", "serenedb:serenedb", csv_path], check=False)
    grant = f'GRANT SELECT ON "{table}" TO {ro_role};\n' if ro_role else ""
    sql = (
        f'DROP TABLE IF EXISTS "{table}";\n'
        f"CREATE TABLE \"{table}\" AS SELECT * FROM read_csv('{csv_path}');\n" + grant
    )
    r = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1"], input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"load error: {r.stderr.strip()[:200]}")
    return {"entity": es, "table": table, "rows": len(rows), "cols": len(cols), "sec": dt}


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: poc_load_entity.py <EntitySet>  (напр. Catalog_КлассификаторБанков)")
    res = load_entity(sys.argv[1])
    print(res)


if __name__ == "__main__":
    main()
