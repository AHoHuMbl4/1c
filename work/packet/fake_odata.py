#!/usr/bin/env python3
"""Ложный OData для сравнения пакетов «до/после»: отдаёт строки из golden-фикстур.

Нужен, чтобы доказать, что правка «чанки на диск по ходу обхода» не изменила НИ
ОДНОГО байта собираемого пакета: один и тот же источник данных, два бинаря агента,
побайтное сравнение чанков и манифеста.

Запуск: fake_odata.py <порт> <каталог фикстур>
"""
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
FIX = sys.argv[2]
# FAKE_DELAY_MS — пауза на каждый запрос: имитация медленной 1С
# (проверка порционной отправки и пауз-повторов агента).
DELAY_MS = int(os.environ.get("FAKE_DELAY_MS", "0"))

ENTITIES = {}
for fn in sorted(os.listdir(FIX)):
    if not fn.endswith(".page1.json"):
        continue
    name = fn[: -len(".page1.json")]
    doc = json.load(open(os.path.join(FIX, fn), encoding="utf-8"))
    ENTITIES[name] = doc.get("value", doc if isinstance(doc, list) else [])
print("сущностей в фикстурах:", len(ENTITIES), flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write("odata %s\n" % (fmt % a))

    def do_GET(self):
        if DELAY_MS:
            time.sleep(DELAY_MS / 1000.0)
        u = urllib.parse.urlsplit(self.path)
        name = urllib.parse.unquote(u.path.strip("/").split("/")[-1])
        qs = urllib.parse.parse_qs(u.query)
        rows = ENTITIES.get(name)
        if rows is None:
            return self._send(404, {"odata.error": {"message": "нет такой сущности"}})
        top = int(qs.get("$top", ["10000"])[0])
        skip = int(qs.get("$skip", ["0"])[0])
        sel = qs.get("$select", [None])[0]
        page = rows[skip: skip + top]
        if sel:                       # проба версий: только Ref_Key,DataVersion
            keep = sel.split(",")
            page = [{k: r.get(k) for k in keep if k in r} for r in page]
        body = {"value": page}
        if "$inlinecount" in qs:
            body["odata.count"] = len(rows)
        return self._send(200, body)

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json;charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
