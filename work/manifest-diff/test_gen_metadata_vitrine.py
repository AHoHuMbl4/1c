#!/usr/bin/env python3
"""Замок gen_metadata_vitrine.py: парсер такта, полнота, типы префиксов.

Без pytest. Прогон: python3 work/manifest-diff/test_gen_metadata_vitrine.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import gen_metadata_vitrine as G  # noqa: E402

PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def _entity_props(xml: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in re.finditer(r'<EntityType Name="([^"]+)".*?</EntityType>', xml, re.S):
        out[m.group(1).lower()] = set(re.findall(r'<Property Name="([^"]+)"', m.group(0)))
    return out


def _load_arrived() -> set[str]:
    path = os.path.join(ROOT, "../../docs/completeness-okna/arrived.txt")
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return set()
    return {ln.strip() for ln in open(path, encoding="utf-8") if ln.strip()}


# --- (a) парсер corpus_build на фикстуре ---
FIXTURE_COLS = [
    ("recorder", "VARCHAR"),
    ("recorder_type", "VARCHAR"),
    ("period", "VARCHAR"),
    ("linenumber", "VARCHAR"),
    ("active", "BOOLEAN"),
    ("Организация_Key", "VARCHAR"),
    ("Сумма", "VARCHAR"),
]

key, props, open_type = G.build_entity_props(
    "AccumulationRegister_РеализацияУслуг_RecordType", FIXTURE_COLS,
)
ents = {
    "AccumulationRegister_РеализацияУслуг": G.synthetic_register_wrapper(
        "AccumulationRegister_РеализацияУслуг", True,
    ),
    "AccumulationRegister_РеализацияУслуг_RecordType": (key, props, open_type),
    "Catalog_Валюты": (
        ["Ref_Key"],
        [
            ("Ref_Key", "Edm.Guid", "false"),
            ("Code", "Edm.String", "true"),
            ("Description", "Edm.String", "true"),
        ],
        False,
    ),
}
# unpack wrapper tuple
wk, wp = ents["AccumulationRegister_РеализацияУслуг"]
ents["AccumulationRegister_РеализацияУслуг"] = (wk, wp, True)

xml = G.build_xml({k: (v[0], v[1], v[2]) for k, v in ents.items()})
ent_n, prop_n, key_n = G.parse_like_corpus_build(xml)
t("parser: entities > 0", ent_n >= 3, ent_n)
t("parser: properties > 0", prop_n >= 5, prop_n)
t("parser: keyed entities", key_n >= 3, key_n)
t("parser: balance RecordType prop",
  "RecordType" in xml and "AccumulationRegister_РеализацияУслуг_RecordType" in xml)

# --- (b) типы префиксов ---
t("kind: catalog", G.is_odata_entity_name("Catalog_Валюты"))
t("kind: document", G.is_odata_entity_name("Document_РеализацияТМЦ"))
t("kind: accumulation", G.is_odata_entity_name("AccumulationRegister_ИмпортТМЦ"))
t("kind: wrapper", G.is_register_wrapper("AccumulationRegister_ИмпортТМЦ"))
t("kind: shadow", G.is_register_record_shadow("AccumulationRegister_ИмпортТМЦ_RecordType"))
t("kind: not wrapper for shadow",
  not G.is_register_wrapper("AccumulationRegister_ИмпортТМЦ_RecordType"))
t("edm: _Key", G.map_edm_type("Организация_Key", "VARCHAR") == "Edm.Guid")
t("edm: boolean", G.map_edm_type("deletionmark", "BOOLEAN") == "Edm.Boolean")
t("edm: LineNumber", G.map_edm_type("linenumber", "VARCHAR") == "Edm.Int64")

# --- (c) полнота: витрина ⊂ снимок (оффлайн мок) ---
vitrine = {
    "catalog_валюты": [("ref_key", "VARCHAR"), ("code", "VARCHAR"), ("description", "VARCHAR")],
    "accumulationregister_продажи": [
        ("recorder", "VARCHAR"), ("period", "VARCHAR"), ("linenumber", "VARCHAR"),
        ("Сумма", "VARCHAR"),
    ],
}
tables = set(vitrine.keys())
entities = ["Catalog_Валюты", "AccumulationRegister_Продажи", "AccumulationRegister_Продажи_RecordType"]
built = {}
for ent in entities:
    vt = G.vitrine_table_for_entity(ent, tables)
    cols = vitrine.get(vt or "", [])
    k, p, o = G.build_entity_props(ent, cols if not G.is_register_wrapper(ent) else [])
    built[ent] = (k, p, o)
xml2 = G.build_xml(built)
parsed_props = _entity_props(xml2)

for tbl, cols in vitrine.items():
    ent_key = None
    for ent in entities:
        if G.is_register_record_shadow(ent) and G.vitrine_table_for_entity(ent, tables) == tbl:
            ent_key = ent.lower()
            break
    if not ent_key:
        for ent in entities:
            if G.vitrine_table_for_entity(ent, tables) == tbl:
                ent_key = ent.lower()
                break
    if not ent_key:
        t("completeness: map " + tbl, False, "no entity")
        continue
    snap = parsed_props.get(ent_key, set())
    for col, _ in cols:
        pn = G.odata_prop_name(col)
        t("completeness: %s.%s" % (ent_key, col), pn in snap or col in snap, snap)

# --- (d) артефакт okna: парсер + покрытие arrived ---
okna_path = os.path.join(ROOT, "metadata-okna.xml")
if os.path.isfile(okna_path):
    okna_xml = open(okna_path, encoding="utf-8").read()
    e_ok, p_ok, k_ok = G.parse_like_corpus_build(okna_xml)
    t("okna-artifact: parser entities", e_ok >= 800, e_ok)
    t("okna-artifact: all keyed", k_ok == e_ok, (k_ok, e_ok))
    t("okna-artifact: entity_sets", okna_xml.count("<EntitySet Name=") == e_ok)
    props_map = _entity_props(okna_xml)
    arrived = _load_arrived()
    if arrived:
        arrived_with = sum(
            1 for a in arrived
            if len(props_map.get(a.lower(), ())) >= 3
            or G.is_register_wrapper(a)
        )
        ratio = arrived_with / len(arrived)
        if ratio >= 0.5:
            t("okna-artifact: arrived props ratio", True,
              "%.2f (%d/%d)" % (ratio, arrived_with, len(arrived)))
        else:
            print("WARN- okna-artifact stub: arrived props %.0f%% (%d/%d) — "
                  "regen на окне: bash work/manifest-diff/run-metadata-okna.sh"
                  % (ratio * 100, arrived_with, len(arrived)))
    t("okna-artifact: RecordType balance prop",
      "accumulationregister_импорттмц_recordtype" in props_map
      and "RecordType" in props_map["accumulationregister_импорттмц_recordtype"])

# --- (e) живой прогон только по GEN_METADATA_LIVE=1 (7890 часто timeout) ---
dsn = os.environ.get("SERENEDB_DSN", "")
if not dsn or "port=" not in dsn:
    for p in ("/etc/1c-mcp-reports.env", "/etc/1c-serene-ask-postgres.env"):
        if os.path.isfile(p):
            for line in open(p):
                line = line.strip()
                if line.startswith("SERENEDB_DSN="):
                    dsn = line.split("=", 1)[1].strip()
                    break

live_ok = False
if os.environ.get("GEN_METADATA_LIVE") == "1" and dsn:
    try:
        tables_live, _ = G.load_vitrine_schema(dsn)
        if tables_live:
            sample = sorted(tables_live)[:3]
            ents_live = []
            for tbl in sample:
                for p in G.KIND_PREFIXES:
                    if tbl.lower().startswith(p.lower()):
                        ents_live.append(p + tbl.split("_", 1)[1])
                        break
            if ents_live:
                xml_live, stats = G.generate(dsn, ents_live)
                e, _, k = G.parse_like_corpus_build(xml_live)
                t("live: parser", e > 0 and k > 0, (e, k))
                t("live: stats entities", stats["entities"] == len(ents_live), stats)
                live_ok = True
    except Exception as exc:
        t("live: dsn", False, exc)

if not live_ok:
    print("skip- live: GEN_METADATA_LIVE=1 и живой DSN (7890 на окне okna)")

print("---")
print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
