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

# ── G8a: collision V2 (H1) + PY2 инвариант записи (H3) ────────────────────────
_wa_coll_m = re.search(r"_WA_COLL='((?:[^']|'\\'')*)'", sh)
_wa_coll = _wa_coll_m.group(1) if _wa_coll_m else ""
t("collision V2: роль disambiguation engine",
  "disambiguation engine" in _wa_coll, _wa_coll[:80])
# few-shot: два типа × bestUsedFor в полном JSON (не sketch)
_fs = ""
if "Good full output:" in _wa_coll:
    _fs = _wa_coll.split("Good full output:", 1)[1].split("Bad:", 1)[0]
t("collision V2: few-shot полный JSON (два bestUsedFor)",
  _fs.count('"bestUsedFor"') == 2
  and '"entity":"ent_partners"' in _fs
  and '"entity":"ent_counterparties"' in _fs,
  (_fs.count('"bestUsedFor"'), _fs[:120]))
t("collision V2: quality over quantity",
  "quality over quantity" in _wa_coll)
# V0-маркеры — нейтральные подстроки без императивов: старое оформление
# проверяем по уникальным V0-фразам-существительным. Gate-safe промта держит
# гейт коммита (check-prompt-rules, бьёт по добавленным литералам) — в замке
# не дублируем: любой паттерн триггеров в тесте сам стал бы триггером.
_v0_meta = "platform meta-labels"
_v0_contrast = "empty contrast"
_v0_exact = "exactly 1 or 2"
t("collision V2: позитив (нет V0 meta-labels списка)",
  _v0_meta not in _wa_coll
  and "concrete everyday words a person would type" in _wa_coll)
t("collision V2: contrast в позитивной форме (whole asking-words)",
  "give contrast with whole asking-words" in _wa_coll
  and _v0_exact not in _wa_coll
  and "quality over quantity" in _wa_coll)

# H3: маркеры skip-ветки в PY2 (не в init)
_py2 = ""
if "<<'PY2'" in sh:
    _py2 = sh.split("<<'PY2'", 1)[1].split("PY2\n", 1)[0]
t("collision H3: маркер skip-ветки is_title_fb / degenerate",
  "is_title_fb" in _py2
  and "degenerate after filter" in _py2
  and "len(aliases) < 2" in _py2)
t("collision H3: лог-строка в PY2",
  "collision row skipped (degenerate after filter):" in _py2
  and "kept previous" in _py2)

# Живой вызов сборщика rows: извлекаем PY2 из sh и прогоняем фикстуры
import json as _json
import tempfile as _tf
import subprocess as _sp


def _run_collision_py2(items, pay):
    """Прогон реального PY2-heredoc из wiki_alias.sh на фикстуре."""
    assert "<<'PY2'" in sh
    body = sh.split("<<'PY2'\n", 1)[1].split("\nPY2\n", 1)[0]
    with _tf.TemporaryDirectory() as td:
        td = Path(td)
        ans = td / "ans"
        payf = td / "pay"
        rowsf = td / "rows.json"
        ans.write_text(
            _json.dumps({"payloads": [{"text": _json.dumps(
                {"items": items}, ensure_ascii=False)}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        payf.write_text(_json.dumps(pay, ensure_ascii=False), encoding="utf-8")
        r = _sp.run(
            [sys.executable, "-c", body, str(ans), str(payf), str(rowsf)],
            cwd=str(HERE),
            capture_output=True,
            text=True,
        )
        rows = _json.loads(rowsf.read_text(encoding="utf-8") or "[]")
        return rows, r.stderr, r.returncode


_deg_items = [{
    "entity": "ent_a",
    "aliases": ["ок"],
    "bestUsedFor": ["x"],
    "notEnoughFor": ["y"],
}]
_deg_pay = [{"entity": "ent_a", "title": "Сущность А", "quantities": ""}]
_deg_rows, _deg_err, _deg_rc = _run_collision_py2(_deg_items, _deg_pay)
t("collision H3: [['ок']] → строка пропущена",
  _deg_rc == 0 and _deg_rows == []
  and "collision row skipped (degenerate after filter): ent_a" in _deg_err
  and "kept previous" in _deg_err,
  (_deg_rows, _deg_err[:200], _deg_rc))

# фикстура: две сущности с ≥2 aliases len≥4 → обе записаны
_ok_items = [
    {"entity": "ent_a", "aliases": ["фраза нормальная", "вторая фраза"],
     "bestUsedFor": ["x"], "notEnoughFor": ["y"]},
    {"entity": "ent_b", "aliases": ["фраза нормальная", "вторая фраза"],
     "bestUsedFor": ["x"], "notEnoughFor": ["y"]},
]
_ok_pay = [
    {"entity": "ent_a", "title": "Тип А", "quantities": ""},
    {"entity": "ent_b", "title": "Тип Б", "quantities": ""},
]
_ok_rows, _ok_err, _ok_rc = _run_collision_py2(_ok_items, _ok_pay)
t("collision H3: две нормальные фразы → обе сущности записаны",
  _ok_rc == 0 and len(_ok_rows) == 2
  and {r["src_table"] for r in _ok_rows} == {"ent_a", "ent_b"}
  and "degenerate after filter" not in _ok_err,
  (_ok_rows, _ok_err[:200], _ok_rc))

# title-fallback [title] — валиден (одна строка = title)
_tf_items = [{
    "entity": "ent_tf",
    "aliases": ["справочник"],
    "bestUsedFor": ["x"],
    "notEnoughFor": ["y"],
}]
_tf_pay = [{"entity": "ent_tf", "title": "Банки", "quantities": ""}]
_tf_rows, _tf_err, _tf_rc = _run_collision_py2(_tf_items, _tf_pay)
t("collision H3: title-fallback [title] → записан",
  _tf_rc == 0 and len(_tf_rows) == 1
  and _tf_rows[0]["aliases"] == "Банки"
  and "degenerate after filter" not in _tf_err,
  (_tf_rows, _tf_err[:200], _tf_rc))

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

# ── gateway: ALIAS_INFER_RUNTIME infer|agent (G3) ────────────────────────────
import json as _json
import alias_infer_gateway as IG  # noqa: E402

t("runtime дефолт {} → infer", IG.infer_runtime({}) == "infer")
t("runtime agent → agent",
  IG.infer_runtime({"ALIAS_INFER_RUNTIME": "agent"}) == "agent")
t("runtime иное → infer",
  IG.infer_runtime({"ALIAS_INFER_RUNTIME": "rpc"}) == "infer")

_cmd_infer = IG.build_cmd(
    message_file="/tmp/msg",
    model="vllm/x",
    thinking="off",
    prompt="hi",
    env={},
)
t("дефолт cmd = infer model run",
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

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
