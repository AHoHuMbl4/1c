#!/usr/bin/env python3
"""Оффлайн: гейт вектор-бюджета + content_hash (стоп ДО записи в search_corpus).

Порог — ДОЛЯ от векторов базы (MERGE_VECTOR_LOSS_TOLERANCE, умолчание 0.5%).
Потеря = было − живут(тот же row_key + hash/common_eq) − карта xfer (rewrite_wave).

Запуск: python3 test_vector_budget_gate.py
"""
import hashlib
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(ROOT, "corpus_merge.sql")
BUILD = os.path.join(ROOT, "build.sh")
INIT = os.path.join(ROOT, "corpus_init.sql")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:220] if detail else "")


def doc_bmap(doc):
    out = {}
    if not doc:
        return out
    for p in doc.split(" | "):
        i = p.find(": ")
        if i <= 0:
            continue
        out[p[:i]] = p[i + 2 :]
    return out


def content_hash(doc):
    m = doc_bmap(doc)
    parts = []
    for k in sorted(m):
        if k in ("DataVersion", "__metadata"):
            continue
        if "navigationLinkUrl" in k:
            continue
        if m[k] == "":
            continue
        parts.append(k + "\x01" + m[k])
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def bmap_common_eq(a, b):
    common = set(a) & set(b)
    if not common:
        return False
    return all(a[k] == b[k] for k in common)


def default_tol():
    raw = os.environ.get("MERGE_VECTOR_LOSS_TOLERANCE", "0.005")
    try:
        v = float(raw)
    except ValueError:
        v = 0.005
    return v if v > 0 else 0.005


def emb_xfer_map(old_rows, new_rows):
    def ch_of(r):
        return r.get("content_hash") or content_hash(r.get("doc") or "")

    old_by_ch = defaultdict(list)
    old_by_refs = defaultdict(list)
    for o in old_rows:
        if o.get("emb") is None:
            continue
        old_by_ch[(o["src_table"], ch_of(o))].append(o)
        refs = o.get("refs") or ""
        if refs:
            old_by_refs[(o["src_table"], refs)].append(o)
    new_by_ch = defaultdict(list)
    new_by_refs = defaultdict(list)
    for n in new_rows:
        new_by_ch[(n["src_table"], ch_of(n))].append(n)
        refs = n.get("refs") or ""
        if refs:
            new_by_refs[(n["src_table"], refs)].append(n)
    best = {}
    for key, news in new_by_ch.items():
        olds = old_by_ch.get(key, [])
        if len(olds) == 1 and len(news) == 1:
            n = news[0]
            best[(n["src_table"], n["row_key"])] = 1
    for key, news in new_by_refs.items():
        olds = old_by_refs.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        o, n = olds[0], news[0]
        if bmap_common_eq(doc_bmap(o["doc"]), doc_bmap(n["doc"])):
            best.setdefault((n["src_table"], n["row_key"]), 2)
    return set(best)


def vec_budget(old_rows, new_rows, *, rewrite_wave=None, use_xfer=True):
    rewrite_wave = set(rewrite_wave or [])

    def ch_of(r):
        return r.get("content_hash") or content_hash(r.get("doc") or "")

    old_emb = [o for o in old_rows if o.get("emb") is not None]
    was_total = len(old_emb)
    new_idx = {
        (n["src_table"], n["row_key"]): (ch_of(n), doc_bmap(n.get("doc") or ""))
        for n in new_rows
    }
    surviving = 0
    hash_kill = 0
    unmatched_kill = 0
    by = defaultdict(lambda: {
        "was": 0, "surviving": 0, "hash_kill": 0, "unmatched": 0, "saved": 0,
    })
    for o in old_emb:
        st, rk = o["src_table"], o["row_key"]
        by[st]["was"] += 1
        och = ch_of(o)
        ob = doc_bmap(o.get("doc") or "")
        if (st, rk) not in new_idx:
            unmatched_kill += 1
            by[st]["unmatched"] += 1
            continue
        nch, nb = new_idx[(st, rk)]
        if nch == och or bmap_common_eq(ob, nb):
            surviving += 1
            by[st]["surviving"] += 1
        else:
            hash_kill += 1
            by[st]["hash_kill"] += 1

    saved = set()
    if use_xfer and rewrite_wave:
        saved = {
            (st, rk) for st, rk in emb_xfer_map(old_rows, new_rows)
            if st in rewrite_wave
        }
    for st, _rk in saved:
        by[st]["saved"] += 1
    saved_n = len(saved)
    died = max(was_total - surviving - saved_n, 0)

    reason = "ok"
    if unmatched_kill > 0 and any(
        st in rewrite_wave and by[st]["saved"] == 0 for st in by
    ):
        reason = "rewrite_wave без карты"
    elif unmatched_kill > 0 and any(st in rewrite_wave for st in by):
        reason = "rewrite_wave: unmatched минус карта"
    elif unmatched_kill > 0:
        reason = "unmatched"
    elif hash_kill > 0:
        reason = "content_hash/значение-изменение вне карты"

    frac = (died / was_total) if was_total else 0.0
    return {
        "died": died, "was": was_total, "surviving": surviving, "saved": saved_n,
        "hash_kill": hash_kill, "unmatched": unmatched_kill, "reason": reason,
        "fraction": frac, "by_table": dict(by),
    }


def gate_fires(budget, tol=None):
    tol = default_tol() if tol is None else tol
    if budget["was"] == 0:
        return False
    return budget["fraction"] > tol


# --- 1. смена формы (порядок/пустые/шум), тот же row_key → потерь 0 ---
old_form = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Номенклатура: X | Цена: 100", "emb": [0.1],
}]
new_form = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Цена: 100 | Номенклатура: X | Организация: | DataVersion: 3",
}]
b1 = vec_budget(old_form, new_form, use_xfer=False)
t("form-only same key: content_hash equal",
  content_hash(old_form[0]["doc"]) == content_hash(new_form[0]["doc"]))
t("form-only same key: died=0", b1["died"] == 0, b1)
t("form-only same key: gate quiet", not gate_fires(b1))
t("form-only same key: surviving=1", b1["surviving"] == 1 and b1["saved"] == 0)
t("form-only reorder: hash equal",
  content_hash("t | A: 1 | B: 2") == content_hash("t | B: 2 | A: 1"))

# форма с новой заполненной колонкой → hash другой, common_eq спасает
old_ff = [{
    "src_table": "e", "row_key": "k1", "refs": "Номенклатура: X",
    "doc": "уст | Номенклатура: X | Цена: 100", "emb": [0.1],
}]
new_ff = [{
    "src_table": "e", "row_key": "k1", "refs": "Номенклатура: X",
    "doc": "уст | Номенклатура: X | Цена: 100 | Организация: ООО",
}]
b1b = vec_budget(old_ff, new_ff, use_xfer=False)
t("form filled col: hash differs",
  content_hash(old_ff[0]["doc"]) != content_hash(new_ff[0]["doc"]))
t("form filled col: common_eq → died=0", b1b["died"] == 0 and b1b["surviving"] == 1, b1b)

# --- 2. перепроведение со сменой значения → только изменённые ---
old_val = [
    {"src_table": "e", "row_key": "k1", "doc": "t | V: 1", "emb": [1.0]},
    {"src_table": "e", "row_key": "k2", "doc": "t | V: 2", "emb": [2.0]},
    {"src_table": "e", "row_key": "k3", "doc": "t | V: 3", "emb": [3.0]},
]
new_val = [
    {"src_table": "e", "row_key": "k1", "doc": "t | V: 1"},
    {"src_table": "e", "row_key": "k2", "doc": "t | V: 99"},
    {"src_table": "e", "row_key": "k3", "doc": "t | V: 3"},
]
b2 = vec_budget(old_val, new_val, use_xfer=True)
t("value change: hash_kill=1", b2["hash_kill"] == 1, b2)
t("value change: surviving=2", b2["surviving"] == 2, b2)
t("value change: died=1", b2["died"] == 1, b2)
t("value change: reason", "content_hash" in b2["reason"] or "значение" in b2["reason"])
t("value change 33%: fires at 0.5%", gate_fires(b2, 0.005))
t("value change 33%: quiet at tol=0.5", not gate_fires(b2, 0.5))

# --- 3. волна 30% вне карты → стоп ---
n = 100
old_wave = [
    {"src_table": "e", "row_key": "o%d" % i, "refs": "r%d" % i,
     "doc": "t | K: %d | V: %d" % (i, i), "emb": [float(i)]}
    for i in range(n)
]
new_wave = []
for i in range(n):
    if i < 70:
        # равный канон (перестановка) → content_hash xfer
        new_wave.append({
            "src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
            "doc": "t | V: %d | K: %d" % (i, i),
        })
    else:
        new_wave.append({
            "src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
            "doc": "t | K: %d | V: %d" % (i, i + 1000),
        })
b3 = vec_budget(old_wave, new_wave, rewrite_wave={"e"}, use_xfer=True)
t("wave 30% loss: saved=70", b3["saved"] == 70, b3)
t("wave 30% loss: died=30", b3["died"] == 30, b3)
t("wave 30% loss: fraction=0.3", abs(b3["fraction"] - 0.3) < 1e-9, b3)
t("wave 30% loss: gate fires", gate_fires(b3, 0.005))
t("wave 30% loss: reason rewrite/unmatched",
  "rewrite_wave" in b3["reason"] or "unmatched" in b3["reason"], b3["reason"])

b3b = vec_budget(old_wave, new_wave, rewrite_wave={"e"}, use_xfer=False)
t("wave no map: died=100", b3b["died"] == 100)
t("wave no map: reason без карты",
  b3b["reason"] == "rewrite_wave без карты", b3b["reason"])

# --- 4. потеря 0.3% ниже порога ---
n4 = 1000
old4 = [
    {"src_table": "e", "row_key": "o%d" % i, "refs": "r%d" % i,
     "doc": "t | K: %d" % i, "emb": [1.0]}
    for i in range(n4)
]
new4 = [
    {"src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
     "doc": ("t | K: %d" % i) if i < 997 else ("t | K: %d | X: 1" % i)}
    for i in range(n4)
]
# last 3: add filled col with no common? K still common with same value → common_eq!
# need real value change for the 3
new4 = [
    {"src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
     "doc": ("t | K: %d" % i) if i < 997 else ("t | K: %d" % (i + 5000))}
    for i in range(n4)
]
b4 = vec_budget(old4, new4, rewrite_wave={"e"}, use_xfer=True)
t("0.3% loss: died=3", b4["died"] == 3, b4)
t("0.3% loss: fraction=0.003", abs(b4["fraction"] - 0.003) < 1e-12, b4)
t("0.3% loss: below 0.5% → quiet", not gate_fires(b4, 0.005))

# --- 5. порог из env ---
t("default tol 0.005", default_tol() == 0.005)
_saved = os.environ.get("MERGE_VECTOR_LOSS_TOLERANCE")
os.environ["MERGE_VECTOR_LOSS_TOLERANCE"] = "0.01"
t("env tol 0.01", default_tol() == 0.01)
if _saved is None:
    os.environ.pop("MERGE_VECTOR_LOSS_TOLERANCE", None)
else:
    os.environ["MERGE_VECTOR_LOSS_TOLERANCE"] = _saved
t("env restored", default_tol() == (float(_saved) if _saved else 0.005))

# --- grep ---
txt = open(MERGE, encoding="utf-8").read()
bsh = open(BUILD, encoding="utf-8").read()
init = open(INIT, encoding="utf-8").read()

t("SQL: tmp3_merge_vec_budget", "CREATE OR REPLACE TABLE tmp3_merge_vec_budget AS" in txt)
t("SQL: error vector-budget", "вектор-бюджет" in txt)
t("SQL: vector_loss_gate", "vector_loss_gate" in txt)
t("SQL: vector_loss_bypass", "vector_loss_bypass" in txt)
t("SQL: reason rewrite_wave без карты", "rewrite_wave без карты" in txt)
t("SQL: reason unmatched", "THEN 'unmatched'" in txt)
t("SQL: reason content_hash/значение",
  "content_hash/значение-изменение вне карты" in txt)
t("SQL: tol 0.005", "vector_loss_tol" in txt and "0.005" in txt)
t("SQL: gate BEFORE MERGE",
  txt.find("tmp3_merge_vec_budget") < txt.find("MERGE INTO search_corpus"))
t("SQL: gate BEFORE DELETE unmatched keys",
  txt.find("вектор-бюджет")
  < txt.find("DELETE FROM search_corpus c\nWHERE c.src_table IN"))
t("SQL: content_hash fill AFTER gate",
  txt.find("вектор-бюджет")
  < txt.find("UPDATE search_corpus SET content_hash = corpus_content_hash(doc)"))
t("SQL: MATCHED content_hash + common_eq keep emb",
  "WHEN MATCHED AND t.content_hash IS DISTINCT FROM s.content_hash" in txt
  and "THEN t.emb ELSE NULL END" in txt)
t("SQL: row_key join unchanged",
  "ON t.src_table = s.src_table AND t.row_key = s.row_key" in txt)
t("init: corpus_content_hash", "CREATE OR REPLACE MACRO corpus_content_hash(doc)" in init)
t("init: content_hash column", "content_hash VARCHAR" in init)
t("build.sh: MERGE_VECTOR_LOSS_TOLERANCE", "MERGE_VECTOR_LOSS_TOLERANCE" in bsh)
t("build.sh: MERGE_VECTOR_LOSS_BYPASS", "MERGE_VECTOR_LOSS_BYPASS" in bsh)
t("build.sh: cfg vector_loss_tol",
  "vector_loss_tol" in bsh and "vector_loss_bypass" in bsh)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
