#!/usr/bin/env python3
"""S1: атомы ответа — живые символы; whitelist veto снесён."""
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


t("pair_slots_only: >1 → True, 1 → False",
  A.pair_slots_only(2) is True and A.pair_slots_only(1) is False)
t("render_atom_pair callable", callable(A.render_atom_pair))
t("fill_atom_pairs callable", callable(A.fill_atom_pairs))
t("S1: atom_whitelist_* GONE",
  not hasattr(A, "atom_whitelist_labels")
  and not hasattr(A, "atom_whitelist_numbers"))
t("answer_slot_mode callable", callable(getattr(A, "answer_slot_mode", None)))

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
