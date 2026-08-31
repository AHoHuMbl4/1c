#!/usr/bin/env python3
"""Оффлайн: перенос emb при rewrite-волне без пересчёта (О4).

Пары: новая↔старая по refs (непустым, уникальным с обеих сторон).
Равенство контента: пересечение колонок doc («колонка: значение»), новые
колонки формы игнорируются. emb переносится только при доказанном равенстве.

Запуск: python3 test_corpus_merge_emb_transfer.py
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
        print("FAIL-", name, ("| " + detail)[:200] if detail else "")


def doc_bmap(doc):
    """Как corpus_doc_bmap: пары «ключ: значение» через « | »."""
    out = {}
    if not doc:
        return out
    for p in doc.split(" | "):
        i = p.find(": ")
        if i <= 0:
            continue
        out[p[:i]] = p[i + 2 :]
    return out


def bmap_common_eq(a, b):
    """Как corpus_bmap_common_eq: пересечение непусто и значения совпали."""
    common = set(a) & set(b)
    if not common:
        return False
    return all(a[k] == b[k] for k in common)


def emb_xfer(old_rows, new_rows):
    """old/new: list of dict(src_table, refs, doc, emb|row_key).

    Возвращает list of (src_table, row_key, emb) — перенесённые.
    """
    from collections import defaultdict

    old_by = defaultdict(list)
    for o in old_rows:
        refs = o.get("refs") or ""
        if not refs or o.get("emb") is None:
            continue
        old_by[(o["src_table"], refs)].append(o)

    new_by = defaultdict(list)
    for n in new_rows:
        refs = n.get("refs") or ""
        if not refs:
            continue
        new_by[(n["src_table"], refs)].append(n)

    out = []
    for key, news in new_by.items():
        olds = old_by.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        o, n = olds[0], news[0]
        if bmap_common_eq(doc_bmap(o["doc"]), doc_bmap(n["doc"])):
            out.append((n["src_table"], n["row_key"], o["emb"]))
    return out


# --- (а) смена формы без смены значений → emb перенесён ---
old_a = [{
    "src_table": "e", "refs": "Номенклатура: X | ТипЦен: 23%",
    "doc": "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100",
    "emb": [0.1],
}]
new_a = [{
    "src_table": "e", "row_key": "newsha1", "refs": "Номенклатура: X | ТипЦен: 23%",
    "doc": "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100"
           " | Организация: ООО | Пересчет: нет",
}]
xa = emb_xfer(old_a, new_a)
t("a: form-only → emb transferred", xa == [("e", "newsha1", [0.1])])
t("a: queue 0", len(new_a) - len(xa) == 0)

# --- (б) смена значения общей колонки → emb NULL ---
old_b = [{
    "src_table": "e", "refs": "Номенклатура: X | ТипЦен: 23%",
    "doc": "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100",
    "emb": [0.2],
}]
new_b = [{
    "src_table": "e", "row_key": "sha_b", "refs": "Номенклатура: X | ТипЦен: 33%",
    "doc": "установка | Номенклатура: X | ТипЦен: 33% | Цена: 100"
           " | Организация: ООО",
}]
# refs тоже сменились (значение ссылки) → пара не ищется; плюс контент другой
xb = emb_xfer(old_b, new_b)
t("b: value change via refs → no pair", xb == [])

# тот же refs (не-ссылочная колонка), другое значение общей → NULL
old_b2 = [{
    "src_table": "e", "refs": "Номенклатура: X",
    "doc": "установка | Номенклатура: X | Цена: 100 | Коммент: a",
    "emb": [0.21],
}]
new_b2 = [{
    "src_table": "e", "row_key": "sha_b2", "refs": "Номенклатура: X",
    "doc": "установка | Номенклатура: X | Цена: 149 | Коммент: a | Организация: ООО",
}]
xb2 = emb_xfer(old_b2, new_b2)
t("b: common col value differs → no xfer", xb2 == [])

# --- (в) смена refs → пара не ищется ---
old_c = [{
    "src_table": "e", "refs": "A: 1", "doc": "t | A: 1 | V: 1", "emb": [0.3],
}]
new_c = [{
    "src_table": "e", "row_key": "sha_c", "refs": "A: 2",
    "doc": "t | A: 2 | V: 1",
}]
t("c: refs changed → no xfer", emb_xfer(old_c, new_c) == [])

# --- (г) отсутствие refs → NULL ---
old_d = [{
    "src_table": "e", "refs": "", "doc": "t | V: 1", "emb": [0.4],
}]
new_d = [{
    "src_table": "e", "row_key": "sha_d", "refs": "", "doc": "t | V: 1",
}]
t("d: empty refs → no xfer", emb_xfer(old_d, new_d) == [])
old_d2 = [{
    "src_table": "e", "refs": None, "doc": "t | V: 1", "emb": [0.41],
}]
new_d2 = [{
    "src_table": "e", "row_key": "sha_d2", "refs": None, "doc": "t | V: 1",
}]
t("d: null refs → no xfer", emb_xfer(old_d2, new_d2) == [])

# --- (д) волна частично: перенесено ровно K равных ---
old_e = [
    {"src_table": "e", "refs": "r1", "doc": "t | K: a | V: 1", "emb": [1.0]},
    {"src_table": "e", "refs": "r2", "doc": "t | K: b | V: 2", "emb": [2.0]},
    {"src_table": "e", "refs": "r3", "doc": "t | K: c | V: 3", "emb": [3.0]},
    {"src_table": "e", "refs": "r4", "doc": "t | K: d | V: 4", "emb": [4.0]},
]
new_e = [
    {"src_table": "e", "row_key": "n1", "refs": "r1",
     "doc": "t | K: a | V: 1 | Org: Z"},          # equal → xfer
    {"src_table": "e", "row_key": "n2", "refs": "r2",
     "doc": "t | K: b | V: 99 | Org: Z"},         # V changed → no
    {"src_table": "e", "row_key": "n3", "refs": "r3",
     "doc": "t | K: c | V: 3 | Org: Z"},          # equal → xfer
    {"src_table": "e", "row_key": "n4", "refs": "r4x",
     "doc": "t | K: d | V: 4 | Org: Z"},          # refs changed → no
]
xe = emb_xfer(old_e, new_e)
t("e: exactly K=2 transferred", len(xe) == 2, str(xe))
t("e: keys n1 and n3",
  set(x[1] for x in xe) == {"n1", "n3"})
t("e: emb values preserved",
  {x[1]: x[2] for x in xe} == {"n1": [1.0], "n3": [3.0]})

# --- дубли refs: не переносим ---
old_dup = [
    {"src_table": "e", "refs": "rx", "doc": "t | V: 1", "emb": [9.0]},
    {"src_table": "e", "refs": "rx", "doc": "t | V: 1", "emb": [9.1]},
]
new_dup = [
    {"src_table": "e", "row_key": "nd", "refs": "rx", "doc": "t | V: 1"},
]
t("dup refs old → no xfer", emb_xfer(old_dup, new_dup) == [])

# --- живой пример пары (форма + ТипЦен) ---
live_old = (
    "установкаценноменклатуры | Номенклатура: товар | ТипЦен: 23% new energ / 141"
    " | Цена: 10"
)
live_new_form = (
    "установкаценноменклатуры | Номенклатура: товар | ТипЦен: 23% new energ / 141"
    " | Цена: 10 | Организация: База | Пересчет: Нет"
)
live_new_val = (
    "установкаценноменклатуры | Номенклатура: товар | ТипЦен: 33% new energ / 149"
    " | Цена: 10 | Организация: База | Пересчет: Нет"
)
t("live: form-only common eq",
  bmap_common_eq(doc_bmap(live_old), doc_bmap(live_new_form)))
t("live: ТипЦен change → not eq",
  not bmap_common_eq(doc_bmap(live_old), doc_bmap(live_new_val)))

# --- grep SQL ---
txt = open(MERGE, encoding="utf-8").read()
t("SQL: corpus_doc_bmap macro", "CREATE OR REPLACE MACRO corpus_doc_bmap(doc)" in txt)
t("SQL: corpus_bmap_common_eq macro",
  "CREATE OR REPLACE MACRO corpus_bmap_common_eq(a, b)" in txt)
t("SQL: tmp3_merge_emb_xfer", "CREATE OR REPLACE TABLE tmp3_merge_emb_xfer AS" in txt)
t("SQL: tmp3_merge_emb_old", "CREATE OR REPLACE TABLE tmp3_merge_emb_old AS" in txt)
t("SQL: tmp3_merge_emb_new", "CREATE OR REPLACE TABLE tmp3_merge_emb_new AS" in txt)
t("SQL: pair by refs",
  "INNER JOIN tmp3_merge_emb_old o USING (src_table, refs)" in txt)
t("SQL: unique refs HAVING", "HAVING count(*) = 1" in txt)
t("SQL: unique refs QUALIFY",
  "QUALIFY count(*) OVER (PARTITION BY src_table, refs) = 1" in txt)
t("SQL: MERGE не несёт массивы (сборка 26.07.3)",
  "SELECT s.* FROM tmp3_corpus s WHERE s.src_table IN (" in txt
  and "LEFT JOIN tmp3_merge_emb_xfer x" not in txt)
t("SQL: INSERT с NULL, перенос — после",
  "s.refs_map, NULL);" in txt)
t("SQL: пакетный UPDATE-перенос 1000",
  "tmp3_merge_emb_xfer_n" in txt and "x.n >= ' || (b * 1000)" in txt
  and "search_corpus.emb IS NULL" in txt)
t("SQL: search_quality entity_emb_xfer", "entity_emb_xfer:" in txt)
t("SQL: only rewrite_wave tables",
  "IN (SELECT src_table FROM tmp3_merge_rewrite_wave)" in txt
  and txt.count("tmp3_merge_rewrite_wave") >= 3)
# Имена живых таблиц — только в старых комментариях-замерах, не в SELECT/WHERE xfer.
xfer_body = txt.split("tmp3_merge_emb_old AS", 1)[-1].split(
    "ЗАПИСЬ — ПАЧКАМИ", 1)[0]
t("SQL: xfer block has no concrete table names",
  "document_" not in xfer_body and "informationregister_" not in xfer_body
  and "catalog_" not in xfer_body)
t("SQL: MATCHED still drops emb on hash change",
  "refs_map = s.refs_map, emb = NULL WHEN NOT MATCHED" in txt)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
