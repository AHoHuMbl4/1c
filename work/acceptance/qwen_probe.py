#!/usr/bin/env python3
"""Probe vLLM endpoints — writes JSON to runs/."""
import json
import os
import urllib.request

OUT = os.path.join(os.path.dirname(__file__), "runs", "qwen-probe-endpoints.json")
BASE = os.environ.get("QWEN_BASE", "https://a1f19thc-8000.thundercompute.net").rstrip("/")
KEY = os.environ.get("DEEPSEEK_API_KEY", "")


def probe(url):
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + KEY, "User-Agent": "curl/8.5.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return {"status": r.status, "body": r.read()[:2000].decode("utf-8", "replace")}
    except Exception as e:
        return {"error": type(e).__name__, "msg": str(e)[:300]}


def main():
    if not KEY:
        raise SystemExit("DEEPSEEK_API_KEY not set")
    urls = [BASE + "/v1/models", BASE + "/health"]
    out = {u: probe(u) for u in urls}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(OUT)


if __name__ == "__main__":
    main()
