#!/usr/bin/env python3
"""Один вызов модели через `openclaw` CLI (рантаймы infer/agent) без tool surface.

Умолчание — `--local` (доки установленной сборки `cli/infer.md` Behavior:
stateless `model run` defaults to local; gateway не нужен). 🔴 [замер 24.08]
`--gateway` режет RPC-потолком 120000 ms (`GatewayTransportError`); на пачке
wiki-alias 20 сущностей / vLLM Qwen3.8-27B: gw 619 с exit 1, loc 1034 с exit 0.
Потолок в схеме/конфиге не поднимается (`timeoutMs: 12e4` литерал в CLI).
`ALIAS_INFER_TRANSPORT=gateway` / `BRANCH_ALIAS_INFER=gateway` — только короткая
проба маршрутизации. Ключ/URL/id модели в код не входят (конфиг OpenClaw).
Промпт из файла (обход лимита argv у длинных JSON-пачек).

Agent-режим (`ALIAS_INFER_RUNTIME=agent`): `openclaw agent --local` +
`--message-file` (доки `cli/agent.md`). Нужен песочнице 27B: G0 показал, что
`infer model run --local` не читает `params` каталога (extra-params только на
агентном рантайме), а P4 §4 требует temperature=0 — оно уже в openclaw.json
песочницы (seed/maxTokens тоже). С 13.09 дефолт — `agent`: на reasoning-
модели без thinking-kwargs infer получает 200 без текста («No text output
returned», живой замер okna, OpenRouter qwen/qwen3.8-27b) — techContext
ловушка 60. `infer` остаётся для провайдеров без reasoning-вывода.

Сессия на вызов (agent): `--session-key alias-gen-<uuid4hex>` — bare ключ +
`--agent` скопится в `agent:<id>:<key>` (доки `cli/agent.md`); изоляция
контекста пачек — история пачек не течёт в следующий промт (без ключа
reuse шёл в `agent:dict:main` и один растущий session.jsonl).

Таймаут subprocess: `ALIAS_AGENT_TIMEOUT_SEC` (дефолт 1800; замер пачки до
1034 с). TimeoutExpired → kill, err с причиной, ans = сырой stdout, exit 124.
Таймаут на оба режима (infer тоже может висеть); дефолт 1800 не режет бой.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
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


def infer_runtime(env: dict | None = None) -> str:
    """`agent` (дефолт: params из каталога) или `infer` (без params; провайдер без reasoning)."""
    src = env if env is not None else os.environ
    raw = (src.get("ALIAS_INFER_RUNTIME") or "agent").strip().lower()
    return "infer" if raw == "infer" else "agent"


def agent_id(env: dict | None = None) -> str:
    """Id агента OpenClaw для agent-режима; умолчание `dict`."""
    src = env if env is not None else os.environ
    raw = (src.get("ALIAS_AGENT_ID") or "dict").strip()
    return raw or "dict"


def agent_timeout_sec(env: dict | None = None) -> int:
    """Потолок subprocess.run: ALIAS_AGENT_TIMEOUT_SEC, дефолт 1800."""
    src = env if env is not None else os.environ
    raw = (src.get("ALIAS_AGENT_TIMEOUT_SEC") or "").strip()
    if not raw:
        return 1800
    try:
        return max(1, int(raw))
    except ValueError:
        return 1800


def build_cmd(
    *,
    message_file: str,
    model: str,
    thinking: str,
    prompt: str | None = None,
    env: dict | None = None,
) -> list[str]:
    """Собрать argv openclaw: infer model run или agent --local."""
    if infer_runtime(env) == "agent":
        return [
            "openclaw",
            "agent",
            "--local",
            "--agent",
            agent_id(env),
            "--session-key",
            "alias-gen-%s" % (uuid.uuid4().hex,),
            "--message-file",
            message_file,
            "--model",
            model,
            "--thinking",
            thinking,
            "--json",
        ]
    if prompt is None:
        raise ValueError("infer runtime requires prompt text for --prompt")
    return [
        "openclaw",
        "infer",
        "model",
        "run",
        infer_transport_flag(env),
        "--model",
        model,
        "--thinking",
        thinking,
        "--json",
        "--prompt",
        prompt,
    ]


def agent_result_from_stdout(stdout: str) -> tuple[int, str]:
    """Разобрать stdout `openclaw agent --json` → (exit, тело ans).

    Валидный JSON с непустыми payloads/text → 0 и JSON (meta.transport=agent).
    Иначе → 1 и сырой stdout (как при ошибке infer).
    """
    raw = stdout or ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return 1, raw
    if not isinstance(data, dict):
        return 1, raw
    payloads = data.get("payloads")
    if not isinstance(payloads, list) or not payloads:
        return 1, raw
    texts = [
        str(o.get("text") or "").strip()
        for o in payloads
        if isinstance(o, dict)
    ]
    if not any(texts):
        return 1, raw
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        data["meta"] = meta
    meta["transport"] = "agent"
    return 0, json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--message-file", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--thinking", default="off")
    p.add_argument(
        "--temperature",
        default=None,
        help="accepted for callers; not forwarded (CLI has no matching flag)",
    )
    p.add_argument("--ans", required=True, help="stdout JSON (обёртка под parse)")
    p.add_argument("--err", default="", help="stderr агента")
    args = p.parse_args()

    prompt = Path(args.message_file).read_text(encoding="utf-8")
    if not prompt.strip():
        print("alias_infer_gateway: пустой prompt", file=sys.stderr)
        return 2

    runtime = infer_runtime()
    if args.temperature is not None:
        if runtime == "agent":
            # params — из каталога openclaw.json (G0 / P4 §4); CLI-флага нет.
            print(
                "agent runtime: params from openclaw.json catalog",
                file=sys.stderr,
            )
        else:
            # openclaw infer model run: --model/--thinking/--local/--gateway/--json/--prompt/--file
            # (docs/cli/infer.md). No --temperature in that surface; leave unused.
            print(
                "alias_infer_gateway: --temperature=%s noted but not forwarded "
                "(openclaw infer model run has no matching CLI flag)"
                % (args.temperature,),
                file=sys.stderr,
            )

    if runtime == "agent":
        cmd = build_cmd(
            message_file=args.message_file,
            model=args.model,
            thinking=args.thinking,
        )
    else:
        cmd = build_cmd(
            message_file=args.message_file,
            model=args.model,
            thinking=args.thinking,
            prompt=prompt,
        )
    timeout_sec = agent_timeout_sec()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else (
            (exc.stdout or b"").decode("utf-8", errors="replace")
        )
        err_blob = (
            "alias_infer_gateway: subprocess timeout after %ds\n" % (timeout_sec,)
            + (exc.stderr if isinstance(exc.stderr, str) else (
                (exc.stderr or b"").decode("utf-8", errors="replace")
            ))
        )
        if args.err:
            Path(args.err).write_text(err_blob, encoding="utf-8")
        Path(args.ans).write_text(out or "", encoding="utf-8")
        return 124
    err_blob = proc.stderr or ""
    if proc.returncode != 0 and (proc.stdout or "").strip():
        err_blob = (err_blob + "\n" + proc.stdout).strip() + "\n"
    if args.err:
        Path(args.err).write_text(err_blob, encoding="utf-8")

    if proc.returncode != 0:
        Path(args.ans).write_text(proc.stdout or "", encoding="utf-8")
        return proc.returncode

    if runtime == "agent":
        code, body = agent_result_from_stdout(proc.stdout or "")
        Path(args.ans).write_text(body, encoding="utf-8")
        return code

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
