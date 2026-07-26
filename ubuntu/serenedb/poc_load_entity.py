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

def _odata_auth(req):
    """Добавить Bearer шлюза. Один способ на всех клиентов OData.

    Шлюз стал fail-closed (без токена не стартует и отвечает 401). Токен был роздан
    только сборщику индекса — остальные клиенты продолжали ходить без заголовка, и
    канал к 1С молча разорвался: преполёт возвращал None, синк грузил ноль сущностей,
    юнит при этом не падал. Поэтому заголовок ставится здесь, а не в каждом вызове.
    """
    if isinstance(req, str):
        req = urllib.request.Request(req)      # вызывают и строкой, и объектом
    tok = os.environ.get("ODG_GATEWAY_TOKEN", "")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    return req


ODATA = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres")
CSV_DIR = os.environ.get("CSV_DIR", "/var/lib/serenedb")
PAGE = 1000


_KEYS_CACHE = {}


def declared_key(entity_set):
    """Объявленный ключ сущности из `$metadata` — источник правды, в т.ч. составной."""
    if not _KEYS_CACHE:
        try:
            xml = urllib.request.urlopen(
                _odata_auth(ODATA + "/$metadata"), timeout=300).read().decode("utf-8", "replace")
        except Exception:                       # noqa: BLE001
            return []
        for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
            km = re.search(r"<Key>(.*?)</Key>", m.group(2), re.S)
            _KEYS_CACHE[m.group(1)] = (
                re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1)) if km else [])
    return _KEYS_CACHE.get(entity_set, [])


def _order_by(entity_set):
    """Порядок страниц — по ОБЪЯВЛЕННОМУ ключу, а не по предположению про `Ref_Key`.

    Без сортировки `$skip/$top` не гарантирует одинаковый порядок между страницами:
    строки перекрываются, а часть теряется НАВСЕГДА — витрина тихо неполная, суммы
    тихо заниженные. Прежний вариант знал только `Ref_Key`; у 3121 типа из 4585 ключ
    составной, а у 497 нет ни одной Guid-колонки, и для них сортировки не было вовсе.
    """
    key = declared_key(entity_set)
    if key:
        # `*_Type` — служебные спутники ссылок, сортировать по ним смысла нет
        cols = [k for k in key if not k.endswith("_Type")] or key
        return ",".join(cols)
    url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(
        {"$format": "json", "$top": "1"}
    )
    try:
        v = json.load(urllib.request.urlopen(_odata_auth(url), timeout=120)).get("value", [])
    except Exception:
        return None
    return "Ref_Key" if v and "Ref_Key" in v[0] else None


def count_of(entity_set):
    """Сколько строк в 1С. Нужно, чтобы сверить выгрузку и не принять неполную за полную."""
    url = "%s/%s/$count" % (ODATA, urllib.parse.quote(entity_set))
    try:
        return int(urllib.request.urlopen(_odata_auth(url), timeout=120).read().decode().strip())
    except Exception:                           # noqa: BLE001
        return -1


def fetch_all(entity_set):
    """Выгрузить сущность целиком, со сверкой количества.

    Короткая страница НЕ означает конец данных: замерено — под нагрузкой (сразу после
    переписи из 4585 запросов) 1С вернула 517 строк вместо 1000 в середине выгрузки, и
    прежний код на этом останавливался. Итог: 19 517 строк из 23 878, витрина тихо
    неполная, суммы тихо заниженные, ошибок в журнале ноль. Повторный прогон отдал все
    23 878 — то есть дефект плавающий, а такой опаснее постоянного.

    Поэтому: идём до ПУСТОЙ страницы и сверяем итог с `$count`. Расхождение — ошибка,
    а не «загрузили сколько получилось».
    """
    order = _order_by(entity_set)
    expected = count_of(entity_set)
    rows, skip, short_pages = [], 0, 0
    while True:
        params = {"$format": "json", "$top": str(PAGE), "$skip": str(skip)}
        if order:
            params["$orderby"] = order  # стабильный порядок → страницы не перекрываются
        url = f"{ODATA}/{urllib.parse.quote(entity_set)}?" + urllib.parse.urlencode(params)
        v = json.load(urllib.request.urlopen(_odata_auth(url), timeout=120)).get("value", [])
        if not v:
            break
        rows.extend(v)
        skip += len(v)
        if len(v) < PAGE:
            short_pages += 1
            # Короткая страница в середине — признак нагрузки, а не конца. Продолжаем,
            # пока не придёт пустая или пока не набрали ожидаемое количество.
            if expected >= 0 and len(rows) >= expected:
                break
            if expected < 0 and short_pages > 1:
                break
    if expected >= 0 and len(rows) != expected:
        raise RuntimeError(
            "%s: выгружено %d строк, в 1С %d — выгрузка неполная" % (entity_set, len(rows), expected))
    return rows


def published_entity_sets():
    """Множество имён entity set, РЕАЛЬНО опубликованных в OData (служебный документ) — источник
    правды об именах сущностей. Нужен, чтобы валидировать рукописный выбор против реальности, а не
    верить памяти. Возвращает None при сетевой ошибке (тогда преполёт пропускается — без ложной тревоги)."""
    try:
        url = f"{ODATA}/?" + urllib.parse.urlencode({"$format": "json"})
        doc = json.load(urllib.request.urlopen(_odata_auth(url), timeout=60))
        return {e.get("name", "") for e in doc.get("value", []) if e.get("name")}
    except Exception:
        return None


def safe_col(name):
    """Безопасное имя колонки для ЛЮБОГО алфавита.

    Раньше здесь был диапазон «латиница + русская кириллица»: на японской, китайской
    или греческой конфигурации ВСЕ имена схлопывались в одно (`catalog`, `col`), и
    каждая следующая сущность затирала предыдущую. Проверять принадлежность к алфавиту
    надо средствами Unicode, а не перечислением букв.
    """
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


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
    # Узлы-ПАПКИ иерархии (группы номенклатуры, категории, регионы) раньше отбрасывались
    # как «не бизнес-строки». Для коробки это неверно: требование владельца — «информация
    # должна быть вся», а про группы спрашивают ровно так же, как про элементы («что в
    # группе Электроника», «какие группы товаров есть»). Замерено: на одном справочнике
    # это 4361 строка из 23 878 — 18% данных, выброшенных молча.
    # Папки остаются различимы: колонка IsFolder есть в витрине, поиск её видит.
    where = ""
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
