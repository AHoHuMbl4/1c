#!/usr/bin/env python3
"""Прибор K6-мера v2: сравнение v1 vs v2 на gold-23 + 5 «позиций».

Пул: alias_idx tfidf + структурное расширение (держатели kind, live sales при
пустом alias на sum/name). Модель не зовётся. serene_ask.py не трогаем.

  SERENEDB_DSN=… python3 work/k6-rank-v2/bench.py

Доки: Relevance Tuning — business signal в ORDER BY (лексика × данные).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERENEDB = os.path.join(ROOT, "ubuntu/serenedb")
sys.path.insert(0, HERE)
sys.path.insert(0, SERENEDB)

from entity_rank_v2 import (  # noqa: E402
    features_table, is_noncanon_sales, object_prefix, period_bounds,
    reorder_v1, reorder_v2, kind_from_alias_overlap,
    expand_holders as k6_expand_holders,
    expand_stem_and_live as k6_expand_stem_and_live,
)

GOLD = os.environ.get(
    "SET_FILE", os.path.join(ROOT, "ubuntu/serenedb/ab-gold-okna.tsv"))
EXTRA = os.environ.get(
    "EXTRA_FILE", os.path.join(HERE, "questions_positions.tsv"))
DEPTH = int(os.environ.get("DEPTH", "24"))
STEM = os.environ.get("ASK_STEM_DICT", "search_dict_stem")
DUMP_DIR = os.environ.get("DUMP_DIR", os.path.join(HERE, "dumps"))
TZ_TODAY = os.environ.get("ASK_TODAY", "")


def _dsn_parts():
    d = os.environ.get("SERENEDB_DSN_RO") or os.environ.get("SERENEDB_DSN") or ""
    out = {}
    for m in re.finditer(r"(\w+)=([^\s]+)", d):
        out[m.group(1)] = m.group(2).strip("'\"")
    return out


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql):
    p = _dsn_parts()
    env = os.environ.copy()
    if p.get("password") and not env.get("PGPASSWORD"):
        env["PGPASSWORD"] = p["password"]
    cmd = [
        "psql",
        "-h", p.get("host", "127.0.0.1"),
        "-p", str(p.get("port", "7890")),
        "-U", p.get("user", "serene_ro"),
        "-d", p.get("dbname", "postgres"),
        "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "psql")[:500])
    rows = []
    for ln in r.stdout.splitlines():
        if not ln.strip():
            continue
        rows.append(tuple(ln.split("\t")))
    return rows


def gold_pairs(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split("\t")
            if len(parts) < 2:
                continue
            q, sql = parts[0], parts[1]
            mode = parts[2] if len(parts) > 2 else "digits"
            # extra file may give etalon src directly in col2 without SQL
            if not re.search(r"src_table\s*=", sql, re.I) and sql.startswith(
                    ("catalog_", "accumulationregister_", "document_",
                     "informationregister_")):
                want = sql.lower()
                form = parts[2] if len(parts) > 2 else "count"
                out.append((q, want, mode, form))
                continue
            srcs = re.findall(r"src_table\s*=\s*'([^']+)'", sql, re.I)
            if len(srcs) >= 2 and "DISTINCT" in sql.upper():
                want = next(
                    (s for s in srcs if s.startswith("accumulationregister_")),
                    srcs[-1])
            elif srcs:
                want = srcs[0]
            else:
                continue
            sql_u = sql.upper()
            # complement = catalog count минус DISTINCT (два src_table + DISTINCT),
            # не путать с `d - INTERVAL` в окне.
            n_src = len(srcs)
            if n_src >= 2 and "DISTINCT" in sql_u and re.search(
                    r"\)\s*-\s*\(", sql):
                form = "complement"
            elif "DISTINCT" in sql_u:
                form = "distinct"
            elif re.search(r"\bSUM\s*\(", sql_u):
                form = "sum"
            else:
                form = "count"
            out.append((q, want.lower(), mode, form))
    return out



def alias_order(question, depth=DEPTH):
    rows = psql(
        "SELECT src_table, tfidf(alias_idx.tableoid) AS s "
        "FROM alias_idx "
        "WHERE aliases @@ %s "
        "ORDER BY s DESC NULLS LAST, src_table LIMIT %d"
        % (lit(question), depth))
    return [r[0] for r in rows if r and r[0]]


def kind_guess(question):
    """Kind = лидер catalog по aliases@@ / stem (K6 §7.5 п.5)."""
    return kind_from_alias_overlap(psql, lit, question, stem_dict=STEM)


def expand_holders(order, kind):
    return k6_expand_holders(order, kind, psql, lit, stem_dict=STEM)


def expand_stem_and_live(order, question, form, want_agg):
    return k6_expand_stem_and_live(order, question, form, want_agg, psql, lit,
                                   stem_dict=STEM)


def place(order, etalon, fam):
    et = fam.get(etalon, etalon)
    for i, t in enumerate(order, 1):
        if fam.get(t, t) == et or t == etalon:
            return i
    return 0


def family_map():
    rows = psql(
        "SELECT src_table, coalesce(nullif(parent, ''), src_table) FROM search_tables")
    return {r[0]: r[1] for r in rows if r and r[0]}


def today_db():
    if TZ_TODAY:
        return datetime.date.fromisoformat(TZ_TODAY[:10])
    r = psql("SELECT timezone('Europe/Chisinau', now())::date")
    return datetime.date.fromisoformat(r[0][0])


def bucket(p):
    if p == 1:
        return "lead"
    if 1 <= p <= 3:
        return "top3"
    if 1 <= p <= 8:
        return "top8"
    if p == 0:
        return "miss"
    return "out8"  # in pool but >8


def score_set(pairs, fam, today, tag):
    stats = {
        "v0": {"lead": 0, "top3": 0, "top8": 0, "miss": 0, "out8": 0},
        "v1": {"lead": 0, "top3": 0, "top8": 0, "miss": 0, "out8": 0},
        "v2": {"lead": 0, "top3": 0, "top8": 0, "miss": 0, "out8": 0},
    }
    rows_out = []
    dumps = []
    v1_top3_ok = []  # questions where v1 had etalon in top3
    v2_broke = []
    for i, (q, want, mode, form) in enumerate(pairs, 1):
        order0 = alias_order(q)
        kind = kind_guess(q)
        order0 = expand_holders(order0, kind)
        want_agg = "sum" if form in ("sum", "name") or mode == "name" else "count"
        order0 = expand_stem_and_live(order0, q, form, want_agg)
        # period: only when form already implies window (distinct/complement) —
        # do NOT invent period for plain count (avoids v1 demotion of catalogs)
        intent = {"kind": kind, "want": want_agg, "period": {}}
        if form in ("distinct", "complement"):
            fr, to = period_bounds(intent, today=today)
            intent["period"] = {"from": fr.isoformat(), "to": to.isoformat()}
        feats = features_table(
            psql, lit, order0, intent, today=today, stem_dict=lit(STEM))
        # v1 only reorders on count (as entity_answer_fit)
        order1 = (reorder_v1(order0, feats) if want_agg == "count"
                  else list(order0))
        order2 = reorder_v2(order0, feats, intent, form)
        p0 = place(order0, want, fam)
        p1 = place(order1, want, fam)
        p2 = place(order2, want, fam)
        for key, p in (("v0", p0), ("v1", p1), ("v2", p2)):
            b = bucket(p)
            stats[key][b] += 1
            if b == "top3":
                # top3 includes lead — also counted in lead; keep both metrics
                pass
            # fix: lead already counted; top3 should be cumulative 1..3
        # recount top3/top8 as cumulative
        for key, p in (("v0", p0), ("v1", p1), ("v2", p2)):
            stats[key]["top3"] = stats[key].get("_t3", 0)
            stats[key]["top8"] = stats[key].get("_t8", 0)
        for key, p in (("v0", p0), ("v1", p1), ("v2", p2)):
            if 1 <= p <= 3:
                stats[key]["_t3"] = stats[key].get("_t3", 0) + 1
            if 1 <= p <= 8:
                stats[key]["_t8"] = stats[key].get("_t8", 0) + 1
        if 1 <= p1 <= 3:
            v1_top3_ok.append(q)
            if not (1 <= p2 <= 3):
                v2_broke.append(q)
        head = lambda o: (o[0] if o else "—")
        row = {
            "i": i, "q": q, "etalon": want, "form": form, "kind": kind,
            "place_v0": p0, "place_v1": p1, "place_v2": p2,
            "head_v0": head(order0), "head_v1": head(order1), "head_v2": head(order2),
            "n_pool": len(order0),
            "feat_etalon": feats.get(want, {}),
            "top5_v2": order2[:5],
            "top5_v1": order1[:5],
        }
        rows_out.append(row)
        dumps.append(row)
        print(
            "%2d. %s→%s→%s  et=%s  kind=%s form=%s pool=%d | %s"
            % (i, p0 or "∅", p1 or "∅", p2 or "∅", want, kind, form,
               len(order0), q[:48]))
    # finalize cumulative
    for key in stats:
        stats[key]["top3"] = stats[key].get("_t3", 0)
        stats[key]["top8"] = stats[key].get("_t8", 0)
        stats[key].pop("_t3", None)
        stats[key].pop("_t8", None)
        # lead/miss/out8 already from bucket; but top3 in bucket was exclusive — wipe exclusive
        # Recompute lead/miss/out8 cleanly from rows
    for key in ("v0", "v1", "v2"):
        stats[key] = {"lead": 0, "top3": 0, "top8": 0, "miss": 0, "out8": 0}
    for row in rows_out:
        for key, pk in (("v0", "place_v0"), ("v1", "place_v1"), ("v2", "place_v2")):
            p = row[pk]
            if p == 1:
                stats[key]["lead"] += 1
            if 1 <= p <= 3:
                stats[key]["top3"] += 1
            if 1 <= p <= 8:
                stats[key]["top8"] += 1
            if p == 0:
                stats[key]["miss"] += 1
            elif p > 8:
                stats[key]["out8"] += 1
    os.makedirs(DUMP_DIR, exist_ok=True)
    dump_path = os.path.join(DUMP_DIR, "%s.json" % tag)
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "rows": dumps,
                   "v1_top3_ok": v1_top3_ok, "v2_broke_top3": v2_broke},
                  f, ensure_ascii=False, indent=2, default=str)
    print("\n=== %s n=%d ===" % (tag, len(pairs)))
    for key in ("v0", "v1", "v2"):
        s = stats[key]
        print("%s  lead=%d  top3=%d  top8=%d  out8=%d  miss=%d"
              % (key, s["lead"], s["top3"], s["top8"], s["out8"], s["miss"]))
    print("v1_top3_ok=%d  v2_broke_those=%d %s"
          % (len(v1_top3_ok), len(v2_broke), v2_broke[:5]))
    print("dump=%s" % dump_path)
    return stats, rows_out, v2_broke


def main():
    today = today_db()
    fam = family_map()
    gold = gold_pairs(GOLD)
    print("today=%s gold=%d depth=%d\n" % (today, len(gold), DEPTH))
    g_stats, _, g_broke = score_set(gold, fam, today, "gold23")
    extra = []
    if os.path.isfile(EXTRA):
        extra = gold_pairs(EXTRA)
        print("\n--- extra positions ---\n")
        score_set(extra, fam, today, "positions5")
    # gate summary
    lead_v2 = g_stats["v2"]["lead"]
    ok_gate = lead_v2 >= 12 and len(g_broke) == 0
    print("\nGATE: v2_lead=%d/23 broke_v1_top3=%d → %s"
          % (lead_v2, len(g_broke), "PASS" if ok_gate else "FAIL"))
    summary = {
        "today": str(today),
        "gold": g_stats,
        "gate_lead_ge_12": lead_v2 >= 12,
        "gate_no_top3_regress": len(g_broke) == 0,
        "gate": ok_gate,
    }
    with open(os.path.join(DUMP_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return 0 if ok_gate else 1


if __name__ == "__main__":
    sys.exit(main())
