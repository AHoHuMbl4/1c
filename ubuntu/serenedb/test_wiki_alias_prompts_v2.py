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
ent_batch_sql = (HERE / "wiki_alias_select_entity_batch.sql").read_text(encoding="utf-8")
merge_sql = (HERE / "wiki_alias_merge_entity.sql").read_text(encoding="utf-8")

# ── (а) шесть блоков промтов «1 задача = 1 вызов» (атомы-строки, без .claude/state) ─
def _heredoc(var: str) -> str:
    m = re.search(
        rf"{re.escape(var)}=\$\(cat <<'EOF_WA_PROMPT'\n(.*?)\nEOF_WA_PROMPT",
        sh, re.S)
    return m.group(1) if m else ""


_init_a, _init_b, _init_c = _heredoc("_WA_INIT_A"), _heredoc("_WA_INIT_B"), _heredoc("_WA_INIT_C")
_coll_a, _coll_b, _coll_c = _heredoc("_WA_COLL_A"), _heredoc("_WA_COLL_B"), _heredoc("_WA_COLL_C")
t("шесть heredoc-блоков промтов на месте",
  all([_init_a, _init_b, _init_c, _coll_a, _coll_b, _coll_c]),
  (len(_init_a), len(_init_b), len(_init_c), len(_coll_a), len(_coll_b), len(_coll_c)))

_ent_once = "Every Input entity appears once; entity values copy Input exactly"
t("все шесть промтов: entity copy Input exactly (ревью владельца 14.09: COLL-B/C тоже)",
  all(_ent_once in x
      for x in (_init_a, _init_b, _init_c, _coll_a, _coll_b, _coll_c)))
t("INIT-A/B/C: Schema exact copy of Input entity string",
  all('<exact copy of Input entity string>' in x
      for x in (_init_a, _init_b, _init_c)))
t("INIT-A: лимит 3 to 10",
  "3 to 10" in _init_a)
t("INIT-B + COLL-B: no PARENTHESES WITH A COMMA INSIDE",
  "no PARENTHESES WITH A COMMA INSIDE" in _init_b
  and "no PARENTHESES WITH A COMMA INSIDE" in _coll_b)
t("INIT-C + COLL-C: hard format NEF (no commas and no parentheses)",
  "no commas and no parentheses" in _init_c
  and "no commas and no parentheses" in _coll_c)
t("collision: шаблон SHARED_WORD в A/B/C",
  all("<SHARED_WORD>" in x for x in (_coll_a, _coll_b, _coll_c)))
t("collision: подстановка WORD в A/B/C",
  '_WA_COLL_A//<SHARED_WORD>/$WORD' in sh
  and '_WA_COLL_B//<SHARED_WORD>/$WORD' in sh
  and '_WA_COLL_C//<SHARED_WORD>/$WORD' in sh)
t("COLLISION-A: DISTINCTIVE + entity exact",
  "DISTINCTIVE" in _coll_a
  and _ent_once in _coll_a
  and '<exact copy of Input entity string>' in _coll_a)

# «1 задача = 1 вызов»: на пачку — три поля (три вызова шлюза через wa_infer_field)
_tf_body = ""
if "wa_infer_three_fields()" in sh:
    _tf_body = sh.split("wa_infer_three_fields()", 1)[1].split("\nwhile :;", 1)[0]
t("1 задача=1 вызов: three_fields → aliases/best/nef",
  'aliases "$site"' in _tf_body
  and 'bestUsedFor "$site"' in _tf_body
  and 'notEnoughFor "$site"' in _tf_body
  and _tf_body.count("wa_infer_field ") == 3,
  _tf_body.count("wa_infer_field "))
t("1 задача=1 вызов: шлюз внутри wa_infer_field",
  "alias_infer_gateway.py" in sh.split("wa_infer_field()", 1)[1].split(
      "wa_infer_three_fields()", 1)[0])

# measure / dayfork — без новых маркеров INIT (тексты сайтов не менялись)
_meas_txt = ""
# вырежем measure-промт между «величины» циклом и dayfork: первый printf CLOSE IN MEANING после done_measures
_i_meas = sh.find("done_measures=0")
_i_day = sh.find("FORK CLASSES")
if _i_meas >= 0 and _i_day > _i_meas:
    _meas_txt = sh[_i_meas:_i_day]
_day_txt = sh[_i_day:_i_day + 800] if _i_day >= 0 else ""
t("measure/dayfork: без новых маркеров entity-copy",
  _ent_once not in _meas_txt
  and _ent_once not in _day_txt
  and "<exact copy of Input entity string>" not in _meas_txt
  and "FORK CLASSES" in _day_txt
  and "3 to 8" in _meas_txt,  # measure по-прежнему 3..8, не 3..10
  (_ent_once in _meas_txt, "3 to 8" in _meas_txt, "FORK CLASSES" in _day_txt))

# event-формы в A-промтах (без wordlist базы)
_event_mark = "spoken action/event form"
t("event-формы: INIT-A и COLL-A",
  _event_mark in _init_a and _event_mark in _coll_a)
for _w in ("наторговали", "сделали", "вышло", "покупают"):
    t("нет wordlist «%s»" % _w, _w not in sh)

# ── axes / rank markers в шести промтах + SQL axes ────────────────────────────
_m = "AXIS NOUNS FROM axes"
t("INIT-A: %s" % _m, _m in _init_a, "INIT-A missing: %s" % _m)
_m = "EXCEPT spoken action/event forms (rule 2) and AXIS subject nouns under rule 7"
t("INIT-A: %s" % _m, _m in _init_a, "INIT-A missing: %s" % _m)
_m = "Do " + "not copy raw dimension labels"
t("INIT-A: %s" % _m, _m in _init_a, "INIT-A missing: %s" % _m)
_m = "RANK TEMPLATES"
t("INIT-B: %s" % _m, _m in _init_b, "INIT-B missing: %s" % _m)
_m = "using a spoken axis noun from axes when present"
t("INIT-B: %s" % _m, _m in _init_b, "INIT-B missing: %s" % _m)
_m = "AXIS vs EVENT using axes"
t("INIT-C: %s" % _m, _m in _init_c, "INIT-C missing: %s" % _m)
_m = "axis master list"
t("INIT-C: %s" % _m, _m in _init_c, "INIT-C missing: %s" % _m)
_m = "not ranked event totals on the axis"
t("INIT-C: %s" % _m, _m in _init_c, "INIT-C missing: %s" % _m)
_m = "AXIS subject noun"
t("COLL-A: %s" % _m, _m in _coll_a, "COLL-A missing: %s" % _m)
_m = "ranking / top-N / best / most that THIS type alone answers"
t("COLL-B: %s" % _m, _m in _coll_b, "COLL-B missing: %s" % _m)
_m = "the shared word is an axis subject"
t("COLL-C: %s" % _m, _m in _coll_c, "COLL-C missing: %s" % _m)
_m = "AS axes"
t("select_entity_batch SQL: %s" % _m, _m in ent_batch_sql,
  "wiki_alias_select_entity_batch.sql missing: %s" % _m)
_m = "axes := axes"
t("select_entity_batch SQL: %s" % _m, _m in ent_batch_sql,
  "wiki_alias_select_entity_batch.sql missing: %s" % _m)
_m = "AS axes"
t("collision_round SQL: %s" % _m, _m in coll_sql,
  "wiki_alias_collision_round.sql missing: %s" % _m)
_m = "axes := axes"
t("collision_round SQL: %s" % _m, _m in coll_sql,
  "wiki_alias_collision_round.sql missing: %s" % _m)

# ── collision assemble (бывший H3/PY2): через assemble_field_items ────────────
import json as _json
import io as _io
from contextlib import redirect_stderr as _redir_err


def _assemble_coll(items_a, items_b, items_c, pay):
    err = _io.StringIO()
    with _redir_err(err):
        rows = P.assemble_field_items(
            _json.dumps({"items": items_a}, ensure_ascii=False),
            _json.dumps({"items": items_b}, ensure_ascii=False),
            _json.dumps({"items": items_c}, ensure_ascii=False),
            pay, site="collision")
    return rows, err.getvalue()


_deg_pay = [{"entity": "ent_a", "title": "Сущность А", "quantities": ""}]
_deg_rows, _deg_err = _assemble_coll(
    [{"entity": "ent_a", "aliases": ["ок"]}],
    [{"entity": "ent_a", "bestUsedFor": ["x", "y"]}],
    [{"entity": "ent_a", "notEnoughFor": ["z"]}],
    _deg_pay)
t("collision H3: [['ок']] → строка пропущена",
  _deg_rows == []
  and "collision row skipped (degenerate after filter): ent_a" in _deg_err
  and "kept previous" in _deg_err,
  (_deg_rows, _deg_err[:200]))

_ok_pay = [
    {"entity": "ent_a", "title": "Тип А", "quantities": ""},
    {"entity": "ent_b", "title": "Тип Б", "quantities": ""},
]
_ok_rows, _ok_err = _assemble_coll(
    [{"entity": "ent_a", "aliases": ["фраза нормальная", "вторая фраза"]},
     {"entity": "ent_b", "aliases": ["фраза нормальная", "вторая фраза"]}],
    [{"entity": "ent_a", "bestUsedFor": ["x", "y"]},
     {"entity": "ent_b", "bestUsedFor": ["x", "y"]}],
    [{"entity": "ent_a", "notEnoughFor": ["z"]},
     {"entity": "ent_b", "notEnoughFor": ["z"]}],
    _ok_pay)
t("collision H3: две нормальные фразы → обе сущности записаны",
  len(_ok_rows) == 2
  and {r["src_table"] for r in _ok_rows} == {"ent_a", "ent_b"}
  and "degenerate after filter" not in _ok_err,
  (_ok_rows, _ok_err[:200]))

_tf_pay = [{"entity": "ent_tf", "title": "Банки", "quantities": ""}]
_tf_rows, _tf_err = _assemble_coll(
    [{"entity": "ent_tf", "aliases": ["справочник"]}],
    [{"entity": "ent_tf", "bestUsedFor": ["x", "y"]}],
    [{"entity": "ent_tf", "notEnoughFor": ["z"]}],
    _tf_pay)
t("collision H3: title-fallback [title] → записан",
  len(_tf_rows) == 1
  and _tf_rows[0]["aliases"] == "Банки"
  and "degenerate after filter" not in _tf_err,
  (_tf_rows, _tf_err[:200]))

t("collision: assemble + check-field в оболочке",
  "--assemble" in sh and "--check-field" in sh
  and "wa_infer_three_fields" in sh)

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
# filter/title — в assemble_field_items (parse.py), не inline PY2 в .sh
_parse_src = (HERE / "wiki_alias_parse.py").read_text(encoding="utf-8")
t("assemble зовёт filter_entity_aliases + titles_by_entity",
  "filter_entity_aliases(" in _parse_src
  and "titles_by_entity" in _parse_src
  and "def assemble_field_items" in _parse_src)
t("оболочка collision/init идёт через --assemble",
  "--assemble" in sh and "wa_infer_three_fields" in sh)

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

# ── gateway: ALIAS_INFER_RUNTIME infer|agent (G3) ────────────────────────────
import json as _json
import alias_infer_gateway as IG  # noqa: E402

t("runtime дефолт {} → agent", IG.infer_runtime({}) == "agent")
t("runtime agent → agent",
  IG.infer_runtime({"ALIAS_INFER_RUNTIME": "agent"}) == "agent")
t("runtime иное → agent",
  IG.infer_runtime({"ALIAS_INFER_RUNTIME": "rpc"}) == "agent")

_cmd_infer = IG.build_cmd(
    message_file="/tmp/msg",
    model="vllm/x",
    thinking="off",
    prompt="hi",
    env={"ALIAS_INFER_RUNTIME": "infer"},
)
t("infer cmd (явный env) = infer model run",
  _cmd_infer[:4] == ["openclaw", "infer", "model", "run"]
  and "--prompt" in _cmd_infer
  and "openclaw agent" not in " ".join(_cmd_infer),
  _cmd_infer)
t("infer-режим без openclaw agent",
  "agent" not in _cmd_infer)

_cmd_agent = IG.build_cmd(
    message_file="/tmp/msg",
    model="vllm/x",
    thinking="off",
    env={"ALIAS_INFER_RUNTIME": "agent"},
)
t("agent cmd: --local --agent dict --message-file --json",
  _cmd_agent[:3] == ["openclaw", "agent", "--local"]
  and "--agent" in _cmd_agent
  and _cmd_agent[_cmd_agent.index("--agent") + 1] == "dict"
  and "--message-file" in _cmd_agent
  and _cmd_agent[_cmd_agent.index("--message-file") + 1] == "/tmp/msg"
  and "--json" in _cmd_agent,
  _cmd_agent)
t("agent-режим без infer model run",
  "infer" not in _cmd_agent, _cmd_agent)

# G3b: session-key на вызов + таймаут subprocess
t("agent cmd: --session-key alias-gen-",
  "--session-key" in _cmd_agent
  and _cmd_agent[_cmd_agent.index("--session-key") + 1].startswith("alias-gen-"),
  _cmd_agent)
t("agent cmd: session-key присутствует (нет argv без ключа)",
  "--session-key" in _cmd_agent
  and "--agent" in _cmd_agent
  and "--message-file" in _cmd_agent,
  _cmd_agent)
_cmd_agent_b = IG.build_cmd(
    message_file="/tmp/msg",
    model="vllm/x",
    thinking="off",
    env={"ALIAS_INFER_RUNTIME": "agent"},
)
_sk_a = _cmd_agent[_cmd_agent.index("--session-key") + 1]
_sk_b = _cmd_agent_b[_cmd_agent_b.index("--session-key") + 1]
t("session-key уникален между двумя build_cmd",
  _sk_a != _sk_b
  and _sk_a.startswith("alias-gen-")
  and _sk_b.startswith("alias-gen-"),
  (_sk_a, _sk_b))

t("timeout дефолт 1800", IG.agent_timeout_sec({}) == 1800)
t("timeout ALIAS_AGENT_TIMEOUT_SEC=7",
  IG.agent_timeout_sec({"ALIAS_AGENT_TIMEOUT_SEC": "7"}) == 7)
# замок на проводку: main() зовёт subprocess.run(..., timeout=agent_timeout_sec())
_src = Path(IG.__file__).read_text(encoding="utf-8")
t("timeout= передаётся в subprocess.run (литерал в main)",
  "timeout=timeout_sec" in _src
  and "agent_timeout_sec()" in _src
  and "TimeoutExpired" in _src,
  "timeout_sec / TimeoutExpired")
t("infer-режим: argv прежний, таймаут тот же параметр",
  _cmd_infer[:4] == ["openclaw", "infer", "model", "run"]
  and "--session-key" not in _cmd_infer
  and IG.agent_timeout_sec({}) == 1800,
  _cmd_infer)

_cmd_agent_id = IG.build_cmd(
    message_file="/tmp/msg",
    model="vllm/x",
    thinking="off",
    env={"ALIAS_INFER_RUNTIME": "agent", "ALIAS_AGENT_ID": "sandbox"},
)
t("ALIAS_AGENT_ID переопределяет агента",
  _cmd_agent_id[_cmd_agent_id.index("--agent") + 1] == "sandbox",
  _cmd_agent_id)

_ok_code, _ok_body = IG.agent_result_from_stdout(
    _json.dumps({"payloads": [{"text": "x"}], "meta": {}})
)
_ok_parsed = _json.loads(_ok_body)
t("agent parser: payloads сохранены",
  _ok_code == 0
  and _ok_parsed["payloads"][0]["text"] == "x"
  and _ok_parsed.get("meta", {}).get("transport") == "agent",
  (_ok_code, _ok_body[:120]))
_empty_fix = _json.dumps({"payloads": []})
_empty_code, _empty_body = IG.agent_result_from_stdout(_empty_fix)
t("agent parser: пустой payloads → exit 1 + сырой stdout",
  _empty_code == 1 and _empty_body == _empty_fix,
  (_empty_code, _empty_body[:120]))
_blank_fix = _json.dumps({"payloads": [{"text": "  "}]})
_blank_code, _blank_body = IG.agent_result_from_stdout(_blank_fix)
t("agent parser: пустой text → exit 1",
  _blank_code == 1 and _blank_body == _blank_fix,
  (_blank_code, _blank_body[:120]))

# ── --retry-items-json (ретрай битого items JSON в шлюзе) ─────────────────────
import tempfile as _tmpmod

t("retry-items-json: флаг в argparse (дефолт 0)",
  "--retry-items-json" in _src
  and "default=0" in _src
  and "retry-items-json" in _src,
  "flag+default=0")

# дефолт 0: валидный конверт agent + проза без items → exit 0 (как раньше)
_broken_text = "Let me think. No JSON items here."
_ok_items_text = '{"items":[{"entity":"catalog_x","aliases":["a","b"]}]}'
_agent_broken = _json.dumps({"payloads": [{"text": _broken_text}], "meta": {}})
_agent_ok = _json.dumps({"payloads": [{"text": _ok_items_text}], "meta": {}})


class _Proc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _run_gateway_main(argv, env_extra=None, fake_stdout_seq=None):
    """Вызов IG.main() с подменой subprocess.run; возвращает (rc, ans, err, calls)."""
    calls = []
    seq = list(fake_stdout_seq or [])
    idx = {"i": 0}

    def _fake_run(cmd, **kw):
        calls.append(list(cmd))
        i = idx["i"]
        idx["i"] = i + 1
        item = seq[i] if i < len(seq) else seq[-1]
        if isinstance(item, _Proc):
            return item
        return _Proc(item)

    old_run = IG.subprocess.run
    old_argv = sys.argv
    old_env = {k: os.environ.get(k) for k in (
        "ALIAS_INFER_RUNTIME", "ALIAS_AGENT_TIMEOUT_SEC",
    )}
    try:
        IG.subprocess.run = _fake_run
        if env_extra:
            for k, v in env_extra.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        with _tmpmod.TemporaryDirectory() as td:
            td = Path(td)
            msg = td / "msg"
            msg.write_text("prompt body for gateway test", encoding="utf-8")
            ans = td / "ans"
            err = td / "err"
            sys.argv = [
                "alias_infer_gateway.py",
                "--message-file", str(msg),
                "--model", "vllm/x",
                "--thinking", "off",
                "--ans", str(ans),
                "--err", str(err),
            ] + list(argv)
            rc = IG.main()
            ans_txt = ans.read_text(encoding="utf-8") if ans.exists() else ""
            err_txt = err.read_text(encoding="utf-8") if err.exists() else ""
            return rc, ans_txt, err_txt, calls
    finally:
        IG.subprocess.run = old_run
        sys.argv = old_argv
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_rc0, _ans0, _err0, _calls0 = _run_gateway_main(
    [],  # без --retry-items-json → дефолт 0
    env_extra={"ALIAS_INFER_RUNTIME": "agent"},
    fake_stdout_seq=[_agent_broken],
)
t("retry дефолт 0: битый items + валидный конверт → exit 0, 1 вызов",
  _rc0 == 0 and len(_calls0) == 1
  and "retry" not in _err0
  and _broken_text in _ans0,
  (_rc0, len(_calls0), _err0[:80], _ans0[:80]))

_rc_r, _ans_r, _err_r, _calls_r = _run_gateway_main(
    ["--retry-items-json", "2"],
    env_extra={"ALIAS_INFER_RUNTIME": "agent"},
    fake_stdout_seq=[_agent_broken, _agent_ok],
)
t("retry 2: 1-я битая → 2-я ok, exit 0, err содержит retry 1/2",
  _rc_r == 0 and len(_calls_r) == 2
  and "retry 1/2" in _err_r
  and "items" in _ans_r
  and "catalog_x" in _ans_r,
  (_rc_r, len(_calls_r), _err_r, _ans_r[:120]))
t("retry: session-key свежий на каждую попытку",
  len(_calls_r) == 2
  and "--session-key" in _calls_r[0]
  and "--session-key" in _calls_r[1]
  and _calls_r[0][_calls_r[0].index("--session-key") + 1]
  != _calls_r[1][_calls_r[1].index("--session-key") + 1],
  (_calls_r[0][_calls_r[0].index("--session-key") + 1],
   _calls_r[1][_calls_r[1].index("--session-key") + 1]))

_rc_x, _ans_x, _err_x, _calls_x = _run_gateway_main(
    ["--retry-items-json", "1"],
    env_extra={"ALIAS_INFER_RUNTIME": "agent"},
    fake_stdout_seq=[_agent_broken, _agent_broken],
)
t("retry исчерпание: обе битые → exit 1",
  _rc_x == 1 and len(_calls_x) == 2
  and "retry 1/1" in _err_x,
  (_rc_x, len(_calls_x), _err_x))

_infer_broken = _json.dumps({
    "outputs": [{"text": _broken_text}],
    "transport": "local", "provider": "vllm", "model": "x", "attempts": 0,
})
_infer_ok = _json.dumps({
    "outputs": [{"text": _ok_items_text}],
    "transport": "local", "provider": "vllm", "model": "x", "attempts": 0,
})
_rc_i, _ans_i, _err_i, _calls_i = _run_gateway_main(
    ["--retry-items-json", "2"],
    env_extra={"ALIAS_INFER_RUNTIME": "infer"},
    fake_stdout_seq=[_infer_broken, _infer_ok],
)
t("retry infer: та же items-валидация, exit 0 после ретрая",
  _rc_i == 0 and len(_calls_i) == 2
  and "retry 1/2" in _err_i
  and _calls_i[0][:4] == ["openclaw", "infer", "model", "run"]
  and "catalog_x" in _ans_i,
  (_rc_i, len(_calls_i), _err_i, _ans_i[:120]))

# R8: rc!=0 (провайдер/инфра) — без ретрая, исходный exit (не маскировать под items)
_rc_500, _ans_500, _err_500, _calls_500 = _run_gateway_main(
    ["--retry-items-json", "2"],
    env_extra={"ALIAS_INFER_RUNTIME": "agent"},
    fake_stdout_seq=[_Proc("provider error body", returncode=500, stderr="HTTP 500\n")],
)
t("retry: rc!=0 (500) при N=2 → 1 вызов, exit 500, err без retry",
  _rc_500 == 500 and len(_calls_500) == 1
  and "retry" not in _err_500
  and "items JSON invalid" not in _err_500
  and "provider error body" in _ans_500,
  (_rc_500, len(_calls_500), _err_500[:120], _ans_500[:80]))

# rc==0 + валидный items с первой попытки → без ретраев
_rc_ok1, _ans_ok1, _err_ok1, _calls_ok1 = _run_gateway_main(
    ["--retry-items-json", "2"],
    env_extra={"ALIAS_INFER_RUNTIME": "agent"},
    fake_stdout_seq=[_agent_ok],
)
t("retry: rc==0 + валидный items с 1-й → 1 вызов, exit 0, без retry",
  _rc_ok1 == 0 and len(_calls_ok1) == 1
  and "retry" not in _err_ok1
  and "catalog_x" in _ans_ok1,
  (_rc_ok1, len(_calls_ok1), _err_ok1[:80], _ans_ok1[:120]))

# проводка: --retry-items-json 2 в wa_infer_field (entity/collision/reask)
# и отдельно в measure-сайте; dayfork/branch — без флага.
_retry_n = sh.count("--retry-items-json 2")
t("wiki_alias.sh: --retry-items-json 2 ×2 (wa_infer_field + measure)",
  _retry_n == 2, _retry_n)

_br = (HERE / "branch_alias.sh").read_text(encoding="utf-8")
t("branch_alias.sh: без --retry-items-json (форма forks, не items)",
  "--retry-items-json 2" not in _br
  and "не items" in _br
  and '{"forks"' in _br,
  "comment+no-flag")

# ── R4: rc0 + 0 разобранных → mark_skip (якорь + окно, не голый grep) ─────────
# Entity: от three_fields/assemble до MERGE entity.
_i_parse_e = sh.find("wa_infer_three_fields init")
if _i_parse_e < 0:
    _i_parse_e = sh.find("wiki_alias_parse.py --assemble")
_i_merge_e = sh.find("wiki_alias_merge_entity.sql", _i_parse_e) if _i_parse_e >= 0 else -1
_win_e = sh[_i_parse_e:_i_merge_e] if _i_parse_e >= 0 and _i_merge_e > _i_parse_e else ""
t("R4 entity: окно three_fields→MERGE найдено",
  bool(_win_e), (_i_parse_e, _i_merge_e))
t("R4 entity: parse-0 → mark_skip до MERGE",
  "wiki_alias_mark_skip.sql" in _win_e
  and "rc0" in _win_e
  and "разобрано 0" in _win_e,
  _win_e[:200])

# Measure: окно от разбора после entity-MERGE до merge_measures.sql.
_i_parse_m = sh.find("python3 ./wiki_alias_parse.py", _i_merge_e) if _i_merge_e >= 0 else -1
_i_merge_m = sh.find("wiki_alias_merge_measures.sql", _i_parse_m) if _i_parse_m >= 0 else -1
_win_m = sh[_i_parse_m:_i_merge_m] if _i_parse_m >= 0 and _i_merge_m > _i_parse_m else ""
t("R4 measure: окно parse→MERGE найдено",
  bool(_win_m), (_i_parse_m, _i_merge_m))
t("R4 measure: parse-0 → mark_measure_skip до MERGE",
  "wiki_alias_mark_measure_skip.sql" in _win_m
  and "rc0" in _win_m
  and "разобрано 0" in _win_m,
  _win_m[:160])

_mark_skip = (HERE / "wiki_alias_mark_skip.sql").read_text(encoding="utf-8")
_mark_meas = (HERE / "wiki_alias_mark_measure_skip.sql").read_text(encoding="utf-8")
t("R4 mark_skip: MERGE + WHEN MATCHED UPDATE seen_at",
  "MERGE INTO" in _mark_skip
  and "WHEN MATCHED" in _mark_skip
  and "UPDATE SET seen_at" in _mark_skip
  and "WHEN NOT MATCHED THEN INSERT" in _mark_skip,
  _mark_skip[:120])
t("R4 mark_measure_skip: MERGE + WHEN MATCHED UPDATE seen_at",
  "MERGE INTO" in _mark_meas
  and "WHEN MATCHED" in _mark_meas
  and "UPDATE SET seen_at" in _mark_meas
  and "WHEN NOT MATCHED THEN INSERT" in _mark_meas,
  _mark_meas[:120])

t("R4 echo: «rc0» и «разобрано 0» в оболочке",
  "rc0" in sh and "разобрано 0" in sh,
  ("rc0" in sh, "разобрано 0" in sh))

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
