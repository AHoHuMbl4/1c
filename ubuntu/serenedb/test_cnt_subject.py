#!/usr/bin/env python3
"""Замок CNT-SUBJECT: records vs axis_values (мок ds_chat, без сети/БД)."""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
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
        print("FAIL-", name, detail)


# ── fixtures ─────────────────────────────────────────────────────────────────
SRC_REG = "accumulationregister_реализациятмц"
SRC_DOC = "document_реализациятмц"
AXIS_COL = "Контрагент"
AXIS_LAB = "Контрагенты"
SRC_LAB = "Реализация ТМЦ"
ETALON = "145"


def _restore(keys, saved):
    for k in keys:
        if k in saved:
            setattr(A, k, saved[k])


# ── parse / should_call ───────────────────────────────────────────────────────
t("parse: records", A.parse_cnt_subject('{"subject":"records"}') == "records")
t("parse: axis_values",
  A.parse_cnt_subject('{"subject": "axis_values"}') == "axis_values")
t("parse: мусор → None", A.parse_cnt_subject("not json") is None)
t("parse: чужой subject → None",
  A.parse_cnt_subject('{"subject":"rows"}') is None)
t("should_call: count+ось+регистр",
  A.cnt_subject_should_call({"want": "count"}, SRC_REG, AXIS_COL) is True)
t("should_call: пустой want+ось",
  A.cnt_subject_should_call({"want": ""}, SRC_REG, AXIS_COL) is True)
t("should_call: без оси → False",
  A.cnt_subject_should_call({"want": "count"}, SRC_REG, None) is False)
t("should_call: catalog → False",
  A.cnt_subject_should_call(
      {"want": "count"}, "catalog_контрагенты", AXIS_COL) is False)
t("should_call: sum → False",
  A.cnt_subject_should_call({"want": "sum"}, SRC_REG, AXIS_COL) is False)
# rank-guard: want=count + ранговая фраза → слой не зовём
_Q_TOP = "топ клиентов по сумме"
t("should_call: count+топ → False",
  A.cnt_subject_should_call(
      {"want": "count"}, SRC_REG, AXIS_COL, question=_Q_TOP) is False)
# defense in depth: axis_values + rank → DISTINCT-ветка выключена
_want_r = "count"
_cnt_subj_r = "axis_values"
_use_distinct_rank = (
    _cnt_subj_r == "axis_values" and AXIS_COL and SRC_REG
    and _want_r in ("count", "")
    and not A.rank_intent_from({"want": "count"}, {}, _Q_TOP))
t("rank+axis_values: DISTINCT-ветка выкл",
  _use_distinct_rank is False
  and A.rank_intent_from({"want": "count"}, {}, _Q_TOP) is True)
t("SYS в OUR_PROMPTS", A.CNT_SUBJECT_SYS in A.OUR_PROMPTS)

# ── (г) без оси → слой не зовётся ─────────────────────────────────────────────
_calls = []
_saved = {}
for k in ("ds_chat", "deadline_hit"):
    _saved[k] = getattr(A, k)


def _chat_track(messages, temperature=0, max_tokens=900):
    _calls.append(messages)
    return json.dumps({"subject": "axis_values"})


A.ds_chat = _chat_track
A.deadline_hit = lambda rid=None: False
_calls.clear()
diag_g = {}
got_g = A.resolve_cnt_subject(
    "сколько клиентов", {"want": "count"}, SRC_REG, None,
    src_label=SRC_LAB, src_kind="регистр", axis_label=AXIS_LAB, diag=diag_g)
t("(г) без оси: ds_chat=0", len(_calls) == 0, len(_calls))
t("(г) без оси: diag cnt_subject=records",
  diag_g.get("cnt_subject") == "records", diag_g)
t("(г) возврат records", got_g == "records")

# ── (а) клиенты → axis_values → DISTINCT SQL ──────────────────────────────────
_calls.clear()
diag_a = {}
A.ds_chat = lambda *a, **k: json.dumps({"subject": "axis_values"})
got_a = A.resolve_cnt_subject(
    "сколько клиентов реально покупают?", {"want": "count"}, SRC_REG, AXIS_COL,
    src_label=SRC_LAB, src_kind="регистр накопления",
    axis_label=AXIS_LAB, diag=diag_a)
t("(а) subject=axis_values", got_a == "axis_values" and diag_a.get("cnt_subject") == "axis_values")

_sql_a = []


def _psql_a(q):
    _sql_a.append(q)
    return [["145"]]


_saved["psql"] = A.psql
_saved["_num"] = A._num
A.psql = _psql_a
A._num = lambda x: float(str(x).replace(",", ".").replace(" ", "") or 0)
agg_a = A.aggregate_distinct_axis(SRC_REG, "true", [], AXIS_COL)
t("(а) form=distinct_axis", (agg_a or {}).get("form") == "distinct_axis", agg_a)
t("(а) count из SQL", (agg_a or {}).get("count") == 145, agg_a)
t("(а) SQL содержит COUNT(DISTINCT",
  any("count(DISTINCT" in (q or "").lower()
      or "count(distinct" in (q or "").lower() for q in _sql_a),
  _sql_a[:1])
t("(а) SQL содержит ось",
  any(AXIS_COL in (q or "") for q in _sql_a), _sql_a[:1])

# ── (б) документы → records → обычный COUNT ───────────────────────────────────
_calls.clear()
diag_b = {}
A.ds_chat = _chat_track


def _chat_records(messages, temperature=0, max_tokens=900):
    _calls.append(messages)
    return json.dumps({"subject": "records"})


A.ds_chat = _chat_records
got_b = A.resolve_cnt_subject(
    "сколько документов реализации за декабрь 2025?",
    {"want": "count"}, SRC_DOC, AXIS_COL,
    src_label=SRC_LAB, src_kind="документ",
    axis_label=AXIS_LAB, diag=diag_b)
t("(б) subject=records", got_b == "records" and diag_b.get("cnt_subject") == "records")
t("(б) ds_chat вызван", len(_calls) == 1)

_sql_b = []


def _psql_b(q):
    _sql_b.append(q)
    # aggregate() ждёт несколько колонок — отдаём минимум для count
    if "count(" in (q or "").lower() and "distinct" not in (q or "").lower():
        return [["3027", None, None, None, None, None, None, 0, 0]]
    return [["3027"]]


A.psql = _psql_b
# records-путь: не зовём distinct; проверяем что resolve не требует DISTINCT
t("(б) records → не axis_values", diag_b.get("cnt_subject") == "records")
# имитация ветки z20: при records distinct не строится
_use_distinct_b = diag_b.get("cnt_subject") != "records"
t("(б) ветка distinct выключена", _use_distinct_b is False)

# ── (в) мусор / исключение / deadline → fallback ──────────────────────────────
diag_c1 = {}
A.ds_chat = lambda *a, **k: "%%%not json%%%"
got_c1 = A.resolve_cnt_subject(
    "q", {"want": "count"}, SRC_REG, AXIS_COL,
    src_label=SRC_LAB, src_kind="регистр", axis_label=AXIS_LAB, diag=diag_c1)
t("(в) мусор → fallback",
  got_c1 == "records" and diag_c1.get("cnt_subject") == "fallback")

diag_c2 = {}


def _boom(*a, **k):
    raise RuntimeError("ds down")


A.ds_chat = _boom
got_c2 = A.resolve_cnt_subject(
    "q", {"want": "count"}, SRC_REG, AXIS_COL,
    src_label=SRC_LAB, src_kind="регистр", axis_label=AXIS_LAB, diag=diag_c2)
t("(в) исключение → fallback",
  got_c2 == "records" and diag_c2.get("cnt_subject") == "fallback")

diag_c3 = {}
A.deadline_hit = lambda rid=None: True
A.ds_chat = _chat_track
_calls.clear()
got_c3 = A.resolve_cnt_subject(
    "q", {"want": "count"}, SRC_REG, AXIS_COL,
    src_label=SRC_LAB, src_kind="регистр", axis_label=AXIS_LAB, diag=diag_c3)
t("(в) deadline → fallback, ds_chat=0",
  got_c3 == "records" and diag_c3.get("cnt_subject") == "fallback"
  and len(_calls) == 0, (_calls, diag_c3))
A.deadline_hit = lambda rid=None: False

# ── (д) эталон не входит в слой ───────────────────────────────────────────────
_calls.clear()
captured = []


def _chat_cap(messages, temperature=0, max_tokens=900):
    captured.append(messages)
    return json.dumps({"subject": "axis_values"})


A.ds_chat = _chat_cap
A.resolve_cnt_subject(
    "сколько клиентов реально покупают?", {"want": "count"}, SRC_REG, AXIS_COL,
    src_label=SRC_LAB, src_kind="регистр", axis_label=AXIS_LAB, diag={})
blob = json.dumps(captured, ensure_ascii=False)
t("(д) эталон отсутствует во входе", ETALON not in blob, blob[:200])
t("(д) нет gold/answer/etalon ключей",
  all(x not in blob.lower() for x in ("etalon", "gold_answer", '"answer":')),
  blob[:200])
t("(д) есть подписи вики", SRC_LAB in blob and AXIS_LAB in blob)

# ── (е) формулировка axis_values без «записей» про ось ────────────────────────
atom = A.atom_from_agg(
    {"count": 145, "sum": None, "form": "distinct_axis", "axis": AXIS_COL,
     "grain": "axis", "axis_label": AXIS_LAB},
    operation="count", grain="axis", form="distinct_axis",
    axis=AXIS_LAB, measure_label=None)
rendered = A.render_atom_pair(atom) or ""
t("(е) render содержит число и ось",
  "145" in rendered and AXIS_LAB in rendered, rendered)
t("(е) render без «записей»",
  "запис" not in rendered.lower(), rendered)

# compose body hint
body_bits = []
_orig_compose_parts = None
# Проверяем текст подсказки в compose через прямой разбор ветки form
z18 = (ROOT / "ask" / "z18_compose.py").read_text(encoding="utf-8")
t("(е) compose: hint distinct values",
  "distinct values of the chosen axis" in z18)
t("(е) compose: records hint остаётся для не-distinct",
  "number of records" in z18)

# SYS без доменных слов базы
sys_txt = A.CNT_SUBJECT_SYS
t("п.0: SYS без контрагент/клиент/реализац",
  not any(w in sys_txt.lower()
          for w in ("контрагент", "клиент", "реализац", "номенклатур")))

# ── (ж) should_call=False → diag["cnt_subject"]=="records" ────────────────────
# catalog: слой не зовём, но diag обязан совпасть с возвратом (z20 читает diag).
_calls.clear()
diag_zh = {}
A.ds_chat = _chat_track
A.deadline_hit = lambda rid=None: False
got_zh = A.resolve_cnt_subject(
    "сколько контрагентов", {"want": "count"}, "catalog_контрагенты", AXIS_COL,
    src_label="Контрагенты", src_kind="справочник",
    axis_label=AXIS_LAB, diag=diag_zh)
t("(ж) should_call=False: ds_chat=0", len(_calls) == 0, len(_calls))
t("(ж) should_call=False: diag=records",
  got_zh == "records" and diag_zh.get("cnt_subject") == "records", diag_zh)

# ── (з) later-условие: forced axis_values+rank → DISTINCT не зовётся ──────────
# Имитация later-ветки z20 при agg=None (grain=row / groups упали).
_cnt_subj_forced = "axis_values"
_later_use_distinct = (
    _cnt_subj_forced != "records"
    and not A.rank_intent_from({"want": "count"}, {}, _Q_TOP))
t("(з) later forced axis_values+rank → False",
  _later_use_distinct is False
  and A.rank_intent_from({"want": "count"}, {}, _Q_TOP) is True)

_restore(["ds_chat", "deadline_hit", "psql", "_num"], _saved)

print()
total = PASS + len(FAIL)
if FAIL:
    print("ПРОВАЛЕНО: %s/%s" % (len(FAIL), total), FAIL)
    sys.exit(1)
print("%s/0 зелёные" % PASS)
sys.exit(0)
