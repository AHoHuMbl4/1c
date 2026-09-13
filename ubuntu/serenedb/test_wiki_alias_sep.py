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

# ── миграционный SQL ─────────────────────────────────────────────────────────
mig = (HERE / "wiki_alias_migrate_sep.sql").read_text(encoding="utf-8")
t("migrate: snap CREATE TABLE … AS SELECT *",
  "CREATE TABLE :alias_snap AS SELECT * FROM :alias_table" in mig
  and "CREATE TABLE :measure_snap AS SELECT * FROM :measure_table" in mig)
t("migrate: replace с условием скобок",
  "replace(aliases, ', ', ' | ')" in mig
  and "regexp_matches(aliases, '\\([^)]*,[^)]*\\)')" in mig
  and "NOT regexp_matches" in mig)
t("migrate: контрольные SELECT по колонкам",
  "entity.aliases replaced" in mig
  and "entity.best_used_for replaced" in mig
  and "entity.not_enough_for replaced" in mig
  and "measure.aliases replaced" in mig
  and "untouched" in mig)
t("migrate: шапка — только по слову владельца",
  "ПО СЛОВУ ВЛАДЕЛЬЦА" in mig
  and "entity_card_build" in mig)

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
t("recover: str_split ' | ' < 3 в критерии",
  "len(str_split(coalesce(t.aliases, ''), ' | ')) < 3" in rec)
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


def _n_pipe(a: str | None) -> int:
    """Как len(str_split(coalesce(a,''), ' | ')): '' → [''], len=1."""
    if a is None:
        a = ""
    if a == "":
        return 1
    return len(a.split(" | "))


def _stub_aliases(a: str | None) -> bool:
    if a is None:
        a = ""
    n = _n_pipe(a)
    all_short = a != "" and all(len(x.strip()) < 4 for x in a.split(" | "))
    return n < 3 or all_short


def should_recover(t_aliases, s_aliases, *, has_snap: bool, seen_fresh: bool) -> bool:
    """Py-эмуляция критерия H4 recover_collision."""
    if not seen_fresh or not has_snap or s_aliases is None:
        return False
    if not _stub_aliases(t_aliases):
        return False
    sn, tn = _n_pipe(s_aliases), _n_pipe(t_aliases)
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

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
