#!/usr/bin/env python3
"""Оффлайн B0: search_changed_rows — витринный ключ, gone и регистр без Ref_Key.

Замок: key_text через '|', enrichment LineNumber, delta INSERT, gone=deleted_gone
с ref_key агента; регистр без Ref_Key — EXISTS в дельте, не Ref_Key в gone-DELETE.

Запуск: python3 test_corpus_merge_gone_register.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "packet"))
import packet_apply as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


mart_doc = ["Ref_Key", "DataVersion", "LineNumber", "Номенклатура_Key"]
mart_reg = ["Recorder", "Recorder_Type", "Period", "LineNumber", "Количество"]

t("enrich: документ без Recorder — без LineNumber",
  A._enrich_key_cols(["Ref_Key"], mart_doc) == ["Ref_Key"])
t("enrich: регистр + LineNumber в витрине",
  A._enrich_key_cols(["Recorder", "Recorder_Type"], mart_reg)
  == ["Recorder", "Recorder_Type", "LineNumber"])
t("enrich: LineNumber уже в ключе — не дублируем",
  A._enrich_key_cols(["Recorder", "LineNumber"], mart_reg)
  == ["Recorder", "LineNumber"])

t("key_text: Ref_Key|LineNumber",
  A._key_text_expr(mart_doc, ["Ref_Key", "LineNumber"])
  == "coalesce(CAST(\"Ref_Key\" AS VARCHAR), '') || '|' || "
     "coalesce(CAST(\"LineNumber\" AS VARCHAR), '')")
t("key_text: lower колонки витрины",
  A._key_text_expr(["ref_key", "linenumber"], ["Ref_Key", "LineNumber"])
  == "coalesce(CAST(\"ref_key\" AS VARCHAR), '') || '|' || "
     "coalesce(CAST(\"linenumber\" AS VARCHAR), '')")
t("key_text: один сегмент",
  A._key_text_expr(mart_doc, ["Ref_Key"])
  == "coalesce(CAST(\"Ref_Key\" AS VARCHAR), '')")

s = A._delta_delete_clause("accumulationregister_x", mart_reg)
t("регистр: DELETE EXISTS, не Ref_Key",
  "EXISTS" in s and "Recorder" in s and "Ref_Key" not in s, s)

src = open(os.path.join(ROOT, "..", "packet", "packet_apply.py"), encoding="utf-8").read()
t("delta: INSERT search_changed_rows из d_",
  "INSERT INTO search_changed_rows" in src and "FROM \"d_" in src
  and "delta" in src)
t("delta: key_text concat в SELECT",
  "_key_text_expr" in src and "|| '|' ||" in src)
t("gone: deleted_gone в INSERT",
  "deleted_gone" in src and "INSERT INTO search_changed_rows" in src)
t("gone: ref_key агента как key_text",
  "deleted_gone" in src and "v.k" in src)
t("gone: комментарий полной B",
  "будущая полная B" in src)
t("gone: DELETE по Ref_Key прежний",
  'DELETE FROM "%s" WHERE "Ref_Key" IN' in src)
t("ensure: DDL search_changed_rows с ts",
  "search_changed_rows" in src and "ts TIMESTAMP DEFAULT now()" in src)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
