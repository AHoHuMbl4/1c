#!/usr/bin/env python3
"""Оффлайн-замок Ф6.3: same_concept_groups + ASK_SOLR_SYNONYMS / ASK_SOLR_SYNONYMS_DICT."""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
# Изоляция: флаги Ф6.3 не должны зависеть от окружения сессии.
os.environ.pop("ASK_SOLR_SYNONYMS", None)
os.environ.pop("ASK_SOLR_SYNONYMS_DICT", None)

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []
ASK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene_ask.py")
ASK_MD5 = hashlib.md5(open(ASK_PATH, "rb").read()).hexdigest()


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def with_env(**kw):
    saved = {}
    for k, v in kw.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A.ASK_SOLR_SYNONYMS = os.environ.get("ASK_SOLR_SYNONYMS", "0") == "1"
    A.ASK_SOLR_SYNONYMS_DICT = os.environ.get("ASK_SOLR_SYNONYMS_DICT", "")
    return saved


def restore_env(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    A.ASK_SOLR_SYNONYMS = os.environ.get("ASK_SOLR_SYNONYMS", "0") == "1"
    A.ASK_SOLR_SYNONYMS_DICT = os.environ.get("ASK_SOLR_SYNONYMS_DICT", "")


class Cap:
    def __init__(self, row):
        self.sql = []
        self.row = row

    def __call__(self, sql):
        self.sql.append(sql)
        # Число колонок = число ts_lexize(…) в SELECT.
        n = len(re.findall(r"ts_lexize\(", sql))
        cells = list(self.row)
        if len(cells) < n:
            cells = cells + ["{}"] * (n - len(cells))
        return [cells[:n]]


# --- умолчание ---
t("default ASK_SOLR_SYNONYMS False", A.ASK_SOLR_SYNONYMS is False)
t("default ASK_SOLR_SYNONYMS_DICT empty", A.ASK_SOLR_SYNONYMS_DICT == "")

# --- флаг off → только STEM_DICT, без solr dict в SQL ---
saved = with_env(ASK_SOLR_SYNONYMS="0", ASK_SOLR_SYNONYMS_DICT="my_solr_syn")
cap = Cap(["{а}", "{а}"])
real, A.psql = A.psql, cap
out, n = A.same_concept_groups([["Альтаир"], ["Альтаиру"]])
A.psql = real
restore_env(saved)
sql = cap.sql[-1] if cap.sql else ""
t("off: calls psql", bool(cap.sql), cap.sql)
t("off: STEM_DICT in SQL", "ts_lexize('%s'" % A.STEM_DICT in sql
                 or "ts_lexize('%s'," % A.STEM_DICT in sql
                 or ("ts_lexize('" + A.STEM_DICT + "'" in sql), sql)
t("off: no solr dict in SQL", "my_solr_syn" not in sql, sql)
t("off: merges by stem", n == 1 and len(out) == 1, (out, n))

# --- флаг on без имени словаря → как off (нет нового ts_lexize) ---
saved = with_env(ASK_SOLR_SYNONYMS="1", ASK_SOLR_SYNONYMS_DICT="")
cap = Cap(["{а}", "{а}"])
real, A.psql = A.psql, cap
A.same_concept_groups([["Альтаир"], ["Альтаиру"]])
A.psql = real
restore_env(saved)
sql = cap.sql[-1] if cap.sql else ""
t("on+empty dict: no extra dict name",
  sql.count("ts_lexize(") == 2, sql)
t("on+empty dict: only STEM",
  all(A.STEM_DICT in p for p in re.findall(r"ts_lexize\('([^']*)'", sql)), sql)

# --- флаг on + dict из env → ts_lexize(<dict>) в SQL ---
DICT = "f6_solr_syn_test"
saved = with_env(ASK_SOLR_SYNONYMS="1", ASK_SOLR_SYNONYMS_DICT=DICT)
# stem: разные; syn: общий класс → сведение по union
cap = Cap(["{остатк}", "{depozit,stoc,остатки,склад}",
           "{склад}", "{depozit,stoc,остатки,склад}"])
real, A.psql = A.psql, cap
out, n = A.same_concept_groups([["остатки"], ["склад"]])
A.psql = real
restore_env(saved)
sql = cap.sql[-1] if cap.sql else ""
t("on: STEM still in SQL", A.STEM_DICT in sql, sql)
t("on: solr dict from env in SQL",
  "ts_lexize('%s'" % DICT in sql or ("ts_lexize('" + DICT + "'" in sql), sql)
t("on: four ts_lexize (stem+syn ×2)", sql.count("ts_lexize(") == 4, sql)
t("on: merges by synonym class", n == 1 and len(out) == 1, (out, n))

# --- dict имя берётся из env, не из хардкода ---
DICT2 = "custom_syn_dict_xyz"
saved = with_env(ASK_SOLR_SYNONYMS="1", ASK_SOLR_SYNONYMS_DICT=DICT2)
cap = Cap(["{a}", "{a}", "{b}", "{b}"])
real, A.psql = A.psql, cap
A.same_concept_groups([["foo"], ["bar"]])
A.psql = real
restore_env(saved)
sql = cap.sql[-1] if cap.sql else ""
t("custom dict name in SQL", DICT2 in sql, sql)
t("no previous test dict name", DICT not in sql, sql)

print("\nmd5 serene_ask.py:", ASK_MD5)
print("Итог:", PASS, "ok,", len(FAIL), "fail")
sys.exit(1 if FAIL else 0)
