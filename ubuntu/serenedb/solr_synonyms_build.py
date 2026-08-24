#!/usr/bin/env python3
"""Ф6.3: компиляция Solr-карты синонимов из таблиц → DROP+CREATE словарь файлом.

Списков слов в коде нет: правила приходят из search_entity_alias (wiki-alias)
и search_synonym_bridge (кэш моста на лету). Здесь только формат Solr и лимиты
по фактуре docs/F6_SYNONYMS_FACTS.md §3.2 (~20 000 правил / ~400 КБ inline OK;
длиннее — честная ошибка, п. 13 TARGET).

Доки: CREATE TEXT SEARCH DICTIONARY › solr_synonyms
(https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms).

Запуск из такта (wiki_alias.sh / CLI):
  python3 solr_synonyms_build.py compile --dsn \"$DSN\" [--dict NAME] [--out FILE]
  python3 solr_synonyms_build.py write-ddl --dict NAME --map-file MAP [--out FILE]

Оффлайн: функции escape_term / rule_from_alias_csv / compile_rules / check_limits /
render_ddl — без сети и без LLM.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Лимиты — живой замер 24.08 на SereneDB 26.08.1 (F6_SYNONYMS_FACTS §3.2):
# 20 000 правил / ~400 КБ CREATE+ts_lexize OK; argv ломается раньше — кормим файлом.
MAX_RULES = 20_000
MAX_BYTES = 400_000

DEFAULT_DICT = "search_dict_syn"
ALIAS_TABLE_DEFAULT = "search_entity_alias"
BRIDGE_TABLE = "search_synonym_bridge"


class LimitError(ValueError):
    """Карта длиннее практического потолка — вместо тихой обрезки код поднимает эту ошибку."""


def escape_term(term: str) -> str:
    """Экранирование запятой и обратного слэша внутри терма Solr-правила."""
    s = (term or "").strip()
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace(",", "\\,")


def split_alias_csv(aliases: str) -> list[str]:
    """Разобрать CSV алиасов; термы с экранированной запятой не режутся."""
    out, cur, i, s = [], [], 0, aliases or ""
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            cur.append(s[i + 1])
            i += 2
            continue
        if ch == ",":
            t = "".join(cur).strip()
            if t:
                out.append(t)
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    t = "".join(cur).strip()
    if t:
        out.append(t)
    return out


def rule_from_alias_csv(aliases: str) -> str | None:
    """Двусторонний класс Solr: a, b, c. Один терм — не правило (passthrough и так)."""
    terms = [escape_term(t) for t in split_alias_csv(aliases)]
    terms = [t for t in terms if t]
    # уникальные с сохранением порядка
    seen, uniq = set(), []
    for t in terms:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    if len(uniq) < 2:
        return None
    return ", ".join(uniq)


def rule_one_way(lhs: str, rhs: str) -> str | None:
    """Одностороннее правило Solr: lhs => rhs (каждый бок — один или несколько термов)."""
    left = [escape_term(t) for t in split_alias_csv(lhs)]
    right = [escape_term(t) for t in split_alias_csv(rhs)]
    left = [t for t in left if t]
    right = [t for t in right if t]
    if not left or not right:
        return None
    return "%s => %s" % (", ".join(left), ", ".join(right))


def rule_from_bridge_row(rule: str) -> str | None:
    """Строка кэша моста уже в Solr-формате; нормализуем термы и экранирование."""
    raw = (rule or "").strip()
    if not raw or raw.startswith("#"):
        return None
    if "=>" in raw:
        left, right = raw.split("=>", 1)
        return rule_one_way(left, right)
    return rule_from_alias_csv(raw)


def compile_rules(alias_rows, bridge_rows=None) -> str:
    """Собрать Solr-карту: одна строка — одно правило. Источники раздельно по смыслу."""
    rules = []
    seen = set()

    def add(rule: str | None):
        if not rule:
            return
        key = rule.lower()
        if key in seen:
            return
        seen.add(key)
        rules.append(rule)

    for row in alias_rows or []:
        if isinstance(row, dict):
            add(rule_from_alias_csv(row.get("aliases") or ""))
        else:
            add(rule_from_alias_csv(str(row)))

    for row in bridge_rows or []:
        if isinstance(row, dict):
            if "lhs" in row or "rhs" in row:
                add(rule_one_way(row.get("lhs") or "", row.get("rhs") or ""))
            else:
                add(rule_from_bridge_row(row.get("rule") or ""))
        else:
            add(rule_from_bridge_row(str(row)))

    rules.sort(key=lambda r: r.lower())
    return "\n".join(rules)


def check_limits(solr_map: str, max_rules: int = MAX_RULES, max_bytes: int = MAX_BYTES) -> None:
    """П. 13: сверх лимита — ошибка, не тихая обрезка."""
    text = solr_map or ""
    n_rules = 0 if not text.strip() else len(text.splitlines())
    n_bytes = len(text.encode("utf-8"))
    if n_rules > max_rules:
        raise LimitError(
            "solr synonyms: %d правил > лимита %d (F6_SYNONYMS_FACTS §3.2) — "
            "карта не обрезается" % (n_rules, max_rules))
    if n_bytes > max_bytes:
        raise LimitError(
            "solr synonyms: %d байт > лимита %d (F6_SYNONYMS_FACTS §3.2) — "
            "карта не обрезается" % (n_bytes, max_bytes))


def sql_literal(s: str) -> str:
    return "'" + (s or "").replace("'", "''") + "'"


def render_ddl(dict_name: str, solr_map: str) -> str:
    """DROP+CREATE файлом (IF NOT EXISTS карту не меняет — фактура §5.2)."""
    name = (dict_name or DEFAULT_DICT).strip()
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError("некорректное имя словаря: %r" % dict_name)
    body = [
        "-- Ф6.3 solr_synonyms: пересоздание карты",
        "-- источник wiki-alias: search_entity_alias.aliases (двусторонние классы)",
        "-- источник bridge:     search_synonym_bridge.rule (кэш моста на лету)",
        "-- Доки: https://docs.serenedb.com/sql/statements/create_text_search_dictionary/solr-synonyms",
        "\\set ON_ERROR_STOP on",
        "DROP TEXT SEARCH DICTIONARY IF EXISTS %s;" % name,
        "CREATE TEXT SEARCH DICTIONARY %s (" % name,
        "  template = 'solr_synonyms',",
        "  synonyms = %s" % sql_literal(solr_map),
        ");",
        "",
    ]
    return "\n".join(body)


def fetch_source_rows(dsn: str, alias_table: str) -> tuple[list[dict], list[dict]]:
    """Один SELECT на источник → JSON. Обработка классов — в compile_rules, не в SQL-цикле."""
    # Имя таблицы — только [A-Za-z0-9_], как ALIAS_TABLE у wiki_alias.
    if not alias_table or not all(c.isalnum() or c == "_" for c in alias_table):
        raise ValueError("некорректное имя alias-таблицы: %r" % alias_table)

    def one(sql: str) -> list:
        r = subprocess.run(
            ["psql", dsn, "-tAc", sql],
            capture_output=True, text=True, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            # Нет таблицы bridge на старой базе — пустой источник, не падение такта.
            if "search_synonym_bridge" in sql and (
                    "does not exist" in err.lower()
                    or "not found" in err.lower()
                    or "Catalog Error" in err):
                return []
            raise RuntimeError("psql: %s" % (err[:400] or "exit %d" % r.returncode))
        raw = (r.stdout or "").strip()
        if not raw or raw in ("null", "NULL"):
            return []
        try:
            data = json.loads(raw)
        except ValueError as e:
            raise RuntimeError("psql JSON: %s" % e) from e
        return data if isinstance(data, list) else []

    # Источник wiki-alias (комментарий в DDL).
    # list() по пустому набору → NULL; coalesce даёт строку «[]» для json.loads.
    alias_sql = (
        "SELECT coalesce("
        "(SELECT to_json(list(struct_pack(aliases := aliases))) "
        " FROM %s WHERE coalesce(trim(aliases), '') <> ''), '[]')" % alias_table)
    # Источник кэш моста.
    bridge_sql = (
        "SELECT coalesce("
        "(SELECT to_json(list(struct_pack(rule := rule))) "
        " FROM %s WHERE coalesce(trim(rule), '') <> ''), '[]')" % BRIDGE_TABLE)
    return one(alias_sql), one(bridge_sql)


def compile_from_db(dsn: str, alias_table: str, dict_name: str, out_path: str) -> int:
    """Скомпилировать из БД. Пустые источники → словарь не пересоздаём (код 0).

    Возвращает 0 и не трогает out_path при пустой карте (старый файл не применяется).
    """
    alias_rows, bridge_rows = fetch_source_rows(dsn, alias_table)
    solr_map = compile_rules(alias_rows, bridge_rows)
    if not solr_map.strip():
        print("solr synonyms: пустые источники — словарь не пересоздаётся", file=sys.stderr)
        return 0
    check_limits(solr_map)
    ddl = render_ddl(dict_name, solr_map)
    out = out_path or os.path.join(
        os.environ.get("CSV_DIR", "/var/lib/serenedb"),
        "solr_synonyms_%s.sql" % dict_name)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(ddl)
    print("solr synonyms: правил %d, байт %d → %s" % (
        len(solr_map.splitlines()), len(solr_map.encode("utf-8")), out))
    return 1  # 1 = файл записан (для --apply); не код ошибки


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ф6.3 compile solr_synonyms dictionary")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="SELECT из alias+bridge → DDL-файл")
    c.add_argument("--dsn", default=os.environ.get(
        "SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres"))
    c.add_argument("--dict", default=os.environ.get(
        "ASK_SOLR_SYNONYMS_DICT") or os.environ.get("SOLR_SYN_DICT") or DEFAULT_DICT)
    c.add_argument("--alias-table", default=os.environ.get(
        "ALIAS_TABLE", ALIAS_TABLE_DEFAULT))
    c.add_argument("--out", default="")
    c.add_argument("--apply", action="store_true",
                   help="после записи выполнить psql -f (иначе только файл)")

    w = sub.add_parser("write-ddl", help="карта из файла → DDL (оффлайн/тесты)")
    w.add_argument("--dict", default=DEFAULT_DICT)
    w.add_argument("--map-file", required=True)
    w.add_argument("--out", required=True)

    t = sub.add_parser("compile-rows", help="JSON рядов → карта/DDL (оффлайн)")
    t.add_argument("--alias-json", default="")
    t.add_argument("--bridge-json", default="")
    t.add_argument("--dict", default=DEFAULT_DICT)
    t.add_argument("--out-map", default="")
    t.add_argument("--out-ddl", default="")

    args = p.parse_args(argv)

    if args.cmd == "write-ddl":
        raw = sys.stdin.read() if args.map_file == "-" else open(
            args.map_file, encoding="utf-8").read()
        check_limits(raw)
        open(args.out, "w", encoding="utf-8").write(render_ddl(args.dict, raw))
        return 0

    if args.cmd == "compile-rows":
        alias_rows = json.loads(open(args.alias_json, encoding="utf-8").read()) if args.alias_json else []
        bridge_rows = json.loads(open(args.bridge_json, encoding="utf-8").read()) if args.bridge_json else []
        solr_map = compile_rules(alias_rows, bridge_rows)
        check_limits(solr_map)
        if args.out_map:
            open(args.out_map, "w", encoding="utf-8").write(solr_map)
        if args.out_ddl:
            if not solr_map.strip():
                print("empty map — ddl not written", file=sys.stderr)
                return 0
            open(args.out_ddl, "w", encoding="utf-8").write(
                render_ddl(args.dict, solr_map))
        if not args.out_map and not args.out_ddl:
            sys.stdout.write(solr_map)
        return 0

    if args.cmd == "compile":
        out = args.out
        if not out:
            exch = os.environ.get("CSV_DIR", "/var/lib/serenedb")
            out = os.path.join(exch, "solr_synonyms_%s.sql" % args.dict)
        try:
            wrote = compile_from_db(args.dsn, args.alias_table, args.dict, out)
        except LimitError as e:
            print(str(e), file=sys.stderr)
            return 2
        # wrote==1 только если карта непустая и файл записан в этом запуске
        if args.apply and wrote == 1:
            r = subprocess.run(["psql", args.dsn, "-q", "-f", out],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print("solr synonyms apply: %s" % (
                    (r.stderr or r.stdout or "")[:400]), file=sys.stderr)
                return r.returncode
            print("solr synonyms: словарь %s обновлён" % args.dict)
        return 0

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LimitError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print("solr synonyms: %s" % e, file=sys.stderr)
        sys.exit(1)
