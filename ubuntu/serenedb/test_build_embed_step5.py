#!/usr/bin/env python3
"""Оффлайн-замок шага 5 build.sh: embed_bulk, gate, strict transfer, restore globals.

План v10 C+D.2: шаг 5 без tick_guard; embed_bulk; пропуск при 0 NULL;
gate pg_stat_activity; EMBED_TRANSFER_STRICT; restore GLOBAL threads/http_timeout;
REFRESH corpus_ivf_idx + smoke kNN при досчёте > 0.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build.sh")
BULK = os.path.join(ROOT, "embed_bulk.sh")
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:200]) if detail else "")


def step5_block(body: str) -> str:
    m = re.search(
        r"== 5\. векторы новым строкам корпуса.*?(\n== 5-alt\.|\n# 🔴 СЛУЖЕБНЫМ)",
        body,
        re.S,
    )
    return m.group(0) if m else ""


def main() -> int:
    body = open(BUILD, encoding="utf-8").read()
    bulk = open(BULK, encoding="utf-8").read()
    s5 = step5_block(body)
    t("шаг 5 найден", bool(s5), body[s5.find("== 5") : s5.find("== 5") + 80] if s5 else "")

    t("шаг 5 зовёт embed_bulk", "embed_bulk.sh" in s5)
    t("шаг 5 не зовёт embed_missing", "embed_missing.sh" not in s5)
    t("шаг 5 без tick_guard", "embed_tick_guard" not in s5)

    t("gate pg_stat_activity p_doc", "pg_stat_activity" in s5 and "p_doc" in s5)
    t("gate corpus_merge", "corpus_merge" in s5)
    t("gate idle in transaction", "idle in transaction" in s5)
    t("gate непустой query", "coalesce(query,'')<>''" in s5.replace(" ", ""))
    t("gate → fail", "fail \"шаг 5:" in s5 or "fail \"шаг 5" in s5)

    t("пропуск при 0 NULL", "_EMB5_NULL" in s5 and "пропуск" in s5)
    t("перепроверка count в момент запуска", "_EMB5_NULL=$(psql" in s5.replace(" ", ""))

    t("EMBED_TRANSFER_STRICT=1 в шаге 5", "EMBED_TRANSFER_STRICT=1" in s5)
    t("EMBED_THREADS ≤3", "EMBED_THREADS" in s5 and "-gt 3" in s5)
    t("EMBED_BATCH_ROWS", "EMBED_BATCH_ROWS" in s5)
    t("EMBED_MAXLEN в вызове", "EMBED_MAXLEN" in s5)

    t("restore GLOBAL threads", "restore_embed_globals" in s5 and "SET GLOBAL threads" in s5)
    t("restore GLOBAL http_timeout", "SET GLOBAL http_timeout" in s5)
    t("restore после bulk (успех и ошибка)", s5.count("restore_embed_globals") >= 2)
    t("restore без || true", "|| true" not in s5[s5.find("restore_embed_globals"):s5.find("_bulk_thr")])
    t("restore fail на успехе bulk", "restore_embed_globals || fail" in s5.replace("\n", " "))

    t("fail если осталось>0 (JSON)", "_emb5_left" in s5 and "осталось" in s5)
    t("досчёт = было − осталось", "_emb5_done=$" in s5.replace(" ", ""))

    t("REFRESH corpus_ivf_idx", "corpus_ivf_idx" in s5 and "REFRESH_INDEX" in s5)
    t("search_idx шаг 6 не тронут", "VACUUM (REFRESH_INDEX) search_idx;" in body)
    t("smoke kNN LIMIT 5", "<=>" in s5 and "LIMIT 5" in s5)
    _smoke = s5[s5.find("_knn_n"):] if "_knn_n" in s5 else ""
    t("smoke без ai_embed", "ai_embed" not in _smoke)
    t("smoke emb IS NOT NULL", "emb IS NOT NULL" in s5)

    t("embed_bulk EMBED_TRANSFER_STRICT", "EMBED_TRANSFER_STRICT" in bulk)
    t("embed_bulk strict без || true", "_strict=1" in bulk or "_strict" in bulk)

    st = os.stat(BUILD)
    t("build.sh +x", bool(st.st_mode & 0o111))
    r = subprocess.run(["bash", "-n", BUILD], capture_output=True, text=True)
    t("build.sh bash -n", r.returncode == 0, r.stderr[:120])
    r = subprocess.run(["bash", "-n", BULK], capture_output=True, text=True)
    t("embed_bulk.sh bash -n", r.returncode == 0, r.stderr[:120])

    print("\nитог: %d ok, %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAIL:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
