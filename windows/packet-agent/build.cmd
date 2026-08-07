@echo off
rem =====================================================================
rem  Сборка packet-agent.exe — агент пакетного транспорта Windows -> Ubuntu.
rem  БЕЗ сторонних зависимостей: компилятор входит в состав .NET Framework.
rem  По образцу windows\odata-setup\build.cmd.
rem =====================================================================
setlocal
chcp 65001 >nul 2>&1

set "CSC=%windir%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%windir%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [ОШИБКА] Не найден компилятор C^# ^(csc.exe^) из .NET Framework 4.
  echo          Установите .NET Framework 4.8 и повторите.
  exit /b 1
)

rem Сборка кладётся в build\ (в .gitignore): локальная сборка не конфликтует
rem с репозиторием при git pull.
if not exist "%~dp0build" mkdir "%~dp0build"
set "OUT=%~dp0build\packet-agent.exe"

echo Компилятор: %CSC%
echo Выход:      %OUT%
echo.

"%CSC%" /nologo /target:exe /platform:anycpu /optimize+ /langversion:5 ^
  /out:"%OUT%" ^
  /reference:System.dll ^
  /reference:System.Core.dll ^
  /reference:System.Web.Extensions.dll ^
  "%~dp0src\PacketAgent.cs"

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Сборка не удалась.
  exit /b 1
)

echo.
echo [OK] Собрано: %OUT%
for %%F in ("%OUT%") do echo      размер: %%~zF байт
"%OUT%" --version
echo.
echo Golden-проба формата CSV:  work\packet\golden\probe.cmd "%OUT%"
endlocal
