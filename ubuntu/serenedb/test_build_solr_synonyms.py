#!/usr/bin/env python3
"""Оффлайн-замок Ф6.3 хвост: шаг compile solr_synonyms в такте build.sh.

Без сети и без живой базы. Проверяет:
  (а) шаг стоит после wiki_alias и до карточки; зовёт compile с --dict/--apply;
  (б) падение компилятора идёт в fail такта, не soft-echo;
  (в) повторный прогон той же карты даёт тот же DDL (идемпотентность DROP+CREATE).
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

# --- (а) место и параметры шага в такте ---
wiki_pos = build.find("./wiki_alias.sh")
solr_pos = build.find("solr_synonyms_build.py compile")
card_pos = build.find("entity_card_build.sql")
t("build has wiki_alias", wiki_pos >= 0)
t("build has solr compile step", solr_pos >= 0, "not found")
t("compile after wiki_alias", solr_pos > wiki_pos, "wiki=%d solr=%d" % (wiki_pos, solr_pos))
t("compile before entity_card", 0 <= solr_pos < card_pos,
  "solr=%d card=%d" % (solr_pos, card_pos))

# фрагмент шага 7-solr (от echo до следующего echo ==)
m = re.search(
    r'echo "== 7-solr\.[^"]*"\n(.*?)(?=\necho "== |\n# 🔴 Карточка)',
    build, re.S)
block = m.group(1) if m else ""
t("7-solr block extracted", bool(block), "no match")
t("step uses SOLR_SYN_DICT", "--dict \"$SOLR_SYN_DICT\"" in block or
  "--dict \"$SOLR_SYN_DICT\"" in build[solr_pos:solr_pos + 400], block[:200])
t("step passes --apply", "--apply" in block)
t("step writes SOLR_OUT under CSV_DIR",
  "solr_synonyms_${SOLR_SYN_DICT}.sql" in block or
  "solr_synonyms_${SOLR_SYN_DICT}.sql" in build)
t("step controlled by SOLR_SYN_DICT env",
  "SOLR_SYN_DICT=" in build[:build.find("echo \"== 0.")] and
  "ASK_SOLR_SYNONYMS_DICT" in build[:build.find("echo \"== 0.")])

# fail-closed: около compile должен быть || fail, не soft-echo «продолжается»
window = build[solr_pos:solr_pos + 350]
t("compile fail-closed (|| fail)",
  "|| fail" in window and "продолжается" not in window, window)

# soft-path wiki_alias не должен быть единственным местом compile в такте
# (wiki_alias.sh вне build — здесь только прямой зов)
t("build calls compile directly",
  "python3 ./solr_synonyms_build.py compile" in build)

# --- (б) падение компилятора не проглатывается (мини-такт с stub) ---
stub_fail = textwrap.dedent(r"""
#!/bin/bash
set -u
fail() { echo "СБОРКА ПРЕРВАНА: $1" >&2; exit 1; }
DSN="host=stub"
SOLR_SYN_DICT="search_dict_syn"
CSV_DIR="$1"
SOLR_OUT="${CSV_DIR}/solr_synonyms_${SOLR_SYN_DICT}.sql"
# stub python3: любой compile → exit 2 (как LimitError)
python3() {
  echo "stub: $*" >&2
  return 2
}
python3 ./solr_synonyms_build.py compile \
  --dsn "$DSN" --dict "$SOLR_SYN_DICT" \
  --alias-table "search_entity_alias" \
  --out "$SOLR_OUT" --apply \
  || fail "компиляция словаря solr_synonyms ($SOLR_SYN_DICT)"
echo "не должны дойти сюда"
""")

with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "step.sh")
    open(script, "w", encoding="utf-8").write(stub_fail)
    os.chmod(script, 0o755)
    r = subprocess.run(
        ["bash", script, td], capture_output=True, text=True)
    t("stub LimitError → exit != 0", r.returncode != 0, "rc=%d" % r.returncode)
    t("stub fail message visible",
      "СБОРКА ПРЕРВАНА" in (r.stderr or "") or "СБОРКА ПРЕРВАНА" in (r.stdout or ""),
      (r.stderr or r.stdout or "")[:200])
    t("stub did not continue past fail",
      "не должны дойти сюда" not in (r.stdout or "") + (r.stderr or ""))

# успех: stub пишет маркер и exit 0 — шаг проходит
stub_ok = textwrap.dedent(r"""
#!/bin/bash
set -u
fail() { echo "СБОРКА ПРЕРВАНА: $1" >&2; exit 1; }
DSN="host=stub"
SOLR_SYN_DICT="${ASK_SOLR_SYNONYMS_DICT:-search_dict_syn}"
CSV_DIR="$1"
LOG="$2"
SOLR_OUT="${CSV_DIR}/solr_synonyms_${SOLR_SYN_DICT}.sql"
python3() {
  # фиксируем argv для проверки параметров
  printf '%s\n' "$*" >> "$LOG"
  # имитация --apply: пишем файл (как compile_from_db + psql)
  case " $* " in
    *" compile "*)
      echo "-- ddl for $SOLR_SYN_DICT" > "$SOLR_OUT"
      echo "ok apply" >> "$LOG"
      return 0 ;;
  esac
  return 1
}
python3 ./solr_synonyms_build.py compile \
  --dsn "$DSN" --dict "$SOLR_SYN_DICT" \
  --alias-table "search_entity_alias" \
  --out "$SOLR_OUT" --apply \
  || fail "компиляция словаря solr_synonyms ($SOLR_SYN_DICT)"
""")

with tempfile.TemporaryDirectory() as td:
    script = os.path.join(td, "step_ok.sh")
    log = os.path.join(td, "argv.log")
    open(script, "w", encoding="utf-8").write(stub_ok)
    os.chmod(script, 0o755)
    env = os.environ.copy()
    env["ASK_SOLR_SYNONYMS_DICT"] = "f6_tact_syn"
    r = subprocess.run(
        ["bash", script, td, log], capture_output=True, text=True, env=env)
    t("stub ok → exit 0", r.returncode == 0, (r.stderr or "")[:200])
    argv = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    t("stub got compile", "compile" in argv, argv)
    t("stub got --dict from env", "--dict f6_tact_syn" in argv, argv)
    t("stub got --apply", "--apply" in argv, argv)
    t("stub got --out path", "solr_synonyms_f6_tact_syn.sql" in argv, argv)
    out_path = os.path.join(td, "solr_synonyms_f6_tact_syn.sql")
    t("stub wrote out file", os.path.isfile(out_path))

# --- (в) идемпотентность: одна карта → один и тот же DDL дважды ---
alias_rows = [{"aliases": "alpha, beta"}, {"aliases": "gamma, delta, epsilon"}]
m1 = B.compile_rules(alias_rows)
m2 = B.compile_rules(alias_rows)
t("compile_rules stable", m1 == m2 and bool(m1.strip()), repr(m1)[:120])
try:
    B.check_limits(m1)
    lim_ok = True
except B.LimitError:
    lim_ok = False
t("fixture under limits", lim_ok)
d1 = B.render_ddl("search_dict_syn", m1)
d2 = B.render_ddl("search_dict_syn", m2)
t("render_ddl idempotent", d1 == d2)
t("ddl is DROP+CREATE pipeline (recreate)",
  "DROP TEXT SEARCH DICTIONARY IF EXISTS search_dict_syn" in d1
  and "CREATE TEXT SEARCH DICTIONARY search_dict_syn" in d1
  and "template = 'pipeline'" in d1
  and "step1_stemming = true" in d1)

# повторный «прогон шага» write-ddl в один out — содержимое не плодит дублей
with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "syn.sql")
    open(out, "w", encoding="utf-8").write(d1)
    open(out, "w", encoding="utf-8").write(d2)  # второй прогон перезаписывает
    got = open(out, encoding="utf-8").read()
    t("second write same bytes", got == d1)
    # в карте нет дубликатов правил
    rules = [ln for ln in m1.splitlines() if ln.strip()]
    t("no duplicate rules in map", len(rules) == len(set(r.lower() for r in rules)),
      rules)

# С3: шаг такта не ссылается на снятый bridge-слот
t("build has no alias+bridge wording", "alias+bridge" not in build)
t("build has no search_synonym_bridge", "search_synonym_bridge" not in build)
t("module has no bridge path",
  "search_synonym_bridge" not in open(B.__file__, encoding="utf-8").read()
  and not hasattr(B, "BRIDGE_TABLE")
  and not hasattr(B, "rule_from_bridge_row"))

print()
print("Итог:", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("FAIL:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
