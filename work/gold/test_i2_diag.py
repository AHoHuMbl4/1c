#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I0-П2: i2_runner пишет wiki-подмножество diag в jsonl (без сети)."""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import i2_runner as I2  # noqa: E402

PASS, FAIL = 0, []


def t(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


def main() -> int:
    diag = {
        "wiki_pool": ["catalog_a", "catalog_b"],
        "wiki_pick": "catalog_a",
        "wiki_verify": "catalog_a",
        "wiki_verify_yes": 1,
        "wiki_verify_no": 1,
        "wiki_verify_unsure": 0,
        "wiki_verdicts": [
            {"i": 1, "fit": "yes", "why": "ok"},
            {"i": 2, "fit": "no", "why": "no"},
        ],
        "wiki_empty_pool": False,
        "wiki_attempted": True,
        "wiki_verify_n": 2,
        "wiki_verify_truncated": 0,
        "wiki_verify_error": 1,
        "wiki_none": "verify_none",
        "wiki_homonym_tie": ["catalog_b"],
        "wiki_verify_confirm": "agree",
        "wiki_verify2_yes": 1,
        "wiki_verify2_no": 1,
        "wiki_verify2_unsure": 0,
        "wiki_verify2_error": 0,
        "wiki_verify2_truncated": 0,
        "wiki_verdicts2": [{"i": 1, "fit": "yes", "why": "ok2"}],
        "found": 1,
        "doubt": False,
        "terms": ["noise"],
        "шаги": [{"шаг": "noise"}],
    }
    slice_ = I2.wiki_diag_slice(diag)
    t("wiki_diag_slice only wiki keys",
      set(slice_) <= set(I2._I2_WIKI_DIAG_KEYS)
      and "terms" not in slice_ and "шаги" not in slice_
      and slice_.get("wiki_pick") == "catalog_a"
      and len(slice_.get("wiki_verdicts") or []) == 2)
    t("wiki_diag_slice optional wiki_leader absent",
      "wiki_leader" not in slice_)
    t("wiki_diag_slice carries observability keys",
      slice_.get("wiki_attempted") is True
      and slice_.get("wiki_verify_n") == 2
      and slice_.get("wiki_verify_error") == 1
      and slice_.get("wiki_none") == "verify_none"
      and slice_.get("wiki_homonym_tie") == ["catalog_b"])
    t("wiki_diag_slice carries P2b confirm keys",
      slice_.get("wiki_verify_confirm") == "agree"
      and slice_.get("wiki_verify2_yes") == 1
      and slice_.get("wiki_verify2_no") == 1
      and slice_.get("wiki_verdicts2") == [{"i": 1, "fit": "yes", "why": "ok2"}]
      and "wiki_verify2_error" in slice_
      and "wiki_verify2_truncated" in slice_)
    t("wiki_diag_slice empty on junk",
      I2.wiki_diag_slice(None) == {} and I2.wiki_diag_slice({}) == {})

    ans = I2.PathAnswer(
        path=I2.PATH_ENGINE,
        text="Итого 5.",
        kind="answer",
        diag=diag,
        nums=[5.0],
        latency_s=0.1,
        verdict=I2.VERDICT_MATCH,
    )
    fields = I2.path_answer_jsonl_fields(ans)
    t("jsonl fields keep legacy keys",
      fields.get("verdict") == I2.VERDICT_MATCH
      and fields.get("kind") == "answer"
      and "text" in fields and "nums" in fields)
    t("jsonl fields carry wiki subset",
      isinstance(fields.get("wiki"), dict)
      and fields["wiki"].get("wiki_verify_yes") == 1
      and fields["wiki"].get("wiki_attempted") is True
      and fields["wiki"].get("wiki_verify_error") == 1
      and "terms" not in fields["wiki"])
    t("jsonl fields carry doubt/found",
      fields.get("found") == 1 and fields.get("doubt") is False)

    web_ans = I2.PathAnswer(
        path=I2.PATH_WEB,
        text="Итого 5.",
        kind="answer",
        diag=diag,
        nums=[5.0],
        latency_s=0.2,
        verdict=I2.VERDICT_MATCH,
    )
    row = I2.QuestionRow(
        question="сколько?", etalon="5", engine=ans, web=web_ans)
    with tempfile.TemporaryDirectory() as td:
        I2.run_i2(
            [row], paths=[I2.PATH_ENGINE, I2.PATH_WEB],
            engine_ask=lambda q: ans,
            web_ask=lambda q: web_ans,
            out_dir=td, workers=1)
        jl = os.path.join(td, "i2-answers.jsonl")
        t("jsonl file written", os.path.isfile(jl))
        line = open(jl, encoding="utf-8").readline()
        rec = json.loads(line)
        eng = rec.get("engine") or {}
        t("jsonl engine.wiki present",
          isinstance(eng.get("wiki"), dict)
          and eng["wiki"].get("wiki_pool") == ["catalog_a", "catalog_b"]
          and eng["wiki"].get("wiki_attempted") is True
          and eng["wiki"].get("wiki_verify_n") == 2
          and eng["wiki"].get("wiki_verify_error") == 1
          and eng.get("found") == 1
          and eng.get("doubt") is False,
          eng)
        web = rec.get("web") or {}
        t("jsonl web drops kind (legacy filter)",
          "kind" not in web
          and set(web) <= {
              "verdict", "text", "nums", "latency_s", "error",
              "wiki", "doubt", "found",
          },
          web)
        t("jsonl web keeps wiki subset",
          isinstance(web.get("wiki"), dict)
          and web["wiki"].get("wiki_verify_error") == 1)

    print("---", PASS, "ok,", len(FAIL), "fail")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
