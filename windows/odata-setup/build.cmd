@echo off
rem =====================================================================
rem  Сборка setup-1c-odata.exe
rem  БЕЗ сторонних зависимостей: компилятор входит в состав .NET Framework,
rem  который есть на любой современной Windows. Ничего ставить не нужно.
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

if not exist "%~dp0dist" mkdir "%~dp0dist"
set "OUT=%~dp0dist\setup-1c-odata.exe"

echo Компилятор: %CSC%
echo Выход:      %OUT%
echo.

"%CSC%" /nologo /target:exe /platform:anycpu /optimize+ /langversion:5 ^
  /win32manifest:"%~dp0src\app.manifest" ^
  /out:"%OUT%" ^
  /reference:System.dll ^
  /reference:System.Core.dll ^
  /reference:System.Xml.dll ^
  /reference:System.Xml.Linq.dll ^
  /reference:System.IO.Compression.dll ^
  /reference:System.IO.Compression.FileSystem.dll ^
  "%~dp0src\Sys.cs" "%~dp0src\Steps.cs" "%~dp0src\Program.cs"

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Сборка не удалась.
  exit /b 1
)

echo.
echo [OK] Собрано: %OUT%
for %%F in ("%OUT%") do echo      размер: %%~zF байт
certutil -hashfile "%OUT%" SHA256 2>nul | findstr /r "^[0-9a-f]"
echo.
echo Проверить, ничего не меняя:  "%OUT%" --check
echo Справка:                     "%OUT%" --help
endlocal
