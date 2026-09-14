#!/usr/bin/env python3
"""Разбор ответа агента словаря: сущности и величины.

Вынесен из `wiki_alias.sh`, чтобы отбор имён величин проверялся оффлайн: модель
имеет право вернуть что угодно, а в таблицу попадает только имя, которое уже
было во входном списке этой сущности. Выдуманное имя отбрасывает `canon_measure`.

Алиасы сущности: обиходные слова из ответа модели доходят до таблицы; имена
величин и их алиасы из того же ответа в `search_entity_alias` не пишутся —
их место в `search_measure_alias` (`filter_entity_aliases`). Мета-ярлыки
платформы 1С (класс объекта, не предмет) вычищаются тем же фильтром.

Запуск из скрипта:
    python3 wiki_alias_parse.py ANS.json PAY ROWS.json MEASURES.json
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata


# Хранение списков: разделитель ' | ' (P4 §2.4); потолок 1600 (P4 §3).
_JOIN_SEP = " | "
_JOIN_CAP = 1600


def _scrub_pipe_elem(s):
    """Элемент без '|': вырезать символ; пусто → отброс. Лог в stderr (P4 §2.4 п.4)."""
    s = str(s).strip()
    if not s:
        return None
    if "|" in s:
        cleaned = s.replace("|", "").strip()
        print(
            "wiki_alias_parse: pipe in element stripped: %r -> %r"
            % (s, cleaned or None),
            file=sys.stderr,
        )
        if not cleaned:
            return None
        return cleaned
    return s


def _join(x, n=_JOIN_CAP):
    parts = []
    for i in (x or []):
        cleaned = _scrub_pipe_elem(i)
        if cleaned:
            parts.append(cleaned)
    s = _JOIN_SEP.join(parts)
    if len(s) > n:
        # п.13: обрезка по потолку видна (семантика среза прежняя — посреди элемента).
        print(
            "wiki_alias_parse: join truncated to %d: len=%d"
            % (n, len(s)),
            file=sys.stderr,
        )
        return s[:n]
    return s


def _dig(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("text", "content") and isinstance(v, str) and "{" in v:
                yield v
            yield from _dig(v)
    elif isinstance(o, list):
        for v in o:
            yield from _dig(v)


def text_from_agent(raw):
    """Достать JSON-текст из конверта `openclaw agent --json` или из сырого ответа."""
    try:
        env = json.loads(raw)
        cands = list(_dig(env))
        return max(cands, key=len) if cands else ""
    except ValueError:
        return raw


def extract_items_payload(text):
    """Достать dict с ключом items из ответа модели (в т.ч. с reasoning-преамбулой).

    Стратегия (живая песочница 13.09: проза + обрывки схемы, валидный JSON в конце):
      1) весь text = JSON;
      2) жадный ``\\{.*\\}`` (прежнее поведение);
      3) от последнего ``"items"`` назад до ближайшей ``{``, сегмент до
         последней ``}``; при провале loads — укорачивать по предыдущей ``}``.
    Неудача попытки — кратко в stderr. Нет items → None (не исключение).
    """
    text = text or ""

    def _ok(obj):
        return isinstance(obj, dict) and "items" in obj

    # 1: целиком
    try:
        obj = json.loads(text)
        if _ok(obj):
            return obj
        print(
            "wiki_alias_parse: extract attempt 1: JSON without items",
            file=sys.stderr,
        )
    except ValueError as e:
        print(
            "wiki_alias_parse: extract attempt 1 failed: %s" % (e,),
            file=sys.stderr,
        )

    # 2: жадный {.*} (как раньше)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if _ok(obj):
                return obj
            print(
                "wiki_alias_parse: extract attempt 2: JSON without items",
                file=sys.stderr,
            )
        except ValueError as e:
            print(
                "wiki_alias_parse: extract attempt 2 failed: %s" % (e,),
                file=sys.stderr,
            )
    else:
        print(
            "wiki_alias_parse: extract attempt 2 failed: no {…} match",
            file=sys.stderr,
        )

    # 3: последний "items" → назад до { → до последней }; укорачивать при нужде
    idx = text.rfind('"items"')
    if idx < 0:
        print(
            "wiki_alias_parse: extract attempt 3 failed: no \"items\"",
            file=sys.stderr,
        )
        return None
    brace = text.rfind("{", 0, idx)
    if brace < 0:
        print(
            "wiki_alias_parse: extract attempt 3 failed: no { before items",
            file=sys.stderr,
        )
        return None
    end = text.rfind("}")
    if end <= brace:
        print(
            "wiki_alias_parse: extract attempt 3 failed: no } after items",
            file=sys.stderr,
        )
        return None
    segment = text[brace : end + 1]
    while segment:
        try:
            obj = json.loads(segment)
            if _ok(obj):
                return obj
            print(
                "wiki_alias_parse: extract attempt 3: JSON without items",
                file=sys.stderr,
            )
            return None
        except ValueError:
            prev = segment.rfind("}", 0, len(segment) - 1)
            if prev < 0:
                break
            segment = segment[: prev + 1]
    print(
        "wiki_alias_parse: extract attempt 3 failed: loads",
        file=sys.stderr,
    )
    return None


def allowed_quantities(pay):
    """entity -> канонические имена величин из входной пачки (как в данных, не из модели)."""
    out = {}
    if isinstance(pay, dict):
        pay = pay.get("items") or pay.get("value") or []
    for rec in pay or []:
        if not isinstance(rec, dict):
            continue
        e = (rec.get("entity") or rec.get("src_table") or "").strip()
        if not e:
            continue
        raw = rec.get("quantities") or ""
        if isinstance(raw, list):
            names = [str(x).strip() for x in raw if str(x).strip()]
        else:
            names = [x.strip() for x in str(raw).split(",") if x.strip()]
        out[e] = names
    return out


def canon_measure(name, allowed):
    """Имя из ответа модели -> канон из входного списка, либо None если выдумано."""
    n = (name or "").strip()
    if not n or not allowed:
        return None
    if n in allowed:
        return n
    low = {a.lower(): a for a in allowed}
    return low.get(n.lower())


def _alias_tokens(raw):
    """Список слов/оборотов из ответа модели (массив или CSV-строка).

    CSV: новый разделитель ' | '; старый ', ' (и голая ',' как запас).
    Дедуп — у вызывающей стороны (filter_entity_aliases), здесь не трогаем.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    s = str(raw)
    if " | " in s:
        parts = s.split(" | ")
    elif ", " in s:
        parts = s.split(", ")
    else:
        parts = s.split(",")
    return [x.strip() for x in parts if x.strip()]


# Стоп-варианты мета-классов платформы 1С (P3 §2): casefold + ё→е уже применены.
# Предметные («тмц», «склад», «номенклатура») сюда не входят.
_PLATFORM_META_STOP = frozenset({
    # ru
    "список", "списки",
    "справочник", "справочники",
    "каталог", "каталоги",
    "реестр", "реестры",
    "тип", "типы",
    "вид", "виды",
    "группа", "группы",
    "документ", "документы",
    "журнал", "журналы",
    "регистр", "регистры",
    "отчет", "отчеты",
    "запись", "записи",
    "карточка", "карточки",
    "перечень", "перечни",
    "перечисление", "перечисления",
    "константа", "константы",
    "движение", "движения",
    # en
    "list", "lists",
    "catalog", "catalogues", "catalogs",
    "directory", "directories",
    "journal", "journals",
    "register", "registers",
    "document", "documents",
    "report", "reports",
    "enum", "enumeration",
})


# Невидимые: soft-hyphen/BOM — удалить; ZWSP/ZWNJ/ZWJ — пробел (граница слова),
# иначе «список\\u200bклиентов» склеится и не сопоставится со стопом (R6-2).
# NFKC — только в _norm_meta_token (сопоставление); сохраняемый остаток без NFKC
# (канон P3 §4.2 п.1 / R7: «№5»/«м²» не портить).
_INVISIBLE_DROP = ("\u00ad", "\ufeff")
_INVISIBLE_SPACE = ("\u200b", "\u200c", "\u200d")


def _strip_invisibles(s: str) -> str:
    """Чистка невидимок для сохраняемого остатка (без NFKC)."""
    s = s or ""
    for ch in _INVISIBLE_DROP:
        s = s.replace(ch, "")
    for ch in _INVISIBLE_SPACE:
        s = s.replace(ch, " ")
    return s


def _norm_meta_token(s: str) -> str:
    """Нормализация только для сопоставления со стопом/ban (NFKC+casefold+ё→е)."""
    s = _strip_invisibles(s or "")
    s = unicodedata.normalize("NFKC", s)
    return s.strip().casefold().replace("ё", "е")


# Краевая пунктуация токена при сопоставлении со стопом/ban (P3 §4.2; R4).
_EDGE_PUNCT = set("«„“\"»(),;:.!?…—–")

# Разделители слов фразы (и краевые символы остатка после выреза).
_SEP_CHARS = " -/_"


def _strip_edge_punct(s: str) -> str:
    """Срезать краевые запятые/скобки/кавычки/.!?…/тире; дефис/слэш/_ — не сюда."""
    s = (s or "").strip()
    while s and s[0] in _EDGE_PUNCT:
        s = s[1:]
    while s and s[-1] in _EDGE_PUNCT:
        s = s[:-1]
    return s.strip()


def _clean_result_edges(s: str) -> str:
    """Края остатка: пробелы, дефис/слэш/_, краевая пунктуация _EDGE_PUNCT."""
    s = (s or "").strip()
    while s:
        if s[0] in _EDGE_PUNCT or s[0] in _SEP_CHARS:
            s = s[1:].lstrip()
            continue
        if s[-1] in _EDGE_PUNCT or s[-1] in _SEP_CHARS:
            s = s[:-1].rstrip()
            continue
        break
    return s.strip()


_SEP_RE = re.compile(r"([\s\-/_]+)")


def _phrase_parts(phrase: str):
    """Чередование слов и разделителей на уже подготовленной фразе.

    Пробел/дефис/слэш/_ — разделители; краевая пунктуация слова срезана.
    """
    raw = (phrase or "").strip()
    if not raw:
        return []
    parts = []
    for i, chunk in enumerate(_SEP_RE.split(raw)):
        if not chunk:
            continue
        if i % 2 == 1:
            parts.append(("s", chunk))
            continue
        w = _strip_edge_punct(chunk)
        if w:
            parts.append(("w", w))
    return parts


def _phrase_words(phrase: str):
    """Слова фразы для сопоставления со стопом/ban (без разделителей)."""
    return [w for kind, w in _phrase_parts(phrase) if kind == "w"]


def _strip_platform_meta_phrase(phrase: str, ban=None):
    """Убрать мета-токены и слова quantity-ban из фразы.

    Возвращает (результат|None, words_removed). None = фразу отбросить.
    Канон P3 §4.2 + R5/R7: дефис/слэш/_ — разделитель матча; вырез — из
    исходной фразы (только чистка невидимок, без NFKC) с сохранением
    разделителей; при вырезе из середины соседние разделители схлопываются
    в один (левый); нет выреза — фраза как есть; пусто → отброс.
    Qty-бан — точный по целому токену/слову, не по кускам multi-word фразы
    (канон §3.1): multi-word qty в ban не режет отдельные слова.
    """
    ban = ban or set()
    prepared = _strip_invisibles(phrase or "").strip()
    parts = _phrase_parts(prepared)
    words = [w for kind, w in parts if kind == "w"]
    if not words:
        return None, False

    def _drop_word(w: str) -> bool:
        key = _norm_meta_token(w)
        if key in _PLATFORM_META_STOP:
            return True
        # точный матч целого слова/токена со стопом ban (не подстрока фразы)
        if key in ban:
            return True
        return False

    n_drop = sum(1 for w in words if _drop_word(w))
    if n_drop == 0:
        edge = _clean_result_edges(_strip_edge_punct(prepared))
        return (edge if edge else None), False

    out_chunks = []
    prev_kept = False
    # Один разделитель между оставшимися словами (левый из пары при вырезе).
    sep_buf = None
    for kind, val in parts:
        if kind == "s":
            if prev_kept and sep_buf is None:
                sep_buf = val
            continue
        if _drop_word(val):
            continue
        if prev_kept and sep_buf is not None:
            out_chunks.append(sep_buf)
        out_chunks.append(val)
        prev_kept = True
        sep_buf = None

    if not out_chunks:
        return None, True
    result = _clean_result_edges("".join(out_chunks))
    if not result:
        return None, True
    return result, True


def titles_by_entity(pay):
    """entity -> title из входной пачки (wiki_entity_facts.label), не из ответа модели."""
    out = {}
    if isinstance(pay, dict):
        pay = pay.get("items") or pay.get("value") or []
    for rec in pay or []:
        if not isinstance(rec, dict):
            continue
        e = (rec.get("entity") or rec.get("src_table") or "").strip()
        if not e:
            continue
        tit = (rec.get("title") or "").strip()
        if tit:
            out[e] = tit
    return out


def filter_entity_aliases(aliases, quantity_names=None, quantity_aliases=None,
                          title=None):
    """Оставить обиходные слова сущности; выкинуть мусор величин и мета-класс.

    Отсев величин — по данным той же пачки/ответа. Мета — конечный стоп
    платформы 1С (P3), без слов конкретной базы. Quantities этим фильтром
    не трогаются (вызывающая сторона передаёт только entity-aliases).
    Всё вырезано + title есть → [title]; без title → [] (P3 §4.3). Голое
    мета-слово не оставляем «чтобы не пусто».
    """
    ban = set()
    for n in quantity_names or []:
        s = str(n).strip()
        if s:
            ban.add(_norm_meta_token(s))
    for a in quantity_aliases or []:
        s = str(a).strip()
        if s:
            ban.add(_norm_meta_token(s))
    toks = _alias_tokens(aliases)
    after_qty = []
    seen = set()
    for tok in toks:
        key = _norm_meta_token(tok)
        if key in ban or key in seen:
            if key in ban:
                print(
                    "wiki_alias_parse: quantity-name alias dropped: %r" % (tok,),
                    file=sys.stderr,
                )
            continue
        seen.add(key)
        after_qty.append(tok)

    out, seen_out = [], set()
    dropped_meta = []
    for tok in after_qty:
        cleaned, words_removed = _strip_platform_meta_phrase(tok, ban=ban)
        if cleaned is None:
            dropped_meta.append(tok)
            print(
                "wiki_alias_parse: platform meta alias dropped: %r" % (tok,),
                file=sys.stderr,
            )
            continue
        if words_removed:
            print(
                "wiki_alias_parse: platform meta token stripped: %r -> %r"
                % (tok, cleaned),
                file=sys.stderr,
            )
        key = _norm_meta_token(cleaned)
        if key in seen_out:
            continue
        seen_out.add(key)
        out.append(cleaned)

    # P3 §4.3 / R6-1: исходные алиасы были, после ВСЕХ фильтров пусто → title
    if not out and toks:
        title_s = (title or "").strip()
        if title_s:
            print(
                "wiki_alias_parse: meta filter emptied aliases; title fallback: %r"
                % (title_s,),
                file=sys.stderr,
            )
            return [title_s]
        print(
            "wiki_alias_parse: meta filter emptied aliases; no title (empty record)",
            file=sys.stderr,
        )
        return []
    return out


def _salvage_items(raw_json):
    """Целые элементы items из обрезанного JSON (срез по лимиту токенов).

    Идём по массиву items сканером сбалансированных скобок и отдаём только
    завершённые объекты; неполный хвост отбрасывается — он переспросится.
    """
    start = raw_json.find('"items"')
    if start < 0:
        return []
    arr = raw_json.find("[", start)
    if arr < 0:
        return []
    out = []
    i = arr + 1
    depth = 0
    obj_start = -1
    in_str = False
    esc = False
    while i < len(raw_json):
        c = raw_json[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(raw_json[obj_start:i + 1])
                    if isinstance(obj, dict):
                        out.append(obj)
                except ValueError:
                    pass
        elif c == "]" and depth == 0:
            break
        i += 1
    return out


def parse_items(text, pay):
    """(entity_rows, measure_rows). Величины — только с каноническим именем и непустым алиасом."""
    allowed = allowed_quantities(pay)
    titles = titles_by_entity(pay)
    entity_rows, measure_rows = [], []
    payload = extract_items_payload(text)
    if payload is not None:
        items = payload.get("items") or []
    else:
        # [замер окно 28.08] длинные пачки обрезаются лимитом токенов
        # вызова: JSON рвётся на середине items. Целые элементы до среза
        # обязаны спасаться, а не теряться пачкой (п. 13); остаток
        # переспросится идемпотентно на следующем круге.
        # extract вернул None — salvage по жадному сегменту (логика не тронута).
        m = re.search(r"\{.*\}", text or "", re.S)
        if not m:
            return entity_rows, measure_rows
        items = _salvage_items(m.group(0))
    for it in items:
        if not isinstance(it, dict):
            continue
        e = (it.get("entity") or "").strip()
        if not e:
            continue
        allow = allowed.get(e) or []
        q_alias_ban = []
        kept_measures = []
        for q in it.get("quantities") or []:
            if not isinstance(q, dict):
                continue
            name = canon_measure(q.get("name"), allow)
            q_toks = _alias_tokens(q.get("aliases"))
            q_alias_ban.extend(q_toks)
            if not name or not q_toks:
                continue
            kept_measures.append(
                {"src_table": e, "measure": name, "aliases": _join(q_toks)})
        ent_aliases = filter_entity_aliases(
            it.get("aliases"), quantity_names=allow, quantity_aliases=q_alias_ban,
            title=titles.get(e))
        entity_rows.append({
            "src_table": e,
            "aliases": _join(ent_aliases),
            "best_used_for": _join(it.get("bestUsedFor")),
            "not_enough_for": _join(it.get("notEnoughFor")),
        })
        measure_rows.extend(kept_measures)
    return entity_rows, measure_rows


# ── «1 задача = 1 вызов»: однопольные JSON → полный item (dictfix §2) ─────────
# Падение поля (ретрай до сборки): не JSON/не schema; aliases пуст/ниже минимума
# сайта; best пуст или <2; NEF пуст — НЕ падение; NEF/best — hard-format.

_FIELD_KEYS = ("aliases", "bestUsedFor", "notEnoughFor")
_PAREN_COMMA_RE = re.compile(r"\([^)]*,[^)]*\)")


def _hard_format_best_ok(s: str) -> bool:
    """bestUsedFor: запрет скобок с запятой внутри (P-8)."""
    return _PAREN_COMMA_RE.search(s or "") is None


def _hard_format_nef_ok(s: str) -> bool:
    """notEnoughFor: без запятых и скобок (downstream comma-CSV)."""
    s = s or ""
    return "," not in s and "(" not in s and ")" not in s


def _items_from_field_text(text):
    """items из однопольного ответа; None = не JSON / нет schema items."""
    payload = extract_items_payload(text or "")
    if payload is None:
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    return items


def entities_from_pay(pay):
    """Множество entity-ключей Input пачки (точные строки, без нормализации)."""
    out = set()
    if isinstance(pay, dict):
        pay = pay.get("items") or pay.get("value") or []
    for rec in pay or []:
        if not isinstance(rec, dict):
            continue
        e = (rec.get("entity") or rec.get("src_table") or "").strip()
        if e:
            out.add(e)
    return out


def _field_values_map(items, field, allowed=None):
    """entity -> list значений поля (только строки/токены).

    allowed — set entity из Input: неизвестная → пропуск + stderr;
    дубль внутри ответа → пропуск дубля + stderr. Возвращает
    (out|None, n_unknown): None = schema (нет ключа поля на item).
    """
    out = {}
    n_unknown = 0
    seen = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        e = (it.get("entity") or "").strip()
        if not e:
            continue
        if e in seen:
            print(
                "wiki_alias_parse: duplicate entity skipped: %r" % (e,),
                file=sys.stderr,
            )
            continue
        if allowed is not None and e not in allowed:
            print(
                "wiki_alias_parse: unknown entity skipped: %r" % (e,),
                file=sys.stderr,
            )
            n_unknown += 1
            continue
        seen.add(e)
        if field not in it:
            return None, n_unknown  # schema: ключ поля обязателен
        raw = it.get(field)
        if raw is None:
            out[e] = []
        elif isinstance(raw, list):
            out[e] = [str(x).strip() for x in raw if str(x).strip()]
        else:
            out[e] = _alias_tokens(raw)
    return out, n_unknown


def _aliases_meet_min(aliases, title, site):
    """True если aliases проходят минимум сайта после filter."""
    title_s = (title or "").strip()
    if site == "collision":
        is_title_fb = (len(aliases) == 1 and title_s and aliases[0] == title_s)
        if is_title_fb:
            return True
        if len(aliases) < 2 or all(len(a) < 4 for a in aliases):
            return False
        return True
    # init / reask
    return len(aliases) >= 3


def _payload_text(raw_or_text):
    """Текст с items: конверт шлюза (text_from_agent) или сырой JSON items."""
    raw = raw_or_text or ""
    dug = text_from_agent(raw)
    if dug and '"items"' in dug:
        return dug
    if '"items"' in raw:
        return raw
    return dug or raw


def check_field_answer(raw_or_text, pay, field, site="init"):
    """Проверка одного поля до сборки.

    Возвращает (ok: bool, reason: str). reason пуст при ok.
    site: init|collision (reask = init). field: aliases|bestUsedFor|notEnoughFor.
    """
    if field not in _FIELD_KEYS:
        return False, "unknown field %r" % (field,)
    if site not in ("init", "collision"):
        return False, "unknown site %r" % (site,)
    text = _payload_text(raw_or_text)

    items = _items_from_field_text(text)
    if items is None:
        return False, "%s: not JSON / no items schema" % field

    pay_ents = entities_from_pay(pay)
    fmap, n_unknown = _field_values_map(items, field, allowed=pay_ents)
    if fmap is None:
        return False, "%s: schema — missing field key on an item" % field
    # Любая причёсанная/чужая entity = ретрай поля (доля неизвестных > 0).
    if n_unknown > 0:
        return False, "%s: unknown entity not in Input (n=%d)" % (
            field, n_unknown)
    if not fmap:
        return False, "%s: items empty" % field

    titles = titles_by_entity(pay)
    allowed = allowed_quantities(pay)

    if field == "aliases":
        ok_n = 0
        for e, raw_aliases in fmap.items():
            filtered = filter_entity_aliases(
                raw_aliases, quantity_names=allowed.get(e) or [],
                title=titles.get(e))
            if _aliases_meet_min(filtered, titles.get(e), site):
                ok_n += 1
            else:
                return False, (
                    "%s: entity %s below min after filter (site=%s, n=%d)"
                    % (field, e, site, len(filtered)))
        if ok_n == 0:
            return False, "%s: no entity met min after filter" % field
        return True, ""

    if field == "bestUsedFor":
        for e, vals in fmap.items():
            if len(vals) < 2:
                return False, "%s: entity %s has %d templates (need >=2)" % (
                    field, e, len(vals))
            for s in vals:
                if not _hard_format_best_ok(s):
                    return False, (
                        "%s: hard-format (paren+comma) entity %s: %r"
                        % (field, e, s[:80]))
        return True, ""

    # notEnoughFor: пустой список допустим; падение — schema (выше) или hard-format
    for e, vals in fmap.items():
        for s in vals:
            if not _hard_format_nef_ok(s):
                return False, (
                    "%s: hard-format (comma/paren) entity %s: %r"
                    % (field, e, s[:80]))
    return True, ""


def assemble_field_items(aliases_raw, best_raw, nef_raw, pay, site="init"):
    """Собрать три однопольных ответа в entity_rows (формат parse_items).

    aliases/best/nef — сырой ответ шлюза или JSON-текст. measures не заполняются
    (quantities — отдельный сайт). При site=collision строки ниже минимума
    aliases пропускаются с логом (как прежний PY2).
    """
    titles = titles_by_entity(pay)
    allowed = allowed_quantities(pay)
    pay_ents = entities_from_pay(pay)

    def _map(raw, field):
        text = _payload_text(raw)
        items = _items_from_field_text(text)
        if items is None:
            return {}
        fmap, _n_unk = _field_values_map(items, field, allowed=pay_ents)
        return fmap or {}

    a_map = _map(aliases_raw, "aliases")
    b_map = _map(best_raw, "bestUsedFor")
    c_map = _map(nef_raw, "notEnoughFor")

    entities = []
    seen = set()
    for e in list(a_map) + list(b_map) + list(c_map):
        if e not in seen:
            seen.add(e)
            entities.append(e)

    rows = []
    for e in entities:
        filtered = filter_entity_aliases(
            a_map.get(e), quantity_names=allowed.get(e) or [],
            title=titles.get(e))
        if site == "collision":
            title_s = (titles.get(e) or "").strip()
            is_title_fb = (len(filtered) == 1 and title_s
                           and filtered[0] == title_s)
            if not is_title_fb and (
                    len(filtered) < 2 or all(len(a) < 4 for a in filtered)):
                print(
                    "collision row skipped (degenerate after filter): %s"
                    " — kept previous" % e,
                    file=sys.stderr,
                )
                continue
        elif len(filtered) < 3:
            print(
                "init row skipped (aliases < 3 after filter): %s" % e,
                file=sys.stderr,
            )
            continue
        best = b_map.get(e) or []
        if len(best) < 2:
            print(
                "row skipped (bestUsedFor < 2): %s" % e,
                file=sys.stderr,
            )
            continue
        nef = c_map.get(e) or []
        rows.append({
            "src_table": e,
            "aliases": _join(filtered),
            "best_used_for": _join(best),
            "not_enough_for": _join(nef),
        })
    return rows


def main(argv):
    # --check-field FIELD --site SITE ANS PAY  → exit 0/1, reason в stderr
    if len(argv) >= 2 and argv[1] == "--check-field":
        # argv: script --check-field FIELD --site SITE ANS PAY
        field = argv[2]
        site = "init"
        rest = argv[3:]
        if rest and rest[0] == "--site":
            site = rest[1]
            rest = rest[2:]
        ans_path, pay_path = rest[0], rest[1]
        raw = open(ans_path, encoding="utf-8", errors="replace").read()
        try:
            pay = json.loads(open(pay_path, encoding="utf-8").read() or "[]")
        except ValueError:
            pay = []
        ok, reason = check_field_answer(raw, pay, field, site=site)
        if not ok:
            print("wiki_alias_parse: field fail %s: %s" % (field, reason),
                  file=sys.stderr)
            return 1
        return 0

    # --assemble --site SITE ANS_A ANS_B ANS_C PAY ROWS [MEASURES]
    if len(argv) >= 2 and argv[1] == "--assemble":
        site = "init"
        rest = argv[2:]
        if rest and rest[0] == "--site":
            site = rest[1]
            rest = rest[2:]
        ans_a, ans_b, ans_c, pay_path, rows_path = rest[:5]
        meas_path = rest[5] if len(rest) > 5 else None
        try:
            pay = json.loads(open(pay_path, encoding="utf-8").read() or "[]")
        except ValueError:
            pay = []
        raw_a = open(ans_a, encoding="utf-8", errors="replace").read()
        raw_b = open(ans_b, encoding="utf-8", errors="replace").read()
        raw_c = open(ans_c, encoding="utf-8", errors="replace").read()
        entities = assemble_field_items(raw_a, raw_b, raw_c, pay, site=site)
        open(rows_path, "w", encoding="utf-8").write(
            json.dumps(entities, ensure_ascii=False))
        if meas_path:
            open(meas_path, "w", encoding="utf-8").write("[]")
        print("алиасов разобрано: %d, величин: 0" % len(entities))
        return 0

    ans_path, pay_path, rows_path, meas_path = argv[1], argv[2], argv[3], argv[4]
    raw = open(ans_path, encoding="utf-8", errors="replace").read()
    try:
        pay = json.loads(open(pay_path, encoding="utf-8").read() or "[]")
    except ValueError:
        pay = []
    entities, measures = parse_items(text_from_agent(raw), pay)
    open(rows_path, "w", encoding="utf-8").write(json.dumps(entities, ensure_ascii=False))
    open(meas_path, "w", encoding="utf-8").write(json.dumps(measures, ensure_ascii=False))
    print("алиасов разобрано: %d, величин: %d" % (len(entities), len(measures)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
