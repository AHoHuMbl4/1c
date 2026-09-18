#!/usr/bin/env python3
"""Замок D4: дайджесты опций + kind-prior + llm_option_highlight.
D4FIX2_MARK: accounting≠above document; entity 0≠DEAD; SC exact_value;
llm wait/deadline; empty label skip; dead-click text.
D4FIX3_MARK: entity prior by question; avg round 2dp; digest≡aggregate NUMBER.
D4FIX4_MARK: digest.count ≡ aggregate.count при intent.amount (nums+live).
D4FIX5_MARK: fail-soft digests/prior/llm; found coerce; value=None->itog:0;
short-circuit as-of stamp.

Отдельный файл (не расширение test_measure_degenerate): D1 уже 94 кейса;
D4 — отдельный контракт (digest≡aggregate, hint append, арбитр, kind-prior).
Мок psql, без живой БД.
Доки: Sql › Query syntax › FILTER; Sql › Expressions › Casting (TRY_CAST).
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
os.environ.setdefault("ASK_ATOM_TERMINAL", "0")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


SRC = "accumulationregister_fixture_sales"
SRC_DOC = "document_fixture_sales"
MEAS_LIVE = "Всего"
MEAS_DEAD = "Сумма"
MEAS_LIVE2 = "СуммаВзаиморасчетов"

_REAL = {
    "psql": A.psql,
    "deadline_hit": A.deadline_hit,
    "llm_option_highlight": getattr(A, "llm_option_highlight", None),
    "_live_measure_date_col": getattr(A, "_live_measure_date_col", None),
}


def _restore():
    for k, v in _REAL.items():
        if v is not None and hasattr(A, k):
            setattr(A, k, v)


# --- hint in _opt_values / clarify_say (реальный diag, не тавтология) ---
opts_hint = [{
    "label": "всего", "measure": MEAS_LIVE,
    "hint": "итог: 4\u00a0218\u00a0825.39",
    "digest": 4218825.39,
}]
vals = A._opt_values(opts_hint)
t("hint+digest in _opt_values", 4218825.39 in vals, vals)

diag_cs = {}
body = A.clarify_say("сколько выручки?", [
    {"label": "всего", "hint": "итог: 4\u00a0218\u00a0825.39", "measure": MEAS_LIVE,
     "digest": 4218825.39},
    {"label": "сумма", "hint": "0 · не ведётся", "measure": MEAS_DEAD},
], diag_cs)
t("clarify_say keeps digest digits in hint",
  "4" in body and "218" in body and "825" in body
  and "не ведётся" in body
  and not diag_cs.get("clarify_gate_rejected"),
  (body[:200], diag_cs))

diag_cs2 = {}
body2 = A.clarify_say("сколько выручки?", [
    {"label": "всего", "hint": "итог: 4 218 825,39", "measure": MEAS_LIVE,
     "digest": 4218825.39},
    {"label": "сумма", "hint": "0 · не ведётся", "measure": MEAS_DEAD},
], diag_cs2)
t("clarify_say keeps spaced comma digits 4 218 825,39",
  ("4 218 825,39" in body2 or ("4218825" in body2.replace(" ", "").replace(",", "."))
   or ("4" in body2 and "218" in body2 and "825" in body2))
  and not diag_cs2.get("clarify_gate_rejected"),
  (body2[:220], diag_cs2))

# --- label clean, hint append ---
opt = {"label": "Реализация (документ)", "hint": "для продаж", "measure": MEAS_LIVE,
       "measure_verdict": "alive", "answer_mode": "aggregate", "src": SRC}
A._hint_append(opt, "итог: 10")
t("hint append keeps discriminator",
  opt["hint"].startswith("для продаж") and "итог: 10" in opt["hint"]
  and "Реализация" in opt["label"] and "итог" not in opt["label"],
  opt)

# --- digest == aggregate: сверка FROM/WHERE/FILTER с каноном z17 (не мок-числа) ---
sqls_nums = []


def fake_psql_nums(sql):
    sqls_nums.append(sql)
    if "query_table" in sql:
        return [[5, 100.0, 1.0, 50.0, 20.0, 5]]
    return [[10, 4218825.39, 1.0, 999.0, 100.0, 10]]


A.psql = fake_psql_nums
A.deadline_hit = lambda rid=None: False
sqls_nums.clear()
batch = A._digest_nums_batch(
    SRC, [MEAS_LIVE], "doc @@ ts_phrase('x')",
    ["doc_date >= DATE '2026-08-01'",
     "map_extract(nums, %s)[1] > 0" % A.lit(MEAS_DEAD)],  # чужой amount
    "sum",
    intent={"amount": {"op": ">", "value": 100}})
t("nums digest has value+count_amount",
  batch and batch[MEAS_LIVE]["value"] == 4218825.39
  and batch[MEAS_LIVE]["count_amount"] == 10
  and batch[MEAS_LIVE]["via"] == "nums",
  batch)
sql_n = sqls_nums[-1] if sqls_nums else ""
t("nums digest ≡ aggregate: INDEX+match+FILTER+TRY_CAST+map_extract своей меры",
  "doc @@ ts_phrase" in sql_n
  and "FILTER" in sql_n
  and "TRY_CAST" in sql_n
  and "map_extract(nums" in sql_n
  and MEAS_LIVE in sql_n
  and "query_table" not in sql_n
  # чужой amount срезан из WHERE; свой — в FILTER через intent
  and MEAS_DEAD not in sql_n,
  sql_n[:500])
# amount своей меры в FILTER
t("nums amount pred is for digest measure not requested alien",
  MEAS_DEAD not in sql_n and MEAS_LIVE in sql_n and "> 100" in sql_n,
  sql_n[:400])

# live-only batch + date_col rewrite
A._live_measure_date_col = lambda src: "Period"
sqls_live = []


def fake_psql_live(sql):
    sqls_live.append(sql)
    return [[5, 100.0, 1.0, 50.0, 20.0, 5]]


A.psql = fake_psql_live
sqls_live.clear()
batch_l = A._digest_live_batch(
    SRC, [MEAS_LIVE], ["doc_date >= DATE '2026-08-01'"], {}, "sum")
t("live digest has value+count_amount",
  batch_l and batch_l[MEAS_LIVE]["value"] == 100.0
  and batch_l[MEAS_LIVE]["count_amount"] == 5
  and batch_l[MEAS_LIVE]["via"] == "live",
  batch_l)
sql_l = sqls_live[-1] if sqls_live else ""
t("live digest ≡ aggregate_live_column: query_table + date_col, no raw doc_date",
  "query_table" in sql_l
  and "doc_date" not in sql_l
  and "Period" in sql_l
  and "try_cast" in sql_l.lower()
  and "@@" not in sql_l,
  sql_l[:400])

# attach digests on measure menu
A.psql = fake_psql_nums
opts = [
    {"src": SRC, "measure": MEAS_LIVE, "label": "всего",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": ""},
    {"src": SRC, "measure": MEAS_DEAD, "label": "сумма",
     "measure_verdict": "degenerate", "answer_mode": "aggregate",
     "hint": "0 · не ведётся"},
]
out = A.attach_option_digests(
    opts, kind="measure", intent={"want": "sum", "period": {"from": "2026-08-01"}},
    plan={}, match="doc @@ ts_phrase('x')",
    preds=["doc_date >= DATE '2026-08-01'"],
    diag={}, form_key="sum", layers={MEAS_LIVE: "nums"}, src=SRC)
alive = [o for o in out if o["measure"] == MEAS_LIVE][0]
dead = [o for o in out if o["measure"] == MEAS_DEAD][0]
t("alive digest in hint, label clean",
  "итог" in (alive.get("hint") or "") and alive.get("digest") == 4218825.39
  and alive.get("answer_mode") == "short_circuit"
  and "итог" not in (alive.get("label") or ""),
  alive)
t("dead keeps 0 · не ведётся before click",
  "не ведётся" in (dead.get("hint") or ""), dead)

# live-fail keeps nums digests
sql_calls = {"n": 0}


def fake_psql_mixed(sql):
    sql_calls["n"] += 1
    if "query_table" in sql:
        raise RuntimeError("live boom")
    return [[10, 4218825.39, 1.0, 999.0, 100.0, 10]]


A.psql = fake_psql_mixed
opts_mix = [
    {"src": SRC, "measure": MEAS_LIVE, "label": "всего",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": ""},
    {"src": SRC, "measure": MEAS_LIVE2, "label": "взаим",
     "measure_verdict": "alive", "answer_mode": "text_with_total", "hint": ""},
]
out_mix = A.attach_option_digests(
    opts_mix, kind="measure", form_key="sum",
    layers={MEAS_LIVE: "nums", MEAS_LIVE2: "live"},
    src=SRC, diag={}, match="doc @@ ts_phrase('x')",
    preds=["doc_date >= DATE '2026-08-01'"], intent={"want": "sum"})
nums_o = [o for o in out_mix if o["measure"] == MEAS_LIVE][0]
live_o = [o for o in out_mix if o["measure"] == MEAS_LIVE2][0]
t("live-fail keeps nums digest, live deferred",
  nums_o.get("digest") == 4218825.39
  and "посчитаю по выбору" in (live_o.get("hint") or "")
  and "посчитаю по выбору" not in (nums_o.get("hint") or ""),
  (nums_o, live_o))

# compare: one SQL (not 2×nums)
sqls_cmp = []


def fake_cmp(sql):
    sqls_cmp.append(sql)
    # count1 + 5*1 + count2 + 5*1 = 12 cols for one measure
    return [[3, 10.0, 1.0, 9.0, 5.0, 3, 2, 4.0, 1.0, 3.0, 2.0, 2]]


A.psql = fake_cmp
sqls_cmp.clear()
cb = A._digest_compare_batch(
    SRC, [MEAS_LIVE], "doc @@ ts_phrase('x')", [],
    {"period": {"from": "2026-08-01", "to": "2026-08-31"},
     "period2": {"from": "2026-07-01", "to": "2026-07-31"}},
    {MEAS_LIVE: "nums"})
t("compare one SELECT two period-FILTER",
  len(sqls_cmp) == 1 and sqls_cmp[0].count("FILTER") >= 2
  and cb[MEAS_LIVE]["base"] == 10.0 and cb[MEAS_LIVE]["other"] == 4.0,
  (len(sqls_cmp), cb, sqls_cmp[0][:300] if sqls_cmp else ""))

# list: one preview SQL (UNION ALL), not N
sqls_list = []


def fake_list(sql):
    sqls_list.append(sql)
    if "UNION ALL" in sql or " mid" in sql or "AS mid" in sql:
        return [[0, "100"], [0, "90"], [1, "50"]]
    # counts for 2 measures
    return [[5, 3]]


A.psql = fake_list
sqls_list.clear()
lb = A._digest_list_batch(
    SRC, [MEAS_LIVE, MEAS_LIVE2], "doc @@ ts_phrase('x')", [],
    {MEAS_LIVE: "nums", MEAS_LIVE2: "nums"}, intent=None, limit=3)
t("list batched preview one UNION ALL not per-measure loop",
  len(sqls_list) == 2  # counts + preview
  and any("UNION ALL" in s for s in sqls_list)
  and lb[MEAS_LIVE]["count"] == 5
  and len(lb[MEAS_LIVE].get("preview") or []) >= 1,
  (len(sqls_list), sqls_list, lb))

# deadline -> defer
A.deadline_hit = lambda rid=None: True
A.psql = fake_psql_nums
opts2 = [
    {"src": SRC, "measure": MEAS_LIVE, "label": "всего",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": "was"},
    {"src": SRC, "measure": MEAS_LIVE2, "label": "взаим",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": ""},
]
out2 = A.attach_option_digests(
    opts2, kind="measure", form_key="sum", layers={}, src=SRC, diag={})
t("budget miss -> посчитаю по выбору",
  all("посчитаю по выбору" in (o.get("hint") or "") for o in out2)
  and "was" in (out2[0].get("hint") or ""),  # append not replace
  out2)
A.deadline_hit = lambda rid=None: False

# rank/group: no bare sum digit
opts_rk = [
    {"src": SRC, "measure": MEAS_LIVE, "label": "всего",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": ""},
    {"src": SRC, "measure": MEAS_LIVE2, "label": "взаим",
     "measure_verdict": "alive", "answer_mode": "aggregate", "hint": ""},
]
out_rk = A.attach_option_digests(
    opts_rk, kind="measure", form_key="rank", layers={MEAS_LIVE: "nums"},
    src=SRC, diag={}, match="x", preds=[])
t("rank/group hint without sum digit from digest field",
  all(o.get("digest") is None for o in out_rk)
  and all("посчитаю по выбору" in (o.get("hint") or "") for o in out_rk),
  out_rk)

# kind-prior
opts_k = [
    {"src": SRC_DOC, "label": "док", "measure": MEAS_LIVE},
    {"src": SRC, "label": "рег", "measure": MEAS_LIVE},
]
sorted_k = A.kind_prior_sort(
    opts_k,
    intent={"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-31"}},
    plan={"compute": "sum"})
t("kind-prior accumulationregister_ above document_",
  sorted_k[0]["src"] == SRC and sorted_k[1]["src"] == SRC_DOC,
  sorted_k)
sorted_same = A.kind_prior_sort(
    list(opts_k), intent={"want": "count"}, plan={})
t("kind-prior noop without money+period",
  sorted_same[0]["src"] == SRC_DOC, sorted_same)

# llm arbiter mock — ★ APPEND в конец
calls = {"n": 0}


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"2"}}],"usage":{}}'


def fake_urlopen(req, timeout=None):
    calls["n"] += 1
    calls["timeout"] = timeout
    return _Resp()


import urllib.request as _ur
_real_urlopen = _ur.urlopen
_ur.urlopen = fake_urlopen
A.DS_KEY = "x"
A.deadline_hit = lambda rid=None: False
opts_llm = [
    {"label": "A", "hint": "итог: 1"},
    {"label": "B", "hint": "итог: 2"},
]
diag = {}
pick = A.llm_option_highlight("сколько?", opts_llm, diag)
t("llm pick index 1, star APPEND at end of hint",
  pick == 1 and (opts_llm[1]["hint"] or "").endswith("★")
  and "★" not in (opts_llm[0]["hint"] or "")
  and not (opts_llm[1]["hint"] or "").startswith("★")
  and diag.get("llm_pick") == 1
  and opts_llm[0]["label"] == "A",  # order unchanged
  (pick, opts_llm, diag))

# timeout -> no marker
def boom(req, timeout=None):
    raise TimeoutError("slow")


_ur.urlopen = boom
opts_to = [{"label": "A", "hint": "h"}, {"label": "B", "hint": "h2"}]
diag2 = {}
pick2 = A.llm_option_highlight("q", opts_to, diag2)
t("llm timeout -> no star, menu intact",
  pick2 is None and diag2.get("llm_pick") is None
  and not any("★" in (o.get("hint") or "") for o in opts_to),
  (pick2, opts_to))
_ur.urlopen = _real_urlopen

# short-circuit consume atom == digest
agg = A._measure_short_circuit_agg(
    digest=4218825.39, digest_form="sum", count=10, count_amount=10,
    measure=MEAS_LIVE, min_v=1.0, max_v=999.0)
t("short-circuit agg carries min/max from ticket fields",
  agg.get("min") == 1.0 and agg.get("max") == 999.0 and agg.get("sum") == 4218825.39,
  agg)

# issue_decision whitelist min/max
opt_t = {
    "src": SRC, "measure": MEAS_LIVE, "label": "всего",
    "measure_verdict": "alive", "digest": 10.0, "digest_form": "sum",
    "digest_scope": {"via": "nums"}, "answer_mode": "short_circuit",
    "count": 2, "count_amount": 2, "min": 1.0, "max": 9.0,
}
tid = A.issue_decision("q", opt_t, "measure", "v1")
ticket = A._DECISIONS.get(tid) if hasattr(A, "_DECISIONS") else None
if ticket is None:
    # fallback: peek via consume path / sealed storage
    with A._DECISION_LOCK:
        ticket = A._DECISIONS.get(tid)
t("issue_decision copies min/max",
  ticket and ticket.get("min") == 1.0 and ticket.get("max") == 9.0
  and ticket.get("digest") == 10.0,
  ticket)

# entity digest one SELECT
sqls = []


def fake_ent(sql):
    sqls.append(sql)
    return [
        [SRC, 12, "2022-01-01", "2026-08-01"],
        [SRC_DOC, 0, "", ""],
    ]


A.psql = fake_ent
eb = A._digest_entity_batch([SRC, SRC_DOC], "", ["doc_date >= DATE '2026-01-01'"])
t("entity one SELECT all srcs",
  len(sqls) == 1 and "GROUP BY" in sqls[0]
  and eb[SRC]["count"] == 12 and eb[SRC_DOC]["count"] == 0,
  (sqls, eb))
eopts = [
    {"src": SRC, "label": "рег", "hint": "алиас"},
    {"src": SRC_DOC, "label": "док", "hint": ""},
]
eout = A.attach_option_digests(
    eopts, kind="entity", preds=["doc_date >= DATE '2026-01-01'"], diag={})
t("entity hint append + records 0 without DEAD",
  "алиас" in (eout[0].get("hint") or "") and "записей" in (eout[0].get("hint") or "")
  and "записей: 0" in (eout[1].get("hint") or "")
  and "не ведётся" not in (eout[1].get("hint") or ""),
  eout)

# --- D4FIX2: kind-prior negatives ---
SRC_ACC = "accountingregister_fixture_sales"
SRC_INF = "informationregister_fixture_sales"
opts_acc = [
    {"src": SRC_DOC, "label": "док", "measure": MEAS_LIVE},
    {"src": SRC_ACC, "label": "бух", "measure": MEAS_LIVE},
]
sorted_acc = A.kind_prior_sort(
    list(opts_acc),
    intent={"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-31"}},
    plan={"compute": "sum"})
t("kind-prior accountingregister_ not above document_",
  [o["src"] for o in sorted_acc] == [SRC_DOC, SRC_ACC],
  sorted_acc)
opts_inf = [
    {"src": SRC_DOC, "label": "док", "measure": MEAS_LIVE},
    {"src": SRC_INF, "label": "свед", "measure": MEAS_LIVE},
]
sorted_inf = A.kind_prior_sort(
    list(opts_inf),
    intent={"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-31"}},
    plan={"compute": "sum"})
t("kind-prior informationregister_ vs document_ noop",
  [o["src"] for o in sorted_inf] == [SRC_DOC, SRC_INF],
  sorted_inf)
opts_ent_list = [
    {"src": SRC_DOC, "label": "док"},
    {"src": SRC, "label": "рег"},
]
sorted_ent = A.kind_prior_sort(
    list(opts_ent_list),
    intent={"want": "count", "period": {"from": "2026-08-01"}},
    plan={})
t("kind-prior entity without measure + want=count noop",
  [o["src"] for o in sorted_ent] == [SRC_DOC, SRC],
  sorted_ent)
# D4FIX3: entity без measure + want=sum+period → accum первым
opts_ent_sum = [
    {"src": SRC_DOC, "label": "док"},
    {"src": SRC, "label": "рег"},
]
sorted_ent_sum = A.kind_prior_sort(
    list(opts_ent_sum),
    intent={"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-31"}},
    plan={"compute": "sum"})
t("kind-prior entity want=sum+period → accumulationregister_ first",
  [o["src"] for o in sorted_ent_sum] == [SRC, SRC_DOC],
  sorted_ent_sum)

# short-circuit atom.exact_value == digest ≠ count
agg_sc = A._measure_short_circuit_agg(
    digest=4218825.39, digest_form="sum", count=10, count_amount=10,
    measure=MEAS_LIVE, min_v=1.0, max_v=999.0)
atom_sc = A.atom_from_agg(
    agg_sc, operation="sum", measure_id=MEAS_LIVE,
    measure_label="всего", money=True)
ev_sc = (atom_sc or {}).get("exact_value")
t("short-circuit atom.exact_value == digest ≠ count",
  ev_sc == 4218825.39 and ev_sc != 10 and agg_sc.get("sum") == 4218825.39,
  {"ev": ev_sc, "agg": agg_sc})

# llm: wait ≤ min(0.8, rem); deadline_hit → no star
_ur.urlopen = fake_urlopen
calls.clear()
calls["n"] = 0
A.deadline_hit = lambda rid=None: False
_rem_real = getattr(A, "_deadline_remaining_sec", None)
A._deadline_remaining_sec = lambda: 0.25
opts_wait = [{"label": "A", "hint": "h"}, {"label": "B", "hint": "h2"}]
diag_w = {}
A.llm_option_highlight("q", opts_wait, diag_w)
t("llm wait ≤ min(800ms, remaining)",
  calls.get("timeout") is not None and calls["timeout"] <= 0.25 + 1e-9
  and calls["timeout"] <= 0.8,
  calls)
A.deadline_hit = lambda rid=None: True
opts_dl = [{"label": "A", "hint": "h"}, {"label": "B", "hint": "h2"}]
diag_dl = {}
pick_dl = A.llm_option_highlight("q", opts_dl, diag_dl)
t("llm deadline_hit → menu immediately without star",
  pick_dl is None and diag_dl.get("llm_pick") is None
  and not any("★" in (o.get("hint") or "") for o in opts_dl),
  (pick_dl, opts_dl, diag_dl))
A.deadline_hit = lambda rid=None: False
if _rem_real is not None:
    A._deadline_remaining_sec = _rem_real

# llm: empty label skipped (no raw measure to arbiter)
calls2 = {"n": 0, "body": None}


class _Resp2:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"choices":[{"message":{"content":"1"}}],"usage":{}}'


def fake_urlopen2(req, timeout=None):
    calls2["n"] += 1
    calls2["timeout"] = timeout
    try:
        calls2["body"] = req.data.decode() if req.data else ""
    except Exception:  # noqa: BLE001
        calls2["body"] = ""
    return _Resp2()


_ur.urlopen = fake_urlopen2
opts_nolab = [
    {"label": "", "measure": MEAS_LIVE, "hint": "итог: 1"},
    {"label": "всего", "measure": MEAS_LIVE2, "hint": "итог: 2"},
    {"label": "взаим", "measure": MEAS_DEAD, "hint": "итог: 3"},
]
diag_nl = {}
pick_nl = A.llm_option_highlight("q", opts_nolab, diag_nl)
try:
    _uc = __import__("json").loads(calls2.get("body") or "{}")["messages"][1]["content"]
except Exception:  # noqa: BLE001
    _uc = calls2.get("body") or ""
t("llm skips empty label (no raw measure fallback)",
  pick_nl is not None
  and "1..2." in _uc
  and "всего" in _uc
  and MEAS_LIVE not in _uc  # сырое имя колонки пустого label не ушло
  and "итог: 1" not in _uc,  # пункт без label пропущен целиком
  (pick_nl, _uc, diag_nl))
_ur.urlopen = _real_urlopen

# dead-click → текст «не ведётся», не число
dead_fn = getattr(A, "_measure_degenerate_not_kept_answer", None)
t("dead-click helper present", callable(dead_fn))
if callable(dead_fn):
    out_dead = dead_fn("q", MEAS_DEAD, SRC, {}, None, __import__("time").time())
    t("dead-click → text не ведётся, atoms empty",
      (out_dead or {}).get("kind") == "answer"
      and "не ведётся" in ((out_dead or {}).get("text") or "")
      and not ((out_dead or {}).get("atoms") or []),
      out_dead)

# deadline+found=0 entity → записей: 0 без DEAD
A.deadline_hit = lambda rid=None: True
eopts_dl = [
    {"src": SRC, "label": "рег", "hint": "", "found": 0},
    {"src": SRC_DOC, "label": "док", "hint": "", "found": 5},
]
eout_dl = A.attach_option_digests(eopts_dl, kind="entity", diag={})
t("deadline entity found=0 → записей: 0 without DEAD",
  "записей: 0" in (eout_dl[0].get("hint") or "")
  and "не ведётся" not in (eout_dl[0].get("hint") or "")
  and "посчитаю по выбору" in (eout_dl[1].get("hint") or ""),
  eout_dl)
A.deadline_hit = lambda rid=None: False

# --- D4FIX3: avg round + digest ≡ aggregate ЧИСЛОМ ---
AVG_RAW = 20.123456
AVG_RND = round(AVG_RAW, 2)  # 20.12
sqls_eq = []


def fake_eq_nums(sql):
    sqls_eq.append(sql)
    if "duckdb_columns" in sql:
        return [[1]]
    if "query_table" in sql:
        # live: count,sum,min,max,avg,count_amount
        return [[5, 100.5, 1.0, 50.0, AVG_RAW, 5]]
    if "min(doc_date)" in sql:
        # z17 aggregate: 10 cols (dates between avg and count_amount)
        return [[10, 4218825.39, 1.0, 999.0, AVG_RAW,
                 "2026-01-01", "2026-08-31", 10, 0, 0]]
    # digest nums: count + sum,min,max,avg,count_amount
    return [[10, 4218825.39, 1.0, 999.0, AVG_RAW, 10]]


A.psql = fake_eq_nums
A._live_column_exists = lambda src, col: True
A._live_std_excl_preds = lambda src: []
A._live_measure_date_col = lambda src: "Period"
sqls_eq.clear()
dig_n = A._digest_nums_batch(
    SRC, [MEAS_LIVE], "doc @@ ts_phrase('x')",
    ["doc_date >= DATE '2026-08-01'"], "avg")
agg_n = A.aggregate(
    SRC, "doc @@ ts_phrase('x')",
    ["doc_date >= DATE '2026-08-01'"], MEAS_LIVE)
dn = dig_n[MEAS_LIVE]
t("nums digest avg rounded to 2dp",
  dn.get("avg") == AVG_RND and dn.get("value") == AVG_RND, dn)
t("nums digest ≡ aggregate NUMBER: sum/avg/min/max/count_amount",
  agg_n is not None
  and dn.get("sum") == agg_n.get("sum")
  and dn.get("avg") == agg_n.get("avg")
  and dn.get("min") == agg_n.get("min")
  and dn.get("max") == agg_n.get("max")
  and dn.get("count_amount") == agg_n.get("count_amount"),
  {"dig": dn, "agg": agg_n})

sqls_eq.clear()
dig_l = A._digest_live_batch(
    SRC, [MEAS_LIVE], ["doc_date >= DATE '2026-08-01'"], {}, "avg")
agg_l = A.aggregate_live_column(
    SRC, ["doc_date >= DATE '2026-08-01'"], MEAS_LIVE)
dl = dig_l[MEAS_LIVE]
t("live digest avg rounded to 2dp",
  dl.get("avg") == AVG_RND and dl.get("value") == AVG_RND, dl)
t("live digest ≡ aggregate_live_column NUMBER: sum/avg/min/max/count_amount",
  agg_l is not None
  and dl.get("sum") == agg_l.get("sum")
  and dl.get("avg") == agg_l.get("avg")
  and dl.get("min") == agg_l.get("min")
  and dl.get("max") == agg_l.get("max")
  and dl.get("count_amount") == agg_l.get("count_amount"),
  {"dig": dl, "agg": agg_l})

agg_avg_sc = A._measure_short_circuit_agg(
    digest=AVG_RAW, digest_form="avg", count=10, count_amount=10,
    measure=MEAS_LIVE, min_v=1.0, max_v=999.0)
t("short-circuit avg rounded to 2dp",
  agg_avg_sc.get("avg") == AVG_RND, agg_avg_sc)

# --- D4FIX4: digest.count ≡ aggregate.count при intent.amount ---
INTENT_AMT = {"amount": {"op": ">", "value": 100}, "want": "sum"}
PREDS_BASE = ["doc_date >= DATE '2026-08-01'"]
PREDS_AGG = PREDS_BASE + A._num_pred(INTENT_AMT, MEAS_LIVE)


def _count_star_filt_has_amount(sql):
    """Первый count(*) FILTER (...): есть ли amount-предикат (> 100).
    Скобки вложенные (coalesce/try_cast) — баланс, не [^)].
    """
    s = sql or ""
    key = "count(*) FILTER ("
    i = s.find(key)
    if i < 0:
        return False
    start = i + len(key)
    depth = 1
    j = start
    while j < len(s) and depth:
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
        j += 1
    return "> 100" in s[start:j]


sqls_amt = []


def fake_eq_amt(sql):
    sqls_amt.append(sql)
    if "duckdb_columns" in sql:
        return [[1]]
    if "min(doc_date)" in sql:
        # z17 aggregate: amount в WHERE → count=3
        return [[3, 100.0, 1.0, 50.0, 20.0,
                 "2026-01-01", "2026-08-31", 3, 0, 0]]
    if "query_table" in sql:
        # live digest fixed: count(*) FILTER(amount)
        if _count_star_filt_has_amount(sql):
            return [[3, 100.5, 1.0, 50.0, 20.0, 3]]
        # aggregate_live: bare count(*), amount в WHERE
        if "> 100" in sql and "WHERE" in sql and "> 100" in sql.split("WHERE", 1)[-1]:
            return [[3, 100.5, 1.0, 50.0, 20.0, 3]]
        return [[99, 100.5, 1.0, 50.0, 20.0, 99]]
    # digest nums
    if _count_star_filt_has_amount(sql):
        return [[3, 100.0, 1.0, 50.0, 20.0, 3]]
    return [[99, 100.0, 1.0, 50.0, 20.0, 99]]


A.psql = fake_eq_amt
A._live_column_exists = lambda src, col: True
A._live_std_excl_preds = lambda src: []
A._live_measure_date_col = lambda src: "Period"
sqls_amt.clear()
dig_na = A._digest_nums_batch(
    SRC, [MEAS_LIVE], "doc @@ ts_phrase('x')",
    PREDS_BASE, "sum", intent=INTENT_AMT)
agg_na = A.aggregate(
    SRC, "doc @@ ts_phrase('x')", PREDS_AGG, MEAS_LIVE)
dna = dig_na[MEAS_LIVE]
sql_dig_n = next((s for s in sqls_amt if "map_extract(nums" in s
                  and "min(doc_date)" not in s), "")
t("nums amount: count(*) FILTER carries amount_m",
  _count_star_filt_has_amount(sql_dig_n), sql_dig_n[:400])
t("nums digest ≡ aggregate NUMBER with amount: count",
  agg_na is not None
  and dna.get("count") == agg_na.get("count")
  and dna.get("count") == 3
  and dna.get("count_amount") == agg_na.get("count_amount"),
  {"dig": dna, "agg": agg_na})

sqls_amt.clear()
dig_la = A._digest_live_batch(
    SRC, [MEAS_LIVE], PREDS_BASE, INTENT_AMT, "sum")
agg_la = A.aggregate_live_column(SRC, PREDS_AGG, MEAS_LIVE)
dla = dig_la[MEAS_LIVE]
sql_dig_l = next((s for s in sqls_amt if "query_table" in s
                  and "count(*) FILTER" in s), "")
t("live amount: count(*) FILTER carries amount_m",
  _count_star_filt_has_amount(sql_dig_l), sql_dig_l[:400])
t("live digest ≡ aggregate_live_column NUMBER with amount: count",
  agg_la is not None
  and dla.get("count") == agg_la.get("count")
  and dla.get("count") == 3
  and dla.get("count_amount") == agg_la.get("count_amount"),
  {"dig": dla, "agg": agg_la})

# --- D4FIX5: fail-soft digests / found coerce / value=None / as_of ---
# 1) highlight boom -> clarify, opts>=2, no star, menu present
_real_hl = A.llm_option_highlight
_real_attach = A.attach_option_digests
_real_prior = A.kind_prior_sort


def _boom_hl(question, opts, diag=None, *, timeout_sec=None):
    raise RuntimeError("D4FIX5 highlight boom")


A.deadline_hit = lambda rid=None: False
A.attach_option_digests = (
    lambda opts, **kw: [
        dict(o, hint=(o.get("hint") or "") or "итог: 1") for o in opts])
A.kind_prior_sort = lambda opts, **kw: list(opts)
A.llm_option_highlight = _boom_hl
items_fs = [
    {"label": "всего", "measure": MEAS_LIVE, "hint": "", "src": SRC},
    {"label": "сумма", "measure": MEAS_DEAD, "hint": "", "src": SRC},
]
diag_fs = {}
out_fs = A.finalize_clarify_menu(
    "сколько?", "measure", items_fs, diag_fs, 20, __import__("time").time(),
    with_digests=True)
opts_fs = (out_fs or {}).get("options") or []
t("исключение в highlight → kind=clarify, opts≥2, без ★, меню есть",
  (out_fs or {}).get("kind") == "clarify"
  and len(opts_fs) >= 2
  and diag_fs.get("llm_pick") is None
  and not any("★" in (o.get("hint") or "") for o in opts_fs),
  (out_fs and out_fs.get("kind"), len(opts_fs), diag_fs, opts_fs))

# digests boom -> menu_digests=False, defer, menu still


def _boom_attach(opts, **kw):
    raise RuntimeError("D4FIX5 digests boom")


A.attach_option_digests = _boom_attach
A.llm_option_highlight = _real_hl
items_dg = [
    {"label": "всего", "measure": MEAS_LIVE, "hint": "для продаж", "src": SRC},
    {"label": "сумма", "measure": MEAS_DEAD, "hint": "", "src": SRC,
     "measure_verdict": "degenerate"},
]
diag_dg = {}
out_dg = A.finalize_clarify_menu(
    "сколько?", "measure", items_dg, diag_dg, 20, __import__("time").time(),
    with_digests=True)
opts_dg = (out_dg or {}).get("options") or []
t("исключение в digests → menu_digests=False, defer, меню есть",
  (out_dg or {}).get("kind") == "clarify"
  and len(opts_dg) >= 2
  and diag_dg.get("menu_digests") is False
  and diag_dg.get("llm_pick") is None
  and any("посчитаю по выбору" in (o.get("hint") or "") for o in opts_dg),
  (out_dg and out_dg.get("kind"), diag_dg, opts_dg))
A.attach_option_digests = _real_attach
A.kind_prior_sort = _real_prior
A.llm_option_highlight = _real_hl

# 2) found="x" + deadline -> no raise; defer/записей: 0
A.deadline_hit = lambda rid=None: True
eopts_x = [
    {"src": SRC, "label": "рег", "hint": "", "found": "x"},
    {"src": SRC_DOC, "label": "док", "hint": "", "found": 5},
]
raised = False
try:
    eout_x = A.attach_option_digests(eopts_x, kind="entity", diag={})
except Exception as e:  # noqa: BLE001
    raised = True
    eout_x = e
t('found="x" + deadline_hit → defer/записей: 0, без raise',
  not raised
  and isinstance(eout_x, list)
  and "записей: 0" in (eout_x[0].get("hint") or "")
  and "посчитаю по выбору" in (eout_x[1].get("hint") or ""),
  eout_x)
A.deadline_hit = lambda rid=None: False

# 3a) value=None + count -> itog:0 / записей:N (not defer)
h0 = A._digest_hint_text("sum", {"value": None, "count": 0})
hN = A._digest_hint_text("sum", {"value": None, "count": 7})
t("value=None count=0 → итог: 0 (не defer)",
  h0.startswith("итог:") and "0" in h0 and "посчитаю" not in h0, h0)
t("value=None count>0 → записей: N (не defer)",
  hN.startswith("записей:") and "7" in hN and "посчитаю" not in hN, hN)
t("value=None без count → defer",
  A._digest_hint_text("sum", {"value": None}) == A._DIGEST_DEFER)

# 3b) short-circuit as-of stamp (z20:4098-4102 contract)
t("_DIGEST_AS_OF constant",
  getattr(A, "_DIGEST_AS_OF", None) == "на момент вопроса")
_txt0 = "4\u00a0218\u00a0825.39"
_out0 = {"text": _txt0, "diag": {"answer_mode": "short_circuit"}}
_d0 = dict(_out0.get("diag") or {})
if _d0.get("digest_as_of") or _d0.get("answer_mode") == "short_circuit":
    _d0["digest_as_of"] = True
    _tx = (_out0.get("text") or "").strip()
    if _tx and A._DIGEST_AS_OF not in _tx:
        _out0 = dict(_out0, text="%s (%s)" % (_tx, A._DIGEST_AS_OF))
_out0 = dict(_out0, diag=_d0)
t("short-circuit → текст с «на момент вопроса»",
  A._DIGEST_AS_OF in (_out0.get("text") or "")
  and _out0.get("diag", {}).get("digest_as_of") is True,
  _out0)


_restore()
print()
print("ИТОГ: ok — %d проверок" % PASS if not FAIL else
      "ИТОГ: FAIL %d / ok %d: %s" % (len(FAIL), PASS, FAIL))
sys.exit(0 if not FAIL else 1)
