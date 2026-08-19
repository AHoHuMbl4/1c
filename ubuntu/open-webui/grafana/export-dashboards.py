#!/usr/bin/env python3
"""Выгрузить дашборды Grafana из её базы в семена репозитория.

Зачем: дашборд, созданный руками в UI, живёт только в grafana.db на фронте —
переустановка теряет его молча (так и вышло с okna-sales, 19.08). Семя в git
восстанавливается установщиком (setup-okna-grafana.sh, шаг 8).

Читает базу ТОЛЬКО на чтение и без пароля админа: Grafana 13 держит дашборды
в unified storage (таблица `resource`, kind=Dashboard), а не в `dashboard`
[замер 19.08 — таблица dashboard пуста при живом дашборде].

Ссылка на datasource заменяется на плейсхолдер ${DS_SERENEDB}: uid datasource
генерируется при создании и на другой машине другой. Установщик подставляет
живой uid обратно.

Каталог выгрузки — обязательный параметр --out (argparse required=True,
умолчания нет). Семена контурные, grafana/contours/<контур>: в панелях стоят
имена таблиц конкретной базы 1С, поэтому установщик берёт их только по
DASHBOARD_SEEDS_DIR — на чужой базе коробка не получит чужих имён.

    python3 export-dashboards.py --out grafana/contours/okna [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys

DS_PLACEHOLDER = "${DS_SERENEDB}"
# Тип postgres-datasource Grafana 13 отдаёт плагином, а создаётся он как postgres
# [замер 19.08] — семя должно ловить оба имени.
PG_TYPES = ("postgres", "grafana-postgresql-datasource")
# Поля, которые ставит сама Grafana при сохранении: в семя не уносим.
DROP_KEYS = {"version", "id", "schemaVersion", "weekStart", "fiscalYearStartMonth",
             "editable", "graphTooltip", "links", "annotations", "preload"}


def replace_ds(node, ds_uids: set[str]):
    """Рекурсивно заменить uid datasource на плейсхолдер."""
    if isinstance(node, dict):
        if node.get("type") in PG_TYPES and node.get("uid") in ds_uids:
            return {"type": node["type"], "uid": DS_PLACEHOLDER}
        return {k: replace_ds(v, ds_uids) for k, v in node.items()}
    if isinstance(node, list):
        return [replace_ds(v, ds_uids) for v in node]
    return node


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/var/lib/1c-grafana/grafana.db")
    ap.add_argument("--out", required=True,
                    help="каталог семян контура, например grafana/contours/okna")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    ds_uids = {r[0] for r in con.execute("select uid from data_source")}
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    written = 0
    for name, value in con.execute(
            "select name, value from resource where resource='dashboards'"):
        spec = json.loads(value).get("spec")
        if not spec:
            continue
        seed = {k: v for k, v in spec.items() if k not in DROP_KEYS}
        seed["uid"] = name
        seed = {"uid": seed.pop("uid"), **replace_ds(seed, ds_uids)}
        path = out / f"{name}.json"
        path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"{path}: {len(seed.get('panels', []))} панелей")
        written += 1
    if not written:
        print("дашбордов в базе нет", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
