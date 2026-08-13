#!/usr/bin/env python3
"""Оффлайн-проба packet_server: сервер на 127.0.0.1:0, весь мир — временный каталог.

Прогон: python3 ubuntu/packet/test_packet_server.py
Бинарь age — из PACKET_AGE_BIN, PATH или dev-копии work/packet/bin/.
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEV_AGE = os.path.join(_REPO, "work", "packet", "bin", "age", "age")
_DEV_KEYGEN = os.path.join(_REPO, "work", "packet", "bin", "age", "age-keygen")
if not os.environ.get("PACKET_AGE_BIN") and os.path.exists(_DEV_AGE):
    os.environ["PACKET_AGE_BIN"] = _DEV_AGE
    os.environ["PACKET_AGE_KEYGEN_BIN"] = _DEV_KEYGEN

import packet_crypto as C  # noqa: E402

# Контур пробы: корень хранения и файл баз во временном каталоге, env — до импорта
# packet_server (его конфиг читается на импорте).
_TMP = tempfile.TemporaryDirectory()
ROOT = os.path.join(_TMP.name, "root")
WORK = os.path.join(_TMP.name, "work")
os.makedirs(ROOT)
os.makedirs(WORK)
TOKEN = "tok-ut-proba"
IDENTITY = os.path.join(_TMP.name, "ut.key")
PUB = C.keygen(IDENTITY)
BASES_PATH = os.path.join(_TMP.name, "bases.json")
with open(BASES_PATH, "w", encoding="utf-8") as f:
    json.dump({"ut": {"token": TOKEN, "identity": IDENTITY, "config": {
        "config_version": 3,
        "entities": ["Catalog_Контрагенты", "Document_Реализация"],
        "params": {"page_size": 10000, "tact_seconds": 1200, "chunk_mb": 32},
    }}}, f, ensure_ascii=False)
os.environ["PACKET_ROOT"] = ROOT
os.environ["PACKET_BASES"] = BASES_PATH

import packet_server as S  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("ok  " if cond else "FAIL") + f"  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


ZSTD = S.ZSTD_BIN if os.path.exists(S.ZSTD_BIN) else shutil.which("zstd")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_n = [0]


def _wf(name: str, data: bytes) -> str:
    _n[0] += 1
    p = os.path.join(WORK, f"{_n[0]:03d}-{name}")
    with open(p, "wb") as f:
        f.write(data)
    return p


def make_chunk(name: str, csv_bytes: bytes):
    """CSV → zstd → age; возвращает (запись манифеста, шифртекст)."""
    z = subprocess.run([ZSTD, "-q", "-3", "-c"], input=csv_bytes,
                       capture_output=True, check=True).stdout
    enc = _wf(name + ".age", b"")
    C.encrypt_file(_wf(name + ".zst", z), enc, PUB)
    eb = open(enc, "rb").read()
    entry = {"name": name, "entity": "Catalog_Контрагенты", "rows": 2,
             "bytes_plain": len(csv_bytes), "bytes_enc": len(eb),
             "sha256_plain": sha256(csv_bytes), "sha256_enc": sha256(eb)}
    return entry, eb


def enc_manifest(m: dict) -> bytes:
    enc = _wf("manifest.age", b"")
    C.encrypt_file(_wf("manifest.json", json.dumps(m, ensure_ascii=False).encode()), enc, PUB)
    return open(enc, "rb").read()


def make_chunk_plain(name: str, csv_bytes: bytes):
    """Пилотный plain-режим: CSV → zstd, без age. sha256_enc — отпечаток zst."""
    z = subprocess.run([ZSTD, "-q", "-3", "-c"], input=csv_bytes,
                       capture_output=True, check=True).stdout
    entry = {"name": name, "entity": "Catalog_Контрагенты", "rows": 2,
             "bytes_plain": len(csv_bytes), "bytes_enc": len(z),
             "sha256_plain": sha256(csv_bytes), "sha256_enc": sha256(z)}
    return entry, z


def plain_manifest(m: dict) -> bytes:
    return json.dumps(m, ensure_ascii=False).encode()


def manifest(pkg_id: str, seq: int, entries: list, version: int = 1) -> dict:
    return {"manifest_version": version, "package_id": f"ut/{pkg_id}",
            "base_id": "ut", "seq": seq, "kind": "delta",
            "created_utc": "2026-08-06T10:00:00Z", "agent_version": "proba-1",
            "entities": [], "chunks": entries}


PORT = 0


def req(method: str, path: str, body=None, token=TOKEN, cn=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if cn is not None:
        headers["X-SSL-Client-CN"] = cn
    conn.request(method, path, body=body, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    try:
        return r.status, json.loads(data) if data else {}
    except ValueError:
        return r.status, {"_raw": data[:200].decode("utf-8", "replace")}


def pkg_dir(pkg_id: str) -> str:
    return os.path.join(ROOT, "inbox", "ut", pkg_id)


def main() -> int:
    global PORT
    if not ZSTD:
        print("FAIL  zstd не найден в системе")
        return 1
    if not S.init():
        print("FAIL  init() не принял файл баз")
        return 1
    srv = S.Server(("127.0.0.1", 0), S.Handler)
    PORT = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    csv1 = "Ref_Key,Name\r\nk1,Ромашка\r\n".encode()
    csv2 = "Ref_Key,Name\r\nk2,Одуванчик\r\n".encode()

    # 1. полный цикл: manifest → chunk-00001 → status → chunk-00002 → verified
    e1, b1 = make_chunk("chunk-00001", csv1)
    e2, b2 = make_chunk("chunk-00002", csv2)
    pkg_a = "000041-aaaaaaaa"
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/manifest",
                enc_manifest(manifest(pkg_a, 41, [e1, e2])))
    check("1: manifest принят", st == 200 and r.get("state") == "receiving", f"{st} {r}")
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/chunk/chunk-00001", b1)
    check("1: chunk-00001 принят", st == 200, f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status")
    check("1: status после 1 чанка: receiving, missing=[chunk-00002]",
          st == 200 and r.get("state") == "receiving"
          and r.get("received") == ["chunk-00001"] and r.get("missing") == ["chunk-00002"],
          f"{st} {r}")
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/chunk/chunk-00002", b2)
    check("1: chunk-00002 принят", st == 200, f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status")
    check("1: пакет собран — verified", st == 200 and r.get("state") == "verified"
          and r.get("missing") == [] and r.get("error") is None, f"{st} {r}")
    # повторный status идёт по маркеру, без перепроверки: ломаем zstd — ответ тот же
    real_zstd = S.ZSTD_BIN
    S.ZSTD_BIN = "/nonexistent/zstd"
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status")
    S.ZSTD_BIN = real_zstd
    check("1: повторный status без перепроверки", st == 200 and r.get("state") == "verified",
          f"{st} {r}")
    stj = json.load(open(os.path.join(pkg_dir(pkg_a), "state.json"), encoding="utf-8"))
    check("1: маркер state.json пакета = verified", stj.get("state") == "verified", str(stj))

    # 2. идемпотентность чанка: повтор — no-op 200; другое содержимое — 409
    eb, bb = make_chunk("chunk-00001", csv1)
    pkg_b = "000042-bbbbbbbb"
    req("PUT", f"/v1/package/ut/{pkg_b}/manifest", enc_manifest(manifest(pkg_b, 42, [eb])))
    req("PUT", f"/v1/package/ut/{pkg_b}/chunk/chunk-00001", bb)
    st, r = req("PUT", f"/v1/package/ut/{pkg_b}/chunk/chunk-00001", bb)
    check("2: повторный PUT чанка — no-op 200", st == 200 and r.get("noop") is True, f"{st} {r}")
    _e, other = make_chunk("chunk-00001", "Ref_Key,Name\r\nk9,Подмена\r\n".encode())
    st, r = req("PUT", f"/v1/package/ut/{pkg_b}/chunk/chunk-00001", other)
    check("2: другое содержимое под тем же именем — 409",
          st == 409 and r.get("error") == "chunk_hash_mismatch", f"{st} {r}")

    # 3. manifest_version=99 → rejected version_unsupported
    pkg_c = "000043-cccccccc"
    st, r = req("PUT", f"/v1/package/ut/{pkg_c}/manifest",
                enc_manifest(manifest(pkg_c, 43, [e1], version=99)))
    check("3: версия 99 — 409 version_unsupported",
          st == 409 and str(r.get("error", "")).startswith("version_unsupported"), f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_c}/status")
    check("3: status показывает rejected",
          st == 200 and r.get("state") == "rejected"
          and "version_unsupported" in str(r.get("error")), f"{st} {r}")

    # 4. seq <= last_applied → rejected stale_seq (state.json базы правим руками)
    bs_path = os.path.join(ROOT, "inbox", "ut", "state.json")
    bs = json.load(open(bs_path, encoding="utf-8"))
    bs["last_applied_seq"] = 100
    json.dump(bs, open(bs_path, "w", encoding="utf-8"), ensure_ascii=False)
    pkg_e = "000045-eeeeeeee"
    st, r = req("PUT", f"/v1/package/ut/{pkg_e}/manifest",
                enc_manifest(manifest(pkg_e, 5, [e1])))
    check("4: seq 5 при last_applied 100 — 409 stale_seq",
          st == 409 and r.get("error") == "stale_seq", f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_e}/status")
    check("4: status показывает rejected/stale_seq",
          r.get("state") == "rejected" and r.get("error") == "stale_seq", f"{st} {r}")
    bs["last_applied_seq"] = 0
    json.dump(bs, open(bs_path, "w", encoding="utf-8"), ensure_ascii=False)

    # 5. авторизация: неверный/отсутствующий токен — 401 везде, /health — без него
    for method, path, body in (
        ("PUT", f"/v1/package/ut/{pkg_a}/manifest", b"x"),
        ("PUT", f"/v1/package/ut/{pkg_a}/chunk/chunk-00001", b"x"),
        ("GET", f"/v1/package/ut/{pkg_a}/status", None),
        ("GET", "/v1/agent/config?base_id=ut&config_version=3&agent_version=p", None),
    ):
        st, r = req(method, path, body, token="wrong")
        check(f"5: чужой токен {method} {path.split('/')[4] if '/package/' in path else 'config'} — 401",
              st == 401 and r.get("error") == "unauthorized", f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status", token=None)
    check("5: без токена — 401", st == 401, f"{st} {r}")
    st, r = req("GET", "/health", token=None)
    check("5: /health без авторизации", st == 200 and r.get("status") == "packet-server-ok",
          f"{st} {r}")
    st, r = req("GET", "/v1/nope")
    check("5: чужой путь — 404", st == 404, f"{st} {r}")
    # 5а. mTLS-фактор: CN от релея, чужой базе — 401 даже с верным токеном
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status", cn="other")
    check("5а: чужой CN — 401 при верном токене", st == 401, f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status", cn="ut")
    check("5а: CN базы — пропускает", st == 200, f"{st} {r}")

    # 6. чанк подменён на диске после заливки → status → quarantined
    ed, bd = make_chunk("chunk-00001", csv1)
    pkg_d = "000044-dddddddd"
    req("PUT", f"/v1/package/ut/{pkg_d}/manifest", enc_manifest(manifest(pkg_d, 44, [ed])))
    req("PUT", f"/v1/package/ut/{pkg_d}/chunk/chunk-00001", bd)
    victim = os.path.join(pkg_dir(pkg_d), "chunk-00001.csv.zst.age")
    raw = bytearray(open(victim, "rb").read())
    raw[-100] ^= 0xFF
    open(victim, "wb").write(raw)
    st, r = req("GET", f"/v1/package/ut/{pkg_d}/status")
    check("6: подмена чанка на диске — quarantined",
          st == 200 and r.get("state") == "quarantined"
          and str(r.get("error", "")).startswith("verify_"), f"{st} {r}")

    # 7. имя чанка с path traversal — 400
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/chunk/..", b"x")
    check("7: имя «..» — 400", st == 400 and r.get("error") == "bad_chunk_name", f"{st} {r}")
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/chunk/%2e%2e", b"x")
    check("7: имя «%2e%2e» — 400", st == 400, f"{st} {r}")

    # 8. чанк вне манифеста — 409
    _e8, b8 = make_chunk("chunk-00099", csv1)
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/chunk/chunk-00099", b8)
    check("8: незаявленный чанк — 409",
          st == 409 and r.get("error") == "chunk_not_declared", f"{st} {r}")

    # 9. config: версия равна — короткий ответ; старее — полный с recipient_pubkey
    st, r = req("GET", "/v1/agent/config?base_id=ut&config_version=3&agent_version=p")
    check("9: config_version равен — короткий ответ",
          st == 200 and r == {"config_version": 3}, f"{st} {r}")
    st, r = req("GET", "/v1/agent/config?base_id=ut&config_version=1&agent_version=p")
    check("9: config_version старее — полный конфиг с recipient",
          st == 200 and r.get("config_version") == 3
          and r.get("recipient_pubkey") == PUB
          and r.get("entities") == ["Catalog_Контрагенты", "Document_Реализация"],
          f"{st} {r}")

    # 10. Content-Length сверх лимита — 413 до чтения тела
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    conn.putrequest("PUT", f"/v1/package/ut/{pkg_a}/chunk/chunk-00001")
    conn.putheader("Authorization", f"Bearer {TOKEN}")
    conn.putheader("Content-Length", str(S.PACKET_MAX_CHUNK_BYTES + 1))
    conn.endheaders(b"x")
    resp = conn.getresponse()
    st10, body10 = resp.status, resp.read()
    conn.close()
    check("10: Content-Length > 64 МБ — 413", st10 == 413
          and b"body_too_large" in body10, f"{st10} {body10[:120]}")

    # 11. превышение лимита пакетов в приёме — 429
    real_lim = S.PACKET_MAX_ACTIVE_PACKAGES
    S.PACKET_MAX_ACTIVE_PACKAGES = 2  # pkg_a verified + pkg_b receiving уже заняли оба
    pkg_f = "000046-ffffffff"
    st, r = req("PUT", f"/v1/package/ut/{pkg_f}/manifest",
                enc_manifest(manifest(pkg_f, 46, [e1])))
    S.PACKET_MAX_ACTIVE_PACKAGES = real_lim
    check("11: лимит пакетов в приёме — 429",
          st == 429 and r.get("error") == "limit_active_packages", f"{st} {r}")

    # 12. повтор манифеста после verified — no-op, состояние не сбрасывается
    st, r = req("PUT", f"/v1/package/ut/{pkg_a}/manifest",
                enc_manifest(manifest(pkg_a, 41, [e1, e2])))
    check("12: повтор манифеста — no-op 200", st == 200 and r.get("noop") is True, f"{st} {r}")
    st, r = req("GET", f"/v1/package/ut/{pkg_a}/status")
    check("12: состояние после повтора — verified", r.get("state") == "verified", f"{st} {r}")

    # 13. plain-режим пилота (без age): тот же цикл, режим — по магии файлов
    pe1, pb1 = make_chunk_plain("chunk-00001", csv1)
    pkg_p = "000051-aabbccdd"
    st, r = req("PUT", f"/v1/package/ut/{pkg_p}/manifest",
                plain_manifest(manifest(pkg_p, 51, [pe1])))
    check("13: plain manifest принят", st == 200 and r.get("state") == "receiving", f"{st} {r}")
    check("13: в plain-режиме manifest.json.age не создаётся",
          not os.path.exists(os.path.join(pkg_dir(pkg_p), "manifest.json.age"))
          and os.path.exists(os.path.join(pkg_dir(pkg_p), "manifest.json")))
    st, r = req("PUT", f"/v1/package/ut/{pkg_p}/chunk/chunk-00001", pb1)
    check("13: plain чанк принят", st == 200, f"{st} {r}")
    check("13: чанк хранится как .csv.zst",
          os.path.exists(os.path.join(pkg_dir(pkg_p), "chunk-00001.csv.zst")))
    st, r = req("GET", f"/v1/package/ut/{pkg_p}/status")
    check("13: plain пакет собран — verified",
          st == 200 and r.get("state") == "verified" and r.get("missing") == []
          and r.get("error") is None, f"{st} {r}")
    # подмена байта в plain-чанке на диске → quarantined (verify по магии)
    pkg_q = "000052-aabbccdd"
    pe2, pb2 = make_chunk_plain("chunk-00001", csv1)
    req("PUT", f"/v1/package/ut/{pkg_q}/manifest", plain_manifest(manifest(pkg_q, 52, [pe2])))
    req("PUT", f"/v1/package/ut/{pkg_q}/chunk/chunk-00001", pb2)
    victim = os.path.join(pkg_dir(pkg_q), "chunk-00001.csv.zst")
    raw = bytearray(open(victim, "rb").read())
    raw[-1] ^= 0xFF
    open(victim, "wb").write(raw)
    st, r = req("GET", f"/v1/package/ut/{pkg_q}/status")
    check("13: подмена plain-чанка на диске — quarantined",
          st == 200 and r.get("state") == "quarantined"
          and str(r.get("error", "")).startswith("verify_"), f"{st} {r}")
    # магия-мусор → 409 bad_format
    pkg_b = "000053-aabbccdd"
    st, r = req("PUT", f"/v1/package/ut/{pkg_b}/manifest", b"\x00\x01binary-garbage")
    check("13: манифест-мусор — 409 bad_format",
          st == 409 and r.get("error") == "bad_format", f"{st} {r}")
    pe3, _pb3 = make_chunk_plain("chunk-00001", csv1)
    req("PUT", f"/v1/package/ut/{pkg_b}/manifest", plain_manifest(manifest(pkg_b, 53, [pe3])))
    st, r = req("PUT", f"/v1/package/ut/{pkg_b}/chunk/chunk-00001", b"garbage-chunk")
    check("13: чанк-мусор — 409 bad_format",
          st == 409 and r.get("error") == "bad_format", f"{st} {r}")

    # 14. база, добавленная в файл ПОСЛЕ старта приёмника, обязана приниматься
    # сразу (перечитывание по mtime в _auth_base), а не после /agent/config —
    # живой случай 10.08: слот на юните получал 401 «токен отклонён» при верном
    # токене, потому что перечитывание звучало только на пути конфига.
    with open(BASES_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    doc["buh2"] = {"token": "tok-buh2-proba", "identity": IDENTITY, "config": {
        "config_version": 1, "entities": [],
        "params": {"page_size": 10000, "tact_seconds": 1200, "chunk_mb": 32}}}
    tmp = BASES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp, BASES_PATH)
    mt = os.path.getmtime(BASES_PATH)  # mtime обязан уехать вперёд даже на
    os.utime(BASES_PATH, (mt + 2, mt + 2))  # грубой ФС (секундная точность)
    m_b = {"manifest_version": 1, "package_id": "buh2/000061-bbbb2222",
           "base_id": "buh2", "seq": 61, "kind": "delta",
           "created_utc": "2026-08-10T07:00:00Z", "agent_version": "proba-1",
           "entities": [], "chunks": []}
    st, r = req("PUT", "/v1/package/buh2/000061-bbbb2222/manifest",
                enc_manifest(m_b), token="tok-buh2-proba")
    check("14: новая база без рестарта — manifest принят (не 401)",
          st == 200 and r.get("state") == "receiving", f"{st} {r}")
    st, r = req("PUT", "/v1/package/buh2/000062-bbbb2222/manifest",
                enc_manifest({**m_b, "package_id": "buh2/000062-bbbb2222", "seq": 62}),
                token="tok-ut-proba")
    check("14: чужой токен для новой базы — 401", st == 401, f"{st} {r}")

    # 15. обрыв keep-alive клиентом после успешного ответа — не ошибка приёмника:
    # одна строка в журнале, без разбора стека. Живой случай 12.08 на okna:
    # HAProxy релея закрывает соединение с RST, и на каждый успешный запрос
    # агента шло по 20 строк traceback-а ConnectionResetError — настоящие
    # ошибки в таком журнале не видны (CHANGELOG 12.08).
    cap = io.StringIO()
    real_err, sys.stderr = sys.stderr, cap
    try:
        s = socket.create_connection(("127.0.0.1", PORT), 5)
        s.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\nConnection: keep-alive\r\n\r\n")
        head = s.recv(4096)
        # RST вместо FIN — так рвёт соединение релей
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        s.close()
        for _ in range(100):  # ждём, пока поток обработчика упрётся в обрыв
            if "закрыто клиентом" in cap.getvalue() or "Traceback" in cap.getvalue():
                break
            time.sleep(0.05)
    finally:
        sys.stderr = real_err
    log = cap.getvalue()
    check("15: ответ до обрыва доставлен", head.split(b"\r\n", 1)[0].endswith(b"200 OK"),
          head[:40])
    check("15: обрыв соединения — без разбора стека", "Traceback" not in log, log[:400])
    check("15: обрыв соединения — одна понятная строка",
          log.count("соединение закрыто клиентом") == 1, log[:400])

    # 16. отчёт хода такта (POST /v1/agent/progress) — необязательная ручка
    # диагностики: пишет progress.json и НЕ трогает ни seq, ни состояний пакетов
    # (заведена 12.08 — до неё первый полный проход шёл часами вслепую).
    seq_before = json.load(open(os.path.join(ROOT, "inbox", "ut", "state.json"),
                                encoding="utf-8"))["last_applied_seq"]
    prog = json.dumps({"phase": "read", "entity": "Catalog_Контрагенты", "i": 7,
                       "n": 819, "rows_entity": 1200, "rows_total": 5000,
                       "elapsed_sec": 42, "kind": "full", "seq": 3,
                       "agent_version": "проба-1"}).encode()
    st, r = req("POST", "/v1/agent/progress?base_id=ut", prog)
    check("16: отчёт принят", st == 200 and r.get("ok") is True, f"{st} {r}")
    pj = os.path.join(ROOT, "inbox", "ut", "progress.json")
    saved = json.load(open(pj, encoding="utf-8")) if os.path.exists(pj) else {}
    check("16: progress.json записан с отметкой времени",
          saved.get("entity") == "Catalog_Контрагенты" and saved.get("i") == 7
          and "received_utc" in saved, saved)
    st, r = req("POST", "/v1/agent/progress?base_id=ut", prog, token="tok-chuzhoy")
    check("16: чужой токен — 401", st == 401, f"{st} {r}")
    st, r = req("POST", "/v1/agent/progress?base_id=ut", "не json".encode("utf-8"))
    check("16: мусор вместо JSON — 400 bad_json",
          st == 400 and r.get("error") == "bad_json", f"{st} {r}")
    st, r = req("POST", "/v1/agent/progress?base_id=ut", b"x" * 20000)
    check("16: перебор размера — 413", st == 413, f"{st} {r}")
    st, r = req("POST", "/v1/package/ut/000041-aaaaaaaa/manifest", prog)
    check("16: POST не открывает чужие пути — 404", st == 404, f"{st} {r}")
    seq_after = json.load(open(os.path.join(ROOT, "inbox", "ut", "state.json"),
                               encoding="utf-8"))["last_applied_seq"]
    check("16: состояние пакетов не тронуто", seq_before == seq_after,
          f"{seq_before} -> {seq_after}")
    # Свежий отчёт затирает прежний (последний важнее истории).
    st, _ = req("POST", "/v1/agent/progress?base_id=ut",
                json.dumps({"phase": "done"}).encode())
    saved2 = json.load(open(pj, encoding="utf-8"))
    check("16: свежий отчёт заменяет прежний",
          st == 200 and saved2.get("phase") == "done" and "entity" not in saved2, saved2)

    # 17. число чанков в пакете не ограничено НАШИМ числом (13.08). Оно задаётся
    # чужой схемой: не меньше чанка на непустую сущность. Прежний предел 4096 у
    # ERP-контура (9151 сущность) отверг бы манифест и обнулил сутки чтения 1С.
    wide = [dict(make_chunk("chunk-%05d" % i, b"x")[0]) for i in range(1, 4098)]
    m_wide = {"manifest_version": 1, "package_id": "ut/000071-wide0001",
              "base_id": "ut", "seq": 71, "kind": "full",
              "created_utc": "2026-08-13T05:00:00Z", "agent_version": "проба-1",
              "entities": [], "chunks": wide}
    st, r = req("PUT", "/v1/package/ut/000071-wide0001/manifest", enc_manifest(m_wide))
    check("17: 4097 чанков принято — предела по числу нет",
          st == 200 and r.get("state") == "receiving", f"{st} {r}")
    # Предел остаётся доступным: положительное значение в env включает его.
    real_limit = S.PACKET_MAX_CHUNKS_PER_PACKAGE
    S.PACKET_MAX_CHUNKS_PER_PACKAGE = 10
    st, r = req("PUT", "/v1/package/ut/000072-wide0002/manifest",
                enc_manifest({**m_wide, "package_id": "ut/000072-wide0002", "seq": 72}))
    S.PACKET_MAX_CHUNKS_PER_PACKAGE = real_limit
    check("17: заданный предел по-прежнему отвергает",
          st == 409 and r.get("error") == "limit_chunks_per_package", f"{st} {r}")

    srv.shutdown()
    print(f"\n{'ПРОБА ЗЕЛЁНАЯ' if not FAILS else 'ПАДЕНИЯ: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
