"""Д3: замок «инвертированный индекс не пуст при непустой таблице».

Инвертированный индекс SereneDB eventually consistent: после INSERT/UPDATE
строки видны индексу только после refresh (VACUUM REFRESH_* или фон).
Пустой индекс при живой таблице — молчаливая потеря качества (п. 13 TARGET.md).

Чистая функция + оффлайн-проверки пайплайна; живая пара table/index —
через psql в corpus_postcheck.sql и в демо test_inverted_index_guard.py.
"""
from __future__ import annotations


def assert_index_covers_table(table_rows: int, index_rows: int, *, label: str = "") -> None:
    """Падает, если таблица непуста, а индекс пуст.

    Пустая таблица + пустой индекс (свежая установка) — норма.
    index_rows > 0 при table_rows > 0 — норма (в т.ч. краткий лаг, когда
    count(index) ещё показывает старые документы после DELETE).
    """
    tr = int(table_rows)
    ir = int(index_rows)
    if tr < 0 or ir < 0:
        raise ValueError("negative row counts: table=%d index=%d" % (tr, ir))
    if tr > 0 and ir == 0:
        where = (" (%s)" % label) if label else ""
        raise AssertionError(
            "inverted index empty while table has %d row(s)%s — VACUUM (REFRESH_*) missing"
            % (tr, where)
        )
