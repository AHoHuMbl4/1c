#!/usr/bin/env python3
"""Оффлайн: packet-синк не затирает search_changed_sources до rebuild."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from changed_sources_sql import changed_sources_sql  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("ok  " if cond else "FAIL") + "  " + name + (("  " + str(detail)[:200]) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


pkt0 = changed_sources_sql(set(), packet=True)
check("packet empty: no wipe", "DELETE FROM search_changed_sources;\n" not in pkt0)
check("packet empty: ok=1", "changed_sources_ok', 1" in pkt0)
check("packet empty: no INSERT values", "INSERT INTO search_changed_sources SELECT t FROM (VALUES" not in pkt0)

pkt1 = changed_sources_sql({"accumulationregister_x", "document_y"}, packet=True)
check("packet append: no wipe", "DELETE FROM search_changed_sources;\n" not in pkt1)
check("packet append: WHERE NOT IN", "WHERE t NOT IN (SELECT src_table FROM search_changed_sources)" in pkt1)
check("packet append: both tables", "accumulationregister_x" in pkt1 and "document_y" in pkt1)

http0 = changed_sources_sql(set(), packet=False)
check("http empty: wipe", "DELETE FROM search_changed_sources;\n" in http0)
check("http empty: no INSERT values", "INSERT INTO search_changed_sources SELECT * FROM (VALUES" not in http0)

http1 = changed_sources_sql({"t1"}, packet=False)
check("http replace: wipe", "DELETE FROM search_changed_sources;\n" in http1)
check("http replace: INSERT", "INSERT INTO search_changed_sources SELECT * FROM (VALUES ('t1'))" in http1)
check("http replace: not append", "WHERE t NOT IN" not in http1)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene_sync.py"),
           encoding="utf-8").read()
pipe = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.sh"),
            encoding="utf-8").read()
check("sync helper or pipeline keep",
      "changed_sources_sql(" in src or "tmp_changed_keep" in pipe)
check("pipeline packet keep", "tmp_changed_keep" in pipe)
i_sync = pipe.find("python serene_sync.py")
i_ins = pipe.find("INSERT INTO search_changed_sources SELECT src_table FROM tmp_changed_keep")
check("pipeline restore after sync", i_sync >= 0 and i_ins > i_sync)

build = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus_build.sql"),
             encoding="utf-8").read()
check("tmp3_lag exists", "CREATE OR REPLACE TABLE tmp3_lag" in build)
check("tmp3_build includes lag", "SELECT tbl FROM tmp3_lag" in build)
check("tmp3_build includes lag children", "JOIN tmp3_lag" in build or "tmp3_lag l" in build)

cov = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "coverage_build.sql"),
           encoding="utf-8").read()
check("coverage extra reason", "в корпусе больше витрины" in cov)

if FAILS:
    print("FAIL %d/%d" % (len(FAILS), 17))
    sys.exit(1)
print("OK %d/%d" % (17 - len(FAILS), 17))
