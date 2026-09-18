"""Zone 21: Wiki hybrid entity choice (PLAN_WIKI_CHOICE §Б3)."""
from __future__ import annotations

from ask._imports import *
from ask._wire import register_zone, apply_bindings

apply_bindings(globals())

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
WIKI_VERIFY_MAX_TOKENS = int(os.environ.get("WIKI_VERIFY_MAX_TOKENS", "2048"))
WIKI_PASSPORT_BODY_MAX = int(os.environ.get("WIKI_PASSPORT_BODY_MAX", "1500"))
WIKI_SEP_GAP = float(os.environ.get("WIKI_SEP_GAP", "0.04"))
WIKI_EMBED_MAXLEN = int(os.environ.get("WIKI_EMBED_MAXLEN", "20000"))
# C1 rescue: полный пул без срезов каскада 3/8 (design-c §2 шаг 1).
WIKI_RESCUE_ALIAS_N = int(os.environ.get("WIKI_RESCUE_ALIAS_N", "96"))
WIKI_RESCUE_TOP = int(os.environ.get("WIKI_RESCUE_TOP", "24"))
WIKI_NORM_DIST = int(os.environ.get("WIKI_NORM_DIST", "2"))
WIKI_RESOLVER_TIMEOUT_SEC = float(os.environ.get("WIKI_RESOLVER_TIMEOUT_SEC", "0.8"))
WIKI_CONCEPTS_TIMEOUT_SEC = float(os.environ.get("WIKI_CONCEPTS_TIMEOUT_SEC", "0.8"))
# PERF4: покарточный параллельный verify (design-c §2 шаг 3, решение владельца 18.09).
WIKI_VERIFY_WORKERS = int(os.environ.get("WIKI_VERIFY_WORKERS", "4"))

_HYBRID_SQL = None
_PASSPORT_SQL = None

WIKI_RESOLVER_SYS = (
    "Map the user question to numbered entity options (human labels and hints only). "
    "Return one JSON object: "
    '{"verdict":"one"|"many"|"none","concepts":[<tokens>]}'
    ". verdict one = exactly one option fits; many = several fit; none = no option fits. "
    "concepts = question tokens naming the entity, a measure, a kind, or a platform type "
    "(as opposed to data-filter values)."
)


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

# Покарточный verify (rescue шаг 3): один паспорт = один вызов, маленький контекст.
WIKI_CARD_VERIFY_SYS = (
    "Assess this entity passport against the user question. "
    "Passport fields: name, wiki excerpt, platform kind, axes, measures, "
    "traits present in this passport vs pool neighbors; "
    "doesNotAnswer lists topics marked outside entity coverage. "
    "Return one JSON object: "
    '{"fit": <"yes"|"no"|"unsure">, "why": <one line>}'
)


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


# типы метаданных 1С ($metadata), не слова домена.
# Родовые термины платформы — одинаковы для любой базы 1С. Длинные фразы
# раньше коротких: «регистр накопления» до «регистр», «журнал документов»
# до «журнал»/«документ».
_NAMED_PLATFORM_TYPE_PHRASES = (
    ("план видов характеристик", ("chartofcharacteristictypes",)),
    ("план видов расчёта", ("chartofcalculationtypes",)),
    ("регистр накопления", ("accumulationregister",)),
    ("регистр сведений", ("informationregister",)),
    ("регистр расчёта", ("calculationregister",)),
    ("регистр бухгалтерии", ("accountingregister",)),
    ("журнал документов", ("documentjournal",)),
    ("бизнес-процесс", ("businessprocess",)),
    ("план счетов", ("chartofaccounts",)),
    ("план обмена", ("exchangeplan",)),
    ("перечисление", ("enum",)),
    ("справочник", ("catalog",)),
    ("константа", ("constant",)),
    ("журнал", ("documentjournal",)),
    ("документ", ("document",)),
    ("регистр", (
        "accumulationregister",
        "informationregister",
        "calculationregister",
        "accountingregister",
    )),
    ("задача", ("task",)),
)

# Паттерны словоформ родовых терминов типов (конечный словарь платформы).
_NAMED_TYPE_WORD_RE = {
    "регистр": r"регистр(?:а|е|ом|у|ы|ов)?",
    # формы «движен*» — производные платформенного механизма регистров (iv);
    # многословная value-группа («движения денежных средств») не exclude:
    # _group_is_platform_only требует все слова группы платформенными.
    "движен": r"движен(?:и[еяю]|ий|иями|иям|иях|ием)?",
    "накопления": r"накоплен(?:ия|ие|ии|ием|ий)?",
    "сведений": r"сведен(?:ий|ия|ие|ии|ием|иям|иями|иях)?",
    "расчёта": r"расч[её]т(?:а|е|ом|у|ы|ов)?",
    "бухгалтерии": r"бухгалтер(?:ии|ия|ией|ию)?",
    "журнал": r"журнал(?:а|е|ом|у|ы|ов)?",
    "документов": r"документ(?:ов|а|е|ом|у|ы|ам|ами|ах)?",
    "документ": r"документ(?:а|е|ом|у|ы|ов|ам|ами|ах)?",
    "справочник": r"справочник(?:а|е|ом|у|и|ов|ам|ами|ах)?",
    "перечисление": r"перечислен(?:ие|ия|ии|ием|ий|ию)?",
    "план": r"план(?:а|е|ом|у|ы|ов)?",
    "видов": r"вид(?:ов|а|е|ом|у|ы|ам)?",
    "характеристик": r"характеристик(?:а|и|е|ой|у|ам|ами|ах)?",
    "счетов": r"сч[её]т(?:ов|а|е|ом|у|ы|ам)?",
    "обмена": r"обмен(?:а|е|ом|у|ы)?",
    "константа": r"констант(?:а|ы|е|ой|у|ам|ами|ах)?",
    "бизнес-процесс": r"бизнес(?:\s*|-)+процесс(?:а|е|ом|у|ы|ов)?",
    "задача": r"задач(?:а|и|е|ей|у|ам|ами|ах)?",
}

_NAMED_TYPE_PHRASE_RE = None


def _norm_ye(text):
    return (text or "").lower().replace("ё", "е")


def _named_type_phrase_patterns():
    """Скомпилировать фразы типов (один раз): границы слова, формы падежей."""
    global _NAMED_TYPE_PHRASE_RE
    if _NAMED_TYPE_PHRASE_RE is not None:
        return _NAMED_TYPE_PHRASE_RE
    out = []
    for phrase, kinds in _NAMED_PLATFORM_TYPE_PHRASES:
        parts = []
        for raw in phrase.split():
            key = raw
            pat = _NAMED_TYPE_WORD_RE.get(key) or _NAMED_TYPE_WORD_RE.get(
                _norm_ye(key))
            if not pat:
                pat = re.escape(_norm_ye(key))
            parts.append(pat)
        body = r"\s+".join(parts)
        cre = re.compile(
            r"(?<![а-яёa-z0-9_])" + body + r"(?![а-яёa-z0-9_])",
            re.IGNORECASE)
        out.append((cre, tuple(kinds)))
    _NAMED_TYPE_PHRASE_RE = out
    return out


def named_platform_kinds(question):
    """Допустимые OData-типы, если в вопросе назван род метаданных 1С.

    Пустой список — тип не назван (фильтр пула не трогает). «регистр» без
    уточнения → все *register. Длинные фразы раньше коротких.
    """
    q = _norm_ye(question)
    if not q.strip():
        return []
    for cre, kinds in _named_type_phrase_patterns():
        if cre.search(q):
            return list(kinds)
    return []


def _card_odata_kind(card):
    """OData-префикс карточки (platform kind) из src_table."""
    src = str((card or {}).get("src_table") or "")
    return src.split("_", 1)[0].lower() if src else ""


def filter_pool_by_named_type(question, cards, diag=None):
    """Исключить из пула карточки чужого типа, если тип назван в вопросе.

    Не добавляет кандидатов и не сортирует. Тип не назван → пул как был.
    После фильтра пустой пул — честное «нет такого типа» (каскад → no_data).
    """
    cards = list(cards or [])
    allowed = named_platform_kinds(question)
    if diag is not None:
        diag["named_type"] = list(allowed)
        diag["pool_before"] = len(cards)
    if not allowed:
        if diag is not None:
            diag["pool_after"] = len(cards)
        return cards
    out = [c for c in cards if _card_odata_kind(c) in allowed]
    if diag is not None:
        diag["pool_after"] = len(out)
        if len(cards) > 0 and len(out) == 0:
            diag["named_pool_zeroed"] = True
    return out


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


def _rescue_norm_glues(question, norm_glue=""):
    """Span-норм-склейки для struct_norm (>=2 токена, длина склейки >=8).

    design-c §2 шаг 1: против хвоста src_table — любой span с DL<=допуск,
    не склейка всего вопроса.
    """
    explicit = (norm_glue or "").strip()
    if explicit:
        g = _homonym_norm(explicit)
        return [g] if len(g) >= 8 else []
    seen = set()
    out = []
    for glue, _toks in _question_spans_glued(question or "", min_tokens=2):
        if len(glue) < 8 or glue in seen:
            continue
        seen.add(glue)
        out.append(glue)
    return out


def _wiki_hybrid_vars(question, intent, *, rescue_mode=False, norm_glue=""):
    intent = intent or {}
    ac = wiki_action_class(intent)
    ac_sql = ac if ac in ("event", "object") else "none"
    # [01.09] пул ищется по ПОИСКОВОЙ ФОРМЕ (вопрос без периода/чисел из
    # разбора): периодные слова утягивали kNN и словарь к карточкам периода
    # («закрытие месяца») и выталкивали верную карточку. LLM-шаги каскада
    # по-прежнему видят исходный вопрос.
    q_search = (intent.get("search_form") or "").strip() or (question or "")
    if rescue_mode:
        glues = _rescue_norm_glues(question, norm_glue=norm_glue)
        alias_top = WIKI_RESCUE_ALIAS_N
        # TOP+1: Python видит pre-limit и отличает потолок от ровно-TOP
        pick_limit = WIKI_RESCUE_TOP + 1
    else:
        # обычный каскад: struct_norm пуст (glue только если передан явно)
        glues = _rescue_norm_glues(question, norm_glue=norm_glue) if (
            norm_glue or "").strip() else []
        alias_top = WIKI_ALIAS_TOP
        pick_limit = WIKI_PICK_N
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
        "pick_limit": pick_limit,
        "alias_top": alias_top,
        "measure": (intent.get("measure") or "").replace("'", "''"),
        "rescue_mode": 1 if rescue_mode else 0,
        "norm_glues": glues,
        "norm_dist": WIKI_NORM_DIST,
    }


def _wiki_substitute_sql(template, vars_):
    out = template
    for key, val in vars_.items():
        if isinstance(val, int):
            rep = str(val)
        elif isinstance(val, (list, tuple)):
            # SQL list literal для UNNEST(:norm_glues)
            items = ["'%s'" % str(x).replace("'", "''") for x in val]
            rep = "[%s]" % ", ".join(items)
        else:
            rep = "'%s'" % str(val).replace("'", "''")
        out = out.replace(":%s" % key, rep)
        out = re.sub(r":'" + re.escape(key) + r"'", rep, out)
    return out


def wiki_hybrid_pool(question, intent=None, *, rescue_mode=False, norm_glue="",
                     diag=None):
    """kNN-топ-N → структурное сужение в SQL. Пустой пул — [].

    rescue_mode: без axis_ok/filtered, alias/pick потолки rescue, +norm.
    """
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
    vars_ = _wiki_hybrid_vars(
        question, intent, rescue_mode=rescue_mode, norm_glue=norm_glue)
    if rescue_mode and diag is not None:
        diag["rescue_no_axis_filter"] = True
        diag["wiki_rescue_alias_n"] = vars_["alias_top"]
        diag["wiki_rescue_top"] = WIKI_RESCUE_TOP
    qsql = _wiki_substitute_sql(sql_body, vars_)
    try:
        rows = psql(qsql)
    except RuntimeError:
        # fail-soft норм-слагаемого / SQL: пустой пул, не 503
        if rescue_mode and diag is not None:
            diag["wiki_rescue_sql_error"] = True
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
        # r[8]=platform_prefix (есть; Python kind — из src); r[9]=src_layer.
        src_layer = None
        if len(r) > 9 and r[9] is not None:
            try:
                src_layer = int(r[9])
            except (TypeError, ValueError):
                src_layer = None
        card = {
            "src_table": src,
            "name": (r[1] if len(r) > 1 else "") or "",
            "description": (r[2] if len(r) > 2 else "") or "",
            "axes": (r[3] if len(r) > 3 else "") or "",
            "measures": (r[4] if len(r) > 4 else "") or "",
            "covered": int(r[5] or 0) if len(r) > 5 else 0,
            "distance": float(r[6]) if len(r) > 6 and r[6] is not None else 1.0,
            "parent": parent,
            "platform_kind": wiki_platform_kind(src, parent),
        }
        if src_layer is not None:
            card["src_layer"] = src_layer
        out.append(card)
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


import re

# YAML-забор: три ASCII-дефиса. Unicode em-dash «—» (U+2014) НЕ разделитель.
_YAML_FENCE = re.compile(r"(?m)^---\s*$")
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_CAPTION_FORBIDDEN = (
    "pagetype:", "entitytype:", "canonicalid:",
    "\nid:", "id: entity.", "aliases:", "bestusedfor:", "notenoughfor:",
    "relationships:", "targetid:",
)


def wiki_strip_passport_yaml(text):
    """Тело wiki_pages / card.description → без YAML-frontmatter.

    Если текст начинается с забора --- … ---, берём хвост после закрывающего.
    Если забор встречается позже — берём префикс до первого забора
    (на случай «заголовок\\n---\\nmeta»). Em-dash «—» не режем.
    """
    t = (text or "").replace("\r\n", "\n")
    if not t.strip():
        return ""
    lines = t.split("\n")
    fence_idx = [i for i, ln in enumerate(lines) if _YAML_FENCE.match(ln)]
    if not fence_idx:
        return t.strip()
    if fence_idx[0] == 0 and len(fence_idx) >= 2:
        return "\n".join(lines[fence_idx[1] + 1:]).strip()
    if fence_idx[0] == 0:
        return ""  # только frontmatter, закрывающего нет
    return "\n".join(lines[:fence_idx[0]]).strip()


def wiki_caption_leaks(text):
    """True, если строка несёт паспортные ключи / YAML-забор / сырой src в backticks."""
    s = (text or "")
    if "---" in s and _YAML_FENCE.search(s):
        return True
    low = s.lower()
    if any(m in low for m in _CAPTION_FORBIDDEN):
        return True
    if "`" in s and looks_like_src_table(
            s.split("`")[1].strip() if s.count("`") >= 2 else ""):
        return True
    return False


def wiki_human_menu_caption(name, body, existing_label=""):
    """Единая санитарная подпись для ЛЮБОГО пункта меню из wiki-паспорта.

    Порядок: (1) name; (2) H1 после снятия YAML; (3) уже человеческий
    existing_label от mk_opts (с kind-различителем). Паспортные ключи
    отсекает wiki_caption_leaks.
    """
    name = (name or "").strip()
    existing = (existing_label or "").strip()
    human = wiki_strip_passport_yaml(body or "")
    h1 = ""
    for ln in human.splitlines():
        ln = ln.strip()
        if ln.startswith("#"):
            h1 = ln.lstrip("#").strip()
            break
    base_pre = (name or "").strip()
    h1_pre = h1.strip()
    # кандидаты-«грязные» не участвуют (U4-красная обход №1: фоллбек в name)
    name = base_pre if not wiki_caption_leaks(base_pre) else ""
    h1 = h1_pre if not wiki_caption_leaks(h1_pre) else ""
    base = name or h1
    # сохранить «Реализация ТМЦ (регистр…)» от disambiguate_labels, если чисто
    if (existing and not wiki_caption_leaks(existing)
            and base and base.lower() in existing.lower()):
        out = existing
    else:
        out = base or (existing if not wiki_caption_leaks(existing) else "")
    if wiki_caption_leaks(out):
        out = name or h1 or "вариант"
    if not out:
        # U4-красная обход №2: пустой результат не оставляет грязный prev
        out = "вариант"
    return out.strip()


def wiki_human_menu_hint(hint):
    """Hint без UUID и без паспортных ключей. Пусто — допустимо."""
    h = (hint or "").strip()
    if not h:
        return ""
    h = _UUID_RE.sub("", h)
    h = re.sub(r"\s{2,}", " ", h).strip(" ;,")
    if wiki_caption_leaks(h):
        return ""
    return h


def fork_labels_of(fork_key, srcs):
    """Проверенные подписи веток из `search_fork_label`: {src: label}. Пустые — пропуск.

    Таблицы нет / права нет — пусто (как у алиасов): исход B тогда недостижим → C.

    S1/B7: щель onepath (бывш. fork-детектор; W2-A1/W2-R1 — жива через
    wiki-clarify / currency mismatch).
    """
    srcs = [s for s in (srcs or []) if s]
    if not fork_key or not srcs:
        return {}
    try:
        rows = psql(
            "SELECT src, label FROM search_fork_label "
            "WHERE fork_key = %s AND src IN (%s) AND coalesce(label,'') <> ''"
            % (lit(fork_key), ", ".join(lit(s) for s in srcs)))
    except RuntimeError:
        return {}
    out = {}
    for r in rows or []:
        if r and r[0] and r[1] and str(r[1]).strip():
            out[r[0]] = str(r[1]).strip()
    return out


def fork_labels_covering(srcs):
    """Подписи для набора src: ключ словаря, покрывающий все src, иначе частичный.

    Возвращает ({src: label}, fork_key|None). Нужен, когда sha1(src_set¦ctx)
    детектора не совпал с ключом, под которым агент писал подписи.

    S1/B7: щель onepath (бывш. fork-детектор; W2-R1 — mk_opts ← wiki-clarify).
    """
    srcs = sorted({s for s in (srcs or []) if s})
    if not srcs:
        return {}, None
    try:
        rows = psql(
            "SELECT fork_key, src, label FROM search_fork_label "
            "WHERE src IN (%s) AND coalesce(label,'') <> ''"
            % ", ".join(lit(s) for s in srcs))
    except RuntimeError:
        return {}, None
    by_fk = {}
    for r in rows or []:
        if r and r[0] and r[1] and r[2] and str(r[2]).strip():
            by_fk.setdefault(r[0], {})[r[1]] = str(r[2]).strip()
    for k, m in by_fk.items():
        if all(s in m for s in srcs):
            return m, k
    merged = {}
    for m in by_fk.values():
        merged.update(m)
    return ({s: merged[s] for s in srcs if s in merged},
            next(iter(by_fk), None))


def wiki_menu_captions(options, passports_by_src=None, cards_by_src=None):
    """Единый форматтер подписей меню (формула №15 ступень 4; K4 §2.1).

    N вариантов на входе → N на выходе, порядок сохранён. Текст только из
    wiki-passport / card (те же поля, что wiki_format_passport_lines /
    wiki_format_card_lines). Без паспорта — человеческий label как есть.
    Без LLM, без фильтрации / слияния / сортировки / выбора главного.
    """
    passports_by_src = passports_by_src or {}
    cards_by_src = cards_by_src or {}
    out = []
    for opt in list(options or []):
        row = dict(opt)
        src = row.get("src") or ""
        name = ""
        body = ""
        p = passports_by_src.get(src) if src else None
        if isinstance(p, dict):
            name = (p.get("name") or "").strip()
            body = (p.get("wiki_body") or p.get("description") or "")
        else:
            c = cards_by_src.get(src) if src else None
            if isinstance(c, dict):
                name = (c.get("name") or "").strip()
                body = (c.get("description") or "")
        # даже без паспорта — прогнать уже лежащий label/hint (общее правило).
        # Kind-суффикс mk_opts (« (документ)») не терять: captions поверх
        # чистого label, вид дописывается после ровно один раз.
        prev = (row.get("label") or "").strip()
        kw = ""
        try:
            kw = (kind_word(src) or "") if src else ""
        except NameError:
            kw = ""
        kind_sfx = (" (%s)" % kw) if kw else ""
        had_kind = bool(kind_sfx and prev.endswith(kind_sfx))
        prev_clean = prev[: -len(kind_sfx)].rstrip() if had_kind else prev
        text = wiki_human_menu_caption(name, body, existing_label=prev_clean)
        if text:
            if had_kind and kind_sfx and not text.endswith(kind_sfx):
                text = "%s%s" % (text, kind_sfx)
            row["label"] = text
            row["wiki_caption"] = text
        if "hint" in row:
            row["hint"] = wiki_human_menu_hint(row.get("hint"))
        out.append(row)
    return out


def wiki_captions_map_from_cards(cards):
    """src_table → карточка/паспорт для wiki_menu_captions (порядок не трогает)."""
    out = {}
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        src = c.get("src_table") or ""
        if src:
            out[src] = c
    return out


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


_WIKI_VERIFY_FIT_MAP = {
    "yes": "yes", "no": "no", "unsure": "unsure",
    "подходит": "yes", "не_подходит": "no", "не подходит": "no",
    "сомневаюсь": "unsure",
}


def _wiki_row_to_verdict(row, n_passports):
    """Один объект verdict → нормализованная запись или None."""
    if not isinstance(row, dict):
        return None
    idx = row.get("index")
    if idx is None or not str(idx).strip().isdigit():
        return None
    i = int(idx)
    if i < 1 or i > n_passports:
        return None
    fit_raw = str(row.get("fit") or "").strip().lower()
    fit = _WIKI_VERIFY_FIT_MAP.get(
        fit_raw, fit_raw if fit_raw in ("yes", "no", "unsure") else "")
    if fit not in ("yes", "no", "unsure"):
        return None
    why = str(row.get("why") or "").strip()[:200]
    return {"index": i, "fit": fit, "why": why}


def _wiki_verdicts_from_rows(rows, n_passports):
    verdicts = []
    if not isinstance(rows, list):
        return verdicts
    for row in rows:
        v = _wiki_row_to_verdict(row, n_passports)
        if v:
            verdicts.append(v)
    return verdicts


def _wiki_salvage_verdicts(txt, n_passports):
    """Завершённые объекты verdict из обрезанного JSON массива verdicts."""
    verdicts = []
    m = re.search(r'"verdicts"\s*:\s*\[', txt)
    if not m:
        return verdicts
    pos = m.end()
    n_txt = len(txt)
    while pos < n_txt:
        while pos < n_txt and txt[pos] in " \t\n\r,":
            pos += 1
        if pos >= n_txt or txt[pos] == "]":
            break
        if txt[pos] != "{":
            break
        depth = 0
        start = pos
        end = None
        for i in range(pos, n_txt):
            ch = txt[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            break
        try:
            row = json.loads(txt[start:end])
        except (ValueError, TypeError):
            break
        v = _wiki_row_to_verdict(row, n_passports)
        if v:
            verdicts.append(v)
        pos = end
    return verdicts


def wiki_parse_verify_response(raw, n_passports):
    """Структурный разбор {verdicts:[{index, fit, why}]}.

    Возвращает (verdicts, mode): mode — full | salvage | failed.
    """
    txt = (raw or "").strip()
    if not txt or n_passports <= 0:
        return [], "failed"
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except (ValueError, KeyError, TypeError):
        salvaged = _wiki_salvage_verdicts(txt, n_passports)
        if salvaged:
            return salvaged, "salvage"
        return [], "failed"
    if not isinstance(j, dict):
        salvaged = _wiki_salvage_verdicts(txt, n_passports)
        if salvaged:
            return salvaged, "salvage"
        return [], "failed"
    rows = j.get("verdicts")
    if not isinstance(rows, list):
        salvaged = _wiki_salvage_verdicts(txt, n_passports)
        if salvaged:
            return salvaged, "salvage"
        return [], "failed"
    return _wiki_verdicts_from_rows(rows, n_passports), "full"


def _homonym_norm(s):
    """Та же нормализация, что у disambiguate_labels: lower + без пробелов."""
    return "".join(str(s).lower().split())


def _homonym_keys(passport):
    """Ключи имени/stem паспорта для одноимённости разных OData-kind."""
    p = passport or {}
    keys = set()
    name = (p.get("name") or "").strip()
    src = str(p.get("src_table") or "")
    if not name and src:
        # человеческий хвост после префикса (платформенное имя, не домен)
        try:
            name = (human_table_label(src) or "").strip()
        except NameError:
            parts = src.split("_", 1)
            name = parts[1] if len(parts) == 2 else ""
    n = _homonym_norm(name)
    if n:
        keys.add(n)
    if "_" in src:
        stem = _homonym_norm(src.split("_", 1)[1])
        if stem:
            keys.add(stem)
    return frozenset(keys)


def wiki_homonym_kind_peers(passports, focus_src):
    """Соседи focus с тем же name/stem и другим OData-kind. ≥2 → конфликт.

    Вердикт verify (yes/no) соседа не вычёркивает: лотерея как раз yes+no.
    """
    pool = [p for p in (passports or []) if p and p.get("src_table")]
    focus = next((p for p in pool if p["src_table"] == focus_src), None)
    if not focus or len(pool) < 2:
        return []
    fk = _homonym_keys(focus)
    if not fk:
        return []
    fkind = _card_odata_kind(focus)
    peers = [focus]
    for p in pool:
        if p["src_table"] == focus_src:
            continue
        if _card_odata_kind(p) == fkind:
            continue
        if fk & _homonym_keys(p):
            peers.append(p)
    return peers if len(peers) >= 2 else []


def wiki_load_cards_by_src(src_tables):
    """Догрузка карточек по src_table (штатная таблица search_wiki_entity_card)."""
    srcs = [s for s in (src_tables or []) if s]
    if not srcs:
        return {}
    lst = ", ".join(lit(s) for s in srcs)
    out = {}
    try:
        rows = psql(
            "SELECT c.src_table, c.name, c.description, c.axes, c.measures, "
            "c.covered, coalesce(t.parent, '') "
            "FROM search_wiki_entity_card c "
            "LEFT JOIN %s t ON t.src_table = c.src_table "
            "WHERE c.src_table IN (%s)" % (TABLES, lst))
    except RuntimeError:
        return {}
    for r in rows or []:
        if not r or not r[0]:
            continue
        src = str(r[0])
        parent = (r[6] if len(r) > 6 else "") or ""
        out[src] = {
            "src_table": src,
            "name": (r[1] if len(r) > 1 else "") or "",
            "description": (r[2] if len(r) > 2 else "") or "",
            "axes": (r[3] if len(r) > 3 else "") or "",
            "measures": (r[4] if len(r) > 4 else "") or "",
            "covered": int(r[5] or 0) if len(r) > 5 else 0,
            "parent": parent,
            "platform_kind": wiki_platform_kind(src, parent),
        }
    return out


def wiki_db_homonym_peer_rows(leader_src, label_norm):
    """Один SELECT: src_table с тем же норм-label и другим OData-префиксом.

    Stem — не критерий (канон D2). Без LIMIT на сборе. RuntimeError — наружу
    (fail-soft на амбиг-метке).
    """
    leader_src = (leader_src or "").strip()
    label_norm = (label_norm or "").strip()
    if not leader_src or not label_norm:
        return []
    lkind = leader_src.split("_", 1)[0].lower()
    rows = psql(
        "SELECT src_table, label FROM %s "
        "WHERE regexp_replace(lower(coalesce(label, '')), '\\s|\\p{Z}', '', 'g') = %s "
        "  AND src_table <> %s"
        % (TABLES, lit(label_norm), lit(leader_src)))
    out = []
    for r in rows or []:
        if not r or not r[0]:
            continue
        src = str(r[0])
        if src.split("_", 1)[0].lower() == lkind:
            continue
        out.append((src, (r[1] if len(r) > 1 else "") or ""))
    return out


def wiki_entity_clarify_menu(question, candidates, diag, cut, t0,
                             by=None, match="", preds=None,
                             *, reason="wiki_separability", intent=None, plan=None):
    """Общий конвейер clarify entity: mk_opts → captions → readings_menu.

    D2-гомоним (reason=wiki_homonym_db): skip_empty_filter — пир found=0 не
    выпадает; kind — из mk_opts/disambiguate_labels (fallback — один
    label_with_kind при сборке). Прочие wiki-меню — без skip и без пост-kind.
    """
    cands = [c for c in (candidates or []) if c]
    tied = []
    for c in cands:
        if isinstance(c, dict):
            src = c.get("src_table") or c.get("src") or ""
        else:
            src = str(c or "")
        if src and src not in tied:
            tied.append(src)
    if len(tied) < 2:
        return None
    try:
        lab_by = {
            r[0]: r[1] for r in psql(
                "SELECT src_table, label FROM %s WHERE src_table IN (%s)"
                % (TABLES, ", ".join(lit(c) for c in tied)))
            if r and len(r) > 1 and r[0]}
    except RuntimeError:
        lab_by = {}
    for c in cands:
        if not isinstance(c, dict):
            continue
        src = c.get("src_table") or c.get("src") or ""
        name = (c.get("name") or "").strip()
        if src and name and src not in lab_by:
            lab_by[src] = name
    window_preds = list(preds) if preds is not None else []
    is_homonym = reason == "wiki_homonym_db"
    # C1: skip+rebuild также для wiki_rescue и wiki_separability при full_pool
    _skip_rebuild = (
        is_homonym
        or reason == "wiki_rescue"
        or (reason == "wiki_separability" and bool((diag or {}).get("wiki_full_pool")))
    )
    opts = mk_opts(
        tied, lab_by, {}, by or {}, match=match or "", preds=window_preds,
        skip_empty_filter=_skip_rebuild)
    # rebuild при skip-ветке; иначе opts<2 → None как HEAD
    if _skip_rebuild and len(opts) < 2 and len(tied) >= 2:
        counted = by or {}
        opts = []
        for s in tied:
            raw = lab_by.get(s) or human_table_label(s)
            opts.append({
                "src": s,
                "label": label_with_kind(s, raw),
                "hint": "",
                "distinct_by": "",
                "found": counted.get(s, 0),
            })
    if len(opts) < 2:
        return None
    _pmap = wiki_captions_map_from_cards(cands)
    opts = wiki_menu_captions(opts, passports_by_src=_pmap)
    # D4: captions final then digests/kind-prior/highlight
    return finalize_clarify_menu(
        question, "entity", opts, diag, cut, t0, reason=reason,
        intent=intent, plan=plan, match=match or "", preds=preds,
        with_digests=True)


def wiki_homonym_peer_fail_soft(question, diag, cut, t0):
    """R6: амбиг-метка и сбой peer-SQL — текст без числа, не picked/leader."""
    d = dict(diag or {})
    d["wiki_homonym_peer_check"] = "error"
    d["wiki_pick"] = "homonym_peer_fail"
    text = ("не удалось проверить одноимённые источники; "
            "число без уточнения не подтверждаю")
    sec = round(time.time() - t0, 2) if t0 else None
    return {
        "partial": cut or None,
        "kind": "answer",
        "text": text,
        "atoms": [],
        "sources": [],
        "diag": _diag_pack(d, sec=sec),
    }


def wiki_leader_db_homonym_gate(leader, question, intent, diag, cut, t0,
                                by=None, match="", preds=None, plan=None):
    """После sole-yes: пиры из базы по label → clarify; иначе None (=leader)."""
    leader = (leader or "").strip()
    if not leader:
        return None
    try:
        rows = psql(
            "SELECT label FROM %s WHERE src_table = %s LIMIT 1"
            % (TABLES, lit(leader)))
    except RuntimeError:
        return wiki_homonym_peer_fail_soft(question, diag, cut, t0)
    label = ""
    if rows and rows[0] and rows[0][0]:
        label = str(rows[0][0])
    label_norm = _homonym_norm(label)
    if not label_norm:
        return None
    # штатная ambiguous_labels глотает SQL-сбой → пустой set → silent leader;
    # дешёвый свой check с пробросом ошибки (канон fail-soft, не swallow)
    try:
        cnt_rows = psql(
            "SELECT count(*) FROM %s WHERE regexp_replace(lower(coalesce(label, '')), '\\s|\\p{Z}', '', 'g') = %s"
            % (TABLES, lit(label_norm)))
    except RuntimeError:
        return wiki_homonym_peer_fail_soft(question, diag, cut, t0)
    n_peers = 0
    if cnt_rows and cnt_rows[0] and cnt_rows[0][0] is not None:
        try:
            n_peers = int(cnt_rows[0][0])
        except (TypeError, ValueError):
            n_peers = 0
    if n_peers <= 1:
        return None
    allowed = named_platform_kinds(question)
    leader_kind = _card_odata_kind({"src_table": leader})
    # named-kind ПЕРВЫМ: нет рода ≠ лидера в allowed → пиров быть не может → leader
    if allowed and not any(k != leader_kind for k in allowed):
        return None
    try:
        peer_rows = wiki_db_homonym_peer_rows(leader, label_norm)
    except RuntimeError:
        # R6 только когда после фильтра рода пир ещё возможен
        if allowed and not any(k != leader_kind for k in allowed):
            return None
        return wiki_homonym_peer_fail_soft(question, diag, cut, t0)
    peers_src = []
    for src, _lab in peer_rows:
        if allowed and _card_odata_kind({"src_table": src}) not in allowed:
            continue
        peers_src.append(src)
    if not peers_src:
        return None
    cards_by = wiki_load_cards_by_src([leader] + peers_src)
    candidates = []
    if leader in cards_by:
        candidates.append(cards_by[leader])
    else:
        candidates.append({"src_table": leader, "name": label})
    peer_lab = {s: l for s, l in peer_rows}
    for src in peers_src:
        if src in cards_by:
            candidates.append(cards_by[src])
        else:
            candidates.append({
                "src_table": src,
                "name": peer_lab.get(src) or label,
            })
    if diag is not None:
        diag["wiki_pick"] = "clarify"
        diag["wiki_homonym_db_peers"] = [
            c.get("src_table") for c in candidates]
    menu = wiki_entity_clarify_menu(
        question, candidates, diag, cut, t0,
        by=by, match=match, preds=preds,
        reason="wiki_homonym_db", intent=intent, plan=plan)
    if menu is not None:
        return menu
    return wiki_homonym_peer_fail_soft(question, diag, cut, t0)


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
    # В4 / решение 4-А: лидер только если ровно ОДИН не отвергнут (yes),
    # а ВСЕ остальные получили no. ≥2 неотвергнутых (два yes / yes+unsure) →
    # wiki-tie clarify. Пропуск вердикта ≠ no — в лидера не пускает.
    # S2-b: одноимённый peer другого kind → clarify, не silent leader.
    if (len(yes_i) == 1
            and len(no_i) == len(passports) - 1
            and not unsure_i):
        leader = passports[yes_i[0] - 1].get("src_table")
        if not wiki_validate_leader_axes(leader, intent):
            diag["wiki_verify"] = "axis_reject"
            return {"outcome": "none", "reason": "axis_reject", "diag": diag}
        peers = wiki_homonym_kind_peers(passports, leader)
        if peers:
            diag["wiki_verify"] = "clarify"
            diag["wiki_homonym_tie"] = [p.get("src_table") for p in peers]
            diag["wiki_homonym_blocked_leader"] = leader
            return {
                "outcome": "clarify",
                "candidates": peers,
                "diag": diag,
            }
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
            max_tokens=WIKI_VERIFY_MAX_TOKENS)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("ask DEGRADED: wiki verify без модели (%s)\n" % str(e)[:80])
        return {"outcome": "degraded", "diag": diag}
    verdicts, parse_mode = wiki_parse_verify_response(raw, len(full))
    if parse_mode == "salvage":
        diag["wiki_verify_truncated"] = 1
    if (raw or "").strip() and parse_mode == "failed":
        sys.stderr.write("ask DEGRADED: wiki verify ответ не разобран\n")
        diag["wiki_verify_n"] = len(full)
        return {"outcome": "degraded", "verdicts": [], "diag": diag}
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



# ── C1+C2: резолверный проход полного пула (design-c §2) ─────────────────────

def _term_group_primary(group):
    """Первая непустая альтернатива term-группы."""
    if isinstance(group, (list, tuple)):
        for a in group:
            s = str(a or "").strip()
            if s:
                return s
        return ""
    return str(group or "").strip()


def _term_group_norm(group):
    return _homonym_norm(_term_group_primary(group))


def _src_tail_norm(src):
    src = str(src or "")
    if "_" not in src:
        return ""
    return _homonym_norm(src.split("_", 1)[1])


def _src_label_norm(src, card=None):
    if card and (card.get("name") or "").strip():
        return _homonym_norm(card.get("name"))
    try:
        return _homonym_norm(human_table_label(src) or "")
    except Exception:  # noqa: BLE001
        return _src_tail_norm(src)


def _question_spans_glued(question, min_tokens=2):
    """Непрерывные >=min_tokens токена вопроса → норм-склейки (через границы групп)."""
    toks = [t for t in re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ]+", question or "") if t]
    out = []
    n = len(toks)
    for i in range(n):
        for j in range(i + min_tokens, n + 1):
            glue = _homonym_norm(" ".join(toks[i:j]))
            if glue:
                out.append((glue, toks[i:j]))
    return out


def _token_is_platform_word(tok):
    t = _norm_ye(tok or "")
    if not t:
        return False
    for _key, pat in _NAMED_TYPE_WORD_RE.items():
        cre = re.compile(
            r"(?<![а-яёa-z0-9_])" + pat + r"(?![а-яёa-z0-9_])",
            re.IGNORECASE)
        if cre.fullmatch(t):
            return True
    return False


def _group_is_platform_only(group):
    """(iv): вся группа — платформенные слова с границами; value-микс остаётся."""
    if isinstance(group, (list, tuple)):
        alts = [str(a or "").strip() for a in group if str(a or "").strip()]
    else:
        alts = [str(group or "").strip()] if str(group or "").strip() else []
    if not alts:
        return False
    # берём первичную форму; многословная value-группа с чужим токеном — False
    words = re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ]+", alts[0])
    if not words:
        return False
    return all(_token_is_platform_word(w) for w in words)


# (iii) кэш на проход: src+spans+targets не меняются внутри одного ask.
_III_SPAN_HIT_CACHE = {}


def _iii_span_targets(src, card=None):
    """Норм-хвост и норм-label выбранного src (длина >=8), без дублей."""
    targets = []
    tail = _src_tail_norm(src)
    if tail and len(tail) >= 8:
        targets.append(tail)
    lab = _src_label_norm(src, card)
    if lab and len(lab) >= 8 and lab not in targets:
        targets.append(lab)
    return targets


def _iii_cache_put(key, hits):
    if len(_III_SPAN_HIT_CACHE) >= 16:
        _III_SPAN_HIT_CACHE.clear()
    _III_SPAN_HIT_CACHE[key] = frozenset(hits)


def _iii_span_hit_glues(src, question, *, card=None, dist=None, diag=None,
                        src_layer=None):
    """(iii) hit-склейки одним SQL: штатный damerau_levenshtein, допуск WIKI_NORM_DIST.

    Доки: Sql › Functions › Text Functions › damerau_levenshtein;
          Sql › Query syntax › SELECT › unnest.
    Fail-soft: сбой → пустой set (слой (iii) недоступен), diag-факт.
    src_layer=2 (struct_norm): склейка уже совпала против хвоста в hybrid-SQL —
    переиспользуем факт без запроса: hit = склейки, для которых length-гард
    против хвоста совместим с допуском И (точный == хвост ИЛИ единственный
    кандидат); иначе — один SELECT тем же предикатом (точный список hit).
    """
    dist = WIKI_NORM_DIST if dist is None else dist
    spans = _question_spans_glued(question or "", min_tokens=2)
    glue_toks = {}
    glues = []
    for glue, toks in spans:
        if not glue or len(glue) < 8:
            continue
        if glue in glue_toks:
            continue
        glue_toks[glue] = list(toks)
        glues.append(glue)
    if not src or not glues:
        return set(), glue_toks

    targets = _iii_span_targets(src, card)
    if not targets:
        return set(), glue_toks

    layer = src_layer
    if layer is None and card is not None:
        layer = card.get("src_layer")
    try:
        layer = int(layer) if layer is not None else None
    except (TypeError, ValueError):
        layer = None

    cache_key = (str(src), tuple(glues), tuple(targets), int(dist), layer)
    cached = _III_SPAN_HIT_CACHE.get(cache_key)
    if cached is not None:
        return set(cached), glue_toks

    hits = set()
    # src_layer=2: struct_norm уже доказал EXISTS(glue↔хвост). Без запроса —
    # только когда список hit однозначен (exact == хвост или ровно один
    # length-совместимый кандидат); иначе падаем в SQL за точным DL.
    if layer == 2:
        tail = _src_tail_norm(src)
        if tail and len(tail) >= 8:
            exact = [g for g in glues if g == tail]
            compat = [g for g in glues if abs(len(g) - len(tail)) <= int(dist)]
            if exact:
                hits = set(exact)
            elif len(compat) == 1:
                hits = set(compat)
            # иначе — SQL ниже (точный DL движка)
            if hits:
                _iii_cache_put(cache_key, hits)
                return hits, glue_toks

    # Один SELECT на проход: unnest(склейки) × targets, штатный DL.
    glue_lit = "[%s]" % ", ".join(lit(g) for g in glues)
    target_lit = "[%s]" % ", ".join(lit(t) for t in targets)
    qsql = (
        "SELECT g.glue FROM unnest(%s) AS g(glue), unnest(%s) AS t(tgt) "
        "WHERE length(g.glue) >= 8 AND length(t.tgt) >= 8 "
        "AND damerau_levenshtein(g.glue, t.tgt) <= %d"
        % (glue_lit, target_lit, int(dist)))
    try:
        rows = psql(qsql)
    except Exception:  # noqa: BLE001 — fail-soft: (iii) недоступен
        if diag is not None:
            diag["conceptual_iii_sql_error"] = True
        _iii_cache_put(cache_key, ())
        return set(), glue_toks
    for r in rows or []:
        if r and r[0]:
            hits.add(str(r[0]))
    _iii_cache_put(cache_key, hits)
    return hits, glue_toks


def conceptual_term_group_norms(terms, *, intent=None, concepts=None, src=None,
                                question="", card=None, exact_matched=None,
                                diag=None, src_layer=None):
    """Единая понятийность (i)–(iv) → set норм-форм исключаемых term-групп.

    (i) measure/kind ∪ (ii) concepts ∪ (iii) span-DL к хвосту/label src ∪
    (iv) платформенные слова всей группой. Concepts не помечают exact-matched.
    (iii) — штатный damerau_levenshtein одним SQL на проход (не локальный DL).
    """
    intent = intent or {}
    exclude = set()
    # (i) слоты measure/kind
    for slot in ("measure", "kind"):
        raw = intent.get(slot)
        items = raw if isinstance(raw, (list, tuple)) else ([raw] if raw else [])
        for it in items:
            n = _homonym_norm(_intent_text(it) if callable(globals().get("_intent_text")) else str(it or ""))
            if not n and it is not None:
                n = _homonym_norm(str(it))
            if n:
                exclude.add(n)
    # (ii) concepts резолвера
    exact = set(_homonym_norm(x) for x in (exact_matched or []) if x)
    for c in (concepts or []):
        n = _homonym_norm(c)
        if n and n not in exact:
            exclude.add(n)
    # (iv) платформенные
    for g in (terms or []):
        if _group_is_platform_only(g):
            n = _term_group_norm(g)
            if n:
                exclude.add(n)
    # (iii) span-DL при известном src — безусловно (один SQL / кэш / src_layer=2)
    if src:
        hit_glues, glue_toks = _iii_span_hit_glues(
            src, question, card=card, diag=diag, src_layer=src_layer)
        hit_toks = set()
        for glue in hit_glues:
            exclude.add(glue)
            for t in glue_toks.get(glue) or []:
                hit_toks.add(_homonym_norm(t))
        for g in (terms or []):
            gn = _term_group_norm(g)
            if not gn:
                continue
            # группа пересекается с hit-токенами span
            gtoks = [_homonym_norm(t) for t in re.findall(
                r"[0-9a-zA-Zа-яА-ЯёЁ]+", _term_group_primary(g))]
            if any(t in hit_toks for t in gtoks):
                exclude.add(gn)
            # группа ≡ имя/хвост src
            if gn == _src_tail_norm(src) or gn == _src_label_norm(src, card):
                exclude.add(gn)
    return exclude


def filter_terms_by_concepts(terms, exclude_norms, diag=None):
    """Исключить понятийные term-группы; вернуть (kept, skipped)."""
    kept, skipped = [], []
    excl = set(exclude_norms or [])
    for g in (terms or []):
        n = _term_group_norm(g)
        if n and n in excl:
            skipped.append(g)
        else:
            # также: любая альтернатива группы в excl
            alts = g if isinstance(g, (list, tuple)) else [g]
            if any(_homonym_norm(a) in excl for a in alts if a):
                skipped.append(g)
            else:
                kept.append(g)
    if diag is not None and skipped:
        diag["probe_terms_skipped"] = [
            _term_group_primary(g) for g in skipped]
        diag["conceptual_exclude_n"] = len(skipped)
    return kept, skipped


def _wiki_resolver_budget_sec(*, concepts_only=False):
    try:
        rem = _deadline_remaining_sec()
    except Exception:  # noqa: BLE001
        rem = None
    wait = (WIKI_CONCEPTS_TIMEOUT_SEC if concepts_only
            else WIKI_RESOLVER_TIMEOUT_SEC)
    if rem is not None:
        wait = min(wait, float(rem))
    return max(0.0, wait)


def wiki_pool_resolver(question, cards, diag=None, *, concepts_only=False):
    """Один LLM-вызов: трихотомия + concepts. Fail-soft; ★ не пишет.

    Образец бюджета — llm_option_highlight (<=800 мс). Вход: вопрос + label+hint.
    """
    diag = diag if isinstance(diag, dict) else {}
    cards = list(cards or [])
    out = {"verdict": None, "concepts": [], "ok": False, "fail": False}
    if not cards:
        out["fail"] = True
        return out
    if deadline_hit():
        out["fail"] = True
        diag["wiki_resolver"] = "deadline"
        return out
    wait = _wiki_resolver_budget_sec(concepts_only=concepts_only)
    if wait <= 0:
        out["fail"] = True
        diag["wiki_resolver"] = "no_budget"
        return out
    # вход LLM <= PICK_BUDGET
    lines, used = [], []
    budget = int(globals().get("PICK_BUDGET") or 8000)
    size = 0
    truncated = False
    for i, c in enumerate(cards):
        lab = (c.get("name") or "").strip() or human_table_label(c.get("src_table") or "")
        hint = (c.get("description") or "").strip()[:80]
        if not lab:
            continue
        row = "%d. %s%s" % (len(used) + 1, lab, (" (%s)" % hint) if hint else "")
        if size + len(row) + 1 > budget and used:
            truncated = True
            break
        used.append(c)
        lines.append(row)
        size += len(row) + 1
    if truncated:
        diag["resolver_input_truncated"] = True
    if len(used) < 1:
        out["fail"] = True
        return out
    prompt = (
        "Q: %s\nOptions:\n%s\n"
        "Reply with JSON {\"verdict\":\"one|many|none\",\"concepts\":[...]}."
        % (str(question or "").strip(), "\n".join(lines)))
    messages = [
        {"role": "system", "content": WIKI_RESOLVER_SYS},
        {"role": "user", "content": prompt},
    ]
    raw = ""
    try:
        body = _ds_chat_body(messages, temperature=0, max_tokens=200)
        if deadline_hit():
            out["fail"] = True
            diag["wiki_resolver"] = "deadline"
            return out
        req = urllib.request.Request(
            DS_BASE + "/v1/chat/completions",
            data=json.dumps(body).encode(), method="POST")
        req.add_header("Authorization", "Bearer " + (DS_KEY or ""))
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=wait) as r:
            data = json.loads(r.read())
        raw = (_ds_chat_content(data) or "").strip()
    except Exception as e:  # noqa: BLE001
        out["fail"] = True
        diag["wiki_resolver"] = "error"
        diag["wiki_resolver_err"] = str(e)[:80]
        return out
    try:
        j = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, KeyError, TypeError):
        out["fail"] = True
        diag["wiki_resolver"] = "unparseable"
        return out
    if not isinstance(j, dict):
        out["fail"] = True
        return out
    verd = str(j.get("verdict") or "").strip().lower()
    if verd in ("one", "exactly one", "1"):
        verd = "one"
    elif verd in ("many", "several", "multi", "multiple"):
        verd = "many"
    elif verd in ("none", "no", "zero", "0"):
        verd = "none"
    else:
        verd = None
    concepts = []
    raw_c = j.get("concepts")
    if isinstance(raw_c, list):
        for x in raw_c:
            s = str(x or "").strip()
            if s:
                concepts.append(s)
    out["verdict"] = verd if not concepts_only else None
    out["concepts"] = concepts
    out["ok"] = True
    diag["wiki_resolver"] = verd or ("concepts" if concepts_only else "ok")
    # успех (в т.ч. пустой список) = отвечено; LLM больше не зовётся
    diag["rescue_concepts"] = list(concepts)
    return out


def wiki_concepts_call(question, cards, diag=None, *, retry=True):
    """Concepts-вызов с одним inline-повтором при первом fail (<=800 мс)."""
    diag = diag if isinstance(diag, dict) else {}
    r1 = wiki_pool_resolver(question, cards, diag, concepts_only=True)
    if r1.get("ok"):
        return r1
    if retry:
        diag["wiki_concepts_retry"] = True
        r2 = wiki_pool_resolver(question, cards, diag, concepts_only=True)
        if r2.get("ok"):
            return r2
        diag["wiki_concepts_unavailable"] = True
        return r2
    diag["wiki_concepts_unavailable"] = True
    return r1


def wiki_passport_enrich_slice(cards, cache=None, *, distinct_against=None):
    """Enrich ПОЛНЫМ body на переданный слайс (не только первые 8).

    cache: опциональный dict src_table → {wiki_body, parent, not_enough_for};
    живёт только внутри одного прохода (передаёт caller параметром, не через diag),
    между HTTP-запросами не шарится. Пишем только успешные body.
    distinct_against: пул для wiki_passport_distinct (покарточный verify — весь pool).
    """
    cards = list(cards or [])
    if not cards:
        return []
    by_src = {}
    # обходим срез WIKI_PASSPORT_N: подставляем весь слайс
    srcs = [c.get("src_table") for c in cards if c.get("src_table")]
    if not srcs:
        return [dict(c) for c in cards]
    missing = []
    seen_miss = set()
    for s in srcs:
        if cache is not None and s in cache:
            by_src[s] = cache[s]
        elif s not in seen_miss:
            seen_miss.add(s)
            missing.append(s)
    if missing:
        template = _wiki_passport_sql()
        if template.strip().startswith("\\set"):
            template = "\n".join(
                ln for ln in template.splitlines()
                if not ln.strip().startswith("\\set"))
        lst = ", ".join("'%s'" % str(s).replace("'", "''") for s in missing)
        qsql = template.replace(":src_list", lst).replace(
            ":body_max", str(WIKI_PASSPORT_BODY_MAX))
        try:
            for r in psql(qsql) or []:
                if not r or not r[0]:
                    continue
                entry = {
                    "wiki_body": (r[2] if len(r) > 2 else "") or "",
                    "parent": (r[5] if len(r) > 5 else "") or "",
                    "not_enough_for": (r[7] if len(r) > 7 else "") or "",
                }
                key = str(r[0])
                by_src[key] = entry
                # кэш только успешный body; miss/ошибка/пустой SQL — без записи
                if cache is not None and entry.get("wiki_body"):
                    cache[key] = entry
        except RuntimeError:
            pass
    distinct_pool = (list(distinct_against)
                     if distinct_against is not None else cards)
    out = []
    for c in cards:
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
        row["distinct"] = wiki_passport_distinct(row, distinct_pool)
        out.append(row)
    return out


def _wiki_parse_card_verify(raw):
    """Разбор ответа покарточного verify: flat {fit,why} или verdicts[index=1]."""
    verdicts, mode = wiki_parse_verify_response(raw, 1)
    if verdicts:
        return verdicts[0], mode
    txt = (raw or "").strip()
    if not txt:
        return None, "failed"
    try:
        j = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except (ValueError, KeyError, TypeError):
        return None, "failed"
    if not isinstance(j, dict):
        return None, "failed"
    if "fit" in j:
        v = _wiki_row_to_verdict({"index": 1, "fit": j.get("fit"),
                                 "why": j.get("why")}, 1)
        if v:
            return v, "full"
    return None, "failed"


def wiki_batch_verify(question, intent, cards, diag=None, *, passport_cache=None):
    """Покарточный параллельный verify (design-c §2 шаг 3, PERF4).

    1 карточка = 1 ds_chat; ThreadPoolExecutor(WIKI_VERIFY_WORKERS).
    Гейт бюджета: deadline_hit() перед СТАРТОМ каждого вызова модели;
    уже стартовавшие дозавершаются и вливаются. Кэш паспортов — параметром
    (не diag). Имя wiki_batch_verify сохранено: замки мокают его.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    diag = dict(diag or {})
    cards = list(cards or [])
    if not cards:
        return {"verdicts_by_src": {}, "passports": [], "incomplete": False,
                "diag": diag}
    if passport_cache is not None and not isinstance(passport_cache, dict):
        passport_cache = None
    # backward compat: старый путь через diag (до PERF4) — читаем, не пишем
    if passport_cache is None:
        legacy = diag.get("_wiki_passport_cache")
        if isinstance(legacy, dict):
            passport_cache = legacy

    workers = max(1, int(WIKI_VERIFY_WORKERS or 1))
    cache_lock = threading.Lock()
    by_src = {}
    all_passports = []
    incomplete = False
    started_n = 0
    skipped_n = 0
    err_last = None
    pool_cards = cards  # distinct vs полный входной пул этого вызова
    # Промт карточки собирается здесь (главный поток): kind/_intent_text
    # фиксируются аргументом, а не повторным чтением в воркере (PERF6).
    ask_text = question or ""
    kind = _intent_text((intent or {}).get("kind"))
    if kind:
        ask_text = "%s (%s)" % (ask_text, kind)

    def _enrich_one(card):
        try:
            with cache_lock:
                return wiki_passport_enrich_slice(
                    [card], cache=passport_cache, distinct_against=pool_cards)
        except TypeError as e:
            msg = str(e)
            # мок замка без cache=/distinct_against=
            if "unexpected keyword argument" in msg:
                try:
                    with cache_lock:
                        return wiki_passport_enrich_slice(
                            [card], cache=passport_cache)
                except TypeError:
                    return wiki_passport_enrich_slice([card])
            raise

    def _verify_one(card, ask_text=ask_text):
        nonlocal started_n, skipped_n, err_last
        src = card.get("src_table")
        enriched = _enrich_one(card)
        p = enriched[0] if enriched else dict(card)
        listing = wiki_format_passport_lines([p])
        # гейт СТАРТА вызова модели (решение владельца): сериализован —
        # число вызовов у границы времени может превышать последовательный.
        # rid и token_acc живут в ContextVar; пул наследует их через
        # copy_context().run на каждом submit (PERF6).
        with cache_lock:
            if deadline_hit():
                skipped_n += 1
                return {"src": src, "passport": p, "verdict": None,
                        "skipped": True}
            rem = _deadline_remaining_sec()
            if rem is not None and rem <= 0:
                skipped_n += 1
                return {"src": src, "passport": p, "verdict": None,
                        "skipped": True}
            started_n += 1
        try:
            raw = ds_chat(
                [{"role": "system", "content": WIKI_CARD_VERIFY_SYS},
                 {"role": "user", "content": "%s\n\nPassport:\n%s"
                  % (ask_text, listing)}],
                max_tokens=WIKI_VERIFY_MAX_TOKENS)
        except Exception as e:  # noqa: BLE001
            with cache_lock:
                err_last = str(e)[:80]
            return {"src": src, "passport": p, "verdict": None, "error": True}
        v, parse_mode = _wiki_parse_card_verify(raw)
        if parse_mode == "failed" and (raw or "").strip():
            return {"src": src, "passport": p, "verdict": None,
                    "parse_failed": True}
        return {"src": src, "passport": p, "verdict": v, "skipped": False}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Снимок ContextVar главного потока на каждый submit (rid, token_acc).
        futs = [pool.submit(contextvars.copy_context().run, _verify_one, c)
                for c in cards]
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                incomplete = True
                err_last = str(e)[:80]
                continue
            if not r:
                incomplete = True
                continue
            p = r.get("passport")
            src = r.get("src")
            if p and src:
                all_passports.append(p)
            if r.get("skipped") or r.get("error") or r.get("parse_failed"):
                incomplete = True
                continue
            v = r.get("verdict")
            if src and v:
                by_src[src] = v
            elif src:
                incomplete = True

    if skipped_n:
        diag["wiki_batch_verify_deadline"] = True
        diag["wiki_card_verify_deadline"] = True
    if err_last:
        diag["wiki_batch_verify_error"] = err_last
        diag["wiki_card_verify_error"] = err_last
    diag["wiki_batch_verify_n"] = started_n
    diag["wiki_card_verify_n"] = started_n
    diag["wiki_card_verify_workers"] = workers
    diag["wiki_batch_verdicts"] = len(by_src)
    diag["wiki_card_verdicts"] = len(by_src)
    return {
        "verdicts_by_src": by_src,
        "passports": all_passports,
        "incomplete": incomplete or len(by_src) < len(cards),
        "diag": diag,
    }


def wiki_outcome_from_full_verify(verdicts_by_src, pool, intent, diag=None,
                                  *, ceiling_hit=False):
    """Исход verify на ПОЛНОМ финальном пуле (копипаста :1110 с срезом — нет).

    sole = ровно 1 yes ∧ все прочие no ∧ |verdicts|==|pool| ∧ ¬ceiling_hit.
    """
    diag = dict(diag or {})
    pool = list(pool or [])
    if not pool:
        return {"outcome": "none", "reason": "empty_pool", "diag": diag}
    if ceiling_hit:
        diag["wiki_ceiling_hit"] = True
    vb = verdicts_by_src or {}
    yes_src, unsure_src, no_src, missing = [], [], [], []
    for c in pool:
        src = c.get("src_table")
        v = vb.get(src)
        if not v:
            missing.append(src)
            continue
        fit = v.get("fit")
        if fit == "yes":
            yes_src.append(src)
        elif fit == "unsure":
            unsure_src.append(src)
        else:
            no_src.append(src)
    diag["wiki_verify_yes"] = len(yes_src)
    diag["wiki_verify_unsure"] = len(unsure_src)
    diag["wiki_verify_no"] = len(no_src)
    diag["wiki_verify_missing"] = len(missing)
    complete = (len(missing) == 0 and len(vb) >= len(pool)
                and not ceiling_hit)
    # sole только при полном вердикте и без потолка
    if (complete and len(yes_src) == 1 and not unsure_src
            and len(no_src) == len(pool) - 1):
        leader = yes_src[0]
        if not wiki_validate_leader_axes(leader, intent):
            diag["wiki_verify"] = "axis_reject"
            return {"outcome": "none", "reason": "axis_reject", "diag": diag}
        peers = wiki_homonym_kind_peers(
            [{"src_table": c.get("src_table"), "name": c.get("name")}
             for c in pool], leader)
        if peers:
            diag["wiki_verify"] = "clarify"
            diag["wiki_homonym_tie"] = [p.get("src_table") for p in peers]
            diag["wiki_homonym_blocked_leader"] = leader
            return {"outcome": "clarify", "candidates": peers,
                    "reason": "homonym", "diag": diag}
        diag["wiki_verify"] = leader
        return {"outcome": "leader", "leader": leader, "diag": diag}
    if missing:
        return {"outcome": "incomplete", "reason": "verdicts_incomplete",
                "diag": diag}
    if len(yes_src) == 0 and not unsure_src:
        diag["wiki_verify"] = "none"
        return {"outcome": "none", "reason": "verify_none", "diag": diag}
    tie = []
    seen = set()
    for src in yes_src + unsure_src:
        if src not in seen:
            seen.add(src)
            card = next((c for c in pool if c.get("src_table") == src), None)
            tie.append(card or {"src_table": src})
    if len(tie) >= 2:
        diag["wiki_verify"] = "clarify"
        diag["wiki_verify_tie"] = [c.get("src_table") for c in tie]
        return {"outcome": "clarify", "candidates": tie,
                "reason": "separability", "diag": diag}
    diag["wiki_verify"] = "none"
    return {"outcome": "none", "reason": "verify_none", "diag": diag}


def _stamp_rescue_concepts(menu, concepts, *, pending=False):
    if not isinstance(menu, dict) or menu.get("kind") != "clarify":
        return menu
    for o in menu.get("options") or []:
        if not isinstance(o, dict):
            continue
        # Entity-опция: measure consume-bypass в option не эмитится (design-c §2);
        # сдираем, если попали чужим путём (вторая линия к гарду issue_decision).
        o.pop("measure_verdict", None)
        o.pop("answer_mode", None)
        o.pop("digest_form", None)
        if pending:
            o["rescue_concepts_pending"] = True
            # pending ≠ ответ; повтор — прерогатива consume
            o.pop("rescue_concepts", None)
        else:
            # успех (в т.ч. пустой) = отвечено
            o["rescue_concepts"] = list(concepts or [])
    return menu


def _rescue_menu_or_degrade(question, pool, diag, cut, t0, *, reason="wiki_rescue",
                            intent=None, plan=None, by=None, match="", preds=None,
                            concepts=None, pending=False):
    """Меню всего пула; None при живом пуле → деградация R-I (повтор меню/R-D)."""
    pool = list(pool or [])
    if len(pool) < 2:
        return None  # caller → R-D
    menu = wiki_entity_clarify_menu(
        question, pool, diag, cut, t0,
        by=by, match=match, preds=preds,
        reason=reason, intent=intent, plan=plan)
    if menu is None and len(pool) >= 2:
        # R-I: деградация — rebuild opts вручную + finalize
        diag["wiki_rescue_menu_degraded"] = True
        tied = [c.get("src_table") for c in pool if c.get("src_table")]
        opts = []
        for s, c in zip(tied, pool):
            raw = (c.get("name") or "").strip() or human_table_label(s)
            opts.append({
                "src": s,
                "label": label_with_kind(s, raw) if callable(globals().get("label_with_kind")) else raw,
                "hint": "",
                "distinct_by": "",
                "found": (by or {}).get(s, 0),
            })
        if len(opts) >= 2:
            menu = finalize_clarify_menu(
                question, "entity", opts, diag, cut, t0, reason=reason,
                intent=intent, plan=plan, match=match or "", preds=preds,
                with_digests=True)
    if menu is not None:
        menu = _stamp_rescue_concepts(menu, concepts, pending=pending)
    return menu


def _rescue_no_data(question, diag, cut, t0, reason):
    return {
        "kind": "no_data",
        "partial": cut or None,
        "text": NO_DATA_TEXT or refuse_text(question),
        "sources": [],
        "diag": _diag_pack(diag, sec=round(time.time() - t0, 2), reason=reason),
    }


def wiki_rescue_full_pool_pass(question, intent, diag, cut, t0,
                               by=None, match="", preds=None, plan=None,
                               *, origin="cascade"):
    """ТОЧКА 1 / escalate: сборка rescue_pool → покарточный verify → резолвер → исход."""
    diag = diag if isinstance(diag, dict) else {}
    intent = intent or {}
    plan = plan or {}
    # однократность прохода: повторный вход (любой origin) — прежний исход
    if diag.get("wiki_full_pool") or diag.get("wiki_rescue_escalated"):
        return None
    # дедлайн до входа — прежний исход; штамп однократности не сжигается
    _dh = globals().get("deadline_hit")
    if callable(_dh) and _dh():
        return None
    diag["wiki_full_pool"] = True
    diag["wiki_rescue_origin"] = origin
    if origin == "escalate":
        diag["wiki_rescue_escalated"] = True

    # PERF4: кэш паспортов локально в проходе, параметром (НЕ diag — п.16).
    passport_cache = {}
    sec_pool = 0.0
    sec_verify = 0.0
    sec_resolver = 0.0
    sec_menu = [0.0]

    def _stamp_stages():
        # ДО любого _diag_pack (красная №2); тел паспортов в diag нет.
        # Идемпотентно: повторный вызов (в т.ч. finally) обновляет ключи in-place,
        # не плодит дубли; shallow-copy в _diag_pack видит финальные значения.
        stages = diag.get("wiki_rescue_stage_sec")
        if not isinstance(stages, dict):
            stages = {}
            diag["wiki_rescue_stage_sec"] = stages
        stages["pool"] = round(sec_pool, 1)
        stages["verify"] = round(sec_verify, 1)
        stages["resolver"] = round(sec_resolver, 1)
        stages["menu"] = round(sec_menu[0], 1)
        diag.pop("_wiki_passport_cache", None)  # страховка от чужого наследия

    try:  # stamp в finally + явный stamp перед pack-путями
        # шаг 1 — rescue_pool
        _tp0 = time.monotonic()
        try:
            pool = wiki_hybrid_pool(
                question, intent, rescue_mode=True, diag=diag)
        except Exception as e:  # noqa: BLE001
            diag["wiki_rescue_pool_error"] = str(e)[:80]
            pool = []
        sec_pool = time.monotonic() - _tp0
        # named-фильтр на rescue пропускаем: флаг named_pool_zeroed — с каскада;
        # force_menu ниже держит sole при этом флаге.
        # SQL вернул TOP+1; ceiling_hit := pre-limit > WIKI_RESCUE_TOP
        pre_count = len(pool)
        ceiling_hit = pre_count > WIKI_RESCUE_TOP
        if ceiling_hit:
            diag["wiki_rescue_truncated"] = pre_count - WIKI_RESCUE_TOP
            pool = pool[:WIKI_RESCUE_TOP]
        else:
            diag["wiki_rescue_truncated"] = 0
        diag["wiki_rescue_pool_n"] = len(pool)
        diag["wiki_rescue_pre_count"] = pre_count
        diag["wiki_rescue_pool"] = [c.get("src_table") for c in pool]

        # шаг 2 — пуст → прежний честный no_data
        if not pool:
            return None  # caller сохраняет прежний исход

        force_menu = bool(diag.get("named_pool_zeroed"))

        # R-I: дедлайн после входа
        if deadline_hit():
            diag["wiki_rescue_ri"] = "deadline"
            if len(pool) >= 2:
                _tm0 = time.monotonic()
                _stamp_stages()
                menu = _rescue_menu_or_degrade(
                    question, pool, diag, cut, t0, reason="wiki_rescue",
                    intent=intent, plan=plan, by=by, match=match, preds=preds)
                sec_menu[0] += time.monotonic() - _tm0
                if menu is not None:
                    return menu
            return None

        # шаг 3 — покарточный параллельный verify
        _tv0 = time.monotonic()
        try:
            batch = wiki_batch_verify(
                question, intent, pool, diag=diag,
                passport_cache=passport_cache)
        except TypeError as e:
            # мок замка без passport_cache=
            if "passport_cache" in str(e):
                batch = wiki_batch_verify(
                    question, intent, pool, diag=diag)
            else:
                raise
        sec_verify = time.monotonic() - _tv0
        diag.update(batch.get("diag") or {})
        # ceiling_hit = pre-limit>TOP only; named_pool_zeroed stays its own diag key
        # (sole held by force_menu below, without wiki_ceiling_hit)
        outcome = wiki_outcome_from_full_verify(
            batch.get("verdicts_by_src") or {}, pool, intent, diag=diag,
            ceiling_hit=ceiling_hit)

        # шаг 4 — резолвер один раз; трихотомия до sole
        concepts = []
        concepts_pending = False
        resolver = {"ok": False, "fail": True, "verdict": None, "concepts": []}
        provisional_sole = outcome.get("outcome") == "leader"
        _tr0 = time.monotonic()
        try:
            resolver = wiki_pool_resolver(question, pool, diag)
            if resolver.get("ok"):
                concepts = list(resolver.get("concepts") or [])
            else:
                # один inline-повтор
                diag["wiki_resolver_retry"] = True
                resolver = wiki_pool_resolver(question, pool, diag)
                if resolver.get("ok"):
                    concepts = list(resolver.get("concepts") or [])
                else:
                    concepts_pending = True
                    diag["wiki_concepts_unavailable"] = True
        except Exception as e:  # noqa: BLE001
            concepts_pending = True
            diag["wiki_resolver_err"] = str(e)[:80]
        sec_resolver = time.monotonic() - _tr0

        # успех (в т.ч. пустой) = отвечено; pending ≠ ответ (повтор — consume)
        if concepts_pending:
            diag.pop("rescue_concepts", None)
            diag["rescue_concepts_pending"] = True
        else:
            diag["rescue_concepts"] = list(concepts)

        verd = resolver.get("verdict") if resolver.get("ok") else None

        def _nd(reason):
            _stamp_stages()
            return _rescue_no_data(question, diag, cut, t0, reason)

        def _menu(reason="wiki_rescue", cands=None):
            cands = cands if cands is not None else pool
            if len(cands) < 2:
                _stamp_stages()  # до pack на caller fail_soft / early paths
                return None
            _tm0 = time.monotonic()
            try:
                _stamp_stages()  # до pack внутри меню
                return _rescue_menu_or_degrade(
                    question, cands, diag, cut, t0, reason=reason,
                    intent=intent, plan=plan, by=by, match=match, preds=preds,
                    concepts=concepts, pending=concepts_pending)
            finally:
                sec_menu[0] += time.monotonic() - _tm0

        def _finish_sole(leader):
            # штамп ДО post_verify / db-гомоним-гейта / любых упакованных возвратов
            _stamp_stages()
            # demote ТОЛЬКО при fail/pending (§2 шаг 3(a)); пустой OK = ответ
            _concepts_gap = (
                concepts_pending
                or (resolver.get("fail") and not resolver.get("ok")))
            if _concepts_gap:
                excl = conceptual_term_group_norms(
                    intent.get("terms") or [], intent=intent, concepts=[],
                    src=leader, question=question)
                remaining_non = False
                for g in (intent.get("terms") or []):
                    n = _term_group_norm(g)
                    if n and n not in excl and not _group_is_platform_only(g):
                        remaining_non = True
                        break
                if remaining_non:
                    m = _menu()
                    if m is not None:
                        return m
                    return _nd("wiki_rescue_demote")
            if not wiki_leader_post_verify(leader, intent, question, diag):
                return _nd("wiki_post_verify_fail")
            gated = wiki_leader_db_homonym_gate(
                leader, question, intent, diag, cut, t0,
                by=by, match=match, preds=preds, plan=plan)
            if gated is not None:
                return _stamp_rescue_concepts(
                    gated, concepts, pending=concepts_pending)
            lead_card = next((c for c in pool if c.get("src_table") == leader), None)
            marks = {}
            if lead_card and lead_card.get("src_layer") is not None:
                diag["src_layer"] = lead_card.get("src_layer")
            _out = {"picked": [leader], "marks": marks, "plan": plan}
            if concepts_pending:
                _out["rescue_concepts_pending"] = True
            else:
                # успех (в т.ч. пустой) = отвечено
                _out["rescue_concepts"] = list(concepts)
            return _out

        # --- таблица (a)/(b)/(b2)/(c) ---
        # (a) sole-yes: concepts-only уже получены; трихотомия игнорируется
        if provisional_sole and not force_menu:
            return _finish_sole(outcome.get("leader"))

        # (b) in-pool kind-гомоним
        if outcome.get("outcome") == "clarify" and outcome.get("reason") == "homonym":
            m = _menu(reason="wiki_homonym_db", cands=outcome.get("candidates") or pool)
            if m is not None:
                return m
            _stamp_stages()
            return wiki_homonym_peer_fail_soft(question, diag, cut, t0)

        # (b2) verify-clarify >=2: tie → wiki_separability; полный пул — fallback
        if outcome.get("outcome") == "clarify":
            if outcome.get("reason") == "separability":
                reason = "wiki_separability"
            else:
                reason = ("wiki_rescue" if origin != "cascade"
                          else "wiki_separability")
            m = _menu(reason=reason, cands=outcome.get("candidates") or pool)
            if m is not None:
                return m
            m = _menu(reason="wiki_rescue", cands=pool)
            if m is not None:
                return m
            return None

        # (c) none/unsure/неполнота — трихотомия читается
        if outcome.get("outcome") == "incomplete":
            # verd==one + неполный вердикт → дозапрос батчей; sole → путь (a)
            if verd == "one":
                vb = dict(batch.get("verdicts_by_src") or {})
                missing = [c for c in pool if c.get("src_table") not in vb]
                if missing and not deadline_hit():
                    diag["wiki_batch_verify_refetch"] = True
                    diag["wiki_card_verify_refetch"] = True
                    _tv1 = time.monotonic()
                    try:
                        batch2 = wiki_batch_verify(
                            question, intent, missing, diag=diag,
                            passport_cache=passport_cache)
                    except TypeError as e:
                        if "passport_cache" in str(e):
                            batch2 = wiki_batch_verify(
                                question, intent, missing, diag=diag)
                        else:
                            raise
                    sec_verify += time.monotonic() - _tv1
                    vb.update(batch2.get("verdicts_by_src") or {})
                    diag.update(batch2.get("diag") or {})
                    batch = {
                        "verdicts_by_src": vb,
                        "passports": list(batch.get("passports") or []) + list(
                            batch2.get("passports") or []),
                        "incomplete": bool(batch2.get("incomplete")) or (
                            len(vb) < len(pool)),
                        "diag": diag,
                    }
                    outcome = wiki_outcome_from_full_verify(
                        vb, pool, intent, diag=diag,
                        ceiling_hit=ceiling_hit)
                    if outcome.get("outcome") == "leader" and not force_menu:
                        return _finish_sole(outcome.get("leader"))
                # остался non-sole → меню
            m = _menu()
            if m is not None:
                return m
            if len(pool) == 1:
                return _nd("wiki_rescue_rd")
            return None

        # ceiling_hit → sole уже не выставлялся; меню
        if ceiling_hit or force_menu:
            m = _menu()
            if m is not None:
                return m
            if len(pool) == 1:
                return _nd("wiki_rescue_rd")
            return None

        # трихотомия на none/unsure
        if verd == "one":
            # полный вердикт → меню всего пула (резолвер не лидер)
            m = _menu()
            if m is not None:
                return m
            if len(pool) == 1:
                return _nd("wiki_rescue_rd")
            return None
        if verd in ("many", None) or resolver.get("fail") or diag.get("resolver_input_truncated"):
            m = _menu()
            if m is not None:
                return m
            if len(pool) == 1:
                return _nd("wiki_rescue_rd")
            return None
        if verd == "none":
            if diag.get("resolver_input_truncated") or ceiling_hit:
                m = _menu()
                if m is not None:
                    return m
            # полное покрытие → честный no_data (ПОЛИТИКА)
            return _nd("wiki_rescue_none")

        m = _menu()
        if m is not None:
            return m
        return None
    finally:
        _stamp_stages()


def wiki_primary_entity_cascade(question, intent, cands, diag, cut, t0,
                                by, match, preds, counts_for_model, plan=None):
    """Wiki entity pick — единственный путь выбора сущности.

    [01.09] Вики — первая и единственная ступень (схема владельца
    PLAN_WIKI_CHOICE: вход — LLM+вики понимает вопрос). Обходные
    manual-выборы вырезаны. Если wiki вернула None без своего wiki_pick —
    в diag ставится wiki_pick=fallback (деградация wiki: пустая таблица,
    пустой пул, сбой verify), дальше честный no_data. Уже поставленный
    """
    picked, marks, plan = [], {}, plan or {}
    _wiki_skip_manual = False
    _wiki = try_wiki_hybrid_entity_pick(
        question, intent, diag, cut, t0,
        by=by, match=match, preds=preds, plan=plan)
    if (_wiki and _wiki.get("kind") in ("no_data", "clarify", "answer")):
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
        # ТОЧКА 1: любой уход в отказ, кроме wiki_none_empty/off-topic
        # (off-topic уже вернулся выше через kind=no_data reason=wiki_none_empty).
        _dh = globals().get("deadline_hit")
        if not diag.get("wiki_full_pool") and not (callable(_dh) and _dh()):
            _resc = wiki_rescue_full_pool_pass(
                question, intent, diag, cut, t0,
                by=by, match=match, preds=preds, plan=plan,
                origin="cascade")
            if isinstance(_resc, dict):
                if _resc.get("kind") in ("no_data", "clarify", "answer"):
                    return _resc
                if _resc.get("picked"):
                    picked = _resc["picked"]
                    marks = _resc.get("marks") or marks
                    plan = _resc.get("plan") or plan
                    # список (в т.ч. пустой) = отвечено; нет ключа → снять
                    _rc = _resc.get("rescue_concepts")
                    if isinstance(_rc, list):
                        diag["rescue_concepts"] = list(_rc)
                    else:
                        diag.pop("rescue_concepts", None)
                    if _resc.get("rescue_concepts_pending"):
                        diag["rescue_concepts_pending"] = True
                    else:
                        diag.pop("rescue_concepts_pending", None)
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
                                by=None, match="", preds=None, plan=None):
    """Единая точка интеграции для z20."""
    if diag is None:
        diag = {}
    diag["wiki_attempted"] = True
    try:
        if not psql("SELECT 1 FROM search_wiki_entity_card LIMIT 1"):
            return None
    except RuntimeError:
        return None
    cards = wiki_hybrid_pool(question, intent)
    # Тип из текста вопроса — часть интерпретации: чужие platform_kind
    # режем КОДОМ до verify/LLM (дополнение к В4, решение владельца 11.09).
    cards = filter_pool_by_named_type(question, cards, diag=diag)
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
        return wiki_entity_clarify_menu(
            question, pick.get("candidates") or [], diag, cut, t0,
            by=by, match=match, preds=preds,
            reason="wiki_separability", intent=intent, plan=plan)
    leader = pick.get("leader")
    if leader:
        if not wiki_leader_post_verify(leader, intent, question, diag):
            return None
        gated = wiki_leader_db_homonym_gate(
            leader, question, intent, diag, cut, t0,
            by=by, match=match, preds=preds, plan=plan)
        if gated is not None:
            return gated
        lead_card = next((c for c in cards if c.get("src_table") == leader), None)
        if lead_card and lead_card.get("src_layer") is not None:
            diag["src_layer"] = lead_card.get("src_layer")
        return {"picked": [leader], "marks": {}, "plan": {}}
    return None


def wiki_intent_named_measures(intent):
    """Все названные в разборе меры: measure и альтернативы списком."""
    intent = intent or {}
    raw = intent.get("measure")
    if isinstance(raw, (list, tuple)):
        items = raw
    elif raw is not None:
        items = [raw]
    else:
        items = []
    out, seen = [], set()
    for item in items:
        m = _intent_text(item)
        if not m:
            continue
        key = m.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def wiki_axis_is_question_subject(intent, axis_word):
    """Ось — предмет счёта (kind = action_axis), не квалификатор разреза."""
    intent = intent or {}
    axis_word = (axis_word or "").strip()
    if not axis_word:
        return False
    kind = _intent_text(intent.get("kind")) or ""
    if not kind:
        return False
    return kind.lower() == axis_word.lower()


def wiki_leader_carries_axis(leader, axis_word, intent=None, question="",
                             *, require_axis_cats=False):
    """Лидер структурно несёт named action_axis (каталог оси или refcol).

    require_axis_cats=True (unaccounted dictionary-ось): пустой axis_cats →
    False, не вакуумный True. LLM-action_axis без catalog — прежний fail-open.
    """
    leader = (leader or "").strip()
    axis_word = (axis_word or "").strip()
    if not leader or not axis_word:
        return True
    try:
        intent = intent or {}
        period = intent.get("period") or {}
        has_period = bool(period.get("from") or period.get("to"))
        _efc = globals().get("entity_form_catalogs_for_kind")
        if not callable(_efc):
            return True
        axis_cats = [c for c in (_efc(axis_word, allow_meaning=has_period) or []) if c]
        if not axis_cats:
            return not require_axis_cats
        if leader in axis_cats:
            return True
        cats_sql = ", ".join(lit(c) for c in sorted(set(axis_cats)))
        rows = psql(
            "SELECT 1 FROM search_refcols "
            "WHERE src_table = %s AND target_src IN (%s) "
            "  AND col IS NOT NULL AND trim(col) <> '' LIMIT 1"
            % (lit(leader), cats_sql))
        return bool(rows)
    except RuntimeError:
        return True


def wiki_leader_post_verify(leader, intent, question, diag=None):
    """Post-verify лидера: все известные меры + квалификатор action_axis."""
    diag = diag if diag is not None else {}
    intent = intent or {}
    for m in wiki_intent_named_measures(intent):
        if not wiki_measure_carried(leader, m):
            diag["wiki_measure_not_carried"] = leader
            diag["wiki_none"] = "measure_not_carried"
            return False
    axis_word = _intent_text(intent.get("action_axis"))
    axis_from_unaccounted = False
    if not axis_word:
        _ru = globals().get("resolved_unaccounted_slice_axis_word")
        if callable(_ru):
            try:
                axis_word = _ru(question, intent) or ""
                if axis_word:
                    axis_from_unaccounted = True
            except RuntimeError:
                axis_word = ""
    if (axis_word
            and not wiki_axis_is_question_subject(intent, axis_word)
            and (axis_from_unaccounted
                 or _wiki_axis_has_carriers(axis_word, intent, question))
            and not wiki_leader_carries_axis(
                leader, axis_word, intent, question,
                require_axis_cats=axis_from_unaccounted)):
        diag["wiki_axis_not_carried"] = leader
        diag["wiki_none"] = "axis_not_carried"
        return False
    return True


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
