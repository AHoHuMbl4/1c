#!/usr/bin/env python3
"""Диагностика брендинга Open WebUI (вывод без секретов)."""
import json, os, urllib.request, urllib.error

BASE = "http://127.0.0.1:8080"
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@okna.local")
PASSWORD = os.environ["ADMIN_PASS"]


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw.decode(errors="replace")[:300]}
        return e.code, payload


def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower()
            if any(x in kl for x in ("key", "token", "secret", "password", "api_key")):
                out[k] = "***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(i) for i in obj]
    return obj


st, cfg = req("GET", "/api/config")
print("=== /api/config ===")
print(json.dumps(redact(cfg), ensure_ascii=False, indent=2)[:2500])

st, tok = req("POST", "/api/v1/auths/signin", {"email": EMAIL, "password": PASSWORD})
print("=== signin ===", st, list(tok.keys()) if isinstance(tok, dict) else tok)
auth = tok.get("token") if isinstance(tok, dict) else None
if not auth:
    raise SystemExit(1)

for path in (
    "/api/v1/models/",
    "/openai/config",
    "/api/v1/configs/models",
    "/api/v1/configs/suggestions",
    "/api/v1/configs/banners",
    "/api/v1/auths/",
):
    st, body = req("GET", path, token=auth)
    print(f"=== GET {path} [{st}] ===")
    print(json.dumps(redact(body), ensure_ascii=False, indent=2)[:2000])
    print()
