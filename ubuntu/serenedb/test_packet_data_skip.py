#!/usr/bin/env python3
"""Оффлайн-проба: packet-режим не ходит за данными по HTTP; HTTP-режим — регресс.

Без живой 1С и без обязательного psql: HTTP — ThreadingHTTPServer; packet —
временный каталог packet-meta; счётчик витрины подменяется.

Запуск: python3 test_packet_data_skip.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
os.environ.setdefault("CSV_DIR", "/tmp")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import poc_load_entity as L  # noqa: E402

FAILS = []
HTTP_CALLS = []


def check(name, got, want):
    if got != want:
        FAILS.append("%s:\n    получено %r\n    ожидалось %r" % (name, got, want))


META_XML = """<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><Schema>
<EntityType Name="Catalog_А"><Key><PropertyRef Name="Ref_Key"/></Key>
<Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="DataVersion" Type="Edm.String"/>
<Property Name="Наименование" Type="Edm.String"/>
</EntityType>
<EntityContainer Name="standard">
<EntitySet Name="Catalog_А" EntityType="standard.Catalog_А"/>
</EntityContainer>
</Schema></edmx:Edmx>"""

_ROWS = [{"Ref_Key": "k1", "DataVersion": "v1", "Наименование": "один"},
         {"Ref_Key": "k2", "DataVersion": "v1", "Наименование": "два"}]


class _ODataH(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def do_GET(self):
        HTTP_CALLS.append(self.path)
        u = urllib.parse.urlsplit(self.path)
        qs = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if u.path == "/$metadata":
            return self._raw(200, META_XML.encode("utf-8"), "application/xml")
        parts = u.path.strip("/").split("/")
        if len(parts) == 1:
            name = urllib.parse.unquote(parts[0])
            if name == "Catalog_А":
                body = {"value": _ROWS, "odata.count": str(len(_ROWS))}
                return self._json(200, body)
        if len(parts) == 2 and parts[1] == "$count":
            name = urllib.parse.unquote(parts[0])
            if name == "Catalog_А":
                return self._raw(200, str(len(_ROWS)).encode(), "text/plain")
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


def _fake_psql_rows(sql):
    if "duckdb_columns" in sql:
        return [("1",)]
    if "count(*)" in sql:
        return [("17",)]
    raise RuntimeError("unexpected sql: %s" % sql[:80])


# ── HTTP-режим: fetch_all читает данные ───────────────────────────────────────
_srv, http_base = _start_http()
L.ODATA = http_base
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()
HTTP_CALLS.clear()

rows = L.fetch_all("Catalog_А")
check("HTTP fetch_all: строк", len(rows), 2)
check("HTTP fetch_all: был HTTP-запрос", len(HTTP_CALLS) > 0, True)

# ── packet: load_entity_delta без HTTP ────────────────────────────────────────
_TMP = tempfile.TemporaryDirectory()
local_base = _write_meta(_TMP.name)
L.ODATA = local_base
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()
L._psql_rows = _fake_psql_rows  # noqa: SLF001 — проба

buf = io.StringIO()
with redirect_stderr(buf):
    dr = L.load_entity_delta("Catalog_А")
msg = buf.getvalue()
check("packet delta: changed=0", dr.get("changed"), 0)
check("packet delta: gone=0", dr.get("gone"), 0)
check("packet delta: rows из витрины", dr.get("rows"), 17)
check("packet delta: delta=True", dr.get("delta"), True)
check("packet delta: сообщение в журнале",
      "packet-режим: пробы данных у агента" in msg, True)

HTTP_CALLS.clear()
buf = io.StringIO()
with redirect_stderr(buf):
    fr = L.load_entity("Catalog_А")
check("packet full: changed=0", fr.get("changed"), 0)
check("packet full: rows из витрины", fr.get("rows"), 17)
check("packet full: HTTP не вызывался", HTTP_CALLS, [])
check("packet full: сообщение в журнале",
      "packet-режим: пробы данных у агента" in buf.getvalue(), True)

# ── packet: fetch_all не строит URL от каталога ───────────────────────────────
try:
    L.fetch_all("Catalog_А")
    check("packet fetch_all: исключение", "нет", "RuntimeError")
except RuntimeError as e:
    check("packet fetch_all: исключение", "packet-режим" in str(e), True)

# ── HTTP load_entity_delta по-прежнему ходит (регресс) ────────────────────────
L.ODATA = http_base
L._KEYS_CACHE.clear()
L._PROPS_CACHE.clear()
L._OWNER_CACHE.clear()
L._PROPS_CACHE.update({
    "Catalog_А": [("Ref_Key", "Edm.Guid"), ("DataVersion", "Edm.String"),
                    ("Наименование", "Edm.String")],
})

_real_psql = L._psql_rows


def _delta_psql(sql):
    if "duckdb_columns" in sql:
        return [("1",)]
    if "count(DISTINCT" in sql:
        return [("0",)]
    if 'FROM "catalog_а"' in sql.lower() and "DISTINCT" in sql:
        return [("k1", "v0"), ("k2", "v0")]
    if "count(*)" in sql:
        return [("2",)]
    return _real_psql(sql)


L._psql_rows = _delta_psql  # noqa: SLF001
HTTP_CALLS.clear()
try:
    L.load_entity_delta("Catalog_А")
    check("HTTP delta: HTTP-запрос был", len(HTTP_CALLS) > 0, True)
except Exception as e:  # noqa: BLE001 — psql может отсутствовать
    if HTTP_CALLS:
        check("HTTP delta: HTTP-запрос был", True, True)
    else:
        check("HTTP delta: HTTP-запрос был", False, True)

_srv.shutdown()

N_CHECKS = 14
if FAILS:
    print("FAIL %d/%d" % (len(FAILS), N_CHECKS))
    print("\n\n".join(FAILS))
    sys.exit(1)
print("OK %d/%d" % (N_CHECKS, N_CHECKS))
