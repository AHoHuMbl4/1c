#!/usr/bin/env python3
"""S1+S3: action_class / fork_classes / event_duel снесены; щели и intent живы."""
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


for name in ("fork_classes", "fork_classes_windowed", "fork_detector_scan",
             "resolve_fork_outcome", "event_duel_applies"):
    t("S1/S3 GONE: " + name, not hasattr(A, name))

t("parse_intent callable", callable(A.parse_intent))
t("pair_slots_only", A.pair_slots_only(2) is True)
t("fork_labels_of slit", callable(A.fork_labels_of))

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
