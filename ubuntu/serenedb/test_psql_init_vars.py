#!/usr/bin/env python3
"""Оффлайн-замок Д4: psql-переменные corpus_init/precheck заданы в build.sh.

Дефект 24.08–27.08 okna: corpus_init.sql ждал :"solr_syn_dict", а живой
build.sh звал файл без `-v solr_syn_dict=…` → syntax error → такт failed
3083 раза подряд. Этот тест ловит рассинхрон «SQL требует / вызывающий не
передаёт» до выката, без journalctl.

Сломанный случай (ожидаем FAIL): временно убрать `-v solr_syn_dict` из
фрагмента init-зова — тест красный.
Починенный: build.sh как в дереве — все PASS.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build.sh")
INIT = os.path.join(ROOT, "corpus_init.sql")
PRE = os.path.join(ROOT, "corpus_precheck.sql")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def vars_in_sql(text: str) -> set[str]:
    # :"name" (идентификатор) и :'name' (литерал) — штатная подстановка psql.
    return set(re.findall(r""":['"]([A-Za-z_][A-Za-z0-9_]*)['"]""", text))


def vars_passed_near(build: str, needle: str) -> set[str]:
    """Переменные `-v name=` в окне вокруг первого зова `needle` (-f файл)."""
    pos = build.find(needle)
    if pos < 0:
        return set()
    # окно: от предыдущего echo/psql до конца строки с -f
    start = max(0, pos - 400)
    end = min(len(build), pos + len(needle) + 80)
    window = build[start:end]
    return set(re.findall(r"""-v\s+([A-Za-z_][A-Za-z0-9_]*)=""", window))


build = open(BUILD, encoding="utf-8").read()
init = open(INIT, encoding="utf-8").read()
pre = open(PRE, encoding="utf-8").read()

t("build defines SOLR_SYN_DICT",
  re.search(r"^SOLR_SYN_DICT=", build, re.M) is not None)
t("build refuses empty SOLR_SYN_DICT before init",
  'fail "не задан SOLR_SYN_DICT' in build or
  "fail \"не задан SOLR_SYN_DICT" in build)

init_vars = vars_in_sql(init)
pre_vars = vars_in_sql(pre)
t("corpus_init uses solr_syn_dict", "solr_syn_dict" in init_vars, sorted(init_vars))
t("corpus_init has \\if default for solr_syn_dict",
  r"\if :{?solr_syn_dict}" in init and r"\set solr_syn_dict" in init)

init_passed = vars_passed_near(build, "-f corpus_init.sql")
pre_passed = vars_passed_near(build, "-f corpus_precheck.sql")

t("build passes -v solr_syn_dict to corpus_init",
  "solr_syn_dict" in init_passed, sorted(init_passed))
t("build passes -v dict_locale to corpus_init",
  "dict_locale" in init_passed, sorted(init_passed))

# Каждая переменная из init, кроме тех что закрыты \if-умолчанием в том же файле,
# должна быть в -v. Умолчание есть только у solr_syn_dict — dict_locale всё равно
# обязан передаваться (иначе locale пустой).
missing_init = sorted(init_vars - init_passed)
t("все :vars corpus_init покрыты -v в build (или известное умолчание)",
  missing_init == [] or missing_init == ["solr_syn_dict"] and
  r"\if :{?solr_syn_dict}" in init,
  "missing=" + ",".join(missing_init))

if "solr_syn_dict" in pre_vars:
    t("build passes -v solr_syn_dict to corpus_precheck",
      "solr_syn_dict" in pre_passed, sorted(pre_passed))

# Регрессия исходного дефекта: окно зова init без -v solr_syn_dict — красный.
broken = re.sub(
    r"""-v\s+solr_syn_dict="\$SOLR_SYN_DICT"\s*\\\n\s*""",
    "",
    build,
    count=1,
)
broken_passed = vars_passed_near(broken, "-f corpus_init.sql")
t("сломанный build (без -v solr_syn_dict) ловится",
  "solr_syn_dict" not in broken_passed,
  "если этот FAIL — регэксп сломал разбор, а не замок")

print()
print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
