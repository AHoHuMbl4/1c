#!/usr/bin/env python3
"""Приёмник пакетов пакетного транспорта Windows → Ubuntu (контракт §8).

Принимает манифест и чанки по HTTP, расшифровывает манифест при приёме,
доводит пакет до состояния verified (age + sha256 + zstd) и хранит маркер
состояния; перевод в applied выполняет отдельный apply-компонент.

Хранение (PACKET_ROOT):
  inbox/<base_id>/state.json                       — last_applied_seq + состояния пакетов
  inbox/<base_id>/<package_id>/manifest.json.age   — манифест как пришёл (age-режим)
  inbox/<base_id>/<package_id>/manifest.json       — разобранный манифест (в plain-режиме
                                                     это и есть файл как пришёл)
  inbox/<base_id>/<package_id>/<name>.csv.zst.age  — чанки как пришли (age-режим)
  inbox/<base_id>/<package_id>/<name>.csv.zst      — чанки как пришли (plain-режим пилота)
  inbox/<base_id>/<package_id>/state.json          — состояние пакета + error

Режим каждого файла определяется магией (age-encryption.org/ или 28 B5 2F FD),
не конфигом: оба режима принимаются одновременно (пилот без age-слоя 06.08).

Конфиг — env: PACKET_ROOT, PACKET_LISTEN, PACKET_BASES (JSON баз:
token/identity/config). Без файла баз — FATAL на старте. Только stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import packet_crypto as C

PACKET_ROOT = os.environ.get("PACKET_ROOT", "/var/lib/1c-packet")
PACKET_LISTEN = os.environ.get("PACKET_LISTEN", "127.0.0.1:6021")
PACKET_BASES = os.environ.get("PACKET_BASES", "/etc/1c-packet-bases.json")
ZSTD_BIN = os.environ.get("PACKET_ZSTD_BIN", "/usr/bin/zstd")

# Лимиты — контракт К8 (docs/PACKET_CONTRACT.md §8). Превышение на создании
# пакета — 429, внутри манифеста — rejected(limit_*).
PACKET_MAX_CHUNK_BYTES = int(os.environ.get("PACKET_MAX_CHUNK_BYTES", str(64 * 1024 * 1024)))
PACKET_MAX_CHUNKS_PER_PACKAGE = int(os.environ.get("PACKET_MAX_CHUNKS_PER_PACKAGE", "4096"))
PACKET_MAX_INBOX_BYTES = int(os.environ.get("PACKET_MAX_INBOX_BYTES", str(20 * 1024 * 1024 * 1024)))
PACKET_MAX_ACTIVE_PACKAGES = int(os.environ.get("PACKET_MAX_ACTIVE_PACKAGES", "8"))
# Версия манифеста, которую понимает этот приёмник (контракт, шапка файла).
PACKET_MANIFEST_VERSION = 1

# Чанки со служебными именами хранятся без вставки «.csv» (контракт §2).
_SERVICE_CHUNKS = ("metadata", "gone", "index")

# Режим файла определяется магией, а не конфигом (пилот без age-слоя, решение
# владельца 06.08: канал шифрован TLS + SSH-туннелем + mTLS). Оба режима
# принимаются одним приёмником одновременно. sha256_enc манифеста — отпечаток
# файла как пришёл: в plain-режиме это отпечаток zst-файла.
_AGE_MAGIC = b"age-encryption.org/"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
_LOCK = threading.Lock()

BASES: dict = {}
_BASES_MTIME: float | None = None


def _load_bases() -> bool:
    """Прочитать файл баз в BASES; False — файл не читается или пуст."""
    global _BASES_MTIME
    try:
        with open(PACKET_BASES, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or not data:
        return False
    BASES.clear()
    BASES.update(data)
    try:
        _BASES_MTIME = os.path.getmtime(PACKET_BASES)
    except OSError:
        _BASES_MTIME = None
    return True


def _reload_bases_if_changed() -> None:
    """Перечитать файл баз, если его mtime изменился с прошлого чтения.

    Зовётся на /agent/config: config-builder (packet_config.py) переписывает
    запись базы атомарно, и без перечитывания агент получал бы заставший конфиг
    до перезапуска приёмника. Побочное следствие, принятое осознанно: токены и
    identity на этом пути тоже становятся свежими без перезапуска. Битый или
    полупустой файл игнорируется — остаётся прежняя версия (fail-stale, а не
    fail-open и не падение работающего приёмника)."""
    if _BASES_MTIME is None:
        return
    try:
        mt = os.path.getmtime(PACKET_BASES)
    except OSError:
        return
    if mt != _BASES_MTIME:
        _load_bases()


def init() -> bool:
    """Загрузить файл баз; False — старт отменён (fail-closed, как odata_gateway)."""
    if not os.path.exists(PACKET_BASES):
        sys.stderr.write(
            f"FATAL: файл баз {PACKET_BASES} не найден — без списка баз приёмник "
            "не может проверить ни один токен. Задайте PACKET_BASES.\n"
        )
        return False
    if not _load_bases():
        sys.stderr.write(f"FATAL: файл баз {PACKET_BASES} не читается или пуст\n")
        return False
    os.makedirs(os.path.join(PACKET_ROOT, "inbox"), exist_ok=True)
    return True


# --- хранилище ---------------------------------------------------------------


def _valid_id(s: str) -> bool:
    # «..» отсекает path traversal; слеши и «%» не проходят regex по построению.
    return bool(s) and ".." not in s and bool(_ID_RE.fullmatch(s))


def _base_dir(base_id: str) -> str:
    return os.path.join(PACKET_ROOT, "inbox", base_id)


def _pkg_dir(base_id: str, pkg_id: str) -> str:
    return os.path.join(_base_dir(base_id), pkg_id)


def _chunk_filenames(name: str) -> tuple[str, str]:
    """Имена хранения чанка: (age-форма, plain-форма) — контракт §2."""
    base = name + (".zst" if name in _SERVICE_CHUNKS else ".csv.zst")
    return base + ".age", base


def _chunk_stored(pkg_dir: str, name: str) -> str | None:
    """Путь принятого чанка в любом из двух режимов, либо None."""
    for fn in _chunk_filenames(name):
        p = os.path.join(pkg_dir, fn)
        if os.path.exists(p):
            return p
    return None


def _sniff(path: str) -> str:
    """Режим файла по магии: 'age' | 'zstd' | 'other'."""
    try:
        with open(path, "rb") as f:
            head = f.read(len(_AGE_MAGIC))
    except OSError:
        return "other"
    if head.startswith(_AGE_MAGIC):
        return "age"
    if head.startswith(_ZSTD_MAGIC):
        return "zstd"
    return "other"


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json_atomic(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _silent_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _base_state(base_id: str) -> dict:
    st = _read_json(os.path.join(_base_dir(base_id), "state.json"), None)
    if not isinstance(st, dict):
        st = {"last_applied_seq": 0, "packages": {}}
    st.setdefault("last_applied_seq", 0)
    st.setdefault("packages", {})
    return st


def _pkg_state(base_id: str, pkg_id: str) -> dict:
    st = _read_json(os.path.join(_pkg_dir(base_id, pkg_id), "state.json"), None)
    if not isinstance(st, dict):
        st = {"state": "receiving", "error": None}
    return st


def _set_pkg_state(base_id: str, pkg_id: str, state: str, error, seq=None) -> dict:
    """Записать состояние пакета в state.json пакета и в сводный state.json базы."""
    with _LOCK:
        pkg_dir = _pkg_dir(base_id, pkg_id)
        os.makedirs(pkg_dir, exist_ok=True)
        st = _pkg_state(base_id, pkg_id)
        st["state"] = state
        st["error"] = error
        if seq is not None:
            st["seq"] = seq
        st["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _write_json_atomic(os.path.join(pkg_dir, "state.json"), st)
        bs = _base_state(base_id)
        bs["packages"][pkg_id] = {"state": state, "error": error}
        _write_json_atomic(os.path.join(_base_dir(base_id), "state.json"), bs)
    return st


def _inbox_bytes(base_id: str) -> int:
    total = 0
    for dp, _dn, fns in os.walk(_base_dir(base_id)):
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return total


# --- проверки манифеста и пакета ---------------------------------------------


def _validate_manifest(m, base_id: str, pkg_id: str):
    """Код ошибки либо None. Чистая функция — состояние не трогает."""
    if not isinstance(m, dict):
        return "manifest_invalid"
    if m.get("manifest_version") != PACKET_MANIFEST_VERSION:
        return f"version_unsupported: max={PACKET_MANIFEST_VERSION}"
    if m.get("base_id") != base_id or m.get("package_id") != f"{base_id}/{pkg_id}":
        return "id_mismatch"
    if not isinstance(m.get("seq"), int):
        return "manifest_invalid"
    chunks = m.get("chunks")
    if not isinstance(chunks, list):
        return "manifest_invalid"
    if len(chunks) > PACKET_MAX_CHUNKS_PER_PACKAGE:
        return "limit_chunks_per_package"
    for e in chunks:
        if not isinstance(e, dict) or not _valid_id(str(e.get("name", ""))):
            return "manifest_invalid"
        for k in ("sha256_enc", "sha256_plain"):
            if not isinstance(e.get(k), str) or len(e[k]) != 64:
                return "manifest_invalid"
        for k in ("bytes_enc", "bytes_plain"):
            if not isinstance(e.get(k), int):
                return "manifest_invalid"
    return None


def _verify_package(handler, base_id: str, pkg_id: str, manifest: dict) -> dict:
    """Полная проверка пакета: sha256 шифртекста → age → zstd → sha256 открытого."""
    pkg_dir = _pkg_dir(base_id, pkg_id)
    identity = BASES[base_id].get("identity", "")

    def fail(code: str, name: str) -> dict:
        handler.log_message("QUARANTINE base=%s pkg=%s chunk=%s code=%s",
                            base_id, pkg_id, name, code)
        return _set_pkg_state(base_id, pkg_id, "quarantined", code)

    kinds = set()
    for e in manifest["chunks"]:
        name = e["name"]
        enc = _chunk_stored(pkg_dir, name)
        if enc is None or C.sha256_file(enc) != e["sha256_enc"]:
            return fail("verify_hash_mismatch", name)
        kind = _sniff(enc)
        if kind not in ("age", "zstd"):
            return fail("bad_format", name)
        kinds.add(kind)
        fd, dec = tempfile.mkstemp(dir=pkg_dir, prefix=".verify-")
        os.close(fd)
        fd, plain = tempfile.mkstemp(dir=pkg_dir, prefix=".verify-")
        os.close(fd)
        try:
            src = enc                            # plain-режим: файл уже zst
            if kind == "age":
                try:
                    C.decrypt_file(enc, dec, identity)
                except C.PacketCryptoError:
                    return fail("verify_decrypt_failed", name)
                src = dec
            with open(plain, "wb") as out:
                p = subprocess.run([ZSTD_BIN, "-d", "-q", "-c", src],
                                   stdout=out, stderr=subprocess.PIPE)
            if p.returncode != 0:
                return fail("verify_zstd_failed", name)
            if (C.sha256_file(plain) != e["sha256_plain"]
                    or os.path.getsize(plain) != e["bytes_plain"]):
                return fail("verify_plain_mismatch", name)
        finally:
            _silent_unlink(dec)
            _silent_unlink(plain)
    handler.log_message("VERIFIED base=%s pkg=%s chunks=%d mode=%s",
                        base_id, pkg_id, len(manifest["chunks"]),
                        "+".join(sorted(kinds)))
    return _set_pkg_state(base_id, pkg_id, "verified", None)


# --- HTTP ---------------------------------------------------------------------


class Server(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("pkt %s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, status: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, status: int, code: str) -> None:
        self.log_message("%s %s -> %d %s", self.command, self.path, status, code)
        self._json(status, {"error": code})

    def _err_early(self, status: int, code: str) -> None:
        # Отказ до чтения тела: соединение закрывается, иначе непрочитанное тело
        # попадёт в разбор keep-alive потока как «новый запрос».
        self.close_connection = True
        self._err(status, code)

    def _segments(self) -> list[str]:
        path = urllib.parse.urlsplit(self.path).path
        return [urllib.parse.unquote(s) for s in path.split("/") if s != ""]

    def _auth_base(self, base_id: str) -> bool:
        # Fail-closed: неизвестная база и пустой токен в записи — отказ.
        rec = BASES.get(base_id)
        if not rec:
            return False
        token = rec.get("token") or ""
        if not token:
            return False
        # mTLS-фактор (контракт §8): релей проставляет CN клиентского сертификата
        # заголовком; если заголовок приехал — он обязан совпасть с базой пути.
        cn = self.headers.get("X-SSL-Client-CN", "")
        if cn and cn != base_id:
            return False
        return self.headers.get("Authorization", "") == f"Bearer {token}"

    def _read_body(self, limit: int):
        """Тело запроса либо None (ответ об ошибке уже отправлен)."""
        cl = self.headers.get("Content-Length")
        if cl is None:
            self._err(411, "content_length_required")
            return None
        try:
            n = int(cl)
        except ValueError:
            self._err(400, "bad_content_length")
            return None
        if n < 0 or n > limit:
            # Тело не читаем: соединение закрывается, чтобы не разъехался
            # разбор keep-alive потока.
            self.close_connection = True
            self._err(413, "body_too_large")
            return None
        parts, left = [], n
        while left > 0:
            b = self.rfile.read(min(left, 1 << 20))
            if not b:
                break
            parts.append(b)
            left -= len(b)
        return b"".join(parts)

    # -- PUT --

    def do_PUT(self):
        segs = self._segments()
        if segs[:2] == ["v1", "package"] and len(segs) == 5 and segs[4] == "manifest":
            base_id, pkg_id = segs[2], segs[3]
            if not (_valid_id(base_id) and _valid_id(pkg_id)):
                return self._err_early(400, "invalid_id")
            if not self._auth_base(base_id):
                return self._err_early(401, "unauthorized")
            return self._put_manifest(base_id, pkg_id)
        if segs[:2] == ["v1", "package"] and len(segs) == 6 and segs[4] == "chunk":
            base_id, pkg_id, name = segs[2], segs[3], segs[5]
            if not (_valid_id(base_id) and _valid_id(pkg_id)):
                return self._err_early(400, "invalid_id")
            if not _valid_id(name):
                return self._err_early(400, "bad_chunk_name")
            if not self._auth_base(base_id):
                return self._err_early(401, "unauthorized")
            return self._put_chunk(base_id, pkg_id, name)
        return self._err_early(404, "not_found")

    def _put_manifest(self, base_id: str, pkg_id: str):
        # Лимит тела манифеста — тот же, что у чанка: отдельной константы
        # контракт не задаёт, а 64 МБ покрывает 4096 записей чанков с запасом.
        body = self._read_body(PACKET_MAX_CHUNK_BYTES)
        if body is None:
            return
        pkg_dir = _pkg_dir(base_id, pkg_id)
        manifest_path = os.path.join(pkg_dir, "manifest.json")
        st = _pkg_state(base_id, pkg_id)
        # Идемпотентность (контракт §8): повтор манифеста — no-op.
        if os.path.exists(manifest_path) and st["state"] in ("receiving", "verified", "applied"):
            return self._json(200, {"state": st["state"], "noop": True})
        if st["state"] in ("rejected", "quarantined"):
            return self._err(409, st.get("error") or st["state"])
        if not os.path.isdir(pkg_dir):
            bs = _base_state(base_id)
            active = sum(1 for p in bs["packages"].values()
                         if p.get("state") in ("receiving", "verified"))
            if active >= PACKET_MAX_ACTIVE_PACKAGES:
                return self._err(429, "limit_active_packages")
            if _inbox_bytes(base_id) >= PACKET_MAX_INBOX_BYTES:
                return self._err(429, "limit_inbox_bytes")
        os.makedirs(pkg_dir, exist_ok=True)
        json_tmp = os.path.join(pkg_dir, ".manifest.json.tmp")
        age_tmp = None
        if body.startswith(_AGE_MAGIC):
            mode = "age"
            age_tmp = os.path.join(pkg_dir, ".manifest.age.tmp")
            with open(age_tmp, "wb") as f:
                f.write(body)
            identity = BASES[base_id].get("identity", "")
            try:
                C.decrypt_file(age_tmp, json_tmp, identity)
            except C.PacketCryptoError:
                _silent_unlink(age_tmp)
                _silent_unlink(json_tmp)
                _set_pkg_state(base_id, pkg_id, "rejected", "manifest_decrypt_failed")
                return self._err(409, "manifest_decrypt_failed")
        elif body.lstrip()[:1] == b"{":
            # plain-режим пилота: манифест — открытый JSON, хранится как есть.
            mode = "plain"
            with open(json_tmp, "wb") as f:
                f.write(body)
        else:
            return self._err(409, "bad_format")
        m = _read_json(json_tmp, None)
        err = _validate_manifest(m, base_id, pkg_id)
        if err is None and m["seq"] <= _base_state(base_id)["last_applied_seq"]:
            err = "stale_seq"
        if err is not None:
            _silent_unlink(age_tmp or json_tmp)
            _silent_unlink(json_tmp)
            _set_pkg_state(base_id, pkg_id, "rejected", err)
            return self._err(409, err)
        if age_tmp is not None:
            os.replace(age_tmp, os.path.join(pkg_dir, "manifest.json.age"))
        os.replace(json_tmp, manifest_path)
        _set_pkg_state(base_id, pkg_id, "receiving", None, seq=m["seq"])
        self.log_message("manifest принят base=%s pkg=%s seq=%d chunks=%d mode=%s",
                         base_id, pkg_id, m["seq"], len(m["chunks"]), mode)
        return self._json(200, {"state": "receiving", "seq": m["seq"]})

    def _put_chunk(self, base_id: str, pkg_id: str, name: str):
        body = self._read_body(PACKET_MAX_CHUNK_BYTES)
        if body is None:
            return
        pkg_dir = _pkg_dir(base_id, pkg_id)
        st = _pkg_state(base_id, pkg_id)
        if st["state"] in ("rejected", "quarantined"):
            return self._err(409, st.get("error") or st["state"])
        manifest = _read_json(os.path.join(pkg_dir, "manifest.json"), None)
        if not isinstance(manifest, dict):
            return self._err(409, "manifest_missing")
        entries = {e["name"]: e for e in manifest["chunks"]}
        e = entries.get(name)
        if e is None:
            return self._err(409, "chunk_not_declared")
        if body.startswith(_AGE_MAGIC):
            fn = _chunk_filenames(name)[0]
        elif body.startswith(_ZSTD_MAGIC):
            fn = _chunk_filenames(name)[1]
        else:
            return self._err(409, "bad_format")
        sha = hashlib.sha256(body).hexdigest()
        if sha != e["sha256_enc"] or len(body) != e["bytes_enc"]:
            return self._err(409, "chunk_hash_mismatch")
        dest = os.path.join(pkg_dir, fn)
        if os.path.exists(dest) and C.sha256_file(dest) == sha:
            return self._json(200, {"state": st["state"], "chunk": name, "noop": True})
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, dest)
        self.log_message("chunk принят base=%s pkg=%s chunk=%s bytes=%d mode=%s",
                         base_id, pkg_id, name, len(body),
                         "age" if fn.endswith(".age") else "plain")
        return self._json(200, {"state": st["state"], "chunk": name})

    # -- GET --

    def do_GET(self):
        segs = self._segments()
        if segs == ["health"]:
            return self._json(200, {"status": "packet-server-ok"})
        if segs[:2] == ["v1", "package"] and len(segs) == 5 and segs[4] == "status":
            base_id, pkg_id = segs[2], segs[3]
            if not (_valid_id(base_id) and _valid_id(pkg_id)):
                return self._err(400, "invalid_id")
            if not self._auth_base(base_id):
                return self._err(401, "unauthorized")
            return self._get_status(base_id, pkg_id)
        if segs == ["v1", "agent", "config"]:
            # Конфиг отдаём по свежей записи базы (перечитывание по mtime —
            # см. _reload_bases_if_changed); токены при этом тоже свежие.
            _reload_bases_if_changed()
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            base_id = qs.get("base_id", [""])[0]
            if not _valid_id(base_id):
                return self._err(400, "invalid_id")
            if not self._auth_base(base_id):
                return self._err(401, "unauthorized")
            return self._get_config(base_id, qs)
        return self._err(404, "not_found")

    def _get_status(self, base_id: str, pkg_id: str):
        pkg_dir = _pkg_dir(base_id, pkg_id)
        bs = _base_state(base_id)
        if not os.path.isdir(pkg_dir) and pkg_id not in bs["packages"]:
            return self._err(404, "no_such_package")
        st = _pkg_state(base_id, pkg_id)
        manifest = _read_json(os.path.join(pkg_dir, "manifest.json"), None)
        received, missing = [], []
        if isinstance(manifest, dict):
            for e in manifest["chunks"]:
                (received if _chunk_stored(pkg_dir, e["name"]) else missing).append(e["name"])
        # Проверка — синхронно в запросе status: пакеты мелкие, отдельный
        # фоновый воркер на этом шаге не заводится. verified — маркер, повторная
        # проверка по нему не гоняется.
        if st["state"] == "receiving" and isinstance(manifest, dict) and not missing:
            st = _verify_package(self, base_id, pkg_id, manifest)
        return self._json(200, {"state": st["state"], "received": received,
                                "missing": missing, "error": st.get("error")})

    def _get_config(self, base_id: str, qs: dict):
        cfg = BASES[base_id].get("config") or {}
        cur = cfg.get("config_version", 0)
        try:
            client_ver = int(qs.get("config_version", [""])[0])
        except ValueError:
            client_ver = None
        self.log_message("agent config base=%s client_ver=%s cur=%s agent=%s",
                         base_id, client_ver, cur, qs.get("agent_version", ["?"])[0])
        if client_ver == cur:
            return self._json(200, {"config_version": cur})
        resp = dict(cfg)
        resp["config_version"] = cur
        try:
            resp["recipient_pubkey"] = C.recipient_of(BASES[base_id].get("identity", ""))
        except C.PacketCryptoError as e:
            return self._err(500, f"recipient_unavailable: {e}")
        return self._json(200, resp)


def main() -> int:
    if not init():
        return 2
    host, sep, port = PACKET_LISTEN.rpartition(":")
    if not sep:
        host, port = "127.0.0.1", PACKET_LISTEN
    srv = Server((host, int(port)), Handler)
    sys.stderr.write(
        f"packet-server на http://{host}:{port} корень={PACKET_ROOT} баз={len(BASES)}\n"
    )
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
