#!/usr/bin/env python3
"""Оффлайн-проба служебного чанка `log` (лог установщика/агента).

Оффлайн: весь мир — временный каталог, чанки в пилотном plain-режиме (zstd без
age — приёмник и apply определяют режим по магии), SQL в витрину подменён
(контрактную транзакцию против живого движка покрывает test_packet_apply.py).

Проверяется: секция `log` манифеста → файл <PACKET_META_DIR>/<base>/logs/
<pkg>[_<source>].log с содержимым байт-в-байт; повторная посылка не затирает
прежний файл; `../../evil` в source не выходит за каталог logs.

Было: python3 -m pytest (25.08: pytest в системном питоне нет — переписано
на стиль PASS/FAIL остальных packet-замков, без ослабления проверок).

Прогон: python3 ubuntu/packet/test_packet_log.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Контур пробы: корень хранения, meta-каталог и файл баз — во временном каталоге,
# env — до импорта packet_apply/packet_server (их конфиг читается на импорте).
_TMP = tempfile.TemporaryDirectory()
ROOT = os.path.join(_TMP.name, "root")
META_DIR = os.path.join(_TMP.name, "packet-meta")
BASE_ID = "utlog"
ZSTD = os.environ.get("PACKET_ZSTD_BIN", "/usr/bin/zstd")
BASES_PATH = os.path.join(_TMP.name, "bases.json")
with open(BASES_PATH, "w", encoding="utf-8") as f:
    json.dump({BASE_ID: {"token": "tok-utlog", "identity": "", "config": {}}},
              f, ensure_ascii=False)
os.environ["PACKET_ROOT"] = ROOT
os.environ["PACKET_BASES"] = BASES_PATH
os.environ["PACKET_META_DIR"] = META_DIR

import packet_apply as A  # noqa: E402
import packet_server as S  # noqa: E402

LOGS_DIR = os.path.join(META_DIR, BASE_ID, "logs")

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _write_pkg(seq: int, rand: str, source: str | None, content: bytes):
    """Verified-пакет с одним служебным чанком `log` (plain zstd, как пилот)."""
    pkg_id = f"{seq:06d}-{rand}"
    pdir = os.path.join(ROOT, "inbox", BASE_ID, pkg_id)
    os.makedirs(pdir)
    z = subprocess.run([ZSTD, "-q", "-3", "-c"], input=content,
                       capture_output=True, check=True).stdout
    with open(os.path.join(pdir, "log.zst"), "wb") as f:
        f.write(z)
    manifest = {"manifest_version": 1, "base_id": BASE_ID, "seq": seq,
                "kind": "delta", "created_utc": "2026-08-11T10:00:00Z",
                "agent_version": "proba-1", "package_id": f"{BASE_ID}/{pkg_id}",
                "entities": [], "log": {"source": source, "chunks": ["log"]},
                "chunks": [{"name": "log", "entity": "", "rows": 0,
                            "bytes_plain": len(content), "bytes_enc": len(z),
                            "sha256_plain": _sha256(content),
                            "sha256_enc": _sha256(z)}]}
    return pkg_id, manifest


def _no_mart():
    # SQL витрины не проверяется: контрактные таблицы — забота живой пробы.
    real_psql, real_scalar = A._psql, A._psql_scalar
    A._psql = lambda sql: None
    A._psql_scalar = lambda sql: "0"
    return real_psql, real_scalar


def _restore_mart(pair):
    A._psql, A._psql_scalar = pair


t("server: log в SERVICE_CHUNKS", "log" in S._SERVICE_CHUNKS)
t("server: log — valid_id", S._valid_id("log"))
t("server: имена чанка без .csv",
  S._chunk_filenames("log") == ("log.zst.age", "log.zst"))

_mart = _no_mart()
try:
    content = "установка начата\nшаг 1 ок\n".encode("utf-8")
    pkg_id, m = _write_pkg(1, "log00001", "install.log", content)
    applied = A.apply_package(BASE_ID, pkg_id, m, dry_run=False)
    dst = os.path.join(LOGS_DIR, pkg_id + "_install.log")
    t("log: apply → applied", applied == "applied", applied)
    t("log: файл на месте", os.path.exists(dst))
    t("log: содержимое байт-в-байт",
      os.path.exists(dst) and open(dst, "rb").read() == content)

    first = b"log v1\n"
    pkg_id2, m2 = _write_pkg(2, "log00002", "install.log", first)
    t("resend: первый apply",
      A.apply_package(BASE_ID, pkg_id2, m2, dry_run=False) == "applied")
    with open(os.path.join(ROOT, "inbox", BASE_ID, pkg_id2, "log.zst"), "wb") as f:
        f.write(subprocess.run([ZSTD, "-q", "-3", "-c"], input=b"log v2\n",
                               capture_output=True, check=True).stdout)
    t("resend: повторный apply",
      A.apply_package(BASE_ID, pkg_id2, m2, dry_run=False) == "applied")
    dst1 = os.path.join(LOGS_DIR, pkg_id2 + "_install.log")
    dst2 = os.path.join(LOGS_DIR, pkg_id2 + "_install-2.log")
    t("resend: первый файл не затёрт",
      open(dst1, "rb").read() == first)
    t("resend: второй файл = v2",
      open(dst2, "rb").read() == b"log v2\n")

    pkg_id3, m3 = _write_pkg(3, "log00003", "../../evil", b"evil\n")
    t("traversal: apply",
      A.apply_package(BASE_ID, pkg_id3, m3, dry_run=False) == "applied")
    t("traversal: каталог logs есть", os.path.isdir(LOGS_DIR))
    outside = False
    for fn in os.listdir(LOGS_DIR):
        if os.path.dirname(os.path.join(LOGS_DIR, fn)) != LOGS_DIR:
            outside = True
    t("traversal: все файлы внутри logs", not outside)
    names = [fn for fn in os.listdir(LOGS_DIR) if fn.startswith(pkg_id3)]
    t("traversal: одно имя без ..",
      len(names) == 1 and "/" not in names[0] and ".." not in names[0], names)
    t("traversal: нет META/evil",
      not os.path.exists(os.path.join(META_DIR, BASE_ID, "evil"))
      and not os.path.exists(os.path.join(META_DIR, "evil")))
    t("traversal: содержимое evil",
      names and open(os.path.join(LOGS_DIR, names[0]), "rb").read() == b"evil\n")

    pkg_id4, m4 = _write_pkg(4, "log00004", None, b"bare\n")
    t("без source: apply",
      A.apply_package(BASE_ID, pkg_id4, m4, dry_run=False) == "applied")
    dst4 = os.path.join(LOGS_DIR, pkg_id4 + ".log")
    t("без source: содержимое",
      open(dst4, "rb").read() == b"bare\n")

    def _skipped_pkg(seq: int, rand: str, skipped: list):
        pkg_id = f"{seq:06d}-{rand}"
        pdir = os.path.join(ROOT, "inbox", BASE_ID, pkg_id)
        os.makedirs(pdir)
        manifest = {"manifest_version": 1, "base_id": BASE_ID, "seq": seq,
                    "kind": "meta", "created_utc": "2026-08-11T10:00:00Z",
                    "agent_version": "proba-1", "package_id": f"{BASE_ID}/{pkg_id}",
                    "entities": [], "skipped": skipped, "chunks": []}
        return pkg_id, manifest

    pkg1, m1 = _skipped_pkg(10, "skp00001",
                            [{"entity": "Catalog_X", "error": "no_read_right"}])
    t("skipped: первая запись",
      A.apply_package(BASE_ID, pkg1, m1, dry_run=False) == "applied")
    dst_sk = os.path.join(META_DIR, BASE_ID, "skipped.json")
    t("skipped: entities=1",
      len(json.load(open(dst_sk, encoding="utf-8"))["entities"]) == 1)
    pkg2, m_sk2 = _skipped_pkg(11, "skp00002", [])
    t("skipped: пустой список очищает",
      A.apply_package(BASE_ID, pkg2, m_sk2, dry_run=False) == "applied")
    t("skipped: entities=[]",
      json.load(open(dst_sk, encoding="utf-8"))["entities"] == [])
finally:
    _restore_mart(_mart)

print("\nИТОГ: %d ok, %d fail" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
