#!/usr/bin/env python3
"""
Форк MCP Toolkit (ROCTUP, GPL-3.0) для read-only «второго мозга».

Зачем: на стенде доказано (2026-07-22), что UI-тумблер отключения execute_code —
косметика: он убирает инструмент из tools/list, но НЕ блокирует вызов. Отключённый
execute_code продолжает исполнять произвольный BSL-код при прямом tools/call
(вернул 111*111=12321). Причина в коде: диспетчер вызывает ВыполнитьКод() без
проверки флага ИнструментВключен_ExecuteCode (флаг проверяется только при построении
схемы инструментов).

Что делает патч: вставляет ранний отказ в ОБЕ функции-исполнителя пользовательского
кода — ВыполнитьКод (серверный путь) и ВыполнитьКодНаКлиенте (клиентский путь). После
этого никакой путь диспетчеризации не может исполнить код — execute_code всегда
возвращает «Неизвестный инструмент: execute_code» (формат настоящего отказа тулкита).

Прочие Вычислить(...) в модуле НЕ трогаются — это внутренняя интроспекция метаданных
(«Метаданные.» + имя), не пользовательский код.

Использование:
    python3 patch_execute_code.py <путь к Forms/Форма/Ext/Form/Module.bsl>

Источник (upstream, клонировать свежим при пересборке):
    https://github.com/ROCTUP/1c-mcp-toolkit  (файл 1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl)
Сборка .epf из пропатченного дерева — см. BUILD.md.
"""
import sys

MARKER = "ФОРК read-only: execute_code вырезан"
REFUSAL = ('\tВозврат Новый Структура("success, error", Ложь, '
           '"Неизвестный инструмент: execute_code"); // ' + MARKER)
TARGETS = ("Функция ВыполнитьКод(Код)", "Функция ВыполнитьКодНаКлиенте(Код)")


def main(path):
    src = open(path, encoding="utf-8-sig").read()
    if MARKER in src:
        print("already patched")
        return
    out, patched = [], 0
    for line in src.split("\n"):
        out.append(line)
        if line.strip() in TARGETS:
            out.append(REFUSAL)
            patched += 1
    if patched != 2:
        raise SystemExit(f"expected 2 target functions, patched {patched} — upstream changed, review")
    open(path, "w", encoding="utf-8-sig").write("\n".join(out))
    print(f"patched {patched} functions")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
