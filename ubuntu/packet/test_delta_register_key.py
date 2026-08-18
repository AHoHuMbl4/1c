#!/usr/bin/env python3
"""Оффлайн: дельта регистра без Ref_Key сливается по Recorder+LineNumber."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packet_apply as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


s = A._delta_delete_clause("document_x", ["Ref_Key", "DataVersion", "LineNumber"])
t("документ: DELETE по Ref_Key",
  'WHERE "Ref_Key" IN' in s and "Recorder" not in s, s)

s = A._delta_delete_clause(
    "accumulationregister_x",
    ["Recorder", "Recorder_Type", "Period", "LineNumber", "Всего"])
t("регистр: EXISTS по Recorder", "Recorder" in s and "EXISTS" in s, s)
t("регистр: LineNumber в предикате", "LineNumber" in s, s)
t("регистр: без Ref_Key", "Ref_Key" not in s, s)

try:
    A._delta_delete_clause("weird", ["Period", "Всего"])
    t("без ключа — карантин", False)
except A.Quarantine as q:
    t("без ключа — карантин", str(q) == "delta_without_key", q)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
