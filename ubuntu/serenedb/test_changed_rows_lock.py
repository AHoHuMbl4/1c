#!/usr/bin/env python3
"""Оффлайн: контур маркеров строк search_changed_rows (полная B, этап 0).

0c: DDL живёт в corpus_init.sql с UNIQUE (src_table, key_text, op); миграция для
баз, собранных до пакета, идемпотентна (оба statement-условия пусты при готовом
констрейнте). 0d: pipeline.sh возвращает строковый снимок после синка дописыванием
отсутствующих — симметрично sources. L0/0f/сторож A: dual \\set partial_rebuild в
build+merge; потребление через CASE (не \\if); сторож A в merge после empty-entity.

Писатели пакета A: packet_apply (_contract_tx), poc_load_entity (_upsert_changed_rows),
serene_sync (err → сентинель '*'/full).

Запуск: python3 test_changed_rows_lock.py
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(ROOT, "corpus_init.sql")
BUILD = os.path.join(ROOT, "corpus_build.sql")
MERGE = os.path.join(ROOT, "corpus_merge.sql")
PIPE = os.path.join(ROOT, "pipeline.sh")
APPLY = os.path.join(ROOT, "..", "packet", "packet_apply.py")
POC = os.path.join(ROOT, "poc_load_entity.py")
SYNC = os.path.join(ROOT, "serene_sync.py")
UBUNTU = os.path.join(ROOT, "..")

PASS, FAIL = 0, []

UPSERT_ON_CONFLICT = (
    "ON CONFLICT (src_table, key_text, op) DO UPDATE SET ts = EXCLUDED.ts"
)
SET_PARTIAL_RE = re.compile(r"^\\set partial_rebuild ([01])\s*$", re.M)


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail))[:200] if detail else "")


def _fn_body(src, name):
    m = re.search(r"^def %s\b.*?(?=^def |\Z)" % re.escape(name), src, re.M | re.S)
    return m.group(0) if m else ""


init = open(INIT, encoding="utf-8").read()
build = open(BUILD, encoding="utf-8").read()
merge = open(MERGE, encoding="utf-8").read()
pipe = open(PIPE, encoding="utf-8").read()
apply_py = open(APPLY, encoding="utf-8").read()
poc = open(POC, encoding="utf-8").read()
sync = open(SYNC, encoding="utf-8").read()

# --- 0c: DDL в corpus_init (канон для новых баз) ---
t("init: DDL search_changed_rows",
  "CREATE TABLE IF NOT EXISTS search_changed_rows" in init)
t("init: UNIQUE тройки",
  "UNIQUE (src_table, key_text, op)" in init)
t("init: op/ts колонки",
  "op VARCHAR, ts TIMESTAMP DEFAULT now()" in init)

# --- 0c: миграция идемпотентна (для баз, собранных до пакета) ---
n_cond = init.count("WHERE NOT EXISTS (SELECT 1 FROM information_schema.table_constraints")
t("init: миграция за констрейнтом-условием (два statement)",
  n_cond >= 2, "found %d" % n_cond)
t("init: дедуп оставляет свежий ts (row_number ts DESC)",
  "ORDER BY ts DESC, rowid DESC" in init)
t("init: ADD CONSTRAINT UNIQUE",
  "ADD CONSTRAINT search_changed_rows_uniq" in init)

# --- 3d (синхронная часть 0c): писатели идемпотентны при UNIQUE ---
# Upsert уехал в _contract_tx. Три раздельных доказательства генерации маркеров
# (пропажа любого ловится): литералы op в extend/append, не общий ON CONFLICT.
apply_pkg = _fn_body(apply_py, "apply_package")
apply_gone_fn = _fn_body(apply_py, "_apply_gone")
t("apply: row_markers delta",
  '(table, k, "delta")' in apply_pkg)
t("apply: row_markers deleted_gone",
  '(table, k, "deleted_gone")' in apply_gone_fn)
t('apply: full сентинель ("*", "full")',
  '(table, "*", "full")' in apply_pkg)
contract_tx = _fn_body(apply_py, "_contract_tx")
t("apply: _contract_tx содержит INSERT INTO search_changed_rows",
  "INSERT INTO search_changed_rows" in contract_tx
  and UPSERT_ON_CONFLICT in contract_tx)
# SKIP-инвариант (план 0b/5b) читает max(ts) — повторная отметка ОБЯЗАНА освежать ts
t("apply: ensure-миграция свежего ts",
  "ORDER BY ts DESC, rowid DESC" in apply_py)

# --- 0d: снимок rows возвращается после синка ---
i_sync = pipe.find("serene_sync.py")
i_snap = pipe.find("tmp_changed_rows_keep AS SELECT")
i_restore = pipe.find("INSERT INTO search_changed_rows SELECT k.src_table")
i_drop = pipe.find("DROP TABLE tmp_changed_rows_keep")
t("pipeline: rows snapshot до sync",
  i_sync >= 0 and i_snap >= 0 and i_snap < i_sync)
t("pipeline: rows restore после sync",
  i_sync >= 0 and i_restore > i_sync)
t("pipeline: rows restore дописыванием отсутствующих",
  "WHERE NOT EXISTS (SELECT 1 FROM search_changed_rows r" in pipe)
t("pipeline: rows snapshot снимается (DROP)",
  i_drop > i_restore > 0)

# --- L0/0f/сторож A: dual \\set + потребление CASE (не \\if) ---
# Прежний assert «константа не читается до этапа 1» снят: потребление легитимно
# (R6 CTAS + сторож A). \\if по-прежнему запрещён — только CASE.
t("merge: константа partial_rebuild=0",
  "\\set partial_rebuild 0" in merge)

_sets_b = SET_PARTIAL_RE.findall(build)
_sets_m = SET_PARTIAL_RE.findall(merge)
t("dual \\set: ровно один в build",
  len(_sets_b) == 1, _sets_b)
t("dual \\set: ровно один в merge",
  len(_sets_m) == 1, _sets_m)
t("dual \\set: значения равны",
  len(_sets_b) == 1 and len(_sets_m) == 1 and _sets_b[0] == _sets_m[0],
  "build=%s merge=%s" % (_sets_b, _sets_m))

t("потребление :partial_rebuild в build",
  ":partial_rebuild" in build)
t("потребление :partial_rebuild в merge",
  ":partial_rebuild" in merge)
t("\\if :partial_rebuild нет (CASE, не \\if)",
  "\\if :partial_rebuild" not in build
  and "\\if :partial_rebuild" not in merge)

# (а) R6-ветка CTAS mode='full' при partial_rebuild=0
t("build: CASE mode — :partial_rebuild=0 → 'full' (R6)",
  "WHEN :partial_rebuild = 0 THEN 'full'" in build
  and "END AS mode" in build)

# (б) сторож A после empty-entity / «собрались пустыми», до vec_budget
i_empty = merge.find("собрались пустыми")
i_guard = merge.find("mode IS DISTINCT FROM 'full'")
i_err_a = merge.find("partial_rebuild=0, но mode")
i_vec = merge.find("tmp3_merge_vec_budget")
t("merge: сторож A (mode IS DISTINCT FROM 'full' + error)",
  i_guard >= 0 and i_err_a >= 0 and "error(" in merge[i_guard - 80:i_err_a + 120])
t("merge: сторож A после empty-entity, до vec_budget",
  i_empty >= 0 and i_guard > i_empty and i_vec > i_guard,
  "empty@%d guard@%d vec@%d" % (i_empty, i_guard, i_vec))

# L4(б) сразу после CTAS tmp3_build
i_ctas = build.find("CREATE OR REPLACE TABLE tmp3_build AS")
i_l4 = build.find("corpus_build: L4(б)")
t("build: L4(б) после CTAS (mode IS NULL + error)",
  i_ctas >= 0 and i_l4 > i_ctas
  and "mode IS NULL" in build[i_ctas:i_l4 + 200]
  and "error(" in build[i_l4 - 40:i_l4 + 120],
  "ctas@%d l4@%d" % (i_ctas, i_l4))

# rebuild_mode per-src
t("build: rebuild_mode per-src k='rebuild_mode:'",
  "'rebuild_mode:' ||" in build or "\"rebuild_mode:\" ||" in build)
t("build: DELETE LIKE 'rebuild_mode:%'",
  "DELETE FROM search_quality WHERE k LIKE 'rebuild_mode:%'" in build)

# env-замок: unit-ы и git-шаблоны env — без PARTIAL_/MERGE_ (рубильник только \\set)
_env_hits = []
for _dir in (
    os.path.join(UBUNTU, "systemd"),
    os.path.join(UBUNTU, "packet", "systemd"),
):
    for _pat in ("*.service", "*.conf", "*.env", "*.env.example"):
        for _p in glob.glob(os.path.join(_dir, "**", _pat), recursive=True):
            try:
                _txt = open(_p, encoding="utf-8").read()
            except OSError:
                continue
            if re.search(r"PARTIAL_|MERGE_", _txt):
                _env_hits.append(os.path.relpath(_p, UBUNTU))
# шаблоны /etc из git (имена совпадают с EnvironmentFile юнитов)
for _p in glob.glob(os.path.join(UBUNTU, "**", "*.env.example"), recursive=True):
    try:
        _txt = open(_p, encoding="utf-8").read()
    except OSError:
        continue
    if re.search(r"PARTIAL_|MERGE_", _txt):
        _rel = os.path.relpath(_p, UBUNTU)
        if _rel not in _env_hits:
            _env_hits.append(_rel)
t("env-замок: нет PARTIAL_/MERGE_ в unit/env-шаблонах",
  not _env_hits, _env_hits)

# --- пакет A: HTTP-писатель poc_load_entity ---
upsert_helper = _fn_body(poc, "_upsert_changed_rows")
t("poc: хелпер upsert с ON CONFLICT DO UPDATE SET ts",
  "def _upsert_changed_rows" in upsert_helper
  and UPSERT_ON_CONFLICT in upsert_helper)

delta_fn = _fn_body(poc, "load_entity_delta")
# Маркеры ПОСЛЕ DML: вызов deleted_gone ниже любого DELETE FROM витрины
i_del = delta_fn.find("DELETE FROM")
i_gone_mark = delta_fn.find('_upsert_changed_rows(table, gone, "deleted_gone")')
i_delta_mark = delta_fn.find('_upsert_changed_rows(table, delta_keys, "delta")')
t("poc delta: deleted_gone не раньше DELETE витрины",
  i_del >= 0 and i_gone_mark > i_del
  and i_delta_mark > i_del,
  "DELETE@%d delta@%d gone@%d" % (i_del, i_delta_mark, i_gone_mark))
# persist ⊆ applied: delta_keys = changed − gone, gone → deleted_gone
t("poc delta: persist ⊆ applied (delta_keys исключает gone)",
  "delta_keys = [k for k in changed if k not in" in delta_fn
  and '_upsert_changed_rows(table, delta_keys, "delta")' in delta_fn
  and '_upsert_changed_rows(table, gone, "deleted_gone")' in delta_fn)

full_fn = _fn_body(poc, "load_entity")
n_full_sentinel = full_fn.count('_upsert_changed_rows(table, ["*"], "full")')
n_upsert_in_full = full_fn.count("_upsert_changed_rows")
t("poc full: сентинель ['*'] op full — ровно один ряд",
  n_full_sentinel == 1 and n_upsert_in_full == 1,
  "sentinel=%d upserts=%d" % (n_full_sentinel, n_upsert_in_full))

# --- L7: serene_sync err → '*' / full (FULLB §5) ---
# Вызов — строка кода, не комментарий (strip не начинается с '#').
t("sync err: _upsert_changed_rows с ['*'], full",
  any("_upsert_changed_rows" in ln and '["*"]' in ln and '"full"' in ln
      and not ln.strip().startswith("#")
      for ln in sync.splitlines()))

# --- 0f вне A: писатели rows не ветвятся по mode/partial_rebuild ---
t("poc: нет mode/partial_rebuild",
  "partial_rebuild" not in poc and not re.search(r"\bmode\b", poc))
t("sync: нет partial_rebuild; upsert-вызовы без mode",
  "partial_rebuild" not in sync
  and all("mode" not in ln
          for ln in sync.splitlines() if "_upsert_changed_rows" in ln))

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
