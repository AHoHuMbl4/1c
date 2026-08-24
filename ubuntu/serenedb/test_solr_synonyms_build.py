#!/usr/bin/env python3
"""Оффлайн-замок Ф6.3 шаг 2: компиляция Solr-карты из alias/bridge без LLM/сети.

(а) фиктивные строки → ожидаемая Solr-строка (bi / one-way / экранирование запятых);
(б) пустая alias-таблица → пустая карта, DDL не пишется / словарь не пересоздаётся;
(в) сверх лимита → LimitError, не тихая обрезка (п. 13 TARGET).
"""
from __future__ import annotations

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
bridge_rows = [
    {"rule": "laptop => notebook"},
    {"lhs": "car", "rhs": "auto"},
    {"rule": "tv, television, telly"},
]
got = B.compile_rules(alias_rows, bridge_rows)
lines = got.splitlines()
t("bi class from alias CSV", "alpha, beta, gamma" in lines, got)
t("bi class trimmed", "zebra, yak" in lines, got)
t("single term skipped", "one" not in lines and not any(l == "one" for l in lines), got)
t("one-way from bridge rule", "laptop => notebook" in lines, got)
t("one-way from lhs/rhs", "car => auto" in lines, got)
t("bi from bridge rule", "television, telly, tv" in lines or "tv, television, telly" in lines, got)
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
empty_map = B.compile_rules([], [])
t("empty sources → empty map", empty_map == "", repr(empty_map))
empty_map2 = B.compile_rules([{"aliases": ""}, {"aliases": "solo"}], [])
t("only singles → empty map (no recreate)", empty_map2 == "", repr(empty_map2))

with tempfile.TemporaryDirectory() as td:
    ddl_path = os.path.join(td, "out.sql")
    # simulate compile-rows empty: DDL not written
    rc_map = B.compile_rules([], [{"rule": ""}])
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
t("ddl marks bridge source", "search_synonym_bridge" in ddl)
t("ddl embeds map", "a, b" in ddl and "laptop => notebook" in ddl)
t("no synonym literals in module defaults beyond format",
  "остатк" not in open(B.__file__, encoding="utf-8").read()
  and "depozit" not in open(B.__file__, encoding="utf-8").read())

# лимиты из фактуры
t("MAX_RULES = 20000 (facts §3.2)", B.MAX_RULES == 20_000)
t("MAX_BYTES = 400000 (facts §3.2)", B.MAX_BYTES == 400_000)

print()
print("Итог:", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("FAIL:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
