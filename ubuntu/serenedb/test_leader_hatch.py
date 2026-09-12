#!/usr/bin/env python3
"""S1 некролог: fork leader hatch снесены с fork/veto-зонами.

Щели onepath сохранены (labels / terminal / accounting / pair_slots / headline).
Запуск: python3 ubuntu/serenedb/test_leader_hatch.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
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
        print("FAIL-", name, detail)


DEAD = ['fork_detector_scan', 'resolve_fork_outcome', 'fork_outcome_a', 'fork_outcome_b', 'fork_outcome_c', 'fork_outcome_unique', 'pick_measure', 'unresolved_quantity', 'alias_supported', 'arbiter_figures', 'atom_whitelist_labels', 'atom_whitelist_numbers', 'pair_unanswered', 'mute_measure_blocks', 'figures_numbers']
SLITS = ['fork_labels_of', 'fork_labels_covering', 'atom_terminal_gate_text', 'stock_balance_is_sales_noise', 'pair_slots_only', 'question_expects_accounting_data', '_fork_sum_headline_pool']

for name in DEAD:
    t("S1 GONE: " + name, not hasattr(A, name))

for name in SLITS:
    t("S1 slit: " + name, callable(getattr(A, name, None)) or getattr(A, name, None) is not None)

# smoke slits
t("fork_labels_of empty key → {}", A.fork_labels_of("", ["a"]) == {})
t("fork_labels_covering empty → ({}, None)", A.fork_labels_covering([]) == ({}, None))
t("pair_slots_only", A.pair_slots_only(2) is True and A.pair_slots_only(1) is False)
t("stock_balance_is_sales_noise реализация",
  A.stock_balance_is_sales_noise("accumulationregister_реализациятмц") is True)
t("atom_terminal_gate_text callable", callable(A.atom_terminal_gate_text))

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
