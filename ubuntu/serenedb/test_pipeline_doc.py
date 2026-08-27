#!/usr/bin/env python3
"""Оффлайн-замок docs/PIPELINE.md: каждая ссылка «путь · якорь (~N)» резолвится.

Без сети, БД и сервисов. Не импортирует serene_ask. Падает, если схема протухла:
файл исчез, якорь не найден, или остались голые path:lineno без якоря.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DOC = ROOT / "docs" / "PIPELINE.md"

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:240]) if detail else "")


# Полная ссылка: `path` · якорь `fragment` (~N)
FULL_RE = re.compile(
    r"`([^`]+)`\s*·\s*якорь\s*`([^`]+)`\s*\(~(\d+)\)"
)
# Продолжение в той же ячейке: ; · якорь `fragment` (~N)
CONT_RE = re.compile(
    r";\s*·\s*якорь\s*`([^`]+)`\s*\(~(\d+)\)"
)
# Голый path:lineno в бэктиках (регрессия к протухающему формату)
BARE_RE = re.compile(
    r"`((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:py|sh|cs|sql|timer|service|md|json|toml|cmd|ps1)):\d+`"
)

t("PIPELINE.md exists", DOC.is_file(), str(DOC))
text = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
t("doc non-empty", len(text) > 500, len(text))
t("doc declares anchor format", "· якорь `" in text and "test_pipeline_doc.py" in text)

links: list[tuple[str, str, int, int]] = []  # path, anchor, line_hint, pos
for m in FULL_RE.finditer(text):
    links.append((m.group(1), m.group(2), int(m.group(3)), m.start()))

# Continuations inherit path of the nearest preceding FULL (same table cell chain).
# Нельзя брать «последний link в списке»: Conts дописываются в конец и затирали бы
# более поздний FULL с большим offset в файле.
full_spans = [(m.start(), m.end(), m.group(1)) for m in FULL_RE.finditer(text)]
for m in CONT_RE.finditer(text):
    prev_path = None
    for _start, end, path in full_spans:
        if end <= m.start():
            prev_path = path
        else:
            break
    if prev_path is None:
        FAIL.append("orphan-cont")
        print("FAIL-", "orphan continuation", m.group(0)[:80])
        continue
    links.append((prev_path, m.group(1), int(m.group(2)), m.start()))

t("at least 40 anchored links", len(links) >= 40, len(links))
t("no bare path:lineno links", not BARE_RE.search(text),
  BARE_RE.findall(text)[:5])

# Resolve each link
seen = set()
for path, anchor, hint, _pos in links:
    key = (path, anchor, hint)
    if key in seen:
        continue
    seen.add(key)
    fp = ROOT / path
    ok_file = fp.is_file()
    t("file %s" % path, ok_file, str(fp))
    if not ok_file:
        continue
    body = fp.read_text(encoding="utf-8", errors="replace")
    ok_anchor = anchor in body
    t("anchor in %s: %r" % (path, anchor[:60]), ok_anchor)
    if not ok_anchor:
        continue
    # справочный номер: якорь должен быть на hint±80 (сдвиг документа vs код)
    lines = body.splitlines()
    if 1 <= hint <= len(lines):
        lo = max(0, hint - 1 - 80)
        hi = min(len(lines), hint - 1 + 81)
        window = "\n".join(lines[lo:hi])
        t("hint~%d near anchor in %s" % (hint, path), anchor in window,
          "hint line=%r" % (lines[hint - 1][:120] if hint <= len(lines) else ""))
    else:
        t("hint~%d in range for %s" % (hint, path), False,
          "file has %d lines" % len(lines))

# Смысловые маркеры починки из pipeline-verify (не протухают как номера)
markers = [
    ("no false MERGE on sync arrow",
     "poc_load_entity" in text and "MERGE строк" not in text),
    ("sync not only branch B", "не «только B»" in text and "KEEP_MARKS" in text),
    ("ports 8091 and 8099 both named", ":8091" in text and ":8099" in text),
    ("classify in chat table", "classify_entities.py" in text
     and "/v1/chat/completions" in text),
    ("branch_alias present", "branch_alias" in text),
    ("need_say in serene_enough", "serene_enough.py" in text and "need_say" in text),
    ("white spot 11 closed", "закрыто" in text and "serene-index.service" in text),
    ("A/B detect via pipeline.sh -d", 'if [ -d "${ETL_ODATA_BASE:-}" ]' in text),
]
for name, cond in markers:
    t(name, cond)

print()
print("PASS %d  FAIL %d  links %d" % (PASS, len(FAIL), len(links)))
if FAIL:
    print("failed:", ", ".join(FAIL[:20]))
    sys.exit(1)
sys.exit(0)
