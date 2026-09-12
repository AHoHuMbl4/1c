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
        # r[8]=platform_prefix (SQL); platform_kind считаем из src/parent.
        # r[9]=src_kind — провенанс слагаемого пула (только в конец).
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
            "src_kind": (r[9] if len(r) > 9 else "") or "",
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
        # даже без паспорта — прогнать уже лежащий label/hint (общее правило)
        prev = (row.get("label") or "").strip()
        text = wiki_human_menu_caption(name, body, existing_label=prev)
        if text:
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


def _wiki_sanitize_why(why):
    """why для diag/журнала: одна строка, ≤200 символов."""
    s = str(why or "").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:200]


def _wiki_verdicts_for_diag(verdicts):
    """Компактные вердикты в diag: ключи i/fit/why, why санитизирован."""
    out = []
    for v in verdicts or []:
        if not isinstance(v, dict):
            continue
        idx = v.get("index")
        fit = v.get("fit")
        if idx is None or fit not in ("yes", "no", "unsure"):
            continue
        out.append({
            "i": int(idx),
            "fit": fit,
            "why": _wiki_sanitize_why(v.get("why")),
        })
    return out


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


def _wiki_verify_fit_buckets(verdicts, n_passports):
    """Индексы yes / unsure / no по вердиктам (1-based, как у модели)."""
    by_idx = {v["index"]: v for v in (verdicts or [])}
    yes_i, unsure_i, no_i = [], [], []
    for i in range(1, n_passports + 1):
        v = by_idx.get(i)
        if not v:
            continue
        if v["fit"] == "yes":
            yes_i.append(i)
        elif v["fit"] == "unsure":
            unsure_i.append(i)
        else:
            no_i.append(i)
    return yes_i, unsure_i, no_i


def _wiki_verify_confirm_sole_yes(
        ask_text, listing, full, first_verdicts, first_leader, diag):
    """Согласие на sole-yes: второй вызов тому же судье (I0-П2b).

    agree — parse2=full, ровно n вердиктов, один yes|unsure = лидер₁, остальные no.
    disagree / disagree-trunc / disagree-partial — иначе: clarify по yes∪unsure;
    пусто / все-no₂ → none. Счётчики первого вызова не затираются (wiki_verify2_*).
    """
    n = len(full)
    msgs = [{"role": "system", "content": WIKI_VERIFY_SYS},
            {"role": "user", "content": "%s\n\nPassports:\n%s"
             % (ask_text, listing)}]
    raw2 = None
    try:
        raw2 = ds_chat(msgs, max_tokens=WIKI_VERIFY_MAX_TOKENS)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(
            "ask: wiki verify confirm без модели (%s)\n" % str(e)[:80])
        diag["wiki_verify2_error"] = 1
        diag["wiki_verify_confirm"] = "disagree"
        yes1, unsure1, _ = _wiki_verify_fit_buckets(first_verdicts, n)
        tie_idx = sorted(set(yes1 + unsure1))
        diag["wiki_verify"] = "clarify"
        diag["wiki_verify_tie"] = [
            full[i - 1].get("src_table") for i in tie_idx if 0 < i <= n]
        return {
            "outcome": "clarify",
            "candidates": [full[i - 1] for i in tie_idx if 0 < i <= n],
            "verdicts": first_verdicts,
            "diag": diag,
        }
    verdicts2, parse2 = wiki_parse_verify_response(raw2, n)
    if parse2 == "salvage":
        diag["wiki_verify2_truncated"] = 1
    if (raw2 or "").strip() and parse2 == "failed":
        diag["wiki_verify2_error"] = 1
        diag["wiki_verify_confirm"] = "disagree"
        yes1, unsure1, _ = _wiki_verify_fit_buckets(first_verdicts, n)
        tie_idx = sorted(set(yes1 + unsure1))
        diag["wiki_verify"] = "clarify"
        diag["wiki_verify_tie"] = [
            full[i - 1].get("src_table") for i in tie_idx if 0 < i <= n]
        return {
            "outcome": "clarify",
            "candidates": [full[i - 1] for i in tie_idx if 0 < i <= n],
            "verdicts": first_verdicts,
            "diag": diag,
        }
    yes2, unsure2, no2 = _wiki_verify_fit_buckets(verdicts2, n)
    diag["wiki_verify2_yes"] = len(yes2)
    diag["wiki_verify2_unsure"] = len(unsure2)
    diag["wiki_verify2_no"] = len(no2)
    diag["wiki_verdicts2"] = _wiki_verdicts_for_diag(verdicts2)
    leader_idx = next(
        (i for i in range(1, n + 1)
         if full[i - 1].get("src_table") == first_leader),
        None)
    by2 = {v["index"]: v for v in (verdicts2 or [])}
    n_v2 = len(verdicts2 or [])
    covers_all = set(by2) == set(range(1, n + 1))
    complete = (parse2 == "full" and n_v2 == n and covers_all)
    same_fit = False
    if leader_idx is not None:
        v_lead = by2.get(leader_idx)
        same_fit = bool(v_lead and v_lead["fit"] in ("yes", "unsure"))
    other_yes = [i for i in yes2 if i != leader_idx]
    other_unsure = [i for i in unsure2 if i != leader_idx]
    # agree: полный разбор, все n, ровно один yes|unsure = лидер₁, остальные явные no.
    # отсутствие вердикта ≠ no (salvage/partial → не agree).
    if complete and same_fit and not other_yes and not other_unsure:
        diag["wiki_verify_confirm"] = "agree"
        return None  # лидер первого вызова остаётся
    if parse2 == "salvage":
        diag["wiki_verify_confirm"] = "disagree-trunc"
    elif parse2 == "full" and not complete:
        diag["wiki_verify_confirm"] = "disagree-partial"
    else:
        diag["wiki_verify_confirm"] = "disagree"
    # Успешный второй «все no» — флип без поддержки: none (не утверждать 1-й yes).
    if not yes2 and not unsure2 and len(no2) == n:
        diag["wiki_verify"] = "none"
        return {
            "outcome": "none",
            "reason": "verify_confirm_none",
            "verdicts": first_verdicts,
            "diag": diag,
        }
    yes1, unsure1, _ = _wiki_verify_fit_buckets(first_verdicts, n)
    tie_idx = sorted(set(yes1 + unsure1 + yes2 + unsure2))
    if not tie_idx:
        diag["wiki_verify"] = "none"
        return {
            "outcome": "none",
            "reason": "verify_confirm_none",
            "verdicts": first_verdicts,
            "diag": diag,
        }
    diag["wiki_verify"] = "clarify"
    diag["wiki_verify_tie"] = [
        full[i - 1].get("src_table") for i in tie_idx if 0 < i <= n]
    return {
        "outcome": "clarify",
        "candidates": [full[i - 1] for i in tie_idx if 0 < i <= n],
        "verdicts": first_verdicts,
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
    # Согласие только на sole-yes при пуле >1; wiki_verify_error — не подтверждать.
    # (wiki_verify=="degraded" никто не пишет — мёртвая ветка снята, I0-П2b-фикс.)
    skip_confirm = (
        len(full) <= 1
        or bool(diag.get("wiki_verify_error")))
    try:
        raw = ds_chat(
            [{"role": "system", "content": WIKI_VERIFY_SYS},
             {"role": "user", "content": "%s\n\nPassports:\n%s"
              % (ask_text, listing)}],
            max_tokens=WIKI_VERIFY_MAX_TOKENS)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("ask DEGRADED: wiki verify без модели (%s)\n" % str(e)[:80])
        diag["wiki_verdicts"] = []
        diag["wiki_verify_error"] = 1
        return {"outcome": "degraded", "diag": diag}
    verdicts, parse_mode = wiki_parse_verify_response(raw, len(full))
    if parse_mode == "salvage":
        diag["wiki_verify_truncated"] = 1
    if (raw or "").strip() and parse_mode == "failed":
        sys.stderr.write("ask DEGRADED: wiki verify ответ не разобран\n")
        diag["wiki_verify_n"] = len(full)
        diag["wiki_verdicts"] = []
        return {"outcome": "degraded", "verdicts": [], "diag": diag}
    diag["wiki_verify_n"] = len(full)
    resolved = wiki_outcome_from_verify(verdicts, full, intent, diag=diag)
    resolved["verdicts"] = verdicts
    d = dict(resolved.get("diag") or diag)
    d["wiki_verdicts"] = _wiki_verdicts_for_diag(verdicts)
    # I0-П2b: sole-yes → повторный вызов (пул >1, не degraded).
    if (not skip_confirm
            and resolved.get("outcome") == "leader"
            and resolved.get("leader")
            and not d.get("wiki_verify_error")):
        confirmed = _wiki_verify_confirm_sole_yes(
            ask_text, listing, full, verdicts,
            resolved.get("leader"), d)
        if confirmed is not None:
            confirmed["verdicts"] = confirmed.get("verdicts") or verdicts
            cd = dict(confirmed.get("diag") or d)
            if "wiki_verdicts" not in cd:
                cd["wiki_verdicts"] = d.get("wiki_verdicts") or []
            confirmed["diag"] = cd
            return confirmed
        d["wiki_verify_confirm"] = "agree"
    resolved["diag"] = d
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
        by=by, match=match, preds=preds)
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



_WIKI_PICK_HINT_SENTINELS = frozenset({
    "bad_index", "axis_reject", "fallback", "none", "clarify", "wiki_degraded",
})


def _stash_wiki_pick_hint(diag):
    """Сохранить прежний wiki_pick (пик) до sentinel clarify/fallback."""
    prev = (diag or {}).get("wiki_pick")
    if (isinstance(prev, str) and prev.strip()
            and prev not in _WIKI_PICK_HINT_SENTINELS):
        diag["wiki_pick_hint"] = prev


def try_wiki_hybrid_entity_pick(question, intent, diag, cut, t0,
                                by=None, match="", preds=None):
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
            # I0-П5: pick без модели — пика нет; пул>1 → меню, не отказ.
            diag["wiki_degraded"] = 1
            _stash_wiki_pick_hint(diag)
            pick = {"outcome": "clarify", "candidates": list(cards), "diag": diag}
            diag["wiki_pick"] = "clarify"
        else:
            verify = wiki_verify_candidates(question, intent, cards, diag=diag)
            diag.update(verify.get("diag") or {})
            if verify.get("outcome") == "degraded":
                # I0-П5: непроверенный пик не утверждается.
                # tie+degraded: меню по candidates пика, иначе по пулу.
                diag["wiki_degraded"] = 1
                _stash_wiki_pick_hint(diag)
                prior = (pick.get("candidates")
                         if pick.get("outcome") == "clarify" else None)
                cand = list(prior) if prior else list(cards)
                pick = {"outcome": "clarify", "candidates": cand, "diag": diag}
                diag["wiki_pick"] = "clarify"
            elif verify.get("outcome") in ("leader", "clarify", "none"):
                pick = verify
                if verify.get("outcome") == "leader":
                    diag["wiki_pick"] = (
                        verify.get("leader") or diag.get("wiki_pick"))
                elif verify.get("outcome") == "none":
                    diag["wiki_pick"] = "none"
                    diag["wiki_none"] = verify.get("reason") or "verify_none"
                elif verify.get("outcome") == "clarify":
                    diag["wiki_pick"] = "clarify"
    if pick.get("outcome") == "degraded":
        # Пул=1 (или иной остаточный degraded): честный отказ, не пик.
        diag["wiki_degraded"] = 1
        _stash_wiki_pick_hint(diag)
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
                % (TABLES, ", ".join(lit(c) for c in tied)))
                if r and len(r) > 1 and r[0]}
        except RuntimeError:
            lab_by = {}
        opts = mk_opts(tied, lab_by, {}, by or {}, match=match or "", preds=preds or [])
        if len(opts) >= 2:
            # В4: равные числа → меню (1-Б); подписи из паспортов verify-кандидатов.
            # S2-d-(а): clarify только через единый построитель (не bare Dict).
            _pmap = wiki_captions_map_from_cards(pick.get("candidates") or [])
            opts = wiki_menu_captions(opts, passports_by_src=_pmap)
            return readings_menu(
                question, "entity", opts, diag, cut, t0,
                reason="wiki_separability")
        # Меню не собралось (пустое окно / keep_empty) — честный reason.
        if diag.get("wiki_degraded"):
            diag["wiki_pick"] = "wiki_degraded"
    leader = pick.get("leader")
    if leader:
        if not wiki_leader_post_verify(leader, intent, question, diag):
            return None
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
