#!/usr/bin/env python3
"""Оффлайн: сквозной rid и формат TRACE (без сети и базы).

Замки:
  · rid из payload доезжает в журнал и stderr;
  · без rid сервис генерирует (12–16 alnum);
  · строка TRACE не несёт текст вопроса.

Запуск: python3 ubuntu/serenedb/test_trace_rid.py
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_JOURNAL", "1")

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


SECRET = "секретный-вопрос-rid-probe-XYZ"
RID_IN = "a1b2c3d4e5f67890"


# ── rid нормализация ─────────────────────────────────────────────────────────
r0 = A._rid_norm("")
t("без rid: генерируется", len(r0) >= 12 and r0.isalnum())
t("rid входной сохраняется", A._rid_norm(RID_IN) == RID_IN[:16])
t("rid: не-alnum отбрасываются", A._rid_norm("ab!@#cd") == "abcd")


# ── TRACE без текста вопроса ─────────────────────────────────────────────────
A._rid_enter(RID_IN)
buf = io.StringIO()
old_err = sys.stderr
sys.stderr = buf
try:
    A._trace_write("service", "probe", 42, "ok")
    A._token_acc_start()
    A._token_acc_record({"prompt_tokens": 3, "completion_tokens": 1})
finally:
    sys.stderr = old_err
log = buf.getvalue()
t("TRACE: rid в строке", ("TRACE %s service probe" % RID_IN) in log)
t("TRACE: без текста вопроса", SECRET not in log and "секрет" not in log.lower())
t("model TOKENS: формат TRACE", "TRACE %s model TOKENS" % RID_IN in log)


# ── journal INSERT с rid ─────────────────────────────────────────────────────
captured, nid_box = [], [0]


def fake_psql(sql):
    captured.append(sql)
    if "nextval" in sql:
        nid_box[0] += 1
        return [[str(nid_box[0])]]
    if "search_quality" in sql:
        return [["1710000000"]]
    if "concat_ws" in sql:
        return [["1|2|3"]]
    if "count(*)" in sql:
        return [["8"]]
    return []


old_psql = A.psql
A.psql = fake_psql
A.ASK_JOURNAL = True
try:
    A._rid_enter(RID_IN)
    A._ask_journal_write(SECRET, {"kind": "answer", "diag": {}},
                         A.time.monotonic(), rid=RID_IN)
    ins = [s for s in captured
           if s.strip().upper().startswith("INSERT INTO ASK_JOURNAL ")][-1]
    t("journal: rid в INSERT", ("'%s'" % RID_IN) in ins or ('"%s"' % RID_IN) in ins)
    t("journal: текст вопроса не в ask_journal", SECRET not in ins)
finally:
    A.psql = old_psql


# ── answer_checked без rid генерирует ────────────────────────────────────────
A.ENOUGH_ON = False
A.parse_intent = lambda q, today: {"kind": "x", "terms": [], "parse": {}}
A.answer = lambda *a, **k: {"kind": "no_data", "text": "", "diag": {"шаги": []}}
A.ASK_JOURNAL = False
A._rid_ctx.set("")
try:
    A.answer_checked("probe", rid=None)
finally:
    pass
gen = A._rid_get()
t("answer_checked: генерирует rid", len(gen) >= 12)
t("answer_checked: rid 12-16 alnum", gen.isalnum() and 12 <= len(gen) <= 16)


# ── I0-П2-фикс: формат TRACE «wiki verify» ───────────────────────────────────
fmt = getattr(A, "wiki_verify_trace_fields", None)
t("wiki_verify_trace_fields exported", callable(fmt))
if callable(fmt):
    sole = fmt({"wiki_verify": "catalog_goods", "wiki_verify_yes": 1,
                "wiki_verify_no": 0, "wiki_verify_unsure": 0})
    t("TRACE sole: leader=src not none",
      sole.get("leader") == "catalog_goods"
      and sole.get("verdicts") == "1yes/0no/0u",
      sole)
    bad = fmt({"wiki_verify": "bad_index", "wiki_verify_yes": 0,
               "wiki_verify_no": 0, "wiki_verify_unsure": 0})
    t("TRACE sentinel bad_index",
      bad.get("leader") == "- (bad_index)", bad)
    ax = fmt({"wiki_verify": "axis_reject"})
    t("TRACE sentinel axis_reject",
      ax.get("leader") == "- (axis_reject)", ax)
    deg = fmt({"wiki_verify_error": 1, "wiki_pick_hint": "catalog_a",
               "wiki_verdicts": []})
    t("TRACE degraded uses wiki_pick_hint",
      deg.get("verdicts") == "degraded" and deg.get("leader") == "catalog_a",
      deg)
    deg2 = fmt({"wiki_verify_error": 1, "wiki_verdicts": []})
    t("TRACE degraded without hint -> leader=-",
      deg2.get("verdicts") == "degraded" and deg2.get("leader") == "-",
      deg2)
    deg_wd = fmt({"wiki_degraded": 1, "wiki_pick_hint": "catalog_b"})
    t("TRACE wiki_degraded alone uses hint",
      deg_wd.get("verdicts") == "degraded" and deg_wd.get("leader") == "catalog_b",
      deg_wd)
    deg_ign = fmt({"wiki_verify_error": 1, "wiki_pick": "catalog_a"})
    t("TRACE degraded ignores wiki_pick for leader",
      deg_ign.get("leader") == "-", deg_ign)
    nl = fmt({"wiki_verify": "src" + chr(10) + "with  spaces", "wiki_verify_yes": 1})
    t("TRACE leader sanitized one line",
      chr(10) not in nl.get("leader", "") and "  " not in nl.get("leader", ""),
      nl)
    conf0 = fmt({"wiki_verify": "catalog_goods", "wiki_verify_yes": 1,
                 "wiki_verify_no": 0, "wiki_verify_unsure": 0})
    t("TRACE confirm absent -> -",
      conf0.get("confirm") == "-" and "2" not in conf0, conf0)
    conf1 = fmt({
        "wiki_verify": "catalog_goods", "wiki_verify_yes": 1,
        "wiki_verify_no": 1, "wiki_verify_unsure": 0,
        "wiki_verify_confirm": "agree",
        "wiki_verify2_yes": 1, "wiki_verify2_no": 1, "wiki_verify2_unsure": 0,
    })
    t("TRACE confirm+2 on second call",
      conf1.get("confirm") == "agree" and conf1.get("2") == "1/1/0",
      conf1)
    conf_nl = fmt({
        "wiki_verify": "catalog_a",
        "wiki_verify_confirm": "disagree" + chr(10) + "x",
        "wiki_verify2_yes": 0,
    })
    t("TRACE confirm sanitized",
      chr(10) not in conf_nl.get("confirm", ""), conf_nl)

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
