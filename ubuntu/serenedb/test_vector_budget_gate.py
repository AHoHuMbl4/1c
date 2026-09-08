#!/usr/bin/env python3
"""Оффлайн: гейт вектор-бюджета + content_hash (стоп ДО записи в search_corpus).

Порог — ДОЛЯ от векторов базы (MERGE_VECTOR_LOSS_TOLERANCE, умолчание 0.5%).
Потеря = было − живут(тот же row_key + hash/common_eq) − карта xfer (rewrite_wave).

Запуск: python3 test_vector_budget_gate.py
"""
import hashlib
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(ROOT, "corpus_merge.sql")
BUILD = os.path.join(ROOT, "build.sh")
INIT = os.path.join(ROOT, "corpus_init.sql")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:220] if detail else "")


def doc_bmap(doc):
    out = {}
    if not doc:
        return out
    for p in doc.split(" | "):
        i = p.find(": ")
        if i <= 0:
            continue
        out[p[:i]] = p[i + 2 :]
    return out


def content_hash(doc):
    m = doc_bmap(doc)
    parts = []
    for k in sorted(m):
        if k in ("DataVersion", "__metadata"):
            continue
        if "navigationLinkUrl" in k:
            continue
        if m[k] == "":
            continue
        parts.append(k + "\x01" + m[k])
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def bmap_common_eq(a, b):
    common = set(a) & set(b)
    if not common:
        return False
    return all(a[k] == b[k] for k in common)


def default_tol():
    raw = os.environ.get("MERGE_VECTOR_LOSS_TOLERANCE", "0.005")
    try:
        v = float(raw)
    except ValueError:
        v = 0.005
    return v if v > 0 else 0.005


def emb_xfer_map(old_rows, new_rows):
    def ch_of(r):
        return r.get("content_hash") or content_hash(r.get("doc") or "")

    old_by_ch = defaultdict(list)
    old_by_refs = defaultdict(list)
    for o in old_rows:
        if o.get("emb") is None:
            continue
        old_by_ch[(o["src_table"], ch_of(o))].append(o)
        refs = o.get("refs") or ""
        if refs:
            old_by_refs[(o["src_table"], refs)].append(o)
    new_by_ch = defaultdict(list)
    new_by_refs = defaultdict(list)
    for n in new_rows:
        new_by_ch[(n["src_table"], ch_of(n))].append(n)
        refs = n.get("refs") or ""
        if refs:
            new_by_refs[(n["src_table"], refs)].append(n)
    best = {}
    for key, news in new_by_ch.items():
        olds = old_by_ch.get(key, [])
        if len(olds) == 1 and len(news) == 1:
            n = news[0]
            best[(n["src_table"], n["row_key"])] = 1
    for key, news in new_by_refs.items():
        olds = old_by_refs.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        o, n = olds[0], news[0]
        if bmap_common_eq(doc_bmap(o["doc"]), doc_bmap(n["doc"])):
            best.setdefault((n["src_table"], n["row_key"]), 2)
    return set(best)


def vec_budget(old_rows, new_rows, *, rewrite_wave=None, use_xfer=True,
               deleted=None, collapse=None):
    # deleted/collapse — сущности с ОБЪЯСНЁННОЙ убылью (key_deleted_delta /
    # key_collapse в corpus_merge.sql): их unmatched — не потеря.
    rewrite_wave = set(rewrite_wave or [])
    deleted = set(deleted or [])
    collapse = set(collapse or [])

    def ch_of(r):
        return r.get("content_hash") or content_hash(r.get("doc") or "")

    old_emb = [o for o in old_rows if o.get("emb") is not None]
    was_total = len(old_emb)
    new_idx = {
        (n["src_table"], n["row_key"]): (ch_of(n), doc_bmap(n.get("doc") or ""))
        for n in new_rows
    }
    surviving = 0
    hash_kill = 0
    unmatched_kill = 0
    by = defaultdict(lambda: {
        "was": 0, "surviving": 0, "hash_kill": 0, "unmatched": 0, "saved": 0,
    })
    for o in old_emb:
        st, rk = o["src_table"], o["row_key"]
        by[st]["was"] += 1
        och = ch_of(o)
        ob = doc_bmap(o.get("doc") or "")
        if (st, rk) not in new_idx:
            unmatched_kill += 1
            by[st]["unmatched"] += 1
            continue
        nch, nb = new_idx[(st, rk)]
        if nch == och or bmap_common_eq(ob, nb):
            surviving += 1
            by[st]["surviving"] += 1
        else:
            hash_kill += 1
            by[st]["hash_kill"] += 1

    saved = set()
    if use_xfer and rewrite_wave:
        saved = {
            (st, rk) for st, rk in emb_xfer_map(old_rows, new_rows)
            if st in rewrite_wave
        }
    for st, _rk in saved:
        by[st]["saved"] += 1
    saved_n = len(saved)
    # «Умерёт» = ОКОНЧАТЕЛЬНАЯ потеря (правка 08.09, синхронно corpus_merge.sql):
    # hash_kill НЕ входит (строка жива, шаг 5 пересчитает emb на месте);
    # unmatched вычитается ПОСТРОЧНО, если контент (content_hash) жив в новой
    # сборке той же сущности (замена ключа), либо сущность объяснена целиком
    # (deleted/collapse — витрина; wave — замена формы ключа с сохранением
    # объёма: векторы вернёт xfer-карта/шаг 5, функциональность не теряется).
    new_ch_by_st = defaultdict(set)
    for n_ in new_rows:
        new_ch_by_st[n_["src_table"]].add(ch_of(n_))
    old_rows_by = defaultdict(list)
    for o in old_emb:
        old_rows_by[o["src_table"]].append(o)
    died = 0
    for st, rows in old_rows_by.items():
        if st in rewrite_wave or st in deleted or st in collapse:
            continue
        new_ch_n = {}
        for n_ in new_rows:
            new_ch_n[(n_["src_table"], ch_of(n_))] = new_ch_n.get((n_["src_table"], ch_of(n_)), 0) + 1
        for o in rows:
            if (o["src_table"], o["row_key"]) in new_idx:
                continue  # не unmatched
            och = ch_of(o)
            # 1:1-уникальность (как пара xfer-карты): дубли ch не объясняются
            old_ch_n = sum(1 for r in rows if ch_of(r) == och)
            if old_ch_n == 1 and new_ch_n.get((st, och), 0) == 1:
                continue  # единственный контент пришёл единственной строкой
            # НЕ-1:1 приход с балансом кратности тоже честен: 2 старых дубля
            # ушли, 2 новых дубля пришли — счётный баланс по группе ch.
            if new_ch_n.get((st, och), 0) >= old_ch_n:
                continue
            died += 1

    reason = "ok"
    if unmatched_kill > 0 and any(
        st in rewrite_wave and by[st]["saved"] == 0 for st in by
    ):
        reason = "rewrite_wave без карты"
    elif unmatched_kill > 0 and any(st in rewrite_wave for st in by):
        reason = "rewrite_wave: unmatched минус карта"
    elif unmatched_kill > 0:
        reason = "unmatched"
    elif hash_kill > 0:
        reason = "content_hash/значение-изменение вне карты"

    frac = (died / was_total) if was_total else 0.0
    return {
        "died": died, "was": was_total, "surviving": surviving, "saved": saved_n,
        "hash_kill": hash_kill, "unmatched": unmatched_kill, "reason": reason,
        "fraction": frac, "by_table": dict(by),
    }


def gate_fires(budget, tol=None):
    tol = default_tol() if tol is None else tol
    if budget["was"] == 0:
        return False
    return budget["fraction"] > tol


# --- 1. смена формы (порядок/пустые/шум), тот же row_key → потерь 0 ---
old_form = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Номенклатура: X | Цена: 100", "emb": [0.1],
}]
new_form = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Цена: 100 | Номенклатура: X | Организация: | DataVersion: 3",
}]
b1 = vec_budget(old_form, new_form, use_xfer=False)
t("form-only same key: content_hash equal",
  content_hash(old_form[0]["doc"]) == content_hash(new_form[0]["doc"]))
t("form-only same key: died=0", b1["died"] == 0, b1)
t("form-only same key: gate quiet", not gate_fires(b1))
t("form-only same key: surviving=1", b1["surviving"] == 1 and b1["saved"] == 0)
t("form-only reorder: hash equal",
  content_hash("t | A: 1 | B: 2") == content_hash("t | B: 2 | A: 1"))

# форма с новой заполненной колонкой → hash другой, common_eq спасает
old_ff = [{
    "src_table": "e", "row_key": "k1", "refs": "Номенклатура: X",
    "doc": "уст | Номенклатура: X | Цена: 100", "emb": [0.1],
}]
new_ff = [{
    "src_table": "e", "row_key": "k1", "refs": "Номенклатура: X",
    "doc": "уст | Номенклатура: X | Цена: 100 | Организация: ООО",
}]
b1b = vec_budget(old_ff, new_ff, use_xfer=False)
t("form filled col: hash differs",
  content_hash(old_ff[0]["doc"]) != content_hash(new_ff[0]["doc"]))
t("form filled col: common_eq → died=0", b1b["died"] == 0 and b1b["surviving"] == 1, b1b)


# --- 5. (08.09) hash_kill при ЖИВОЙ строке — не потеря: emb пересчитает шаг 5 ---
old_hk = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Цена: 100", "emb": [0.1],
}]
new_hk = [{
    "src_table": "e", "row_key": "k1", "refs": "r",
    "doc": "уст | Цена: 200",   # значение изменилось, ключ жив
}]
b5 = vec_budget(old_hk, new_hk, use_xfer=False)
t("hash_kill живая строка: hash_kill=1", b5["hash_kill"] == 1, b5)
t("hash_kill живая строка: died=0 (пересчёт шагом 5)", b5["died"] == 0, b5)
t("hash_kill живая строка: gate quiet", not gate_fires(b5))

# --- 6. (08.09) unmatched при объяснённой убыли (deleted) — не потеря ---
old_del = [{
    "src_table": "d", "row_key": "k%d" % i, "refs": "r",
    "doc": "уст | Цена: %d" % i, "emb": [0.1],
} for i in range(10)]
b6 = vec_budget(old_del, [], use_xfer=False, deleted={"d"})
t("deleted-сущность: unmatched=10", b6["unmatched"] == 10, b6)
t("deleted-сущность: died=0 (убыль объяснена витриной)", b6["died"] == 0, b6)
t("deleted-сущность: gate quiet", not gate_fires(b6))

# --- 7. (08.09) необъяснённый unmatched — потеря, гейт стреляет ---
old_un = [{
    "src_table": "u", "row_key": "k%d" % i, "refs": "r",
    "doc": "уст | Цена: %d" % i, "emb": [0.1],
} for i in range(10)]
b7 = vec_budget(old_un, [], use_xfer=False)
t("необъяснённый unmatched: died=10", b7["died"] == 10, b7)
t("необъяснённый unmatched: gate fires", gate_fires(b7))

# --- 2. перепроведение со сменой значения → только изменённые ---
old_val = [
    {"src_table": "e", "row_key": "k1", "doc": "t | V: 1", "emb": [1.0]},
    {"src_table": "e", "row_key": "k2", "doc": "t | V: 2", "emb": [2.0]},
    {"src_table": "e", "row_key": "k3", "doc": "t | V: 3", "emb": [3.0]},
]
new_val = [
    {"src_table": "e", "row_key": "k1", "doc": "t | V: 1"},
    {"src_table": "e", "row_key": "k2", "doc": "t | V: 99"},
    {"src_table": "e", "row_key": "k3", "doc": "t | V: 3"},
]
b2 = vec_budget(old_val, new_val, use_xfer=True)
t("value change: hash_kill=1", b2["hash_kill"] == 1, b2)
t("value change: surviving=2", b2["surviving"] == 2, b2)
t("value change: died=0 (живая строка, шаг 5 пересчитает)", b2["died"] == 0, b2)
t("value change: reason", "content_hash" in b2["reason"] or "значение" in b2["reason"])
t("value change 33%: quiet (пересчёт ≠ потеря)", not gate_fires(b2, 0.005))
t("value change 33%: quiet at tol=0.5", not gate_fires(b2, 0.5))

# --- 3. волна 30% вне карты → стоп ---
n = 100
old_wave = [
    {"src_table": "e", "row_key": "o%d" % i, "refs": "r%d" % i,
     "doc": "t | K: %d | V: %d" % (i, i), "emb": [float(i)]}
    for i in range(n)
]
new_wave = []
for i in range(n):
    if i < 70:
        # равный канон (перестановка) → content_hash xfer
        new_wave.append({
            "src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
            "doc": "t | V: %d | K: %d" % (i, i),
        })
    else:
        new_wave.append({
            "src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
            "doc": "t | K: %d | V: %d" % (i, i + 1000),
        })
b3 = vec_budget(old_wave, new_wave, rewrite_wave={"e"}, use_xfer=True)
t("wave 30% loss: saved=70", b3["saved"] == 70, b3)
t("wave 30% loss: died=0 (волна объяснена, объём сохранён)", b3["died"] == 0, b3)
t("wave 30% loss: fraction=0", b3["fraction"] == 0.0, b3)
t("wave 30% loss: gate quiet", not gate_fires(b3, 0.005))
t("wave 30% loss: reason rewrite/unmatched",
  "rewrite_wave" in b3["reason"] or "unmatched" in b3["reason"], b3["reason"])

b3b = vec_budget(old_wave, new_wave, rewrite_wave={"e"}, use_xfer=False)
t("wave no map: died=0 (волна объяснена и без карты)", b3b["died"] == 0)
t("wave no map: reason без карты",
  b3b["reason"] == "rewrite_wave без карты", b3b["reason"])

# --- 4. потеря 0.3% ниже порога ---
n4 = 1000
old4 = [
    {"src_table": "e", "row_key": "o%d" % i, "refs": "r%d" % i,
     "doc": "t | K: %d" % i, "emb": [1.0]}
    for i in range(n4)
]
new4 = [
    {"src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
     "doc": ("t | K: %d" % i) if i < 997 else ("t | K: %d | X: 1" % i)}
    for i in range(n4)
]
# last 3: add filled col with no common? K still common with same value → common_eq!
# need real value change for the 3
new4 = [
    {"src_table": "e", "row_key": "n%d" % i, "refs": "r%d" % i,
     "doc": ("t | K: %d" % i) if i < 997 else ("t | K: %d" % (i + 5000))}
    for i in range(n4)
]
b4 = vec_budget(old4, new4, rewrite_wave={"e"}, use_xfer=True)
t("0.3% loss: died=0 (волна объяснена)", b4["died"] == 0, b4)
t("0.3% loss: fraction=0", b4["fraction"] == 0.0, b4)
t("0.3% loss: gate quiet", not gate_fires(b4, 0.005))


# --- 8. (армия 08.09) 1000 старых дублей одного ch, 1 новый → потеря ловится ---
old_dup = [{
    "src_table": "z", "row_key": "o%d" % i, "refs": "r",
    "doc": "t | K: dup", "emb": [0.1],      # одинаковый контент у всех
} for i in range(1000)]
new_dup = [{"src_table": "z", "row_key": "n0", "refs": "r", "doc": "t | K: dup"}]
b8 = vec_budget(old_dup, new_dup, use_xfer=False)
t("1000 дублей ch -> 1 новый: died=1000 (не маскируется)", b8["died"] == 1000, b8)
t("1000 дублей ch -> 1 новый: gate fires", gate_fires(b8))
b8b = vec_budget(old_dup, old_dup[:], use_xfer=False)  # все 1000 пришли
# keys различаются? old_dup vs копия old_dup: те же ключи -> surviving
t("1000 дублей, ключи те же: died=0", b8b["died"] == 0, b8b)

# --- 9. (армия 08.09) happy-path: 1000 ключей сменились, 1000 того же ch пришли ---
old_hp = [{
    "src_table": "h", "row_key": "o%d" % i, "refs": "r%d" % i,
    "doc": "t | K: %d" % (i % 50), "emb": [0.1],   # 50 значений × ~20 дублей
} for i in range(1000)]
new_hp = [{
    "src_table": "h", "row_key": "n%d" % i, "refs": "r%d" % i,
    "doc": "t | K: %d" % (i % 50),
} for i in range(1000)]
b9 = vec_budget(old_hp, new_hp, use_xfer=False)
t("1000→1000 баланс ch: died=0 (замена ключей)", b9["died"] == 0, b9)
t("1000→1000 баланс ch: gate quiet", not gate_fires(b9))

# --- 5. порог из env ---
t("default tol 0.005", default_tol() == 0.005)
_saved = os.environ.get("MERGE_VECTOR_LOSS_TOLERANCE")
os.environ["MERGE_VECTOR_LOSS_TOLERANCE"] = "0.01"
t("env tol 0.01", default_tol() == 0.01)
if _saved is None:
    os.environ.pop("MERGE_VECTOR_LOSS_TOLERANCE", None)
else:
    os.environ["MERGE_VECTOR_LOSS_TOLERANCE"] = _saved
t("env restored", default_tol() == (float(_saved) if _saved else 0.005))

# --- grep ---
txt = open(MERGE, encoding="utf-8").read()
bsh = open(BUILD, encoding="utf-8").read()
init = open(INIT, encoding="utf-8").read()

t("SQL: tmp3_merge_vec_budget", "CREATE OR REPLACE TABLE tmp3_merge_vec_budget AS" in txt)
t("SQL: error vector-budget", "вектор-бюджет" in txt)
t("SQL: vector_loss_gate", "vector_loss_gate" in txt)
t("SQL: vector_loss_bypass", "vector_loss_bypass" in txt)
t("SQL: reason rewrite_wave без карты", "rewrite_wave без карты" in txt)
t("SQL: reason unmatched", "THEN 'unmatched'" in txt)
t("SQL: reason content_hash/значение",
  "content_hash/значение-изменение вне карты" in txt)
t("SQL: tol 0.005", "vector_loss_tol" in txt and "0.005" in txt)
t("SQL: gate BEFORE MERGE",
  txt.find("tmp3_merge_vec_budget") < txt.find("MERGE INTO search_corpus"))
t("SQL: gate BEFORE DELETE unmatched keys",
  txt.find("вектор-бюджет")
  < txt.find("DELETE FROM search_corpus c\nWHERE c.src_table IN"))
t("SQL: content_hash fill AFTER gate",
  txt.find("вектор-бюджет")
  < txt.find("миграция content_hash пачками"))
t("SQL: миграция content_hash пачками (не одним UPDATE)",
  "tmp3_ch_jobs" in txt
  and "UPDATE search_corpus SET content_hash = corpus_content_hash(doc) WHERE content_hash IS NULL AND doc IS NOT NULL AND src_table IN (" in txt
  and txt.find("UPDATE search_corpus SET content_hash") < txt.find("MERGE INTO search_corpus AS t"))
t("SQL: монолитного UPDATE-миграции нет",
  "UPDATE search_corpus SET content_hash = corpus_content_hash(doc)\nWHERE content_hash IS NULL AND doc IS NOT NULL;" not in txt)
t("SQL: MATCHED content_hash + common_eq keep emb",
  "WHEN MATCHED AND t.content_hash IS DISTINCT FROM s.content_hash" in txt
  and "THEN t.emb ELSE NULL END" in txt)
t("SQL: row_key join unchanged",
  "ON t.src_table = s.src_table AND t.row_key = s.row_key" in txt)
t("init: corpus_content_hash", "CREATE OR REPLACE MACRO corpus_content_hash(doc)" in init)
# [замер 01.09 okna] map_from_entries падал на дублирующихся ключах (значение с ' | '
# и 'x: y' внутри) — «Map keys must be unique», такт умирал в миграции content_hash.
# Формула обязана схлопывать дубли map_concat'ом (последний выигрывает) и не звать
# map_from_entries на необработанном списке пар.
t("init: bmap дедуп дублей ключей",
  "list_reduce(" in init and "(acc, m) -> map_concat(acc, m)" in init)
t("init: bmap без сырого map_from_entries",
  init.find("map_from_entries(\n") == -1)
t("merge: bmap дедуп дублей ключей",
  "list_reduce(" in txt and "(acc, m) -> map_concat(acc, m)" in txt)
t("merge: bmap пустой список вне reduce (CASE len=0 раньше)",
  0 < txt.find("THEN MAP{}::MAP(VARCHAR, VARCHAR)")
  < txt.find("list_reduce("))
t("init: content_hash column", "content_hash VARCHAR" in init)
t("build.sh: MERGE_VECTOR_LOSS_TOLERANCE", "MERGE_VECTOR_LOSS_TOLERANCE" in bsh)
t("build.sh: MERGE_VECTOR_LOSS_BYPASS", "MERGE_VECTOR_LOSS_BYPASS" in bsh)
t("build.sh: cfg vector_loss_tol",
  "vector_loss_tol" in bsh and "vector_loss_bypass" in bsh)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
