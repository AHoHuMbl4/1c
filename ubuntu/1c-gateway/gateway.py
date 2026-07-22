#!/usr/bin/env python3
"""
1C read-only gateway — единственная дверь от «второго мозга» к MCP Toolkit 1С.

Модель безопасности (вся на стороне Ubuntu, на Винде — ничего кастомного):

    мозг ──► этот прокси (deny-by-default allowlist) ──► 192.168.56.1:6003 (проброс на Windows-тулкит)

Прокси пропускает ТОЛЬКО безопасные read-методы. execute_code и любой не-whitelist
инструмент отбиваются здесь, на HTTP-уровне, и до 1С не доходят вообще. Bearer-токен
тулкита хранится тут (мозг его не знает); наружу прокси слушает только localhost.

Тулкит на Винде слушает сетевой интерфейс, роутер 192.168.56.1 пробрасывает :6003 на него;
LXC ходит на 192.168.56.1:6003. Проверено на живой системе 2026-07-22 (execute_query читает,
execute_code режется прокси).

Почему это надёжно, тремя слоями:
  1. Сеть: 6003 доступен только внутри доверенной сети LXC (через роутер .1); наружу не торчит.
  2. Этот прокси: deny-by-default, execute_code режется до 1С.
  3. Фундамент: язык запросов 1С не имеет DML — execute_query физически не пишет.

Конфиг — через переменные окружения (см. значения по умолчанию ниже).
Зависимостей нет (только stdlib) — максимально воспроизводимо.
"""
import json
import os
import sys
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Встроенный HTTP-сервер тулкита однопоточный и деградирует под пачкой параллельных
# соединений (копит CLOSE_WAIT). Сериализуем обращения к нему — не бьём конкурентно.
_UPSTREAM_LOCK = threading.Lock()

# --- конфиг ---
LISTEN_HOST   = os.environ.get("GW_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT   = int(os.environ.get("GW_LISTEN_PORT", "6010"))
UPSTREAM_BASE = os.environ.get("GW_UPSTREAM", "http://192.168.56.1:6003").rstrip("/")
TOOLKIT_TOKEN = os.environ.get("GW_TOOLKIT_TOKEN", "")   # Bearer к тулкиту (обязателен)
GATEWAY_TOKEN = os.environ.get("GW_GATEWAY_TOKEN", "")    # Bearer, который ДОЛЖЕН предъявить мозг (опц.)
TIMEOUT       = float(os.environ.get("GW_TIMEOUT", "180"))

# Разрешённые методы протокола MCP (deny-by-default: чего нет здесь — режется).
ALLOWED_METHODS = {"initialize", "notifications/initialized", "tools/list", "ping"}

# Разрешённые инструменты для tools/call — ТОЛЬКО чтение. execute_code сюда НЕ входит.
ALLOWED_TOOLS = {
    "execute_query",
    "get_metadata",
    "get_event_log",
    "get_object_by_link",
    "get_link_of_object",
    "find_references_to_object",
    "get_access_rights",
    "get_bsl_syntax_help",
}


def _jsonrpc_error(req_id, message, code=-32601):
    body = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    return json.dumps(body).encode("utf-8")


def _decision(payload):
    """Вернуть (allow: bool, reason: str) для одного JSON-RPC запроса."""
    if not isinstance(payload, dict):
        return False, "bad request"
    method = payload.get("method")
    if method not in ALLOWED_METHODS and method != "tools/call":
        return False, f"method not allowed: {method}"
    if method == "tools/call":
        name = (payload.get("params") or {}).get("name")
        if name not in ALLOWED_TOOLS:
            return False, f"tool not allowed (read-only gateway): {name}"
    return True, "ok"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("gw %s - %s\n" % (self.address_string(), fmt % args))

    def _auth_ok(self):
        if not GATEWAY_TOKEN:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {GATEWAY_TOKEN}"

    def _send(self, status, body=b"", ctype="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        # health — локально, без обращения к 1С
        if self.path.rstrip("/") == "/health":
            return self._send(200, json.dumps({"status": "gateway-ok"}).encode())
        return self._send(404, _jsonrpc_error(None, "not found"))

    def do_POST(self):
        if self.path.rstrip("/") != "/mcp":
            return self._send(404, _jsonrpc_error(None, "not found"))
        if not self._auth_ok():
            return self._send(401, _jsonrpc_error(None, "unauthorized"))

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._send(400, _jsonrpc_error(None, "invalid json"))

        allow, reason = _decision(payload)
        if not allow:
            self.log_message("DENY %s", reason)
            # Формат отказа как у тулкита — предсказуемо для мозга.
            return self._send(200, _jsonrpc_error(payload.get("id"), reason))

        # forward наверх (тулкит по IP) с его Bearer-токеном
        req = urllib.request.Request(UPSTREAM_BASE + "/mcp", data=raw, method="POST")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Connection", "close")   # не оставлять соединение висеть у тулкита
        if TOOLKIT_TOKEN:
            req.add_header("Authorization", f"Bearer {TOOLKIT_TOKEN}")
        sid = self.headers.get("Mcp-Session-Id")
        if sid:
            req.add_header("Mcp-Session-Id", sid)
        try:
            with _UPSTREAM_LOCK:   # сериализуем — не бьём однопоточный сервер тулкита конкурентно
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    body = resp.read()
                    ctype = resp.headers.get("Content-Type", "application/json")
                    extra = {}
                    up_sid = resp.headers.get("Mcp-Session-Id")
                    if up_sid:
                        extra["Mcp-Session-Id"] = up_sid
                    return self._send(resp.status, body, ctype, extra)
        except urllib.error.HTTPError as e:
            return self._send(e.code, e.read() or _jsonrpc_error(payload.get("id"), "upstream error"))
        except Exception as e:
            return self._send(502, _jsonrpc_error(payload.get("id"), f"upstream unreachable: {e}"))


def main():
    if not TOOLKIT_TOKEN:
        sys.stderr.write("WARN: GW_TOOLKIT_TOKEN пуст — тулкит, вероятно, ответит 401\n")
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write(f"1c-gateway на http://{LISTEN_HOST}:{LISTEN_PORT}  →  {UPSTREAM_BASE}\n")
    sys.stderr.write(f"allow methods={sorted(ALLOWED_METHODS)} tools={sorted(ALLOWED_TOOLS)}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
