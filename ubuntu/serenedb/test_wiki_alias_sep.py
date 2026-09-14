#!/usr/bin/env python3
"""Оффлайн-замок G2: разделитель ' | ', потолок 1600, двойные читатели.

Без базы и сети. Отдельный файл — не раздувать prompts_v2 (G1) и не смешивать
с семантикой meta/title; parse-замок остаётся на инвариантах разбора величин.
"""
from __future__ import annotations

import io
import os
import re
import sys
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wiki_alias_parse as P  # noqa: E402
import entity_rank_v2 as ER  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# ── _join: разделитель и потолок ─────────────────────────────────────────────
joined = P._join(["а", "б", "в"])
t("_join пишет ' | '", joined == "а | б | в", joined)
t("_join потолок по умолчанию 1600", P._JOIN_CAP == 1600 and P._join.__defaults__[0] == 1600)

# Длинный список: не режется раньше 1600 (элементы по 10 симв. + sep)
items = ["x" * 10 for _ in range(200)]  # 200*10 + 199*3 = 2597 > 1600
long = P._join(items)
t("_join длинный список режется на 1600, не раньше",
  len(long) == 1600 and " | " in long[:50],
  (len(long), long[:40]))
# При потолке 900 старый код обрезал бы раньше — убедимся, что 901-й символ достижим
mid = P._join(["y" * 50] * 20)  # 20*50 + 19*3 = 1057
t("_join >900 символов не режется раньше 1600",
  len(mid) == 1057, len(mid))

# ── валидатор '|': лог + результат ───────────────────────────────────────────
buf = io.StringIO()
with redirect_stderr(buf):
    scrubbed = P._join(["нормальный", "плохой|хвост", "|", "ещё"])
err = buf.getvalue()
t("pipe-валидатор: символ вырезан, элемент сохранён",
  scrubbed == "нормальный | плохойхвост | ещё", scrubbed)
t("pipe-валидатор: голый '|' отброшен",
  " |  | " not in scrubbed and scrubbed.count("|") == 2, scrubbed)
t("pipe-валидатор: лог в stderr",
  "pipe in element stripped" in err and "плохой|хвост" in err, err[:200])

# ── _alias_tokens: оба формата ───────────────────────────────────────────────
t("_alias_tokens: новый ' | '",
  P._alias_tokens("а | б | в") == ["а", "б", "в"])
t("_alias_tokens: старый ', '",
  P._alias_tokens("а, б, в") == ["а", "б", "в"])
t("_alias_tokens: BUF с запятой внутри + pipe",
  P._alias_tokens("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("_alias_tokens: список без изменений",
  P._alias_tokens(["а", "б"]) == ["а", "б"])
# дедуп в filter (не в tokens)
got_dedup = P.filter_entity_aliases("клиент | Клиент | товар")
t("_alias_tokens+filter: дедуп после разбора ' | '",
  got_dedup == ["клиент", "товар"], got_dedup)
got_old = P.filter_entity_aliases("клиент, Клиент, товар")
t("_alias_tokens+filter: дедуп после разбора ', '",
  got_old == ["клиент", "товар"], got_old)

# ── потребители: маркеры нового формата + фолбэк ─────────────────────────────
build = (HERE / "wiki_build.sql").read_text(encoding="utf-8")
t("wiki_build: str_split ' | '", "str_split(coalesce(a.aliases, ''), ' | ')" in build)
t("wiki_build: фолбэк ', ' (aliases)",
  "THEN str_split(a.aliases, ', ')" in build
  and "position(', ' IN coalesce(a.aliases, '')) > 0" in build)
# P4: best/nef без ', '-фолбэка — «взнос работодателя, НДФЛ» без ' | ' → 1 элемент
t("wiki_build: best/nef БЕЗ фолбэка ', '",
  "THEN str_split(a.best_used_for, ', ')" not in build
  and "THEN str_split(a.not_enough_for, ', ')" not in build
  and "str_split(coalesce(a.best_used_for, ''), ' | ')" in build
  and "str_split(coalesce(a.not_enough_for, ''), ' | ')" in build)

left = (HERE / "wiki_alias_collision_left.sql").read_text(encoding="utf-8")
t("collision_left: ' | ' + фолбэк ', '",
  "str_split(coalesce(aliases, ''), ' | ')" in left
  and "THEN str_split(aliases, ', ')" in left
  and "position(', ' IN coalesce(aliases, '')) > 0" in left)

round_sql = (HERE / "wiki_alias_collision_round.sql").read_text(encoding="utf-8")
t("collision_round: ' | ' + фолбэк ', '",
  "str_split(coalesce(aliases, ''), ' | ')" in round_sql
  and "THEN str_split(aliases, ', ')" in round_sql
  and "position(', ' IN coalesce(aliases, '')) > 0" in round_sql)

rank = (HERE / "entity_rank_v2.py").read_text(encoding="utf-8")
t("entity_rank_v2: split_part ' | ' + фолбэк",
  "split_part(coalesce(a.aliases, ''), ' | ', 1)" in rank
  and "split_part(a.aliases, ', ', 1)" in rank
  and "position(', ' IN coalesce(a.aliases, '')) > 0" in rank)

# ── entity_rank_v2._alias_parts: dual-разбор мер (G2c / R14) ─────────────────
t("_alias_parts: новый ' | '",
  ER._alias_parts("сумма | итог | всего") == ["сумма", "итог", "всего"])
t("_alias_parts: старый ', '",
  ER._alias_parts("сумма, итог, всего") == ["сумма", "итог", "всего"])
t("_alias_parts: BUF с запятой внутри + pipe",
  ER._alias_parts("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("_alias_parts: дедуп casefold",
  ER._alias_parts("Сумма | сумма | ИТОГ") == ["Сумма", "ИТОГ"])
t("_alias_parts: голая ',' (запас)",
  ER._alias_parts("а,б,в") == ["а", "б", "в"])

# ── z14_clarify_memory._alias_parts: dual (G2d) — живой импорт, без БД/env ───
from ask.z14_clarify_memory import _alias_parts as Z14_alias_parts  # noqa: E402
t("z14._alias_parts: новый ' | '",
  Z14_alias_parts("сумма | итог | всего") == ["сумма", "итог", "всего"])
t("z14._alias_parts: старый ', '",
  Z14_alias_parts("сумма, итог, всего") == ["сумма", "итог", "всего"])
t("z14._alias_parts: BUF с запятой внутри + pipe",
  Z14_alias_parts("взнос работодателя, НДФЛ | другая")
  == ["взнос работодателя, НДФЛ", "другая"])
t("z14._alias_parts: дедуп casefold",
  Z14_alias_parts("Сумма | сумма | ИТОГ") == ["Сумма", "ИТОГ"])
t("z14._alias_parts: голая ',' (запас)",
  Z14_alias_parts("а,б,в") == ["а", "б", "в"])
t("z14._alias_parts: список без изменений",
  Z14_alias_parts(["а", "б"]) == ["а", "б"])

reask = (HERE / "wiki_alias_reask_merge_confirmed.sql").read_text(encoding="utf-8")
t("reask append через ' | '",
  "t.aliases || ' | ' || n.aliases" in reask
  and "|| ', '" not in reask)

z02 = (HERE / "ask" / "z02_intent.py").read_text(encoding="utf-8")
t("z02_intent: re.split [,;|/] не трогали",
  're.split(r"[,;|/]"' in z02)

# ── promote: union-MERGE черновик→бой (§3.99) ────────────────────────────────
def _sql_body_early(s: str) -> str:
    return "\n".join(
        ln for ln in s.splitlines() if not ln.lstrip().startswith("--")
    )


prom_path = HERE / "wiki_alias_promote.sql"
t("promote: файл wiki_alias_promote.sql есть", prom_path.is_file())
prom = prom_path.read_text(encoding="utf-8") if prom_path.is_file() else ""
prom_body = _sql_body_early(prom) if prom else ""

t("promote: union-MERGE через _alias_union_tokens",
  "CREATE OR REPLACE MACRO _alias_union_tokens" in prom
  and "MERGE INTO" in prom
  and "_alias_union_tokens(t.aliases, s.draft_aliases)" in prom)
t("promote: dual-сплит маркер ',| [|] ' (без backslash, scs §3.119)",
  ",| [|] " in prom)
t("promote: снапшот боя _pre_promote_ + snap_suffix",
  "_pre_promote_" in prom
  and 'CREATE TABLE :"entity_snap" AS SELECT * FROM :"battle_table"' in prom
  and ":snap_suffix" in prom)
t("promote: гейты fail-closed (a)(b)(c)(d) + \\if + error",
  "GATE (a)" in prom and "GATE (b)" in prom and "GATE (c)" in prom and "GATE (d)" in prom
  and "\\if :gate_a_ok" in prom and "\\if :gate_b_ok" in prom and "\\if :gate_c_ok" in prom
  and "\\if :gate_d_ok" in prom
  and "error(" in prom)
t("promote: гейт (d) построчный — list_has_all(battle, snap) по ключу",
  "list_has_all(" in prom
  and 'JOIN :"entity_snap" s ON' in prom.replace("\n", " ")
  and "list_filter(list_transform(" in prom)
t("promote: нет replace-стиля SET aliases = n. (§3.99)",
  not re.search(r"SET\s+aliases\s*=\s*n\.", prom_body, re.I)
  and "aliases = n.aliases" not in prom_body)
t("promote: нет DELETE unmatched-by-source (C2)",
  "NOT MATCHED BY SOURCE" not in prom_body)
t("promote: матрица (г) best/nef — heal/keep/union",
  # бой заморожен + чистый непустой draft → replace draft
  "THEN s.draft_best" in prom
  and "THEN s.draft_nef" in prom
  and "NOT regexp_matches(coalesce(s.draft_best" in prom
  and "NOT regexp_matches(coalesce(s.draft_nef" in prom
  and "trim(s.draft_best) <> ''" in prom
  and "trim(s.draft_nef) <> ''" in prom
  # бой заморожен + dirty/empty draft → боевое; бой чист + dirty draft → боевое
  and prom.count("THEN t.best_used_for") >= 2
  and prom.count("THEN t.not_enough_for") >= 2
  # NOT-форма в heal + положительная в keep-dirty-draft (иначе две keep без WHEN)
  and prom.count("regexp_matches(coalesce(s.draft_best") >= 2
  and prom.count("regexp_matches(coalesce(s.draft_nef") >= 2
  # порядок веток: heal раньше keep (иначе heal мёртв); union после keep
  and prom.find("THEN s.draft_best") < prom.find("THEN t.best_used_for")
  and prom.find("THEN s.draft_nef") < prom.find("THEN t.not_enough_for")
  and prom.find("THEN t.best_used_for")
     < prom.find("_alias_union_tokens(t.best_used_for, s.draft_best)")
  and prom.find("THEN t.not_enough_for")
     < prom.find("_alias_union_tokens(t.not_enough_for, s.draft_nef)")
  # оба чисты → union
  and "_alias_union_tokens(t.best_used_for, s.draft_best)" in prom
  and "_alias_union_tokens(t.not_enough_for, s.draft_nef)" in prom
  # aliases — union как было (§3.99)
  and "_alias_union_tokens(t.aliases, s.draft_aliases)" in prom
  # отчёт: счётчики веток
  and "best_frozen_healed" in prom
  and "best_frozen_dirty_draft" in prom
  and "best_frozen_empty_draft" in prom
  and "nef_frozen_healed" in prom
  and "nef_frozen_dirty_draft" in prom
  and "nef_frozen_empty_draft" in prom
  and "insert_with_pattern" in prom
  # шапка под матрицу (г), не старое «оставляем БОЕВОЕ»
  and "матрица заморозки (г)" in prom
  and "оставляем БОЕВОЕ" not in prom)
t("promote: откат закомментирован внизу",
  "ОТКАТ" in prom and "pre_promote_" in prom
  and "INSERT INTO search_entity_alias SELECT *" in prom)
t("promote: шапка — только по слову владельца",
  "ПО СЛОВУ ВЛАДЕЛЬЦА" in prom and "§3.99" in prom)

# ── residual SEP migrate (после promote) ─────────────────────────────────────
mig = (HERE / "wiki_alias_migrate_sep.sql").read_text(encoding="utf-8")
mig_body = _sql_body_early(mig)
t("migrate: residual — БЕЗ собственного CREATE snap",
  "CREATE TABLE" not in mig_body
  and "pre_promote_" in mig
  and "НЕ свой" in mig)
t("migrate: replace с скобками + guard position(' | ')=0",
  "replace(aliases, ', ', ' | ')" in mig
  and "regexp_matches(aliases, '\\([^)]*,[^)]*\\)')" in mig
  and "NOT regexp_matches" in mig
  and "position(' | ' IN aliases) = 0" in mig
  and "position(' | ' IN best_used_for) = 0" in mig
  and "position(' | ' IN not_enough_for) = 0" in mig)
t("migrate: транзакция BEGIN/COMMIT + dry_run",
  "BEGIN;" in mig and "COMMIT;" in mig
  and "dry_run" in mig and "aliases_elig" in mig)
t("migrate: скобочные 13/27 — комментарий, force-regen отдельно",
  "13/27" in mig and "force-regen" in mig)
t("migrate: откат из снапшота promote",
  "ОТКАТ" in mig and "pre_promote_" in mig)
t("migrate: шапка — только по слову владельца",
  "ПО СЛОВУ ВЛАДЕЛЬЦА" in mig)

# ── G4: PROBE_TABLE (песочница не марает боевую память столкновений) ─────────
init = (HERE / "wiki_alias_init.sql").read_text(encoding="utf-8")
# DDL-строка probe — переменная, не литерал (CREATE … :probe_table)
ddl_probe = [ln for ln in init.splitlines() if "CREATE TABLE" in ln and "probe" in ln.lower()]
t("init: DDL probe через :probe_table, без литерала search_alias_probe",
  len(ddl_probe) == 1
  and ":probe_table" in ddl_probe[0]
  and "search_alias_probe" not in ddl_probe[0],
  ddl_probe)
t("init: литерал search_alias_probe отсутствует в файле",
  "search_alias_probe" not in init)

t("collision_round: :probe_table в NOT EXISTS и INSERT, литерала нет",
  "FROM :probe_table" in round_sql
  and "INSERT INTO :probe_table" in round_sql
  and "search_alias_probe" not in round_sql)
t("collision_left: :probe_table в NOT EXISTS, литерала нет",
  "FROM :probe_table" in left
  and "search_alias_probe" not in left)

sh = (HERE / "wiki_alias.sh").read_text(encoding="utf-8")
t("wiki_alias.sh: PROBE_TABLE дефолт search_alias_probe",
  'PROBE_TABLE="${PROBE_TABLE:-search_alias_probe}"' in sh)
t("wiki_alias.sh: -v probe_table в psql_wa и psql_wa_tA",
  sh.count('-v probe_table="$PROBE_TABLE"') >= 2)
# collision_left/round зовутся psql_wa_tA — переменная должна быть в обеих обёртках
t("wiki_alias.sh: collision_left через psql_wa_tA (probe_table доезжает)",
  'psql_wa_tA -f "$HERE/wiki_alias_collision_left.sql"' in sh)
# :probe_table только в SQL, которые зовутся через обёртки с -v probe_table
probe_sql_files = [
    HERE / "wiki_alias_init.sql",
    HERE / "wiki_alias_collision_round.sql",
    HERE / "wiki_alias_collision_left.sql",
]
other_sql = [p for p in HERE.glob("wiki_alias*.sql") if p not in probe_sql_files]
t(":probe_table только в init/round/left (остальные SQL без переменной)",
  all(":probe_table" not in p.read_text(encoding="utf-8") for p in other_sql),
  [p.name for p in other_sql if ":probe_table" in p.read_text(encoding="utf-8")])

# ── G5: force в выборке пачек (select entity/measure) ─────────────────────────
ent_sel = (HERE / "wiki_alias_select_entity_batch.sql").read_text(encoding="utf-8")
meas_sel = (HERE / "wiki_alias_select_measure_batch.sql").read_text(encoding="utf-8")

def _sql_body(s: str) -> str:
    """Строки кода без --комментариев (счётчики NOT EXISTS не путают с шапкой)."""
    return "\n".join(
        ln for ln in s.splitlines() if not ln.lstrip().startswith("--")
    )


ent_body, meas_body = _sql_body(ent_sel), _sql_body(meas_sel)

t("entity_batch: литерал coalesce(a.aliases,'') <> '' сохранён",
  "coalesce(a.aliases,'') <> ''" in ent_sel)
t("entity_batch: :force = 0 AND в обоих NOT EXISTS",
  ent_body.count("NOT EXISTS") == 2 and ent_body.count(":force = 0 AND") == 2)
t("entity_batch: шапка про force=1 / P7 §5.5",
  "force=1" in ent_sel and "P7 §5.5" in ent_sel)

e0 = re.sub(r":force\b", "0", ent_sel)
e1 = re.sub(r":force\b", "1", ent_sel)
t("entity force=0: отсев жив (0 = 0 AND + непустые)",
  "0 = 0 AND" in e0 and "coalesce(a.aliases,'') <> ''" in e0)
t("entity force=1: отсев выключен (1 = 0 AND) — непустые не режутся",
  "1 = 0 AND" in e1 and ":force = 0 AND" not in e1)

t("measure_batch: литерал coalesce(m.aliases,'') <> '' сохранён",
  "coalesce(m.aliases,'') <> ''" in meas_sel)
# Два NOT EXISTS отсева × seed+основной = 4; EXISTS сущности — без force.
t("measure_batch: :force = 0 AND в обоих NOT EXISTS отсева (seed+main)",
  meas_body.count("NOT EXISTS") == 4 and meas_body.count(":force = 0 AND") == 4)
t("measure_batch: шапка про force=1 / P7 §5.5",
  "force=1" in meas_sel and "P7 §5.5" in meas_sel)

m0 = re.sub(r":force\b", "0", meas_sel)
m1 = re.sub(r":force\b", "1", meas_sel)
t("measure force=0: отсев жив (0 = 0 AND + непустые)",
  "0 = 0 AND" in m0 and "coalesce(m.aliases,'') <> ''" in m0)
t("measure force=1: отсев выключен (1 = 0 AND)",
  "1 = 0 AND" in m1 and ":force = 0 AND" not in m1)

# Оба select — через psql_wa_tA (обёртка несёт -v force); не голый psql.
for _sel, _label in (
    ("wiki_alias_select_entity_batch.sql", "entity"),
    ("wiki_alias_select_measure_batch.sql", "measure"),
):
    _i = sh.find(_sel)
    _chunk = sh[max(0, _i - 160):_i]
    t("wiki_alias.sh: select_%s через psql_wa_tA (−v force)" % _label,
      _i > 0 and "psql_wa_tA" in _chunk and "psql " not in _chunk.replace("psql_wa", ""),
      _chunk[-80:])
t("wiki_alias.sh: -v force в обеих обёртках psql_wa*",
  sh.count('-v force="$WIKI_ALIAS_FORCE"') >= 2)

# ── G5b: OFFSET-курсор при force=1 (продвижение пачек) ───────────────────────
_OFF = "OFFSET CASE WHEN :force = 1 THEN :skip_rows ELSE 0 END"
t("entity_batch: OFFSET CASE WHEN :force=1 THEN :skip_rows ELSE 0",
  _OFF in ent_body)
t("measure_batch: OFFSET CASE WHEN :force=1 THEN :skip_rows ELSE 0",
  _OFF in meas_body)
# Инвариант: при force=0 OFFSET всегда 0 (ветка ELSE 0 в том же CASE).
t("OFFSET force=0 → ELSE 0 (оба select)",
  all("ELSE 0 END" in b and _OFF in b for b in (ent_body, meas_body)))

# entity-select: -v skip_rows="$done_total"; measure: -v skip_rows="$done_measures"
_ei = sh.find("wiki_alias_select_entity_batch.sql")
_echunk = sh[max(0, _ei - 220):_ei]
t("wiki_alias.sh: entity-select несёт -v skip_rows=$done_total",
  _ei > 0 and '-v skip_rows="$done_total"' in _echunk, _echunk[-100:])
_mi = sh.find("wiki_alias_select_measure_batch.sql")
_mchunk = sh[max(0, _mi - 280):_mi]
t("wiki_alias.sh: measure-select несёт -v skip_rows=$done_measures",
  _mi > 0 and '-v skip_rows="$done_measures"' in _mchunk, _mchunk[-120:])
t("wiki_alias.sh: done_measures=0 перед циклом мер",
  "done_measures=0" in sh and "done_measures=$((done_measures + BATCH))" in sh)

# ── G8b: cand/left не выбирают мета-стоп P3 (живые множества равны) ───────────
# Правило: frozenset SQL VALUES == _PLATFORM_META_STOP (строгое равенство).
_META_NOT_IN = "NOT IN (SELECT word FROM meta_stop)"
_PICK_ORDER = "ORDER BY c.n DESC, c.alias LIMIT 1"
_VALUES_RE = re.compile(
    r"meta_stop\s*\(\s*word\s*\)\s*AS\s*\(\s*VALUES\s*((?:\([^)]+\)\s*,?\s*)+)\)",
    re.IGNORECASE | re.DOTALL,
)
_WORD_RE = re.compile(r"\(\s*'((?:[^'\\]|\\.)*)'\s*\)")


def _meta_stop_from_sql(sql_text: str) -> frozenset:
    m = _VALUES_RE.search(sql_text)
    if not m:
        return frozenset()
    return frozenset(_WORD_RE.findall(m.group(1)))


_py_stop = frozenset(P._PLATFORM_META_STOP)
_round_stop = _meta_stop_from_sql(round_sql)
_left_stop = _meta_stop_from_sql(left)

t("G8b round: meta_stop VALUES == _PLATFORM_META_STOP",
  _round_stop == _py_stop,
  "only_sql=%r only_py=%r" % (sorted(_round_stop - _py_stop),
                              sorted(_py_stop - _round_stop)))
t("G8b left: meta_stop VALUES == _PLATFORM_META_STOP",
  _left_stop == _py_stop,
  "only_sql=%r only_py=%r" % (sorted(_left_stop - _py_stop),
                              sorted(_py_stop - _left_stop)))
t("G8b round: cand фильтр NOT IN meta_stop",
  _META_NOT_IN in round_sql)
t("G8b left: cand фильтр NOT IN meta_stop",
  _META_NOT_IN in left)
t("G8b round: комментарий источник _PLATFORM_META_STOP",
  "wiki_alias_parse.py:_PLATFORM_META_STOP" in round_sql)
t("G8b left: комментарий источник _PLATFORM_META_STOP",
  "wiki_alias_parse.py:_PLATFORM_META_STOP" in left)
t("G8b pick: ORDER BY c.n DESC, c.alias LIMIT 1 неизменен",
  _PICK_ORDER in round_sql)

# ── G8c / H4: recover_collision из снапшота (заготовка, без живой базы) ───────
rec = (HERE / "wiki_alias_recover_collision.sql").read_text(encoding="utf-8")
rec_body = _sql_body(rec)

t("recover: :snap_table переменная (не хардкод snap-имени)",
  ":snap_table" in rec
  and "alias_okna_c5" not in rec
  and "alias_okna_c5_pre_v2" not in rec)
t("recover: :alias_table + :since в критерии",
  ":alias_table" in rec and "CAST(:'since' AS TIMESTAMP)" in rec)
t("recover: dual n_elems < 3 в критерии (CASE position)",
  "position(' | ' IN coalesce(t.aliases, '')) > 0" in rec
  and "THEN str_split(coalesce(t.aliases, ''), ' | ')" in rec
  and "ELSE str_split(coalesce(t.aliases, ''), ', ') END) < 3" in rec)
t("recover: UPDATE ... FROM snap",
  "UPDATE :alias_table t" in rec_body
  and "FROM :snap_table s" in rec_body
  and "SET aliases = s.aliases" in rec_body)
_upd = rec_body[rec_body.find("UPDATE :alias_table t"):
            rec_body.find("SELECT 'recovered_now_match_snap'")]
t("recover: UPDATE без SET seen_at (мягкость)",
  "seen_at =" not in _upd.replace("seen_at >=", "SEEN_AT_GE"))
t("recover: контрольные SELECT (отчёт + remaining_stub)",
  "n_to_recover" in rec
  and "remaining_stub" in rec
  and "recovered_now_match_snap" in rec
  and "LIMIT 20" in rec)
t("recover: шапка-предупреждение о запуске",
  "ПО СЛОВУ ВЛАДЕЛЬЦА" in rec
  and "ПЕРЕД повторным" in rec
  and "G8c" in rec
  and "H4" in rec)


def _n_elems(a: str | None) -> int:
    """Dual как SQL: pipe если ' | ' есть, иначе ', '. '' → [''], len=1."""
    if a is None:
        a = ""
    if a == "":
        return 1
    if " | " in a:
        return len(a.split(" | "))
    return len(a.split(", "))


def _stub_aliases(a: str | None) -> bool:
    if a is None:
        a = ""
    n = _n_elems(a)
    # Короткость — по pipe-разбору t (текущий формат); dual только счётчик.
    parts = a.split(" | ") if a else [""]
    all_short = a != "" and all(len(x.strip()) < 4 for x in parts)
    return n < 3 or all_short


def should_recover(t_aliases, s_aliases, *, has_snap: bool, seen_fresh: bool) -> bool:
    """Py-эмуляция критерия H4 recover_collision (dual n_elems)."""
    if not seen_fresh or not has_snap or s_aliases is None:
        return False
    if not _stub_aliases(t_aliases):
        return False
    sn, tn = _n_elems(s_aliases), _n_elems(t_aliases)
    return sn >= 3 or sn > tn


t("recover-crit: обрубок+хороший snap → восстановить",
  should_recover(
      "номенклатуры | товара",
      "Вид Номенклатуры | Виды Номенклатуры | тип товара | номенклатура",
      has_snap=True, seen_fresh=True) is True)
t("recover-crit: хорошее новое (≥3) → НЕ трогать",
  should_recover(
      "акт сверки | сверка взаиморасчетов | акт сверки расчетов | остаток",
      "акт сверки | сверка | взаиморасчёты | долг | расхождения",
      has_snap=True, seen_fresh=True) is False)
t("recover-crit: snap тоже плох → НЕ трогать",
  should_recover(
      "цен | и",
      "цена | вид",
      has_snap=True, seen_fresh=True) is False)
t("recover-crit: нет в snap → НЕ трогать",
  should_recover(
      "номенклатуры | товара",
      None,
      has_snap=False, seen_fresh=True) is False)

# ── G8c2: dual-счётчик (snap старого формата ', ') ───────────────────────────
# Маркер: position ' | ' + ELSE str_split ', ' (как в SQL n_elems).
t("G8c2 SQL: dual-CASE (position ' | ' + ELSE str_split ', ')",
  "position(' | ' IN coalesce(s.aliases, '')) > 0" in rec
  and "THEN str_split(coalesce(s.aliases, ''), ' | ')" in rec
  and "ELSE str_split(coalesce(s.aliases, ''), ', ')" in rec
  and "G8c2" in rec
  and "СТАРЫЙ формат" in rec)

# 1) t обрубок pipe + snap хороший ', ' (3+) → лечится (баг до dual: n_pipe(snap)=1)
t("G8c2 crit: stub pipe + snap ', ' ≥3 → recover",
  should_recover(
      "номенклатуры | товара",
      "Вид Номенклатуры, Виды Номенклатуры, тип товара, номенклатура",
      has_snap=True, seen_fresh=True) is True)
# 2) t хороший pipe ≥3 → НЕ
t("G8c2 crit: t pipe ≥3 → НЕ трогать",
  should_recover(
      "акт сверки | сверка взаиморасчетов | акт сверки расчетов | остаток",
      "акт, сверка, долг, расхождения",
      has_snap=True, seen_fresh=True) is False)
# 3) snap ', ' плох (1–2) → НЕ
t("G8c2 crit: snap ', ' плох (2) → НЕ",
  should_recover(
      "цен | и",
      "цена, вид",
      has_snap=True, seen_fresh=True) is False)
# 4) snap пуст → НЕ (n_elems('')=1, не > stub и не ≥3)
t("G8c2 crit: snap пуст → НЕ",
  should_recover(
      "номенклатуры | товара",
      "",
      has_snap=True, seen_fresh=True) is False)
# 5) запятая ВНУТРИ фразы в snap старого формата:
# dual без ' | ' режет по ', ' → ДВА элемента («взнос…» / «НДФЛ»), как до миграции.
# В новом формате (' | ') запятая внутри фразы НЕ режет — одна целая.
# Осознанно: для snap pre-v2 это два элемента; критерий ≥3 их не спасёт в одиночку.
_comma_inside = "«взнос работодателя, НДФЛ»"
_comma_parts_old = _comma_inside.split(", ")  # dual ELSE-ветка (нет ' | ')
t("G8c2 dual: snap «взнос работодателя, НДФЛ» → 2 элемента (старый ', ')",
  _n_elems(_comma_inside) == 2
  and _comma_parts_old == ["«взнос работодателя", "НДФЛ»"],
  (_n_elems(_comma_inside), _comma_parts_old))
_pipe_with_comma = "«взнос работодателя, НДФЛ» | другая"
t("G8c2 dual: pipe — фраза с запятой целая (1 атом + другая)",
  _n_elems(_pipe_with_comma) == 2
  and _pipe_with_comma.split(" | ") == ["«взнос работодателя, НДФЛ»", "другая"],
  _pipe_with_comma.split(" | "))

# ── SEP: Solr dual-split (', ' / ',' И ' | ') — блокер миграции ───────────────
# Twin = solr_synonyms_build.split_alias_csv / rule_from_alias_csv (паритет SQL).
# SQL: статика маркера regexp ',| [|] ' (класс, без backslash — scs, §3.119).
import solr_synonyms_build as SB  # noqa: E402

_solr_sql = (HERE / "solr_synonyms_compile.sql").read_text(encoding="utf-8")
t("solr compile.sql: dual regexp ',| [|] ' (CSV + pipe, без backslash — scs)",
  "regexp_split_to_array(" in _solr_sql
  and ",| [|] " in _solr_sql
  and "replace(r.aliases, '\\\\,', chr(1))" in _solr_sql,
  "marker missing")

# (a) только ' | ' → правило (до dual было 0)
_pipe_only = SB.rule_from_alias_csv("клиент | покупатель | контрагент")
t("solr twin: (a) pipe-only даёт правило",
  _pipe_only is not None
  and set(p.strip() for p in _pipe_only.split(","))
  == {"клиент", "покупатель", "контрагент"},
  _pipe_only)

# (b) только ', ' → те же правила, что раньше (регресс-ноль)
_csv_only = SB.rule_from_alias_csv("клиент, покупатель, контрагент")
t("solr twin: (b) csv-only как раньше",
  _csv_only == "клиент, покупатель, контрагент",
  _csv_only)
t("solr twin: (b) csv ≡ pipe (один класс)",
  _csv_only is not None and _pipe_only is not None
  and set(p.strip() for p in _csv_only.split(","))
  == set(p.strip() for p in _pipe_only.split(",")),
  (_csv_only, _pipe_only))

# escape CSV не сломан dual'ом
_esc = SB.rule_from_alias_csv("red\\,blue, green")
t("solr twin: (b) escape \\, жив",
  _esc is not None and "red\\,blue" in _esc and "green" in _esc,
  _esc)

# (c) смешанная таблица — правила от обеих строк
_mixed = SB.compile_rules([
    {"aliases": "alpha, beta"},
    {"aliases": "one | two"},
    {"aliases": "solo"},
])
_mixed_lines = set(_mixed.splitlines())
t("solr twin: (c) mixed CSV+pipe → обе правила",
  "alpha, beta" in _mixed_lines and "one, two" in _mixed_lines,
  _mixed)

# (d) одиночное слово без разделителя — как раньше (не правило)
t("solr twin: (d) одиночное без sep → None",
  SB.rule_from_alias_csv("solo") is None)
t("solr twin: (d) одиночное pipe-слово → None",
  SB.rule_from_alias_csv("толькоодно") is None)
t("solr twin: (d) split_alias_csv одиночное",
  SB.split_alias_csv("solo") == ["solo"])

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
