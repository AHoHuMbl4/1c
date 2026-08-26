#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Офлайн-замок И4: приёмочный набор не пересекается с рабочими.

Приёмочный (заморожен): docs/ACCEPTANCE_UT.md (58).
Рабочие: ab-gold-okna / probe / ab-gold / golden-questions / calendar-axis.

Падает, если вопрос из приёмки появился в рабочем наборе (нормализованный текст).
Сеть, psql, scorer-прогон не нужны. ab_scorer / serene_ask не импортируются.
См. docs/GOLD_SETS.md.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
DOC = os.path.join(REPO, "docs", "GOLD_SETS.md")
ACCEPTANCE_UT = os.path.join(REPO, "docs", "ACCEPTANCE_UT.md")

# Роли — канон из GOLD_SETS.md §3. Менять только вместе с документом.
WORKING = [
    ("ab-gold-okna.tsv", 25),
    ("ab-probe-okna.tsv", 8),
    ("ab-gold.tsv", 8),
    ("golden-questions.txt", 8),
    ("ab-calendar-axis-okna.tsv", 6),
]

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


def norm_q(s: str) -> str:
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s.strip(" «»\"'?.!,;:")


def load_tsv_questions(path: str) -> list[str]:
    qs: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qs.append(line.split("\t", 1)[0].strip())
    return qs


def load_txt_questions(path: str) -> list[str]:
    qs: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qs.append(line)
    return qs


def load_acceptance_ut(path: str) -> list[str]:
    text = open(path, encoding="utf-8").read()
    return [
        m.group(2)
        for m in re.finditer(r"^\*\*(\d+)\. «(.+?)»\*\*", text, flags=re.M)
    ]


def test_files_exist() -> None:
    t("есть docs/GOLD_SETS.md", os.path.isfile(DOC), DOC)
    t("есть docs/ACCEPTANCE_UT.md", os.path.isfile(ACCEPTANCE_UT), ACCEPTANCE_UT)
    for name, _n in WORKING:
        path = os.path.join(ROOT, name)
        t("рабочий файл %s" % name, os.path.isfile(path), path)


def test_doc_declares_roles() -> None:
    if not os.path.isfile(DOC):
        t("GOLD_SETS объявляет приёмку", False, "нет файла")
        return
    text = open(DOC, encoding="utf-8").read()
    t(
        "GOLD_SETS: приёмочный = ACCEPTANCE_UT",
        "ACCEPTANCE_UT.md" in text and "заморожен" in text.lower(),
    )
    t(
        "GOLD_SETS: рабочий = ab-gold-okna",
        "ab-gold-okna.tsv" in text and "правки" in text,
    )
    t(
        "GOLD_SETS: правило пересечения",
        "test_gold_sets_split.py" in text,
    )


def test_acceptance_count() -> None:
    qs = load_acceptance_ut(ACCEPTANCE_UT)
    t("приёмка: 58 вопросов", len(qs) == 58, len(qs))
    # уникальность внутри приёмки
    norms = [norm_q(q) for q in qs]
    dup = [n for n in set(norms) if norms.count(n) > 1]
    t("приёмка: без внутренних дублей", not dup, dup[:5])


def test_working_counts() -> None:
    for name, expect in WORKING:
        path = os.path.join(ROOT, name)
        if name.endswith(".txt"):
            qs = load_txt_questions(path)
        else:
            qs = load_tsv_questions(path)
        t("рабочий %s: %d вопросов" % (name, expect), len(qs) == expect, len(qs))


def test_no_acceptance_in_working() -> None:
    acc = {norm_q(q): q for q in load_acceptance_ut(ACCEPTANCE_UT)}
    leaks: list[str] = []
    for name, _n in WORKING:
        path = os.path.join(ROOT, name)
        if name.endswith(".txt"):
            qs = load_txt_questions(path)
        else:
            qs = load_tsv_questions(path)
        for q in qs:
            n = norm_q(q)
            if n in acc:
                leaks.append("%s ← %r (приёмка: %r)" % (name, q, acc[n]))
    t(
        "приёмка ∩ рабочие = ∅",
        not leaks,
        "; ".join(leaks[:8]) if leaks else "",
    )
    t("число утечек = 0", len(leaks) == 0, len(leaks))


def test_probe_subset_of_gold_okna_mostly() -> None:
    """Диагностика реестра: probe почти ⊂ gold-okna (факт §4 GOLD_SETS). Не гейт ролей."""
    gold = {norm_q(q) for q in load_tsv_questions(os.path.join(ROOT, "ab-gold-okna.tsv"))}
    probe = load_tsv_questions(os.path.join(ROOT, "ab-probe-okna.tsv"))
    inter = sum(1 for q in probe if norm_q(q) in gold)
    t("probe ∩ gold-okna = 7 (подмножество)", inter == 7, inter)


def main() -> int:
    test_files_exist()
    test_doc_declares_roles()
    test_acceptance_count()
    test_working_counts()
    test_no_acceptance_in_working()
    test_probe_subset_of_gold_okna_mostly()
    print()
    print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
    if FAIL:
        print("провалы:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
