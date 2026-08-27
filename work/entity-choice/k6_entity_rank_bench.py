#!/usr/bin/env python3
"""ПРИБОР K6: место эталонной сущности до/после меры answer_fit.

Набор: ubuntu/serenedb/ab-gold-okna.tsv (23 вопроса). Эталон — src_table из SQL
(не руками). Ранг «до» — tfidf по search_entity_alias (лексика словаря).
Ранг «после» — тот же список, переставленный reorder_by_answer_fit.

Модель не зовётся. Считает база. serene_ask.py не трогаем.

  SERENEDB_DSN=… python3 work/entity-choice/k6_entity_rank_bench.py

На okna: DSN+PGPASSWORD из окружения юнита ask (dbname=postgres).
"""
from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))

from entity_answer_fit import (  # noqa: E402
    answer_fit_table, period_bounds, reorder_by_answer_fit,
)

GOLD = os.environ.get(
    "SET_FILE", os.path.join(ROOT, "ubuntu/serenedb/ab-gold-okna.tsv"))
DEPTH = int(os.environ.get("DEPTH", "24"))
STEM = os.environ.get("ASK_STEM_DICT", "search_dict_stem")
TZ_TODAY = os.environ.get("ASK_TODAY", "")  # YYYY-MM-DD; пусто — из базы


def _dsn_parts():
    d = os.environ.get("SERENEDB_DSN_RO") or os.environ.get("SERENEDB_DSN") or ""
    out = {}
    for m in re.finditer(r"(\w+)=([^\s]+)", d):
        out[m.group(1)] = m.group(2)
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
        raise RuntimeError((r.stderr or r.stdout or "psql")[:400])
    rows = []
    for ln in r.stdout.splitlines():
        if not ln.strip():
            continue
        rows.append(tuple(ln.split("\t")))
    return rows


def gold_pairs(path):
    """вопрос → эталонный src_table (первый src_table='…' в SQL, не CTE-имя)."""
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
            if "DISTINCT" in sql_u:
                form = "distinct"
            elif re.search(r"\bSUM\s*\(", sql_u):
                form = "sum"
            else:
                form = "count"
            out.append((q, want.lower(), mode, form))
    return out


def kind_guess(question):
    """Род без модели: основы вопроса ∩ catalog aliases — лидер по tfidf.

    Не список слов: двигатель ранжирует aliases @@ вопрос по alias_idx.
    """
    rows = psql(
        "SELECT src_table, tfidf(alias_idx.tableoid) AS s "
        "FROM alias_idx "
        "WHERE aliases @@ %s AND src_table LIKE 'catalog_%%' "
        "ORDER BY s DESC NULLS LAST, src_table LIMIT 3"
        % lit(question))
    if not rows:
        return ""
    src = rows[0][0]
    lab = psql(
        "SELECT coalesce(nullif(trim(split_part(a.aliases, ',', 1)), ''), t.label) "
        "FROM search_entity_alias a JOIN search_tables t ON t.src_table = a.src_table "
        "WHERE a.src_table = %s LIMIT 1" % lit(src))
    if lab and lab[0] and lab[0][0]:
        return str(lab[0][0]).strip().split()[0].lower()
    return src.replace("catalog_", "")


def alias_order(question, depth=DEPTH):
    # Доки: Ranking — ORDER BY scorer(idx.tableoid); FROM индекс, не JOIN базы.
    rows = psql(
        "SELECT src_table, tfidf(alias_idx.tableoid) AS s "
        "FROM alias_idx "
        "WHERE aliases @@ %s "
        "ORDER BY s DESC NULLS LAST, src_table LIMIT %d"
        % (lit(question), depth))
    return [r[0] for r in rows if r and r[0]]


def expand_holders(order, kind):
    """Как entity_form_expand_pool: держатели осей kind-catalog в пул, если их нет.

    Иначе fit нечему поднимать — лексика справочника вытеснила регистр из top-N.
    Гейт: в лексическом пуле уже есть catalog_* kind (не тащим оси от ложного kind).
    """
    out = list(order)
    seen = set(out)
    if not kind or not out:
        return out
    cats = [r[0] for r in (psql(
        "SELECT t.src_table FROM search_tables t "
        "LEFT JOIN search_entity_alias a ON a.src_table = t.src_table "
        "WHERE t.src_table LIKE 'catalog_%%' AND list_has_any("
        "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
        "  list_filter(ts_lexize(%s, concat_ws(' ', t.label, a.aliases, "
        "                                      coalesce(a.best_used_for,''))),"
        "              x -> length(x) >= 3))"
        % (lit(STEM), lit(kind), lit(STEM))) or []) if r and r[0]]
    if not cats or not any(c in seen for c in cats):
        return out
    for cat in cats:
        if cat not in seen:
            seen.add(cat)
            out.append(cat)
        for h in psql(
                "SELECT src_table FROM search_refcols "
                "WHERE target_src = %s AND src_table LIKE 'accumulationregister_%%'"
                % lit(cat)) or []:
            if h and h[0] and h[0] not in seen:
                seen.add(h[0])
                out.append(h[0])
    return out


def place(order, etalon, fam):
    """1-based; 0 = нет. Семья: parent или сам."""
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


def main():
    pairs = gold_pairs(GOLD)
    fam = family_map()
    today = today_db()
    print("gold=%s вопросов=%d depth=%d today=%s\n" % (GOLD, len(pairs), DEPTH, today))
    before = {"lead": 0, "top3": 0, "miss": 0}
    after = {"lead": 0, "top3": 0, "miss": 0}
    lines = []
    for i, (q, want, mode, form) in enumerate(pairs, 1):
        order0 = alias_order(q)
        kind = kind_guess(q)
        order0 = expand_holders(order0, kind)
        # want агрегата — из формы эталонного SQL (distinct/count/sum), не из слов.
        want_agg = "sum" if form == "sum" or mode == "name" else "count"
        intent = {"kind": kind, "want": want_agg, "period": {}}
        scores = answer_fit_table(
            psql, lit, order0, intent, today=today,
            stem_dict=lit(STEM))
        order1 = (reorder_by_answer_fit(order0, scores)
                  if want_agg == "count" else list(order0))
        p0 = place(order0, want, fam)
        p1 = place(order1, want, fam)
        for bag, p in ((before, p0), (after, p1)):
            if p == 1:
                bag["lead"] += 1
            if 1 <= p <= 3:
                bag["top3"] += 1
            if p == 0:
                bag["miss"] += 1
        head0 = order0[0] if order0 else "—"
        head1 = order1[0] if order1 else "—"
        fit_w = scores.get(want, 0)
        lines.append(
            "%2d. place %s→%s  etalon=%s  head %s→%s  fit_et=%s  kind=%s form=%s | %s"
            % (i, p0 or "∅", p1 or "∅", want, head0, head1, fit_w, kind, form, q[:50]))
    print("=== ДО (alias tfidf + expand holders) ===")
    print("эталон-лидер: %d / %d" % (before["lead"], len(pairs)))
    print("в тройке:     %d / %d" % (before["top3"], len(pairs)))
    print("не найден:    %d / %d" % (before["miss"], len(pairs)))
    print("\n=== ПОСЛЕ (answer_fit reorder на count) ===")
    print("эталон-лидер: %d / %d" % (after["lead"], len(pairs)))
    print("в тройке:     %d / %d" % (after["top3"], len(pairs)))
    print("не найден:    %d / %d" % (after["miss"], len(pairs)))
    print("\n=== построчно ===")
    for ln in lines:
        print(ln)
    # контрольные K6
    print("\n=== контроль K6 (form=count|distinct, etalon catalog|register) ===")
    for q, want, _mode, form in pairs:
        if form not in ("count", "distinct"):
            continue
        if not (want.startswith("catalog_") or want.startswith("accumulationregister_")):
            continue
        o0 = alias_order(q)
        kind = kind_guess(q)
        o0 = expand_holders(o0, kind)
        sc = answer_fit_table(
            psql, lit, o0, {"kind": kind, "want": "count", "period": {}},
            today=today, stem_dict=lit(STEM))
        o1 = reorder_by_answer_fit(o0, sc)
        print("Q:", q)
        print("  etalon", want, "before", place(o0, want, fam),
              "after", place(o1, want, fam), "form", form)
        print("  top3 before", o0[:3])
        print("  top3 after ", o1[:3])
        print("  fit", {k: sc[k] for k in o1[:5] if k in sc})


if __name__ == "__main__":
    main()
