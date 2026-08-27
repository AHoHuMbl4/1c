#!/usr/bin/env python3
"""Оффлайн-замки K4/K6 / ASK_ENTITY_FORM (work/entity-compare-form-design.md).

Контракт: R = E×P×M×W×F; флаг 0 = status quo; без новых языковых литералов.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.pop("ASK_ENTITY_FORM", None)

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
    saved = os.environ.get("ASK_ENTITY_FORM")
    if on:
        os.environ["ASK_ENTITY_FORM"] = "1"
    else:
        os.environ.pop("ASK_ENTITY_FORM", None)
    A.ASK_ENTITY_FORM = os.environ.get("ASK_ENTITY_FORM", "0") == "1"
    return saved


def _restore(saved):
    if saved is None:
        os.environ.pop("ASK_ENTITY_FORM", None)
    else:
        os.environ["ASK_ENTITY_FORM"] = saved
    A.ASK_ENTITY_FORM = os.environ.get("ASK_ENTITY_FORM", "0") == "1"


t("ASK_ENTITY_FORM default off", A.ASK_ENTITY_FORM is False)
t("ASK_ENTITY_FORM exists", hasattr(A, "ASK_ENTITY_FORM"))

# ── флаг 0: compare по-прежнему режется want=list ────────────────────────────
_s = _flag(0)
_intent_list = {
    "period": {"from": "2026-08-17", "to": "2026-08-23"},
    "want": "list",
}
_q_cmp = "эта неделя лучше прошлой или хуже?"
# K2 P5 (6a379d8): better/worse + «прошл» — структурный вход compare даже
# без ASK_ENTITY_FORM (Q6 живьём: WTD-пара −792128.74). Старый кейс
# «flag0 → False» описывал поведение до P5 и устарел.
t("flag0: want=list + лучше/прошл → compare True (K2 P5)",
  A.sales_compare_intent(_intent_list, _q_cmp) is True)
_restore(_s)

# ── флаг 1: compare не блокируется want=list ─────────────────────────────────
_s = _flag(1)
t("flag1: want=list → compare True",
  A.sales_compare_intent(_intent_list, _q_cmp) is True)
_intent_sum = dict(_intent_list, want="sum")
t("flag1: want=sum → compare True",
  A.sales_compare_intent(_intent_sum, _q_cmp) is True)
# суперлатив остаётся rank
t("flag1: суперлатив не compare",
  A.sales_compare_intent(
      {"want": "list", "period": {"from": "2026-08-24", "to": "2026-08-25"}},
      "что лучше всего продавалось на этой неделе?") is False)

# окна: prev_week → WTD + prior
TODAY = "2026-08-25"
p1, p2, fid = A.sales_compare_windows(_intent_list, TODAY, _q_cmp)
t("flag1: windows form wtd", fid == "wtd", fid)
t("flag1: cur WTD Mon→today",
  p1.get("from") == "2026-08-24" and p1.get("to") == TODAY, p1)
t("flag1: prior full prev week",
  p2.get("from") == "2026-08-17" and p2.get("to") == "2026-08-23", p2)
_restore(_s)

# ── distinct_axis ≠ row_count ────────────────────────────────────────────────
_s = _flag(1)
row_sales = {"count": 77901, "folders": 0, "sums": {"measure_x": 1.0},
             "distinct": {"axis_x": 141}}
atom_row = A._fork_atom_of(row_sales, ["accumulationregister_a"],
                           want="count")
atom_dist = A.entity_form_atom_distinct(
    src="accumulationregister_a", axis="axis_x", value=141,
    period={"from": "2025-08-25", "to": "2026-08-25"})
t("distinct_axis atom form",
  atom_dist and atom_dist.get("form") == "distinct_axis", atom_dist)
t("distinct_axis exact=141 не row_count",
  atom_dist.get("exact_value") == 141
  and atom_dist.get("exact_value") != row_sales["count"])
t("distinct_axis fp ≠ row_count fp",
  A._fork_atom_equiv_fp(atom_dist) != A._fork_atom_equiv_fp(atom_row))
_restore(_s)

# ── complement = cat − distinct ──────────────────────────────────────────────
_s = _flag(1)
atom_comp = A.entity_form_atom_complement(
    catalog_src="catalog_a", sales_src="accumulationregister_a",
    axis="axis_x", catalog_n=2384, distinct_n=493,
    period={"from": "2026-08-01", "to": "2026-08-25"})
t("complement form", atom_comp and atom_comp.get("form") == "complement")
t("complement = cat − distinct",
  atom_comp.get("exact_value") == 2384 - 493, atom_comp.get("exact_value"))
_restore(_s)

# ── catalog + date-pred → не no_live_cells из-за даты ────────────────────────
_s = _flag(1)
_calls = []


def _fake_scan(match, preds, rel):
    _calls.append({"preds": list(preds or []), "srcs": sorted(rel.keys())})
    out = {}
    for s in rel:
        if str(s).startswith("catalog_") and preds:
            continue
        out[s] = {"count": 10, "folders": 0, "sums": {}}
    return out


_old = A.fork_scan
A.fork_scan = _fake_scan
rel = {
    "catalog_a": [],
    "accumulationregister_a": ["measure_x"],
}
cells, merged, _pby = A.fork_scan_readings(
    "", [{"period": {"from": "2026-08-01", "to": "2026-08-25"},
          "window_fp": "w1", "origin": "assumed"}],
    rel)
cat_cell = next(c for c in cells if c["src"] == "catalog_a")
t("flag1: catalog cell computed (без date-pred)",
  cat_cell.get("status") == "computed", cat_cell)
t("flag1: catalog scan вызван без preds",
  any(c["srcs"] == ["catalog_a"] and c["preds"] == [] for c in _calls),
  _calls)
sales_cell = next(c for c in cells if c["src"] == "accumulationregister_a")
t("flag1: sales с date-pred жив",
  sales_cell.get("status") == "computed")
A.fork_scan = _old
_restore(_s)

_s = _flag(0)
_calls.clear()
A.fork_scan = _fake_scan
cells0, _, _ = A.fork_scan_readings(
    "", [{"period": {"from": "2026-08-01", "to": "2026-08-25"},
          "window_fp": "w1", "origin": "assumed"}],
    rel)
cat0 = next(c for c in cells0 if c["src"] == "catalog_a")
t("flag0: catalog + date → no_live_cells",
  cat0.get("status") == "no_live_cells", cat0)
A.fork_scan = _old
_restore(_s)

# ── early classes>1 + arb_pool=1 → не unique молча ───────────────────────────
_s = _flag(1)
# узкий API: запись пропуска / развилка (две формы — разные exact_value)
skip = A.entity_form_collapse_guard(
    early_classes=2, arb_pool_len=1, form_applicable=True)
t("collapse guard: applicable → not silent unique",
  skip.get("action") in ("resolve_early", "fork") and not skip.get("silent_unique"))
skip_na = A.entity_form_collapse_guard(
    early_classes=2, arb_pool_len=1, form_applicable=False)
t("collapse guard: N/A → fork_outcome_skipped",
  skip_na.get("fork_outcome_skipped") == "arb_pool_collapsed")
# при early=1 схлопывание не трогаем
skip_one = A.entity_form_collapse_guard(
    early_classes=1, arb_pool_len=1, form_applicable=True)
t("collapse guard: early=1 → action none",
  skip_one.get("action") == "none")
_restore(_s)

# ── pre_entity + early_classes>1 → не атом формы (молчаливый лидер) ───────────
# Правило, не фраза: want=count, несколько catalog_* + sales, classes>1.
# pre_entity не имеет права вернуть F; post-entity путь (без when) — оставляем.
_s = _flag(1)
_old_exp = A.entity_form_expand_pool
_old_structs = getattr(A, "entity_form_structs", None)
_old_comp = A.entity_form_compute
_meta_f = {
    "catalog_src": "catalog_a", "sales_src": "accumulationregister_a",
    "axis": "axis_x", "period": {"from": "2025-08-25", "to": "2026-08-25"},
}
A.entity_form_expand_pool = lambda p, intent=None: list(p or [])
# единственная структурная форма — проверяем именно early_classes, не form_n
A.entity_form_structs = lambda intent, pool, today=None: [
    ("distinct_axis", dict(_meta_f))]
A.entity_form_compute = lambda form, meta, match="": A.entity_form_atom_distinct(
    src=meta.get("sales_src"), axis=meta.get("axis"), value=141,
    period=meta.get("period"))
_pool_multi = [
    "catalog_a", "catalog_b", "catalog_c", "accumulationregister_a",
]
_gate = getattr(A, "entity_form_pre_entity_ok", None)
t("pre_entity gate: early_classes>1 → False",
  callable(_gate) and _gate(early_classes=2, form_n=1) is False,
  _gate(early_classes=2, form_n=1) if callable(_gate) else "no gate")
t("pre_entity gate: early_classes<=1 + form_n=1 → True",
  callable(_gate) and _gate(early_classes=1, form_n=1) is True)
t("pre_entity gate: form_n!=1 → False",
  callable(_gate) and _gate(early_classes=0, form_n=2) is False)
try:
    _ans_pre = A.try_entity_form_answer(
        "q", {"want": "count"}, _pool_multi, when="pre_entity",
        early_classes=2)
except TypeError as _e:
    _ans_pre = "no_when_kw:%s" % _e
t("pre_entity + early_classes>1 → try не атом формы",
  _ans_pre is None, _ans_pre)
_ans_post = A.try_entity_form_answer(
    "q", {"want": "count"}, _pool_multi, early_classes=2)
t("post_entity: early_classes>1 всё ещё может отдать F",
  _ans_post is not None
  and (_ans_post.get("atom") or {}).get("form") == "distinct_axis",
  (_ans_post or {}).get("kind") if isinstance(_ans_post, dict) else _ans_post)
_ans_ok = A.try_entity_form_answer(
    "q", {"want": "count"}, _pool_multi, when="pre_entity",
    early_classes=1)
t("pre_entity + early_classes<=1 → форма ок",
  isinstance(_ans_ok, dict) and _ans_ok.get("kind") == "answer",
  _ans_ok)
# form_n>1 при early=0: pre_entity тоже отказывает
A.entity_form_structs = lambda intent, pool, today=None: [
    ("distinct_axis", dict(_meta_f, catalog_src="catalog_a")),
    ("distinct_axis", dict(_meta_f, catalog_src="catalog_b")),
]
_ans_multi_f = A.try_entity_form_answer(
    "q", {"want": "count"}, _pool_multi, when="pre_entity",
    early_classes=0)
t("pre_entity + form_n>1 → try не атом формы",
  _ans_multi_f is None, _ans_multi_f)
A.entity_form_expand_pool = _old_exp
if _old_structs is not None:
    A.entity_form_structs = _old_structs
A.entity_form_compute = _old_comp
_restore(_s)

# ── flag0: F-путь закрыт (applicable / try) ──────────────────────────────────
_s = _flag(0)
t("flag0: entity_form_applicable False",
  A.entity_form_applicable(
      {"want": "count", "period": {"from": "2026-08-01", "to": "2026-08-25"}},
      ["catalog_x", "accumulationregister_y"]) is False)
t("flag0: try_entity_form_answer None",
  A.try_entity_form_answer(
      "сколько клиентов покупают?",
      {"want": "count", "period": {"from": "2025-08-25", "to": "2026-08-25"}},
      ["catalog_x", "accumulationregister_y"]) is None)
_restore(_s)

# ── compare atom пара, не «· rank» ───────────────────────────────────────────
_s = _flag(1)
cmp_atom = A.build_answer_atom(
    operation="compare", exact_value=-792128.74, measure_id="measure_x",
    measure_label="measure_x", form="compare", proof_status=A.PROOF_COMPUTED)
pair = A.render_atom_pair(cmp_atom)
t("compare pair собрана", bool(pair) and "792" in pair.replace(" ", ""), pair)
t("compare pair без · rank", pair and "· rank" not in pair and "rank" not in pair.lower())
_restore(_s)

# ── нет новых DATA-литералов okna / «книгапродаж» / «не продаётся» в diff ─────
_src = open(A.__file__, encoding="utf-8").read()
# эвристика: функции entity_form* не содержат кириллических NL-триггеров
tree = ast.parse(_src)
banned = ("не продаётся", "реально", "книгапродаж", "номенклатура",
          "контрагент", "лучше прошлой")
found_banned = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if not node.name.startswith("entity_form") and node.name not in (
                "sales_compare_intent", "sales_compare_windows",
                "fork_scan_readings", "fork_detector_scan",
                "_fork_atom_equiv_fp"):
            continue
        for n in ast.walk(node):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                low = n.value.lower()
                for b in banned:
                    if b in low:
                        found_banned.append((node.name, n.value[:60]))
t("нет banned литералов в entity_form/compare-правках",
  not found_banned, found_banned)

# entity_form_applicable — структура (period + catalog + sales), не подстроки
_s = _flag(1)
t("applicable: нет period + только catalog → False",
  A.entity_form_applicable(
      {"want": "count"}, ["catalog_x"]) is False)
t("applicable: нет period + movement в пуле → True",
  A.entity_form_applicable(
      {"want": "count", "kind": "клиенты"},
      ["document_sales", "catalog_x"]) is True
  or A.entity_form_applicable(
      {"want": "count"},
      ["catalog_x", "accumulationregister_y"]) is True)
t("applicable: period + catalog + sales → True",
  A.entity_form_applicable(
      {"want": "count", "period": {"from": "2026-08-01", "to": "2026-08-25"}},
      ["catalog_x", "accumulationregister_y"]) is True)
t("applicable: want=sum → False",
  A.entity_form_applicable(
      {"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-25"}},
      ["catalog_x", "accumulationregister_y"]) is False)
_restore(_s)

# ── регресс: счёт позиций справочника ≠ distinct_axis (пул с движением) ─────
# Структура как на стейдже: want=count без окна, в пуле товарный catalog +
# чужой catalog + sales (номенклатура держится строками продаж → movement всегда).
# F не должна открывать distinct по соседнему каталогу из dump развилки.
_s = _flag(1)
_old_exp = A.entity_form_expand_pool
_old_axis = A.entity_form_axis_on_sales
_old_ck = A.entity_form_catalogs_for_kind
A.entity_form_expand_pool = lambda p, intent=None: list(p or [])
A.entity_form_catalogs_for_kind = (
    lambda k, allow_meaning=True: ["catalog_product_a"])
A.entity_form_axis_on_sales = (
    lambda cat, sales: ((sales[0], "axis_x") if sales else (None, None)))
_pool_price = [
    "catalog_product_a", "catalog_b",
    "accumulationregister_a",
]
_form_price, _meta_price = A.entity_form_pick(
    {"want": "count", "kind": "positions"}, _pool_price, today="2026-08-25")
t("price-list count: no distinct_axis (polluted pool)",
  _form_price is None, (_form_price, (_meta_price or {}).get("catalog_src")))
# зеркало K6.2: kind → нетоварный catalog, без окна — distinct остаётся
A.entity_form_catalogs_for_kind = (
    lambda k, allow_meaning=True: ["catalog_b"])
_form_cli, _meta_cli = A.entity_form_pick(
    {"want": "count", "kind": "clients"}, _pool_price, today="2026-08-25")
t("clients count: distinct_axis on kind catalog",
  _form_cli == "distinct_axis"
  and (_meta_cli or {}).get("catalog_src") == "catalog_b",
  (_form_cli, (_meta_cli or {}).get("catalog_src")))
A.entity_form_expand_pool = _old_exp
A.entity_form_axis_on_sales = _old_axis
A.entity_form_catalogs_for_kind = _old_ck
_restore(_s)

# ── регресс: пустой stem SQL + meaning→чужой catalog → F без окна НЕ открыть ─
# Живая улика :8092: kind=«прайс», ts_lexize SQL = 0, meaning_candidates
# подсовывает catalog_договоры → distinct_axis(Договор)=1 вместо счёта 2384.
_s = _flag(1)
_old_psql = A.psql
_old_mc = A.meaning_candidates
_old_exp = A.entity_form_expand_pool
_old_axis = A.entity_form_axis_on_sales
A.psql = lambda *a, **k: []  # stem/label SQL → 0 строк
A.meaning_candidates = lambda *a, **k: ["catalog_b"]
A.entity_form_expand_pool = lambda p, intent=None: list(p or [])
A.entity_form_axis_on_sales = (
    lambda cat, sales: (
        (sales[0], "axis_x") if cat == "catalog_b" and sales
        else (None, None)))
_pool_meaning = [
    "catalog_product_a", "catalog_b",
    "accumulationregister_a",
]
_form_m, _meta_m = A.entity_form_pick(
    {"want": "count", "kind": "kind_x"}, _pool_meaning, today="2026-08-25")
t("price kind: empty stem SQL → no distinct via meaning",
  _form_m is None,
  (_form_m, (_meta_m or {}).get("catalog_src"),
   (_meta_m or {}).get("axis")))
A.psql = _old_psql
A.meaning_candidates = _old_mc
A.entity_form_expand_pool = _old_exp
A.entity_form_axis_on_sales = _old_axis
_restore(_s)

# ── Gate A: счёт document_* — F не отвечает (не catalog×sales) ───────────────
# want=count + явное окно; kind→document; в пуле document + catalog + sales.
# Meaning-запас может подсунуть catalog — форма всё равно None.
_s = _flag(1)
_old_exp = A.entity_form_expand_pool
_old_axis = A.entity_form_axis_on_sales
_old_ck = A.entity_form_catalogs_for_kind
_old_comp = A.entity_form_compute
_old_mv = A.entity_form_movements_for_kind
A.entity_form_expand_pool = lambda p, intent=None: list(p or [])
A.entity_form_catalogs_for_kind = (
    lambda k, allow_meaning=True: ["catalog_x"])  # meaning→catalog
A.entity_form_axis_on_sales = (
    lambda cat, sales: ((sales[0], "axis_x") if sales else (None, None)))
A.entity_form_compute = lambda form, meta, match="": A.entity_form_atom_distinct(
    src=meta.get("sales_src"), axis=meta.get("axis"), value=2059,
    period=meta.get("period"))
A.entity_form_movements_for_kind = (
    lambda k, allow_meaning=True: ["document_a"])
_pool_doc = [
    "document_a", "catalog_x", "accumulationregister_y",
]
_intent_doc = {
    "want": "count", "kind": "kind_doc",
    "period": {"from": "2025-12-01", "to": "2025-12-31"},
}
_form_doc, _meta_doc = A.entity_form_pick(_intent_doc, _pool_doc)
t("document count: no F",
  _form_doc is None,
  (_form_doc, (_meta_doc or {}).get("catalog_src")))
_ans_doc = A.try_entity_form_answer("q", _intent_doc, _pool_doc)
t("document count: try не атом формы",
  _ans_doc is None, _ans_doc)
A.entity_form_expand_pool = _old_exp
A.entity_form_axis_on_sales = _old_axis
A.entity_form_catalogs_for_kind = _old_ck
A.entity_form_compute = _old_comp
A.entity_form_movements_for_kind = _old_mv
_restore(_s)

# ── Gate B: rank top-N + одно окно → не compare (K4 двух окон цел) ───────────
_s = _flag(1)
_intent_rank = {
    "want": "list", "kind": "клиент",
    "period": {"from": "2026-08-17", "to": "2026-08-23"},
    "amount": {"value": 3},
}
_q_rank = "кто из клиентов молодец за прошлую неделю, три лучших"
t("rank top-N single window: no compare",
  A.sales_compare_intent(_intent_rank, _q_rank) is False)
_rp1, _rp2, _rfid = A.sales_compare_windows(
    _intent_rank, TODAY, _q_rank)
t("rank top-N single window: окно одно (не пара compare)",
  _rp1.get("from") == "2026-08-17" and _rp1.get("to") == "2026-08-23"
  and not (_rp2.get("from") or _rp2.get("to")),
  (_rfid, _rp1, _rp2))
t("rank top-N single window: rank остаётся",
  A.rank_intent_from(_intent_rank, question=_q_rank) is True)
# K4: два окна по-прежнему compare
t("K4 two-window: compare цел",
  A.sales_compare_intent(_intent_list, _q_cmp) is True)
_kp1, _kp2, _kfid = A.sales_compare_windows(_intent_list, TODAY, _q_cmp)
t("K4 two-window: пара WTD+prior",
  _kfid == "wtd" and bool(_kp2.get("from")), (_kfid, _kp1, _kp2))
_restore(_s)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
