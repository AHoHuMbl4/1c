#!/usr/bin/env python3
"""Универсальный генератор синтетического $metadata из витрины SereneDB.

Вход: DSN (postgres-протокол SereneDB) + список сущностей OData (файл или JSON
конфига пакета) ИЛИ все таблицы витрины с OData-префиксами. Колонки — из
duckdb_columns() текущей базы (information_schema.columns в SereneDB пуст);
опционально DESCRIBE для сверки. Имена конкретной базы в коде не перечисляются.

Форма XML — как manifest-gen.ps1 / живой OData: EntityType + EntitySet,
ключи и Edm-типы по платформенным префиксам и именам колонок витрины.

Использование:
  python3 gen_metadata_vitrine.py --dsn 'host=127.0.0.1 port=7890 ...' \\
      --entities-file contour.txt --out metadata-okna.xml

  python3 gen_metadata_vitrine.py --dsn ... --packet-bases /etc/1c-packet-bases.json \\
      --base-id okna-1 --out metadata.xml
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# OData-префиксы платформы 1С (не имена конфигурации).
KIND_PREFIXES = (
    "Catalog_",
    "Document_",
    "DocumentJournal_",
    "Constant_",
    "InformationRegister_",
    "AccumulationRegister_",
    "AccountingRegister_",
    "CalculationRegister_",
    "ChartOfAccounts_",
    "ChartOfCharacteristicTypes_",
    "ChartOfCalculationTypes_",
    "ExchangePlan_",
    "BusinessProcess_",
    "Task_",
)

REGISTER_KINDS = ("AccumulationRegister_", "AccountingRegister_", "CalculationRegister_")
MOVEMENT_SUFFIXES = ("_RecordType", "_RowType")

PLATFORM_COL_MAP = {
    "ref_key": "Ref_Key",
    "dataversion": "DataVersion",
    "deletionmark": "DeletionMark",
    "parent_key": "Parent_Key",
    "isfolder": "IsFolder",
    "code": "Code",
    "description": "Description",
    "number": "Number",
    "date": "Date",
    "posted": "Posted",
    "predefined": "Predefined",
    "predefineddataname": "PredefinedDataName",
    "recorder": "Recorder",
    "recorder_key": "Recorder_Key",
    "recorder_type": "Recorder_Type",
    "period": "Period",
    "linenumber": "LineNumber",
    "active": "Active",
    "surrogatekey": "SurrogateKey",
    "recordtype": "RecordType",
    "ref": "Ref",
    "type": "Type",
    "accountdr_key": "AccountDr_Key",
    "accountcr_key": "AccountCr_Key",
    "account_key": "Account_Key",
}

BOOL_COLS = frozenset({
    "deletionmark", "posted", "active", "predefined", "isfolder",
    "executed", "completed", "started", "offbalance",
})

SERVICE_TABLE_PREFIXES = (
    "search_", "alias_", "ask_", "packet_", "resolver_", "wiki_", "pkt_",
    "emb_", "res_emb_", "tmp", "corpus_", "coverage_",
)


def _lit(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def safe_col(name: str) -> str:
    """Имя таблицы/колонки витрины — как packet_apply.safe_col / poc_load_entity."""
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def _load_pg_env(env: dict) -> None:
    if env.get("PGPASSWORD"):
        return
    for p in ("/etc/1c-mcp-reports.env", "/etc/1c-serene-ask-postgres.env"):
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line.startswith("PGPASSWORD="):
                env["PGPASSWORD"] = line.split("=", 1)[1].strip()
            elif line.startswith("SERENEDB_DSN=") and not env.get("_DSN_FROM_FILE"):
                env["_DSN_FROM_FILE"] = line.split("=", 1)[1].strip()


def _psql_cmd(dsn: str, env: dict) -> List[str]:
    """psql argv: conninfo без PGHOST/PGPORT из окружения (иначе порт 5432)."""
    for k in ("PGHOST", "PGPORT", "PGUSER", "PGDATABASE", "PGPASSFILE"):
        env.pop(k, None)
    if "connect_timeout" not in dsn:
        dsn = dsn.rstrip() + " connect_timeout=15"
    return ["psql", dsn, "-v", "ON_ERROR_STOP=1"]


def psql_rows(dsn: str, sql: str, field_sep: str = "\t") -> List[str]:
    env = os.environ.copy()
    _load_pg_env(env)
    cmd = _psql_cmd(dsn, env) + ["-tA", "-F", field_sep, "-c", sql]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("psql: " + (r.stderr or r.stdout or "failed").strip())
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def load_entities_from_file(path: str) -> List[str]:
    names: List[str] = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def load_entities_from_packet_bases(path: str, base_id: str) -> List[str]:
    raw = json.load(open(path, encoding="utf-8"))
    bases = raw.get("bases", raw)
    if isinstance(bases, dict):
        entry = bases.get(base_id)
    else:
        entry = next((b for b in bases if b.get("id") == base_id or b.get("base_id") == base_id), None)
    if not entry:
        raise SystemExit("база %s не найдена в %s" % (base_id, path))
    ents = entry.get("config", entry).get("entities", entry.get("entities"))
    if not ents:
        raise SystemExit("в конфиге базы %s нет entities" % base_id)
    return list(ents)


def is_service_table(name: str) -> bool:
    low = name.lower()
    return any(low.startswith(p) for p in SERVICE_TABLE_PREFIXES)


def is_odata_entity_name(name: str) -> bool:
    return any(name.startswith(p) for p in KIND_PREFIXES)


def is_register_wrapper(name: str) -> bool:
    if any(name.endswith(s) for s in MOVEMENT_SUFFIXES):
        return False
    return any(name.startswith(p) for p in REGISTER_KINDS)


def is_register_record_shadow(name: str) -> bool:
    return any(name.startswith(p) for p in REGISTER_KINDS) and any(
        name.endswith(s) for s in MOVEMENT_SUFFIXES
    )


def is_information_register(name: str) -> bool:
    return name.startswith("InformationRegister_")


def vitrine_table_for_entity(entity: str, tables: set[str]) -> Optional[str]:
    low = safe_col(entity).lower()
    if low in tables:
        return low
    if low.endswith("_recordtype"):
        parent = low[: -len("_recordtype")]
        if parent in tables:
            return parent
    if low.endswith("_rowtype"):
        parent = low[: -len("_rowtype")]
        if parent in tables:
            return parent
    return None


def odata_prop_name(col: str) -> str:
    low = col.lower()
    if low in PLATFORM_COL_MAP:
        return PLATFORM_COL_MAP[low]
    if col.endswith("_Key") or col.endswith("_Type"):
        return col
    return col


def map_edm_type(col: str, storage_type: str) -> str:
    low = col.lower()
    st = (storage_type or "").upper()
    if st == "BOOLEAN" or low in BOOL_COLS:
        return "Edm.Boolean"
    if st in ("UUID", "GUID"):
        return "Edm.Guid"
    if st in ("TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "DATE", "TIMESTAMPTZ"):
        return "Edm.DateTime"
    if st in ("DOUBLE", "FLOAT", "REAL"):
        return "Edm.Double"
    if st.startswith("DECIMAL"):
        return "Edm.Decimal"
    if st in ("BIGINT", "HUGEINT", "UBIGINT"):
        return "Edm.Int64"
    if st in ("INTEGER", "SMALLINT", "TINYINT", "UTINYINT", "USMALLINT"):
        return "Edm.Int16"
    if st in ("BLOB", "BYTEA", "BINARY"):
        return "Edm.Binary"
    # VARCHAR и прочее — по имени колонки
    if low.endswith("_key") or low in ("ref_key", "recorder_key"):
        return "Edm.Guid"
    if low.endswith("_type") or low in ("recorder", "ref", "type", "businessprocess", "routepoint"):
        return "Edm.String"
    if low in ("linenumber", "surrogatekey", "sentno", "receivedno"):
        return "Edm.Int64"
    if low in ("period", "date") or low.endswith("_date") or "дата" in low:
        return "Edm.DateTime"
    if low in ("dataversion", "number", "code", "description"):
        return "Edm.String"
    if low == "recordtype":
        return "Edm.String"
    # числовые реквизиты в витрине часто VARCHAR
    if low in ("сумма", "amount", "курс", "rate", "количество", "quantity"):
        return "Edm.Double"
    return "Edm.String"


def infer_key(entity: str, props: List[Tuple[str, str]]) -> List[str]:
    names = {odata_prop_name(c).lower(): odata_prop_name(c) for c, _ in props}
    cols = {c.lower(): c for c, _ in props}

    if entity.startswith("DocumentJournal_"):
        if "ref" in names and "ref_type" in names:
            return [names["ref"], names["ref_type"]]
        return ["Ref", "Ref_Type"]

    if is_register_record_shadow(entity):
        key: List[str] = []
        if "recorder" in names:
            key.append(names["recorder"])
        elif "recorder_key" in names:
            key.append(names["recorder_key"])
        if "linenumber" in names:
            key.append(names["linenumber"])
        if "recorder_type" in names and "recorder" in names:
            key.append(names["recorder_type"])
        if key:
            return key

    if is_information_register(entity) and not is_register_record_shadow(entity):
        key = []
        if "period" in names:
            key.append(names["period"])
        for n in sorted(names):
            if n.endswith("_key") and names[n] not in key:
                key.append(names[n])
        if key:
            return key
        if "surrogatekey" in names:
            return [names["surrogatekey"]]

    if "ref_key" in names and "linenumber" in names:
        return [names["ref_key"], names["linenumber"]]
    if "ref_key" in names:
        return [names["ref_key"]]
    if "recorder" in names and "recorder_type" in names:
        return [names["recorder"], names["recorder_type"]]
    if "recorder_key" in names:
        return [names["recorder_key"]]
    if "surrogatekey" in names:
        return [names["surrogatekey"]]
    if is_register_record_shadow(entity):
        if composite:
            return ["Recorder", "Recorder_Type", "LineNumber"]
        return ["Recorder_Key", "LineNumber"]
    if "ref_key" in cols:
        return [odata_prop_name(cols["ref_key"])]
    return ["Ref_Key"]


def has_composite_refs(props: List[Tuple[str, str]]) -> bool:
    return any(c.lower().endswith("_type") for c, _ in props)


def synthetic_register_wrapper(entity: str, composite: bool = True) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    base = entity
    row = base + "_RowType"
    coll = "Collection(StandardODATA." + row + ")"
    if composite:
        key = ["Recorder", "Recorder_Type"]
        props: List[Tuple[str, str, str]] = [
            ("Recorder", "Edm.String", "false"),
            ("RecordSet", coll, "false"),
            ("Recorder_Type", "Edm.String", "false"),
        ]
    else:
        key = ["Recorder_Key"]
        props = [
            ("Recorder_Key", "Edm.Guid", "false"),
            ("RecordSet", coll, "false"),
        ]
    return key, props


def synthetic_recordtype_skeleton(
    entity: str, props: List[Tuple[str, str]], composite: bool,
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Дополняет колонки витрины платформенными полями, если их нет."""
    existing = {odata_prop_name(c).lower() for c, _ in props}
    out_props: List[Tuple[str, str, str]] = []
    key_names = infer_key(entity, props)
    key_low = {k.lower() for k in key_names}

    def add(name: str, edm: str, nul: str) -> None:
        if name.lower() not in existing:
            out_props.append((name, edm, nul))
            existing.add(name.lower())

    if composite:
        add("Recorder", "Edm.String", "false" if "recorder" in key_low else "true")
        add("Recorder_Type", "Edm.String", "false" if "recorder_type" in key_low else "true")
    else:
        add("Recorder_Key", "Edm.Guid", "false" if "recorder_key" in key_low else "true")
    add("Period", "Edm.DateTime", "true")
    add("LineNumber", "Edm.Int64", "false" if "linenumber" in key_low else "true")
    add("Active", "Edm.Boolean", "true")
    if entity.startswith("AccumulationRegister_"):
        add("RecordType", "Edm.String", "true")

    for col, st in props:
        pn = odata_prop_name(col)
        edm = map_edm_type(col, st)
        nul = "false" if pn.lower() in key_low else "true"
        out_props.append((pn, edm, nul))

    return key_names, out_props


def build_entity_props(
    entity: str, columns: List[Tuple[str, str]],
) -> Tuple[List[str], List[Tuple[str, str, str]], bool]:
    composite = any(c.lower() == "recorder" for c, _ in columns) or any(
        c.lower().endswith("_type") for c, _ in columns
    )

    if is_register_wrapper(entity):
        key, props = synthetic_register_wrapper(entity, composite=True)
        return key, props, True

    if is_register_record_shadow(entity):
        key, props = synthetic_recordtype_skeleton(entity, columns, composite)
        return key, props, True

    props_out: List[Tuple[str, str, str]] = []
    for col, st in columns:
        pn = odata_prop_name(col)
        edm = map_edm_type(col, st)
        props_out.append((pn, edm, "true"))

    if not props_out and not is_register_wrapper(entity):
        props_out = [
            ("Ref_Key", "Edm.Guid", "false"),
            ("DataVersion", "Edm.String", "true"),
            ("DeletionMark", "Edm.Boolean", "true"),
        ]

    key = infer_key(entity, columns)
    key_low = {k.lower() for k in key}
    props_final: List[Tuple[str, str, str]] = []
    seen = set()
    for pn, edm, nul in props_out:
        nul = "false" if pn.lower() in key_low else nul
        if pn.lower() in seen:
            continue
        seen.add(pn.lower())
        props_final.append((pn, edm, nul))

    open_type = has_composite_refs(columns) or entity.startswith("Task_")
    return key, props_final, open_type


def emit_entity_type(
    name: str, key: List[str], props: List[Tuple[str, str, str]], open_type: bool,
) -> str:
    lines = []
    if open_type:
        lines.append(f'\t\t<EntityType Name="{name}" OpenType="true">')
    else:
        lines.append(f'\t\t<EntityType Name="{name}">')
    if key:
        lines.append("\t\t\t<Key>")
        for k in key:
            lines.append(f'\t\t\t\t<PropertyRef Name="{k}"/>')
        lines.append("\t\t\t</Key>")
    for pn, edm, nul in props:
        lines.append(
            f'\t\t\t<Property Name="{pn}" Type="{edm}" Nullable="{nul}"/>'
        )
    lines.append("\t\t</EntityType>")
    return "\n".join(lines)


def build_xml(entities: Dict[str, Tuple[List[str], List[Tuple[str, str, str]], bool]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx" Version="1.0">',
        '\t<edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" '
        'm:DataServiceVersion="3.0" m:MaxDataServiceVersion="3.0">',
        '\t\t<Schema xmlns="http://schemas.microsoft.com/ado/2009/11/edm" Namespace="StandardODATA">',
    ]
    names = sorted(entities.keys())
    for name in names:
        key, props, open_type = entities[name]
        parts.append(emit_entity_type(name, key, props, open_type))
    parts.append('\t\t<EntityContainer Name="EnterpriseV8" m:IsDefaultEntityContainer="true">')
    for name in names:
        parts.append(
            f'\t\t\t<EntitySet Name="{name}" EntityType="StandardODATA.{name}"/>'
        )
    parts.append("\t\t</EntityContainer>")
    parts.append("\t\t</Schema>")
    parts.append("\t</edmx:DataServices>")
    parts.append("</edmx:Edmx>")
    return "\n".join(parts) + "\n"


def load_vitrine_schema(dsn: str) -> Tuple[set[str], Dict[str, List[Tuple[str, str]]]]:
    sql = (
        "SELECT table_name, column_name, data_type "
        "FROM duckdb_columns() "
        "WHERE database_name = current_database() AND schema_name = 'public' "
        "ORDER BY table_name, column_index"
    )
    rows = psql_rows(dsn, sql)
    tables: set[str] = set()
    schema: Dict[str, List[Tuple[str, str]]] = {}
    for line in rows:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        t, c, dt = parts[0], parts[1], parts[2]
        if is_service_table(t):
            continue
        tables.add(t)
        schema.setdefault(t, []).append((c, dt))
    return tables, schema


def vitrine_tables_from_entities(
    entities: Sequence[str], tables: set[str],
) -> Dict[str, str]:
    """entity → vitrine table used for columns."""
    mapping: Dict[str, str] = {}
    for ent in entities:
        vt = vitrine_table_for_entity(ent, tables)
        if vt:
            mapping[ent] = vt
    return mapping


def generate(
    dsn: str,
    entities: Sequence[str],
    skip_missing: bool = False,
) -> Tuple[str, dict]:
    tables, schema = load_vitrine_schema(dsn)
    built: Dict[str, Tuple[List[str], List[Tuple[str, str, str]], bool]] = {}
    missing: List[str] = []
    col_total = 0

    for ent in entities:
        if not is_odata_entity_name(ent):
            continue
        vt = vitrine_table_for_entity(ent, tables)
        if is_register_wrapper(ent):
            key, props, open_type = build_entity_props(ent, [])
            built[ent] = (key, props, open_type)
            col_total += len(props)
            continue
        if not vt:
            if skip_missing:
                missing.append(ent)
                continue
            key, props, open_type = build_entity_props(ent, [])
            built[ent] = (key, props, open_type)
            col_total += len(props)
            continue
        cols = schema.get(vt, [])
        key, props, open_type = build_entity_props(ent, cols)
        built[ent] = (key, props, open_type)
        col_total += len(props)

    xml = build_xml(built)
    stats = {
        "entities": len(built),
        "entity_sets": len(built),
        "columns": col_total,
        "vitrine_tables": len(tables),
        "missing": missing,
    }
    return xml, stats


def parse_like_corpus_build(xml: str) -> Tuple[int, int, int]:
    """Зеркало corpus_build.sql §1: EntityType, Property, сущности с непустым ключом."""
    ents = re.findall(r"<EntityType\s.*?</EntityType>", xml, re.S)
    props = re.findall(r'<Property\s+Name="([^"]+)"\s+Type="([^"]+)"', xml)
    keyed = 0
    for body in ents:
        km = re.search(r"<Key>(.*?)</Key>", body, re.S)
        if not km:
            continue
        refs = re.findall(r'<PropertyRef\s+Name="([^"]+)"', km.group(1))
        if refs:
            keyed += 1
    return len(ents), len(props), keyed


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="синтетический $metadata из витрины SereneDB")
    ap.add_argument("--dsn", default=os.environ.get("SERENEDB_DSN", ""), help="DSN SereneDB")
    ap.add_argument("--entities-file", help="файл: одна сущность OData на строку")
    ap.add_argument("--packet-bases", help="JSON баз пакета")
    ap.add_argument("--base-id", help="id базы в packet-bases")
    ap.add_argument("--out", required=True, help="путь выходного XML")
    ap.add_argument("--skip-missing", action="store_true",
                    help="пропустить сущности без таблицы витрины")
    args = ap.parse_args(argv)

    if not args.dsn:
        ap.error("нужен --dsn или SERENEDB_DSN")

    if args.entities_file:
        entities = load_entities_from_file(args.entities_file)
    elif args.packet_bases and args.base_id:
        entities = load_entities_from_packet_bases(args.packet_bases, args.base_id)
    else:
        tables, _ = load_vitrine_schema(args.dsn)
        entities = sorted(
            t for t in tables if is_odata_entity_name(
                # восстановить PascalCase префикса из lower table name — только для
                # таблиц, чьё имя совпадает с lower(OData); остальные не трогаем
                next((p + t.split("_", 1)[1] for p in KIND_PREFIXES
                      if t.lower().startswith(p.lower().replace("_", "_"))), t)
            )
        )

    xml, stats = generate(args.dsn, entities, skip_missing=args.skip_missing)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)

    ent_n, prop_n, key_n = parse_like_corpus_build(xml)
    sys.stderr.write(
        "ENTITY-COUNT=%d SET-COUNT=%d PROPERTY-COUNT=%d KEYED=%d "
        "VITRINE-TABLES=%d MISSING=%d → %s\n"
        % (
            stats["entities"], stats["entity_sets"], stats["columns"],
            key_n, stats["vitrine_tables"], len(stats["missing"]), args.out,
        )
    )
    if stats["missing"]:
        sys.stderr.write("MISSING: " + ",".join(stats["missing"][:20]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
