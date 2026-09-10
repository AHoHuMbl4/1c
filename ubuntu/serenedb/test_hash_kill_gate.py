#!/usr/bin/env python3
"""Оффлайн: гейт необъяснённого hash_kill (FIX_HASHKILL_GATE_PLAN v3).

Массовая смена текста вне свежей дельты 1С → STOP ДО записи.
Объяснение — только свежие маркеры search_changed_rows через bridge_row_matches
и окно epoch(ts) > corpus_built_ts; emb_xfer/full не объясняют.

Запуск: python3 test_hash_kill_gate.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(ROOT, "corpus_merge.sql")
BUILD = os.path.join(ROOT, "build.sh")
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:220] if detail else "")


def bridge_row_matches(row_key, marker, n_seg):
    """Модель corpus_init.sql bridge_row_matches (упрощённо для замка)."""
    if not marker or all(s == "" for s in marker.split("|")):
        return False
    if row_key == marker or row_key.startswith(marker + "#"):
        return True
    parts = marker.split("|")
    if len(parts) == n_seg + 1 and parts[n_seg].isdigit():
        norm = "|".join(parts[:n_seg])
        return row_key == norm or row_key.startswith(norm + "#")
    if len(parts) < n_seg:
        return (row_key == marker
                or row_key.startswith(marker + "|")
                or row_key.startswith(marker + "#"))
    return False


def rehash_unexplained(die_rows, markers, built_ts, *, emb_xfer=None):
    """die_rows: [(src, row_key, n_seg)]; markers: [(src, key_text, ts_epoch)].
    emb_xfer игнорируется намеренно (запрет плана)."""
    del emb_xfer  # не вычитаем
    out = []
    for src, rk, n_seg in die_rows:
        explained = any(
            m_src == src
            and m_ts > built_ts
            and bridge_row_matches(rk, m_key, n_seg)
            for m_src, m_key, m_ts in markers
        )
        if not explained:
            out.append((src, rk))
    return out


def rehash_gate_fires(unexplained_n, total_emb, tol=0.005, bypass=False):
    if bypass or total_emb == 0:
        return False
    return (unexplained_n / total_emb) > tol


ERROR_MUST = ("RUNBOOK", "§3.113")

# --- 1) массовый hash_kill без свежих маркеров → STOP ---
die_mass = [("e", "k%d" % i, 1) for i in range(100)]
un1 = rehash_unexplained(die_mass, markers=[], built_ts=1000)
t("1: без маркеров все unexplained", len(un1) == 100, len(un1))
t("1: STOP при 100/1000 > 0.5%",
  rehash_gate_fires(len(un1), 1000, tol=0.005))
txt = open(MERGE, encoding="utf-8").read()
# Ветка 1: RUNBOOK/§3.113 ищем В СРЕЗЕ rehash-error(), не по всему файлу
# (комментарии LOSS тоже содержат эти слова — всегда-зелёная ветка).
_i_re = txt.find("массовая смена текста вне свежей дельты 1С")
_rehash_err = txt[_i_re:_i_re + 3000] if _i_re >= 0 else ""
t("1: error содержит RUNBOOK и §3.113",
  all(s in _rehash_err for s in ERROR_MUST))

# --- 2) свежие маркеры вычитают ---
die2 = [("e", "ref|4", 2), ("e", "ref|5", 2), ("e", "other", 1)]
markers_fresh = [
    ("e", "ref|4", 2000),
    ("e", "ref|5", 2000),
]
un2 = rehash_unexplained(die2, markers_fresh, built_ts=1000)
t("2: свежие маркеры вычитают парные",
  un2 == [("e", "other")], un2)
t("2: SQL — bridge_row_matches + окно ts > built_ts",
  "bridge_row_matches(" in txt
  and "epoch(m.ts)::BIGINT" in txt
  and "corpus_built_ts" in txt
  and "die_hash_unexplained" in txt)

# --- 3) старый маркер НЕ объясняет ---
markers_old = [("e", "ref|4", 500)]  # ts <= built_ts
un3 = rehash_unexplained([("e", "ref|4", 2)], markers_old, built_ts=1000)
t("3: старый маркер остаётся unexplained", un3 == [("e", "ref|4")], un3)
t("3: SQL окно строго > (не >=)",
  "epoch(m.ts)::BIGINT" in txt
  and "> coalesce((SELECT v FROM search_quality" in txt
  and "WHERE k = 'corpus_built_ts'" in txt)

# --- 4) rehash_bypass → гейт тих ---
t("4: bypass глушит STOP",
  not rehash_gate_fires(100, 1000, tol=0.005, bypass=True))
t("4: SQL — rehash_bypass в CASE",
  "WHEN (SELECT rehash_bypass FROM tmp3_merge_cfg LIMIT 1)" in txt)

# --- 5) cfg/build.sh синхронны ---
bsh = open(BUILD, encoding="utf-8").read()
t("5: cfg defaults rehash_tol/bypass в merge",
  "rehash_tol = coalesce(rehash_tol, 0.005)" in txt
  and "rehash_bypass = coalesce(rehash_bypass, false)" in txt)
t("5: build.sh — rehash в том же CREATE tmp3_merge_cfg",
  "MERGE_VECTOR_REHASH_TOLERANCE" in bsh
  and "MERGE_VECTOR_REHASH_BYPASS" in bsh
  and "rehash_tol" in bsh
  and "rehash_bypass" in bsh
  and "AS vector_loss_bypass," in bsh
  and "AS rehash_tol," in bsh)
# один CREATE OR REPLACE с обеими парами колонок
m = re.search(
    r"CREATE OR REPLACE TABLE tmp3_merge_cfg AS\s*"
    r"SELECT[^;]+rehash_bypass",
    bsh,
    re.S,
)
t("5: один CREATE несёт vector_loss и rehash",
  m is not None and "vector_loss_tol" in (m.group(0) if m else ""),
  "no single CREATE" if not m else "")

# --- 6) STOP rehash НЕ в условии «векторов_умрёт» ---
# Вырезаем CASE гейта вектор-бюджета (между vector_loss_gate INSERT и
# vector_loss_bypass INSERT) — в нём не должно быть hash_kill_unexplained.
# Пустой срез (якорь не найден) = FAIL, а не всегда-зелёная ветка.
i_gate = txt.find("SELECT 'vector_loss_gate'")
i_bypass = txt.find("SELECT 'vector_loss_bypass'")
vloss_case = txt[i_gate:i_bypass] if i_gate >= 0 and i_bypass > i_gate else ""
t("6: hash_kill_unexplained вне CASE векторов_умрёт",
  len(vloss_case) > 0
  and "hash_kill_unexplained" not in vloss_case
  and "массовая смена текста вне свежей дельты 1С" in txt
  and txt.find("векторов_умрёт") < txt.find("массовая смена текста вне свежей дельты 1С"))

# --- 7) emb_xfer НЕ вычитается ---
block = txt.split("die_hash_unexplained AS", 1)[-1].split(
    "-- 🔴 «УМРЁТ»", 1)[0]
t("7: emb_xfer не в die_hash_unexplained",
  "emb_xfer" not in block and "tmp3_merge_emb_xfer" not in block)

# --- 8) die_hash_rows — row-level (нет GROUP BY до антисоединения) ---
rows_cte = txt.split("die_hash_rows AS (", 1)[-1].split(
    "die_unmatched AS (", 1)[0]
t("8: die_hash_rows без GROUP BY",
  "GROUP BY" not in rows_cte
  and "o.src_table, o.row_key" in rows_cte
  and "len(k.key_cols)" in rows_cte)

# --- 9) окно ТОЛЬКО через corpus_built_ts ---
t("9: окно только corpus_built_ts + epoch(ts)>v",
  "k = 'corpus_built_ts'" in txt
  and "epoch(m.ts)::BIGINT" in txt
  and "mart_changed_ts" not in block)

# --- 10) слепое row_key = key_text без моста запрещено ---
t("10: нет слепого row_key = key_text в unexplained",
  "row_key = m.key_text" not in block
  and "row_key = key_text" not in block
  and "bridge_row_matches(d.row_key, m.key_text, d.n_seg)" in txt)

# метка rehash_gate; vector_loss_gate цел
t("SQL: rehash_gate метка", "SELECT 'rehash_gate'" in txt)
t("SQL: vector_loss_gate не тронут",
  "SELECT 'vector_loss_gate'" in txt
  and "вектор-бюджет — потеря" in txt)
t("SQL: комментарий §3.113 / 1.43M",
  "§3.113" in txt and "1.43M" in txt)

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
