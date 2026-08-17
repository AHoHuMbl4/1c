#!/usr/bin/env python3
"""Читай-сторона журнала ask_journal + разметка наборов самопроверки.

Независимая истина — прямой SQL по корпусу (та же формула, что selftest_check).
Существующие приборы selftest_* не меняются.

  ASK_BASE=ut_test|postgres python3 ubuntu/serenedb/ask_journal_label.py
  ASK_BASE=both — обе дев-базы.

Пишет work/acceptance/runs/ask-journal-label-<база>.json
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
NF = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
SUM_TOL = Decimal("0.01")


def load_env(path):
    if not os.path.isfile(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def rw_dsn(base):
    return "host=127.0.0.1 port=7890 user=postgres dbname=%s" % base


def psql_rw(base, sql):
    env = dict(os.environ)
    env.pop("PGUSER", None)
    env.pop("PGDATABASE", None)
    env.pop("PGPASSWORD", None)
    p = subprocess.run(["psql", rw_dsn(base), "-v", "ON_ERROR_STOP=1",
                        "-tA", "-F", "\x1f", "-c", sql],
                       text=True, capture_output=True, env=env)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[:300])
    return [ln for ln in p.stdout.splitlines() if ln.strip()]


def apply_schema(base):
    env = dict(os.environ)
    env.pop("PGUSER", None)
    env.pop("PGPASSWORD", None)
    env["ASK_JOURNAL_RW_DSN"] = rw_dsn(base)
    p = subprocess.run(["bash", os.path.join(HERE, "ask_journal_apply.sh"), base],
                       text=True, capture_output=True, env=env)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-300:])


def load_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def truth_of(base):
    """Прямой пересчёт count/sum по корпусу — как selftest_check.compute_truth."""
    sys.path.insert(0, HERE)
    load_env("/etc/1c-serene-ask-%s.env" % base)
    load_env("/etc/1c-mcp-reports.env")
    import serene_ask as A
    A.DSN = "host=127.0.0.1 port=7890 user=serene_ro dbname=%s" % base
    A.PGPASSWORD = os.environ.get("PGPASSWORD", "")
    counts = {}
    for r in A.psql("SELECT src_table, count(*) FILTER (WHERE %s) FROM %s GROUP BY 1"
                    % (NF, A.CORPUS)):
        if r and r[0]:
            counts[r[0]] = int(r[1] or 0)
    sums = {}
    q = ("SELECT src_table, struct_extract(x,'key'), "
         "sum(TRY_CAST(x.value AS DECIMAL(38,10))) FILTER (WHERE %s) "
         "FROM %s, unnest(map_entries(nums)) AS u(x) "
         "WHERE nums IS NOT NULL GROUP BY 1, 2" % (NF, A.CORPUS))
    for r in A.psql(q):
        if r and r[0] and len(r) > 1 and r[1]:
            sums[(r[0], r[1])] = r[2] if r[2] != "" else None
    return counts, sums, A


def replay(base, A):
    """Прогон записанного потока самопроверки в журнал (channel=selftest)."""
    gen = load_jsonl(os.path.join(RUNS, "selftest-%s.jsonl" % base))
    if not gen:
        gen = load_jsonl(os.path.join(RUNS, "selftest-%s-tier2.jsonl" % base))
    results = {}
    for name in ("selftest-%s-results.jsonl" % base,
                 "selftest-%s-results-tier2.jsonl" % base):
        for rec in load_jsonl(os.path.join(RUNS, name)):
            rid = rec.get("id")
            if rid and rid not in results:
                results[rid] = rec
    code_md5 = A._journal_code_md5()
    alias_ver = A._journal_alias_ver()
    build_ts = A._journal_build_ts()
    psql_rw(base, "DELETE FROM ask_journal WHERE channel='selftest'")
    mx = psql_rw(base, "SELECT coalesce(max(id),0) FROM ask_journal")
    top = int((mx[0] if mx else "0") or 0)
    if top <= 0:
        psql_rw(base, "SELECT setval('ask_journal_id_seq', 1, false)")
    else:
        psql_rw(base, "SELECT setval('ask_journal_id_seq', %d)" % top)
    lit = A.lit
    chunk, n = [], 0

    def flush():
        if not chunk:
            return
        psql_rw(base, "INSERT INTO ask_journal ("
                "id, db_name, channel, user_hash, q_hash, q_len, intent_json, outcome, "
                "fork_outcome, atoms, fork_keys, ticket_used, ticket_error, code_md5, "
                "build_ts, alias_ver, tokens_in, tokens_out, tokens_calls, latency_ms, "
                "partial_flag, freshness_age_sec, uncounted, truncated, discarded_before) "
                "SELECT nextval('ask_journal_id_seq'), current_database(), x.* FROM (VALUES "
                + ",".join(chunk) + ") AS x")
        chunk.clear()

    for rec in gen:
        res = results.get(rec.get("id")) or {}
        kind = res.get("kind") or "unavailable"
        if res.get("http") and res.get("http") != 200:
            kind = "unavailable"
        q = rec.get("question") or ""
        fig = res.get("figures") or {}
        atom = json.dumps({"operation": rec.get("qkind") or "count",
                           "exact_value": fig.get("sum") or fig.get("count"),
                           "measure_id": rec.get("measure")}, ensure_ascii=False)
        intent = json.dumps({"kind": rec.get("qkind"), "measure": rec.get("measure")},
                            ensure_ascii=False)
        lat = int((res.get("sec") or 0) * 1000)
        qh = hashlib.sha256(q.encode("utf-8")).hexdigest()
        uh = hashlib.sha256(base.encode("utf-8")).hexdigest()
        chunk.append("(%s,%s,%s,%s,%s,%s,%s,%s::JSON,%s,FALSE,'',%s,%s,%s,NULL,NULL,NULL,%s,"
                     "FALSE,NULL,0,0,0)" % (
                         lit("selftest"), lit(uh), lit(qh), len(q), lit(intent),
                         lit(kind), lit(""), lit(atom), lit("[]"),
                         lit(code_md5), lit(build_ts), lit(alias_ver), lat))
        n += 1
        if len(chunk) >= 80:
            flush()
    flush()
    return n, len(results)


def summary_sql(base):
    rows = psql_rw(base, """
        SELECT outcome, coalesce(code_md5,''), coalesce(alias_ver,''),
               count(*),
               count(*) FILTER (WHERE uncounted > 0),
               count(*) FILTER (WHERE truncated > 0),
               count(*) FILTER (WHERE ticket_used),
               count(*) FILTER (WHERE coalesce(ticket_error,'') <> ''),
               round(avg(latency_ms)),
               count(*) FILTER (WHERE partial_flag)
        FROM ask_journal
        GROUP BY 1, 2, 3
        ORDER BY 1, 2
    """)
    parsed = []
    for ln in rows:
        p = ln.split("\x1f")
        if len(p) < 10:
            continue
        parsed.append({
            "outcome": p[0], "code_md5": p[1][:12], "alias_ver": p[2],
            "n": int(p[3] or 0), "uncounted_n": int(p[4] or 0),
            "truncated_n": int(p[5] or 0), "ticket_used": int(p[6] or 0),
            "ticket_error": int(p[7] or 0), "avg_latency_ms": p[8],
            "partial_n": int(p[9] or 0),
        })
    tot = psql_rw(base, "SELECT count(*), "
                         "count(*) FILTER (WHERE uncounted > 0), "
                         "count(*) FILTER (WHERE truncated > 0), "
                         "count(*) FILTER (WHERE channel='selftest'), "
                         "count(*) FILTER (WHERE channel='http' OR channel='lock') "
                         "FROM ask_journal")
    t = (tot[0].split("\x1f") if tot else ["0"] * 5)
    privacy = psql_rw(base,
        "SELECT count(*) FROM duckdb_columns() WHERE table_name='ask_journal' "
        "AND schema_name='public' AND database_name=current_database() "
        "AND lower(column_name) IN ('question','text','query')")
    kinds = psql_rw(base, "SELECT outcome, count(*) FROM ask_journal GROUP BY 1 ORDER BY 1")
    return {
        "by_outcome_version": parsed,
        "total": int(t[0] or 0),
        "uncounted_rows": int(t[1] or 0),
        "truncated_rows": int(t[2] or 0),
        "selftest_rows": int(t[3] or 0),
        "live_rows": int(t[4] or 0),
        "question_columns": int(privacy[0] or 0) if privacy else 0,
        "kinds": {ln.split("\x1f")[0]: int(ln.split("\x1f")[1])
                  for ln in kinds if "\x1f" in ln},
    }


def truth_check(base, counts, sums):
    """Замок 13-14: виды исходов в журнале + сверка атомов selftest с SQL."""
    gen = {r["id"]: r for r in load_jsonl(os.path.join(RUNS, "selftest-%s.jsonl" % base))}
    if not gen:
        gen = {r["id"]: r for r in load_jsonl(os.path.join(RUNS, "selftest-%s-tier2.jsonl" % base))}
    results = {}
    for name in ("selftest-%s-results.jsonl" % base,
                 "selftest-%s-results-tier2.jsonl" % base):
        for rec in load_jsonl(os.path.join(RUNS, name)):
            if rec.get("id"):
                results[rec["id"]] = rec
    class_n = Counter()
    atom_ok = atom_bad = atom_skip = 0
    for rid, rec in gen.items():
        res = results.get(rid)
        if not res:
            class_n["нет результата"] += 1
            continue
        kind = res.get("kind") or "unavailable"
        class_n[kind] += 1
        src = rec.get("src_table")
        focus = res.get("focus")
        if kind not in ("answer", "figures"):
            atom_skip += 1
            continue
        if focus != src:
            atom_skip += 1
            continue
        fig = res.get("figures") or {}
        if rec.get("qkind") == "count":
            want, got = counts.get(src), fig.get("count")
            ok = (got is not None and want is not None and int(got) == int(want))
        else:
            want = sums.get((src, rec.get("measure")))
            got = fig.get("sum")
            w, g = dec(want), dec(got)
            ok = w is not None and g is not None and abs(w - g) <= SUM_TOL
        if ok:
            atom_ok += 1
        else:
            atom_bad += 1
    return {"flow_kinds": dict(class_n), "atom_ok": atom_ok,
            "atom_bad": atom_bad, "atom_skip": atom_skip}


def one_base(base):
    print("==", base)
    apply_schema(base)
    counts, sums, A = truth_of(base)
    n_gen, n_res = replay(base, A)
    summ = summary_sql(base)
    truth = truth_check(base, counts, sums)
    lost = A._JOURNAL_LOST
    out = {"base": base, "replayed": n_gen, "results_seen": n_res,
           "journal_lost": lost, "keep_n": A._journal_keep_n(),
           "entities": len(counts), "journal": summ, "truth": truth,
           "lock13_kinds": sorted(summ.get("kinds") or {}),
           "uncounted_share": (summ["uncounted_rows"] / summ["total"]
                               if summ["total"] else 0),
           "truncated_share": (summ["truncated_rows"] / summ["total"]
                               if summ["total"] else 0)}
    path = os.path.join(RUNS, "ask-journal-label-%s.json" % base)
    os.makedirs(RUNS, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in (
        "base", "replayed", "results_seen", "journal_lost", "keep_n",
        "lock13_kinds", "uncounted_share", "truncated_share") if k in out},
                     ensure_ascii=False))
    print("  journal.kinds", summ.get("kinds"))
    print("  truth.flow_kinds", truth.get("flow_kinds"))
    print("  atom ok/bad/skip", truth["atom_ok"], truth["atom_bad"], truth["atom_skip"])
    print("  wrote", path)
    return out


def main():
    which = os.environ.get("ASK_BASE") or (sys.argv[1] if len(sys.argv) > 1 else "both")
    bases = ["postgres", "ut_test"] if which in ("both", "all") else [which]
    reports = [one_base(b) for b in bases]
    return 0 if reports else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
