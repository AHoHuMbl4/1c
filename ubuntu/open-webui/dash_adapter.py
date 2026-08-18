#!/usr/bin/env python3
"""dash_adapter — сквозной вход из Open WebUI в Grafana (дашборды okna).

Точка входа страницы дашбордов. Пользователь уже залогинен в чате (OWUI);
адаптер подтверждает его сессию у самого OWUI и выдаёт короткоживущий
JWT для Grafana в cookie `gf_jwt`. Дальше Caddy копирует cookie в заголовок
`X-JWT-Assertion` на каждый запрос /dash/* — Grafana ([auth.jwt]) впускает
без формы логина под тем же логином (docs/DASHBOARD_GRAFANA.md §2).

    GET /dash/enter?to=/d/<uid>   — вход: Set-Cookie gf_jwt + 302 на /dash<to>
    GET /dash/healthz             — 200 ok (проверка юнита)

Env (юнит читает /etc/1c-grafana.env):
    OWUI_URL             http://127.0.0.1:8080
    JWT_PRIVATE_KEY_FILE /etc/1c-grafana-jwt-private.pem
    JWT_TTL_SEC          43200 (12 ч — время жизни cookie-сессии дашбордов)
    LISTEN               127.0.0.1:3002
    DASH_PREFIX          /dash

Запускается своим venv'ом (/opt/1c-grafana/venv, pyjwt) под пользователем
dashenter. venv OWUI не подходит: /home/webui ему недоступен [замер 18.08].
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt

OWUI_URL = os.environ.get("OWUI_URL", "http://127.0.0.1:8080").rstrip("/")
KEY_FILE = os.environ.get("JWT_PRIVATE_KEY_FILE", "/etc/1c-grafana-jwt-private.pem")
TTL = int(os.environ.get("JWT_TTL_SEC", "43200"))
LISTEN = os.environ.get("LISTEN", "127.0.0.1:3002")
DASH_PREFIX = os.environ.get("DASH_PREFIX", "/dash")

# Роль OWUI → роль Grafana. Админ чата управляет и дашбордами.
ROLE_MAP = {"admin": "Admin", "user": "Viewer", "pending": "Viewer"}


def owui_session_user(token_cookie: str) -> dict | None:
    """Подтвердить сессию у OWUI: проксируем его же cookie на /api/v1/auths/.
    OWUI сам разбирает свой token (get_session_user читает и cookie)."""
    req = urllib.request.Request(
        f"{OWUI_URL}/api/v1/auths/",
        headers={"Cookie": f"token={token_cookie}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def mint(user: dict) -> str:
    with open(KEY_FILE, "rb") as fh:
        key = fh.read()
    now = int(time.time())
    role = ROLE_MAP.get(str(user.get("role", "user")), "Viewer")
    return jwt.encode(
        {"sub": str(user.get("id") or user.get("email")),
         "email": user.get("email", ""),
         "name": user.get("name") or user.get("email", ""),
         "role": role, "iat": now, "nbf": now - 5, "exp": now + TTL},
        key, algorithm="RS256")


class Handler(BaseHTTPRequestHandler):
    server_version = "dash-adapter/1.0"

    def log_message(self, fmt, *args):  # токены в access-log не пишем
        pass

    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8",
              extra: list[tuple[str, str]] | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra or []:
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == f"{DASH_PREFIX}/healthz":
            self._send(200, b"ok\n")
            return
        if path != f"{DASH_PREFIX}/enter":
            self._send(404, b"not found\n")
            return

        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get("token")
        if morsel is None or not morsel.value:
            # Нет сессии чата — на форму логина OWUI.
            self._send(302, extra=[("Location", "/")])
            return
        user = owui_session_user(morsel.value)
        if not user or not user.get("email"):
            self._send(401, b"session not valid; open the chat and log in first\n")
            return

        token = mint(user)
        query = parse_qs(urlparse(self.path).query)
        to = (query.get("to") or ["/dashboards"])[0]
        # Только локальные пути дашбордов — иначе open redirect.
        if not to.startswith("/") or to.startswith("//"):
            to = "/dashboards"

        jar_out = cookies.SimpleCookie()
        jar_out["gf_jwt"] = token
        jar_out["gf_jwt"]["path"] = DASH_PREFIX
        jar_out["gf_jwt"]["httponly"] = True
        jar_out["gf_jwt"]["secure"] = True
        jar_out["gf_jwt"]["samesite"] = "Lax"
        jar_out["gf_jwt"]["max-age"] = TTL
        self._send(302, extra=[("Location", f"{DASH_PREFIX}{to}"),
                               ("Set-Cookie", jar_out.output(header="").strip())])

    do_HEAD = do_GET


def main() -> None:
    host, port = LISTEN.rsplit(":", 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
