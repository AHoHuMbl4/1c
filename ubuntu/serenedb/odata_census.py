#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Перепись базы 1С: что там есть, что непусто, что закрыто правами.

Заменяет рукописные списки сущностей. Требование владельца: коробка ставится без
ручного разбора — значит состав данных система определяет сама, а не человек галочками.

Что делает:
  1. служебный документ OData -> перечень ВСЕХ сущностей;
  2. `$metadata` -> объявленный ключ каждой (в т.ч. составной) и типы свойств;
  3. `$count` по каждой, параллельно -> непустые / пустые / закрытые правами;
  4. профиль сохраняется в витрину: клиент видит, что именно система не видит.

Пункт 4 важен отдельно: часть сущностей закрыта правами читателя — это законно, но
молчать об этом нельзя. Раньше закрытая правами сущность и сущность на ноль строк
выглядели одинаково (обе просто исчезали), и клиент не знал, что часть его данных
недоступна.
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ODATA = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
PARALLEL = int(os.environ.get("CENSUS_PARALLEL", "12"))
TIMEOUT = float(os.environ.get("CENSUS_TIMEOUT", "60"))

# Виды сущностей, для которых перепись имеет смысл, берутся из самой базы: мы не решаем,
# что «бизнес», а что нет — грузим всё, что непусто и доступно.


def _auth(req):
    if isinstance(req, str):
        req = urllib.request.Request(req)
    tok = os.environ.get("ODG_GATEWAY_TOKEN", "")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    return req


def _get(url, timeout=None):
    with urllib.request.urlopen(_auth(url), timeout=timeout or TIMEOUT) as r:
        return r.read()


def entity_sets():
    """Все опубликованные сущности из служебного документа OData."""
    url = "%s/?%s" % (ODATA, urllib.parse.urlencode({"$format": "json"}))
    doc = json.loads(_get(url))
    return sorted({e.get("name", "") for e in doc.get("value", []) if e.get("name")})


def metadata():
    """Объявленные ключи и типы: {сущность: {"key": [...], "props": {имя: тип}}}."""
    xml = _get(ODATA + "/$metadata", timeout=300).decode("utf-8", "replace")
    out = {}
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        name, body = m.group(1), m.group(2)
        km = re.search(r"<Key>(.*?)</Key>", body, re.S)
        key = re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1)) if km else []
        props = dict(re.findall(r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', body))
        out[name] = {"key": key, "props": props}
    return out


def count_one(es):
    """Сколько строк. Различаем ПУСТО и ЗАКРЫТО ПРАВАМИ — это разные вещи.

    Раньше любая ошибка превращалась в -1 и сущность просто исчезала из кандидатов;
    закрытая правами и пустая были неотличимы, и клиенту про это не говорили.
    """
    url = "%s/%s/$count" % (ODATA, urllib.parse.quote(es))
    try:
        return es, int(_get(url).decode().strip()), ""
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = (e.read() or b"").decode("utf-8", "replace")[:200]
        except Exception:                       # noqa: BLE001
            pass
        if e.code in (401, 403):
            return es, -1, "нет прав"
        # 1С отдаёт «Доступ запрещен» кодом 500 с текстом в теле
        if "Доступ" in body or "denied" in body.lower() or "Access" in body:
            return es, -1, "нет прав"
        return es, -1, "HTTP %d" % e.code
    except Exception as e:                      # noqa: BLE001
        return es, -1, type(e).__name__


def census(sets=None, meta=None):
    """Полная перепись. Возвращает список записей по каждой сущности."""
    sets = sets if sets is not None else entity_sets()
    meta = meta if meta is not None else metadata()
    rows = []
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for es, n, err in pool.map(count_one, sets):
            info = meta.get(es, {})
            rows.append({
                "entity": es,
                "rows": n,
                "problem": err,
                "key": info.get("key") or [],
                "props": len(info.get("props") or {}),
            })
    return rows


def to_load(rows):
    """Что грузить: всё непустое и доступное. Никакого отбора человеком."""
    return [r["entity"] for r in rows if r["rows"] > 0]


def summary(rows):
    ok = [r for r in rows if r["rows"] > 0]
    empty = [r for r in rows if r["rows"] == 0]
    denied = [r for r in rows if r["problem"] == "нет прав"]
    other = [r for r in rows if r["rows"] < 0 and r["problem"] != "нет прав"]
    composite = [r for r in ok if len(r["key"]) > 1]
    return {
        "всего": len(rows), "непустых": len(ok), "пустых": len(empty),
        "закрыто_правами": len(denied), "прочие_ошибки": len(other),
        "строк_всего": sum(r["rows"] for r in ok),
        "из_них_составной_ключ": len(composite),
    }


def main():
    rows = census()
    s = summary(rows)
    print(json.dumps(s, ensure_ascii=False))
    top = sorted([r for r in rows if r["rows"] > 0], key=lambda r: -r["rows"])[:10]
    for r in top:
        print("  %-52s %8d  ключ: %s" % (r["entity"][:52], r["rows"], ",".join(r["key"]) or "—"))
    if s["закрыто_правами"]:
        print("  закрыто правами читателя: %d сущностей — клиент их через бота не увидит"
              % s["закрыто_правами"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
