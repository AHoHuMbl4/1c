#!/usr/bin/env python3
"""Оффлайн: перенос emb при rewrite-волне + стабильность content_hash (О4).

Карта xfer: (A) уникальный content_hash; (B) уникальные refs + пересечение
колонок doc (форма с новыми заполненными полями). Смена формы при тех же
значениях общих колонок → emb живёт (тот же row_key) или спасается картой.

Запуск: python3 test_corpus_merge_emb_transfer.py
"""
import hashlib
import os
import sys
from collections import defaultdict

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
    out = {}
    if not doc:
        return out
    for p in doc.split(" | "):
        i = p.find(": ")
        if i <= 0:
            continue
        out[p[:i]] = p[i + 2 :]
    return out


def content_hash(doc):
    m = doc_bmap(doc)
    parts = []
    for k in sorted(m):
        if k in ("DataVersion", "__metadata"):
            continue
        if "navigationLinkUrl" in k:
            continue
        if m[k] == "":
            continue
        parts.append(k + "\x01" + m[k])
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def bmap_common_eq(a, b):
    common = set(a) & set(b)
    if not common:
        return False
    return all(a[k] == b[k] for k in common)


def emb_xfer(old_rows, new_rows):
    """Пары: content_hash (prio 1) или unique refs + common_eq (prio 2)."""
    def ch_of(r):
        return r.get("content_hash") or content_hash(r.get("doc") or "")

    old_by_ch = defaultdict(list)
    old_by_refs = defaultdict(list)
    for o in old_rows:
        if o.get("emb") is None:
            continue
        old_by_ch[(o["src_table"], ch_of(o))].append(o)
        refs = o.get("refs") or ""
        if refs:
            old_by_refs[(o["src_table"], refs)].append(o)

    new_by_ch = defaultdict(list)
    new_by_refs = defaultdict(list)
    for n in new_rows:
        new_by_ch[(n["src_table"], ch_of(n))].append(n)
        refs = n.get("refs") or ""
        if refs:
            new_by_refs[(n["src_table"], refs)].append(n)

    best = {}  # (src, row_key) -> (prio, emb)
    for key, news in new_by_ch.items():
        olds = old_by_ch.get(key, [])
        if len(olds) == 1 and len(news) == 1:
            n = news[0]
            best[(n["src_table"], n["row_key"])] = (1, olds[0]["emb"])
    for key, news in new_by_refs.items():
        olds = old_by_refs.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        o, n = olds[0], news[0]
        if not bmap_common_eq(doc_bmap(o["doc"]), doc_bmap(n["doc"])):
            continue
        k = (n["src_table"], n["row_key"])
        if k not in best or best[k][0] > 2:
            best[k] = (2, o["emb"])
    return [(st, rk, emb) for (st, rk), (_p, emb) in sorted(best.items())]


# --- (а) форма: порядок / пустые / шум → content_hash равен ---
doc_a_old = "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100"
doc_a_ord = "установка | Цена: 100 | ТипЦен: 23% | Номенклатура: X"
doc_a_empty = "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100 | Организация: "
doc_a_noise = "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100 | DataVersion: 9"
t("a: reorder content_hash equal",
  content_hash(doc_a_old) == content_hash(doc_a_ord))
t("a: empty col ignored",
  content_hash(doc_a_old) == content_hash(doc_a_empty))
t("a: platform noise ignored",
  content_hash(doc_a_old) == content_hash(doc_a_noise))
t("a: same row_key + equal hash → xfer pair exists (no-op keep)",
  emb_xfer(
      [{"src_table": "e", "row_key": "k1", "refs": "r", "doc": doc_a_old, "emb": [0.1]}],
      [{"src_table": "e", "row_key": "k1", "refs": "r", "doc": doc_a_ord}],
  ) == [("e", "k1", [0.1])])

# форма с НОВОЙ заполненной колонкой → хэш другой, common_eq спасает по refs
doc_a_form = (
    "установка | Номенклатура: X | ТипЦен: 23% | Цена: 100"
    " | Организация: ООО | Пересчет: нет"
)
t("a: filled form col → content_hash differs",
  content_hash(doc_a_old) != content_hash(doc_a_form))
t("a: filled form + common_eq via refs → xfer",
  emb_xfer(
      [{"src_table": "e", "row_key": "old", "refs": "Номенклатура: X | ТипЦен: 23%",
        "doc": doc_a_old, "emb": [0.1]}],
      [{"src_table": "e", "row_key": "newsha1", "refs": "Номенклатура: X | ТипЦен: 23%",
        "doc": doc_a_form}],
  ) == [("e", "newsha1", [0.1])])
t("a: wave equal-hash (reorder) → xfer by content_hash",
  emb_xfer(
      [{"src_table": "e", "row_key": "old", "doc": doc_a_old, "emb": [0.1]}],
      [{"src_table": "e", "row_key": "newsha1", "doc": doc_a_ord}],
  ) == [("e", "newsha1", [0.1])])

# --- (б) смена значения → нет xfer ---
doc_b_old = "установка | Номенклатура: X | Цена: 100 | Коммент: a"
doc_b_new = "установка | Номенклатура: X | Цена: 149 | Коммент: a | Организация: ООО"
t("b: value change → content_hash differs",
  content_hash(doc_b_old) != content_hash(doc_b_new))
t("b: value change → no xfer (common_eq false)",
  emb_xfer(
      [{"src_table": "e", "row_key": "o", "refs": "Номенклатура: X",
        "doc": doc_b_old, "emb": [0.21]}],
      [{"src_table": "e", "row_key": "sha_b2", "refs": "Номенклатура: X",
        "doc": doc_b_new}],
  ) == [])

# --- дубли ---
t("dup content_hash → no xfer",
  emb_xfer(
      [{"src_table": "e", "row_key": "o1", "doc": "t | V: 1", "emb": [9.0]},
       {"src_table": "e", "row_key": "o2", "doc": "t | V: 1", "emb": [9.1]}],
      [{"src_table": "e", "row_key": "nd", "doc": "t | V: 1"}],
  ) == [])

# --- волна частично ---
old_e = [
    {"src_table": "e", "row_key": "o1", "refs": "r1", "doc": "t | K: a | V: 1", "emb": [1.0]},
    {"src_table": "e", "row_key": "o2", "refs": "r2", "doc": "t | K: b | V: 2", "emb": [2.0]},
    {"src_table": "e", "row_key": "o3", "refs": "r3", "doc": "t | K: c | V: 3", "emb": [3.0]},
    {"src_table": "e", "row_key": "o4", "refs": "r4", "doc": "t | K: d | V: 4", "emb": [4.0]},
]
new_e = [
    {"src_table": "e", "row_key": "n1", "refs": "r1", "doc": "t | V: 1 | K: a"},  # reorder
    {"src_table": "e", "row_key": "n2", "refs": "r2", "doc": "t | K: b | V: 99 | Org: Z"},
    {"src_table": "e", "row_key": "n3", "refs": "r3", "doc": "t | K: c | V: 3 | Org: Z"},  # form
    {"src_table": "e", "row_key": "n4", "refs": "r4x", "doc": "t | K: d | V: 4 | Org: Z"},
]
xe = emb_xfer(old_e, new_e)
t("e: exactly K=2 transferred", len(xe) == 2, str(xe))
t("e: keys n1 and n3", set(x[1] for x in xe) == {"n1", "n3"}, str(xe))
t("e: emb values preserved",
  {x[1]: x[2] for x in xe} == {"n1": [1.0], "n3": [3.0]})

# --- live ---
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
t("live: form filled → hash differs, common_eq true",
  content_hash(live_old) != content_hash(live_new_form)
  and bmap_common_eq(doc_bmap(live_old), doc_bmap(live_new_form)))
t("live: ТипЦен change → not common_eq",
  not bmap_common_eq(doc_bmap(live_old), doc_bmap(live_new_val)))

# --- grep SQL ---
txt = open(MERGE, encoding="utf-8").read()
t("SQL: corpus_doc_bmap macro", "CREATE OR REPLACE MACRO corpus_doc_bmap(doc)" in txt)
t("SQL: corpus_content_hash macro",
  "CREATE OR REPLACE MACRO corpus_content_hash(doc)" in txt)
t("SQL: corpus_bmap_common_eq macro",
  "CREATE OR REPLACE MACRO corpus_bmap_common_eq(a, b)" in txt)
t("SQL: tmp3_merge_emb_xfer", "CREATE OR REPLACE TABLE tmp3_merge_emb_xfer AS" in txt)
t("SQL: pair by content_hash",
  "INNER JOIN tmp3_merge_emb_old o USING (src_table, content_hash)" in txt)
t("SQL: pair by refs fallback",
  "INNER JOIN tmp3_merge_emb_old_refs o USING (src_table, refs)" in txt)
t("SQL: common_eq in xfer", "corpus_bmap_common_eq(n.bmap, o.bmap)" in txt)
t("SQL: MERGE keeps emb on common_eq form",
  "corpus_bmap_common_eq(corpus_doc_bmap(t.doc), corpus_doc_bmap(s.doc))" in txt
  and "THEN t.emb ELSE NULL END" in txt)
t("SQL: MATCHED on content_hash",
  "WHEN MATCHED AND t.content_hash IS DISTINCT FROM s.content_hash" in txt)
t("SQL: INSERT с NULL, перенос — после", "s.refs_map, NULL);" in txt)
t("SQL: пакетный UPDATE-перенос 1000",
  "tmp3_merge_emb_xfer_n" in txt and "x.n >= ' || (b * 1000)" in txt)
t("SQL: only rewrite_wave tables",
  "IN (SELECT src_table FROM tmp3_merge_rewrite_wave)" in txt)
t("SQL: content_hash column beside doc_hash",
  "ADD COLUMN IF NOT EXISTS content_hash VARCHAR" in txt)
xfer_body = txt.split("tmp3_merge_emb_old AS", 1)[-1].split("ЗАПИСЬ — ПАЧКАМИ", 1)[0]
t("SQL: xfer block has no concrete table names",
  "document_" not in xfer_body and "informationregister_" not in xfer_body
  and "catalog_" not in xfer_body)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
