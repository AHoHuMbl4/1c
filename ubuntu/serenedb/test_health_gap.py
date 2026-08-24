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



# Ref_Key: строки витрины >> корпус, объекты равны — gap нет ([замер 23.08 okna]).
g = A._assemble_health_gap({"document_x": (439, 439)}, [])
t("Ref_Key equal objects: no gap", g is None, g)

g = A._assemble_health_gap({"document_x": (500, 439)}, [])
t("Ref_Key objects missing: gap", g and g["rows_missing"] == 61 and g["entities"] == 1, g)
t("Ref_Key worst objects not rows",
  g and g["worst"][0]["витрина"] == 500 and g["worst"][0]["корпус"] == 439, g)

# _classify: index publish без объектного долга — не systemic.
real_psql, real_classify = A.psql, A._real_corpus_object_gaps
A._real_corpus_object_gaps = lambda: False
g = A._classify_health_gap({"entities": 6, "rows_missing": 148, "worst": [
    {"src": "catalog_a", "витрина": 10, "корпус": 8}]})
t("index publish not systemic", g and g.get("kind") == "index_publish", g)
A._real_corpus_object_gaps = lambda: True
g = A._classify_health_gap({"entities": 1, "rows_missing": 5, "worst": []})
t("real object gap stays systemic", g and g.get("kind") == "systemic", g)
A.psql, A._real_corpus_object_gaps = real_psql, real_classify

# _measure_health_gap: один SELECT search_coverage, не цикл _vitrina_objects.
_vo_calls = []
real_vo, real_psql2 = A._vitrina_objects, A.psql
def mock_vo(name):
    _vo_calls.append(name)
    return 0
A._vitrina_objects = mock_vo
def mock_psql2(sql):
    if "FROM search_coverage" in sql and "объектов_витрины" in sql:
        return [["document_doc", 100, 100], ["catalog_plain", 50, 50]]
    return []
A.psql = mock_psql2
g = A._measure_health_gap()
A._vitrina_objects, A.psql = real_vo, real_psql2
t("measure does not scan vitrina per entity", _vo_calls == [], _vo_calls)
t("measure equal objects no gap", g is None, g)

def mock_psql_gap(sql):
    if "FROM search_coverage" in sql and "объектов_витрины" in sql:
        return [["document_doc", 120, 100]]
    return []
A.psql = mock_psql_gap
g = A._measure_health_gap()
A.psql = real_psql2
t("measure coverage missing", g and g["rows_missing"] == 20 and g["entities"] == 1, g)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
