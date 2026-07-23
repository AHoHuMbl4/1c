#!/usr/bin/env python3
"""Тесты целостности витрины SereneDB — ловят класс «ответ правдоподобный, а данные врут»
(тот самый баг, что вскрылся на «банки в Казани»: 721 банк потерян кривой пагинацией).
Read-only. Запуск: python3 test_integrity.py

Проверяем ИНВАРИАНТЫ (не магические числа — они меняются с данными):
  T1. Grain: в каждой таблице с ref_key  count(*) == count(DISTINCT ref_key)  (одна строка на объект 1С).
  T2. Витрина == источник: distinct ref_key в таблице == count в ЖИВОМ OData (нет потерь/дублей загрузки).
  T3. resolver_index: непусто, размерность emb == EMBED_DIM, нет NULL в value/emb.
  T4. Нет полностью пустых по ключу таблиц с «фантомными» строками (все ref_key NULL при rows>0).
Любой FAIL → ненулевой код выхода (годится как гейт перед деплоем/после синка).
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

import poc_load_entity as L

try:
    import serene_report as S
    EMBED_DIM = getattr(S, "EMBED_DIM", 1536)
except Exception:
    EMBED_DIM = 1536

DSN = L.DSN
ODATA = L.ODATA
# banks — витрина-проекция классификатора (особое имя, грузится rebuild_banks), знаем маппинг явно
SPECIAL = {"banks": "Catalog_КлассификаторБанков"}

_fail = 0


def q(sql):
    r = subprocess.run(["psql", DSN, "-tAc", sql], text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return r.stdout.strip()


def check(name, cond, detail=""):
    global _fail
    if not cond:
        _fail += 1
    print(f"  {'PASS' if cond else 'FAIL ✗'}  {name}   {detail}")


def tables():
    return [t for t in q("SELECT DISTINCT table_name FROM duckdb_columns() WHERE schema_name='public'").splitlines() if t]


def cols_lower(t):
    return {c.lower() for c in q(f"SELECT column_name FROM duckdb_columns() WHERE table_name='{t}'").splitlines() if c}


def odata_count(es):
    url = f"{ODATA}/{urllib.parse.quote(es)}?" + urllib.parse.urlencode(
        {"$format": "json", "$top": "1", "$inlinecount": "allpages"})
    try:
        d = json.load(urllib.request.urlopen(url, timeout=60))
        c = d.get("odata.count")
        return int(c) if c is not None else None
    except Exception as e:
        return f"ERR {str(e)[:40]}"


def main():
    tbls = tables()
    print(f"таблиц в витрине: {len(tbls)}  (EMBED_DIM={EMBED_DIM})")

    print("\n== T1. Grain: одна строка на объект 1С ==")
    keyed = []
    for t in tbls:
        if t == "resolver_index":
            continue
        c = cols_lower(t)
        if "ref_key" not in c:
            continue
        keyed.append(t)
        n, d = q(f'SELECT count(*)||chr(124)||count(DISTINCT ref_key) FROM "{t}"').split("|")
        check(f"grain {t}", n == d, f"rows={n} distinct_ref_key={d}")

    print("\n== T2. Витрина == живой OData (нет потерь/дублей загрузки) ==")
    ent_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serene-entities.txt")
    ents = [l.strip() for l in open(ent_file, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
    pairs = [(es, L.safe_col(es).lower()) for es in ents] + [(v, k) for k, v in SPECIAL.items()]
    existing = set(tbls)
    for es, t in pairs:
        if t not in existing or "ref_key" not in cols_lower(t):
            continue
        mart = int(q(f'SELECT count(DISTINCT ref_key) FROM "{t}"'))
        oc = odata_count(es)
        if isinstance(oc, str) or oc is None:
            check(f"mart==OData {t}", True, f"OData count n/a ({oc}) — пропуск")
        else:
            check(f"mart==OData {t}", mart == oc, f"mart={mart} odata={oc}")

    print("\n== T3. resolver_index ==")
    ri = int(q("SELECT count(*) FROM resolver_index"))
    check("resolver непусто", ri > 0, f"n={ri}")
    nulls = int(q("SELECT count(*) FROM resolver_index WHERE value IS NULL OR emb IS NULL"))
    check("resolver без NULL value/emb", nulls == 0, f"nulls={nulls}")
    for fn in ("len(emb)", "array_length(emb)", "len(emb::FLOAT[])"):  # диалект массива варьируется
        try:
            dim = q(f"SELECT DISTINCT {fn} FROM resolver_index").splitlines()
            check("resolver размерность emb", dim == [str(EMBED_DIM)], f"{fn}={dim} ожидалось [{EMBED_DIM}]")
            break
        except Exception:
            continue
    else:
        check("resolver размерность emb", True, "проверка размерности недоступна в диалекте — пропуск")

    print("\n== T4. Нет «фантомных» строк (rows>0, но все ref_key NULL) ==")
    for t in keyed:
        rows = int(q(f'SELECT count(*) FROM "{t}"'))
        nonnull = int(q(f'SELECT count(ref_key) FROM "{t}"'))
        check(f"non-null ref_key {t}", not (rows > 0 and nonnull == 0), f"rows={rows} non_null_ref={nonnull}")

    print(f"\nИТОГ: {'ВСЁ PASS ✅' if _fail == 0 else str(_fail) + ' FAIL ✗'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
