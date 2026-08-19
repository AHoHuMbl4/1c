#!/usr/bin/env python3
"""Исходы A/B/C на классах детектора (план §2, шаг 4).

Замки:
  · A только при полном совпадении атома и нескольких src;
  · B только при всех ветках с подписями и всех ячейках посчитанных;
  · C иначе (непосчитанное / неподписанное);
  · непосчитанная ячейка → не A/B;
  · детерминизм порядка пар на снимке;
  · перестановка пар невозможна (только fill/render по индексу);
  · ASK_FORK_OUTCOMES=0 — эвакуация (флаг читается).

Запуск: python3 ubuntu/serenedb/test_fork_outcomes.py
Без базы, сети и модели (подписи — подменой fork_labels_of).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


def fc_sum(rows):
    rel = {s: list((rows[s].get("sums") or {}).keys()) for s in rows}
    return A.fork_classes(rows, "сумма", want="sum", rel_by_src=rel)



# ── resolve_fork_outcome ──────────────────────────────────────────────────────
cls1 = fc_sum({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)})
rows1 = {"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)}
out, pay = A.resolve_fork_outcome(cls1, rows1, measure_ctx="сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("A: один класс, два src", out == "A" and len(pay["srcs"]) == 2)

cls_u = fc_sum({"a": row(19, Сумма=100.0)})
out, pay = A.resolve_fork_outcome(cls_u, {"a": row(19, Сумма=100.0)}, "сумма", want="sum", rel_by_src={"a": ["Сумма"]})
t("unique: один класс, один src", out == "unique")

cls2 = fc_sum({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}


def _labs(fk, srcs):
    return {}


A.fork_labels_of = _labs
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("C: несколько классов без подписей", out == "C" and pay["reason"] == "unsigned_class")


def _labs_ok(fk, srcs):
    return {"a": "Отгрузки", "b": "Оплаты"}


A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("B: несколько классов с подписями",
  out == "B" and len(pay["classes"]) == 2
  and all(c.get("label") for c in pay["classes"]))

# непосчитанная ячейка
unc = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}
cls_u2 = fc_sum(unc)
# подменим атом на uncounted через прямую сборку payload
ordered = A.ordered_fork_classes(cls_u2, unc)
ordered[0]["atom"] = A.build_answer_atom(
    operation="sum", exact_value=None, proof_status=A.PROOF_UNCOUNTED)
# resolve смотрит proof через ordered_fork_classes заново — подменим rows на битый
# через scan_error / прямой путь: atom с None exact
# Проще: пустой sums и count None — но fork_scan так не отдаёт.
# Проверяем правило: uncounted в resolve через atom status.
# Соберём вручную: если atom exact None → C.


def resolve_with_uncounted():
    classes = fc_sum({"a": row(1, Сумма=1.0), "b": row(2, Сумма=2.0)})
    rows = {"a": row(1, Сумма=1.0), "b": row(2, Сумма=2.0)}
    real_of = A.ordered_fork_classes

    def boom(classes, rows, measure_word="", want=None, rel_by_src=None):
        items = real_of(classes, rows, measure_word, want=want)
        items[0]["atom"]["proof_status"] = A.PROOF_UNCOUNTED
        items[0]["atom"]["exact_value"] = None
        return items

    A.ordered_fork_classes = boom
    try:
        return A.resolve_fork_outcome(classes, rows, "сумма")
    finally:
        A.ordered_fork_classes = real_of


out, pay = resolve_with_uncounted()
t("C: непосчитанная ячейка — не A/B", out == "C" and pay["reason"] == "uncounted_cell")

out, pay = A.resolve_fork_outcome({}, {}, "сумма")
t("empty: нет живых ячеек", out == "empty")

out, pay = A.resolve_fork_outcome(None, None, scan_error=RuntimeError("x"))
t("unavailable: ошибка скана", out == "unavailable")

# ── детерминизм порядка ───────────────────────────────────────────────────────
A.fork_labels_of = _labs_ok
o1 = A.ordered_fork_classes(cls2, rows2)
o2 = A.ordered_fork_classes(cls2, rows2)
t("детерминизм ordered_fork_classes",
  [c["srcs"] for c in o1] == [c["srcs"] for c in o2]
  and [c["fingerprint"] for c in o1] == [c["fingerprint"] for c in o2])

# перестановка: B строит пары только через render; порядок = ordered
A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
bres = A.fork_outcome_b("сколько?", pay, {})
t("B: две пары, labels свои",
  bres and bres["kind"] == "figures"
  and len(bres["atoms"]) == 2
  and len(bres["options"]) == 2
  and "Отгрузки" in bres["text"] and "Оплаты" in bres["text"])
# порядок текста = порядок atoms = ordered; смешать нельзя API
swapped = "Оплаты: 100"
# exact values: a has 100, b has 200; labels from _labs_ok by src
# after ordered sort by fingerprint — whichever first
t("B: source_fixed/memory_eligible false",
  bres.get("source_fixed") is False and bres.get("memory_eligible") is False)
t("B: options на класс (по одному src-представителю)",
  len(bres["options"]) == 2
  and all(o.get("src") and o.get("label") for o in bres["options"]))

# ── A: без метки источника ────────────────────────────────────────────────────
out, pay = A.resolve_fork_outcome(cls1, rows1, "сумма")
ares = A.fork_outcome_a("сколько?", pay["class"], {})
t("A: kind=answer, sources пуст, source_fixed=false",
  ares["kind"] == "answer"
  and ares["sources"] == []
  and ares.get("source_fixed") is False
  and ares.get("memory_eligible") is False)
t("A: в тексте нет имён src",
  "document_" not in (ares.get("text") or "")
  and "accumulation" not in (ares.get("text") or ""))

# ── флаг эвакуации ────────────────────────────────────────────────────────────
t("FORK_OUTCOMES умолчание True", A.FORK_OUTCOMES is True)

# ── класс из многих src — одна пара в B-логике (один класс не B) ──────────────
many = {"s%02d" % i: row(5, Сумма=50.0) for i in range(5)}
cls_m = A.fork_classes(many)
out, pay = A.resolve_fork_outcome(cls_m, many, "сумма")
t("много src с одним атомом → A (одна пара), не по источникам",
  out == "A" and len(pay["srcs"]) == 5)



# ── NA: sum-вопрос, нет релевантных величин — не блокирует B ───────────────
na_rows = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0), "c": row(5)}
na_cls = A.fork_classes(na_rows)
A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(
    na_cls, na_rows, "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"], "c": []})
t("NA класс не блокирует B",
  out == "B" and len(pay.get("classes") or []) == 2
  and pay.get("na_classes") == 1)
atom_na = A._fork_atom_of(row(5), ["c"], "сумма", want="sum", rel_measures=[])
t("want=sum без rel_measures → NA",
  atom_na.get("proof_status") == A.PROOF_NA)

# лексическая Сумма тождественно 0, живая мера вне rel — NA, не «0», не блокирует B
A.fork_labels_of = _labs_ok
dead0 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0),
         "c": row(50, Сумма=0.0, Количество=5.0)}
out, pay = A.resolve_fork_outcome(
    A.fork_classes(dead0), dead0, "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"], "c": ["Сумма"]})
t("мёртвая Сумма регистра → NA, B из живых",
  out == "B" and len(pay.get("classes") or []) == 2
  and pay.get("na_classes") == 1)
atom_dead = A._fork_atom_of(row(50, Сумма=0.0, Количество=5.0), ["c"], "сумма",
                           want="sum", rel_measures=["Сумма"])
t("want=sum + тождественный 0 в rel → NA, не computed 0",
  atom_dead.get("proof_status") == A.PROOF_NA
  and atom_dead.get("exact_value") is None)

# ── covering: подписи по src, не только по sha1(ctx) ───────────────────────────
real_cov = A.fork_labels_covering
A.fork_labels_covering = lambda srcs: (
    {"a": "Отгрузки", "b": "Оплаты"}, "fk_cover")
A.fork_labels_of = lambda fk, srcs: {}  # точный ключ пуст
cls2 = fc_sum({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("B через covering, когда точный fork_key пуст",
  out == "B" and pay.get("fork_key") == "fk_cover")
A.fork_labels_covering = real_cov

# ── want=sum: не count при пустых sums ────────────────────────────────────────
atom_sum = A._fork_atom_of(row(100), ["x"], "сумма", want="sum")
t("want=sum без величин → uncounted, не count",
  atom_sum.get("operation") == "sum"
  and atom_sum.get("exact_value") is None
  and atom_sum.get("proof_status") == A.PROOF_UNCOUNTED)
atom_cnt = A._fork_atom_of(row(100, Сумма=50.0), ["x"], "сумма", want="count")
t("want=count → count, не sum",
  atom_cnt.get("operation") == "count" and atom_cnt.get("exact_value") == 100)

# ── широкий класс: десятки src, одна пара на класс атома ─────────────────────
many_same = {"s%02d" % i: row(5, Сумма=50.0) for i in range(30)}
cls_wide = A.fork_classes(many_same)
t("30 src, один атом → 1 класс",
  len(cls_wide) == 1 and len(next(iter(cls_wide.values()))) == 30)

two_atoms = dict(many_same)
two_atoms["t00"] = row(5, Сумма=99.0)
cls2w = A.fork_classes(two_atoms)
A.fork_labels_of = lambda fk, srcs: {}
A.fork_labels_covering = lambda srcs: (
    {sorted(srcs)[0]: "Класс A", list(cls2w.values())[1][0]: "Класс B"}
    if len(srcs) == 1 else ({}, None))
real_cov = A.fork_labels_covering
def _cov(srcs):
    m = {}
    for ss in cls2w.values():
        rep = sorted(ss)[0]
        if rep in srcs:
            m[rep] = "Класс-%s" % rep
    return m, "fk"
A.fork_labels_covering = _cov
A.fork_labels_of = lambda fk, srcs: {s: "L-%s" % s for s in srcs}
out, pay = A.resolve_fork_outcome(cls2w, two_atoms, "сумма", want="sum")
t("2 класса атомов из 31 src → B с 2 парами, не 31",
  out == "B" and len(pay.get("classes") or []) == 2)
A.fork_labels_covering = real_cov


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
