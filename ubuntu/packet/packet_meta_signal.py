#!/usr/bin/env python3
"""Сигнал «приёмнику нужен снимок $metadata» ↔ агент Windows.

Контракт: docs/PACKET_CONTRACT.md §8 params.need_metadata, §9 apply.
Дефект Д5: агент шлёт metadata только при first/resync или смене отпечатка
(state.json). Если файл <PACKET_META_DIR>/<base>/$metadata на Ubuntu пропал,
а отпечаток у агента уже совпал — снимок больше не приедет (74× delta с
metadata.included=false). Обратный канал: Ubuntu ставит params.need_metadata=1
и поднимает config_version; агент ≥1.1.3 шлёт kind=meta. После apply снимок
пишется — флаг снимается.

Только stdlib. Журнал — stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

PACKET_BASES = os.environ.get("PACKET_BASES", "/etc/1c-packet-bases.json")
PACKET_META_DIR = os.environ.get("PACKET_META_DIR", "/var/lib/serenedb/packet-meta")

# Имя параметра в /agent/config → params (контракт §8). Агент читает как Long≠0.
NEED_META_KEY = "need_metadata"


def _log(msg: str) -> None:
    sys.stderr.write("meta-signal: %s\n" % msg)


def snap_path(base_id: str) -> str:
    return os.path.join(PACKET_META_DIR, base_id, "$metadata")


def snap_present(base_id: str) -> bool:
    """Файл снимка есть и непустой."""
    p = snap_path(base_id)
    try:
        return os.path.isfile(p) and os.path.getsize(p) > 0
    except OSError:
        return False


def _load_bases(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("PACKET_BASES: корень не объект")
    return data


def _write_bases_atomic(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".bases-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _need_flag(params: dict) -> bool:
    v = params.get(NEED_META_KEY)
    if v is True:
        return True
    if isinstance(v, (int, float)) and int(v) != 0:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return True
    return False


def request_metadata(base_id: str, bases_path: str = PACKET_BASES) -> int:
    """Выставить need_metadata=1 и поднять config_version, если ещё не стоит.

    0 — флаг уже был / выставлен; 1 — базы нет; 2 — нет записи файла.
    """
    if snap_present(base_id):
        _log("%s: снимок уже на месте (%s) — сигнал не нужен" % (base_id, snap_path(base_id)))
        return 0
    try:
        data = _load_bases(bases_path)
    except (OSError, ValueError) as e:
        _log("FATAL: не читается %s: %s" % (bases_path, e))
        return 2
    rec = data.get(base_id)
    if not isinstance(rec, dict):
        _log("FATAL: базы %s нет в %s" % (base_id, bases_path))
        return 1
    cfg = rec.get("config") if isinstance(rec.get("config"), dict) else {}
    params = dict(cfg.get("params") or {})
    cur = int(cfg.get("config_version", 0) or 0)
    if _need_flag(params):
        _log("%s: need_metadata уже выставлен, config_version=%d — на следующем "
             "такте агент ≥1.1.3 шлёт kind=meta" % (base_id, cur))
        return 0
    params[NEED_META_KEY] = 1
    new_cfg = dict(cfg)
    new_cfg["params"] = params
    new_cfg["config_version"] = cur + 1
    # entities сохраняем как были — только сигнал о снимке
    if "entities" not in new_cfg and isinstance(cfg.get("entities"), list):
        new_cfg["entities"] = cfg["entities"]
    rec = dict(rec)
    rec["config"] = new_cfg
    data[base_id] = rec
    try:
        _write_bases_atomic(bases_path, data)
    except PermissionError as e:
        _log("FATAL: нет записи в %s: %s" % (bases_path, e))
        return 2
    _log("%s: запрошен снимок $metadata — need_metadata=1, config_version %d → %d "
         "(агент ≥1.1.3 шлёт kind=meta; 1.0.x — нужен --smoke на Windows)"
         % (base_id, cur, cur + 1))
    return 0


def ack_metadata(base_id: str, bases_path: str = PACKET_BASES) -> int:
    """Снять need_metadata после успешной записи снимка. 0 — ок/нечего снимать."""
    try:
        data = _load_bases(bases_path)
    except (OSError, ValueError) as e:
        _log("ack: не читается %s: %s — флаг не снят" % (bases_path, e))
        return 2
    rec = data.get(base_id)
    if not isinstance(rec, dict):
        return 0
    cfg = rec.get("config") if isinstance(rec.get("config"), dict) else {}
    params = dict(cfg.get("params") or {})
    if not _need_flag(params):
        return 0
    params.pop(NEED_META_KEY, None)
    cur = int(cfg.get("config_version", 0) or 0)
    new_cfg = dict(cfg)
    new_cfg["params"] = params
    new_cfg["config_version"] = cur + 1
    rec = dict(rec)
    rec["config"] = new_cfg
    data[base_id] = rec
    try:
        _write_bases_atomic(bases_path, data)
    except PermissionError as e:
        _log("ack: нет записи в %s: %s" % (bases_path, e))
        return 2
    _log("%s: need_metadata снят после записи снимка, config_version %d → %d"
         % (base_id, cur, cur + 1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="сигнал need_metadata для агента")
    ap.add_argument("action", choices=("request", "ack", "status"))
    ap.add_argument("base_id")
    ap.add_argument("--bases", default=PACKET_BASES)
    args = ap.parse_args(argv)
    if args.action == "status":
        present = snap_present(args.base_id)
        _log("%s: snap=%s path=%s" % (args.base_id, "есть" if present else "НЕТ",
                                      snap_path(args.base_id)))
        try:
            data = _load_bases(args.bases)
            cfg = (data.get(args.base_id) or {}).get("config") or {}
            params = cfg.get("params") or {}
            _log("  config_version=%s need_metadata=%s entities=%d"
                 % (cfg.get("config_version"), params.get(NEED_META_KEY),
                    len(cfg.get("entities") or [])))
        except (OSError, ValueError, TypeError) as e:
            _log("  bases: %s" % e)
            return 2
        return 0 if present else 1
    if args.action == "request":
        return request_metadata(args.base_id, args.bases)
    return ack_metadata(args.base_id, args.bases)


if __name__ == "__main__":
    sys.exit(main() or 0)
