#!/usr/bin/env python3
"""Ф6.3 / С5: компиляция Solr-карты — оффлайн-эталон и тесты.

Тактовый путь (build.sh, после wiki_alias): psql -f solr_synonyms_compile.sql
(Э1б, п. 20 — без Python-посредника). Этот модуль остаётся для замков и write-ddl.

Списков слов в коде нет: правила приходят из search_entity_alias (wiki-alias).
Ключи карты — стемы одиночных слов через штатный ts_lexize(search_dict_stem)
(Snowball по locale словаря). Многословные алиасы в карту не кладутся (С3).
Словарь — pipeline: text(stemming) → solr_synonyms (Cookbook › Synonyms).

Отдельный orphan-слот кэша моста снят (С3, docs/SYNONYM_BRIDGE_DECISION.md).
Лимиты — docs/F6_SYNONYMS_FACTS.md §3.2 (~20 000 правил / ~400 КБ inline OK;
длиннее — честная ошибка, п. 13 TARGET).

Доки: CREATE TEXT SEARCH DICTIONARY › pipeline / solr_synonyms / text;
Cookbook › Stemming and Stopwords; Cookbook › Synonyms.

Запуск из такта (wiki_alias.sh / CLI):
  python3 solr_synonyms_build.py compile --dsn \"$DSN\" [--dict NAME] [--out FILE]
  python3 solr_synonyms_build.py write-ddl --dict NAME --map-file MAP [--out FILE]

Оффлайн: escape_term / rule_from_alias_csv / compile_rules / check_limits /
render_ddl / is_single_word — без сети и без LLM.
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
STEM_DICT_DEFAULT = "search_dict_stem"
ALIAS_STEM_DICT = "search_dict_alias_stem"
DEFAULT_LOCALE = "ru_RU.UTF-8"


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


def is_single_word(term: str) -> bool:
    """Одиночное слово (без пробелов/табов) — кандидат в стем-ключ карты (С3)."""
    s = (term or "").strip()
    if not s:
        return False
    return not any(c.isspace() for c in s)


def normalize_locale(locale: str) -> str:
    """DICT_LOCALE из build.sh бывает ru_RU.utf8 — для CREATE нужен ICU-вид."""
    loc = (locale or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE
    if loc.lower().endswith(".utf8") and not loc.lower().endswith(".utf-8"):
        loc = loc[:-4] + "UTF-8"
    return loc


def rule_from_terms(terms) -> str | None:
    """Двусторонний класс Solr из уже нормализованных термов. Один — не правило."""
    cleaned = [escape_term(t) for t in (terms or [])]
    cleaned = [t for t in cleaned if t]
    seen, uniq = set(), []
    for t in cleaned:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    if len(uniq) < 2:
        return None
    return ", ".join(uniq)


def rule_from_alias_csv(aliases: str, stem_map=None) -> str | None:
    """Класс из CSV алиасов. stem_map: поверхность → стем; без него — поверхность.

    В карту идут только одиночные слова (С3). При stem_map ключи — стемы движка.
    """
    surfaces = [t for t in split_alias_csv(aliases) if is_single_word(t)]
    if not surfaces:
        return None
    if stem_map is None:
        return rule_from_terms(surfaces)
    stems = []
    for t in surfaces:
        st = stem_map.get(t)
        if st is None:
            st = stem_map.get(t.lower())
        if st:
            stems.append(st)
    return rule_from_terms(stems)


def compile_rules(alias_rows, stem_map=None) -> str:
    """Собрать Solr-карту: одна строка — одно правило. Источник — alias CSV.

    stem_map — опциональная карта поверхность→стем (из ts_lexize). Без неё
    оффлайн-тесты работают на поверхности одиночных слов.
    """
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
            add(rule_from_alias_csv(row.get("aliases") or "", stem_map))
        else:
            add(rule_from_alias_csv(str(row), stem_map))

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


def render_ddl(dict_name: str, solr_map: str, locale: str = DEFAULT_LOCALE) -> str:
    """DROP+CREATE pipeline text(stem)→solr_synonyms (IF NOT EXISTS карту не меняет)."""
    name = (dict_name or DEFAULT_DICT).strip()
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError("некорректное имя словаря: %r" % dict_name)
    loc = normalize_locale(locale)
    body = [
        "-- Ф6.3/С5 solr_synonyms: pipeline text(stem) → solr_synonyms",
        "-- источник wiki-alias: search_entity_alias.aliases (стем-ключи одиночных)",
        "-- Доки: https://docs.serenedb.com/cookbook/search/synonyms",
        "--       https://docs.serenedb.com/sql/statements/create_text_search_dictionary/pipeline",
        "\\set ON_ERROR_STOP on",
        "DROP TEXT SEARCH DICTIONARY IF EXISTS %s;" % name,
        "CREATE TEXT SEARCH DICTIONARY %s (" % name,
        "  template = 'pipeline',",
        "  step1_template = 'text',",
        "  step1_locale = %s," % sql_literal(loc),
        "  step1_case = 'lower',",
        "  step1_stemming = true,",
        "  step2_template = 'solr_synonyms',",
        "  step2_synonyms = %s" % sql_literal(solr_map),
        ");",
        "",
    ]
    return "\n".join(body)


def render_alias_stem_index_ddl(locale: str, alias_table: str = ALIAS_TABLE_DEFAULT) -> str:
    """Гарантия: search_dict_alias_stem + alias_idx на нём (С5, не откат к search_dict)."""
    if not alias_table or not all(c.isalnum() or c == "_" for c in alias_table):
        raise ValueError("некорректное имя alias-таблицы: %r" % alias_table)
    loc = normalize_locale(locale)
    return "\n".join([
        "CREATE TEXT SEARCH DICTIONARY IF NOT EXISTS %s (" % ALIAS_STEM_DICT,
        "  template = 'text', locale = %s, case = 'lower'," % sql_literal(loc),
        "  stemming = true, accent = false,",
        "  frequency = true, position = true, norm = true);",
        "DROP INDEX IF EXISTS alias_idx;",
        "CREATE INDEX alias_idx ON %s" % alias_table,
        "  USING inverted(aliases %s, src_table) INCLUDE (src_table);" % ALIAS_STEM_DICT,
        "GRANT SELECT ON alias_idx TO serene_ro;",
        "VACUUM (REFRESH_TABLE) %s;" % alias_table,
        "",
    ])


def fetch_source_rows(dsn: str, alias_table: str) -> list[dict]:
    """Один SELECT → JSON рядов alias. Обработка классов — в compile_rules, не в SQL-цикле."""
    if not alias_table or not all(c.isalnum() or c == "_" for c in alias_table):
        raise ValueError("некорректное имя alias-таблицы: %r" % alias_table)

    # list() по пустому набору → NULL; coalesce даёт строку «[]» для json.loads.
    # Доки: SELECT / to_json / list — штатный путь выгрузки; карта пишется
    # CREATE TEXT SEARCH DICTIONARY › solr_synonyms (SYNONYMS inline).
    alias_sql = (
        "SELECT coalesce("
        "(SELECT to_json(list(struct_pack(aliases := aliases))) "
        " FROM %s WHERE coalesce(trim(aliases), '') <> ''), '[]')" % alias_table)
    r = subprocess.run(
        ["psql", dsn, "-tAc", alias_sql],
        capture_output=True, text=True, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError("psql: %s" % (err[:400] or "exit %d" % r.returncode))
    raw = (r.stdout or "").strip()
    if not raw or raw in ("null", "NULL"):
        return []
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise RuntimeError("psql JSON: %s" % e) from e
    return data if isinstance(data, list) else []


def collect_single_terms(alias_rows) -> list[str]:
    """Уникальные одиночные слова из рядов alias (порядок стабилен)."""
    seen, out = set(), []
    for row in alias_rows or []:
        aliases = row.get("aliases") if isinstance(row, dict) else str(row)
        for t in split_alias_csv(aliases or ""):
            if not is_single_word(t):
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def fetch_stem_map(dsn: str, terms: list[str], stem_dict: str = STEM_DICT_DEFAULT) -> dict:
    """Поверхность → стем через ts_lexize(stem_dict). Списков слов в коде нет."""
    if not stem_dict or not all(c.isalnum() or c == "_" for c in stem_dict):
        raise ValueError("некорректное имя stem-словаря: %r" % stem_dict)
    if not terms:
        return {}
    # Один SELECT: VALUES + ts_lexize → JSON список пар. Доки: ts_lexize / stemming.
    values = ", ".join("(%s)" % sql_literal(t) for t in terms)
    sql = (
        "SELECT coalesce(to_json(list(struct_pack("
        "  term := v.term, "
        "  stem := coalesce((ts_lexize('%s', v.term))[1], v.term)"
        "))), '[]')"
        " FROM (VALUES %s) AS v(term)" % (stem_dict, values))
    r = subprocess.run(
        ["psql", dsn, "-tAc", sql],
        capture_output=True, text=True, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RuntimeError("psql stem: %s" % (err[:400] or "exit %d" % r.returncode))
    raw = (r.stdout or "").strip()
    if not raw or raw in ("null", "NULL"):
        return {}
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise RuntimeError("psql stem JSON: %s" % e) from e
    out = {}
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            term = row.get("term")
            stem = row.get("stem")
            if term and stem:
                out[term] = stem
                out[str(term).lower()] = stem
    return out


def resolve_locale(dsn: str, locale_arg: str = "") -> str:
    """Locale из CLI/env, иначе DEFAULT. Не хардкодим базу — берём настройку сборки."""
    if locale_arg and locale_arg.strip():
        return normalize_locale(locale_arg)
    env = (
        os.environ.get("SEARCH_DICT_LOCALE")
        or os.environ.get("BUILD_DICT_LOCALE")
        or os.environ.get("DICT_LOCALE")
        or "")
    if env.strip():
        return normalize_locale(env)
    # запасной: locale основного search_dict, если движок отдаёт
    sql = (
        "SELECT coalesce("
        "(SELECT locale FROM duckdb_text_search_dictionaries()"
        " WHERE database_name = current_database()"
        "   AND dictionary_name = 'search_dict' LIMIT 1), '')")
    r = subprocess.run(
        ["psql", dsn, "-tAc", sql],
        capture_output=True, text=True, check=False)
    if r.returncode == 0:
        got = (r.stdout or "").strip()
        if got and got not in ("null", "NULL"):
            return normalize_locale(got)
    return DEFAULT_LOCALE


def compile_from_db(dsn: str, alias_table: str, dict_name: str, out_path: str,
                    stem_dict: str = STEM_DICT_DEFAULT, locale: str = "") -> int:
    """Скомпилировать из БД. Пустые источники → словарь не пересоздаём (код 0).

    Возвращает 0 и не трогает out_path при пустой карте (старый файл не применяется).
    """
    alias_rows = fetch_source_rows(dsn, alias_table)
    terms = collect_single_terms(alias_rows)
    stem_map = fetch_stem_map(dsn, terms, stem_dict=stem_dict)
    solr_map = compile_rules(alias_rows, stem_map=stem_map)
    if not solr_map.strip():
        print("solr synonyms: пустые источники — словарь не пересоздаётся", file=sys.stderr)
        return 0
    check_limits(solr_map)
    loc = resolve_locale(dsn, locale)
    ddl = render_ddl(dict_name, solr_map, locale=loc)
    out = out_path or os.path.join(
        os.environ.get("CSV_DIR", "/var/lib/serenedb"),
        "solr_synonyms_%s.sql" % dict_name)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(ddl)
    print("solr synonyms: правил %d, байт %d → %s (pipeline stem, locale=%s)" % (
        len(solr_map.splitlines()), len(solr_map.encode("utf-8")), out, loc))
    return 1  # 1 = файл записан (для --apply); не код ошибки


def apply_alias_stem_index(dsn: str, alias_table: str, locale: str) -> None:
    """Пересоздать alias_idx на search_dict_alias_stem (идемпотентно каждый compile)."""
    ddl = render_alias_stem_index_ddl(locale, alias_table)
    # VACUUM отдельно от DDL (как wiki_alias / corpus_merge).
    parts = ddl.strip().split("VACUUM (REFRESH_TABLE)")
    head = parts[0].rstrip().rstrip(";") + ";\n"
    path = os.path.join(
        os.environ.get("CSV_DIR", "/var/lib/serenedb"),
        "alias_idx_stem_ensure.sql")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
    r = subprocess.run(
        ["psql", dsn, "-q", "-f", path],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("alias_idx stem: %s" % (
            (r.stderr or r.stdout or "")[:400] or "exit %d" % r.returncode))
    if len(parts) > 1:
        vac = "VACUUM (REFRESH_TABLE)" + parts[1]
        r2 = subprocess.run(
            ["psql", dsn, "-q", "-c", vac],
            capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError("alias_idx VACUUM: %s" % (
                (r2.stderr or r2.stdout or "")[:400] or "exit %d" % r2.returncode))
    print("solr synonyms: alias_idx → %s" % ALIAS_STEM_DICT, file=sys.stderr)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ф6.3/С5 compile solr_synonyms dictionary")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compile", help="SELECT из search_entity_alias → DDL-файл")
    c.add_argument("--dsn", default=os.environ.get(
        "SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres"))
    c.add_argument("--dict", default=os.environ.get(
        "ASK_SOLR_SYNONYMS_DICT") or os.environ.get("SOLR_SYN_DICT") or DEFAULT_DICT)
    c.add_argument("--alias-table", default=os.environ.get(
        "ALIAS_TABLE", ALIAS_TABLE_DEFAULT))
    c.add_argument("--stem-dict", default=os.environ.get(
        "ASK_STEM_DICT") or STEM_DICT_DEFAULT)
    c.add_argument("--locale", default="")
    c.add_argument("--out", default="")
    c.add_argument("--apply", action="store_true",
                   help="после записи выполнить psql -f + alias_idx stem")
    c.add_argument("--skip-alias-index", action="store_true",
                   help="не пересоздавать alias_idx (только словарь)")

    w = sub.add_parser("write-ddl", help="карта из файла → DDL (оффлайн/тесты)")
    w.add_argument("--dict", default=DEFAULT_DICT)
    w.add_argument("--map-file", required=True)
    w.add_argument("--out", required=True)
    w.add_argument("--locale", default=DEFAULT_LOCALE)

    t = sub.add_parser("compile-rows", help="JSON рядов alias → карта/DDL (оффлайн)")
    t.add_argument("--alias-json", default="")
    t.add_argument("--stem-json", default="",
                   help="опционально {surface:stem}; без файла — поверхность")
    t.add_argument("--dict", default=DEFAULT_DICT)
    t.add_argument("--locale", default=DEFAULT_LOCALE)
    t.add_argument("--out-map", default="")
    t.add_argument("--out-ddl", default="")

    args = p.parse_args(argv)

    if args.cmd == "write-ddl":
        raw = sys.stdin.read() if args.map_file == "-" else open(
            args.map_file, encoding="utf-8").read()
        check_limits(raw)
        open(args.out, "w", encoding="utf-8").write(
            render_ddl(args.dict, raw, locale=args.locale))
        return 0

    if args.cmd == "compile-rows":
        alias_rows = json.loads(open(args.alias_json, encoding="utf-8").read()) if args.alias_json else []
        stem_map = None
        if args.stem_json:
            stem_map = json.loads(open(args.stem_json, encoding="utf-8").read())
        solr_map = compile_rules(alias_rows, stem_map=stem_map)
        check_limits(solr_map)
        if args.out_map:
            open(args.out_map, "w", encoding="utf-8").write(solr_map)
        if args.out_ddl:
            if not solr_map.strip():
                print("empty map — ddl not written", file=sys.stderr)
                return 0
            open(args.out_ddl, "w", encoding="utf-8").write(
                render_ddl(args.dict, solr_map, locale=args.locale))
        if not args.out_map and not args.out_ddl:
            sys.stdout.write(solr_map)
        return 0

    if args.cmd == "compile":
        out = args.out
        if not out:
            exch = os.environ.get("CSV_DIR", "/var/lib/serenedb")
            out = os.path.join(exch, "solr_synonyms_%s.sql" % args.dict)
        try:
            wrote = compile_from_db(
                args.dsn, args.alias_table, args.dict, out,
                stem_dict=args.stem_dict, locale=args.locale)
        except LimitError as e:
            print(str(e), file=sys.stderr)
            return 2
        if args.apply and wrote == 1:
            r = subprocess.run(["psql", args.dsn, "-q", "-f", out],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print("solr synonyms apply: %s" % (
                    (r.stderr or r.stdout or "")[:400]), file=sys.stderr)
                return r.returncode
            print("solr synonyms: словарь %s обновлён (pipeline stem)" % args.dict)
            if not args.skip_alias_index:
                loc = resolve_locale(args.dsn, args.locale)
                try:
                    apply_alias_stem_index(args.dsn, args.alias_table, loc)
                except RuntimeError as e:
                    print(str(e), file=sys.stderr)
                    return 1
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
