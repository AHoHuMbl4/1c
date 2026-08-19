#!/usr/bin/env python3
"""dash_adapter — сквозной вход из Open WebUI в Grafana (дашборды okna).

Точка входа страницы дашбордов. Пользователь уже залогинен в чате (OWUI);
адаптер подтверждает его сессию у самого OWUI и выдаёт короткоживущий
JWT для Grafana в cookie `gf_jwt`. Дальше Caddy копирует cookie в заголовок
`X-JWT-Assertion` на каждый запрос /dash/* — Grafana ([auth.jwt]) впускает
без формы логина под тем же логином (docs/DASHBOARD_GRAFANA.md §2).

    GET  /dash/enter?to=/d/<uid>  — вход: Set-Cookie gf_jwt + 302 на /dash<to>
    GET  /dash/healthz            — 200 ok (проверка юнита)
    POST /dash/add                — «добавить в дашборд»: спецификация счёта
                                    (diag.счёт от serene_ask) → панель в личном
                                    дашборде пользователя, ответ — ссылка на неё

Env (юнит читает /etc/1c-grafana.env):
    OWUI_URL             http://127.0.0.1:8080
    JWT_PRIVATE_KEY_FILE /etc/1c-grafana-jwt-private.pem
    JWT_TTL_SEC          43200 (12 ч — время жизни cookie-сессии дашбордов)
    LISTEN               127.0.0.1:3002
    DASH_PREFIX          /dash
    GRAFANA_URL          http://127.0.0.1:3001
    GRAFANA_ADMIN_PASSWORD  для /dash/add (панель заводится от имени админа,
                            дашборд получает пользователь чата)

Запускается своим venv'ом (/opt/1c-grafana/venv, pyjwt) под пользователем
dashenter. venv OWUI не подходит: /home/webui ему недоступен [замер 18.08].
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "grafana"))
from panel_from_scope import Grafana, SpecError  # noqa: E402

OWUI_URL = os.environ.get("OWUI_URL", "http://127.0.0.1:8080").rstrip("/")
KEY_FILE = os.environ.get("JWT_PRIVATE_KEY_FILE", "/etc/1c-grafana-jwt-private.pem")
TTL = int(os.environ.get("JWT_TTL_SEC", "43200"))
LISTEN = os.environ.get("LISTEN", "127.0.0.1:3002")
DASH_PREFIX = os.environ.get("DASH_PREFIX", "/dash")

GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3001")
GRAFANA_PW = os.environ.get("GRAFANA_ADMIN_PASSWORD", "")
# Панель кладётся в личный дашборд пользователя чата: uid из его id, а не из
# имени — имя человек меняет, дашборд от этого не должен раздваиваться.
DASH_UID_PREFIX = "ask-"
# Тело запроса /dash/add — спецификация счёта, а не текст: потолок мал нарочно.
MAX_BODY = 16 * 1024

# Роль OWUI → роль Grafana. Админ чата управляет и дашбордами.
ROLE_MAP = {"admin": "Admin", "user": "Viewer", "pending": "Viewer"}


def user_dashboard(user: dict) -> tuple[str, str]:
    """(uid, заголовок) личного дашборда пользователя чата."""
    key = str(user.get("id") or user.get("email") or "")
    uid = DASH_UID_PREFIX + hashlib.sha1(key.encode()).hexdigest()[:12]
    who = user.get("name") or user.get("email") or "чат"
    return uid, f"Панели — {who}"


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

    def _session_user(self) -> dict | None:
        """Пользователь чата по его же cookie. Нет сессии — None."""
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get("token")
        if morsel is None or not morsel.value:
            return None
        return owui_session_user(morsel.value)

    def do_POST(self):
        """«Добавить в дашборд»: спецификация счёта → панель у этого пользователя.

        🔴 SQL панели собирается ДЕТЕРМИНИРОВАННО из спецификации, посчитанной
        базой (`diag.счёт` от serene_ask): источник, условие, величина, ось.
        Модель тут не участвует — она не пишет запрос и не видит схему
        (п. 19, 20 TARGET.md).
        """
        if urlparse(self.path).path != f"{DASH_PREFIX}/add":
            self._send(404, b"not found\n")
            return
        user = self._session_user()
        if not user or not user.get("email"):
            self._send(401, b"session not valid; open the chat and log in first\n")
            return
        if not GRAFANA_PW:
            self._send(503, "нет GRAFANA_ADMIN_PASSWORD в окружении юнита\n".encode())
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(413, f"тело запроса вне 1..{MAX_BODY} байт\n".encode())
            return
        try:
            spec = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, b"body is not json\n")
            return
        if not isinstance(spec, dict):
            self._send(400, b"spec must be an object\n")
            return

        uid, title = user_dashboard(user)
        try:
            out = Grafana(GRAFANA_URL, GRAFANA_PW).add_panel(uid, title, spec)
        except SpecError as exc:
            # Спецификация не годится — говорим чем именно, а не «ошибка».
            self._send(400, f"спецификация не годится: {exc}\n".encode())
            return
        except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            self._send(502, f"grafana недоступна: {exc}\n".encode())
            return

        body = json.dumps({"url": f"{DASH_PREFIX}/d/{out['uid']}?viewPanel={out['panel_id']}",
                           "dashboard_uid": out["uid"], "panel_id": out["panel_id"],
                           "title": out["title"], "sql": out["rawSql"]},
                          ensure_ascii=False).encode()
        self._send(200, body, "application/json; charset=utf-8")

    do_HEAD = do_GET


def main() -> None:
    host, port = LISTEN.rsplit(":", 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
