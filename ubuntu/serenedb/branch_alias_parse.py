#!/usr/bin/env python3
"""Разбор ответа агента словаря развилок: подписи веток.

Вынесен из `branch_alias.sh`, чтобы отбор проверялся оффлайн (тот же приём, что у
`wiki_alias_parse.py`): модель имеет право вернуть что угодно, а в таблицу попадает
только пара (fork_key, src), которая УЖЕ была во входной пачке, — и только с
непустой подписью. Чужой fork_key, чужой src внутри класса, пустая подпись —
отбрасываются; пропущенный src просто отсутствует (его переспросит следующий
прогон — заглушку-попытку ставит скрипт).

Запуск из скрипта:
    python3 branch_alias_parse.py ANS.json PAY ROWS.json
"""
from __future__ import annotations

import json
import re
import sys

from wiki_alias_parse import text_from_agent

MAX_LABEL = 900


def known_forks(pay):
    """fork_key -> список src класса и title -> src из входной пачки."""
    out = {}
    title_to_src = {}
    if isinstance(pay, dict):
        pay = pay.get("forks") or pay.get("items") or pay.get("value") or []
    for rec in pay or []:
        if not isinstance(rec, dict):
            continue
        fk = (rec.get("fork_key") or "").strip()
        if not fk:
            continue
        srcs = []
        for s in rec.get("sources") or []:
            if isinstance(s, dict):
                name = (s.get("src") or "").strip()
                title = (s.get("title") or "").strip()
            else:
                name = str(s).strip()
                title = ""
            if name:
                srcs.append(name)
            if title:
                title_to_src[norm(title)] = name
        out[fk] = (srcs, title_to_src)
    return out


def norm(s):
    return "".join(str(s).lower().split())


def parse_labels(text, pay):
    """[{fork_key, src, label}] — только известные пары с непустой подписью."""
    known = known_forks(pay)
    rows = []
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return rows
    try:
        forks = json.loads(m.group(0)).get("forks") or []
    except ValueError:
        return rows
    for fork in forks:
        if not isinstance(fork, dict):
            continue
        fk = (fork.get("fork_key") or "").strip()
        if fk not in known:
            continue
        allowed, title_to_src = known[fk]
        labels = fork.get("labels")
        if not isinstance(labels, dict):
            continue
        for src, label in labels.items():
            src = (src or "").strip()
            if src not in allowed:
                # Модель часто использует человеческий title вместо src-идентификатора;
                # сводим по title, если он однозначен.
                ns = norm(src)
                if ns in title_to_src and title_to_src[ns] in allowed:
                    src = title_to_src[ns]
                else:
                    continue
            label = str(label or "").strip()[:MAX_LABEL]
            if not label:
                continue
            rows.append({"fork_key": fk, "src": src, "label": label})
    return rows


def main(argv):
    ans_path, pay_path, rows_path = argv[1], argv[2], argv[3]
    raw = open(ans_path, encoding="utf-8", errors="replace").read()
    try:
        pay = json.loads(open(pay_path, encoding="utf-8").read() or "[]")
    except ValueError:
        pay = []
    rows = parse_labels(text_from_agent(raw), pay)
    if not rows:
        # Конверт не найден — ответ мог прийти сырым JSON (без --json-обёртки):
        # text_from_agent такой вернёт пустым, потому что ищет поля text/content.
        rows = parse_labels(raw, pay)
    open(rows_path, "w", encoding="utf-8").write(json.dumps(rows, ensure_ascii=False))
    print("подписей веток разобрано: %d" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
