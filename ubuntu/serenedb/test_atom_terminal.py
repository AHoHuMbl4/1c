#!/usr/bin/env python3
"""S1: atom_terminal_gate_text (щель) + render_atom_pair."""
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


t("atom_terminal_gate_text callable", callable(A.atom_terminal_gate_text))
t("render_atom_pair callable", callable(A.render_atom_pair))
t("S1: fork_outcome stubs GONE",
  not hasattr(A, "fork_outcome_a") and not hasattr(A, "fork_outcome_b"))

atom = {"proof_status": getattr(A, "PROOF_COMPUTED", "computed"),
        "exact_value": 42.5, "measure_label": "Всего", "operation": "sum"}
# ASK_ATOM_TERMINAL off by default → refuse/empty ok; with agg+TOTAL_TEXT may fill
txt = A.atom_terminal_gate_text(atom, "сколько?", agg={"count": 1, "sum": 42.5})
t("atom_terminal_gate_text returns str-or-empty",
  isinstance(txt, str), repr(txt)[:80])
pair = A.render_atom_pair(atom)
t("render_atom_pair smoke", pair is None or isinstance(pair, str), pair)

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
