#!/usr/bin/env python3
"""Оффлайн: /health видит разворот по дням и лишние строки корпуса (п.13)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


t("нет разрыва", A._assemble_health_gap({}, []) is None)

g = A._assemble_health_gap({"catalog_x": (100, 60)}, [])
t("итог витрина>корпус: missing", g and g["rows_missing"] == 40 and g["entities"] == 1, g)
t("итог витрина>корпус: нет extra", g and "rows_extra" not in g, g)

g = A._assemble_health_gap({"reg": (176, 331)}, [])
t("итог корпус>витрина: extra", g and g.get("rows_extra") == 155 and g["rows_missing"] == 0, g)

# Живой кейс okna 18.08: нетто +40 прячет +155/−175.
days = [
    ("accumulationregister_реализациятмц", "2026-08-17", 176, 331),
    ("accumulationregister_реализациятмц", "2026-08-18", 48, 25),
    ("accumulationregister_реализациятмц", "2026-08-19", 175, 0),
    ("accumulationregister_реализациятмц", "2026-08-11", 20, 23),
]
g = A._assemble_health_gap(
    {"accumulationregister_реализациятмц": (77421, 77381)}, days)
t("дни важнее итога: не 40 missing", g and g["rows_missing"] != 40, g)
t("дни: missing 19.08+18.08", g and g["rows_missing"] == 175 + 23, g)
t("дни: extra 17.08+11.08", g and g.get("rows_extra") == 155 + 3, g)
t("дни: worst содержит d", g and any("d" in w for w in g["worst"]), g)
t("дни: одна сущность", g and g["entities"] == 1, g)

# Итоги совпали, дни нет — прежний /health молчал бы.
g = A._assemble_health_gap({"reg": (100, 100)}, [
    ("reg", "2026-08-17", 50, 80),
    ("reg", "2026-08-19", 50, 20),
])
t("нетто ноль по дням всё равно gap", g is not None, g)
t("нетто ноль: extra 30 missing 30",
  g and g.get("rows_extra") == 30 and g["rows_missing"] == 30, g)

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus_build.sql")
txt = open(src, encoding="utf-8").read()
t("corpus_build дописывает LineNumber",
  "list_concat(r.key_cols, ['LineNumber'])" in txt)
t("corpus_build только при Recorder",
  "NOT list_contains(r.key_cols, 'Recorder')" in txt)

msrc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus_merge.sql")
mtxt = open(msrc, encoding="utf-8").read()
t("merge сторож: split_part первого куска ключа",
  "split_part(t.row_key, '|', 1) = split_part(c.row_key, '|', 1)" in mtxt)
t("merge сторож: guid#N = тот же объект",
  "t.row_key = split_part(c.row_key, '#', 1)" in mtxt)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
