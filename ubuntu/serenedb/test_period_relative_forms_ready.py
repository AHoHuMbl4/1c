#!/usr/bin/env python3
"""Оффлайн-замок: словарь period_relative_forms в такте + видимость в /health.

Без сети и без живой базы. Проверяет:
  (а) шаг 1-period в build.sh: read_text → search_meta, fail-closed, вне SKIP;
  (б) /health: пустой словарь → degraded + loaded=False; загруженный → ok;
  (в) запасной путь файла работает при cwd ≠ каталог модуля.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build.sh")
LOAD_SQL = os.path.join(ROOT, "period_relative_forms_load.sql")
FORMS_JSON = os.path.join(ROOT, "period_relative_forms.json")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


# ── (а) такт сборки ──────────────────────────────────────────────────────────
build = open(BUILD, encoding="utf-8").read()
load_sql = open(LOAD_SQL, encoding="utf-8").read()

t("load sql exists", os.path.isfile(LOAD_SQL))
t("forms json exists", os.path.isfile(FORMS_JSON))
t("build has 1-period step", 'echo "== 1-period.' in build)
t("build calls period_relative_forms_load.sql",
  "-f period_relative_forms_load.sql" in build)
t("build copies json into CSV_DIR",
  "period_relative_forms.json" in build
  and "CSV_DIR" in build[build.find("1-period"):build.find("1-period") + 800])
t("build fail-closed on load",
  '|| fail "загрузка period_relative_forms' in build)
# шаг после блока SKIP корпуса (fi перед 1-period), не внутри else
m = re.search(
    r'\nfi\n\n# Словарь относительных окон.*?echo "== 1-period\.',
    build, re.S)
t("1-period outside SKIP_BUILD else", bool(m), "step inside skip branch?")
t("sql uses read_text", "read_text(:'period_forms_path')" in load_sql)
t("sql writes search_meta key",
  "period_relative_forms" in load_sql
  and "INSERT INTO search_meta" in load_sql)
t("sql fail-closed empty/object",
  "error('period_relative_forms:" in load_sql
  or 'error("period_relative_forms:' in load_sql)
t("sql validates OBJECT via json_type/json_keys",
  "json_type(content) = 'OBJECT'" in load_sql
  and "json_keys" in load_sql)
t("sql has no Russian phrase literals",
  "прошл" not in load_sql and "недел" not in load_sql)


# ── (б) /health готовность ───────────────────────────────────────────────────
class FakeHandler(A.Handler):
    def __init__(self):
        self.path = "/health"
        self._code = None
        self._body = None

    def _send(self, code, obj):
        self._code = code
        self._body = obj


REAL = {
    "psql": A.psql,
    "hg": A._health_gap,
    "cls": A._classify_health_gap,
    "prf": A.period_relative_forms,
    "hprf": A._health_period_relative_forms,
    "native_flag": A.ASK_HEALTH_NATIVE_FRESHNESS,
}


def reset():
    A.psql = REAL["psql"]
    A._health_gap = REAL["hg"]
    A._classify_health_gap = REAL["cls"]
    A.period_relative_forms = REAL["prf"]
    A.ASK_HEALTH_NATIVE_FRESHNESS = False


A.ASK_HEALTH_NATIVE_FRESHNESS = False
A.psql = lambda sql: [[100]] if "count(*)" in sql.lower() else []
A._health_gap = lambda: None
A._classify_health_gap = lambda g: None

A.period_relative_forms = lambda: {}
h = FakeHandler()
h.do_GET()
t("empty dict → HTTP 503", h._code == 503, h._code)
t("empty dict → status degraded",
  (h._body or {}).get("status") == "degraded", h._body)
t("empty dict → loaded False",
  (h._body or {}).get("period_relative_forms", {}).get("loaded") is False,
  h._body)
t("empty dict → forms 0",
  (h._body or {}).get("period_relative_forms", {}).get("forms") == 0, h._body)

A.period_relative_forms = lambda: {"prev_week": ["last week"]}
h = FakeHandler()
h.do_GET()
t("loaded dict → HTTP 200", h._code == 200, h._code)
t("loaded dict → serene-ask-ok",
  (h._body or {}).get("status") == "serene-ask-ok", h._body)
t("loaded dict → loaded True",
  (h._body or {}).get("period_relative_forms", {}).get("loaded") is True,
  h._body)
t("loaded dict → forms >= 1",
  (h._body or {}).get("period_relative_forms", {}).get("forms", 0) >= 1,
  h._body)

reset()
A.period_relative_forms = lambda: {}
got = A._health_period_relative_forms()
t("helper empty → loaded False",
  got == {"loaded": False, "forms": 0}, got)
A.period_relative_forms = lambda: {"a": ["x"], "b": ["y"]}
got = A._health_period_relative_forms()
t("helper loaded → loaded True forms 2",
  got == {"loaded": True, "forms": 2}, got)
reset()


# ── (в) запасной файл при чужом cwd ──────────────────────────────────────────
A._PERIOD_RELATIVE_FORMS.update({"at": 0.0, "map": None})
A.psql = lambda sql: []  # meta пуста → только файл
old_cwd = os.getcwd()
try:
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        forms = A.period_relative_forms()
    t("fallback file works from other cwd",
      isinstance(forms, dict) and "prev_week" in forms
      and any("прошл" in str(p) or "week" in str(p).lower()
              for p in (forms.get("prev_week") or [])),
      forms)
finally:
    os.chdir(old_cwd)
    A._PERIOD_RELATIVE_FORMS.update({"at": 0.0, "map": None})
    reset()

# путь строится от __file__, не от cwd
import serene_ask as _A  # noqa: E402

src = _A.ask_source()
# узкий фрагмент функции period_relative_forms
i = src.find("def period_relative_forms(")
j = src.find("\ndef period_form_from_question(", i)
frag = src[i:j]
t("fallback uses __file__ dirname",
  "os.path.dirname(os.path.abspath(__file__))" in frag
  and "period_relative_forms.json" in frag, frag[:400])

print()
print("PASS %d FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
