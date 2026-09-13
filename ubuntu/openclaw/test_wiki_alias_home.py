#!/usr/bin/env python3
"""Замок шаблона и скрипта генераторного openclaw-HOME (G7a).

Проверяет:
  - wiki-alias-home-template.json: валидный JSON + ловушки ночи 12–13.09;
  - wiki_alias_setup_home.sh: bash -n, плейсхолдеры, apiKey только из env;
  - живой прогон скрипта в TMP-HOME → конфиг валиден, поля на месте.

Запуск:
  python3 ubuntu/openclaw/test_wiki_alias_home.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Значение опции contextInjection из доков OpenClaw config-agents.md (штатный JSON).
_CI_OFF = "never"


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "wiki-alias-home-template.json"
SETUP = HERE / "wiki_alias_setup_home.sh"

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# ─── шаблон ───────────────────────────────────────────────────────────
raw = TEMPLATE.read_text(encoding="utf-8")
t("шаблон: файл существует", TEMPLATE.is_file())

tpl = None
try:
    tpl = json.loads(raw)
    t("шаблон: JSON валиден", True)
except json.JSONDecodeError as e:
    t("шаблон: JSON валиден", False, e)

# Плейсхолдеры ключа — не реальный секрет
t("шаблон: apiKey — плейсхолдер @@WIKI_LLM_API_KEY@@",
  '"apiKey": "@@WIKI_LLM_API_KEY@@"' in raw
  or '"apiKey":"@@WIKI_LLM_API_KEY@@"' in raw.replace(" ", ""))
t("шаблон: нет живого ключа вне @@…@@",
  not re.search(r'"apiKey"\s*:\s*"(?!@@)[^"]+"', raw))

for ph in (
    "@@WIKI_LLM_BASE_URL@@",
    "@@WIKI_LLM_API_KEY@@",
    "@@WIKI_LLM_MODEL_ID@@",
    "@@WIKI_ALIAS_AGENT_ID@@",
):
    t(f"шаблон: плейсхолдер {ph}", ph in raw)

if tpl is not None:
    t("шаблон: НЕТ gateway", "gateway" not in tpl)

    vllm = ((tpl.get("models") or {}).get("providers") or {}).get("vllm") or {}
    models = vllm.get("models") or []
    m0 = models[0] if models else {}
    t("шаблон: vllm.timeoutSeconds=900", vllm.get("timeoutSeconds") == 900)
    t("шаблон: vllm.api=openai-completions", vllm.get("api") == "openai-completions")
    t("шаблон: vllm.baseUrl плейсхолдер",
      vllm.get("baseUrl") == "@@WIKI_LLM_BASE_URL@@")
    t("шаблон: vllm.apiKey плейсхолдер",
      vllm.get("apiKey") == "@@WIKI_LLM_API_KEY@@")
    t("шаблон: models[0].id = @@WIKI_LLM_MODEL_ID@@",
      m0.get("id") == "@@WIKI_LLM_MODEL_ID@@")
    t("шаблон: models[0].maxTokens=12288 (провайдер!)",
      m0.get("maxTokens") == 12288,
      m0.get("maxTokens"))

    defaults = (tpl.get("agents") or {}).get("defaults") or {}
    t("шаблон: skipBootstrap true", defaults.get("skipBootstrap") is True)
    t("шаблон: contextInjection отключён",
      defaults.get("contextInjection") == _CI_OFF)
    t("шаблон: thinkingDefault off", defaults.get("thinkingDefault") == "off")
    t("шаблон: heartbeat 0m",
      (defaults.get("heartbeat") or {}).get("every") == "0m")
    t("шаблон: skills []", defaults.get("skills") == [])

    cat = defaults.get("models") or {}
    # ключ каталога с плейсхолдером модели
    model_keys = [k for k in cat if "@@WIKI_LLM_MODEL_ID@@" in k]
    t("шаблон: каталог models имеет vllm/@@MODEL@@",
      any(k.startswith("vllm/") for k in model_keys), list(cat))
    params = (cat.get(model_keys[0]) or {}).get("params") if model_keys else {}
    t("шаблон: params.temperature=0", params.get("temperature") == 0)
    t("шаблон: params.seed=42", params.get("seed") == 42)
    t("шаблон: params.maxTokens=12288", params.get("maxTokens") == 12288)
    t("шаблон: enable_thinking false",
      (params.get("chat_template_kwargs") or {}).get("enable_thinking") is False)

    alist = (tpl.get("agents") or {}).get("list") or []
    agent = alist[0] if alist else {}
    t("шаблон: agents.list не пуст", bool(alist))
    t("шаблон: агент id = @@WIKI_ALIAS_AGENT_ID@@",
      agent.get("id") == "@@WIKI_ALIAS_AGENT_ID@@")
    t("шаблон: агент model = vllm/@@WIKI_LLM_MODEL_ID@@",
      agent.get("model") == "vllm/@@WIKI_LLM_MODEL_ID@@")


# ─── скрипт ───────────────────────────────────────────────────────────
t("скрипт: файл существует", SETUP.is_file())
sh_text = SETUP.read_text(encoding="utf-8") if SETUP.is_file() else ""

bn = subprocess.run(
    ["bash", "-n", str(SETUP)], capture_output=True, text=True
)
t("скрипт: bash -n", bn.returncode == 0, bn.stderr.strip())

t("скрипт: set -euo pipefail (strict)",
  re.search(r"set\s+-euo\s+pipefail", sh_text) is not None)
t("скрипт: подстановка @@WIKI_LLM_BASE_URL@@",
  "@@WIKI_LLM_BASE_URL@@" in sh_text)
t("скрипт: подстановка @@WIKI_LLM_API_KEY@@",
  "@@WIKI_LLM_API_KEY@@" in sh_text)
t("скрипт: подстановка @@WIKI_LLM_MODEL_ID@@",
  "@@WIKI_LLM_MODEL_ID@@" in sh_text)
t("скрипт: подстановка @@WIKI_ALIAS_AGENT_ID@@",
  "@@WIKI_ALIAS_AGENT_ID@@" in sh_text)

# Маркер отсутствия argv-ключа: apiKey только из env WIKI_LLM_API_KEY
t("скрипт: apiKey только из env WIKI_LLM_API_KEY",
  "WIKI_LLM_API_KEY" in sh_text
  and "API_KEY=\"${WIKI_LLM_API_KEY" in sh_text.replace(" ", ""))
t("скрипт: маркер «не argv» / usage без ключа в позиционных",
  "не из argv" in sh_text.lower()
  or "не argv" in sh_text.lower()
  or "только из env" in sh_text.lower())
# Usage: HOME base_url model_id [agent_id] [owner] — 3–5 позиционных, без apiKey
t("скрипт: $# -ge 3 && $# -le 5 (без argv-ключа)",
  re.search(r'\$#.*-ge\s*3.*-le\s*5|\$#.*-le\s*5.*-ge\s*3', sh_text) is not None
  or ('"$#" -ge 3' in sh_text and '"$#" -le 5' in sh_text)
  or ("$#" in sh_text and "-ge 3" in sh_text and "-le 5" in sh_text))
t("скрипт: abs-HOME guard (case /*)",
  "/*)" in sh_text
  and ("абсолютн" in sh_text.lower() or "двойной .openclaw" in sh_text.lower()))
t("скрипт: маркер chown при [owner]",
  "chown -R" in sh_text and 'OWNER="${5' in sh_text.replace(" ", ""))
t("скрипт: маркер отсутствия chown без owner",
  re.search(r'\[\s+-n\s+"\$OWNER"\s+\]', sh_text) is not None
  or '[ -n "$OWNER" ]' in sh_text)
t("скрипт: chmod 700 HOME", "chmod 700" in sh_text and "OPENCLAW_HOME" in sh_text)
t("скрипт: chmod/install 600 конфиг",
  ("chmod 600" in sh_text or "install -m 600" in sh_text)
  and ("openclaw.json" in sh_text or "CFG" in sh_text))
t("скрипт: идемпотентный .bak",
  ".bak-" in sh_text or "bak-$(" in sh_text)
t("скрипт: mkdir workspace",
  ".openclaw/workspace" in sh_text or 'workspace"' in sh_text)


# ─── живой прогон в TMP-HOME ──────────────────────────────────────────
tmp_home = Path(tempfile.mkdtemp(prefix="wiki-alias-home-"))
try:
    env = os.environ.copy()
    env["WIKI_LLM_API_KEY"] = "test-key-not-secret-g7a"
    base_url = "http://127.0.0.1:9/v1"
    model_id = "Qwen3.8-27B-TEST"
    agent_id = "dict"
    proc = subprocess.run(
        [
            "bash", str(SETUP),
            str(tmp_home), base_url, model_id, agent_id,
        ],
        capture_output=True, text=True, env=env, timeout=30,
    )
    print("--- живой прогон stdout ---")
    print(proc.stdout.rstrip() or "(пусто)")
    if proc.stderr.strip():
        print("--- живой прогон stderr ---")
        print(proc.stderr.rstrip())
    t("живой: exit 0", proc.returncode == 0, proc.stderr.strip() or proc.stdout)

    cfg_path = tmp_home / ".openclaw" / "openclaw.json"
    ws_path = tmp_home / ".openclaw" / "workspace"
    t("живой: конфиг создан", cfg_path.is_file(), str(cfg_path))
    t("живой: workspace mkdir", ws_path.is_dir())
    mode_home = oct(tmp_home.stat().st_mode)[-3:]
    mode_cfg = oct(cfg_path.stat().st_mode)[-3:] if cfg_path.is_file() else "---"
    t("живой: HOME mode 700", mode_home == "700", mode_home)
    t("живой: конфиг mode 600", mode_cfg == "600", mode_cfg)

    cfg = None
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            t("живой: JSON валиден", True)
        except json.JSONDecodeError as e:
            t("живой: JSON валиден", False, e)

    if cfg is not None:
        t("живой: нет @@ плейсхолдеров",
          "@@" not in cfg_path.read_text(encoding="utf-8"))
        t("живой: НЕТ gateway", "gateway" not in cfg)
        vllm = ((cfg.get("models") or {}).get("providers") or {}).get("vllm") or {}
        m0 = (vllm.get("models") or [{}])[0]
        t("живой: baseUrl подставлен", vllm.get("baseUrl") == base_url)
        t("живой: apiKey из env",
          vllm.get("apiKey") == "test-key-not-secret-g7a")
        t("живой: model id", m0.get("id") == model_id)
        t("живой: provider maxTokens=12288", m0.get("maxTokens") == 12288)
        t("живой: timeoutSeconds=900", vllm.get("timeoutSeconds") == 900)
        defaults = (cfg.get("agents") or {}).get("defaults") or {}
        t("живой: skipBootstrap", defaults.get("skipBootstrap") is True)
        t("живой: contextInjection отключён",
          defaults.get("contextInjection") == _CI_OFF)
        mk = f"vllm/{model_id}"
        params = ((defaults.get("models") or {}).get(mk) or {}).get("params") or {}
        t("живой: temp=0 seed=42",
          params.get("temperature") == 0 and params.get("seed") == 42)
        t("живой: params maxTokens=12288", params.get("maxTokens") == 12288)
        t("живой: enable_thinking false",
          (params.get("chat_template_kwargs") or {}).get("enable_thinking") is False)
        agent = ((cfg.get("agents") or {}).get("list") or [{}])[0]
        t("живой: агент dict",
          agent.get("id") == agent_id and agent.get("model") == mk)
        t("живой: workspace путь",
          defaults.get("workspace") == str(ws_path))

        # идемпотентность: повтор → .bak
        proc2 = subprocess.run(
            ["bash", str(SETUP), str(tmp_home), base_url, model_id, agent_id],
            capture_output=True, text=True, env=env, timeout=30,
        )
        baks = list((tmp_home / ".openclaw").glob("openclaw.json.bak-*"))
        t("живой: повтор exit 0", proc2.returncode == 0, proc2.stderr)
        t("живой: .bak после перезаписи", len(baks) >= 1, [p.name for p in baks])

    # без env — отказ
    env_no = os.environ.copy()
    env_no.pop("WIKI_LLM_API_KEY", None)
    proc3 = subprocess.run(
        ["bash", str(SETUP), str(tmp_home), base_url, model_id],
        capture_output=True, text=True, env=env_no, timeout=30,
    )
    t("живой: без WIKI_LLM_API_KEY → ненулевой exit",
      proc3.returncode != 0, proc3.returncode)

    # abs-HOME guard: относительный путь → отказ (ловушка двойного .openclaw)
    proc_rel = subprocess.run(
        ["bash", str(SETUP), "./rel-home", base_url, model_id],
        capture_output=True, text=True, env=env, timeout=30,
        cwd=str(tmp_home),
    )
    t("живой: относительный HOME ./rel → ненулевой exit",
      proc_rel.returncode != 0, proc_rel.returncode)
    t("живой: относительный HOME — текст про абсолютный/двойной .openclaw",
      "абсолют" in (proc_rel.stderr + proc_rel.stdout).lower()
      or "двойной" in (proc_rel.stderr + proc_rel.stdout).lower()
      or "/*" in (proc_rel.stderr + proc_rel.stdout),
      (proc_rel.stderr or proc_rel.stdout)[:200])
finally:
    shutil.rmtree(tmp_home, ignore_errors=True)


print()
total = PASS + len(FAIL)
print("ИТОГ: %d/%d" % (PASS, len(FAIL)))
print("---", PASS, "ok,", len(FAIL), "fail")
if FAIL:
    print("ПРОВАЛЕНО: %s" % "; ".join(FAIL))
    raise SystemExit(1)
print("все %d проверок пройдены" % PASS)
