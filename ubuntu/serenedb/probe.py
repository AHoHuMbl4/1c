#!/usr/bin/env python3
"""Тест-зонд аналитики: NL-вопрос -> run_report (реальный путь NL->SQL->validate->exec).
Только ЧТЕНИЕ. Печатает JSON результата (question/sql/error?/columns/rows/n). Зовётся probe.sh.
"""
import json
import sys

import serene_report as R

if len(sys.argv) < 2:
    sys.exit("usage: probe.py '<вопрос>'")
print(json.dumps(R.run_report(sys.argv[1]), ensure_ascii=False, indent=2))
