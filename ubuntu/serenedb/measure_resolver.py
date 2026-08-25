#!/usr/bin/env python3
"""Стендовый замер косинусов резолвера (НЕ часть такта сборки / Ф6).

term → ближайшее значение resolver_index + similarity. Чтобы выбрать порог
min_cos, отделяющий верные разрешения от ложных (см. serene_report._semantic_into).
Read-only.

🔴 Термы — только argv. Списков городов/сущностей в коде нет: на чужой базе
вызывающий передаёт свой набор. Без аргументов — usage и код 2.
Примеры стенда (не код, только подсказка usage): спб питере питре йоркшир …
"""
import sys
import serene_report as R


def main(argv=None) -> int:
    terms = list(argv if argv is not None else sys.argv[1:])
    if not terms:
        print(
            "usage: measure_resolver.py <term> [term...]\n"
            "стенд: термы передаёт вызывающий; списков значений в коде нет",
            file=sys.stderr,
        )
        return 2
    vecs = R.embed(terms)
    for t, v in zip(terms, vecs):
        lit = R._vec_literal(v)
        out = R.psql(
            # cosine_similarity — родная функция движка; печатаем похожесть, а не расстояние,
            # чтобы числа сравнивались с порогом 0.70 из _semantic_into напрямую.
            f"SELECT value, round(cosine_similarity(emb,{lit})::numeric,3) FROM resolver_index "
            f"ORDER BY 2 DESC LIMIT 1", ["-tAF", " | "]).stdout.strip()
        print(f"  {t:12} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
