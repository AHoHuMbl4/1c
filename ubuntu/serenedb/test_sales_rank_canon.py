#!/usr/bin/env python3
"""Оффлайн-замки rank-path (work/rank-path-fix-design.md §5.1).

Контракт ASK_SALES_RANK_CANON: E/M/W + анти-clarify; флаг 0 = sum-путь как раньше.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.pop("ASK_SALES_RANK_CANON", None)

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


def _flag(on):
    saved = os.environ.get("ASK_SALES_RANK_CANON")
    if on:
        os.environ["ASK_SALES_RANK_CANON"] = "1"
    else:
        os.environ.pop("ASK_SALES_RANK_CANON", None)
    A.ASK_SALES_RANK_CANON = os.environ.get("ASK_SALES_RANK_CANON", "0") == "1"
    return saved


def _restore(saved):
    if saved is None:
        os.environ.pop("ASK_SALES_RANK_CANON", None)
    else:
        os.environ["ASK_SALES_RANK_CANON"] = saved
    A.ASK_SALES_RANK_CANON = os.environ.get("ASK_SALES_RANK_CANON", "0") == "1"


def _ef_flag(on):
    saved = os.environ.get("ASK_ENTITY_FORM")
    if on:
        os.environ["ASK_ENTITY_FORM"] = "1"
    else:
        os.environ.pop("ASK_ENTITY_FORM", None)
    A.ASK_ENTITY_FORM = os.environ.get("ASK_ENTITY_FORM", "0") == "1"
    return saved


def _ef_restore(saved):
    if saved is None:
        os.environ.pop("ASK_ENTITY_FORM", None)
    else:
        os.environ["ASK_ENTITY_FORM"] = saved
    A.ASK_ENTITY_FORM = os.environ.get("ASK_ENTITY_FORM", "0") == "1"


t("ASK_SALES_RANK_CANON default off", A.ASK_SALES_RANK_CANON is False)

_NAMES = ["Всего", "Количество", "Себестоимость", "СуммаНДС", "Курс"]
_ALS = {"Всего": ["итого", "деньги"], "Количество": ["кол-во"]}


def _fake_psql(q):
    if "written_by IN" in q:
        if "document_реализациятмц" not in q:
            return []
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "parent, written_by" in q:
        rows = [
            ("document_реализациятмц", "", ""),
            ("accumulationregister_реализациятмц", "", "document_реализациятмц"),
            ("accumulationregister_книгапродаж", "", "document_реализациятмц"),
            ("documentjournal_розничнаяторговля", "", ""),
        ]
        return [r for r in rows if ("'%s'" % r[0]) in q or lit_hit(q, r[0])]
    if "LIKE 'accumulationregister_" in q and "written_by" in q and "IN" not in q:
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "SELECT written_by FROM" in q:
        return [("document_реализациятмц",)]
    raise RuntimeError(q[:140])


def lit_hit(q, name):
    return name in q


def _fake_mbs(srcs):
    out = {}
    for s in srcs or []:
        if "реализациятмц" in s and s.startswith("accumulation"):
            out[s] = ["Всего", "Количество"]
        elif "книгапродаж" in s:
            out[s] = ["Всего", "СуммаНДС"]
        else:
            out[s] = ["Всего"]
    return out


_old_psql, _old_mbs = A.psql, A._measures_by_src
A.psql = _fake_psql
A._measures_by_src = _fake_mbs

# ── E: rank + document → lock регистра без «продали» ─────────────────────────
_cands_doc = ["document_реализациятмц"]
_intent_client = {"want": "list", "kind": "клиент"}
_q_buy = "какой клиент больше всех купил в этом месяце?"

_sv = _flag(False)
try:
    got0 = A.prefer_entity_for_sales(_cands_doc, _intent_client, _q_buy)
    t("flag0: купил+rank не поднимает регистр",
      got0 == _cands_doc, got0)
    t("flag0: sales_rank_engaged false",
      not A.sales_rank_engaged(_intent_client, {}, _q_buy, _cands_doc))
finally:
    _restore(_sv)

_sv = _flag(True)
try:
    t("flag1: sales_lift_possible на document",
      A.sales_lift_possible(_cands_doc))
    t("flag1: sales_rank_engaged",
      A.sales_rank_engaged(_intent_client, {}, _q_buy, _cands_doc))
    got1 = A.prefer_entity_for_sales(_cands_doc, _intent_client, _q_buy)
    t("flag1: купил+rank → lock регистра (E K1b/K2/K3)",
      got1 and got1[0] == "accumulationregister_реализациятмц", got1)
    t("flag1: sales_canon_src без «продали»",
      A.sales_canon_src(_cands_doc, _intent_client, _q_buy)
      == "accumulationregister_реализациятмц")
    # cold lift закрыт на rank-пути
    got_j = A.prefer_entity_for_sales(
        ["documentjournal_розничнаяторговля"], _intent_client, _q_buy)
    t("flag1: rank без document/register — без cold-lift",
      got_j == ["documentjournal_розничнаяторговля"], got_j)
finally:
    _restore(_sv)

# ── M: какого товара → Количество; force_money off на rank ───────────────────
_q_goods = "какого товара больше всего продали за всё время?"
_intent_goods = {"want": "sum", "kind": "продажи", "measure": "продали"}

_sv = _flag(False)
try:
    t("flag0: force_money на «какого…продали» ещё true (старый дефект)",
      A.sales_force_money_measure(_intent_goods, _q_goods))
finally:
    _restore(_sv)

_sv = _flag(True)
try:
    t("flag1: force_money false при любом rank_intent",
      not A.sales_force_money_measure(_intent_goods, _q_goods))
    t("flag1: force_money false на клиентский rank",
      not A.sales_force_money_measure(_intent_client, _q_buy))
    _m, _how = A.sales_rank_canon_measure(
        _NAMES, _intent_goods, _q_goods, _ALS)
    t("flag1: какого товара → Количество (M K1a)",
      _m == "Количество", (_m, _how))
    _m2, _how2 = A.sales_rank_canon_measure(
        _NAMES, {"want": "list", "measure": "деньгам"},
        "дай топ-3 клиента по деньгам за этот месяц", _ALS)
    t("flag1: money-роль → Всего (K2)",
      _m2 == "Всего", (_m2, _how2))
    t("flag1: money-роль без measure_ambiguous",
      _m2 == "Всего" and _how2 in ("role_choice", "sales_money_role"), _how2)
    # клиентский rank без money-алиаса: canon не навязывает qty (ответ → money fallback).
    _m3, _how3 = A.sales_rank_canon_measure(
        _NAMES, {"want": "list", "kind": "продажи", "measure": "продали"},
        "кому мы больше всего продали за всё время?", _ALS)
    t("flag1: кому…продали → None в canon (не qty)",
      _m3 is None, (_m3, _how3))
    _m4, _how4 = A.sales_rank_canon_measure(
        _NAMES, {"want": "sum", "kind": "продажи", "measure": "продавалось"},
        "что лучше всего продавалось на этой неделе?", _ALS)
    t("flag1: что лучше всего продавалось → Количество (не Всего)",
      _m4 == "Количество", (_m4, _how4))
    # §9: без sales written_by в cands — gate не включается (не cold).
    t("flag1: rank без lift (справочник) — не engaged",
      not A.sales_rank_engaged(
          {"want": "list"}, {}, "как у нас дела?",
          ["catalog_номенклатура"]))
    # голый want=list без фразы рейтинга — не engaged (регресс clarify).
    t("flag1: как у нас дела want=list — не engaged",
      not A.sales_rank_engaged(
          {"want": "list"}, {}, "как у нас дела?",
          ["document_реализациятмц"]))
    t("flag1: три лучших + sales-doc → engaged",
      A.sales_rank_engaged(
          {"want": "list"}, {}, 
          "кто из клиентов молодец за прошлую неделю, три лучших",
          ["document_реализациятмц"]))
    t("flag1: top_n три лучших → 3",
      A._sales_rank_top_n({"want":"list"}, {},
          "кто из клиентов молодец за прошлую неделю, три лучших") == 3)
    t("flag1: top_n топ-3 → 3",
      A._sales_rank_top_n({"want":"list"}, {"compute":"max"},
          "дай топ-3 клиента по деньгам за этот месяц") == 3)
finally:
    _restore(_sv)

# ── M+: rank×product без названной меры → qty (класс топ-N товара) ───────────
# [замер 25.08 okna] «дай топ-3 товара за вчера» → Всего (money fallback),
# эталон — Количество. Срыв: sales_rank_canon_measure→None, затем
# call-site money из‑за _rank_wants_quantity("топ"≠"top"). Правило: роль оси
# (product_axis / target_src catalog), не список русских слов.
_q_top3 = "дай топ-3 товара за вчера"
_intent_top3 = {"want": "list", "kind": "товар", "amount": {"value": 3}}
_AX_PROD = [
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
]
_AX_CLIENT = [
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
]

_sv = _flag(True)
try:
    t("rule: топ-3 товара без product_axis — canon None (ось не дана)",
      A.sales_rank_canon_measure(
          _NAMES, _intent_top3, _q_top3, _ALS)[0] is None)
    _m5, _how5 = A.sales_rank_canon_measure(
        _NAMES, _intent_top3, _q_top3, _ALS, product_axis=True)
    t("rule: топ-3 товара + product_axis → Количество",
      _m5 == "Количество" and _how5 == "sales_qty_canon", (_m5, _how5))
    # оси из данных: kind_axis_hits → ТМЦ (товарный catalog)
    _old_hits = A.kind_axis_hits
    A.kind_axis_hits = lambda axes, text: (
        ["ТМЦ"] if text and ("товар" in text.lower() or text == "товар") else [])
    try:
        t("rule: product_axis по target_src catalog_номенклатура",
          A.sales_rank_product_axis(
              "accumulationregister_реализациятмц", _intent_top3, _q_top3,
              axes=_AX_PROD))
        _m6, _how6 = A.sales_rank_canon_measure(
            _NAMES, _intent_top3, _q_top3, _ALS, axes=_AX_PROD,
            src="accumulationregister_реализациятмц")
        t("rule: canon через оси данных → Количество",
          _m6 == "Количество", (_m6, _how6))
        # клиентская ось: hit Контрагент — не qty
        A.kind_axis_hits = lambda axes, text: (
            ["Контрагент"] if text and "клиент" in (text or "").lower() else [])
        t("rule: client axis — не product",
          not A.sales_rank_product_axis(
              "accumulationregister_реализациятмц",
              {"want": "list", "kind": "клиент"},
              "какой клиент больше всех купил в этом месяце",
              axes=_AX_CLIENT))
        _m7, _how7 = A.sales_rank_canon_measure(
            _NAMES, {"want": "list", "kind": "клиент"},
            "какой клиент больше всех купил в этом месяце", _ALS,
            axes=_AX_CLIENT, src="accumulationregister_реализациятмц",
            product_axis=False)
        t("rule: клиент без money-алиаса → None (fallback money снаружи)",
          _m7 is None, (_m7, _how7))
    finally:
        A.kind_axis_hits = _old_hits
    # money названа — деньги даже на товарной оси
    _m8, _how8 = A.sales_rank_canon_measure(
        _NAMES, {"want": "list", "measure": "деньгам"},
        "дай топ-3 товара по деньгам за вчера", _ALS, product_axis=True)
    t("rule: товар + money названа → Всего",
      _m8 == "Всего", (_m8, _how8))
    # нет qty у источника — None из canon (снаружи возьмут money)
    _m9, _how9 = A.sales_rank_canon_measure(
        ["Всего", "СуммаНДС"], _intent_top3, _q_top3, _ALS, product_axis=True)
    t("rule: product_axis без qty-меры → None",
      _m9 is None, (_m9, _how9))
    # живой путь answer(): sales_rank_resolve_measure (не inline fallback)
    _sm_live, _how_live = A.sales_rank_resolve_measure(
        _NAMES, _intent_top3, _q_top3, _ALS,
        src="accumulationregister_реализациятмц", axes=_AX_PROD)
    t("live: resolve_measure топ-3 товара → Количество",
      _sm_live == "Количество" and _how_live in ("sales_qty_canon", "sales_rank_hint_canon"),
      (_sm_live, _how_live))
    # client rank через тот же resolver → money
    _sm_cli, _how_cli = A.sales_rank_resolve_measure(
        _NAMES, {"want": "list", "kind": "клиент"},
        "какой клиент больше всех купил в этом месяце", _ALS,
        src="accumulationregister_реализациятмц", axes=_AX_CLIENT)
    t("live: resolve_measure клиент → Всего",
      _sm_cli == "Всего" and _how_cli == "sales_rank_money",
      (_sm_cli, _how_cli))
    # ранний rank_measure_hint не должен обходить resolver на rank×sales
    _eng_top3 = A.sales_rank_engaged(
        _intent_top3, {}, _q_top3,
        ["accumulationregister_реализациятмц"])
    t("live: rank_sales_early для топ-3 товара",
      _eng_top3, _eng_top3)
    _mh_early = A.rank_measure_hint(_NAMES, _intent_top3, _q_top3, _ALS)
    t("live: hint есть, но answer пропускает при engaged",
      _mh_early == "Количество" and _eng_top3,
      (_mh_early, _eng_top3))
finally:
    _restore(_sv)

# ── K-regress: мера ранга не имеет права на compare-путь ─────────────────────
# [замер 26.08 okna] после sales_rank_resolve_measure compare «неделя лучше/хуже»
# ушёл в qty через engaged(want=list)+product_axis fallback → FAIL want=money-diff.
# Домен: sales_rank_engaged только для ранжирования; compare → sum/money.
_q_cmp_week = "эта неделя лучше прошлой или хуже?"
_intent_cmp_list = {"want": "list", "kind": "продажи"}
_AX_FALLBACK_PROD = [
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
]
_sv = _flag(True)
_sv_ef = _ef_flag(True)
_old_lift = A.sales_lift_possible
_old_hits = A.kind_axis_hits
_old_rar = A.rank_axis_resolve
try:
    A.sales_lift_possible = lambda cands: True
    A.kind_axis_hits = lambda axes, text: []
    A.rank_axis_resolve = lambda src, axes, intent, question, plan=None: (
        (axes[0]["col"], []) if axes else (None, []))
    t("regress: compare intent при want=list",
      A.sales_compare_intent(_intent_cmp_list, _q_cmp_week))
    _eng_cmp = A.sales_rank_engaged(
        _intent_cmp_list, {}, _q_cmp_week, ["document_реализациятмц"])
    t("regress: sales_rank_engaged OFF на compare",
      not _eng_cmp, _eng_cmp)
    t("regress: force_money ON на compare (sum-путь)",
      A.sales_force_money_measure(_intent_cmp_list, _q_cmp_week))
    # если resolve всё же позвали — ответный путь не должен: qty через
    # product_axis fallback при отсутствии hit по вопросу = влияние ранга.
    _sm_cmp, _how_cmp = A.sales_rank_resolve_measure(
        _NAMES, _intent_cmp_list, _q_cmp_week, _ALS,
        src="accumulationregister_реализациятмц", axes=_AX_FALLBACK_PROD,
        plan={}, diag={})
    t("regress: resolve на compare не навязывает qty через ось",
      not (_sm_cmp == "Количество" and _how_cmp == "sales_qty_canon"
           and _eng_cmp),
      (_sm_cmp, _how_cmp, _eng_cmp))
    # топ-N товара по-прежнему engaged (класс, который чинили)
    t("regress: топ-3 товара всё ещё engaged",
      A.sales_rank_engaged(
          _intent_top3, {}, _q_top3,
          ["accumulationregister_реализациятмц"]))
finally:
    A.sales_lift_possible = _old_lift
    A.kind_axis_hits = _old_hits
    A.rank_axis_resolve = _old_rar
    _ef_restore(_sv_ef)
    _restore(_sv)

# ── sum-путь при флаге 0 и 1 без rank не меняется ────────────────────────────
_q_sum = "сколько продали вчера?"
_intent_sum = {"want": "sum", "kind": "продажи", "measure": "продали"}
for on, label in ((False, "flag0"), (True, "flag1")):
    _sv = _flag(on)
    try:
        t("%s: sum force_money on" % label,
          A.sales_force_money_measure(_intent_sum, _q_sum))
        got_s = A.prefer_entity_for_sales(
            ["document_реализациятмц", "accumulationregister_книгапродаж"],
            _intent_sum, _q_sum)
        t("%s: sum → регистр+money path" % label,
          got_s and got_s[0] == "accumulationregister_реализациятмц"
          and A.sales_money_measure(_NAMES) == "Всего", got_s)
        t("%s: sum не sales_rank_engaged" % label,
          not A.sales_rank_engaged(_intent_sum, {"compute": "sum"}, _q_sum,
                                   ["document_реализациятмц"]))
    finally:
        _restore(_sv)

A.psql = _old_psql
A._measures_by_src = _old_mbs

# ── W: prev_week reading + ticket лидер ──────────────────────────────────────
_sv = _flag(True)
try:
    intent_w = {
        "period": {"from": "2026-08-24", "to": "2026-08-25"},
        "parse": {"assumed": ["period.from", "period.to"]},
    }
    r_w = A.period_readings(intent_w, today="2026-08-25")
    ids = {x["interpretation_id"] for x in r_w}
    t("flag1: при wtd есть reading prev_week",
      "prev_week" in ids and "wtd" in ids, ids)
    _pw = next(x for x in r_w if x["interpretation_id"] == "prev_week")
    t("flag1: prev_week границы gold [week−7d, week)",
      _pw["period"].get("from") == "2026-08-17"
      and _pw["period"].get("to") == "2026-08-23",
      _pw["period"])
    t("flag1: без ticket лидер = wtd (status quo)",
      (A.prefer_window_leader(r_w) or {}).get("interpretation_id") == "wtd")
    t("flag1: ticket/словарь prev → лидер prev_week",
      (A.prefer_window_leader(r_w, prefer_form="prev_week")
       or {}).get("interpretation_id") == "prev_week")
    # словарь фраз (данные) → prev
    t("flag1: phrase «прошлую неделю» → prev_week",
      A.period_form_from_question(
          "кто из клиентов молодец за прошлую неделю, три лучших")
      == "prev_week")
    intent_lead = dict(intent_w)
    A.apply_period_leader(
        intent_lead, today="2026-08-25",
        question="кто из клиентов молодец за прошлую неделю, три лучших")
    t("flag1: apply_period_leader + phrase → окно prev",
      (intent_lead.get("period") or {}).get("from") == "2026-08-17"
      and (intent_lead.get("period") or {}).get("to") == "2026-08-23",
      intent_lead.get("period"))
finally:
    _restore(_sv)

_sv = _flag(False)
try:
    r0 = A.period_readings(
        {"period": {"from": "2026-08-24", "to": "2026-08-25"},
         "parse": {"assumed": ["period.from", "period.to"]}},
        today="2026-08-25")
    t("flag0: period_readings без prev_week (md5-путь)",
      "prev_week" not in {x["interpretation_id"] for x in r0},
      {x["interpretation_id"] for x in r0})
finally:
    _restore(_sv)

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(0 if not FAIL else 1)
