#!/usr/bin/env python3
"""S2-b / D2: одноимённые прочтения разных OData-kind → clarify, не silent leader.

Оффлайн, без БД/сети. Мок паспортов + wiki_outcome_from_verify +
try_wiki_hybrid_entity_pick (пиры из «базы» по label).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []

# Фикстуры замка (имена — только здесь, не логика продукта).
DOC = "document_реализациятмц"
REG = "accumulationregister_реализациятмц"
REG2 = "informationregister_реализациятмц"
LABEL = "Реализация ТМЦ"
LABEL_NORM = "реализациятмц"


def t(name: str, cond: bool, detail="") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def load_z21(extra_ns=None):
    import ask._imports as real_imp

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    fake = types.ModuleType("ask._wire")
    fake.register_zone = lambda *a, **k: None
    fake.apply_bindings = lambda g: None
    sys.modules["ask._wire"] = fake
    sys.modules["ask._imports"] = real_imp
    src = Z21.read_text(encoding="utf-8")

    def _human(src_table, label=None):
        lab = (label or "").strip()
        if lab:
            return lab
        s = str(src_table or "")
        return s.split("_", 1)[1] if "_" in s else s

    def _readings_menu(question, kind, items, diag, cut, t0, *, reason=""):
        items = list(items or [])
        if len(items) < 2:
            return None
        return {"kind": "clarify", "options": items, "text": reason or "?",
                "diag": dict(diag or {}), "partial": cut}

    def _label_with_kind(src_table, label):
        head = str(src_table or "").split("_", 1)[0].lower()
        kind = {
            "document": "документ",
            "accumulationregister": "регистр накопления",
            "informationregister": "регистр сведений",
            "catalog": "справочник",
        }.get(head, "")
        lab = _human(src_table, label)
        return "%s (%s)" % (lab, kind) if kind else lab

    def _disambiguate(pairs, ambiguous=None):
        """Как z20.disambiguate_labels: kind только при коллизии/амбиг."""
        ambiguous = ambiguous if ambiguous is not None else frozenset()
        norm = lambda s: "".join(str(s or "").lower().split())
        seen = {}
        for src, lab in pairs:
            seen.setdefault(norm(lab), []).append(src)
        out = {}
        for src, lab in pairs:
            many = (len(seen.get(norm(lab), [])) > 1
                    or norm(lab) in ambiguous)
            out[src] = (_label_with_kind(src, lab) if many
                        else _human(src, lab))
        return out

    def _mk_opts(srcs, lab_by, marks=None, by=None, match="", preds=None,
                 live=None, skip_empty_filter=False):
        counted = live
        if counted is None and preds is not None and not skip_empty_filter:
            # имитация keep_empty: режем found=0, если кто-то жив
            counted = by or {}
        srcs = list(srcs or [])
        if counted is not None and not skip_empty_filter:
            live_srcs = [s for s in srcs if counted.get(s, 0) > 0]
            if live_srcs:
                srcs = live_srcs
        # ambiguous_labels подменяется в тестах после load — читаем из ns
        ambig = frozenset()
        try:
            ambig = ns_ref[0]["ambiguous_labels"]()
        except (RuntimeError, TypeError, KeyError, IndexError):
            ambig = frozenset({LABEL_NORM})
        dis = _disambiguate(
            [(s, lab_by.get(s) or "") for s in srcs], ambiguous=ambig)
        return [{"label": dis.get(s) or _human(s), "src": s,
                 "hint": "", "found": (counted or by or {}).get(s, 0)}
                for s in srcs]

    ns_ref = [None]  # заполним после сборки ns

    ns = {
        "__name__": "z21_wiki_choice",
        "__file__": str(Z21),
        "rank_intent_from": lambda *a, **k: False,
        "_intent_text": lambda x: (
            x[0] if isinstance(x, (list, tuple)) and x else x or "") or "",
        "kind_word": lambda s: (
            "документ" if str(s).startswith("document_")
            else "регистр накопления" if str(s).startswith("accumulationregister_")
            else "регистр сведений" if str(s).startswith("informationregister_")
            else "справочник"),
        "human_table_label": _human,
        "label_with_kind": _label_with_kind,
        "ambiguous_labels": lambda: frozenset({LABEL_NORM}),
        "intent_axis_words": lambda intent: [],
        "ds_chat": lambda *a, **k: "{}",
        "lit": lambda s: "'%s'" % str(s).replace("'", "''"),
        "psql": lambda q: [],
        "_ensure_embed_secret": lambda: None,
        "EMBED_MODEL": "m",
        "EMBED_SECRET_NAME": "sec",
        "EMBED_DIM": 1024,
        "STEM_DICT": "russian",
        "TABLES": "search_tables",
        "NO_DATA_TEXT": "",
        "refuse_text": lambda q: "refuse",
        "question_expects_accounting_data": lambda intent, q, diag=None: True,
        "clarify_say": lambda *a, **k: "clarify?",
        "mk_opts": _mk_opts,
        "wiki_menu_captions": lambda opts, **k: opts,
        "wiki_captions_map_from_cards": lambda cards: {
            (c.get("src_table") or ""): c for c in (cards or [])
            if isinstance(c, dict) and c.get("src_table")},
        "readings_menu": _readings_menu,
        # D4: z21 зовёт finalize_clarify_menu; offline-замок — без SQL дайджестов
        "finalize_clarify_menu": (
            lambda question, kind, items, diag, cut, t0, *, reason="",
                   intent=None, plan=None, match="", preds=None,
                   form_key=None, layers=None, src=None, slot_mode=None,
                   with_digests=True: _readings_menu(
                       question, kind, items, diag, cut, t0, reason=reason)),
        "wiki_validate_leader_axes": lambda leader, intent: True,
        "_diag_pack": lambda d, **k: d,
        "register_zone": lambda *a, **k: None,
        "apply_bindings": lambda g: None,
        "wiki_platform_kind": lambda src, parent="": (
            str(src or "").split("_", 1)[0]),
        "time": types.SimpleNamespace(time=lambda: 0.0),
    }
    if extra_ns:
        ns.update(extra_ns)
    for k, v in vars(real_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns.setdefault(k, v)
    ns_ref[0] = ns
    exec(compile(src, str(Z21), "exec"), ns)
    ns["wiki_validate_leader_axes"] = lambda leader, intent: True
    return ns


def _verdicts(fits):
    return [{"index": i + 1, "fit": f} for i, f in enumerate(fits)]


def _psql_router(tables, cards=None, fail_peer=False, fail_ambig_label=False,
                 fail_leader_label=False, fail_ambig_count=False):
    """Мок psql: search_tables / card / probe / ambig-count."""
    tables = dict(tables or {})
    cards = dict(cards or {})

    def _psql(q):
        qs = " ".join(str(q).lower().split())
        if "search_wiki_entity_card limit 1" in qs or (
                "from search_wiki_entity_card" in qs and "limit 1" in qs
                and "where" not in qs):
            return [(1,)]
        if fail_peer and "from search_tables" in qs and "<>" in qs:
            raise RuntimeError("peer-sql-fail")
        # label лидера (LIMIT 1) — отдельно от IN-списка mk_opts
        if (fail_leader_label
                and "select label from search_tables" in qs
                and "limit 1" in qs):
            raise RuntimeError("label-fail")
        # gate: SELECT count(*) … label_norm (не swallow ambiguous_labels)
        if "select count(*)" in qs and "from search_tables" in qs:
            if fail_ambig_count or fail_ambig_label:
                raise RuntimeError("ambig-count-fail")
            n = 0
            for _src, lab in tables.items():
                norm = "".join(str(lab).lower().split())
                if ("'%s'" % norm) in q or norm in qs.replace(" ", ""):
                    n += 1
            return [(n,)]
        if fail_ambig_label and "select label from search_tables" in qs:
            raise RuntimeError("label-fail")
        if "from search_wiki_entity_card" in qs and "where" in qs:
            out = []
            for src, card in cards.items():
                if ("'%s'" % src) in q or ('"%s"' % src) in q or src in q:
                    out.append((
                        src,
                        card.get("name") or "",
                        card.get("description") or "",
                        card.get("axes") or "",
                        card.get("measures") or "",
                        card.get("covered") or 0,
                        card.get("parent") or "",
                    ))
            return out
        if "select src_table, label from search_tables" in qs:
            out = []
            for src, lab in tables.items():
                # IN-list or single / peer scan
                if "<>" in qs:
                    # peer scan: same norm label
                    if "".join(str(lab).lower().split()) == LABEL_NORM:
                        out.append((src, lab))
                elif any(("'%s'" % src) in q for src in tables) or src in q:
                    if ("'%s'" % src) in q or (
                            "in (" in qs and src in q):
                        out.append((src, lab))
            # broader: if WHERE src_table IN — return matching
            if "in (" in qs:
                out = [(s, tables[s]) for s in tables
                       if ("'%s'" % s) in q]
            return out
        if "select label from search_tables" in qs:
            for src, lab in tables.items():
                if ("'%s'" % src) in q:
                    return [(lab,)]
            return []
        return []

    return _psql


def _batch_verify_leader(leader):
    """Мок wiki_batch_verify: ровно один yes на leader → sole → leader."""
    def _batch(question, intent, cards, diag=None, *, passport_cache=None):
        vb = {}
        for c in cards or []:
            src = c.get("src_table")
            if not src:
                continue
            vb[src] = {
                "fit": "yes" if src == leader else "no",
                "why": "ok" if src == leader else "n",
            }
        return {
            "verdicts_by_src": vb,
            "passports": list(cards or []),
            "incomplete": False,
            "diag": dict(diag or {}),
        }
    return _batch


def _run_leader_pick(z, leader, question="", tables=None, cards=None,
                     ambig=None, fail_peer=False, preds=None, by=None,
                     fail_leader_label=False, fail_ambig=False,
                     fail_ambig_count=False):
    tables = tables or {leader: LABEL}
    cards = cards if cards is not None else {
        leader: {"src_table": leader, "name": LABEL}}
    ambig_set = frozenset(ambig) if ambig is not None else frozenset({LABEL_NORM})
    # production-мок: ambiguous_labels глотает сбой → пустой set (не raise)
    if fail_ambig:
        z["ambiguous_labels"] = lambda: frozenset()
        fail_ambig_count = True
    else:
        z["ambiguous_labels"] = lambda: ambig_set
    z["psql"] = _psql_router(
        tables, cards, fail_peer=fail_peer,
        fail_leader_label=fail_leader_label,
        fail_ambig_count=fail_ambig_count)
    z["wiki_hybrid_pool"] = lambda q, intent=None: [
        cards.get(leader) or {"src_table": leader, "name": LABEL}]
    # PERF7: try_wiki зовёт wiki_batch_verify (per-card); 1 yes → leader
    z["wiki_batch_verify"] = _batch_verify_leader(leader)
    z["wiki_leader_post_verify"] = lambda *a, **k: True
    diag = {}
    return z["try_wiki_hybrid_entity_pick"](
        question or "сколько реализации тмц", {}, diag, None, 0.0,
        by=by or {}, match="", preds=preds if preds is not None else [
            "doc_date >= DATE '2026-09-01'"]), diag


def main():
    z = load_z21()
    outcome = z["wiki_outcome_from_verify"]
    peers_fn = z["wiki_homonym_kind_peers"]

    # --- прежние S2-b ---
    p_same = [
        {"src_table": DOC, "name": LABEL},
        {"src_table": REG, "name": LABEL},
    ]
    out1 = outcome(_verdicts(["yes", "no"]), p_same, {})
    t("same name different kind → clarify",
      out1.get("outcome") == "clarify" and len(out1.get("candidates") or []) == 2,
      out1)
    t("diag wiki_homonym_tie",
      (out1.get("diag") or {}).get("wiki_homonym_tie")
      and len((out1.get("diag") or {}).get("wiki_homonym_tie")) == 2)

    p_diff = [
        {"src_table": "catalog_a", "name": "Альфа"},
        {"src_table": "catalog_b", "name": "Бета"},
    ]
    out2 = outcome(_verdicts(["yes", "no"]), p_diff, {})
    t("different names → leader",
      out2.get("outcome") == "leader" and out2.get("leader") == "catalog_a",
      out2)

    p_stem = [
        {"src_table": "document_FooBar", "name": ""},
        {"src_table": "accumulationregister_FooBar", "name": "другие слова"},
    ]
    out3 = outcome(_verdicts(["yes", "no"]), p_stem, {})
    t("same stem different kind → clarify",
      out3.get("outcome") == "clarify", out3)

    p_same_kind = [
        {"src_table": "catalog_one", "name": "Товар"},
        {"src_table": "catalog_two", "name": "Товар"},
    ]
    out4 = outcome(_verdicts(["yes", "no"]), p_same_kind, {})
    t("same name same kind → leader",
      out4.get("outcome") == "leader", out4)

    pr = peers_fn(p_same, DOC)
    t("peers ≥2", len(pr) == 2, pr)
    t("peers empty for sole pool",
      peers_fn(p_same[:1], DOC) == [])

    z20 = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
    t("z20: label_with_kind / disambiguate_labels живы",
      "def label_with_kind" in z20 and "def disambiguate_labels" in z20)
    t("z20: skip_empty_filter в mk_opts",
      "skip_empty_filter" in z20)
    z21txt = Z21.read_text(encoding="utf-8")
    t("z21: readings_menu на clarify hybrid",
      ("readings_menu(" in z21txt
       or "finalize_clarify_menu(" in z21txt))
    t("z21: wiki_homonym_kind_peers жив",
      "def wiki_homonym_kind_peers" in z21txt)
    t("z21: wiki_leader_db_homonym_gate жив",
      "def wiki_leader_db_homonym_gate" in z21txt)

    # --- D2: пул document + пир register в «базе» → clarify 2 ---
    tables_both = {DOC: LABEL, REG: LABEL}
    cards_both = {
        DOC: {"src_table": DOC, "name": LABEL},
        REG: {"src_table": REG, "name": LABEL},
    }
    out_d, diag_d = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both)
    t("D2: pool document + peer register → clarify 2",
      out_d and out_d.get("kind") == "clarify"
      and len(out_d.get("options") or []) == 2,
      out_d)
    srcs_d = sorted(o.get("src") for o in (out_d or {}).get("options") or [])
    t("D2: clarify содержит document+register",
      srcs_d == sorted([DOC, REG]), srcs_d)

    # симметрично: пул register + пир document
    out_r, _ = _run_leader_pick(
        z, REG, tables=tables_both, cards=cards_both)
    t("D2: pool register + peer document → clarify 2",
      out_r and out_r.get("kind") == "clarify"
      and len(out_r.get("options") or []) == 2,
      out_r)

    # оба в пуле (pool-local) — уже покрыто out1; дубль через gate не ломает
    t("D2: оба в пуле (outcome) → clarify",
      out1.get("outcome") == "clarify")

    # пир в search_tables БЕЗ карточки → clarify 2 (синтетический паспорт)
    out_syn, _ = _run_leader_pick(
        z, DOC, tables=tables_both,
        cards={DOC: {"src_table": DOC, "name": LABEL}})  # REG без карточки
    t("D2: пир без карточки → clarify 2",
      out_syn and out_syn.get("kind") == "clarify"
      and len(out_syn.get("options") or []) == 2,
      out_syn)

    # ≥3 пира → все в меню
    tables3 = {DOC: LABEL, REG: LABEL, REG2: LABEL}
    out3p, _ = _run_leader_pick(
        z, DOC, tables=tables3,
        cards={DOC: {"src_table": DOC, "name": LABEL},
               REG: {"src_table": REG, "name": LABEL},
               REG2: {"src_table": REG2, "name": LABEL}})
    opts3 = (out3p or {}).get("options") or []
    t("D2: ≥3 пира → все в меню",
      out3p and out3p.get("kind") == "clarify" and len(opts3) == 3,
      out3p)
    t("D2: ≥3 — все src на месте",
      sorted(o.get("src") for o in opts3) == sorted([DOC, REG, REG2]),
      [o.get("src") for o in opts3])

    # разные label → НЕ пир → leader
    tables_diff = {DOC: LABEL, REG: "Другое имя"}
    out_diff, _ = _run_leader_pick(
        z, DOC, tables=tables_diff,
        cards={DOC: {"src_table": DOC, "name": LABEL}},
        ambig=frozenset())  # метка лидера не амбиг
    t("D2: разные label / неамбиг → leader",
      out_diff and out_diff.get("picked") == [DOC], out_diff)

    # единственный src → leader
    out_sole, _ = _run_leader_pick(
        z, DOC, tables={DOC: LABEL},
        cards={DOC: {"src_table": DOC, "name": LABEL}},
        ambig=frozenset())
    t("D2: единственный src → leader",
      out_sole and out_sole.get("picked") == [DOC], out_sole)

    # неамбиг (count=1) → peer-SQL не звать
    calls = {"peer": 0, "count": 0}
    tables_sole_lab = {DOC: LABEL, REG: "Другое имя"}
    cards_sole = {DOC: {"src_table": DOC, "name": LABEL}}
    base_psql = _psql_router(tables_sole_lab, cards_sole)

    def psql_count(q):
        qs = " ".join(str(q).lower().split())
        if "select count(*)" in qs and "search_tables" in qs:
            calls["count"] += 1
        if "<>" in qs and "search_tables" in qs:
            calls["peer"] += 1
        return base_psql(q)

    z["ambiguous_labels"] = lambda: frozenset()  # swallow-мок не влияет на gate
    z["psql"] = psql_count
    z["wiki_hybrid_pool"] = lambda q, intent=None: [
        {"src_table": DOC, "name": LABEL}]
    z["wiki_batch_verify"] = _batch_verify_leader(DOC)
    z["wiki_leader_post_verify"] = lambda *a, **k: True
    out_na = z["try_wiki_hybrid_entity_pick"](
        "сколько", {}, {}, None, 0.0, by={}, match="", preds=[])
    t("D2: неамбиг → peer-SQL не звать",
      out_na and out_na.get("picked") == [DOC]
      and calls["peer"] == 0 and calls["count"] >= 1,
      (out_na, calls))

    # названный kind → leader (пир чужого рода не поднимается)
    out_named, _ = _run_leader_pick(
        z, REG,
        question="по регистру накопления реализация тмц",
        tables=tables_both, cards=cards_both)
    # named filter: document peer cut → 0 own-kind peers → leader
    t("D2: названный kind → leader",
      out_named and out_named.get("picked") == [REG], out_named)

    # пир пуст в окне (found=0) → всё равно в меню (skip_empty_filter)
    out_empty, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both,
        preds=["doc_date >= DATE '2026-09-01'"],
        by={DOC: 5, REG: 0})
    opts_e = (out_empty or {}).get("options") or []
    t("D2: пир found=0 в окне → всё равно в меню",
      out_empty and out_empty.get("kind") == "clarify"
      and len(opts_e) == 2
      and any(o.get("src") == REG for o in opts_e),
      out_empty)

    # в подписях нет сырых префиксов
    labels = [o.get("label") or "" for o in opts_e]
    t("D2: в подписях нет сырых префиксов",
      all("document_" not in lb and "accumulationregister_" not in lb
          for lb in labels)
      and any("документ" in lb.lower() or "регистр" in lb.lower()
              for lb in labels),
      labels)

    # ambig ∧ peer-SQL fail → не picked
    out_fail, diag_fail = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both, fail_peer=True)
    t("D2: ambig ∧ peer-SQL fail → не picked",
      out_fail is not None
      and not out_fail.get("picked")
      and out_fail.get("kind") == "answer"
      and not (out_fail.get("atoms") or [])
      and (out_fail.get("diag") or {}).get("wiki_homonym_peer_check") == "error",
      out_fail)

    # mk_opts зовётся с явным skip_empty_filter на D2-пути
    seen_skip = {"v": None}
    real_mk = z["mk_opts"]

    def mk_spy(*a, **k):
        seen_skip["v"] = k.get("skip_empty_filter")
        return real_mk(*a, **k)

    z["mk_opts"] = mk_spy
    _run_leader_pick(z, DOC, tables=tables_both, cards=cards_both)
    t("D2: mk_opts skip_empty_filter=True",
      seen_skip["v"] is True, seen_skip)

    # --- D2-fix1: (а) ровно один суффикс вида, без повтора ---
    out_one, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both)
    labs_one = [o.get("label") or "" for o in (out_one or {}).get("options") or []]
    t("D2-fix1: ровно один суффикс вида, без повтора",
      out_one and out_one.get("kind") == "clarify"
      and len(labs_one) == 2
      and all(lb.count("(") == 1 and lb.count(")") == 1 for lb in labs_one)
      and any("(документ)" in lb for lb in labs_one)
      and any("регистр" in lb for lb in labs_one)
      and not any(lb.count("документ") > 1 for lb in labs_one)
      and not any("(документ) (документ)" in lb for lb in labs_one),
      labs_one)

    # --- D2-fix1: (б) found=0 при 2 живых + 1 пустом (rebuild не маскирует) ---
    tables3b = {DOC: LABEL, REG: LABEL, REG2: LABEL}
    cards3b = {
        DOC: {"src_table": DOC, "name": LABEL},
        REG: {"src_table": REG, "name": LABEL},
        REG2: {"src_table": REG2, "name": LABEL},
    }
    out_3e, _ = _run_leader_pick(
        z, DOC, tables=tables3b, cards=cards3b,
        preds=["doc_date >= DATE '2026-09-01'"],
        by={DOC: 5, REG: 3, REG2: 0})
    opts_3e = (out_3e or {}).get("options") or []
    srcs_3e = sorted(o.get("src") for o in opts_3e)
    t("D2-fix1: 2 живых + 1 found=0 → все 3 в меню",
      out_3e and out_3e.get("kind") == "clarify"
      and len(opts_3e) == 3
      and srcs_3e == sorted([DOC, REG, REG2])
      and any(o.get("src") == REG2 and o.get("found") == 0 for o in opts_3e),
      (srcs_3e, opts_3e))

    # без skip_empty_filter пустой выпал бы — проверяем spy на wiki_separability
    seen_skip2 = {"v": "unset"}
    real_mk2 = z["mk_opts"]

    def mk_spy2(*a, **k):
        seen_skip2["v"] = k.get("skip_empty_filter", False)
        return real_mk2(*a, **k)

    z["mk_opts"] = mk_spy2
    z["psql"] = _psql_router(
        {"catalog_a": "Альфа", "catalog_b": "Бета"},
        {"catalog_a": {"src_table": "catalog_a", "name": "Альфа"},
         "catalog_b": {"src_table": "catalog_b", "name": "Бета"}})
    z["ambiguous_labels"] = lambda: frozenset()
    menu_nh = z["wiki_entity_clarify_menu"](
        "сколько", [
            {"src_table": "catalog_a", "name": "Альфа"},
            {"src_table": "catalog_b", "name": "Бета"},
        ], {}, None, 0.0, by={"catalog_a": 1, "catalog_b": 1},
        match="", preds=[], reason="wiki_separability")
    labs_nh = [o.get("label") or "" for o in (menu_nh or {}).get("options") or []]
    t("D2-fix1: не-гомоним меню без kind-суффиксов",
      menu_nh and menu_nh.get("kind") == "clarify"
      and len(labs_nh) == 2
      and sorted(labs_nh) == ["Альфа", "Бета"]
      and not any("(" in lb for lb in labs_nh),
      labs_nh)
    t("D2-fix1: wiki_separability → skip_empty_filter=False",
      seen_skip2["v"] is False, seen_skip2)

    # --- D2-fix1: (3) fail-soft label-SELECT / ambiguous_labels ---
    out_lab, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both,
        fail_leader_label=True)
    t("D2-fix1: label-SELECT fail → не picked (R6)",
      out_lab is not None
      and not out_lab.get("picked")
      and out_lab.get("kind") == "answer"
      and not (out_lab.get("atoms") or [])
      and (out_lab.get("diag") or {}).get("wiki_homonym_peer_check") == "error",
      out_lab)

    out_am, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both, fail_ambig=True)
    t("D2-fix1: ambiguous_labels fail → не picked (R6)",
      out_am is not None
      and not out_am.get("picked")
      and out_am.get("kind") == "answer"
      and not (out_am.get("atoms") or [])
      and (out_am.get("diag") or {}).get("wiki_homonym_peer_check") == "error",
      out_am)

    # --- D2-fix2: (а) separability + 1 живой + 1 found=0 → None как HEAD ---
    z["mk_opts"] = real_mk2  # снять spy
    z["psql"] = _psql_router(
        {"catalog_a": "Альфа", "catalog_b": "Бета"},
        {"catalog_a": {"src_table": "catalog_a", "name": "Альфа"},
         "catalog_b": {"src_table": "catalog_b", "name": "Бета"}})
    z["ambiguous_labels"] = lambda: frozenset()
    menu_sep = z["wiki_entity_clarify_menu"](
        "сколько", [
            {"src_table": "catalog_a", "name": "Альфа"},
            {"src_table": "catalog_b", "name": "Бета"},
        ], {}, None, 0.0, by={"catalog_a": 5, "catalog_b": 0},
        match="", preds=["doc_date >= DATE '2026-09-01'"],
        reason="wiki_separability")
    t("D2-fix2: separability 1 живой + 1 found=0 → None",
      menu_sep is None, menu_sep)

    # --- D2-fix2: (б) production-мок swallow → пустой set, НЕ silent leader ---
    # ambiguous_labels возвращает [] (как при SQL-сбое с пустым кэшем),
    # но count-check падает → R6, не leader при живых пирах в tables
    out_sw, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_both, fail_ambig=True)
    t("D2-fix2: swallow ambiguous_labels + count-fail → не leader",
      out_sw is not None
      and not out_sw.get("picked")
      and out_sw.get("kind") == "answer"
      and (out_sw.get("diag") or {}).get("wiki_homonym_peer_check") == "error",
      out_sw)

    # --- D2-fix2: (в)+(г) card.name≠label → kind ровно один раз; реальный captions ---
    # load_z21 после exec уже держит реальный wiki_menu_captions (не identity)
    t("D2-fix2: wiki_menu_captions не identity",
      z["wiki_menu_captions"].__name__ == "wiki_menu_captions"
      and z["wiki_menu_captions"] is not None)
    CARD_NAME = "Реализация товаров и материалов"
    cards_rename = {
        DOC: {"src_table": DOC, "name": CARD_NAME},
        REG: {"src_table": REG, "name": CARD_NAME},
    }
    out_cap, _ = _run_leader_pick(
        z, DOC, tables=tables_both, cards=cards_rename)
    labs_cap = [o.get("label") or "" for o in (out_cap or {}).get("options") or []]
    t("D2-fix2: card.name≠label → kind сохранён ровно один раз",
      out_cap and out_cap.get("kind") == "clarify"
      and len(labs_cap) == 2
      and all(CARD_NAME in lb for lb in labs_cap)
      and all(lb.count("(") == 1 and lb.count(")") == 1 for lb in labs_cap)
      and any("(документ)" in lb for lb in labs_cap)
      and any("регистр" in lb for lb in labs_cap)
      and not any(lb.count("документ") > 1 for lb in labs_cap),
      labs_cap)

    # --- D2-fix3: named узкий ∧ peer-SQL fail → leader, не R6 ---
    # allowed=['accumulationregister'], leader того же kind → пиров 0;
    # peer-SQL при RuntimeError: узкий named → leader (п.21; кейс: R6 здесь лишний).
    peer_spy = {"n": 0}
    base_fail = _psql_router(
        tables_both, cards_both, fail_peer=True)

    def psql_named_fail(q):
        qs = " ".join(str(q).lower().split())
        if "<>" in qs and "search_tables" in qs:
            peer_spy["n"] += 1
        return base_fail(q)

    z["ambiguous_labels"] = lambda: frozenset({LABEL_NORM})
    z["psql"] = psql_named_fail
    z["wiki_hybrid_pool"] = lambda q, intent=None: [
        cards_both.get(REG) or {"src_table": REG, "name": LABEL}]
    z["wiki_batch_verify"] = _batch_verify_leader(REG)
    z["wiki_leader_post_verify"] = lambda *a, **k: True
    diag_nf = {}
    out_nf = z["try_wiki_hybrid_entity_pick"](
        "по регистру накопления реализация тмц", {}, diag_nf, None, 0.0,
        by={}, match="", preds=["doc_date >= DATE '2026-09-01'"])
    t("D2-fix3: named узкий ∧ peer-SQL fail → picked=[leader], не R6",
      out_nf and out_nf.get("picked") == [REG]
      and not (out_nf.get("diag") or {}).get("wiki_homonym_peer_check")
      and peer_spy["n"] == 0,
      (out_nf, peer_spy, diag_nf))

    # --- D2-fix4: NBSP/таб ≡ обычный пробел в peer/count SQL ---
    # Python "".join(s.lower().split()) съедает любой unicode-пробел;
    # без той же нормы в SQL: count=0 → silent leader.
    LABEL_NBSP = "Реализация\u00a0ТМЦ"
    LABEL_TAB = "Реализация\tТМЦ"
    tables_nbsp = {DOC: LABEL_NBSP, REG: LABEL_NBSP}
    cards_nbsp = {
        DOC: {"src_table": DOC, "name": LABEL_NBSP},
        REG: {"src_table": REG, "name": LABEL_NBSP},
    }
    out_nbsp, _ = _run_leader_pick(
        z, DOC, tables=tables_nbsp, cards=cards_nbsp,
        ambig=[LABEL_NORM])
    t("D2-fix4: оба пира с NBSP → clarify 2",
      out_nbsp and out_nbsp.get("kind") == "clarify"
      and len(out_nbsp.get("options") or []) == 2,
      out_nbsp)

    tables_mix = {DOC: LABEL_NBSP, REG: LABEL}  # NBSP vs U+0020
    cards_mix = {
        DOC: {"src_table": DOC, "name": LABEL_NBSP},
        REG: {"src_table": REG, "name": LABEL},
    }
    out_mix, _ = _run_leader_pick(
        z, DOC, tables=tables_mix, cards=cards_mix,
        ambig=[LABEL_NORM])
    t("D2-fix4: смешанный NBSP/пробел → clarify 2 (эквивалентны)",
      out_mix and out_mix.get("kind") == "clarify"
      and len(out_mix.get("options") or []) == 2,
      out_mix)

    tables_tab = {DOC: LABEL_TAB, REG: LABEL}
    cards_tab = {
        DOC: {"src_table": DOC, "name": LABEL_TAB},
        REG: {"src_table": REG, "name": LABEL},
    }
    out_tab, _ = _run_leader_pick(
        z, DOC, tables=tables_tab, cards=cards_tab,
        ambig=[LABEL_NORM])
    t("D2-fix4: таб/пробел → clarify 2 (эквивалентны)",
      out_tab and out_tab.get("kind") == "clarify"
      and len(out_tab.get("options") or []) == 2,
      out_tab)

    z21src = Z21.read_text(encoding="utf-8")
    t("D2-fix4: count/peer SQL = regexp_replace \\s|\\p{Z} (не replace space)",
      "regexp_replace(lower(coalesce(label, '')), '\\\\s|\\\\p{Z}', '', 'g')"
      in z21src
      and "lower(replace(label,' ',''))" not in z21src
      and "lower(replace(coalesce(label, ''), ' ', ''))" not in z21src,
      "sql-norm missing or old replace remains")

    print()
    total = PASS + len(FAIL)
    if FAIL:
        print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
        return 1
    print("%s/0 зелёные" % PASS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
