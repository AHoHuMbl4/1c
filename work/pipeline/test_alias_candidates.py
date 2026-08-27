#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Офлайн-замок прибора кандидатов алиасов (С5).

Запуск: python3 work/pipeline/test_alias_candidates.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPE = os.path.join(ROOT, "work", "pipeline")
FIX = os.path.join(PIPE, "fixtures")
sys.path.insert(0, PIPE)

import alias_candidates as AC  # noqa: E402

PASS = 0
FAIL: list[str] = []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:160]) if detail else "")


journal = AC.load_journal_file(os.path.join(FIX, "alias_candidates_journal.tsv"))
only_bad = [r for r in journal if r.outcome in AC.JOURNAL_OUTCOMES]
top = AC.top_terms(only_bad, 5)
t("journal rows loaded", len(journal) == 15, len(journal))
t("journal clarify+no_data", len(only_bad) >= 10, len(only_bad))
t("top terms non-empty", len(top) >= 3, top)
top_words = [w for w, _ in top]
t("top includes петель", "петель" in top_words, top_words)
t("top includes склад", "склад" in top_words or "складе" in top_words, top_words)
t("answer row ignored in freq", all(w != "продали" or c < 2 for w, c in top), top)

terms = {w for w, _ in top}
from_journal = AC.candidates_from_journal(journal, terms)
t("journal candidates", len(from_journal) >= 2, len(from_journal))
t(
    "journal source tag",
    all(src.startswith("journal_") for _, _, src in from_journal),
    from_journal[:3],
)

blocked = bool(AC.WRITE_SQL_RE.search("INSERT INTO t VALUES (1)"))
t("write sql blocked", blocked)

gold = AC.scorer.load_gold(os.path.join(FIX, "alias_candidates_gold.tsv"))
t("gold fixture rows", len(gold) == 5, len(gold))
subset = AC.gold_questions_for_term(gold, "петель", 3, AC.random.Random(1))
t("gold subset by term", len(subset) >= 1, len(subset))
t(
    "expected entity parse",
    AC.expected_entity(gold[2]["sql"]) == "catalog_номенклатура",
    AC.expected_entity(gold[2]["sql"]),
)

cand_ok = AC.Candidate("петель", "catalog_номенклатура", "journal_atoms", journal_freq=3)
AC.validate_candidate(cand_ok, gold, 3, None, "search_entity_alias", "alias_idx", True, AC.random.Random(2))
t("validate dry_run", cand_ok.check_result == "dry_run", cand_ok.check_result)


def fake_rank(dsn, question, entity, alias_table, index):
    exp = AC.expected_entity(next(r["sql"] for r in gold if r["q"] == question))
    return 1 if entity == exp else 0


with patch.object(AC, "alias_rank", side_effect=fake_rank):
    c1 = AC.Candidate("позиций", "catalog_номенклатура", "journal_atoms", journal_freq=1)
    AC.validate_candidate(c1, gold, 3, "fake", "t", "i", False, AC.random.Random(4))
    t("validate pass mock", c1.check_result == "pass", c1.check_result)
    c2 = AC.Candidate("клиент", "catalog_контрагенты", "journal_atoms", journal_freq=1)
    AC.validate_candidate(c2, gold, 3, "fake", "t", "i", False, AC.random.Random(5))
    t("validate fail mock", c2.check_result in ("fail", "partial"), c2.check_result)

merged = AC.merge_candidates(from_journal[:4], {w: n for w, n in top})
for c in merged:
    AC.validate_candidate(c, gold, 2, None, "t", "i", True, AC.random.Random(6))
tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False)
tmp.close()
AC.write_tsv(tmp.name, merged)
text = open(tmp.name, encoding="utf-8").read()
lines = [ln for ln in text.strip().splitlines() if ln]
t("tsv header", lines[0].startswith("term\tcandidate_link\tsource\t"), lines[0][:60])
t("tsv data rows", len(lines) == len(merged) + 1, len(lines))
t("tsv columns", len(lines[1].split("\t")) == 9, lines[1])
os.unlink(tmp.name)

out_path = os.path.join(tempfile.gettempdir(), "alias_cand_test_out.tsv")
rc = AC.main(
    [
        "--journal-file",
        os.path.join(FIX, "alias_candidates_journal.tsv"),
        "--gold-file",
        os.path.join(FIX, "alias_candidates_gold.tsv"),
        "--top",
        "5",
        "--sample",
        "3",
        "--out",
        out_path,
        "--seed",
        "42",
    ]
)
t("cli exit 0", rc == 0, rc)
t("cli wrote file", os.path.isfile(out_path), out_path)
if os.path.isfile(out_path):
    cli_lines = open(out_path, encoding="utf-8").read().strip().splitlines()
    t("cli candidates>0", len(cli_lines) > 1, len(cli_lines))
    os.unlink(out_path)

calls: list[str] = []


def spy_psql(dsn, sql, field_sep="\x1f"):
    calls.append(sql.strip()[:40])
    if "wiki_entity_facts" in sql:
        return [["[]"]]
    return []


with patch.object(AC, "psql_rows", side_effect=spy_psql):
    with patch.object(AC, "candidates_from_model", return_value=[]):
        AC.main(
            [
                "--journal-file",
                os.path.join(FIX, "alias_candidates_journal.tsv"),
                "--gold-file",
                os.path.join(FIX, "alias_candidates_gold.tsv"),
                "--top",
                "3",
                "--apply",
                "--dsn",
                "host=fake",
                "--out",
                out_path,
            ]
        )
t("apply no INSERT", not any("INSERT" in c.upper() for c in calls), calls[:5])
if os.path.isfile(out_path):
    os.unlink(out_path)

print("\nИТОГ: %d/%d" % (PASS, PASS + len(FAIL)))
if FAIL:
    print("FAIL:", ", ".join(FAIL))
    sys.exit(1)
