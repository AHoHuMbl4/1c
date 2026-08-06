@echo off
rem =====================================================================
rem  Golden-проба формата CSV агента пакетного транспорта (PACKET_CONTRACT К5).
rem  Агент разворачивает сохранённые страницы OData (--flatten), результат
rem  сверяется ПОБАЙТНО (fc /b) с эталоном Python-версии (reference\*.csv).
rem  Запуск: из этого каталога, packet-agent.exe — в ..\..\windows\packet-agent\build\
rem          или путь первым аргументом: probe.cmd C:\path\packet-agent.exe
rem =====================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "AGENT=%~1"
if "%AGENT%"=="" set "AGENT=%~dp0..\..\windows\packet-agent\build\packet-agent.exe"
if not exist "%AGENT%" (
  echo [ОШИБКА] не найден агент: %AGENT%
  echo          соберите windows\packet-agent\build.cmd или передайте путь аргументом
  exit /b 2
)

if not exist out mkdir out
set FAIL=0

rem Снимок $metadata лежит сжатым (fixtures\metadata.xml.zst, 20 МБ -> ~0,5 МБ).
rem Перед прогоном распаковываем рядом — агент читает metadata.xml возле страниц.
set "ZSTD=zstd.exe"
where %ZSTD% >nul 2>&1
if errorlevel 1 set "ZSTD=C:\1c\packet\zstd.exe"
if not exist fixtures\metadata.xml (
  if not exist fixtures\metadata.xml.zst (
    echo [ОШИБКА] нет ни fixtures\metadata.xml, ни fixtures\metadata.xml.zst
    exit /b 2
  )
  if not exist "%ZSTD%" (
    echo [ОШИБКА] не найден zstd для распаковки снимка: %ZSTD%
    exit /b 2
  )
  "%ZSTD%" -d -q -f fixtures\metadata.xml.zst -o fixtures\metadata.xml
  if errorlevel 1 (
    echo [ОШИБКА] не удалось распаковать fixtures\metadata.xml.zst
    exit /b 2
  )
)

for %%F in (fixtures\*.page1.json) do (
  set "E=%%~nF"
  set "E=!E:.page1=!"
  echo --- !E!
  "%AGENT%" --flatten "%%F" "!E!" "out\!E!.csv"
  if errorlevel 1 (
    echo [ОШИБКА] агент вернул ошибку на !E!
    set FAIL=1
  ) else (
    fc /b "out\!E!.csv" "reference\!E!.csv" >nul
    if errorlevel 1 (
      echo [РАСХОЖДЕНИЕ] !E!: CSV агента отличается от эталона
      echo   fc /b out\!E!.csv reference\!E!.csv   ^(показать байты^)
      set FAIL=1
    ) else (
      echo [OK] !E!: байт-в-байт совпал с эталоном
    )
  )
)

echo.
if "%FAIL%"=="0" (
  echo [ИТОГ] golden-проба ПРОЙДЕНА: формат CSV совпадает с poc_load_entity.py
) else (
  echo [ИТОГ] golden-проба НЕ ПРОЙДЕНА — дефект ФОРМАТА ^(К5^), агент в бой не выкатывается
)
exit /b %FAIL%
