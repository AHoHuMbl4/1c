#!/usr/bin/env python3
"""Один вызов модели через `openclaw infer model run` без tool surface.

Умолчание — `--local` (доки установленной сборки `cli/infer.md` Behavior:
stateless `model run` defaults to local; gateway не нужен). 🔴 [замер 24.08]
`--gateway` режет RPC-потолком 120000 ms (`GatewayTransportError`); на пачке
wiki-alias 20 сущностей / vLLM Qwen3.8-27B: gw 619 с exit 1, loc 1034 с exit 0.
Потолок в схеме/конфиге не поднимается (`timeoutMs: 12e4` литерал в CLI).
`ALIAS_INFER_TRANSPORT=gateway` / `BRANCH_ALIAS_INFER=gateway` — только короткая
проба маршрутизации. Ключ/URL/id модели в код не входят (конфиг OpenClaw).
Промпт из файла (обход лимита argv у длинных JSON-пачек).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def infer_transport_flag(env: dict | None = None) -> str:
    """`--local` или `--gateway`; иное/пустое → local (штатный default model run)."""
    src = env if env is not None else os.environ
    raw = (
        src.get("BRANCH_ALIAS_INFER")
        or src.get("ALIAS_INFER_TRANSPORT")
        or "local"
    ).strip().lower()
    return "--gateway" if raw == "gateway" else "--local"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--message-file", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--thinking", default="off")
    p.add_argument("--ans", required=True, help="stdout JSON (обёртка под parse)")
    p.add_argument("--err", default="", help="stderr агента")
    args = p.parse_args()

    prompt = Path(args.message_file).read_text(encoding="utf-8")
    if not prompt.strip():
        print("alias_infer_gateway: пустой prompt", file=sys.stderr)
        return 2

    cmd = [
        "openclaw",
        "infer",
        "model",
        "run",
        infer_transport_flag(),
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--json",
        "--prompt",
        prompt,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    err_blob = proc.stderr or ""
    if proc.returncode != 0 and (proc.stdout or "").strip():
        err_blob = (err_blob + "\n" + proc.stdout).strip() + "\n"
    if args.err:
        Path(args.err).write_text(err_blob, encoding="utf-8")

    if proc.returncode != 0:
        Path(args.ans).write_text(proc.stdout or "", encoding="utf-8")
        return proc.returncode

    try:
        infer = json.loads(proc.stdout)
    except json.JSONDecodeError:
        Path(args.ans).write_text(proc.stdout or "", encoding="utf-8")
        return 1

    texts = [
        str(o.get("text") or "").strip()
        for o in (infer.get("outputs") or [])
        if isinstance(o, dict)
    ]
    text = "\n".join(t for t in texts if t)
    wrapped = {
        "payloads": [{"text": text}],
        "meta": {
            "transport": infer.get("transport"),
            "agentMeta": {
                "provider": infer.get("provider"),
                "model": infer.get("model"),
                "fallbackAttempts": infer.get("attempts"),
            },
        },
        "_infer": infer,
    }
    Path(args.ans).write_text(
        json.dumps(wrapped, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
