#!/usr/bin/env python3
"""Оффлайн-проба разбора словаря: БЕЗ базы, БЕЗ сети, БЕЗ модели.

Имена выдуманы: проба не знает ни одной настоящей базы. Держит инварианты,
без которых словарь врёт с первого такта:

  * имя поля, которого не было во входе, в таблицу величин не попадает;
  * пустой алиас — не ответ (это попытка, её пишет осечка пачки, а не разбор);
  * обиходные слова из ответа модели доходят до aliases сущности;
  * имена величин и их алиасы из ответа в aliases сущности не пишутся.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki_alias_parse as P  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


PAY = [{"entity": "document_отгрузкапробная", "title": "Отгрузка Пробная",
        "quantities": "ИтогПробный, СуммаКартойПробная, Курс"}]

TEXT = """
{"items":[{
  "entity":"document_отгрузкапробная",
  "aliases":["отгрузка пробная","продажа"],
  "quantities":[
    {"name":"ИтогПробный","aliases":["оборот","сумма продаж","итог"]},
    {"name":"суммакартойпробная","aliases":["оплата картой","карта"]},
    {"name":"ВыдуманноеПоле","aliases":["секретный итог"]},
    {"name":"Курс","aliases":[]}
  ],
  "bestUsedFor":["сколько отгрузили"],
  "notEnoughFor":["книга продаж"]
}]}
"""

ents, meas = P.parse_items(TEXT, PAY)
by = {(r["src_table"], r["measure"]): r["aliases"] for r in meas}

t("сущность разобрана", len(ents) == 1 and ents[0]["src_table"] == "document_отгрузкапробная")
t("каноническое имя величины сохранено дословно",
  by.get(("document_отгрузкапробная", "ИтогПробный")) == "оборот | сумма продаж | итог")
t("имя в другом регистре сводится к канону из входа, а не пишется как выдумала модель",
  by.get(("document_отгрузкапробная", "СуммаКартойПробная")) == "оплата картой | карта"
  and "суммакартойпробная" not in {r["measure"] for r in meas})
t("🔴 выдуманное имя величины отброшено",
  not any(r["measure"] == "ВыдуманноеПоле" for r in meas), meas)
t("пустой алиас — не ответ, в таблицу не идёт (Курс без слов)",
  "Курс" not in {r["measure"] for r in meas}, meas)
t("во входе три поля, в словарь попали только два описанных",
  len(meas) == 2, meas)

ents2, meas2 = P.parse_items("not json at all", PAY)
t("неразбираемый ответ — пустые списки, а не исключение",
  ents2 == [] and meas2 == [])

t("канон: точное имя из списка",
  P.canon_measure("ИтогПробный", ["ИтогПробный", "Курс"]) == "ИтогПробный")
t("канон: выдумка — None",
  P.canon_measure("Секрет", ["ИтогПробный"]) is None)

# ── обиходные слова сущности vs мусор величин (дефект словаря 25.08) ──────────
# Паттерн живого срыва: модель клала title + склонения + имена реквизитов в
# aliases, а обиход («покупатель») либо не просила, либо теряла. Здесь — выдуманная
# сущность; слова не из боевой базы.
PAY_H = [{"entity": "catalog_партнёрыпробные", "title": "Партнёры Пробные",
          "quantities": "ДниОтсрочкиПробные, ЛимитКредитаПробный"}]

TEXT_H = """
{"items":[{
  "entity":"catalog_партнёрыпробные",
  "aliases":["Партнёры Пробные","партнёр пробный","покупатель","клиент пробный",
             "ДниОтсрочкиПробные","дни отсрочки пробные","лимит кредита"],
  "quantities":[
    {"name":"ДниОтсрочкиПробные","aliases":["дни отсрочки пробные","отсрочка"]},
    {"name":"ЛимитКредитаПробный","aliases":["лимит кредита","кредитный лимит"]}
  ],
  "bestUsedFor":["кто покупает"],
  "notEnoughFor":["другой каталог"]
}]}
"""

ents_h, meas_h = P.parse_items(TEXT_H, PAY_H)
alias_csv = (ents_h[0]["aliases"] if ents_h else "") or ""
alias_set = {a.strip().casefold() for a in P._alias_tokens(alias_csv)}

t("обиходное слово из ответа доходит до aliases сущности",
  "покупатель" in alias_set and "клиент пробный" in alias_set, alias_csv)
t("title сущности в aliases сохраняется",
  "партнёры пробные" in alias_set, alias_csv)
t("🔴 имя величины из входа не пишется в aliases сущности",
  "дниотсрочкипробные" not in alias_set, alias_csv)
t("🔴 алиас величины из ответа не пишется в aliases сущности",
  "дни отсрочки пробные" not in alias_set
  and "лимит кредита" not in alias_set
  and "кредитный лимит" not in alias_set, alias_csv)
t("величины при этом получили свои обиходные слова",
  len(meas_h) == 2
  and any("отсрочка" in (r["aliases"] or "") for r in meas_h)
  and any("кредитный лимит" in (r["aliases"] or "") for r in meas_h), meas_h)

got = P.filter_entity_aliases(
    ["Title", "human word", "FieldName", "field nickname"],
    quantity_names=["FieldName"],
    quantity_aliases=["field nickname"])
t("filter_entity_aliases: обиход остаётся, мусор величин уходит",
  got == ["Title", "human word"], got)
t("filter_entity_aliases: пустой ответ — пустой список",
  P.filter_entity_aliases([], quantity_names=["X"]) == [])
t("filter_entity_aliases: дубликаты схлопываются без учёта регистра",
  P.filter_entity_aliases(["Alpha", "alpha", "Beta"]) == ["Alpha", "Beta"])

# ── обрезанный ответ (лимит токенов вызова; живой случай окна 28.08) ────────
TEXT_TRUNC = """{
  "items": [
    {"entity":"catalog_пробный","aliases":["Пробный","проба"],
     "quantities":[],"bestUsedFor":["t"],"notEnoughFor":["n"]},
    {"entity":"catalog_второй","aliases":["Второй","вт","обре
"""
ents_t, _ = P.parse_items(TEXT_TRUNC, {"items": []})
t("🔴 обрезанный JSON: целые элементы спасаются, а не теряются пачкой",
  len(ents_t) == 1 and ents_t[0]["src_table"] == "catalog_пробный", ents_t)
t("salvage: пустой/без items — пусто, не исключение",
  P._salvage_items("{}") == [] and P._salvage_items("xx") == [])

# ── G6: «1 задача = 1 вызов» — --check-field / --assemble / сторож entity ─────
# PY2/extract в .sh убраны: разбор поля и сборка — CLI wiki_alias_parse.
import io
import json as _json
import tempfile
from contextlib import redirect_stderr, redirect_stdout

_PAY_G6 = [
    {"entity": "ent_a", "title": "Тип А", "quantities": ""},
    {"entity": "ent_b", "title": "Тип Б", "quantities": ""},
]

_ANS_A = _json.dumps({
    "items": [
        {"entity": "ent_a", "aliases": ["фраза нормальная", "вторая фраза", "третья"]},
        {"entity": "ent_b", "aliases": ["слово длинное", "ещё одно", "третье слово"]},
    ]
}, ensure_ascii=False)
_ANS_B = _json.dumps({
    "items": [
        {"entity": "ent_a", "bestUsedFor": ["как считать", "кто купил"]},
        {"entity": "ent_b", "bestUsedFor": ["сколько было", "когда закрыли"]},
    ]
}, ensure_ascii=False)
_ANS_C = _json.dumps({
    "items": [
        {"entity": "ent_a", "notEnoughFor": ["not stock", "see sibling"]},
        {"entity": "ent_b", "notEnoughFor": ["not price"]},
    ]
}, ensure_ascii=False)

# валидная сборка: aliases+best+nef в одну строку
_rows_ok = P.assemble_field_items(_ANS_A, _ANS_B, _ANS_C, _PAY_G6, site="init")
t("G6: assemble — две сущности, aliases+best+nef",
  len(_rows_ok) == 2
  and {r["src_table"] for r in _rows_ok} == {"ent_a", "ent_b"}
  and all(r.get("aliases") and r.get("best_used_for") for r in _rows_ok)
  and any(r.get("not_enough_for") for r in _rows_ok),
  _rows_ok)

_ok_check, _ok_why = P.check_field_answer(_ANS_A, _PAY_G6, "aliases", site="init")
t("G6: --check-field aliases ok на валидном",
  _ok_check and _ok_why == "", (_ok_check, _ok_why))

# P-8 hard-format: bestUsedFor — скобка+запятая внутри; запятая без скобок ок;
# notEnoughFor — любая запятая/скобка = падение
_ANS_BEST_PAREN = _json.dumps({
    "items": [
        {"entity": "ent_a", "bestUsedFor": ["topic (a, b)", "other topic"]},
        {"entity": "ent_b", "bestUsedFor": ["how many", "who bought"]},
    ]
}, ensure_ascii=False)
_fail_paren, _why_paren = P.check_field_answer(
    _ANS_BEST_PAREN, _PAY_G6, "bestUsedFor", site="init")
t("G6: check-field bestUsedFor paren+comma → fail",
  (not _fail_paren) and "hard-format (paren+comma)" in _why_paren,
  (_fail_paren, _why_paren))

_ANS_BEST_COMMA = _json.dumps({
    "items": [
        {"entity": "ent_a", "bestUsedFor": ["topic a, b", "other topic"]},
        {"entity": "ent_b", "bestUsedFor": ["how many", "who bought"]},
    ]
}, ensure_ascii=False)
_ok_comma, _why_comma = P.check_field_answer(
    _ANS_BEST_COMMA, _PAY_G6, "bestUsedFor", site="init")
t("G6: check-field bestUsedFor comma without paren → ok",
  _ok_comma and _why_comma == "", (_ok_comma, _why_comma))

_ANS_NEF_FMT = _json.dumps({
    "items": [
        {"entity": "ent_a", "notEnoughFor": ["topic (x)"]},
        {"entity": "ent_b", "notEnoughFor": ["ok topic"]},
    ]
}, ensure_ascii=False)
_fail_nef, _why_nef = P.check_field_answer(
    _ANS_NEF_FMT, _PAY_G6, "notEnoughFor", site="init")
t("G6: check-field notEnoughFor hard-format → fail",
  (not _fail_nef) and "hard-format (comma/paren)" in _why_nef,
  (_fail_nef, _why_nef))

# неизвестная entity: assemble пропускает + stderr; check — падение
_ANS_UNK = _json.dumps({
    "items": [
        {"entity": "ent_a", "aliases": ["фраза нормальная", "вторая фраза", "третья"]},
        {"entity": "ent_scrubbed", "aliases": ["чужое", "ещё чужое", "третье"]},
    ]
}, ensure_ascii=False)
_err_unk = io.StringIO()
with redirect_stderr(_err_unk):
    _rows_unk = P.assemble_field_items(
        _ANS_UNK, _ANS_B, _ANS_C, _PAY_G6, site="init")
t("G6: неизвестная entity — не в rows, stderr пропуск",
  all(r["src_table"] != "ent_scrubbed" for r in _rows_unk)
  and "unknown entity skipped" in _err_unk.getvalue()
  and "ent_scrubbed" in _err_unk.getvalue(),
  (_rows_unk, _err_unk.getvalue()[:200]))

_fail_unk, _why_unk = P.check_field_answer(
    _ANS_UNK, _PAY_G6, "aliases", site="init")
t("G6: check-field — любая неизвестная entity = падение",
  (not _fail_unk) and "unknown entity" in _why_unk,
  (_fail_unk, _why_unk))

# дубль entity: пропуск дубля + stderr; первая копия остаётся
_ANS_DUP = _json.dumps({
    "items": [
        {"entity": "ent_a", "aliases": ["фраза нормальная", "вторая фраза", "третья"]},
        {"entity": "ent_a", "aliases": ["дубль один", "дубль два", "дубль три"]},
        {"entity": "ent_b", "aliases": ["слово длинное", "ещё одно", "третье слово"]},
    ]
}, ensure_ascii=False)
_err_dup = io.StringIO()
with redirect_stderr(_err_dup):
    _rows_dup = P.assemble_field_items(
        _ANS_DUP, _ANS_B, _ANS_C, _PAY_G6, site="init")
_alias_a = next((r["aliases"] for r in _rows_dup if r["src_table"] == "ent_a"), "")
t("G6: дубль entity — пропуск + stderr, первая копия",
  "duplicate entity skipped" in _err_dup.getvalue()
  and "фраза нормальная" in _alias_a
  and "дубль один" not in _alias_a
  and len(_rows_dup) == 2,
  (_alias_a, _err_dup.getvalue()[:200], _rows_dup))

# collision-degenerate: короткие aliases → пропуск строки
_ANS_DEG = _json.dumps({
    "items": [{"entity": "ent_a", "aliases": ["ок"]}]
}, ensure_ascii=False)
_ANS_DEG_B = _json.dumps({
    "items": [{"entity": "ent_a", "bestUsedFor": ["x", "y"]}]
}, ensure_ascii=False)
_ANS_DEG_C = _json.dumps({
    "items": [{"entity": "ent_a", "notEnoughFor": ["z"]}]
}, ensure_ascii=False)
_err_deg = io.StringIO()
with redirect_stderr(_err_deg):
    _rows_deg = P.assemble_field_items(
        _ANS_DEG, _ANS_DEG_B, _ANS_DEG_C,
        [{"entity": "ent_a", "title": "Сущность А", "quantities": ""}],
        site="collision")
t("G6: collision-degenerate — строка пропущена",
  _rows_deg == []
  and "collision row skipped (degenerate after filter)" in _err_deg.getvalue()
  and "kept previous" in _err_deg.getvalue(),
  (_rows_deg, _err_deg.getvalue()[:200]))

# CLI --assemble / --check-field
_td = tempfile.mkdtemp()
try:
    _pay_p = os.path.join(_td, "pay.json")
    _a = os.path.join(_td, "a.json")
    _b = os.path.join(_td, "b.json")
    _c = os.path.join(_td, "c.json")
    _rows_p = os.path.join(_td, "rows.json")
    open(_pay_p, "w", encoding="utf-8").write(_json.dumps(_PAY_G6, ensure_ascii=False))
    open(_a, "w", encoding="utf-8").write(_ANS_A)
    open(_b, "w", encoding="utf-8").write(_ANS_B)
    open(_c, "w", encoding="utf-8").write(_ANS_C)
    _buf = io.StringIO()
    with redirect_stdout(_buf):
        _rc_asm = P.main([
            "wiki_alias_parse.py", "--assemble", "--site", "init",
            _a, _b, _c, _pay_p, _rows_p,
        ])
    _out_asm = _buf.getvalue().strip()
    _rows_cli = _json.loads(open(_rows_p, encoding="utf-8").read())
    t("G6: CLI --assemble → 2 строки + stdout",
      _rc_asm == 0 and len(_rows_cli) == 2
      and "алиасов разобрано: 2" in _out_asm,
      (_rc_asm, _out_asm, _rows_cli))
    _rc_chk = P.main([
        "wiki_alias_parse.py", "--check-field", "aliases", "--site", "init",
        _a, _pay_p,
    ])
    t("G6: CLI --check-field aliases → 0",
      _rc_chk == 0, _rc_chk)
    open(_a, "w", encoding="utf-8").write(_ANS_UNK)
    _rc_bad = P.main([
        "wiki_alias_parse.py", "--check-field", "aliases", "--site", "init",
        _a, _pay_p,
    ])
    t("G6: CLI --check-field неизвестная → 1",
      _rc_bad == 1, _rc_bad)
finally:
    import shutil
    shutil.rmtree(_td, ignore_errors=True)

# extract_items_payload — регресс (преамбула), без зависимости от PY2 в .sh
_FINAL_ITEMS = (
    '{"items":[{"entity":"catalog_партнёрыпробные",'
    '"aliases":["партнёр","покупатель"],'
    '"bestUsedFor":["кто покупает"],'
    '"notEnoughFor":["юрлицо — см. контрагенты"],'
    '"quantities":[]},'
    '{"entity":"catalog_контрагентыпробные",'
    '"aliases":["контрагент","юрлицо"],'
    '"bestUsedFor":["ИНН"],'
    '"notEnoughFor":["покупатель — см. партнёры"],'
    '"quantities":[]}]}'
)
TEXT_PREAMBLE = (
    "Let me analyze this task carefully.\n\n"
    "Looking at the schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"]}],\n"
    "Final answer:\n"
    + _FINAL_ITEMS
)
got_pre = P.extract_items_payload(TEXT_PREAMBLE)
t("G6: extract преамбула → items из финального JSON",
  got_pre is not None and len(got_pre.get("items") or []) == 2,
  got_pre)

# R4: stdout-контракт «0 разобранных» (оболочка читает числа sed/awk)
ents0, meas0 = P.parse_items('{"items":[]}', PAY)
t("R4: items=[] → 0 сущностей и 0 величин",
  len(ents0) == 0 and len(meas0) == 0, (ents0, meas0))

_td2 = tempfile.mkdtemp()
try:
    _ans = os.path.join(_td2, "ans.json")
    _pay = os.path.join(_td2, "pay.json")
    _rows = os.path.join(_td2, "rows.json")
    _meas = os.path.join(_td2, "meas.json")
    open(_ans, "w", encoding="utf-8").write('{"items":[]}\n')
    open(_pay, "w", encoding="utf-8").write("[]\n")
    _buf = io.StringIO()
    with redirect_stdout(_buf):
        _rc = P.main(["wiki_alias_parse.py", _ans, _pay, _rows, _meas])
    _out = _buf.getvalue().strip()
    t("R4: main items=[] → ровно «алиасов разобрано: 0, величин: 0»",
      _rc == 0 and _out == "алиасов разобрано: 0, величин: 0",
      (_rc, _out))
finally:
    import shutil
    shutil.rmtree(_td2, ignore_errors=True)

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
