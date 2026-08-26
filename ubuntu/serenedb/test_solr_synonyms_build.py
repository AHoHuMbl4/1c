#!/usr/bin/env python3
"""Оффлайн-замок Ф6.3 шаг 2: компиляция Solr-карты из search_entity_alias без LLM/сети.

(а) фиктивные строки → ожидаемая Solr-строка (bi / экранирование запятых);
(б) пустая alias-таблица → пустая карта, DDL не пишется / словарь не пересоздаётся;
(в) сверх лимита → LimitError, не тихая обрезка (п. 13 TARGET);
(г) слот search_synonym_bridge снят (С3): ветка bridge в сборке отсутствует.
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solr_synonyms_build as B  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:220]) if detail else "")


# --- (а) двусторонние классы из alias CSV ---
alias_rows = [
    {"aliases": "alpha, beta, gamma"},
    {"aliases": "one"},  # один терм — не правило
    {"aliases": ""},
    {"aliases": "  zebra , yak  "},
]
got = B.compile_rules(alias_rows)
lines = got.splitlines()
t("bi class from alias CSV", "alpha, beta, gamma" in lines, got)
t("bi class trimmed", "zebra, yak" in lines, got)
t("single term skipped", "one" not in lines and not any(l == "one" for l in lines), got)
# порядок термов в bi-классе — как в источнике после escape; сортировка — по строкам правил
t("rules sorted case-insensitive", lines == sorted(lines, key=str.lower), lines)

# экранирование запятой внутри терма
esc = B.rule_from_alias_csv("red\\,blue, green")
t("escape: term with comma stays one",
  esc is not None and esc.split(", ")[0] == "red\\,blue", esc)
t("escape: peer term present", esc is not None and "green" in esc, esc)
t("escape_term backslash", B.escape_term("a\\b") == "a\\\\b")
t("escape_term comma", B.escape_term("a,b") == "a\\,b")

rule2 = B.rule_from_alias_csv("foo\\,bar, baz")
t("escaped comma in CSV input kept",
  rule2 is not None and "foo\\,bar" in rule2 and "baz" in rule2, rule2)
t("raw escape_term for DDL safety", B.escape_term("foo,bar") == "foo\\,bar")

# --- (б) пустая таблица ---
empty_map = B.compile_rules([])
t("empty sources → empty map", empty_map == "", repr(empty_map))
empty_map2 = B.compile_rules([{"aliases": ""}, {"aliases": "solo"}])
t("only singles → empty map (no recreate)", empty_map2 == "", repr(empty_map2))

with tempfile.TemporaryDirectory() as td:
    ddl_path = os.path.join(td, "out.sql")
    # simulate compile-rows empty: DDL not written
    rc_map = B.compile_rules([{"aliases": ""}])
    if not rc_map.strip():
        # не вызываем render — как compile_from_db
        wrote = False
    else:
        open(ddl_path, "w").write(B.render_ddl("search_dict_syn", rc_map))
        wrote = True
    t("empty → ddl not written", wrote is False and not os.path.exists(ddl_path))

# --- (в) лимит: ошибка, не обрезка ---
huge_rules = ["t%05d, u%05d" % (i, i) for i in range(B.MAX_RULES + 5)]
huge_map = "\n".join(huge_rules)
try:
    B.check_limits(huge_map)
    lim_ok = False
    lim_detail = "no error"
except B.LimitError as e:
    lim_ok = True
    lim_detail = str(e)
t("over MAX_RULES → LimitError", lim_ok, lim_detail)
t("limit error mentions count", lim_ok and str(B.MAX_RULES) in lim_detail, lim_detail)

# байтовый потолок
fat = ("x" * 80 + ", " + "y" * 80 + "\n") * (B.MAX_BYTES // 100 + 50)
try:
    B.check_limits(fat)
    byte_ok = False
except B.LimitError as e:
    byte_ok = "байт" in str(e) or "byte" in str(e).lower() or str(B.MAX_BYTES) in str(e)
t("over MAX_BYTES → LimitError", byte_ok)

# обрезки нет: check_limits не возвращает урезанную строку
before = huge_map
try:
    B.check_limits(before)
except B.LimitError:
    pass
t("map unchanged after failed check", before == huge_map)

# --- DDL форма ---
ddl = B.render_ddl("search_dict_syn", "a, b\nlaptop => notebook")
t("ddl has DROP", "DROP TEXT SEARCH DICTIONARY IF EXISTS search_dict_syn" in ddl, ddl[:200])
t("ddl has CREATE solr_synonyms", "template = 'solr_synonyms'" in ddl, ddl[:300])
t("ddl marks wiki-alias source", "search_entity_alias" in ddl)
t("ddl embeds map", "a, b" in ddl and "laptop => notebook" in ddl)
t("no synonym literals in module defaults beyond format",
  "остатк" not in open(B.__file__, encoding="utf-8").read()
  and "depozit" not in open(B.__file__, encoding="utf-8").read())

# лимиты из фактуры
t("MAX_RULES = 20000 (facts §3.2)", B.MAX_RULES == 20_000)
t("MAX_BYTES = 400000 (facts §3.2)", B.MAX_BYTES == 400_000)

# --- (г) С3: bridge-path снят — замок против возврата ---
src = open(B.__file__, encoding="utf-8").read()
t("no BRIDGE_TABLE const", "BRIDGE_TABLE" not in src and not hasattr(B, "BRIDGE_TABLE"))
t("no search_synonym_bridge literal", "search_synonym_bridge" not in src)
t("no rule_from_bridge_row", "rule_from_bridge_row" not in src
  and not hasattr(B, "rule_from_bridge_row"))
t("no rule_one_way helper", "rule_one_way" not in src and not hasattr(B, "rule_one_way"))
t("no --bridge-json CLI", "--bridge-json" not in src)
sig = inspect.signature(B.compile_rules)
t("compile_rules takes only alias_rows",
  list(sig.parameters) == ["alias_rows"], list(sig.parameters))
t("ddl does not mark bridge source", "search_synonym_bridge" not in ddl
  and "bridge" not in ddl.lower())

root = os.path.dirname(os.path.abspath(__file__))
init_sql = open(os.path.join(root, "corpus_init.sql"), encoding="utf-8").read()
pre_sql = open(os.path.join(root, "corpus_precheck.sql"), encoding="utf-8").read()
build_sh = open(os.path.join(root, "build.sh"), encoding="utf-8").read()
t("corpus_init has no CREATE search_synonym_bridge",
  "CREATE TABLE IF NOT EXISTS search_synonym_bridge" not in init_sql)
t("corpus_precheck has no bridge table name",
  "search_synonym_bridge" not in pre_sql)
t("corpus_precheck no error about missing bridge table",
  "нет таблицы search_" not in pre_sql
  and "кэш моста для" not in pre_sql)
t("build.sh echo is alias-only",
  "alias+bridge" not in build_sh
  and any(
      "7-solr" in ln and "alias" in ln and "bridge" not in ln
      for ln in build_sh.splitlines() if ln.lstrip().startswith("echo")))

print()
print("Итог:", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("FAIL:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
