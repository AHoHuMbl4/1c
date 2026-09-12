"""Zone 10: Ранг (rank)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

def count_question_skips_axis(intent, measure, grain_dec, plan=None):
    """Счёт записей сущности без оси — axis-clarify здесь лишний (B8-02 / Z2 §3.3).

    «Сколько контрагентов» — row count по справочнику; оси Parent/Город — не
    альтернативные прочтения вопроса, а шум структуры. Plain count/list/пустой
    want без явного разреза — не меню осей (волна W).
    """
    if (grain_dec or {}).get("clarify") != "axis":
        return False
    want = (intent or {}).get("want") or ""
    if want not in ("", "count", "list"):
        return False
    # list сам по себе — счёт/перечень без оси (исторический skip);
    # явный разрез (amount / max|min) — не skip. count/"" — ещё not breakdown.
    if want != "list" and question_wants_breakdown(intent, plan):
        return False
    amt = (intent or {}).get("amount") or {}
    if amt.get("op") or amt.get("value") is not None:
        return False
    if (plan or {}).get("compute") in ("max", "min"):
        return False
    if measure:
        return False
    return True


def question_wants_breakdown(intent, plan=None):
    """Ось уместна только при явном разрезе (топ/список/max/min), не для итога."""
    intent = intent or {}
    plan = plan or {}
    want = intent.get("want") or ""
    amt = intent.get("amount") or {}
    if want == "list":
        return True
    if not amt.get("op") and amt.get("value") is not None:
        return True
    if (plan.get("compute") or "") in ("max", "min"):
        return True
    return False


def total_question_skips_axis(intent, measure, grain_dec, plan=None, question="",
                              trusted=None, resolved=None):
    """Итог «всего»/sum без разреза — axis-clarify не задаётся (план владельца шаг 5)."""
    if rank_intent_from(intent, plan, question):
        return False
    if (grain_dec or {}).get("clarify") != "axis":
        return False
    if question_wants_breakdown(intent, plan):
        return False
    q = " ".join(str(question or "").lower().split())
    if any(w in q for w in ("всего", "итого", "итог ", " overall", " in total")):
        return True
    want = (intent or {}).get("want") or ""
    compute = (plan or {}).get("compute") or ""
    if want == "sum" or compute == "sum":
        return True
    if measure_already_proven(trusted, resolved, measure):
        return True
    return False


def rank_question_text(question):
    """Фразы рейтинга в тексте вопроса — не только want=list."""
    q = " ".join(str(question or "").lower().split())
    if not q:
        return False
    markers = (
        "больше всего", "больше всех", "лучше всего", "лучше всех",
        "наибольш", "наименьш",
        "лучших", "лучший", "лучшие", "лучшего", "лучшая",
        "какого товар", "какой товар", "какая номенклатур",
        "top ", " most ", "maximum", "leader", "лидер", "рейтинг",
        "топ-", "топ ",
    )
    if any(m in q for m in markers):
        return True
    if "лучше" in q and any(w in q for w in (
            "продав", "продаж", "продал", "sold", "sales", "sell")):
        return True
    return False


def rank_intent_from(intent, plan=None, question=""):
    """Рейтинг/топ: want=list, amount без порога, max/min или фраза вопроса."""
    intent = intent or {}
    plan = plan or {}
    amt = intent.get("amount") or {}
    if (intent.get("want") or "") == "list":
        return True
    if not amt.get("op") and amt.get("value") is not None:
        return True
    if (plan.get("compute") or "") in ("max", "min"):
        return True
    if rank_question_text(question):
        return True
    return False


# Классификация оси rank: модели — только имена осей из данных (п.19), без строк.
AXIS_PICK_SYS = """You map a user's question to a grouping axis.

You get the question and a numbered list of axis names available on the chosen
record type. Labels come from the database; they are dimensions for GROUP BY.
Reply with one JSON object and nothing else:
  {"axes": [numbers]}
Numbers are 1-based indices from the list, best first.
One number when one axis fits the question clearly.
Several numbers when different axes would answer different readings of the same
question (at most three).
Empty list when no axis fits.
Reply with indices only; naming totals or inventing axis names is outside this step."""


def rank_axis_label_rows(axes):
    """[(col, label)] для осей: метка target_src из search_tables, иначе имя колонки."""
    axes = [a for a in (axes or []) if a.get("col")]
    if not axes:
        return []
    srcs = [a.get("target_src") for a in axes if a.get("target_src")]
    labs = {}
    if srcs:
        try:
            for r in psql("SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                          % (TABLES, ", ".join(lit(s) for s in srcs))) or []:
                if r and r[0]:
                    labs[r[0]] = (r[1] or r[0]).strip()
        except RuntimeError:
            labs = {}
    out = []
    for a in axes:
        col = a["col"]
        ts = (a.get("target_src") or "").strip()
        lab = labs.get(ts) or col
        if ts and lab != col:
            lab = "%s (%s)" % (lab, col)
        out.append((col, lab))
    return out


def rank_axes_rerank(query, axes):
    """Полный порядок осей штатным rerank по меткам (вопрос → ось, не kind→источник)."""
    query = (query or "").strip()
    rows = rank_axis_label_rows(axes)
    if not query or not rows:
        return []
    docs = [lab for _c, lab in rows]
    cols = [c for c, _lab in rows]
    order = rerank(query, docs)
    if not order:
        return []
    return [cols[i] for i in order if 0 <= i < len(cols)]


def rank_axis_pick(question, kind, axes):
    """Ось rank: модель видит только имена/метки осей источника (п.19).

    Возвращает упорядоченный список col (лучший первый). Пусто — сигнала нет,
    вызывающий идёт на rerank/hits. Сбой сети — пусто, не отказ ответа.
    """
    axes = [a for a in (axes or []) if a.get("col")]
    if not axes:
        return []
    if len(axes) == 1:
        return [axes[0]["col"]]
    rows = rank_axis_label_rows(axes)
    if len(rows) < 2:
        return [rows[0][0]] if rows else []
    listing = "\n".join("%d. %s" % (i + 1, lab) for i, (_c, lab) in enumerate(rows))
    ask_text = (question or "").strip()
    if kind and kind.strip():
        ask_text = ("%s (%s)" % (ask_text, kind.strip())).strip() if ask_text else kind.strip()
    if not ask_text:
        return []
    try:
        raw = ds_chat(
            [{"role": "system", "content": AXIS_PICK_SYS},
             {"role": "user",
              "content": "%s\n\nAxes:\n%s" % (ask_text, listing)}],
            max_tokens=80)
    except Exception as e:                     # noqa: BLE001 — сеть/квота
        sys.stderr.write("ask: axis-pick without model (%s)\n" % str(e)[:80])
        return []
    txt = (raw or "").strip()
    got = []
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        if isinstance(j, dict):
            got = [int(x) for x in (j.get("axes") or []) if str(x).strip().isdigit()]
    except (ValueError, KeyError, TypeError):
        got = [int(x) for x in re.findall(r"\d+", txt)]
    cols = [c for c, _lab in rows]
    picked = []
    for i in got:
        if i == 0:
            continue
        if 1 <= i <= len(cols) and cols[i - 1] not in picked:
            picked.append(cols[i - 1])
        if len(picked) >= 3:
            break
    return picked


def rank_axis_resolve(src, axes, intent, question, plan=None):
    """Ось GROUP BY для rank: классификация вопроса по перечню осей источника.

    Порядок сигнала (без предпочтения имён колонок и без словарей языка):
      1) модель по короткому списку имён/меток осей (rank_axis_pick);
      2) stem/meaning вопроса ∩ target_src (kind_axis_hits на question);
      3) штатный rerank вопроса по меткам осей;
      4) kind-hits только если вопроса нет (kind = род источника, не ось).
    Две+ правдоподобные — лидер + люк (§2), не молчаливый выбор первой.
    Возвращает (col, alts). Нет оси — (None, pool).
    """
    axes = list(axes or [])
    if not axes and src:
        try:
            axes = refcols_of(src)
        except RuntimeError:
            axes = []
    cols = [a.get("col") for a in axes if a.get("col")]
    if not cols:
        return None, []
    if len(cols) == 1:
        return cols[0], []
    kind = ((intent or {}).get("kind") or "").strip()
    q = (question or "").strip()
    picked = []
    if q or kind:
        picked = rank_axis_pick(q, kind, axes)
    if not picked and q:
        picked = list(kind_axis_hits(axes, q) or [])
    if not picked and q:
        ordered = rank_axes_rerank(q, axes)
        if ordered:
            # В3: ≥2 правдоподобные → меню (не ordered[0] / не лидер+люк).
            picked = [c for c in ordered if c in cols]
            if len(cols) == 2:
                for c in cols:
                    if c not in picked:
                        picked.append(c)
            elif len(cols) > 2 and len(picked) < 2:
                picked = list(cols)
    if not picked and kind and not q:
        picked = list(kind_axis_hits(axes, kind) or [])
        if not picked:
            picked = list(kind_axis_rerank(axes, kind) or [])
    if not picked and kind and q:
        # Kind без вопроса ошибочно брал одну ось (Договор на «продажи»).
        # При живом вопросе kind дополняет rerank; ≥2 → меню (В3).
        ordered = rank_axes_rerank(q, axes)
        kh = list(kind_axis_hits(axes, kind) or [])
        if ordered:
            picked = [c for c in ordered if c in cols]
            for c in kh:
                if c not in picked:
                    picked.append(c)
        elif kh:
            picked = kh
    if not picked:
        return None, list(cols)
    if len(picked) == 1:
        return picked[0], []
    # В3: ≥2 оси — меню (axis-clarify), не auto col + люк.
    return None, picked


register_zone('ask.z10_rank', globals())
