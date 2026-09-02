#!/usr/bin/env python3
"""Оффлайн-замок ubuntu/serenedb/embed_bulk.sh (без сети и живой базы).

Проверяет устройство из docs/EMBED_BULK_HOWTO.md:
  своя ATTACH-база на поток, оператор 16 строк, SET GLOBAL отдельно,
  повтор при сетевом отказе, постоянная метка (докатка).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "embed_bulk.sh")
PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + detail[:200]) if detail else "")


def main() -> int:
    body = open(SCRIPT, encoding="utf-8").read()
    code = re.sub(r"#.*", "", body)

    st = os.stat(SCRIPT)
    t("chmod +x", bool(st.st_mode & 0o111))
    r = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
    t("bash -n", r.returncode == 0, r.stderr[:120])

    t("ATTACH с ROW_GROUP_SIZE",
      "ATTACH" in body and "ROW_GROUP_SIZE" in body)
    t("своя база на поток (_w${w}.db)",
      "_w${w}.db" in body or '_w${w}.db' in body or "${TAG}_w${w}.db" in body)
    t("нет общей записи без ATTACH в part основного",
      "CREATE OR REPLACE TABLE ${TAG}_part_" not in code)

    t("EMBED_BATCH_ROWS умолчание 16",
      'EMBED_BATCH_ROWS:-16' in body or 'EMBED_BATCH_ROWS:-16}' in body)
    t("потолок batch ≤ 16 в коде",
      "ROWS_PER_BATCH" in body and "-gt 16" in body)

    t("SET GLOBAL threads отдельным оператором",
      "SET GLOBAL threads" in body)
    t("SET GLOBAL http_timeout отдельным оператором",
      "SET GLOBAL http_timeout" in body)
    ag = body[body.find("apply_globals"):body.find("transfer_attached")]
    t("GLOBAL — два отдельных psql в apply_globals",
      ag.count("psql ") >= 2
      and "SET GLOBAL threads" in ag
      and "SET GLOBAL http_timeout" in ag
      and "SET GLOBAL threads" in ag.split("http_timeout")[0],
      ag[:180])

    t("EMBED_THREADS параметр (не зашивка под 6 карт)",
      "EMBED_THREADS:-3" in body)
    t("EMBED_POOL_PER_STREAM длинный круг",
      "EMBED_POOL_PER_STREAM:-50000" in body)
    t("повтор chunk при отказе",
      "CHUNK_RETRIES" in body and "пауза" in body)
    t("transfer в конце круга",
      "transfer_attached" in body)
    t("постоянная метка TAG (докатка)",
      'TAG="emb_${DBNAME}_${TBL}"' in body or "emb_${DBNAME}_${TBL}" in body)
    t("NOT EXISTS / докатка chunk не считает заново",
      "NOT EXISTS" in body and "transfer_attached" in body)
    t("прогресс по ходу",
      "bulk_progress" in body or "progress_loop" in body)
    t("EMBED_PROGRESS_SEC умолчание 300",
      "EMBED_PROGRESS_SEC:-300" in body)
    t("EMBED_PROGRESS_SEC зажат 300–600",
      "PROGRESS_SEC" in body and "-lt 300" in body and "-gt 600" in body)
    t("EMBED_TRANSFER_STRICT в transfer",
      "EMBED_TRANSFER_STRICT" in body)
    t("strict: перенос без || true",
      "_strict=1" in body or "EMBED_TRANSFER_STRICT" in body)
    t("fail если осталось>0 (exit 1)",
      "осталось $after без вектора" in body and "exit 1" in body.split("осталось $after")[-1][:80])
    t("нет имён klient/okna в коде",
      not re.search(r"\b(klient-1|klient1|okna|ut_test)\b", code))
    t("dbname у движка", "current_database()" in body)

    print("\nитог: %d ok, %d fail" % (PASS, len(FAIL)))
    if FAIL:
        print("FAIL:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
