#!/usr/bin/env python3
"""Идемпотентно добавляет провайдер vLLM в openclaw.json (шлюз undebot).

Читает VLLM_BASE_URL и VLLM_API_KEY из окружения (systemd подставляет из
/etc/1c-embed.env). Не трогает deepseek и прочие поля конфига.
"""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

VLLM_MODEL_ID = os.environ.get("VLLM_MODEL_ID", "Qwen3.8-27B")
VLLM_BASE = (os.environ.get("VLLM_BASE_URL") or "").rstrip("/")
if VLLM_BASE and not VLLM_BASE.endswith("/v1"):
    VLLM_BASE = VLLM_BASE + "/v1"


def vllm_provider_block() -> dict:
    return {
        "baseUrl": VLLM_BASE,
        "apiKey": "${VLLM_API_KEY}",
        "api": "openai-completions",
        "timeoutSeconds": int(os.environ.get("VLLM_TIMEOUT_SEC", "300")),
        "models": [
            {
                "id": VLLM_MODEL_ID,
                "name": "Qwen3.8 27B (vLLM)",
                "reasoning": True,
                "input": ["text"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": int(os.environ.get("VLLM_CONTEXT", "131072")),
                "maxTokens": int(os.environ.get("VLLM_MAX_TOKENS", "8192")),
                "compat": {
                    "thinkingFormat": "qwen-chat-template",
                    "supportsTools": False,
                },
            }
        ],
    }


def merge_allow(cfg: dict) -> bool:
    changed = False
    agents = cfg.setdefault("agents", {}).setdefault("defaults", {})
    models = agents.setdefault("models", {})
    ref = f"vllm/{VLLM_MODEL_ID}"
    if ref not in models:
        models[ref] = {"params": {"chat_template_kwargs": {"enable_thinking": False}}}
        changed = True
    if "vllm/*" not in models:
        models["vllm/*"] = {}
        changed = True
    return changed


def merge_plugins(cfg: dict) -> bool:
    changed = False
    plugins = cfg.setdefault("plugins", {})
    allow = plugins.setdefault("allow", [])
    if "vllm" not in allow:
        allow.append("vllm")
        changed = True
    entries = plugins.setdefault("entries", {})
    if entries.get("vllm", {}).get("enabled") is not True:
        entries["vllm"] = {"enabled": True}
        changed = True
    return changed


def merge_auth(cfg: dict) -> bool:
    changed = False
    profiles = cfg.setdefault("auth", {}).setdefault("profiles", {})
    if "vllm:default" not in profiles:
        profiles["vllm:default"] = {"provider": "vllm", "mode": "api_key"}
        changed = True
    return changed


def merge_provider(cfg: dict) -> bool:
    if not VLLM_BASE:
        print("patch_vllm: VLLM_BASE_URL не задан — пропуск", file=sys.stderr)
        return False
    changed = False
    providers = cfg.setdefault("models", {}).setdefault("providers", {})
    want = vllm_provider_block()
    cur = providers.get("vllm")
    if cur != want:
        providers["vllm"] = want
        changed = True
    if cfg.get("models", {}).get("mode") != "merge":
        cfg.setdefault("models", {})["mode"] = "merge"
        changed = True
    return changed


def merge_agent_dict(cfg: dict) -> bool:
    agents = cfg.setdefault("agents", {})
    lst = agents.setdefault("list", [])
    want = {
        "id": "dict",
        "model": f"vllm/{VLLM_MODEL_ID}",
        "thinkingDefault": "off",
    }
    for i, a in enumerate(lst):
        if a.get("id") == "dict":
            merged = {k: v for k, v in a.items() if k != "tools"}
            merged.update(want)
            if merged != a:
                lst[i] = merged
                return True
            return False
    lst.append(dict(want))
    return True


def patch(cfg: dict) -> bool:
    return any(
        (
            merge_provider(cfg),
            merge_allow(cfg),
            merge_plugins(cfg),
            merge_auth(cfg),
            merge_agent_dict(cfg),
        )
    )


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw/openclaw.json"))
    if not path.is_file():
        print(f"patch_vllm: нет файла {path}", file=sys.stderr)
        return 2
    cfg = json.loads(path.read_text(encoding="utf-8"))
    before = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    changed = patch(cfg)
    after = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    if changed and before != after:
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"patch_vllm: обновлён {path}")
        return 0
    print("patch_vllm: уже актуален")
    return 0


if __name__ == "__main__":
    sys.exit(main())
