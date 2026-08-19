#!/usr/bin/env python3
"""Приёмка дашбордов: отдают ли панели данные.

Зачем отдельно от probe: probe `select version()` ходит НЕ тем путём, что
панель. При datasource без `jsonData.database` probe проходил, а панели
давали No data [замер 19.08, ловушка 11 docs/DASHBOARD_GRAFANA.md]. Здесь
гоняется `rawSql` каждой панели каждого дашборда через `/api/ds/query` —
ровно то, что делает открытая страница.

Окно берётся из самого дашборда (`time`, `panel.timeFrom`): своё окно было бы
подгонкой под нашу базу — на базе с другой историей исправная панель дала бы
0 строк.

Пароль админа: env `GRAFANA_ADMIN_PASSWORD`, иначе первая строка stdin.
В аргументы командной строки пароль не принимается — иначе он попадёт
в список процессов и в историю оболочки.

    GRAFANA_ADMIN_PASSWORD=… python3 check-panels.py
    echo пароль | python3 check-panels.py --url http://127.0.0.1:3001

Код возврата: 0 — все панели с данными, 1 — есть пустые или с ошибкой.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3001")
    ap.add_argument("--user", default="admin")
    args = ap.parse_args()

    password = os.environ.get("GRAFANA_ADMIN_PASSWORD") or sys.stdin.readline().strip()
    if not password:
        print("нет пароля админа: env GRAFANA_ADMIN_PASSWORD или stdin", file=sys.stderr)
        return 2
    auth = "Basic " + base64.b64encode(f"{args.user}:{password}".encode()).decode()

    def call(method: str, path: str, body=None):
        req = urllib.request.Request(
            args.url.rstrip("/") + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Authorization": auth})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as exc:
            # Панель с битым запросом отвечает 400/500 — это НАХОДКА приёмки,
            # а не повод падать: тело несёт ошибку базы, её и показываем
            # [замер 19.08: панель с несуществующей колонкой роняла приёмку].
            body_text = exc.read().decode("utf-8", "replace")
            try:
                return json.loads(body_text)
            except json.JSONDecodeError:
                return {"results": {"A": {"error": f"HTTP {exc.code}: {body_text[:300]}"}}}

    bad, checked = [], 0
    for item in call("GET", "/api/search?type=dash-db"):
        dash = call("GET", f"/api/dashboards/uid/{item['uid']}")["dashboard"]
        window = dash.get("time") or {}
        for panel in dash.get("panels", []):
            for target in panel.get("targets", []):
                sql = target.get("rawSql")
                if not sql:
                    continue
                checked += 1
                query = {
                    "queries": [{"refId": "A", "datasource": panel["datasource"],
                                 "rawSql": sql,
                                 "format": target.get("format", "table")}],
                    "from": panel.get("timeFrom") or window.get("from", "now-6h"),
                    "to": window.get("to", "now")}
                res = call("POST", "/api/ds/query", query)["results"]["A"]
                title = f"{dash['title']} / {panel.get('title')}"
                if res.get("error"):
                    print(f"❌ {title}: {res['error']}")
                    bad.append(title)
                    continue
                rows = 0
                for frame in res.get("frames", []):
                    values = frame.get("data", {}).get("values") or []
                    rows = max(rows, len(values[0]) if values else 0)
                print(f"{'✅' if rows else '⚠️'} {title}: строк {rows}")
                if not rows:
                    bad.append(title)
    if not checked:
        print("панелей с запросом не найдено", file=sys.stderr)
        return 1
    print(f"итог: панелей {checked}, без данных {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
