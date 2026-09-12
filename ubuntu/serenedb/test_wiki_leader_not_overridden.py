#!/usr/bin/env python3
"""S1: wiki-лидер на одном пути; fork-gate снесён.

Прежний resolve_fork_wiki_gate / fork_clarify_from_wiki_pool ушли с
fork-outcomes. Живы: wiki_leader_alive, wiki-каскад в z20, identity-патч.
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
from ask._bootstrap import _patch_z20_wiki_primary  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


t("wiki_leader_alive callable", callable(A.wiki_leader_alive))
t("S1: fork_clarify_from_wiki_pool GONE",
  not hasattr(A, "fork_clarify_from_wiki_pool"))
t("S1: resolve_fork_wiki_gate GONE",
  not hasattr(A, "resolve_fork_wiki_gate"))

z20 = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
t("диск: wiki_primary_entity_cascade в z20",
  "wiki_primary_entity_cascade" in z20)
t("диск: fork_deferred_to_wiki снесён",
  "fork_deferred_to_wiki" not in z20)
t("диск: fork_clarify_from_wiki_pool снесён",
  "fork_clarify_from_wiki_pool" not in z20)
patched = _patch_z20_wiki_primary(z20)
t("S1: patch identity", patched == z20)
t("S1: cascade после identity-патча",
  "wiki_primary_entity_cascade" in patched)

# wiki_leader_alive: yes=1 → True
diag1 = {
    "wiki_hybrid_pick": True,
    "wiki_verify": "document_alpha",
    "wiki_verify_yes": 1,
    "wiki_verify_no": 5,
    "wiki_pool": ["document_alpha", "document_beta"],
}
t("wiki_leader_alive: yes=1",
  A.wiki_leader_alive(diag1, ["document_alpha"]) is True)
diag_tie = dict(diag1, wiki_verify_yes=2)
t("wiki_leader_alive: tie yes=2 → False",
  A.wiki_leader_alive(diag_tie, ["document_alpha"]) is False)

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(1 if FAIL else 0)
