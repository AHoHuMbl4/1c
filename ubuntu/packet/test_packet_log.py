#!/usr/bin/env python3
"""pytest-проба служебного чанка `log` (лог установщика/агента).

Оффлайн: весь мир — временный каталог, чанки в пилотном plain-режиме (zstd без
age — приёмник и apply определяют режим по магии), SQL в витрину подменён
(контрактную транзакцию против живого движка покрывает test_packet_apply.py).

Проверяется: секция `log` манифеста → файл <PACKET_META_DIR>/<base>/logs/
<pkg>[_<source>].log с содержимым байт-в-байт; повторная посылка не затирает
прежний файл; `../../evil` в source не выходит за каталог logs.

Прогон: python3 -m pytest ubuntu/packet/test_packet_log.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

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


@pytest.fixture
def no_mart(monkeypatch):
    # SQL витрины не проверяется: контрактные таблицы — забота живой пробы.
    monkeypatch.setattr(A, "_psql", lambda sql: None)
    monkeypatch.setattr(A, "_psql_scalar", lambda sql: "0")


def test_server_takes_log_chunk():
    assert "log" in S._SERVICE_CHUNKS
    assert S._valid_id("log")
    # Хранение как у прочих служебных: log.zst / log.zst.age, без «.csv».
    assert S._chunk_filenames("log") == ("log.zst.age", "log.zst")


def test_log_saved(no_mart):
    content = "установка начата\nшаг 1 ок\n".encode("utf-8")
    pkg_id, m = _write_pkg(1, "log00001", "install.log", content)
    assert A.apply_package(BASE_ID, pkg_id, m, dry_run=False) == "applied"
    dst = os.path.join(LOGS_DIR, pkg_id + "_install.log")
    assert os.path.exists(dst)
    assert open(dst, "rb").read() == content


def test_log_resend_no_overwrite(no_mart):
    first = b"log v1\n"
    pkg_id, m = _write_pkg(2, "log00002", "install.log", first)
    assert A.apply_package(BASE_ID, pkg_id, m, dry_run=False) == "applied"
    # Повторная посылка того же лога (тот же pkg, новое содержимое чанка).
    with open(os.path.join(ROOT, "inbox", BASE_ID, pkg_id, "log.zst"), "wb") as f:
        f.write(subprocess.run([ZSTD, "-q", "-3", "-c"], input=b"log v2\n",
                               capture_output=True, check=True).stdout)
    assert A.apply_package(BASE_ID, pkg_id, m, dry_run=False) == "applied"
    dst1 = os.path.join(LOGS_DIR, pkg_id + "_install.log")
    dst2 = os.path.join(LOGS_DIR, pkg_id + "_install-2.log")
    assert open(dst1, "rb").read() == first  # первый файл не затёрт
    assert open(dst2, "rb").read() == b"log v2\n"


def test_log_source_traversal(no_mart):
    pkg_id, m = _write_pkg(3, "log00003", "../../evil", b"evil\n")
    assert A.apply_package(BASE_ID, pkg_id, m, dry_run=False) == "applied"
    # Всё записанное — внутри каталога logs, наружу ни байта.
    assert os.path.isdir(LOGS_DIR)
    for fn in os.listdir(LOGS_DIR):
        assert os.path.dirname(os.path.join(LOGS_DIR, fn)) == LOGS_DIR
    names = [fn for fn in os.listdir(LOGS_DIR) if fn.startswith(pkg_id)]
    assert len(names) == 1 and "/" not in names[0] and ".." not in names[0]
    assert not os.path.exists(os.path.join(META_DIR, BASE_ID, "evil"))
    assert not os.path.exists(os.path.join(META_DIR, "evil"))
    assert open(os.path.join(LOGS_DIR, names[0]), "rb").read() == b"evil\n"


def test_log_without_source(no_mart):
    pkg_id, m = _write_pkg(4, "log00004", None, b"bare\n")
    assert A.apply_package(BASE_ID, pkg_id, m, dry_run=False) == "applied"
    dst = os.path.join(LOGS_DIR, pkg_id + ".log")
    assert open(dst, "rb").read() == b"bare\n"
