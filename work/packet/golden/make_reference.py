#!/usr/bin/env python3
"""Эталонный CSV для golden-пробы агента пакетного транспорта (К5).

Прогоняет сохранённые страницы OData (`fixtures/<entity>.page1.json`) через ТЕ ЖЕ
функции, что боевая выгрузка: `_flatten_nested`, `_cell`, `safe_col` и `csv.writer`
из `ubuntu/serenedb/poc_load_entity.py` — источника истины формата (PACKET_CONTRACT §7).

$metadata берётся из СНИМКА `fixtures/metadata.xml.zst` (того, что ляжет рядом с агентом
на Windows — probe.cmd распаковывает), а не из живой базы: эталон и агент разбирают
один и тот же текст.

Запуск:  python3 make_reference.py          (из каталога work/packet/golden)
Результат: reference/<entity>.csv — побайтовый эталон для `fc /b`.
"""
import csv, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "ubuntu", "serenedb"))
import poc_load_entity as poc  # noqa: E402


def _load_metadata_from_snapshot():
    """Заполнить кэши poc разбором СНИМКА, тем же regex, что poc._load_metadata."""
    import subprocess
    snap = os.path.join(HERE, "fixtures", "metadata.xml")
    if not os.path.exists(snap):  # в git лежит сжатый (20 МБ -> ~0,5 МБ)
        snap += ".zst"
    if snap.endswith(".zst"):
        p = subprocess.run(["zstd", "-d", "-c", snap], capture_output=True, timeout=120)
        if p.returncode != 0:
            raise RuntimeError("zstd -d fixtures/metadata.xml.zst: " + p.stderr.decode("utf-8", "replace"))
        xml = p.stdout.decode("utf-8", "replace")
    else:
        xml = open(snap, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        km = re.search(r"<Key>(.*?)</Key>", m.group(2), re.S)
        poc._KEYS_CACHE[m.group(1)] = (
            re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1)) if km else [])
        poc._PROPS_CACHE[m.group(1)] = re.findall(
            r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', m.group(2))


def make_reference(entity):
    """Та же цепочка, что poc.load_entity: flatten -> union колонок -> safe_col -> _cell."""
    path = os.path.join(HERE, "fixtures", entity + ".page1.json")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f).get("value", [])
    # Дополнительные страницы (page2, ...) дописываются в том же порядке, как в fetch_all.
    n = 2
    while os.path.exists(os.path.join(HERE, "fixtures",
                                      "%s.page%d.json" % (entity, n))):
        with open(os.path.join(HERE, "fixtures",
                               "%s.page%d.json" % (entity, n)), encoding="utf-8") as f:
            rows.extend(json.load(f).get("value", []))
        n += 1
    # Синтетические фикстуры (имя с подчёркивания, сущности нет в $metadata) идут с
    # entity_set=None — как в poc._flatten_nested: без разворота и без защиты шапки.
    # Боевые сущности проходят fail-closed ветку со снимком metadata.xml.
    meta_name = entity if entity in poc._PROPS_CACHE else None
    rows, _nested = poc._flatten_nested(rows, meta_name)
    if not rows:
        return 0
    cols = list(dict.fromkeys(k for r in rows for k in r.keys()))
    out = os.path.join(HERE, "reference", entity + ".csv")
    with open(out, "w", newline="") as f:      # как в poc: csv сам ставит \r\n
        w = csv.writer(f)
        w.writerow([poc.safe_col(c) for c in cols])
        for r in rows:
            w.writerow([poc._cell(r.get(c)) for c in cols])
    return len(rows)


def main():
    _load_metadata_from_snapshot()
    fx = os.path.join(HERE, "fixtures")
    entities = sorted(m.group(1) for fn in os.listdir(fx)
                      for m in [re.match(r"(.+)\.page1\.json$", fn)] if m)
    if not entities:
        sys.exit("нет фикстур fixtures/*.page1.json")
    for e in entities:
        n = make_reference(e)
        print("%-55s -> reference/%s.csv (%d строк)" % (e, e, n))


if __name__ == "__main__":
    main()
