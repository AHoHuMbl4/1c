#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Перепись базы 1С: что там есть, что непусто, что закрыто правами.

Заменяет рукописные списки сущностей. Требование владельца: коробка ставится без
ручного разбора — значит состав данных система определяет сама, а не человек галочками.

Что делает:
  1. служебный документ OData (HTTP) или EntitySet снимка `$metadata` (packet) ->
     перечень ВСЕХ сущностей;
  2. `$metadata` -> объявленный ключ каждой (в т.ч. составной) и типы свойств;
  3. `$count` по каждой (HTTP) или count(*) в витрине (packet), параллельно ->
     непустые / пустые / закрытые правами;
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
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

import poc_load_entity as L

ODATA = os.environ.get("ETL_ODATA_BASE", "http://127.0.0.1:6011").rstrip("/")
PARALLEL = int(os.environ.get("CENSUS_PARALLEL", "12"))
TIMEOUT = float(os.environ.get("CENSUS_TIMEOUT", "60"))
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")

# В packet-режиме закрытые сущности приходят из skipped.json агента (не из HTTP).
_SKIP_RIGHTS = frozenset({"no_read_right", "rls_filtered", "access_denied", "auth_failed"})


def _is_local():
    return L._is_local_base(ODATA)


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


def _lit(v):
    return "'" + str(v).replace("'", "''") + "'"


def _skipped_map():
    """{сущность: error} из skipped.json packet-meta; пусто, если файла нет."""
    if not _is_local():
        return {}
    path = os.path.join(ODATA, "skipped.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for e in doc.get("entities") or []:
        name = e.get("entity") or e.get("name") or ""
        if name:
            out[name] = e.get("error") or ""
    return out


def _problem_from_skip(err):
    if not err:
        return "нет прав"
    low = err.lower()
    if err in _SKIP_RIGHTS or "right" in low or "401" in low or "403" in low or "rls" in low:
        return "нет прав"
    return err


def _mart_count(entity):
    """Число строк сущности в локальной витрине; 0, если таблицы ещё нет."""
    table = L.safe_col(entity).lower()
    sql = (
        "SELECT CASE WHEN EXISTS (SELECT 1 FROM duckdb_tables() "
        "WHERE database_name = current_database() AND table_name = %s) "
        "THEN (SELECT count(*) FROM \"%s\") ELSE 0 END"
        % (_lit(table), table.replace('"', '""'))
    )
    p = subprocess.run(["psql", DSN, "-tAc", sql], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return int(p.stdout.strip() or "0")


def entity_sets():
    """Все опубликованные сущности: HTTP — служебный документ; packet — EntitySet `$metadata`."""
    if _is_local():
        pub = L.published_entity_sets()
        if pub is None:
            raise ValueError("нет снимка $metadata в %s" % ODATA)
        return sorted(pub)
    url = "%s/?%s" % (ODATA, urllib.parse.urlencode({"$format": "json"}))
    doc = json.loads(_get(url))
    return sorted({e.get("name", "") for e in doc.get("value", []) if e.get("name")})


def metadata():
    """Объявленные ключи и типы: {сущность: {"key": [...], "props": {имя: тип}}}."""
    if _is_local():
        xml = L._read_meta_xml(ODATA)
    else:
        xml = _get(ODATA + "/$metadata", timeout=300).decode("utf-8", "replace")
    if not xml:
        return {}
    out = {}
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        name, body = m.group(1), m.group(2)
        km = re.search(r"<Key>(.*?)</Key>", body, re.S)
        key = re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1)) if km else []
        props = dict(re.findall(r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', body))
        out[name] = {"key": key, "props": props}
    return out


def count_one(es, skipped=None):
    """Сколько строк. Различаем ПУСТО и ЗАКРЫТО ПРАВАМИ — это разные вещи.

    Раньше любая ошибка превращалась в -1 и сущность просто исчезала из кандидатов;
    закрытая правами и пустая были неотличимы, и клиенту про это не говорили.
    """
    if _is_local():
        skipped = skipped if skipped is not None else _skipped_map()
        if es in skipped:
            return es, -1, _problem_from_skip(skipped[es])
        try:
            return es, _mart_count(es), ""
        except Exception as e:                  # noqa: BLE001
            return es, -1, type(e).__name__
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
    skipped = _skipped_map() if _is_local() else None
    rows = []
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        if skipped is not None:
            it = pool.map(lambda es: count_one(es, skipped), sets)
        else:
            it = pool.map(count_one, sets)
        for es, n, err in it:
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
