#!/usr/bin/env python3
"""Config-builder пакетного транспорта: итоговый контур сущностей для агента.

Контракт — docs/PACKET_CONTRACT.md §10, камень Б2 плана PLAN_MVP_PACKET_TRANSPORT §13.
Источник истины отбора — Ubuntu: контур считается здесь теми же тремя признаками,
что serene_sync._service_skip, и агент получает готовый список через GET /agent/config
(сам агент ничего не исключает и не добавляет).

Один заход на базу:
  1. отбор контура — ОДНИМ запросом в движке (п. 20 TARGET): перепись base_profile
     (rows>0) ∩/∖ признаки search_entity_force (mode=load возвращает источник,
     mode=skip убирает — слово владельца сильнее остальных) и search_entity_class
     (cls='service'), с приоритетом force > class — форма serene_sync._service_skip;
  2. only_binary — единственный признак в Python, это разбор снимка $metadata из
     packet_metadata (её пишет packet_apply), а не запрос к данным; строки для
     base_id нет — признак не применяется, остаются census+class+force;
  3. итог — в запись базы в PACKET_BASES (config.entities); config_version растёт
     на 1, только если список или params изменились (без изменений файл не трогается,
     и агент не дёргается);
  4. search_entity_skipped перезаписывается причинами в форме serene_sync (п. 13
     TARGET: исключённое видно с причиной).

Файл баз переписывается атомарно (temp+replace) read-modify-write: токены, identity
и записи других баз сохраняются как были.

Журнал — построчно в stderr. --dry-run печатает итоговый список и причины без
единой записи (ни в файл баз, ни в витрину).

Конфиг — аргументы и env: SERENEDB_DSN, PACKET_BASES, PACKET_CONFIG_*.
Только stdlib.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile

DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
PACKET_BASES = os.environ.get("PACKET_BASES", "/etc/1c-packet-bases.json")

# Параметры такта агента для начального конфига (форма ответа /agent/config —
# контракт §8). Уже записанные в файле params сохраняются, эти значения —
# только для базы, у которой конфига ещё не было.
PACKET_CONFIG_PAGE_SIZE = int(os.environ.get("PACKET_CONFIG_PAGE_SIZE", "10000"))
PACKET_CONFIG_TACT_SECONDS = int(os.environ.get("PACKET_CONFIG_TACT_SECONDS", "1200"))
PACKET_CONFIG_CHUNK_MB = int(os.environ.get("PACKET_CONFIG_CHUNK_MB", "32"))

# Читающая роль витрины для GRANT на search_entity_skipped. Имя — идентификатор,
# приходит из окружения, поэтому пропускается только форма идентификатора, иначе
# берётся умолчание (то же решение, что serene_sync._ro_role и packet_apply).
_ro_env = os.environ.get("PACKET_CONFIG_RO_ROLE", "serene_ro")
RO_ROLE = _ro_env if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", _ro_env) else "serene_ro"

# Типы, которые штатный OData 1С не отдаёт в JSON (poc_load_entity.UNSERVABLE_TYPES).
_BINARY_TYPES = ("Edm.Stream", "Edm.Binary")

# Причины исключения — дословно как serene_sync._service_skip: по этим строкам
# владелец и бот читают search_entity_skipped, разносить формы двух писателей
# было бы вторым местом истины.
WHY_FORCE = "решение владельца (search_entity_force)"
WHY_CLASS = "размечено служебным (search_entity_class)"
WHY_BINARY = "всё содержимое двоичное, текста нет ($metadata)"


def _log(msg: str) -> None:
    sys.stderr.write("config %s\n" % msg)


def _lit(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def safe_col(name) -> str:
    # Та же функция, что poc_load_entity.safe_col (и packet_apply.safe_col):
    # имя колонки для любого алфавита. Ключи search_entity_class/force хранят
    # именно такие имена в нижнем регистре (serene_sync._service_skip).
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


# --- доступ к витрине (подменяется в оффлайн-пробе) ----------------------------


def _rows(dsn: str, sql: str) -> list[tuple]:
    """Строки запроса списком кортежей. SQL через stdin и вывод --csv — как
    poc_load_entity._psql_rows: запятые и переводы строк в значениях (снимок
    $metadata — 16 МБ XML) разбираются CSV-ридером, а не угадыванием."""
    p = subprocess.run(["psql", dsn, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])
    return [tuple(r) for r in csv.reader(io.StringIO(p.stdout)) if r]


def _exec(dsn: str, sql: str) -> None:
    p = subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:200])


# --- признак only_binary по снимку $metadata -------------------------------------


def _props_by_type(xml: str) -> dict:
    """Поля сущностей из $metadata — тот же разбор, что poc_load_entity._load_metadata."""
    props = {}
    for m in re.finditer(r'<EntityType\s+Name="([^"]+)"(.*?)</EntityType>', xml, re.S):
        props[m.group(1)] = re.findall(
            r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', m.group(2))
    return props


def _only_binary(props: dict, entity_set: str) -> bool:
    """Семантика poc_load_entity.only_binary: всё содержимое двоичное, а
    человекочитаемых строковых полей нет. Не знаем сущность — считается грузимой."""
    p = props.get(entity_set) or props.get(entity_set + "_RecordType") or []
    if not p:
        return False
    names = [n for n, _ in p]
    typed = {n[:-5] for n in names if n.endswith("_Type")}   # у составной ссылки есть пара
    blob = (any(n.endswith("_Base64Data") for n in names)
            or any(t in _BINARY_TYPES for _, t in p))
    human = [n for n, t in p
             if t == "Edm.String" and not n.endswith(("_Type", "_Key", "_Base64Data"))
             and n not in typed
             and n not in ("Ref_Key", "DataVersion", "Predefined", "PredefinedDataName")]
    return blob and not human


# --- контур: отбор одним SQL в движке ---------------------------------------------
#
# П. 20 TARGET: отбор (перепись ∩/∖ признаки с приоритетом force > class) делает
# движок одним запросом — три запроса со склейкой в Python были сочтены снайпером
# собственной обработкой данных вне базы. В Python остаётся ровно то, чего у движка
# нет: разбор снимка $metadata (признак only_binary).
# [замер-основание 06.08, живая ut_test, сборка 26.07.3] форма запроса ниже даёт
# то же, что прежняя Python-склейка: keep=784, service=805 — число в число.

# Якоря-комментарии: движок их игнорирует, а оффлайн-проба по ним различает запросы.
_TABLES_SQL = ("/* tables */ SELECT table_name FROM duckdb_tables() "
               "WHERE database_name = current_database() "
               "AND table_name IN ('search_entity_class', 'search_entity_force');")
# Фильтр по database_name — ловушка techContext №25: duckdb_tables() отдаёт таблицы
# всех присоединённых баз, без фильтра чужая search_entity_class выглядела бы своей.
# Колонка database_name проверена живьём на 26.07.3 (доки: Metadata Functions).

_SAFE_COL_SQL = ("lower(trim(BOTH '_' FROM "
                 "regexp_replace(entity, '[^\\p{L}\\p{N}_]', '_', 'g')))")
# Выражение дословно повторяет safe_col(entity).lower() (проверено живьём: классы
# RE2 \p{L}\p{N} работают, lower+trim дают тот же ключ, что и Python-версия).


def _contour_sql(has_class: bool, has_force: bool) -> str:
    """Один запрос контура: (entity, verdict) для каждой непустой сущности.

    Ветки CASE и JOIN'ы включаются только для существующих таблиц признаков:
    нет class — нет ветки 'service', нет обеих — голый 'keep'. Порядок веток в
    CASE — приоритет serene_sync._service_skip: слово владельца (force) раньше
    разметки (class)."""
    branches = []
    joins = []
    if has_force:
        branches.append("WHEN lower(trim(COALESCE(f.mode,''))) = 'load' THEN 'load'")
        branches.append("WHEN lower(trim(COALESCE(f.mode,''))) = 'skip' THEN 'skip'")
        joins.append("LEFT JOIN search_entity_force f ON f.src_table = k.k")
    if has_class:
        branches.append("WHEN c.cls = 'service' THEN 'service'")
        joins.append("LEFT JOIN search_entity_class c ON c.src_table = k.k")
    head = ("/* contour */ WITH src AS (SELECT entity, %s AS k0 FROM base_profile "
            "WHERE rows > 0), keyed AS (SELECT entity, CASE WHEN k0 = '' OR k0 ~ '^[0-9]' "
            "THEN 'c_' || k0 ELSE k0 END AS k FROM src) " % _SAFE_COL_SQL)
    if not branches:
        return head + "SELECT k.entity, 'keep' AS verdict FROM keyed k ORDER BY 1;"
    case = "CASE %s ELSE 'keep' END AS verdict" % " ".join(branches)
    return head + "SELECT k.entity, %s FROM keyed k %s ORDER BY 1;" % (case, " ".join(joins))


def compute_contour(rows: list, props: dict | None) -> tuple[list[str], dict]:
    """Итоговый контур и причины по ответу движка (entity, verdict).

    'load' — грузим (слово владельца сильнее любого признака), 'skip'/'service' —
    причина из вердикта; only_binary применяется здесь, к вердикту 'keep', — это
    разбор $metadata, а не запрос к данным."""
    skip = {}
    entities = []
    for es, verdict in rows:
        if verdict == "load":
            entities.append(es)
        elif verdict == "skip":
            skip[es] = WHY_FORCE
        elif verdict == "service":
            skip[es] = WHY_CLASS
        elif props is not None and _only_binary(props, es):
            skip[es] = WHY_BINARY
        else:
            entities.append(es)
    return sorted(entities), skip


def _skipped_sql(skip: dict) -> str:
    # Форма записи — как serene_sync.main: таблица с той же схемой, права читателю
    # выдаются сразу (без GRANT читающая роль видит пустоту — то же молчание,
    # против которого таблица заведена), перечень перезаписывается целиком.
    vals = ",".join("(%s,%s)" % (_lit(e), _lit(w)) for e, w in sorted(skip.items()))
    return ("CREATE TABLE IF NOT EXISTS search_entity_skipped "
            "(entity VARCHAR, why VARCHAR, seen_at TIMESTAMP);\n"
            "GRANT SELECT ON search_entity_skipped TO %s;\n"
            "DELETE FROM search_entity_skipped;\n"
            "INSERT INTO search_entity_skipped "
            "SELECT e, w, now() FROM (VALUES %s) AS s(e, w);"
            % (RO_ROLE, vals))


def _read_sources(dsn: str, base_id: str):
    """Вердикты контура и снимок $metadata из витрины. Ровно три обращения:
    существование таблиц признаков (/* tables */), контур одним запросом
    (/* contour */), снимок (/* metadata */). Контур читается строго — его
    падение означает, что переписи нет или она нечитаема, и заход отменяется;
    снимок при отсутствии таблицы считается отсутствующим (признак only_binary
    тогда не применяется — та же осторожность в одну сторону, что у serene_sync:
    неразмеченное грузится)."""
    have = {r[0] for r in _rows(dsn, _TABLES_SQL) if r}
    rows = [(r[0], r[1]) for r in _rows(
        dsn, _contour_sql("search_entity_class" in have, "search_entity_force" in have))
        if len(r) > 1]
    try:
        meta = [r[0] for r in _rows(
            dsn, "/* metadata */ SELECT content FROM packet_metadata WHERE base_id = %s"
            % _lit(base_id)) if r]
    except RuntimeError:
        meta = []
    props = _props_by_type(meta[0]) if meta else None
    return rows, props


# --- файл баз -----------------------------------------------------------------------


def _load_bases(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(f"файл баз {path} не читается: {e}")
    if not isinstance(data, dict):
        raise RuntimeError(f"файл баз {path} не JSON-объект")
    return data


def _write_bases_atomic(path: str, data: dict) -> None:
    # temp+replace в том же каталоге: приёмник в любой момент видит либо старый,
    # либо новый файл целиком, но не половину записи.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                               prefix=".bases-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(base_id: str, dsn: str, bases_path: str, dry_run: bool = False) -> int:
    """Один заход на базу. 0 — контур посчитан (записан или совпал), 2 — отказ."""
    data = _load_bases(bases_path)
    rec = data.get(base_id)
    if not isinstance(rec, dict):
        _log(f"FATAL: база {base_id!r} отсутствует в {bases_path} — записать конфиг "
             "некуда (токен и identity заводит комплект)")
        return 2
    try:
        rows, props = _read_sources(dsn, base_id)
    except RuntimeError as e:
        _log(f"FATAL: контур-запрос не прошёл (переписи нет или она нечитаема): {e}; "
             "конфиг не тронут")
        return 2
    if not rows:
        _log(f"FATAL: перепись base_profile пуста — контур считать не из чего; "
             "конфиг не тронут")
        return 2
    verdicts = {}
    for _es, v in rows:
        verdicts[v] = verdicts.get(v, 0) + 1
    _log(f"перепись: {len(rows)} непустых сущностей; вердикты движка: "
         + ", ".join("%s=%d" % (v, n) for v, n in sorted(verdicts.items()))
         + f"; $metadata={'есть' if props is not None else 'нет (признак only_binary не применяется)'}")

    entities, skip = compute_contour(rows, props)
    by_why = {}
    for w in skip.values():
        by_why[w] = by_why.get(w, 0) + 1
    _log("контур: %d сущностей, исключено %d (%s)"
         % (len(entities), len(skip),
            "; ".join("%s — %d" % (w, n) for w, n in sorted(by_why.items())) or "без исключений"))
    for e, w in sorted(skip.items()):
        _log(f"  исключена {e}: {w}")

    old_cfg = rec.get("config") if isinstance(rec.get("config"), dict) else {}
    params = old_cfg.get("params") or {
        "page_size": PACKET_CONFIG_PAGE_SIZE,
        "tact_seconds": PACKET_CONFIG_TACT_SECONDS,
        "chunk_mb": PACKET_CONFIG_CHUNK_MB,
    }
    cur = int(old_cfg.get("config_version", 0) or 0)
    changed = old_cfg.get("entities") != entities or old_cfg.get("params") != params

    if dry_run:
        if changed:
            _log("dry-run: записей нет; config_version вырос бы до %d" % (cur + 1))
        else:
            _log("dry-run: записей нет; config_version без изменений (%d)" % cur)
        for e in entities:
            _log(f"  + {e}")
        return 0

    # search_entity_skipped — независимо от изменения контура: причины видны
    # по состоянию на этот заход (форма записи — serene_sync).
    if skip:
        _exec(dsn, _skipped_sql(skip))
        _log(f"search_entity_skipped перезаписана: {len(skip)} строк с причинами")

    if not changed:
        _log(f"без изменений: config_version={cur} не тронут, агент не дёргается")
        return 0
    new_cfg = dict(old_cfg)
    new_cfg["config_version"] = cur + 1
    new_cfg["entities"] = entities
    new_cfg["params"] = params
    rec["config"] = new_cfg
    data[base_id] = rec
    _write_bases_atomic(bases_path, data)
    _log(f"записано: config_version {cur} → {cur + 1}, сущностей {len(entities)}, "
         "токены и записи других баз сохранены")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="config-builder контура сущностей агента (контракт §10)")
    ap.add_argument("base_id")
    ap.add_argument("--dsn", default=DSN, help="DSN базы движка этой базы 1С")
    ap.add_argument("--bases", default=PACKET_BASES, help="файл баз приёмника (PACKET_BASES)")
    ap.add_argument("--dry-run", action="store_true",
                    help="печать итогового списка и причин без единой записи")
    args = ap.parse_args(argv)
    try:
        return run(args.base_id, args.dsn, args.bases, dry_run=args.dry_run)
    except RuntimeError as e:
        _log(f"FATAL: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
