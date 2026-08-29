#!/usr/bin/env python3
"""Оффлайн: сторож corpus_merge — смена формы ключа vs коллапс vs удалённая дельта (п.13).

100 % старых ключей сущности + непустая новая сборка не меньше → пропуск с записью;
частичный уход при росте + живые Recorder в витрине → коллапс, пропуск с записью;
частичный уход + мёртвый Recorder + документ удалён → deleted_delta, пропуск;
частичный уход + мёртвый Recorder + документ жив → STOP (дефект транспорта);
частичный уход иначе или новая меньше старой → STOP.

Запуск: python3 test_corpus_merge_key_form.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(ROOT, "corpus_merge.sql")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def classify_entity(было, уйдёт, стало, *, recorder_alive=None, doc_alive=None):
    """Логика tmp3_merge_ent_guard + key_form + key_collapse + deleted_delta."""
    if было > 0 and стало < было:
        return "shrink_stop"
    if уйдёт > 0 and уйдёт < было:
        if стало > было and recorder_alive is True:
            return "collapse_ok"
        if стало > было and recorder_alive is False and doc_alive is False:
            return "deleted_delta_ok"
        if стало > было and recorder_alive is False and doc_alive is True:
            return "transport_stop"
        return "partial_stop"
    if было > 0 and уйдёт == было and стало > 0 and стало >= было:
        return "key_form_ok"
    return "ok"


def guard_count(unmatched_by_ent, exempt_ents):
    total = sum(unmatched_by_ent.values())
    exempt = sum(n for ent, n in unmatched_by_ent.items() if ent in exempt_ents)
    return total - exempt


# --- симуляция правил ---
t("key_form: 100% уход, новая больше", classify_entity(100, 100, 150) == "key_form_ok")
t("key_form: 100% уход, новая равна", classify_entity(206839, 206839, 208338) == "key_form_ok")
t("collapse: частичный уход, рост, recorder жив",
  classify_entity(75436, 23, 76000, recorder_alive=True) == "collapse_ok")
t("collapse: рост обязателен", classify_entity(100, 50, 100, recorder_alive=True) == "partial_stop")
t("deleted_delta: мёртвый recorder, документ удалён",
  classify_entity(75436, 11, 76000, recorder_alive=False, doc_alive=False) == "deleted_delta_ok")
t("transport: мёртвый recorder, документ жив",
  classify_entity(75436, 59, 76000, recorder_alive=False, doc_alive=True) == "transport_stop")
t("collapse: мёртвый recorder без doc → delta не collapse",
  classify_entity(100, 50, 120, recorder_alive=False) == "partial_stop")
t("partial: 50 из 100 без recorder", classify_entity(100, 50, 120) == "partial_stop")
t("shrink: новая меньше", classify_entity(100, 100, 80) == "shrink_stop")
t("shrink раньше key_form", classify_entity(100, 100, 50) == "shrink_stop")
t("ok: часть совпала", classify_entity(100, 0, 100) == "ok")
t("ok: новая сущность", classify_entity(0, 0, 50) == "ok")

t("guard: key_form снимает с порога",
  guard_count({"a": 100, "b": 10}, {"a"}) == 10)
t("guard: collapse тоже снимает",
  guard_count({"a": 23, "b": 10}, {"a"}) == 10)
t("guard: deleted_delta снимает",
  guard_count({"a": 11, "b": 10}, {"a"}) == 10)
t("guard: без exempt весь объём",
  guard_count({"a": 100, "b": 10}, set()) == 110)

# --- grep SQL ---
txt = open(MERGE, encoding="utf-8").read()
t("SQL: tmp3_merge_unmatched", "CREATE OR REPLACE TABLE tmp3_merge_unmatched AS" in txt)
t("SQL: tmp3_merge_ent_guard", "CREATE OR REPLACE TABLE tmp3_merge_ent_guard AS" in txt)
t("SQL: tmp3_merge_key_form", "CREATE OR REPLACE TABLE tmp3_merge_key_form AS" in txt)
t("SQL: tmp3_merge_key_collapse", "CREATE OR REPLACE TABLE tmp3_merge_key_collapse AS" in txt)
t("SQL: tmp3_merge_key_deleted_delta", "CREATE OR REPLACE TABLE tmp3_merge_key_deleted_delta AS" in txt)
t("SQL: p_collapse_dead", "PREPARE p_collapse_dead AS" in txt)
t("SQL: p_doc_alive", "PREPARE p_doc_alive AS" in txt)
t("SQL: transport_defect STOP", "дефект транспорта" in txt)
t("SQL: query_table Recorder", 'query_table($1) q WHERE q."Recorder"' in txt)
t("SQL: Period repost anti-join", "list_contains(k.key_cols, 'Period')" in txt)
t("SQL: частичная потеря STOP", "частичная потеря объектов" in txt)
t("SQL: shrink STOP", "новая сборка меньше старой" in txt)
t("SQL: search_quality entity_key_form_changed",
  "entity_key_form_changed:" in txt)
t("SQL: search_quality entity_key_collapse",
  "entity_key_collapse:" in txt)
t("SQL: search_quality entity_deleted_delta",
  "entity_deleted_delta:" in txt)
t("SQL: порог исключает key_form",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_form" in txt)
t("SQL: порог исключает key_collapse",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse" in txt)
t("SQL: порог исключает deleted_delta",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta" in txt)
t("SQL: partial исключает collapse",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_collapse k WHERE k.src_table = g.src_table)" in txt)
t("SQL: partial исключает deleted_delta",
  "NOT EXISTS (SELECT 1 FROM tmp3_merge_key_deleted_delta k WHERE k.src_table = g.src_table)" in txt)
t("SQL: нет списка таблиц",
  "informationregister_ценыноменклатуры" not in txt
  and "document_реализациятмц" not in txt)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
