#!/usr/bin/env python3
"""Замер косинусов резолвера: term -> ближайшее значение resolver_index + similarity. Чтобы выбрать
порог min_cos, отделяющий верные разрешения (спб/питере) от ложных (йоркшир/питре). Read-only."""
import serene_report as R

TERMS = ["спб", "питере", "питре", "йоркшир", "лондон", "москва", "казань", "ростов", "пятигорск"]
vecs = R.embed(TERMS)
for t, v in zip(TERMS, vecs):
    lit = R._vec_literal(v)
    out = R.psql(
        f"SELECT value, round(array_cosine_similarity(emb,{lit})::numeric,3) FROM resolver_index "
        f"ORDER BY 2 DESC LIMIT 1", ["-tAF", " | "]).stdout.strip()
    print(f"  {t:12} -> {out}")
