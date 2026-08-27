#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок набора неоднозначности okna (И1 / Э3).

Без сети и без живой базы: разбор TSV, параметр AB_AMBIGUOUS, режимы clarify/kind.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ab_scorer as S  # noqa: E402

PASS, FAIL = 0, []
AMB_FILE = os.path.join(ROOT, "ab-ambiguous-okna.tsv")
AMB_N = 18


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


def test_load_ambiguous_set():
    rows = S.load_gold(AMB_FILE)
    t("ambiguous: %d вопросов" % AMB_N, len(rows) == AMB_N, len(rows))
    modes = {r.get("mode") for r in rows}
    t("ambiguous: только clarify/kind (вид ответа)",
      modes <= {"clarify", "kind"} and "clarify" in modes and "kind" in modes,
      modes)
    t("ambiguous: нет digits/name (не величина)",
      not (modes & {"digits", "name"}), modes)
    clar = [r for r in rows if r.get("mode") == "clarify"]
    kind = [r for r in rows if r.get("mode") == "kind"]
    t("ambiguous: clarify ≥ 10 (оси уточнения)", len(clar) >= 10, len(clar))
    t("ambiguous: kind ≥ 5 (no_data / answer по SQL)", len(kind) >= 5, len(kind))
    qs = [r["q"].lower() for r in rows]
    t("ambiguous: период «за год»", any("за год" in q for q in qs), qs[:3])
    t("ambiguous: склад", any("склад" in q for q in qs), qs)
    t("ambiguous: вне 1С (президент)", any("президент" in q for q in qs), qs)
    # игла clarify — литерал, не SQL
    needle_ok = 0
    for r in clar:
        kind_n, spec = S.row_want_spec(r)
        if kind_n == "needle" and spec:
            needle_ok += 1
    t("ambiguous: у clarify есть игла оси", needle_ok == len(clar),
      (needle_ok, len(clar)))
    # kind: SQL-эталон (SELECT …)
    sql_kind = 0
    for r in kind:
        kind_n, spec = S.row_want_spec(r)
        if kind_n == "sql" and S._is_sql_spec(spec):
            sql_kind += 1
    t("ambiguous: у kind — SQL эталон", sql_kind == len(kind),
      (sql_kind, len(kind)))


def test_param_ambiguous():
    path = S.resolve_gold_file(environ={}, script_dir=ROOT)
    t("умолч.: ambiguous не выбран",
      "ambiguous" not in os.path.basename(path), path)
    path_a = S.resolve_gold_file(
        environ={"AB_AMBIGUOUS": "okna"}, script_dir=ROOT)
    t("AB_AMBIGUOUS=okna → ab-ambiguous-okna.tsv",
      os.path.basename(path_a) == "ab-ambiguous-okna.tsv", path_a)
    path1 = S.resolve_gold_file(
        environ={"AB_AMBIGUOUS": "1"}, script_dir=ROOT)
    t("AB_AMBIGUOUS=1 → тот же файл",
      os.path.basename(path1) == "ab-ambiguous-okna.tsv", path1)
    path_exp = S.resolve_gold_file(
        environ={
            "AB_AMBIGUOUS": "okna",
            "AB_GOLD_FILE": "/tmp/custom-gold.tsv",
        },
        script_dir=ROOT)
    t("AB_GOLD_FILE перекрывает ambiguous",
      path_exp == "/tmp/custom-gold.tsv", path_exp)
    path_both = S.resolve_gold_file(
        environ={"AB_CONTOUR": "okna", "AB_AMBIGUOUS": "okna"},
        script_dir=ROOT)
    t("CONTOUR+AMBIGUOUS → ambiguous (приоритет)",
      os.path.basename(path_both) == "ab-ambiguous-okna.tsv", path_both)
    path_cal = S.resolve_gold_file(
        environ={"AB_AMBIGUOUS": "okna", "AB_CALENDAR_AXIS": "okna"},
        script_dir=ROOT)
    t("AMBIGUOUS сильнее CALENDAR_AXIS",
      os.path.basename(path_cal) == "ab-ambiguous-okna.tsv", path_cal)
    path_probe = S.resolve_gold_file(
        environ={"AB_PROBE": "okna"}, script_dir=ROOT)
    t("PROBE без AMBIGUOUS → probe-okna",
      os.path.basename(path_probe) == "ab-probe-okna.tsv", path_probe)


def _load_via_exit(path):
    code = (
        "import sys; sys.path.insert(0, %r); import ab_scorer as S; "
        "S.load_gold(%r)"
    ) % (ROOT, path)
    p = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True)
    return p.returncode, (p.stderr or "") + (p.stdout or "")


def test_empty_broken_errors():
    with tempfile.TemporaryDirectory() as td:
        empty = os.path.join(td, "empty.tsv")
        open(empty, "w", encoding="utf-8").write("# только\n\n")
        rc, err = _load_via_exit(empty)
        t("пустой набор → exit 1", rc == 1, (rc, err[:120]))
        t("пустой набор → текст ошибки",
          "пуст" in err.lower() or "битый" in err.lower(), err[:160])


def main():
    test_load_ambiguous_set()
    test_param_ambiguous()
    test_empty_broken_errors()
    print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
          else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
