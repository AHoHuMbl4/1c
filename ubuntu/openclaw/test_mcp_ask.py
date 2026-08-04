#!/usr/bin/env python3
"""Оффлайн-проба моста: БЕЗ сервиса ответов, БЕЗ сети, БЕЗ модели.

Мост — часть шага 7: это последняя точка, где внутреннее становится клиентским. Своей
пробы у него не было, а живой прогон 04.08 показал, зачем она нужна: боту уходили
внутренние счётчики под своими именами (`reranked_of=1502`), и человек услышал «всего в
базе 1 502 документа» — числа законные, сказанное про них ложное.

Запуск тем же питоном, которым мост исполняется (в системном `mcp` нет):
    /opt/openclaw-mcp/venv/bin/python ubuntu/openclaw/test_mcp_ask.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_URL", "http://127.0.0.1:1/ask")
os.environ.setdefault("ASK_TOKEN", "test")

import mcp_ask as M  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


# ---------------------------------------------- F251: имена, которые можно произнести
named = M._named_partial({"reranked_of": 1502, "reranked": 60})
t("F251: внутренние имена заменены на произносимые",
  named == {"record_kinds_considered": 1502, "record_kinds_kept_after_ranking": 60})
t("F251: числа при этом не меняются — гейт сверяет их с ответом инструмента",
  set(named.values()) == {1502, 60})

unknown = M._named_partial({"reranked_of": 7, "нечто_новое": 42})
t("F251: неизвестный ключ числом наружу не идёт",
  42 not in unknown.values() and "нечто_новое" not in unknown)
t("F251: но и не пропадает молча — сказано, что отсечка была (п. 13)",
  unknown.get("other_limits_applied") == 1)

t("F251: пустая пометка не рождает блок",
  M._named_partial({}) == {} and M._named_partial(None) == {})
t("F251: значения None отбрасываются (их нечего говорить)",
  M._named_partial({"reranked": None}) == {})

# ------------------------------------------------------- блок для модели собирается
block = M._kv_block("PARTIAL", M._named_partial({"reranked_of": 1502, "reranked": 60}))
t("PARTIAL: блок машинный, без прозы, с обоими числами",
  block.startswith("PARTIAL:") and "record_kinds_considered=1502" in block
  and "record_kinds_kept_after_ranking=60" in block)
t("PARTIAL: целое печатается без хвоста .0 — иначе гейт сверяет «60.0» с «60»",
  "=60\n" in block + "\n")

out = M._with_partial("ответ", {"partial": {"reranked_of": 1502, "reranked": 60}})
t("PARTIAL: приписывается к ответу, а не заменяет его",
  out.startswith("ответ") and "PARTIAL:" in out)
t("PARTIAL: без пометки ответ не трогается",
  M._with_partial("ответ", {"partial": None}) == "ответ")

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
