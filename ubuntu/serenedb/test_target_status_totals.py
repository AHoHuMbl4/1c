#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок: сводные числа в docs/TARGET_STATUS.md = пересчёт таблицы.

Парсит стадию каждого из 21 пункта в «Одной таблицей» и сверяет строку
«Итог» (счётчики и поимённые списки). Без сети, ssh, сервисов, psql.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(ROOT, "..", "..", "docs", "TARGET_STATUS.md")

PASS = 0
FAIL: list[str] = []

STAGES = ("🟢", "🟡", "🔴", "⚪")
ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*[^|]+\|\s*([🟢🟡🔴⚪])\s*\|"
)
# **Итог …: 🟢 N · 🟡 N · 🔴 N [= 21].**  (⚪ опционально; точка перед **)
ITOG_RE = re.compile(
    r"^\*\*Итог[^*]*:\s*"
    r"🟢\s*(\d+)\s*·\s*"
    r"🟡\s*(\d+)\s*·\s*"
    r"🔴\s*(\d+)"
    r"(?:\s*·\s*⚪\s*(\d+))?"
    r"(?:\s*=\s*(\d+))?\s*\.?\s*\*\*\s*$"
)
# (🟢 8,19 · 🟡 1,2,… · 🔴 3,10,11,15)
LIST_RE = re.compile(
    r"^\(\s*"
    r"🟢\s*([\d,\s]+)\s*·\s*"
    r"🟡\s*([\d,\s]+)\s*·\s*"
    r"🔴\s*([\d,\s]+)"
    r"(?:\s*·\s*⚪\s*([\d,\s]+))?"
    r"\s*\)\s*$"
)
# Любая другая «текущая» сводка стадий вне исторических *Правка* / цитат.
# Ловим только жирные/заголовочные строки с тремя счётчиками подряд.
OTHER_SUMMARY_RE = re.compile(
    r"(?m)^(?!\*)(?!.*Было)(?!.*было «)(?!.*сначала записала)"
    r".*🟢\s*(\d+)\s*·\s*🟡\s*(\d+)\s*·\s*🔴\s*(\d+)"
)


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def _parse_nums(blob: str) -> list[int]:
    blob = blob.strip()
    if not blob:
        return []
    return [int(x) for x in re.findall(r"\d+", blob)]


def parse_table(text: str) -> dict[int, str]:
    """Строки таблицы контракта: # → эмодзи стадии (колонка 3)."""
    rows: dict[int, str] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("## Одной таблицей"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.startswith("**Итог"):
            break
        m = ROW_RE.match(line)
        if not m:
            continue
        n = int(m.group(1))
        stage = m.group(2)
        if n in rows:
            raise ValueError("дубль пункта %d в таблице" % n)
        rows[n] = stage
    return rows


def counts_from(rows: dict[int, str]) -> dict[str, int]:
    c = Counter(rows.values())
    return {s: int(c.get(s, 0)) for s in STAGES}


def lists_from(rows: dict[int, str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {s: [] for s in STAGES}
    for n in sorted(rows):
        out[rows[n]].append(n)
    return out


def main() -> int:
    t("файл существует", os.path.isfile(DOC), DOC)
    text = open(DOC, encoding="utf-8").read()

    try:
        rows = parse_table(text)
    except ValueError as e:
        t("таблица без дублей", False, str(e))
        rows = {}

    t("в таблице ровно 21 пункт", len(rows) == 21, "got %d" % len(rows))
    t(
        "пункты 1..21 без дыр",
        set(rows.keys()) == set(range(1, 22)),
        "keys=%s" % sorted(rows.keys()),
    )

    expect_counts = counts_from(rows) if rows else {s: 0 for s in STAGES}
    expect_lists = lists_from(rows) if rows else {s: [] for s in STAGES}
    total = sum(expect_counts.values())

    itog_line = None
    list_line = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if ITOG_RE.match(line):
            itog_line = line
            # список — ближайшая непустая строка после Итога
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].strip() == "":
                    continue
                list_line = lines[j]
                break
            break

    t("есть строка **Итог", itog_line is not None, "не найдена")
    if itog_line:
        m = ITOG_RE.match(itog_line)
        assert m is not None
        got = {
            "🟢": int(m.group(1)),
            "🟡": int(m.group(2)),
            "🔴": int(m.group(3)),
            "⚪": int(m.group(4) or 0),
        }
        sum_claimed = m.group(5)
        t(
            "Итог 🟢 = таблица",
            got["🟢"] == expect_counts["🟢"],
            "итог=%d таблица=%d (%s)"
            % (got["🟢"], expect_counts["🟢"], expect_lists["🟢"]),
        )
        t(
            "Итог 🟡 = таблица",
            got["🟡"] == expect_counts["🟡"],
            "итог=%d таблица=%d" % (got["🟡"], expect_counts["🟡"]),
        )
        t(
            "Итог 🔴 = таблица",
            got["🔴"] == expect_counts["🔴"],
            "итог=%d таблица=%d" % (got["🔴"], expect_counts["🔴"]),
        )
        t(
            "Итог ⚪ = таблица",
            got["⚪"] == expect_counts["⚪"],
            "итог=%d таблица=%d" % (got["⚪"], expect_counts["⚪"]),
        )
        if sum_claimed is not None:
            t(
                "Итог сумма = 21",
                int(sum_claimed) == 21 and total == 21,
                "claimed=%s table_total=%d" % (sum_claimed, total),
            )
        else:
            t("Итог сумма указана (= N)", False, itog_line)

    t("есть строка списков после Итога", list_line is not None and LIST_RE.match(list_line or "") is not None, list_line)
    if list_line and LIST_RE.match(list_line):
        lm = LIST_RE.match(list_line)
        assert lm is not None
        got_lists = {
            "🟢": _parse_nums(lm.group(1)),
            "🟡": _parse_nums(lm.group(2)),
            "🔴": _parse_nums(lm.group(3)),
            "⚪": _parse_nums(lm.group(4) or ""),
        }
        for stage in STAGES:
            t(
                "список %s = таблица" % stage,
                got_lists[stage] == expect_lists[stage],
                "итог=%s таблица=%s" % (got_lists[stage], expect_lists[stage]),
            )
            t(
                "длина списка %s = счётчик таблицы" % stage,
                len(got_lists[stage]) == expect_counts[stage],
                "len=%d count=%d" % (len(got_lists[stage]), expect_counts[stage]),
            )

    # Покрытие: каждый номер 1..21 ровно в одном списке
    if list_line and LIST_RE.match(list_line):
        flat: list[int] = []
        for stage in STAGES:
            flat.extend(expect_lists[stage])
        t(
            "списки покрывают 1..21 без пересечений",
            sorted(flat) == list(range(1, 22)),
            "flat=%s" % flat,
        )

    # Других живых сводок «🟢 N · 🟡 N · 🔴 N» кроме Итога быть не должно
    # (исторические «было» в *Правка* / цитатах — пропускаем по OTHER_SUMMARY_RE).
    other = []
    for line in lines:
        if line.startswith("**Итог"):
            continue
        if line.lstrip().startswith("*"):
            continue  # курсивные исторические правки
        if "«" in line and "»" in line and ("было" in line.lower() or "Было" in line):
            continue
        if OTHER_SUMMARY_RE.search(line) and not ITOG_RE.match(line):
            # внутри ячеек таблицы тоже бывают числа — только строки целиком-сводки
            if re.search(r"🟢\s*\d+\s*·\s*🟡\s*\d+\s*·\s*🔴\s*\d+", line):
                # ячейки таблицы начинаются с |
                if line.lstrip().startswith("|"):
                    continue
                other.append(line[:120])
    t("нет второй сводки стадий вне Итога", other == [], str(other)[:200])

    print("---")
    print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
    if FAIL:
        print("failed:", ", ".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
