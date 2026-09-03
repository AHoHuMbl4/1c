#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-замок: SKIP-канон resolver_build.sql (Скорость-II этап 3).

По TAKT_SPEED2_PLAN: в skip-ветке отсутствуют UNPIVOT/MERGE/p_seen/p_val; CREATE,
оба service-DELETE и отчёт resolver_* исполняются в обеих ветках. Пустой USING у
NOT MATCHED BY SOURCE DELETE стирает индекс (C1-ошибка плана v1) — этот случай
замок ловит структурной проверкой веток.

Запуск: python3 test_resolver_skip_canon.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.join(ROOT, "resolver_build.sql")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


txt = open(SQL, encoding="utf-8").read()
lines = txt.splitlines()


def strip_sql_comments(s: str) -> str:
    """Убрать --комментарии; строки psql-метакоманд оставить."""
    out = []
    for ln in s.splitlines():
        if ln.lstrip().startswith("\\"):
            out.append(ln)
            continue
        # не трогаем строковые литерали грубо: для замка достаточно отрезать хвост --
        if "--" in ln:
            # простая эвристика: -- вне одинарных кавычек
            buf, i, in_q = [], 0, False
            while i < len(ln):
                c = ln[i]
                if c == "'" and not in_q:
                    in_q = True
                    buf.append(c)
                    i += 1
                    continue
                if c == "'" and in_q:
                    if i + 1 < len(ln) and ln[i + 1] == "'":
                        buf.append("''")
                        i += 2
                        continue
                    in_q = False
                    buf.append(c)
                    i += 1
                    continue
                if not in_q and c == "-" and i + 1 < len(ln) and ln[i + 1] == "-":
                    break
                buf.append(c)
                i += 1
            ln = "".join(buf)
        out.append(ln)
    return "\n".join(out)


code = strip_sql_comments(txt)


def find_if_blocks(src: str, cond_re: str):
    """Найти пары then/else для \\if <cond>. Возвращает list of (then, else)."""
    # Разбить на токены строк-метакоманд + куски SQL между ними.
    parts = re.split(r"(?m)^(\\if\b.*|\\else\b.*|\\elif\b.*|\\endif\b.*)$", src)
    # parts[0]=preamble, then alternating (meta, body)...
    stack = []  # each: {cond, then, else, phase}
    done = []
    i = 0
    # Rebuild sequentially
    tokens = []
    # Re-scan line by line for clarity
    cur_then = []
    cur_else = []
    phase = None  # None | 'then' | 'else'
    cond = None
    depth = 0
    want = re.compile(cond_re)

    for ln in src.splitlines(keepends=True):
        m_if = re.match(r"^\\if\s+(.+?)\s*$", ln)
        m_else = re.match(r"^\\else\b", ln)
        m_endif = re.match(r"^\\endif\b", ln)
        if m_if:
            if depth == 0 and want.search(m_if.group(1)):
                # start tracking top-level matching if
                depth = 1
                cond = m_if.group(1).strip()
                phase = "then"
                cur_then, cur_else = [], []
                continue
            if depth > 0:
                depth += 1
                if phase == "then":
                    cur_then.append(ln)
                elif phase == "else":
                    cur_else.append(ln)
                continue
            continue
        if m_else and depth == 1:
            phase = "else"
            continue
        if m_else and depth > 1:
            if phase == "then":
                cur_then.append(ln)
            else:
                cur_else.append(ln)
            continue
        if m_endif:
            if depth == 1:
                done.append((cond, "".join(cur_then), "".join(cur_else)))
                depth = 0
                phase = None
                cond = None
                continue
            if depth > 1:
                depth -= 1
                if phase == "then":
                    cur_then.append(ln)
                else:
                    cur_else.append(ln)
                continue
            continue
        if depth > 0:
            if phase == "then":
                cur_then.append(ln)
            elif phase == "else":
                cur_else.append(ln)
    return done


# --- дефолт без переменной = полный прогон ---
t("default: \\if :{?resolver_skip_unpivot} есть",
  r"\if :{?resolver_skip_unpivot}" in txt)
t("default: \\set resolver_skip_unpivot 0 в else",
  bool(re.search(
      r"\\if\s+:\{\?resolver_skip_unpivot\}\s*\n\\else\s*\n\\set\s+resolver_skip_unpivot\s+0\s*\n\\endif",
      txt)))

# --- главный if skip ---
main_ifs = find_if_blocks(code, r"^:resolver_skip_unpivot$")
t("главный \\if :resolver_skip_unpivot найден",
  len(main_ifs) >= 1, "n=%d" % len(main_ifs))

skip_arm = else_arm = ""
if main_ifs:
    # Первый = ветка UNPIVOT/MERGE (второй может быть метка отчёта без else)
    # Берём блок, у которого есть else с MERGE или res_seen
    chosen = None
    for cond, then_b, else_b in main_ifs:
        if "MERGE INTO resolver_index" in else_b or "res_seen" in else_b:
            chosen = (then_b, else_b)
            break
    if chosen is None and main_ifs:
        chosen = (main_ifs[0][1], main_ifs[0][2])
    skip_arm, else_arm = chosen

t("skip-ветка: нет MERGE INTO resolver_index",
  "MERGE INTO resolver_index" not in skip_arm)
t("skip-ветка: нет CREATE res_seen",
  "CREATE OR REPLACE TABLE res_seen" not in skip_arm
  and "CREATE TABLE res_seen" not in skip_arm)
t("skip-ветка: нет PREPARE p_seen",
  "PREPARE p_seen" not in skip_arm)
t("skip-ветка: нет PREPARE p_val",
  "PREPARE p_val" not in skip_arm)
t("skip-ветка: нет UNPIVOT",
  "UNPIVOT" not in skip_arm)
t("skip-ветка: нет res_emb_xfer",
  "res_emb_xfer" not in skip_arm)
t("full-ветка: есть MERGE INTO resolver_index",
  "MERGE INTO resolver_index" in else_arm)
t("full-ветка: есть res_seen и p_val",
  "res_seen" in else_arm and "PREPARE p_val" in else_arm)
t("full-ветка: есть UNPIVOT",
  "UNPIVOT" in else_arm)

# NOT MATCHED BY SOURCE только в full-ветке (не в skip) — регресс C1
t("C1: NOT MATCHED BY SOURCE только в full-ветке",
  "NOT MATCHED BY SOURCE" in else_arm
  and "NOT MATCHED BY SOURCE" not in skip_arm)
t("C1: USING res_clip рядом с MERGE (не пустой USING)",
  "USING res_clip" in else_arm
  and "MERGE INTO resolver_index" in else_arm)

# --- CREATE + права и оба service-DELETE вне главного if ---
# Позиции: до первого \\if :resolver_skip_unpivot (после дефолта)
m_main = re.search(r"(?m)^\\if\s+:resolver_skip_unpivot\s*$", txt)
t("позиция главного \\if найдена", m_main is not None)
before = txt[: m_main.start()] if m_main else ""
# после последнего \endif главного блока — грубо: всё после первого endif,
# который закрывает главный if. Надёжнее: код ДО if + код ПОСЛЕ полного
# разбора.
after_main = ""
if main_ifs and m_main:
    # найти \\endif, закрывающий главный if: сканируем от m_main
    depth = 0
    end_pos = None
    for m in re.finditer(r"(?m)^(\\if\b|\\endif\b)", txt[m_main.start():]):
        tok = m.group(1)
        if tok.startswith(r"\if"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                end_pos = m_main.start() + m.end()
                break
    if end_pos is not None:
        after_main = txt[end_pos:]

outside = before + "\n" + after_main

t("CREATE TABLE IF NOT EXISTS resolver_index вне skip-if",
  "CREATE TABLE IF NOT EXISTS resolver_index" in before)
t("GRANT serene_resolver вне skip-if",
  "GRANT SELECT ON resolver_index TO serene_resolver" in before)
t("REVOKE serene_ro вне skip-if",
  "REVOKE SELECT ON resolver_index FROM serene_ro" in before)

# оба service-DELETE: метаданные (tmp3_ent) и классы (search_entity_class)
meta_del = re.search(
    r"DELETE FROM resolver_index\s+r\s+WHERE\s+\(SELECT count\(\*\) FROM tmp3_ent\)",
    outside, re.I | re.S)
class_del = re.search(
    r"DELETE FROM resolver_index\s+r\s+WHERE\s+EXISTS\s*\(\s*SELECT 1 FROM search_entity_class",
    outside, re.I | re.S)
t("service-DELETE по tmp3_ent вне skip-if", meta_del is not None)
t("service-DELETE по cls=service вне skip-if", class_del is not None)
t("оба DELETE не внутри skip-ветки",
  meta_del is not None and class_del is not None
  and skip_arm.count("DELETE FROM resolver_index") == 0)

# classify-flip назван (красная R4, п. 13): сколько строк снимет class-DELETE —
# считается ДО удаления и уходит в отчёт; усыхание резолвера с причиной.
purged_cnt = re.search(
    r"CREATE OR REPLACE TABLE res_service_purged\s+AS\s+SELECT count\(\*\) AS n",
    outside, re.I | re.S)
t("снятое service: счёт до DELETE (res_service_purged)",
  purged_cnt is not None
  and class_del is not None
  and purged_cnt.start() < class_del.start())
t("отчёт: resolver_service_purged вне skip-if",
  "'resolver_service_purged'" in outside)

# --- отчёт в обеих ветках / всегда + метка skip ---
t("отчёт: INSERT resolver_values есть",
  "'resolver_values'" in txt or '"resolver_values"' in txt)
t("отчёт: счёт из resolver_index",
  bool(re.search(r"'resolver_values'.*FROM resolver_index", txt, re.S)))
t("отчёт: resolver_unpivot + skipped",
  "'resolver_unpivot'" in txt and "skipped" in txt)

# метка skipped только при skip
skip_report_ifs = [
    (th, el) for cond, th, el in main_ifs
    if "resolver_unpivot" in th or "skipped" in th
]
t("метка resolver_unpivot=skipped в skip-\\if",
  any("resolver_unpivot" in th and "skipped" in th for th, _ in skip_report_ifs)
  or any(
      "resolver_unpivot" in th and "skipped" in th
      for _, th, _ in find_if_blocks(code, r":resolver_skip_unpivot")
  ))

# в skip-if с меткой нет MERGE
t("метка skip без MERGE в том же then",
  all("MERGE INTO" not in th for th, _ in skip_report_ifs)
  if skip_report_ifs else
  ("resolver_unpivot" in txt))  # fallback: наличие есть

# нет второго источника решения (порогов/дат внутри SQL для skip)
t("нет своих порогов skip (только переменная)",
  not re.search(r"resolver_skip_unpivot\s*[<>=]", code)
  and "SKIP_BUILD" not in code)

print()
print("PASS %d FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
