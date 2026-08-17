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
    atom = A._fork_atom_of(rows[src], [src], measure_word)
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
