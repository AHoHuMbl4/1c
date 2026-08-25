#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт выката: сверка отчёта полного скорера с базлайном docs/DEPLOY_GATE.md.

Без сети, без /ask, без правки эталонов. Код выхода 0/1.

Отчёт: jsonl (строки с q/question + verdict) или текстовый вывод ab_scorer
(markdown-таблица | question | mode | verdict | … |).

Путь отчёта: аргумент, иначе AB_SCORER_REPORT, иначе
$AB_MARK_DIR/.claude/scorer-okna-last.{jsonl,txt} (и то же без .claude/).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_DEFAULT_BASELINE_DOC = os.path.join(_REPO_ROOT, "docs", "DEPLOY_GATE.md")

_MIN_TOTAL_FLOOR = 25

_REPORT_NAMES = (
    "scorer-okna-last.jsonl",
    "scorer-okna-last.txt",
    "scorer-okna-last.md",
)


def _repo_root() -> str:
    mark = os.environ.get("AB_MARK_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if mark and os.path.isdir(mark):
        return os.path.abspath(mark)
    return _REPO_ROOT


def load_baseline(path: str) -> dict:
    """Читает JSON-снимок из fenced-блока docs/DEPLOY_GATE.md."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        raise SystemExit("базлайн: в %s нет fenced ```json``` снимка" % path)
    data = json.loads(m.group(1))
    for key in ("pass", "total", "fails"):
        if key not in data:
            raise SystemExit("базлайн: нет поля %r" % key)
    fails = []
    for item in data["fails"]:
        if isinstance(item, str):
            fails.append({"q": item, "class": ""})
        else:
            q = (item.get("q") or item.get("question") or "").strip()
            if not q:
                raise SystemExit("базлайн: пустой вопрос в fails")
            fails.append({"q": q, "class": (item.get("class") or "").strip()})
    data["fails"] = fails
    data["fail_qs"] = {f["q"] for f in fails}
    data["pass"] = int(data["pass"])
    data["total"] = int(data["total"])
    return data


def _norm_verdict(v: str) -> str:
    s = (v or "").strip().upper()
    if s in ("OK", "PASS", "TRUE", "1"):
        return "OK"
    if s in ("FAIL", "FAILED", "FALSE", "0"):
        return "FAIL"
    return s


def parse_jsonl(text: str) -> list[dict]:
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit("jsonl строка %d: %s" % (i, e))
        if not isinstance(obj, dict):
            continue
        if obj.get("summary") is True or "pass" in obj and "total" in obj and "q" not in obj and "question" not in obj:
            continue
        q = (obj.get("q") or obj.get("question") or "").strip()
        if not q:
            continue
        verdict = _norm_verdict(str(obj.get("verdict") or obj.get("ok") or ""))
        if verdict not in ("OK", "FAIL"):
            if obj.get("ok") is True:
                verdict = "OK"
            elif obj.get("ok") is False:
                verdict = "FAIL"
            else:
                raise SystemExit("jsonl строка %d: нет verdict для %r" % (i, q[:60]))
        rows.append({
            "q": q,
            "mode": (obj.get("mode") or "").strip(),
            "verdict": verdict,
            "class": (obj.get("class") or obj.get("defect") or "").strip(),
        })
    return rows


_MD_ROW = re.compile(
    r"^\|\s*(.*?)\s*\|\s*(\w+)\s*\|\s*(OK|FAIL)\s*\|",
    re.IGNORECASE,
)


def parse_markdown_report(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        if re.match(r"^\|\s*-+", line) or "question" in line.lower() and "verdict" in line.lower():
            continue
        m = _MD_ROW.match(line)
        if not m:
            continue
        q = m.group(1).replace("\\|", "|").strip()
        if not q or q.lower() == "question":
            continue
        rows.append({
            "q": q,
            "mode": m.group(2).strip(),
            "verdict": _norm_verdict(m.group(3)),
            "class": "",
        })
    if rows:
        return rows
    # запас: список «Провалы» + сводка «верных X/Y»
    fails = []
    for line in text.splitlines():
        m = re.match(r"^-\s*\w+\s*\|\s*(.+?)\s*\|\s*", line)
        if m:
            fails.append(m.group(1).strip())
    m = re.search(r"верных\s+(\d+)\s*/\s*(\d+)", text)
    if m and fails:
        # без полной таблицы не восстанавливаем OK — недостаточно для гейта
        raise SystemExit(
            "отчёт: есть сводка %s/%s и список провалов, но нет построчной "
            "таблицы/jsonl — сохраните полный вывод ab_scorer" % (m.group(1), m.group(2))
        )
    return rows


def load_report(path: str) -> list[dict]:
    text = open(path, encoding="utf-8").read()
    if path.endswith(".jsonl") or (text.lstrip().startswith("{") and "\n{" in text[:2000]):
        # jsonl: первая непустая строка — объект
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        if first.lstrip().startswith("{"):
            try:
                rows = parse_jsonl(text)
                if rows:
                    return rows
            except SystemExit:
                if path.endswith(".jsonl"):
                    raise
    rows = parse_markdown_report(text)
    if not rows:
        # последняя попытка — весь файл как jsonl
        rows = parse_jsonl(text)
    if not rows:
        raise SystemExit("отчёт пуст или не разобран: %s" % path)
    return rows


def find_default_report(root: str) -> str:
    env = (os.environ.get("AB_SCORER_REPORT") or "").strip()
    if env:
        if not os.path.isfile(env):
            raise SystemExit("AB_SCORER_REPORT не файл: %s" % env)
        return env
    candidates = []
    for sub in (os.path.join(root, ".claude"), root):
        for name in _REPORT_NAMES:
            candidates.append(os.path.join(sub, name))
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise SystemExit(
        "нет отчёта: передайте путь или положите один из %s в "
        "$AB_MARK_DIR/.claude/ (AB_MARK_DIR=%s)" % (", ".join(_REPORT_NAMES), root)
    )


def evaluate(rows: list[dict], baseline: dict) -> tuple[bool, list[str]]:
    """Возвращает (ok, сообщения)."""
    msgs: list[str] = []
    total = len(rows)
    # при дубликатах вопроса берём последний вердикт
    by_q: dict[str, dict] = {}
    for r in rows:
        by_q[r["q"]] = r
    uniq = list(by_q.values())
    n = len(uniq)
    n_pass = sum(1 for r in uniq if r["verdict"] == "OK")
    fail_qs = {r["q"] for r in uniq if r["verdict"] == "FAIL"}
    base_pass = baseline["pass"]
    base_total = baseline["total"]
    base_fails = baseline["fail_qs"]
    min_total = max(_MIN_TOTAL_FLOOR, base_total)

    if n < min_total:
        msgs.append("короткий набор: %d вопросов (нужно ≥ %d)" % (n, min_total))
    if total != n:
        msgs.append("дубликаты вопросов в отчёте: строк %d, уникальных %d" % (total, n))

    if n_pass < base_pass:
        msgs.append("pass %d < базлайн %d" % (n_pass, base_pass))

    new_fails = sorted(fail_qs - base_fails)
    if new_fails:
        msgs.append("новый FAIL (%d): %s" % (
            len(new_fails),
            "; ".join(q[:60] for q in new_fails[:5]),
        ))

    if not msgs:
        msgs.append(
            "ок: %d/%d (базлайн %d/%d), новых FAIL нет; известных FAIL %d"
            % (n_pass, n, base_pass, base_total, len(fail_qs & base_fails))
        )
        return True, msgs
    return False, msgs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Гейт выката: полный скорер vs базлайн")
    p.add_argument("report", nargs="?", help="путь к jsonl или txt отчёту ab_scorer")
    p.add_argument(
        "--baseline-doc",
        default=os.environ.get("DEPLOY_GATE_DOC") or _DEFAULT_BASELINE_DOC,
        help="docs/DEPLOY_GATE.md со снимком JSON",
    )
    args = p.parse_args(argv)

    baseline = load_baseline(args.baseline_doc)
    report = args.report or find_default_report(_repo_root())
    rows = load_report(report)
    ok, msgs = evaluate(rows, baseline)
    for m in msgs:
        stream = sys.stdout if ok else sys.stderr
        stream.write(("%s\n" if ok else "🔴 %s\n") % m)
    if ok:
        sys.stdout.write("гейт выката: PASS (%s)\n" % report)
        return 0
    sys.stderr.write("гейт выката: FAIL (%s)\n" % report)
    return 1


if __name__ == "__main__":
    sys.exit(main())
