#!/usr/bin/env python3
"""Оффлайн-замок Э6: $metadata в packet_config — через read_text, не open.

Без сети и без БД. Мок _rows как test_packet_config / test_changed_sources_lock:
статический grep исходника + форма SQL + поведение при подмене.

Прогон: python3 ubuntu/packet/test_packet_metadata_readtext.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import packet_config as PC  # noqa: E402

FAILS: list[str] = []
SRC = open(PC.__file__, encoding="utf-8").read()


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}"
          + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# (а) статический grep: нет open(…$metadata…) чтения файла данных
open_meta = re.findall(
    r"open\s*\([^)]*\$metadata[^)]*\)",
    SRC,
)
# open через переменную snap/path, где рядом join(..., "$metadata")
open_snap_blocks = re.findall(
    r"with\s+open\s*\(\s*snap\b[^)]*\)|"
    r"open\s*\(\s*snap\b|"
    r"open\s*\(\s*_meta_snap_path|"
    r"with\s+open\s*\([^)]*PACKET_META_DIR",
    SRC,
)
check("а: нет open(...$metadata...)", not open_meta, repr(open_meta))
check("а: нет open(snap)/open(PACKET_META_DIR) для снимка",
      not open_snap_blocks, repr(open_snap_blocks))
# чтение снимка только через read_text в SQL
check("б: SQL содержит read_text",
      "read_text(" in SRC and "/* metadata */" in SRC
      and "_metadata_sql" in SRC)
check("б: якорь metadata и regexp EntityType как у corpus_build",
      "regexp_extract_all" in SRC
      and "<EntityType" in SRC
      and "<EntitySet" in SRC)

# (в) замок падает, если вернуть open: эмулируем «плохой» исходник
bad = SRC.replace(
    "props, sets = _load_metadata(dsn, snap)",
    'with open(snap, encoding="utf-8") as f:\n'
    "        props = _props_by_type(f.read()); sets = []",
    1,
)
bad_opens = re.findall(r"open\s*\(\s*snap\b", bad)
check("в: регрессия open(snap) ловится grep-ом замка",
      bool(bad_opens), "подмена не создала open(snap)")

# мок psql: _metadata_sql → _meta_from_rows без движка
META_XML = """<edmx:Edmx><Schema>
<EntityType Name="Catalog_X"><Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Name" Type="Edm.String"/></EntityType>
<EntityType Name="Catalog_Bin"><Property Name="Ref_Key" Type="Edm.String"/>
<Property Name="Blob" Type="Edm.Stream"/>
<Property Name="Blob_Base64Data" Type="Edm.String"/></EntityType>
<EntityContainer>
<EntitySet Name="Catalog_X" EntityType="Catalog_X"/>
<EntitySet Name="Catalog_Bin" EntityType="Catalog_Bin"/>
</EntityContainer>
</Schema></edmx:Edmx>"""

with tempfile.TemporaryDirectory() as tmp:
    snap = os.path.join(tmp, "$metadata")
    with open(snap, "w", encoding="utf-8") as f:
        f.write(META_XML)
    sql = PC._metadata_sql(snap)
    check("мок: SQL несёт путь снимка и read_text",
          "read_text(" in sql and snap.replace("'", "''") in sql
          and "/* metadata */" in sql)

    # эмуляция ответа движка = тот же разбор, что FakeDB в test_packet_config
    props_py = PC._props_by_type(META_XML)
    sets_py = PC._entity_sets(META_XML)
    fake_rows = []
    for ent, pairs in props_py.items():
        for prop, edm in pairs:
            fake_rows.append(("prop", ent, prop, edm, ""))
    for es in sets_py:
        fake_rows.append(("set", "", "", "", es))
    props_sql, sets_sql = PC._meta_from_rows(fake_rows)
    check("мок: props бит-в-бит с Python-regex",
          props_sql == props_py, repr(props_sql))
    check("мок: EntitySet бит-в-бит",
          sets_sql == sets_py, repr(sets_sql))
    check("мок: only_binary на разобранных props",
          PC._only_binary(props_sql, "Catalog_Bin")
          and not PC._only_binary(props_sql, "Catalog_X"))

    # _read_sources через мок _rows
    calls: list[str] = []

    def fake_rows_fn(dsn, sql):
        calls.append(sql)
        if "/* tables */" in sql:
            return []
        if "/* contour */" in sql:
            return [("Catalog_X", "keep"), ("Catalog_Bin", "keep")]
        if "/* metadata */" in sql:
            return fake_rows
        raise RuntimeError(sql[:60])

    real = PC._rows
    PC._rows = fake_rows_fn
    PC.PACKET_META_DIR = tmp
    # snap path = PACKET_META_DIR/base/$metadata → base=""
    # _meta_snap_path("b") = tmp/b/$metadata — положим туда
    bdir = os.path.join(tmp, "b")
    os.makedirs(bdir)
    os.replace(snap, os.path.join(bdir, "$metadata"))
    try:
        rows, props, sets = PC._read_sources("fake", "b")
    finally:
        PC._rows = real
    check("мок _read_sources: metadata через _rows, не open",
          props == props_py and sets == sets_py
          and any("/* metadata */" in c and "read_text(" in c for c in calls),
          repr(calls)[:200])
    check("мок _read_sources: contour+tables+metadata",
          sum("/* tables */" in c for c in calls) == 1
          and sum("/* contour */" in c for c in calls) == 1
          and sum("/* metadata */" in c for c in calls) == 1)

n_ok = 11 - len(FAILS)
if FAILS:
    print("FAIL %d/%d: %s" % (len(FAILS), 11, ", ".join(FAILS)))
    sys.exit(1)
print("OK %d/%d" % (n_ok, 11))
