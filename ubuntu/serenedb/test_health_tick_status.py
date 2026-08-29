#!/usr/bin/env python3
"""Оффлайн: /health отдаёт tick_status из search_quality (PLAN_WIKI_CHOICE §7)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


t("parse empty", A._parse_tick_status_note("") == (0, ""))
t("parse ok note", A._parse_tick_status_note("fail=0|reason=") == (0, ""))
t("parse fail", A._parse_tick_status_note("fail=100|reason=corpus_build:stop")
  == (100, "corpus_build:stop"))

real_psql = A.psql


def mock_tick_row(v, note):
    def _psql(sql):
        if "k='tick_status'" in sql:
            return [[v, note]]
        if "count(*)" in sql.lower():
            return [[50]]
        return []
    return _psql


A.psql = mock_tick_row(1_700_000_000, "fail=0|reason=")
out = A._measure_tick_status()
t("measure known", out.get("known") is True, out)
t("measure no recent fail", out.get("had_recent_fail") is False, out)
t("measure summary has freshness", "мин" in (out.get("summary") or ""), out)

A.psql = mock_tick_row(1_700_000_000, "fail=1700000100|reason=corpus_merge:stop")
out2 = A._measure_tick_status()
t("recent fail", out2.get("had_recent_fail") is True, out2)
t("fail reason", out2.get("fail_reason") == "corpus_merge:stop", out2)
t("summary has reason", "corpus_merge:stop" in (out2.get("summary") or ""), out2)

A.psql = real_psql


class FakeHandler(A.Handler):
    def __init__(self):
        self.path = "/health"
        self._code = None
        self._body = None

    def _send(self, code, obj):
        self._code = code
        self._body = obj


def stub_corpus():
    def _psql(sql):
        if "k='tick_status'" in sql:
            return [[1_700_000_000, "fail=0|reason="]]
        if "count(*)" in sql.lower():
            return [[100]]
        return []
    return _psql


saved = A._health_gap, A._classify_health_gap, A.psql
A.psql = stub_corpus()
A._health_gap = lambda: None
A._classify_health_gap = lambda g: None
h = FakeHandler()
h.do_GET()
A._health_gap, A._classify_health_gap, A.psql = saved
t("health HTTP 200", h._code == 200, h._code)
tick = (h._body or {}).get("tick") or {}
t("health has tick", tick.get("known") is True, h._body)
t("health tick summary", "мин" in (tick.get("summary") or ""), tick)

src = A.ask_source()
t("source has _measure_tick_status", "_measure_tick_status" in src)
t("source has tick_status SQL", "k='tick_status'" in src)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
