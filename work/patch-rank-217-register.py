#!/usr/bin/env python3
"""Rank: убрать {total}/217.10, детерминированный топ-1; регистр вместо табчастей."""
import pathlib

ASK = pathlib.Path("/srv/1c/ubuntu/serenedb/serene_ask.py")
TEST = pathlib.Path("/srv/1c/ubuntu/serenedb/test_rank_axis_anchor.py")


def replace_once(text, old, new, label):
    if old not in text:
        if new.split("\n", 1)[0].strip()[:40] in text:
            print("skip:", label)
            return text
        raise SystemExit("missing: %s" % label)
    return text.replace(old, new, 1)


def patch_prefer():
    text = ASK.read_text(encoding="utf-8")
    old = '''    elif not tops:
        doc_parents = []
        for c in cands:
            p = parent_by.get(c) or ""
            if p and p not in doc_parents:
                doc_parents.append(p)
        reg_doc_parents = [p for p in doc_parents
                           if str(p).startswith(("accumulationregister_", "document_"))]
        ordered = lifted + reg_doc_parents + list(cands)
    else:
        ordered = tops + children
    out, seen = [], set()
    for c in ordered:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out'''
    new = '''    elif not tops:
        ordered = lifted + list(cands)
    else:
        ordered = tops + children
    out, seen = [], set()
    for c in ordered:
        if c not in seen:
            seen.add(c)
            out.append(c)
    if lifted and docs:
        drop = {c for c in out
                if str(c).startswith("document_") and parent_by.get(c) in docs}
        if drop:
            out = [c for c in out if c not in drop]
        front = lifted + [c for c in out if c not in lifted]
        out = front
    return out'''
    text = replace_once(text, old, new, "prefer drop tabparts")
    ASK.write_text(text, encoding="utf-8")


def patch_rank_leader_fn():
    text = ASK.read_text(encoding="utf-8")
    anchor = "def product_axis_pref(cols):"
    fn = '''

def rank_leader_answer_text(agg, measure_label=None):
    """Текст ответа топ-1 по первой группе (имя + value), без итога множества."""
    if not agg or agg.get("grain") != "group":
        return None
    gs = agg.get("groups") or []
    if not gs or not isinstance(gs[0], dict):
        return None
    nm = (gs[0].get("name") or "").strip()
    val = gs[0].get("value")
    if val is None:
        val = _group_leader(agg)
    if val is None:
        return None
    if nm:
        return "\u00ab%s\u00bb: %s" % (nm, _fmt_human(val))
    return _fmt_human(val)

'''
    if "def rank_leader_answer_text" not in text:
        text = text.replace(anchor, fn + anchor, 1)
    ASK.write_text(text, encoding="utf-8")


def patch_fill_figures():
    text = ASK.read_text(encoding="utf-8")
    old = '''    elif slot_mode == "rank":
        known.pop("leader", None)
        known.pop("count", None)
        for k in ("max", "min", "avg"):
            known.pop(k, None)'''
    new = '''    elif slot_mode == "rank":
        known.pop("leader", None)
        known.pop("count", None)
        _ng = (agg or {}).get("n_groups")
        _shown_g = len((agg or {}).get("groups") or [])
        if _ng is not None and _ng <= _shown_g:
            known.pop("sum", None)
        for k in ("max", "min", "avg"):
            known.pop(k, None)'''
    text = replace_once(text, old, new, "fill rank pop sum")
    ASK.write_text(text, encoding="utf-8")


def patch_compose_rows():
    text = ASK.read_text(encoding="utf-8")
    old = '''    payload = []
    shown = rows[:ROWS_TO_MODEL]'''
    new = '''    payload = []
    shown = rows[:ROWS_TO_MODEL]
    if slot_mode == "rank" and (agg or {}).get("grain") == "group":
        shown = []'''
    text = replace_once(text, old, new, "compose rank no row examples")
    ASK.write_text(text, encoding="utf-8")


def patch_compose_total():
    text = ASK.read_text(encoding="utf-8")
    old = '''        if slot_mode == "rank":
            body += ("\\n  sum (TOTAL of the whole matching set, not one group) "
                     "-> {total}")'''
    new = '''        if slot_mode == "rank":
            _ng = agg.get("n_groups")
            _shown_g = len(agg.get("groups") or [])
            if _ng is not None and _ng > _shown_g:
                body += ("\\n  sum (TOTAL of the whole matching set, not one group) "
                         "-> {total}")'''
    text = replace_once(text, old, new, "compose rank total only if truncated")
    ASK.write_text(text, encoding="utf-8")


def patch_gate():
    text = ASK.read_text(encoding="utf-8")
    old = '''        elif slot_mode == "rank" and group_grain:
            allow(agg.get("sum"))
            allow(agg.get("leader"))
            allow(agg.get("count"))
            allow(agg.get("count_amount"))
            allow(agg.get("n_groups"))
            for g in agg.get("groups") or []:
                allow(g.get("value"))
                allow(g.get("count"))
                allow(g.get("value2"))
                allow(g.get("count2"))
                if money:
                    allow(g.get("sum"))'''
    new = '''        elif slot_mode == "rank" and group_grain:
            allow(agg.get("leader"))
            allow(agg.get("count"))
            allow(agg.get("count_amount"))
            allow(agg.get("n_groups"))
            _ng = agg.get("n_groups")
            _shown_g = len(agg.get("groups") or [])
            if _ng is not None and _ng > _shown_g:
                allow(agg.get("sum"))
            for g in agg.get("groups") or []:
                allow(g.get("value"))
                allow(g.get("count"))
                allow(g.get("value2"))
                allow(g.get("count2"))
                allow(g.get("sum"))'''
    text = replace_once(text, old, new, "gate rank whitelist")
    ASK.write_text(text, encoding="utf-8")


def patch_compose_slot():
    text = ASK.read_text(encoding="utf-8")
    old = '''    elif slot_mode == "rank":
        if money and agg.get("sum") is not None:
            slots["sum"] = agg["sum"]
        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):'''
    new = '''    elif slot_mode == "rank":
        _ng = agg.get("n_groups")
        _shown_g = len(agg.get("groups") or [])
        if (money and agg.get("sum") is not None
                and _ng is not None and _ng > _shown_g):
            slots["sum"] = agg["sum"]
        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):'''
    text = replace_once(text, old, new, "compose_slot rank sum")
    ASK.write_text(text, encoding="utf-8")


def patch_deterministic():
    text = ASK.read_text(encoding="utf-8")
    old = '''    if not ok:
        sys.stderr.write("ask GATE: числа вне данных: %s\\n" % bad[:6])
        # Гейт отклонил формулировку модели. Числа при этом посчитаны базой и верны —'''
    new = '''    if not ok:
        sys.stderr.write("ask GATE: числа вне данных: %s\\n" % bad[:6])
        if (slot_mode == "rank" and (agg or {}).get("grain") == "group"
                and (agg.get("groups") or [])):
            _rank_txt = rank_leader_answer_text(agg, say_measure or measure)
            if _rank_txt:
                _ok_r, _bad_r = gate(_rank_txt, seen, agg, extra_vals, our_dates,
                                     money=money, slot_mode=slot_mode)
                if _ok_r:
                    _rank_txt = ensure_count_named(_rank_txt, agg, slot_mode)
                    _rank_txt = ensure_answer_passport(_rank_txt, _pass_frag)
                    diag["rank_deterministic"] = True
                    return {"partial": cut or None, "kind": "answer",
                            "text": _rank_txt, "sources": [src] if src else [],
                            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2))}
        # Гейт отклонил формулировку модели. Числа при этом посчитаны базой и верны —'''
    text = replace_once(text, old, new, "rank deterministic answer")
    ASK.write_text(text, encoding="utf-8")


def patch_fork_pool():
    text = ASK.read_text(encoding="utf-8")
    old = '''        _fork_pool = list(cands[:max(ARBITER_MAX * 4, 16)])
        try:'''
    new = '''        _fork_pool = prefer_entity_for_rank(
            list(cands[:max(ARBITER_MAX * 4, 16)]), intent, question)
        try:'''
    text = replace_once(text, old, new, "fork pool prefer")
    ASK.write_text(text, encoding="utf-8")


def patch_tests():
    text = TEST.read_text(encoding="utf-8")
    block = '''
# --- e82abb5 follow-up: 217.10 в rank-тексте, детерминированный топ-1 ---
AGG217 = {
    "count": 19, "sum": 217.10, "leader": 3.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "n_groups": 1,
    "groups": [{"name": "Prod X", "value": 3.0, "count": 19, "sum": 21.0}],
    "folders": 0, "count_amount": 19,
}
ROWS217 = A.serene_axis.group_rows(AGG217["groups"])
SEEN217 = A.rows_seen(ROWS217)
text217 = "Наибольшее количество — «Prod X»: {total}."
filled217, bad217 = A._fill_figures(text217, AGG217, [], True, slot_mode="rank")
t("rank fill: {total} не подставляет sum множества",
  "217" not in filled217.replace("\\u00a0", ""), filled217)
t("rank fill: g0 через rank_leader",
  "3" in (A.rank_leader_answer_text(AGG217) or ""))
ok217, bad217g = A.gate(
    A.rank_leader_answer_text(AGG217) or "", SEEN217, AGG217, [1], [],
    money=True, slot_mode="rank")
t("rank gate leader 3 проходит", ok217, bad217g)
ok217b, bad217b = A.gate(
    "лидер 217.10", SEEN217, AGG217, [1], [], money=True, slot_mode="rank")
t("rank gate 217.10 отвергнут", not ok217b and bad217b, bad217b)
t("rank gate bad217 str", bad217b and isinstance(bad217b[0], str), bad217b)

# --- prefer: три табчасти, регистр по written_by ---
def _fake_psql3(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",)]
    if "parent, written_by" in q:
        return [
            ("document_реализациятмц_номенклатура", "document_реализациятмц", ""),
            ("document_передачаврознице_номенклатура", "document_передачаврознице", ""),
            ("document_реализациятмц_массабрутто", "document_реализациятмц", ""),
        ]
    raise RuntimeError("no db")

_old3 = A.psql
A.psql = _fake_psql3
try:
    q3 = "какого товара больше всего продали за всё время?"
    c3 = [
        "document_реализациятмц_номенклатура",
        "document_передачаврознице_номенклатура",
        "document_реализациятмц_массабрутто",
    ]
    got3 = A.prefer_entity_for_rank(c3, intent_sale, q3)
    t("prefer 3 tabparts: регистр первый",
      got3 and got3[0] == "accumulationregister_реализациятмц", got3)
    t("prefer 3 tabparts: табчасти сняты",
      not [x for x in got3 if x.startswith("document_")], got3)
finally:
    A.psql = _old3

'''
    if "AGG217" not in text:
        text = text.replace(
            'print("\\n%d ok, %d fail" % (PASS, len(FAIL)))',
            block + '\nprint("\\n%d ok, %d fail" % (PASS, len(FAIL)))',
            1)
    TEST.write_text(text, encoding="utf-8")


def main():
    patch_rank_leader_fn()
    patch_prefer()
    patch_fill_figures()
    patch_compose_rows()
    patch_compose_total()
    patch_gate()
    patch_compose_slot()
    patch_deterministic()
    patch_fork_pool()
    patch_tests()
    print("patched ok")


if __name__ == "__main__":
    main()
