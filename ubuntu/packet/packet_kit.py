#!/usr/bin/env python3
"""Генератор комплекта базы пакетного транспорта (AGENT_TZ §2, контракт §3/§10).

На базу создаётся: identity age (private key), токен Bearer, клиентский
сертификат mTLS (подпись своего CA 1c-packet-ca — первый фактор, проверяется
HAProxy релея; токен остаётся вторым), начальный конфиг агента, фрагмент файла
баз приёмника и packet-setup.json для установщика Windows.

CA заводится root-шагом установки приёмника (setup-receiver): ключ
/etc/1c-packet-ca.key, сертификат /etc/1c-packet-ca.crt (пути перекрываются env
PACKET_CA_KEY/PACKET_CA_CRT). Без CA комплект не собирается — отказ с текстом,
а не комплект без сертификата. Повторный прогон: identity сохраняется (контракт
§3), токен и сертификат перевыпускаются — это и есть ротация/отзыв.

Секреты не попадают в git: весь вывод — в --out каталог (умолчание work/packet/kit/<base>,
в .gitignore). Раскладка по /etc — за владельцем (сессии туда не пишут).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packet_crypto as C  # noqa: E402

BASE_ID_RE = __import__("re").compile(r"[a-z0-9_-]+")

# Свой CA mTLS (решение владельца 06.08): клиентский сертификат агента проверяет
# HAProxy релея, Bearer-токен остаётся вторым фактором.
PACKET_CA_KEY = os.environ.get("PACKET_CA_KEY", "/etc/1c-packet-ca.key")
PACKET_CA_CRT = os.environ.get("PACKET_CA_CRT", "/etc/1c-packet-ca.crt")
OPENSSL_BIN = os.environ.get("PACKET_OPENSSL_BIN") or shutil.which("openssl")
# Срок клиентского сертификата (825 дней ≈ 27 месяцев) — именованная настройка.
CLIENT_CERT_DAYS = int(os.environ.get("PACKET_CLIENT_CERT_DAYS", "825"))


def fail(msg: str) -> "SystemExit":
    sys.stderr.write(f"packet_kit: {msg}\n")
    return SystemExit(2)


def _openssl(argv: list[str], what: str) -> subprocess.CompletedProcess:
    """Вызов openssl, как packet_crypto зовёт age: своей криптографии нет."""
    if not OPENSSL_BIN:
        raise fail("openssl не найден — задайте PACKET_OPENSSL_BIN")
    p = subprocess.run([OPENSSL_BIN] + argv, capture_output=True, timeout=120)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise fail(f"{what}: openssl завершился кодом {p.returncode}: {err[:200]}")
    return p


def issue_client_cert(base_id: str, out: str) -> str:
    """Клиентский сертификат базы: genrsa → CSR (CN=<base_id>) → подпись CA →
    PKCS#12. Возвращает пароль PFX."""
    # Серийник случайный, а не из serial-файла CA: перевыпуск (повторный прогон)
    # даёт новый сертификат, и каталог /etc не загрязняется ca.srl — рабочий
    # аккаунт туда не пишет, пишет только в каталог комплекта.
    key_pem = os.path.join(out, "client-key.pem")
    csr = os.path.join(out, "client.csr")
    crt = os.path.join(out, "client.crt")
    ext = os.path.join(out, "client-ext.cnf")
    pfx = os.path.join(out, "client.pfx")
    _openssl(["genrsa", "-out", key_pem, "2048"], "ключ клиента")
    os.chmod(key_pem, 0o600)
    _openssl(["req", "-new", "-key", key_pem, "-out", csr, "-subj", f"/CN={base_id}"],
             "CSR клиента")
    with open(ext, "w", encoding="utf-8") as f:
        f.write("basicConstraints=CA:FALSE\n"
                "keyUsage=digitalSignature\n"
                "extendedKeyUsage=clientAuth\n"
                "subjectKeyIdentifier=hash\n"
                "authorityKeyIdentifier=keyid\n")
    _openssl(["x509", "-req", "-in", csr, "-CA", PACKET_CA_CRT, "-CAkey", PACKET_CA_KEY,
              "-set_serial", "0x" + secrets.token_hex(16),
              "-days", str(CLIENT_CERT_DAYS), "-sha256", "-extfile", ext, "-out", crt],
             "подпись сертификата CA")
    os.chmod(crt, 0o644)
    pfx_password = secrets.token_urlsafe(18)
    _openssl(["pkcs12", "-export", "-inkey", key_pem, "-in", crt,
              "-out", pfx, "-passout", f"pass:{pfx_password}"], "сборка PKCS#12")
    os.chmod(pfx, 0o600)
    # CSR и extfile — промежуточные, в комплекте они мусор.
    for junk in (csr, ext):
        try:
            os.unlink(junk)
        except OSError:
            pass
    return pfx_password


def entities_from_dsn(dsn: str) -> list[str]:
    """Список сущностей из переписи base_profile указанной базы (одним SELECT)."""
    sql = "SELECT entity FROM base_profile WHERE rows > 0 ORDER BY 1;"
    p = subprocess.run(
        ["psql", dsn, "--csv", "-tA", "-c", sql], capture_output=True, timeout=120
    )
    if p.returncode != 0:
        raise fail(f"psql: {p.stderr.decode('utf-8', 'replace').strip()}")
    return [ln.split(",")[0] for ln in p.stdout.decode().splitlines() if ln.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_id")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dsn", default=None, help="DSN базы для начального списка сущностей")
    ap.add_argument("--receiver-url", default="https://1c-gate.timpul.ru")
    args = ap.parse_args()

    if not BASE_ID_RE.fullmatch(args.base_id):
        raise fail(f"base_id не по форме [a-z0-9_-]+: {args.base_id!r}")

    # CA проверяется ДО создания каталога комплекта: без CA комплекта не
    # получается вовсе, и мусора от отказа не остаётся.
    missing = [p for p in (PACKET_CA_KEY, PACKET_CA_CRT) if not os.path.exists(p)]
    if missing:
        raise fail("CA 1c-packet-ca не заведён: нет %s — сначала root-шаг "
                   "установки приёмника (setup-receiver); пути перекрываются "
                   "PACKET_CA_KEY/PACKET_CA_CRT" % ", ".join(missing))

    out = args.out or os.path.join("work", "packet", "kit", args.base_id)
    os.makedirs(out, exist_ok=True)
    identity = os.path.join(out, "age.key")

    if os.path.exists(identity):
        pubkey = C.recipient_of(identity)  # комплект не затирается (контракт §3)
        print(f"identity уже есть — pubkey взят из неё: {pubkey}")
    else:
        pubkey = C.keygen(identity)
        print(f"identity создан: {identity} (600)")

    # Сертификат перевыпускается при каждом прогоне — это ротация/отзыв.
    pfx_password = issue_client_cert(args.base_id, out)
    print(f"клиентский сертификат: {out}/client.crt + client-key.pem (600) + client.pfx")

    token = secrets.token_hex(32)

    entities: list[str] = []
    if args.dsn:
        entities = entities_from_dsn(args.dsn)
        print(f"сущностей из base_profile: {len(entities)}")

    config = {
        "config_version": 1,
        "entities": entities,
        "params": {"page_size": 10000, "tact_seconds": 1200, "chunk_mb": 32},
    }

    setup = {
        "base_id": args.base_id,
        "token": token,
        "recipient_pubkey": pubkey,
        "receiver_url": args.receiver_url,
        "client_pfx": "client.pfx",
        "client_pfx_password": pfx_password,
    }
    with open(os.path.join(out, "packet-setup.json"), "w", encoding="utf-8") as f:
        json.dump(setup, f, ensure_ascii=False, indent=2)

    bases_entry = {args.base_id: {"token": token, "identity": identity, "config": config}}
    with open(os.path.join(out, "bases-entry.json"), "w", encoding="utf-8") as f:
        json.dump(bases_entry, f, ensure_ascii=False, indent=2)

    print(f"комплект: {out}/packet-setup.json (установщику), {out}/bases-entry.json (приёмнику)")
    print("раскладка /etc и перезапуск приёмника — за владельцем")
    return 0


if __name__ == "__main__":
    sys.exit(main())
