# Сборка форка MCP Toolkit без GUI (headless)

Форк вырезает `execute_code` (см. `patch_execute_code.py` — почему). Собирается конфигуратором 1С в пакетном режиме, GUI не нужен. Проверено на стенде 2026-07-22, платформа 8.3.27.1786.

## Шаги (на машине с 1С)

```bash
# 1. Свежий клон upstream (GPL-3.0)
git clone https://github.com/ROCTUP/1c-mcp-toolkit.git

# 2. Патч модуля формы (заглушить обе функции исполнения кода)
python3 patch_execute_code.py "1c-mcp-toolkit/1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl"
#   -> "patched 2 functions"
```

```powershell
# 3. Пустая база для сборки (конфигуратору нужен контекст базы + лицензия)
$exe = 'C:\Program Files (x86)\1cv8\8.3.27.1786\bin\1cv8.exe'
& $exe CREATEINFOBASE 'File="C:\1c\bases\bld"' /DisableStartupDialogs

# 4. Сборка .epf из файлов-исходников (корневой XML — MCPToolkit.xml)
& $exe DESIGNER /F"C:\1c\bases\bld" /DisableStartupDialogs `
  /LoadExternalDataProcessorOrReportFromFiles `
  "<src>\1c\MCPToolkit\MCPToolkit.xml" `
  "C:\1c\distr\MCP_Toolkit_FORK.epf" `
  /Out "C:\1c\logs\build_fork.log"
#   лог: "Загрузка завершена" ; на выходе MCP_Toolkit_FORK.epf (~1.8 MB)
```

## Проверка результата
- Заголовок `.epf` — сигнатура контейнера 1С `FF FF FF 7F` (валидная обработка).
- Живой тест (после переоткрытия форка в 1С и запуска сервера): прямой `tools/call` к `execute_code` → `{"success": false, "error": "Неизвестный инструмент: execute_code"}`; `execute_query` — работает как прежде.

## NB
- `/LoadExternalDataProcessorOrReportFromFiles <исходник-xml> <выходной-epf>` — порядок: сперва источник, потом результат.
- Пересобирать при апдейте upstream; патчер сам проверяет, что нашёл ровно 2 целевые функции (иначе upstream изменился — ревью).
- Форк не зависит от UI-тумблера execute_code: код заглушён на уровне функций, тумблер может быть в любом положении.
