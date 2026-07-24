#!/usr/bin/env python3
"""serene_select (Фаза 2) — генерирует список сущностей витрины ИЗ ЖИВОГО OData, не из головы.
Общие СТРУКТУРНЫЕ правила (никаких имён в коде): бизнес-объекты верхнего уровня (Catalog_/Document_,
не табличные части X_Y), не системные (…ПрисоединенныеФайлы / Удалить…), НЕПУСТЫЕ (count>0). Пишет
`serene-entities.txt` из РЕАЛЬНЫХ имён. Переносится на любую 1С-базу — что там, узнаём у OData.

Запуск:  python3 serene_select.py [min_rows]   (env как у poc_load_entity: ETL_ODATA_BASE)
"""
import concurrent.futures
import json
import os
import sys
import urllib.parse
import urllib.request

import poc_load_entity as L

OUT = os.environ.get("SELECTED_FILE",
                     os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene-entities.txt"))


def _is_business_toplevel(name):
    """Бизнес-объект верхнего уровня: Catalog_/Document_, без табличной части (X_Y), не системный.
    Структурно, без списка имён — платформенные соглашения 1С."""
    if not (name.startswith("Catalog_") or name.startswith("Document_")):
        return False
    core = name.split("_", 1)[1]
    if "_" in core:  # табличная часть (Document_X_Товары / Catalog_X_ДопРеквизиты)
        return False
    low = core.lower()
    return "присоединенныефайлы" not in low and not low.startswith("удалить")


def _count(es):
    try:
        u = L.ODATA + "/" + urllib.parse.quote(es) + "?" + urllib.parse.urlencode(
            {"$format": "json", "$top": "1", "$inlinecount": "allpages"})
        d = json.load(urllib.request.urlopen(u, timeout=60))
        c = d.get("odata.count")
        return es, (int(c) if c is not None else len(d.get("value", [])))
    except Exception:  # noqa: BLE001
        return es, -1


def main():
    min_rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    pub = L.published_entity_sets()
    if not pub:
        sys.exit("не получил список сущностей OData")
    cands = sorted(n for n in pub if _is_business_toplevel(n))
    print(f"бизнес-сущностей верхнего уровня: {len(cands)}; считаю непустые (порог {min_rows})…")
    keep = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for es, n in ex.map(_count, cands):
            if isinstance(n, int) and n >= min_rows:
                keep.append((es, n))
    keep.sort()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# СГЕНЕРИРОВАНО serene_select.py из ЖИВОГО OData (Фаза 2) — не править вручную, перегенерировать.\n")
        f.write("# Только НЕПУСТЫЕ бизнес-сущности верхнего уровня; имена — из реальности, преполёт сверяет каждый прогон.\n\n")
        f.write("\n".join(es for es, _ in keep) + "\n")
    print(f"записано непустых: {len(keep)} -> {OUT}")
    for es, n in keep[:50]:
        print(f"  {es}  ({n})")


if __name__ == "__main__":
    main()
