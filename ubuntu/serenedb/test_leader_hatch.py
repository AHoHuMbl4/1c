#!/usr/bin/env python3
"""В4 замок: fork-авто B/A снесены; C меню/unsigned жив.

Замки:
  · B-авто / A-авто → None (негатив);
  · C unsigned: число + FORK_OTHER_READING, без имён веток;
  · sales_canon_force_pool снесён в В2 — символа нет;
  · resolve по-прежнему классифицирует B/A.

Запуск: python3 ubuntu/serenedb/test_leader_hatch.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


cls2 = A.fork_classes({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)},
                      "сумма", want="sum",
                      rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}


def _labs_ok(fk, srcs):
    return {"a": "Отгрузки", "b": "Оплаты"}


A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(
    cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("resolve → B при подписях", out == "B")
bres = A.fork_outcome_b("сколько?", pay, {}, picked_src="b")
t("В4: fork_outcome_b → None", bres is None)

# ── C unsigned ────────────────────────────────────────────────────────────────
A.fork_labels_of = lambda fk, srcs: {}
out, pay = A.resolve_fork_outcome(
    cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
cres = A.fork_outcome_c("сколько?", pay, cls2, rows2, {}, picked_src="a")
t("C unsigned: kind=figures", cres.get("kind") == "figures")
t("C unsigned: число + фраза",
  "100" in (cres.get("text") or "")
  and A.FORK_OTHER_READING in (cres.get("text") or ""))
t("C unsigned: без имён веток",
  "Отгрузки" not in (cres.get("text") or "")
  and "Оплаты" not in (cres.get("text") or ""))
t("C unsigned: options пуст", not cres.get("options"))

cres2 = A.fork_outcome_c("сколько?", pay, cls2, rows2, {}, picked_src="z")
t("C unsigned: нет leader → unavailable", cres2.get("kind") == "unavailable")

# ── A3 авто снесён ────────────────────────────────────────────────────────────
cls_a = A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)},
                       "сумма", want="sum",
                       rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
rows_a = {"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)}
out, pay = A.resolve_fork_outcome(
    cls_a, rows_a, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
ares = A.fork_outcome_a("сколько?", pay["class"], {})
t("В4: fork_outcome_a → None", ares is None)
t("resolve → A при одном классе multi-src", out == "A")

# В2: sales_canon_force_pool снесён
t("0 sales_canon_force_pool", not hasattr(A, "sales_canon_force_pool"))

# mute авто снесён
t("В4: prefer_mute → None",
  A.prefer_mute_computed_over_clarify(
      {"x": {"atom": {"proof_status": A.PROOF_COMPUTED, "exact_value": 1},
             "figures": {"count": 1}}},
      "x", [{"count": 0}]) is None)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
