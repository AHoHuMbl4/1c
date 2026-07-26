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
  2. Этот прокси пропускает ТОЛЬКО GET и только под базовым OData-путём (`..` отклоняется
     с 403), writes режет на входе. Bearer-токен обязателен: без него сервис не стартует.
  3. Состав OData ограничен (УстановитьСоставСтандартногоИнтерфейсаOData).
Bearer/креды 1С хранятся здесь, мозг их не знает; наружу прокси слушает localhost.

Конфиг — env (см. дефолты ниже). Только stdlib.
"""
import base64
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _url_ascii(raw: str) -> str:
    """URL для http.client обязан быть ASCII, иначе UnicodeEncodeError.

    `self.path` у BaseHTTPRequestHandler декодирован как latin-1, поэтому не-ASCII
    символы (кириллические имена реквизитов в $select/$filter) роняли прокси:
    'ascii' codec can't encode characters. Возвращаем байты и percent-кодируем
    ТОЛЬКО не-ASCII — всё ASCII (включая уже готовые %XX, $, &, =, ') не трогаем,
    поэтому уже закодированные клиентом запросы не портятся.
    """
    out = []
    for b in raw.encode("latin-1", "replace"):
        out.append(chr(b) if b < 0x80 else "%%%02X" % b)
    return "".join(out)

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
        # Fail-closed. Раньше здесь было «нет токена — пускаем всех», и токен в env
        # не задали: шлюз отдавал всю опубликованную 1С любому локальному процессу
        # без единого заголовка. Пустая переменная окружения не должна молча снимать
        # защиту — теперь без токена сервис вообще не стартует (см. main()).
        return self.headers.get("Authorization", "") == f"Bearer {GATEWAY_TOKEN}"

    @staticmethod
    def _path_ok(raw: str) -> bool:
        """Путь обязан оставаться ВНУТРИ базового OData-адреса.

        `UPSTREAM` уже содержит базовый путь публикации, а путь клиента к нему
        дописывается. Поэтому `..` выводит запрос за пределы OData — на корень
        веб-сервера. Проверено до правки: `GET /../../..` отдавал 200.
        Разрешаем только обычные сегменты; сравниваем и исходную, и раскодированную
        форму, чтобы `%2e%2e` не проскочил мимо.
        """
        for form in (raw, urllib.parse.unquote(raw)):
            path = form.split("?", 1)[0]
            if "\\" in path:
                return False
            for seg in path.split("/"):
                if seg == "..":
                    return False
        return True

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
        if not self._path_ok(self.path):
            self.log_message("DENY path traversal %s", self.path)
            return self._send(403, b'{"error":"path outside OData base"}')
        # проксируем GET на OData; путь клиента добавляется к базовому OData-URL
        path = self.path if self.path.startswith("/") else "/" + self.path
        url = UPSTREAM + _url_ascii(path)
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
    if not GATEWAY_TOKEN:
        # Отказ на старте, а не тихое снятие защиты: опечатка в имени переменной
        # окружения не должна превращать шлюз в открытый доступ к данным 1С.
        sys.stderr.write("FATAL: ODG_GATEWAY_TOKEN не задан — шлюз без авторизации "
                         "отдавал бы 1С кому угодно. Задайте токен в окружении.\n")
        return 2
    if not (ODATA_USER and ODATA_PASS):
        sys.stderr.write("WARN: ODG_USER/ODG_PASS пусты — OData ответит 401\n")
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write(f"1c-odata-gateway на http://{LISTEN_HOST}:{LISTEN_PORT}  →  {UPSTREAM}  (только GET)\n")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
