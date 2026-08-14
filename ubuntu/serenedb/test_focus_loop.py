#!/usr/bin/env python3
"""Оффлайн-проба КАНАЛА ВЫБОРА СУЩНОСТИ: БЕЗ базы, БЕЗ сети, БЕЗ вызовов модели.

🔴 ЗАЧЕМ. Живой прогон okna 13.08: человек 23 раза уточнял «продажи за неделю» и не
получил числа ни разу. Причина не в модели и не во фронте — в устройстве канала:

  1. `search_tables.label` строится срезанием типа записи (`corpus_build.sql`:
     `Document_` и `AccumulationRegister_` уходят), поэтому документ и регистр с одним
     именем получают ОДНУ метку. В okna таких пар 6, и одна из них — «Реализация ТМЦ»,
     то есть главное слово бизнеса;
  2. уточнение отдаёт боту только метку (`mcp_ask`, решение 03.08: внутренние имена
     таблиц клиенту не уходят), значит оба варианта выглядят одинаково: `focus=Реализация ТМЦ`;
  3. что бы человек ни выбрал, `resolve_focus` находит по метке ДВЕ таблицы, честно
     отказывается угадывать (п. 12) и отбрасывает выбор;
  4. сервис идёт обычным путём -> снова уточнение. Круг замкнут ПО ПОСТРОЕНИЮ: любой
     ответ человека возвращает ту же строку и приводит к тому же уточнению.

Дефект общий, а не про okna: пары «документ + одноимённый регистр» есть в любой
конфигурации 1С, поэтому проба берёт ВЫДУМАННЫЕ имена — она не знает ни одной
настоящей базы и годится на любой.

Что проверяется (в порядке цепочки):
  * метка-дубль вообще опознаётся как неоднозначная;
  * варианты уточнения РАЗЛИЧИМЫ на вид — иначе человек выбирает вслепую;
  * значения `focus` у разных вариантов РАЗНЫЕ — иначе выбор не несёт информации;
  * выбор сводится обратно ровно к одной таблице — и именно к той, которую выбрали;
  * внутренние имена таблиц в текст для бота не попадают (защита решения 03.08).

Запуск тем же питоном, которым исполняется мост (в системном нет `mcp`):
    /opt/openclaw-mcp/venv/bin/python ubuntu/serenedb/test_focus_loop.py
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "openclaw"))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("ASK_URL", "http://127.0.0.1:1/ask")

import serene_ask as A  # noqa: E402
import mcp_ask as M  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


# --- выдуманная база: документ и регистр с ОДНОЙ меткой ---------------------------
DOC = "document_отгрузкапробная"
REG = "accumulationregister_отгрузкапробная"
LABEL = "Отгрузка Пробная"
UNIQ = "catalog_складыпробные"
UNIQ_LABEL = "Склады Пробные"

_ROWS = {DOC: LABEL, REG: LABEL, UNIQ: UNIQ_LABEL}


def _fake_psql(sql, *a, **kw):
    """Отвечает как `search_tables` выдуманной базы — на три запроса `resolve_focus`:
    точное имя источника, сведение по метке и подбор кандидатов для подписи с видом."""
    s = " ".join(sql.split())
    # Кандидаты по началу строки: движок вернёт те, чья метка — префикс искомого;
    # надмножество допустимо, точное сравнение делает сам `resolve_focus`.
    if "HAVING" in s:
        # Неоднозначные метки базы: те, что носит больше одного источника.
        cnt = {}
        for v in _ROWS.values():
            key = "".join(v.lower().split())
            cnt[key] = cnt.get(key, 0) + 1
        return [[k] for k, n in cnt.items() if n > 1]
    if "LIKE" in s and "label" in s:
        return [[k, v] for k, v in _ROWS.items()]
    m = re.search(r"src_table = '([^']*)'", s)
    if m and "label" not in s:
        name = m.group(1)
        return [[name]] if name in _ROWS else []
    m = re.search(r"lower\(replace\('([^']*)'", s) or re.search(r"replace\('([^']*)'", s)
    if m:
        want = m.group(1).replace(" ", "").lower()
        hit = [[k] for k, v in _ROWS.items() if v.replace(" ", "").lower() == want]
        return hit[:2]
    return []


A.psql = _fake_psql

# --- 1. неоднозначность вообще опознаётся ----------------------------------------
diag = {}
t("метка-дубль опознана как неоднозначная (выбор не навязан)",
  A.resolve_focus(LABEL, diag) is None and diag.get("focus_ambiguous") == LABEL, diag)

diag = {}
t("уникальная метка сводится к своей таблице",
  A.resolve_focus(UNIQ_LABEL, diag) == UNIQ, diag)

diag = {}
t("внутреннее имя сводится к себе же (прежний путь цел)",
  A.resolve_focus(DOC, diag) == DOC, diag)

# --- 2. что мост отдаёт боту ------------------------------------------------------
# 🔴 Варианты строит НАСТОЯЩИЙ код сервиса (`mk_opts`), а не выдуманный список: дефект
# живёт в цепочке «сервис -> мост -> focus -> сведение», и проба, подсовывающая мосту
# готовые подписи, проверяла бы только мост и осталась бы красной при любой починке.
OPTS = A.mk_opts([DOC, REG], {DOC: LABEL, REG: LABEL},
                 marks={}, by={DOC: 12, REG: 3400})
M._ask = lambda *a, **kw: {"kind": "clarify", "text": "Что именно посчитать?",
                           "options": OPTS}
out = M.ask_1c("сколько отгружено", "", "", "")

picks = re.findall(r"focus=([^\n|]+)", out)
picks = [p.strip() for p in picks if p.strip()]

t("оба варианта показаны боту", len(picks) == 2, picks)
t("🔴 ГЛАВНОЕ: значения focus у вариантов РАЗНЫЕ (иначе выбор не несёт информации)",
  len(set(picks)) == 2, picks)
t("варианты различимы на вид (подписи не совпадают)",
  len(set(re.findall(r"^- ([^|\n]+)", out, re.M))) == 2,
  re.findall(r"^- ([^|\n]+)", out, re.M))
t("внутренние имена таблиц в текст для бота не попали (решение 03.08)",
  DOC not in out and REG not in out,
  [x for x in (DOC, REG) if x in out])

# --- 3. сквозная проверка: выбор возвращается и сводится к ОДНОЙ таблице ----------
if len(picks) == 2:
    got = []
    for p in picks:
        d = {}
        got.append(A.resolve_focus(p, d))
    t("🔴 ПЕТЛЯ РАЗОРВАНА: каждый выбор сводится ровно к одной таблице",
      all(g in (DOC, REG) for g in got), got)
    t("выбор ведёт к РАЗНЫМ таблицам (а не обе в одну)",
      len(set(got)) == 2 and set(got) == {DOC, REG}, got)
else:
    t("🔴 ПЕТЛЯ РАЗОРВАНА: каждый выбор сводится ровно к одной таблице", False, picks)
    t("выбор ведёт к РАЗНЫМ таблицам (а не обе в одну)", False, picks)

# --- 4. одноимённая сущность ЕСТЬ В БАЗЕ, но в списке её нет -----------------------
# 🔴 Живой замер okna 13.08 вскрыл этот пробел: в вариантах стояла одна «Реализация
# ТМЦ», подпись выглядела однозначной, человек её выбирал — а сведение идёт по базе,
# где меток две, и выбор снова отбрасывался. Проба, знающая только список, этого не
# видит, поэтому случай заведён отдельно.
A._AMBIG_CACHE.update({"at": 0.0, "set": frozenset()})
solo = A.mk_opts([DOC], {DOC: LABEL}, marks={}, by={DOC: 12})
t("одноимённый в базе -> вид дописан даже когда в списке он один",
  solo[0]["label"] != LABEL and "(" in solo[0]["label"], solo[0]["label"])
d = {}
t("такой выбор сводится к своей таблице",
  A.resolve_focus(solo[0]["label"], d) == DOC, (solo[0]["label"], d))
uniq_solo = A.mk_opts([UNIQ], {UNIQ: UNIQ_LABEL}, marks={}, by={UNIQ: 5})
t("уникальной метке вид НЕ дописывается (привычный вид цел)",
  uniq_solo[0]["label"] == UNIQ_LABEL, uniq_solo[0]["label"])

# --- 5. пояснение видно человеку, но в focus не входит -----------------------------
OPTS2 = [dict(o, hint="отгрузочные документы; данные по 2026-12-31" if o["src"] == DOC
              else "итоги по регистру; данные по 2026-08-28") for o in OPTS]
M._ask = lambda *a, **kw: {"kind": "clarify", "text": "Что посчитать?", "options": OPTS2}
out2 = M.ask_1c("сколько отгружено", "", "", "")
picks2 = [p.strip() for p in re.findall(r"focus=([^\n|]+)", out2) if p.strip()]
t("пояснение показано человеку", "отгрузочные документы" in out2 and "данные по" in out2)
t("пояснение НЕ попало в focus (значение выбора прежнее)",
  picks2 == picks, (picks2, picks))
if picks2:
    d2 = {}
    t("выбор с пояснением всё так же сводится к таблице",
      A.resolve_focus(picks2[0], d2) in (DOC, REG), (picks2[0], d2))

# --- 6. величина: подпись и значение выбора — одна человеческая строка ---------
MEAS_OPTS = [
    {"src": DOC, "measure": "ИтогПробный", "label": "оборот",
     "entity_label": "Отгрузка Пробная (документ)", "distinct_by": ""},
    {"src": DOC, "measure": "СуммаКартойПробная", "label": "оплата картой",
     "entity_label": "Отгрузка Пробная (документ)", "distinct_by": ""},
]
M._ask = lambda *a, **kw: {"kind": "clarify", "text": "НДС или карта?",
                           "options": MEAS_OPTS}
out_m = M.ask_1c("сумма продаж", "", "", "")
meas_picks = [p.strip() for p in re.findall(r"measure=([^\n|]+)", out_m) if p.strip()]
t("величина: оба варианта показаны боту", len(meas_picks) == 2, meas_picks)
t("величина: measure= совпадает с подписью (как focus у сущности)",
  set(meas_picks) == {"оборот", "оплата картой"}, meas_picks)
t("величина: внутренние имена полей боту не ушли",
  "ИтогПробный" not in out_m and "СуммаКартойПробная" not in out_m, out_m)
t("величина: выбор «оборот» сводится к полю",
  A.resolve_measure("оборот", ["ИтогПробный", "СуммаКартойПробная"],
                    {"ИтогПробный": "оборот, сумма продаж",
                     "СуммаКартойПробная": "оплата картой"}) == "ИтогПробный")

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
