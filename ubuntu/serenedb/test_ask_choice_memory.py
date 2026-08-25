#!/usr/bin/env python3
"""Память явного выбора (план §8 шаг 6, аудит §13).

Замки:
  · клик (decision_id без memory) не пишет;
  · «запомни» пишет; повтор класса — shadow в diag, kind/text не меняются;
  · «забудь» снимает;
  · чужой пользователь / другая база не видит;
  · коллизия разных веток у разных пользователей видна в diag;
  · ошибка записи не роняет ответ.

Запуск: python3 ubuntu/serenedb/test_ask_choice_memory.py
Оффлайн без базы; живой контур — при PGPASSWORD.
"""
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_CHOICE_MEMORY", "1")

import ask_choice_mem as ACM  # noqa: E402
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


# ── отпечаток класса: набор прочтений, не выбранный src ──────────────────────
k1 = ACM.choice_class_key(["doc_a", "reg_b"], "сумма", "none")
k2 = ACM.choice_class_key(["reg_b", "doc_a"], "сумма", "none")
k3 = ACM.choice_class_key(["doc_a", "reg_b"], "количество", "none")
k4 = ACM.choice_class_key(["doc_a", "reg_b"], "сумма", "2024-01-01|2024-12-31|explicit|kept")
t("класс: порядок src не важен", k1 == k2)
t("класс: величина входит в ключ", k1 != k3)
t("класс: окно входит в ключ", k1 != k4)
t("класс: выбранный src в ключ не входит (ключ от набора)",
  "doc_a" not in k1 and len(k1) == 64)

act, q = ACM.split_memory_action("запомни так")
t("фраза без поля memory не память",
  act is None and q == "запомни так")
act, q = ACM.split_memory_action("Забудь.")
t("фраза забудь без поля не память", act is None and q == "Забудь.")
act, q = ACM.split_memory_action("сколько продали, запомни так")
t("хвост без поля не снимается",
  act is None and q == "сколько продали, запомни так")
act, q = ACM.split_memory_action("сколько продали", "remember")
t("поле memory=remember", act == "remember" and q == "сколько продали")
act, q = ACM.split_memory_action("сколько продали", "forget")
t("поле memory=forget", act == "forget" and q == "сколько продали")
act, q = ACM.split_memory_action("сколько продали")
t("обычный вопрос: не память", act is None and q == "сколько продали")
act, q = ACM.split_memory_action("", "remember")
t("пустое question + memory=remember", act == "remember" and q == "")
t("два telegram id — разные hash",
  ACM.user_hash_of("telegram:111") != ACM.user_hash_of("telegram:222")
  and len(ACM.user_hash_of("telegram:111")) == 64)
t("session fallback ≠ sender hash",
  ACM.user_hash_of("session:agent:main:openai:abc")
  != ACM.user_hash_of("telegram:111"))


class Store:
    def __init__(self):
        self.rows = {}  # (user_hash, class_key) -> dict
        self.sql = []
        self.nid = 0

    def psql(self, sql):
        self.sql.append(sql)
        u = sql.strip().upper()
        if "NEXTVAL" in u:
            self.nid += 1
            return [[str(self.nid)]]
        if u.startswith("INSERT"):
            # вытащим поля из VALUES — достаточно для замков
            return []
        if u.startswith("UPDATE") and "CANCELLED" in u:
            lits = sql.split("'")[1::2]
            uh = lits[0] if lits else ""
            ck = lits[1] if len(lits) > 1 else ""
            for row in self.rows.values():
                if (row.get("active") and row.get("user_hash") == uh
                        and row.get("class_key") == ck):
                    row["active"] = False
                    row["cancelled"] = True
            return []
        if "FROM ASK_CHOICE_MEMORY WHERE USER_HASH" in u or (
                "FROM ask_choice_memory WHERE user_hash" in sql):
            uh = None
            ck = None
            # грубый разбор литералов
            parts = sql.split("'")
            lits = parts[1::2]
            if len(lits) >= 2:
                uh, ck = lits[0], lits[1]
            row = self.rows.get((uh, ck))
            if not row or not row.get("active") or row.get("cancelled"):
                return []
            return [[row["chosen_src"], row["chosen_measure"], row["chosen_axis"],
                     row["chosen_label"], row["entity_ver"], row["readings_fp"],
                     row["window_fp"]]]
        if "COUNT(DISTINCT USER_HASH)" in u or "count(DISTINCT user_hash)" in sql:
            ck = None
            parts = sql.split("'")
            lits = parts[1::2]
            if lits:
                ck = lits[0]
            groups = {}
            for row in self.rows.values():
                if row.get("class_key") != ck or not row.get("active") or row.get("cancelled"):
                    continue
                key = (row["chosen_src"], row["chosen_measure"], row["chosen_axis"])
                groups.setdefault(key, set()).add(row["user_hash"])
            return [[a, b, c, str(len(us))] for (a, b, c), us in groups.items()]
        if "FROM SEARCH_TABLES" in u or "FROM search_tables" in sql:
            return [["document_a", "А", "", ""], ["document_b", "Б", "", ""]]
        if "search_measure_alias" in sql:
            return []
        if u.startswith("SELECT SETVAL") or u.startswith("SELECT COALESCE"):
            return [["0"]]
        return []


def _put(store, user, ck, src, measure="", axis="", label=""):
    uh = ACM.user_hash_of(user)
    store.rows[(uh, ck)] = {
        "user_hash": uh, "class_key": ck, "chosen_src": src,
        "chosen_measure": measure, "chosen_axis": axis, "chosen_label": label,
        "entity_ver": "v1", "readings_fp": "document_a|document_b",
        "window_fp": "none", "active": True, "cancelled": False,
    }


def _upsert_hook(store):
    real = ACM._memory_upsert

    def wrapped(psql, row):
        nid = real(psql, row)
        store.rows[(row["user_hash"], row["class_key"])] = dict(row, active=True,
                                                               cancelled=False)
        return nid
    return wrapped


# ── клик не пишет ────────────────────────────────────────────────────────────
st = Store()
A.reset_decisions_for_tests()
A.ASK_CHOICE_MEMORY = True
opts = [
    {"src": "document_a", "label": "Отгрузки", "found": 10},
    {"src": "document_b", "label": "Оплаты", "found": 5},
]
out0 = {"kind": "figures", "text": "пары", "options": opts,
        "diag": {"fork": {"atoms": [
            {"srcs": ["document_a"]}, {"srcs": ["document_b"]}]},
            "measure": "сумма"}}
sealed = A.seal_clarify(out0, "на какую сумму продали", user="u1")
tid = sealed["options"][0]["decision_id"]
old_up = ACM._memory_upsert
ACM._memory_upsert = _upsert_hook(st)
try:
    click = ACM.attach_choice_memory(
        sealed, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action=None,
        decision_id=tid, enabled=True, lost_box=[0])
    t("клик: INSERT не было",
      not any(s.strip().upper().startswith("INSERT") for s in st.sql),
      st.sql[:2])
    t("клик: kind/text те же",
      click.get("kind") == "figures" and click.get("text") == "пары")
    t("клик: stored нет", not (click.get("diag") or {}).get("memory", {}).get("stored"))

    # ── запомни пишет ────────────────────────────────────────────────────────
    st.sql.clear()
    rem = ACM.attach_choice_memory(
        {"kind": "answer", "text": "", "diag": {}, "options": []},
        psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action="remember",
        decision_id=tid, enabled=True, lost_box=[0])
    t("запомни: INSERT был",
      any(s.strip().upper().startswith("INSERT") for s in st.sql))
    t("запомни: stored", (rem.get("diag") or {}).get("memory", {}).get("stored") is True)
    t("запомни: kind не сменился", rem.get("kind") == "answer")

    ck = ACM.class_meta_of(sealed)["class_key"]
    t("запомни: ключ класса на билете = ключ входа",
      A.peek_decision(tid, user="u1")[0].get("class_key") == ck)

    # ── повтор: shadow, ответ не меняется ────────────────────────────────────
    again_in = {"kind": "figures", "text": "пары", "options": opts,
                "diag": {"fork": {"atoms": [
                    {"srcs": ["document_a"]}, {"srcs": ["document_b"]}]},
                    "measure": "сумма"}}
    again = ACM.attach_choice_memory(
        again_in, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action=None,
        decision_id=None, enabled=True, lost_box=[0])
    mem = (again.get("diag") or {}).get("memory") or {}
    t("повтор: kind/text не меняются",
      again.get("kind") == "figures" and again.get("text") == "пары")
    t("повтор: shadow-пометка",
      (mem.get("would_apply_text") or "").startswith("память применилась бы:"))
    t("повтор: ветка = выбранный src",
      (mem.get("would_apply") or {}).get("src") == "document_a")
    t("повтор: mode=shadow", mem.get("mode") == "shadow")

    # ── чужой пользователь не видит ──────────────────────────────────────────
    other = ACM.attach_choice_memory(
        again_in, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u2", action=None,
        enabled=True, lost_box=[0])
    om = (other.get("diag") or {}).get("memory") or {}
    t("чужой user: would_apply нет", om.get("would_apply") is None)

    # ── коллизия ─────────────────────────────────────────────────────────────
    _put(st, "u2", ck, "document_b", label="Оплаты")
    coll = ACM.attach_choice_memory(
        again_in, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action=None,
        enabled=True, lost_box=[0])
    cm = (coll.get("diag") or {}).get("memory") or {}
    t("коллизия: n_branches=2",
      (cm.get("collision") or {}).get("n_branches") == 2,
      str(cm.get("collision")))

    # ── забудь снимает ───────────────────────────────────────────────────────
    bye = ACM.attach_choice_memory(
        again_in, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action="forget",
        decision_id=tid, enabled=True, lost_box=[0])
    t("забудь: cancelled",
      (bye.get("diag") or {}).get("memory", {}).get("cancelled") is True)
    after = ACM.attach_choice_memory(
        again_in, psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action=None,
        enabled=True, lost_box=[0])
    t("забудь: would_apply снята у себя",
      ((after.get("diag") or {}).get("memory") or {}).get("would_apply") is None)

    # ── без пользователя не пишет ────────────────────────────────────────────
    st.sql.clear()
    nouser = ACM.attach_choice_memory(
        {"kind": "answer", "text": "x", "diag": {}},
        psql=st.psql, tables="search_tables",
        peek_decision=A.peek_decision, user=None, action="remember",
        decision_id=tid, enabled=True, lost_box=[0])
    t("без user: ошибка need_user",
      (nouser.get("diag") or {}).get("memory", {}).get("error") == "need_user")
    t("без user: INSERT нет",
      not any(s.strip().upper().startswith("INSERT") for s in st.sql))

    # ── ошибка SQL не роняет ответ ───────────────────────────────────────────
    def boom(_sql):
        raise RuntimeError("down")
    lost = [0]
    boom_out = ACM.attach_choice_memory(
        {"kind": "figures", "text": "целый", "diag": {}},
        psql=boom, tables="search_tables",
        peek_decision=A.peek_decision, user="u1", action="remember",
        decision_id=tid, enabled=True, lost_box=lost)
    t("fail-open: text цел", boom_out.get("text") == "целый")
    t("fail-open: счётчик потерь", lost[0] >= 1)
finally:
    ACM._memory_upsert = old_up


# ── peek used ticket ─────────────────────────────────────────────────────────
A.reset_decisions_for_tests()
sealed2 = A.seal_clarify(
    {"kind": "clarify", "text": "?", "options": opts, "diag": {}},
    "q", user="u1")
tid2 = sealed2["options"][0]["decision_id"]
A.consume_decision(tid2, "q", user="u1")
peeked, err = A.peek_decision(tid2, user="u1")
t("peek после used: билет читается", err is None and peeked.get("used") is True)
t("peek чужому: user_mismatch",
  A.peek_decision(tid2, user="u2")[1] == "user_mismatch")


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


def _clean_env():
    # Наследуемые BASH_FUNC_* (completion) роняют `set -u` в apply.sh при старте bash.
    return {k: v for k, v in os.environ.items()
            if not k.startswith("BASH_FUNC") and k not in ("BASH_ENV", "BASH_OPTS")}


def _engine_alive(dsn, timeout_sec=5):
    # Без ответа движка живой блок зависает (замер 25.08 :7890). Оффлайн уже
    # прогнан; живое помечаем отдельно, не выдаём пропуск за успех.
    try:
        p = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tAc", "SELECT 1"],
            text=True, capture_output=True, env=dict(os.environ),
            timeout=timeout_sec)
        return p.returncode == 0 and (p.stdout or "").strip() == "1"
    except subprocess.TimeoutExpired:
        return False


if os.environ.get("PGPASSWORD") and _engine_alive(RW):
    env = _clean_env()
    env["ASK_JOURNAL_RW_DSN"] = RW
    app = subprocess.run(
        ["bash", os.path.join(HERE, "ask_choice_memory_apply.sh"), "ut_test"],
        text=True, capture_output=True, env=env)
    t("apply ut_test", app.returncode == 0, (app.stderr or app.stdout)[-240:])
    _psql(RW, "DELETE FROM ask_choice_memory WHERE user_hash LIKE '%'")
    A.DSN = RO
    A.PGPASSWORD = os.environ.get("PGPASSWORD", "")
    A.ASK_CHOICE_MEMORY = True
    A.reset_decisions_for_tests()
    live_opts = [
        {"src": "document_приобретениетоваровуслуг", "label": "Документ"},
        {"src": "accumulationregister_закупки", "label": "Регистр"},
    ]
    live_out = {"kind": "figures", "text": "live-pairs",
                "options": live_opts,
                "diag": {"measure": "сумма",
                         "fork": {"atoms": [
                             {"srcs": ["document_приобретениетоваровуслуг"]},
                             {"srcs": ["accumulationregister_закупки"]}]}}}
    sealed_l = A.seal_clarify(live_out, "закупки live", user="telegram:111")
    tid_l = sealed_l["options"][0]["decision_id"]
    click_l = A.attach_memory_shadow(sealed_l, user="telegram:111", action=None,
                                     decision_id=tid_l)
    n_click = _psql(RW, "SELECT count(*) FROM ask_choice_memory")
    t("live: клик не пишет",
      n_click.returncode == 0 and int(n_click.stdout.strip() or 0) == 0,
      n_click.stdout + n_click.stderr[:80])
    rem_l = A.attach_memory_shadow(
        {"kind": "answer", "text": "", "diag": {}, "options": []},
        user="telegram:111", action="remember", decision_id=tid_l)
    t("live: запомни stored",
      (rem_l.get("diag") or {}).get("memory", {}).get("stored") is True,
      str((rem_l.get("diag") or {}).get("memory")))
    n_rem = _psql(RW, "SELECT count(*) FROM ask_choice_memory WHERE active")
    t("live: строка есть",
      n_rem.returncode == 0 and int(n_rem.stdout.strip() or 0) >= 1,
      n_rem.stdout + n_rem.stderr[:80])
    shadow = A.attach_memory_shadow(live_out, user="telegram:111", action=None)
    sm = (shadow.get("diag") or {}).get("memory") or {}
    t("live: shadow would_apply, text тот же",
      shadow.get("text") == "live-pairs"
      and (sm.get("would_apply_text") or "").startswith("память применилась бы:"),
      str(sm)[:200])
    other_l = A.attach_memory_shadow(live_out, user="telegram:222", action=None)
    t("live: чужой user не видит",
      ((other_l.get("diag") or {}).get("memory") or {}).get("would_apply") is None)
    # коллизия: второй пользователь помнит другую ветку со СВОИМ билетом
    sealed_u2 = A.seal_clarify(dict(live_out), "закупки live", user="telegram:222")
    tid_u2 = sealed_u2["options"][1]["decision_id"]
    rem_u2 = A.attach_memory_shadow(
        {"kind": "answer", "text": "", "diag": {}, "options": []},
        user="telegram:222", action="remember", decision_id=tid_u2)
    t("live: u2 запомнил другую ветку",
      (rem_u2.get("diag") or {}).get("memory", {}).get("stored") is True,
      str((rem_u2.get("diag") or {}).get("memory")))
    coll_l = A.attach_memory_shadow(live_out, user="telegram:111", action=None)
    clm = (coll_l.get("diag") or {}).get("memory") or {}
    t("live: коллизия двух веток",
      (clm.get("collision") or {}).get("n_branches") == 2,
      str(clm.get("collision")))
    bye_l = A.attach_memory_shadow(live_out, user="telegram:111", action="forget",
                                   decision_id=tid_l)
    t("live: забудь cancelled",
      (bye_l.get("diag") or {}).get("memory", {}).get("cancelled") is True)
    after_l = A.attach_memory_shadow(live_out, user="telegram:111", action=None)
    t("live: после забудь would_apply нет",
      ((after_l.get("diag") or {}).get("memory") or {}).get("would_apply") is None)
    priv = _psql(RW, "SELECT has_table_privilege('serene_ro','ask_choice_memory','SELECT'),"
                     "has_table_privilege('serene_ro','ask_choice_memory','INSERT'),"
                     "has_table_privilege('serene_ro','ask_choice_memory','UPDATE'),"
                     "has_table_privilege('serene_ro','ask_choice_memory','DELETE')")
    bits = (priv.stdout or "").strip().split("|")
    t("live: GRANT SELECT+INSERT+UPDATE, не DELETE",
      len(bits) == 4 and bits[0].strip().startswith("t")
      and bits[1].strip().startswith("t") and bits[2].strip().startswith("t")
      and bits[3].strip().startswith("f"),
      priv.stdout.strip())
    cols = _psql(RW, "SELECT string_agg(column_name, ',') FROM ("
                     "SELECT DISTINCT column_name FROM duckdb_columns() "
                     "WHERE table_name='ask_choice_memory' AND schema_name='public' "
                     "AND database_name=current_database()) s")
    colnames = (cols.stdout or "").strip().lower()
    t("live: колонки question нет",
      "question" not in colnames.split(","),
      colnames[:120])
    # postgres: той же строки нет (таблица другой базы)
    env = _clean_env()
    env["ASK_JOURNAL_RW_DSN"] = "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
    app2 = subprocess.run(
        ["bash", os.path.join(HERE, "ask_choice_memory_apply.sh"), "postgres"],
        text=True, capture_output=True, env=env)
    t("apply postgres", app2.returncode == 0, (app2.stderr or app2.stdout)[-200:])
    pg = _psql("host=127.0.0.1 port=7890 user=postgres dbname=postgres",
               "SELECT count(*) FROM ask_choice_memory")
    t("чужая база: строк telegram:111 нет (или таблица пуста этой памятью)",
      pg.returncode == 0 and int(pg.stdout.strip() or 0) == 0,
      pg.stdout + pg.stderr[:80])
elif os.environ.get("PGPASSWORD"):
    print("skip live (движок не отвечает — требует живого контура)")
else:
    print("skip live (нет PGPASSWORD)")



# ── apply=0 vs apply=1 ───────────────────────────────────────────────────────
t("apply_notice из записи",
  ACM.apply_notice_text({"label": "Отгрузки", "measure": "сумма"})
  == "помню: Отгрузки / сумма")
apply_opts = [
    {"src": "document_a", "label": "Отгрузки", "found": 10},
    {"src": "document_b", "label": "Оплаты", "found": 5},
]
probe_out = {"kind": "figures", "text": "пары", "options": apply_opts,
             "diag": {"fork_outcome": "B", "fork": {"atoms": [
                 {"srcs": ["document_a"]}, {"srcs": ["document_b"]}]},
                      "measure": "сумма"}}
ck_apply = ACM.class_meta_of(probe_out)["class_key"]
st_apply = Store()
_put(st_apply, "u1", ck_apply, "document_a", label="Отгрузки")
st_apply.rows[(ACM.user_hash_of("u1"), ck_apply)]["entity_ver"] = ""
pr = ACM.probe_memory_apply(probe_out, psql=st_apply.psql, tables="search_tables", user="u1")
t("probe: can_apply без коллизии", pr.get("can_apply") is True, str(pr))
sh = ACM.attach_choice_memory(
    dict(probe_out), psql=st_apply.psql, tables="search_tables",
    peek_decision=A.peek_decision, user="u1", enabled=True, lost_box=[0])
t("apply=0: kind/text не меняются",
  sh.get("kind") == "figures" and sh.get("text") == "пары")
t("apply=0: mode=shadow", ((sh.get("diag") or {}).get("memory") or {}).get("mode") == "shadow")
_put(st_apply, "u2", ck_apply, "document_b", label="Оплаты")
pr_coll = ACM.probe_memory_apply(probe_out, psql=st_apply.psql, tables="search_tables", user="u1")
t("probe: коллизия → can_apply false",
  pr_coll.get("can_apply") is False and pr_coll.get("reason") == "collision")
fin = ACM.finish_apply({"kind": "answer", "text": "1 234,56 руб.", "diag": {}}, pr)
t("finish_apply: помню в text",
  (fin.get("text") or "").startswith("помню: Отгрузки"))
t("finish_apply: diag applied",
  ((fin.get("diag") or {}).get("memory") or {}).get("applied") is True)
pr_other = ACM.probe_memory_apply(probe_out, psql=st_apply.psql, tables="search_tables", user="u9")
t("probe: чужой user miss", pr_other.get("can_apply") is False)

print("\nИТОГ: %d ok, %d fail" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
