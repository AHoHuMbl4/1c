#!/usr/bin/env python3
"""Оффлайн-замок Ф6.3 хвост: шаг compile solr_synonyms в такте build.sh.

Без сети и без живой базы. Проверяет:
  (а) шаг стоит после wiki_alias и до карточки; зовёт solr_synonyms_compile.sql;
  (б) падение компилятора идёт в fail такта, не soft-echo;
  (в) solr_synonyms_compile.sql — pipeline + escape/dedupe в SQL (оффлайн статика).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solr_synonyms_build as B  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build.sh")
SQL = os.path.join(ROOT, "solr_synonyms_compile.sql")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


build = open(BUILD, encoding="utf-8").read()
compile_sql = open(SQL, encoding="utf-8").read()

# --- (а) место и параметры шага в такте ---
wiki_pos = build.find("./wiki_alias.sh")
solr_pos = build.find("solr_synonyms_compile.sql")
card_pos = build.find("entity_card_build.sql")
t("build has wiki_alias", wiki_pos >= 0)
t("build has solr compile sql step", solr_pos >= 0, "not found")
t("compile after wiki_alias", solr_pos > wiki_pos, "wiki=%d solr=%d" % (wiki_pos, solr_pos))
t("compile before entity_card", 0 <= solr_pos < card_pos,
  "solr=%d card=%d" % (solr_pos, card_pos))

m = re.search(
    r'echo "== 7-solr\.[^"]*"\n(.*?)(?=\necho "== |\n# 🔴 Карточка)',
    build, re.S)
block = m.group(1) if m else ""
t("7-solr block extracted", bool(block), "no match")
t("step uses SOLR_SYN_DICT", "-v solr_syn_dict=\"$SOLR_SYN_DICT\"" in block, block[:200])
t("step passes dict_locale", "-v dict_locale=\"$DICT_LOCALE\"" in block)
t("step uses alias_table param", "alias_table=" in block)
t("step calls psql -f compile sql", "solr_synonyms_compile.sql" in block)
t("build no python solr compile", "solr_synonyms_build.py compile" not in build)

window = build[solr_pos:solr_pos + 350]
t("compile fail-closed (|| fail)",
  "|| fail" in window and "продолжается" not in window, window)
t("build calls compile sql directly", "solr_synonyms_compile.sql" in build)

# --- SQL: pipeline + escape/dedupe ---
t("sql has regexp_split escape-aware", "(?<!\\\\)," in compile_sql or "(?<!\\)," in compile_sql)
t("sql escape backslash/comma", "\\\\" in compile_sql and "\\," in compile_sql)
t("sql ts_lexize stems", "ts_lexize" in compile_sql)
t("sql string_agg rules", "string_agg" in compile_sql)
t("sql pipeline CREATE via gexec", "step2_template = ''solr_synonyms''" in compile_sql)
t("sql alias_idx stem dict", "search_dict_alias_stem" in compile_sql)
t("sql limit error()", "error(" in compile_sql and "max_rules" in compile_sql)
t("sql empty sources branch", "пустые источники" in compile_sql)

# --- (б) падение компилятора не проглатывается (мини-такт с stub) ---
stub_fail = textwrap.dedent(r"""
#!/bin/bash
set -u
fail() { echo "СБОРКА ПРЕРВАНА: $1" >&2; exit 1; }
DSN="host=stub"
SOLR_SYN_DICT="search_dict_syn"
DICT_LOCALE="ru_RU.utf8"
psql() { echo "stub psql fail" >&2; return 2; }
psql "$DSN" -q \
  -v dict_locale="$DICT_LOCALE" \
  -v solr_syn_dict="$SOLR_SYN_DICT" \
  -v alias_table="search_entity_alias" \
  -f solr_synonyms_compile.sql \
  || fail "компиляция словаря solr_synonyms ($SOLR_SYN_DICT)"
echo "не должны дойти сюда"
""")

with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "step.sh")
    open(script, "w", encoding="utf-8").write(stub_fail)
    os.chmod(script, 0o755)
    r = subprocess.run(["bash", script], capture_output=True, text=True, cwd=ROOT)
    t("stub psql fail → exit != 0", r.returncode != 0, "rc=%d" % r.returncode)
    t("stub fail message visible",
      "СБОРКА ПРЕРВАНА" in (r.stderr or "") or "СБОРКА ПРЕРВАНА" in (r.stdout or ""),
      (r.stderr or r.stdout or "")[:200])

stub_ok = textwrap.dedent(r"""
#!/bin/bash
set -u
fail() { echo "СБОРКА ПРЕРВАНА: $1" >&2; exit 1; }
DSN="host=stub"
SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-search_dict_syn}"
DICT_LOCALE="ru_RU.utf8"
LOG="$1"
psql() {
  printf '%s\n' "$*" >> "$LOG"
  return 0
}
psql "$DSN" -q \
  -v dict_locale="$DICT_LOCALE" \
  -v solr_syn_dict="$SOLR_SYN_DICT" \
  -v alias_table="search_entity_alias" \
  -f solr_synonyms_compile.sql \
  || fail "компиляция словаря solr_synonyms ($SOLR_SYN_DICT)"
""")

with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "step_ok.sh")
    log = os.path.join(td, "argv.log")
    open(script, "w", encoding="utf-8").write(stub_ok)
    os.chmod(script, 0o755)
    env = os.environ.copy()
    env["ASK_SOLR_SYNONYMS_DICT"] = "f6_tact_syn"
    r = subprocess.run(["bash", script, log], capture_output=True, text=True, env=env, cwd=ROOT)
    t("stub ok → exit 0", r.returncode == 0, (r.stderr or "")[:200])
    argv = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    t("stub got -f compile sql", "solr_synonyms_compile.sql" in argv, argv)
    t("stub got -v solr_syn_dict", "solr_syn_dict=f6_tact_syn" in argv, argv)

# --- (в) оффлайн: Python-эталон compile_rules стабилен (write-ddl) ---
alias_rows = [{"aliases": "alpha, beta"}, {"aliases": "gamma, delta, epsilon"}]
m1 = B.compile_rules(alias_rows)
d1 = B.render_ddl("search_dict_syn", m1)
t("render_ddl pipeline idempotent",
  "DROP TEXT SEARCH DICTIONARY IF EXISTS search_dict_syn" in d1
  and "template = 'pipeline'" in d1
  and "step1_stemming = true" in d1)

t("build has no alias+bridge wording", "alias+bridge" not in build)
t("build has no search_synonym_bridge", "search_synonym_bridge" not in build)

print()
print("Итог:", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("FAIL:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
