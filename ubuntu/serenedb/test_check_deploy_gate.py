#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок check_deploy_gate.py: синтетические отчёты, без сети и /ask."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "check_deploy_gate.py")
BASELINE_DOC = os.path.join(ROOT, "..", "..", "docs", "DEPLOY_GATE.md")

PASS = 0
FAIL: list[str] = []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# Базлайн-вопросы FAIL из docs/DEPLOY_GATE.md (должны совпасть со снимком).
BASE_FAILS = [
    "дай топ-3 товара за вчера",
    "сколько позиций совсем не продаётся в этом месяце?",
    "эта неделя лучше прошлой или хуже?",
    "в этом месяце продали больше, чем в прошлом?",
    "сколько клиентов реально покупают?",
]

# 20 OK-вопросов — любые стабильные строки, не пересекающиеся с FAIL.
BASE_OKS = [
    "сколько продали вчера?",
    "сколько продали позавчера?",
    "сколько уже продали сегодня?",
    "сколько продали на этой неделе?",
    "сколько наторговали на прошлой неделе?",
    "сколько продали в этом месяце?",
    "сколько продали в прошлом месяце?",
    "что лучше всего продавалось на этой неделе?",
    "какой клиент больше всех купил в этом месяце?",
    "кто из клиентов молодец за прошлую неделю, три лучших",
    "дай топ-3 клиента по деньгам за этот месяц",
    "сколько наторговали в прошедшее воскресенье?",
    "почему в воскресенье продаж ноль, это сбой?",
    "сколько у нас всего клиентов?",
    "сколько позиций у нас в прайсе?",
    "какого товара больше всего продали за всё время?",
    "кому мы больше всего продали за всё время?",
    "сколько петель осталось на складе?",
    "как у нас дела?",
    "сколько документов реализации за декабрь 2025?",
]


def _jsonl(rows: list[tuple[str, str]]) -> str:
    lines = []
    for q, verdict in rows:
        lines.append(json.dumps({"q": q, "verdict": verdict, "mode": "digits"}, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _markdown(rows: list[tuple[str, str]]) -> str:
    out = ["== live: верных %d/%d, средняя 1.00 с\n" % (
        sum(1 for _, v in rows if v == "OK"), len(rows))]
    out.append("| question | mode | verdict | fact |")
    out.append("|---|---|---|---|")
    for q, verdict in rows:
        out.append("| %s | digits | %s | ok |" % (q, verdict))
    return "\n".join(out) + "\n"


def _baseline_rows(extra_fail: str | None = None, drop_ok: int = 0) -> list[tuple[str, str]]:
    oks = list(BASE_OKS)
    if drop_ok:
        oks = oks[:-drop_ok]
    rows = [(q, "OK") for q in oks] + [(q, "FAIL") for q in BASE_FAILS]
    if extra_fail:
        rows.append((extra_fail, "FAIL"))
    return rows


def run_gate(report_body: str, suffix: str = ".jsonl") -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "report" + suffix)
        open(path, "w", encoding="utf-8").write(report_body)
        return subprocess.run(
            [sys.executable, SCRIPT, path, "--baseline-doc", BASELINE_DOC],
            capture_output=True,
            text=True,
            timeout=15,
        )


def main() -> int:
    t("скрипт существует", os.path.isfile(SCRIPT))
    t("базлайн-док существует", os.path.isfile(BASELINE_DOC))

    # снимок JSON в доке читается
    import check_deploy_gate as G  # noqa: E402

    bl = G.load_baseline(BASELINE_DOC)
    t("базлайн pass=20", bl["pass"] == 20, bl["pass"])
    t("базлайн total=25", bl["total"] == 25, bl["total"])
    t("базлайн 5 FAIL", len(bl["fail_qs"]) == 5, len(bl["fail_qs"]))
    t("базлайн FAIL совпадают", set(BASE_FAILS) == bl["fail_qs"],
      sorted(bl["fail_qs"] ^ set(BASE_FAILS)))

    # 1) pass: ровно базлайн
    rows = _baseline_rows()
    t("синтетика: 20 OK + 5 FAIL = 25", len(rows) == 25, len(rows))
    r = run_gate(_jsonl(rows))
    t("pass jsonl → rc 0", r.returncode == 0, "rc=%s err=%s" % (r.returncode, (r.stderr or "")[:160]))
    t("pass jsonl → PASS в stdout", "PASS" in (r.stdout or ""), r.stdout[:120])

    r = run_gate(_markdown(rows), suffix=".txt")
    t("pass markdown → rc 0", r.returncode == 0, "rc=%s err=%s" % (r.returncode, (r.stderr or "")[:160]))

    # улучшение: один FAIL стал OK
    better = [(q, "OK" if q == BASE_FAILS[0] else v) for q, v in rows]
    r = run_gate(_jsonl(better))
    t("улучшение FAIL→OK → rc 0", r.returncode == 0, "rc=%s" % r.returncode)

    # 2) регресс: новый FAIL
    bad = _baseline_rows(extra_fail="сколько продали вчера? РЕГРЕСС-маркер")
    # заменим один OK на другой вопрос-FAIL, сохранив размер ≥25
    bad = [(q, v) for q, v in rows if q != BASE_OKS[0]]
    bad.append((BASE_OKS[0], "FAIL"))  # бывший OK стал FAIL — новый относительно базлайна
    r = run_gate(_jsonl(bad))
    t("регресс новый FAIL → rc 1", r.returncode == 1, "rc=%s out=%s" % (r.returncode, (r.stderr or "")[:160]))
    t("регресс → текст про новый FAIL", "новый FAIL" in (r.stderr or ""), (r.stderr or "")[:200])

    # pass < базлайна без «нового» имени: уберём один OK из отчёта и один baseline FAIL
    # (короче и pass ниже) — ловится коротким набором / pass
    short_pass = [(q, "OK") for q in BASE_OKS[:15]] + [(q, "FAIL") for q in BASE_FAILS]
    r = run_gate(_jsonl(short_pass))
    t("pass 15 при total 20 → rc 1", r.returncode == 1, "rc=%s" % r.returncode)

    # 3) короткий набор (probe-размер)
    probe = [(q, "OK") for q in BASE_OKS[:8]]
    r = run_gate(_jsonl(probe))
    t("короткий набор 8 → rc 1", r.returncode == 1, "rc=%s" % r.returncode)
    t("короткий → сообщение", "короткий набор" in (r.stderr or ""), (r.stderr or "")[:200])

    # AB_MARK_DIR: файл по умолчанию
    with tempfile.TemporaryDirectory() as td:
        claude = os.path.join(td, ".claude")
        os.makedirs(claude)
        open(os.path.join(claude, "scorer-okna-last.jsonl"), "w", encoding="utf-8").write(
            _jsonl(rows)
        )
        env = os.environ.copy()
        env["AB_MARK_DIR"] = td
        r = subprocess.run(
            [sys.executable, SCRIPT, "--baseline-doc", BASELINE_DOC],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        t("AB_MARK_DIR default jsonl → rc 0", r.returncode == 0,
          "rc=%s err=%s" % (r.returncode, (r.stderr or "")[:160]))

    # evaluate() напрямую
    ok, msgs = G.evaluate(
        [{"q": q, "verdict": v, "mode": "digits", "class": ""} for q, v in rows],
        bl,
    )
    t("evaluate базлайн → ok", ok, msgs)

    print()
    if FAIL:
        print("ИТОГО: %d ok, %d FAIL" % (PASS, len(FAIL)))
        for name in FAIL:
            print("  -", name)
        return 1
    print("ИТОГО: %d/0" % PASS)
    return 0


if __name__ == "__main__":
    # импорт соседнего модуля
    sys.path.insert(0, ROOT)
    sys.exit(main())
