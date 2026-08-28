#!/usr/bin/env python3
"""С5: замок морфологии словаря в пайплайне.

Падает, если словарь собран без морфологии (bare solr_synonyms / alias_idx
на search_dict без стемма / формы одного слова → разные ключи карты).

Оффлайн: сравнение старого DDL (поверхность) vs нового (pipeline + stem-ключи).
Живой DSN не нужен.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import solr_synonyms_build as B  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def assert_morph_ddl(ddl: str, label: str) -> bool:
    """Критерий морфологии в CREATE: pipeline + step1 stemming + solr step2."""
    d = ddl.lower()
    checks = [
        ("pipeline" in d and "template = 'pipeline'" in d),
        ("step1_stemming = true" in d or "step1_stemming=true" in d),
        ("step2_template = 'solr_synonyms'" in d),
        ("template = 'solr_synonyms'" not in d.split("step2_template")[0]
         if "step2_template" in d else False),
    ]
    # bare solr (старый) — первый template solr_synonyms без pipeline
    if "template = 'pipeline'" not in d and "template = 'solr_synonyms'" in d:
        return False
    return all(checks[:3])


def assert_surface_keys_differ(map_text: str) -> bool:
    """Старая карта: клиент и клиентов — разные термы (нет сведения)."""
    lines = [ln.lower() for ln in (map_text or "").splitlines() if ln.strip()]
    blob = "\n".join(lines)
    # если обе формы как отдельные ключи/члены без общего стема — дефект для morph
    has_client = "клиент" in blob
    has_clients = "клиентов" in blob or "клиенты" in blob
    # при стем-ключах поверхность «клиентов» не должна жить как отдельный ключ
    return has_client and has_clients and ("клиентов" in blob or "клиенты" in blob)


# --- (а) старая сборка: bare solr + поверхностные ключи → замок КРАСНЫЙ ---
old_map = "клиенты, контрагент, поставщик\nпродажа, реализации"
old_ddl = (
    "DROP TEXT SEARCH DICTIONARY IF EXISTS search_dict_syn;\n"
    "CREATE TEXT SEARCH DICTIONARY search_dict_syn (\n"
    "  template = 'solr_synonyms',\n"
    "  synonyms = %s\n"
    ");\n" % B.sql_literal(old_map))
t("OLD bare solr_synonyms fails morph check",
  assert_morph_ddl(old_ddl, "old") is False, old_ddl[:180])
t("OLD surface map keeps клиенты+клиентов as distinct forms risk",
  assert_surface_keys_differ("клиент, foo\nклиентов, bar") is True)

# --- (б) новая сборка: pipeline + stem-ключи → замок ЗЕЛЁНЫЙ ---
stem_map = {
    "клиенты": "клиент",
    "клиента": "клиент",
    "клиентов": "клиент",
    "контрагент": "контрагент",
    "поставщик": "поставщик",
    "продажа": "продаж",
    "продажи": "продаж",
}
alias_rows = [
    {"aliases": "клиенты, контрагент, поставщик"},
    {"aliases": "продажа, продажи"},
    {"aliases": "список партнеров"},  # многословный — в карту не идёт
]
new_map = B.compile_rules(alias_rows, stem_map=stem_map)
new_ddl = B.render_ddl("search_dict_syn", new_map, locale="ru_RU.UTF-8")
t("NEW pipeline DDL passes morph check", assert_morph_ddl(new_ddl, "new"), new_ddl[:220])
t("NEW map uses stem клиент (not клиенты/клиентов)",
  "клиент" in new_map and "клиенты" not in new_map and "клиентов" not in new_map,
  new_map)
# продажа+продажи → один стем «продаж» → класса ≥2 нет, правило не пишется (С3)
t("NEW drops single-stem class (продажа/продажи→продаж)",
  "продаж" not in new_map and "продажа" not in new_map, new_map)
t("NEW skips multi-word aliases",
  "партнер" not in new_map and "список" not in new_map, new_map)
t("NEW DDL has step1_stemming", "step1_stemming = true" in new_ddl)
t("NEW DDL has step1 text + step2 solr",
  "step1_template = 'text'" in new_ddl
  and "step2_template = 'solr_synonyms'" in new_ddl)

# формы одного слова + сосед → один стем-ключ класса (не поверхность)
rule = B.rule_from_alias_csv(
    "клиент, клиента, клиентов, клиенты, контрагент", stem_map)
t("inflections collapse to one stem key in class",
  rule is not None
  and "клиент" in (rule or "")
  and "контрагент" in (rule or "")
  and "клиентов" not in (rule or "")
  and "клиенты" not in (rule or ""),
  rule)

# --- (в) corpus_init: alias stem dict + alias_idx + pipeline placeholder ---
init = open(os.path.join(ROOT, "corpus_init.sql"), encoding="utf-8").read()
t("corpus_init defines search_dict_alias_stem",
  "search_dict_alias_stem" in init and "stemming = true" in init)
t("corpus_init alias_idx uses search_dict_alias_stem",
  "USING inverted(aliases search_dict_alias_stem" in init)
t("corpus_init alias_idx does NOT use bare search_dict",
  "USING inverted(aliases search_dict," not in init
  and "USING inverted(aliases search_dict " not in init)
t("corpus_init solr placeholder is pipeline",
  "step1_stemming = true" in init
  and "step2_template = 'solr_synonyms'" in init)

compile_sql = open(os.path.join(ROOT, "solr_synonyms_compile.sql"), encoding="utf-8").read()
t("compile.sql runtime is pipeline stem path",
  "step1_stemming = true" in compile_sql
  and "ts_lexize" in compile_sql
  and "search_dict_alias_stem" in compile_sql)

# --- (г) ensure DDL для alias_idx ---
idx_ddl = B.render_alias_stem_index_ddl("ru_RU.UTF-8")
t("alias stem index DDL drops+creates alias_idx",
  "DROP INDEX IF EXISTS alias_idx" in idx_ddl
  and "search_dict_alias_stem" in idx_ddl
  and "VACUUM (REFRESH_TABLE)" in idx_ddl)
t("alias stem index has frequency=true", "frequency = true" in idx_ddl)

# --- (д) compile_rules signature accepts stem_map ---
import inspect
sig = inspect.signature(B.compile_rules)
t("compile_rules accepts stem_map",
  "alias_rows" in sig.parameters and "stem_map" in sig.parameters)

# --- (е) write-ddl / render roundtrip ---
with tempfile.TemporaryDirectory() as td:
    mp = os.path.join(td, "m.txt")
    out = os.path.join(td, "d.sql")
    open(mp, "w", encoding="utf-8").write(new_map)
    rc = B.main(["write-ddl", "--dict", "search_dict_syn", "--map-file", mp,
                 "--out", out, "--locale", "ru_RU.UTF-8"])
    got = open(out, encoding="utf-8").read()
    t("write-ddl exit 0", rc == 0)
    t("write-ddl produces morph DDL", assert_morph_ddl(got, "write"), got[:200])

# --- (ж) явный контраст: same input surface vs stem ---
surface = B.compile_rules(alias_rows, stem_map=None)
stemmed = B.compile_rules(alias_rows, stem_map=stem_map)
t("surface≠stem maps (lock would catch rollback)",
  surface != stemmed and "клиенты" in surface and "клиент" in stemmed,
  "surface=%r stem=%r" % (surface[:80], stemmed[:80]))

print()
print("Итог:", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("FAIL:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
