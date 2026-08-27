#!/usr/bin/env python3
"""Оффлайн-замок Д5: отсутствие $metadata ловится внятным словом + need_metadata.

Прогон: python3 ubuntu/packet/test_packet_meta_signal.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import packet_meta_signal as S  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS:", name)
    else:
        FAIL += 1
        print("FAIL:", name, detail)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="d5-meta-")
    try:
        bases = os.path.join(tmp, "bases.json")
        meta_dir = os.path.join(tmp, "packet-meta")
        os.makedirs(os.path.join(meta_dir, "b1"))
        data = {
            "b1": {
                "token": "t",
                "identity": "age1x",
                "config": {
                    "config_version": 3,
                    "entities": ["Catalog_X"],
                    "params": {"page_size": 10000, "tact_seconds": 1200, "chunk_mb": 32},
                },
            }
        }
        with open(bases, "w", encoding="utf-8") as f:
            json.dump(data, f)

        S.PACKET_BASES = bases
        S.PACKET_META_DIR = meta_dir

        # (а) нет снимка → request ставит need_metadata и поднимает version
        check("а: snap отсутствует", not S.snap_present("b1"))
        rc = S.request_metadata("b1", bases)
        check("а: request rc=0", rc == 0)
        with open(bases, encoding="utf-8") as f:
            after = json.load(f)
        cfg = after["b1"]["config"]
        check("а: need_metadata=1", cfg["params"].get("need_metadata") == 1,
              repr(cfg["params"]))
        check("а: config_version 3→4", cfg["config_version"] == 4,
              repr(cfg["config_version"]))

        # (б) повторный request не крутит version зря
        rc2 = S.request_metadata("b1", bases)
        check("б: повтор request rc=0", rc2 == 0)
        with open(bases, encoding="utf-8") as f:
            after2 = json.load(f)
        check("б: version остался 4", after2["b1"]["config"]["config_version"] == 4)

        # (в) ack снимает флаг
        snap = os.path.join(meta_dir, "b1", "$metadata")
        with open(snap, "w", encoding="utf-8") as f:
            f.write("<edmx/>")
        check("в: snap появился", S.snap_present("b1"))
        rc3 = S.ack_metadata("b1", bases)
        check("в: ack rc=0", rc3 == 0)
        with open(bases, encoding="utf-8") as f:
            after3 = json.load(f)
        params3 = after3["b1"]["config"]["params"]
        check("в: need_metadata снят", "need_metadata" not in params3, repr(params3))
        check("в: version 4→5", after3["b1"]["config"]["config_version"] == 5)

        # (г) request при живом снимке — no-op
        rc4 = S.request_metadata("b1", bases)
        check("г: request при snap rc=0", rc4 == 0)
        with open(bases, encoding="utf-8") as f:
            after4 = json.load(f)
        check("г: version не вырос", after4["b1"]["config"]["config_version"] == 5)
        check("г: need_metadata не вернулся",
              "need_metadata" not in after4["b1"]["config"]["params"])

        # (д) build.sh содержит замок с внятным словом
        build = open(os.path.join(ROOT, "..", "serenedb", "build.sh"),
                     encoding="utf-8").read()
        check("д: build.sh зовёт packet_meta_signal request",
              "packet_meta_signal" in build and "request" in build)
        check("д: fail с словом need_metadata / нет снимка",
              "нет снимка" in build and "need_metadata" in build)
        check("д: fail до corpus_build (якорь перед precheck)",
              build.find("нет снимка") < build.find("corpus_precheck.sql"))

        # (е) агент ≥1.1.3 читает need_metadata
        agent = open(os.path.join(ROOT, "..", "..", "windows", "packet-agent",
                                  "src", "PacketAgent.cs"), encoding="utf-8").read()
        check("е: Version 1.1.3", 'Version = "1.1.3"' in agent)
        check("е: NeedMetadata helper", "NeedMetadata(" in agent)
        check("е: early kind=meta на need_metadata",
              "need_metadata — отправляю kind=meta" in agent)

        # (ж) apply зовёт ack после записи снимка
        apply = open(os.path.join(ROOT, "packet_apply.py"), encoding="utf-8").read()
        check("ж: apply импортирует ack_metadata",
              "ack_metadata" in apply and "packet_meta_signal" in apply)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("PASS %d FAIL %d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
