#!/usr/bin/env python3
"""
CLI над serene_report — умный NL->запрос по витрине SereneDB.
Запуск:  python3 report_query.py "топ-5 городов по числу банков"
Env: см. serene_report.py (SERENEDB_DSN, DEEPSEEK_API_KEY).
"""
import sys
from serene_report import run_report, format_table


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: report_query.py "<вопрос>"')
    res = run_report(sys.argv[1])
    print(f"Вопрос: {res['question']}")
    print(format_table(res))


if __name__ == "__main__":
    main()
