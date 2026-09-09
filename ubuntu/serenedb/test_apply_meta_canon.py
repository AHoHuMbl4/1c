#!/usr/bin/env python3
"""Оффлайн: нормализация регистра колонок full-загрузки по $metadata (инцидент 09.09).

Модель: _meta_canon строит lower→Name из Property-имён снимка (коллизии
пропускаются с журналом); _full_sql перечисляет колонки с алиасами canon[lower(h)]
в КАЖДОЙ части UNION ALL; без канона/заголовка — прежняя форма SELECT *.

Запуск: python3 test_apply_meta_canon.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "packet"))
import packet_apply as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


# --- канон из снимка $metadata (tmp-файл, реальный парсер) ---
xml = ('<edmx:Edmx xmlns:edmx="http://x"><DataServices><Schema>'
       '<EntityType Name="Cat"><Property Name="Ref_Key" Type="Edm.String"/>'
       '<Property Name="DataVersion" Type="Edm.String"/>'
       '<Property Name="Code" Type="Edm.String"/></EntityType>'
       '<EntityType Name="Doc"><Property Name="Ref_Key" Type="Edm.String"/>'
       '<Property Name="LineNumber" Type="Edm.Int32"/></EntityType></Schema>'
       '</DataServices></edmx:Edmx>')
with tempfile.TemporaryDirectory() as d:
    base = "probe-base"
    bd = os.path.join(d, base)
    os.makedirs(bd)
    with open(os.path.join(bd, "$metadata"), "w", encoding="utf-8") as f:
        f.write(xml)
    A._META_CANON_CACHE.clear()
    A.PACKET_META_DIR = d
    canon = A._meta_canon(base)
    t("канон: lower→Name построен", canon.get("ref_key") == "Ref_Key"
      and canon.get("dataversion") == "DataVersion")
    t("канон: посторонних имён нет", "description" not in canon)
    A._META_CANON_CACHE.clear()
    t("канон: нет снимка — пуст (fail-open + журнал)",
      A._meta_canon("no-such-base") == {})

# --- алиасы в _full_sql ---
canon = {"ref_key": "Ref_Key", "dataversion": "DataVersion", "code": "Code"}
hdr = ["ref_key", "dataversion", "code", "Description"]
src = ("SELECT * FROM read_csv('/x/a.csv', o)\nUNION ALL\n"
       "SELECT * FROM read_csv('/x/b.csv', o)")
out = A._full_sql("t", src, header=hdr, canon=canon)
t("full: алиас по канону", '"ref_key" AS "Ref_Key"' in out)
t("full: алиасы в КАЖДОЙ части UNION", out.count(' AS "DataVersion"') == 2)
t("full: колонка без расхождения — без алиаса", '"Description"' in out
  and 'Description AS' not in out)
t("full: голых SELECT * не осталось", "SELECT * FROM" not in out)
t("full: DROP/CREATE/GRANT форма на месте",
      out.startswith('DROP TABLE IF EXISTS "t"') and "GRANT SELECT" in out)
t("full: без канона — прежняя SELECT DISTINCT *",
      "SELECT DISTINCT *" in A._full_sql("t", src))
t("full: без header — прежняя форма",
      "SELECT DISTINCT *" in A._full_sql("t", src, canon=canon))

# --- статика: проводка в вызове ---
src_apply = open(os.path.join(ROOT, "..", "packet", "packet_apply.py"),
                 encoding="utf-8").read()
t("apply: вызов несёт header+canon",
      "header=_csv_header(chunk_paths[0])," in src_apply
      and "canon=_meta_canon(base_id)" in src_apply)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
