#!/usr/bin/env python3
"""Apply-компонент пакетного транспорта: перевод пакетов verified → applied.

Один заход обходит все пакеты verified (всех баз либо одной — флаг/env) в порядке
seq: манифест разбирается, чанки дешифруются (age) и распаковываются (zstd) во
временный каталог, затем изменения уходят в витрину SereneDB теми же SQL-формами,
что у poc_load_entity.py (merge-дельта, полная загрузка с QUALIFY-дедупом, gone).

Атомарность пакета (контракт §8): DDL в SereneDB вне транзакций, поэтому каждая
операция повторяема без вреда, а контрактные таблицы и отметка applied пишутся
последними одной DML-транзакцией. Обрыв до неё оставляет пакет в verified, и
следующий заход повторяет его целиком.

Конфиг — env: PACKET_ROOT, PACKET_BASES (JSON баз, формат packet_server),
SERENEDB_DSN, PACKET_ZSTD_BIN, PACKET_META_DIR, PACKET_APPLY_*. Только stdlib.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import packet_crypto as C

PACKET_ROOT = os.environ.get("PACKET_ROOT", "/var/lib/1c-packet")
PACKET_BASES = os.environ.get("PACKET_BASES", "/etc/1c-packet-bases.json")
DSN = os.environ.get("SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=postgres")
ZSTD_BIN = os.environ.get("PACKET_ZSTD_BIN", "/usr/bin/zstd")

# Предел длины строки CSV — бюджет памяти читателя, как ETL_CSV_MAX_LINE у
# poc_load_entity (то же значение по умолчанию, то же основание).
PACKET_APPLY_CSV_MAX_LINE = int(os.environ.get("PACKET_APPLY_CSV_MAX_LINE", str(200 * 1024 * 1024)))
# Ключи на удаление идут VALUES-наборами по столько штук за запрос.
PACKET_APPLY_GONE_BATCH = int(os.environ.get("PACKET_APPLY_GONE_BATCH", "1000"))
# Читающая роль витрины для GRANT. Имя — идентификатор, приходит из окружения,
# поэтому пропускается только форма идентификатора, иначе берётся умолчание
# (то же решение, что serene_sync._ro_role).
_ro_env = os.environ.get("PACKET_APPLY_RO_ROLE", "serene_ro")
RO_ROLE = _ro_env if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", _ro_env) else "serene_ro"

# Чанки со служебными именами хранятся без вставки «.csv» (контракт §2).
_SERVICE_CHUNKS = ("metadata", "gone", "index")
# Операции сущности, при которых данные заливаются чанками (остальные — gone_only).
_DATA_OPS = ("full", "full_entity", "delta")

BASES: dict = {}


def _log(msg: str) -> None:
    sys.stderr.write("apply %s\n" % msg)


def _chunk_filename(name: str) -> str:
    return name + (".zst.age" if name in _SERVICE_CHUNKS else ".csv.zst.age")


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json_atomic(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _base_dir(base_id: str) -> str:
    return os.path.join(PACKET_ROOT, "inbox", base_id)


def _pkg_dir(base_id: str, pkg_id: str) -> str:
    return os.path.join(_base_dir(base_id), pkg_id)


def _base_state(base_id: str) -> dict:
    st = _read_json(os.path.join(_base_dir(base_id), "state.json"), None)
    if not isinstance(st, dict):
        st = {"last_applied_seq": 0, "packages": {}}
    st.setdefault("last_applied_seq", 0)
    st.setdefault("packages", {})
    return st


def _set_pkg_state(base_id: str, pkg_id: str, state: str, error, seq=None) -> None:
    # Дубль записи packet_server._set_pkg_state: apply — самостоятельный процесс,
    # форма state.json общая по контракту хранения (шапка packet_server.py).
    pkg_dir = _pkg_dir(base_id, pkg_id)
    st = _read_json(os.path.join(pkg_dir, "state.json"), None)
    if not isinstance(st, dict):
        st = {}
    st["state"] = state
    st["error"] = error
    if seq is not None:
        st["seq"] = seq
    st["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json_atomic(os.path.join(pkg_dir, "state.json"), st)
    bs = _base_state(base_id)
    bs["packages"][pkg_id] = {"state": state, "error": error}
    _write_json_atomic(os.path.join(_base_dir(base_id), "state.json"), bs)


def _mark_applied(base_id: str, pkg_id: str, seq: int) -> None:
    _set_pkg_state(base_id, pkg_id, "applied", None, seq=seq)
    bs = _base_state(base_id)
    bs["last_applied_seq"] = max(int(bs.get("last_applied_seq", 0)), seq)
    _write_json_atomic(os.path.join(_base_dir(base_id), "state.json"), bs)


def safe_col(name) -> str:
    # Та же функция, что poc_load_entity.safe_col: имя колонки для любого алфавита.
    out = []
    for ch in str(name):
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    s = "".join(out).strip("_")
    if not s or s[0].isdigit():
        s = "c_" + s
    return s


def _lit(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _psql(sql: str) -> None:
    # SQL идёт через stdin, а не аргументом -c: у argv жёсткий предел, и длинный
    # список ключей его перекрывает (разбор у poc_load_entity._psql_rows).
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])


def _psql_scalar(sql: str) -> str:
    p = subprocess.run(["psql", DSN, "-tA", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return p.stdout.strip()


class Quarantine(RuntimeError):
    # Сбой, после которого пакет уходит в quarantined с кодом причины.
    pass


# --- разбор пакета ------------------------------------------------------------


def _decrypt_chunks(base_id: str, pkg_id: str, manifest: dict, tmp: str) -> dict:
    """Все чанки пакета: age → zstd → открытый файл во временном каталоге."""
    identity = (BASES.get(base_id) or {}).get("identity", "")
    out = {}
    for e in manifest["chunks"]:
        name = e["name"]
        enc = os.path.join(_pkg_dir(base_id, pkg_id), _chunk_filename(name))
        dec = os.path.join(tmp, name + ".zst")
        plain = os.path.join(tmp, name + (".csv" if name not in _SERVICE_CHUNKS else ""))
        C.decrypt_file(enc, dec, identity)
        with open(plain, "wb") as fh:
            p = subprocess.run([ZSTD_BIN, "-d", "-q", "-c", dec],
                               stdout=fh, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise RuntimeError("zstd: %s" % p.stderr.decode("utf-8", "replace").strip()[:200])
        os.chmod(plain, 0o644)
        out[name] = plain
    return out


def _csv_source(paths: list[str]) -> str:
    """SELECT-источник read_csv с опциями контракта poc_load_entity (header,
    all_varchar, quote/escape, предел строки). Несколько чанков — UNION ALL."""
    opts = ("header=true, all_varchar=true, quote='\"', escape='\"', "
            "maximum_line_size=%d" % PACKET_APPLY_CSV_MAX_LINE)
    reads = ["SELECT * FROM read_csv(%s, %s)" % (_lit(p), opts) for p in paths]
    if len(reads) == 1:
        return reads[0]
    return "(" + " UNION ALL ".join(reads) + ")"


def _full_sql(table: str, src: str, key_cols: list[str]) -> str:
    # Формы poc_load_entity.load_entity: дедуп QUALIFY по объявленному ключу,
    # без ключа — DISTINCT; DROP + CREATE, затем GRANT читающей роли.
    # QUALIFY крепится к SELECT, поэтому UNION-источник оборачивается подзапросом.
    wrapped = src if src.startswith("(") else None
    if key_cols:
        part = ", ".join('"%s"' % k for k in key_cols)
        qual = "QUALIFY row_number() OVER (PARTITION BY %s ORDER BY %s) = 1" % (part, part)
        select = ("SELECT * FROM %s AS q %s" % (wrapped, qual)) if wrapped \
            else ("%s %s" % (src, qual))
    else:
        select = ("SELECT DISTINCT * FROM %s AS q" % wrapped) if wrapped \
            else src.replace("SELECT *", "SELECT DISTINCT *", 1)
    return ('DROP TABLE IF EXISTS "%s";\n'
            'CREATE TABLE "%s" AS %s;\n'
            'GRANT SELECT ON "%s" TO %s;\n' % (table, table, select, table, RO_ROLE))


def _check_mix_versions(table: str) -> None:
    # Инвариант К3 (контракт §9): одна версия на Ref_Key, запрос как у
    # poc_load_entity.load_entity_delta. Нарушение — карантин, дельту не льём.
    n = _psql_scalar('SELECT count(*) FROM (SELECT "Ref_Key" FROM "%s" '
                     'GROUP BY 1 HAVING count(DISTINCT "DataVersion")>1)' % table)
    if n and int(n) > 0:
        raise Quarantine("mix_versions")


def _delta_sql(table: str, src: str) -> str:
    # Форма poc_load_entity.load_entity_delta: TEMP-таблица → DELETE по Ref_Key
    # → INSERT. Повтор безопасен: DELETE снимает прошлую порцию тех же ключей.
    return ('CREATE OR REPLACE TEMP TABLE "d_%s" AS %s;\n'
            'DELETE FROM "%s" WHERE "Ref_Key" IN (SELECT "Ref_Key" FROM "d_%s");\n'
            'INSERT INTO "%s" SELECT * FROM "d_%s";\n'
            % (table, src, table, table, table, table))


def _apply_gone(path: str, changed_tables: set) -> int:
    """gone.csv (колонки entity,ref_key): DELETE по ключам пачками."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    header = [h.strip() for h in rows[0]]
    try:
        ie, ir = header.index("entity"), header.index("ref_key")
        data = rows[1:]
    except ValueError:
        ie, ir, data = 0, 1, rows[1:]
    keys: dict[str, list[str]] = {}
    for r in data:
        if len(r) > max(ie, ir):
            keys.setdefault(r[ie], []).append(r[ir])
    total = 0
    for entity, ks in keys.items():
        table = safe_col(entity).lower()
        changed_tables.add(table)
        for i in range(0, len(ks), PACKET_APPLY_GONE_BATCH):
            vals = ",".join("(%s)" % _lit(k) for k in ks[i:i + PACKET_APPLY_GONE_BATCH])
            _psql('DELETE FROM "%s" WHERE "Ref_Key" IN '
                  '(SELECT k FROM (VALUES %s) AS g(k));' % (table, vals))
        total += len(ks)
    return total


# Каталог снимков $metadata: <PACKET_META_DIR>/<base_id>/$metadata. Снимок едет
# ФАЙЛОМ, а не таблицей: read_text в corpus_build.sql читает и локальные файлы,
# поэтому боевой скрипт сборки работает без правок — build.sh получает
# ETL_ODATA_BASE=<каталог>/<base_id>, и движок читает <каталог>/<base_id>/$metadata
# (решение владельца 06.08: боевые скрипты сборки не трогаем).
PACKET_META_DIR = os.environ.get("PACKET_META_DIR", "/var/lib/serenedb/packet-meta")


def _apply_metadata(base_id: str, manifest: dict, path: str) -> None:
    """Снимок $metadata из чанка — в файл <PACKET_META_DIR>/<base_id>/$metadata.

    Атомарно: temp+os.replace в том же каталоге — движок в любой момент видит
    либо старый снимок целиком, либо новый. Файл читает процесс движка (в бою
    apply идёт под root), поэтому владелец и режим выставляются явно."""
    base_dir = os.path.join(PACKET_META_DIR, base_id)
    os.makedirs(base_dir, exist_ok=True)
    os.chmod(base_dir, 0o755)
    fd, tmp = tempfile.mkstemp(dir=base_dir, prefix=".metadata-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(path, "rb") as src:
            shutil.copyfileobj(src, out)
        os.chmod(tmp, 0o644)
        if os.geteuid() == 0:
            try:
                shutil.chown(tmp, user="serenedb", group="serenedb")
            except LookupError as e:
                raise RuntimeError(f"chown serenedb:serenedb: {e}")
        os.replace(tmp, os.path.join(base_dir, "$metadata"))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- контрактные таблицы (форма serene_sync) -----------------------------------


def _ensure_contract_tables() -> None:
    # DDL вне транзакции (движок так и работает), IF NOT EXISTS — повторяемо.
    _psql("CREATE TABLE IF NOT EXISTS search_changed_sources (src_table VARCHAR);\n"
          "GRANT SELECT ON search_changed_sources TO %s;\n"
          "CREATE TABLE IF NOT EXISTS base_profile "
          "(entity TEXT, rows BIGINT, problem TEXT, key_props TEXT);\n"
          "CREATE TABLE IF NOT EXISTS search_quality (k TEXT, v BIGINT, note TEXT);\n"
          % RO_ROLE)


def _contract_tx(changed_tables: set, profile: list[dict]) -> None:
    """Последний шаг пакета: контрактные таблицы одной DML-транзакцией.

    Формы повторяют serene_sync: search_changed_sources переписывается целиком
    (пустой список законен), в base_profile обновляются строки затронутых
    сущностей, в search_quality ставится отметка mart_changed_ts = now.
    """
    sql = ["BEGIN;", "DELETE FROM search_changed_sources;"]
    if changed_tables:
        vals = ",".join("(%s)" % _lit(t) for t in sorted(changed_tables))
        sql.append("INSERT INTO search_changed_sources SELECT * FROM (VALUES %s) AS s(t);" % vals)
    if profile:
        # Форма serene_sync: число строк обновляется, ключ и примечание сущности
        # в профиле сохраняются; вставляются только новые для профиля сущности.
        pairs = ",".join("(%s,%d)" % (_lit(p["entity"]), p["rows"]) for p in profile)
        sql.append("UPDATE base_profile SET rows = v.n FROM (VALUES %s) AS v(e, n) "
                   "WHERE base_profile.entity = v.e;" % pairs)
        vals = ",".join("(%s,%d,%s,%s)" % (_lit(p["entity"]), p["rows"], _lit(""),
                                           _lit(",".join(p.get("key") or [])))
                        for p in profile)
        sql.append("INSERT INTO base_profile SELECT * FROM (VALUES %s) AS v(e, n, p, k) "
                   "WHERE NOT EXISTS (SELECT 1 FROM base_profile WHERE base_profile.entity = v.e);"
                   % vals)
    sql.append("DELETE FROM search_quality WHERE k='mart_changed_ts';")
    sql.append("INSERT INTO search_quality VALUES ('mart_changed_ts', epoch(now())::BIGINT, "
               "'витрина менялась (пакетный apply)');")
    sql.append("COMMIT;")
    _psql("\n".join(sql) + "\n")


# --- план и применение ----------------------------------------------------------


def _plan(base_id: str, pkg_id: str, m: dict) -> list[str]:
    lines = ["пакет %s/%s seq=%d kind=%s" % (base_id, pkg_id, m.get("seq"), m.get("kind"))]
    for ent in m.get("entities") or []:
        lines.append("  сущность %s op=%s rows=%s чанки=%s ключ=%s"
                     % (ent.get("name"), ent.get("op"), ent.get("rows"),
                        ",".join(ent.get("chunks") or []), ",".join(ent.get("key") or [])))
    if (m.get("gone") or {}).get("chunks"):
        lines.append("  gone: чанки=%s" % ",".join(m["gone"].get("chunks") or []))
    if (m.get("metadata") or {}).get("included"):
        lines.append("  metadata: fingerprint=%s" % (m["metadata"].get("fingerprint") or ""))
    lines.append("  контрактная транзакция: search_changed_sources + base_profile + "
                 "search_quality.mart_changed_ts")
    return lines


def apply_package(base_id: str, pkg_id: str, m: dict, dry_run: bool) -> str:
    """Один пакет. Итог: applied / quarantined / failed (остался verified) / planned."""
    seq = m["seq"]
    if dry_run:
        for line in _plan(base_id, pkg_id, m):
            print(line)
        return "planned"
    tmp = tempfile.mkdtemp(prefix="packet-apply-")
    os.chmod(tmp, 0o755)  # каталог читает процесс движка (read_csv)
    try:
        try:
            files = _decrypt_chunks(base_id, pkg_id, m, tmp)
            if (m.get("metadata") or {}).get("included") and "metadata" in files:
                _apply_metadata(base_id, m, files["metadata"])
                _log("base=%s pkg=%s metadata записан" % (base_id, pkg_id))
            changed_tables: set = set()
            profile: list[dict] = []
            for ent in m.get("entities") or []:
                op = ent.get("op")
                if op not in _DATA_OPS:
                    continue
                table = safe_col(ent.get("name", "")).lower()
                src = _csv_source([files[c] for c in ent.get("chunks") or [] if c in files])
                if op == "delta":
                    _check_mix_versions(table)
                    _psql(_delta_sql(table, src))
                else:
                    key_cols = [safe_col(k) for k in ent.get("key") or []]
                    _psql(_full_sql(table, src, key_cols))
                changed_tables.add(table)
                profile.append({"entity": ent.get("name"), "key": ent.get("key") or [],
                                "table": table})
                _log("base=%s pkg=%s entity=%s op=%s" % (base_id, pkg_id, table, op))
            if (m.get("gone") or {}).get("chunks") and "gone" in files:
                n_gone = _apply_gone(files["gone"], changed_tables)
                _log("base=%s pkg=%s gone=%d" % (base_id, pkg_id, n_gone))
            # Число строк профиля — фактическое, после всех операций пакета
            # (gone снимает строки уже после merge, как у serene_sync).
            for p in profile:
                n = _psql_scalar('SELECT count(*) FROM "%s"' % p["table"])
                p["rows"] = int(n) if n.isdigit() else 0
        except Quarantine as q:
            _set_pkg_state(base_id, pkg_id, "quarantined", str(q), seq=seq)
            _log("QUARANTINE base=%s pkg=%s code=%s" % (base_id, pkg_id, q))
            return "quarantined"
        except (RuntimeError, C.PacketCryptoError, OSError, KeyError) as e:
            # Сбой до контрактной транзакции: пакет остаётся verified, повтор
            # следующего захода безопасен (все операции повторяемы).
            _log("ОШИБКА base=%s pkg=%s: %s — пакет остался verified" % (base_id, pkg_id, str(e)[:300]))
            return "failed"
        try:
            _ensure_contract_tables()
            _contract_tx(changed_tables, profile)
        except RuntimeError as e:
            _set_pkg_state(base_id, pkg_id, "quarantined",
                           "contract_tx_failed: %s" % str(e)[:200], seq=seq)
            _log("QUARANTINE base=%s pkg=%s code=contract_tx_failed" % (base_id, pkg_id))
            return "quarantined"
        _mark_applied(base_id, pkg_id, seq)
        _log("APPLIED base=%s pkg=%s seq=%d" % (base_id, pkg_id, seq))
        return "applied"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _iter_verified(only_base: str | None) -> list[tuple[str, str, dict]]:
    """(base_id, pkg_id, manifest) всех пакетов в состоянии verified, по seq."""
    inbox = os.path.join(PACKET_ROOT, "inbox")
    out = []
    if not os.path.isdir(inbox):
        return out
    for base_id in sorted(os.listdir(inbox)):
        if only_base and base_id != only_base:
            continue
        bdir = _base_dir(base_id)
        if not os.path.isdir(bdir):
            continue
        last_applied = _base_state(base_id)["last_applied_seq"]
        for pkg_id in sorted(os.listdir(bdir)):
            pdir = os.path.join(bdir, pkg_id)
            if not os.path.isdir(pdir):
                continue
            st = _read_json(os.path.join(pdir, "state.json"), {})
            if st.get("state") != "verified":
                continue
            m = _read_json(os.path.join(pdir, "manifest.json"), None)
            if not isinstance(m, dict) or not isinstance(m.get("seq"), int):
                _log("base=%s pkg=%s: манифест не читается, пропуск" % (base_id, pkg_id))
                continue
            if m["seq"] <= last_applied:
                _log("base=%s pkg=%s seq=%d <= last_applied=%d, пропуск"
                     % (base_id, pkg_id, m["seq"], last_applied))
                continue
            out.append((base_id, pkg_id, m))
    out.sort(key=lambda t: (t[0], t[2]["seq"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="apply-компонент пакетного транспорта")
    ap.add_argument("--base", default=os.environ.get("PACKET_APPLY_BASE") or None,
                    help="обработать только эту базу")
    ap.add_argument("--dry-run", action="store_true",
                    default=os.environ.get("PACKET_APPLY_DRY_RUN", "") not in ("", "0"),
                    help="разобрать и напечатать план без обращений к витрине")
    args = ap.parse_args()

    if not os.path.exists(PACKET_BASES):
        sys.stderr.write("FATAL: файл баз %s не найден, задайте PACKET_BASES\n" % PACKET_BASES)
        return 2
    try:
        with open(PACKET_BASES, encoding="utf-8") as f:
            BASES.update(json.load(f))
    except (OSError, ValueError) as e:
        sys.stderr.write("FATAL: файл баз %s не читается: %s\n" % (PACKET_BASES, e))
        return 2

    todo = _iter_verified(args.base)
    if not todo:
        _log("пакетов verified нет — нечего применять")
        return 0
    bad = 0
    skip_bases: set = set()
    for base_id, pkg_id, m in todo:
        if base_id in skip_bases:
            continue
        res = apply_package(base_id, pkg_id, m, args.dry_run)
        if res in ("failed", "quarantined"):
            bad += 1
            # Поздние пакеты этой базы строятся поверх ранних — после сбоя
            # база дальше не идёт, остальные базы продолжаются.
            skip_bases.add(base_id)
    return 3 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
