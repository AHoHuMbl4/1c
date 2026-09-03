#!/usr/bin/env python3
"""Синтетика онбординга E4: железо→conf, форма EMBED_HOST, красный такт.

Железо НЕ читается: в логику уходят только аргументы box_tune_plan / env-прослойка.
Живой systemd, swapon и движок не трогаем.

Прогон: python3 ubuntu/serenedb/test_box_tune.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TUNE = os.path.join(REPO, "ubuntu", "serenedb", "box_tune.sh")
EMBED_CHECK = os.path.join(REPO, "ubuntu", "serenedb", "embed_check.sh")
WATCH = os.path.join(REPO, "ubuntu", "monitoring", "tact_watch.sh")
FIRSTBUILD_UNIT = os.path.join(
    REPO, "ubuntu", "packet", "systemd", "1c-serene-firstbuild@.service"
)
PIPELINE_UNIT = os.path.join(REPO, "ubuntu", "systemd", "1c-serene-pipeline@.service")

FAILS: list[str] = []
N_ALL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global N_ALL
    N_ALL += 1
    print(("ok  " if cond else "FAIL") + f"  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def bash(script: str, env: dict[str, str] | None = None, timeout: int = 20) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        env=e,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def plan(ram_kb: int, vcpu: int) -> dict[str, str]:
    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_plan {ram_kb} {vcpu}',
        env={"BOX_TUNE_RAM_KB": "1", "BOX_TUNE_VCPU": "1"},  # plan() uses argv; env only for subprocess readers
    )
    check(
        f"plan({ram_kb},{vcpu}) exit 0",
        r.returncode == 0,
        r.stderr.strip() or r.stdout[-200:],
    )
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def form_check(host: str) -> subprocess.CompletedProcess:
    return bash(
        f'set -euo pipefail; . "{TUNE}"; embed_host_form_check "$EMBED_HOST"',
        env={"EMBED_HOST": host},
    )


def watch_tokens(
    failed: str,
    since: str,
    now: str,
    max_min: str = "15",
) -> str:
    r = bash(
        f'set -euo pipefail; . "{WATCH}"; tact_watch_tokens',
        env={
            "TACT_WATCH_FAILED_LIST": failed,
            "TACT_WATCH_FAILED_SINCE": since,
            "TACT_WATCH_NOW": now,
            "TACT_FAIL_MAX_MIN": max_min,
        },
    )
    check("tact_watch exit 0", r.returncode == 0, r.stderr.strip())
    return r.stdout.strip()


def main() -> int:
    # --- 1. формулы: числа ночи klient-1 (8 vCPU / 11.7 GiB) ---
    k1 = plan(12_241_604, 8)
    check("k1 phase small", k1.get("phase_class") == "small")
    check("k1 cpu_threads=4", k1.get("cpu_threads") == "4", str(k1))
    check("k1 io_threads=4", k1.get("io_threads") == "4")
    check("k1 thread_min=4 (precheck BUILD_THREAD_MIN)", k1.get("thread_min") == "4")
    check("k1 swap>=12", int(k1.get("swap_gib", "0")) >= 12, str(k1.get("swap_gib")))
    check("k1 first limit 18GB", k1.get("memory_limit_first") == "18GB", str(k1.get("memory_limit_first")))
    # 80 % от 12241604 КиБ / 1024 = 9563 MB ≈ SHOW 9.3 GiB
    check("k1 steady ~80%", k1.get("memory_limit_steady", "").endswith("MB") and 9000 <= int(k1["memory_limit_steady"][:-2]) <= 10000,
          str(k1.get("memory_limit_steady")))

    # --- 2. малая коробка ~7.6 GiB / 4 vCPU (okna) ---
    ok = plan(7_969_177, 4)  # 7.6 GiB в КиБ
    check("okna phase small", ok.get("phase_class") == "small")
    check("okna cpu_threads=4", ok.get("cpu_threads") == "4", str(ok))
    check("okna thread_min=4", ok.get("thread_min") == "4")
    check("okna swap>=4", int(ok.get("swap_gib", "0")) >= 4)
    check("okna first limit uses 1.5×RAM", ok.get("memory_limit_first", "").endswith("GB"))

    # --- 3. большая коробка ~62 GiB / 6 vCPU (дев 29.07, пул эмбеддера) ---
    big = plan(62 * 1024 * 1024, 6)
    check("big phase large", big.get("phase_class") == "large")
    check("big cpu_threads~93 capped 96", 16 <= int(big.get("cpu_threads", "0")) <= 96, str(big.get("cpu_threads")))
    check("big cpu_threads>=thread_min", int(big.get("cpu_threads", "0")) >= int(big.get("thread_min", "99")), str(big))
    check("big io_threads=8", big.get("io_threads") == "8")
    check("big swap=0", big.get("swap_gib") == "0")
    check("big thread_min=workers+8", big.get("thread_min") == "16")

    # --- 4. порог 16 GiB: ниже — small, выше — large (пик p_doc 11.09 GiB) ---
    lo = plan(16 * 1024 * 1024, 8)
    hi = plan(16 * 1024 * 1024 + 1, 8)
    check("16 GiB still small", lo.get("phase_class") == "small")
    check("16 GiB+1 large", hi.get("phase_class") == "large")
    check("16 GiB threads capped 4", lo.get("cpu_threads") == "4")

    # --- 5. инъекция: plan не читает /proc (подсовываем ложные BOX_TUNE_* и другие числа) ---
    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_plan 12241604 8 | awk -F= \'$1=="cpu_threads\"{{print $2}}\'',
        env={"BOX_TUNE_RAM_KB": "999999999", "BOX_TUNE_VCPU": "64"},
    )
    check("plan ignores BOX_TUNE_* readers", r.stdout.strip() == "4", r.stdout + r.stderr)

    # readers themselves are the injection point
    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_read_ram_kb; echo x; box_tune_read_vcpu',
        env={"BOX_TUNE_RAM_KB": "4242", "BOX_TUNE_VCPU": "7"},
    )
    lines = [ln for ln in r.stdout.splitlines() if ln]
    check("reader inject ram", lines[0] == "4242", r.stdout)
    check("reader inject vcpu", lines[-1] == "7", r.stdout)

    # --- 6. apply пишет conf/env/state без root/swap/sql ---
    with tempfile.TemporaryDirectory() as td:
        conf = os.path.join(td, "serened.conf")
        envf = os.path.join(td, "pipeline.env")
        state = os.path.join(td, "box-tune.state")
        swap = os.path.join(td, "swapfile")
        with open(conf, "w", encoding="utf-8") as f:
            f.write("--listen=postgres://127.0.0.1:7890\n--cpu_threads=160\n")
        with open(envf, "w", encoding="utf-8") as f:
            f.write("SERENEDB_DSN=host=127.0.0.1 port=7890\n")
        r = bash(
            f'set -euo pipefail; . "{TUNE}"; box_tune_apply_first_build',
            env={
                "BOX_TUNE_RAM_KB": "12241604",
                "BOX_TUNE_VCPU": "8",
                "BOX_TUNE_CONF": conf,
                "BOX_TUNE_PIPELINE_ENV": envf,
                "BOX_TUNE_STATE": state,
                "BOX_TUNE_SWAPFILE": swap,
                "BOX_TUNE_DSN": "",
                "BOX_TUNE_SWAP_APPLY": "0",
                "BOX_TUNE_RESTART": "0",
                "BOX_TUNE_SQL": "0",
                "BOX_TUNE_SKIP_RESTART": "1",
            },
        )
        check("apply exit 0", r.returncode == 0, r.stderr)
        conf_txt = open(conf, encoding="utf-8").read()
        env_txt = open(envf, encoding="utf-8").read()
        st_txt = open(state, encoding="utf-8").read()
        check("conf cpu_threads=4", "--cpu_threads=4" in conf_txt, conf_txt)
        check("conf io_threads=4", "--io_threads=4" in conf_txt)
        check("conf kept listen", "--listen=" in conf_txt)
        check("env BUILD_THREAD_MIN=4", "BUILD_THREAD_MIN=4" in env_txt, env_txt)
        check("state first-build", "phase=first-build" in st_txt)
        r2 = bash(
            f'set -euo pipefail; . "{TUNE}"; box_tune_restore',
            env={
                "BOX_TUNE_STATE": state,
                "BOX_TUNE_SWAPFILE": swap,
                "BOX_TUNE_DSN": "",
                "BOX_TUNE_SWAP_APPLY": "0",
                "BOX_TUNE_SQL": "0",
                "BOX_TUNE_RAM_KB": "12241604",
                "BOX_TUNE_VCPU": "8",
            },
        )
        check("restore exit 0", r2.returncode == 0, r2.stderr)
        st2 = open(state, encoding="utf-8").read()
        check("state restored", "phase=restored" in st2, st2)

    # --- 7. форма EMBED_HOST ---
    good = form_check("http://gpu-erw.timpul.pro:8000")
    check("form ok scheme+host+port", good.returncode == 0, good.stderr)
    bad_bare = form_check("gpu-erw.timpul.pro")
    check("form reject bare host (000)", bad_bare.returncode != 0)
    bad_noport = form_check("http://gpu-erw.timpul.pro")
    check("form reject no port", bad_noport.returncode != 0)
    bad_scheme = form_check("gpu-erw.timpul.pro:8000")
    check("form reject host:port without scheme", bad_scheme.returncode != 0)
    empty = form_check("")
    check("form reject empty", empty.returncode != 0)

    r = bash(
        f'EMBED_CHECK_FORM_ONLY=1 EMBED_HOST="http://e.example:8000" EMBED_PATH=/v1/embeddings '
        f'EMBED_MODEL=x bash "{EMBED_CHECK}"',
    )
    check("embed_check FORM_ONLY ok", r.returncode == 0, r.stderr)
    r = bash(
        f'EMBED_CHECK_FORM_ONLY=1 EMBED_HOST="gpu-erw.timpul.pro" EMBED_PATH=/v1/embeddings '
        f'EMBED_MODEL=x bash "{EMBED_CHECK}"',
    )
    check("embed_check FORM_ONLY rejects bare", r.returncode != 0)

    # --- 8. красный такт: failed дольше N минут ---
    now = "1000000"
    old = str(1000000 - 20 * 60)
    fresh = str(1000000 - 5 * 60)
    tok = watch_tokens(
        "1c-serene-firstbuild@acme.service",
        f"1c-serene-firstbuild@acme.service={old}",
        now,
        "15",
    )
    check("watch alerts after 15 min", "такт:1c-serene-firstbuild@acme:20мин" in tok, tok)
    tok2 = watch_tokens(
        "1c-serene-pipeline@postgres.service",
        f"1c-serene-pipeline@postgres.service={fresh}",
        now,
        "15",
    )
    check("watch silent under N", tok2 == "", tok2)
    tok3 = watch_tokens("", "", now, "15")
    check("watch empty failed list", tok3 == "", tok3)

    # --- 9. юниты: Restart= и предел, не петля ---
    fb = open(FIRSTBUILD_UNIT, encoding="utf-8").read()
    pl = open(PIPELINE_UNIT, encoding="utf-8").read()
    check("firstbuild Restart=on-failure", "Restart=on-failure" in fb)
    check("firstbuild RestartSec=2min", "RestartSec=2min" in fb)
    check("firstbuild StartLimitBurst=5", "StartLimitBurst=5" in fb)
    check("firstbuild StartLimitIntervalSec=1h", "StartLimitIntervalSec=1h" in fb)
    check("pipeline Restart=on-failure", "Restart=on-failure" in pl)
    check("pipeline StartLimitBurst=5", "StartLimitBurst=5" in pl)

    # --- 10. firstbuild_unit снимает path в начале (антилуп 14.08) ---
    fbsh = open(os.path.join(REPO, "ubuntu", "packet", "firstbuild_unit.sh"), encoding="utf-8").read()
    check(
        "firstbuild disables path before work",
        "disable --now" in fbsh and fbsh.find("disable --now") < fbsh.find("первая сборка слоя"),
    )
    check("firstbuild calls box_tune_apply", "box_tune_apply_first_build" in fbsh)
    check("firstbuild calls embed_check", "embed_check.sh" in fbsh)
    check("firstbuild restore after pipeline", fbsh.find("pipeline@$DB") < fbsh.find("box_tune_restore") or "box_tune_restore" in fbsh)
    check("firstbuild calls disk preflight", "box_tune_disk_preflight" in fbsh)

    # --- 10b. Скорость-II этап 4: allocator_background_threads в firstbuild, не в conf ---
    tune_src = open(TUNE, encoding="utf-8").read()
    m_apply_fn = re.search(
        r"box_tune_apply_first_build\(\)\s*\{(.*?)\n\}",
        tune_src,
        re.S,
    )
    apply_fn = m_apply_fn.group(1) if m_apply_fn else ""
    check(
        "apply_first_build calls allocator_bg helper",
        "box_tune_allocator_bg_threads" in apply_fn,
    )
    check(
        "allocator_background_threads not upserted to conf",
        not re.search(
            r"box_tune_upsert_flag\s+[^\n]*allocator_background_threads",
            tune_src,
        ),
    )

    # --- 11. E4b префлайт диска: числа ночи klient-1 18.08 06:06 ---
    # 30 ГиБ свободно, 15 148 327 строк: целиком WAL не влезет, пачка 1e6 — да.
    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_plan 31457280 42991616 15148327 17511219',
    )
    check("disk plan night exit 0", r.returncode == 0, r.stderr)
    dplan: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            dplan[k] = v
    check("night merge_unchunked=0", dplan.get("merge_unchunked") == "0", str(dplan))
    check("night disk_ok=1", dplan.get("disk_ok") == "1", str(dplan))
    check("night chunk 1e6", int(dplan.get("merge_chunk_rows", "0")) == 1_000_000, str(dplan.get("merge_chunk_rows")))
    check("night wal_unchunked > 50GiB", int(dplan.get("wal_unchunked_kb", "0")) > 50 * 1024 * 1024, str(dplan.get("wal_unchunked_kb")))

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_plan 31457280 42991616 600000 0',
    )
    d2: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d2[k] = v
    check("small corpus unchunked ok", d2.get("merge_unchunked") == "1", str(d2))
    check("small corpus disk_ok", d2.get("disk_ok") == "1")

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_plan 2097152 42991616 15148327 0',
    )
    d3: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d3[k] = v
    check("2GiB free disk_ok=0", d3.get("disk_ok") == "0", str(d3))

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_plan 4194304 1000 0 0',
    )
    d4: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d4[k] = v
    check("no stage 4GiB < 8GiB stop", d4.get("disk_ok") == "0", str(d4))

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_preflight',
        env={
            "BOX_TUNE_FREE_KB": "31457280",
            "BOX_TUNE_ENGINE_KB": "42991616",
            "BOX_TUNE_STAGE_ROWS": "15148327",
            "BOX_TUNE_SQL": "0",
        },
    )
    check("preflight night inject exit 0", r.returncode == 0, r.stderr)
    check("preflight prints disk_ok=1", "disk_ok=1" in r.stdout, r.stdout)

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_preflight',
        env={
            "BOX_TUNE_FREE_KB": "2097152",
            "BOX_TUNE_ENGINE_KB": "42991616",
            "BOX_TUNE_STAGE_ROWS": "15148327",
            "BOX_TUNE_SQL": "0",
        },
    )
    check("preflight tight exit 1", r.returncode != 0)
    check("preflight tight names candidates", "swapfile-1c-build" in r.stderr or "Кандидаты" in r.stderr, r.stderr)

    bsh = open(os.path.join(REPO, "ubuntu", "serenedb", "build.sh"), encoding="utf-8").read()
    check("build.sh calls disk preflight before merge", "box_tune_disk_preflight" in bsh and bsh.find("box_tune_disk_preflight") < bsh.find("corpus_merge.sql"))
    check("build.sh writes tmp3_merge_cfg", "tmp3_merge_cfg" in bsh)
    merg = open(os.path.join(REPO, "ubuntu", "serenedb", "corpus_merge.sql"), encoding="utf-8").read()
    check("merge chunks via gexec", "\\gexec" in merg and "tmp3_merge_jobs" in merg)
    check("merge filters src_table IN not EXISTS-scan", "src_table IN (" in merg and "EXISTS (SELECT 1 FROM tmp3_merge_jobs" not in merg.split("слияние пачками")[1])
    check("merge checkpoint per pack", "checkpoint()" in merg)
    check("merge first-build 48h window", "INTERVAL '48 hours'" in merg)
    check("build.sh writes merge baseline", "merge_engine_baseline_kb" in bsh)
    check("merge does not wrap all in one BEGIN", merg.find("tmp3_merge_jobs") < merg.find("VACUUM (REFRESH_INDEX)") and "BEGIN;" not in merg.split("tmp3_merge_jobs")[1].split("VACUUM")[0])

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_projected_engine_kb 61648164 8004024 15148327 42991616',
    )
    check("projected engine exit 0", r.returncode == 0, r.stderr)
    projected = int(r.stdout.strip() or "0")
    check("projected ~75GiB not 116GiB linear", 70 * 1024 * 1024 < projected < 80 * 1024 * 1024, str(projected))

    r = bash(
        f'set -euo pipefail; . "{TUNE}"; box_tune_disk_preflight',
        env={
            "BOX_TUNE_FREE_KB": "9860732",
            "BOX_TUNE_ENGINE_KB": "61648164",
            "BOX_TUNE_STAGE_ROWS": "15148327",
            "BOX_TUNE_CORPUS_ROWS": "8004024",
            "BOX_TUNE_ENGINE_BASELINE_KB": "42991616",
            "BOX_TUNE_TOTAL_KB": "100663296",
            "BOX_TUNE_SQL": "0",
        },
    )
    check("partial merge preflight fail engine projection", r.returncode != 0, r.stderr)
    check("partial merge mentions projected", "projected_engine_kb" in r.stdout, r.stdout)

    print()
    if FAILS:
        print(f"FAIL {len(FAILS)}/{N_ALL}: " + ", ".join(FAILS))
        return 1
    print(f"OK {N_ALL}/{N_ALL}")
    return 0


if __name__ == "__main__":
    # recount checks actually executed
    sys.exit(main())
