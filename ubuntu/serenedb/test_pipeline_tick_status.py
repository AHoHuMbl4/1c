#!/usr/bin/env python3
"""Оффлайн: tick_status.sh пишет одну строку search_quality (PLAN_WIKI_CHOICE §7)."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "tick_status.sh")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


t("tick_status.sh exists", os.path.isfile(SCRIPT))

txt = open(SCRIPT, encoding="utf-8").read()
t("uses search_quality k=tick_status", "k = 'tick_status'" in txt)
t("documents one-row schema", "одна строка" in txt)
t("note format fail|reason", "fail=" in txt and "reason=" in txt)
t("DELETE then INSERT", "DELETE FROM search_quality" in txt)
t("build.sh sources tick_status", "tick_status.sh" in open(
    os.path.join(HERE, "build.sh"), encoding="utf-8").read())
t("build.sh calls tick_status_ok", "tick_status_ok" in open(
    os.path.join(HERE, "build.sh"), encoding="utf-8").read())
t("pipeline.sh sources tick_status", "tick_status.sh" in open(
    os.path.join(HERE, "pipeline.sh"), encoding="utf-8").read())

tmpdir = tempfile.mkdtemp()
state = os.path.join(tmpdir, "sq.tsv")

mock_psql = os.path.join(tmpdir, "psql")
mock_py = r'''#!/usr/bin/env python3
import os, re, sys
state = os.environ["MOCK_SQ"]
sql = ""
if "-c" in sys.argv:
    sql = sys.argv[sys.argv.index("-c") + 1]
if "SELECT coalesce(v,0)" in sql:
    if os.path.isfile(state):
        print(open(state, encoding="utf-8").read().strip())
elif "DELETE FROM search_quality" in sql:
    pass
elif "INSERT INTO search_quality" in sql:
    m = re.search(r"VALUES \('tick_status', (\d+)::BIGINT, '([^']*)'\)", sql)
    if m:
        open(state, "w", encoding="utf-8").write("%s|%s" % (m.group(1), m.group(2)))
'''
with open(mock_psql, "w", encoding="utf-8") as f:
    f.write(mock_py)
os.chmod(mock_psql, 0o755)

env = os.environ.copy()
env["PATH"] = tmpdir + os.pathsep + env.get("PATH", "")
env["MOCK_SQ"] = state
env["SERENEDB_DSN"] = "mock"

rc = subprocess.run(
    ["bash", "-c", ". '%s'; tick_status_ok" % SCRIPT],
    env=env, capture_output=True, text=True)
t("tick_status_ok exit 0", rc.returncode == 0, rc.stderr)
parts = []
if os.path.isfile(state):
    row = open(state, encoding="utf-8").read()
    t("ok wrote row", "|" in row, row)
    parts = row.split("|", 1)
    t("ok v is epoch", parts[0].isdigit() and int(parts[0]) > 1_000_000_000, row)
    t("ok clears reason", parts[1] == "fail=0|reason=", row)

rc2 = subprocess.run(
    ["bash", "-c", ". '%s'; tick_status_fail probe stop" % SCRIPT],
    env=env, capture_output=True, text=True)
t("tick_status_fail exit 0", rc2.returncode == 0, rc2.stderr)
if os.path.isfile(state) and parts:
    row2 = open(state, encoding="utf-8").read()
    t("fail keeps ok v", row2.split("|")[0] == parts[0], row2)
    t("fail reason machine", "probe:stop" in row2, row2)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
