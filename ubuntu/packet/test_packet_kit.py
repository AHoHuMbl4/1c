#!/usr/bin/env python3
"""Оффлайн-проба packet_kit: без сети и базы. Бинарь age — как в test_packet_crypto.

mTLS: перед прогонами kit заводится временный CA теми же командами, что пойдут
в root-шаг setup-receiver, и kit зовётся с PACKET_CA_KEY/PACKET_CA_CRT на него
(боевых /etc/1c-packet-ca.* на машине разработки нет — и это штатный случай:
без env-перекрытия kit отвечает отказом).
"""

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


def openssl(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["openssl"] + list(argv), capture_output=True, timeout=60)


def run_kit(*argv: str, ca: tuple[str, str] | None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Умолчания kit смотрят в /etc — там CA быть не может; прогонам с CA пути
    # даются явно, прогону «без CA» — заведомо отсутствующие.
    key, crt = ca or ("/nonexistent/1c-packet-ca.key", "/nonexistent/1c-packet-ca.crt")
    env.update({"PACKET_CA_KEY": key, "PACKET_CA_CRT": crt})
    return subprocess.run(
        [sys.executable, KIT, *argv], capture_output=True, timeout=120, cwd=_REPO, env=env
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        # Временный CA — те же команды, что у root-шага setup-receiver.
        ca_key = os.path.join(d, "1c-packet-ca.key")
        ca_crt = os.path.join(d, "1c-packet-ca.crt")
        p = openssl("genrsa", "-out", ca_key, "2048")
        check("CA: genrsa", p.returncode == 0)
        p = openssl("req", "-x509", "-new", "-key", ca_key, "-days", "3650", "-sha256",
                    "-subj", "/CN=1c-packet-ca",
                    "-addext", "basicConstraints=critical,CA:TRUE",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                    "-out", ca_crt)
        check("CA: самоподписанный сертификат", p.returncode == 0)
        ca = (ca_key, ca_crt)

        out = os.path.join(d, "kit")
        p = run_kit("ut", "--out", out, ca=ca)
        check("kit: код 0", p.returncode == 0)

        setup = json.load(open(os.path.join(out, "packet-setup.json"), encoding="utf-8"))
        entry = json.load(open(os.path.join(out, "bases-entry.json"), encoding="utf-8"))
        ident = os.path.join(out, "age.key")

        check("kit: поля packet-setup",
              set(setup) == {"base_id", "token", "recipient_pubkey", "receiver_url",
                             "client_pfx", "client_pfx_password"})
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

        # (а)-(в): сертификат mTLS
        crt = os.path.join(out, "client.crt")
        key_pem = os.path.join(out, "client-key.pem")
        pfx = os.path.join(out, "client.pfx")
        v = openssl("verify", "-CAfile", ca_crt, crt)
        check("kit: client.crt проходит openssl verify под CA", v.returncode == 0)
        subj = openssl("x509", "-in", crt, "-noout", "-subject").stdout.decode()
        check("kit: CN сертификата == base_id", "CN = ut" in subj or "CN=ut" in subj)
        eku = openssl("x509", "-in", crt, "-noout", "-ext", "extendedKeyUsage").stdout.decode()
        check("kit: extendedKeyUsage=clientAuth", "Client Authentication" in eku)
        check("kit: client-key.pem 600", (os.stat(key_pem).st_mode & 0o777) == 0o600)
        check("kit: client_pfx — имя файла комплекта", setup["client_pfx"] == "client.pfx")
        check("kit: пароль PFX непустой", bool(setup["client_pfx_password"]))
        pi = openssl("pkcs12", "-info", "-in", pfx, "-noout",
                     "-passin", "pass:" + setup["client_pfx_password"])
        check("kit: PFX разбирается паролем из packet-setup.json", pi.returncode == 0)
        serial1 = openssl("x509", "-in", crt, "-noout", "-serial").stdout
        csr_left = [f for f in os.listdir(out) if f.endswith((".csr", ".cnf"))]
        check("kit: промежуточных csr/extfile в комплекте нет", not csr_left)

        # повторный прогон: identity не затирается, токен новый, сертификат новый
        p2 = run_kit("ut", "--out", out, ca=ca)
        setup2 = json.load(open(os.path.join(out, "packet-setup.json"), encoding="utf-8"))
        check("kit: повтор — код 0", p2.returncode == 0)
        check("kit: повтор — pubkey прежний", setup2["recipient_pubkey"] == pub)
        check("kit: повтор — токен перевыпущен", setup2["token"] != setup["token"])
        serial2 = openssl("x509", "-in", crt, "-noout", "-serial").stdout
        check("kit: повтор — сертификат перевыпущен (serial другой)", serial1 != serial2)
        check("kit: повтор — пароль PFX новый",
              setup2["client_pfx_password"] != setup["client_pfx_password"])
        v2 = openssl("verify", "-CAfile", ca_crt, crt)
        check("kit: повтор — новый сертификат тоже verify под CA", v2.returncode == 0)

        # шифрование под выданный pubkey реально расшифровывается identity комплекта
        src, enc, dec = (os.path.join(d, n) for n in ("p", "c.age", "back"))
        with open(src, "wb") as f:
            f.write(b"kit-roundtrip")
        C.encrypt_file(src, enc, setup["recipient_pubkey"])
        C.decrypt_file(enc, dec, ident)
        check("kit: roundtrip pubkey↔identity", open(dec, "rb").read() == b"kit-roundtrip")

    # невалидный base_id — отказ, каталог не создаётся мусором
    with tempfile.TemporaryDirectory() as d:
        p3 = run_kit("Bad ID", "--out", os.path.join(d, "k"), ca=None)
        check("kit: невалидный base_id — отказ", p3.returncode == 2)

    # (г) без CA — отказ rc=2 и ни одного файла комплекта
    with tempfile.TemporaryDirectory() as d:
        out4 = os.path.join(d, "kit")
        p4 = run_kit("ut", "--out", out4, ca=None)
        check("kit: без CA — отказ rc=2", p4.returncode == 2)
        check("kit: без CA — ни одного файла", not os.path.exists(out4))
        check("kit: без CA — текст про root-шаг",
              b"CA" in p4.stderr and b"setup-receiver" in p4.stderr)

    print(f"\n{'ПРОБА ЗЕЛЁНАЯ' if not FAILS else 'ПАДЕНИЯ: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
