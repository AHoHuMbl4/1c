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
        parent = (r[8] if len(r) > 8 else "") or ""
        out.append({
            "src_table": r[0],
            "name": r[1] or "",
            "description": (r[2] if len(r) > 2 else "") or "",
            "axes": (r[3] if len(r) > 3 else "") or "",
            "measures": (r[4] if len(r) > 4 else "") or "",
            "covered": int(r[5] or 0) if len(r) > 5 else 0,
            "distance": float(r[6]) if len(r) > 6 and r[6] is not None else 1.0,
            "parent": parent,
            "platform_kind": wiki_platform_kind(r[0], parent),
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
    """K9: refcols несут оси kind/action_axis из intent."""
    if not leader:
        return False
    intent = intent or {}
    words = intent_axis_words(intent) if "intent_axis_words" in globals() else []
    if not words:
        return True
    try:
        if leader.startswith("accumulationregister_"):
            regs = registers_for_kind_axes(intent, [leader])
            if leader in regs:
                return True
        if leader.startswith("catalog_"):
            for w in words:
                if leader in (entity_form_catalogs_for_kind(w, allow_meaning=False) or []):
                    return True
        rows = psql(
            "SELECT 1 FROM search_refcols r WHERE r.src_table = %s "
            "AND list_has_any("
            "  list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "  list_filter(ts_lexize(%s, concat_ws(' ', r.col, r.target_src)),"
            "              x -> length(x) >= 3)) LIMIT 1"
            % (lit(leader), lit(STEM_DICT), lit(" ".join(words)),
               lit(STEM_DICT)))
        return bool(rows)
    except RuntimeError:
        return True


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


def try_wiki_hybrid_entity_pick(question, intent, diag, cut, t0,
                                by=None, match="", preds=None):
    """Единая точка интеграции для z20."""
    if not ASK_WIKI_CHOICE:
        return None
    diag = dict(diag or {})
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
