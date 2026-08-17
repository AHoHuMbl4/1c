#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн: учёт usage DeepSeek в ds_chat → diag.tokens (без сети и базы)."""
import io
import json
import sys
import urllib.request

import serene_ask as A

PASS = 0
FAIL = []


def t(name, ok):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append(name)


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(req, timeout=120):
    return _Resp(_fake_urlopen.payload)


# ── _diag_pack: сумма двух вызовов с hit/miss ───────────────────────────────
A._token_acc_start()
A._token_acc_record({"prompt_tokens": 100, "completion_tokens": 20,
                     "prompt_cache_hit_tokens": 80, "prompt_cache_miss_tokens": 20})
A._token_acc_record({"prompt_tokens": 50, "completion_tokens": 10,
                     "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 10})
d = A._diag_pack({"шаг": "проба"})
t("diag.tokens: calls/in/out", d.get("tokens") == {"calls": 2, "in": 150, "out": 30,
                                                   "cache_hit": 120, "cache_miss": 30})
t("diag.tokens: hit/miss ключи", "cache_hit" in d["tokens"] and "cache_miss" in d["tokens"])

# ── без usage: не падает, поля tokens нет ───────────────────────────────────
A._token_acc_start()
c = A._ds_chat_content({"choices": [{"message": {"content": "ok"}}]})
t("_ds_chat_content без usage → текст", c == "ok")
d0 = A._diag_pack({})
t("без usage: tokens отсутствует", "tokens" not in d0)

# ── ds_chat через подмену urlopen ───────────────────────────────────────────
_logs = io.StringIO()
_old_err = sys.stderr
sys.stderr = _logs
try:
    A._token_acc_start()
    _fake_urlopen.payload = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
    }
    _real = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen
    try:
        out = A.ds_chat([{"role": "user", "content": "x"}])
    finally:
        urllib.request.urlopen = _real
    t("ds_chat с usage → content", out == "hi")
    d1 = A._diag_pack({})
    t("ds_chat с usage → diag", d1.get("tokens") == {"calls": 1, "in": 11, "out": 3})
    log = _logs.getvalue()
    t("journal: ask TOKENS без hit/miss", "ask TOKENS in=11 out=3" in log
      and "hit=" not in log and "miss=" not in log)
finally:
    sys.stderr = _old_err

# ── битый ответ: без choices и usage ────────────────────────────────────────
A._token_acc_start()
c2 = A._ds_chat_content({})
t("пустой ответ → None", c2 is None)
t("пустой ответ → tokens нет", "tokens" not in A._diag_pack({}))

# ── ASK_THINKING_OFF_BODY: extra_body для vLLM/Qwen ─────────────────────────
_old = A.ASK_THINKING_OFF_BODY
A.ASK_THINKING_OFF_BODY = False
b0 = A._ds_chat_body([{"role": "user", "content": "x"}])
t("off: без extra_body", "extra_body" not in b0)
A.ASK_THINKING_OFF_BODY = True
b1 = A._ds_chat_body([{"role": "user", "content": "x"}])
t("on: chat_template_kwargs thinking off", b1.get("chat_template_kwargs") == {
    "enable_thinking": False})
A.ASK_THINKING_OFF_BODY = _old

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    for n in FAIL:
        print(" ", n)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
