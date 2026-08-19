#!/usr/bin/env python3
"""Панель Grafana из спецификации счёта, посчитанного базой.

Это исполнительная половина кнопки «добавить в дашборд». На вход — то, что
`serene_ask` объявляет о своём счёте (`diag.счёт`: источник, условие, величина,
ось), на выход — панель в дашборде пользователя.

🔴 SQL здесь СОБИРАЕТСЯ ДЕТЕРМИНИРОВАННО из спецификации, а не пишется моделью:
числа считает база, схема в модель не уходит (п. 19, 20 TARGET.md). Модель в
этом пути не участвует вовсе.

Касты обязательны: SereneDB отдаёт колонки как VARCHAR, без `::timestamp` и
`::DECIMAL` запрос падает (`date_trunc(STRING_LITERAL, VARCHAR)`,
`sum(VARCHAR)`) — ловушка 1 docs/DASHBOARD_GRAFANA.md.

CLI для проверки без чата:

    GRAFANA_ADMIN_PASSWORD=… python3 panel_from_scope.py --spec spec.json \
        --dashboard-uid user-demo --dashboard-title "Панели — demo"
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

# Разрешённые виды панели: имя типа Grafana и форма запроса.
KINDS = ("timeseries", "barchart", "stat")
# 🔴 Тип postgres-datasource Grafana 13 отдаёт плагином (`grafana-postgresql-datasource`),
# хотя создаётся он как `postgres` [замер 19.08]. Ищем по обоим именам, а в панель
# кладём то, что назвала сама Grafana.
PG_TYPES = ("postgres", "grafana-postgresql-datasource")
# Потолок строк для разреза по оси — граница ПОКАЗА, не счёта: считает база,
# панель рисует топ. Число видно в заголовке панели, молчаливой потери нет (п. 13).
AXIS_ROWS = 50


class SpecError(ValueError):
    """Spec rejected: missing field or disallowed text."""


def _ident(name: str, what: str) -> str:
    """Column/table name from ask spec. Quotes, ; and comments are rejected."""
    value = str(name or "").strip()
    if not value:
        raise SpecError(f"{what}: empty")
    for bad in ('"', ";", "--", "/*", "*/"):
        if bad in value:
            raise SpecError(f"{what}: disallowed text {bad!r}")
    return value


def _condition(where: str) -> str:
    """Condition from ask scope (built by code, not by a human or a model)."""
    value = str(where or "").strip()
    for bad in (";", "--", "/*", "*/"):
        if bad in value:
            raise SpecError(f"condition: disallowed text {bad!r}")
    return value


def build_sql(spec: dict) -> tuple[str, str, str]:
    """(rawSql, формат для Grafana, вид панели) из спецификации счёта."""
    kind = spec.get("kind") or ("barchart" if spec.get("axis") else "timeseries")
    if kind not in KINDS:
        raise SpecError(f"panel kind {kind!r} not in {KINDS}")
    src = _ident(spec.get("src"), "источник")
    measure = _ident(spec.get("measure"), "величина")
    where = _condition(spec.get("where"))
    tail = f" WHERE {where}" if where else ""

    if kind == "stat":
        return (f'SELECT sum("{measure}"::DECIMAL) AS "{measure}" FROM {src}{tail}',
                "table", kind)
    if kind == "barchart":
        axis = _ident(spec.get("axis"), "ось")
        return (f'SELECT "{axis}"::VARCHAR AS metric, sum("{measure}"::DECIMAL) AS value'
                f" FROM {src}{tail} GROUP BY 1 ORDER BY 2 DESC LIMIT {AXIS_ROWS}",
                "table", kind)
    period_col = spec.get("period_col")
    if not period_col:
        raise SpecError("period_col is required in spec for timeseries")
    period = _ident(period_col, "period_col")
    return (f'SELECT date_trunc(\'day\', "{period}"::timestamp) AS time,'
            f' sum("{measure}"::DECIMAL) AS value FROM {src}{tail}'
            " GROUP BY 1 ORDER BY 1", "time_series", kind)


def make_panel(spec: dict, datasource: dict, panel_id: int, y: int) -> dict:
    """Панель Grafana целиком: запрос, вид, место на сетке."""
    sql, fmt, kind = build_sql(spec)
    title = str(spec.get("title") or "").strip() or spec.get("measure") or "Панель"
    if kind == "barchart":
        title = f"{title} — top {AXIS_ROWS}"
    return {
        "id": panel_id,
        "type": kind,
        "title": title,
        "datasource": datasource,
        "gridPos": {"h": 9, "w": 12 if kind != "stat" else 5, "x": 0, "y": y},
        "targets": [{"refId": "A", "format": fmt, "datasource": datasource,
                     "rawSql": sql}],
    }


class Grafana:
    """Тонкий клиент API Grafana: пароль только из окружения, не из аргументов."""

    def __init__(self, url: str, password: str, user: str = "admin"):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(
            self.url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Authorization": self.auth})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    def default_datasource(self) -> dict:
        """Postgres-datasource: по uid из env, isDefault, или единственный экземпляр."""
        wanted_uid = os.environ.get("GRAFANA_DS_UID", "").strip()
        all_pg = [ds for ds in self.call("GET", "/api/datasources")
                  if ds.get("type") in PG_TYPES]
        if not all_pg:
            raise RuntimeError("no postgres datasource in Grafana")
        if wanted_uid:
            for ds in all_pg:
                if ds.get("uid") == wanted_uid:
                    return {"type": ds["type"], "uid": ds["uid"]}
            raise RuntimeError(f"datasource uid={wanted_uid!r} not found")
        for ds in all_pg:
            if ds.get("isDefault"):
                return {"type": ds["type"], "uid": ds["uid"]}
        if len(all_pg) == 1:
            return {"type": all_pg[0]["type"], "uid": all_pg[0]["uid"]}
        raise RuntimeError("multiple postgres datasources, set GRAFANA_DS_UID")

    def dashboard(self, uid: str, title: str) -> dict:
        try:
            return self.call("GET", f"/api/dashboards/uid/{uid}")["dashboard"]
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        # Первая панель пользователя — заводим дашборд под него.
        return {"uid": uid, "title": title, "panels": [], "tags": ["ask"],
                "time": {"from": "now-1y", "to": "now"}, "refresh": "5m"}

    def check_query(self, datasource: dict, sql: str, fmt: str, window: dict) -> int:
        """Прогнать запрос панели до закрепления: ошибка базы — наверх, строки — числом.

        Держится кодом: `add_panel` зовёт эту проверку перед POST дашборда, и
        `SpecError` прерывает закрепление — битая панель до дашборда не доходит
        (замок `test_panel_from_scope`, живой отказ 19.08 на несуществующей оси).
        """
        body = {"queries": [{"refId": "A", "datasource": datasource,
                             "rawSql": sql, "format": fmt}],
                "from": window.get("from", "now-90d"), "to": window.get("to", "now")}
        try:
            res = self.call("POST", "/api/ds/query", body)["results"]["A"]
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", "replace")
            try:
                res = json.loads(payload)["results"]["A"]
            except (json.JSONDecodeError, KeyError):
                raise SpecError(f"query failed: HTTP {exc.code}") from exc
        if res.get("error"):
            raise SpecError(f"query failed: {res['error']}")
        rows = 0
        for frame in res.get("frames", []):
            values = frame.get("data", {}).get("values") or []
            rows = max(rows, len(values[0]) if values else 0)
        return rows

    def add_panel(self, uid: str, title: str, spec: dict) -> dict:
        dash = self.dashboard(uid, title)
        panels = dash.get("panels") or []
        panel_id = max([p.get("id") or 0 for p in panels], default=0) + 1
        y = max([(p.get("gridPos") or {}).get("y", 0) + (p.get("gridPos") or {}).get("h", 9)
                 for p in panels], default=0)
        panel = make_panel(spec, self.default_datasource(), panel_id, y)
        target = panel["targets"][0]
        rows = self.check_query(panel["datasource"], target["rawSql"],
                                target["format"], dash.get("time") or {})
        dash["panels"] = panels + [panel]
        self.call("POST", "/api/dashboards/db",
                  {"dashboard": dash, "overwrite": True,
                   "message": f"панель из ответа: {panel['title']}"})
        return {"uid": uid, "panel_id": panel_id, "title": panel["title"],
                "rawSql": target["rawSql"], "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3001")
    ap.add_argument("--spec", required=True, help="файл со спецификацией счёта (JSON)")
    ap.add_argument("--dashboard-uid", required=True)
    ap.add_argument("--dashboard-title", default="Панели из чата")
    args = ap.parse_args()

    password = os.environ.get("GRAFANA_ADMIN_PASSWORD") or sys.stdin.readline().strip()
    if not password:
        print("no admin password: set GRAFANA_ADMIN_PASSWORD or pipe to stdin", file=sys.stderr)
        return 2
    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    out = Grafana(args.url, password).add_panel(
        args.dashboard_uid, args.dashboard_title, spec)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
