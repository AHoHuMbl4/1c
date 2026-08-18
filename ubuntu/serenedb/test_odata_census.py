#!/usr/bin/env python3
"""Оффлайн-проба odata_census: HTTP-режим и packet-режим (локальный каталог).

Без живой 1С и без обязательного psql: HTTP — ThreadingHTTPServer; packet —
временный каталог packet-meta; счётчики витрины подменяются.

Запуск: python3 test_odata_census.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import odata_census as C  # noqa: E402
import poc_load_entity as L  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append("%s:\n    получено %r\n    ожидалось %r" % (name, got, want))


META_XML = """<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><Schema>
<EntityType Name="Catalog_А"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Наименование" Type="Edm.String"/>
</EntityType>
<EntityType Name="Catalog_Закрыта"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
</EntityType>
<EntityType Name="Document_Пустой"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
</EntityType>
<EntityContainer Name="standard">
<EntitySet Name="Catalog_А" EntityType="standard.Catalog_А"/>
<EntitySet Name="Catalog_Закрыта" EntityType="standard.Catalog_Закрыта"/>
<EntitySet Name="Document_Пустой" EntityType="standard.Document_Пустой"/>
</EntityContainer>
</Schema></edmx:Edmx>"""

_COUNTS = {"Catalog_А": 42, "Document_Пустой": 0}
_ALL_ENTITIES = ["Catalog_А", "Catalog_Закрыта", "Document_Пустой"]
_SKIP_ENTITIES = set()


class _ODataH(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if u.path in ("", "/") and ("$format" in qs or "%24format" in qs):
            body = {"value": [{"name": n} for n in sorted(_COUNTS)]}
            return self._json(200, body)
        if u.path == "/$metadata":
            return self._raw(200, META_XML.encode("utf-8"), "application/xml")
        parts = u.path.strip("/").split("/")
        if len(parts) == 2 and parts[1] == "$count":
            name = urllib.parse.unquote(parts[0])
            if name not in _COUNTS:
                return self._json(404, {"error": "нет"})
            return self._raw(200, str(_COUNTS[name]).encode(), "text/plain")
        return self._json(404, {"error": "нет"})

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _raw(self, code, b, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def _start_http():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _ODataH)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def _write_meta(base_dir):
    d = os.path.join(base_dir, "probe-base")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "$metadata"), "w", encoding="utf-8") as f:
        f.write(META_XML)
    return d


def _fake_mart(entity):
    if entity in _SKIP_ENTITIES:
        raise AssertionError("закрытая сущность: _mart_count не вызывается")
    return _COUNTS.get(entity, 0)


# ── HTTP-режим (регресс) ───────────────────────────────────────────────────────
_srv, http_base = _start_http()
C.ODATA = http_base
L.ODATA = http_base
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()

check("HTTP entity_sets", C.entity_sets(), sorted(_COUNTS))
meta = C.metadata()
check("HTTP metadata: ключ Catalog_А", meta["Catalog_А"]["key"], ["Ref_Key"])
check("HTTP count Catalog_А", C.count_one("Catalog_А")[1], 42)
check("HTTP count пустой", C.count_one("Document_Пустой")[1], 0)
rows_http = C.census(sets=["Catalog_А", "Document_Пустой"], meta=meta)
check("HTTP census rows>0", [r["entity"] for r in rows_http if r["rows"] > 0], ["Catalog_А"])

# ── packet: $metadata есть, skipped.json нет ───────────────────────────────────
_TMP = tempfile.TemporaryDirectory()
local_base = _write_meta(_TMP.name)
_SKIP_ENTITIES.clear()
C.ODATA = local_base
L.ODATA = local_base
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()
C._mart_count = _fake_mart  # noqa: SLF001 — проба

check("local is_local", C._is_local(), True)
check("local entity_sets", C.entity_sets(), _ALL_ENTITIES)
check("local skipped пуст", C._skipped_map(), {})
rows_local = C.census()
by_ent = {r["entity"]: r for r in rows_local}
check("local count Catalog_А", by_ent["Catalog_А"]["rows"], 42)
check("local count пустой", by_ent["Document_Пустой"]["rows"], 0)
check("local problem пустой", by_ent["Document_Пустой"]["problem"], "")

# ── packet: skipped.json есть ($metadata тоже) ────────────────────────────────
skip_path = os.path.join(local_base, "skipped.json")
with open(skip_path, "w", encoding="utf-8") as f:
    json.dump({"updated_utc": "2026-08-18T00:00:00Z",
               "entities": [{"entity": "Catalog_Закрыта", "error": "no_read_right"}]},
              f, ensure_ascii=False)
_SKIP_ENTITIES.add("Catalog_Закрыта")

check("local skipped map", C._skipped_map(), {"Catalog_Закрыта": "no_read_right"})
closed = C.count_one("Catalog_Закрыта")
check("local closed rows", closed[1], -1)
check("local closed problem", closed[2], "нет прав")
rows_skip = C.census(sets=["Catalog_Закрыта", "Catalog_А"], meta=meta)
by2 = {r["entity"]: r for r in rows_skip}
check("local skipped в census", by2["Catalog_Закрыта"]["problem"], "нет прав")
check("local открытая в census", by2["Catalog_А"]["rows"], 42)

# ── packet: skipped.json есть, $metadata нет — entity_sets падает честно ─────
_TMP2 = tempfile.TemporaryDirectory()
bare = os.path.join(_TMP2.name, "bare-base")
os.makedirs(bare)
with open(os.path.join(bare, "skipped.json"), "w", encoding="utf-8") as f:
    json.dump({"entities": [{"entity": "X", "error": "no_read_right"}]}, f)
C.ODATA = bare
L.ODATA = bare
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()
try:
    C.entity_sets()
    check("local без metadata: исключение", "нет", "ValueError")
except ValueError:
    check("local без metadata: исключение", "ValueError", "ValueError")

# ── итог ───────────────────────────────────────────────────────────────────────
_srv.shutdown()

N_CHECKS = 17
if FAILS:
    print("FAIL %d/%d" % (len(FAILS), N_CHECKS))
    print("\n\n".join(FAILS))
    sys.exit(1)
print("OK %d/%d" % (N_CHECKS, N_CHECKS))
