#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Офлайн-замок: ab-acceptance-ut.tsv ↔ docs/ACCEPTANCE_UT.md (заморозка 58).

Падает, если вопрос изменён, добавлен или удалён относительно приёмочного MD.
Сеть, psql, прогон скорера не нужны. serene_ask не импортируется.
См. docs/GOLD_SETS.md (приёмка заморожена).
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
MD = os.path.join(REPO, "docs", "ACCEPTANCE_UT.md")
TSV = os.path.join(ROOT, "ab-acceptance-ut.tsv")
EXPECT_N = 58

PASS = 0
FAIL: list[str] = []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def load_md_questions(path: str) -> list[str]:
    """Тот же разбор заголовков, что test_gold_sets_split / run_acceptance."""
    text = open(path, encoding="utf-8").read()
    return [
        m.group(2)
        for m in re.finditer(r"^\*\*(\d+)\. «(.+?)»\*\*", text, flags=re.M)
    ]


def load_tsv_rows(path: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                raise ValueError("ожидали 3 колонки, получили %d: %s" % (
                    len(parts), line[:80]))
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def test_files() -> None:
    t("есть ACCEPTANCE_UT.md", os.path.isfile(MD), MD)
    t("есть ab-acceptance-ut.tsv", os.path.isfile(TSV), TSV)


def test_counts_and_verbatim() -> None:
    md_qs = load_md_questions(MD)
    rows = load_tsv_rows(TSV)
    tsv_qs = [r[0] for r in rows]

    t("MD: %d вопросов" % EXPECT_N, len(md_qs) == EXPECT_N, len(md_qs))
    t("TSV: %d строк данных" % EXPECT_N, len(rows) == EXPECT_N, len(rows))
    t("число строк TSV = число вопросов MD", len(rows) == len(md_qs),
      "tsv=%d md=%d" % (len(rows), len(md_qs)))

    # дословное совпадение по порядку (заморозка формулировок)
    same = md_qs == tsv_qs
    detail = ""
    if not same:
        for i, (a, b) in enumerate(zip(md_qs, tsv_qs), 1):
            if a != b:
                detail = "первая рассинхронизация №%d md=%r tsv=%r" % (i, a, b)
                break
        if len(md_qs) != len(tsv_qs):
            only_md = set(md_qs) - set(tsv_qs)
            only_tsv = set(tsv_qs) - set(md_qs)
            detail = "only_md=%s only_tsv=%s" % (
                list(only_md)[:3], list(only_tsv)[:3])
    t("каждый вопрос MD дословно в TSV (порядок)", same, detail)

    # множество: ничего не добавили и не выкинули
    t("множество вопросов MD == TSV", set(md_qs) == set(tsv_qs),
      "Δ md-tsv=%s tsv-md=%s" % (
          list(set(md_qs) - set(tsv_qs))[:3],
          list(set(tsv_qs) - set(md_qs))[:3]))


def test_modes_known() -> None:
    rows = load_tsv_rows(TSV)
    allowed = {"digits", "kind", "clarify", "name", "unchecked"}
    bad = [(r[0][:40], r[2]) for r in rows if r[2].strip().lower() not in allowed]
    t("режимы из допустимого набора load_gold/отчёта", not bad, bad[:5])
    unchecked = [r for r in rows if r[2].strip().lower() == "unchecked"]
    t("unchecked → пустая средняя колонка",
      all(not r[1].strip() for r in unchecked), unchecked[:3])
    # сейчас в MD у всех 58 есть ожидание (эталон/kind/SQL в теле) → unchecked = 0
    t("unchecked = 0 (у всех 58 есть ожидание в MD)",
      len(unchecked) == 0, len(unchecked))
    kind_rows = [r for r in rows if r[2].strip().lower() == "kind"]
    t("kind → SQL-эталон (SELECT…)",
      all(re.match(r"(?is)^\s*(with|select)\b", r[1] or "") for r in kind_rows),
      kind_rows[:2])
    digits = [r for r in rows if r[2].strip().lower() == "digits"]
    t("digits → SQL (WITH/SELECT)",
      all(re.match(r"(?is)^\s*(with|select)\b", r[1] or "") for r in digits),
      [r[0][:40] for r in digits if not re.match(r"(?is)^\s*(with|select)\b", r[1] or "")][:3])


def test_load_gold() -> None:
    """load_gold читает TSV без сети/БД (только разбор файла)."""
    sys.path.insert(0, ROOT)
    import ab_scorer as S  # noqa: WPS433

    rows = S.load_gold(TSV)
    t("load_gold: %d строк" % EXPECT_N, len(rows) == EXPECT_N, len(rows))
    md_qs = load_md_questions(MD)
    got = [r["q"] for r in rows]
    t("load_gold: вопросы дословно = MD", got == md_qs,
      "first diff" if got != md_qs else "")
    modes = {r.get("mode") for r in rows}
    t("load_gold: есть digits/kind/clarify",
      {"digits", "kind", "clarify"} <= modes, modes)


def main() -> int:
    test_files()
    test_counts_and_verbatim()
    test_modes_known()
    test_load_gold()
    print()
    print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
    if FAIL:
        print("провалы:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
