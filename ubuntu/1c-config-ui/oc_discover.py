#!/usr/bin/env python3
"""
Discovery сущностей 1С через OData-шлюз (конфиг-нейтрально): список всех
верхнеуровневых Catalog_/Document_ с числом записей ($count), параллельно.

Результат — json [{set, kind, name, count, system}] — кэш для веб-UI настройки
(галочки «что тянуть») и для ETL. Общий модуль: используется oc_config_ui.py.
Только stdlib.
"""
import concurrent.futures as cf
import json
import os
import urllib.parse
import urllib.request

ODATA_BASE = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
TOP_PREFIXES = ("Catalog", "Document")
WORKERS = int(os.environ.get("DISCOVER_WORKERS", "12"))
TIMEOUT = float(os.environ.get("DISCOVER_TIMEOUT", "60"))

# Эвристика «служебное/системное» — для ПРЕДотметки чекбоксов (человек решает сам).
# Это не фильтр, а подсказка: снять галочки с типичного платформенного мусора.
SYSTEM_HINTS = (
    "Настройк", "Версии", "ВариантыОтчетов", "ПоляФорм", "Правила", "Предопределен",
    "Идентификатор", "Служебн", "Удалить", "Ключи", "Метаданные", "Расширени",
    "ПравилаОбмена", "Обмен", "Регламент", "ПредставленияОтчетов", "Классификатор",
    "ХранилищеДопХарактеристик", "СтруктураПодчиненн", "ЗапросыВыбораДанных",
    "ДоступныеТаблицы", "ШаблоныСообщений", "Предопределённ", "ПричиныУвольнения",
)


def http_get(path, want_json=True):
    req = urllib.request.Request(f"{ODATA_BASE}/{path}", method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if want_json else raw


def top_level_sets():
    doc = http_get("?$format=json")
    out = []
    for e in doc.get("value", []):
        n = e.get("name", "")
        if n.split("_", 1)[0] in TOP_PREFIXES and n.count("_") == 1:
            out.append(n)
    return out


def count_of(entity_set):
    try:
        return int(http_get(f"{urllib.parse.quote(entity_set)}/$count", want_json=False).strip())
    except Exception:
        return None


def is_system(name):
    return any(h.lower() in name.lower() for h in SYSTEM_HINTS)


def discover(non_empty_only=True):
    sets = top_level_sets()
    results = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for es, cnt in zip(sets, ex.map(count_of, sets)):
            if non_empty_only and (cnt == 0 or cnt is None):
                continue
            prefix, name = es.split("_", 1)
            results.append({
                "set": es, "kind": prefix, "name": name,
                "count": cnt, "system": is_system(name),
            })
    results.sort(key=lambda r: (r["system"], r["kind"], -(r["count"] or 0)))
    return results


if __name__ == "__main__":
    import sys
    data = discover()
    biz = [r for r in data if not r["system"]]
    print(f"непустых сущностей: {len(data)} (бизнес≈{len(biz)}, системных≈{len(data)-len(biz)})")
    for r in data[:40]:
        flag = "sys" if r["system"] else "   "
        print(f"  [{flag}] {r['set']}: {r['count']}")
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]
        json.dump(data, open(out, "w"), ensure_ascii=False)
        print(f"→ {out}")
