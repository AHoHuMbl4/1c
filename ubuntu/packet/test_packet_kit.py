#!/usr/bin/env python3
"""Оффлайн-проба packet_kit: без сети и базы. Бинарь age — как в test_packet_crypto."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEV_AGE = os.path.join(_REPO, "work", "packet", "bin", "age", "age")
_DEV_KEYGEN = os.path.join(_REPO, "work", "packet", "bin", "age", "age-keygen")
if not os.environ.get("PACKET_AGE_BIN") and os.path.exists(_DEV_AGE):
    os.environ["PACKET_AGE_BIN"] = _DEV_AGE
    os.environ["PACKET_AGE_KEYGEN_BIN"] = _DEV_KEYGEN

sys.path.insert(0, os.path.join(_REPO, "ubuntu", "packet"))
import packet_crypto as C  # noqa: E402

KIT = os.path.join(_REPO, "ubuntu", "packet", "packet_kit.py")
FAILS: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}")
    if not cond:
        FAILS.append(name)


def run_kit(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, KIT, *argv], capture_output=True, timeout=120, cwd=_REPO
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "kit")
        p = run_kit("ut", "--out", out)
        check("kit: код 0", p.returncode == 0)

        setup = json.load(open(os.path.join(out, "packet-setup.json"), encoding="utf-8"))
        entry = json.load(open(os.path.join(out, "bases-entry.json"), encoding="utf-8"))
        ident = os.path.join(out, "age.key")

        check("kit: поля packet-setup", set(setup) == {"base_id", "token", "recipient_pubkey", "receiver_url"})
        check("kit: base_id", setup["base_id"] == "ut")
        check("kit: receiver_url", setup["receiver_url"] == "https://1c-gate.timpul.ru")
        check("kit: токен 64 hex", len(setup["token"]) == 64 and all(c in "0123456789abcdef" for c in setup["token"]))
        pub = C.recipient_of(ident)
        check("kit: pubkey совпадает с identity", setup["recipient_pubkey"] == pub)
        check("kit: identity 600", (os.stat(ident).st_mode & 0o777) == 0o600)

        e = entry["ut"]
        check("kit: bases-entry token совпадает", e["token"] == setup["token"])
        check("kit: bases-entry identity — путь комплекта", e["identity"] == ident)
        cfg = e["config"]
        check("kit: config_version=1", cfg["config_version"] == 1)
        check("kit: entities — список", isinstance(cfg["entities"], list))
        check("kit: params", set(cfg["params"]) == {"page_size", "tact_seconds", "chunk_mb"})

        # повторный прогон: identity не затирается, токен новый, pubkey прежний
        p2 = run_kit("ut", "--out", out)
        setup2 = json.load(open(os.path.join(out, "packet-setup.json"), encoding="utf-8"))
        check("kit: повтор — код 0", p2.returncode == 0)
        check("kit: повтор — pubkey прежний", setup2["recipient_pubkey"] == pub)
        check("kit: повтор — токен перевыпущен", setup2["token"] != setup["token"])

        # шифрование под выданный pubkey реально расшифровывается identity комплекта
        src, enc, dec = (os.path.join(d, n) for n in ("p", "c.age", "back"))
        with open(src, "wb") as f:
            f.write(b"kit-roundtrip")
        C.encrypt_file(src, enc, setup["recipient_pubkey"])
        C.decrypt_file(enc, dec, ident)
        check("kit: roundtrip pubkey↔identity", open(dec, "rb").read() == b"kit-roundtrip")

    # невалидный base_id — отказ, каталог не создаётся мусором
    with tempfile.TemporaryDirectory() as d:
        p3 = run_kit("Bad ID", "--out", os.path.join(d, "k"))
        check("kit: невалидный base_id — отказ", p3.returncode == 2)

    print(f"\n{'ПРОБА ЗЕЛЁНАЯ' if not FAILS else 'ПАДЕНИЯ: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
