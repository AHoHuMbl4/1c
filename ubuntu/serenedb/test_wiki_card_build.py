#!/usr/bin/env python3
"""Оффлайн-замок Б1–Б2: wiki_card_build.sql + wiki_card_knn.sql.

Без сети и живой базы. Проверяет: сборка из wiki_pages/refcols/measure_alias,
MERGE, ivf+cosine, top-5 kNN, отсутствие предметных имён сущностей okna в SQL.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "wiki_card_build.sql"
KNN = ROOT / "wiki_card_knn.sql"

PASS, FAIL = 0, []

# Явные имена сущностей okna — не должны быть в SQL (п. 0 TARGET).
FORBIDDEN_ENTITY = re.compile(
    r"(?i)(accumulationregister_|catalog_)(?:остат|номенклат|контрагент|реализац|"
    r"склад|продаж|клиент|товар|warehouse|nomenclature|counterpart)",
)

# Маршрутизационные слова домена в строковых литералах SQL (не в комментариях на русском).
DOMAIN_LITERAL = re.compile(
    r"(?i)['\"][^'\"]{0,200}(?:остат|склад|warehouse|позиц|номенклат|товар|"
    r"контрагент|клиент|продаж|sale|revenue)[^'\"]{0,200}['\"]",
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def strip_sql_comments(text: str) -> str:
    text = re.sub(r"--[^\n]*", "", text)
    return text


def main() -> int:
    build = BUILD.read_text(encoding="utf-8")
    knn = KNN.read_text(encoding="utf-8")
    combined = strip_sql_comments(build + "\n" + knn)

    t("wiki_card_build.sql exists", BUILD.is_file())
    t("wiki_card_knn.sql exists", KNN.is_file())

    t("uses wiki_pages", "wiki_pages" in build)
    t("uses search_refcols", "search_refcols" in build)
    t("uses search_measure_alias", "search_measure_alias" in build)
    t("MERGE into card table", "MERGE INTO search_wiki_entity_card" in build)
    t("covered flag", re.search(r"\bcovered\b", build) is not None)
    t("card_text for embed", "card_text" in build)
    t("emb reset before MERGE", "SET emb = NULL" in build)
    t("ivf cosine index", "emb ivf (metric = 'cosine')" in build)
    t("no hnsw", "hnsw" not in build.lower())

    t("kNN LIMIT 5", "LIMIT 5" in knn)
    t("kNN uses ai_embed", "ai_embed" in knn)
    t("kNN cosine distance", "<=>" in knn)
    t("kNN returns axes measures", "c.axes" in knn and "c.measures" in knn)

    t("okna_entity_hardcode_scan", FORBIDDEN_ENTITY.search(combined) is None,
      FORBIDDEN_ENTITY.search(combined).group(0)[:60] if FORBIDDEN_ENTITY.search(combined) else "")
    t("domain_routing_literal_scan", DOMAIN_LITERAL.search(combined) is None,
      DOMAIN_LITERAL.search(combined).group(0)[:60] if DOMAIN_LITERAL.search(combined) else "")

    r = subprocess.run([sys.executable, "-m", "py_compile", __file__],
                       capture_output=True, text=True)
    t("self py_compile", r.returncode == 0, r.stderr[:120])

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
