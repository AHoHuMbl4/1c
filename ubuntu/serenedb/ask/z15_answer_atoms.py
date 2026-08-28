"""Zone 15: Атомы ответа (answer-atoms)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def stop2_active(focus=None, measure_pick=None, no_arbiter=False, trusted=None):
    """Стоп 2: соперники в круг, пока неоднозначность не доказана билетом.

    Сырой focus/measure — подсказка отбора, не выбор человека (аудит §10, план §6).
    Гасит стоп 2 только decision_id (trusted) или аварийный ASK_RAW_FOCUS_TRUST=1.
    """
    if no_arbiter:
        return False
    if guards_skip_for_choice(focus, measure_pick, trusted):
        return False
    return True


def determined_answer_rivals(picked, par, writer_pair=None, alias_leader=None,
                            known_src=None):
    """Соперники стопа 2: уже определённые, без бюджета шага 3.

    Семья (шапка/ТЧ), writer_pair, лидер словаря другой семьи. Не «следующий по
    RRF» и не порог веса. known_src — узкий набор уже известных таблиц (кандидаты,
    alias_top), из которого берётся не больше одного соседа по семье.
    """
    if not picked:
        return []

    def family(t):
        return (par or {}).get(t) or t

    fam0 = family(picked)
    out, seen = [], {picked}

    def add(t):
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    if writer_pair:
        add(writer_pair)
    parent = (par or {}).get(picked) or ""
    if parent and parent != picked:
        add(parent)
    for t in (known_src or []):
        if t == picked:
            continue
        if family(t) == fam0:
            add(t)
            break
    if alias_leader and family(alias_leader) != fam0:
        add(alias_leader)
    return out




def answer_money(want, compute, measure):
    """Нужны ли в этом ответе денежные числа.

    Поле, которое модель назвала, само по себе денег не открывает: на «сколько»
    (`want`/`compute` = count) их нет, даже если словарь свёл «всего» к колонке.
    `want=list` сюда не входит: пустой want в разборе становится list, и иначе
    деньги выключатся на вопросах про сумму, где разбор не сказал sum.
    """
    counting = (compute or "") == "count" or (want or "") == "count"
    return bool(measure) and not counting


def answer_slot_mode(want, compute, form=None, grain=None):
    """Какие числовые слоты открыты форме ответа (стоп 1).

    Режим сужает compose и белый список гейта до слотов одной формы: иначе
    законные числа с разной ролью оказываются в одном допуске.

      count — счёт (и служебные даты/папки); деньги / лидер / числа строк закрыты.
      sum   — итог множества; лидер, цифры строк и счёт записей закрыты
              (счёт после гейта может дописать код — `ensure_count_named`).
      rank  — группы по индексам; итог множества — отдельное место; `{leader}` нет;
              счёт записей не свободен (как на sum); при sum≠лидер оба обязательны.
      list  — цитаты строк (прежний белый список строк).
    """
    counting = (compute or "") == "count" or (want or "") == "count"
    if counting:
        return "count"
    form = (form or "").lower()
    grain = (grain or "").lower()
    if form == "compare":
        return "compare" if ASK_ATOM_TERMINAL else "rank"
    if form == "rank":
        return "rank"
    if (want or "") == "sum" or (compute or "") in ("sum", "max", "min", "avg"):
        return "sum"
    if grain == "group":
        return "rank"
    return "list"


def compose_slot_values(agg, measure=None, folders=0, money=None, slot_mode=None):
    """Числа, которые compose подставит в плейсхолдеры этого ответа.

    Не `amount=` примеров строк и не покрытие (`in_1c` / `missing`): они не итог.
    Вызов из answer передаёт `money=` и `slot_mode=` явно (тот же флаг, что compose
    и гейт). `money=None` — как `bool(measure)`, только для проб без оси вопроса.
    `slot_mode=None` — вывести из grain (group → rank, иначе list) для старых проб.
    """
    if money is None:
        money = bool(measure)
    if slot_mode is None:
        slot_mode = "rank" if (agg or {}).get("grain") == "group" else "list"
    slots = {}
    if not agg:
        return slots
    # Стоп 1: count — слот модели только count/list (не sum/rank).
    if agg.get("count") is not None and slot_mode in ("count", "list"):
        slots["count"] = agg["count"]
    if slot_mode == "count":
        pass
    elif slot_mode == "compare" and money:
        if agg.get("sum") is not None:
            slots["sum"] = agg["sum"]
    elif slot_mode == "sum" and money:
        ca = agg.get("count_amount")
        if ca is not None and ca != agg.get("count"):
            slots["count_amount"] = ca
        if agg.get("count") == 0 and agg.get("outside_period"):
            slots["count"] = 0
        keys = ("sum",) if agg.get("grain") == "group" else ("sum", "max", "min", "avg")
        for k in keys:
            if agg.get(k) is not None:
                slots[k] = agg[k]
    elif slot_mode == "rank":
        _ng = agg.get("n_groups")
        _shown_g = len(agg.get("groups") or [])
        if (money and agg.get("sum") is not None
                and _ng is not None and _ng > _shown_g):
            slots["sum"] = agg["sum"]
        for i, g in enumerate((agg.get("groups") or [])[:ROWS_TO_MODEL]):
            if g.get("value") is not None:
                slots["g%d" % i] = g["value"]
    elif money:
        ca = agg.get("count_amount")
        if ca is not None and ca != agg.get("count"):
            slots["count_amount"] = ca
        keys = ("sum",) if agg.get("grain") == "group" else ("sum", "max", "min", "avg")
        for k in keys:
            if agg.get(k) is not None:
                slots[k] = agg[k]
        if agg.get("grain") == "group":
            lead = _group_leader(agg)
            if lead is not None:
                slots["leader"] = lead
    if (slot_mode in ("rank", "list") and agg.get("grain") == "group"
            and agg.get("n_groups") is not None):
        ng, shown = agg["n_groups"], len(agg.get("groups") or [])
        if ng > shown:
            slots["n_groups"] = ng
    dmin = agg.get("date_min")
    if dmin:
        slots["date_min"] = dmin
        if agg.get("date_max"):
            slots["date_max"] = agg["date_max"]
    nfold = folders if folders else (agg.get("folders") or 0)
    if nfold:
        slots["folders"] = nfold
    if agg.get("undated"):
        slots["undated"] = agg["undated"]
    if agg.get("outside_period"):
        slots["outside_period"] = agg["outside_period"]
    return slots


# ═══════════════ AnswerAtom + детерминированный renderer (план §5, аудит §17) ═══════════════
# Одно кодовое место собирает атом; пара «подпись + число + единица + оговорка» —
# одной операцией `render_atom_pair`. Модель не получает значений и не пишет подписи:
# при нескольких парах в задании только `{pair:p0}`… — код подставляет пару целиком.
# Перепутанные подписи фразу не собирают: API смешать label одного атома с value другого отсутствует.
UNIT_UNKNOWN = "unknown"                       # явная «единица неизвестна» (машинный маркер)
PROOF_COMPUTED = "computed"
PROOF_NA = "not_applicable"
PROOF_UNCOUNTED = "not_computed"
_ATOM_OPS = frozenset({"count", "sum", "max", "min", "avg", "rank", "compare", "list"})


def atom_operation(want=None, compute=None, form=None, grain=None, slot_mode=None):
    """Операция атома из уже принятых решений формы (не из прозы модели)."""
    sm = slot_mode or answer_slot_mode(want, compute, form, grain)
    if sm == "count":
        return "count"
    if sm == "compare" or (form or "").lower() == "compare":
        return "compare"
    if sm == "rank":
        return "rank"
    if sm == "sum":
        c = (compute or "").lower()
        if c in ("max", "min", "avg"):
            return c
        return "sum"
    return "list"


def _atom_exact_value(agg, operation, money):
    """Точное значение базы для операции; без float-схлопывания сверх round в _fmt."""
    if not agg:
        return None
    if operation == "count":
        return agg.get("count")
    if operation in ("max", "min", "avg"):
        return agg.get(operation)
    if operation in ("sum", "rank", "compare"):
        if (agg or {}).get("grain") == "group":
            lead = _group_leader(agg)
            if lead is not None:
                return lead
        if money and agg.get("sum") is not None:
            return agg.get("sum")
        return agg.get("count")
    # list
    if money and agg.get("sum") is not None:
        return agg.get("sum")
    return agg.get("count")


def build_answer_atom(operation=None, exact_value=None, display_value=None,
                      measure_id=None, measure_label=None,
                      unit_or_currency=None, period=None, filters=None,
                      grain=None, axis=None, form=None,
                      completeness=None, freshness=None, excluded=None,
                      proof_status=None, interpretation_id=None, src=None):
    """Типизированный AnswerAtom (аудит §17). Одно место сборки.

    `measure_label` — проверенная человеческая подпись из данных
    (`search_measure_alias` / `search_tables`), не проза модели.
    `unit_or_currency` пуст → явный маркер `unknown`.
    `src` — доказательство/пересчёт; в клиентское сравнение A не входит.
    """
    op = (operation or "count").lower()
    if op not in _ATOM_OPS:
        op = "count"
    status = proof_status or (
        PROOF_COMPUTED if exact_value is not None else PROOF_UNCOUNTED)
    unit = unit_or_currency if unit_or_currency is not None else ""
    disp = display_value
    if disp is None and exact_value is not None:
        disp = _fmt(exact_value)
    atom = {
        "operation": op,
        "exact_value": exact_value,
        "display_value": disp,
        "measure_id": (measure_id or None),
        "measure_label": (measure_label or "").strip() or None,
        "unit_or_currency": unit,
        "period": period or None,
        "filters": filters or None,
        "grain": grain or None,
        "axis": axis or None,
        "form": form or None,
        "completeness": completeness or None,
        "freshness": freshness or None,
        "excluded": excluded or None,
        "proof_status": status,
    }
    if interpretation_id:
        atom["interpretation_id"] = interpretation_id
    if src:
        atom["src"] = src
    return atom


def atom_from_agg(agg, operation=None, measure_id=None, measure_label=None,
                  money=True, period=None, period_origin="", filters=None,
                  grain=None, axis=None, form=None, completeness=None,
                  freshness=None, excluded=None, proof_status=None,
                  interpretation_id=None, src=None, folders=0,
                  unit_or_currency=None, period2=None, compare_form=None):
    """Собрать атом из уже посчитанного `agg` и меток из данных."""
    op = (operation or "count").lower()
    if op not in _ATOM_OPS:
        op = "count"
    exact = _atom_exact_value(agg, op, money)
    excl = dict(excluded or {}) if excluded else {}
    nfold = folders if folders else ((agg or {}).get("folders") or 0)
    if nfold and "folders" not in excl:
        excl["folders"] = nfold
    if (agg or {}).get("undated") and "undated" not in excl:
        excl["undated"] = agg["undated"]
    if (agg or {}).get("outside_period") and "outside_period" not in excl:
        excl["outside_period"] = agg["outside_period"]
    per = None
    if period and (period.get("from") or period.get("to")):
        per = {"from": period.get("from") or None,
               "to": period.get("to") or None,
               "origin": period_origin or None}
    elif (agg or {}).get("date_min") or (agg or {}).get("date_max"):
        per = {"from": (agg or {}).get("date_min") or None,
               "to": (agg or {}).get("date_max") or None,
               "origin": period_origin or None}
    status = proof_status
    if status is None:
        status = PROOF_COMPUTED if exact is not None else PROOF_UNCOUNTED
    atom = build_answer_atom(
        operation=op, exact_value=exact, measure_id=measure_id,
        measure_label=measure_label,
        unit_or_currency=(unit_or_currency if unit_or_currency is not None
                          else _unit_for_measure(measure_id, money, src=src)),
        period=per, filters=filters,
        grain=grain or (agg or {}).get("grain"),
        axis=axis, form=form or (agg or {}).get("form"),
        completeness=completeness, freshness=freshness,
        excluded=excl or None, proof_status=status,
        interpretation_id=interpretation_id, src=src)
    # P5: pair of windows + base/other for compare render (code, not prompt).
    _form = (form or (agg or {}).get("form") or "").lower()
    if _form == "compare" or op == "compare":
        if (agg or {}).get("compare_base") is not None:
            atom["compare_base"] = agg["compare_base"]
        if (agg or {}).get("compare_other") is not None:
            atom["compare_other"] = agg["compare_other"]
        p2 = period2 if isinstance(period2, dict) else None
        if p2 and (p2.get("from") or p2.get("to")):
            atom["period2"] = {"from": p2.get("from") or None,
                               "to": p2.get("to") or None}
        if compare_form:
            atom["compare_form"] = compare_form
    return atom


def _period_window_human(period):
    """ISO from..to for compare pair line (machine bounds, not model prose)."""
    p = period if isinstance(period, dict) else {}
    fr = str(p.get("from") or "").strip()
    to = str(p.get("to") or "").strip()
    if fr and to:
        return "%s..%s" % (fr, to)
    return fr or to or "?"


def render_atom_pair(atom):
    """Пара «подпись + число + единица + оговорка полноты» — ОДНОЙ операцией.

    Нет API «подпись отдельно + число отдельно»: смешать label чужого атома с value
    своего нет: такого API нет. Непосчитанный атом пары не даёт (None) — фраза не собирается.
    P5 compare: «Всего: {diff} · {p1} ({base}) против {p2} ({other})» + mtd/wtd note.
    """
    if not isinstance(atom, dict):
        return None
    if atom.get("proof_status") == PROOF_UNCOUNTED:
        return None
    if atom.get("exact_value") is None and atom.get("display_value") is None:
        return None
    label = (atom.get("measure_label") or "").strip()
    value = atom.get("display_value")
    if value is None:
        value = _fmt(atom.get("exact_value"))
    unit = atom.get("unit_or_currency") or ""
    parts = []
    _is_cmp = ((atom.get("form") or "").lower() == "compare"
               or (atom.get("operation") or "").lower() == "compare")
    _base, _other = atom.get("compare_base"), atom.get("compare_other")
    if _is_cmp and _base is not None and _other is not None:
        _lab = label or "Всего"
        parts.append("%s: %s · %s (%s) против %s (%s)" % (
            _lab, value,
            _period_window_human(atom.get("period")), _fmt(_base),
            _period_window_human(atom.get("period2")), _fmt(_other)))
        _cf = (atom.get("compare_form") or "").lower()
        if _cf == "mtd":
            parts.append("· текущий период неполный, прошлый — полный месяц")
        elif _cf == "wtd":
            parts.append("· текущий период неполный, прошлый — полная неделя")
    elif (atom.get("form") or "").lower() == "distinct_axis":
        ax = (atom.get("axis") or "").strip()
        if ax:
            parts.append("%s · %s" % (value, ax))
        else:
            parts.append(str(value))
    elif label:
        parts.append("%s: %s" % (label, value))
    else:
        parts.append(str(value))
    if unit and unit != UNIT_UNKNOWN:
        parts.append(str(unit))
    excl = atom.get("excluded") or {}
    if isinstance(excl, dict) and excl:
        notes = []
        if excl.get("folders"):
            notes.append("folders=%s" % _fmt(excl["folders"]))
        if excl.get("undated"):
            notes.append("undated=%s" % _fmt(excl["undated"]))
        if excl.get("outside_period"):
            notes.append("outside_period=%s" % _fmt(excl["outside_period"]))
        if notes:
            parts.append("· " + ", ".join(notes))
    comp = atom.get("completeness")
    if isinstance(comp, dict) and comp.get("missing"):
        parts.append("· missing=%s" % _fmt(comp["missing"]))
    return " ".join(parts)


def fill_atom_pairs(text, pairs):
    """Подставить `{pair:p0}`… целыми парами. Одиночного числа/подписи здесь нет.

    Нераспознанный индекс или непосчитанный атом — отказ места (как у `_fill_figures`):
    заготовка человеку не уходит.
    """
    if not text:
        return text, []
    bad = []
    catalog = list(pairs or [])

    def one(mt):
        role, name = mt.group(1).lower(), (mt.group(2) or "").strip()
        if role != "pair":
            return mt.group(0)
        idx = None
        if name.lower().startswith("p") and name[1:].isdigit():
            idx = int(name[1:])
        elif name.isdigit():
            idx = int(name)
        if idx is None or idx < 0 or idx >= len(catalog):
            bad.append(mt.group(0))
            return mt.group(0)
        rendered = render_atom_pair(catalog[idx])
        if not rendered:
            bad.append(mt.group(0))
            return mt.group(0)
        return rendered

    return SLOT.sub(one, text), bad



register_zone('ask.z15_answer_atoms', globals())
