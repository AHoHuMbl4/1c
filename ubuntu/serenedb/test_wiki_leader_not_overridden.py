#!/usr/bin/env python3
"""В4 repair: wiki-лидер не перебивается fork-меню (формула №15).

  (1) wiki-лидер (yes=1) + fork классов>1 → defer (тракт к answer), меню нет,
      diag.fork_deferred_to_wiki=True
  (2) wiki tie (yes=2) + fork → меню из wiki-карточек (options.src ⊆ wiki_pool)
  (3) wiki-пула нет + fork классов>1 → меню из левых src не строится (no_data)

Запуск: python3 ubuntu/serenedb/test_wiki_leader_not_overridden.py
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


# ── символы и патч z20 ────────────────────────────────────────────────────────
t("wiki_leader_alive callable", callable(A.wiki_leader_alive))
t("fork_clarify_from_wiki_pool callable",
  callable(A.fork_clarify_from_wiki_pool))
t("resolve_fork_wiki_gate callable", callable(A.resolve_fork_wiki_gate))

z20 = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
# Волна W: V4c маркеры на ДИСКЕ (долг патча закрыт); патч — no-op по E–H.
t("диск: fork_deferred_to_wiki в z20",
  "fork_deferred_to_wiki" in z20)
t("диск: fork_clarify_from_wiki_pool в z20",
  "fork_clarify_from_wiki_pool" in z20)
t("диск: early-clarify гейт wiki_leader_alive",
  "or wiki_leader_alive(diag, picked))" in z20)
patched = _patch_z20_wiki_primary(z20)
t("bootstrap: fork_deferred_to_wiki после патча",
  "fork_deferred_to_wiki" in patched)
t("bootstrap: fork_clarify_from_wiki_pool после патча",
  "fork_clarify_from_wiki_pool" in patched)
t("bootstrap: early-clarify гейт wiki_leader_alive после патча",
  "or wiki_leader_alive(diag, picked))" in patched)


# ── (1) лидер → defer, меню нет, флаг diag ────────────────────────────────────
leader = "document_alpha"
diag1 = {
    "wiki_hybrid_pick": True,
    "wiki_verify": leader,
    "wiki_verify_yes": 1,
    "wiki_verify_no": 5,
    "wiki_pool": [leader, "document_beta", "catalog_gamma"],
    "fork": {"classes": 5},
}
act1, pay1 = A.resolve_fork_wiki_gate(
    diag1, [leader], "B",
    {"classes": [{"srcs": ["x"]}, {"srcs": ["y"]}]},
    question="q")
t("leader+fork→defer", act1 == "defer", act1)
t("leader: меню нет", pay1 is None)
t("leader: fork_deferred_to_wiki",
  diag1.get("fork_deferred_to_wiki") is True)
t("leader: wiki_leader_alive",
  A.wiki_leader_alive(diag1, [leader]) is True)
# «kind=answer по лидеру»: defer оставляет picked — тракт не уходит в clarify
t("leader: picked цел, не clarify",
  act1 == "defer" and pay1 is None
  and not (isinstance(pay1, dict) and pay1.get("kind") == "clarify"))


# ── (2) tie (yes=2) → меню из wiki_pool ───────────────────────────────────────
pool2 = ["document_a", "document_b", "catalog_c"]
diag2 = {
    "wiki_hybrid_pick": False,
    "wiki_verify": "clarify",
    "wiki_verify_yes": 2,
    "wiki_verify_tie": pool2[:2],
    "wiki_pool": pool2,
    "fork": {"classes": 3},
}
# psql/mk_opts offline: подмена
_real_psql = A.psql
A.psql = lambda q: [(s, "L-%s" % s) for s in pool2]
_real_enrich = getattr(A, "wiki_passport_enrich", None)
A.wiki_passport_enrich = lambda cards: [
    {"src_table": c["src_table"], "name": "N-%s" % c["src_table"],
     "wiki_body": "body"} for c in cards]
try:
    act2, pay2 = A.resolve_fork_wiki_gate(
        diag2, [], "B",
        {"classes": [{"srcs": ["fork_left_1"]},
                     {"srcs": ["fork_left_2"]},
                     {"srcs": ["fork_left_3"]}]},
        question="q")
finally:
    A.psql = _real_psql
    if _real_enrich is not None:
        A.wiki_passport_enrich = _real_enrich

t("tie+fork→clarify", act2 == "clarify", act2)
opts2 = (pay2 or {}).get("options") or []
srcs2 = [o.get("src") for o in opts2 if o.get("src")]
t("tie: options из wiki_pool",
  act2 == "clarify" and len(srcs2) >= 2
  and set(srcs2) <= set(pool2), srcs2)
t("tie: fork-ветки вне пула не попали",
  not any(s.startswith("fork_left") for s in srcs2), srcs2)
t("tie: wiki_leader_alive ложь",
  A.wiki_leader_alive(diag2, pool2[:1]) is False)


# ── (3) wiki-пула нет → no_data, не меню из левых src ─────────────────────────
diag3 = {
    "wiki_hybrid_pick": False,
    "wiki_pool": [],
    "fork": {"classes": 4},
}
act3, pay3 = A.resolve_fork_wiki_gate(
    diag3, [], "C",
    {"reason": "multi_class_menu",
     "classes": [{"srcs": ["left_a"]}, {"srcs": ["left_b"]}]},
    question="q")
t("no-pool+fork→no_data", act3 == "no_data", act3)
t("no-pool: options пуст",
  not ((pay3 or {}).get("options") or []))
t("no-pool: left src не в ответе",
  "left_a" not in str(pay3) and "left_b" not in str(pay3))

# фильтр fork_outcome_c: entity-src без пула → None
fake_clarify = {
    "kind": "clarify",
    "options": [{"src": "left_a", "label": "A"},
                {"src": "left_b", "label": "B"}],
    "sources": ["A", "B"],
}
t("fork_c_options: без пула + src → None",
  A.fork_c_options_without_left_srcs(fake_clarify, []) is None)
kept = A.fork_c_options_without_left_srcs(
    fake_clarify, ["left_a", "left_b", "other"])
t("fork_c_options: пересечение с пулом",
  kept is not None
  and {o["src"] for o in kept["options"]} == {"left_a", "left_b"})
t("fork_c_options: place src='' проходит",
  A.fork_c_options_without_left_srcs(
      {"kind": "clarify",
       "options": [{"src": "", "label": "W1"}, {"src": "", "label": "W2"}],
       "sources": ["W1", "W2"]},
      []) is not None)


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
