#!/usr/bin/env python3
"""Один вызов vLLM/прочей модели через шлюз OpenClaw без tool surface.

`openclaw infer model run --gateway` шлёт modelRun/promptMode=none (доки
cli/infer.md) — vLLM не получает tool payload. Промпт читается из файла
(обход лимита argv у длинных JSON-пачек).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


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
        "--gateway",
        "--model",
        args.model,
        "--thinking",
        args.thinking,
        "--json",
        "--prompt",
        prompt,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if args.err:
        Path(args.err).write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        if proc.stdout.strip():
            Path(args.ans).write_text(proc.stdout, encoding="utf-8")
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
