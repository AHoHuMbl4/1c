"""Zone 21: Wiki hybrid entity choice (PLAN_WIKI_CHOICE §Б3)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

ASK_WIKI_CHOICE = os.environ.get("ASK_WIKI_CHOICE", "0") == "1"
WIKI_KNN_N = int(os.environ.get("WIKI_KNN_N", "15"))
WIKI_PICK_N = int(os.environ.get("WIKI_PICK_N", "5"))
WIKI_SEP_GAP = float(os.environ.get("WIKI_SEP_GAP", "0.04"))
WIKI_EMBED_MAXLEN = int(os.environ.get("WIKI_EMBED_MAXLEN", "20000"))

_HYBRID_SQL = None


def _wiki_hybrid_sql():
    global _HYBRID_SQL
    if _HYBRID_SQL is None:
        _HYBRID_SQL = (ASK_ROOT / "wiki_card_hybrid.sql").read_text(encoding="utf-8")
    return _HYBRID_SQL

WIKI_PICK_SYS = """Map the user's question to one numbered entity card, or 0.
Each card shows: name, description, platform kind, axes, measures (same fields for all).
Reply with one JSON object only:
  {"choice": <1-based card index or 0>, "separable": <true|false>}"""


def wiki_aggregate_want(intent, question=""):
    """count/sum/rank по сущности — tabpart не самостоятельный кандидат."""
    intent = intent or {}
    want = (intent or {}).get("want") or ""
    wl = str(want).strip().lower()
    if wl in ("count", "sum", "max", "min", "avg"):
        return True
    if rank_intent_from(intent, question=question):
        return True
    if wl in ("", "list"):
        amt = (intent or {}).get("amount") or {}
        if not amt.get("op") and amt.get("value") is None:
            return wl != "list"
    return False


def wiki_action_class(intent):
    ac = (intent or {}).get("action_class") or "none"
    ac = str(ac).strip().lower()
    return ac if ac in ("event", "object") else "none"


def wiki_action_axis(intent):
    return _intent_text((intent or {}).get("action_axis")) or ""


def wiki_platform_kind(src_table, parent=""):
    """Вид платформы 1С; tabpart — по parent из search_tables."""
    if parent:
        owner = kind_word(parent) or "документ"
        return "табличная часть (%s)" % owner
    return kind_word(src_table) or str(src_table or "").split("_", 1)[0]


def wiki_axis_phrase(intent):
    """Оси разбора (kind + action_axis) — структурный вход SQL."""
    if "intent_axis_words" in globals():
        words = intent_axis_words(intent)
        if words:
            return " ".join(words)
    return wiki_action_axis(intent)


def _wiki_hybrid_vars(question, intent):
    intent = intent or {}
    ac = wiki_action_class(intent)
    ac_sql = ac if ac in ("event", "object") else "none"
    return {
        "question": question or "",
        "embed_model": EMBED_MODEL.replace("'", "''"),
        "embed_secret": EMBED_SECRET_NAME.replace("'", "''"),
        "embed_dim": EMBED_DIM,
        "embed_maxlen": WIKI_EMBED_MAXLEN,
        "knn_limit": WIKI_KNN_N,
        "action_class": ac_sql,
        "action_axis": wiki_axis_phrase(intent).replace("'", "''"),
        "want_agg": 1 if wiki_aggregate_want(intent, question) else 0,
        "stem_dict": STEM_DICT.replace("'", "''"),
        "pick_limit": WIKI_PICK_N,
    }


def _wiki_substitute_sql(template, vars_):
    out = template
    for key, val in vars_.items():
        if isinstance(val, int):
            rep = str(val)
        else:
            rep = "'%s'" % str(val).replace("'", "''")
        out = out.replace(":%s" % key, rep)
        out = re.sub(r":'" + re.escape(key) + r"'", rep, out)
    return out


def wiki_hybrid_pool(question, intent=None):
    """kNN-топ-N → структурное сужение в SQL. Пустой пул — []."""
    if not question:
        return []
    try:
        _ensure_embed_secret()
    except RuntimeError:
        return []
    sql_body = _wiki_hybrid_sql()
    if sql_body.strip().startswith("\\set"):
        sql_body = "\n".join(
            ln for ln in sql_body.splitlines()
            if not ln.strip().startswith("\\set"))
    qsql = _wiki_substitute_sql(sql_body, _wiki_hybrid_vars(question, intent))
    try:
        rows = psql(qsql)
    except RuntimeError:
        return []
    out = []
    for r in rows or []:
        if not r or not r[0]:
            continue
        src = str(r[0])
        # Защита: если SQL вернул rk первым — src_table уедет в цифру («1»).
        if src.isdigit() and len(r) > 1 and r[1]:
            r = r[1:]
            src = str(r[0])
        parent = (r[7] if len(r) > 7 else "") or ""
        out.append({
            "src_table": src,
            "name": (r[1] if len(r) > 1 else "") or "",
            "description": (r[2] if len(r) > 2 else "") or "",
            "axes": (r[3] if len(r) > 3 else "") or "",
            "measures": (r[4] if len(r) > 4 else "") or "",
            "covered": int(r[5] or 0) if len(r) > 5 else 0,
            "distance": float(r[6]) if len(r) > 6 and r[6] is not None else 1.0,
            "parent": parent,
            "platform_kind": wiki_platform_kind(src, parent),
        })
    return out


def wiki_format_card_lines(cards):
    lines = []
    for i, c in enumerate(cards or []):
        lines.append(
            "%d. name: %s\n   description: %s\n   platform: %s\n   axes: %s\n   measures: %s"
            % (i + 1,
               c.get("name") or "—",
               (c.get("description") or "—")[:200],
               c.get("platform_kind") or "—",
               c.get("axes") or "—",
               c.get("measures") or "—"))
    return "\n\n".join(lines)


def wiki_knn_separable(cards):
    """Разделяемость топ-2 по cosine distance."""
    if len(cards or []) < 2:
        return True, None
    d0 = float(cards[0].get("distance") or 0)
    d1 = float(cards[1].get("distance") or 0)
    gap = d1 - d0
    return gap >= WIKI_SEP_GAP, round(gap, 4)


def wiki_validate_leader_axes(leader, intent):
    """Форма src: ось уже сужена SQL (axis_ok / struct src_layer=2).

    Повторный registers_for_kind_axes+refcols отвергал лидера из пула
    (struct проходит axis_ok без EXISTS, Python — нет) → axis_reject на
    верном accumulationregister. Доки: list_has_any / ts_lexize в hybrid SQL.
    """
    if not leader or str(leader).isdigit():
        return False
    head = str(leader).split("_", 1)[0].lower()
    return head in (
        "catalog", "document", "accumulationregister",
        "informationregister", "documentjournal", "constant")


def wiki_pick_from_cards(question, intent, cards, diag=None):
    """Модель: лидер или «ни один»; близко → переспрос (код + kNN gap)."""
    diag = dict(diag or {})
    cards = list(cards or [])
    if not cards:
        return {"outcome": "none", "reason": "empty_pool", "diag": diag}
    k_sep, gap = wiki_knn_separable(cards)
    diag["wiki_knn_gap"] = gap
    listing = wiki_format_card_lines(cards)
    ask_text = question or ""
    kind = _intent_text((intent or {}).get("kind"))
    if kind:
        ask_text = "%s (%s)" % (ask_text, kind)
    try:
        raw = ds_chat(
            [{"role": "system", "content": WIKI_PICK_SYS},
             {"role": "user", "content": "%s\n\nCards:\n%s" % (ask_text, listing)}],
            max_tokens=120)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("ask DEGRADED: wiki pick без модели (%s)\n" % str(e)[:80])
        return {"outcome": "degraded", "diag": diag}
    choice, separable = 0, k_sep
    txt = (raw or "").strip()
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        if isinstance(j, dict):
            c = j.get("choice")
            if c is not None and str(c).strip().isdigit():
                choice = int(c)
            if "separable" in j:
                separable = bool(j.get("separable")) and k_sep
    except (ValueError, KeyError, TypeError):
        nums = [int(x) for x in re.findall(r"\b(\d+)\b", txt)]
        choice = nums[0] if nums else 0
    if choice == 0:
        diag["wiki_pick"] = "none"
        return {"outcome": "none", "reason": "model_none", "diag": diag}
    if choice < 1 or choice > len(cards):
        diag["wiki_pick"] = "bad_index"
        return {"outcome": "none", "reason": "bad_index", "diag": diag}
    leader = cards[choice - 1]["src_table"]
    if (not leader or str(leader).isdigit()
            or "_" not in str(leader)):
        diag["wiki_pick"] = "bad_index"
        diag["wiki_leader_rejected"] = leader
        return {"outcome": "none", "reason": "bad_src", "diag": diag}
    if not wiki_validate_leader_axes(leader, intent):
        diag["wiki_pick"] = "axis_reject"
        diag["wiki_leader_rejected"] = leader
        return {"outcome": "none", "reason": "axis_reject", "diag": diag}
    if not separable and len(cards) >= 2:
        diag["wiki_pick"] = "clarify"
        diag["wiki_tie"] = [cards[0]["src_table"], cards[1]["src_table"]]
        return {"outcome": "clarify", "candidates": cards[:2], "diag": diag}
    diag["wiki_pick"] = leader
    return {"outcome": "leader", "leader": leader, "diag": diag}


def wiki_stock_canon_takeover(question, intent, diag, cands, plan=None):
    """Wiki catalog-tie/none не перекрывает stock_canon (остаток — регистр)."""
    intent = intent or {}
    plan = plan or {}
    if (diag or {}).get("register_count_locked"):
        return None
    _ccq = globals().get("catalog_count_question")
    if callable(_ccq) and _ccq(intent, question):
        return None
    _ckt = globals().get("catalog_kind_total_question")
    if callable(_ckt) and _ckt(intent, question):
        return None
    if "stock_question_engaged" not in globals():
        return None
    if not stock_question_engaged(question, intent, plan):
        return None
    canon = (diag or {}).get("stock_canon_locked")
    if not canon and "stock_canon_src" in globals():
        try:
            canon = stock_canon_src(cands, question, intent, plan)
        except RuntimeError:
            canon = None
    return canon or None


def wiki_primary_entity_cascade(question, intent, cands, diag, cut, t0,
                                by, match, preds, counts_for_model, plan=None):
    """Wiki-first entity pick; manual balance/event/count_theme only on fallback."""
    picked, marks, plan = [], {}, plan or {}
    if diag.get("register_count_locked"):
        return {"picked": [diag["register_count_locked"]], "marks": {},
                "plan": plan}
    if diag.get("sales_canon_locked"):
        return {"picked": [diag["sales_canon_locked"]], "marks": {},
                "plan": plan}
    _wiki_skip_manual = False
    if ASK_WIKI_CHOICE:
        _wiki = try_wiki_hybrid_entity_pick(
            question, intent, diag, cut, t0,
            by=by, match=match, preds=preds)
        if (_wiki and _wiki.get("kind") in ("no_data", "clarify")
                and not diag.get("sales_canon_locked")):
            _sc = wiki_stock_canon_takeover(question, intent, diag, cands, plan)
            if _sc:
                picked = [_sc]
                diag["wiki_stock_override"] = _sc
                diag["wiki_pick"] = "stock_override"
                diag["stock_canon_locked"] = _sc
            else:
                return _wiki
        if _wiki and _wiki.get("picked") and not picked:
            picked = _wiki["picked"]
            marks = _wiki.get("marks") or {}
            plan = _wiki.get("plan") or {}
            # Wiki catalog на stock-вопрос — не канон остатка; takeover регистра.
            _sc = wiki_stock_canon_takeover(question, intent, diag, cands, plan)
            if _sc and str(picked[0]).startswith("catalog_"):
                picked = [_sc]
                diag["wiki_stock_override"] = _sc
                diag["wiki_pick"] = "stock_override"
                diag["stock_canon_locked"] = _sc
            else:
                diag["wiki_hybrid_pick"] = True
        elif _wiki is None and not diag.get("wiki_pick"):
            diag["wiki_pick"] = "fallback"
        if (not picked and diag.get("wiki_empty_pool")
                and question_expects_accounting_data(intent, question, diag)):
            _sc = wiki_stock_canon_takeover(question, intent, diag, cands, plan)
            if _sc:
                picked = [_sc]
                diag["wiki_stock_override"] = _sc
                diag["wiki_pick"] = "stock_override"
                diag["stock_canon_locked"] = _sc
            else:
                return {"kind": "no_data",
                        "partial": cut or None,
                        "text": NO_DATA_TEXT or refuse_text(question),
                        "sources": [],
                        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                           reason="wiki_empty_pool")}
        if (not picked and diag.get("wiki_pool_n", 0) > 0
                and diag.get("wiki_pick") in ("none", "axis_reject", "bad_index")):
            _sc = wiki_stock_canon_takeover(question, intent, diag, cands, plan)
            if _sc:
                picked = [_sc]
                diag["wiki_stock_override"] = _sc
                diag["wiki_pick"] = "stock_override"
                diag["stock_canon_locked"] = _sc
            else:
                _wiki_skip_manual = True
                if (question_expects_accounting_data(intent, question, diag)
                        and diag.get("wiki_pick") == "none"):
                    return {"kind": "no_data",
                            "partial": cut or None,
                            "text": NO_DATA_TEXT or refuse_text(question),
                            "sources": [],
                            "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                               reason="wiki_none")}
    if not picked and not _wiki_skip_manual:
        _bal = try_balance_code_entity_pick(
            question, intent, cands, diag, cut, t0, {}, plan=plan)
        if _bal and _bal.get("kind") in ("no_data", "clarify"):
            return _bal
        if _bal and _bal.get("picked"):
            picked = _bal["picked"]
            marks = _bal.get("marks") or {}
            plan = _bal.get("plan") or {}
            diag["balance_code_pick"] = True
            if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                diag["wiki_manual_fallback"] = "balance"
        else:
            _ev = try_event_code_entity_pick(
                question, intent, cands, diag, cut, t0, by, match, preds, {})
            if _ev and _ev.get("kind") in ("no_data", "clarify"):
                return _ev
            if _ev and _ev.get("picked"):
                picked = _ev["picked"]
                marks = _ev.get("marks") or {}
                plan = _ev.get("plan") or {}
                diag["event_code_pick"] = True
                if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                    diag["wiki_manual_fallback"] = "event"
            else:
                _ct = try_count_theme_code_pick(
                    question, intent, cands, diag, cut, t0)
                if _ct and _ct.get("picked"):
                    picked = _ct["picked"]
                    marks, plan = {}, {}
                    diag.update(_ct.get("diag") or {})
                    if ASK_WIKI_CHOICE and diag.get("wiki_pick") and not diag.get("wiki_hybrid_pick"):
                        diag["wiki_manual_fallback"] = "count_theme"
    if not picked and not _wiki_skip_manual:
        try:
            picked, marks, plan = pick_entity(question, intent.get("kind"), cands,
                                              counts_for_model, match, diag)
        except RuntimeError:
            picked, marks, plan = [], {}, {}
            diag["degraded"] = "выбор сущности сделан без модели"
    return {"picked": picked, "marks": marks, "plan": plan}


def try_wiki_hybrid_entity_pick(question, intent, diag, cut, t0,
                                by=None, match="", preds=None):
    """Единая точка интеграции для z20."""
    if not ASK_WIKI_CHOICE:
        return None
    if diag is None:
        diag = {}
    diag["wiki_attempted"] = True
    try:
        if not psql("SELECT 1 FROM search_wiki_entity_card LIMIT 1"):
            return None
    except RuntimeError:
        return None
    cards = wiki_hybrid_pool(question, intent)
    diag["wiki_pool_n"] = len(cards)
    diag["wiki_pool"] = [c["src_table"] for c in cards]
    if not cards:
        if not question_expects_accounting_data(intent, question, diag):
            diag["wiki_none"] = "empty_pool"
            return {"kind": "no_data",
                    "partial": cut or None,
                    "text": refuse_text(question) or NO_DATA_TEXT,
                    "sources": [],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                       reason="wiki_none_empty")}
        diag["wiki_pick"] = "none"
        diag["wiki_empty_pool"] = True
        return None
    pick = wiki_pick_from_cards(question, intent, cards, diag=diag)
    diag.update(pick.get("diag") or {})
    if pick.get("outcome") == "degraded":
        diag["wiki_pick"] = "fallback"
        return None
    # event_count_period_assumed + clarify/none → fallback: event_code_pick
    # считает distinct по оси (без wiki-clarify чужих карточек).
    if (diag.get("event_count_period_assumed")
            and pick.get("outcome") in ("clarify", "none")):
        diag["wiki_pick"] = "fallback"
        diag["wiki_period_assumed_fallback"] = pick.get("outcome")
        return None
    if pick.get("outcome") == "none":
        if not diag.get("wiki_pick"):
            diag["wiki_pick"] = "none"
        diag["wiki_none"] = pick.get("reason") or "model_none"
        return None
    if pick.get("outcome") == "clarify":
        tied = [c["src_table"] for c in (pick.get("candidates") or [])]
        try:
            lab_by = {r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in tied))) if r and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = mk_opts(tied, lab_by, {}, by or {}, match=match or "", preds=preds or [])
        if len(opts) >= 2:
            return {"partial": cut or None, "kind": "clarify",
                    "text": clarify_say(question, opts, diag)
                            or ", ".join("«%s»" % o["label"] for o in opts),
                    "options": opts, "sources": [o["label"] for o in opts],
                    "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                       reason="wiki_separability")}
    leader = pick.get("leader")
    if leader:
        return {"picked": [leader], "marks": {}, "plan": {}}
    return None


register_zone("ask.z21_wiki_choice", globals())
