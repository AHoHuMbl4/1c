#!/usr/bin/env python3
"""Лидер люка B/C — контракт 23.08 (оффлайн).

Замки:
  · B: text = одна пара лидера; options = N−1; leader = класс с picked[0];
  · C unsigned: число + FORK_OTHER_READING, без имён веток, options пуст;
  · A3: без options;
  · канон продаж с lock → fork не открывает люк (sales_canon_force_pool);
  · журнал B: atoms[0]=leader, clarify_options = hatch-only.

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


# ── B: leader + hatch ─────────────────────────────────────────────────────────
cls2 = A.fork_classes({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)},
                      "сумма", want="sum",
                      rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}


def _labs_ok(fk, srcs):
    return {"a": "Отгрузки", "b": "Оплаты"}


A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(
    cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
bres = A.fork_outcome_b("сколько?", pay, {}, picked_src="b")
t("B leader=b: text одна пара Оплаты",
  bres and "Оплаты" in bres["text"] and "200" in bres["text"]
  and "Отгрузки" not in bres["text"])
t("B leader=b: options только a", len(bres["options"]) == 1
  and bres["options"][0]["label"] == "Отгрузки")
t("B: atoms[0] лидер", bres["atoms"][0]["measure_label"] == "Оплаты")

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

# picked не в классе → unavailable
cres2 = A.fork_outcome_c("сколько?", pay, cls2, rows2, {}, picked_src="z")
t("C unsigned: нет leader → unavailable", cres2.get("kind") == "unavailable")

# ── A3 без options ────────────────────────────────────────────────────────────
cls_a = A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)},
                       "сумма", want="sum",
                       rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
rows_a = {"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)}
out, pay = A.resolve_fork_outcome(
    cls_a, rows_a, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
ares = A.fork_outcome_a("сколько?", pay["class"], {})
t("A3: без options", not ares.get("options"))
t("A3: kind=answer", ares.get("kind") == "answer")

# ── канон продаж: lock → один src, не люк ────────────────────────────────────
_p, _a, _d = A.sales_canon_force_pool(
    "accumulationregister_реализациятмц", ["accumulationregister_реализациятмц"],
    ["accumulationregister_реализациятмц", "document_реализациятмц"], True)
t("sales_canon lock: arb_pool один src", len(_a) == 1 and _d is False)

# ── журнал B hatch ───────────────────────────────────────────────────────────
A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(
    cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
bres = A.fork_outcome_b("сколько?", pay, {}, picked_src="a")
opts = A._journal_clarify_options(bres)
t("journal B: clarify_options hatch-only",
  isinstance(opts, list) and len(opts) == 1 and opts[0].get("label") == "Оплаты")
t("journal B: atoms[0]=leader",
  A._journal_atoms_slim(bres)[0].get("exact_value") == 100.0)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
