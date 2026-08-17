#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
import serene_ask as A  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "runs", "qwen-thinking-formats.json")


def main():
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("EMBED_API_KEY")
    base = os.environ.get("DEEPSEEK_BASE", "https://a1f19thc-8000.thundercompute.net").rstrip("/")
    q = "today=2026-08-17\n\nQuestion: На какую сумму мы закупили товаров и услуг?"
    msgs = [{"role": "system", "content": A.INTENT_SYS}, {"role": "user", "content": q}]
    rows = []
    for label, extra in [
        ("plain", {}),
        ("extra_body", {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}),
        ("top_level", {"chat_template_kwargs": {"enable_thinking": False}}),
    ]:
        body = {"model": "Qwen3.8-27B", "temperature": 0, "max_tokens": 400,
                "messages": msgs, **extra}
        req = urllib.request.Request(
            base + "/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                       "User-Agent": "curl/8.5.0"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            msg = data["choices"][0]["message"]
            rows.append({"label": label, "usage": data.get("usage"),
                         "blocks": len(A._json_blocks(msg.get("content") or "")),
                         "content_head": (msg.get("content") or "")[:160],
                         "reasoning_len": len(msg.get("reasoning_content") or "")})
        except Exception as e:  # noqa: BLE001
            rows.append({"label": label, "error": str(e)})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
