#!/usr/bin/env python3
"""Минтер JWT для сквозного входа в Grafana (стенд; зародыш адаптера).

Прототип того, что будет делать адаптер по вызову Action-кнопки из Open
WebUI: известны пользователь чата (OWUI передаёт __user__: id, email, name)
и целевой дашборд — отсюда короткоживущий JWT и готовая ссылка, которая
открывает Grafana без формы логина ([auth.jwt] url_login).

Использование:
  python3 work/grafana-stand/mint-jwt.py --email u@example.org --name "Иван" \
      [--sub user-id] [--path /d/stand-from-chat] [--ttl 60]

Ключ приватный: $GRAFANA_STAND_DIR/jwt-private.pem (умолчание
/dev/shm/grafana-stand). Токен в stdout — это ссылка целиком.
"""
import argparse
import os
import time

import jwt

STAND = os.environ.get("GRAFANA_STAND_DIR", "/dev/shm/grafana-stand")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--role", default="Viewer",
                    choices=["Viewer", "Editor", "Admin"])
    ap.add_argument("--path", default="/d/stand-from-chat")
    ap.add_argument("--ttl", type=int, default=60,
                    help="секунд жизни токена (ссылка одноразовая по смыслу)")
    ap.add_argument("--base", default=None,
                    help="база Grafana; умолчание http://127.0.0.1:$GRAFANA_PORT|3001")
    args = ap.parse_args()

    with open(os.path.join(STAND, "jwt-private.pem"), "rb") as fh:
        key = fh.read()
    now = int(time.time())
    token = jwt.encode(
        {"sub": args.sub or args.email, "email": args.email,
         "name": args.name or args.email, "role": args.role,
         "iat": now, "nbf": now - 5, "exp": now + args.ttl},
        key, algorithm="RS256")
    base = args.base or f"http://127.0.0.1:{os.environ.get('GRAFANA_PORT', '3001')}"
    print(f"{base}{args.path}?auth_token={token}")


if __name__ == "__main__":
    main()
