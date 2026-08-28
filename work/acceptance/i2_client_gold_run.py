#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И2: независимый прогон приёмочного набора client-gold через /ask.

Только измеряет: POST /ask каждому вопросу набора, фиксирует kind/text/числа,
сверяет с эталоном 1С где он есть (допуск 0.5 %, числа с типографскими
разделителями). Базу не трогает, ничего не правит. Разбор классов провалов —
по артефактам (answers.jsonl / summary.tsv) после прогона.

Окружение:
  ASK_URL    — URL эндпоинта /ask (обяз.)
  ASK_TOKEN  — Bearer-токен (обяз.)
  I2_IN      — путь к набору (по умолч. ubuntu/serenedb/client-gold-okna.tsv)
  I2_OUT     — каталог артефактов (по умолч. work/acceptance/runs/i2-validate/<tag>)
  I2_TAG     — метка прогона (по умолч. runN по счёту каталогов)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

SP = " \u00a0\u2007\u2009\u202f\u200b"
NUM_RE = re.compile(r"\d{1,3}(?:[%s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?" % SP)
TOL = 0.005


def parse_num(s: str) -> float:
    return float(re.sub("[%s]" % SP, "", s).replace(",", "."))


def extract_nums(text: str):
    out = []
    for m in NUM_RE.finditer(text or ""):
        try:
            out.append(parse_num(m.group(0)))
        except ValueError:
            pass
    return out


def ask(url: str, token: str, question: str, timeout: int = 120):
    body = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"},
    )
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:  # noqa: BLE001 — прибор фиксирует любую ошибку
            last = str(e)
            time.sleep(3)
    return None, last


def main() -> int:
    url = os.environ.get("ASK_URL", "").rstrip("/")
    token = os.environ.get("ASK_TOKEN", "")
    if not url or not token:
        print("нужны ASK_URL и ASK_TOKEN", file=sys.stderr)
        return 2
    root = "/srv/1c"
    src = os.environ.get("I2_IN") or root + "/ubuntu/serenedb/client-gold-okna.tsv"
    outdir = os.environ.get("I2_OUT")
    tag = os.environ.get("I2_TAG")
    if not outdir:
        base = root + "/work/acceptance/runs/i2-validate"
        n = 1
        if os.path.isdir(base):
            n = len([d for d in os.listdir(base) if d.startswith("run")]) + 1
        tag = tag or ("run%d" % n)
        outdir = base + "/" + tag
    os.makedirs(outdir, exist_ok=True)

    rows = []
    with open(src, encoding="utf-8") as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if header is None:
                header = parts
                continue
            d = dict(zip(header, parts + [""] * (len(header) - len(parts))))
            rows.append(d)
    if not rows:
        print("пустой набор %s" % src, file=sys.stderr)
        return 2

    jl = open(outdir + "/answers.jsonl", "w", encoding="utf-8")
    tsv = open(outdir + "/summary.tsv", "w", encoding="utf-8")
    tsv.write("question\tkind\tstatus\tetalon\tgot\tnum_in_text\tlatency_s\n")
    stat = {"answer": 0, "clarify": 0, "figures": 0, "error": 0, "other": 0}
    st_stat = {"match": 0, "mismatch": 0, "pending": 0}
    for i, row in enumerate(rows, 1):
        q = row.get("question", "").strip()
        etalon = (row.get("etalon") or "").strip()
        t0 = time.time()
        ans, err = ask(url, token, q)
        lat = round(time.time() - t0, 1)
        if ans is None:
            kind, text = "error", ""
            got, nums = "", []
        else:
            kind = ans.get("kind") or "?"
            text = ans.get("text") or ""
            nums = extract_nums(text)
            got = "; ".join(("%.2f" % n).rstrip("0").rstrip(".") for n in nums[:6])
        jl.write(json.dumps({"q": q, "kind": kind, "text": text,
                             "nums": nums, "etalon": etalon,
                             "error": err, "latency_s": lat},
                            ensure_ascii=False) + "\n")
        if ans is None:
            status = "error"
        elif etalon:
            try:
                ev = float(etalon.replace(" ", "").replace(",", "."))
            except ValueError:
                status, ev = "pending", None
            if ev is not None:
                ok = any(abs(n - ev) <= max(abs(ev) * TOL, 0.01) for n in nums)
                status = "match" if ok else "mismatch"
        else:
            status = "pending"
        stat[kind if kind in stat else ("other" if kind != "error" else "error")] += 1
        if status in st_stat:
            st_stat[status] += 1
        tsv.write("%s\t%s\t%s\t%s\t%s\t%d\t%s\n" % (
            q, kind, status, etalon or "—", got or "—", len(nums), lat))
        jl.flush()
        print("[%d/%d] %-55s %-8s %-9s %.1fs" % (i, len(rows), q[:55], kind, status, lat),
              flush=True)
    jl.close()
    tsv.close()
    print("\n=== сводка %s ===" % outdir)
    print("kind:", json.dumps(stat, ensure_ascii=False))
    print("status:", json.dumps(st_stat, ensure_ascii=False))
    print("итого вопросов:", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
