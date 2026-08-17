#!/usr/bin/env python3
"""Замер стоимости и качества вызовов openclaw agent для словарных контуров.

Штатный путь: `openclaw agent --json --message-file` (как wiki_alias / branch_alias).
Не заменяет прямой вызов модели — только измеряет тот же механизм.

Режимы (ALIAS_BENCH_MODE):
  overhead   — контрольный prompt + один боевой чанк branch (40 src), gateway
  thinking   — тот же чанк на шлюзе: thinking off vs попытка non-off (если поддержано)
  ab         — A/B flash vs pro на N чанках branch + 2 пачки wiki (меры)
  report     — только собрать JSON из каталога прогонов

Использование:
  set -a; source /etc/1c-mcp-reports.env; set +a
  ALIAS_BENCH_MODE=overhead python3 work/entity-choice/alias_agent_bench.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERENED = ROOT / "ubuntu" / "serenedb"
sys.path.insert(0, str(SERENED))

import branch_alias_parse as bap  # noqa: E402
import wiki_alias_parse as wap  # noqa: E402

OPENCLAW = Path("/usr/lib/node_modules/openclaw/openclaw.mjs")
NODE = Path("/usr/bin/node")
OUT = ROOT / "work" / "acceptance" / "runs"
BENCH_PROFILE = ROOT / "out" / "openclaw-dict-bench"

BRANCH_PROMPT_HEAD = (
    "JSON only, no prose, no code fences. Below are FORK CLASSES of one database. "
    "Each class lists record types (sources) whose data OVERLAP: the same business fact "
    "can be read from any of them, and totals by the shown measure DIFFER between them, "
    "so a person asking about that measure picks a branch. For each source of "
    "every class write a short label that says what these records MEAN for the business — "
    "what kind of fact it is, and how it differs from the other sources of the same class; "
    "the person already sees the type name, so the label adds business meaning beyond "
    "the visible type name, rather than repeating the name. Use the SAME language as the titles. "
    "Keys in labels are the technical source identifiers (the \"src\" field); each source also "
    "carries a human title, which is shown to the person separately and is not a key. Schema: "
    "{\"forks\":[{\"fork_key\":\"<copy exactly>\",\"labels\":"
    "{\"<technical source id exactly>\":\"<label>\"}}]}. Input: "
)

WIKI_PROMPT_HEAD = (
    "JSON only, no prose, no code fences. Below are record types of one database, shown "
    "together because they are CLOSE IN MEANING — that is what makes them easy to confuse. "
    "For each, in the SAME language as its title: (1) aliases — the SHORT NAMES a person "
    "here uses for this kind of record, including its own title; names of its quantities do "
    "not belong here; (2) quantities — for each name from the input quantities list, copy "
    "that name exactly and give the short names a person uses for that value (a noun or a "
    "noun with the action word, 1-3 words each, no sentences); (3) bestUsedFor — the "
    "questions it answers; (4) notEnoughFor — what it does not answer, naming the sibling "
    "types from this list that a person could mean instead and what each of them answers. "
    "Schema: {\"items\":[{\"entity\":\"...\",\"aliases\":[\"...\"],\"quantities\":"
    "[{\"name\":\"<exact from input quantities>\",\"aliases\":[\"...\"]}],"
    "\"bestUsedFor\":[\"...\"],\"notEnoughFor\":[\"...\"]}]}. Input: "
)


def dsn() -> str:
    return os.environ.get(
        "SERENEDB_DSN", "host=127.0.0.1 port=7890 user=postgres dbname=ut_test"
    )


def psql_json(sql: str) -> list | dict | None:
    r = subprocess.run(
        ["psql", dsn(), "-tA", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    raw = (r.stdout or "").strip()
    if not raw or raw in ("null", "[]"):
        return None
    return json.loads(raw)


def openclaw_agent(
    msg_path: Path,
    *,
    session_key: str,
    model: str | None = None,
    thinking: str = "off",
    local: bool = False,
    profile: str | None = None,
    timeout_s: int = 600,
) -> tuple[dict | None, str, int, int]:
    cmd = [str(NODE), str(OPENCLAW), "agent", "--agent", "main", "--json",
           "--session-key", session_key, "--thinking", thinking,
           "--message-file", str(msg_path), "--timeout", str(timeout_s)]
    if model:
        cmd.extend(["--model", model])
    if local:
        cmd.append("--local")
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:" + env.get("PATH", "")
    if not local:
        pass
    else:
        env["OPENCLAW_CONFIG_PATH"] = str(BENCH_PROFILE / "openclaw.json")
        env["OPENCLAW_STATE_DIR"] = str(BENCH_PROFILE / "state2")
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    ms = int((time.time() - t0) * 1000)
    err = (r.stderr or "").strip()
    if not (r.stdout or "").strip():
        return None, err, ms, r.returncode
    try:
        return json.loads(r.stdout), err, ms, r.returncode
    except json.JSONDecodeError:
        return None, err or "invalid json stdout", ms, r.returncode


def extract_usage(resp: dict | None) -> dict:
    if not resp:
        return {}
    meta = resp.get("meta") or (resp.get("result") or {}).get("meta") or {}
    am = meta.get("agentMeta") or {}
    u = am.get("usage") or am.get("lastCallUsage") or {}
    return {
        "input": u.get("input"),
        "output": u.get("output"),
        "cache_read": u.get("cacheRead"),
        "total": u.get("total"),
        "model": am.get("model") or am.get("resolvedRef"),
        "reasoning": am.get("reasoningEffort") or am.get("reasoning"),
        "duration_ms": meta.get("durationMs") or resp.get("meta", {}).get("durationMs"),
    }


def dig_text(resp: dict | None) -> str:
    if not resp:
        return ""
    raw = json.dumps(resp, ensure_ascii=False)
    text = wap.text_from_agent(raw)
    if text:
        return text
    for p in resp.get("payloads") or []:
        if isinstance(p, dict) and p.get("text"):
            return p["text"]
    return ""


def branch_need_sql(batch: int = 1, src_chunk: int = 40) -> str:
    return f"""
  WITH need AS (
    SELECT c.fork_key, c.src_set, c.measure_ctx
    FROM search_fork_class c
    WHERE EXISTS (
      SELECT 1 FROM unnest(str_split(c.src_set, ',')) AS x(s)
      WHERE NOT EXISTS (
        SELECT 1 FROM search_fork_label l
        WHERE l.fork_key = c.fork_key AND l.src = trim(x.s, '{{}} ')
          AND coalesce(l.label, '') <> ''))
    ORDER BY c.fork_key LIMIT {batch}),
  raw_srcs AS (
    SELECT n.fork_key, n.measure_ctx, trim(x.s, '{{}} ') AS src
    FROM need n, unnest(str_split(n.src_set, ',')) AS x(s)
    WHERE NOT EXISTS (
      SELECT 1 FROM search_fork_label l
      WHERE l.fork_key = n.fork_key AND l.src = trim(x.s, '{{}} ')
        AND coalesce(l.label, '') <> '')),
  srcs AS (
    SELECT fork_key, measure_ctx, src
    FROM (
      SELECT fork_key, measure_ctx, src,
             row_number() OVER (PARTITION BY fork_key ORDER BY src) AS rn
      FROM raw_srcs) z WHERE rn <= {src_chunk})"""


def branch_payload(batch: int = 1, src_chunk: int = 40) -> tuple[list, list]:
    sql = branch_need_sql(batch, src_chunk)
    pay = psql_json(
        sql
        + """
    SELECT to_json(list(struct_pack(fork_key := fork_key, measure := measure,
                                    sources := items)))
    FROM (SELECT s.fork_key, max(s.measure_ctx) AS measure,
                 list(struct_pack(src := s.src,
                                  title := coalesce(t.label, s.src),
                                  bestUsedFor := coalesce(a.best_used_for, ''))
                      ORDER BY s.src) AS items
          FROM srcs s
          LEFT JOIN search_tables t ON t.src_table = s.src
          LEFT JOIN search_entity_alias a ON a.src_table = s.src
          GROUP BY s.fork_key ORDER BY s.fork_key) z"""
    )
    flat = psql_json(
        sql + " SELECT to_json(list(struct_pack(fork_key := fork_key, src := src))) FROM srcs"
    )
    if isinstance(pay, dict):
        pay = [pay]
    if isinstance(flat, dict):
        flat = [flat]
    return pay or [], flat or []


def wiki_measure_payload(limit: int = 20) -> list:
    batch = limit
    sql = f"""
    WITH seed AS (
      SELECT f.src_table, t.emb FROM wiki_entity_facts f
      JOIN search_tables t ON t.src_table = f.src_table
      WHERE f.cls <> 'service'
        AND coalesce(f.measures,'') <> ''
        AND EXISTS (SELECT 1 FROM search_entity_alias a
                    WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
        AND NOT EXISTS (SELECT 1 FROM search_measure_alias m
                        WHERE m.src_table = f.src_table AND coalesce(m.aliases,'') <> '')
      ORDER BY f.src_table LIMIT 1)
    SELECT to_json(list(struct_pack(entity := src_table, title := label,
                                    quantities := coalesce(measures,''))))
    FROM (SELECT f.*, t.emb <=> (SELECT emb FROM seed) AS d
            FROM wiki_entity_facts f
            JOIN search_tables t ON t.src_table = f.src_table
           WHERE f.cls <> 'service'
             AND coalesce(f.measures,'') <> ''
             AND EXISTS (SELECT 1 FROM search_entity_alias a
                         WHERE a.src_table = f.src_table AND coalesce(a.aliases,'') <> '')
             AND NOT EXISTS (SELECT 1 FROM search_measure_alias m
                             WHERE m.src_table = f.src_table AND coalesce(m.aliases,'') <> '')
           ORDER BY d, f.src_table LIMIT {batch})"""
    pay = psql_json(sql)
    if isinstance(pay, dict):
        return [pay]
    return pay or []


def norm_name(s: str) -> str:
    return "".join(str(s).lower().split())


def branch_metrics(pay: list, rows: list, text: str) -> dict:
    expected = []
    titles = {}
    for rec in pay:
        fk = (rec.get("fork_key") or "").strip()
        for s in rec.get("sources") or []:
            src = (s.get("src") if isinstance(s, dict) else str(s)).strip()
            title = (s.get("title") if isinstance(s, dict) else "") or src
            if fk and src:
                expected.append((fk, src))
                titles[(fk, src)] = title
    got = {(r["fork_key"], r["src"]): r["label"] for r in rows}
    json_ok = bool(re.search(r"\{.*\}", text or "", re.S))
    nonempty = [k for k, v in got.items() if (v or "").strip()]
    echo = [k for k, v in got.items()
            if norm_name(v) == norm_name(titles.get(k, k[1]))]
    return {
        "json_ok": json_ok,
        "expected_src": len(expected),
        "covered_src": len([k for k in expected if k in got and got[k].strip()]),
        "nonempty": len(nonempty),
        "echo_name": len(echo),
        "parsed_rows": len(rows),
    }


def wiki_metrics(pay: list, ent_rows: list, meas_rows: list, text: str) -> dict:
    allowed = wap.allowed_quantities(pay)
    expected_q = sum(len(v) for v in allowed.values())
    got_q = len(meas_rows)
    json_ok = bool(re.search(r"\{.*\}", text or "", re.S))
    entities = {r["src_table"] for r in ent_rows if r.get("aliases")}
    return {
        "json_ok": json_ok,
        "entities": len(entities),
        "expected_quantities": expected_q,
        "covered_quantities": got_q,
        "measure_nonempty": sum(1 for r in meas_rows if (r.get("aliases") or "").strip()),
        "parsed_entities": len(ent_rows),
    }


def write_msg(head: str, payload, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = head + json.dumps(payload, ensure_ascii=False)
    path.write_text(body, encoding="utf-8")
    return len(body.encode("utf-8"))


def run_branch_case(
    run_dir: Path,
    tag: str,
    pay: list,
    *,
    gateway: bool = True,
    model: str | None = None,
    thinking: str = "off",
) -> dict:
    msg = run_dir / f"{tag}.msg"
    msg_bytes = write_msg(BRANCH_PROMPT_HEAD, pay, msg)
    resp, err, ms, ec = openclaw_agent(
        msg,
        session_key=f"alias-bench-{tag}-{int(time.time()*1000)}",
        model=model,
        thinking=thinking,
        local=not gateway,
        profile=None,
    )
    text = dig_text(resp)
    rows = bap.parse_labels(text, pay)
    if not rows and resp:
        rows = bap.parse_labels(json.dumps(resp, ensure_ascii=False), pay)
    usage = extract_usage(resp)
    metrics = branch_metrics(pay, rows, text)
    sample_labels = [
        {"fork_key": r["fork_key"], "src": r["src"], "label": r["label"]}
        for r in rows[:3]
    ]
    out = {
        "tag": tag,
        "kind": "branch",
        "gateway": gateway,
        "model": model or usage.get("model"),
        "thinking": thinking,
        "msg_bytes": msg_bytes,
        "exit": ec,
        "error": err[:500] if err else "",
        "ms": ms,
        "usage": usage,
        "metrics": metrics,
        "samples": sample_labels,
    }
    (run_dir / f"{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def run_wiki_case(
    run_dir: Path,
    tag: str,
    pay: list,
    *,
    gateway: bool = False,
    model: str | None = None,
    thinking: str = "off",
) -> dict:
    msg = run_dir / f"{tag}.msg"
    msg_bytes = write_msg(WIKI_PROMPT_HEAD, pay, msg)
    resp, err, ms, ec = openclaw_agent(
        msg,
        session_key=f"alias-bench-{tag}-{int(time.time()*1000)}",
        model=model,
        thinking=thinking,
        local=not gateway,
        profile=None,
    )
    text = dig_text(resp)
    ent_rows, meas_rows = wap.parse_items(text, pay)
    usage = extract_usage(resp)
    metrics = wiki_metrics(pay, ent_rows, meas_rows, text)
    samples = []
    for r in ent_rows[:2]:
        samples.append({"entity": r["src_table"], "aliases": r.get("aliases", "")[:120]})
    for r in meas_rows[:2]:
        samples.append({"entity": r["src_table"], "measure": r["measure"],
                        "aliases": r.get("aliases", "")[:80]})
    out = {
        "tag": tag,
        "kind": "wiki_measures",
        "gateway": gateway,
        "model": model or usage.get("model"),
        "thinking": thinking,
        "msg_bytes": msg_bytes,
        "exit": ec,
        "error": err[:500] if err else "",
        "ms": ms,
        "usage": usage,
        "metrics": metrics,
        "samples": samples,
    }
    (run_dir / f"{tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def mode_overhead(run_dir: Path) -> dict:
    ctrl_msg = run_dir / "control.msg"
    ctrl_msg.write_text('JSON only: {"ping":"pong"}', encoding="utf-8")
    ctrl_resp, ctrl_err, ctrl_ms, ctrl_ec = openclaw_agent(
        ctrl_msg,
        session_key=f"alias-bench-ctrl-{int(time.time()*1000)}",
        thinking="off",
        local=False,
    )
    pay, _ = branch_payload(1, 40)
    branch = run_branch_case(run_dir, "branch_chunk40", pay, gateway=True, thinking="off")
    ctrl_usage = extract_usage(ctrl_resp)
    return {
        "control": {
            "msg_bytes": len(ctrl_msg.read_bytes()),
            "exit": ctrl_ec,
            "error": ctrl_err[:300] if ctrl_err else "",
            "ms": ctrl_ms,
            "usage": ctrl_usage,
        },
        "branch_chunk40": branch,
        "overhead_input_est": (ctrl_usage.get("input") or 0),
        "payload_input_est": (branch.get("usage") or {}).get("input", 0),
    }


def mode_thinking(run_dir: Path) -> dict:
    pay, _ = branch_payload(1, 40)
    off = run_branch_case(run_dir, "think_off", pay, gateway=True, thinking="off")
    hi_resp, hi_err, hi_ms, hi_ec = openclaw_agent(
        run_dir / "think_off.msg",
        session_key=f"alias-bench-think-hi-{int(time.time()*1000)}",
        thinking="high",
        local=False,
    )
    hi = {
        "thinking": "high",
        "exit": hi_ec,
        "error": hi_err[:500] if hi_err else "",
        "ms": hi_ms,
        "usage": extract_usage(hi_resp),
    }
    (run_dir / "think_high.json").write_text(json.dumps(hi, ensure_ascii=False, indent=2))
    return {"off": off, "high_attempt": hi}


def mode_ab(run_dir: Path, n_chunks: int = 8) -> dict:
    results = {"branch": [], "wiki": []}
    # branch: несколько чанков — сдвигаем окно по fork_key
    for i in range(n_chunks):
        pay, _ = branch_payload(batch=1, src_chunk=40)
        if not pay:
            break
        for model in ("deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-pro"):
            tag = f"branch_{i}_{model.split('/')[-1]}"
            results["branch"].append(
                run_branch_case(run_dir, tag, pay, gateway=False, model=model, thinking="off")
            )
        # пометить первый src класса как attempt чтобы следующий чанк другой
        # (упрощение: используем OFFSET через временную метку в fork_key не меняя БД —
        #  для разнообразия берём batch=i+1 через SQL LIMIT/OFFSET)
    # Пересборка с OFFSET
    results["branch"] = []
    for i in range(n_chunks):
        sql = branch_need_sql(1, 40).replace(
            "ORDER BY c.fork_key LIMIT 1",
            f"ORDER BY c.fork_key LIMIT 1 OFFSET {i}",
        )
        pay = psql_json(
            sql
            + """
    SELECT to_json(list(struct_pack(fork_key := fork_key, measure := measure,
                                    sources := items)))
    FROM (SELECT s.fork_key, max(s.measure_ctx) AS measure,
                 list(struct_pack(src := s.src,
                                  title := coalesce(t.label, s.src),
                                  bestUsedFor := coalesce(a.best_used_for, ''))
                      ORDER BY s.src) AS items
          FROM srcs s
          LEFT JOIN search_tables t ON t.src_table = s.src
          LEFT JOIN search_entity_alias a ON a.src_table = s.src
          GROUP BY s.fork_key ORDER BY s.fork_key) z"""
        )
        if not pay:
            break
        if isinstance(pay, dict):
            pay = [pay]
        for model in ("deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-pro"):
            tag = f"branch_{i}_{model.split('/')[-1]}"
            results["branch"].append(
                run_branch_case(run_dir, tag, pay, gateway=False, model=model, thinking="off")
            )
    for wi in range(2):
        pay = wiki_measure_payload(20)
        if not pay:
            break
        for model in ("deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-pro"):
            tag = f"wiki_{wi}_{model.split('/')[-1]}"
            results["wiki"].append(
                run_wiki_case(run_dir, tag, pay, gateway=False, model=model, thinking="off")
            )
    return summarize_ab(results)


def summarize_ab(results: dict) -> dict:
    def agg(items, kind):
        by = {}
        for it in items:
            m = it.get("model") or "?"
            by.setdefault(m, []).append(it)
        rows = []
        for model, lst in by.items():
            u_in = [x["usage"].get("input") or 0 for x in lst if x.get("usage")]
            u_out = [x["usage"].get("output") or 0 for x in lst if x.get("usage")]
            ms = [x.get("ms") or 0 for x in lst]
            if kind == "branch":
                cov = [x["metrics"].get("covered_src", 0) for x in lst]
                exp = [x["metrics"].get("expected_src", 1) for x in lst]
                echo = [x["metrics"].get("echo_name", 0) for x in lst]
                json_ok = sum(1 for x in lst if x["metrics"].get("json_ok"))
            else:
                cov = [x["metrics"].get("covered_quantities", 0) for x in lst]
                exp = [x["metrics"].get("expected_quantities", 1) for x in lst]
                echo = [0] * len(lst)
                json_ok = sum(1 for x in lst if x["metrics"].get("json_ok"))
            rows.append({
                "model": model,
                "n": len(lst),
                "json_ok": json_ok,
                "avg_in": round(sum(u_in) / len(u_in), 1) if u_in else None,
                "avg_out": round(sum(u_out) / len(u_out), 1) if u_out else None,
                "avg_ms": round(sum(ms) / len(ms)) if ms else None,
                "coverage_pct": round(100 * sum(cov) / max(sum(exp), 1), 1),
                "echo_name": sum(echo),
            })
        return rows
    summary = {
        "branch": agg(results["branch"], "branch"),
        "wiki": agg(results["wiki"], "wiki"),
        "raw": results,
    }
    bf = summary["branch"]
    wf = summary["wiki"]
    flash_b = next((r for r in bf if "flash" in r["model"]), None)
    pro_b = next((r for r in bf if "pro" in r["model"]), None)
    flash_w = next((r for r in wf if "flash" in r["model"]), None)
    pro_w = next((r for r in wf if "pro" in r["model"]), None)
    if flash_b and pro_b:
        branch_ok = (
            flash_b["coverage_pct"] >= pro_b["coverage_pct"]
            and flash_b["echo_name"] <= pro_b["echo_name"]
        )
        wiki_ok = True
        if flash_w and pro_w:
            wiki_ok = (
                flash_w["coverage_pct"] >= pro_w["coverage_pct"]
                and flash_w["echo_name"] <= pro_w["echo_name"]
            )
        winner = "flash" if branch_ok and wiki_ok else "pro"
        summary["decision"] = {
            "winner": winner,
            "branch_ok": branch_ok,
            "wiki_ok": wiki_ok,
            "flash_branch": flash_b,
            "pro_branch": pro_b,
            "flash_wiki": flash_w,
            "pro_wiki": pro_w,
        }
    return summary


def mode_qwen_ab(run_dir: Path, n_chunks: int = 5) -> dict:
    """A/B vLLM vs baseline pro (5 branch + 2 wiki), через production gateway."""
    results = {"branch": [], "wiki": []}
    for i in range(n_chunks):
        sql = branch_need_sql(1, 40).replace(
            "ORDER BY c.fork_key LIMIT 1",
            f"ORDER BY c.fork_key LIMIT 1 OFFSET {i}",
        )
        pay = psql_json(
            sql
            + """
    SELECT to_json(list(struct_pack(fork_key := fork_key, measure := measure,
                                    sources := items)))
    FROM (SELECT s.fork_key, max(s.measure_ctx) AS measure,
                 list(struct_pack(src := s.src,
                                  title := coalesce(t.label, s.src),
                                  bestUsedFor := coalesce(a.best_used_for, ''))
                      ORDER BY s.src) AS items
          FROM srcs s
          LEFT JOIN search_tables t ON t.src_table = s.src
          LEFT JOIN search_entity_alias a ON a.src_table = s.src
          GROUP BY s.fork_key ORDER BY s.fork_key) z"""
        )
        if not pay:
            break
        if isinstance(pay, dict):
            pay = [pay]
        for model in ("vllm/Qwen3.8-27B", "deepseek/deepseek-v4-pro"):
            tag = f"branch_{i}_{model.split('/')[-1].replace('.', '_')}"
            results["branch"].append(
                run_branch_case(run_dir, tag, pay, gateway=True, model=model, thinking="off")
            )
    for wi in range(2):
        pay = wiki_measure_payload(20)
        if not pay:
            break
        for model in ("vllm/Qwen3.8-27B", "deepseek/deepseek-v4-pro"):
            tag = f"wiki_{wi}_{model.split('/')[-1].replace('.', '_')}"
            results["wiki"].append(
                run_wiki_case(run_dir, tag, pay, gateway=True, model=model, thinking="off")
            )
    return summarize_ab(results)


def main() -> int:
    mode = os.environ.get("ALIAS_BENCH_MODE", "overhead")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(os.environ.get("ALIAS_BENCH_DIR") or (OUT / f"alias-agent-bench-{stamp}"))
    run_dir.mkdir(parents=True, exist_ok=True)
    report = {"mode": mode, "run_dir": str(run_dir), "dsn_db": dsn().split("dbname=")[-1]}
    if mode == "overhead":
        report["result"] = mode_overhead(run_dir)
    elif mode == "thinking":
        report["result"] = mode_thinking(run_dir)
    elif mode == "ab":
        n = int(os.environ.get("ALIAS_BENCH_CHUNKS", "8"))
        report["result"] = mode_ab(run_dir, n)
    elif mode == "qwen_ab":
        n = int(os.environ.get("ALIAS_BENCH_CHUNKS", "5"))
        report["result"] = mode_qwen_ab(run_dir, n)
    else:
        print(f"unknown mode {mode}", file=sys.stderr)
        return 2
    out_path = run_dir / "summary.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
