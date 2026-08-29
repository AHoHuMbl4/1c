#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок набора оси календаря (§7bis / calendar-axis-design §5.2).

Без сети и без живой базы: разбор TSV, параметр AB_CALENDAR_AXIS, ошибки пустого/битого.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ab_scorer as S  # noqa: E402

PASS, FAIL = 0, []
AXIS_FILE = os.path.join(ROOT, "ab-calendar-axis-okna.tsv")
# §5.2: шесть пунктов (включая follow-up с нажатием)
AXIS_N = 6


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


def test_load_axis_set():
    rows = S.load_gold(AXIS_FILE)
    t("ось: %d вопросов (=§5.2)" % AXIS_N, len(rows) == AXIS_N, len(rows))
    modes = {r.get("mode") for r in rows}
    t("ось: режимы digits/kind/clarify",
      {"digits", "kind", "clarify"} <= modes, modes)
    qs = [r["q"] for r in rows]
    t("ось: рабочие дни недели",
      any("рабочие дни этой недели" in q.lower() for q in qs), qs[:2])
    t("ось: будни с начала месяца",
      any("будни" in q.lower() for q in qs), qs)
    t("ось: календарная неделя",
      any("календарн" in q.lower() for q in qs), qs)
    t("ось: с 1 по 15",
      any("1 по 15" in q for q in qs), qs)
    t("ось: праздники",
      any("праздник" in q.lower() for q in qs), qs)
    clar = [r for r in rows if r.get("mode") == "clarify"]
    t("ось: follow-up clarify + игла",
      len(clar) == 1 and "рабоч" in (clar[0].get("sql") or "").lower(),
      clar)
    kind_n, spec = S.row_want_spec(clar[0])
    t("ось: игла clarify без psql",
      kind_n == "needle" and "рабоч" in spec.lower(), (kind_n, spec))


def test_param_default_off():
    path = S.resolve_gold_file(environ={}, script_dir=ROOT)
    t("умолч.: набор оси не выбран",
      os.path.basename(path) == "ab-gold.tsv", path)
    path_cal = S.resolve_gold_file(
        environ={"AB_CALENDAR_AXIS": "okna"}, script_dir=ROOT)
    t("AB_CALENDAR_AXIS=okna → ab-calendar-axis-okna.tsv",
      os.path.basename(path_cal) == "ab-calendar-axis-okna.tsv", path_cal)
    path1 = S.resolve_gold_file(
        environ={"AB_CALENDAR_AXIS": "1"}, script_dir=ROOT)
    t("AB_CALENDAR_AXIS=1 → тот же файл",
      os.path.basename(path1) == "ab-calendar-axis-okna.tsv", path1)
    path_off = S.resolve_gold_file(
        environ={"AB_CALENDAR_AXIS": ""}, script_dir=ROOT)
    t("AB_CALENDAR_AXIS пуст → не ось",
      "calendar-axis" not in os.path.basename(path_off), path_off)
    path_exp = S.resolve_gold_file(
        environ={
            "AB_CALENDAR_AXIS": "okna",
            "AB_GOLD_FILE": "/tmp/custom-gold.tsv",
        },
        script_dir=ROOT)
    t("AB_GOLD_FILE перекрывает ось",
      path_exp == "/tmp/custom-gold.tsv", path_exp)
    path_probe = S.resolve_gold_file(
        environ={"AB_PROBE": "okna"}, script_dir=ROOT)
    t("PROBE без оси → probe-okna",
      os.path.basename(path_probe) == "ab-probe-okna.tsv", path_probe)
    path_both = S.resolve_gold_file(
        environ={"AB_CONTOUR": "okna", "AB_CALENDAR_AXIS": "1"},
        script_dir=ROOT)
    t("CONTOUR+ось → файл оси",
      os.path.basename(path_both) == "ab-calendar-axis-okna.tsv", path_both)


def test_k2_offline_hooks():
    """K2: офлайн-хуки period repair и calendar block (без базы)."""
    import serene_ask as A  # noqa: E402

    mdr = A.month_day_range_from_question("Сколько отгрузили с 1 по 15", "2026-08-29")
    t("K2: month_day_range",
      mdr and mdr.get("from") == "2026-08-01" and mdr.get("to") == "2026-08-15", mdr)
    A.calendar_day_basis_phrases = lambda: {
        "working_days": ["рабочие дни"], "holiday": ["праздники"]}
    A.calendar_registers = lambda: frozenset()
    A.calendar_working_day_keys = lambda: frozenset()
    A.calendar_map_rows = lambda: []
    blk = A.calendar_axis_unavailable_block("Продажи в праздники")
    t("K2: праздники no_data",
      blk and blk.get("kind") == "no_data", blk)


def _load_via_exit(path):
    """load_gold при пустом/битом зовёт sys.exit(1); ловим код и stderr."""
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
        open(empty, "w", encoding="utf-8").write(
            "# только комментарий\n\n")
        rc, err = _load_via_exit(empty)
        t("пустой набор → exit 1", rc == 1, (rc, err[:120]))
        t("пустой набор → текст ошибки",
          "пуст" in err.lower() or "битый" in err.lower(), err[:160])

        broken = os.path.join(td, "broken.tsv")
        open(broken, "w", encoding="utf-8").write(
            "нет таба здесь\nещё\tслишком\tмного\tколонок\tздесь\n")
        rc2, err2 = _load_via_exit(broken)
        t("битый набор → exit 1", rc2 == 1, (rc2, err2[:120]))
        t("битый набор → внятная ошибка",
          "битый" in err2.lower() or "пуст" in err2.lower()
          or "табул" in err2.lower() or "колонок" in err2.lower(),
          err2[:200])

        missing = os.path.join(td, "no-such.tsv")
        rc3, err3 = _load_via_exit(missing)
        t("нет файла → exit 1", rc3 == 1, (rc3, err3[:120]))
        t("нет файла → текст «нет набора»",
          "нет набора" in err3.lower(), err3[:160])


def main():
    test_load_axis_set()
    test_param_default_off()
    test_empty_broken_errors()
    test_k2_offline_hooks()
    print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
          else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
