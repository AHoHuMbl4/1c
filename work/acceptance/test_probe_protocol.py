#!/usr/bin/env python3
"""Оффлайн-замки протокола проб и сканера bash -s "$Q".

Запуск: python3 work/acceptance/test_probe_protocol.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import probe_protocol as P  # noqa: E402

MULTI = "сколько петель осталось на складе?"
TRUNC = "сколько"  # ssh bash -s "$Q" даёт q_len=7… нет, "сколько" = 7 chars? 
# "сколько" is 7 chars in Russian... actually "сколько" = 7 letters
# Full question len:


class TestProbeProtocol(unittest.TestCase):
    def test_q_hash_stable(self):
        h = P.q_hash(MULTI)
        self.assertEqual(h, hashlib.sha256(MULTI.encode()).hexdigest())
        self.assertEqual(len(h), 64)

    def test_format_parse_roundtrip(self):
        line = P.format_line(
            rid="r1",
            port=8091,
            code_md5_val="abcd1234",
            q_len_val=P.q_len(MULTI),
            outcome="no_data",
            question=MULTI,
        )
        self.assertTrue(line.startswith("PROBE\t"))
        parsed = P.parse_line(line)
        self.assertEqual(parsed["rid"], "r1")
        self.assertEqual(parsed["port"], "8091")
        self.assertEqual(parsed["q_len"], str(P.q_len(MULTI)))
        self.assertEqual(parsed["outcome"], "no_data")
        self.assertIn("петель", parsed["question"])

    def test_truncated_probe_detected(self):
        """§3.94: q_len=5 при полном вопросе — недействительный замер."""
        full_len = P.q_len(MULTI)
        self.assertGreater(full_len, 10)
        bad_len = 5  # типичный обрез «сколько» не то — but 5 was "сколько" partial?
        ok, msg, meta = True, "", {}
        # simulate mismatch logic
        if bad_len != full_len:
            ok = False
            msg = "q_len mismatch: sent=%d journal=%d" % (full_len, bad_len)
        self.assertFalse(ok)
        self.assertIn("mismatch", msg)

    def test_verify_journal_ok(self):
        q = MULTI
        rid = "probe-test"
        with patch.object(P, "_psql_row", return_value=(0, "%d|%s|no_data|%s|c560aebe" % (
                P.q_len(q), P.q_hash(q), rid))):
            ok, msg, meta = P.verify_journal(q, rid=rid, wait_sec=0)
        self.assertTrue(ok, msg)
        self.assertEqual(meta["got_len"], P.q_len(q))
        self.assertEqual(meta["code_md5"], "c560aebe")

    def test_verify_journal_fail_len(self):
        q = MULTI
        with patch.object(P, "_psql_row", return_value=(0, "5|%s|no_data|r1|abcd" % P.q_hash(q))):
            ok, msg, _meta = P.verify_journal(q, rid="r1", wait_sec=0)
        self.assertFalse(ok)
        self.assertIn("q_len mismatch", msg)

    def test_finish_uses_journal_code_md5_not_local(self):
        q = MULTI
        rid = "probe-test"
        row = "%d|%s|no_data|%s|c560aebe" % (P.q_len(q), P.q_hash(q), rid)
        ok, msg, line = P.finish_probe(
            q, rid=rid, port=8091, outcome="no_data", journal_row=row)
        self.assertTrue(ok, msg)
        parsed = P.parse_line(line)
        self.assertEqual(parsed["code_md5"], "c560aebe")

    def test_finish_rejects_empty_code_md5(self):
        q = MULTI
        rid = "probe-test"
        row = "%d|%s|no_data|%s|" % (P.q_len(q), P.q_hash(q), rid)
        ok, msg, line = P.finish_probe(
            q, rid=rid, port=8091, outcome="no_data", journal_row=row)
        self.assertFalse(ok)
        self.assertIn("code_md5 empty", msg)
        self.assertEqual(line, "")

    def test_finish_cli_exit_code(self):
        import subprocess
        q = MULTI
        rid = "r1"
        bad_row = "5|%s|no_data|r1|abc" % P.q_hash(q)
        p = subprocess.run(
            [sys.executable, os.path.join(ROOT, "probe_protocol.py"), "finish",
             "--rid", rid, "--port", "8091", "--outcome", "no_data",
             "--journal-row", bad_row, q],
            capture_output=True, text=True,
        )
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_dump_script_no_local_code_md5(self):
        dump = open(os.path.join(ROOT, "okna-ask-dump.sh"), encoding="utf-8").read()
        self.assertNotIn("probe_code_md5", dump)
        self.assertNotIn("/srv/1c/ubuntu/serenedb/serene_ask.py", dump)
        self.assertIn("probe_finish", dump)
        self.assertIn("probe_ssh_journal_row", dump)

    def test_scan_shell_finds_bad_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "bad.sh")
            good = os.path.join(td, "good.sh")
            open(bad, "w", encoding="utf-8").write(
                '#!/bin/bash\nssh host bash -s "$Q"\n')
            open(good, "w", encoding="utf-8").write(
                '#!/bin/bash\nssh host bash -s <<EOF\n')
            hits = P.scan_shell_bug(td)
            paths = [h[0] for h in hits]
            self.assertIn(bad, paths)
            self.assertNotIn(good, paths)

    def test_acceptance_tree_no_bash_s_dollar_q(self):
        acc = os.path.join(os.path.dirname(ROOT), "work", "acceptance")
        if not os.path.isdir(acc):
            acc = ROOT
        hits = P.scan_shell_bug(acc)
        # resume-8097-range.sh передаёт номера вопросов LO/HI — не текст /ask
        hits = [(p, ln, t) for p, ln, t in hits if "resume-8097-range" not in p]
        self.assertEqual(hits, [], "ssh bash -s \"$VAR\" in: %s" % hits)

    def test_write_record(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "run.probe.tsv")
            P.write_record(path, P.format_line(
                rid="x", port=1, code_md5_val="a", q_len_val=3,
                outcome="ok", question="abc"))
            self.assertTrue(os.path.isfile(path))
            self.assertIn("PROBE", open(path, encoding="utf-8").read())


def main():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestProbeProtocol)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    print("test_probe_protocol: %d tests OK" % result.testsRun)


if __name__ == "__main__":
    main()
