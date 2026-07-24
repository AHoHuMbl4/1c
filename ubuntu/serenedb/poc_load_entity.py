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


def _order_by(entity_set):
    """Ключ стабильной сортировки для пагинации. `Ref_Key` — универсальный идентификатор
    объекта 1С (уникален у любого справочника/документа). БЕЗ сортировки $skip/$top не
    гарантирует одинаковый порядок между страницами → строки перекрываются между страницами
    (наблюдали дубли ×2/×3) и часть строк вовсе теряется. Определяем ключ по данным, без хардкода."""
    url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(
        {"$format": "json", "$top": "1"}
    )
    try:
        v = json.load(urllib.request.urlopen(url, timeout=120)).get("value", [])
    except Exception:
        return None
    return "Ref_Key" if v and "Ref_Key" in v[0] else None


def fetch_all(entity_set):
    order = _order_by(entity_set)
    rows, skip = [], 0
    while True:
        params = {"$format": "json", "$top": str(PAGE), "$skip": str(skip)}
        if order:
            params["$orderby"] = order  # стабильный порядок → страницы не перекрываются
        url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(params)
        v = json.load(urllib.request.urlopen(url, timeout=120)).get("value", [])
        if not v:
            break
        rows.extend(v)
        skip += len(v)
        if len(v) < PAGE:
            break
    return rows


def published_entity_sets():
    """Множество имён entity set, РЕАЛЬНО опубликованных в OData (служебный документ) — источник
    правды об именах сущностей. Нужен, чтобы валидировать рукописный выбор против реальности, а не
    верить памяти. Возвращает None при сетевой ошибке (тогда преполёт пропускается — без ложной тревоги)."""
    try:
        url = f"{ODATA}/?" + urllib.parse.urlencode({"$format": "json"})
        doc = json.load(urllib.request.urlopen(url, timeout=60))
        return {e.get("name", "") for e in doc.get("value", []) if e.get("name")}
    except Exception:
        return None


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
    # Grain-инвариант: одна строка на объект 1С. Поверх стабильной пагинации — дедуп-сеть:
    # если страницы OData всё же перекрылись, ref_key (уникальный ключ платформы) убирает копии;
    # для сущностей без ref_key (напр. регистры) — снимаем полностью идентичные строки.
    has_ref = any(safe_col(c).lower() == "ref_key" for c in cols)
    # is_folder=true — узлы-ПАПКИ иерархии справочника 1С (регионы/группы), не бизнес-строки. Исключаем
    # для ЛЮБОГО справочника с этой колонкой (общее платформенное правило 1С, не per-entity). CAST — на
    # случай инференса строкой; COALESCE(NULL→не-папка) — сущности без is_folder (документы) не затронуты.
    # поле 1С — IsFolder (без подчёркивания); safe_col.lower() = 'isfolder'. DuckDB идентификаторы
    # регистронезависимы, поэтому ссылаемся как isfolder (совпадёт с колонкой IsFolder).
    has_folder = any(safe_col(c).lower() == "isfolder" for c in cols)
    where = " WHERE NOT COALESCE(CAST(isfolder AS BOOLEAN), false)" if has_folder else ""
    select = (
        f"SELECT * FROM read_csv('{csv_path}'){where} "
        "QUALIFY row_number() OVER (PARTITION BY ref_key ORDER BY ref_key) = 1"
        if has_ref else f"SELECT DISTINCT * FROM read_csv('{csv_path}'){where}"
    )
    sql = (
        f'DROP TABLE IF EXISTS "{table}";\n'
        f'CREATE TABLE "{table}" AS {select};\n' + grant
    )
    r = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1"], input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"load error: {r.stderr.strip()[:200]}")
    c = subprocess.run(["psql", DSN, "-tAc", f'SELECT count(*) FROM "{table}";'], text=True, capture_output=True)
    n = int(c.stdout.strip()) if c.returncode == 0 and c.stdout.strip().isdigit() else len(rows)
    # rows = grain витрины (после дедупа), rows_raw = сколько строк отдал OData (видно перекрытие страниц)
    return {"entity": es, "table": table, "rows": n, "rows_raw": len(rows), "cols": len(cols), "sec": dt}


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: poc_load_entity.py <EntitySet>  (напр. Catalog_КлассификаторБанков)")
    res = load_entity(sys.argv[1])
    print(res)


if __name__ == "__main__":
    main()
