"""Zone 21: Wiki hybrid entity choice (PLAN_WIKI_CHOICE §Б3)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

ASK_WIKI_CHOICE = os.environ.get("ASK_WIKI_CHOICE", "0") == "1"
WIKI_KNN_N = int(os.environ.get("WIKI_KNN_N", "15"))
# [01.09] Пул шире паспортов: структурные слагаемые (словарь/мера) ГАРАНТИРУЮТ
# присутствие, но не должны вытеснять близких kNN-соседей (замер: карточка
# «отработанноевремя» при d=0.378 не входила в пул из 5 — три места занимал
# словарь по слову «регистр»).
WIKI_PICK_N = int(os.environ.get("WIKI_PICK_N", "8"))
WIKI_ALIAS_TOP = int(os.environ.get("WIKI_ALIAS_TOP", "3"))
# [01.09, ночь] Паспортов столько же, сколько карточек у выбора: карточка за
# пределами паспортов физически не может быть подтверждена верификацией
# (замер: верная accumulationregister_книгапродаж стала №6 пула после
# объединения двух форм вопроса — при 5 паспортах верификация её не видела и
# вопрос уходил в no_data при живом эталоне 76 075).
WIKI_PASSPORT_N = int(os.environ.get("WIKI_PASSPORT_N", "8"))
WIKI_PASSPORT_BODY_MAX = int(os.environ.get("WIKI_PASSPORT_BODY_MAX", "1500"))
WIKI_SEP_GAP = float(os.environ.get("WIKI_SEP_GAP", "0.04"))
WIKI_EMBED_MAXLEN = int(os.environ.get("WIKI_EMBED_MAXLEN", "20000"))

_HYBRID_SQL = None
_PASSPORT_SQL = None


def _wiki_hybrid_sql():
    global _HYBRID_SQL
    if _HYBRID_SQL is None:
        _HYBRID_SQL = (ASK_ROOT / "wiki_card_hybrid.sql").read_text(encoding="utf-8")
    return _HYBRID_SQL


def _wiki_passport_sql():
    global _PASSPORT_SQL
    if _PASSPORT_SQL is None:
        _PASSPORT_SQL = (ASK_ROOT / "wiki_passport.sql").read_text(encoding="utf-8")
    return _PASSPORT_SQL


WIKI_PICK_SYS = """Map the user's question to one numbered entity card, or 0.
Each card shows: name, description, platform kind, axes, measures (same fields for all).
Reply with one JSON object only:
  {"choice": <1-based card index or 0>, "separable": <true|false>}"""

WIKI_VERIFY_SYS = """Assess each numbered entity passport against the user question.
Each passport shows: name, wiki excerpt, platform kind, axes, measures,
traits present only in this passport vs pool neighbors;
doesNotAnswer lists topics marked outside entity coverage.
Reply with one JSON object only:
  {"verdicts": [{"index": <1-based passport index>, "fit": <"yes"|"no"|"unsure">,
                 "why": <one line>}]}
Include one verdict per passport shown."""


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


def wiki_axis_phrase(intent, question=""):
    """Оси разбора (kind + action_axis) — структурный вход SQL.

    [01.09 okna] ОСЬ ПОДАЁТСЯ В ФИЛЬТР ТОЛЬКО КОГДА БАЗА ЕЁ НЕСЁТ: у оси есть
    носители (каталог-ось по label/aliases или регистры с такой ref-осью).
    Слово без носителей — это ИМЯ ЦЕЛИ («записей в регистре книгапродаж»:
    стемов «книгапродаж» нет ни в одном refcol), и осевой фильтр срезал весь
    kNN-топ — пул пуст при живой карточке, no_data при живом эталоне
    (29 вопросов «движений в регистре X»). Имя цели несёт сам вопрос —
    kNN его видит; фильтр осей для несуществующей оси был бессмыслен и
    вреден. Проверка носителей — штатные резолверы (resolved_warehouse_
    axis_word / registers_for_kind_axes), не слова кода.

    [01.09, вечер] ОСЬ — ТОЛЬКО НАЗВАННАЯ ЧЕЛОВЕКОМ (action_axis). Род записей
    (kind) осью не является: «движений в регистре отработанноевремя» — слово
    «движения» нашло случайного носителя («движения денежных средств»), и
    фильтр срезал ближайших kNN-соседей (карточки отработанноевремя d=0.378
    не попали в пул из 7). Симметрично правилу live_axis_col_for_count:
    смысловой мост — для названной оси, а не для рода.
    """
    if "intent_axis_words" not in globals():
        return wiki_action_axis(intent)
    if not _intent_text((intent or {}).get("action_axis")):
        return ""
    words = intent_axis_words(intent)
    if words:
        phrase = " ".join(words)
        if _wiki_axis_has_carriers(phrase, intent, question):
            return phrase
    return ""


_WIKI_AXIS_CARRIERS = {"at": 0.0, "phrase": None, "res": None}


def _wiki_axis_has_carriers(phrase, intent, question=""):
    """Есть ли у фразы-оси носители в базе (каталог-ось или ref-ось регистра).

    Кэш 300 с по фразе. Ошибка чтения = «носителей нет» — фильтр оси
    отключается, пул строится по kNN (безопасная сторона).
    """
    now = time.time()
    if (_WIKI_AXIS_CARRIERS["phrase"] == phrase
            and now - _WIKI_AXIS_CARRIERS["at"] < 300):
        return _WIKI_AXIS_CARRIERS["res"]
    res = False
    try:
        _rw = globals().get("resolved_warehouse_axis_word")
        if callable(_rw) and _rw(question or phrase, intent or {}):
            res = True
    except RuntimeError:
        res = False
    if not res:
        try:
            _rg = globals().get("registers_for_kind_axes")
            if callable(_rg) and _rg(intent or {}, None, question or phrase):
                res = True
        except RuntimeError:
            res = False
    _WIKI_AXIS_CARRIERS.update({"at": now, "phrase": phrase, "res": res})
    return res


def _wiki_hybrid_vars(question, intent):
    intent = intent or {}
    ac = wiki_action_class(intent)
    ac_sql = ac if ac in ("event", "object") else "none"
    # [01.09] пул ищется по ПОИСКОВОЙ ФОРМЕ (вопрос без периода/чисел из
    # разбора): периодные слова утягивали kNN и словарь к карточкам периода
    # («закрытие месяца») и выталкивали верную карточку. LLM-шаги каскада
    # по-прежнему видят исходный вопрос.
    q_search = (intent.get("search_form") or "").strip() or (question or "")
    return {
        "question": q_search,
        # [01.09, ночь] сырой вопрос — второй вход пула (kNN + словарь):
        # search_form на склеенных именах сворачивается в голый токен, по
        # которому вектор промахивается (замер L8: регрессия 17→10 match).
        "question_raw": (question or ""),
        "embed_model": EMBED_MODEL.replace("'", "''"),
        "embed_secret": EMBED_SECRET_NAME.replace("'", "''"),
        "embed_dim": EMBED_DIM,
        "embed_maxlen": WIKI_EMBED_MAXLEN,
        "knn_limit": WIKI_KNN_N,
        "action_class": ac_sql,
        "action_axis": wiki_axis_phrase(intent, question).replace("'", "''"),
        "want_agg": 1 if wiki_aggregate_want(intent, question) else 0,
        "stem_dict": STEM_DICT.replace("'", "''"),
        "pick_limit": WIKI_PICK_N,
        "alias_top": WIKI_ALIAS_TOP,
        "measure": (intent.get("measure") or "").replace("'", "''"),
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


def _wiki_substitute_passport_sql(template, src_tables):
    tables = [s for s in (src_tables or [])[:WIKI_PASSPORT_N] if s]
    if not tables:
        return ""
    lst = ", ".join("'%s'" % str(s).replace("'", "''") for s in tables)
    out = template
    if out.strip().startswith("\\set"):
        out = "\n".join(
            ln for ln in out.splitlines()
            if not ln.strip().startswith("\\set"))
    out = out.replace(":src_list", lst)
    out = out.replace(":body_max", str(WIKI_PASSPORT_BODY_MAX))
    return out


def _wiki_parse_axes_set(axes_str):
    out = set()
    for part in (axes_str or "").split(","):
        part = part.strip()
        if "->" in part:
            out.add(part.split("->", 1)[0].strip().lower())
        elif part:
            out.add(part.lower())
    return out


def _wiki_parse_measures_set(measures_str):
    out = set()
    for part in (measures_str or "").split(";"):
        part = part.strip()
        if ":" in part:
            out.add(part.split(":", 1)[0].strip().lower())
        elif part:
            out.add(part.lower())
    return out


def wiki_passport_distinct(card, pool):
    """Поля осей/мер, которых нет у других кандидатов пула."""
    my_ax = _wiki_parse_axes_set(card.get("axes"))
    my_ms = _wiki_parse_measures_set(card.get("measures"))
    o_ax, o_ms = set(), set()
    for c in pool or []:
        if c.get("src_table") == card.get("src_table"):
            continue
        o_ax |= _wiki_parse_axes_set(c.get("axes"))
        o_ms |= _wiki_parse_measures_set(c.get("measures"))
    parts = []
    d_ax = sorted(my_ax - o_ax)
    d_ms = sorted(my_ms - o_ms)
    if d_ax:
        parts.append("axes: " + ", ".join(d_ax))
    if d_ms:
        parts.append("measures: " + ", ".join(d_ms))
    return "; ".join(parts) if parts else "—"


def wiki_passport_enrich(cards):
    """Расширенный паспорт top-N: wiki body + отличия от соседей пула."""
    cards = list(cards or [])
    if not cards:
        return []
    top = cards[:WIKI_PASSPORT_N]
    rest = cards[WIKI_PASSPORT_N:]
    by_src = {}
    qsql = _wiki_substitute_passport_sql(
        _wiki_passport_sql(), [c.get("src_table") for c in top])
    if qsql:
        try:
            for r in psql(qsql) or []:
                if not r or not r[0]:
                    continue
                by_src[str(r[0])] = {
                    "wiki_body": (r[2] if len(r) > 2 else "") or "",
                    "parent": (r[5] if len(r) > 5 else "") or "",
                    "not_enough_for": (r[7] if len(r) > 7 else "") or "",
                }
        except RuntimeError:
            pass
    out = []
    for c in top:
        row = dict(c)
        extra = by_src.get(row.get("src_table") or "", {})
        if extra.get("wiki_body"):
            row["wiki_body"] = extra["wiki_body"]
        elif row.get("description"):
            row["wiki_body"] = row["description"]
        else:
            row["wiki_body"] = ""
        if extra.get("parent") is not None:
            row["parent"] = extra["parent"]
        if extra.get("not_enough_for"):
            row["not_enough_for"] = extra["not_enough_for"]
        row["platform_kind"] = wiki_platform_kind(
            row.get("src_table"), row.get("parent") or "")
        row["distinct"] = wiki_passport_distinct(row, top)
        out.append(row)
    for c in rest:
        out.append(dict(c))
    return out


def wiki_format_passport_lines(passports, short_tail=None):
    """Макет паспортов для модели: полные top-N, хвост — только имена."""
    lines = []
    for i, p in enumerate(passports or []):
        if i >= WIKI_PASSPORT_N:
            break
        body = (p.get("wiki_body") or p.get("description") or "—")[:WIKI_PASSPORT_BODY_MAX]
        distinct_line = p.get("distinct") or "—"
        nef = (p.get("not_enough_for") or "").strip()
        if nef:
            distinct_line += "\n   doesNotAnswer: %s" % nef
        lines.append(
            "%d. passport\n   name: %s\n   wiki: %s\n   platform: %s\n   axes: %s\n"
            "   measures: %s\n   distinct: %s"
            % (i + 1,
               p.get("name") or "—",
               body or "—",
               p.get("platform_kind") or "—",
               p.get("axes") or "—",
               p.get("measures") or "—",
               distinct_line))
    tail = short_tail or []
    if tail:
        names = ", ".join(
            (c.get("name") or c.get("src_table") or "?") for c in tail)
        lines.append("Other pool names only: %s" % names)
    return "\n\n".join(lines)


def wiki_parse_verify_response(raw, n_passports):
    """Структурный разбор {verdicts:[{index, fit, why}]}."""
    verdicts = []
    txt = (raw or "").strip()
    if not txt or n_passports <= 0:
        return verdicts
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except (ValueError, KeyError, TypeError):
        return verdicts
    if not isinstance(j, dict):
        return verdicts
    rows = j.get("verdicts")
    if not isinstance(rows, list):
        return verdicts
    fit_map = {
        "yes": "yes", "no": "no", "unsure": "unsure",
        "подходит": "yes", "не_подходит": "no", "не подходит": "no",
        "сомневаюсь": "unsure",
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if idx is None or not str(idx).strip().isdigit():
            continue
        i = int(idx)
        if i < 1 or i > n_passports:
            continue
        fit_raw = str(row.get("fit") or "").strip().lower()
        fit = fit_map.get(fit_raw, fit_raw if fit_raw in ("yes", "no", "unsure") else "")
        if fit not in ("yes", "no", "unsure"):
            continue
        why = str(row.get("why") or "").strip()[:200]
        verdicts.append({"index": i, "fit": fit, "why": why})
    return verdicts


def wiki_outcome_from_verify(verdicts, passports, intent, diag=None):
    """Исход верификации: leader / clarify / none (код, без «лучший из плохих»)."""
    diag = dict(diag or {})
    passports = list(passports or [])[:WIKI_PASSPORT_N]
    if not passports:
        return {"outcome": "none", "reason": "empty_passports", "diag": diag}
    by_idx = {v["index"]: v for v in (verdicts or [])}
    yes_i, unsure_i, no_i = [], [], []
    for i in range(1, len(passports) + 1):
        v = by_idx.get(i)
        if not v:
            continue
        if v["fit"] == "yes":
            yes_i.append(i)
        elif v["fit"] == "unsure":
            unsure_i.append(i)
        else:
            no_i.append(i)
    diag["wiki_verify_yes"] = len(yes_i)
    diag["wiki_verify_unsure"] = len(unsure_i)
    diag["wiki_verify_no"] = len(no_i)
    if len(yes_i) == 1 and not unsure_i:
        leader = passports[yes_i[0] - 1].get("src_table")
        if not wiki_validate_leader_axes(leader, intent):
            diag["wiki_verify"] = "axis_reject"
            return {"outcome": "none", "reason": "axis_reject", "diag": diag}
        diag["wiki_verify"] = leader
        return {"outcome": "leader", "leader": leader, "diag": diag}
    if len(yes_i) == 0 and not unsure_i:
        diag["wiki_verify"] = "none"
        return {"outcome": "none", "reason": "verify_none", "diag": diag}
    tie_idx = sorted(set(yes_i + unsure_i))
    if not tie_idx:
        diag["wiki_verify"] = "none"
        return {"outcome": "none", "reason": "verify_none", "diag": diag}
    diag["wiki_verify"] = "clarify"
    diag["wiki_verify_tie"] = [
        passports[i - 1].get("src_table") for i in tie_idx
        if 0 < i <= len(passports)]
    return {
        "outcome": "clarify",
        "candidates": [passports[i - 1] for i in tie_idx
                       if 0 < i <= len(passports)],
        "diag": diag,
    }


def wiki_verify_candidates(question, intent, cards, diag=None):
    """Паспортная verify: вопрос + пул карточек (≥1) → модель → verdicts."""
    diag = dict(diag or {})
    cards = list(cards or [])
    if not cards:
        return {"outcome": "none", "reason": "empty_pool", "diag": diag}
    enriched = wiki_passport_enrich(cards)
    full = enriched[:WIKI_PASSPORT_N]
    short = enriched[WIKI_PASSPORT_N:]
    listing = wiki_format_passport_lines(full, short_tail=short)
    ask_text = question or ""
    kind = _intent_text((intent or {}).get("kind"))
    if kind:
        ask_text = "%s (%s)" % (ask_text, kind)
    try:
        raw = ds_chat(
            [{"role": "system", "content": WIKI_VERIFY_SYS},
             {"role": "user", "content": "%s\n\nPassports:\n%s"
              % (ask_text, listing)}],
            max_tokens=400)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("ask DEGRADED: wiki verify без модели (%s)\n" % str(e)[:80])
        return {"outcome": "degraded", "diag": diag}
    verdicts = wiki_parse_verify_response(raw, len(full))
    diag["wiki_verify_n"] = len(full)
    resolved = wiki_outcome_from_verify(verdicts, full, intent, diag=diag)
    resolved["verdicts"] = verdicts
    resolved["diag"] = dict(resolved.get("diag") or diag)
    return resolved


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
    choice, separable, pick_reason = 0, k_sep, "model_none"
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
        choice = 0
        pick_reason = "model_unparseable"
    if choice == 0:
        diag["wiki_pick"] = "none"
        return {"outcome": "none", "reason": pick_reason, "diag": diag}
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


def wiki_primary_entity_cascade(question, intent, cands, diag, cut, t0,
                                by, match, preds, counts_for_model, plan=None):
    """Wiki-first entity pick; manual balance/event/count_theme only on fallback.

    [01.09] Вики — ПЕРВАЯ ступень для всех вопросов (схема владельца
    PLAN_WIKI_CHOICE: вход — LLM+вики понимает вопрос). Замки продаж/регистра
    ставятся ЗДЕСЬ, ПОСЛЕ вики-попытки, как fallback — раньше они стояли в z20
    выше каскада и перехватывали выбор до вики (замер: «Сколько валют?»
    уходил в накопregister_импорттмц замком регистра по стиху «валют» в его
    мерах). Уже поставленные замки (поздний продажный канон и др.) — по-прежнему
    уважаются первой проверкой.
    """
    picked, marks, plan = [], {}, plan or {}
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
            return _wiki
        if _wiki and _wiki.get("picked") and not picked:
            picked = _wiki["picked"]
            marks = _wiki.get("marks") or {}
            plan = _wiki.get("plan") or {}
            diag["wiki_hybrid_pick"] = True
        elif _wiki is None and not diag.get("wiki_pick"):
            diag["wiki_pick"] = "fallback"
    # 🔴 [01.09, требование владельца: «физически один путь»] Обходных
    # выборов сущности больше НЕ СУЩЕСТВУЕТ: замки продаж/регистра/прайса,
    # stock-takeover, баланс/событие/тема-коды, выбор по реранку — вырезаны.
    # Единственный путь: вики-каскад (пул карточек → LLM → верификация
    # паспортами). Дал лидера — работаем; дал чипы — спрашиваем человека;
    # не дал ничего — честный отказ. На любой базе работает одна и та же
    # логика, перепроверять точечно нечем и не нужно.
    if not picked:
        _reason = diag.get("wiki_pick") or "wiki_no_leader"
        if diag.get("wiki_empty_pool"):
            _reason = "wiki_empty_pool"
        return {"kind": "no_data",
                "partial": cut or None,
                "text": NO_DATA_TEXT or refuse_text(question),
                "sources": [],
                "diag": _diag_pack(diag, sec=round(time.time() - t0, 2),
                                   reason=_reason)}
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
    if len(cards) == 1:
        verify = wiki_verify_candidates(question, intent, cards, diag=diag)
        diag.update(verify.get("diag") or {})
        pick = verify
    else:
        pick = wiki_pick_from_cards(question, intent, cards, diag=diag)
        diag.update(pick.get("diag") or {})
        if pick.get("outcome") == "degraded":
            diag["wiki_pick"] = "fallback"
            return None
        verify = wiki_verify_candidates(question, intent, cards, diag=diag)
        diag.update(verify.get("diag") or {})
        if verify.get("outcome") == "degraded":
            pass
        elif verify.get("outcome") in ("leader", "clarify", "none"):
            pick = verify
            if verify.get("outcome") == "leader":
                diag["wiki_pick"] = verify.get("leader") or diag.get("wiki_pick")
            elif verify.get("outcome") == "none":
                diag["wiki_pick"] = "none"
                diag["wiki_none"] = verify.get("reason") or "verify_none"
            elif verify.get("outcome") == "clarify":
                diag["wiki_pick"] = "clarify"
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
        # [01.09, ночь] Спрошенная величина — структурный факт, не промт.
        # Если база ЗНАЕТ названную меру (есть носители в search_measure_alias),
        # ответить на неё может только носитель: верификация-модель это
        # пропускала (замер L11: «остатки по складу» → catalog_местахранения,
        # носители «остатка» в базе — другие сущности; ответ «3 склада» при
        # эталоне no_data). Если носителей в базе нет вовсе, мера — понятие из
        # вопроса («торговля»), а не имя поля: доказать отсутствие нельзя,
        # ответ не роняется (п. 21). Проверка кодом, судья — те же данные.
        _measure = _intent_text((intent or {}).get("measure"))
        if _measure and not wiki_measure_carried(leader, _measure):
            diag["wiki_measure_not_carried"] = leader
            diag["wiki_none"] = "measure_not_carried"
            return None
        return {"picked": [leader], "marks": {}, "plan": {}}
    return None


def wiki_measure_carried(src_table, measure):
    """Лидер — носитель названной меры, или носителей в базе нет вовсе.

    Один запрос к search_measure_alias (те же данные и тот же стем-приём,
    что у struct_measure в пуле). Носителей нет — мера считается понятием
    вопроса: True. Ошибка чтения — True: отказ требует доказанного
    отсутствия (п. 21). Доки: ts_lexize / list_has_any (как в hybrid SQL).
    """
    try:
        rows = psql(
            "SELECT count(*),"
            "       count(*) FILTER (WHERE src_table = %s)"
            "  FROM search_measure_alias"
            " WHERE list_has_any("
            "   list_filter(ts_lexize(%s, %s), x -> length(x) >= 3),"
            "   list_filter(ts_lexize(%s,"
            "       concat_ws(' ', measure, aliases)), x -> length(x) >= 3))"
            % (lit(src_table), lit(STEM_DICT), lit(measure), lit(STEM_DICT)))
    except RuntimeError:
        return True
    if not rows:
        return True
    any_n, leader_n = int(rows[0][0] or 0), int(rows[0][1] or 0)
    return any_n == 0 or leader_n > 0


register_zone("ask.z21_wiki_choice", globals())
