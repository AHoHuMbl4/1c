#!/usr/bin/env python3
"""SQL списка изменившихся таблиц витрины для синка.

HTTP-контур: синк пишет список этого прогона целиком (DELETE + INSERT).
Packet-контур: отметки кладёт apply; синк только дописывает свои (если есть)
и не делает DELETE FROM search_changed_sources. Сборка снимает строку
в corpus_merge — по src, которые вошли в tmp3_build.

Доки: sql/statements/delete, sql/statements/insert.
"""


def changed_sources_sql(changed_tables, *, packet, role="serene_ro"):
    sql = ("CREATE TABLE IF NOT EXISTS search_changed_sources (src_table VARCHAR);\n"
           "GRANT SELECT ON search_changed_sources TO %s;\n" % role)
    vals = ",".join("(%s)" % ("'" + t.replace("'", "''") + "'")
                    for t in sorted(changed_tables))
    if packet:
        if vals:
            sql += ("INSERT INTO search_changed_sources "
                    "SELECT t FROM (VALUES %s) AS s(t) "
                    "WHERE t NOT IN (SELECT src_table FROM search_changed_sources);\n"
                    % vals)
    else:
        sql += "DELETE FROM search_changed_sources;\n"
        if vals:
            sql += ("INSERT INTO search_changed_sources "
                    "SELECT * FROM (VALUES %s) AS s(t);\n" % vals)
    sql += ("DELETE FROM search_quality WHERE k = 'changed_sources_ok';\n"
            "INSERT INTO search_quality VALUES ('changed_sources_ok', 1, "
            "'список изменившихся таблиц полон: синк дошёл до конца');\n")
    return sql
