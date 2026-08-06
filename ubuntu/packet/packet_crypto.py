#!/usr/bin/env python3
"""Криптография пакетного транспорта: тонкая обёртка над штатным age CLI.

Здесь нет ни одного криптопримитива — только вызовы age/age-keygen и разбор
их вывода. Формат файлов — age v1, получатель X25519. Устройство и основания —
docs/PACKET_CONTRACT.md §3.

Бинарь ищется так: env PACKET_AGE_BIN → PATH (`age`, `age-keygen`).
Ubuntu (бой): пакет ОС `age`. Разработка: work/packet/bin/ (в .gitignore).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

AGE_BIN = os.environ.get("PACKET_AGE_BIN") or shutil.which("age")
KEYGEN_BIN = os.environ.get("PACKET_AGE_KEYGEN_BIN") or shutil.which("age-keygen")

_RECIPIENT_RE = re.compile(r"(age1[0-9a-z]+)")


class PacketCryptoError(RuntimeError):
    """Сбой age: возврат ненулевой, бинарь не найден, невозможный ключ."""


def _need(bin_path: str | None, what: str) -> str:
    if not bin_path:
        raise PacketCryptoError(
            f"{what}: бинарь не найден. Задайте PACKET_AGE_BIN или поставьте пакет age."
        )
    return bin_path


def _run(argv: list[str], what: str) -> subprocess.CompletedProcess:
    p = subprocess.run(argv, capture_output=True, timeout=600)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise PacketCryptoError(f"{what}: age завершился кодом {p.returncode}: {err}")
    return p


def keygen(identity_path: str) -> str:
    """Сгенерировать identity (private key) в файл 600, вернуть recipient (pubkey)."""
    kg = _need(KEYGEN_BIN, "keygen")
    if os.path.exists(identity_path):
        raise PacketCryptoError(f"keygen: файл {identity_path} уже есть — не затираю")
    p = _run([kg, "-o", identity_path], "keygen")
    os.chmod(identity_path, 0o600)
    m = _RECIPIENT_RE.search(p.stderr.decode("utf-8", "replace"))
    if not m:  # age-keygen печатает «Public key: age1…» в stderr
        raise PacketCryptoError("keygen: не удалось разобрать public key из вывода age-keygen")
    return m.group(1)


def recipient_of(identity_path: str) -> str:
    """Публичный получатель по файлу identity (без показа private key)."""
    kg = _need(KEYGEN_BIN, "recipient_of")
    p = _run([kg, "-y", identity_path], "recipient_of")
    out = p.stdout.decode("utf-8", "replace").strip()
    if not _RECIPIENT_RE.fullmatch(out):
        raise PacketCryptoError(f"recipient_of: неожиданный вывод age-keygen -y: {out!r}")
    return out


def encrypt_file(src: str, dst: str, recipient: str) -> None:
    """Зашифровать файл получателю X25519. Только recipient-форму age1…"""
    age = _need(AGE_BIN, "encrypt")
    if not _RECIPIENT_RE.fullmatch(recipient or ""):
        raise PacketCryptoError(f"encrypt: получатель не похож на X25519 recipient: {recipient!r}")
    _run([age, "-r", recipient, "-o", dst, src], "encrypt")


def decrypt_file(src: str, dst: str, identity_path: str) -> None:
    """Расшифровать файл identity с Ubuntu. Битый/чужой файл → PacketCryptoError."""
    age = _need(AGE_BIN, "decrypt")
    _run([age, "-d", "-i", identity_path, "-o", dst, src], "decrypt")
    if not os.path.exists(dst):
        # Каприз age CLI (проверено на v1.1.1): при ПУСТОМ открытом тексте выходной файл
        # не создаётся вовсе, код возврата 0. Для контракта пустой файл — законный.
        open(dst, "wb").close()


def sha256_file(path: str) -> str:
    """sha256 файла — отпечатки чанков в манифесте (контракт §5)."""
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
