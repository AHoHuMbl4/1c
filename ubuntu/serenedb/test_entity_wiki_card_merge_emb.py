#!/usr/bin/env python3
"""Оффлайн-замок: entity_card / wiki_card — emb живёт при неизменном тексте.

- quantities/axes/measures вне текста под вектор;
- смена только агрегата → emb цел;
- смена label/about → emb=NULL у затронутых;
- форма card (старый card держал quantities) → xfer;
- повторный прогон → no-op.

Запуск: python3 test_entity_wiki_card_merge_emb.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ENT = os.path.join(ROOT, "entity_card_build.sql")
WIKI = os.path.join(ROOT, "wiki_card_build.sql")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail)[:200] if detail else "")


def card_stable(label, aliases="", about=""):
    parts = [label]
    if aliases:
        parts.append(aliases)
    if about:
        parts.append(about)
    return " | ".join(parts)


def wiki_stable(name, description=""):
    parts = [name]
    if description:
        parts.append(description)
    return " | ".join(parts)


def entity_tick(stored, incoming):
    """stored/incoming: src -> dict(label,aliases,about,quantities,attrs,card,emb).
    Возвращает (new_store, n_null_introduced_on_prior_emb)."""
    xfer = set()
    for src, s in incoming.items():
        if src not in stored or stored[src].get("emb") is None:
            continue
        old = stored[src]
        if old["card"] == s["card"]:
            continue
        if old["card"] in (
            card_stable(s["card"], old.get("quantities", "")),
            " | ".join(p for p in [s["card"], old.get("quantities", "")] if p),
            " | ".join(p for p in [s["card"], s.get("quantities", "")] if p),
        ) or s["card"] == card_stable(
            old.get("label", ""), old.get("aliases", ""), old.get("about", "")
        ):
            # форма: old card = new_stable | quantities
            if old["card"] == " | ".join(
                p for p in [s["card"], old.get("quantities") or ""] if p != ""
            ) or old["card"] == " | ".join(
                p for p in [s["card"], s.get("quantities") or ""] if p != ""
            ) or s["card"] == card_stable(
                old.get("label", ""), old.get("aliases", ""), old.get("about", "")
            ):
                xfer.add(src)

    out = {}
    nulls = 0
    for src, s in incoming.items():
        prev = stored.get(src)
        emb = None
        if prev and prev.get("card") == s["card"]:
            emb = prev.get("emb")
        elif src in xfer:
            emb = prev.get("emb")
        elif prev and prev.get("emb") is not None and prev.get("card") != s["card"]:
            nulls += 1
            emb = None
        row = dict(s)
        row["emb"] = emb
        out[src] = row
    return out, nulls, xfer


# --- entity: неизменный источник ---
st = {
    "e1": {
        "label": "Реализация",
        "aliases": "продажа",
        "about": "отгрузка",
        "quantities": "Сумма, Количество",
        "attrs": "Ref_Key",
        "card": card_stable("Реализация", "продажа", "отгрузка"),
        "emb": [0.1],
    }
}
inc = {
    "e1": {
        "label": "Реализация",
        "aliases": "продажа",
        "about": "отгрузка",
        "quantities": "Сумма, Количество, Вес",  # агрегат вырос
        "attrs": "Ref_Key, Date",
        "card": card_stable("Реализация", "продажа", "отгрузка"),
    }
}
out, nulls, xfer = entity_tick(st, inc)
t("ent a: quantities change keeps emb", out["e1"]["emb"] == [0.1])
t("ent a: zero nulls", nulls == 0)

# --- entity: смена about ---
inc2 = {
    "e1": {
        "label": "Реализация",
        "aliases": "продажа",
        "about": "другое",
        "quantities": "Сумма",
        "attrs": "Ref_Key",
        "card": card_stable("Реализация", "продажа", "другое"),
    }
}
out2, nulls2, _ = entity_tick(out, inc2)
t("ent b: about change nulls emb", out2["e1"]["emb"] is None)
t("ent b: exactly one null", nulls2 == 1)

# --- entity: rerun ---
out3, nulls3, _ = entity_tick(out2, inc2)
t("ent c: rerun no-op emb", out3["e1"]["emb"] is None and nulls3 == 0)

# --- entity: форма old card с quantities → xfer ---
st_f = {
    "e1": {
        "label": "Реализация",
        "aliases": "продажа",
        "about": "отгрузка",
        "quantities": "Сумма",
        "attrs": "",
        "card": "Реализация | продажа | отгрузка | Сумма",
        "emb": [0.5],
    }
}
inc_f = {
    "e1": {
        "label": "Реализация",
        "aliases": "продажа",
        "about": "отгрузка",
        "quantities": "Сумма",
        "attrs": "",
        "card": card_stable("Реализация", "продажа", "отгрузка"),
    }
}
out_f, nulls_f, xfer_f = entity_tick(st_f, inc_f)
t("ent d: form xfer keeps emb", out_f["e1"]["emb"] == [0.5])
t("ent d: in xfer", "e1" in xfer_f)
t("ent d: zero nulls", nulls_f == 0)

# --- wiki: axes/measures вне card_text ---
def wiki_tick(stored, incoming):
    xfer = set()
    for src, s in incoming.items():
        if src not in stored or stored[src].get("emb") is None:
            continue
        old = stored[src]
        if old["card_text"] == s["card_text"]:
            continue
        old_form = " | ".join(
            p
            for p in [
                s["card_text"],
                old.get("axes") or None,
                old.get("measures") or None,
            ]
            if p
        )
        if old["card_text"] == old_form or s["card_text"] == wiki_stable(
            old.get("name", ""), old.get("description", "")
        ):
            xfer.add(src)
    out = {}
    nulls = 0
    for src, s in incoming.items():
        prev = stored.get(src)
        emb = None
        if prev and prev.get("card_text") == s["card_text"]:
            emb = prev.get("emb")
        elif src in xfer:
            emb = prev.get("emb")
        elif prev and prev.get("emb") is not None:
            nulls += 1
        row = dict(s)
        row["emb"] = emb
        out[src] = row
    return out, nulls, xfer


wst = {
    "w1": {
        "name": "Склад",
        "description": "места хранения",
        "axes": "a -> b",
        "measures": "qty: остаток",
        "card_text": wiki_stable("Склад", "места хранения"),
        "emb": [0.3],
    }
}
winc = {
    "w1": {
        "name": "Склад",
        "description": "места хранения",
        "axes": "a -> b, c -> d",
        "measures": "qty: остаток; sum: сумма",
        "card_text": wiki_stable("Склад", "места хранения"),
    }
}
wout, wn, _ = wiki_tick(wst, winc)
t("wiki a: axes/measures change keeps emb", wout["w1"]["emb"] == [0.3])
t("wiki a: zero nulls", wn == 0)

winc2 = {
    "w1": {
        "name": "Склад",
        "description": "новое описание",
        "axes": "a -> b",
        "measures": "qty: остаток",
        "card_text": wiki_stable("Склад", "новое описание"),
    }
}
wout2, wn2, _ = wiki_tick(wout, winc2)
t("wiki b: description change nulls emb", wout2["w1"]["emb"] is None)
t("wiki b: one null", wn2 == 1)
wout3, wn3, _ = wiki_tick(wout2, winc2)
t("wiki c: rerun no-op", wn3 == 0 and wout3["w1"]["emb"] is None)

# --- SQL grep entity ---
ent = open(ENT, encoding="utf-8").read()
# card concat без quantities: нет coalesce(q.quantities в concat_ws card
card_assign = re.search(
    r"concat_ws\(' \| ', t\.label, coalesce\(a\.aliases, ''\),\s*"
    r"coalesce\(a\.best_used_for, ''\)\) AS card",
    ent,
)
t("ent SQL: card without quantities", card_assign is not None)
t("ent SQL: quantities column remains", "AS quantities" in ent)
t("ent SQL: emb xfer table", "tmp_entity_card_emb_xfer" in ent)
t("ent SQL: batch xfer 1000", "tmp_entity_card_emb_xfer_n" in ent)
t("ent SQL: MERGE not replace", "MERGE INTO search_entity_card" in ent)
t("ent SQL: no CREATE OR REPLACE search_entity_card",
  "CREATE OR REPLACE TABLE search_entity_card" not in ent)

# --- SQL grep wiki ---
wiki = open(WIKI, encoding="utf-8").read()
wiki_card = re.search(
    r"concat_ws\(' \| ', t\.label, nullif\(w\.body, ''\)\) AS card_text",
    wiki,
)
t("wiki SQL: card_text without axes/measures", wiki_card is not None)
t("wiki SQL: axes column remains", "AS axes" in wiki)
t("wiki SQL: measures column remains", "AS measures" in wiki)
t("wiki SQL: emb xfer", "tmp_wiki_card_emb_xfer" in wiki)
t("wiki SQL: batch 1000", "tmp_wiki_card_emb_xfer_n" in wiki)
t("wiki SQL: MERGE", "MERGE INTO search_wiki_entity_card" in wiki)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
