#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Офлайн-замок И0: etalon_1c без сети и без psql.

Держит: разбор OData, сравнение чисел, классификацию расхождений,
генерацию client-gold, отсутствие зашитых имён контура в исходнике."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from decimal import Decimal
from urllib.parse import unquote, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import etalon_1c as E  # noqa: E402

PASS = 0
FAIL = []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


t("count: plain int", E.parse_odata_count("17") == 17)
t("count: bytes", E.parse_odata_count(b"25") == 25)
t("count: json value", E.parse_odata_count("{\"value\": 8}") == 8)
t("count: @odata.count", E.parse_odata_count("{\"@odata.count\": 42}") == 42)
t("count: quoted", E.parse_odata_count("\"100\"") == 100)

rows = E.parse_odata_value_rows({"value": [{"Ref_Key": "a", "IsFolder": False}, {"Ref_Key": "b", "IsFolder": True}]})
t("value rows: len", len(rows) == 2)
t("value rows: field", rows[0]["Ref_Key"] == "a")
try:
    E.parse_odata_value_rows({"no": 1})
    t("value без поля падает", False)
except ValueError:
    t("value без поля падает", True)

t("equal ints", E.numbers_equal(17, 17))
t("equal decimal str", E.numbers_equal("21188510.49", Decimal("21188510.49")))
t("equal within kopeck", E.numbers_equal("10.001", "10.004"))
t("unequal", not E.numbers_equal(17, 25))
t("comma decimal", E.numbers_equal("1 234,50", "1234.50"))

# Относительный период — словарь period_relative_forms.json (как в ask), не regex.
if hasattr(E, "period_relative_forms"):
    forms = E.period_relative_forms()
    t("forms: словарь загружен", isinstance(forms, dict) and len(forms) >= 1, forms)
    t(
        "rel: фраза из словаря",
        E.is_relative_period("оборот за прошлую неделю"),
    )
    t(
        "rel: вчера без словаря/hint → нет",
        not E.is_relative_period("Сколько продали вчера?"),
    )
    t(
        "rel: inject forms",
        E.is_relative_period("foo bar baz", forms={"x": ["bar baz"]}),
    )
else:
    t("forms: словарь загружен", False, "period_relative_forms отсутствует")
    t("rel: фраза из словаря", False, "нет словаря")
    t("rel: вчера без словаря/hint → нет", False, "старый regex")
    t("rel: inject forms", False, "нет параметра forms")
t("rel: hint", E.is_relative_period("что угодно", "relative"))
t("stable: партнёры", not E.is_relative_period("Сколько у нас партнёров?", "stable"))
t("stable: hint closed", not E.is_relative_period("вчера?", "closed"))

c = E.classify_discrepancy(17, 17, 25, question="Сколько у нас складов?")
t("склады: declared_wrong", c.status == E.STATUS_DECLARED_WRONG, c)
t("склады: independent read", c.needs_independent_read is True)

c = E.classify_discrepancy(164, 164, 164, question="Сколько партнёров?")
t("партнёры: match", c.status == E.STATUS_MATCH)

c = E.classify_discrepancy(100, 90, question="Сколько продали вчера?", period_hint="relative")
t("вчера: freshness_lag", c.status == E.STATUS_FRESHNESS_LAG, c)
t("вчера: не independent", c.needs_independent_read is False)

c = E.classify_discrepancy(100, 90, question="Сколько продали вчера?", period_hint="relative", just_after_tick=True)
t("вчера сразу после такта: mismatch", c.status == E.STATUS_MISMATCH, c)
t("вчера сразу: independent", c.needs_independent_read is True)

c = E.classify_discrepancy(100, 90, question="Сколько партнёров?")
t("stable mismatch", c.status == E.STATUS_MISMATCH)
t("stable mismatch → read", c.needs_independent_read is True)

c = E.classify_discrepancy(5, None, question="Сколько организаций?")
t("только 1С: pending", c.status == E.STATUS_PENDING)

META = """<edmx:Edmx><Schema><EntityContainer Name=\"standard\">
<EntitySet Name=\"Catalog_Склады\" EntityType=\"standard.Catalog_Склады\"/>
<EntitySet Name=\"Catalog_Партнеры\" EntityType=\"standard.Catalog_Партнеры\"/>
<EntitySet Name=\"Document_РеализацияТоваровУслуг\" EntityType=\"standard.Document_РеализацияТоваровУслуг\"/>
<EntitySet Name=\"AccumulationRegister_ТоварыНаСкладах\" EntityType=\"standard.AccumulationRegister_ТоварыНаСкладах\"/>
</EntityContainer></Schema></edmx:Edmx>"""

sets = E.parse_metadata_entity_sets(META)
t("metadata entity sets", sets == ["Catalog_Склады", "Catalog_Партнеры", "Document_РеализацияТоваровУслуг", "AccumulationRegister_ТоварыНаСкладах"], sets)

meta_q = E.generate_questions_from_metadata(sets)
t("meta: только Catalog+Document по умолчанию", len(meta_q) == 3, len(meta_q))
t("meta: вопрос складов", any("Склады" in r["question"] for r in meta_q))
t("meta: source=metadata", all(r["etalon_source"] == E.ETALON_SOURCE_METADATA for r in meta_q))
t("meta: status pending", all(r["verify_status"] == E.STATUS_PENDING for r in meta_q))

jour = E.generate_questions_from_journal(["Сколько у нас партнёров?", "сколько у нас партнёров?", "Что купили вчера?"])
t("journal: дедуп", len(jour) == 2, jour)
t("journal: source", jour[0]["etalon_source"] == E.ETALON_SOURCE_JOURNAL)

merged = E.merge_gold_rows(jour, meta_q)
tsv = E.format_client_gold_tsv(merged)
parsed = E.parse_client_gold_tsv(tsv)
t("tsv header+rows", len(parsed) == len(merged))
t("tsv columns", set(parsed[0]) == {"question", "etalon", "etalon_source", "verify_status"})
t("tsv starts with header", tsv.splitlines()[0] == "question\tetalon\tetalon_source\tverify_status")

_WAREHOUSE_ROWS = [
    {"Ref_Key": "1", "IsFolder": False},
    {"Ref_Key": "2", "IsFolder": False},
    {"Ref_Key": "3", "IsFolder": True},
    {"Ref_Key": "4", "IsFolder": False},
    {"Ref_Key": "5", "IsFolder": True},
]


def _fixture_get(path_and_query):
    raw = path_and_query.split("?", 1)
    path = unquote(raw[0])
    qs = parse_qs(raw[1]) if len(raw) > 1 else {}
    if path.endswith("/$count"):
        entity = path.strip("/").split("/")[0]
        if entity == "Catalog_Склады":
            filt = (qs.get("$filter") or [""])[0]
            if "IsFolder eq false" in filt:
                return b"3"
            if "IsFolder eq true" in filt:
                return b"2"
            return b"5"
        if entity == "Catalog_Партнеры":
            return b"164"
        raise ValueError("unknown entity count " + entity)
    if path.strip("/") == "Catalog_Склады":
        return json.dumps({"value": list(_WAREHOUSE_ROWS)}, ensure_ascii=False).encode("utf-8")
    if path.strip("/") == "Document_РеализацияТоваровУслуг":
        return json.dumps({"value": [{"СуммаДокумента": "100.50"}, {"СуммаДокумента": "200.25"}]}, ensure_ascii=False).encode("utf-8")
    if path == "/$metadata":
        return META.encode("utf-8")
    raise ValueError("unexpected path " + path_and_query)


odata = E.ODataClient("http://fixture.example", get_bytes=_fixture_get)
t("fixture count all", odata.count("Catalog_Склады") == 5)
t("fixture count folders", odata.count("Catalog_Склады", "IsFolder eq true") == 2)
t("fixture count items", odata.count("Catalog_Склады", "IsFolder eq false") == 3)

spec_wh = E.SliceSpec.from_dict({
    "id": "wh",
    "question": "Сколько у нас складов?",
    "period": "stable",
    "declared": 25,
    "odata": {"entity": "Catalog_Склады", "op": "count", "filter": "IsFolder eq false"},
    "corpus": {"sql": "SELECT 3"},
})


def _sql_ok(sql):
    if "SELECT 3" in sql:
        return "0|3\n" if "slice_i" in sql else "3\n"
    return "0|0\n" if "slice_i" in sql else "0\n"


corpus = E.CorpusClient("host=127.0.0.1 port=9 user=x dbname=x", run_sql=_sql_ok)
res = E.verify_slice(spec_wh, odata, corpus)
t("verify: odata 3", res.odata_value == 3, res.to_dict())
t("verify: corpus 3", res.corpus_value == 3)
t("verify: declared_wrong", res.classification.status == E.STATUS_DECLARED_WRONG, res.to_dict())

spec_sum = E.SliceSpec.from_dict({
    "question": "Сумма реализации",
    "odata": {"entity": "Document_РеализацияТоваровУслуг", "op": "sum", "field": "СуммаДокумента"},
    "corpus": {"sql": "SELECT 300.75"},
})


def _sql_sum(sql):
    return "0|300.75\n" if "slice_i" in sql else "300.75\n"


res2 = E.verify_slice(spec_sum, odata, E.CorpusClient("x", run_sql=_sql_sum))
t("sum odata", res2.odata_value == Decimal("300.75"), res2.odata_value)
t("sum match", res2.classification.status == E.STATUS_MATCH)

spec_local = E.SliceSpec.from_dict({
    "question": "склады без групп",
    "odata": {
        "entity": "Catalog_Склады",
        "op": "count",
        "local_filter": {"field": "IsFolder", "equals": False},
        "select": "Ref_Key,IsFolder",
    },
})
res3 = E.verify_slice(spec_local, odata, None)
t("local_filter count", res3.odata_value == 3, res3.to_dict())

spec_rel = E.SliceSpec.from_dict({
    "question": "Сколько продали вчера?",
    "period": "relative",
    "odata": {"entity": "Catalog_Партнеры", "op": "count"},
    "corpus": {"sql": "SELECT 100"},
})


def _sql_100(sql):
    return "0|100\n" if "slice_i" in sql else "100\n"


res4 = E.verify_slice(spec_rel, odata, E.CorpusClient("x", run_sql=_sql_100))
t("e2e freshness_lag", res4.classification.status == E.STATUS_FRESHNESS_LAG, res4.to_dict())

gold_rows = E.results_to_gold_rows([res, res2])
t("gold source 1c", gold_rows[0]["etalon_source"] == E.ETALON_SOURCE_1C)
t("gold etalon from 1c", str(gold_rows[0]["etalon"]) == "3")
queue = E.independent_read_queue([res, res2])
t("independent queue has declared_wrong", len(queue) == 1 and queue[0]["status"] == E.STATUS_DECLARED_WRONG)

with tempfile.TemporaryDirectory() as td:
    meta_path = os.path.join(td, "meta.xml")
    jour_path = os.path.join(td, "jour.tsv")
    out_path = os.path.join(td, "client-gold.tsv")
    open(meta_path, "w", encoding="utf-8").write(META)
    open(jour_path, "w", encoding="utf-8").write("Живой вопрос из журнала?\n")
    rc = E.main(["generate", "--metadata-xml", meta_path, "--journal-tsv", jour_path, "--out", out_path, "--kinds", "Catalog,Document"])
    t("generate rc", rc == 0)
    body = open(out_path, encoding="utf-8").read()
    got = E.parse_client_gold_tsv(body)
    t("generate: journal first-ish", got[0]["question"] == "Живой вопрос из журнала?")
    t("generate: has metadata rows", len(got) >= 4)

src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etalon_1c.py")
src = open(src_path, encoding="utf-8").read()
hits = E.source_has_hardcoded_base(src)
t("исходник без литералов контура", hits == [], hits)

fake3 = "SERENEDB_DSN=host=127.0.0.1 port=7890 user=postgres dbname=" + "ok" + "na" + "\n"
# contiguous form for detector:
fake3 = "SERENEDB_DSN=host=127.0.0.1 port=7890 user=postgres dbname=okna\n"
t("детектор ловит dbname=okna", "dbname=okna" in E.source_has_hardcoded_base(fake3))

fake4 = "unit = \"1c-serene-ask@okna\"\n"
t("детектор ловит unit", len(E.source_has_hardcoded_base(fake4)) > 0)

filtered = E.filter_rows_local(_WAREHOUSE_ROWS, {"field": "IsFolder", "equals": False})
t("filter local non-folders", len(filtered) == 3)

# --- Ф1 / п.20: N срезов → один запуск клиента корпуса ---
_N = 5
_batch_calls = {"n": 0}


def _batch_run_sql(sql):
    _batch_calls["n"] += 1
    # Ожидаем один UNION ALL-запрос со slice_i; иначе — имитация N отдельных.
    lines = []
    if "slice_i" in sql and "UNION ALL" in sql:
        for i in range(_N):
            lines.append("%d|%d" % (i, 100 + i))
    else:
        # старый путь: один scalar SELECT → одна ячейка
        lines.append("0")
    return "\n".join(lines) + "\n"


_batch_specs = [
    E.SliceSpec.from_dict({
        "id": "b%d" % i,
        "question": "batch slice %d" % i,
        "period": "stable",
        "corpus": {"sql": "SELECT %d" % (100 + i)},
    })
    for i in range(_N)
]
_batch_corpus = E.CorpusClient("x", run_sql=_batch_run_sql)
if hasattr(E, "verify_slices"):
    _batch_res = E.verify_slices(_batch_specs, None, _batch_corpus)
else:
    _batch_res = [
        E.verify_slice(s, None, _batch_corpus) for s in _batch_specs
    ]
t(
    "N срезов → 1 запуск клиента",
    _batch_calls["n"] == 1,
    "calls=%s want=1" % _batch_calls["n"],
)
t(
    "batch: значения на месте",
    len(_batch_res) == _N
    and all(_batch_res[i].corpus_value == (100 + i) for i in range(_N)),
    [r.corpus_value for r in _batch_res],
)

# Построение батч-SQL (если есть) — N веток, один текст.
if hasattr(E, "build_corpus_batch_sql"):
    _bsql = E.build_corpus_batch_sql(["SELECT 1", "SELECT 2", "SELECT 3"])
    t(
        "batch sql: одна конструкция UNION ALL",
        _bsql.count("UNION ALL") == 2 and "slice_i" in _bsql,
        _bsql[:200],
    )
else:
    t("batch sql: одна конструкция UNION ALL", False, "build_corpus_batch_sql отсутствует")

# cmd_verify обязан звать verify_slices, а не цикл verify_slice
_cmd = src
_i_verify = _cmd.find("def cmd_verify")
_i_next = _cmd.find("\ndef cmd_", _i_verify + 1)
_cmd_body = _cmd[_i_verify:_i_next if _i_next > 0 else None]
t(
    "cmd_verify → verify_slices",
    "verify_slices(" in _cmd_body and "verify_slice(" not in _cmd_body,
    _cmd_body[:300],
)

# (б) в исходнике нет языкового списка слов для периодов
t(
    "исходник без языкового списка периодов",
    "period_relative_forms" in src
    and "_RELATIVE_PERIOD_RE" not in src
    and "вчера|позавчера|сегодня" not in src,
    "forms=%s RE=%s lit=%s"
    % (
        "period_relative_forms" in src,
        "_RELATIVE_PERIOD_RE" in src,
        "вчера|позавчера|сегодня" in src,
    ),
)

print()
print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)

