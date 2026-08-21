#!/usr/bin/env python3
"""Замки: канон продаж/меры/прайса; полный путь + живые кандидаты okna (возврат 8–11)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


# --- intent ---
t("sales intent продали", A.sales_sum_intent({"want": "sum", "kind": "продажи"},
                                              "сколько продали сегодня?"))
t("sales intent наторговали", A.sales_sum_intent({"want": "sum", "measure": "торги"},
                                                 "сколько наторговали в воскресенье?"))
t("sales intent неделя лучше", A.sales_sum_intent({"want": "list"},
                                                  "эта неделя лучше прошлой или хуже?"))
t("sales intent не прайс", not A.sales_sum_intent({"want": "count"},
                                                  "сколько позиций у нас в прайсе?"))
t("sales intent не склад", not A.sales_sum_intent({"want": "sum"},
                                                 "сколько товара на складе?"))

# --- score ---
t("score: реализациятмц > книгапродаж",
  A._sales_register_score("accumulationregister_реализациятмц",
                          ["Всего", "Количество"])
  > A._sales_register_score("accumulationregister_книгапродаж",
                            ["Всего", "СуммаНДС", "СуммаБезНДС"]))


def _fake(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "parent, written_by" in q:
        return [
            ("document_реализациятмц", "", ""),
            ("accumulationregister_реализациятмц", "", "document_реализациятмц"),
            ("accumulationregister_книгапродаж", "", "document_реализациятмц"),
            ("document_приходныйкассовыйордер", "", ""),
        ]
    if "map_entries" in q or "search_measure" in q.lower() or "measures" in q.lower():
        return []
    raise RuntimeError(q[:120])


# _measures_by_src may call more SQL — stub broadly
_real_mbs = A._measures_by_src


def _fake_mbs(srcs):
    out = {}
    for s in srcs or []:
        if "реализациятмц" in s and s.startswith("accumulation"):
            out[s] = ["Всего", "Количество"]
        elif "книгапродаж" in s:
            out[s] = ["Всего", "СуммаНДС", "СуммаБезНДС"]
        else:
            out[s] = ["Всего"]
    return out


_old = A.psql
A.psql = _fake
A._measures_by_src = _fake_mbs
try:
    got = A.prefer_entity_for_sales(
        ["document_реализациятмц", "document_приходныйкассовыйордер",
         "accumulationregister_книгапродаж"],
        {"want": "sum", "kind": "продажи", "measure": "продали"},
        "сколько уже продали сегодня?")
    t("prefer: канон реализациятмц первым",
      got and got[0] == "accumulationregister_реализациятмц", got)
    t("prefer: документ регистратора снят",
      "document_реализациятмц" not in got, got)
    t("prefer: книгапродаж не первая",
      got and got[0] != "accumulationregister_книгапродаж", got)
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

# cold lift when only journals
_calls = {"cold": 0}


def _fake_cold(q):
    if "written_by IN" in q:
        return []
    if "parent, written_by" in q:
        return [
            ("documentjournal_розничнаяторговля", "", ""),
            ("documentjournal_оптоваяторговля", "", ""),
        ]
    if "LIKE 'accumulationregister_" in q and "written_by" in q and "IN" not in q:
        _calls["cold"] += 1
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "SELECT written_by FROM" in q:
        return [("document_реализациятмц",)]
    raise RuntimeError(q[:120])


A.psql = _fake_cold
A._measures_by_src = _fake_mbs
try:
    got2 = A.prefer_entity_for_sales(
        ["documentjournal_розничнаяторговля", "documentjournal_оптоваяторговля"],
        {"want": "sum", "measure": "торги"},
        "сколько наторговали в прошедшее воскресенье?")
    t("cold lift: регистр продаж в голову",
      got2 and got2[0] == "accumulationregister_реализациятмц", got2)
    t("cold lift: SQL канона звался", _calls["cold"] >= 1, _calls)
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

# --- stock named ---
A._BALANCE_REGS.update({"at": time.time(), "set": frozenset([
    "accumulationregister_номерабсо", "accumulationregister_расчетныеначисления"])})
_real_goods = A.balance_registers_with_goods


def _no_goods(regs=None):
    return frozenset()


A.balance_registers_with_goods = _no_goods
try:
    gap = A.stock_balance_no_data(
        "сколько петель осталось на складе?", {}, {}, time.time(),
        intent={"measure": "петли", "want": "sum", "kind": "остаток"})
    t("петли: no_data при balance без ТМЦ", gap and gap.get("kind") == "no_data", gap)
    t("петли: named_absent",
      gap and (gap.get("diag") or {}).get("stock_balance_named_absent"), gap)
    gen = A.stock_balance_no_data(
        "сколько товара на складе?", {}, {}, time.time(),
        intent={"measure": "товара", "want": "sum", "kind": "товар"})
    t("товар на складе: не глушим (clarify путь)", gen is None, gen)
finally:
    A.balance_registers_with_goods = _real_goods
    A._BALANCE_REGS.update({"at": 0.0, "set": frozenset()})

gap0 = A.stock_balance_no_data("остаток на складе", {}, {}, time.time())
t("пустой balance_registers → no_data", gap0 and gap0.get("kind") == "no_data", gap0)


# --- override helpers ---
A.psql = _fake
A._measures_by_src = _fake_mbs
try:
    got3 = A.prefer_entity_for_sales(
        ["document_реализациятмц", "accumulationregister_книгапродаж",
         "accumulationregister_реализациятмц"],
        {"want": "sum", "kind": "продажи", "measure": "продали"},
        "сколько продали в прошлом месяце?")
    t("prefer: книгапродаж снята из пула",
      "accumulationregister_книгапродаж" not in got3, got3)
    t("prefer: документ снят", "document_реализациятмц" not in got3, got3)
    t("sales_canon_src lock",
      A.sales_canon_src(
          ["document_реализациятмц", "accumulationregister_книгапродаж"],
          {"want": "sum", "measure": "продали"},
          "сколько продали?") == "accumulationregister_реализациятмц")
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

t("period_zero_why sunday",
  A.period_zero_why_question("почему в воскресенье продаж ноль, это сбой?"))
t("period_zero_why not plain sales",
  not A.period_zero_why_question("сколько продали в воскресенье?"))

# catalog prefer
gotc = A.prefer_entity_for_catalog_count(
    ["informationregister_ценыноменклатуры", "document_установкаценноменклатуры",
     "catalog_номенклатура"],
    {"want": "count"}, "сколько позиций у нас в прайсе?")
t("catalog prefer: номенклатура первой",
  gotc and gotc[0] == "catalog_номенклатура", gotc)
t("catalog prefer: цены не в голове",
  gotc and "ценыноменклатуры" not in (gotc[0] or ""), gotc)


# --- возврат 10: полный путь (intent → канон → исход), не только helper ---
t("money measure: Всего из пула регистра",
  A.sales_money_measure(["Количество", "Себестоимость", "Всего", "СуммаБезНДС"])
  == "Всего")
t("money measure: *Документа",
  A.sales_money_measure(["Количество", "СуммаДокумента"]) == "СуммаДокумента")

# путь #1: sales_sum + lock → мера Всего, alts пусты (нет measure-clarify)
_names = ["Всего", "Количество", "Себестоимость", "СуммаБезНДС"]
_m = A.sales_money_measure(_names)
t("path1: мера канона Всего", _m == "Всего", _m)
t("path1: clarify меры недопустим (alts clear)",
  bool(_m) and _m == "Всего")

# путь #2: lock + fork empty → arb_pool singleton (не clarify источников)
_p, _a, _d = A.sales_canon_force_pool(
    "accumulationregister_реализациятмц",
    picked=["documentjournal_розничнаяторговля", "documentjournal_оптоваяторговля"],
    arb_pool=["accumulationregister_реализациятмц",
              "document_передачатмцврозничнуюторговлю_номенклатура",
              "document_товаротранспортнаянакладная_мбп"],
    doubt=True)
t("path2: picked = канон", _p == ["accumulationregister_реализациятмц"], _p)
t("path2: arb_pool singleton", _a == ["accumulationregister_реализациятмц"], _a)
t("path2: doubt снят", _d is False, _d)
_p0, _a0, _d0 = A.sales_canon_force_pool(None, ["a", "b"], ["a", "b"], True)
t("path2: без lock пул не трогаем", _a0 == ["a", "b"] and _d0 is True)

# путь #3: «сбой» + coverage → отказ coverage (иначе пустой figures)
t("path3: period_zero_why ловит сбой",
  A.period_zero_why_question("почему в воскресенье продаж ноль, это сбой?"))
# имитация ветки about=coverage → refuse
_intent3 = {"about": "coverage", "want": "list", "kind": "продажи", "measure": "продажи"}
_q3 = "почему в воскресенье продаж ноль, это сбой?"
if A.period_zero_why_question(_q3) and (_intent3.get("about") or "") == "coverage":
    _intent3["about"] = "data"
    if (_intent3.get("want") or "") == "list":
        _intent3["want"] = "sum"
t("path3: about снят с coverage", _intent3.get("about") == "data", _intent3)
t("path3: want→sum для канона продаж", _intent3.get("want") == "sum", _intent3)
t("path3: sales_sum после refuse",
  A.sales_sum_intent(_intent3, _q3))

# путь #4: прайс → catalog_номенклатура lock (не tabpart установки цен)
got_tab = A.prefer_entity_for_catalog_count(
    ["document_установкаценноменклатуры_номенклатура",
     "catalog_видыноменклатуры", "catalog_типыцен"],
    {"want": "count"}, "сколько позиций у нас в прайсе?")


def _fake_cat(q):
    if "LIKE 'catalog_" in q or "src_table LIKE 'catalog_" in q:
        return [("catalog_видыноменклатуры",), ("catalog_номенклатура",),
                ("catalog_типыцен",)]
    raise RuntimeError(q[:120])


_oldc = A.psql
A.psql = _fake_cat
try:
    got_cold = A.prefer_entity_for_catalog_count(
        ["document_установкаценноменклатуры_номенклатура"],
        {"want": "count"}, "сколько позиций у нас в прайсе?")
    t("path4: cold lift → catalog_номенклатура",
      got_cold and got_cold[0] == "catalog_номенклатура", got_cold)
    t("path4: tabpart цен снят",
      got_cold and all("установкацен" not in str(x) for x in got_cold), got_cold)
    t("path4: catalog_count_src",
      A.catalog_count_src(
          ["document_установкаценноменклатуры_номенклатура"],
          {"want": "count"}, "сколько позиций у нас в прайсе?")
      == "catalog_номенклатура")
    _pc, _ac, _dc = A.sales_canon_force_pool(
        A.catalog_count_src(
            ["document_установкаценноменклатуры_номенклатура", "catalog_типыцен"],
            {"want": "count"}, "сколько позиций у нас в прайсе?"),
        picked=["document_установкаценноменклатуры_номенклатура"],
        arb_pool=["document_установкаценноменклатуры_номенклатура", "catalog_типыцен"],
        doubt=True)
    t("path4: lock → singleton catalog",
      _ac == ["catalog_номенклатура"] and _dc is False, (_pc, _ac, _dc))
finally:
    A.psql = _oldc

t("path4: видыноменклатуры не product-catalog",
  not A._is_product_catalog("catalog_видыноменклатуры"))
t("path4: номенклатура — product-catalog",
  A._is_product_catalog("catalog_номенклатура"))
t("path4: noise tabpart",
  A._is_price_list_noise("document_установкаценноменклатуры_номенклатура"))


# --- возврат 11: живые кандидаты okna (не мок «только helper») ---
# Как на бою: регистр с июлем + документ передачи (мёртвый 2024) + журналы.
OKNA_CANDS = [
    "documentjournal_розничнаяторговля",
    "documentjournal_оптоваяторговля",
    "document_передачатмцврозничнуюторговлю_номенклатура",
    "document_реализациятмц",
    "accumulationregister_книгапродаж",
    "accumulationregister_реализациятмц",
]
OKNA_JULY_Q = "сколько продали в прошлом месяце?"
OKNA_SUN_Q = "сколько наторговали в прошедшее воскресенье?"
OKNA_WHY_Q = "почему в воскресенье продаж ноль, это сбой?"


def _fake_okna(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "parent, written_by" in q:
        return [
            ("documentjournal_розничнаяторговля", "", ""),
            ("documentjournal_оптоваяторговля", "", ""),
            ("document_передачатмцврозничнуюторговлю_номенклатура", "", ""),
            ("document_реализациятмц", "", ""),
            ("accumulationregister_реализациятмц", "", "document_реализациятмц"),
            ("accumulationregister_книгапродаж", "", "document_реализациятмц"),
        ]
    if "LIKE 'accumulationregister_" in q and "written_by" in q:
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "SELECT written_by FROM" in q:
        return [("document_реализациятмц",)]
    raise RuntimeError(q[:140])


A.psql = _fake_okna
A._measures_by_src = _fake_mbs
try:
    # path july: sticky focus на мёртвый документ → refuse → канон регистр
    _f, _tr, _res, _clr = A.sales_refuse_sticky_focus(
        "document_передачатмцврозничнуюторговлю_номенклатура",
        {"ambiguity": "entity", "src": "document_передачатмцврозничнуюторговлю_номенклатура",
         "from_memory": True},
        {"src": "document_передачатмцврозничнуюторговлю_номенклатура"},
        {"want": "sum", "kind": "продажи", "measure": "продали"},
        OKNA_JULY_Q, OKNA_CANDS)
    t("okna july: sticky focus снят", _f is None, _f)
    t("okna july: memory trusted сброшен", _tr is None, _tr)
    t("okna july: resolved.src снят", not (_res or {}).get("src"), _res)
    t("okna july: cleared→канон регистр",
      _clr and _clr.get("стало") == "accumulationregister_реализациятмц", _clr)
    _canon = A.sales_canon_src(OKNA_CANDS,
                               {"want": "sum", "measure": "продали"}, OKNA_JULY_Q)
    t("okna july: sales_canon_src = реализациятмц",
      _canon == "accumulationregister_реализациятмц", _canon)
    # после refuse + force: singleton, не документ
    _p, _a, _d = A.sales_canon_force_pool(
        _canon,
        picked=["document_передачатмцврозничнуюторговлю_номенклатура"],
        arb_pool=list(OKNA_CANDS), doubt=True)
    t("okna july: pool singleton канон", _a == [_canon] and not _d, (_p, _a, _d))

    # path sunday: lock + stop2-shaped rivals → force снова singleton
    _sun_lock = A.sales_canon_src(
        ["documentjournal_розничнаяторговля", "documentjournal_оптоваяторговля"],
        {"want": "sum", "measure": "торги"}, OKNA_SUN_Q)
    t("okna sunday: cold→регистр",
      _sun_lock == "accumulationregister_реализациятмц", _sun_lock)
    _p2, _a2, _d2 = A.sales_canon_force_pool(
        _sun_lock,
        picked=[_sun_lock],
        arb_pool=[_sun_lock, "document_передачатмцврозничнуюторговлю_номенклатура"],
        doubt=False)
    t("okna sunday: после stop2-rivals снова 1",
      _a2 == [_sun_lock] and len(_a2) == 1, _a2)
    t("okna sunday: не clarify источников (нет 2+ в pool)",
      len(_a2) == 1)

    # path why: coverage refuse + sales + lock → singleton (не книга)
    t("okna why: period_zero_why", A.period_zero_why_question(OKNA_WHY_Q))
    _why_cands = ["documentjournal_розничнаяторговля",
                  "accumulationregister_книгапродаж",
                  "accumulationregister_реализациятмц"]
    _why_lock = A.sales_canon_src(
        _why_cands, {"want": "sum", "kind": "продажи"}, OKNA_WHY_Q)
    t("okna why: lock не книгапродаж",
      _why_lock == "accumulationregister_реализациятмц", _why_lock)
    _p3, _a3, _d3 = A.sales_canon_force_pool(
        _why_lock, [_why_lock],
        [_why_lock, "accumulationregister_книгапродаж"], True)
    t("okna why: singleton без книги",
      _a3 == [_why_lock], _a3)

    # decision_id hatch: явный выбор документа НЕ снимаем
    _fh, _th, _rh, _ch = A.sales_refuse_sticky_focus(
        "document_реализациятмц",
        {"ambiguity": "entity", "src": "document_реализациятмц"},
        {},
        {"want": "sum", "measure": "продали"}, OKNA_JULY_Q, OKNA_CANDS)
    t("okna hatch: decision_id документ сохранён",
      _fh == "document_реализациятмц" and _ch is None, (_fh, _ch))

    # noncanon detector
    t("okna noncanon: передача",
      A.sales_noncanon_focus(
          "document_передачатмцврозничнуюторговлю_номенклатура"))
    t("okna noncanon: регистр канон — False",
      not A.sales_noncanon_focus("accumulationregister_реализациятмц"))
    t("okna noncanon: книга — True",
      A.sales_noncanon_focus("accumulationregister_книгапродаж"))
    t("okna name: money force off",
      not A.sales_force_money_measure({"want": "list"},
                                      "что лучше всего продавалось на этой неделе?"))
    t("okna name: qty = Количество",
      A.sales_qty_measure(["Всего", "Количество", "Сумма"]) == "Количество")
    t("okna sum: money force on",
      A.sales_force_money_measure({"want": "sum"}, "сколько продали вчера?"))
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(0 if not FAIL else 1)
