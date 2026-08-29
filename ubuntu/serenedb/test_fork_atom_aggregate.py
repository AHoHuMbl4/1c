#!/usr/bin/env python3
"""Интеграционный замок шага 4: атом форка == прямой `aggregate` до копейки.

Сверяет `_fork_atom_of` после `fork_scan` с `aggregate` по той же сущности,
WHERE (match + preds) и головной величине. Расхождение — дефект п. 10 / замок §10.

Эталон ut_test ([замер 17.08]): document_приобретениетоваровуслуг.СуммаДокумента
= 73 181 157,68; accumulationregister_закупки.Сумма = 1 137 949,71.

Запуск:  python3 ubuntu/serenedb/test_fork_atom_aggregate.py
Требует живой SereneDB (SERENEDB_DSN_RO / PGPASSWORD), без модели.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _env_path in ("/etc/1c-serene-ask-ut_test.env", "/etc/1c-mcp-reports.env"):
    if os.path.isfile(_env_path):
        for _line in open(_env_path):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault(
    "SERENEDB_DSN_RO", "host=127.0.0.1 port=7890 user=serene_ro dbname=ut_test")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


def _same(a, b):
    if a is None or b is None:
        return a is b
    return round(float(a), 2) == round(float(b), 2)


def check_pair(src, measure_word, match="", preds=None):
    preds = preds or []
    mbs = A._measures_by_src([src])
    als = A._aliases_by_src([src])
    rel = A._fork_relevant(measure_word, mbs.get(src) or [], als.get(src) or {})
    rows = A.fork_scan(match, preds, {src: rel})
    if src not in rows:
        t("%s: fork_scan жив" % src, False, "нет строки")
        return
    atom = A._fork_atom_of(rows[src], [src], measure_word, want="sum",
                          rel_measures=rel)
    mid = atom.get("measure_id")
    t("%s: measure_id выбран" % src, mid is not None, "mid=%s" % mid)
    agg = A.aggregate(src, match or None, preds, measure=mid)
    t("%s: aggregate посчитан" % src, agg and agg.get("sum") is not None)
    t("%s: atom == aggregate до копейки" % src,
      _same(atom.get("exact_value"), agg.get("sum") if agg else None),
      "atom=%s agg=%s mid=%s" % (atom.get("exact_value"),
                                 agg.get("sum") if agg else None, mid))
    t("%s: count совпал" % src,
      int(rows[src].get("count") or 0) == int((agg or {}).get("count") or -1))


# ── форма «ложная пара» (замер okna 17.08): регистр, лексическая Сумма
# тождественно 0, отвечающая Всего без лексики / живая мера вне rel.
# До правки атом = 0 (computed) по мёртвой Сумма; после — Всего до копейки
# либо NA, если ответить нечем. Без базы.
_REG = "accumulationregister_реализациятмц"
_als_reg = {"Сумма": "сумма", "Всего": "итого", "Количество": "кол-во"}
_rel_reg = A._fork_relevant("сумма", ["Сумма", "Всего", "Количество"], _als_reg)
t("форма: rel = лексическая Сумма + структурная Всего",
  set(_rel_reg) == {"Сумма", "Всего"})
_atom_reg = A._fork_atom_of(
    {"count": 77381, "folders": 0,
     "sums": {"Сумма": 0.0, "Всего": 79925955.81, "Количество": 100.0}},
    [_REG], "сумма", alias_by=_als_reg, want="sum", rel_measures=_rel_reg)
t("ложная пара: не 0 по мёртвой Сумма",
  _atom_reg.get("exact_value") != 0 and _atom_reg.get("exact_value") is not None,
  "atom=%s mid=%s status=%s" % (_atom_reg.get("exact_value"),
                                _atom_reg.get("measure_id"),
                                _atom_reg.get("proof_status")))
_atom_fl = A._fork_atom_of(
    {"count": 3826, "folders": 0,
     "sums": {"Всего": 1572493.22, "СуммаБезНДС": 1310413.93}},
    ["document_выручкаотреализациитмцфизлицо_номенклатура"], "сумма",
    want="sum", rel_measures=["СуммаБезНДС", "Всего"])
t("физлицо: Всего, не СуммаБезНДС",
  _same(_atom_fl.get("exact_value"), 1572493.22)
  and _atom_fl.get("measure_id") == "Всего",
  "atom=%s mid=%s" % (_atom_fl.get("exact_value"), _atom_fl.get("measure_id")))
t("ложная пара: Всего до копейки (мера без лексики «сумма»)",
  _same(_atom_reg.get("exact_value"), 79925955.81)
  and _atom_reg.get("measure_id") == "Всего"
  and _atom_reg.get("proof_status") == A.PROOF_COMPUTED,
  "atom=%s mid=%s" % (_atom_reg.get("exact_value"), _atom_reg.get("measure_id")))
_rel_out = A._fork_relevant("сумма", ["Сумма", "Количество"], {"Сумма": "сумма"})
_atom_na = A._fork_atom_of(
    {"count": 10, "folders": 0, "sums": {"Сумма": 0.0, "Количество": 5.0}},
    [_REG], "сумма", want="sum", rel_measures=_rel_out)
t("регистр: лексическая Сумма мертва, живая мера вне rel → NA",
  _atom_na.get("proof_status") == A.PROOF_NA
  and _atom_na.get("exact_value") is None,
  "status=%s val=%s rel=%s" % (_atom_na.get("proof_status"),
                               _atom_na.get("exact_value"), _rel_out))

# clarify axis labels (offline, Э3)
_ord_cl = [
    {"srcs": ["x"], "atom": A.build_answer_atom(
        operation="sum", exact_value=1.0, measure_id="S",
        proof_status=A.PROOF_COMPUTED),
     "row": {"count": 1, "folders": 0, "sums": {"S": 1.0}}},
    {"srcs": ["x"], "atom": A.build_answer_atom(
        operation="count", exact_value=2, proof_status=A.PROOF_COMPUTED),
     "row": {"count": 2, "folders": 0, "sums": {}}},
]
_cl_opts = A._fork_clarify_opts(_ord_cl, {}, {}, {}, "", [], {},
                                "measure", "Сколько закупили товаров?")
t("clarify opts: подпись оси меры (сумм)",
  any("сумм" in (o.get("label") or "").lower() for o in _cl_opts))


try:
    check_pair("document_приобретениетоваровуслуг", "сумма")
    check_pair("accumulationregister_закупки", "сумма")
    # пара закупок — оба числа эталонные
    t("document этalon 73 181 157,68",
      _same(A.aggregate("document_приобретениетоваровуслуг", None, [],
                        measure="СуммаДокумента").get("sum"), 73181157.68))
    t("register этalon 1 137 949,71",
      _same(A.aggregate("accumulationregister_закупки", None, [],
                        measure="Сумма").get("sum"), 1137949.71))
except RuntimeError as e:
    print("SKIP: база недоступна —", str(e)[:120])
    sys.exit(0)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
