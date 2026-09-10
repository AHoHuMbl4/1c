#!/usr/bin/env python3
"""Оффлайн L6: мост маркеров строк search_changed_rows → корпусные row_key (полная B, этап 2).

Модель повторяет формулы макросов corpus_init.sql (bridge_norm / bridge_row_matches):
построчный (m>=n_seg) срезом до declared-длины + потомки «#…»; объектный (m<n_seg:
HTTP-голый Ref_Key, РКО без ТЧ) сегментным префиксом; fold; пустой маркер = miss
(вызывающий даёт mode=full). Статика: макрос определён в corpus_init и В ЕДИНСТВЕННОМ
месте; потребители зовут его вызовом (grep ловит копию формулы list_slice).
corpus_build — вызова bridge_row_matches( нет и копии формулы нет; corpus_merge
(rehash-гейт) — вызов макроса есть, list_slice-копии формулы нет.

Запуск: python3 test_corpus_bridge_lock.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


def bridge_norm(marker, n_seg):
    segs = (marker or "").split("|")
    return "|".join(segs[:n_seg])


def bridge_row_matches(row_key, marker, n_seg):
    if not marker or "".join(s for s in marker.split("|") if s) == "":
        return False
    segs = marker.split("|")
    # 1) точный мир (включая '|' внутри значений) — до разбиений (красная b2r3)
    if row_key == marker or row_key.startswith(marker + "#"):
        return True
    # 2) enriched-хвост: числовой LineNumber в конце — срез до declared
    if len(segs) == n_seg + 1 and segs[n_seg].isdigit():
        k = bridge_norm(marker, n_seg)
        return row_key == k or row_key.startswith(k + "#")
    # 3) объектный маркер: сегментный префикс
    if len(segs) < n_seg:
        return (row_key == marker
                or row_key.startswith(marker + "|")
                or row_key.startswith(marker + "#"))
    return False


# --- построчный документ (declared [Ref_Key,LineNumber], маркер той же длины) ---
t("построчный: точное совпадение", bridge_row_matches("ref|4", "ref|4", 2))
t("построчный: соседняя строка не матчится",
  not bridge_row_matches("ref|5", "ref|4", 2))
t("построчный: дубль #N — потомок", bridge_row_matches("ref|4#2", "ref|4", 2))
t("построчный: коллизия #sha — потомок",
  bridge_row_matches("ref|4#0f1e2d", "ref|4", 2))
t("построчный: чужой префикс-число не матчится",
  not bridge_row_matches("ref|40", "ref|4", 2))

# --- шапка: маркер с пустым LineNumber ---
t("шапка: маркер 'ref|' матчит только шапку",
  bridge_row_matches("ref|", "ref|", 2)
  and not bridge_row_matches("ref|4", "ref|", 2))

# --- fold-каталог (declared [Ref_Key]) ---
t("fold: точное совпадение", bridge_row_matches("ref", "ref", 1))
t("fold: коллизия fold — потомок", bridge_row_matches("ref#0f1e", "ref", 1))
t("fold: строка ТЧ чужого документа не матчится",
  not bridge_row_matches("refx|4", "ref", 1))

# --- объектный маркер (m<n_seg): HTTP-голый Ref_Key / РКО без ТЧ ---
t("объектный: строка ТЧ по префиксу", bridge_row_matches("ref|7", "ref", 2))
t("объектный: fold-шапка равна маркеру", bridge_row_matches("ref", "ref", 2))
t("объектный: потомок шапки #sha", bridge_row_matches("ref#0f1e", "ref", 2))
t("объектный: ложный СТРОКОВЫЙ префикс отсечён разделителем",
  not bridge_row_matches("abc|1", "ab", 2))

# --- регистр-обёртка (маркер enriched длиннее declared) ---
t("регистр: срез до declared ('rec|type|4' → 'rec|type')",
  bridge_row_matches("rec|type", "rec|type|4", 2))
t("регистр: потомок #sha среза", bridge_row_matches("rec|type#7", "rec|type|4", 2))
t("регистр: ключ другого регистратора не матчится",
  not bridge_row_matches("rec2|type", "rec|type|4", 2))

# --- '|'-в-значениях (красная b2r3) ---
t("pipe: точный путь — маркер==row_key при '|' в значении (stale закрыт)",
  bridge_row_matches("Товар|А|4", "Товар|А|4", 2))
t("pipe: потомок '#N' точного мира",
  bridge_row_matches("Товар|А|4#2", "Товар|А|4", 2))
t("pipe: fold 'hello|world' НЕ матчит чужой 'hello' (FP закрыт)",
  not bridge_row_matches("hello", "hello|world", 1)
  and bridge_row_matches("hello|world", "hello|world", 1))
t("pipe: enriched-хвост только числовой — строковый хвост false",
  not bridge_row_matches("hello", "hello|world", 1))

# --- miss моста: пустой маркер ---
t("miss: пустой маркер → false (режим full решает вызывающий)",
  not bridge_row_matches("ref|4", "", 2))
t("miss: маркер из пустых сегментов '|' → false",
  not bridge_row_matches("ref|4", "|", 2))

# --- статика: макрос в corpus_init, единственный источник формулы ---
init = open(os.path.join(ROOT, "corpus_init.sql"), encoding="utf-8").read()
t("init: макрос bridge_norm определён",
  "CREATE OR REPLACE MACRO bridge_norm" in init)
t("init: макрос bridge_row_matches определён",
  "CREATE OR REPLACE MACRO bridge_row_matches" in init)
t("init: нормализация срезом list_slice(string_split…)",
  "list_slice(string_split(coalesce(marker, ''), '|'), 1, n_seg)" in init)
t("init: пустой маркер — miss (fail-closed, len-форма b2r1)",
  init.count("len(list_filter(string_split(coalesce(marker, ''), '|'),") >= 1)
build_body = open(os.path.join(ROOT, "corpus_build.sql"), encoding="utf-8").read()
t("corpus_build.sql: вызова bridge_row_matches нет и копии формулы нет",
  "bridge_row_matches(" not in build_body
  and "list_slice(string_split(" not in build_body)
merge_body = open(os.path.join(ROOT, "corpus_merge.sql"), encoding="utf-8").read()
t("corpus_merge.sql: вызов bridge_row_matches( есть, list_slice-копии нет",
  "bridge_row_matches(" in merge_body
  and "list_slice(string_split(" not in merge_body)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
