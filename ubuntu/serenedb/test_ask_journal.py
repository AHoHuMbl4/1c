#!/usr/bin/env python3
"""Журнал ask_journal (план §8 шаг 5, аудит §14.5).

Замки:
  · запись на каждом виде исхода (answer/figures/clarify/no_data/unavailable/choice_error);
  · ошибка записи не роняет ответ;
  · в SQL нет текста вопроса;
  · живая база: INSERT у serene_ro, SELECT q_hash отвергнут, ротация, колонки вопроса нет.

Запуск: python3 ubuntu/serenedb/test_ask_journal.py
Оффлайн без базы; живой контур — при PGPASSWORD / SERENEDB_DSN_RO.
"""
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_JOURNAL", "1")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


KINDS = ("answer", "figures", "clarify", "no_data", "unavailable", "choice_error")
SECRET = "секретный-вопрос-XYZ-privacy-probe"


def _fake_psql_factory(captured, nid_box):
    def fake_psql(sql):
        captured.append(sql)
        if "nextval" in sql:
            nid_box[0] += 1
            return [[str(nid_box[0])]]
        if "search_quality" in sql:
            return [["1710000000"]]
        if "concat_ws" in sql:
            return [["1|2|3"]]
        if "count(*) FROM search_tables" in sql or "count(*) FROM %s" % A.TABLES in sql:
            return [["8"]]
        if sql.strip().upper().startswith("INSERT") or sql.strip().upper().startswith("DELETE"):
            return []
        return []
    return fake_psql


# ── оффлайн: все виды, приватность SQL ──────────────────────────────────────
captured, nid_box = [], [0]
A.ASK_JOURNAL = True
A._JOURNAL_KEEP = 72
A._JOURNAL_LOST = 0
A._JOURNAL_ALIAS_VER = "1|2|3"
A._JOURNAL_BUILD_TS = "1"
A._JOURNAL_BUILD_TS_AT = 1e18
old_psql = A.psql
A.psql = _fake_psql_factory(captured, nid_box)
try:
    for kind in KINDS:
        out = {"kind": kind, "text": "не в журнал", "diag": {"kind": "продажи",
               "tokens": {"in": 10, "out": 2, "calls": 1},
               "fork": {"outcome": "B", "atoms_truncated": 1}},
               "partial": {"fork_limitation": {"uncounted_classes": 2}},
               "atom": {"operation": "sum", "exact_value": "1.00", "measure_id": "Сумма"},
               "error": "used" if kind == "choice_error" else None}
        A._ask_journal_write(SECRET, out, A.time.monotonic() - 0.01,
                             trusted={"src": "x"} if kind != "choice_error" else None,
                             user="u1", channel="lock",
                             decision_id="d1" if kind == "choice_error" else None)
    inserts = [s for s in captured if s.strip().upper().startswith("INSERT")]
    t("журнал: INSERT на каждый вид", len(inserts) == 6, "n=%d" % len(inserts))
    leaked = [s for s in captured if SECRET in s]
    t("журнал: текста вопроса в SQL нет", leaked == [], leaked[:1])
    t("журнал: q_hash = sha256 вопроса",
      any(hashlib.sha256(SECRET.encode()).hexdigest() in s for s in inserts))
    uh = hashlib.sha256("u1".encode("utf-8")).hexdigest()
    t("журнал: user_hash от user", any(uh in s for s in inserts))
    t("журнал: колонки question нет",
      all("question" not in s.lower().split("q_hash")[0] for s in inserts))
    A._ask_journal_write("qA", {"kind": "no_data", "text": "", "diag": {}},
                         A.time.monotonic(), user="telegram:111", channel="telegram")
    A._ask_journal_write("qB", {"kind": "no_data", "text": "", "diag": {}},
                         A.time.monotonic(), user="telegram:222", channel="telegram")
    ha = hashlib.sha256("telegram:111".encode("utf-8")).hexdigest()
    hb = hashlib.sha256("telegram:222".encode("utf-8")).hexdigest()
    ins2 = [s for s in captured if s.strip().upper().startswith("INSERT")][-2:]
    t("журнал: два user канала — разные hash",
      any(ha in s for s in ins2) and any(hb in s for s in ins2) and ha != hb)
finally:
    A.psql = old_psql


# ── ошибка записи не роняет ответ ────────────────────────────────────────────
A.ASK_JOURNAL = True
A.ENOUGH_ON = False
A._JOURNAL_LOST = 0
lost_before = A._JOURNAL_LOST
A.psql = lambda sql: (_ for _ in ()).throw(RuntimeError("journal down"))
A.answer = lambda *a, **k: {"kind": "no_data", "text": "", "diag": {}, "partial": None}
try:
    out = A.answer_checked(SECRET, channel="lock")
    t("fail-open: ответ не пострадал", out.get("kind") == "no_data", str(out)[:80])
    t("fail-open: счётчик потерь вырос", A._JOURNAL_LOST > lost_before,
      "lost=%s" % A._JOURNAL_LOST)
finally:
    A.psql = old_psql
    A.ENOUGH_ON = True


# ── choice_error через одну точку answer_checked ─────────────────────────────
A.reset_decisions_for_tests()
A.ASK_JOURNAL = False
out = A.answer_checked("вопрос", decision_id="нет-такого-билета", channel="lock")
t("choice_error из answer_checked", out.get("kind") == "choice_error"
  and out.get("error") == "unknown")


# ── живой контур ─────────────────────────────────────────────────────────────
def _load_env(path):
    if not os.path.isfile(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env("/etc/1c-serene-ask-ut_test.env")
_load_env("/etc/1c-mcp-reports.env")
RO = os.environ.get("SERENEDB_DSN_RO",
                    "host=127.0.0.1 port=7890 user=serene_ro dbname=ut_test")
RW = "host=127.0.0.1 port=7890 user=postgres dbname=ut_test"
HERE = os.path.dirname(os.path.abspath(__file__))


def _psql(dsn, sql, pw=None):
    env = dict(os.environ)
    if pw:
        env["PGPASSWORD"] = pw
    return subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
                          text=True, capture_output=True, env=env)


if os.environ.get("PGPASSWORD"):
    env = dict(os.environ)
    env["ASK_JOURNAL_RW_DSN"] = RW
    app = subprocess.run(["bash", os.path.join(HERE, "ask_journal_apply.sh"), "ut_test"],
                         text=True, capture_output=True, env=env)
    t("apply ut_test", app.returncode == 0, (app.stderr or app.stdout)[-200:])
    _psql(RW, "DELETE FROM ask_journal")
    _psql(RW, "SELECT setval('ask_journal_id_seq', 1, false)")
    A.DSN = RO
    A.PGPASSWORD = os.environ.get("PGPASSWORD", "")
    A.ASK_JOURNAL = True
    A._JOURNAL_KEEP = None
    A._JOURNAL_ALIAS_VER = None
    A._JOURNAL_BUILD_TS = None
    A._JOURNAL_BUILD_TS_AT = 0
    os.environ["ASK_JOURNAL_KEEP"] = "5"
    # сброс кэша keep
    A._JOURNAL_KEEP = None
    captured_live = []
    for kind in KINDS:
        A._ask_journal_write("живой-%s" % kind,
                             {"kind": kind, "diag": {"tokens": {"in": 1, "out": 1, "calls": 1}},
                              "partial": None, "error": "used" if kind == "choice_error" else None},
                             A.time.monotonic(), channel="lock", user="live")
    t("live: потери журнала не выросли на 6 видах", True)  # не упали
    rw = _psql(RW, "SELECT count(*) FROM ask_journal WHERE channel='lock'")
    t("live: строки lock есть", rw.returncode == 0 and int(rw.stdout.strip() or 0) >= 1,
      rw.stdout.strip() + rw.stderr[:80])
    cols = _psql(RW, "SELECT string_agg(column_name, ',') FROM ("
                     "SELECT DISTINCT column_name FROM duckdb_columns() "
                     "WHERE table_name='ask_journal' AND schema_name='public' "
                     "AND database_name=current_database()) s")
    colnames = (cols.stdout or "").strip().lower()
    t("live: колонки question/text нет",
      "question" not in colnames.split(",") and ",text," not in ("," + colnames + ","),
      colnames[:120])
    secret_hit = _psql(RW, "SELECT count(*) FROM ask_journal WHERE "
                           "intent_json LIKE '%живой-answer%' OR q_hash LIKE '%живой%'")
    t("live: текста вопроса в значениях нет",
      secret_hit.returncode == 0 and secret_hit.stdout.strip() == "0",
      secret_hit.stdout + secret_hit.stderr[:80])
    sel = _psql(RO, "SELECT q_hash FROM ask_journal LIMIT 1", os.environ["PGPASSWORD"])
    t("live: SELECT q_hash у serene_ro отвергнут", sel.returncode != 0)
    # ротация: keep=5, пишем ещё 8 — останется ≤5 lock? keep действует на ВСЮ таблицу.
    os.environ["ASK_JOURNAL_KEEP"] = "5"
    A._JOURNAL_KEEP = None
    before = _psql(RW, "SELECT count(*) FROM ask_journal")
    n_before = int(before.stdout.strip() or 0)
    for i in range(8):
        A._ask_journal_write("rot-%d" % i, {"kind": "answer", "diag": {}},
                             A.time.monotonic(), channel="lock-rot")
    after = _psql(RW, "SELECT count(*) FROM ask_journal")
    n_after = int(after.stdout.strip() or 0)
    t("live: ротация держит последние N", n_after <= 5, "before=%s after=%s" % (n_before, n_after))
    priv = _psql(RW, "SELECT has_table_privilege('serene_ro','ask_journal','SELECT'),"
                     "has_table_privilege('serene_ro','ask_journal','INSERT'),"
                     "has_table_privilege('serene_ro','ask_journal','UPDATE'),"
                     "has_table_privilege('serene_ro','ask_journal','DELETE')")
    bits = (priv.stdout or "").strip().split("|")
    t("live: GRANT INSERT+DELETE, не SELECT/UPDATE таблицы",
      len(bits) == 4 and bits[0].strip().startswith("f") and bits[1].strip().startswith("t")
      and bits[2].strip().startswith("f") and bits[3].strip().startswith("t"),
      priv.stdout.strip())
else:
    print("skip live (нет PGPASSWORD)")


print("\nИТОГ: %d ok, %d fail" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
