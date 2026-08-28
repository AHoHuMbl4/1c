#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""«Второй мозг»: отвечает на вопрос ПОИСКОМ В БАЗЕ, а не загрузкой схемы в модель.

Контракт намеренно совпадает с braine (`POST /ask` -> {kind, text, sources}), чтобы
переключение OpenClaw было обратимым одной строкой окружения (BRAINE_URL).

Пайплайн (docs/TARGET_ARCHITECTURE.md):

    вопрос
      │
      ├─ 1. РАЗБОР НАМЕРЕНИЯ — один вызов модели, которая видит ТОЛЬКО текст вопроса.
      │     Ни схемы, ни данных, ни имён таблиц в промте нет. На выходе — структура:
      │     что искать словами, какой порог по сумме, какой период, что хотят (список/сумма).
      │
      ├─ 2. ПОИСК В SereneDB — BM25 по словам вопроса + вектор по смыслу, а условия
      │     по числу и дате накладываются предикатами по INCLUDE-колонкам индекса.
      │
      ├─ 3. СЧЁТ В БАЗЕ — count/sum по всему найденному множеству, не по куску.
      │     Именно это отличает нас от чанкового RAG: он суммирует найденный фрагмент
      │     и уверенно выдаёт часть за целое (замер: docs/BENCH_BRAINE_VS_SERENE.md).
      │
      ├─ 4. ФОРМУЛИРОВКА — модель получает вопрос + строки результата (единицы строк).
      │
      └─ 5. ГЕЙТ — КОДОМ: каждое число из ответа обязано встречаться в результате запроса.
            Промт-правила не считаются защитой (требование владельца).

Env: SERENEDB_DSN, DEEPSEEK_*, ALIBABA_* (см. /etc/1c-mcp-reports.env), ASK_TOKEN.
Только stdlib.
"""
from ask._bootstrap import combined_source, load_all, zone_paths

load_all(globals())
SOURCE_PATHS = [str(p) for p in zone_paths()]


def ask_source() -> str:
    """Полный исходник ask (все зоны) — для офлайн-замков, читавших open(__file__)."""
    from ask._bootstrap import combined_source as _cs

    return _cs()


del load_all, combined_source, zone_paths

if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
