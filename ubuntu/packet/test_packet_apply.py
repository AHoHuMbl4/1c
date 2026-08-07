#!/usr/bin/env python3
"""Проба packet_apply против живого движка SereneDB (127.0.0.1:7890).

Сценарий: во временном PACKET_ROOT собирается фейковая база pktprobe и три
verified-пакета руками (manifest.json + чанки zstd+age через packet_crypto):
seq=1 kind=full (сущность pkt_probe_catalog, 3 строки + metadata-чанк),
seq=2 kind=delta (одна изменённая строка + gone на одну), seq=3 — дельта при
нарушенном инварианте «одна версия на Ref_Key». Прогоняется packet_apply и
проверяются данные, GRANT, контрактные таблицы, state.json, идемпотентность
и карантин mix_versions.

Гигиена: таблицы пробы — с префиксом pkt_probe_, маркер base_id 'pktprobe';
контрактные таблицы снимкаются до прогона и восстанавливаются после, всё —
в finally. Перед стартом проверяется отсутствие pkt_probe_* (чужое не затираем).

Прогон: python3 ubuntu/packet/test_packet_apply.py
"""

from __future__ import annotations

import csv as csvmod
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEV_AGE = os.path.join(_REPO, "work", "packet", "bin", "age", "age")
_DEV_KEYGEN = os.path.join(_REPO, "work", "packet", "bin", "age", "age-keygen")
if not os.environ.get("PACKET_AGE_BIN") and os.path.exists(_DEV_AGE):
    os.environ["PACKET_AGE_BIN"] = _DEV_AGE
    os.environ["PACKET_AGE_KEYGEN_BIN"] = _DEV_KEYGEN

import packet_crypto as C  # noqa: E402

DSN = "host=127.0.0.1 port=7890 user=postgres dbname=postgres"
BASE_ID = "pktprobe"
TABLE = "pkt_probe_catalog"
TABLE2 = "pkt_probe_narrow"
GHOST = "pkt_probe_ghost"
META_FP = "sha256:probe-meta-1"
META_XML = "<metadata><entity>pkt_probe_catalog</entity></metadata>"
ZSTD = os.environ.get("PACKET_ZSTD_BIN", "/usr/bin/zstd")

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def psql(sql: str):
    p = subprocess.run(["psql", DSN, "-tA", "--csv", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])
    return [tuple(r) for r in csvmod.reader(io.StringIO(p.stdout)) if r]


def psql_exec(sql: str):
    p = subprocess.run(["psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip()[:300])


def scalar(sql: str) -> str:
    rows = psql(sql)
    return rows[0][0] if rows else ""


# --- сборка фейковых пакетов ---------------------------------------------------

_TMP = tempfile.TemporaryDirectory()
ROOT = os.path.join(_TMP.name, "root")
WORK = os.path.join(_TMP.name, "work")
META_DIR = os.path.join(_TMP.name, "packet-meta")
META_FILE = os.path.join(META_DIR, BASE_ID, "$metadata")
os.makedirs(ROOT)
os.makedirs(WORK)
IDENTITY = os.path.join(_TMP.name, "pktprobe.key")
PUB = C.keygen(IDENTITY)
BASES_PATH = os.path.join(_TMP.name, "bases.json")
with open(BASES_PATH, "w", encoding="utf-8") as f:
    json.dump({BASE_ID: {"token": "tok-pktprobe", "identity": IDENTITY, "config": {}}},
              f, ensure_ascii=False)

_n = [0]


def _wf(name: str, data: bytes) -> str:
    _n[0] += 1
    p = os.path.join(WORK, f"{_n[0]:03d}-{name}")
    with open(p, "wb") as f:
        f.write(data)
    return p


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_chunk(name: str, plain: bytes, entity: str, rows: int):
    """CSV/XML → zstd → age; возвращает (запись манифеста, шифртекст)."""
    z = subprocess.run([ZSTD, "-q", "-3", "-c"], input=plain,
                       capture_output=True, check=True).stdout
    enc = _wf(name + ".age", b"")
    C.encrypt_file(_wf(name + ".zst", z), enc, PUB)
    eb = open(enc, "rb").read()
    entry = {"name": name, "entity": entity, "rows": rows,
             "bytes_plain": len(plain), "bytes_enc": len(eb),
             "sha256_plain": sha256(plain), "sha256_enc": sha256(eb)}
    return entry, eb


def csv_bytes(rows: list[tuple], header=("Ref_Key", "DataVersion", "Description")) -> bytes:
    buf = io.StringIO()
    w = csvmod.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def make_chunk_plain(name: str, plain: bytes, entity: str, rows: int):
    """Пилотный plain-режим: CSV/XML → zstd, без age. sha256_enc — отпечаток zst."""
    z = subprocess.run([ZSTD, "-q", "-3", "-c"], input=plain,
                       capture_output=True, check=True).stdout
    entry = {"name": name, "entity": entity, "rows": rows,
             "bytes_plain": len(plain), "bytes_enc": len(z),
             "sha256_plain": sha256(plain), "sha256_enc": sha256(z)}
    return entry, z


def write_package(seq: int, rand: str, kind: str, manifest: dict, chunks: dict,
                  plain: bool = False) -> str:
    """Каталог пакета в inbox: manifest.json + чанки + state.json verified.
    plain=True — пилотный режим без age: чанки хранятся как .zst/.csv.zst."""
    pkg_id = f"{seq:06d}-{rand}"
    pdir = os.path.join(ROOT, "inbox", BASE_ID, pkg_id)
    os.makedirs(pdir)
    manifest["package_id"] = f"{BASE_ID}/{pkg_id}"
    with open(os.path.join(pdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    for name, data in chunks.items():
        base = ".zst" if name in ("metadata", "gone", "index") else ".csv.zst"
        with open(os.path.join(pdir, name + (base if plain else base + ".age")), "wb") as f:
            f.write(data)
    with open(os.path.join(pdir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"state": "verified", "error": None, "seq": seq}, f)
    bs_path = os.path.join(ROOT, "inbox", BASE_ID, "state.json")
    bs = {"last_applied_seq": 0, "packages": {}}
    if os.path.exists(bs_path):
        bs = json.load(open(bs_path, encoding="utf-8"))
    bs["packages"][pkg_id] = {"state": "verified", "error": None}
    with open(bs_path, "w", encoding="utf-8") as f:
        json.dump(bs, f, ensure_ascii=False)
    return pkg_id


def base_manifest(seq: int, rand: str, kind: str) -> dict:
    return {"manifest_version": 1, "base_id": BASE_ID, "seq": seq, "kind": kind,
            "created_utc": "2026-08-06T10:00:00Z", "agent_version": "proba-1",
            "entities": [], "chunks": []}


def run_apply(*extra) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({"PACKET_ROOT": ROOT, "PACKET_BASES": BASES_PATH, "SERENEDB_DSN": DSN,
                "PACKET_META_DIR": META_DIR,
                "PACKET_AGE_BIN": os.environ.get("PACKET_AGE_BIN", ""),
                "PACKET_AGE_KEYGEN_BIN": os.environ.get("PACKET_AGE_KEYGEN_BIN", "")})
    return subprocess.run([sys.executable,
                           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "packet_apply.py")] + list(extra),
                          capture_output=True, text=True, env=env, timeout=300)


def pkg_state(pkg_id: str) -> dict:
    p = os.path.join(ROOT, "inbox", BASE_ID, pkg_id, "state.json")
    return json.load(open(p, encoding="utf-8"))


def base_state() -> dict:
    p = os.path.join(ROOT, "inbox", BASE_ID, "state.json")
    return json.load(open(p, encoding="utf-8"))


# --- контрактные таблицы: снимок и восстановление --------------------------------

_snap = {"changed_exists": False, "changed": [], "quality_ts": [],
         "profile_table_exists": False}


def snapshot_contract():
    try:
        _snap["changed"] = psql("SELECT src_table FROM search_changed_sources")
        _snap["changed_exists"] = True
    except RuntimeError:
        pass
    try:
        _snap["quality_ts"] = psql("SELECT k, v, note FROM search_quality WHERE k='mart_changed_ts'")
    except RuntimeError:
        pass
    try:
        psql("SELECT 1 FROM base_profile LIMIT 0")
        _snap["profile_table_exists"] = True
    except RuntimeError:
        pass


def restore_contract():
    # Восстановление снимка: apply переписывает search_changed_sources целиком
    # и двигает mart_changed_ts — возвращаем как было до пробы.
    try:
        if _snap["changed_exists"]:
            psql_exec("DELETE FROM search_changed_sources;")
            if _snap["changed"]:
                vals = ",".join("('%s')" % r[0].replace("'", "''") for r in _snap["changed"])
                psql_exec("INSERT INTO search_changed_sources SELECT * FROM (VALUES %s) AS s(t);" % vals)
        else:
            psql_exec("DROP TABLE IF EXISTS search_changed_sources;")
    except RuntimeError as e:
        print(f"⚠ восстановление search_changed_sources: {str(e)[:150]}")
    try:
        psql_exec("DELETE FROM search_quality WHERE k='mart_changed_ts';")
        for r in _snap["quality_ts"]:
            psql_exec("INSERT INTO search_quality VALUES ('%s', %s, '%s');"
                      % (r[0], r[1], r[2].replace("'", "''")))
    except RuntimeError as e:
        print(f"⚠ восстановление search_quality: {str(e)[:150]}")
    try:
        psql_exec("DELETE FROM base_profile WHERE entity = '%s';" % TABLE)
        if not _snap["profile_table_exists"]:
            psql_exec("DROP TABLE IF EXISTS base_profile;")
    except RuntimeError as e:
        print(f"⚠ чистка base_profile: {str(e)[:150]}")


def cleanup():
    for t in (TABLE, TABLE2, GHOST):
        try:
            psql_exec('DROP TABLE IF EXISTS "%s";' % t)
        except RuntimeError as e:
            print(f"⚠ drop {t}: {str(e)[:150]}")
    restore_contract()
    _TMP.cleanup()


# --- прогон ---------------------------------------------------------------------


def main() -> int:
    # 0. Подключение и гигиена входа.
    try:
        scalar("SELECT 1")
    except RuntimeError as e:
        print(f"FATAL  движок не отвечает: {str(e)[:200]}")
        return 2
    left = psql("SELECT table_name FROM duckdb_tables() WHERE table_name LIKE 'pkt\\_probe\\_%'")
    if left:
        print("FATAL  найдены таблицы pkt_probe_* (%s) — стоп, чужое не затираю"
              % ",".join(r[0] for r in left))
        return 2
    snapshot_contract()

    try:
        # 1. Пакеты seq=1 (full) и seq=2 (delta+gone).
        full_csv = csv_bytes([("k1", "v1", "alpha"), ("k2", "v1", "beta"), ("k3", "v1", "gamma")])
        e1, c1 = make_chunk("chunk-00001", full_csv, TABLE, 3)
        em, cm = make_chunk("metadata", META_XML.encode("utf-8"), "", 0)
        m1 = base_manifest(1, "aaa00001", "full")
        m1["entities"] = [{"name": TABLE, "op": "full", "rows": 3,
                           "chunks": ["chunk-00001"], "key": ["Ref_Key"]}]
        m1["metadata"] = {"included": True, "fingerprint": META_FP, "chunks": ["metadata"]}
        m1["chunks"] = [e1, em]
        pkg1 = write_package(1, "aaa00001", "full", m1, {"chunk-00001": c1, "metadata": cm})

        delta_csv = csv_bytes([("k2", "v2", "beta2")])
        e2, c2 = make_chunk("chunk-00001", delta_csv, TABLE, 1)
        gone_csv = b"entity,ref_key\r\n" + TABLE.encode() + b",k3\r\n"
        eg, cg = make_chunk("gone", gone_csv, "", 1)
        m2 = base_manifest(2, "bbb00002", "delta")
        m2["entities"] = [{"name": TABLE, "op": "delta", "rows": 1, "chunks": ["chunk-00001"]}]
        m2["gone"] = {"entities": [TABLE], "chunks": ["gone"]}
        m2["chunks"] = [e2, eg]
        pkg2 = write_package(2, "bbb00002", "delta", m2, {"chunk-00001": c2, "gone": cg})

        # 2. Сухой прогон: план печатается, витрина не тронута.
        r = run_apply("--dry-run")
        check("dry-run код 0", r.returncode == 0, r.stderr.strip()[:200])
        check("dry-run печатает план", "seq=1" in r.stdout and "seq=2" in r.stdout,
              r.stdout.strip()[:200])
        check("dry-run витрину не трогал",
              scalar("SELECT count(*) FROM duckdb_tables() WHERE table_name='%s'" % TABLE) == "0")

        # 3. Боевой прогон.
        r = run_apply()
        check("apply код 0", r.returncode == 0, r.stderr.strip()[-300:])

        n = scalar('SELECT count(*) FROM "%s"' % TABLE)
        check("таблица создана, 2 строки после дельты", n == "2", f"rows={n}")
        rows = dict((r_[0], r_[1:]) for r_ in psql('SELECT "Ref_Key","DataVersion","Description" FROM "%s"' % TABLE))
        check("k2 заменён дельтой", rows.get("k2") == ("v2", "beta2"), repr(rows.get("k2")))
        check("k3 удалён gone", "k3" not in rows)
        check("k1 на месте", rows.get("k1") == ("v1", "alpha"), repr(rows.get("k1")))
        grant = scalar("SELECT has_table_privilege('serene_ro', '%s', 'SELECT')" % TABLE)
        check("GRANT serene_ro есть", grant in ("t", "true", "True"), grant)
        check("снимок $metadata записан ФАЙЛОМ, байт-в-байт из чанка",
              os.path.exists(META_FILE)
              and open(META_FILE, "rb").read() == META_XML.encode("utf-8"))
        check("таблица packet_metadata НЕ создаётся",
              scalar("SELECT count(*) FROM duckdb_tables() "
                     "WHERE database_name = current_database() "
                     "AND table_name='packet_metadata'") == "0")
        src = psql("SELECT src_table FROM search_changed_sources")
        check("search_changed_sources содержит таблицу", (TABLE,) in src, repr(src)[:200])
        prof = psql("SELECT rows, key_props FROM base_profile WHERE entity='%s'" % TABLE)
        check("base_profile: rows=2, ключ", len(prof) == 1 and prof[0][0] == "2"
              and prof[0][1] == "Ref_Key", repr(prof)[:200])
        ts = scalar("SELECT count(*) FROM search_quality WHERE k='mart_changed_ts'")
        check("mart_changed_ts записан", ts == "1", ts)
        check("pkg1 applied", pkg_state(pkg1)["state"] == "applied")
        check("pkg2 applied", pkg_state(pkg2)["state"] == "applied")
        check("last_applied_seq=2", base_state()["last_applied_seq"] == 2)

        # 4. Идемпотентность: повторный заход — no-op.
        before = psql('SELECT * FROM "%s" ORDER BY "Ref_Key"' % TABLE)
        r = run_apply()
        after = psql('SELECT * FROM "%s" ORDER BY "Ref_Key"' % TABLE)
        check("повторный заход код 0", r.returncode == 0, r.stderr.strip()[-200:])
        check("повторный заход данные те же", before == after)
        check("повторный заход состояние то же",
              pkg_state(pkg2)["state"] == "applied" and base_state()["last_applied_seq"] == 2)

        # 4.5. Пакет kind=meta со свежим снимком: файл перезаписывается атомарно.
        META_XML2 = "<metadata><entity>pkt_probe_catalog</entity><v>2</v></metadata>"
        em2, cm2 = make_chunk("metadata", META_XML2.encode("utf-8"), "", 0)
        m2m = base_manifest(3, "ddd00003", "meta")
        m2m["metadata"] = {"included": True, "fingerprint": "sha256:probe-meta-2",
                           "chunks": ["metadata"]}
        m2m["chunks"] = [em2]
        pkg2m = write_package(3, "ddd00003", "meta", m2m, {"metadata": cm2})
        r = run_apply()
        check("meta-пакет код 0", r.returncode == 0, r.stderr.strip()[-200:])
        check("снимок перезаписан новым содержимым",
              open(META_FILE, "rb").read() == META_XML2.encode("utf-8"))
        check("meta-пакет applied", pkg_state(pkg2m)["state"] == "applied")
        check("temp-файлов атомарной записи не осталось",
              os.listdir(os.path.join(META_DIR, BASE_ID)) == ["$metadata"])

        # 5. mix_versions: две версии k1 в витрине → карантин, данные не тронуты.
        psql_exec('INSERT INTO "%s" VALUES (\'k1\', \'v9\', \'alpha-dup\');' % TABLE)
        d3 = csv_bytes([("k9", "v1", "omega")])
        e3, c3 = make_chunk("chunk-00001", d3, TABLE, 1)
        m3 = base_manifest(4, "ccc00004", "delta")
        m3["entities"] = [{"name": TABLE, "op": "delta", "rows": 1, "chunks": ["chunk-00001"]}]
        m3["chunks"] = [e3]
        pkg3 = write_package(4, "ccc00004", "delta", m3, {"chunk-00001": c3})
        r = run_apply()
        st3 = pkg_state(pkg3)
        check("mix_versions: apply код 3", r.returncode == 3, f"rc={r.returncode}")
        check("mix_versions: пакет quarantined",
              st3["state"] == "quarantined" and st3["error"] == "mix_versions", repr(st3))
        check("mix_versions: дельта не применилась",
              scalar('SELECT count(*) FROM "%s" WHERE "Ref_Key"=\'k9\'' % TABLE) == "0")
        psql_exec('DELETE FROM "%s" WHERE "DataVersion"=\'v9\';' % TABLE)
        # 6. Пилотный plain-пакет (без age): full + metadata, режим — по магии.
        META_XML3 = "<metadata><entity>pkt_probe_catalog</entity><v>plain</v></metadata>"
        pf_csv = csv_bytes([("k1", "v3", "plain-a"), ("k7", "v3", "plain-b")])
        pe1, pc1 = make_chunk_plain("chunk-00001", pf_csv, TABLE, 2)
        pem, pcm = make_chunk_plain("metadata", META_XML3.encode("utf-8"), "", 0)
        m5 = base_manifest(5, "eee00005", "full")
        m5["entities"] = [{"name": TABLE, "op": "full", "rows": 2,
                           "chunks": ["chunk-00001"], "key": ["Ref_Key"]}]
        m5["metadata"] = {"included": True, "fingerprint": "sha256:probe-meta-plain",
                          "chunks": ["metadata"]}
        m5["chunks"] = [pe1, pem]
        pkg5 = write_package(5, "eee00005", "full", m5,
                             {"chunk-00001": pc1, "metadata": pcm}, plain=True)
        r = run_apply()
        check("plain-пакет: apply код 0", r.returncode == 0, r.stderr.strip()[-200:])
        check("plain-пакет applied", pkg_state(pkg5)["state"] == "applied")
        rows = dict((r_[0], r_[1:]) for r_
                    in psql('SELECT "Ref_Key","DataVersion","Description" FROM "%s"' % TABLE))
        check("plain full заменил таблицу (2 строки, k7 на месте)",
              len(rows) == 2 and rows.get("k7") == ("v3", "plain-b"), repr(rows)[:150])
        check("plain metadata записан файлом",
              open(META_FILE, "rb").read() == META_XML3.encode("utf-8"))

        # 7. Узкая дельта (живой кейс 112/117): чанк уже таблицы витрины.
        w_hdr = ("Ref_Key", "DataVersion", "Поле1", "Поле2", "Поле3")
        e6, c6 = make_chunk("chunk-00001",
                            csv_bytes([("k1", "v1", "a1", "b1", "c1"),
                                       ("k2", "v1", "a2", "b2", "c2")], header=w_hdr),
                            TABLE2, 2)
        m6 = base_manifest(6, "fff00006", "full")
        m6["entities"] = [{"name": TABLE2, "op": "full", "rows": 2,
                           "chunks": ["chunk-00001"], "key": ["Ref_Key"]}]
        m6["chunks"] = [e6]
        pkg6 = write_package(6, "fff00006", "full", m6, {"chunk-00001": c6})

        e7, c7 = make_chunk("chunk-00001",
                            csv_bytes([("k2", "v2", "новое2"), ("k3", "v1", "новое3")],
                                      header=("Ref_Key", "DataVersion", "Поле2")),
                            TABLE2, 2)
        m7 = base_manifest(7, "fff00007", "delta")
        m7["entities"] = [{"name": TABLE2, "op": "delta", "rows": 2, "chunks": ["chunk-00001"]}]
        m7["chunks"] = [e7]
        pkg7 = write_package(7, "fff00007", "delta", m7, {"chunk-00001": c7})

        # Колонка вперёд: Поле4 в чанке есть, в витрине нет — эталон применяет,
        # в журнал идёт строка про несовпадение схем (п. 13, молчания нет).
        e8, c8 = make_chunk("chunk-00001",
                            csv_bytes([("k4", "v1", "x4", "y4")],
                                      header=("Ref_Key", "DataVersion", "Поле2", "Поле4")),
                            TABLE2, 1)
        m8 = base_manifest(8, "fff00008", "delta")
        m8["entities"] = [{"name": TABLE2, "op": "delta", "rows": 1, "chunks": ["chunk-00001"]}]
        m8["chunks"] = [e8]
        pkg8 = write_package(8, "fff00008", "delta", m8, {"chunk-00001": c8})

        # Дельта на таблицу, которой в витрине нет (ждётся full_entity от агента).
        e9, c9 = make_chunk("chunk-00001",
                            csv_bytes([("g1", "v1", "ghost")]), GHOST, 1)
        m9 = base_manifest(9, "fff00009", "delta")
        m9["entities"] = [{"name": GHOST, "op": "delta", "rows": 1, "chunks": ["chunk-00001"]}]
        m9["chunks"] = [e9]
        pkg9 = write_package(9, "fff00009", "delta", m9, {"chunk-00001": c9})

        r = run_apply()
        check("7: заход код 3 (ghost-дельта в карантине)", r.returncode == 3,
              f"rc={r.returncode} {r.stderr.strip()[-150:]}")
        check("7: full/узкая/вперёд пакеты applied",
              all(pkg_state(p)["state"] == "applied" for p in (pkg6, pkg7, pkg8)))
        rows = dict((r_[0], r_[1:]) for r_ in psql(
            'SELECT "Ref_Key","DataVersion","Поле1","Поле2","Поле3" FROM "%s"' % TABLE2))
        check("7: узкая дельта — k2 заменён, Поле1/Поле3 пустые строки",
              rows.get("k2") == ("v2", "", "новое2", ""), repr(rows.get("k2")))
        check("7: узкая дельта — новая строка k3 тоже выровнена",
              rows.get("k3") == ("v1", "", "новое3", ""), repr(rows.get("k3")))
        check("7: нетронутая строка k1 цела",
              rows.get("k1") == ("v1", "a1", "b1", "c1"), repr(rows.get("k1")))
        check("7: колонка вперёд применилась, k4 без Поле4",
              rows.get("k4") == ("v1", "", "x4", ""), repr(rows.get("k4")))
        check("7: журнал назвал колонки чанка вне витрины",
              "колонки чанка вне витрины" in r.stderr and "Поле4" in r.stderr,
              r.stderr.strip()[-200:])
        st9 = pkg_state(pkg9)
        check("7: delta_without_table — пакет quarantined",
              st9["state"] == "quarantined" and st9["error"] == "delta_without_table",
              repr(st9))
        check("7: ghost-таблица не создана",
              scalar("SELECT count(*) FROM duckdb_tables() "
                     "WHERE database_name = current_database() AND table_name='%s'"
                     % GHOST) == "0")
        r = run_apply()
        check("7: повторный заход ghost не переприменяет",
              r.returncode == 0 and pkg_state(pkg9)["state"] == "quarantined",
              f"rc={r.returncode} {pkg_state(pkg9)}")
    finally:
        cleanup()

    # Гигиена на выходе: ни таблиц пробы, ни маркерных строк.
    left = psql("SELECT table_name FROM duckdb_tables() WHERE table_name LIKE 'pkt\\_probe\\_%'")
    check("после пробы таблиц pkt_probe_* нет", not left, repr(left)[:200])
    markers = []
    try:
        markers += psql("SELECT 1 FROM base_profile WHERE entity LIKE 'pkt\\_probe%'")
    except RuntimeError:
        pass
    check("после пробы маркерных строк нет", not markers)
    check("после пробы таблицы packet_metadata нет",
          scalar("SELECT count(*) FROM duckdb_tables() "
                 "WHERE database_name = current_database() "
                 "AND table_name='packet_metadata'") == "0")

    print()
    if FAILS:
        print("ИТОГ: FAIL — %d проверок: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ИТОГ: ok — все проверки прошли")
    return 0


if __name__ == "__main__":
    sys.exit(main())
