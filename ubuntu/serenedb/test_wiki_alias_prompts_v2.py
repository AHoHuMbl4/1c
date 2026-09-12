#!/usr/bin/env python3
"""Оффлайн-замок промтов v2 генератора словаря (G1 / P7). Без базы и сети."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wiki_alias_parse as P  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


sh = (HERE / "wiki_alias.sh").read_text(encoding="utf-8")
coll_sql = (HERE / "wiki_alias_collision_round.sql").read_text(encoding="utf-8")
merge_sql = (HERE / "wiki_alias_merge_entity.sql").read_text(encoding="utf-8")

# ── (а) три printf init + collision markers ──────────────────────────────────
init_hits = [
    m.group(0)
    for m in re.finditer(r"printf '%s' \"JSON only[^\n]*CLOSE IN MEANING[^\n]*\"", sh)
]
# init may span one line; also catch via BANS count
bans_n = sh.count("BANS for aliases")
# Маркер хвоста init-промта P7 (без императива в литерале: замок ищет
# уникальную подстроку этой фразы — в wiki_alias.sh она ровно в хвосте ×3).
never_n = sh.count("English example strings")
thematic_n = sh.count("THEMATIC")
old_n = sh.count("also the record title itself")
t("init×3: маркер BANS", bans_n == 3, bans_n)
t("init×3: no-EN-copy маркер (P7)", never_n == 3, never_n)
t("init×3: THEMATIC", thematic_n >= 3, thematic_n)
t("старый маркер title itself отсутствует", old_n == 0, old_n)
t("collision: шаблон SHARED_WORD", "<SHARED_WORD>" in sh)
t("collision: подстановка WORD", "${_WA_COLL//<SHARED_WORD>/$WORD}" in sh)
t("collision: DISTINCTIVE в промте", "DISTINCTIVE" in sh)

# ── (б) filter_entity_aliases meta ───────────────────────────────────────────
got = P.filter_entity_aliases(
    ["список", "справочник", "тмц", "склад", "номенклатура", "покупатель"])
t("meta ru целиком уходит; тмц/склад/номенклатура остаются",
  "список" not in [x.casefold() for x in got]
  and "справочник" not in [x.casefold() for x in got]
  and "тмц" in [x.casefold() for x in got]
  and "склад" in [x.casefold() for x in got]
  and "номенклатура" in [x.casefold() for x in got]
  and "покупатель" in [x.casefold() for x in got],
  got)

got_en = P.filter_entity_aliases(["Catalog", "list", "buyers", "warehouse"])
t("meta en целиком уходит; buyers/warehouse остаются",
  all(x.casefold() not in {"catalog", "list"} for x in got_en)
  and "buyers" in [x.casefold() for x in got_en]
  and "warehouse" in [x.casefold() for x in got_en],
  got_en)

got_phrase = P.filter_entity_aliases(["список складов", "catalog of goods", "тмц"])
t("мета-токен внутри фразы вырезается",
  any("склад" in x.casefold() for x in got_phrase)
  and any("goods" in x.casefold() for x in got_phrase)
  and not any(x.casefold() == "список" for x in got_phrase)
  and "тмц" in [x.casefold() for x in got_phrase],
  got_phrase)

got_qty = P.filter_entity_aliases(
    ["клиент", "ИтогПоля"],
    quantity_names=["ИтогПоля"],
    quantity_aliases=["сумма поля"])
t("quantities-бан по-прежнему; мета не трогает quantity path отдельно",
  got_qty == ["клиент"], got_qty)

sole_tit = P.filter_entity_aliases(["справочник"], title="Банки")
t("title-fallback: только мета + title → [title]",
  sole_tit == ["Банки"], sole_tit)

sole_empty = P.filter_entity_aliases(["справочник"], title=None)
t("title-fallback: только мета без title → []",
  sole_empty == [], sole_empty)

sole_empty2 = P.filter_entity_aliases(["список", "каталог"], title="")
t("title-fallback: все мета + пустой title → []",
  sole_empty2 == [], sole_empty2)

got_hyphen = P.filter_entity_aliases(["список-клиентов"])
t("нормализация: список-клиентов → клиентов",
  got_hyphen == ["клиентов"], got_hyphen)

got_comma = P.filter_entity_aliases(["цена, список"])
t("нормализация: цена, список без qty → цена",
  got_comma == ["цена"], got_comma)

got_comma_qty = P.filter_entity_aliases(["цена, список"], quantity_names=["цена"])
t("нормализация: цена, список + qty=цена → отброс",
  got_comma_qty == [], got_comma_qty)

got_qty_phrase = P.filter_entity_aliases(
    ["сумма список"], quantity_names=["сумма"])
t("qty-ban на этапе чистки: сумма список + qty → []",
  got_qty_phrase == [], got_qty_phrase)

got_qty_title = P.filter_entity_aliases(
    ["сумма список"], quantity_names=["сумма"], title="Счета")
t("qty-ban опустошил + title → [title]",
  got_qty_title == ["Счета"], got_qty_title)

got_edge_dot = P.filter_entity_aliases(["список."], title="X")
t("краевая пунктуация: список. → отброс → title",
  got_edge_dot == ["X"], got_edge_dot)

got_edge_bang = P.filter_entity_aliases(["список!"], title="X")
t("краевая пунктуация: список! → отброс → title",
  got_edge_bang == ["X"], got_edge_bang)

got_edge_mdash = P.filter_entity_aliases(["—список"], title="X")
t("краевая пунктуация: —список → отброс → title",
  got_edge_mdash == ["X"], got_edge_mdash)

got_keep_hyphen = P.filter_entity_aliases(["по-русски"])
t("без выреза: по-русски нетронутым",
  got_keep_hyphen == ["по-русски"], got_keep_hyphen)

got_keep_slash = P.filter_entity_aliases(["и/или"])
t("без выреза: и/или нетронутым",
  got_keep_slash == ["и/или"], got_keep_slash)

got_keep_biz = P.filter_entity_aliases(["бизнес-процесс"])
t("без выреза: бизнес-процесс как есть",
  got_keep_biz == ["бизнес-процесс"], got_keep_biz)

got_dedup = P.filter_entity_aliases(["список клиентов", "клиентов"])
t("дедуп после чистки: список клиентов + клиентов → один",
  got_dedup == ["клиентов"], got_dedup)

got_paren = P.filter_entity_aliases(["каталог (товаров)"])
t("нормализация: каталог (товаров) → товаров",
  got_paren == ["товаров"], got_paren)

got_quotes = P.filter_entity_aliases(["„список“"])
t("нормализация: голое „список“ → отброс",
  got_quotes == [], got_quotes)

# ── G1d / R5: склейка остатка с исходными разделителями ──────────────────────
got_r5_hyphen = P.filter_entity_aliases(["по-русски список"])
t("R5: по-русски список → по-русски (дефис сохранён)",
  got_r5_hyphen == ["по-русски"], got_r5_hyphen)

got_r5_slash = P.filter_entity_aliases(["и/или список"])
t("R5: и/или список → и/или (слэш сохранён)",
  got_r5_slash == ["и/или"], got_r5_slash)

got_r5_edge_hyphen = P.filter_entity_aliases(["список-клиентов"])
t("R5: список-клиентов → клиентов (краевой дефис убран)",
  got_r5_edge_hyphen == ["клиентов"], got_r5_edge_hyphen)

got_r5_spaces = P.filter_entity_aliases(["список  складов"])
t("R5: список  складов → складов",
  got_r5_spaces == ["складов"], got_r5_spaces)

got_r5_edge_dot = P.filter_entity_aliases(["клиент список."])
t("R5: клиент список. → клиент",
  got_r5_edge_dot == ["клиент"], got_r5_edge_dot)

# ── G1d / R6-1: title-fallback после ЛЮБОГО фильтра ───────────────────────────
got_r6_sole_qty = P.filter_entity_aliases(
    ["сумма"], quantity_names=["сумма"], title="Счета")
t("R6-1: сумма + qty + title → [Счета]",
  got_r6_sole_qty == ["Счета"], got_r6_sole_qty)

got_r6_sole_qty_no = P.filter_entity_aliases(
    ["сумма"], quantity_names=["сумма"])
t("R6-1: сумма + qty без title → []",
  got_r6_sole_qty_no == [], got_r6_sole_qty_no)

# ── G1d / R6-2: unicode-невидимки и NFKC ──────────────────────────────────────
got_r6_shy = P.filter_entity_aliases(["спи\u00adсок клиентов"])
t("R6-2: soft-hyphen в стоп-слове → клиентов",
  got_r6_shy == ["клиентов"], got_r6_shy)

got_r6_zwsp = P.filter_entity_aliases(["список\u200bклиентов"])
t("R6-2: ZWSP между стоп и словом → клиентов",
  got_r6_zwsp == ["клиентов"], got_r6_zwsp)

got_r6_fw = P.filter_entity_aliases(["ｌｉｓｔ"])
t("R6-2: fullwidth list → drop",
  got_r6_fw == [], got_r6_fw)

# ── G1e / R7: схлоп разделителей, NFKC только на матч, _ как sep ──────────────
got_r7_slash = P.filter_entity_aliases(["склад/список/товар"])
t("R7: склад/список/товар → склад/товар",
  got_r7_slash == ["склад/товар"], got_r7_slash)

got_r7_space = P.filter_entity_aliases(["склад список товар"])
t("R7: склад список товар → склад товар",
  got_r7_space == ["склад товар"], got_r7_space)

got_r7_hyphen = P.filter_entity_aliases(["склад-список-товар"])
t("R7: склад-список-товар → склад-товар",
  got_r7_hyphen == ["склад-товар"], got_r7_hyphen)

got_r7_num = P.filter_entity_aliases(["№5"])
t("R7: №5 без NFKC на остатке",
  got_r7_num == ["№5"], got_r7_num)

got_r7_sq = P.filter_entity_aliases(["м²"])
t("R7: м² без NFKC на остатке",
  got_r7_sq == ["м²"], got_r7_sq)

got_r7_doc = P.filter_entity_aliases(["документ №12"])
t("R7: документ №12 → №12 (документ=стоп)",
  got_r7_doc == ["№12"], got_r7_doc)

got_r7_us = P.filter_entity_aliases(["список_клиентов"])
t("R7: список_клиентов → клиентов",
  got_r7_us == ["клиентов"], got_r7_us)

got_r7_us_keep = P.filter_entity_aliases(["по_русски"])
t("R7: по_русски без меты → как есть",
  got_r7_us_keep == ["по_русски"], got_r7_us_keep)

# ── G1d: multi-word qty — точный бан, не по словам (канон §3.1) ───────────────
got_mw_qty = P.filter_entity_aliases(
    ["сколько продали сегодня"],
    quantity_aliases=["сколько продали"])
t("§3.1: multi-word qty не режет слова фразы",
  got_mw_qty == ["сколько продали сегодня"], got_mw_qty)

# quantities array в parse_items не проходит через meta на самих quantity aliases
PAY = [{"entity": "catalog_x", "title": "X", "quantities": "Q1"}]
TEXT = '''{"items":[{"entity":"catalog_x","aliases":["список","товар"],
 "quantities":[{"name":"Q1","aliases":["список","остаток"]}],
 "bestUsedFor":["a"],"notEnoughFor":["b"]}]}'''
ents, meas = P.parse_items(TEXT, PAY)
t("parse: entity meta уходит, quantity aliases целы (не meta-фильтр)",
  "список" not in (ents[0]["aliases"] if ents else "")
  and "товар" in (ents[0]["aliases"] if ents else "")
  and any("список" in (r["aliases"] or "") for r in meas),
  (ents, meas))

PAY_META = [{"entity": "catalog_y", "title": "Банки", "quantities": ""}]
TEXT_META = '''{"items":[{"entity":"catalog_y","aliases":["справочник"],
 "quantities":[],"bestUsedFor":["a"],"notEnoughFor":["b"]}]}'''
ents_m, _ = P.parse_items(TEXT_META, PAY_META)
t("parse: title из пачки → fallback при опустошении",
  (ents_m[0]["aliases"] if ents_m else "") == "Банки", ents_m)

# ── (в) collision Input JSON: word + aliases ─────────────────────────────────
t("collision SQL: поле word", "word := p.alias" in coll_sql)
t("collision SQL: текущие aliases", "aliases := coalesce(a.aliases" in coll_sql)
t("collision SQL: best_used_for", "best_used_for := coalesce(a.best_used_for" in coll_sql)
t("collision SQL: not_enough_for", "not_enough_for := coalesce(a.not_enough_for" in coll_sql)
t("collision SQL: JOIN alias_table", "LEFT JOIN :alias_table a ON a.src_table" in coll_sql)
t("collision parse зовёт filter_entity_aliases",
  "from wiki_alias_parse import filter_entity_aliases" in sh)
t("collision parse передаёт title из pay",
  "titles_by_entity" in sh and "title=title_by.get" in sh)

# ── (г) merge force: два текста различаются условием MATCHED ─────────────────
t("merge SQL: условие force",
  "OR :force = 1" in merge_sql
  and "coalesce(t.aliases,'') = ''" in merge_sql)

sql0 = re.sub(r":force\b", "0", merge_sql)
sql1 = re.sub(r":force\b", "1", merge_sql)
# выделим WHEN MATCHED строки entity-MERGE (первая)
def matched_line(s):
    for line in s.splitlines():
        if "WHEN MATCHED" in line and "measure" not in line.lower():
            return line
    return ""

m0, m1 = matched_line(sql0), matched_line(sql1)
t("force=0/1: MATCHED-строки различаются", m0 != m1 and "0 = 1" in m0 and "1 = 1" in m1,
  (m0, m1))
norm0 = re.sub(r"OR 0 = 1", "OR FORCE", sql0)
norm1 = re.sub(r"OR 1 = 1", "OR FORCE", sql1)
t("force=0/1: различаются ровно подстановкой force в MATCHED",
  norm0 == norm1 and sql0 != sql1)

merge_meas = (HERE / "wiki_alias_merge_measures.sql").read_text(encoding="utf-8")
t("merge measures: условие force",
  "OR :force = 1" in merge_meas
  and "coalesce(t.aliases,'') = ''" in merge_meas)
mm0 = re.sub(r":force\b", "0", merge_meas)
mm1 = re.sub(r":force\b", "1", merge_meas)

def matched_any(s):
    for line in s.splitlines():
        if "WHEN MATCHED" in line:
            return line
    return ""

mm_line0, mm_line1 = matched_any(mm0), matched_any(mm1)
t("merge measures force=0/1: MATCHED различаются",
  mm_line0 != mm_line1 and "0 = 1" in mm_line0 and "1 = 1" in mm_line1,
  (mm_line0, mm_line1))
mm_n0 = re.sub(r"OR 0 = 1", "OR FORCE", mm0)
mm_n1 = re.sub(r"OR 1 = 1", "OR FORCE", mm1)
t("merge measures force=0/1: различаются ровно подстановкой",
  mm_n0 == mm_n1 and mm0 != mm1)

t("WIKI_ALIAS_FORCE проводка в оболочке",
  'WIKI_ALIAS_FORCE="${WIKI_ALIAS_FORCE:-0}"' in sh
  and '-v force="$WIKI_ALIAS_FORCE"' in sh)

t("alias_infer_gateway: --temperature заглушка",
  "--temperature" in (HERE / "alias_infer_gateway.py").read_text(encoding="utf-8"))

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
