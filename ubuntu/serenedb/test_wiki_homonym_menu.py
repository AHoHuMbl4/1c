#!/usr/bin/env python3
"""S2-b: одноимённые прочтения разных OData-kind → clarify, не silent leader.

Оффлайн, без БД/сети. Мок паспортов + wiki_outcome_from_verify.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Z21 = ROOT / "ask" / "z21_wiki_choice.py"

PASS, FAIL = 0, []


def t(name: str, cond: bool, detail="") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def load_z21():
    import types
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

    ns = {
        "__name__": "z21_wiki_choice",
        "__file__": str(Z21),
        "rank_intent_from": lambda *a, **k: False,
        "_intent_text": lambda x: (
            x[0] if isinstance(x, (list, tuple)) and x else x or "") or "",
        "kind_word": lambda s: (
            "документ" if str(s).startswith("document_")
            else "регистр накопления" if str(s).startswith("accumulationregister_")
            else "справочник"),
        "human_table_label": _human,
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
        "mk_opts": lambda srcs, lab_by, *a, **k: [
            {"label": lab_by.get(s) or _human(s), "src": s} for s in srcs],
        "wiki_menu_captions": lambda opts, **k: opts,
        "wiki_captions_map_from_cards": lambda cards: {},
        "readings_menu": _readings_menu,
        "wiki_validate_leader_axes": lambda leader, intent: True,
        "_diag_pack": lambda d, **k: d,
        "register_zone": lambda *a, **k: None,
        "apply_bindings": lambda g: None,
    }
    for k, v in vars(real_imp).items():
        if k.startswith("_") and k not in ("__builtins__",):
            continue
        ns.setdefault(k, v)
    exec(compile(src, str(Z21), "exec"), ns)
    # validate axes always ok in this lock
    ns["wiki_validate_leader_axes"] = lambda leader, intent: True
    return ns


def _verdicts(fits):
    return [{"index": i + 1, "fit": f} for i, f in enumerate(fits)]


def main():
    z = load_z21()
    outcome = z["wiki_outcome_from_verify"]
    peers_fn = z["wiki_homonym_kind_peers"]

    # 1) same name, different kinds, yes/no → clarify
    p_same = [
        {"src_table": "document_реализациятмц", "name": "Реализация ТМЦ"},
        {"src_table": "accumulationregister_реализациятмц",
         "name": "Реализация ТМЦ"},
    ]
    out1 = outcome(_verdicts(["yes", "no"]), p_same, {})
    t("same name different kind → clarify",
      out1.get("outcome") == "clarify" and len(out1.get("candidates") or []) == 2,
      out1)
    t("diag wiki_homonym_tie",
      (out1.get("diag") or {}).get("wiki_homonym_tie")
      and len((out1.get("diag") or {}).get("wiki_homonym_tie")) == 2)

    # 2) different names → leader (В4 regression)
    p_diff = [
        {"src_table": "catalog_a", "name": "Альфа"},
        {"src_table": "catalog_b", "name": "Бета"},
    ]
    out2 = outcome(_verdicts(["yes", "no"]), p_diff, {})
    t("different names → leader",
      out2.get("outcome") == "leader" and out2.get("leader") == "catalog_a",
      out2)

    # 3) same stem, empty/diverged names, different kinds → clarify
    p_stem = [
        {"src_table": "document_FooBar", "name": ""},
        {"src_table": "accumulationregister_FooBar", "name": "другие слова"},
    ]
    out3 = outcome(_verdicts(["yes", "no"]), p_stem, {})
    t("same stem different kind → clarify",
      out3.get("outcome") == "clarify", out3)

    # 4) same name, same kind ×2 → leader (вне скоупа S2-b)
    p_same_kind = [
        {"src_table": "catalog_one", "name": "Товар"},
        {"src_table": "catalog_two", "name": "Товар"},
    ]
    out4 = outcome(_verdicts(["yes", "no"]), p_same_kind, {})
    t("same name same kind → leader",
      out4.get("outcome") == "leader", out4)

    # 5) peers helper: focus with peer
    pr = peers_fn(p_same, "document_реализациятмц")
    t("peers ≥2", len(pr) == 2, pr)
    t("peers empty for sole pool",
      peers_fn(p_same[:1], "document_реализациятмц") == [])

    # 6) labels path: mk_opts + kind distinguisher markers exist in z20
    z20 = (ROOT / "ask" / "z20_ask_main_http.py").read_text(encoding="utf-8")
    t("z20: label_with_kind / disambiguate_labels живы",
      "def label_with_kind" in z20 and "def disambiguate_labels" in z20)
    t("z21: readings_menu на clarify hybrid",
      "readings_menu(" in Z21.read_text(encoding="utf-8"))
    t("z21: wiki_homonym_kind_peers жив",
      "def wiki_homonym_kind_peers" in Z21.read_text(encoding="utf-8"))

    print()
    total = PASS + len(FAIL)
    if FAIL:
        print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
        return 1
    print("%s/0 зелёные" % PASS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
