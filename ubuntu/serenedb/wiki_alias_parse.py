#!/usr/bin/env python3
"""Разбор ответа агента словаря: сущности и величины.

Вынесен из `wiki_alias.sh`, чтобы отбор имён величин проверялся оффлайн: модель
имеет право вернуть что угодно, а в таблицу попадает только имя, которое уже
было во входном списке этой сущности. Выдуманное имя отбрасывает `canon_measure`.

Алиасы сущности: обиходные слова из ответа модели доходят до таблицы; имена
величин и их алиасы из того же ответа в `search_entity_alias` не пишутся —
их место в `search_measure_alias` (`filter_entity_aliases`).

Запуск из скрипта:
    python3 wiki_alias_parse.py ANS.json PAY ROWS.json MEASURES.json
"""
from __future__ import annotations

import json
import re
import sys


def _join(x, n=900):
    return ", ".join(str(i).strip() for i in (x or []) if str(i).strip())[:n]


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
    """Список слов/оборотов из ответа модели (массив или CSV-строка)."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def filter_entity_aliases(aliases, quantity_names=None, quantity_aliases=None):
    """Оставить обиходные слова сущности; выкинуть мусор величин.

    Отсев — по данным той же пачки/ответа (имена полей из входа и алиасы величин
    из ответа модели), без списков слов конкретной базы или языка.
    """
    ban = set()
    for n in quantity_names or []:
        s = str(n).strip()
        if s:
            ban.add(s.casefold())
    for a in quantity_aliases or []:
        s = str(a).strip()
        if s:
            ban.add(s.casefold())
    out, seen = [], set()
    for tok in _alias_tokens(aliases):
        key = tok.casefold()
        if key in ban or key in seen:
            continue
        seen.add(key)
        out.append(tok)
    return out


def parse_items(text, pay):
    """(entity_rows, measure_rows). Величины — только с каноническим именем и непустым алиасом."""
    allowed = allowed_quantities(pay)
    entity_rows, measure_rows = [], []
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return entity_rows, measure_rows
    try:
        items = json.loads(m.group(0)).get("items") or []
    except ValueError:
        return entity_rows, measure_rows
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
            it.get("aliases"), quantity_names=allow, quantity_aliases=q_alias_ban)
        entity_rows.append({
            "src_table": e,
            "aliases": _join(ent_aliases),
            "best_used_for": _join(it.get("bestUsedFor")),
            "not_enough_for": _join(it.get("notEnoughFor")),
        })
        measure_rows.extend(kept_measures)
    return entity_rows, measure_rows


def main(argv):
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
