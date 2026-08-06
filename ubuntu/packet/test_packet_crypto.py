#!/usr/bin/env python3
"""Оффлайн-проба packet_crypto: без сети, без базы, без сервера.

Бинарь age берётся из PACKET_AGE_BIN, PATH или dev-копии work/packet/bin/.
Прогон: PACKET_AGE_BIN=work/packet/bin/age/age python3 ubuntu/packet/test_packet_crypto.py
"""

from __future__ import annotations

import os
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

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def roundtrip(name: str, data: bytes) -> None:
    with tempfile.TemporaryDirectory() as d:
        ident = os.path.join(d, "id.txt")
        pub = C.keygen(ident)
        src = os.path.join(d, "plain.bin")
        enc = os.path.join(d, "c.age")
        dec = os.path.join(d, "back.bin")
        with open(src, "wb") as f:
            f.write(data)
        C.encrypt_file(src, enc, pub)
        C.decrypt_file(enc, dec, ident)
        with open(dec, "rb") as f:
            back = f.read()
        check(name, back == data and open(enc, "rb").read() != data)


def main() -> int:
    # 1. keygen: файл 600, recipient разбирается двумя путями
    with tempfile.TemporaryDirectory() as d:
        ident = os.path.join(d, "id.txt")
        pub1 = C.keygen(ident)
        mode = os.stat(ident).st_mode & 0o777
        check("keygen: права identity 600", mode == 0o600, oct(mode))
        check("keygen: recipient совпадает с age-keygen -y", C.recipient_of(ident) == pub1)
        try:
            C.keygen(ident)
            check("keygen: существующий identity не затирается", False)
        except C.PacketCryptoError:
            check("keygen: существующий identity не затирается", True)

    # 2. roundtrip на разных полезных нагрузках
    roundtrip("roundtrip: пустой файл", b"")
    roundtrip("roundtrip: unicode/кириллица", "Контрагенты «Ромашка»\r\n".encode())
    roundtrip("roundtrip: бинарные с NUL", bytes(range(256)) * 4)
    roundtrip("roundtrip: 5 МБ случайных", os.urandom(5 << 20))

    # 3. чужой identity не расшифровывает
    with tempfile.TemporaryDirectory() as d:
        id_a, id_b = os.path.join(d, "a.txt"), os.path.join(d, "b.txt")
        pub_a = C.keygen(id_a)
        C.keygen(id_b)
        src, enc, dec = (os.path.join(d, n) for n in ("p", "c.age", "back"))
        with open(src, "wb") as f:
            f.write(b"secret")
        C.encrypt_file(src, enc, pub_a)
        try:
            C.decrypt_file(enc, dec, id_b)
            check("чужой identity: отказ", False)
        except C.PacketCryptoError:
            check("чужой identity: отказ", True)
        check("чужой identity: расшифрованного файла нет", not os.path.exists(dec))

    # 4. подмена шифртекста ловится AEAD
    with tempfile.TemporaryDirectory() as d:
        ident = os.path.join(d, "id.txt")
        pub = C.keygen(ident)
        src, enc, dec = (os.path.join(d, n) for n in ("p", "c.age", "back"))
        with open(src, "wb") as f:
            f.write(os.urandom(4096))
        C.encrypt_file(src, enc, pub)
        raw = bytearray(open(enc, "rb").read())
        raw[-100] ^= 0xFF  # полезная нагрузка, не заголовок
        with open(enc, "wb") as f:
            f.write(raw)
        try:
            C.decrypt_file(enc, dec, ident)
            check("подмена байта: отказ (AEAD)", False)
        except C.PacketCryptoError:
            check("подмена байта: отказ (AEAD)", True)

    # 5. ротация: шифруем новому получателю — старый identity молчит
    with tempfile.TemporaryDirectory() as d:
        old_id, new_id = os.path.join(d, "old.txt"), os.path.join(d, "new.txt")
        C.keygen(old_id)
        new_pub = C.keygen(new_id)
        src, enc, dec = (os.path.join(d, n) for n in ("p", "c.age", "back"))
        with open(src, "wb") as f:
            f.write(b"rotation")
        C.encrypt_file(src, enc, new_pub)
        C.decrypt_file(enc, dec, new_id)
        check("ротация: новый identity расшифровывает", open(dec, "rb").read() == b"rotation")
        try:
            C.decrypt_file(enc, dec, old_id)
            check("ротация: старый identity молчит", False)
        except C.PacketCryptoError:
            check("ротация: старый identity молчит", True)

    # 6. sha256_file: стабилен и чувствителен
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f")
        with open(p, "wb") as f:
            f.write(b"abc" * 1000)
        h1, h2 = C.sha256_file(p), C.sha256_file(p)
        with open(p, "ab") as f:
            f.write(b"x")
        check("sha256: стабилен и чувствителен", h1 == h2 and C.sha256_file(p) != h1)

    # 7. отказ без recipient-формы: парольную фразу подсунуть нельзя
    with tempfile.TemporaryDirectory() as d:
        src, enc = os.path.join(d, "p"), os.path.join(d, "c.age")
        with open(src, "wb") as f:
            f.write(b"x")
        try:
            C.encrypt_file(src, enc, "not-a-recipient")
            check("encrypt: мусорный получатель отвергнут", False)
        except C.PacketCryptoError:
            check("encrypt: мусорный получатель отвергнут", True)

    print(f"\n{'ПРОБА ЗЕЛЁНАЯ' if not FAILS else 'ПАДЕНИЯ: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
