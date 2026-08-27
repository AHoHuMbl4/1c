#!/usr/bin/env python3
"""Д3: замок пустого inverted-индекса при непустой таблице.

Оффлайн: чистая функция + наличие VACUUM REFRESH в wiki_alias.sh и проверки
в corpus_postcheck.sql. Живой fail/pass — демо через mock-счётчики и опционально
SERENEDB_DSN (боковая таблица, не боевой alias_idx).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inverted_index_guard import assert_index_covers_table  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


# --- чистая функция: сломанный / целый ---
try:
    assert_index_covers_table(254, 0, label="alias_idx")
    t("broken case raises", False, "expected AssertionError")
except AssertionError as e:
    t("broken case raises", "empty" in str(e).lower() and "254" in str(e), e)

try:
    assert_index_covers_table(257, 257, label="alias_idx")
    t("healthy equal counts pass", True)
except AssertionError as e:
    t("healthy equal counts pass", False, e)

try:
    assert_index_covers_table(0, 0, label="fresh install")
    t("empty table+index ok", True)
except AssertionError as e:
    t("empty table+index ok", False, e)

try:
    # сразу после DELETE+INSERT фон ещё не сжал старые сегменты — не FAIL Д3
    assert_index_covers_table(100, 254, label="stale lag")
    t("stale higher index not empty-fail", True)
except AssertionError as e:
    t("stale higher index not empty-fail", False, e)

# --- пайплайн: wiki_alias публикует индекс ---
wiki = open(os.path.join(ROOT, "wiki_alias.sh"), encoding="utf-8").read()
t("wiki_alias has VACUUM REFRESH_TABLE",
  "VACUUM (REFRESH_TABLE) $ALIAS_TABLE" in wiki
  or 'VACUUM (REFRESH_TABLE) "$ALIAS_TABLE"' in wiki)
# публикация после итогового SELECT по словарю, до day-basis / solr
pos_refresh = wiki.find("VACUUM (REFRESH_TABLE) $ALIAS_TABLE")
pos_summary = wiki.find("алиасов в базе")
pos_dayfork = wiki.find("§7 / §7bis")
t("refresh after alias summary",
  pos_refresh > pos_summary > 0, "sum=%d ref=%d" % (pos_summary, pos_refresh))
t("refresh before day-basis forks",
  pos_dayfork < 0 or (0 < pos_refresh < pos_dayfork),
  "ref=%d day=%d" % (pos_refresh, pos_dayfork))
t("refresh not inside comment-only",
  "psql" in wiki[max(0, pos_refresh - 120):pos_refresh + 80])

# --- postcheck ловит пустой alias_idx ---
post = open(os.path.join(ROOT, "corpus_postcheck.sql"), encoding="utf-8").read()
t("postcheck mentions alias_idx", "alias_idx" in post)
t("postcheck errors on empty index",
  "alias_idx пуст" in post or "REFRESH_TABLE" in post)
t("postcheck guards non-empty table",
  "search_entity_alias" in post and "count(*) FROM alias_idx" in post)

# --- entity_card уже публикует (регрессия: не сломать образец) ---
card = open(os.path.join(ROOT, "entity_card_build.sql"), encoding="utf-8").read()
t("entity_card still VACUUM REFRESH_TABLE",
  "VACUUM (REFRESH_TABLE) search_entity_card" in card)

# --- живое демо fail→pass на боковой таблице (если DSN дан) ---
dsn = os.environ.get("SERENEDB_DSN") or os.environ.get("D3_LIVE_DSN")
if dsn:
    import subprocess
    import time

    def psql(sql: str) -> str:
        env = os.environ.copy()
        # пароль только из окружения вызывающего; в argv не кладём
        r = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
            capture_output=True, text=True, env=env, timeout=60,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[:400] or r.stdout.strip()[:400])
        return (r.stdout or "").strip()

    psql("DROP TABLE IF EXISTS d3_guard_probe CASCADE")
    psql(
        "CREATE TABLE d3_guard_probe ("
        "src_table VARCHAR PRIMARY KEY, aliases VARCHAR)"
    )
    psql(
        "CREATE INDEX d3_guard_probe_idx ON d3_guard_probe "
        "USING inverted(aliases search_dict, src_table) INCLUDE (src_table)"
    )
    psql("INSERT INTO d3_guard_probe VALUES ('x','клиент')")
    # сразу после INSERT индекс ещё не опубликован → сломанный случай
    tr = int(psql("SELECT count(*) FROM d3_guard_probe"))
    ir = int(psql("SELECT count(*) FROM d3_guard_probe_idx"))
    broken_caught = False
    try:
        assert_index_covers_table(tr, ir, label="d3_guard_probe_idx")
    except AssertionError:
        broken_caught = True
    t("live broken: table>0 index=0 caught",
      broken_caught and tr > 0 and ir == 0,
      "table=%s index=%s" % (tr, ir))
    psql("VACUUM (REFRESH_TABLE) d3_guard_probe")
    tr2 = int(psql("SELECT count(*) FROM d3_guard_probe"))
    ir2 = int(psql("SELECT count(*) FROM d3_guard_probe_idx"))
    try:
        assert_index_covers_table(tr2, ir2, label="d3_guard_probe_idx")
        t("live after REFRESH: pass", tr2 > 0 and ir2 > 0,
          "table=%s index=%s" % (tr2, ir2))
    except AssertionError as e:
        t("live after REFRESH: pass", False, e)
    # фон тоже подтянул бы, но явный REFRESH — контракт пайплайна
    time.sleep(0)  # noqa: placate linters; live path is the point
    psql("DROP TABLE IF EXISTS d3_guard_probe CASCADE")
else:
    t("live demo skipped (set SERENEDB_DSN)", True)

print()
print("%d ok, %d fail" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
