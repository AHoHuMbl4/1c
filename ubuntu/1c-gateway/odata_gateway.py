#!/usr/bin/env python3
"""
1C OData read-only gateway — прод-канал «второго мозга» к 1С через штатный OData.

Почему OData, а не встроенный сервер тулкита: тот обслуживается клиентским
idle-обработчиком 1С (см. docs/TOOLKIT_TRANSPORT_ROOTCAUSE.md) — ~1 req/s и встаёт
на любом модальном окне. OData обслуживается веб-сервером IIS (служба Windows):
многопоточно, авто-старт, переживает ребут, модальных окон в веб-сессии не бывает.

Схема (вся защита на стороне Ubuntu; на Винде — штатный IIS):
    мозг ──► этот прокси (только GET, whitelist) ──► 192.168.56.1:<порт> ──► IIS OData 1С

Гарантии read-only, слоями:
  1. Пользователь 1С read-only (ai_reader) — OData под ним физически не пишет
     (запись = POST/PATCH/DELETE, права не дают). Это ОСНОВНАЯ гарантия.
  2. Этот прокси пропускает ТОЛЬКО GET и только под базовым OData-путём — writes режет.
  3. Состав OData ограничен (УстановитьСоставСтандартногоИнтерфейсаOData).
Bearer/креды 1С хранятся здесь, мозг их не знает; наружу прокси слушает localhost.

Конфиг — env (см. дефолты ниже). Только stdlib.
"""
import base64
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST  = os.environ.get("ODG_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT  = int(os.environ.get("ODG_LISTEN_PORT", "6011"))
# База OData на IIS через проброс роутера .1 (порт — куда роутер пробрасывает IIS:80)
UPSTREAM     = os.environ.get("ODG_UPSTREAM", "http://192.168.56.1:6003/1c/odata/standard.odata").rstrip("/")
ODATA_USER   = os.environ.get("ODG_USER", "")
ODATA_PASS   = os.environ.get("ODG_PASS", "")
GATEWAY_TOKEN = os.environ.get("ODG_GATEWAY_TOKEN", "")  # опц. Bearer, который предъявляет мозг
TIMEOUT      = float(os.environ.get("ODG_TIMEOUT", "120"))


def _basic():
    raw = f"{ODATA_USER}:{ODATA_PASS}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("odg %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body=b"", ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _auth_ok(self):
        if not GATEWAY_TOKEN:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {GATEWAY_TOKEN}"

    # Разрешаем ТОЛЬКО чтение. Всё, что меняет данные, — отклоняем на входе.
    def do_POST(self):   return self._deny()
    def do_PUT(self):    return self._deny()
    def do_PATCH(self):  return self._deny()
    def do_DELETE(self): return self._deny()
    def do_MERGE(self):  return self._deny()

    def _deny(self):
        self.log_message("DENY write method %s %s", self.command, self.path)
        return self._send(405, b'{"error":"read-only gateway: method not allowed"}')

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            return self._send(200, b'{"status":"odata-gateway-ok"}')
        if not self._auth_ok():
            return self._send(401, b'{"error":"unauthorized"}')
        # проксируем GET на OData; путь клиента добавляется к базовому OData-URL
        path = self.path if self.path.startswith("/") else "/" + self.path
        url = UPSTREAM + path
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", _basic())
        accept = self.headers.get("Accept")
        if accept:
            req.add_header("Accept", accept)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "application/json")
                return self._send(resp.status, body, ctype)
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read() or b'{"error":"upstream error"}')
        except Exception as e:
            return self._send(502, f'{{"error":"upstream unreachable: {e}"}}'.encode())


def main():
    if not (ODATA_USER and ODATA_PASS):
        sys.stderr.write("WARN: ODG_USER/ODG_PASS пусты — OData ответит 401\n")
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write(f"1c-odata-gateway на http://{LISTEN_HOST}:{LISTEN_PORT}  →  {UPSTREAM}  (только GET)\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
